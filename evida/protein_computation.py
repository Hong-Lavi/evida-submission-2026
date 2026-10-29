"""Exact saved structure/trajectory inputs for author protein computations."""
import base64
import json
from pathlib import Path
from .protonation import digest, file_digest


def prepare(source, args, tool):
    if source['id'] != args.get('artifact_id') or digest(source['content']) != source['sha256']:
        raise ValueError('Select the exact saved artifact with matching original bytes.')
    body = json.loads(source['content'])
    out = {'tool': tool, 'source_artifact_id': source['id'], 'source_artifact_sha256': source['sha256']}
    if tool == 'trajectory_analysis':
        if set(args) != {'artifact_id', 'alignment'} or args['alignment'] not in ('ca', 'backbone'):
            raise ValueError('Choose CA or backbone alignment for the saved trajectory.')
        if source['kind'] != 'protein_dynamics' or body.get('status') != 'succeeded':
            raise ValueError('A completed saved OpenMM trajectory is required.')
        files = body['trajectory_files']
        for key, encoded in [('topology_pdb', False), ('trajectory_dcd', True)]:
            raw = base64.b64decode(files[key]['base64'], validate=True) if encoded else files[key]['text'].encode()
            if len(raw) > 12*1024*1024 or digest(raw) != files[key]['sha256']:
                raise ValueError('Saved topology/trajectory bytes do not match.')
        return {**out, 'files': files, 'alignment': args['alignment'], 'simulation_conditions': body['simulation_conditions']}
    fields = {'artifact_id', 'chain_ids'}
    if tool == 'protein_dynamics':
        fields |= {'temperature_kelvin', 'ph', 'steps', 'timestep_femtoseconds', 'random_seed'}
    elif tool != 'structure_pockets': raise ValueError('Unknown structure computation.')
    if set(args) != fields or source['kind'] != 'target_structure' or body.get('status') != 'succeeded':
        raise ValueError('Use a saved biological assembly and explicit calculation fields.')
    chains = args['chain_ids']
    available = {r['chain'] for r in body['rows'] if r.get('kind') == 'protein_chain'}
    if not isinstance(chains, list) or not 1 <= len(chains) <= 4 or len(chains) != len(set(chains)) or set(chains)-available:
        raise ValueError('Select one to four distinct protein chains present in the saved assembly.')
    if digest(body['original_cif'].encode()) != body['source']['sha256']:
        raise ValueError('Saved experimental coordinate response does not match its source hash.')
    if tool == 'protein_dynamics':
        if any(r.get('internal_numbering_gaps') for r in body['rows'] if r.get('chain') in chains and r.get('kind') == 'protein_chain'):
            raise ValueError('Missing internal residues need an explicit reviewed structural model before dynamics.')
        for key, lo, hi in [('temperature_kelvin', 250, 350), ('ph', 0, 14), ('steps', 100, 500000),
                            ('timestep_femtoseconds', .5, 2), ('random_seed', 1, 2147483647)]:
            if type(args[key]) not in (int, float) or not lo <= args[key] <= hi:
                raise ValueError('Invalid explicit dynamics parameter: '+key)
        if type(args['steps']) is not int or type(args['random_seed']) is not int:
            raise ValueError('Steps and seed must be integers.')
    return {**out, 'cif': body['original_cif'], 'structure_source': body['source'],
            'chain_ids': chains, 'parameters': {k: v for k, v in args.items() if k not in ('artifact_id','chain_ids')}}


def configuration():
    cfg = json.loads((Path(__file__).parents[1]/'configs/protein-computation-runtime.json').read_text())
    if file_digest(cfg['fpocket']) != cfg['fpocket_sha256']: raise ValueError('fpocket executable changed.')
    return cfg


def cache_key(root, source, args, tool):
    return digest(json.dumps({'input': prepare(source,args,tool),'runtime':configuration(),
        'code':{n:file_digest(Path(root)/'evida'/n)for n in
            ('protein_computation.py','protein_computation_worker.py','runner.py','science.py')}},sort_keys=True).encode())


import os
import selectors
import subprocess
import time
from .protonation import kill_group

def run(request, work):
    cfg = configuration()
    work = Path(work); work.mkdir(exist_ok=False)
    incoming, output = work/'request.json', work/'result.json'
    incoming.write_text(json.dumps({'input': request, 'runtime': cfg}))
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'CUDA_VISIBLE_DEVICES': '',
           'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
           'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'}
    start = time.monotonic()
    process = subprocess.Popen([cfg['python'], '-B',
        str(Path(__file__).with_name('protein_computation_worker.py')), str(incoming), str(output)],
        cwd=work, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
    selector = selectors.DefaultSelector(); selector.register(process.stdout, selectors.EVENT_READ)
    reason = None; count = 0
    try:
        with (work/'worker.log').open('xb') as log:
            while process.poll() is None or selector.get_map():
                if (work/'cancel').exists(): reason = 'cancelled'
                elif time.monotonic()-start > cfg['timeout_seconds']: reason = 'timeout'
                elif sum(p.stat().st_size for p in work.rglob('*') if p.is_file()) > cfg['output_limit_bytes']:
                    reason = 'output_limit'
                if reason: break
                for key, _ in selector.select(.05):
                    block = os.read(key.fileobj.fileno(), 8192)
                    if not block: selector.unregister(key.fileobj); continue
                    log.write(block[:max(0, cfg['log_limit_bytes']-count)]); count += len(block)
                    if count > cfg['log_limit_bytes']: reason = 'log_limit'
    finally:
        selector.close(); process.stdout.close(); kill_group(process)
        process.wait(timeout=2)
    if sum(p.stat().st_size for p in work.rglob('*') if p.is_file()) > cfg['output_limit_bytes']:
        reason = 'output_limit'
    if reason or process.returncode or not output.exists():
        progress = work/'progress.json'
        body = json.loads(progress.read_text()) if progress.exists() and progress.stat().st_size < cfg['output_limit_bytes'] else {'rows': []}
        body.update(status='failed', error=reason or 'author_worker_failure')

    else:
        body = json.loads(output.read_text())
    body.update(source_artifact_id=request['source_artifact_id'],
        source_artifact_sha256=request['source_artifact_sha256'],
        elapsed_seconds=round(time.monotonic()-start, 6), model_calls=0, gpu_used=False,
        runtime_manifest_sha256=file_digest(Path(__file__).parents[1]/'configs/protein-computation-runtime.json'))
    return body
