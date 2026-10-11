"""Freeze current package file hashes after review; no scientific scoring."""
from pathlib import Path
import hashlib
import json

HERE=Path(__file__).resolve().parent
if __name__=='__main__':
    files={str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest()
           for p in sorted(HERE.rglob('*')) if p.is_file() and p.name!='package-manifest.json'
           and '__pycache__' not in p.parts}
    (HERE/'package-manifest.json').write_text(json.dumps({'kind':'public package file integrity, not scientific validation','files':files},indent=2)+'\n')
    print(json.dumps({'files':len(files),'status':'SEALED'}))
