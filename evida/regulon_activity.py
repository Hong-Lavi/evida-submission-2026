"""Author ULM on source-bound gene contrast statistics with preserved resource gaps."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from .resource_integrity import verify_file


def obj(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


TEXT={'type':'string','minLength':1}
SCHEMA=obj({
    'source_artifact_ids':{'type':'array','items':TEXT,'minItems':1,'maxItems':1},
    'table_path':{'type':'array','maxItems':12,'items':{'anyOf':[TEXT,{'type':'integer','minimum':0}]}},
    'gene_field':TEXT,'statistic_field':TEXT,
    'statistic_kind':{'type':'string','enum':['moderated_t','t','z']},
    'organism':{'type':'string','enum':['human']},
    'comparison':TEXT,
    'conditions':{'type':'array','items':TEXT,'minItems':1,'maxItems':30},
    'focus_tfs':{'type':'array','items':TEXT,'maxItems':50},
})


def prepare(arguments,sources):
    ids=arguments['source_artifact_ids']
    if len(ids)!=1 or ids[0] not in sources:
        raise ValueError('보존된 유전자별 대비 통계표 하나를 지정해 주세요.')
    node=sources[ids[0]]
    for key in arguments['table_path']:
        try:
            if isinstance(node,list) and type(key) is int:node=node[key]
            elif isinstance(node,dict) and isinstance(key,str):node=node[key]
            else:raise KeyError(key)
        except (KeyError,IndexError,TypeError) as error:
            raise ValueError('표 위치는 저장된 JSON 본문 기준입니다. 조회 응답의 바깥 result/content 키를 덧붙이지 마세요.') from error
    if not isinstance(node,list) or not 5<=len(node)<=50000:
        raise ValueError('5–50,000행의 유전자별 통계표가 필요합니다. 원자료나 결측을 임의로 채우지 않습니다.')
    rows=[];seen=set()
    for index,row in enumerate(node):
        if not isinstance(row,dict):raise ValueError(f'{index}번 행은 이름이 있는 열 구조여야 합니다.')
        gene=row.get(arguments['gene_field']);value=row.get(arguments['statistic_field'])
        if not isinstance(gene,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',gene):
            raise ValueError(f'{index}번 행의 사람 유전자 기호를 확인하세요. 자동 식별자 변환은 하지 않았습니다.')
        if gene in seen:raise ValueError(f'유전자 {gene}의 통계가 중복됩니다. 원 프로브·전사체 대응을 먼저 확인하세요.')
        if type(value) not in (int,float) or not math.isfinite(value):
            raise ValueError(f'{index}번 행의 대비 통계가 유한한 수가 아닙니다. 결측을0으로 바꾸지 않습니다.')
        seen.add(gene);rows.append({'gene':gene,'statistic':float(value),'source_row_0_based':index})
    if max(r['statistic'] for r in rows)==min(r['statistic'] for r in rows):
        raise ValueError('유전자별 통계가 모두 같습니다. 이 입력으로 조절 패턴을 추정할 수 없습니다.')
    return {'rows':rows,'source_artifact_id':ids[0],'source_table_path':arguments['table_path'],
        'gene_field':arguments['gene_field'],'statistic_field':arguments['statistic_field'],
        'statistic_kind_declared':arguments['statistic_kind'],'comparison':arguments['comparison'],
        'conditions':arguments['conditions'],'focus_tfs':arguments['focus_tfs']}


def verified_resources(root):
    config_path=root/'configs/regulon-resources.json'
    cfg=json.loads(config_path.read_text())
    resources={}
    for name,item in cfg['resources'].items():
        if name not in ('dorothea','collectri'):raise ValueError('등록되지 않은 조절망입니다.')
        resources[name]=verify_file(item['path'],item['sha256'])
    verify_file(cfg['rscript'],cfg['rscript_sha256'])
    runtime_files={name:verify_file(item['path'],item['sha256']) for name,item in cfg['runtime_files'].items()}
    script=root/'evida/regulon_activity.R'
    return cfg,{'config':hashlib.sha256(config_path.read_bytes()).hexdigest(),
        'Rscript':cfg['rscript_sha256'],'script':hashlib.sha256(script.read_bytes()).hexdigest(),
        'resources':resources,'runtime_files':runtime_files,'required_versions':cfg['required_versions']}


def analyze(arguments,sources,root,work):
    prepared=prepare(arguments,sources)
    cfg,fingerprint=verified_resources(root)
    work.mkdir(exist_ok=False)
    request={'prepared':prepared,'resources':cfg['resources'],'required_versions':cfg['required_versions']}
    input_path=work/'input.json';output_path=work/'result.json'
    input_path.write_text(json.dumps(request,ensure_ascii=False,allow_nan=False))
    # The scientific worker passes no provider/service keys or user shell startup.
    env={'PATH':str(Path(cfg['rscript']).parent)+':/usr/bin:/bin','LANG':'C.UTF-8','TZ':'UTC',
         'HOME':str(work),'TMPDIR':str(work),'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
    with (work/'worker.log').open('wb') as log:
        completed=subprocess.run([cfg['rscript'],'--vanilla',str(root/'evida/regulon_activity.R'),
            str(input_path),str(output_path)],cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT,
            timeout=300,check=False)
    if completed.returncode or not output_path.exists():
        raise RuntimeError(f'조절 패턴 계산이 완료되지 않았습니다 (exit={completed.returncode}). 원 입력과 실행 기록을 보존했습니다.')
    result=json.loads(output_path.read_text())
    if result.get('status')!='succeeded':raise ValueError('저자 계산의 성공 상태를 확인하지 못했습니다.')
    result.update(resource_fingerprint=fingerprint,
        source_binding={k:v for k,v in prepared.items() if k not in ('rows','focus_tfs')},
        input_rows_sha256=hashlib.sha256(json.dumps(prepared['rows'],sort_keys=True,separators=(',',':')).encode()).hexdigest())
    return result
