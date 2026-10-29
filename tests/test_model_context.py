"""Model data encoding must preserve scientific values, missingness and relationships."""
import json
import unittest

from evida.model_context import artifact_overview, model_json, next_model_context, pack, select_columns, unpack


class ModelContextTests(unittest.TestCase):
    def test_context_keeps_original_intent_latest_complete_tool_pair_and_retrieval(self):
        context = {"ORIGINAL_MESSAGES": [{"body": {"text": "retain alternatives, units unknown"}}],
                   "RELEVANT_EVIDENCE": [{"artifact_id": "source1"}, {"artifact_id": "old-reading"}],
                   "CURRENT_RESEARCH_NOTES": {"findings": [{"text": "uncertain", "source_ids": ["source1"]}]}}
        outputs = [{"type": "reasoning", "id": "opaque-id", "encrypted_content": "test-opaque", "summary": []},
                   {"type": "function_call", "name": "inspect_artifact", "call_id": "call-2", "arguments": "{}"},
                   {"type": "message", "role": "assistant", "phase": "commentary", "content": []}]
        tool = [{"type": "function_call_output", "call_id": "call-2", "output": '{"value":null}'}]
        request = next_model_context(context, outputs, tool)
        self.assertEqual(unpack(json.loads(request[0]["content"])), context)
        self.assertEqual(request[1:], outputs + tool)

    def test_column_projection_preserves_all_rows_missing_paths_null_zero_and_identity(self):
        import copy
        view = {"artifact_id": "source", "meta": {"unit": "unknown"}, "result": {"contrast": "shared-control",
                "rows": [{"candidate_id": "duplicate", "values": {"x": 0}},
                         {"candidate_id": "duplicate", "values": {"x": None}},
                         {"candidate_id": "third", "values": {"y": 3}}], "total_rows": 3}}
        original = copy.deepcopy(view)
        result = select_columns(view, [["values", "x"]])
        self.assertEqual(view, original)
        cells = [r["cells"][0] for r in result["result"]["rows"]]
        self.assertEqual(cells, [{"present": True, "value": 0}, {"present": True, "value": None}, {"present": False, "value": None}])
        self.assertEqual([r["identity"]["candidate_id"] for r in result["result"]["rows"]], ["duplicate", "duplicate", "third"])
        self.assertEqual(result["result"]["contrast"], "shared-control")
        self.assertEqual(result["meta"], {"unit": "unknown"})

    def test_scientific_rows_roundtrip_without_rounding_or_losing_missingness(self):
        value = {"artifact_id": "art_test", "contrast": {"control": ["mock1", "mock2"], "fit_verified": False},
                 "units": {"effect": "reported original unit"}, "rows": [
                     {"id": str(i), "raw": {"p": "1.611e-204", "se": "NA"},
                      "values": {"p": 1.611e-204, "se": None, "effect": 0 if i == 0 else -8.4474},
                      "states": {"p": "valid", "se": "missing"}}
                     for i in range(20)]}
        encoded = model_json(value)
        self.assertEqual(unpack(json.loads(encoded)), value)
        self.assertIn("evida-columns-v1", encoded)
        self.assertLess(len(encoded), len(json.dumps(value)))

    def test_missing_key_is_not_converted_to_null(self):
        value = [{"id": "missing"}, {"id": "null", "prediction": None},
                 {"id": "zero", "prediction": 0}, {"id": "blank", "prediction": ""}]
        self.assertEqual(unpack(pack(value)), value)

    def test_different_nested_shapes_and_empty_objects_are_preserved(self):
        value = [{"id": "a", "result": {}}, {"id": "b", "result": {"value": None}},
                 {"id": "c", "result": None}]
        self.assertEqual(unpack(pack(value)), value)

    def test_array_order_duplicates_and_unusual_column_names_are_preserved(self):
        rows = [{"gene.id": "duplicate", "a/b": {"group": ["s1", "s1"], "": []}} for _ in range(20)]
        self.assertEqual(unpack(pack(rows)), rows)

    def test_source_object_using_encoding_markers_is_not_misread_as_a_table(self):
        value = {"table_format": "evida-columns-v1", "columns": [["x"]], "rows": [[4]]}
        self.assertEqual(unpack(pack(value)), value)

    def test_source_catalog_keeps_uncertain_relationships_and_retrieval_identity(self):
        contrast = {"shared_controls": ["mock1", "mock2"], "fit_membership_verified": False}
        artifact = {"id": "art_test", "title": "observations", "kind": "rna_observations",
                    "sha256": "source-hash", "meta": {"source": "public source"},
                    "media_type": "application/json", "content": json.dumps({
                        "contrast": contrast, "limits": ["not independent replications"],
                        "summary": {"missing_padj": 1}, "rows": [{"padj": None}]}).encode()}
        view = artifact_overview(artifact)
        self.assertEqual(view["artifact_id"], "art_test")
        self.assertEqual(view["sha256"], "source-hash")
        self.assertEqual(view["summary_view"]["contrast"], contrast)
        self.assertFalse(view["rows_loaded"])
        self.assertEqual(view["total_rows"], 1)
        self.assertNotIn("rows", view["summary_view"])
        self.assertIn("rows", view["available_result_fields"])


if __name__ == "__main__":
    unittest.main()
