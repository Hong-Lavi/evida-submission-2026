# Package review status

**Terminal results included; no additional model fitting during packaging.**

Both experiments are retained: all 30 frozen-feature fits and their negative primary result, plus all 60 neural task/arm completions with zero failures/skips, raw lightweight predictions, receipts, fit metadata, logs and metrics. The original freezes, pretraining amendment and preserved synthetic failure are retained separately from benchmark outcomes. Large weights, embeddings and checkpoints are excluded; their source pins or individual hashes remain.

The seven core fitting/scoring files are unchanged EVIDA code/adapters; CheMeleon author reference files and MIT notice are separately attributed. The package retains MoleculeACE provenance and its MIT notice, with explicit ChEMBL data Attribution-ShareAlike terms. It does not grant software MIT terms to underlying database content.

The original frozen-feature scorer, original neural scorer and independent neural arithmetic can all be rerun offline. A separate exploratory post-score policy contrast is labelled as such. Root original results and comparison definitions are unchanged. `verification/` contains completed reproducibility checks; `provenance/pre-terminal-package-manifest.json` preserves the earlier package snapshot identities.

The full-data independent pre-score gate verified 60/60 records without opening test gold; independent post-score calculations match all task metrics and paired intervals. The current RF/GP policy remains the default recommendation; no automatic GPU-dependent adoption follows from an unclear GP advantage.

No full portable refit was performed in packaging. Direct dependency pins are not a complete transitive lock; exact repeat training may depend on hardware/runtime behavior. Benchmark reuse, one neural seed and unresolved pretraining-structure overlap limit scientific generalization. Public repository upload and release are managed separately by the coordinator.
