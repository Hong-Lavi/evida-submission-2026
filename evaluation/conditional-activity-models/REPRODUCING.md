# Reproduction scope

There are two separate operations: recomputing reported metrics from the archived predictions, and fitting a fresh pair of estimators. Only the first was executed when this package was assembled.

## Recalculate the archived result

Run from this directory with Python and NumPy installed:

```bash
python -B verify_package.py
python -B recompute.py --output recalculation-local
```

The first command verifies all declared package bytes, source pins, dataset hashes, and every source CSV row against the prepared inputs. The second calls the unchanged frozen metric functions and native rank implementation, then checks the recalculated fields against the archived v1 result and v2 coverage supplement. It also checks the exported row CSV against the sealed predictions and official labels. This requires no molecular-model libraries, network, credentials, model providers or GPU. Output includes a full summary, 30-task table, paired confidence-interval table, and 9,802-row prediction table.

The row table preserves candidate identifiers. `cliff_mol` is retained for source traceability; a new cliff-subset comparison is not part of the GP run's declared metric family. The `policy_arm` is copied from the frozen inner selection, never reselected from external labels. All selection and error calculations use unrounded saved predictions.

## Fit a separate reproduction

Use a separate environment with Python 3.12 and the versions in `requirements-fit.txt`. The execution environment receipt records Python 3.12.14. Package installation is a separate network operation; it is not performed by either verification script.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-fit.txt
.venv/bin/python -B run_comparison.py --verify-only
.venv/bin/python -B run_comparison.py --out reproduction-run-01
.venv/bin/python -B recompute.py --run reproduction-run-01 --output reproduction-scores-01
```

The fitting command starts 30 tasks, at concurrency 2, with 600 seconds per task and no automatic retries. Each worker uses two CPU threads and a GP optimizer timeout of 180 seconds. The worker never opens official external labels. All planned terminal receipts are sealed before the scoring command opens labels. A failed or timed-out task stays in the denominator; its missing paired metrics are not imputed. The archived experiment completed 30/30 tasks. Numerical refits may vary with platform or library builds; the source, version, seed and data pins make those differences inspectable.

`run_comparison.py` resolves relative package paths and requires an explicit fresh output directory. The original fitting source and both original scoring sources remain under `frozen-source/` for inspection. They are reference files, not the portable command entry points. The native RF and author GP source files are byte-for-byte copies. No model checkpoint was saved in the recorded run; fitted parameters, training-matrix and label hashes, inner-selection metadata and every prediction are retained in `model-pins.json` and `run-01/`.

## Provenance and metric definitions

The protocol's method, input hashes, task order, seed, time limits, primary metric and secondary metrics were frozen before fitting. The coverage-only scoring amendment was frozen before external labels were opened for this scoring run. It adds whole-denominator RF availability and policy status, preserving the original paired calculation. All 30 task pairs succeeded, so no fallback or failure-only estimate enters the reported effect.

MAE and RMSE compare predicted and reported p-activity. Spearman uses average ranks for ties and reports zero for a constant predictor. The true top 10 and predicted top 10 use descending values with ascending candidate-ID tie breaking. Top-10 recall is the overlap fraction; best selected activity is the maximum reported p-activity among the predicted top 10. Predictive coverage uses posterior observation standard deviation and the fixed normal multiplier 1.6448536269514722.

Bootstrap seed is 20261011, with 5,000 draws. Each draw samples the 29 distinct target IDs with replacement, retaining every endpoint task within the selected target. Each draw then averages the task differences; the original point estimate weights each of the 30 tasks equally. Confidence intervals are the 2.5th and 97.5th bootstrap percentiles. Per-row or per-task independent resampling would be a different analysis.

`source-map.json` distinguishes untouched bytes from the portable protocol, portable fitting wrapper, and path-redacted v2 metadata. The archived protocol hash is retained separately from the public protocol hash; the two are not presented as the same artifact. The package manifest excludes itself, the generated `verification/` records, and optional future reproduction directories.
