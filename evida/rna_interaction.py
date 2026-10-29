"""Bounded IntaRNA author binary on exact saved guide/reference bytes.

Sequence-only thermodynamics is an unmodified proxy, not RNAi efficacy.
"""
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import time

FIELDS={'artifact_id','source_artifact_sha256','reference_id','reference_artifact_sha256',
        'guide_source_pointer','guide_5to3','reference_start_1_based','reference_end_1_based',
        'reference_window_5to3','accessibility_window_size','maximum_base_pair_span',
        'seed_base_pairs','temperature_celsius','max_interactions','representation'}
LIMITS=['Unmodified RNA sequence proxy; chemical modifications, RISC loading, delivery and cellular context are not modelled.',
        'IntaRNA heuristic seed-extension interactions in the explicitly selected transcript window only; not transcriptome-wide off-target analysis.',
        'Reported energies are thermodynamic model outputs, not measured affinity, silencing efficacy or a candidate winner.',
        'seedBP constrains an intermolecular seed anywhere in the interaction; it is not the siRNA guide positions 2–8 seed definition.',
        'Only up to the requested number of interactions with E < 0 and within the fixed suboptimal energy band are reported; absence is not experimental inactivity.']
ENERGY_MEANING={'units':'kcal/mol for energies; original author fields/precision retained',
 'E':'interaction energy including hybridization and both accessibility penalties',
 'ED1':'target-window accessibility opening cost','ED2':'guide accessibility opening cost',
 'E_hybrid':'hybridization contribution without the two accessibility costs',
 'Etotal':'interaction plus both intramolecular ensemble energies; distinct from E',
 'P_E':'probability within the author thermodynamic model, never efficacy probability',
 'seed_columns':'colon-separated multiple putative seeds are retained, not collapsed to one',
 'official_documentation':'https://backofenlab.github.io/IntaRNA/#output-modes'}

def digest(raw):return hashlib.sha256(raw).hexdigest()

def file_digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb')as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()

def prepare(source,reference,args):
 if not isinstance(args,dict)or set(args)!=FIELDS:raise ValueError('Exact named IntaRNA inputs are required.')
 for obj,idkey,shakey in [(source,'artifact_id','source_artifact_sha256'),(reference,'reference_id','reference_artifact_sha256')]:
  if obj['id']!=args[idkey]or not isinstance(obj['content'],bytes):raise ValueError('Select exact saved artifact bytes.')
  actual=digest(obj['content'])
  if actual!=obj['sha256']or actual!=args[shakey]:raise ValueError('Actual Store bytes and requested artifact SHA256 differ.')
 if source['kind']not in ('rna_sequence_evaluation','rna_candidate_generation'):raise ValueError('Use completed saved RNA guide rows.')
 if reference['kind']not in ('rna_reference','rna_reference_archive'):raise ValueError('Use a saved versioned transcript reference.')
 consumed=source.get('meta',{}).get('consumed_artifacts')
 if not isinstance(consumed,list)or args['reference_id']not in consumed:raise ValueError('Guide artifact does not retain this exact reference artifact identity.')
 result=json.loads(source['content']);ref=json.loads(reference['content'])
 if not isinstance(result,dict)or not isinstance(ref,dict)or result.get('status')!='succeeded':raise ValueError('Completed guide calculation and reference objects are required.')
 if ref.get('semantic_type')!='versioned_transcript_sequence':raise ValueError('Reference has no versioned transcript sequence.')
 target=ref.get('sequence_5to3');guide=args['guide_5to3'];rows=result.get('rows')
 if not isinstance(target,str)or not 1<=len(target)<=50000 or not re.fullmatch('[ACGUN]+',target):raise ValueError('Invalid saved transcript sequence.')
 target_sha=digest(target.encode())
 if ref.get('reference',{}).get('sequence_sha256')!=target_sha or result.get('reference',{}).get('sequence_sha256')!=target_sha:raise ValueError('Guide and actual reference sequence identities differ.')
 if not isinstance(rows,list)or not isinstance(args['guide_source_pointer'],str):raise ValueError('Saved guide row is required.')
 m=re.fullmatch(r'/rows/(0|[1-9][0-9]{0,5})/guide_5to3',args['guide_source_pointer'])
 if not m or int(m[1])>=len(rows):raise ValueError('Exact /rows/N/guide_5to3 pointer is required.')
 row=rows[int(m[1])]
 if not isinstance(row,dict)or guide!=row.get('guide_5to3')or not isinstance(guide,str)or not re.fullmatch('[ACGU]{19,30}',guide):raise ValueError('Guide must exactly match a saved 19–30 nt A/C/G/U row; no truncation or normalization.')
 start,end=args['reference_start_1_based'],args['reference_end_1_based']
 if type(start)is not int or type(end)is not int or not 1<=start<=end<=len(target)or end-start+1>500:raise ValueError('Explicit reference window must be 1–500 nt within the saved transcript.')
 window=args['reference_window_5to3']
 if not isinstance(window,str)or window!=target[start-1:end]or not re.fullmatch('[ACGU]+',window):raise ValueError('Window must exactly equal the requested actual reference slice without unknown bases.')
 for name,lo,hi in [('accessibility_window_size',1,len(window)),('maximum_base_pair_span',1,args['accessibility_window_size']if type(args['accessibility_window_size'])is int else 0),('seed_base_pairs',2,min(20,len(window),len(guide))),('max_interactions',1,20)]:
  if type(args[name])is not int or not lo<=args[name]<=hi:raise ValueError('Invalid named IntaRNA parameter: '+name)
 temperature=args['temperature_celsius']
 if type(temperature)not in (int,float)or not math.isfinite(temperature)or not 0<=temperature<=100:raise ValueError('Finite temperature from 0 to 100 Celsius is required.')
 if args['representation']!='unmodified_sequence_proxy':raise ValueError('Explicit unmodified_sequence_proxy representation is required.')
 return {'source_artifact_id':source['id'],'source_artifact_sha256':source['sha256'],'source_kind':source['kind'],
  'reference_artifact_id':reference['id'],'reference_artifact_sha256':reference['sha256'],'reference_kind':reference['kind'],
  'guide_source_pointer':args['guide_source_pointer'],'candidate_id':row.get('id'),'guide_5to3':guide,
  'guide_sequence_sha256':digest(guide.encode()),'source_chemistry':row.get('chemistry'),'source_calculation_scope':row.get('calculation_scope'),
  'reference':ref['reference'],'reference_sequence_sha256':target_sha,'reference_start_1_based':start,'reference_end_1_based':end,
  'reference_window_5to3':window,'reference_window_sha256':digest(window.encode()),
  'parameters':{k:args[k]for k in ('accessibility_window_size','maximum_base_pair_span','seed_base_pairs','temperature_celsius','max_interactions','representation')}}

