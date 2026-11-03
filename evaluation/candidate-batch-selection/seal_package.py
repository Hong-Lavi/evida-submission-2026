"""Seal public files; archives, virtualenvs and temporary copies stay outside the seal."""
from pathlib import Path
import hashlib,json
p=Path(__file__).resolve().parent
files={str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest()for f in sorted(p.rglob('*'))if f.is_file()and f.name!='package-seal.json'and not any(x in f.parts for x in ['.venv','__pycache__','_distribution','_relocation-check'])}
(p/'package-seal.json').write_text(json.dumps({'format':'evida.public-package.sha256.v1','files':files},indent=2)+'\n');print(json.dumps({'sealed_files':len(files)}))
