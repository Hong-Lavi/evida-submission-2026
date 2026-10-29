"""Complete primal checks for the pinned CARNIVAL LP dialect and CBC solutions.

No solver, fit, download or product imports. Reject unrecognized LP syntax.
The edge export rule is checked against the saved original author output.
"""
import csv
import hashlib
import json
import io
import math
from pathlib import Path
import re

NUMBER = r'(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
SIGNED = rf'[+-]?{NUMBER}'
VARIABLE = r'[A-Za-z_][A-Za-z_0-9]*'
TOKENS = re.compile(rf'{NUMBER}|{VARIABLE}|[+-]')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expression(text):
    tokens = TOKENS.findall(text)
    assert ''.join(tokens) == re.sub(r'\s+', '', text), 'unparsed expression'
    result = {}
    index = 0
    while index < len(tokens):
        sign = 1
        if tokens[index] in ('+', '-'):
            sign = -1 if tokens[index] == '-' else 1
            index += 1
        elif index:
            raise ValueError('missing term separator')
        coefficient = 1.0
        if re.fullmatch(NUMBER, tokens[index]):
            coefficient = float(tokens[index])
            index += 1
        variable = tokens[index]
        assert re.fullmatch(VARIABLE, variable), 'expected a variable'
        result[variable] = result.get(variable, 0.0) + sign * coefficient
        index += 1
    return result


def parse_lp_text(text):
    if not isinstance(text, str) or len(text.encode()) > 64 * 1024 * 1024:
        raise ValueError('지원하는 원 LP 크기가 아닙니다.')
    result = {'constraints': [], 'bounds': {}, 'binary': set(), 'integer': set()}
    section = None
    expected = ['Minimize', 'Subject To', 'Bounds', 'Binaries', 'Generals', 'End']
    found = []
    names = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line in expected:
            section = line
            found.append(line)
            continue
        if section == 'Minimize':
            assert 'objective' not in result and line.startswith('Obj:')
            result['objective'] = expression(line.split(':', 1)[1])
        elif section == 'Subject To':
            m = re.fullmatch(rf'({VARIABLE}):\s*(.*?)\s*(<=|>=|=)\s*({SIGNED})', line)
            assert m, f'unrecognized constraint {line[:120]}'
            name, lhs, relation, rhs = m.groups()
            assert name not in names
            names.add(name)
            result['constraints'].append((name, expression(lhs), relation, float(rhs)))
        elif section == 'Bounds':
            m = re.fullmatch(rf'({SIGNED})\s*<=\s*({VARIABLE})\s*<=\s*({SIGNED})', line)
            assert m, f'unrecognized bound {line}'
            lo, variable, hi = m.groups()
            assert variable not in result['bounds']
            result['bounds'][variable] = (float(lo), float(hi))
        elif section in ('Binaries', 'Generals'):
            assert re.fullmatch(VARIABLE, line)
            result['binary' if section == 'Binaries' else 'integer'].add(line)
        else:
            raise ValueError(f'unrecognized LP section/content {line[:100]}')
    assert found == expected, found
    if not result.get('objective') or len(result['constraints']) > 1000000 or len(result['bounds']) > 200000:
        raise ValueError('지원하는 원 LP 범위를 확인해 주세요.')
    for value in result['objective'].values():
        if not math.isfinite(value):
            raise ValueError('유한한 LP 계수가 필요합니다.')
    for _, coefficients, _, rhs in result['constraints']:
        if not all(math.isfinite(v) for v in [rhs, *coefficients.values()]):
            raise ValueError('유한한 LP 제약이 필요합니다.')
    if not all(math.isfinite(v) for bound in result['bounds'].values() for v in bound):
        raise ValueError('유한한 LP 범위가 필요합니다.')
    variables = set(result['objective'])
    for _, expr, _, _ in result['constraints']:
        variables.update(expr)
    assert variables == set(result['bounds']), 'all variables need explicit bounds'
    assert result['binary'] | result['integer'] <= variables
    return result


def read_solution_text(text):
    result = {}
    with io.StringIO(text, newline='') as f:
        rows = csv.DictReader(f)
        assert rows.fieldnames == ['name', 'solution'], rows.fieldnames
        for row in rows:
            name, value = row['name'], float(row['solution'])
            assert name not in result and math.isfinite(value)
            result[name] = value
    return result


