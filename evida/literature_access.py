"""Public web discovery and credential-free Chrome reading for the normal Runner."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from urllib.parse import parse_qsl, urlsplit


def validate_public_url(url):
    if not isinstance(url, str) or len(url) > 3000 or '\\' in url or any(ord(c) < 33 for c in url):
        raise ValueError('Use a public HTTPS research URL.')
    p = urlsplit(url)
    if (p.scheme != 'https' or not p.hostname or '.' not in p.hostname or
            p.username is not None or p.password is not None or p.port not in (None, 443)):
        raise ValueError('Use a public HTTPS research URL without credentials.')
    if re.search(r'/(?:authorize|oauth|login|signin)(?:/|$)', p.path, re.I):
        raise ValueError('Login pages require a separately authorised access route.')
    if any(re.search(r'(?:token|password|secret|signature|api.?key|credential|^sig$|^auth$|authorization|^key$)', key, re.I)
           for key, _ in parse_qsl(p.query) + parse_qsl(p.fragment)):
        raise ValueError('Do not put credentials or signed access links into research tool arguments.')
    return p


def validate(tool, args):
    if tool == 'public_web_search':
        q = args.get('query')
        if not isinstance(q, str) or not 1 <= len(q.strip()) <= 500:
            raise ValueError('Use a concise public scientific search question.')
        if args.get('engine') not in ('bing', 'duckduckgo'):
            raise ValueError('Choose the stated public search engine.')
    elif tool == 'public_research_page':
        validate_public_url(args.get('url'))
        if args.get('render_mode') not in ('http', 'chrome'):
            raise ValueError('Choose HTTP document extraction or Chrome rendering.')
    else:
        raise ValueError('Unknown literature access tool.')


def run(tool, args, work):
    validate(tool, args)
    cfg = json.loads((Path(__file__).parents[1]/'configs/literature-access-runtime.json').read_text())
    work = Path(work); work.mkdir(exist_ok=False)
    incoming, output = work/'request.json', work/'result.json'
    incoming.write_text(json.dumps({'tool': tool, 'arguments': args, 'chrome': cfg['chrome']}))
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'PYTHONNOUSERSITE': '1',
           'PYTHONDONTWRITEBYTECODE': '1', 'TMPDIR': str(work), 'CUDA_VISIBLE_DEVICES': '',
           'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'}
    # No login environment, user browser profile or API credentials enter the browser.
    # Chrome uses Unix socket filenames under TMPDIR; deep artifact paths exceed their limit.
    with tempfile.TemporaryDirectory(prefix='evida-web-', dir='/tmp') as browser_tmp, (work/'worker.log').open('xb') as log:
        env['TMPDIR'] = browser_tmp
        p = subprocess.Popen([cfg['python'], '-B', str(Path(__file__).with_name('literature_access_worker.py')),
            str(incoming), str(output)], env=env, cwd=work, stdout=log, stderr=log, start_new_session=True)
        error = None
        try:
            deadline = time.monotonic()+cfg['timeout_seconds']
            while p.poll() is None:
                if time.monotonic() >= deadline:
                    error = 'retrieval_timeout'; break
                if log.tell() > 1000000 or any(q.exists() and q.stat().st_size > 80*1024*1024
                        for q in (output, work/'progress.json')):
                    error = 'retrieval_output_limit'; break
                time.sleep(.2)
        finally:
            from .protonation import kill_group
            kill_group(p); p.wait(timeout=3)
    if error or p.returncode or not output.exists():
        progress = work/'progress.json'
        result = json.loads(progress.read_text()) if progress.exists() else {'rows': []}
        result.update(status='failed', error=error or 'retrieval_worker_failure')
        return result
    if output.stat().st_size > 80*1024*1024:
        return {'status':'failed','rows':[],'error':'retrieval_output_limit'}
    return json.loads(output.read_text())
