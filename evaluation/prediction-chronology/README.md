# Prediction chronology: a six-case component comparison

All three arms passed all six prespecified chronology cases. This comparison found no primary-score advantage for either product instruction set over a direct GPT-6 Astra response. It exposes one structured-field ambiguity worth testing further; it does not establish biological correctness or performance on a broader population.

This package tests whether a scientific review distinguishes a prediction made before an assigned measurement from an explanation written after its result. Reading a published study does not make every future proposed measurement retrospective. Conversely, an old document created after a result does not become prospective merely because it predates the current review.

## Design

Six fixed synthetic chronology scenarios share a paper-derived 20-row nerandomilast source packet. The paper observations are real source material; the timing, assigned-check IDs, history events, and intervention outcomes stipulated by the scenarios are synthetic. P4 and P5 include immutable synthetic prior-record fixtures. None of these scenarios represents a newly performed biological experiment.

| Case | Assigned measurement history |
|---|---|
| P1 | New intervention proposed after reading literature |
| P2 | Assigned result already seen before the current statement |
| P3 | New replication after reading the original study |
| P4 | Actual fixture prediction record precedes the assigned result |
| P5 | Earlier fixture document was itself written after the result |
| P6 | Timing remains unresolved and no prior record is available |

Each arm received the same case facts, reference hypotheses/check, source values, and prior-history fixtures. Each had one GPT-6 Astra response at max effort, without browsing, scientific tool calls, correction turns, or automatic retry. The six-case denominator is retained for every arm. The original challenge file's four-response ceiling was narrowed to one by the frozen component protocol before responses; no additional answers were selected. Mediator cases D1–D4 remain in the original challenge specification but were not run in this component comparison.

The direct-model arm uses minimal scientific guidance and prose. The two product arms use their complete planner instructions and existing `hypothesis_review` plus nullable `judgment_context` schemas. Their difference is chronology wording and schema descriptions. These are component requests, not full Runner sessions, intent/finalization checks, or end-to-end product evaluations. Plain-versus-product also changes instruction amount and output-format burden.

An independent delegated reviewer froze interpretation before reading the answers and sealed all manual judgments before unblinding the arm mapping. Output form makes blinding partial. The judgments are not automated semantic grades. Every judgment and quoted rationale is included.

## Complete results

| Arm (recorded identifier) | Primary cases passed | Criteria passed | Native JSON schema |
|---|---:|---:|---:|
| Direct Astra (`plain_astra`) | 6/6 | 18/18 | Not applicable: 6 prose answers |
| Product reference (`frozen_f1_02`) | 6/6 | 18/18 | 6/6 valid |
| Product chronology wording (`chronology_corrected`) | 6/6 | 18/18 | 6/6 valid |

All 18 responses have accepted GPT-6 Astra identity receipts. The 12/12 schema result is format compliance, separate from the scientific criteria. The public offline verifier reproduces the arithmetic over sealed judgments, verifies 99 exact judgment quotations, and checks identity receipts and schemas. It does not repeat the reviewer's scientific reasoning or independently certify provider identity beyond the retained receipts.

Before the successful execution, two setup attempts each failed for all 18 jobs: local CLI initialization on a read-only filesystem, then stale path-bound indexed-input metadata. Neither produced an observed model response. All 36 original failure receipts remain separate from the 18-response scientific denominator. The initial adapter counter of 18 counts local invocations, not returned model answers. Successful execution used regenerated path metadata, with the scientific payload, order, model, task, schemas, and single-response budget unchanged.

### Detailed result: B09

B09 is the reference product arm on P6. Its single origin field says `reconstructed_after_result`, while its narrative explicitly leaves the assigned measurement's timing unresolved. The frozen rubric permits an unresolved-context route, so its primary pass is preserved. This is a machine-readable ambiguity, not a retroactively assigned failure. B16, the chronology-wording arm on the same case, leaves the assigned prediction list empty and marks the check unresolved. One contrast within six selected cases is not evidence of general superiority. See the unchanged [judgment](records/independent-review/judgments/B09-judgment-01.json) and [complete comparison](records/unblinded-comparison.json).

## Reproduce the public checks

Requires Python 3.10+ and the dependencies in `requirements.txt`. The checks were exercised with Python 3.13.9 and JSON Schema 4.25.0; they run on CPU and make no network or model calls.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python verify.py
```

Installing dependencies may use the network; running `verify.py` does not. Public files suffice for the 18-answer denominator, manual-score arithmetic, exact answer/quote hashes, rubric and judgment seals, schema checks, model receipts, and original setup accounting. Historical seals bind original bytes; `export-manifest.json` also records hashes of redacted public files.

The paper-derived source packet is deliberately excluded because rights to redistribute its translated/adapted extraction are not established under the paper's CC BY-NC-ND 4.0 license. [Source rights and reconstruction](SOURCE_RIGHTS.md) lists the paper, source locators, row hashes, and the exact-input limitation. Without that packet the public verifier reports source-anchor checks as **not run**, not passed.

If a lawful local copy of the original packet is available:

```bash
.venv/bin/python verify.py --source-packet /local/path/frozen-source.json
.venv/bin/python prepare_requests.py --source-packet /local/path/frozen-source.json --out /local/new-directory
```

These commands verify 225 exact source-anchor occurrences and restore all 18 original requests byte for byte. Anchor checks establish string/path integrity, not scientific support or completeness. The included local-source verification receipt records that this was exercised by the package author; a public-only rerun cannot independently reproduce it. Request preparation makes no model calls. See [execution semantics](REPRODUCING.md) for transport, runtime pins, and the limits of a fresh response comparison.

## What is included and what comes next

`records/` contains all 18 raw answers, visible cases, exact response contracts and instructions, parsed scientific records, identity receipts, rubric, manual reviews and seals, original execution drivers, and separate setup attempts. `export_package.py` is the explicit allowlisted transform; `export-manifest.json` records every transformed locator and original hash. Raw provider logs, account/session identifiers, indexed context dumps, and source-packet bodies are excluded. Scientific answer and judgment strings are unchanged.

A useful next assessment would introduce more independently designed measurement histories, multiple runs, and conflicting or incomplete experimental records, with criteria frozen before responses. It should measure mistaken prospective credit and useful handling of unresolved timing. These six selected development cases support only the component result reported here.
