"""Lossless pharmacology observations; binding and curated action stay distinct.

This adapter does not rank therapies, infer efficacy, or fill missing assay conditions.
Raw GtoPdb records and exact field locators remain available for source review.
"""
from copy import deepcopy


def interaction_evidence(rows, *, target_id, species, source_url):
    if not isinstance(rows, list):
        raise ValueError("An unverified response is not zero interactions.")
    records, seen = [], set()
    for index, row in enumerate(rows):
        if (not isinstance(row, dict) or type(row.get("interactionId")) is not int
                or row["interactionId"] in seen or row.get("targetId") != target_id
                or row.get("targetSpecies") != species
                or type(row.get("ligandId")) is not int or not row.get("ligandName")):
            raise ValueError("Interaction identity, query scope or uniqueness is unverified.")
        seen.add(row["interactionId"])
        refs = row.get("refs")
        if not isinstance(refs, list) or not all(isinstance(r, dict) and type(r.get("referenceId")) is int for r in refs):
            raise ValueError("Reference structure is unverified; preserve raw response for inspection.")
        parameter = row.get("affinityParameter")
        if parameter in {"pKi", "pKd", "Ki", "Kd"}:
            measurement_kind = "binding_affinity"
        elif parameter in {"pIC50", "IC50", "pEC50", "EC50", "pA2", "pKB"}:
            measurement_kind = "potency_or_antagonism_assay_context_required"
        else:
            measurement_kind = "unclassified"
        action = row.get("action")
        known_action = isinstance(action, str) and action.strip().casefold() not in {"", "none", "unknown", "not determined"}
        missing = [field for field in ("assayDescription", "assayConditions") if not row.get(field)]
        records.append({
            "interaction_id": row["interactionId"], "target_id": target_id,
            "ligand_id": row["ligandId"], "ligand_name": row["ligandName"],
            "target_species": species,
            "curated_action": {"type": row.get("type"), "action": action,
                               "status": "reported" if known_action else "unresolved"},
            "measurement": {"kind": measurement_kind, "parameter": parameter,
                            "value_as_reported": row.get("affinity"),
                            "original_value_as_reported": row.get("originalAffinity"),
                            "original_type": row.get("originalAffinityType"),
                            "original_relation": row.get("originalAffinityRelation")},
            "missing_condition_fields": missing,
            "source_url": source_url,
            "original_record_locator": f"$[{index}]",
            "action_locator": f"$[{index}].action",
            "measurement_locator": f"$[{index}].affinity",
            "reference_ids": [r["referenceId"] for r in refs],
            "pmids": [r["pmid"] for r in refs if r.get("pmid")],
            "raw_record": deepcopy(row),
            "interpretation": "Curated action and reported measurement are separate observations. Human target species is not evidence of a human clinical study. Missing assay details remain unknown; reference/ChEMBL overlap needs review. No efficacy or exposure conclusion.",
        })
    return {"status": "OBSERVATIONS_NORMALIZED", "target_id": target_id, "species_filter": species,
            "records": records, "record_count": len(records), "full_returned_pool_preserved": True,
            "unqueried_scope": "Other species, targets, later database changes and evidence outside GtoPdb remain unsearched.",
            "source_attribution": "IUPHAR/BPS Guide to PHARMACOLOGY", "therapeutic_ranking_performed": False}
