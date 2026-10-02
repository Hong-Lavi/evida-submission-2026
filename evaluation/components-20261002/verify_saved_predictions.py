"""Recalculate metrics from saved outputs and separately obtained official gold.

No network, model inference, training, or changes to supplied data.
Requires NumPy and SciPy. See README for the exact upstream downloads.
"""
from pathlib import Path
from collections import defaultdict
import argparse
import csv
import gzip
import hashlib
import json
import math
import numpy as np
from scipy.stats import spearmanr

B = Path(__file__).resolve().parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--nfcorpus-qrels', type=Path)
p.add_argument('--moleculeace-data', type=Path)
args = p.parse_args()
if args.nfcorpus_qrels is None and args.moleculeace_data is None:
    p.error('Supply at least one official data path; no files are downloaded automatically.')
sources = json.loads((B / 'prediction-sources.json').read_text())
protocol = json.loads((B / 'public-protocol-stage1.json').read_text())
report = {'new_model_or_network_calls': 0}

if args.nfcorpus_qrels is not None:
    gold_file = args.nfcorpus_qrels
    assert hashlib.sha256(gold_file.read_bytes()).hexdigest() == sources['nfcorpus_test_qrels_sha256']
    gold = defaultdict(dict)
    with gold_file.open() as f:
        for r in csv.DictReader(f, delimiter='\t'):
            gold[r['query-id']][r['corpus-id']] = int(r['score'])
    ranks = json.loads(gzip.decompress((B / 'nfcorpus-rankings-top100.json.gz').read_bytes()))
    with (B / 'nfcorpus-per-query-metrics.csv').open() as f:
        expected = {r['query_id']: r for r in csv.DictReader(f)}
    maximum_error = 0.0
    for method, queries in ranks.items():
        assert len(queries) == 323 and {r['query_id'] for r in queries} == set(expected) == set(gold)
        for r in queries:
            qid, order = r['query_id'], r['order']
            assert len(order) == len(set(order)) == 100
            rel = gold[qid]
            positive = {d for d, value in rel.items() if value > 0}
            ideal = sum(g / math.log2(i + 2) for i, g in enumerate(sorted(rel.values(), reverse=True)[:10]))
            scores = {
                'ndcg_at_10': sum(rel.get(d, 0) / math.log2(i + 2) for i, d in enumerate(order[:10])) / ideal if ideal else 0.0,
                'recall_at_10': len(positive.intersection(order[:10])) / len(positive),
                'recall_at_100': len(positive.intersection(order)) / len(positive),
                'mrr_at_10': next((1 / (i + 1) for i, d in enumerate(order[:10]) if rel.get(d, 0) > 0), 0.0),
            }
            for name, value in scores.items():
                error = abs(value - float(expected[qid][method + '_' + name]))
                maximum_error = max(error, maximum_error)
                assert error < 1e-12
    report['retrieval'] = {'queries': 323, 'metric_values_checked': 2584, 'maximum_error': maximum_error}

if args.moleculeace_data is not None:
    with gzip.open(B / 'moleculeace-test-predictions.csv.gz', 'rt') as f:
        predictions = defaultdict(list)
        for r in csv.DictReader(f):
            predictions[r['task']].append(r)
    with (B / 'moleculeace-per-task-metrics.csv').open() as f:
        expected = {r['task']: r for r in csv.DictReader(f)}
    assert set(predictions) == set(expected) == {t['task'] for t in protocol['moleculeace']['tasks']}
    count, checked_units, maximum_error = 0, 0, 0.0
    for task in protocol['moleculeace']['tasks']:
        name = task['task']
        file = args.moleculeace_data / (name + '.csv')
        assert hashlib.sha256(file.read_bytes()).hexdigest() == task['sha256']
        with file.open() as f:
            raw = list(csv.DictReader(f))
        assert len(raw) == task['rows']
        for r in raw:
            assert math.isclose(9 - math.log10(float(r['exp_mean [nM]'])), float(r['y [pEC50/pKi]']), abs_tol=1e-10)
            checked_units += 1
        rows = predictions[name]
        indices = [int(r['row_index']) for r in rows]
        assert len(indices) == len(set(indices)) == task['test']
        assert set(indices) == {i for i, r in enumerate(raw) if r['split'] == 'test'}
        pred = np.array([float(r['prediction']) for r in rows])
        mean = np.array([float(r['training_mean']) for r in rows])
        assert len(set(mean)) == 1
        assert all(round(float(r['prediction']), 2) == float(r['native_rounded_prediction']) for r in rows)
        y = np.array([float(raw[i]['y [pEC50/pKi]']) for i in indices])
        cliff = np.array([int(raw[i]['cliff_mol']) == 1 for i in indices])
        calculated = {
            'mae': float(abs(pred - y).mean()), 'rmse': float(np.sqrt(((pred - y) ** 2).mean())),
            'spearman': float(spearmanr(pred, y).statistic),
            'training_mean_mae': float(abs(mean - y).mean()),
            'training_mean_rmse': float(np.sqrt(((mean - y) ** 2).mean())),
            'cliff_n': int(cliff.sum()), 'cliff_rmse': float(np.sqrt(((pred[cliff] - y[cliff]) ** 2).mean())),
        }
        for key, value in calculated.items():
            error = abs(value - float(expected[name][key]))
            maximum_error = max(error, maximum_error)
            assert error < 1e-10
        count += len(rows)
    assert count == 9802 and checked_units == 48714
    report['activity_prediction'] = {'tasks': 30, 'test_predictions_checked': count,
                                     'unit_rows_checked': checked_units, 'maximum_error': maximum_error}

report['status'] = 'PASS'
print(json.dumps(report, indent=2))
