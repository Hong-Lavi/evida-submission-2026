# Synthetic service-response fixtures

The five JSON files in `lens/` and `gtopdb/` are hand-written software test data.
They are **not downloaded API responses**, real publications, biological entities,
assay measurements, clinical results, source-access receipts, or scientific evidence.
Numbers, totals, interaction names and Lens-shaped strings are fictional test inputs.
Lens-shaped strings test parser syntax; no actual assignment/checksum validity is claimed.

The fixtures preserve field retention (including unknown nested fields), both citation
query directions, an X-ending identifier, unresolved citation/page scope, mixed measurement
categories, missing assay conditions, and multiple observations per ligand. Failures,
ambiguous targets, wrong query scope, and successful empty responses are tested separately.

This substitution changes only deterministic offline tests. Live product adapters continue
to retain actual response fields and source attribution. The previous downloaded fixtures
remain in the private source/audit history; do not redistribute them as project-authored code by default.

These fixture texts were newly authored for EVIDA software tests; publication terms follow the repository owner's explicit license decision. Underlying services,
real API responses and any third-party publication material keep their own terms; this note
neither relicenses those sources nor certifies permission for bulk redistribution.
