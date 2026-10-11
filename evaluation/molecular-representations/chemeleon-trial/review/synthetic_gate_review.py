"""Source-only synthetic score-boundary review; never reads actual run files."""
import ast
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import tempfile
import sys

import numpy as np

HERE = Path(__file__).resolve().parents[1]
source = (HERE / 'score_comparison.py').read_text()
tree = ast.parse(source)
# Extract functions without importing trial modules or invoking their main.
namespace = {'np': np, 'defaultdict': defaultdict, 'Counter': Counter,
             'json': json, 'Path': Path, 'sys': sys}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)],
                        type_ignores=[]), '<reviewed-functions>', 'exec'), namespace)


def gate_order():
    # main imports only the Spearman helper before accessing synthetic inputs.
    import sys
    sys.path.insert(0, str(HERE.parent / 'tanimoto-trial/frozen-product'))
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        (root / 'run-01').mkdir()
        tasks = [{'task': 'SYNTH_A', 'gold_sha256': 'unused'},
                 {'task': 'SYNTH_B', 'gold_sha256': 'unused'}]
        receipts = [{'task': t['task'], 'status': 'failed', 'prediction_sha256': None} for t in tasks]
        (root / 'run-01/sealed-predictions.json').write_text(json.dumps({
            'protocol_sha256': 'synthetic-protocol', 'tasks': receipts}))
        for task in tasks:
            folder = root / 'previous' / task['task']; folder.mkdir(parents=True)
            (folder / 'predictions.json').write_text('{}')
        checks = []
        def synthetic_sha(path):
            text = str(path.relative_to(root)); checks.append(text)
            if text == 'protocol.json':
                return 'synthetic-protocol'
            if text == 'previous/SYNTH_A/predictions.json':
                return 'valid-a'
            if text == 'previous/SYNTH_B/predictions.json':
                return 'changed-b'
            if text.endswith('evaluation-only/test-gold.json'):
                raise RuntimeError('synthetic_gold_access_boundary_reached')
            raise AssertionError(text)
        protocol = {'order': [t['task'] for t in tasks], 'tasks': tasks,
                    'frozen_product': str(HERE.parent / 'tanimoto-trial/frozen-product'),
                    'gp_run': str(root / 'previous'), 'data': str(root / 'data'),
                    'gp_prediction_pins': {'SYNTH_A': 'valid-a', 'SYNTH_B': 'expected-b'}}
        namespace.update(HERE=root, load_protocol=lambda: protocol, sha=synthetic_sha)
        try:
            namespace['main']()
        except RuntimeError as error:
            assert str(error) == 'synthetic_gold_access_boundary_reached'
        else:
            raise AssertionError('Expected synthetic boundary')
        assert 'previous/SYNTH_B/predictions.json' not in checks
        return {'observed': 'first_gold_access_precedes_later_fallback_pin_check', 'calls': checks}


def metric_check():
    # Candidate-ID tie-breaking, paired macro and target-cluster count only.
    y = np.asarray([1., 2., 3., 4., 5., 6., 7., 8., 9., 10., 11.])
    ids = [f'id-{i:02d}' for i in range(11)]
    value = namespace['metrics'](y, np.zeros(11), ids, lambda _a, _b: 0.)
    assert value['top10_recall'] == .9
    assert value['best_true_activity_in_selected10'] == 10.
    rows = [{'task': name, 'left': {'mae': delta}, 'right': {'mae': 0.}}
            for name, delta in [('SYNTHA_Ki', 1.), ('SYNTHA_EC50', 2.), ('SYNTHB_Ki', 3.)]]
    value = namespace['interval'](rows, 'left', 'right', 'mae',
                                  {'bootstrap_seed': 20261011, 'bootstrap_repetitions': 100})
    assert value['mean_difference'] == 2. and value['tasks'] == 3 and value['target_clusters'] == 2
    return {'top10_tie_break': 'passed', 'task_macro_and_target_grouping': 'passed'}


result = {'kind': 'independent_source_and_synthetic_review', 'actual_prediction_values_read': False,
          'official_gold_read': False, 'final_scores_read': False, 'model_calls': 0,
          'network_calls': 0, 'gpu_used': False, 'gate': gate_order(), 'metrics': metric_check(),
          'reviewed_source_sha256': {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
              for name in ['protocol.json', 'run_comparison.py', 'score_comparison.py', 'encoder_adapter.py']}}
with (HERE / 'review/synthetic-review-result.json').open('x') as stream:
    json.dump(result, stream, indent=2); stream.write('\n')
print(json.dumps(result, indent=2))
