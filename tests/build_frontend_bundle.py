"""Build deterministic static assets in the exact readable index order, without minification."""
from pathlib import Path
from html.parser import HTMLParser
import hashlib
import json
import re

WEB = Path(__file__).resolve().parents[1] / 'web'
SOURCE = WEB / 'index.source.html'
if not SOURCE.exists():
    SOURCE.write_bytes((WEB / 'index.html').read_bytes())

class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.styles = []
        self.scripts = []
    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == 'link' and attrs.get('rel') == 'stylesheet':
            self.styles.append(attrs['href'])
        if tag == 'script' and attrs.get('src'):
            self.scripts.append(attrs['src'])

original = SOURCE.read_text()
assets = Assets()
assets.feed(original)
receipt = {'kind': 'deterministic_frontend_bundle', 'source_index': 'index.source.html',
           'ordering': 'Document order of stylesheet links and scripts; deployment first, app last.',
           'minified': False, 'scientific_source_rewritten': False, 'bundles': {}}
for kind, inputs, output in [('css', assets.styles, 'workspace.bundle.css'),
                             ('js', assets.scripts, 'workspace.bundle.js')]:
    chunks, rows = [], []
    for name in inputs:
        if name.startswith('/') or '..' in Path(name).parts:
            raise ValueError(f'Expected local relative input: {name}')
        data = (WEB / name).read_bytes()
        rows.append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
        # Boundaries avoid ASI joining adjacent scripts; contents themselves stay byte-preserved.
        boundary = '\n;\n' if kind == 'js' else '\n'
        chunks.append((boundary + f'/* Source: {name} */\n').encode() + data + b'\n')
    data = b''.join(chunks)
    (WEB / output).write_bytes(data)
    receipt['bundles'][kind] = {'output': output, 'bytes': len(data),
                              'sha256': hashlib.sha256(data).hexdigest(), 'inputs': rows}

html = re.sub(r'\s*<link\b[^>]*rel="stylesheet"[^>]*>', '', original)
html = re.sub(r'\s*<script\b[^>]*src="[^\"]+"[^>]*>\s*</script>', '', html)
html = html.replace('</head>', '  <link rel="stylesheet" href="workspace.bundle.css">\n'
                    '  <script src="workspace.bundle.js" defer></script>\n</head>')
(WEB / 'index.html').write_text(html)
(WEB / 'frontend-bundle-manifest.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps({k: {'inputs': len(v['inputs']), 'bytes': v['bytes'], 'sha256': v['sha256']}
                  for k, v in receipt['bundles'].items()}))
