# Prototype P2 revision: interrupted worker artifacts

The independent review reproduced a truncated JSON file stopping the whole runner before any task receipt or final selection seal. This revision changes only recovery and preparation bookkeeping; methods, seeds, draws, batch sizes, original metric parity, tie rules, fallback definition, and scientific comparisons stay fixed.

`run_selection.py` now accepts each baseline/seed artifact only when the complete JSON and its row contract are valid. Missing, truncated, duplicate, foreign, wrongly scoped, or structurally invalid artifacts fail only their declared row group. Their original bytes remain untouched and hashed. Already valid artifacts retain their completed rows. Each affected row records the original worker exit/timeout, when present, together with its artifact error. Task receipts retain `worker_failure` and structured `artifact_errors`, including original SHA and affected row keys. Every planned task continues with no retry.

This exception handling does not cover source/input integrity failures. All source and input pins are checked before each worker and again after it exits; a changed pin aborts without a seal. The final integrity checks are also retained.

`test_runner_recovery.py` runs real synthetic subprocesses: one dies by SIGKILL while writing baseline JSON; another dies while writing the first posterior seed JSON. Further workers return duplicate IDs, an extra NaN field, a top-level object instead of a list, or a missing required field. Remaining tasks succeed. The full run still has 30 launches, 30 terminal tasks, and 3,600 planned rows: 3,372 completed and 228 explicitly failed. The scorer's complete gate accepts the sealed ledger, zero gold files are read, and the truncated original bytes remain exactly preserved. Separate source- and input-mutation subprocesses both abort immediately with only one worker launched and no seal.

Observed final artifacts:

- `final-tests.stderr`: all 18 tests passed in 4.563 seconds.
- `synthetic-killed-yir2elvg/regression-result.json`: full regression result.
- `synthetic-killed-yir2elvg/run-01/selection-seal.json`: SHA `286feba8a5f5dbcaa435a0ddcfbf871d09723bd788c0c34d4ed90c56311cb321`.
- The prior prototype sources/draft/handoff/receipt remain in `prior/`. Earlier synthetic attempts remain separate; none was overwritten.

`prepare_protocol.py --refresh-draft revision-02` preserves the old draft and refreshes own source and regression-artifact pins. It verifies existing candidate input byte hashes but does not parse real NPZ/prediction/feature values, select real candidates, or read gold. `draft-refresh-receipt.json` records both draft hashes. No protocol freeze or actual replay is authorized by this revision.
