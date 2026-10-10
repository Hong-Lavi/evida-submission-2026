#!/usr/bin/env python3
"""Seal this distribution, excluding the seal itself and ephemeral caches."""
import hashlib,json
from pathlib import Path
p=Path(__file__).resolve().parent
files={str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(p.rglob('*')) if f.is_file() and f.name!='package-seal.json' and '__pycache__' not in f.parts and '.venv' not in f.parts}
(p/'package-seal.json').write_text(json.dumps({'format':'evida.public-package.sha256.v1','files':files},indent=2)+'\n')
print(json.dumps({'sealed_files':len(files)}))
