# Reported concentration contrast

`compare_reported_activity_pairs` compares two saved concentration measurements for the same source compound record. It helps a researcher read the reported difference between an explicitly named reference target and comparator target, with the original measurements and assay conditions beside it. The result is a `reported_activity_comparison` artifact with semantic type `source_record_activity_contrast`.

The request contains `reference_target_id`, `comparator_target_id`, one endpoint, a reason, and 1–60 explicit pairs. Each side names an `artifact_id` and `json_pointer`; the server retrieves the numbers, structures and source hashes. Supported paths are a `bioactivities` row, an activity within `compound_candidates`, or a parent’s reported measurement within `proposal_qualification`. Qualification links resolve back to the original artifact and verify its SHA and measurement copy. The current source adapter supports ChEMBL records and accepts any explicitly named target pair.

Both records must share the source namespace, document, source `record_id`, molecule identity and canonical isomeric structure. RDKit preserves stereochemistry without salt stripping, neutralization or tautomer merging. Original strings and separate source records remain available. Repeated or ambiguous measurements are held for review. Source-record correspondence establishes a document-level pairing; physical samples, batches and replicates require their own evidence.

The calculation is:

- `ratio = comparator concentration / reference concentration`
- `log10_ratio = log10(ratio)`

Both sides must report the same endpoint: IC50, Ki, Kd or EC50. Supported molar units are pM, nM, uM/µM/μM, mM and M. Exact values produce points; `<`, `<=`, `>`, and `>=` produce arithmetic bounds with the original open or closed endpoints. A ratio interval containing 1 leaves strict direction unresolved. Missing measurements, unsupported quantities, invalid source flags and identity conflicts remain unresolved. These bounds describe reported censoring, rather than statistical confidence. Unit conversion preserves up to 50 significant source digits exactly; calculations use 120-digit decimal precision. Decimal strings accompany numeric display fields.

Known incompatible conditions hold the contrast. Unreported conditions remain unknown. Where an `assay_response` is retained, its assay object must match the enriched row’s condition copy. A copy without that original response remains readable with `unverified_copy` status and contributes no confirmed condition match. Matching reported fields still leaves complete protocol and construct comparability for review. Results retain both raw records, source and row hashes, the resolved qualification path, assay-condition authority and calculation provenance.

Validation covers 20 focused tests, including source-condition authority and precision boundaries. A preserved development dataset contains 221 pairs in 219 groups; all 221 exact contrasts passed separate arithmetic checks. One preselected, largest-coverage document/assay group of 42 pairs also passed the native Runner → worker → Store → reader path. Those 42 are a subset of the 221. The 221-pair check covers arithmetic; the native check also verifies binding to the retained assay response. Native results preserve the same original values, numeric contrasts, directions and unresolved conditions, while recording condition authority and fuller decimal strings. These are implementation and development replay checks.

Researchers can use the saved result in the existing science-review workflow, inspect both source rows, and choose a follow-up measurement under stated assay conditions. Reported concentration contrast supplies that comparison; biological selectivity and efficacy require further evidence.
