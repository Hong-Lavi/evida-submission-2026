"""Print non-secret identity of the isolated science environment."""
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path

package = Path(importlib.metadata.distribution("admet-ai").locate_file("admet_ai"))
result = {"python": sys.version.split()[0],
          "packages": {name: importlib.metadata.version(name) for name in ("rdkit", "admet-ai", "chemprop", "torch", "jsonschema", "vina", "meeko", "gemmi", "ViennaRNA", "posebusters", "crem")},
          "weights": [{"relative_path": str(p.relative_to(package)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                      for p in sorted(package.rglob("*.pt"))]}
print(json.dumps(result, sort_keys=True))
