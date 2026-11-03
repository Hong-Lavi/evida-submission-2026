# CheMeleon molecular representations: paired activity experiments

Frozen CheMeleon embeddings with EVIDA's native RF had **higher task-average MAE** than native Morgan fingerprints with the same RF: **0.58803 versus 0.55532**, across all **30 MoleculeACE tasks and 9,802 test rows**. The paired difference was +0.03271 p-activity units, with a 95% target-cluster bootstrap interval of [+0.02058, +0.04385]. This frozen-feature method did not earn adoption.

A separate experiment compares task fine-tuning of official CheMeleon weights against a matched randomly initialized neural model, recorded native RF and recorded Tanimoto GP. Its **30 tasks × two neural arms = 60 planned arms** are fixed. Its results are not included in this preparation; [finetune-status.json](finetune-status.json) records the boundary. A terminal package must retain every completion, failure and skipped arm before reporting outcomes.

## Completed frozen-feature comparison

Both RF arms use 300 trees, minimum leaf size 2, seed 20260930 and the same native inner scaffold training rows/labels. CheMeleon produces frozen 2,048-dimensional author fingerprints; native RF uses Morgan radius 2, 2,048 binary bits with chirality. The original RF matrix, labels and predictions were reproduced before the representation fit. The weights were not trained on these target labels in this experiment.

| Task-average metric | Native RF | Tanimoto GP reference | Frozen CheMeleon + RF |
|---|---:|---:|---:|
| MAE ↓ | 0.55532 | 0.53220 | 0.58803 |
| RMSE ↓ | 0.74612 | 0.71219 | 0.76833 |
| Spearman ↑ | 0.75824 | 0.78270 | 0.75282 |
| Measured top-10 recall ↑ | 0.42667 | 0.40333 | 0.41333 |
| Best measured p-activity in selected 10 ↑ | 10.02079 | 10.01053 | 10.00048 |

All 30 frozen-feature fits completed and met their inner usability gates. MAE was worse than native RF on 26 tasks and better on four. Validation-only selection among RF, GP and frozen CheMeleon chose GP on 24 tasks, RF on four and CheMeleon on two. Complete policy comparisons, all task rows and uncertainty intervals are retained in [the original scored results](chemeleon-trial/run-01/scored-results.json) and [recalculated tables](verification/recalculation-01/per-task.csv). Selection metrics and compute costs remain visible even when prediction error differs.

This is a developmental follow-up using the same benchmark on which RF/GP results were already known. Fine-tuning was planned with knowledge of the frozen-feature result. Neither experiment is fresh independent external validation. The 30 target/endpoint tasks form 29 target clusters; CHEMBL237 Ki and EC50 stay together in paired bootstrap draws. The pooled reported-activity labels do not establish assay-context transfer, biological mechanism, clinical benefit or a prospective discovery gain.

## Inspect or reproduce

```bash
python -B verify_package.py
python -B recompute.py --out recalculation-local
```

Verification uses the Python standard library; score recalculation also needs NumPy. These commands make no provider, network, fitting or GPU calls. They verify original prediction identities and all task receipts, execute the unchanged frozen-feature scorer body with explicit archival path bindings, and compare all stored fields except the new calculation time to tolerance `1e-12`.

[REPRODUCING.md](REPRODUCING.md) gives separate full-fit commands. The package contains bounded copies of prepared public data, reference predictions, raw frozen-feature predictions/logs, original and amended protocols, and exact fitting/scoring code. It excludes pretrained weights, embedding arrays and generated neural checkpoints; [weights.json](weights.json) provides the official download and SHA-256. Checkpoint hashes remain in fitting receipts when terminal neural results are included.

[Source attribution](ATTRIBUTION.md), [source-map.json](source-map.json) and [the function-parity receipt](provenance/portable-source-check.json) distinguish unchanged author code, EVIDA adapters, historical sanitized records and portable preparation code. Public protocols retain original hashes through the source map; removed workstation paths and GPU identifiers mean their public byte hashes differ where explicitly marked. Scientific values and prediction bytes are not rewritten.
