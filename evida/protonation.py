"""Bounded author protonation; exact Store inputs, never an efficacy score."""
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

FIELDS = {'artifact_id', 'structures', 'ph_min', 'ph_max', 'precision', 'max_variants'}
KINDS = {'molecule_csv', 'compound_candidates', 'literature_compounds', 'binding_measurements',
         'rdkit', 'admet', 'analogue_proposal', 'source_candidates'}
LIMITS = ['Bounded author protonation enumeration, not measured pKa or state populations.',
          'No affinity, BBB, efficacy, biological direction or therapeutic recommendation.',
          'All returned states and row failures are retained; reaching the variant budget is flagged.']

def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def file_digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def kill_group(process):
    # The session leader may already have exited while a descendant holds its pipe.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def prepare(source, args):
    if set(args) != FIELDS or source['id'] != args['artifact_id']:
        raise ValueError('Exact named source and author parameters are required.')
    raw = source['content']
    actual = digest(raw)
    if actual != source['sha256']:
        raise ValueError('Stored source bytes do not match the Store SHA256.')
    if source['kind'] not in KINDS:
        raise ValueError('Select a saved structure table.')
    if source['kind'] == 'molecule_csv':
        from .science import molecule_rows
        _, rows = molecule_rows(raw, source['meta'])
    else:
        rows = json.loads(raw).get('rows')
    if not isinstance(rows, list):
        raise ValueError('Saved source has no structure rows.')
    for key in ('ph_min', 'ph_max', 'precision'):
        if type(args[key]) not in (int, float) or not math.isfinite(args[key]):
            raise ValueError('Finite named author parameters are required.')
    if not 0 <= args['ph_min'] <= args['ph_max'] <= 14 or not 0 < args['precision'] <= 10:
        raise ValueError('Require 0 <= pH min <= pH max <= 14 and 0 < precision <= 10.')
    if type(args['max_variants']) is not int or not 1 <= args['max_variants'] <= 128:
        raise ValueError('Variant budget must be an integer from 1 to 128.')
    selected = args['structures']
    if not isinstance(selected, list) or not 1 <= len(selected) <= 50:
        raise ValueError('Select 1 to 50 exact structure rows.')
    seen = set()
    bound = []
    for choice in selected:
        if not isinstance(choice, dict) or set(choice) != {'source_pointer', 'smiles'}:
            raise ValueError('Each selection requires source_pointer and exact smiles.')
        pointer, smiles = choice['source_pointer'], choice['smiles']
        match = re.fullmatch(r'/rows/(0|[1-9][0-9]*)/smiles', pointer) if isinstance(pointer, str) else None
        if not match or pointer in seen:
            raise ValueError('Use a unique exact /rows/N/smiles pointer.')
        index = int(match[1]); seen.add(pointer)
        if index >= len(rows) or not isinstance(rows[index], dict):
            raise ValueError('Source row does not exist.')
        row = rows[index]
        if not isinstance(smiles, str) or not 0 < len(smiles) <= 4096 or smiles != row.get('smiles'):
            raise ValueError('SMILES must exactly match the selected saved source row.')
        if row.get('width_matches') is False:
            raise ValueError('Malformed source CSV row.')
        bound.append({**choice, 'candidate_id': row.get('id', row.get('cid', row.get('candidate_id'))),
                      'source_row_index': index})
    return {'source_artifact_id': source['id'], 'source_artifact_sha256': actual,
            'source_kind': source['kind'], 'structures': bound,
            **{key: args[key] for key in ('ph_min', 'ph_max', 'precision', 'max_variants')}}


def configuration():
    path = Path(__file__).parents[1] / 'configs/protonation-runtime.json'
    cfg = json.loads(path.read_text())
    # Runtime locations are deployment-owned, never supplied by the model or HTTP arguments.
    for name, expected in cfg['assets'].items():
        if file_digest(name) != expected:
            raise ValueError('Protonation runtime asset fingerprint mismatch: ' + Path(name).name)
    return cfg


def cache_key(root, source, args):
    bundle = prepare(source, args)
    cfg = configuration()
    code = {name: digest((Path(root) / 'evida' / name).read_bytes()) for name in
            ('protonation.py', 'protonation_worker.py', 'science.py', 'runner.py')}
    return digest(json.dumps({'input': bundle, 'runtime': cfg, 'code': code}, sort_keys=True).encode())


