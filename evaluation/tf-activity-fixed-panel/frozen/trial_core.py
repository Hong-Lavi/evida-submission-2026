"""Frozen-input, availability and seal rules. No label reading or scientific fitting."""
from pathlib import Path
import csv,hashlib,json,math,os,tempfile
LABEL_BASENAMES={'selection-labels.json','all-907-shuffled-selection.json','knockTF_meta.csv'}
STATUSES={'succeeded','failed_method','failed_nonfinite_or_schema','failed_timeout','failed_memory','not_started_arm_deadline','skipped_source_integrity_stop'}
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for x in iter(lambda:f.read(1048576),b''):h.update(x)
 return h.hexdigest()
def load(p):return json.loads(Path(p).read_text())
def atomic_new(p,data):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(prefix=p.name+'.tmp-',dir=p.parent)
 try:
  with os.fdopen(fd,'w') as f:json.dump(data,f,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
  os.link(tmp,p) # Exclusive final name; never replace a terminal record.
 finally:
  Path(tmp).unlink(missing_ok=True)
def canonical_hash(x):return hashlib.sha256(json.dumps(x,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()
def result_name(arm,task):return f'results/{arm}/{task}.json'
def planned(protocol):return [(a,t) for a in protocol['arms'] for t in a['task_order']]
def verify_sources(protocol):
 freeze=Path(__file__).parent/'execution-freeze.json'
 if freeze.exists():
  for name,h in load(freeze)['files'].items():assert sha(freeze.parent/name)==h,('Execution pin changed',name)
 for name,h in protocol['source_pins'].items():
  if Path(name).name not in LABEL_BASENAMES:assert sha(name)==h,('Source pin changed',name)
 config=load(Path(__file__).parent/protocol['runtime_config_file'])
 assert sha(config['rscript'])==config['rscript_sha256']
 for x in list(config['runtime_files'].values())+list(config['resources'].values()):assert sha(x['path'])==x['sha256'],x['path']
 return config

def read_packets(protocol):
 out={}
 for name,h in protocol['packet_sha256'].items():
  p=Path(protocol['input_packet_directory'])/name;assert sha(p)==h
  x=load(p);assert set(x)=={'task_id','gene_values'} and x['task_id']==p.stem
  vals=x['gene_values'];assert vals and all(set(v)=={'gene','value'} for v in vals)
  assert len({v['gene'] for v in vals})==len(vals)
  assert all(isinstance(v['gene'],str) and v['gene'] and type(v['value']) in (int,float) and math.isfinite(v['value']) for v in vals)
  out[x['task_id']]=x
 return out

def networks(protocol):
 out={}
 for name,res in protocol['priors'].items():
  assert sha(res['path'])==res['sha256'];rows=list(csv.DictReader(open(res['path']),delimiter='\t'))
  assert len({(x['source'],x['target']) for x in rows})==len(rows)
  assert all(math.isfinite(float(x['mor'])) and float(x['mor'])!=0 for x in rows)
  out[name]=rows
 return out

def view(packet,representation):
 assert representation in {'stored_zero','omit_zero'}
 vals=packet['gene_values']
 if representation=='omit_zero':vals=[v for v in vals if v['value']!=0]
 return vals

def eligible(vals,net):
 genes={v['gene'] for v in vals};targets={}
 for x in net:
  if x['target'] in genes:targets.setdefault(x['source'],set()).add(x['target'])
 return sorted(tf for tf,ts in targets.items() if len(ts)>=5)

def expected_sources(arm,vals,nets):
 if arm['method']=='own_expression':
  union={x['source'] for rows in nets.values() for x in rows};genes={v['gene'] for v in vals};return sorted(union&genes)
 return eligible(vals,nets[arm['prior']])

def record_base(protocol,arm,packet):
 vals=view(packet,arm['representation'])
 return {'arm_id':arm['arm_id'],'task_id':packet['task_id'],'method':arm['method'],'prior':arm['prior'],'representation':arm['representation'],'input_sha256':protocol['packet_sha256'][packet['task_id']+'.json'],'derived_gene_count':len(vals),'derived_view_sha256':canonical_hash(vals),'score_rows':[],'error':None}

def validate_success(record,arm,packet,nets):
 vals=view(packet,arm['representation']);expect=expected_sources(arm,vals,nets)
 rows=record['score_rows'];assert len(rows)==len(expect)
 assert sorted(x['source'] for x in rows)==expect
 assert len({x['source'] for x in rows})==len(rows)
 assert all(type(x['score']) in (int,float) and math.isfinite(x['score']) for x in rows)
 if arm['method']=='own_expression':
  values={v['gene']:v['value'] for v in vals};assert all(x['score']==values[x['source']] for x in rows)
 return True

def secure_file(root,relative):
 root=Path(root).resolve();p=root/relative
 assert not Path(relative).is_absolute() and '..' not in Path(relative).parts
 assert p.resolve().is_relative_to(root) and not p.is_symlink()
 return p

def validate_failure(root,files,x,arm,packet,nets):
 status=x['status'];task=packet['task_id']
 assert not x['score_rows'] and isinstance(x.get('error'),str) and x['error']
 marker_rel=f"call-started/{arm['arm_id']}/{task}.json";marker=root/marker_rel
 if status=='not_started_arm_deadline':
  assert not marker.exists() and not x.get('call_dir')
  return
 if x.get('terminal_origin')=='supervisor_recovery':
  assert marker_rel in files and 'supervisor-receipt.json' in files
  supervisor=load(root/'supervisor-receipt.json');reason=supervisor['reason']
  assert supervisor['source_integrity_valid'] and supervisor['child_exitcode']!=0
  assert status==('failed_timeout' if reason=='outer_deadline' else 'failed_nonfinite_or_schema')
  assert reason in {'outer_deadline','runner_failed','supervisor_interrupted'}
  assert x['error']==f'{reason}; dispatched=True'
  assert load(marker)['call_dir']==x['call_dir']
  return
 assert arm['method']!='own_expression' and marker_rel in files
 call=secure_file(root,x['call_dir']);rel=str(call.relative_to(root))
 assert load(marker)['call_dir']==x['call_dir'] and rel+'/request.json' in files
 request=load(call/'request.json');vals=view(packet,arm['representation'])
 assert request['method']==arm['method']
 assert request['genes']==[v['gene'] for v in vals]
 ids=[z['task_id'] for z in request['tasks']]
 assert ids==(arm['task_order'] if arm['batching']=='one_30_column_matrix' else [task])
 assert next(z for z in request['tasks'] if z['task_id']==task)['values']==[v['value'] for v in vals]
 receipt_path=call/'receipt.json';raw=None;parse_error=False
 if not receipt_path.exists():
  assert status=='failed_nonfinite_or_schema' and rel+'/dispatch-error.json' in files
  assert load(call/'dispatch-error.json')['error']==x['error']
  assert not (call/'raw-result.json').exists()
  return
 assert rel+'/receipt.json' in files;receipt=load(receipt_path)
 assert receipt['method']==arm['method'] and receipt['task_ids']==ids
 assert receipt['request_sha256']==sha(call/'request.json')
 assert receipt['method_worker_sha256']==sha(Path(__file__).parent/'method_worker.R')
 if receipt['status']=='failed_timeout':
  assert status=='failed_timeout' and receipt['returncode']!=0
  return
 assert receipt['status']=='exited'
 if receipt['returncode']!=0:
  assert status=='failed_method'
  return
 try:
  assert rel+'/raw-result.json' in files
  raw=load(call/'raw-result.json')
 except (OSError,ValueError,AssertionError):parse_error=True
 if parse_error:
  assert status=='failed_nonfinite_or_schema'
  return
 if isinstance(raw,dict) and raw.get('status')=='failed_method':
  msg=str(raw.get('error',''))
  memory=any(z in msg.lower() for z in ('cannot allocate vector','cannot allocate memory','memory exhausted'))
  assert status==('failed_memory' if memory else 'failed_method') and msg
  return
 assert status=='failed_nonfinite_or_schema'
 from worker_runtime import extract_scores
 try:
  scores=extract_scores(raw,arm['method'],task)
  probe=dict(x,score_rows=scores);validate_success(probe,arm,packet,nets)
 except (AssertionError,ValueError,TypeError,KeyError):return
 raise AssertionError('Claimed failure contradicts complete successful raw output')

def gate(protocol,run_dir,verify_inputs=True):
 """Full output gate. Deliberately cannot load labels; scorer does that only afterward."""
 root=Path(run_dir).resolve();seal=load(root/'terminal-seal.json')
 assert seal['status']=='complete_terminal' and seal['source_integrity_valid']
 assert seal['protocol_sha256']==sha(Path(__file__).parent/'protocol.json')
 if verify_inputs:
  verify_sources(protocol)
  here=Path(__file__).parent;freeze=load(here/'execution-freeze.json')
  for name,h in freeze['files'].items():assert sha(here/name)==h,('Execution code changed',name)
  started=load(root/'run-started.json');assert started['execution_freeze_sha256']==sha(here/'execution-freeze.json')
 packets=read_packets(protocol);nets=networks(protocol)
 pairs=planned(protocol);assert len(pairs)==protocol['planned_terminal_rows']
 files=seal['files'];records={}
 actual_files={str(q.relative_to(root)) for q in root.rglob('*') if q.is_file() and q!=root/'terminal-seal.json'}
 assert set(files)==actual_files,'All retained artifacts must be sealed exactly once'
 for rel,h in files.items():assert sha(secure_file(root,rel))==h,('Output hash mismatch',rel)
 expected_names={result_name(a['arm_id'],t) for a,t in pairs}
 actual_names={str(p.relative_to(root)) for p in (root/'results').rglob('*.json')}
 assert actual_names==expected_names
 assert seal['terminal_rows']==len(pairs)
 for arm,task in pairs:
  rel=result_name(arm['arm_id'],task);assert rel in files
  x=load(root/rel);base=record_base(protocol,arm,packets[task])
  for k in ('arm_id','task_id','method','prior','representation','input_sha256','derived_gene_count','derived_view_sha256'):assert x[k]==base[k],(rel,k)
  assert x['status'] in STATUSES
  if x['status']=='succeeded':
   validate_success(x,arm,packets[task],nets)
   if arm['method']!='own_expression':
    from worker_runtime import extract_scores
    call=secure_file(root,x['call_dir']);rel=str(call.relative_to(root))
    assert rel+'/receipt.json' in files and rel+'/request.json' in files and rel+'/raw-result.json' in files
    receipt=load(call/'receipt.json');raw=load(call/'raw-result.json');request=load(call/'request.json')
    assert receipt['status']=='exited' and receipt['returncode']==0
    assert receipt['request_sha256']==sha(call/'request.json') and receipt['method']==arm['method'] and task in receipt['task_ids']
    assert request['method']==arm['method'] and request['network_path']==protocol['priors'][arm['prior']]['path']
    vals=view(packets[task],arm['representation']);assert request['genes']==[v['gene'] for v in vals]
    ids=[z['task_id'] for z in request['tasks']]
    assert ids==(arm['task_order'] if arm['batching']=='one_30_column_matrix' else [task])
    assert receipt['task_ids']==ids
    assert all(z['condition'] in ids and z['statistic'] in ({'wmean','norm_wmean','corr_wmean'} if arm['method']=='wmean' else {arm['method']}) for z in raw['rows'])
    assert receipt['method_worker_sha256']==sha(Path(__file__).parent/'method_worker.R')
    req_task=next(z for z in request['tasks'] if z['task_id']==task);assert req_task['values']==[v['value'] for v in vals]
    assert x['score_rows']==extract_scores(raw,arm['method'],task)
    if verify_inputs:
     cfg=load(Path(__file__).parent/protocol['runtime_config_file'])
     desc=next(v['path'] for k,v in cfg['runtime_files'].items() if k.endswith('/DESCRIPTION'))
     assert Path(raw['package_path']).resolve()==Path(desc).parent.resolve()
     assert Path(raw['r_home']).resolve()==Path(cfg['rscript']).parent.parent.joinpath('lib/R').resolve()
  else:
   validate_failure(root,files,x,arm,packets[task],nets)
   if x.get('call_dir') and x.get('terminal_origin')!='supervisor_recovery':
    req=load(secure_file(root,x['call_dir'])/'request.json');assert req['network_path']==protocol['priors'][arm['prior']]['path']
  for ref in x.get('artifacts',[]):
   assert ref['path'] in files and ref['sha256']==files[ref['path']]
  records[(arm['arm_id'],task)]=x
 return records,packets,nets

def rank_metrics(scores,target):
 assert target in scores and len(scores)>=2 and all(math.isfinite(x) for x in scores.values())
 value=scores[target];a=sum(v<value for v in scores.values());m=sum(v==value for v in scores.values());rank=a+(m+1)/2
 return {'universe_size':len(scores),'rank':rank,'reciprocal_rank':1/rank,'normalized_rank':(rank-1)/(len(scores)-1),'top1':min(1,max(0,(1-a)/m)),'top5':min(1,max(0,(5-a)/m))}

def pair_eval(rec_a,rec_b,universe,target):
 if target not in universe:return {'status':'target_unavailable','metrics_a':None,'metrics_b':None}
 if len(universe)<2:return {'status':'universe_less_than_two','metrics_a':None,'metrics_b':None}
 if rec_a['status']!='succeeded' or rec_b['status']!='succeeded':return {'status':'method_unusable','metrics_a':None,'metrics_b':None}
 sa={x['source']:x['score'] for x in rec_a['score_rows']};sb={x['source']:x['score'] for x in rec_b['score_rows']}
 if any(tf not in sa or tf not in sb or not math.isfinite(sa[tf]) or not math.isfinite(sb[tf]) for tf in universe):return {'status':'required_score_unavailable','metrics_a':None,'metrics_b':None}
 ma=rank_metrics({tf:sa[tf] for tf in universe},target);mb=rank_metrics({tf:sb[tf] for tf in universe},target)
 return {'status':'paired_valid','metrics_a':ma,'metrics_b':mb,'delta_b_minus_a':{k:mb[k]-ma[k] for k in ('normalized_rank','reciprocal_rank','top1','top5')}}
