# Independent after-fix verification

**PASS: the reproduced P2 truncated-output failure is resolved in the reviewed revision.** No additional blocker was found for freezing this draft. This is synthetic failure-handling and integrity evidence, not real-pool acquisition performance or prospective validation.

Draft SHA: `c8c2c85bbc4537bb7aed43e94a76d35791419d668c49b6b48b36e546fe6e35e7`.
Runner SHA: `b476399f7a8a92591f89cdbbac6d95dd8cbb469f0c856e25842422264932baff`.
The original `independent_checks.py`, `independent-result.json`, and `REVIEW.md` remain unchanged. Their original reproduction is retained rather than rewritten into a passing result.

## Same-trigger independent replay

`after_fix_check.py` repeats the original first-worker stimulus: write the same truncated bytes `[{"task":` and return exit -9. The revised collector needs the synthetic packet's `selected_policy_arm`, so the fixture explicitly supplies `gp`; this does not alter the failure trigger. A second worker supplies valid synthetic records to test continuation.

Observed: two worker launches, two terminal receipts, all 240 planned rows retained, 120 completed and 120 failed, with 60 posterior-method fallback rows separately populated. The original truncated bytes and SHA are preserved in the receipt. All failed rows identify their invalid/missing artifacts. The independent call to the real scorer's structural gate passes. No gold is supplied or opened.

`run_selection.py:45–88` now accepts a complete valid worker artifact or records its failure scope without repairing its bytes. Parent orchestration continues through `collect_worker_rows` and `complete_rows` at lines 118–120. Source/input pin violations remain fatal before/after each worker, rather than being misclassified as acquisition failures. The recovery regression explicitly exercises SIGKILL while writing baseline and posterior JSON, plus malformed rows, and checks that source/input changes stay fail-closed.

## Why input pins grew from 176 to 1,482

The original 176 pin entries and hashes are unchanged. Every one of the 1,306 additions is under `acquisition-01/revision-02/`:

| Preserved evidence | Added files |
|---|---:|
| Three 30-task killed-worker synthetic runs, 357 each | 1,071 |
| Six source/input-mutation synthetic runs, 37 each | 222 |
| Prior source/draft copies and test logs | 13 |
| Total | 1,306 |

All 1,306 added hashes and all 11 current source hashes were independently checked. No future actual `acquisition-01/run-01/` outputs are pinned. No `test-gold` or `evaluation-only` files are pinned. Synthetic directories contain their own historical `run-01/` outputs; these are immutable regression evidence and do not overlap the future actual run directory. The unchanged original 176 entries were compared as metadata, without parsing actual candidate data.

All three authored killed-worker seals and their per-task artifact hashes were independently verified: each contains 30 terminal tasks and 3,600 rows. Two earlier fixtures have 3,408 completed/192 failed rows; the latest expanded six-fault fixture has 3,372 completed/228 failed. These are preserved different regression fixtures, not inconsistent scientific denominators. The review harness initially assumed the newest fault count for all three historical fixtures; that reviewer assertion was corrected and recorded separately in `after-fix-review-attempt-01.json`, without treating it as a product failure.

Machine-readable evidence: `after-fix-result.json`. No actual candidate input or posterior values were parsed, no real selection/scoring was run, and no gold, model, network, or GPU calls occurred. Only this review directory was written.
