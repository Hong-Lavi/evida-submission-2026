import json, os, signal, sys
from pathlib import Path
p = Path(sys.argv[1]); out = Path(sys.argv[2]); packet = json.loads(p.read_text())
with (out / 'launch-marker.json').open('x') as f: json.dump({'launches': 1}, f)
behavior = packet['fixture_behavior']
if behavior == 'input_change': p.write_text('{}'); raise SystemExit(0)
if behavior == 'source_change': Path(packet['source_sentinel']).write_text('changed'); raise SystemExit(0)
methods = ['rf_mean','gp_mean','original_policy','random','qPO_latent','qPO_observation','pTop10_latent','pTop10_observation']
def rows(ms, seeds):
 return [{'task':packet['task'],'method':m,'seed':s,'batch':b,'status':'completed',
          'selected_ids':packet['candidate_ids'][-b:][::-1],'fallback_selected_ids':[],'failure':None}
         for m in ms for s in seeds for b in [5,10,20]]
def write(name, value):
 with (out/name).open('x') as f: json.dump(value,f)
def truncate_and_die(name):
 with (out/name).open('x') as f: f.write('[{"task":'); f.flush(); os.fsync(f.fileno())
 os.kill(os.getpid(),signal.SIGKILL)
if behavior == 'baseline_kill': truncate_and_die('baseline.json')
write('baseline.json',rows(methods[:4],range(5)))
if behavior == 'posterior_kill': truncate_and_die('posterior-seed-0.json')
for seed in range(5):
 data=rows(methods[4:],[seed])
 if behavior == 'structural_invalid' and seed == 0:
  data[0]['selected_ids'][0]=data[0]['selected_ids'][1]
 write(f'posterior-seed-{seed}.json',data)
