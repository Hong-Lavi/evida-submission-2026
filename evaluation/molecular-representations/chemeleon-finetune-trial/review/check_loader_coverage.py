"""CPU-only reproduction of the installed Chemprop loader's singleton-tail rule."""
import hashlib
import inspect
import json
from pathlib import Path

from chemprop.data import MoleculeDatapoint, MoleculeDataset, build_dataloader

HERE = Path(__file__).resolve().parent
points = [MoleculeDatapoint.from_smi('CC') for _ in range(193)]
dataset = MoleculeDataset(points)
observations = []
for condition, extra in [('native_default', {}), ('explicit_drop_last_false', {'drop_last': False})]:
    loader = build_dataloader(dataset, batch_size=64, num_workers=0, shuffle=False, **extra)
    batch_counts = [len(batch[0]) for batch in loader]
    observations.append({'condition': condition, 'dataset_rows': len(dataset),
                         'drop_last': loader.drop_last, 'batches': batch_counts,
                         'predicted_row_capacity': sum(batch_counts)})
source = Path(inspect.getsourcefile(build_dataloader))
result = {'scope': '193 identical synthetic ethane structures; loader iteration only, no neural model or GPU.',
          'source': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
          'observations': observations, 'training_runs': 0, 'gpu_used': False, 'network_calls': 0}
(HERE / 'loader-coverage-reproduction.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
