# Tanimoto GP activity prediction: a paired EVIDA component evaluation

An exact Tanimoto Gaussian process achieved **4.16% lower task-average MAE** than EVIDA's native random forest on **all 30 MoleculeACE target/endpoint tasks and 9,802 held-out rows**. Mean Spearman correlation increased from **0.7582 to 0.7827**. Top-10 selection metrics did not improve. This package retains every planned task, saved prediction, declared metric, and paired confidence interval.

## Method and reason for trying it

EVIDA evaluates candidates against activity records for a specified target and endpoint. Its RF control learns from Morgan molecular fingerprints. The trial uses the unchanged `TanimotoKernelGP` and `T_DP` kernel from [Tripp et al., *Tanimoto Random Features for Scalable Molecular Machine Learning*](https://github.com/AustinT/tanimoto-random-features-neurips23/tree/f0edc6b88471ccc9eb19c05ed3e16a6dbf7879e2).

For binary fingerprints, Tanimoto similarity measures shared active bits relative to their union. A GP uses that similarity as covariance, learns a signal scale, observation-noise level and constant mean, and produces a posterior mean and uncertainty. This experiment tests the authors' **exact kernel GP** as a candidate estimator for EVIDA's activity-prediction task.

## Identical training information

The dataset is [MoleculeACE at commit `7e6de0b`](https://github.com/molML/MoleculeACE/tree/7e6de0bd2968c56589c580f2a397f01c531ede26). All 30 official task files are included. Each task retains its official external train/test split. Within official training rows, the native EVIDA input preparation selects one endpoint and applies the existing largest-Murcko-group-first inner split, using approximately 75% for fitting. Both estimators receive **the exact same inner-training matrix and labels**: Morgan radius 2, 2,048 binary bits, chirality enabled. Neither estimator is refitted on the inner holdout before external testing.

Native input preparation rounds per-structure median training labels to three decimals; both arms share those same labels. External evaluation retains the unrounded official labels. The RF uses 300 trees, minimum leaf size 2 and seed 20260930. The GP uses CPU float64, training-only label standardization, exact Cholesky calculations, and a bounded SciPy fit of marginal likelihood. The adapter calls the modern BoTorch fitter in place of the author's older fitter API; the author kernel/model source is unchanged.

Each arm must pass the inner gate: Spearman at least 0.3 and MAE below the inner-training-mean predictor. GP additionally requires optimizer convergence. A separate **inner-selected policy** chooses the usable arm with lower inner-holdout MAE, breaking ties toward RF; it abstains if neither qualifies. This policy is selected without official test labels. All 30 fits completed and both gates passed on every task; the policy selected GP on 25 tasks and RF on 5.

## Measured results

Values are equal-weight averages over the 30 tasks. Paired differences are GP minus RF; lower error and higher correlation/selection metrics are favorable. MAE is the primary prespecified metric. The 95% percentile intervals use 5,000 paired bootstrap draws over **29 target clusters**: CHEMBL237's Ki and EC50 tasks stay together. The 9,802 rows are not treated as independent experiments. Secondary intervals are not adjusted for multiple comparisons.

| Prespecified metric | Training mean | Native RF | Trial GP | GP − RF, 95% CI |
|---|---:|---:|---:|---:|
| MAE ↓ | 1.01055 | 0.55532 | **0.53220** | −0.02312 [−0.03356, −0.01333] |
| RMSE ↓ | 1.21481 | 0.74612 | **0.71219** | −0.03393 [−0.04513, −0.02259] |
| Spearman ↑ | 0.00000 | 0.75824 | **0.78270** | +0.02446 [+0.01540, +0.03570] |
| Measured top-10 recall ↑ | 0.03333 | 0.42667 | 0.40333 | −0.02333 [−0.06552, +0.02069] |
| Best measured p-activity among selected 10 ↑ | 8.79239 | 10.02079 | 10.01053 | −0.01026 [−0.05875, +0.03404] |

GP reduced MAE on 23/30 tasks and increased Spearman on 25/30. The relative MAE reduction is the difference between task-macro MAEs divided by RF's task-macro MAE, not an average of per-task percentages. Top-10 ties are resolved by candidate ID, including the constant-mean control.

The inner-selected policy had MAE **0.53217** (policy − RF: −0.02315, 95% CI [−0.03277, −0.01400]) and Spearman **0.78185** (+0.02361 [+0.01438, +0.03483]). Its top-10 recall was **0.41667** (−0.01000 [−0.04375, +0.02414]). All five policy metrics and all 30 task results appear in [the full tables](results/README.md), [per-task.csv](results/per-task.csv), and [paired-ci.csv](results/paired-ci.csv).

Nominal 90% GP observation-predictive intervals covered a task-average **89.38%** of test labels, with mean width **2.1760 p-activity units**. This is an uncalibrated diagnostic with substantial interval width. Latent and observation standard deviations are retained separately.

## Verify or reproduce

The package is self-contained. Verification and metric recalculation need Python and NumPy; they make no network, provider, GPU, or fitting calls.

```bash
python -B verify_package.py
python -B recompute.py --output recalculation-local
```

The output directory must be new. Recalculation checks every original receipt and prediction hash, recomputes every metric and confidence interval, checks numerical agreement with the frozen result to `1e-12`, and reconciles the [row-level CSV](results/row-predictions.csv). Source CSVs, derived train/features/gold files, and their row identities are also verified. The archived results passed this check. [The verification receipt](verification/recalculation-02/summary.json) records the actual recalculation environment.

For a separate full CPU refit, install the versions in [requirements-fit.txt](requirements-fit.txt) and follow [REPRODUCING.md](REPRODUCING.md). The portable fitting wrapper retains the original worker and supervisor bodies; path resolution and command-line output handling differ. [source-map.json](source-map.json) records original and portable hashes, and [the source check](provenance/portable-source-check.json) confirms those unchanged function bodies. The portable wrapper was checked without running a second fit while assembling this package.

## Interpretation and next check

These results support better **reported-activity estimation and overall ranking** under the captured benchmark conditions. Top-10 recall was 0.4033 for GP and 0.4267 for RF. The next useful check is a conditional GP option in the candidate-scoring path, followed by evaluation of the selection objective on a separate cohort before using it to allocate experiments.

MoleculeACE aggregates reported assays within target/endpoint tasks, with potentially different assay, species and experimental conditions. The official external split and the native inner scaffold split are distinct. This retrospective component evaluation measures prediction of those reported activities. A separate condition-matched cohort and prospective candidate measurements would test transfer to experimental selection. Official labels and RF benchmark results are public; the protocol records this local experiment's freeze and seal order. The recorded predictors used CPU computation throughout.

Author and dataset citations, license notices and adaptation details are retained in [ATTRIBUTION.md](ATTRIBUTION.md). [protocol.json](protocol.json), [dataset-pins.json](dataset-pins.json), [model-pins.json](model-pins.json) and [package-manifest.json](package-manifest.json) identify the exact material behind this result.
