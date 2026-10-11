# Complete task and metric tables

All 30 planned tasks completed. RF and GP were usable on 30/30; the inner-selected policy chose GP on 25 and RF on 5. No failed, timed-out, missing, or gate-abstained task is omitted.

The task is the unit for reported means; confidence intervals resample 29 target clusters. CHEMBL237 has two endpoint tasks. Every value below is computed from the sealed predictions. The tables preserve the official task order.

## All declared paired effects

| Comparison | Metric | Mean difference | 95% CI | Tasks / clusters | Lower / higher / tied |
|---|---|---:|---|---:|---:|
| GP − RF | mae | -0.023118 | [-0.033563, -0.013332] | 30 / 29 | 23 / 7 / 0 |
| GP − RF | rmse | -0.033934 | [-0.045128, -0.022590] | 30 / 29 | 27 / 3 / 0 |
| GP − RF | spearman | +0.024462 | [+0.015400, +0.035698] | 30 / 29 | 5 / 25 / 0 |
| GP − RF | top10_recall | -0.023333 | [-0.065517, +0.020690] | 30 / 29 | 13 / 7 / 10 |
| GP − RF | best_true_activity_in_selected10 | -0.010259 | [-0.058749, +0.034041] | 30 / 29 | 3 / 1 / 26 |
| Inner policy − RF | mae | -0.023147 | [-0.032774, -0.014000] | 30 / 29 | 22 / 3 / 5 |
| Inner policy − RF | rmse | -0.032668 | [-0.044089, -0.021245] | 30 / 29 | 23 / 2 / 5 |
| Inner policy − RF | spearman | +0.023610 | [+0.014380, +0.034835] | 30 / 29 | 2 / 23 / 5 |
| Inner policy − RF | top10_recall | -0.010000 | [-0.043750, +0.024138] | 30 / 29 | 10 / 6 / 14 |
| Inner policy − RF | best_true_activity_in_selected10 | -0.007028 | [-0.056086, +0.037547] | 30 / 29 | 2 / 1 / 27 |

Lower differences favor GP/policy for MAE and RMSE; higher differences favor them for the other metrics. Intervals are descriptive, unadjusted for multiple metrics.

## All task results

MAE is in p-activity units. R@10 is measured top-10 recall. Coverage is the fraction inside the uncalibrated nominal 90% observation-predictive interval. Width is its mean width in p-activity units. `per-task.csv` also contains every RMSE, best-selected-activity value, training-mean metric, policy metric, convergence flag and runtime.