def dot(expression, solution):
    return math.fsum(c * solution[v] for v, c in expression.items())


def validate(lp, solution, tolerance):
    missing = sorted(set(lp['bounds']) - set(solution))
    extra = sorted(set(solution) - set(lp['bounds']))
    if missing or extra:
        return {'valid': False, 'missing_variables': missing, 'extra_variables': extra}
    violations = []
    max_constraint = max_bound = max_integrality = 0.0
    for name, expr, relation, rhs in lp['constraints']:
        residual = dot(expr, solution) - rhs
        violation = abs(residual) if relation == '=' else max(0.0, residual if relation == '<=' else -residual)
        max_constraint = max(max_constraint, violation)
        if violation > tolerance:
            violations.append({'kind': 'constraint', 'name': name, 'violation': violation})
    for variable, (lo, hi) in lp['bounds'].items():
        value = solution[variable]
        violation = max(0.0, lo - value, value - hi)
        max_bound = max(max_bound, violation)
        if violation > tolerance:
            violations.append({'kind': 'bound', 'name': variable, 'violation': violation})
    for variable in lp['binary'] | lp['integer']:
        value = solution[variable]
        violation = abs(value - round(value))
        if variable in lp['binary']:
            violation = max(violation, max(0.0, -value, value - 1))
        max_integrality = max(max_integrality, violation)
        if violation > tolerance:
            violations.append({'kind': 'integrality', 'name': variable, 'violation': violation})
    objective = dot(lp['objective'], solution)
    measurement = math.fsum(c * solution[v] for v, c in lp['objective'].items() if v.startswith('aD'))
    penalty = math.fsum(c * solution[v] for v, c in lp['objective'].items() if v.startswith(('nU', 'nD')))
    return {'valid': not violations, 'variables': len(solution), 'constraints_checked': len(lp['constraints']),
            'bounds_checked': len(lp['bounds']), 'integer_variables_checked': len(lp['binary'] | lp['integer']),
            'max_constraint_violation': max_constraint, 'max_bound_violation': max_bound,
            'max_integrality_violation': max_integrality, 'violations': violations,
            'objective': objective, 'weighted_measurement_error': measurement,
            'nonzero_state_penalty': penalty,
            'objective_decomposition_residual': objective - measurement - penalty}


def biological_graph(solution, mapping, tolerance=1e-6):
    state = {r['nodes']: solution[r['nodesVars']] for r in mapping['nodes']}
    nodes = [{'node': n, 'state': round(v)} for n, v in sorted(state.items())
             if n != 'Perturbation' and abs(v) > tolerance]
    edges = []
    artificial = []
    # Author export rule: a nonzero edge variable alone is insufficient.
    # Its downstream signed state must agree with its up/down implication.
    for row in mapping['edges']:
        target = state[row['Node2']]
        up, down = solution[row['edgesUpVars']], solution[row['edgesDownVars']]
        present = (abs(target - 1) <= tolerance and abs(up - 1) <= tolerance) or (
            abs(target + 1) <= tolerance and abs(down - 1) <= tolerance)
        if present:
            edge = {'source': row['Node1'], 'sign': int(row['Sign']), 'target': row['Node2']}
            (artificial if 'Perturbation' in (row['Node1'], row['Node2']) else edges).append(edge)
    sort_key = lambda r: (r['source'], r['sign'], r['target'])
    return {'nodes': nodes, 'edges': sorted(edges, key=sort_key), 'artificial_edges': sorted(artificial, key=sort_key),
            'measurements': [{'node': r['nodes'], 'input_score': float(r['value']),
                              'fitted_state': state[r['nodes']], 'absolute_difference_variable': solution[r['measurementsVars']]}
                             for r in mapping['measurements']]}


def graph_difference(reference, candidate):
    nodes = lambda g: {r['node']: r['state'] for r in g['nodes']}
    edges = lambda g: {(r['source'], r['sign'], r['target']) for r in g['edges']}
    before, after = nodes(reference), nodes(candidate)
    return {'node_state_changes': [{'node': n, 'before': before.get(n, 0), 'after': after.get(n, 0)}
                                  for n in sorted(before.keys() | after.keys()) if before.get(n, 0) != after.get(n, 0)],
            'removed_edges': [list(x) for x in sorted(edges(reference) - edges(candidate))],
            'added_edges': [list(x) for x in sorted(edges(candidate) - edges(reference))],
            'retained_edges': [list(x) for x in sorted(edges(reference) & edges(candidate))]}


