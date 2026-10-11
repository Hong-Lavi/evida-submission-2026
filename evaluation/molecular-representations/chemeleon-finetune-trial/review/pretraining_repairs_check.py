"""CPU-only checks of review-discovered execution failures; no assay model is trained."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import hashlib
import json
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import run_comparison
from metrics_common import spearman

checks = {'spearman_identical': spearman([1, 2, 3], [1, 2, 3]) == 1.0,
          'spearman_reversed': spearman([1, 2, 3], [3, 2, 1]) == -1.0}
protocol = json.loads((ROOT / 'protocol.json').read_text())
protocol['stop_starting_new_arms_at_utc'] = '2099-01-01T00:00:00+00:00'
raw_protocol = json.dumps(protocol)
original_read = Path.read_text

def read_text(path, *args, **kwargs):
    if path == ROOT / 'protocol.json':
        return raw_protocol
    return original_read(path, *args, **kwargs)

with TemporaryDirectory(prefix='evida-resource-stop-') as temporary:
    out = Path(temporary) / 'run'
    with patch.object(run_comparison, 'verify'), patch.object(Path, 'read_text', read_text), \
         patch.dict(run_comparison.os.environ, {'CUDA_VISIBLE_DEVICES': protocol['gpu_uuid']}), \
         patch.object(run_comparison.subprocess, 'run', return_value=subprocess.CompletedProcess(
             args=['simulated resource check'], returncode=0, stdout='1024, 50\n', stderr='')) as process:
        run_comparison.main(out)
    completion = json.loads((out / 'completion.json').read_text())
    checks['all_60_planned_retained_when_gpu_busy'] = len(completion['attempts']) == 60
    checks['all_resource_skipped'] = all(entry['status'] == 'not_started_resource_busy'
                                         for entry in completion['attempts'])
    checks['no_training_process'] = process.call_count == 1
    checks['individual_receipts'] = len(list(out.glob('*/*-receipt.json'))) == 60
checks['four_loaders_keep_tail'] = (ROOT / 'finetune_adapter.py').read_text().count('drop_last=False') == 4
result = {'status': 'PASS' if all(checks.values()) else 'FAIL', 'checks': checks,
          'GPU_used': False, 'model_calls': 0, 'benchmark_training_started': False,
          'source_sha256': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                            for name in ('metrics_common.py', 'run_comparison.py', 'finetune_adapter.py')}}
(HERE / 'pretraining-repairs-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
assert all(checks.values())
