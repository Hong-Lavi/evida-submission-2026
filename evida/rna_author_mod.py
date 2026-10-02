"""Explicit chemistry/position inputs for the already-trialled author model."""
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess

from .rna_author import file_hash
from .rna_author_worker import verify_pdb

CHEMISTRIES=('2-O-Methyl','2-Fluoro','2-O-(2-Methoxyethyl)','2-Deoxy')


def configuration(verify=False):
    cfg=json.loads((Path(__file__).parents[1]/'configs/rna-author-mod.json').read_text())
    if verify:
        for name,expected in cfg['assets'].items():
            if file_hash(name)!=expected:raise ValueError('수식 저자 모델의 고정 자원이 바뀌었습니다: '+Path(name).name)
    return cfg


def prepare_rows(parent, original, arguments):
    if parent.get('semantic_type')!='conditional_full_author_ensirna_prediction' or parent.get('status')!='succeeded':
        raise ValueError('완료한 전체 ENsiRNA 결과와 그 정확한 구조가 필요합니다.')
    candidate=arguments['candidate_id']
    matches=[row for row in original['rows'] if row['candidate_id']==candidate]
    structures=[row for row in parent['structures'] if row['candidate_id']==candidate]
    if len(matches)!=1 or len(structures)!=1:raise ValueError('원 구조와 후보의 유일한 대응이 필요합니다.')
    base=matches[0]
    sense,anti=base['sense seq'],base['anti seq']
    if not all(re.fullmatch('[ACGU]{19}',seq) for seq in (sense,anti)):
        raise ValueError('현재 수식 연결은 정확19nt blunt core입니다. 긴 가닥을 자동 자르지 않습니다.')
    if sense!=anti.translate(str.maketrans('ACGU','UGCA'))[::-1]:raise ValueError('가이드·보조 가닥 방향이 다릅니다.')
    designs=arguments['designs']
    if not 1<=len(designs)<=4 or len({d['id'] for d in designs})!=len(designs):
        raise ValueError('서로 다른 이름의 수식 비교안1–4개가 필요합니다.')
    rows=[]
    for index,design in enumerate(designs):
        if not isinstance(design['id'],str) or not design['id'].strip():raise ValueError('수식 비교안 이름이 필요합니다.')
        modifications=design['modifications'];seen=set();groups={'guide':{},'passenger':{}}
        for mod in modifications:
            strand,pos,chem=mod['strand'],mod['position_1_based'],mod['chemistry']
            if strand not in groups or type(pos)is not int or not 1<=pos<=19 or chem not in CHEMISTRIES:
                raise ValueError('수식 가닥·위치1–19·지원 당 수식을 확인해 주세요.')
            if (strand,pos)in seen:raise ValueError('같은 가닥·위치의 당 수식은 중복할 수 없습니다.')
            seen.add((strand,pos));groups[strand].setdefault(chem,[]).append(pos)
        row={'ID':'design_'+str(index+1),'source':'explicit_researcher_or_planner_chemistry_proposal',
             'cc':0,'PCT':0,'cc_norm':0,'group':'conditional_core_comparison',
             'sense raw seq':sense,'anti raw seq':anti,'anti length':19,'sense length':19}
        for strand,author in [('guide','anti'),('passenger','sense')]:
            group=groups[strand]
            row[author+' mod']='* '.join(sorted(group)) if group else 0
            row[author+' pos']='*'.join(','.join(str(n)for n in sorted(group[c]))for c in sorted(group)) if group else 0
        rows.append({'author_input':row,'design_id':design['id'],'modifications':modifications,
                     'candidate_id':candidate,'actual_efficacy':None,
                     'source_chemistry':base.get('source_chemistry')})
    return rows,base,structures[0]


def stage_parent(root, artifact, arguments, destination):
    """Resolve only the store-owned attempt; arbitrary supplied paths are invalid."""
    attempt=artifact['meta'].get('attempt_id','')
    if not re.fullmatch(r'attempt_[0-9a-f]{16}',attempt):raise ValueError('원 구조 실행 기록이 없습니다.')
    attempts=(Path(root)/'runs/attempts').resolve()
    directory=(attempts/attempt/'full-author').resolve()
    if not directory.is_relative_to(attempts):raise ValueError('원 구조 경로가 실행 저장소 밖입니다.')
    original=directory/'request.json';parent=json.loads(artifact['content'])
    if not original.is_file() or file_hash(original)!=parent['protocol']['input_sha256']:
        raise ValueError('원 구조 생성 입력을 확인할 수 없습니다. 구조를 재사용했다고 처리하지 않습니다.')
    rows,base,structure=prepare_rows(parent,json.loads(original.read_text()),arguments)
    name=base['siRNA']
    if not re.fullmatch(r'candidate_[1-3]',name):raise ValueError('원 구조 내부 ID가 올바르지 않습니다.')
    pdb=(directory/'pdb'/(name+'.pdb')).resolve()
    if not pdb.is_relative_to(directory) or file_hash(pdb)!=structure['pdb_sha256']:
        raise ValueError('원 구조 해시가 다릅니다.')
    verify_pdb(pdb,base['sense seq'],base['anti seq'])
    target=Path(destination)/'source-core.pdb';shutil.copyfile(pdb,target)
    packet={'rows':rows,'reference':parent['reference'],'source_artifact_id':artifact['id'],
            'source_artifact_sha256':artifact['sha256'],'source_request_sha256':file_hash(original),
            'pdb_path':str(target),'pdb_sha256':file_hash(target),
            'geometry':'Same exact base-only sense+antisense structure; modified atoms are not generated.',
            'structure_seed':structure['structure_seed']}
    transfer=Path(destination)/'modified-transfer.json';transfer.write_text(json.dumps(packet,ensure_ascii=False)+'\n')
    return str(transfer)


def run_modified(transfer, work):
    data=json.loads(Path(transfer).read_text());cfg=configuration(verify=True)
    if file_hash(data['pdb_path'])!=data['pdb_sha256']:raise ValueError('전달 구조 해시가 다릅니다.')
    work=Path(work);work.mkdir(exist_ok=False)
    request=work/'request.json';output=work/'result.json'
    request.write_text(json.dumps({**data,'configuration':cfg},ensure_ascii=False)+'\n')
    env={'PATH':str(Path(cfg['rna_plex']).parent)+':/usr/bin:/bin','LANG':'C.UTF-8','CUDA_VISIBLE_DEVICES':str(cfg['physical_gpu']),
         'PYTHONPATH':cfg['python_overlay']+':'+cfg['author_code'],'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1',
         'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2','MKL_NUM_THREADS':'2',
         'XDG_CACHE_HOME':str(work/'cache'),'MPLCONFIGDIR':str(work/'matplotlib')}
    with (work/'worker.log').open('xb')as log:
        process=subprocess.Popen([cfg['python'],str(Path(__file__).with_name('rna_author_mod_worker.py')),str(request),str(output)],
            cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:status=process.wait(timeout=cfg['timeout_seconds'])
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);process.wait()
            raise RuntimeError('수식 모델 계산 시간이 초과됐습니다. 부분 기록 보존·자동 재호출 없음.')from None
    if status or not output.is_file():
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        raise RuntimeError('수식 저자 계산이 완료되지 않았습니다. 입력·부분 점수·실패 기록을 보존했습니다.')
    body=json.loads(output.read_text())
    if body.get('status')!='succeeded':raise ValueError('완료되지 않은 수식 계산입니다.')
    return body