def parse_lp(path):
    return parse_lp_text(Path(path).read_text())


def read_solution(path):
    return read_solution_text(Path(path).read_text())


def fixed_zero(lp, variable):
    if lp['bounds'].get(variable) == (0., 0.):
        return True
    return any(relation == '=' and rhs == 0 and set(coefficients) == {variable}
               and coefficients[variable] != 0
               for _, coefficients, relation, rhs in lp['constraints'])


def validate_mapping(mapping, lp):
    if not isinstance(mapping, dict):
        raise ValueError('원 변수지도가 없습니다.')
    groups = ['nodes', 'edges', 'measurements']
    if not all(isinstance(mapping.get(k), list) and mapping[k] for k in groups):
        raise ValueError('전체 원 노드·간선·관측 지도가 필요합니다.')
    if len(mapping['measurements']) > 12:
        raise ValueError('관측 범위가 이 경로 도구와 다릅니다.')
    names, variables = set(), set()
    equalities = {tuple(sorted(expr.items())) for _, expr, relation, rhs in lp['constraints']
                  if relation == '=' and rhs == 0}
    constraints = {(tuple(sorted(expr.items())), relation, rhs)
                   for _, expr, relation, rhs in lp['constraints']}
    for row in mapping['nodes']:
        name = row.get('nodes')
        if not isinstance(name, str) or not name or name in names:
            raise ValueError('원 노드 이름이 비어 있거나 중복됩니다.')
        names.add(name)
        keys = ['nodesVars', 'nodesUpVars', 'nodesDownVars', 'nodesActStateVars', 'nodesDistanceVars']
        for key in keys:
            variable = row.get(key)
            if not isinstance(variable, str) or variable not in lp['bounds'] or variable in variables:
                raise ValueError('원 노드 변수 결속이 올바르지 않습니다.')
            variables.add(variable)
        coupled = {row['nodesUpVars']: 1., row['nodesDownVars']: -1.,
                   row['nodesActStateVars']: 1., row['nodesVars']: -1.}
        if tuple(sorted(coupled.items())) not in equalities:
            raise ValueError('원 노드 상태 결합식을 확인할 수 없습니다.')
    for row in mapping['edges']:
        if row.get('Node1') not in names or row.get('Node2') not in names or row.get('Sign') not in (-1, 1):
            raise ValueError('원 간선 지도가 올바르지 않습니다.')
        for key in ['edgesUpVars', 'edgesDownVars']:
            variable = row.get(key)
            if not isinstance(variable, str) or variable not in lp['bounds'] or variable in variables:
                raise ValueError('원 간선 변수 결속이 올바르지 않습니다.')
            variables.add(variable)
    measured = set()
    node_variables = {r['nodes']: r['nodesVars'] for r in mapping['nodes']}
    for row in mapping['measurements']:
        name, variable = row.get('nodes'), row.get('measurementsVars')
        score = float(row['value'])
        if name not in names or name in measured or row.get('nodesVars') != node_variables[name]:
            raise ValueError('원 관측 노드 결속이 다릅니다.')
        if not math.isfinite(score) or score == 0 or variable not in lp['bounds'] or variable in variables:
            raise ValueError('원 관측 변수 또는 점수가 올바르지 않습니다.')
        if abs(lp['objective'].get(variable, -1) - abs(score)) > 1e-10:
            raise ValueError('원 관측과 목표식의 가중치가 다릅니다.')
        sign = 1. if score > 0 else -1.
        required = [(tuple(sorted({row['nodesVars']: 1., variable: -1.}.items())), '<=', sign),
                    (tuple(sorted({row['nodesVars']: 1., variable: 1.}.items())), '>=', sign)]
        if not all(item in constraints for item in required):
            raise ValueError('관측 부호와 원 절대오차 제약이 다릅니다.')
        measured.add(name)
        variables.add(variable)
    if variables != set(lp['bounds']):
        raise ValueError('원 변수지도와 LP 전체 변수 분모가 다릅니다.')
    return True
