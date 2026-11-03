# Independent sealed acquisition-result review

The reported scientific arithmetic and original baselines reproduce. The result does not support automatic selector replacement: pTop10 latent is slightly above GP mean and slightly below the retained policy, with both paired intervals spanning zero. A separate numerical equality-contract bug is confirmed, although it did not split a latent winner or top10 boundary in the inspected actual fixed draws. Keep these conclusions separate.

No original protocol, selection, score, or product file was modified. No real candidate batch was reselected and no alternative actual score was generated. The audit read the authorized sealed labels and used CPU-only sample reconstruction for variance/equality diagnostics; no model, network, or GPU calls occurred.

## Result integrity and baseline parity — PASS

Protocol SHA `d79d47c2078c9bde25b2598766bc1a5b2fa00e73cfdcee4cad178f2a924f9046`.
Selection seal SHA `7ce488b6f5daba8a9bee0518e944d498c5a9bb809f585d38237167e641a52473`.
Scored result SHA `2500403040530d34187a277e1b483d426f367f54a6722d3c8d2f643482c1917a`.

All source/input pins and every terminal receipt/selection artifact were verified before label parsing. Original task order and IDs match the saved GP trial: 30 tasks, 29 target clusters, 9,802 candidates. The saved policy remains GP25/RF5. The full 3,600 method/seed/batch rows are completed, with no fallback or failed rows.

Saved RF and GP prediction vectors and candidate IDs match their original sealed predictions exactly. Every deterministic RF/GP/policy selected batch matches the declared mean/ID sorting. At batch 10, 450 task/seed/baseline comparisons reproduce the original stored recall and best-activity values. Independent Python sorting/counting recomputes all 28,800 raw metric values; maximum numeric difference is 3.55e-15. All raw/fallback/operational summaries coincide because no method failed.

| Batch-10 method | ID-resolved measured-top10 recall |
|---|---:|
| RF mean | 0.4266666667 |
| GP mean | 0.4033333333 |
| Retained original policy | 0.4166666667 |
| pTop10 latent | 0.4146666667 |
| pTop10 observation | 0.4173333333 |
| qPO latent | 0.3873333333 |
| qPO observation | 0.3880000000 |
| Random | 0.0480000000 |

The independent primary bootstrap explicitly samples whole target clusters, expands every sampled cluster's task differences, and takes their equal-task mean. It reproduces both original 5,000-resample intervals:

| pTop10 latent minus comparator | Mean difference | Cluster 95% interval | Task wins/losses/ties |
|---|---:|---:|---:|
| GP mean | +0.0113333333 | [-0.0097045455, 0.0317279095] | 9/5/16 |
| Original policy | -0.0020000000 | [-0.0344873563, 0.0282758621] | 8/7/15 |

These are exploratory paired intervals, not confirmation of improvement or equivalence. RF's higher point estimate also does not establish universal superiority. qPO targets best-candidate capture, so its lower top10 recall alone is not an objective-matched rejection. The higher observation pTop10 point estimate is a fixed sensitivity, not a reason to switch the preferred arm after results.

## Covariance and sample moments

Reconstructed posterior mean, latent SD, and observation SD match every original reconstruction receipt and its preserved absolute1e-7 criterion. Largest differences are respectively 3.09e-8, 2.70e-8, and 2.57e-8. The first reviewer check initially assumed stricter1e-10 equality; the assumption and correction to the preexisting criterion are recorded separately, without changing any scientific input.

Every declared equality group satisfies the recorded mean/covariance/zero-difference-variance tolerances. Rank, quotient group count, projected covariance, observation-noise extrema, and absence of jitter reproduce. Maximum covariance projection correction is 5.03e-15. Seed-0 sample variances over8,192 draws have largest standardized deviations3.87 for latent and3.64 for observation across9,802 marginal checks; these are Monte Carlo diagnostics, not coverage calibration. Seed-0 nonunique winner counts reproduce the saved diagnostics, and all saved top10 membership sums are10.

## P2 numerical bug: duplicate factor rows do not guarantee identical samples

**Location:** `acquisition.py:120`, with exact equality consumed by qPO at lines89–101 and fractional top membership at75–86.

The implementation repeats equal rows in the covariance factor before multiplying random draws by the factor transpose. BLAS can evaluate duplicate output columns through different accumulation kernels, yielding last-bit differences. The declared same-latent-variable equality is therefore lost before exact winner/tie comparisons.

Actual evidence across22 equality groups and5 seeds (110 group/seed checks): only `CHEMBL228_Ki` group indices334/336, candidates `CHEMBL228_Ki:1684` and `CHEMBL228_Ki:1694`, split. The five seeds have1,270/1,186/1,266/1,235/1,218 nonidentical draws out of8,192; maximum difference2.66e-15. Across all110 checks, these discrepancies caused **zero split global-winner events and zero split top10-boundary events**. Thus no actual latent acquisition-mask effect was observed in this fixed run. This is not a claim that a new implementation's full rerun will produce byte-identical samples or batches.

A deterministic synthetic counterexample with194 candidate factor rows,5 factors,128 draws, and two identical rows shows material tie semantics:46/128 winner events split. The identical candidates' empirical qPO winner probabilities become0.8359375/0.8046875 instead of1/1. With nine higher candidates and the duplicate pair at the tenth-place boundary, their pTop10 membership probabilities become0.515625/0.484375 instead of0.5/0.5. This demonstrates a bug in promised equality handling, not better scientific performance.

A local arithmetic prototype calculates each quotient sample once and expands columns using the group lookup. It restores bit-identical duplicated columns and the synthetic tie probabilities. That is the appropriate narrowly scoped correction; no product/selection code was changed here. Observation draws should continue adding independently sampled likelihood noise after latent expansion. If a corrected actual attempt is authorized, preserve original outputs and all methods, seeds, draws, metrics, and denominators; do not select a favorable method or retune using the known test outcomes.

## Artifacts and limits

- `independent-actual-result.json`: score, baseline, CI, and covariance checks. Its PASS is the arithmetic/integrity result, not a clean bill for the equality contract.
- `equality-diagnosis.json`: all actual equality exceptions and reproducible synthetic generation parameters, including the quotient-only arithmetic prototype.
- `review-verdict.json`: separates arithmetic PASS, numerical bug, and the unsupported adoption claim.
- `verify_actual.py` and `equality_diagnosis.py`: review-only reproduction scripts; original inputs remain read-only.

No prospective validation, posterior calibration, multi-round learning, experimental measurement-failure analysis, or optimal batch-design claim follows from this fixed-pool replay. No GitHub package or push was prepared.
