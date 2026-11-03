"""Unchanged metric/rank function bodies from the recorded RF/GP comparison."""
from collections import defaultdict
import math
import numpy as np

def metrics(y, predictions, ids, spearman):
    top_true = sorted(range(len(y)), key=lambda i: (-y[i], ids[i]))[:10]
    top_predicted = sorted(range(len(y)), key=lambda i: (-predictions[i], ids[i]))[:10]
    return {'n': len(y), 'mae': float(np.mean(np.abs(y - predictions))),
            'rmse': float(np.sqrt(np.mean((y - predictions) ** 2))),
            'spearman': spearman(y.tolist(), predictions.tolist()),
            'top10_recall': len(set(top_true) & set(top_predicted)) / len(top_true),
            'best_true_activity_in_selected10': float(max(y[i] for i in top_predicted))}

def cluster_interval(rows, left, right, metric, protocol):
    groups = defaultdict(list)
    for row in rows:
        groups[row['task'].split('_')[0]].append(row[left][metric] - row[right][metric])
    names = sorted(groups)
    if not names:
        return None
    rng = np.random.default_rng(protocol['bootstrap_seed'])
    boot = [np.mean([v for name in rng.choice(names, len(names), replace=True) for v in groups[name]])
            for _ in range(protocol['bootstrap_repetitions'])]
    differences = np.asarray([r[left][metric] - r[right][metric] for r in rows])
    return {'mean_difference': float(np.mean(differences)), 'ci95': np.quantile(boot, [0.025, 0.975]).tolist(),
            'tasks': len(rows), 'target_clusters': len(names),
            'negative': int(np.sum(differences < 0)), 'positive': int(np.sum(differences > 0)),
            'ties': int(np.sum(differences == 0)), 'difference_order': left + ' minus ' + right}

def spearman(left, right):
    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        index = 0
        while index < len(order):
            stop = index
            while stop + 1 < len(order) and values[order[stop + 1]] == values[order[index]]:
                stop += 1
            average = (index + stop) / 2 + 1
            for position in range(index, stop + 1):
                out[order[position]] = average
            index = stop + 1
        return out

    a, b = ranks(left), ranks(right)
    n = len(a)
    mean_a, mean_b = sum(a) / n, sum(b) / n
    top = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    bottom = math.sqrt(sum((x - mean_a) ** 2 for x in a) * sum((y - mean_b) ** 2 for y in b))
    return top / bottom if bottom else 0.0
