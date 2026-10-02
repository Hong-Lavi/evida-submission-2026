"""Credential-free separate pinned CPU environment; no runtime downloads."""
import hashlib
import itertools
import json
import sys
import time
from pathlib import Path

import fm
import joblib
import numpy as np
import torch


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while b:=f.read(1048576):h.update(b)
    return h.hexdigest()


def run(value):
    rows=value['rows'];cfg=value['configuration'];start=time.monotonic()
    for key in ['weights','rna_fm_head','sequence3mer_head']:
        if sha(cfg[key])!=cfg[key+'_sha256']:raise ValueError('동결 모델/가중치 해시가 다릅니다: '+key)
    torch.set_num_threads(2);torch.manual_seed(20260925)
    model,alphabet=fm.pretrained.load_model_and_alphabet_local(Path(cfg['weights']),theme='rna');model.eval()
    batch=alphabet.get_batch_converter();seqs=sorted({r[k] for r in rows for k in ['guide','context']});features={}
    with torch.no_grad():
        for offset in range(0,len(seqs),12):
            part=seqs[offset:offset+12];_,_,tokens=batch([(str(i),s) for i,s in enumerate(part)])
            z=model(tokens,repr_layers=[12])['representations'][12]
            for i,s in enumerate(part):features[s]=z[i,1:1+len(s)].mean(0).numpy()
    xx=np.asarray([np.r_[features[r['guide']],features[r['context']]] for r in rows]);head=joblib.load(cfg['rna_fm_head'])
    pred=head['model'].predict(head['scaler'].transform(xx))
    words=[''.join(x) for x in itertools.product('ACGU',repeat=3)]
    km=np.asarray([[sum(r['guide'][i:i+3]==w for i in range(17))/17 for w in words] for r in rows]);base=joblib.load(cfg['sequence3mer_head'])
    baseline=base['model'].predict(base['scaler'].transform(km))
    trial=json.loads(Path(cfg['trial_result']).read_text())
    return {'status':'succeeded','semantic_type':'experimental_author_assay_label_score_not_efficacy_probability',
        'rows':[{**r,'rna_fm_ridge_score':float(pred[i]),'sequence3mer_ridge_score':float(baseline[i]),
                 'score_outside_training_label_range':bool(pred[i]<0 or pred[i]>1)} for i,r in enumerate(rows)],
        'summary':{'candidates':len(rows),'device':'CPU','model_scope':'19nt unmodified sequence surrogate; dose/cell/chemistry not modeled',
                   'scientific_status':'experimental component; not candidate efficacy validation'},
        'protocol':{'component':'RNA-FM actual pretrained layer12 + local ridge head; NOT ENsiRNA whole model',
                    'rna_fm_alpha':1000,'three_mer_alpha':.01,'weights_sha256':cfg['weights_sha256'],
                    'head_sha256':cfg['rna_fm_head_sha256'],'protocol_sha256':head['protocol_sha256'],
                    'elapsed_seconds':time.monotonic()-start,'torch':torch.__version__,'batch_size':12,'threads':2},
        'development_comparison':trial['results'],
        'sources':[{'url':'https://github.com/ml4bio/RNA-FM','role':'pretrained RNA representation'},
                   {'url':'https://github.com/tanwenchong/ENsiRNA/tree/028824341635903f3c661f5d1cc737de106493d5/ENsiRNA/dataset','role':'author train/validation/EGFP test labels'}],
        'limits':['저자 assay label 척도의 탐색 점수이며 성공 확률·임상 효능·입력 후보의 실험 관측이 아닙니다. 범위를 벗어나도 임의로0–1로 자르지 않습니다.',
                  'EGFP702개 겹치는 창의 시험 MAE는 RNA-FM0.1404/단순3mer0.1472였지만 검증 MAE는0.1771/0.1724로 RNA-FM이 더 나쁘며 일관된 우위가 아닙니다.',
                  '학습·검증 표적 공유와 인접 서열 의존성이 있습니다. 단일 EGFP 시험은 여러 새 표적의 일반화 검증이 아닙니다. 사전학습 중복은 미확인입니다.',
                  '19nt 가이드와 실제 최대61nt 표적 문맥만 사용합니다. 수식·용량·조직·RISC·전달·분해 안정성을 예측하지 않습니다.',
                  '이 회귀 점수는 전체 ENsiRNA의 3D 입력·기하 그래프·원 학습 checkpoint 실행과 다릅니다. 전체 모델은 별도 도구로 실행하며 후보별 실제 실행 기록을 확인해야 합니다.']}

if __name__=='__main__':
    Path(sys.argv[2]).write_text(json.dumps(run(json.loads(Path(sys.argv[1]).read_text())),ensure_ascii=False,allow_nan=False))
