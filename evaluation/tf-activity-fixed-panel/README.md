# Fixed-panel transcription-factor recovery

R decoupleR ULM, MLM, raw signed WMEAN and TF-own-expression are compared on the same 30 frozen KnockTF contrasts under two fixed priors. These exploratory results support retaining EVIDA's current ULM component and examining the prior-specific differences in a separate assessment.

## Why this comparison

A transcription factor's own expression and its downstream target pattern answer related but different questions. This numerical component check measures how these methods rank the annotated inhibited TF. Own-expression provides a simple baseline grounded in the knockdown corpus; downstream target patterns provide a complementary estimate of activity.

## Method and adaptation

The panel was fixed before expression acquisition: Python seed 20261011 shuffles the published metadata order, selecting the first 30 distinct TFs and Profile.IDs without coverage, expression or method-success filtering. All 30 remain in every comparison ledger. This is an exploratory replay of historically known data. Selection spans the full metadata inventory, including cases outside the historical own-TF-logFC < −1 subset.

R 4.4.3 / decoupleR 2.12.0 runs ULM, MLM and raw WMEAN with minsize=5 under frozen DoRothEA and CollecTRI TSVs. Primary inputs retain the CSV's 21,985 represented genes and all stored zeros, including 208 columns zero across this panel. A separate sensitivity drops each row's exact numeric zeros. The zero-omission sensitivity follows the author's documented convention while the original cell-level missingness remains unresolved. Both representations use the published raw log2FC values. The fixed-panel R design keeps its own denominator and preprocessing contract alongside the publication's filtered Python benchmark.

Eligibility is determined from input genes and prior edges before scores: at least five distinct represented targets per TF. Each method must cover the entire eligible universe. Own-expression comparisons additionally require available TF-own-gene values. Cross-prior and cross-representation comparisons use the prespecified input-based intersections. Published target labels were joined only after all 420 terminal records were sealed and passed the independent output gate.

Ascending ranks follow the fixed inhibitory-corpus assumption. Exact ties have midranks, RR is 1/midrank, and normalized rank (NR) is (rank−1)/(universe size−1). Primary metrics are paired mean NR and RR differences. Top-1/top-5 fractional capture is secondary. A difference is always comparator b minus reference a: positive NR favors a; negative RR/top-k favors a. ULM/own-expression has a slightly different universe from ULM/MLM or ULM/WMEAN; its ULM numbers are therefore reported separately.

## Actual results

All 14 arms × 30 tasks finished: **419 succeeded, one MLM method failure**. The zero-omission DoRothEA MLM call for T23 rejected collinear covariates. Its original covariates and failed result remain in the fixed denominator. There were 186 actual R method calls (batch primary, row-wise sensitivity), one live worker, two CPUs, 8 GiB address-space limit, 600-second per-arm limit and 8,700-second outer limit. The supervisor completed in 1,132.85 seconds. Six separate tiny author-method calls established synthetic numerical/batch parity before the actual panel.

Primary stored-zero results, with unavailable targets retained outside paired means:

| Prior | Methods a / b | Paired / planned | Mean NR a / b ↓ | Mean RR a / b ↑ | Secondary top-5 totals a / b |
|---|---|---:|---:|---:|---:|
| dorothea | ULM / mlm | 16/30 | 0.304476 / 0.319679 | 0.198745 / 0.174155 | 5 / 3 |
| dorothea | ULM / wmean | 16/30 | 0.304476 / 0.316934 | 0.198745 / 0.051995 | 5 / 2 |
| dorothea | ULM / own_expression | 16/30 | 0.304553 / 0.184386 | 0.198802 / 0.304813 | 5 / 7 |
| collectri | ULM / mlm | 21/30 | 0.401342 / 0.345935 | 0.103315 / 0.119551 | 2 / 3 |
| collectri | ULM / wmean | 21/30 | 0.401342 / 0.412487 | 0.103315 / 0.007614 | 2 / 0 |
| collectri | ULM / own_expression | 21/30 | 0.400859 / 0.163512 | 0.103507 / 0.276974 | 2 / 8 |

DoRothEA has 14/30 target-unavailable rows in each primary comparison; CollecTRI has 9/30. They remain explicitly unavailable in the coverage ledger. On paired primary rows, DoRothEA favors ULM over MLM and raw WMEAN; CollecTRI favors MLM over ULM on mean NR/RR. Own-expression is strong under both priors. The prior-dependent results favor retaining the current component while testing the CollecTRI MLM signal on a separate panel.

All 26 comparisons, including less favorable results and zero-omission sensitivities, are in `data/all-comparison-summaries.csv` and `data/scored-results.json`. The full 780 comparison rows preserve every candidate score and rank in `data/comparison-details.json.gz`. `data/availability.json` records structural and technical reasons for all 420 arm/task entries; `data/terminal-records.json.gz` preserves all numerical method outputs and the failure. An unavailable target takes precedence in a comparison's status; the separate technical ledger keeps failures visible even in such comparisons. Unavailable results retain their null values and recorded reasons.

## Recheck and reconstruction

Run `python scripts/verify_recompute.py` offline with Python 3.10+ and its standard library. It checks the public manifest, all 420 records and 780 comparison rows, joins preserved method scores to every comparison universe, independently recomputes 425,524 candidate rank checks, exact-tie metrics, all paired means/deltas and all denominators. The script uses an independent implementation of the rank arithmetic on preserved outputs. `verification.json` is the recorded result.

The package supplies the numerical outputs and exact source identities. Obtain the expression matrix and metadata separately from the official references in `SOURCE_DATA.md`, then run:

```sh
python scripts/reconstruct_packets.py --expression /path/knockTF_expr.csv --metadata /path/knockTF_meta.csv --output /new/opaque-inputs
```

This separately verifies source hashes, the seed-based panel and all 30 exact packet hashes. The reconstruction was tested against the retained official files; its receipt is included. Source and eligibility checks require the corresponding external inputs. Frozen method/scorer/worker code is byte-identical in `frozen/`; path-bearing JSON uses documented placeholders. A full inference rerun additionally requires the exact prior TSVs, the matching R/package runtime, path rebinding and a newly frozen local execution manifest. The included offline check covers the preserved outputs and their arithmetic.

`source-map.json` links every exported output to its original SHA256. Host roots alone are replaced with explicit placeholders; scientific output numbers and strings remain unchanged. Aggregation and deterministic gzip are lossless. Original source/scoring seals bind their original files; `package-manifest.json` binds the transformed public files. The frozen protocol preserves its pre-execution draft/approval fields; `data/scored-results.json` records the completed result.

## Next assessment

Retain ULM in the current product. The next assessment should fix an independent panel and use appropriate native t/z statistics to test the CollecTRI MLM signal under the product's input conditions. Preserve own-expression as a visible baseline and report target coverage alongside paired accuracy. Resolving source-cell availability would allow a more direct assessment of measured target coverage; until then, report stored-zero and zero-omission results separately. Keep this completed panel fixed as the reference for that assessment.

See `RIGHTS.md` for source attribution and the package's redistribution scope.