| Task | Test rows | RF MAE | GP MAE | RF ρ | GP ρ | RF R@10 | GP R@10 | Policy | Coverage | Width |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| CHEMBL1862_Ki | 161 | 0.57425 | 0.59165 | 0.8461 | 0.8363 | 0.60 | 0.50 | GP | 0.925 | 2.424 |
| CHEMBL1871_Ki | 134 | 0.58233 | 0.55971 | 0.7088 | 0.7806 | 0.20 | 0.40 | GP | 0.866 | 1.962 |
| CHEMBL2034_Ki | 152 | 0.55095 | 0.52050 | 0.6793 | 0.7021 | 0.60 | 0.60 | GP | 0.882 | 2.071 |
| CHEMBL2047_EC50 | 128 | 0.48272 | 0.48812 | 0.7426 | 0.7425 | 0.70 | 0.60 | RF | 0.906 | 2.041 |
| CHEMBL204_Ki | 553 | 0.62599 | 0.53600 | 0.8241 | 0.8612 | 0.10 | 0.30 | GP | 0.919 | 2.564 |
| CHEMBL2147_Ki | 294 | 0.53924 | 0.51739 | 0.9117 | 0.9215 | 0.30 | 0.20 | GP | 0.915 | 2.285 |
| CHEMBL214_Ki | 666 | 0.55419 | 0.52119 | 0.7656 | 0.7880 | 0.60 | 0.60 | GP | 0.899 | 2.165 |
| CHEMBL218_EC50 | 208 | 0.57406 | 0.57848 | 0.6774 | 0.6746 | 0.60 | 0.60 | GP | 0.889 | 2.249 |
| CHEMBL219_Ki | 374 | 0.58868 | 0.56615 | 0.6871 | 0.7139 | 0.20 | 0.40 | GP | 0.885 | 2.290 |
| CHEMBL228_Ki | 342 | 0.59380 | 0.51298 | 0.7487 | 0.8111 | 0.40 | 0.40 | GP | 0.906 | 2.247 |
| CHEMBL231_Ki | 197 | 0.62742 | 0.58232 | 0.7661 | 0.7881 | 0.50 | 0.50 | RF | 0.863 | 2.052 |
| CHEMBL233_Ki | 630 | 0.62323 | 0.61739 | 0.7691 | 0.7782 | 0.60 | 0.40 | GP | 0.878 | 2.357 |
| CHEMBL234_Ki | 733 | 0.52272 | 0.47548 | 0.7763 | 0.8039 | 0.40 | 0.50 | GP | 0.910 | 2.084 |
| CHEMBL235_EC50 | 472 | 0.50506 | 0.52103 | 0.7718 | 0.7674 | 0.30 | 0.50 | RF | 0.888 | 2.188 |
| CHEMBL236_Ki | 521 | 0.55089 | 0.53243 | 0.8318 | 0.8449 | 0.50 | 0.50 | GP | 0.893 | 2.268 |
| CHEMBL237_EC50 | 193 | 0.64550 | 0.61783 | 0.8093 | 0.8204 | 0.40 | 0.50 | GP | 0.927 | 2.839 |
| CHEMBL237_Ki | 522 | 0.58596 | 0.53789 | 0.8244 | 0.8405 | 0.20 | 0.10 | GP | 0.900 | 2.288 |
| CHEMBL238_Ki | 213 | 0.54554 | 0.54458 | 0.7817 | 0.7939 | 0.50 | 0.30 | GP | 0.892 | 2.177 |
| CHEMBL239_EC50 | 347 | 0.55100 | 0.54160 | 0.7412 | 0.7524 | 0.30 | 0.20 | GP | 0.899 | 2.343 |
| CHEMBL244_Ki | 621 | 0.59164 | 0.55316 | 0.8662 | 0.8833 | 0.40 | 0.40 | GP | 0.911 | 2.409 |
| CHEMBL262_Ki | 173 | 0.57606 | 0.58076 | 0.6810 | 0.6983 | 0.60 | 0.60 | GP | 0.919 | 2.479 |
| CHEMBL264_Ki | 574 | 0.50936 | 0.48079 | 0.7547 | 0.7973 | 0.60 | 0.50 | GP | 0.892 | 2.008 |
| CHEMBL2835_Ki | 126 | 0.27650 | 0.27902 | 0.8596 | 0.8524 | 0.40 | 0.20 | RF | 0.897 | 1.149 |
| CHEMBL287_Ki | 267 | 0.59240 | 0.57128 | 0.6878 | 0.7175 | 0.30 | 0.20 | GP | 0.888 | 2.311 |
| CHEMBL2971_Ki | 197 | 0.42534 | 0.44743 | 0.8726 | 0.8879 | 0.50 | 0.20 | RF | 0.883 | 1.626 |
| CHEMBL3979_EC50 | 226 | 0.52191 | 0.49748 | 0.7993 | 0.8190 | 0.30 | 0.30 | GP | 0.885 | 2.060 |
| CHEMBL4005_Ki | 193 | 0.52503 | 0.50690 | 0.7838 | 0.8137 | 0.50 | 0.50 | GP | 0.845 | 1.833 |
| CHEMBL4203_Ki | 149 | 0.65518 | 0.65159 | 0.5712 | 0.5959 | 0.30 | 0.40 | GP | 0.852 | 2.294 |
| CHEMBL4616_EC50 | 139 | 0.59486 | 0.54286 | 0.4503 | 0.5910 | 0.40 | 0.30 | GP | 0.899 | 2.144 |
| CHEMBL4792_Ki | 297 | 0.56776 | 0.49206 | 0.7575 | 0.8032 | 0.50 | 0.40 | GP | 0.899 | 2.072 |

## Files

- [row-predictions.csv](row-predictions.csv): all 9,802 held-out identities, labels, RF/GP/mean/policy predictions, and both GP standard deviations.
- [per-task.csv](per-task.csv): every declared metric, plus interval coverage/width and operational status, for every task.
- [paired-ci.csv](paired-ci.csv): all ten GP/RF and policy/RF paired metric contrasts.
- [summary.json](summary.json): full-precision numerical result, including coverage and all 30 task records.
- [Original scored result](../run-01/scored-results.json): byte-identical frozen v1 output.
- [Coverage supplement](../run-01/scored-results-v2.json): all numerical fields preserved; its file locator is made relative.

The RF-only availability supplement covers the entire planned denominator. Because every GP/RF pair completed, there are no unpaired-only rows or retrospective fallback decisions. Training-mean scores are a simple reference, not a separate learned arm.
