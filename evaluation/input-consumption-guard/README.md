# Keeping prepared decisions tied to the input they reviewed

In five fixed software scenarios, EVIDA's input-consumption guard prevented two stale publications that the reference implementation accepted: a pending decision prepared before **a new question** or **another publication** at the same state revision. Both implementations preserved normal publication, rejection after a revision-changing correction, and atomic rollback on a database error.

| Fixed scenario | Expected behavior | Reference implementation | Versioned-consumption implementation |
|---|---|---|---|
| Nothing changes after preparation | Publish | Published · pass | Published · pass |
| A correction advances the revision | Reject pending publication | Rejected · pass | Rejected · pass |
| A question is reframed at the same revision | Reject pending publication | Published · property failure | Rejected · pass |
| Another decision publishes at the same revision | Reject pending publication | Published · property failure | Rejected · pass |
| SQLite aborts the workspace update | Roll back the whole transaction | Rolled back · pass | Rolled back · pass |

The fixed denominator is **5 scenarios per implementation**: 3/5 expected properties for the reference and 5/5 for the guarded implementation. Every original outcome, including the reference failures, is retained. These deliberately selected schedules test deterministic software behavior; they are not a sample of scientific tasks, language-model quality, or real-world concurrency frequency.

## How the guard works

A state revision alone does not identify every context change. A question or decision can change without advancing that revision. The guarded implementation records the server-bound input consumed by a response, including the current intent structure, frame identity and latest publication. It compares the received snapshot again under the SQLite write lock before publication. A stale proposal remains inspectable, while its review sidecars are not applied and the current decision is retained. Model-authored consumption declarations remain declarations; the server binds their literal content and version.

The replay calls the actual native `Store`, `Runner.frame`, `Runner.model_context`, and finalization `prepare`/`commit` functions. It uses fresh synthetic workspaces and separate processes for the two implementations. It imports no product test modules, sends no model or network requests, and uses no GPU.

Both implementations receive the same source bytes, intent records, question and substantive proposed decision. The guarded interface additionally receives its required, scripted consumption metadata. The [input-equivalence record](recorded-run/input-equivalence.json) confirms equality after removing only that metadata and replacing random artifact IDs with their source hashes. All original source and initial decision bytes were retained. The rollback scenario left the whole state unchanged.

## Inspect the complete result

- [Original comparison](recorded-run/comparison.json): all ten implementation/scenario outcomes.
- [Reference results](recorded-run/current/results.json) and [guarded results](recorded-run/improved/results.json): individual assertions, including both reference failures.
- `recorded-run/<implementation>/<scenario>/`: original proposals, before/after state, event traces and results, all synthetic.
- [Portable reproduction](portable-check/comparison.json): a fresh offline replay with the same five scenarios and matching observed properties.
- [Source mapping](source-map.json): native source hashes, exact method extracts, and disclosed portability changes.

No visitor database or private researcher wording is included. State JSON records are synthetic. Reproduction creates new local SQLite files; it never opens a live EVIDA database.

## Reproduce locally

Use Python 3.13 and `jsonschema`; the recorded check used Python 3.13.9 and jsonschema 4.25.0. Dependency installation is separate from the offline replay.

```bash
python -m pip install -r requirements.txt
python -B verify.py
python -B replay.py plan --current native/current --improved native/improved --out local-runs/run-01
python -B replay.py run --plan local-runs/run-01/plan.json
python -B verify_input_equivalence.py local-runs/run-01
python -B verify.py --comparison local-runs/run-01
```

Use a new output directory. The driver rejects changed code after planning and does not retry a failed run. The labels `current` and `improved` are retained from the original recording; here they identify the reference and guarded implementations respectively.

The original recording initialized the full production Runner and checked its science-environment identity. The portable version extracts the **unchanged native state-method bodies** and supplies only their Store and original context-delivery setting. It does not initialize a gateway, worker pools, scientific libraries or model weights. The exact method AST hashes are checked by `verify.py`, and the portable run reproduces all original property outcomes. Two comments clarify record-processing wording without changing executable AST. An optional NLI module outside this replay is omitted. These differences are documented in [PORTABILITY.md](PORTABILITY.md).

The input-revision design reference and independent implementation are credited in [ATTRIBUTION.md](ATTRIBUTION.md). The next distinct question is whether actual model responses declare useful input relationships and reconsider the scientific question correctly after a goal change. This package establishes the publication guard's behavior; that research-quality question requires an appropriate product-level experiment.
