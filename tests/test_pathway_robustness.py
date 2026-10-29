from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from evida.pathway_robustness import compare_artifacts, compare_saved_pathways
from evida.store import Store


def case(*, complete_inputs=True, status="succeeded", node_state=1, root_state=1):
    value = {
        "status": status, "semantic_type": "conditional_pathway_hypotheses",
        "selected_inferred_observations": [{"source": "TF", "score": 2.0, "resource": "synthetic"}],
        "author_result": {
            "sifAll": [[{"Node1": "UP", "Sign": 1, "Node2": "TF"},
                        {"Node1": "Perturbation", "Sign": root_state, "Node2": "UP"}]],
            "attributesAll": [[{"Nodes": "UP", "Activity": node_state}, {"Nodes": "TF", "Activity": 1},
                               {"Nodes": "Perturbation", "Activity": root_state}]],
        },
        "solver_review": {"optimal_reported": status == "succeeded", "objective_value": 1.0},
    }
    if complete_inputs:
        value["comparison_inputs"] = {
            "network": [{"source": "UP", "interaction": 1, "target": "TF"},
                        {"source": "ALT", "interaction": -1, "target": "TF"}],
            "measurements": [{"source": "TF", "score": 2.0}],
            "regulon": {"name": "synthetic", "sha256": "1" * 64},
            "dataset": {"sha256": "2" * 64},
            "engine": {"R": "4.4.3", "CARNIVAL": "2.16.0", "cbc_sha256": "3" * 64,
                       "CARNIVAL_rdb_sha256": "4" * 64},
            "solver_options": {"solver": "cbc", "betaWeight": .2, "poolrelGap": .0001,
                               "timelimit": 120, "threads": 1, "workdir": "/test/one"},
        }
    return value


def artifact(aid, content):
    raw = json.dumps(content, ensure_ascii=False, allow_nan=False).encode()
    return {"id": aid, "kind": "pathway_hypotheses", "sha256": hashlib.sha256(raw).hexdigest(),
            "content": raw.decode()}


