# Numerical equality correction: selection complete

The corrected latent sampler guarantees bit-identical columns for each quotient equality group. It computes quotient samples once and expands them by lookup, while observation samples still receive independent likelihood noise. This changes one numerical step in `acquisition.py`; all other copied execution/scoring source bodies remain byte-identical to acquisition-01.

The original code, draft, protocol, source pins, selection seal, all30 selection artifacts, and original score are referenced by hashes in `technical-amendment.json`. They remain preserved. All original scientific fields, methods, seeds0–4, 8,192draws, batch sizes, pools, original GP25/RF5 policy, primary/secondary metrics, ties, target-cluster statistics, limits, and no-retry rule were retained.

Before freezing:20 synthetic tests passed, including the BLAS tie counterexample, no-group RNG parity, zero-rank/multiple groups, and observation noise after latent copying. All110 actual equality-group/seed checks became bit-identical, without candidate selection or gold access.

Actual selection: one execution, exit0,30/30 tasks,3,600/3,600 completed rows, no failures or retries. Two CPU threads, one worker at a time, original180-second task limit. Sum of task wall receipts58.86seconds; this is a runtime receipt, not a claimed speed advantage. Original exec session [operational-id-redacted] is complete.

After the complete selection seal, `compare_selections.py` verified both full structural gates and compared all3,600 row identities and `selected_ids`, `fallback_selected_ids`, and `status`. **Zero rows changed.** The comparison explicitly blocked gold and scored-result access. No new scientific metric was computed by this agent; root owns final scoring. This numerical correction does not establish a scientific performance gain.

Pins:

- Protocol: `bddda529e812f64d55538e475b7d1f5b59b8bd00b617a1c0e821fc305ce4d6de`
- Selection seal: `5436cd01c76b13af9a2d88a224b1997e4c10c1d875ca02685a7fd36f94eb6d40`
- Selection comparison: `selection-comparison.json`
- Completion receipt: `execution-handoff-receipt.json`

Root's final scorer remains `score_selection.py` in this directory, using the existing GP CPU interpreter and library path. It performs its full gate before opening gold. No scorer invocation or GitHub package was performed here.
