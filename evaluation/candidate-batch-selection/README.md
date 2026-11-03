# Candidate batch selection on fixed molecular pools

This same-pool replay supports **keeping EVIDA's current selector**: latent pTop10 recall was **0.41467**, versus **0.41667** for the retained GP/RF policy, and the paired confidence interval included zero. A numerical equality correction changed **none of the 3,600 selected batches**; both complete versions and all positive and negative results are retained here.

## Purpose and method

The question is whether a saved joint GP posterior can choose a useful batch more effectively than ranking its mean. This is a finite-pool activity-selection component, not a complete research workflow, prospective experiment, or measurement-information-gain study. The same benchmark labels had already been examined during model evaluation, so this is explicitly an exploratory replay.

All **30 MoleculeACE target/endpoint tasks**, **29 target clusters**, and **9,802 candidates** are retained. Every method sees the same candidate IDs and saved predictions/posterior. No model is refitted. The reference policy is the original inner-validation choice: GP on 25 tasks and RF on five. Gold activity labels are used only after every task's selection output is terminal and sealed.

Eight methods are compared: RF mean, GP mean, the retained policy, uniform random, and latent/observation variants of qPO and pTop10. Batch sizes are 5, 10, and 20; seeds are 0–4; each seed uses **8,192 joint draws**. This yields **3,600 selection rows per version**. A row is a task/method/seed/batch result, not an independent biological experiment.

- **qPO** seeks a batch containing a best candidate. With unique posterior winners its utility is additive. With nonunique maxima, the independent implementation greedily covers still-uncovered winner events as in Supplement S1 of [Fromer et al.](https://arxiv.org/abs/2410.06333v2); this is an approximation, not a global optimum guarantee.
- **pTop10** ranks expected membership in a sampled top ten, allocating boundary ties fractionally. This fixed-b additive utility differs from qPO's best-capture objective.
- **Latent draws** represent the saved GP function distribution. **Observation draws** add its saved likelihood noise using an independent stream. Scores are model-conditioned Monte Carlo quantities, not calibrated experimental hit probabilities.

The primary comparison is latent pTop10 at batch10 against **both GP mean and the retained policy**, using measured-top10 recall with the original activity/ID tie ordering. Fractional-gold ties and observation variants are prespecified sensitivities. Five seed results are averaged within each task, then tasks receive equal weight. Paired percentile intervals resample whole target clusters 5,000 times, keeping CHEMBL237's Ki and EC50 tasks together.

## Actual results

Both versions completed all30 tasks and all3,600 rows without failure or fallback. All selected IDs, fallback fields, statuses, raw scientific metrics, summaries, and confidence intervals are identical between versions.

| Batch-10 method | Measured-top10 recall |
|---|---:|
| RF mean | 0.42667 |
| GP mean | 0.40333 |
| Retained GP25/RF5 policy | 0.41667 |
| Random | 0.04800 |
| qPO latent | 0.38733 |
| qPO observation | 0.38800 |
| **pTop10 latent — primary** | **0.41467** |
| pTop10 observation — sensitivity | 0.41733 |

| Primary paired comparison | Recall difference | 29-target-cluster 95% CI |
|---|---:|---:|
| pTop10 latent − GP mean | +0.01133 | [−0.00970, +0.03173] |
| pTop10 latent − retained policy | −0.00200 | [−0.03449, +0.02828] |

Both intervals span zero. This does not establish improvement or equivalence. RF's higher point estimate is not proof of general superiority, and qPO's lower recall is not an objective-matched rejection of its best-capture purpose. Batch20 and other sensitivities remain in the complete results rather than replacing the primary comparison. There is no retuning or automatic selector adoption from this replay.

[All method/batch metrics](verification/recalculation-01/all-method-metrics.csv), [all paired comparisons](verification/recalculation-01/all-paired-comparisons.json), and the original full scored files for [version01](records/acquisition-01/run-01/scored-results.json) and [version02](records/acquisition-02/run-01/scored-results.json) preserve every planned metric: ID and fractional top10 recall, any-best/ID-best/fractional-best capture, best activity, simple regret, and mean activity. Raw, operational-failure, and GP-fallback summaries are distinct even though their values coincide here because all rows completed.

### Numerical correction and failure accounting

Version01 multiplies an expanded covariance factor whose equal rows need not yield bit-identical columns under BLAS. One actual duplicate pair differed by at most2.66e-15; across110 actual group/seed checks this split no latent winner or top10 boundary. A synthetic boundary example nevertheless showed incorrect tie allocation. Version02 calculates each quotient variable once and copies its samples to equivalent columns. All110 equality checks then became bit-identical. Methods, seeds, draws, posterior, metrics, and budgets stayed fixed; the full rerun changed zero selection rows. See [the technical amendment](records/acquisition-02/technical-amendment.json) and [independent review](review/review-02/REVIEW.md).

Synthetic tests also exposed a parent-runner failure when a killed worker left truncated JSON. The preserved recovery correction retains those bytes, records failed rows and separate fallback IDs, and finishes the denominator. Its actual-SIGKILL regression preserves30 tasks/3,600 rows, including228 expected failure rows in the expanded fixture. These are synthetic failure tests, not failures hidden from the successful scientific run. The earlier fixtures, setup errors, and raw logs remain archived. A version02 scoring launcher initially used an incorrect executable path and made no scoring call; its sole actual scorer invocation then completed. No model or GPU calls occurred.

## Verify or reproduce

The archive is self-contained for score recomputation and replay from the saved posterior: it includes all30 NPZ files (about32MB total; largest4.12MB), candidate packets, source CSVs, labels, predictions, selections, and code. There is no external checkpoint download or omitted-posterior placeholder.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -B verify_package.py
.venv/bin/python -B recompute.py --out recalculation-local
```

Verification checks original/public hashes, source identities, and all9,802 gold rows against the source CSVs. Independent recomputation recalculates **28,800 raw metric values and1,008 paired intervals per version** to tolerance1e-12. The [verification receipt](verification/recalculation-01/receipt.json) records the successful packaged-artifact run. These commands do not fit a model, resample acquisitions, use a GPU, or call a provider. Dependency installation may use the network; the checks do not.

[REPRODUCING.md](REPRODUCING.md) provides the separate CPU selection-replay commands and clearly distinguishes validated local path preparation from a fresh full rerun. All40 exported Python sources preserve their original function/class ASTs and bytes. The explicit [source map](source-map.json) records original hashes, public hashes, and path/session redactions; scientific values are unchanged. Historical archived drivers are not standalone entrypoints without portable path bindings.

## Next assessment

Keep the current selector. Assess a fixed objective on an independently chosen, condition-matched cohort before using a posterior acquisition score to allocate new experiments. A further study should specify measurement precision, failed measurements, costs, and how each observed result changes the next action; none is demonstrated by this single-batch fixed-pool replay.

[Attribution and licenses](ATTRIBUTION.md) cover MoleculeACE, upstream ChEMBL data, the Tanimoto GP source, and the qPO paper. The qPO authors' repository code is excluded because no redistribution license was established. The included acquisition implementation is independent; a small historical author-function probe is recorded as such, not as a full author-engine validation.
