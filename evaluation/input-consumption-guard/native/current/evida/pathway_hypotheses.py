"""Source-bound author CARNIVAL fitting; candidate mechanisms, not causal truth."""
from __future__ import annotations
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
from .regulon_activity import obj, TEXT
from .resource_integrity import verify_file

SCHEMA = obj({
    'artifact_id': TEXT,
    'resource': {'type': 'string', 'enum': ['dorothea', 'collectri']},
    'tf_ids': {'type': 'array', 'items': TEXT, 'minItems': 1, 'maxItems': 12},
    'selection_reason': TEXT,
    'ancestor_steps': {'type': 'integer', 'minimum': 1, 'maximum': 4},
    'conditions': {'type': 'array', 'items': TEXT, 'minItems': 1, 'maxItems': 30},
})


def prepare(arguments, source, prior):
    if source.get('semantic_type') != 'inferred_regulon_activity' or source.get('status') != 'succeeded':
        raise ValueError('성공한 조절 패턴 계산을 선택해 주세요. 제안한 점수나 실패 결과를 관측으로 바꾸지 않습니다.')
    selected = []
    for tf in arguments['tf_ids']:
        matches = [r for r in source['rows'] if r['source'] == tf and r['resource'] == arguments['resource']]
        if len(matches) != 1:
            raise ValueError(f'{tf}의 해당 조절망 원 결과를 하나로 확인하지 못했습니다. 누락을 음성 관측으로 채우지 않습니다.')
        row = matches[0]
        if type(row['score']) not in (int, float) or not math.isfinite(row['score']) or row['score'] == 0:
            raise ValueError('이 부호 경로 시험에는 유한한 비영점 점수가 필요합니다. 생물학적 부재 판정이 아닙니다.')
        selected.append(dict(row))
    universe = {r['source'] for r in prior} | {r['target'] for r in prior}
    missing = sorted(set(arguments['tf_ids']) - universe)
    if missing:
        raise ValueError('선택한 전사인자가 고정 상호작용망에 없습니다: ' + ', '.join(missing) + '. 해당 가설의 반증이 아닙니다.')
    nodes = set(arguments['tf_ids'])
    frontier = [{'step': 0, 'nodes': len(nodes)}]
    for step in range(arguments['ancestor_steps']):
        nodes |= {r['source'] for r in prior if r['target'] in nodes}
        frontier.append({'step': step + 1, 'nodes': len(nodes)})
    network = [r for r in prior if r['source'] in nodes and r['target'] in nodes]
    if not network or len(network) > 15000:
        raise ValueError(f'현재 선택의 상호작용 {len(network)}개는 이 로컬 시험 범위에 맞지 않습니다. 선택·탐색 범위를 검토해야 하며 경로 없음의 근거가 아닙니다.')
    return {'selected_inferred_observations': selected, 'network': network,
        'source_conditions': source.get('conditions', []), 'requested_conditions': arguments['conditions'],
        'selection_reason': arguments['selection_reason'],
        'search_scope': {'ancestor_steps': arguments['ancestor_steps'], 'frontier': frontier,
            'full_prior_edges': len(prior), 'selected_prior_edges': len(network),
            'selected_prior_nodes': len(nodes), 'global_search_complete': False,
            'unselected_TF_resource_rows_retained_in_source': len(source['rows']) - len(selected)}}


def verified_resources(root):
    cfg_path = root / 'configs/pathway-resources.json'
    cfg = json.loads(cfg_path.read_text())
    verified = {name: verify_file(item['path'], item['sha256']) for name, item in cfg['files'].items()}
    return cfg, {'config': hashlib.sha256(cfg_path.read_bytes()).hexdigest(), 'files': verified,
        'script': hashlib.sha256((root / 'evida/pathway_hypotheses.R').read_bytes()).hexdigest(),
        'required_versions': cfg['required_versions']}


def load_prior(cfg):
    with open(cfg['files']['prior']['path']) as handle:
        rows = list(csv.DictReader(handle, delimiter='\t'))
    for row in rows:
        row['interaction'] = int(row['interaction'])
        if row['interaction'] not in (-1, 1):
            raise ValueError('고정 상호작용망의 부호를 확인해야 합니다.')
    return rows


def analyze(arguments, source, root, work):
    cfg, fingerprint = verified_resources(root)
    prepared = prepare(arguments, source, load_prior(cfg))
    work.mkdir(exist_ok=False)
    request = {**prepared, 'required_versions': cfg['required_versions'],
        'solver_path': cfg['files']['cbc']['path'], 'solver_time_limit_seconds': 120}
    input_path, output_path = work / 'input.json', work / 'result.json'
    input_path.write_text(json.dumps(request, ensure_ascii=False, allow_nan=False))
    rscript = cfg['files']['Rscript']['path']
    env = {'PATH': str(Path(rscript).parent) + ':/usr/bin:/bin', 'LANG': 'C.UTF-8', 'TZ': 'UTC',
        'TMPDIR': str(work), 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'}
    log_path = work / 'worker.log'
    with log_path.open('wb') as log:
        completed = subprocess.run([rscript, '--vanilla', str(root / 'evida/pathway_hypotheses.R'),
            str(input_path), str(output_path)], cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT,
            timeout=180, check=False)
    if completed.returncode or not output_path.exists():
        raise RuntimeError('경로 후보 계산을 완료하지 못했습니다. 원 선택·탐색 범위·로그는 보존했으며 생물학적 부정으로 처리하지 않습니다.')
    result = json.loads(output_path.read_text())
    diagnostic = log_path.read_text(errors='replace')
    optimal = 'Result - Optimal solution found' in diagnostic
    result.update(status='succeeded' if optimal else 'partial',
        solver_review={'optimal_reported': optimal, 'time_limit_seconds': 120,
            'diagnostic_sha256': hashlib.sha256(log_path.read_bytes()).hexdigest(),
            'unique_optimum_established': False}, resource_fingerprint=fingerprint,
        source_binding={'artifact_id': arguments['artifact_id'], 'resource': arguments['resource'],
            'selected_TFs': arguments['tf_ids']})
    return result
