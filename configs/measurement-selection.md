# Native measurement-selection contract

Use freeze_measurement_selection after staging and receiving the relevant reassessment drafts. Read primary conditions; preserve source observations separately from proposed extensions. The general kernel does not pick a biological protocol. Set source/design readiness to false when physical confirmation or precision is still needed. Engine2 IDs are exact draft.subject and revision is draft.content_hash; source_ref points to the draft's /content. Return the resulting artifact ID in the external check measurement_selection_id and include consumed drafts in final reassessment_review_ids. Keep intent records unchanged after these reviews. For checks with no plan use measurement_selection_id=null.

**Source refs convention:** kernel refs are exact `{artifact_id, sha256, json_pointer}`. Native user arguments may use `{artifact_id,json_pointer}`; the wrapper resolves the actual artifact/body, adds its actual SHA256 and validates pointer identity. Empty ref lists are preserved as unknown/unready, never source authority. The kernel does not infer primary-source authority from a string/flag. Model-authored extraction and design choices must be marked by the wrapper's source artifact and handoff `basis` (`source|design|unknown`) and `ready` review flag.

Plan spec, all fields required except explicitly marked optional:

```text
schema_version: 1
purpose: assay_calibration | ranking_evaluation | explanation_discrimination
context: {id, revision, required_fields: [field names], values: {field:value}, field_refs: {field:[Ref]}}
  required_fields must include target_id, endpoint, units, matrix, construct,
  measurement_mechanism, concentration, time; add species/variant/reporter/temp/etc where relevant.
  Null/empty/missing = unknown. Explicit N/A can be {not_applicable:true,reason:"..."}.
candidates: [
 {id, structure_id, parent_group_id, origin: original|generated, parent_candidate_id: null|id,
  identity_refs:[Ref], material:{id:null|id,ready:bool,identity_verified:bool,source_refs:[Ref]},
  measurement_context:{values,field_refs}, observations:[Observation]}
]
  Missing physical lot/material/access keeps a planned candidate with a hold.
  Historical parent labels cannot become generated-child observations. No structure normalization in kernel.
arms: exactly two, array order defines left/right contrast
 {id,kind:prediction,reason,source_refs:[Ref],scores:{every_eligible_pool_id:finite_number},prediction_context:{values,field_refs}}
 OR {id,kind:source_evidence,reason,source_refs:[Ref],order:[every_eligible_pool_id_once]}
  Prediction scores are ALREADY higher-is-better utilities, not a raw lower-is-better endpoint.
  Score ties resolve by candidate ID; evidence order is explicit. Incompatible prediction => unavailable, no refill.
budget: {B:positive_integer,maximum_cost:nonnegative_number,cost_unit:nonempty_string}
cost_items: [{id,kind:measurement|control,candidate_ids:[ids],cost:nonnegative_number,ready:bool,source_refs:[Ref]}]
  Charge each physical item once when any linked union candidate uses it; all controls charged.
  Each union candidate must be covered. Shared candidate/reference items are not charged twice.
  Per-arm B and actual union+controls total are different. All unready cost items gate execution.
utility: {direction:higher|lower,minimum_difference:nonnegative_number,
          bounds:[low,high] OPTIONAL (in signed higher-is-better utility units),top_q:integer OPTIONAL}
inspection_ledger: [caller-supplied history objects], explicit [] permitted
next_check: {
 specimen,controls,readout,precision: {description,basis:source|design|unknown,source_refs:[Ref],ready:bool},
 engine2_refs:[{id:explanation_id,revision:nonempty_string,source_ref:Ref}],
 branches:[{id,kind,condition,action,explanation_ids:[ids],scientific_judgment:hold|review}]
}
  engine2_refs may bind immutable review DRAFT artifacts that are published atomically later.
  branch kinds: valid_improvement,valid_no_improvement,invalid_measurement,insufficient_precision,applicability_unknown.
  Invalid/imprecise branches MUST hold biological judgment; engine does not execute interpretation.
```

`Observation`: `{id,lineage_id,candidate_id,structure_id,material_id,context:{values,field_refs},source_refs:[Ref],observed:bool,valid:bool,precise_enough:bool,relation:'='|'<'|'<='|'>'|'>=',value:finite_decimal,independent_unit_id?:string,inspection_status?:string}`. A missing/invalid value remains ineligible; relation missing/unknown is not exact. One supplied evaluation row per candidate; repeats must be explicitly aggregated upstream with provenance/precision. Same original observation lineage cannot label different candidates. Source/structure/material/context correspondence is checked separately from numeric availability.

`freeze_plan` returns full spec, per-candidate condition/label/readiness reviews, pool_ids, per-arm planned_ids/physically_ready_ids, planned_measurement_union, material_holds, cost and SHA256 seal. Candidate/cost-item source order is normalized. Core planned eligibility = explicit structure refs and no known NEW-context mismatch; unknown context/physical readiness remain visible holds. Historical-label eligibility is independent.

`evaluate` accepts no outcomes (ranking_value_unproven), or `{schema_version:1,plan_seal,inspection_status:held_out_after_seal|retrospective,rows:[Observation]}`. Wrapper alone enforces actual seal-before-label delivery and historical inspection truth. Exact utility contrast: left-minus-right signed sum on differing IDs divided by original B. Shared IDs cancel even without outcomes; identical choices yield zero_by_identical_selection, never ranking improvement. Missing/invalid/censored differing outcomes yield unresolved/identification bounds, never a confidence interval. Bounds are optional preregistered DATA, never invented in engine. Precision flag is supplied source/design evidence, not estimated from n. All comparisons remain finite-pool/assay scoped; no general biological validation.

`handoff` returns `{plan_seal,status:declared_ready|preparation_required,planned_ids,unresolved_gates,next_check,cost,interpretation}`. Required next-check source/design refs, biological branches, material readiness, control/item readiness, frozen arm availability and cost limit are checked. No numerical protocol is chosen. `declared_ready` means caller-verified declared fields, not independent experimental QC approval.


Native-only spec field `prediction_bindings` is required for prediction arms (use {} for source-evidence arms). Map arm ID -> candidate ID -> {score_ref:Ref,candidate_ref:Ref,structure_ref:Ref,direction:higher|lower}. Each ref resolves exact stored computed-artifact data: numeric score, the same candidate ID, the same structure_id. Declared scores must equal the original numeric value (or its sign reversal for lower). The wrapper verifies this, records the bindings and removes this field before the pure kernel. Never type an estimated score from narrative evidence.
