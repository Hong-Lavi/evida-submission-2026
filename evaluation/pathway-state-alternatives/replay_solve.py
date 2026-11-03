"""Optional local replay with an authorized LP and the exactly pinned CBC.

This script is provided for reproduction; packaging did not execute it.
No downloads, installation, model calls or automatic retries.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
from verify_full_primal import query_bytes

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-lp', type=Path, required=True)
    parser.add_argument('--cbc', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--slot', choices=['00-baseline','01-without-GSK3B','02-without-MDM2'], required=True)
    args = parser.parse_args()
    experiment = json.loads((HERE/'experiment.json').read_text())
    environment = json.loads((HERE/'environment-and-sources.json').read_text())
    base = args.base_lp.read_bytes()
    assert hashlib.sha256(base).hexdigest() == experiment['baseline_original_lp_sha256']
    assert hashlib.sha256(args.cbc.read_bytes()).hexdigest() == environment['CBC_binary_sha256']
    slot = next(r for r in experiment['slots'] if r['slot'] == args.slot)
    query = query_bytes(base, slot['added_constraints'])
    assert hashlib.sha256(query).hexdigest() == slot['query_lp_sha256']
    args.output.mkdir(parents=True, exist_ok=False)
    output = args.output.resolve(); lp = output/'query.lp'; lp.write_bytes(query)
    command = [str(args.cbc.resolve()),'-import',str(lp),'-seconds','120','-ratioGap','0.0001',
               '-threads','1','-solve','-printi','csv','-solution',str(output/'solution.csv')]
    (output/'command.json').write_text(json.dumps(command,indent=2))
    timeout = False
    with (output/'solver.log').open('xb') as log:
        proc = subprocess.Popen(command,cwd=output,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,
            env={'PATH':str(args.cbc.resolve().parent)+':/usr/bin:/bin','LANG':'C','LC_ALL':'C','TZ':'UTC',
                 'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','CUDA_VISIBLE_DEVICES':''})
        try:code=proc.wait(timeout=180)
        except subprocess.TimeoutExpired:
            timeout=True;os.killpg(proc.pid,signal.SIGTERM)
            try:proc.wait(timeout=3)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
            code=proc.returncode
    (output/'execution.json').write_text(json.dumps({'returncode':code,'outer_timeout':timeout,'retry':False},indent=2))


if __name__=='__main__':main()
