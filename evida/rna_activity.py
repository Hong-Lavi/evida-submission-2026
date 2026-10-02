"""Experimental frozen RNA-FM + locally trained head, separate from ENsiRNA."""
import hashlib
import json
from pathlib import Path
import subprocess

from .rna_resources import configuration, candidate_rows


def run_activity(result, reference, arguments, work):
    cfg = configuration()['activity']
    selected = candidate_rows(result,arguments['candidate_ids'])
    if reference.get('semantic_type')!='versioned_transcript_sequence' or reference['reference']['sequence_sha256']!=result['reference']['sequence_sha256']:
        raise ValueError('가이드 계산과 동일한 원 전사체 서열을 선택해 주세요.')
    target=reference['sequence_5to3']
    if hashlib.sha256(target.encode()).hexdigest()!=reference['reference']['sequence_sha256']:
        raise ValueError('원 참조 해시가 다릅니다.')
    rows=[]
    for r in selected:
        if len(r['guide_5to3'])!=19:
            raise ValueError('이 부분 모델의 입력은 정확히19nt입니다. 긴 가이드를 자동 자르지 않습니다. 19nt 후보를 별도로 생성·선택해 주세요.')
        sites=r['perfect_complementary_sites']
        if len(sites)!=1:
            raise ValueError('현재 부분 모델은 명확한 표적 부위1개가 필요합니다. 중복 부위를 첫 일치로 자동 선택하지 않습니다.')
        pos=sites[0]['start_1_based']-1
        context=target[max(0,pos-21):pos+19+21]
        if set(context)-set('ACGU'):raise ValueError('모형 문맥에 미확인 염기가 있습니다.')
        rows.append({'id':r['id'],'guide':r['guide_5to3'],'context':context,'target_start_1_based':pos+1,
                     'chemistry':r['chemistry'],'calculation_scope':r['calculation_scope']})
    work=Path(work);work.mkdir(exist_ok=False)
    inp=work/'input.json';out=work/'output.json';inp.write_text(json.dumps({'rows':rows,'configuration':cfg}))
    with (work/'worker.log').open('wb') as log:
        subprocess.run([cfg['python'],str(Path(__file__).with_name('rna_activity_worker.py')),str(inp),str(out)],
            cwd=work,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
    result_body=json.loads(out.read_text());result_body['reference']=reference['reference']
    return result_body
