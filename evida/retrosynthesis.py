"""AiZynthFinder author search bound to exact saved candidate structures."""
import json
from pathlib import Path
from .protonation import digest, file_digest
from .molecular_preparation import prepare as molecular_binding


def prepare(source, arguments):
    fields = {'artifact_id', 'structures', 'time_limit_seconds', 'iteration_limit', 'max_transforms', 'random_seed'}
    if set(arguments) != fields: raise ValueError('Use the declared synthesis-search fields.')
    binding = molecular_binding(source, {k: arguments[k] for k in ('artifact_id', 'structures')}, 'synthetic_complexity')
    if len(binding['structures']) > 3: raise ValueError('Select at most three saved structures per search.')
    for name, lo, hi in [('time_limit_seconds', 10, 120), ('iteration_limit', 10, 200),
                         ('max_transforms', 1, 6), ('random_seed', 0, 2147483647)]:
        if type(arguments[name]) is not int or not lo <= arguments[name] <= hi:
            raise ValueError('Invalid explicit bounded search parameter: ' + name)
        binding[name] = arguments[name]
    binding['tool'] = 'retrosynthesis'
    return binding


def configuration():
    cfg = json.loads((Path(__file__).parents[1]/'configs/retrosynthesis-runtime.json').read_text())
    for path, expected in cfg['assets'].items():
        if file_digest(path) != expected: raise ValueError('Retrosynthesis asset fingerprint differs: ' + Path(path).name)
    return cfg


def cache_key(root, source, args):
    return digest(json.dumps({'input': prepare(source, args), 'runtime': configuration(),
        'code': {n: file_digest(Path(root)/'evida'/n) for n in
                 ('retrosynthesis.py', 'retrosynthesis_worker.py', 'molecular_preparation.py', 'protonation.py', 'science.py', 'runner.py')}}, sort_keys=True).encode())


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
        str(Path(__file__).with_name('retrosynthesis_worker.py')), str(incoming), str(output)],
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
        done = {row['source_pointer'] for row in body['rows']}
        body['rows'].extend({**row, 'status':'not_completed'} for row in request['structures'] if row['source_pointer'] not in done)
    else:
        body = json.loads(output.read_text())
    body.update(source_artifact_id=request['source_artifact_id'],
        source_artifact_sha256=request['source_artifact_sha256'],
        elapsed_seconds=round(time.monotonic()-start, 6), model_calls=0, gpu_used=False,
        runtime_manifest_sha256=file_digest(Path(__file__).parents[1]/'configs/retrosynthesis-runtime.json'))
    return body
