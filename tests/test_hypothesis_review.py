"""Synthetic prediction sets and real immutable Store records; no biological claims."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import jsonschema

from evida.hypothesis_review import bind_record, check_anchor, prepare, validate, view
from evida.store import Store, dump


def loop_fixture():
    alternatives = [{"id": name, "statement": "Synthetic explanation " + name, "part_ids": [],
                     "conditions": ["Same synthetic conditions"], "relations": []} for name in ("a", "b")]
    alternatives[0]["relations"] = [{"alternative_id": "b", "relation": "exclusive_under_conditions",
                                     "conditions": "The two synthetic model assumptions are mutually exclusive in this fixture."}]
    return {"hypotheses": [{"id": "h1", "statement": "Synthetic causal claim", "expected_observation": "Synthetic outcome",
                            "conditional_alternatives": alternatives}],
            "next_checks": [{"id": "c1", "hypothesis_ids": ["h1"],
                             "possible_outcomes": [{"observation": text, "implication": "Synthetic only"}
                                                   for text in ("High", "Low", "Other")],
                             "outcome_links": [{"outcome_index": 0, "effects": [
                                 {"hypothesis_id": "h1", "alternative_ids": ["a"], "part_ids": [],
                                  "relation": "supports", "rationale": "Synthetic proposed update"}], "followup_check_ids": []}]}],
            "revision_rationale": "Synthetic module trial"}


def prediction(alternative, outcomes, source):
    return {"hypothesis_id": "h1", "alternative_id": alternative, "outcome_indices": outcomes,
            "coverage": "complete", "origin": "prospective", "assumptions": ["Synthetic exact outcomes"],
            "rationale": "Explicit constructed prediction, not empirical evidence", "source_ids": [source]}


def review_fixture(source):
    return {"schema_version": "1", "causal_steps": [{
        "id": "s1", "hypothesis_id": "h1", "part_id": "", "claim": "X changes Y in the synthetic system",
        "target_context": "Synthetic target context; no biological measurements", "missing_assumptions": ["Transfer is untested"],
        "evidence_groups": [{"id": "g1", "anchors": [
            {"artifact_id": source, "path": "/rows/0/result", "quote": "Treatment X changed marker Y."},
            {"artifact_id": source, "path": "/methods", "quote": "Synthetic measurement protocol."}],
            "reported_context": "Synthetic source context", "evidence_role": "intervention",
            "text_support": "supports", "text_support_rationale": "Model-authored interpretation",
            "causal_support": "intervention_response_only", "causal_support_rationale": "Mediator causality untested",
            "applicability": "conditional", "applicability_rationale": "Transfer requires additional assumptions",
            "missing_assumptions": ["Unmeasured confounding"]}]}],
        "observations": [{"check_id": "c1", "validity_requirements": ["Both controls pass their prespecified criteria"],
                          "precision_requirement": "Measurement interval must exclude the other declared outcome category",
                          "outcomes": [{"outcome_index": i, "interpretation": "adequate_measurement"} for i in range(3)],
                          "predictions": [prediction("a", [0], source), prediction("b", [1], source)]}]}


class HypothesisReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "state.db")
        self.wid = self.store.create("Synthetic hypothesis review")['id']
        self.content = dump({"rows": [{"result": "Treatment X changed marker Y.",
                                      "limitation": "Randomization was not reported.",
                                      "a/b": {"~id": "Exact nested quote"}}],
                             "methods": "Synthetic measurement protocol."}).encode()
        self.source = self.store.add_artifact(self.wid, "Synthetic source", "article", self.content, {}, bump=False)
        self.loop = loop_fixture()
        self.review = review_fixture(self.source)

    def tearDown(self):
        self.temp.cleanup()

    def prepared(self, review=None, loop=None):
        return prepare(self.store, self.wid, 1, review or self.review, loop or self.loop)

    def observation(self, review=None, loop=None):
        return self.prepared(review, loop)["value"]["observation_checks"][0]

    def publish(self, records=None, loop=None):
        from evida.finalization import commit
        proposal = {"based_on_state_rev": 1, "intent_records": [], "research_loop": copy.deepcopy(loop or self.loop)}
        return commit(self.store, self.wid, 1, "synthetic-job", proposal,
                      [self.prepared(loop=loop)] if records is None else records, [], None)

    def test_exact_multi_anchor_identity_is_distinct_from_causal_assessment(self):
        before = copy.deepcopy(self.review)
        original = self.store.snapshot(self.wid)
        record = self.prepared()
        group = record["value"]["causal_step_checks"][0]["evidence_groups"][0]
        self.assertTrue(group["all_anchors_verified"])
        self.assertFalse(group["causal_support_automatically_verified"])
        self.assertEqual([a["source_sha256"] for a in group["anchor_checks"]],
                         [self.store.artifact(self.wid, self.source)["sha256"]] * 2)
        self.assertEqual(record["value"]["review"], before)
        self.assertEqual(self.review, before)
        self.assertEqual(self.store.snapshot(self.wid), original)
        self.assertEqual(record["value"]["review"]["causal_steps"][0]["evidence_groups"][0]["causal_support"],
                         "intervention_response_only")

    def test_wrong_path_missing_source_and_counterevidence_are_retained(self):
        r = copy.deepcopy(self.review)
        group = copy.deepcopy(r["causal_steps"][0]["evidence_groups"][0])
        group.update(id="counter", text_support="contradicts", causal_support="not_established")
        group["anchors"] = [
            {"artifact_id": self.source, "path": "/rows/0/limitation", "quote": "Randomization was not reported."},
            {"artifact_id": self.source, "path": "/rows/0/result", "quote": "Randomization was not reported."},
            {"artifact_id": "missing-source", "path": "/rows/0/result", "quote": "Missing quote"}]
        r["causal_steps"][0]["evidence_groups"].append(group)
        result = self.prepared(r)["value"]
        checks = result["causal_step_checks"][0]["evidence_groups"][1]["anchor_checks"]
        self.assertEqual([c["status"] for c in checks], ["verified", "rejected", "rejected"])
        self.assertEqual(checks[1]["reason"], "quote_not_at_exact_path")
        self.assertEqual(checks[2]["reason"], "artifact_not_in_this_research")
        self.assertEqual(result["review"], r)
        self.assertEqual(result["summary"]["failed_anchors"], 2)

    def test_json_pointer_escaping_strict_strings_and_integrity(self):
        anchor = {"artifact_id": self.source, "path": "/rows/0/a~1b/~0id", "quote": "Exact nested quote"}
        self.assertEqual(check_anchor(self.store, self.wid, anchor)["status"], "verified")
        for path, quote, reason in [
            ("/rows/00/result", "Treatment", "path_not_found"),
            ("/rows/-1/result", "Treatment", "path_not_found"),
            ("/rows/0/a~2b", "Treatment", "invalid_json_pointer"),
            ("/rows/0", "Treatment", "anchor_target_not_string"),
            ("/rows/0/result", "Treatment  X", "quote_not_at_exact_path"),
            ("/rows/0/result", "", "empty_quote")]:
            with self.subTest(path=path, quote=quote):
                value = check_anchor(self.store, self.wid, {**anchor, "path": path, "quote": quote})
                self.assertEqual(value["reason"], reason)
        other = self.store.create("Other synthetic workspace")["id"]
        self.assertEqual(check_anchor(self.store, other, anchor)["reason"], "artifact_not_in_this_research")
        with self.store.connect(True) as db:
            db.execute("UPDATE artifacts SET content=? WHERE id=?", (b'{}', self.source))
        self.assertEqual(check_anchor(self.store, self.wid, anchor)["reason"], "stored_content_integrity_failed")

    def test_same_predictions_are_shared_not_discriminating(self):
        r = copy.deepcopy(self.review)
        r["observations"][0]["predictions"][1]["outcome_indices"] = [0]
        result = self.observation(r)
        pair = result["outcomes"][0]["pairs"][0]
        self.assertEqual(pair["status"], "shared")
        self.assertFalse(pair["selection_eligible"])
        self.assertEqual(result["outcome_link_diagnostics"][0]["status"], "compatible_but_not_discriminating")
        self.assertEqual(result["outcomes"][1]["pairs"][0]["status"], "neither_predicted")

    def test_complete_sets_separate_only_the_predicted_and_excluded_pair(self):
        result = self.observation()
        pairs = [o["pairs"][0] for o in result["outcomes"]]
        self.assertEqual([p["status"] for p in pairs], ["separating", "separating", "neither_predicted"])
        self.assertTrue(pairs[0]["selection_eligible"])
        self.assertEqual(pairs[0]["compatible_explanation"]["alternative_id"], "a")
        self.assertEqual(pairs[1]["compatible_explanation"]["alternative_id"], "b")
        self.assertEqual(pairs[0]["excluded_explanation"]["alternative_id"], "b")
        self.assertEqual(result["outcome_link_diagnostics"][0]["status"], "consistent_with_prediction_set")
        self.assertNotIn("probability", dump(result))

    def test_partially_overlapping_complete_sets_have_shared_and_separating_outcomes(self):
        r = copy.deepcopy(self.review)
        r["observations"][0]["predictions"][0]["outcome_indices"] = [0, 1]
        r["observations"][0]["predictions"][1]["outcome_indices"] = [1, 2]
        self.assertEqual([o["pairs"][0]["status"] for o in self.observation(r)["outcomes"]],
                         ["separating", "shared", "separating"])

    def test_missing_partial_and_unknown_predictions_do_not_become_exclusions(self):
        for variant in ("missing", "partial", "unknown"):
            with self.subTest(variant=variant):
                r = copy.deepcopy(self.review)
                if variant == "missing":
                    r["observations"][0]["predictions"].pop()
                else:
                    r["observations"][0]["predictions"][1]["coverage"] = variant
                result = self.observation(r)
                self.assertEqual(result["outcomes"][0]["pairs"][0]["status"], "unresolved")
                self.assertEqual(result["outcomes"][0]["unknown_explanations"],
                                 [{"hypothesis_id": "h1", "alternative_id": "b"}])
                if variant == "missing":
                    self.assertEqual(len(result["missing_explanations"]), 1)
        r = copy.deepcopy(self.review)
        r["observations"][0]["predictions"][1].update(coverage="partial", outcome_indices=[0])
        self.assertEqual(self.observation(r)["outcomes"][0]["pairs"][0]["status"], "shared")

    def test_failure_low_precision_inapplicability_and_undeclared_guards_stay_unresolved(self):
        for interpretation in ("measurement_failure", "insufficient_precision", "not_applicable", None):
            with self.subTest(interpretation=interpretation):
                r = copy.deepcopy(self.review)
                if interpretation is None:
                    r["observations"][0]["outcomes"].pop(0)
                else:
                    r["observations"][0]["outcomes"][0]["interpretation"] = interpretation
                outcome = self.observation(r)["outcomes"][0]
                self.assertEqual(outcome["pairs"][0]["status"], "unresolved")
                self.assertFalse(outcome["pairs"][0]["selection_eligible"])
                self.assertTrue(outcome["guard_reasons"])
                self.assertEqual(outcome["excluded_explanations"], [])
                self.assertEqual(len(outcome["unknown_explanations"]), 2)
        for field, value in (("validity_requirements", []), ("validity_requirements", ["unknown"]),
                             ("precision_requirement", ""), ("precision_requirement", "미확인")):
            r = copy.deepcopy(self.review)
            r["observations"][0][field] = value
            self.assertEqual(self.observation(r)["outcomes"][0]["pairs"][0]["status"], "unresolved")

    def test_coexisting_explanations_require_joint_predictions_without_rejecting_either(self):
        loop = copy.deepcopy(self.loop)
        loop["hypotheses"][0]["conditional_alternatives"][0]["relations"] = [
            {"alternative_id": "b", "relation": "can_coexist", "conditions": "Both can operate together"}]
        result = self.observation(loop=loop)
        pair = result["outcomes"][0]["pairs"][0]
        self.assertEqual(pair["status"], "unresolved")
        self.assertTrue(pair["requires_joint_prediction"])
        self.assertEqual(pair["prediction_set_status"], "separating")
        self.assertIsNone(pair["excluded_explanation"])
        self.assertEqual(result["outcomes"][0]["excluded_explanations"], [])
        self.assertEqual(result["outcome_link_diagnostics"][0]["status"], "joint_prediction_required")
        self.assertEqual(loop["hypotheses"][0]["conditional_alternatives"][0]["relations"][0]["relation"], "can_coexist")

    def test_unknown_relations_retain_prediction_differences_without_preference(self):
        for relations in ([], [{"alternative_id": "b", "relation": "unknown", "conditions": "Not established"}],
                          [{"alternative_id": "b", "relation": "exclusive_under_conditions", "conditions": ""}]):
            with self.subTest(relations=relations):
                loop = copy.deepcopy(self.loop)
                loop["hypotheses"][0]["conditional_alternatives"][0]["relations"] = relations
                pair = self.observation(loop=loop)["outcomes"][0]["pairs"][0]
                self.assertEqual(pair["status"], "separating")
                self.assertEqual(pair["prediction_set_status"], "separating")
                self.assertEqual(pair["relationship_status"], "unknown")
                self.assertFalse(pair["selection_eligible"])
                self.assertFalse(pair["requires_joint_prediction"])
                self.assertIn("explanation_relationship_unknown", pair["reasons"])

    def test_cross_hypothesis_relation_does_not_inherit_exclusivity_from_complete_sets(self):
        loop = copy.deepcopy(self.loop)
        loop["hypotheses"] = [{"id": hid, "statement": "Synthetic mechanism " + hid,
                              "expected_observation": "Synthetic outcome"} for hid in ("ha", "hb")]
        loop["next_checks"][0].update(hypothesis_ids=["ha", "hb"], outcome_links=[])
        review = copy.deepcopy(self.review)
        review["causal_steps"][0]["hypothesis_id"] = "ha"
        for row, hid in zip(review["observations"][0]["predictions"], ("ha", "hb")):
            row.update(hypothesis_id=hid, alternative_id="")
        original = copy.deepcopy(review)
        pair = self.observation(review, loop)["outcomes"][0]["pairs"][0]
        self.assertEqual(pair["prediction_set_status"], "separating")
        self.assertEqual(pair["relations"], [])
        self.assertEqual(pair["relationship_status"], "unknown")
        self.assertFalse(pair["selection_eligible"])
        self.assertEqual(review, original)

    def test_unknown_cross_hypothesis_pair_does_not_hide_a_declared_exclusive_pair(self):
        loop = copy.deepcopy(self.loop)
        loop["hypotheses"].append({"id": "other", "statement": "Synthetic additional mechanism",
                                   "expected_observation": "Synthetic outcome"})
        loop["next_checks"][0]["hypothesis_ids"].append("other")
        review = copy.deepcopy(self.review)
        third = copy.deepcopy(review["observations"][0]["predictions"][1])
        third.update(hypothesis_id="other", alternative_id="")
        review["observations"][0]["predictions"].append(third)
        pairs = self.observation(review, loop)["outcomes"][0]["pairs"]
        same = next(p for p in pairs if p["left"]["hypothesis_id"] == p["right"]["hypothesis_id"])
        self.assertTrue(same["selection_eligible"])
        self.assertEqual(same["relationship_status"], "exclusive_under_conditions")
        cross = next(p for p in pairs if p["left"]["alternative_id"] == "a" and p["right"]["hypothesis_id"] == "other")
        self.assertEqual(cross["prediction_set_status"], "separating")
        self.assertFalse(cross["selection_eligible"])

    def test_retrospective_predictions_are_marked_and_not_prospective_selection(self):
        r = copy.deepcopy(self.review)
        r["observations"][0]["predictions"][0]["origin"] = "reconstructed_after_result"
        result = self.observation(r)
        pair = result["outcomes"][0]["pairs"][0]
        self.assertEqual(pair["status"], "separating")
        self.assertTrue(pair["retrospective"])
        self.assertFalse(pair["selection_eligible"])
        self.assertEqual(result["outcome_link_diagnostics"][0]["status"], "retrospective_prediction")
        r["observations"][0]["predictions"][0]["origin"] = "previously_recorded"
        self.assertTrue(self.observation(r)["outcomes"][0]["pairs"][0]["selection_eligible"])

    def test_missing_prediction_sources_preserve_the_declared_sets_and_disable_selection(self):
        r = copy.deepcopy(self.review)
        r["observations"][0]["predictions"][1]["source_ids"] = ["missing"]
        result = self.observation(r)
        self.assertEqual(result["explanations"][1]["source_checks"][0]["status"], "missing")
        pair = result["outcomes"][0]["pairs"][0]
        self.assertEqual(pair["status"], "separating")
        self.assertFalse(pair["selection_eligible"])
        self.assertIn("prediction_source_unresolved", pair["reasons"])
        self.assertEqual(self.prepared(r)["value"]["review"], r)

    def test_omitted_observations_and_base_hypothesis_rows_remain_visible(self):
        r = copy.deepcopy(self.review)
        r["observations"] = []
        result = self.prepared(r)["value"]
        self.assertEqual(result["summary"]["unreviewed_check_ids"], ["c1"])
        self.assertEqual(result["observation_checks"][0]["status"], "not_reviewed")
        self.assertEqual(len(result["observation_checks"][0]["missing_explanations"]), 2)
        loop = copy.deepcopy(self.loop)
        loop["hypotheses"][0].pop("conditional_alternatives")
        loop["next_checks"][0]["outcome_links"] = []
        base = self.prepared(r, loop)["value"]["observation_checks"][0]
        self.assertEqual(base["missing_explanations"], [{"hypothesis_id": "h1", "alternative_id": ""}])

    def test_existing_outcome_links_are_diagnosed_and_never_rewritten(self):
        loop = copy.deepcopy(self.loop)
        loop["next_checks"][0]["outcome_links"][0]["effects"][0]["relation"] = "challenges"
        original = copy.deepcopy(loop)
        result = self.observation(loop=loop)
        self.assertEqual(result["outcome_link_diagnostics"][0]["status"], "conflicts_with_prediction_set")
        self.assertFalse(result["outcome_link_diagnostics"][0]["automatic_rewrite"])
        self.assertEqual(loop, original)

    def test_explicit_parent_prediction_survives_alternatives_without_inferred_exclusivity(self):
        for version in ("1", "2"):
            with self.subTest(version=version):
                review = copy.deepcopy(self.review)
                review["observations"][0]["predictions"].append(prediction("", [1], self.source))
                if version == "2":
                    review.update(schema_version="2", scope={
                        "hypotheses": [{"hypothesis_id": "h1", "status": "reviewed", "reason": "Synthetic causal step"}],
                        "checks": [{"check_id": "c1", "status": "reviewed", "reason": "Synthetic predictions"}]})
                original = copy.deepcopy(review)
                record = self.prepared(review)["value"]
                result = record["observation_checks"][0]
                self.assertEqual(record["review"], original)
                self.assertEqual(review, original)
                self.assertEqual({r["alternative_id"] for r in result["explanations"]}, {"", "a", "b"})
                self.assertEqual(result["missing_explanations"], [])
                parent_pair = next(p for p in result["outcomes"][0]["pairs"]
                                   if {p["left"]["alternative_id"], p["right"]["alternative_id"]} == {"", "a"})
                self.assertEqual(parent_pair["prediction_set_status"], "separating")
                self.assertEqual(parent_pair["relationship_status"], "unknown")
                self.assertFalse(parent_pair["selection_eligible"])
                self.assertIn("explanation_relationship_unknown", parent_pair["reasons"])

    def test_legacy_alternatives_do_not_gain_unrequested_parent_coverage(self):
        result = self.observation()
        self.assertEqual([r["alternative_id"] for r in result["explanations"]], ["a", "b"])
        self.assertEqual(result["missing_explanations"], [])
        review = copy.deepcopy(self.review)
        review["observations"] = []
        result = self.observation(review)
        self.assertEqual(result["missing_explanations"], [
            {"hypothesis_id": "h1", "alternative_id": "a"},
            {"hypothesis_id": "h1", "alternative_id": "b"}])

    def test_authored_parent_does_not_admit_foreign_hypotheses_or_alternatives(self):
        loop = copy.deepcopy(self.loop)
        loop["hypotheses"].append({"id": "outside-check", "statement": "Known but outside this check"})
        for hid, aid in (("foreign", ""), ("outside-check", ""), ("h1", "foreign")):
            with self.subTest(hypothesis_id=hid, alternative_id=aid):
                review = copy.deepcopy(self.review)
                row = prediction(aid, [0], self.source)
                row["hypothesis_id"] = hid
                review["observations"][0]["predictions"].append(row)
                with self.assertRaises(ValueError) as error:
                    validate(review, self.store.snapshot(self.wid), loop)
                self.assertIn("check_id='c1'", str(error.exception))
                self.assertIn(f"hypothesis_id={hid!r}", str(error.exception))
                self.assertIn(f"alternative_id={aid!r}", str(error.exception))
                self.assertIn("/hypothesis_review/observations/0/predictions/2", str(error.exception))

    def test_explicit_parent_does_not_restore_out_of_scope_alternative(self):
        loop = copy.deepcopy(self.loop)
        loop["hypotheses"][0]["conditional_alternatives"][1]["part_ids"] = ["outside-part"]
        loop["next_checks"][0]["scope_targets"] = [{"hypothesis_id": "h1", "part_ids": ["checked-part"]}]
        review = copy.deepcopy(self.review)
        review["observations"][0]["predictions"].append(prediction("", [1], self.source))
        with self.assertRaisesRegex(ValueError, "alternative_id='b'"):
            validate(review, self.store.snapshot(self.wid), loop)
        review["observations"][0]["predictions"].pop(1)
        result = self.observation(review, loop)
        self.assertEqual({r["alternative_id"] for r in result["explanations"]}, {"", "a"})

    def test_bad_decision_local_references_and_duplicate_rows_are_rejected(self):
        state = self.store.snapshot(self.wid)
        for location, field, value in (("step", "hypothesis_id", "foreign"), ("step", "part_id", "foreign"),
                                       ("observation", "check_id", "foreign"), ("prediction", "alternative_id", "foreign"),
                                       ("prediction", "outcome_indices", [3]), ("prediction", "outcome_indices", [0, 0])):
            with self.subTest(location=location, field=field):
                r = copy.deepcopy(self.review)
                target = {"step": r["causal_steps"][0], "observation": r["observations"][0],
                          "prediction": r["observations"][0]["predictions"][0]}[location]
                target[field] = value
                with self.assertRaises(ValueError):
                    validate(r, state, self.loop)
        r = copy.deepcopy(self.review)
        r["observations"][0]["predictions"].append(copy.deepcopy(r["observations"][0]["predictions"][0]))
        with self.assertRaises(ValueError):
            validate(r, state, self.loop)
        r = copy.deepcopy(self.review)
        r["schema_version"] = "future"
        with self.assertRaises(jsonschema.ValidationError):
            validate(r, state, self.loop)

    def test_exact_decision_binding_ignores_latest_unattached_review_and_survives_input_change(self):
        aid, published = self.publish()
        self.assertTrue(published)
        current = view(self.store, self.wid, self.store.snapshot(self.wid))
        self.assertEqual(current["status"], "available")
        self.assertEqual(current["published_decision_id"], aid)
        self.assertTrue(current["is_current_input"])
        unrelated = bind_record(self.prepared(), "another-decision")
        newer = self.store.add_artifact(self.wid, "Unattached review", unrelated["kind"], dump(unrelated["value"]).encode(), unrelated["meta"], bump=False)
        self.assertNotEqual(view(self.store, self.wid, self.store.snapshot(self.wid))["artifact_id"], newer)
        self.store.command(self.wid, 1, "changed", {"kind": "correction", "text": "Synthetic condition changed"})
        stale = view(self.store, self.wid, self.store.snapshot(self.wid))
        self.assertEqual(stale["published_decision_id"], aid)
        self.assertFalse(stale["is_current_input"])
        self.assertEqual(stale["review"], self.review)

    def test_new_decision_without_review_never_inherits_older_review(self):
        self.publish()
        aid, published = self.publish(records=[])
        self.assertTrue(published)
        self.assertIsNone(view(self.store, self.wid, self.store.snapshot(self.wid)))
        self.assertEqual(self.store.snapshot(self.wid)["events"][-1]["body"]["receipt_id"], aid)

    def test_reusing_old_review_at_same_revision_and_loop_is_rejected_by_exact_id(self):
        self.publish()
        state = self.store.snapshot(self.wid)
        prior = view(self.store, self.wid, state)
        proposal = copy.deepcopy(state["decision"])
        aid = self.store.add_artifact(self.wid, "Another identical-loop decision", "decision_proposal", dump(proposal).encode(),
                                      {"finalization_records": {"hypothesis_review": prior["artifact_id"]}}, bump=False)
        self.store.publish_decision(self.wid, 1, proposal, aid)
        result = view(self.store, self.wid, self.store.snapshot(self.wid))
        self.assertEqual(result["status"], "binding_mismatch")
        self.assertEqual(result["issues"], ["review_bound_to_another_decision"])
        self.assertIsNone(result["review"])

    def test_wrong_revision_or_loop_hash_is_not_shown_as_current_and_bind_is_immutable(self):
        for field, bad in (("based_rev", 9), ("loop_sha256", "wrong")):
            with self.subTest(field=field):
                record = self.prepared()
                original = copy.deepcopy(record)
                bound = bind_record(record, "fixture")
                self.assertEqual(record, original)
                self.assertEqual(bound["meta"]["decision_id"], "fixture")
                record["value"][field] = bad
                self.publish(records=[record])
                result = view(self.store, self.wid, self.store.snapshot(self.wid))
                self.assertEqual(result["status"], "binding_mismatch")
                self.assertFalse(result["is_current_input"])


if __name__ == "__main__":
    unittest.main()
