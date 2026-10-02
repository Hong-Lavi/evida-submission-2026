"""Run the quote-supports-clause check, cached, and never let it gate a judgement.

The anchor check proves a quote exists in the stored row. This asks the narrower follow-up: does
that sentence actually carry the clause it was attached to. A quote can be real and still be
about something else.

Design rules this follows:
- It is advisory. A verdict is recorded beside the model's unchanged record, like the anchor
  check, and no judgement is rejected because of it.
- It is optional. If the environment, the model or the GPU is not there, the check is simply
  absent and says so. Nothing else changes.
- It is cached by the exact (quote, clause) pair, so the same pair always gets the same verdict
  and a changed sentence is a new entry rather than a silently reused one.
"""
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

# The pinned science runtime is CPU-only; this check needs the project's GPU environment.
DEFAULT_PYTHON = Path('/data/user_home/hsm927/projects/EVIDA_finals_research_2026'
                      '/audit/component-envs/bge-gpu/bin/python')
TIMEOUT_SECONDS = 900


def pair_key(document, claim):
    digest = hashlib.sha256()
    digest.update(document.encode())
    digest.update(b'\x00')
    digest.update(claim.encode())
    return digest.hexdigest()[:40]


def check(pairs, cache_dir, root, python=None, device='cuda'):
    """pairs: [{'document': quote, 'claim': clause text}] -> {key: verdict}."""
    interpreter = Path(python or DEFAULT_PYTHON)
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    wanted, found, missing = {}, {}, []
    for pair in pairs:
        document, claim = (pair.get('document') or '').strip(), (pair.get('claim') or '').strip()
        if not document or not claim:
            continue
        key = pair_key(document, claim)
        wanted[key] = {'document': document, 'claim': claim}
        path = cache / f'{key}.json'
        try:
            found[key] = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            missing.append(key)
    if not wanted:
        return {}
    if missing:
        if not interpreter.is_file():
            for key in missing:
                found[key] = {'status': 'unavailable',
                              'reason': 'entailment environment not present'}
            return found
        with tempfile.TemporaryDirectory() as work:
            out = Path(work) / 'result.json'
            request = Path(work) / 'request.json'
            request.write_text(json.dumps({
                'out': str(out), 'device': device,
                'pairs': [{'id': key, **wanted[key]} for key in missing]}), encoding='utf-8')
            env = {'PATH': str(interpreter.parent) + ':/usr/bin:/bin', 'LANG': 'C.UTF-8',
                   'HF_HOME': str(Path(cache_dir).parent / '.entailment-cache'),
                   'HF_HUB_OFFLINE': os.environ.get('HF_HUB_OFFLINE', '0'),
                   'CUDA_VISIBLE_DEVICES': os.environ.get('EVIDA_ENTAIL_GPU', '2'),
                   'XDG_CACHE_HOME': work, 'TOKENIZERS_PARALLELISM': 'false'}
            done = subprocess.run([str(interpreter), '-m', 'evida.entail', str(request)],
                                  cwd=str(root), env={**env, 'PYTHONPATH': str(root)},
                                  capture_output=True, timeout=TIMEOUT_SECONDS)
            value = {}
            if done.returncode == 0 and out.exists():
                value = json.loads(out.read_text(encoding='utf-8'))
            if value.get('status') == 'succeeded':
                for row in value['results']:
                    record = {k: v for k, v in row.items() if k != 'id'}
                    (cache / f"{row['id']}.json").write_text(
                        json.dumps(record, ensure_ascii=False), encoding='utf-8')
                    found[row['id']] = record
            else:
                reason = value.get('reason') or f'process exit {done.returncode}'
                for key in missing:
                    found[key] = {'status': 'unavailable', 'reason': reason}
    return found


def verified_clause_indexes(check):
    """Which clauses of a basis had their quote found in the stored row.

    The anchor result is not written back into the basis: `verify_basis` records it separately,
    one entry per assessment, whose clauses carry `clause_index` and `status`. Reading it off the
    clause itself finds nothing and silently checks nothing, so the two are matched by index here.
    """
    return {c['clause_index'] for c in ((check or {}).get('clauses') or [])
            if isinstance(c, dict) and c.get('status') == 'verified'
            and isinstance(c.get('clause_index'), int)}


def annotate(entries, cache_dir, root, python=None):
    """Add `quote_supports_clause` to anchored clauses. Records, never rejects.

    entries: [{'basis': <the recorded basis>, 'check': <its verify_basis entry, or None>}]
    """
    pairs, index = [], []
    for entry in entries:
        basis = entry.get('basis') or {}
        verified = verified_clause_indexes(entry.get('check'))
        for position, clause in enumerate(basis.get('clauses') or []):
            anchor = (clause.get('anchor') or {})
            quote, text = anchor.get('quote'), clause.get('text')
            if position not in verified:
                continue  # an unverified quote is already reported; do not check it further
            if isinstance(quote, str) and isinstance(text, str) and quote.strip() and text.strip():
                pairs.append({'document': quote.strip(), 'claim': text.strip()})
                index.append((clause, pair_key(quote.strip(), text.strip())))
    if not pairs:
        return entries
    try:
        verdicts = check(pairs, cache_dir, root, python)
    except Exception as error:
        for clause, _ in index:
            clause['quote_supports_clause'] = {'status': 'unavailable',
                                               'reason': f'{type(error).__name__}'}
        return entries
    for clause, key in index:
        clause['quote_supports_clause'] = {
            **verdicts.get(key, {'status': 'unavailable', 'reason': 'no verdict returned'}),
            'meaning': 'Whether this sentence alone carries this clause. Advisory: the record is '
                       'unchanged and nothing is rejected on this basis.'}
    return entries
