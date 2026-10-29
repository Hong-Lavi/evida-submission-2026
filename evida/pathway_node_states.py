"""Bounded queries on a saved CARNIVAL LP; zero contrast state is not a knockout."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import time

from . import pathway_lp as lp

TEXT = {'type': 'string', 'minLength': 1}
SCHEMA = {'type': 'object', 'properties': {'artifact_id': TEXT,
    'node_ids': {'type': 'array', 'items': TEXT, 'minItems': 1, 'maxItems': 2}, 'reason': TEXT},
    'required': ['artifact_id', 'node_ids', 'reason'], 'additionalProperties': False}
TOLERANCE = 1e-6
SOLVER_SECONDS = 120
OUTER_SECONDS = 180
RAW_FIELDS = {'solver_package', 'solver_records'}
LIMITS = ['0은 모델의 변화 상태 미사용이며, KO나 약물 효과를 뜻하지 않습니다.',
          '선택 요소를 각각 따로 제한합니다. 두 요소를 동시에 제거하는 시험이 아닙니다.',
          '입력은 추정 TF 부호와 오차 가중치입니다. 점수 크기의 재현이나 실제 단백질 활성 검증이 아닙니다.',
          '가상 시작점은 원 문제의 자유도를 유지합니다. 실제 처치를 고정한 개입 비교가 아닙니다.',
          '시간초과나 대안 미반환은 생물학적 부재·필수성 판정이 아닙니다.']


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def text_sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def unavailable(reason='이 결과에는 다시 질의할 원 계산 묶음이 보존되지 않았습니다. 기존 경로는 그대로 읽을 수 있습니다.'):
    return {'supported': False, 'status': 'solver_package_unavailable', 'reason': reason,
            'selectable_nodes': []}


def presentation(value):
    """Default readers never expand solver bytes, even if author tables are absent."""
    if isinstance(value, list):
        return [presentation(item) for item in value]
    if not isinstance(value, dict):
        return value
    out = {key: presentation(item) for key, item in value.items() if key not in RAW_FIELDS}
    if value.get('semantic_type') == 'conditional_pathway_hypotheses':
        out.setdefault('solver_package_summary', unavailable())
    return out


def solver_status(log, returncode=0, outer_timeout=False):
    if outer_timeout:
        return 'outer_wall_timeout'
    if returncode != 0:
        return 'process_failure'
    if re.search(r'Result - (Problem proven infeasible|Linear relaxation infeasible)', log) or re.search(r'^Problem is infeasible', log, re.M):
        return 'infeasible_reported'
    if 'Result - Optimal solution found (within gap tolerance)' in log:
        return 'optimal_within_relative_gap'
    if 'Result - Optimal solution found' in log:
        return 'optimal_reported'
    if 'Result - Stopped on time limit' in log:
        return 'solver_time_limit'
    return 'unclassified_solver_termination'


def solver_review(log, returncode=0, outer_timeout=False):
    def number(label):
        values = re.findall(r'^' + re.escape(label) + r':\s*([-+0-9.eE]+)', log, re.M)
        value = float(values[-1]) if values else None
        if value is not None and not math.isfinite(value):
            raise ValueError('유한한 solver 수치가 필요합니다.')
        return value
    objective, lower = number('Objective value'), number('Lower bound')
    return {'termination': solver_status(log, returncode, outer_timeout),
            'reported_objective': objective, 'final_lower_bound': lower, 'final_gap': number('Gap'),
            'final_absolute_gap': None if objective is None or lower is None else objective - lower,
            'ratio_gap_setting': 0.0001, 'search_completed_reported': 'Cbc0001I Search completed' in log,
            'threads_option_supported': 'No match for threads' not in log,
            'certificate_scope': 'Numerical CBC report; no formal exact-arithmetic proof. Missing final bound/gap stays null.'}


def objective(check):
    return {'total': check['objective'], 'weighted_sign_error': check['weighted_measurement_error'],
            'state_penalty': check['nonzero_state_penalty']}


def measurements(solution, mapping):
    return [{'node': r['nodes'], 'input_score': float(r['value']),
             'target_sign': 1 if float(r['value']) > 0 else -1,
             'fitted_sign': solution[r['nodesVars']], 'absolute_error': solution[r['measurementsVars']],
             'weight': abs(float(r['value']))} for r in mapping['measurements']]


def graph(solution, mapping, parsed):
    value = lp.biological_graph(solution, mapping)
    value.pop('measurements')
    root = next((r for r in mapping['nodes'] if r['nodes'] == 'Perturbation'), None)
    value['artificial_root'] = None if root is None else {'node': 'Perturbation',
        'state': solution[root['nodesVars']],
        # This describes an explicitly unfixed source sign, not proof that both
        # signs are feasible under every other constraint.
        'free_in_model': not any(set(expr) == {root['nodesActStateVars']} and relation == '='
                                 for _, expr, relation, _ in parsed['constraints'])
                         and parsed['bounds'][root['nodesActStateVars']][0] != parsed['bounds'][root['nodesActStateVars']][1]}
    return value


def eligible(mapping, parsed, solution):
    measured = {row['nodes'] for row in mapping['measurements']}
    zero_fixed = {name for name, bounds in parsed['bounds'].items() if bounds == (0., 0.)}
    zero_fixed.update(next(iter(expr)) for _, expr, relation, rhs in parsed['constraints']
                      if relation == '=' and rhs == 0 and len(expr) == 1 and next(iter(expr.values())) != 0)
    return [row for row in mapping['nodes'] if row['nodes'] != 'Perturbation'
            and row['nodes'] not in measured and row.get('nodesType') == ''
            and abs(solution[row['nodesVars']]) > TOLERANCE
            and row['nodesActStateVars'] in zero_fixed]


def _checked_package(source):
    if source.get('semantic_type') != 'conditional_pathway_hypotheses':
        raise ValueError('보존된 경로 계산 결과가 필요합니다.')
    packet = source.get('solver_package')
    if not isinstance(packet, dict) or packet.get('schema_version') != 1:
        raise ValueError(unavailable()['reason'])
    expected = packet.get('sha256')
    if expected != digest({key: value for key, value in packet.items() if key != 'sha256'}):
        raise ValueError('원 계산 묶음 해시가 다릅니다.')
    for name in ['lp_text', 'solution_csv', 'solver_log', 'input_json']:
        if not isinstance(packet.get(name), str) or text_sha(packet[name]) != packet.get(name + '_sha256'):
            raise ValueError('원 계산 파일 해시가 다릅니다: ' + name)
    if digest(packet['mapping']) != packet['mapping_sha256']:
        raise ValueError('원 변수지도 해시가 다릅니다.')
    if packet['source_binding'] != source.get('source_binding'):
        raise ValueError('원 자료와 계산 묶음의 source 결속이 다릅니다.')
    binding = packet['source_binding']
    if not re.fullmatch('[a-f0-9]{64}', binding.get('sha256', '')) or not binding.get('artifact_id'):
        raise ValueError('원 source artifact SHA가 없습니다.')
    if packet['versions'] != source.get('versions'):
        raise ValueError('원 저자 실행 판본이 다릅니다.')
    if packet['mapping'].get('versions') != packet['versions'] or packet['resource_fingerprint'] != source.get('resource_fingerprint'):
        raise ValueError('원 변수지도 또는 실행 자원의 결속이 다릅니다.')
    options = packet['solver_options']
    if any(options.get(key) != expected for key, expected in
           [('solver', 'cbc'), ('timelimit', 120), ('poolrelGap', 0.0001), ('threads', 1)]):
        raise ValueError('지원하는 원 solver 설정과 다릅니다. 설정을 자동 교체하지 않습니다.')
    inp = json.loads(packet['input_json'])
    measured = [(r['source'], float(r['score'])) for r in source['selected_inferred_observations']]
    if measured != [(r['source'], float(r['score'])) for r in inp['selected_inferred_observations']]:
        raise ValueError('원 관측 입력과 저장 결과가 다릅니다.')
    if sorted(measured) != sorted((r['nodes'], float(r['value'])) for r in packet['mapping']['measurements']):
        raise ValueError('관측과 변수지도가 다릅니다.')
    if inp['source_conditions'] != source.get('source_conditions') or inp['requested_conditions'] != source.get('conditions'):
        raise ValueError('원 계산 조건이 다릅니다.')
    parsed = lp.parse_lp_text(packet['lp_text'])
    solution = lp.read_solution_text(packet['solution_csv'])
    lp.validate_mapping(packet['mapping'], parsed)
    check = lp.validate(parsed, solution, TOLERANCE)
    if not check['valid'] or abs(check['objective_decomposition_residual']) > TOLERANCE:
        raise ValueError('원 기준 해가 전체 primal 검사를 통과하지 못했습니다.')
    report = solver_review(packet['solver_log'])
    if report['termination'] != 'optimal_reported' or report['reported_objective'] is None:
        raise ValueError('기준 목적값의 최적성 보고를 확인하지 못했습니다.')
    if abs(report['reported_objective'] - check['objective']) > TOLERANCE:
        raise ValueError('기준 목적값의 로그와 전체 해가 다릅니다.')
    value = graph(solution, packet['mapping'], parsed)
    author = source.get('author_result', {})
    if not isinstance(author.get('sifAll'), list) or len(author['sifAll']) != 1:
        raise ValueError('이 질의는 하나의 보존 기준 해를 지원합니다.')
    actual = {(e['source'], e['sign'], e['target']) for e in value['edges'] + value['artificial_edges']}
    expected_edges = {(r['Node1'], int(r['Sign']), r['Node2']) for r in author['sifAll'][0]}
    if actual != expected_edges:
        raise ValueError('원 full solution과 반환 그래프가 다릅니다.')
    expected_nodes = {r['Nodes']: r['Activity'] for r in author['attributesAll'][0] if r['Nodes'] != 'Perturbation' and r['Activity'] != 0}
    if {r['node']: r['state'] for r in value['nodes']} != expected_nodes:
        raise ValueError('원 full solution과 반환 노드 상태가 다릅니다.')
    return packet, parsed, solution, check, report, value


def checked_package(source):
    try:
        return _checked_package(source)
    except (KeyError, IndexError, TypeError, AssertionError, OverflowError) as error:
        raise ValueError('원 계산 묶음의 형식 또는 완전성을 확인할 수 없습니다.') from error


def package_summary(source):
    packet, parsed, solution, check, _, value = checked_package(source)
    return {'supported': True, 'status': 'ready', 'package_sha256': packet['sha256'],
            'selectable_nodes': [{'node_id': r['nodes'], 'state': solution[r['nodesVars']]}
                                 for r in eligible(packet['mapping'], parsed, solution)],
            'baseline_objective': check['objective'], 'observation_count': len(packet['mapping']['measurements']),
            'variable_count': len(solution), 'constraint_count': len(parsed['constraints']),
            'artificial_source_free': (value['artificial_root'] or {}).get('free_in_model')}


def attach_package(result, work, source_binding, fingerprint):
    """Only called after our native author worker; never scans another attempt."""
    try:
        work = Path(work)
        candidates = {key: list((work / 'solver').glob(pattern)) for key, pattern in
                      [('lp', 'lpFile_*.lp'), ('solution', 'result_*.csv'), ('mapping', 'parsedData_*.RData')]}
        if any(len(items) != 1 for items in candidates.values()):
            raise ValueError('원 문제 파일을 하나로 확인하지 못했습니다.')
        lp_path, solution_path, rdata_path = (candidates[k][0] for k in ['lp', 'solution', 'mapping'])
        suffix = lp_path.stem.removeprefix('lpFile_')
        if solution_path.stem != 'result_' + suffix or rdata_path.stem != 'parsedData_' + suffix:
            raise ValueError('원 LP·변수지도·해의 실행 이름이 다릅니다.')
        packet = {'schema_version': 1, 'source_binding': source_binding,
                  'versions': result['versions'], 'resource_fingerprint': fingerprint,
                  'mapping': json.loads((work / 'variable-map.json').read_text()),
                  'mapping_rdata_sha256': lp.sha(rdata_path),
                  'solver_options': json.loads((work / 'solver-options.json').read_text())}
        for name, path in [('lp_text', lp_path), ('solution_csv', solution_path),
                           ('solver_log', work / 'worker.log'), ('input_json', work / 'input.json')]:
            packet[name] = path.read_bytes().decode('utf-8')
            packet[name + '_sha256'] = text_sha(packet[name])
        packet['mapping_sha256'] = digest(packet['mapping'])
        packet['sha256'] = digest(packet)
        result['source_binding'] = source_binding
        result['solver_package'] = packet
        result['solver_package_summary'] = package_summary(result)
    except (ValueError, OSError, KeyError, IndexError, TypeError, AssertionError) as error:
        result['solver_package_summary'] = unavailable('원 계산 묶음을 질의용으로 검증하지 못했습니다: ' + str(error)[:180])
    return result


def prepare(source, arguments, *, artifact_sha256=None):
    if not isinstance(source, dict) or source.get('semantic_type') != 'conditional_pathway_hypotheses':
        raise ValueError('보존된 경로 계산 결과가 필요합니다.')
    names = arguments.get('node_ids')
    if not isinstance(names, list) or not 1 <= len(names) <= 2 or any(not isinstance(n, str) or not n.strip() for n in names) or len(names) != len(set(names)):
        raise ValueError('정확한 요소 이름을 중복 없이 1–2개 선택해 주세요.')
    if not isinstance(arguments.get('reason'), str) or not arguments['reason'].strip():
        raise ValueError('선택한 요소의 변화를 확인할 이유를 적어 주세요.')
    if 'solver_package' not in source:
        return {'available': False, 'summary': unavailable()}
    packet, parsed, solution, check, review, value = checked_package(source)
    choices = {r['nodes']: r for r in eligible(packet['mapping'], parsed, solution)}
    if any(name not in choices for name in names):
        raise ValueError('기준 해의 비영점 생물학 요소 중 관측 TF·가상 시작점을 제외하고 선택해 주세요. 원 nAc=0 결속도 필요합니다.')
    return {'available': True, 'packet': packet, 'parsed': parsed, 'solution': solution,
            'nodes': [choices[name] for name in names],
            'baseline': {'objective': objective(check), 'measurements': measurements(solution, packet['mapping']),
                         'graph': value, 'solver': review},
            'source_binding': {'artifact_id': arguments['artifact_id'], 'artifact_sha256': artifact_sha256,
                               'package_sha256': packet['sha256']}}


def add_constraints(original, node):
    parsed = lp.parse_lp_text(original)
    names = {r[0] for r in parsed['constraints']}
    new = [(f'evida_query_{i}', node[key]) for i, key in enumerate(['nodesUpVars', 'nodesDownVars'], 1)]
    if any(name in names for name, _ in new):
        raise ValueError('질의 제약 이름이 원 문제와 충돌합니다.')
    ending = '\r\n' if '\r\n' in original else '\n'
    additions = ''.join(name + ': ' + variable + ' = 0' + ending for name, variable in new)
    marker = ending + 'Bounds' + ending
    if original.count(marker) != 1:
        raise ValueError('원 LP의 제약 위치를 하나로 확인하지 못했습니다.')
    changed = original.replace(marker, ending + additions + 'Bounds' + ending)
    if changed.replace(additions, '', 1) != original:
        raise ValueError('원 LP 보존을 확인하지 못했습니다.')
    return changed, [variable + ' = 0' for _, variable in new]


def compare(baseline, current, tolerance=TOLERANCE):
    delta = current['objective']['total'] - baseline['objective']['total']
    same_fit = len(current['measurements']) == len(baseline['measurements']) and all(
        a['node'] == b['node'] and abs(a['fitted_sign'] - b['fitted_sign']) <= tolerance
        and abs(a['absolute_error'] - b['absolute_error']) <= tolerance
        for a, b in zip(baseline['measurements'], current['measurements']))
    same = abs(delta) <= tolerance
    status = current['solver']['termination']
    outcome = ('same_objective_witness' if same else 'baseline_inconsistency_lower_objective' if delta < 0
               else 'higher_optimum_reported' if status == 'optimal_reported' else 'higher_incumbent_unresolved')
    return {'outcome': outcome, 'same_objective': same, 'same_observation_fit': same_fit,
            'objective_delta': delta, 'tolerance': tolerance}


def _run_solver(command, directory):
    began = time.monotonic()
    timeout = False
    with (directory / 'solver.log').open('xb') as output:
        process = subprocess.Popen(command, cwd=directory,
            env={'PATH': str(Path(command[0]).parent) + ':/usr/bin:/bin', 'LANG': 'C.UTF-8', 'TZ': 'UTC',
                 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'CUDA_VISIBLE_DEVICES': ''},
            stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            returncode = process.wait(timeout=OUTER_SECONDS)
        except subprocess.TimeoutExpired:
            timeout = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            returncode = process.returncode
    return returncode, timeout, time.monotonic() - began


def run(source, arguments, root, work, source_sha256):
    bundle = prepare(source, arguments, artifact_sha256=source_sha256)
    output = {'status': 'unassessed', 'semantic_type': 'conditional_pathway_node_state_queries',
              'title': '선택 요소의 변화 없이 설명되는 경로', 'reason': arguments['reason'],
              'scope': {'operation': 'separate_zero_contrast_state_queries', 'biological_intervention': False,
                        'artificial_source_free': None}, 'source_binding': bundle.get('source_binding',
                        {'artifact_id': arguments['artifact_id'], 'artifact_sha256': source_sha256, 'package_sha256': None}),
              'baseline': None, 'rows': [], 'summary': {'planned_queries': len(arguments['node_ids']),
              'attempted_queries': 0, 'validated_witnesses': 0}, 'limits': LIMITS, 'solver_records': []}
    if not bundle['available']:
        output['rows'] = [{'node_id': n, 'status': 'unassessed', 'reason': bundle['summary']['reason'],
                           'comparison': {'outcome': 'solver_package_unavailable', 'same_objective': None,
                                          'same_observation_fit': None}} for n in arguments['node_ids']]
        return output
    from .pathway_hypotheses import verified_resources
    config, fingerprint = verified_resources(Path(root))
    if fingerprint['files']['cbc'] != bundle['packet']['resource_fingerprint']['files']['cbc']:
        raise ValueError('보존된 기준 문제와 현재 CBC 판본 해시가 다릅니다. 다른 solver로 바꾸지 않습니다.')
    directory = Path(work)
    directory.mkdir(exist_ok=False)
    output['baseline'] = bundle['baseline']
    output['scope']['artificial_source_free'] = (bundle['baseline']['graph']['artificial_root'] or {}).get('free_in_model')
    stop = None
    for index, node in enumerate(bundle['nodes'], 1):
        row = {'node_id': node['nodes'], 'status': 'unassessed', 'attempt_count': 0}
        output['rows'].append(row)
        if stop:
            row.update(reason=stop, solver={'termination': 'not_started_after_stop'},
                       comparison={'outcome': 'unresolved_not_attempted', 'same_objective': None, 'same_observation_fit': None})
            continue
        folder = directory / f'query-{index}'
        folder.mkdir()
        record = {'node_id': node['nodes']}
        try:
            query_text, constraints = add_constraints(bundle['packet']['lp_text'], node)
            query_path, solution_path = folder / 'query.lp', folder / 'solution.csv'
            query_path.write_bytes(query_text.encode('utf-8'))
            command = [config['files']['cbc']['path'], '-import', str(query_path), '-seconds', str(SOLVER_SECONDS),
                       '-ratioGap', '0.0001', '-threads', '1', '-solve', '-printi', 'csv', '-solution', str(solution_path)]
            row.update(attempt_count=1, constraints=constraints, lp_sha256=text_sha(query_text))
            output['summary']['attempted_queries'] += 1
            record.update(lp_text=query_text, lp_sha256=text_sha(query_text), command=command)
            code, timeout, elapsed = _run_solver(command, folder)
            log = (folder / 'solver.log').read_bytes().decode('utf-8')
            review = solver_review(log, code, timeout)
            review.update(elapsed_seconds=elapsed, solver_seconds=SOLVER_SECONDS, outer_seconds=OUTER_SECONDS,
                          returncode=code, outer_timeout=timeout)
            row['solver'] = review
            record.update(solver_log=log, solver_log_sha256=text_sha(log))
            if solution_path.exists():
                record['solution_csv'] = solution_path.read_bytes().decode('utf-8')
                record['solution_csv_sha256'] = text_sha(record['solution_csv'])
            if solution_path.exists() and review['termination'] != 'infeasible_reported':
                solution = lp.read_solution_text(record['solution_csv'])
                parsed = lp.parse_lp_text(query_text)
                check = lp.validate(parsed, solution, TOLERANCE)
                row['validation'] = check
                if not check['valid'] or abs(check['objective_decomposition_residual']) > TOLERANCE:
                    raise ValueError('반환 해가 전체 primal 검사를 통과하지 못했습니다.')
                if any(abs(solution[node[key]]) > TOLERANCE for key in ['nodesVars', 'nodesUpVars', 'nodesDownVars', 'nodesActStateVars']):
                    raise ValueError('질의한 노드가 0 변화 상태가 아닙니다.')
                reported = review['reported_objective']
                if reported is not None and abs(reported - check['objective']) > TOLERANCE:
                    raise ValueError('실제 전체 해와 보고된 목적값이 다릅니다.')
                row.update(objective=objective(check), measurements=measurements(solution, bundle['packet']['mapping']),
                           graph=graph(solution, bundle['packet']['mapping'], parsed))
                row['comparison'] = compare(bundle['baseline'], row)
                row['state_changes'] = lp.graph_difference(bundle['baseline']['graph'], row['graph'])['node_state_changes']
                row['artificial_source_changed'] = (row['graph']['artificial_root'] != bundle['baseline']['graph']['artificial_root']
                    or row['graph']['artificial_edges'] != bundle['baseline']['graph']['artificial_edges'])
                row['status'] = 'succeeded' if review['termination'] in ('optimal_reported', 'optimal_within_relative_gap') else 'partial'
                output['summary']['validated_witnesses'] += 1
                if row['comparison']['outcome'] == 'baseline_inconsistency_lower_objective':
                    row['status'] = 'partial'
                    stop = '제한한 문제에서 더 낮은 값이 나와 기준 최적성 검토가 필요합니다.'
            else:
                row.update(status='unassessed', comparison={'outcome': 'infeasible_reported' if review['termination'] == 'infeasible_reported' else 'unresolved_no_validated_incumbent', 'same_objective': None, 'same_observation_fit': None})
            if review['termination'] not in ('optimal_reported', 'optimal_within_relative_gap', 'infeasible_reported'):
                stop = '시간제한 또는 계산 미완료입니다. 남은 질의를 자동 재시도하지 않았습니다.'
        except (ValueError, OSError, KeyError, IndexError, TypeError, AssertionError) as error:
            row.update(status='failed', reason=str(error)[:300], comparison={'outcome': 'unresolved_invalid_or_failed', 'same_objective': None, 'same_observation_fit': None})
            row.setdefault('solver', {'termination': 'process_or_validation_failure'})
            stop = '계산 또는 해 검증이 실패했습니다. 원 기록을 보존하고 남은 질의는 실행하지 않았습니다.'
            if (folder / 'solver.log').exists() and 'solver_log' not in record:
                record['solver_log'] = (folder / 'solver.log').read_text(errors='replace')
        record['receipt'] = copy.deepcopy(row)
        output['solver_records'].append(record)
        (folder / 'receipt.json').write_text(json.dumps(row, ensure_ascii=False, indent=2, allow_nan=False))
    output['status'] = 'succeeded' if all(r['status'] == 'succeeded' for r in output['rows']) else 'partial'
    return output
