"""Verify every distributed file against the release manifest; no external access."""
from pathlib import Path
import hashlib,json

base=Path(__file__).resolve().parents[1]
manifest=json.loads((base/'package-manifest.json').read_text())
for row in manifest['files']:
    p=base/row['path']
    assert p.resolve().is_relative_to(base.resolve())
    assert p.stat().st_size==row['bytes'],row['path']
    assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],row['path']
print(json.dumps({'status':'PASS','verified_files':len(manifest['files']),'verified_bytes':sum(r['bytes'] for r in manifest['files'])}))
