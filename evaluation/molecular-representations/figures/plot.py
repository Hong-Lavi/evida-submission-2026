"""Recreate the complete activity-model comparison from retained task metrics."""
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / 'input.json').read_text())
rows = data['tasks']
arms = ['gp', 'chemeleon_rf', 'chemeleon_finetuned', 'matched_random']
labels = ['Tanimoto GP', 'Frozen CheMeleon + RF', 'CheMeleon, fine-tuned', 'Matched random initialization']
metrics = ['mae', 'top10_recall']
results = {}
for arm in arms:
    results[arm] = {}
    for metric in metrics:
        groups = defaultdict(list)
        for row in rows:
            groups[row['target']].append(row['metrics'][arm][metric] - row['metrics']['rf'][metric])
        names = sorted(groups)
        totals = np.asarray([sum(groups[name]) for name in names])
        counts = np.asarray([len(groups[name]) for name in names])
        rng = np.random.default_rng(data['bootstrap_seed'])
        draw = rng.integers(len(names), size=(data['bootstrap_repetitions'], len(names)))
        bootstrap = totals[draw].sum(axis=1) / counts[draw].sum(axis=1)
        entry = {'mean_difference': float(totals.sum() / counts.sum()),
                 'ci95': np.quantile(bootstrap, [.025, .975]).tolist(),
                 'task_macro': float(np.mean([row['metrics'][arm][metric] for row in rows]))}
        old = data['original_comparisons'].get(arm, {}).get(metric)
        if old:
            assert np.allclose([entry['mean_difference'], *entry['ci95']],
                               [old['mean_difference'], *old['ci95']], atol=1e-12, rtol=0), (arm, metric)
        results[arm][metric] = entry

plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
                     'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.spines.left': False, 'axes.edgecolor': '#a6afba',
                     'text.color': '#182b3a', 'axes.labelcolor': '#263a49',
                     'svg.fonttype': 'none', 'savefig.facecolor': 'white'})
fig, axes = plt.subplots(1, 2, figsize=(12.4, 5.5), sharey=True)
ys = np.arange(len(arms))[::-1]
for ax, metric, scale, color in zip(axes, metrics, [1, 100], ['#176889', '#7b508c']):
    baseline = float(np.mean([row['metrics']['rf'][metric] for row in rows]))
    ax.axvline(0, color='#8d98a4', linewidth=1.2, linestyle=(0, (4, 3)), zorder=1)
    for y, arm in zip(ys, arms):
        value = results[arm][metric]
        point = value['mean_difference'] * scale
        low, high = np.array(value['ci95']) * scale
        ax.errorbar(point, y, xerr=[[point - low], [high - point]], fmt='o',
                    color=color, markersize=7, linewidth=2, capsize=4, zorder=3)
        ax.annotate(f'{point:+.4f}' if metric == 'mae' else f'{point:+.2f} pp',
                    (point, y), xytext=(0, 11), textcoords='offset points',
                    ha='center', fontsize=10, color=color)
    ax.set_yticks(ys, labels)
    ax.tick_params(axis='y', length=0, pad=12)
    ax.set_ylim(-.5, len(arms) - .25)
    ax.grid(axis='x', color='#eef0f3', zorder=0)
    if metric == 'mae':
        ax.set_title(f'Activity prediction error\nNative RF MAE: {baseline:.4f}', loc='left', fontsize=12, pad=18)
        ax.set_xlabel('MAE difference (p-activity units)\nLower is better', labelpad=13)
        ax.set_xlim(-.075, .195)
    else:
        ax.set_title(f'Recovery of the measured top 10\nNative RF recall: {100 * baseline:.2f}%', loc='left', fontsize=12, pad=18)
        ax.set_xlabel('Top-10 recall difference (percentage points)\nHigher is better', labelpad=13)
        ax.set_xlim(-28, 10)
fig.suptitle('Prediction accuracy and candidate recovery are different goals', x=.025, ha='left',
             fontsize=17, fontweight='bold', y=.98)
fig.text(.025, .902, '30 MoleculeACE target–endpoint tasks · 29 target clusters · 9,802 held-out compound records',
         fontsize=11, color='#526371')
fig.text(.025, .064, 'Points: paired task-average differences. Bars: 95% target-cluster bootstrap intervals (5,000 draws).',
         fontsize=9.5, color='#526371')
fig.text(.025, .024, 'Development experiments tried sequentially on the same benchmark; one fit per task. All five model variants are retained.',
         fontsize=9.5, color='#526371')
fig.subplots_adjust(left=.265, right=.975, bottom=.245, top=.74, wspace=.24)
for extension in ['png', 'svg', 'pdf']:
    fig.savefig(HERE / ('activity-model-comparison.' + extension), dpi=170)
plt.close(fig)
with (HERE / 'task-macro.csv').open('w') as handle:
    writer = csv.writer(handle)
    writer.writerow(['arm', *metrics])
    for arm in ['rf', *arms]:
        writer.writerow([arm, *(float(np.mean([row['metrics'][arm][m] for row in rows])) for m in metrics)])
(HERE / 'recomputed.json').write_text(json.dumps(results, indent=2, allow_nan=False) + '\n')
receipt = {'input_sha256': hashlib.sha256((HERE / 'input.json').read_bytes()).hexdigest(),
           'original_comparisons_match_atol': 1e-12, 'tasks': len(rows),
           'target_clusters': len({row['target'] for row in rows}),
           'test_rows': sum(row['n'] for row in rows), 'model_calls': 0, 'GPU': False,
           'numpy': np.__version__, 'matplotlib': matplotlib.__version__,
           'outputs': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in HERE.glob('activity-model-comparison.*')}}
(HERE / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