class PathwayRobustnessTests(unittest.TestCase):
    def test_root_gauge_changes_are_not_biological_differences_or_probabilities(self):
        result = compare_artifacts([artifact("a", case()), artifact("b", case(root_state=-1))])
        pair = result["pairwise"][0]
        self.assertEqual(pair["comparison_kind"], "same_recorded_settings")
        self.assertEqual(result["summary"]["conserved_signed_nodes"], 2)
        self.assertEqual(result["summary"]["conserved_nodes_not_selected_as_input"], 1)
        self.assertEqual(result["summary"]["conserved_signed_edges"], 1)
        self.assertNotIn("Perturbation", [r.get("node") for r in result["rows"]])
        self.assertTrue(pair["objective_comparison"]["equal_recorded_value"])
        self.assertFalse(result["summary"]["unique_optimum_established"])
        self.assertFalse(result["summary"]["probability_estimation_performed"])

    def test_missing_or_incomplete_attributes_preserve_edges_but_not_false_node_nonselection(self):
        for missing in [True, False]:
            with self.subTest(missing=missing):
                b = case()
                if missing:
                    b["author_result"].pop("attributesAll")
                else:
                    b["author_result"]["attributesAll"][0] = [{"Nodes": "TF", "Activity": 1}]
                result = compare_artifacts([artifact("a", case()), artifact("b", b)])
                pair = result["pairwise"][0]
                self.assertEqual(pair["output_comparison_status"], "partial")
                self.assertEqual(pair["node_comparison_status"], "unassessed")
                self.assertEqual(pair["edge_comparison_status"], "complete")
                self.assertEqual(pair["left_only_nodes"], [])
                self.assertEqual(result["summary"]["conserved_signed_edges"], 1)
                self.assertEqual(result["summary"]["conserved_signed_nodes"], 0)
                up = next(r for r in result["rows"] if r.get("node") == "UP")
                self.assertEqual(up["states"][1]["status"], "unassessed")

    def test_changed_prior_distinguishes_unselected_from_outside_scope(self):
        a, b = case(), case()
        b["author_result"]["sifAll"][0][0] = {"Node1": "ALT", "Sign": -1, "Node2": "TF"}
        b["author_result"]["attributesAll"][0][0] = {"Nodes": "ALT", "Activity": -1}
        b["comparison_inputs"]["network"] = b["comparison_inputs"]["network"][1:]
        result = compare_artifacts([artifact("a", a), artifact("b", b)])
        self.assertEqual(result["pairwise"][0]["comparison_kind"], "changed_prior")
        rows = {r["node"]: r for r in result["rows"] if r["record_type"] == "node"}
        self.assertEqual(rows["UP"]["states"][1]["status"], "outside_search_scope")
        self.assertEqual(rows["ALT"]["states"][0]["status"], "not_selected")
        self.assertEqual(result["summary"]["conserved_signed_nodes"], 1)

    def test_native_counts_and_full_prior_hash_do_not_prove_selected_prior_identity(self):
        a, b = case(complete_inputs=False), case(complete_inputs=False)
        for value in (a, b):
            value["resource_fingerprint"] = {"files": {"prior": "9" * 64}}
            value["search_scope"] = {"selected_prior_edges": 1276, "ancestor_steps": 2}
            value["solver_review"].pop("objective_value")
        result = compare_artifacts([artifact("a", a), artifact("b", b)])
        pair = result["pairwise"][0]
        self.assertEqual(pair["axes"]["prior_signed_edges"]["status"], "unknown")
        self.assertEqual(pair["axes"]["solver_options"]["status"], "unknown")
        self.assertIsNone(pair["objective_comparison"]["equal_recorded_value"])
        self.assertEqual(pair["comparison_kind"], "unresolved_settings")

    def test_exact_scores_resource_and_sign_change_stay_separate(self):
        a, b = case(), case(node_state=-1)
        b["comparison_inputs"]["measurements"][0]["score"] = -2.5
        b["selected_inferred_observations"][0]["score"] = -2.5
        b["comparison_inputs"]["regulon"] = {"name": "other", "sha256": "5" * 64}
        result = compare_artifacts([artifact("a", a), artifact("b", b)])
        pair = result["pairwise"][0]
        self.assertEqual(pair["axes"]["selected_tf_ids"]["status"], "same")
        self.assertEqual(pair["axes"]["selected_tf_scores"]["status"], "different")
        self.assertEqual(pair["axes"]["selected_tf_signs"]["status"], "different")
        self.assertEqual(pair["comparison_kind"], "multiple_axes_changed")
        self.assertEqual(pair["different_signed_nodes"], [{"node": "UP", "left_state": 1, "right_state": -1}])

    def test_failed_and_partial_runs_do_not_turn_into_negative_evidence_or_conservation(self):
        failure = case(status="failed")
        failure.pop("author_result")
        result = compare_artifacts([artifact("ok", case()), artifact("partial", case(status="partial")),
                                    artifact("failed", failure)])
        self.assertEqual(result["summary"]["run_status_counts"]["failed"], 1)
        self.assertEqual(result["summary"]["conserved_signed_nodes"], 0)
        self.assertEqual(result["summary"]["conserved_signed_edges"], 0)
        self.assertEqual(result["pairwise"][0]["output_comparison_status"], "partial")
        self.assertEqual(result["pairwise"][1]["output_comparison_status"], "unassessed")
        self.assertTrue(all(r["states"][2]["status"] == "unassessed" for r in result["rows"]))

    def test_solver_only_requires_all_invariant_inputs_and_ignores_output_locations(self):
        a, b = case(), case()
        b["comparison_inputs"]["solver_options"]["workdir"] = "/test/two"
        result = compare_artifacts([artifact("a", a), artifact("b", b)])
        self.assertEqual(result["pairwise"][0]["comparison_kind"], "same_recorded_settings")
        b["comparison_inputs"]["solver_options"]["timelimit"] = 600
        result = compare_artifacts([artifact("a", a), artifact("b", b)])
        self.assertEqual(result["pairwise"][0]["comparison_kind"], "solver_only")
        b["comparison_inputs"].pop("network")
        result = compare_artifacts([artifact("a", a), artifact("b", b)])
        self.assertEqual(result["pairwise"][0]["comparison_kind"], "solver_change_with_unresolved_axes")

    def test_partial_or_inconsistent_input_records_remain_unknown(self):
        a, b = case(), case()
        b["comparison_inputs"]["solver_options"] = {"betaWeight": .2}
        b["comparison_inputs"]["measurements"][0]["score"] = 9
        b["comparison_inputs"]["network"] = []
        result = compare_artifacts([artifact("a", a), artifact("b", b)])
        pair = result["pairwise"][0]
        for key in ["solver_options", "selected_tf_scores", "prior_signed_edges"]:
            self.assertEqual(pair["axes"][key]["status"], "unknown")
        self.assertIn("returned_edges_outside_recorded_prior", result["runs"][1]["input_issues"])

    def test_all_returned_solutions_are_retained_without_treating_them_as_replicates(self):
        a = case()
        a["author_result"]["sifAll"].append(deepcopy(a["author_result"]["sifAll"][0]))
        attrs = deepcopy(a["author_result"]["attributesAll"][0]); attrs[0]["Activity"] = -1
        a["author_result"]["attributesAll"].append(attrs)
        result = compare_artifacts([artifact("a", a), artifact("b", case())])
        self.assertEqual(len(result["runs"]), 3)
        self.assertEqual(result["summary"]["input_artifacts"], 2)
        self.assertEqual(result["summary"]["different_signed_nodes"], 1)
        self.assertFalse(result["summary"]["independence_assessed"])

    def test_content_integrity_duplicates_and_workspace_scope_are_enforced(self):
        a, b = artifact("a", case()), artifact("b", case())
        corrupt = {**a, "content": a["content"] + " "}
        with self.assertRaises(ValueError): compare_artifacts([corrupt, b])
        with self.assertRaises(ValueError): compare_artifacts([a, a])
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / "comparison.sqlite3")
            first, second = store.create("first")["id"], store.create("second")["id"]
            aid = store.add_artifact(first, "synthetic", "pathway_hypotheses", a["content"].encode(), {})
            bid = store.add_artifact(second, "synthetic", "pathway_hypotheses", b["content"].encode(), {})
            with self.assertRaises(KeyError): compare_saved_pathways(store, first, [aid, bid])

    def test_worker_checks_original_bytes_without_normalizing_line_endings(self):
        from evida import science
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            entries = []
            for index in range(2):
                value = {**case(), "title": "한글이 포함된 저장 자료"}
                raw = json.dumps(value, indent=2, ensure_ascii=False).replace("\n", "\r\n").encode("utf-8")
                path = root / f"input-{index}.json"
                path.write_bytes(raw)
                entries.append({"id": f"saved-{index}", "kind": "pathway_hypotheses",
                                "sha256": hashlib.sha256(raw).hexdigest(), "path": str(path)})
            request, output = root / "request.json", root / "result.json"
            request.write_text(json.dumps({"tool": "pathway_robustness", "pathway_runs": entries,
                "arguments": {"artifact_ids": [r["id"] for r in entries]},
                "input_path": None, "output_path": str(output)}))
            with patch.object(sys, "argv", ["evida.science", str(request)]):
                science.main()
            result = json.loads(output.read_text())
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["runs"][0]["artifact_sha256"], entries[0]["sha256"])
            # A real staged-file modification must still fail source integrity.
            path = Path(entries[0]["path"])
            path.write_bytes(path.read_bytes() + b" ")
            with patch.object(sys, "argv", ["evida.science", str(request)]):
                science.main()
            self.assertEqual(json.loads(output.read_text())["status"], "failed")


if __name__ == "__main__":
    unittest.main()
