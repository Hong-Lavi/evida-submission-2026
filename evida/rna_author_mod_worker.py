"""Actual author modification workflow, using verified exact base geometry."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from rna_author_worker import sha,save,verify_pdb


def main():
    request,output=map(Path,sys.argv[1:]);data=json.loads(request.read_text());cfg=data['configuration']
    work=output.parent;start=time.monotonic();rows=data['rows']
    assert os.environ['CUDA_VISIBLE_DEVICES']==str(cfg['physical_gpu'])
    for path,expected in cfg['assets'].items():assert sha(path)==expected,'Frozen asset changed'
    assert sha(data['pdb_path'])==data['pdb_sha256']
    lock=open(cfg['gpu_lock'],'a');fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    used=int(subprocess.check_output(['/usr/bin/nvidia-smi','--id='+str(cfg['physical_gpu']),
        '--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True).strip())
    if used>=512:raise RuntimeError('GPU occupied; no inference started')
    save(work/'preflight.json',{'input_sha256':sha(request),'physical_gpu':cfg['physical_gpu'],
        'memory_used_mib_before':used,'actual_efficacy':None,'automatic_retry':False})
    import pandas as pd
    import torch
    import RNA
    assert RNA.__version__=='2.7.2'
    torch.set_num_threads(2);assert torch.cuda.is_available() and torch.cuda.device_count()==1
    from utils.random_seed import setup_seed
    setup_seed(12)
    author=[r['author_input']for r in rows]
    pd.DataFrame(author).to_excel(work/'input.xlsx',index=False)
    pdb=work/'pdb';pdb.mkdir()
    for row in author:
        target=pdb/(row['ID']+'.pdb');shutil.copyfile(data['pdb_path'],target)
        verify_pdb(target,row['sense raw seq'],row['anti raw seq'])
    from data.get_pdb import Data_Prepare
    def unexpected(*args,**kwargs):raise RuntimeError('Unexpected additional geometry requested')
    Data_Prepare.get_secondary_structure=unexpected
    Data_Prepare(str(work/'input.xlsx'),str(pdb)).process()
    pre=[json.loads(line)for line in(work/'input.json').read_text().splitlines()]
    assert [r['ID']for r in pre]==[r['ID']for r in author],'Rows omitted/reordered'
    from data.mod_utils import MOD_VOCAB
    for source,prepared in zip(rows,pre):
        expected=[]
        for strand,offset in [('passenger',0),('guide',19)]:
            positions=[m['position_1_based']for m in source['modifications']if m['strand']==strand]
            expected.extend(offset+p for p in positions or [0])
        assert set(prepared['smask'])==set(expected),'Author zero-sentinel/mask convention changed'
        for mod in source['modifications']:
            index=mod['position_1_based']+(19 if mod['strand']=='guide'else 0)
            assert prepared['atom_mask'][index][0]==MOD_VOCAB.mod2index[mod['chemistry']]
        assert len(prepared['start'])==39
    save(work/'preprocessing-review.json',{'rows':[{'id':r['ID'],'smask':r['smask'],'atom_mask':r['atom_mask']}for r in pre],
        'explicit_position_and_chemistry_encoding_checked':True,'source_geometry_sha256':data['pdb_sha256'],
        'author_zero_sentinel_preserved':True,'modified_atom_geometry':False})
    from data.dataset import E2EDataset
    from torch.utils.data import DataLoader
    ds=E2EDataset(str(work/'input.json'),save_dir=str(work/'author-cache'));assert len(ds)==len(rows)
    batch=next(iter(DataLoader(ds,batch_size=len(rows),num_workers=0,collate_fn=E2EDataset.collate_fn)))
    batch={k:v.to('cuda:0')if hasattr(v,'to')else v for k,v in batch.items()}
    assert batch['lengths'].tolist()==[39]*len(rows)
    scores=[]
    for checkpoint in cfg['checkpoints']:
        model=torch.load(checkpoint,map_location='cpu').to('cuda:0').eval()
        with torch.no_grad():
            values=model.test(**batch)[0]
            control={**batch,**{k:torch.ones_like(batch[k])for k in ('pct','cc','marker')}}
            delta=float((values-model.test(**control)[0]).abs().max())
            assert delta<=1e-6 and torch.isfinite(values).all() and values.numel()==len(rows)
        model_rows=[{'candidate_id':source['candidate_id'],'design_id':source['design_id'],
            'modifications':source['modifications'],'source_chemistry':source['source_chemistry'],
            'checkpoint':Path(checkpoint).name,'raw_model_score':float(values[i]),'actual_efficacy':None,
            'representation':'explicit_sugar_modifications_on_19nt_blunt_base_geometry'}for i,source in enumerate(rows)]
        save(work/(Path(checkpoint).stem+'-result.json'),{'rows':model_rows,'checkpoint_sha256':sha(checkpoint),
            'technical_placeholders_max_delta':delta})
        scores.extend(model_rows);del model;torch.cuda.empty_cache()
    save(output,{'status':'succeeded','semantic_type':'conditional_author_modification_model_comparison',
        'reference':data['reference'],'source_artifact_id':data['source_artifact_id'],'rows':scores,
        'summary':{'designs':len(rows),'checkpoints':len(cfg['checkpoints']),'elapsed_seconds':time.monotonic()-start},
        'protocol':{'input_sha256':sha(request),'source_artifact_sha256':data['source_artifact_sha256'],
            'source_request_sha256':data['source_request_sha256'],'pdb_sha256':data['pdb_sha256'],
            'geometry':data['geometry'],'structure_seed':data['structure_seed'],'author_commit':cfg['author_commit'],
            'assets':cfg['assets'],'torch':torch.__version__,'author_zero_sentinel_preserved':True,
            'training_domain_verified_for_these_inputs':False,'actual_efficacy':None},
        'limits':['명시한 양 가닥 당 수식과 위치를 저자 전처리·RNA-FM·5개 ENsiRNA-mod 모델에 실제 전달했습니다.',
            '19nt blunt core의 동일한 염기 구조를 재사용합니다. 수식 원자의3D 구조·돌출부·말단·제형·조직 노출은 반영하지 않습니다.',
            '저자의 무수식 위치0 convention과 위치 mask를 보존합니다. 두 점수의 차이를 화학 수식만의 생물학적 인과효과로 해석하지 않습니다.',
            '지원 vocabulary는 학습 분포 적합성의 증명이 아닙니다. 효능·안전성·성공 확률이나 권장 처방이 아닙니다.',
            '원 후보·다른 계산·조건·반대 근거는 남아 있으며 비수식 ENsiRNA와 서로 다른 모델 점수를 합산하지 않습니다.']})


if __name__=='__main__':
    try:main()
    except Exception as error:
        if len(sys.argv)==3:
            path=Path(sys.argv[2]).parent/'failure.json'
            if not path.exists():save(path,{'status':'FAILED','error_type':type(error).__name__,'message':str(error),'automatic_retry':False})
        raise
