"""Attach 2D depictions to stored candidate rows, cached on disk.

RDKit lives in the pinned science runtime, so drawing runs there as a short subprocess. Results
are cached by the exact SMILES string: the same string always draws the same picture, and a
changed string is a different cache entry rather than a silently reused one.

A depiction is a drawing of the stored structure string. It is not a measurement, not a conformer,
and not verification that a physical sample matches. Rows whose SMILES RDKit cannot read keep
their original string and are marked unparsed.
"""
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

SMILES_FIELDS = ('smiles', 'canonical_smiles', 'SMILES')
# analogue_proposal belongs here for the same reason the retrieval tools do: stage 3 puts the
# generated structures beside the retrieved ones, and a reader compares them by looking.
DEPICTED_KINDS = ('compound_candidates', 'literature_compounds', 'compound_selection',
                  'molecule_csv', 'rdkit', 'admet', 'analogue_proposal')
MAXIMUM_PER_VIEW = 60


def row_smiles(row):
    """The structure string this row stores, without inventing one."""
    if not isinstance(row, dict):
        return None
    for field in SMILES_FIELDS:
        value = row.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    structure = row.get('structure')
    if isinstance(structure, dict):
        for field in SMILES_FIELDS:
            value = structure.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _key(smiles):
    return hashlib.sha256(smiles.encode()).hexdigest()[:40]


def depict(smiles_list, cache_dir, science_python, root, width=280, height=200):
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    wanted = list(dict.fromkeys(s for s in smiles_list if isinstance(s, str) and s.strip()))
    found, missing = {}, []
    for smiles in wanted:
        path = cache / f'{_key(smiles)}.json'
        try:
            found[smiles] = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            missing.append(smiles)
    if missing:
        with tempfile.TemporaryDirectory() as work:
            out = Path(work) / 'result.json'
            request = Path(work) / 'request.json'
            request.write_text(json.dumps({'smiles': missing, 'out': str(out),
                                           'width': width, 'height': height}), encoding='utf-8')
            env = {'PATH': str(Path(science_python).parent) + ':/usr/bin:/bin', 'LANG': 'C.UTF-8',
                   'PYTHONPATH': str(root), 'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1',
                   'MPLCONFIGDIR': work, 'XDG_CACHE_HOME': work}
            done = subprocess.run([str(science_python), '-m', 'evida.depict', str(request)],
                                  cwd=str(root), env=env, capture_output=True, timeout=180)
            if done.returncode == 0 and out.exists():
                for smiles, value in json.loads(out.read_text(encoding='utf-8'))['results'].items():
                    (cache / f'{_key(smiles)}.json').write_text(
                        json.dumps(value, ensure_ascii=False), encoding='utf-8')
                    found[smiles] = value
            else:
                # A drawing failure must not take the rows with it.
                for smiles in missing:
                    found[smiles] = {'status': 'failed',
                                     'reason': f'depiction process exit {done.returncode}'}
    return found


def attach(value, kind, cache_dir, science_python, root):
    """Add `depiction` to each row of a molecule-bearing view. Rows are otherwise untouched."""
    if kind not in DEPICTED_KINDS or not isinstance(value.get('rows'), list):
        return value
    rows = value['rows'][:MAXIMUM_PER_VIEW]
    smiles = [row_smiles(row) for row in rows]
    if not any(smiles):
        return value
    try:
        drawn = depict([s for s in smiles if s], cache_dir, science_python, root)
    except Exception as error:
        value['depiction_status'] = f'unavailable: {type(error).__name__}'
        return value
    for row, one in zip(rows, smiles):
        if one and isinstance(row, dict):
            row['depiction'] = {**drawn.get(one, {'status': 'failed'}), 'smiles': one}
    value['depiction_status'] = 'attached'
    value['depiction_meaning'] = ('2D drawing of the stored SMILES for reading convenience. '
                                  'Not a measurement, a conformer, or sample identity verification.')
    if len(value['rows']) > MAXIMUM_PER_VIEW:
        value['depiction_limit'] = MAXIMUM_PER_VIEW
    return value
