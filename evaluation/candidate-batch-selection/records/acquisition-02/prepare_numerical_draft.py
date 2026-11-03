"""Freeze preparation for authorized numerical-only correction; no selection or gold."""
import json
from pathlib import Path
from common import HERE,load,save,sha,utc
old=HERE.parent/'acquisition-01';protocol=load(old/'protocol.json')
checks=load(HERE/'equality-prefreeze-result.json');assert checks['status']=='PASS'and checks['group_seed_checks']==110
assert 'Ran 20 tests' in (HERE/'numerical-tests.stderr').read_text()and (HERE/'numerical-tests.stderr').read_text().rstrip().endswith('OK')
for file in old.glob('*.py'):
 if file.name!='acquisition.py':assert sha(file)==sha(HERE/file.name),file.name
amend=load(HERE/'technical-amendment.json')
for rel,pin in amend['preserved_original_hashes'].items():
 if rel.endswith('scored-results.json'):continue # Already recorded; do not reopen label-derived results here.
 assert sha(HERE.parent/rel)==pin,rel
current={**protocol,'status':'DRAFT_NUMERICAL_CORRECTION_AUTHORIZED','at':utc(),'technical_amendment':'technical-amendment.json','parent_protocol_sha256':sha(old/'protocol.json'),'source_pins':{str(p):sha(p)for p in HERE.glob('*.py')},'input_pins':dict(protocol['input_pins'])}
for name in ['technical-amendment.json','numerical-only.patch','equality-prefreeze-result.json','numerical-tests.stdout','numerical-tests.stderr','setup-attempt-01-numerical-tests.stdout','setup-attempt-01-numerical-tests.stderr']:
 p=HERE/name;current['input_pins'][str(p)]=sha(p)
for rel,pin in amend['preserved_original_hashes'].items():
 if not rel.endswith('scored-results.json'):current['input_pins'][str(HERE.parent/rel)]=pin
assert not any('evaluation-only' in x or 'test-gold' in x or 'scored-results' in x for x in current['input_pins'])
science={k:v for k,v in protocol.items()if k not in ['status','at','source_pins','input_pins']}
assert all(current[k]==v for k,v in science.items())
save(HERE/'protocol-draft.json',current)
save(HERE/'numerical-readiness.json',{'at':utc(),'status':'READY_FOR_AUTHORIZED_FREEZE','draft_sha256':sha(HERE/'protocol-draft.json'),'all_original_scientific_fields_equal':True,'runtime_files_changed':['acquisition.py'],'synthetic_tests_passed':20,'real_equal_group_seed_checks':110,'new_gold_reads':0,'actual_selection_runs':0,'automatic_retries':0})
print(json.dumps({'status':'READY','draft_sha256':sha(HERE/'protocol-draft.json'),'source_pins':len(current['source_pins']),'input_pins':len(current['input_pins'])}))
