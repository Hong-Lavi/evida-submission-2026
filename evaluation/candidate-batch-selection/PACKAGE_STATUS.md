# Review-ready public package

Both complete acquisition versions are included and independently recalculated. Every original scientific score, selection and denominator is retained. The primary result supports retaining the current selector; the numerical correction produced no changed selections or scientific scores.

Validated from packaged artifacts:

- All30 source CSVs,9,802 labels,30 posterior NPZ hashes, and complete7200 selection records across both versions.
- All57,600 raw metric values and2,016 paired intervals across both versions, tolerance1e-12.
- Relocated verification and full recomputation, plus rejection of a deliberately corrupted posterior copy.
- All40 archived Python source files byte-identical to original; original function/class AST parity recorded.
- Portable path binding and active protocol-pin verification. A fresh full selection replay was not executed during packaging.

`verification/` contains detailed receipts, data/source license review and privacy checks. `_distribution/manifest.json` records the exact file count, unpacked bytes, zip bytes and zip SHA256. `_distribution/` is a delivery convenience, excluded from the payload seal and zip contents.

No public repository, Git metadata, deployment, model service, or GPU was changed or used by this packaging task. Root must review and publish. The qPO author's unlicensed source/probe are excluded; their historical hashes remain as provenance, not as included implementation. All data attribution and upstream share-alike terms are described in `ATTRIBUTION.md`.
