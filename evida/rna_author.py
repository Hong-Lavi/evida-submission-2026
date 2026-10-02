"""Full author ENsiRNA execution, distinct from the existing local activity head.

This first connected representation is explicit: unmodified 19nt blunt cores.
It is a conditional model experiment, never the efficacy of a modified product.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess

from .rna_resources import candidate_rows


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def configuration(verify=False):
    path = Path(__file__).parents[1]/'configs/rna-author.json'
    cfg = json.loads(path.read_text())
    if verify:
        for asset, expected in cfg['assets'].items():
            if not Path(asset).is_file() or file_hash(asset) != expected:
                raise ValueError('전체 RNA 저자 모델의 고정 자원 확인이 필요합니다: '+Path(asset).name)
    return cfg


def prepare_rows(result, reference, arguments):
    if arguments.get('representation') != 'unmodified_19nt_blunt_core_proxy':
        raise ValueError('현재 연결은 명시적 비수식 19nt blunt core 계산입니다. 완성 수식/제형의 효능으로 대체하지 않습니다.')
    if reference.get('semantic_type') != 'versioned_transcript_sequence':
        raise ValueError('버전이 있는 원 전사체 서열이 필요합니다.')
    if result.get('reference', {}).get('sequence_sha256') != reference['reference']['sequence_sha256']:
        raise ValueError('가이드와 원 전사체의 참조가 다릅니다.')
    target = reference['sequence_5to3']
    if hashlib.sha256(target.encode()).hexdigest() != reference['reference']['sequence_sha256']:
        raise ValueError('원 전사체 서열 해시가 다릅니다.')
    selected = candidate_rows(result, arguments['candidate_ids'])
    if len(selected) > 3:
        raise ValueError('구조 계산은 한 번에 최대3개입니다. 나머지 후보도 별도 실행할 수 있습니다.')
    rows = []
    for candidate in selected:
        guide = candidate['guide_5to3']
        if not re.fullmatch('[ACGU]{19}', guide):
            raise ValueError('첫 연결에서 검토한 입력은 정확19nt입니다. 서열을 자동 자르거나 모호한 염기를 추정하지 않습니다.')
        sites = candidate['perfect_complementary_sites']
        if len(sites) != 1:
            raise ValueError('전체 저자 모형의 표적 문맥에 쓸 정확 부위1개가 필요합니다. 첫 일치를 자동 선택하지 않습니다.')
        pos = sites[0]['start_1_based']-1
        sense = guide.translate(str.maketrans('ACGU', 'UGCA'))[::-1]
        if pos < 0 or target[pos:pos+19] != sense:
            raise ValueError('선택된 표적 위치와 가이드 상보 서열이 다릅니다.')
        if re.search('[^ACGU]', target[max(0, pos-21):pos+40]):
            raise ValueError('실제 모델이 읽는 주변 전사체 문맥에 미확인 염기가 있습니다.')
        rows.append({'siRNA': 'candidate_'+str(len(rows)+1), 'anti seq': guide,
            'sense seq': sense, 'mRNA': reference['reference']['transcript_id'],
            'mRNA_seq': target, 'position': pos, 'efficacy': 0, 'anti_seq_len': 19,
            'candidate_id': candidate['id'], 'source_chemistry': candidate.get('chemistry'),
            'source_calculation_scope': candidate.get('calculation_scope'),
            'representation': arguments['representation'], 'actual_efficacy': None})
    return rows


def run_author(result, reference, arguments, work):
    rows = prepare_rows(result, reference, arguments)
    cfg = configuration(verify=True)
    work = Path(work); work.mkdir(exist_ok=False)
    request = work/'request.json'; output = work/'result.json'
    request.write_text(json.dumps({'rows': rows, 'configuration': cfg,
        'reference': reference['reference']}, ensure_ascii=False)+'\n')
    # Explicit resource choice belongs to this local adapter, not user text or
    # the model response. Neither parent API credentials nor provider auth enter.
    env = {k: os.environ[k] for k in ('LANG', 'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
        'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS') if k in os.environ}
    env.update(PATH=str(Path(cfg['rna_plex']).parent)+':/usr/bin:/bin',
        CUDA_VISIBLE_DEVICES=str(cfg['physical_gpu']), PYTHONNOUSERSITE='1',
        PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=cfg['python_overlay']+':'+cfg['author_code']+':'+str(Path(cfg['rosetta_root'])/'main/tools/rna_tools'),
        ROSETTA=cfg['rosetta_root'], ROSETTA3_DB=str(Path(cfg['rosetta_root'])/'main/database'),
        XDG_CACHE_HOME=str(work/'cache'), MPLCONFIGDIR=str(work/'matplotlib'))
    command = [cfg['python'], str(Path(__file__).with_name('rna_author_worker.py')), str(request), str(output)]
    with (work/'worker.log').open('xb') as log:
        process = subprocess.Popen(command, cwd=work, env=env, stdout=log,
            stderr=subprocess.STDOUT, start_new_session=True)
        try:
            status = process.wait(timeout=cfg['timeout_seconds'])
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL); process.wait()
            raise RuntimeError('전체 저자 계산의 제한 시간에 도달했습니다. 부분 출력과 로그를 보존했으며 자동 재실행하지 않습니다.')
    if status or not output.is_file():
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        raise RuntimeError('전체 저자 계산이 완료되지 않았습니다. 입력·구조·부분 점수·실패 기록을 확인해 주세요.')
    body = json.loads(output.read_text())
    if body.get('status') != 'succeeded':
        raise ValueError('완료되지 않은 저자 출력을 성공으로 반환하지 않습니다.')
    return body
