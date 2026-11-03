# Independent complete-result recalculation: PASS

Root authorized outcome access after its unchanged scorer completed successfully. Reviewed seal `56147cfba9a8e5008b8837092aaaaa5d0d9927d16ddf4e64eaae1adeed843897` and score `d183e17032cc820c0891521563b99bd80d8be7c64696edcb81d4a8f622a64cbf`.

`recalculate.py` uses its own arithmetic, SciPy Spearman, NumPy lexicographic rank selection and an independent vectorized cluster-resampling implementation. It does not import the original scoring/metric functions. All 60 neural predictions, all 30 frozen baseline predictions, inputs, gold identities and source hashes were checked; all five task metrics, macro metrics and 20 prespecified cluster intervals agree. Maximum task-metric difference is 2.22e-16; maximum CI difference is 8.33e-17. No fit, inference, network or GPU call was made. Original results remain unchanged.

| Method | Task-macro MAE | RMSE | Spearman | Top10 recall |
|---|---:|---:|---:|---:|
| Recorded RF | 0.55531913 | 0.74612451 | 0.75823887 | 0.42666667 |
| Recorded GP | 0.53220149 | 0.71219048 | 0.78270126 | 0.40333333 |
| Fine-tuned CheMeleon | 0.53095259 | 0.70762316 | 0.78118778 | 0.42000000 |
| Matched random initialization | 0.67794886 | 0.86807313 | 0.63802120 | 0.26333333 |
| Expanded validation policy | 0.53213188 | 0.70980300 | 0.78288371 | 0.41666667 |

All methods cover 30 tasks and 9,802 test rows; neural completion is 60/60. Independent unit for bootstrap is 29 target clusters, with both CHEMBL237 endpoints kept together. Negative MAE differences favor the first method:

- CheMeleon minus RF: −0.02436654, 95% cluster interval [−0.04215554, −0.00774839]; 21/30 task improvements.
- CheMeleon minus GP: −0.00124890, interval [−0.01497055, +0.01218322]; 17/30 improvements.
- CheMeleon minus matched random: −0.14699627, interval [−0.19816848, −0.10424124]; 29/30 improvements.

These support pretrained initialization within the fixed neural recipe and lower MAE than the recorded RF. They do not establish an improvement over the available GP, equivalence, seed robustness or fresh-target generalization. The reused benchmark and one training seed remain material limitations. Maintaining the current CPU-capable path and withholding automatic GPU-dependent adoption is consistent with these results.

## Explicitly post-score descriptive policy comparison

This comparison was requested **after the original results** and is separate from the frozen primary/secondary analysis. No protocol, primary contrast, selector, model or output was changed. Original policy selection is recomputed from the frozen RF/GP validation eligibility and unrounded MAE; neural validation metrics are independently recalculated from raw validation predictions. No test outcomes enter selection.

| Quantity | Original policy | Expanded policy |
|---|---:|---:|
| Selections | 25 GP, 5 RF | 24 CheMeleon, 4 GP, 2 random |
| Task-macro MAE | 0.5321720059 | 0.5321318839 |
| RMSE | 0.7134568984 | 0.7098030004 |
| Spearman | 0.7818485157 | 0.7828837146 |
| Top10 recall | 0.4166666667 | 0.4166666667 |
| Best true p-activity among selected ten | 10.0137652133 | 10.0569333744 |

Expanded minus original MAE is **−0.0000401220**, 95% target-cluster interval **[−0.0119075705, +0.0115123170]**, with 14 improved, 12 worse and 4 identical tasks. The corresponding RMSE interval is [−0.01877546, +0.01052091], Spearman [−0.00795519, +0.01053852], top10 recall [−0.04827586, +0.05000000], and best-selected activity [−0.00140508, +0.10367026]. Do not use this post-score comparison as a retrospectively substituted primary endpoint. It provides no clear policy-level gain for the extra neural training here.

## Recorded computation cost

| Neural arm, all 30 tasks | Worker elapsed-time sum | Trainer.fit elapsed-time sum | Recorded epochs |
|---|---:|---:|---:|
| Fine-tuned CheMeleon | 1,958.825 s (32.647 min) | 1,717.155 s (28.619 min) | 437 |
| Matched random | 2,719.176 s (45.320 min) | 2,476.673 s (41.278 min) | 567 |
| Total | **4,678.001 s (77.967 min)** | **4,193.828 s (69.897 min)** | 1,004 |

Workers ran serially on the assigned GPU. Their elapsed time includes CPU startup, pin checks, preprocessing, IO and prediction; Trainer.fit includes validation and checkpointing. **Do not add these two columns**, which overlap. Neither column measures GPU-kernel time, energy or process CPU time. Coordinator overhead, earlier preflights, preparation, scoring and review are outside these recorded timers, so this is not total project elapsed time.

Historical baseline fit timers sum to 326.967 s for native RF's fit function and 45.488 s for GP fitting across 30 tasks. They were reused, not rerun for this follow-up, and their timing boundaries differ from the neural worker totals; avoid a precise speedup claim from this comparison.

Full independently recalculated per-task values, all five metrics, intervals, policy counts and timing totals are in `independent-results.json`. The public-package review remains pending; use the explicit release/data-boundary checks in `REVIEW.md`.
