"""Append terminal neural records ONLY after coordinator scoring/review.
Never trains, scores, unseals or retries. All 60 planned receipts are required.
"""
from pathlib import Path
import argparse
from datetime import datetime,timezone
import json
from assemble_snapshot import sanitize
from verify_package import HERE,sha,read,require,original_hash,verify

def append(source,coordinator_approved):
    require(coordinator_approved,'Explicit coordinator approval is required')
    verify();source=Path(source).resolve()
    require(not read(HERE/'finetune-status.json')['results_included'],'Terminal archive already present')
    protocol=read(source/'protocol.json');completion=read(source/'run-01/completion.json')
    require(sha(source/'protocol.json')==original_hash('chemeleon-finetune-trial/protocol.json'),'Different protocol; do not merge')
    for file,digest in protocol['source_pins'].items():require(sha(source/file)==digest,'Source drift: '+file)
    expected=[(t['task'],arm) for t in protocol['tasks'] for arm in protocol['arms']]
    require(len(expected)==60,'Expected 60 planned neural arms')
    require([(r['task'],r['arm']) for r in completion['attempts']]==expected,'Incomplete terminal denominator')
    require(completion['protocol_sha256']==sha(source/'protocol.json'),'Completion/protocol mismatch')
    scored=read(source/'run-01/scored-results.json');seal=source/'run-01/sealed-predictions.json'
    require(scored['prediction_seal_sha256']==sha(seal),'Scored seal mismatch')
    require(scored['protocol_sha256']==sha(source/'protocol.json'),'Scored protocol mismatch')
    terminal={'completed','failed','timed_out','failed_missing_predictions','not_started_resource_busy','not_started_time_budget'}
    successes=0
    for row in completion['attempts']:
        require(row['status'] in terminal,'Unknown/nonterminal arm status')
        if row['prediction_sha256']:
            require(sha(source/'run-01'/row['task']/row['arm']/'predictions.json')==row['prediction_sha256'],'Prediction changed')
        if row['status']=='completed':successes+=1
    require(scored['planned_neural_arms']==60 and scored['completed_neural_arms']==successes,'Scored denominator mismatch')
    files=[]
    for path in (source/'run-01').rglob('*'):
        if path.is_file() and path.suffix in {'.json','.log','.csv','.yaml','.yml'}:
            files.append(path)
    source_map=read(HERE/'source-map.json')
    for path in sorted(files):
        destination=HERE/'chemeleon-finetune-trial'/path.relative_to(source)
        require(not destination.exists(),'Archive destination already exists: '+str(destination.relative_to(HERE)))
        raw=path.read_bytes();public=sanitize(raw.decode()).replace(str(source),'<neural-trial>').encode()
        # Logger paths may use a different source root; mapped explicitly above.
        destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(public)
        source_map['files'].append({'original_logical_name':'chemeleon-finetune-trial/'+str(path.relative_to(source)),
          'public_path':str(destination.relative_to(HERE)),'original_sha256':sha(path),'public_sha256':sha(destination),
          'transformation':'unchanged' if raw==public else 'workstation paths/GPU identifier replaced; scientific content retained'})
    (HERE/'source-map.json').write_text(json.dumps(source_map,indent=2,ensure_ascii=False)+'\n')
    result={'status':'TERMINAL_COORDINATOR_SCORED_ARCHIVE','planned_tasks':30,'planned_neural_arms':60,
      'completed_neural_arms':successes,'terminal_receipts':60,'results_included':True,'coordinator_approved':True,
      'packaged_at_utc':datetime.now(timezone.utc).isoformat(),'raw_scored_results':'chemeleon-finetune-trial/run-01/scored-results.json',
      'copied_files':len(files),'checkpoints_included':False,'raw_checkpoint_hashes_retained_in_fit_records':True,
      'training_calls_during_packaging':0,'scoring_calls_during_packaging':0}
    (HERE/'finetune-status.json').write_text(json.dumps(result,indent=2)+'\n')
    # The manifest must be regenerated only after documentation/content review.
    return {**result,'next_step':'Review terminal findings and documentation, then regenerate manifest and verify.'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--coordinator-approved',action='store_true')
    print(json.dumps(append(**vars(p.parse_args())),indent=2))
