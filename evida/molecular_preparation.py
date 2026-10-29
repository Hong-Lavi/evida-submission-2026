"""Source-bound author software; raw variants and failures remain inspectable."""
import json
from pathlib import Path
import os
import selectors
import subprocess
import time

from .protonation import prepare as bind_protonation, digest, file_digest, kill_group

TOOLS = {'molecule_preparation', 'synthetic_complexity'}


def prepare(source, arguments, tool):
    if tool not in TOOLS:
        raise ValueError('Unknown molecular computation.')
    fields = {'artifact_id', 'structures'}
    if tool == 'molecule_preparation':
        fields |= {'ph_min', 'ph_max', 'precision', 'max_variants', 'random_seed'}
    if set(arguments) != fields:
        raise ValueError('Use the exact declared molecular computation fields.')
    # Reuse the existing exact Store-row binding and parameter validator. For
    # SCScore the pH defaults are binding-only and are never sent as model inputs.
    binding = bind_protonation(source, {
        **{k: arguments[k] for k in ('artifact_id', 'structures')},
        **{k: arguments.get(k, v) for k, v in
           {'ph_min': 7.4, 'ph_max': 7.4, 'precision': 1.0, 'max_variants': 1}.items()}})
    if tool == 'synthetic_complexity':
        for key in ('ph_min', 'ph_max', 'precision', 'max_variants'):
            binding.pop(key)
    else:
        seed = arguments['random_seed']
        if type(seed) is not int or not 0 <= seed <= 2147483647:
            raise ValueError('An explicit nonnegative 32-bit random seed is required.')
        if len(binding['structures']) > 12 or binding['max_variants'] > 16:
            raise ValueError('Select at most 12 parents and 16 variants per parent.')
        binding['random_seed'] = seed
    return dict(binding, tool=tool)


def configuration():
    path = Path(__file__).parents[1] / 'configs/molecular-preparation-runtime.json'
    cfg = json.loads(path.read_text())
    for name, expected in cfg['assets'].items():
        if file_digest(name) != expected:
            raise ValueError('Author software/model fingerprint differs: ' + Path(name).name)
    return cfg


def cache_key(root, source, arguments, tool):
    return digest(json.dumps({'input': prepare(source, arguments, tool),
        'runtime': configuration(), 'code': {name: file_digest(Path(root)/'evida'/name)
        for name in ('molecular_preparation.py', 'molecular_preparation_worker.py',
                     'protonation.py', 'runner.py', 'science.py')}}, sort_keys=True).encode())


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
        str(Path(__file__).with_name('molecular_preparation_worker.py')), str(incoming), str(output)],
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
        runtime_manifest_sha256=file_digest(Path(__file__).parents[1]/'configs/molecular-preparation-runtime.json'))
    return body