def run(request, work):
    """Use only fixed runtime manifest. Fixed work/protonation.cancel is the operator cancel seam."""
    cfg = configuration()
    work = Path(work); work.mkdir(exist_ok=False)
    request_path, output = work / 'request.json', work / 'result.json'
    request_path.write_text(json.dumps({'input': request, 'expected_versions': cfg['packages']}))
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'CUDA_VISIBLE_DEVICES': '',
           'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'OMP_NUM_THREADS': '1',
           'OPENBLAS_NUM_THREADS': '1', 'XDG_CACHE_HOME': str(work / 'cache')}
    started = time.monotonic()
    receipt = {'manifest_sha256': digest((Path(__file__).parents[1] / 'configs/protonation-runtime.json').read_bytes()),
               'timeout_seconds': cfg['timeout_seconds'], 'output_limit_bytes': cfg['output_limit_bytes'],
               'log_limit_bytes': cfg['log_limit_bytes'], 'cancel_file': 'protonation.cancel'}
    (work / 'runtime-receipt.json').write_text(json.dumps(receipt))
    process = subprocess.Popen([cfg['python'], '-B', str(Path(__file__).with_name('protonation_worker.py')),
                                str(request_path), str(output)], cwd=work, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
    reason = None; count = 0
    selector = selectors.DefaultSelector(); selector.register(process.stdout, selectors.EVENT_READ)
    try:
        with (work / 'worker.log').open('xb') as log:
            while process.poll() is None or selector.get_map():
                if (work / 'protonation.cancel').exists(): reason = 'cancelled'
                elif time.monotonic() - started > cfg['timeout_seconds']: reason = 'timeout'
                elif any(p.exists() and p.stat().st_size > cfg['output_limit_bytes'] for p in (output, work / 'progress.json')): reason = 'output_limit'
                if reason:
                    kill_group(process)
                    break
                for key, _ in selector.select(0.05):
                    block = os.read(key.fileobj.fileno(), 8192)
                    if not block: selector.unregister(key.fileobj); continue
                    log.write(block[:max(0, cfg['log_limit_bytes'] - count)]); count += len(block)
                    if count > cfg['log_limit_bytes']: reason = 'log_limit'
    finally:
        # Close the pipe without waiting for descendants to close inherited copies.
        selector.close(); process.stdout.close()
        kill_group(process)
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            raise RuntimeError('Author process did not exit within bounded cleanup.')
    if any(p.exists() and p.stat().st_size > cfg['output_limit_bytes'] for p in (output, work / 'progress.json')):
        reason = 'output_limit'
    if reason or process.returncode or not output.exists():
        # Completed rows are committed incrementally, including interrupted runs.
        progress = work / 'progress.json'
        body = json.loads(progress.read_text()) if progress.exists() and progress.stat().st_size <= cfg['output_limit_bytes'] else {'rows': []}
        if progress.exists():
            body['retained_progress'] = {'file': 'progress.json', 'sha256': file_digest(progress),
                                         'bytes': progress.stat().st_size}
        completed = {row['source_pointer'] for row in body.get('rows', [])}
        body['rows'].extend({**row, 'exact_parent_smiles': row['smiles'], 'states': [],
                             'status': 'not_completed', 'reason': reason or 'author_worker_failure'}
                            for row in request['structures'] if row['source_pointer'] not in completed)
        body['parameters'] = {k: request[k] for k in ('ph_min', 'ph_max', 'precision', 'max_variants')}
        body.update(status='failed', error=reason or 'author_worker_failure', limits=LIMITS,
                    semantic_type='author_protonation_enumeration_not_efficacy_prediction')
    else:
        body = json.loads(output.read_text())
    body['runtime_receipt'] = receipt
    body['runtime_fingerprint'] = {'packages': cfg['packages'], 'python_version': cfg['python_version'],
                                   'assets_sha256': digest(json.dumps(cfg['assets'], sort_keys=True).encode()),
                                   'asset_count': len(cfg['assets'])}
    body['source_artifact_id'] = request['source_artifact_id']
    body['source_artifact_sha256'] = request['source_artifact_sha256']
    body['elapsed_seconds'] = round(time.monotonic() - started, 6)
    body['model_calls'] = 0; body['gpu_used'] = False
    return body


def state_csv(result):
    buffer = io.StringIO(); writer = csv.writer(buffer); writer.writerow(['cid', 'smiles'])
    bindings = []; exclusions = []
    for row in result.get('rows', []):
        for index, state in enumerate(row.get('states', [])):
            reasons = []
            if state.get('rdkit_parse_valid') is not True:
                reasons.append('rdkit_parse_not_verified')
            if state.get('heavy_atom_element_counts_preserved') is not True:
                reasons.append('heavy_atom_element_counts_not_verified')
            if reasons:
                exclusions.append({'source_pointer': row['source_pointer'], 'state_index': index,
                                   'exact_author_smiles': state.get('exact_author_smiles'), 'reasons': reasons})
                continue
            if not reasons:
                cid = f"parent_{row['source_row_index']}_state_{index}"
                writer.writerow([cid, state['exact_author_smiles']])
                bindings.append({'id': cid, 'source_pointer': row['source_pointer'],
                                 'state_index': index, 'parent_candidate_id': row.get('candidate_id')})
    return buffer.getvalue(), bindings, exclusions