def configuration():
 path=Path(__file__).parents[1]/'configs/rna-interaction-runtime.json';cfg=json.loads(path.read_text())
 for name,expected in cfg['assets'].items():
  if file_digest(name)!=expected:raise ValueError('IntaRNA fixed runtime fingerprint mismatch: '+Path(name).name)
 return cfg

def cache_key(root,source,reference,args):
 bound=prepare(source,reference,args);cfg=configuration()
 code={n:digest((Path(root)/'evida'/n).read_bytes())for n in ('rna_interaction.py','contracts.py','science.py','runner.py')}
 return digest(json.dumps({'bound_input':bound,'fixed_runtime':cfg,'code':code},sort_keys=True).encode())

def kill_group(process):
 try:os.killpg(process.pid,signal.SIGKILL)
 except ProcessLookupError:pass

def parse_rows(text,bound):
 reader=csv.DictReader(io.StringIO(text),delimiter=';')
 needed={'seq1','seq2','start1','end1','start2','end2','E','ED1','ED2','E_hybrid','Etotal'}
 if not reader.fieldnames or not needed<=set(reader.fieldnames)or len(reader.fieldnames)!=len(set(reader.fieldnames)):raise ValueError('Author CSV has missing/duplicate required columns.')
 rows=[]
 for index,raw in enumerate(reader):
  if None in raw or any(v is None for v in raw.values()):raise ValueError('Incomplete author CSV row.')
  if raw['seq1']!=bound['reference_window_5to3']or raw['seq2']!=bound['guide_5to3']:raise ValueError('Author output sequence identity differs from staged input.')
  coords=[int(raw[k])for k in ('start1','end1','start2','end2')];s1,e1,s2,e2=coords
  if not 1<=s1<=e1<=len(raw['seq1'])or not 1<=s2<=e2<=len(raw['seq2']):raise ValueError('Author output coordinates outside exact input.')
  energies={k:float(raw[k])for k in ('E','Etotal','ED1','ED2','E_hybrid')}
  if not all(math.isfinite(v)for v in energies.values()):raise ValueError('Nonfinite core author energy.')
  rows.append({'author_output_row_index':index,'candidate_id':bound['candidate_id'],'guide_source_pointer':bound['guide_source_pointer'],
   'source_artifact_id':bound['source_artifact_id'],'source_artifact_sha256':bound['source_artifact_sha256'],
   'reference_artifact_id':bound['reference_artifact_id'],'reference_artifact_sha256':bound['reference_artifact_sha256'],
   'target_window_start_1_based':s1,'target_window_end_1_based':e1,'guide_start_1_based':s2,'guide_end_1_based':e2,
   'transcript_start_1_based':bound['reference_start_1_based']+s1-1,'transcript_end_1_based':bound['reference_start_1_based']+e1-1,
   'energy_kcal_mol':energies,'author_fields':raw,'representation':'unmodified_sequence_proxy'})
 if len(rows)>bound['parameters']['max_interactions']:raise ValueError('Author returned more rows than requested.')
 return rows,reader.fieldnames

