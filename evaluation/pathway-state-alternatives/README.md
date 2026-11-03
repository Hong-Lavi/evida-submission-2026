# Alternative explanations from a fixed CARNIVAL problem

EVIDA can ask whether a selected upstream node’s change is required to achieve the same score in a saved pathway explanation. Comparing the original solution with a concrete alternative helps researchers decide which mechanistic distinction deserves the next measurement.

## Purpose and method

This development case uses **one fixed problem and two inferred TF signs**, E2F4(+) and IRF1(−), from the GSE47460 whole-lung contrast of 122 IPF and 91 control samples. Absolute inferred scores weight sign mismatch.

For each chosen node separately, the query adds two equalities setting its original up/down variables to zero. The original activation term is already fixed to zero; the prior, observations, other constraints and objective remain intact. **Zero means an unused change state relative to the modeled contrast.** The calculation identifies alternative explanations; biological intervention effects require measurement.

## Three experimental runs and one product-path check

| Run | Total objective | TF sign error | State penalty | Seconds |
|---|---:|---:|---:|---:|
| Baseline | 1.2 | 0 | 1.2 | 48.27 |
| GSK3B state unused | 1.2 | 0 | 1.2 | 68.10 |
| MDM2 state unused | 1.2 | 0 | 1.2 | 22.24 |
| Native GSK3B path check | 1.2 | 0 | 1.2 | 68.47 |

Both separate queries retained E2F4(+1) and IRF1(−1) at total objective 1.2. The native run confirms the product’s execution path on the same problem. The denominator remains **one problem and two node queries**.

The artificial source remains free and changes from +1 to −1 in the GSK3B solution. This freedom is part of the explanation model. Independent Decimal evaluation found zero violations across all 11,791 variables and all constraints, bounds and integer conditions. CBC reported optimality; unprinted final numeric bounds/gaps remain null. Total score and TF fit are checked separately, including a synthetic example where they differ.

## Recalculate and reproduce

Run the standard-library check:

```bash
python -B verify_results.py
```

It verifies hashes, recomputes all four saved vectors’ objective terms and TF fits, and checks the complete synthetic LP.

Full real-problem constraint verification requires a separately authorized copy of the exact pinned base LP:

```bash
python -B verify_full_primal.py --base-lp /path/to/authorized/base.lp
```

The academic-use prior’s redistribution terms remain unresolved, so real LPs, full maps and named edge lists stay outside this package. Detailed records, attribution, solver settings and this conditional reproduction boundary are retained in `NOTICES.md`, `environment-and-sources.json` and the verification records.

## Next observation

Select a feasible observation whose expected outcomes differ between the retained explanations. Specify the assay context and intervention/readout controls before interpreting the outcome; a failed control leads to repair. The equal-score alternatives make that choice concrete while keeping both explanations available.