def run(bound,work):
 cfg=configuration();work=Path(work);work.mkdir(exist_ok=False);params=bound['parameters']
 (work/'input-binding.json').write_text(json.dumps(bound,ensure_ascii=False,indent=2)+'\n')
 (work/'target.fa').write_text('>target\n'+bound['reference_window_5to3']+'\n');(work/'query.fa').write_text('>query\n'+bound['guide_5to3']+'\n')
 output=work/'author-output.csv';log_path=work/'author.log'
 command=[cfg['binary'],'--target=target.fa','--query=query.fa','--threads=1','--mode=H','--model=X','--energy=V','--energyVRNA=Turner04','--acc=C',
  '--accW='+str(params['accessibility_window_size']),'--accL='+str(params['maximum_base_pair_span']),'--seedBP='+str(params['seed_base_pairs']),
  '--temperature='+str(params['temperature_celsius']),'--outMode=C','--outCsvCols=*','--outNumber='+str(params['max_interactions']),
  '--outOverlap=B','--outMaxE=0','--outDeltaE=100','--out=author-output.csv']
 env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','CUDA_VISIBLE_DEVICES':''}
 started=time.monotonic();receipt={'manifest_sha256':file_digest(Path(__file__).parents[1]/'configs/rna-interaction-runtime.json'),
  'binary_version':cfg['version'],'linked_vienna_version':cfg['vienna_version'],'threads':1,'timeout_seconds':cfg['timeout_seconds'],
  'output_limit_bytes':cfg['output_limit_bytes'],'log_limit_bytes':cfg['log_limit_bytes'],'cancel_file':'intarna.cancel','command':command,
  'fixed_model':{'mode':'H','model':'X','energy':'V','energyVRNA':'Turner04','accessibility':'C','outOverlap':'B','outMaxE':0,'outDeltaE':100,'outCsvCols':'*'},
  'runtime_assets_digest':digest(json.dumps(cfg['assets'],sort_keys=True).encode())}
 (work/'runtime-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 (work/'progress.json').write_text(json.dumps({'status':'running','elapsed_seconds':0,'completed':False}))
 process=subprocess.Popen(command,cwd=work,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
 sel=selectors.DefaultSelector();sel.register(process.stdout,selectors.EVENT_READ);reason=None;count=0
 try:
  with log_path.open('xb')as log:
   while process.poll()is None or sel.get_map():
    elapsed=time.monotonic()-started
    if (work/'intarna.cancel').exists():reason='cancelled'
    elif elapsed>cfg['timeout_seconds']:reason='timeout'
    elif output.exists()and output.stat().st_size>cfg['output_limit_bytes']:reason='output_limit'
    if reason:kill_group(process);break
    for key,_ in sel.select(.05):
     block=os.read(key.fileobj.fileno(),8192)
     if not block:sel.unregister(key.fileobj);continue
     log.write(block[:max(0,cfg['log_limit_bytes']-count)]);count+=len(block)
     if count>cfg['log_limit_bytes']:reason='log_limit';break
    if reason:kill_group(process);break
    (work/'progress.json').write_text(json.dumps({'status':'running','elapsed_seconds':round(elapsed,3),'completed':False,'author_csv_bytes':output.stat().st_size if output.exists()else 0}))
 finally:
  sel.close();process.stdout.close();kill_group(process)
  try:process.wait(timeout=1)
  except subprocess.TimeoutExpired:raise RuntimeError('IntaRNA process did not exit within bounded cleanup.')
 if output.exists()and output.stat().st_size>cfg['output_limit_bytes']:reason='output_limit'
 raw_text=None;rows=[];columns=[];parse_error=None
 if not reason and process.returncode==0 and output.is_file():
  try:raw_text=output.read_bytes().decode('utf-8');rows,columns=parse_rows(raw_text,bound)
  except (ValueError,UnicodeError)as exc:parse_error=str(exc);reason='invalid_author_output'
 elif not reason:reason='author_process_failure'
 retained=[]
 for path in [work/'target.fa',work/'query.fa',work/'input-binding.json',output,log_path,work/'runtime-receipt.json']:
  if path.is_file():retained.append({'file':path.name,'sha256':file_digest(path),'bytes':path.stat().st_size})
 status='failed'if reason else'succeeded'
 result={'status':status,'semantic_type':'source_bound_rna_rna_interactions_unmodified_proxy','rows':rows,'author_columns':columns,
  'source_binding':bound,'runtime_receipt':receipt,'retained_files':retained,'error':reason,'parse_error':parse_error,
  'process_exit_code':process.returncode,'observed_log_bytes':count,'log_truncated':count>cfg['log_limit_bytes'],
  'raw_csv_text':raw_text,'raw_csv_sha256':file_digest(output)if output.exists()else None,
  'energy_semantics':ENERGY_MEANING,'limits':LIMITS,'elapsed_seconds':round(time.monotonic()-started,6),'model_calls':0,'gpu_used':False,
  'summary':{'reported_interactions':len(rows),'reporting_status':'not_completed'if reason else('interactions_reported'if rows else'no_interaction_reported_under_named_constraints'),
             'guide_length':len(bound['guide_5to3']),'target_window_length':len(bound['reference_window_5to3']),'whole_transcript_or_transcriptome_scanned':False}}
 (work/'progress.json').write_text(json.dumps({'status':status,'elapsed_seconds':result['elapsed_seconds'],'completed':not bool(reason),'reported_interactions':len(rows),'error':reason}))
 return result
