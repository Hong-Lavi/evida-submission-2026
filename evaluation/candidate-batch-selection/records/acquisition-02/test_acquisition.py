import ast
import itertools
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import acquisition as a
from common import HERE, BASE, sha, load, save
from run_selection import complete_rows, expected_keys
import score_selection as score


class Mathematics(unittest.TestCase):
    def test_unique_qpo_exhaustive_optimum(self):
        draws = np.array([[5, 1, 0, 0], [4, 1, 0, 0], [0, 6, 1, 0], [0, 0, 5, 0], [0, 0, 4, 0]])
        order, d = a.qpo_order(draws, np.zeros(4), list("ABCD"), 2)
        winners = np.argmax(draws, axis=1)
        utility = lambda picks: np.isin(winners, picks).mean()
        self.assertEqual(utility(order), max(utility(p) for p in itertools.combinations(range(4), 2)))
        self.assertEqual(d["nonunique_winner_draws"], 0)

    def test_nonunique_qpo_avoids_double_counting_identical_winners(self):
        draws = np.array([[3, 3, 0], [3, 3, 0], [0, 0, 3]])
        order, d = a.qpo_order(draws, np.zeros(3), list("ABC"), 2)
        self.assertEqual(order.tolist(), [0, 2])
        self.assertEqual(d["nonunique_winner_draws"], 2)
        self.assertAlmostEqual(sum(d["unconditional_incremental_coverage"]), 1.)

    def test_fractional_membership_and_additive_utility(self):
        draws = np.array([[3, 2, 2, 0, 0], [0, 0, 2, 3, 3]])
        weights = a.fractional_top_membership(draws, 2)
        np.testing.assert_allclose(weights.sum(axis=1), 2)
        self.assertEqual(weights[0, 1], .5)
        p = weights.mean(axis=0)
        order = a.rank(p, list("ABCDE"))[:2]
        utility = lambda picks: weights[:, list(picks)].sum(axis=1).mean()
        self.assertEqual(utility(order), max(utility(pick) for pick in itertools.combinations(range(5), 2)))

    def test_singular_identical_candidates_no_jitter(self):
        mu = np.array([1., 1., 0.])
        cov = np.array([[1., 1., .1], [1., 1., .1], [.1, .1, .5]])
        mean, factor, d = a.posterior_factor(mu, cov)
        self.assertEqual(d["equal_groups"], [[0, 1]])
        self.assertEqual(d["jitter_added"], 0)
        samples = mean + np.random.default_rng(0).normal(size=(100, factor.shape[1])) @ factor.T
        np.testing.assert_array_equal(samples[:, 0], samples[:, 1])
        np.testing.assert_allclose(factor @ factor.T, cov, atol=d["covariance_tolerance"])

    def test_deterministic_ties_and_near_but_distinct_not_merged(self):
        _, factor, d = a.posterior_factor(np.ones(3), np.zeros((3, 3)))
        self.assertEqual(d["equal_groups"], [[0, 1, 2]])
        self.assertEqual(factor.shape[1], 0)
        _, _, near = a.posterior_factor(np.ones(2), np.array([[1., 1.-1e-6], [1.-1e-6, 1.]]))
        self.assertEqual(near["equal_groups"], [])
        self.assertEqual(near["quotient_rank"], 2)

    def test_bad_covariance_and_nonfinite_rejected(self):
        for cov in [np.array([[1., 2.], [2., 1.]]), np.array([[1., .1], [.3, 1.]]), np.full((2, 2), np.nan)]:
            with self.assertRaises(ValueError):
                a.posterior_factor(np.zeros(2), cov)

    def test_observation_noise_and_seed_determinism(self):
        ids = list("ABC")
        mu = np.array([1., 1., 0.]); cov = np.array([[1., 1., 0.], [1., 1., 0.], [0., 0., .3]])
        args = (ids, mu, cov, np.sqrt(np.diag(cov) + .2), [0, 1], 256, 2)
        x, dx = a.posterior_orders(*args); y, dy = a.posterior_orders(*args)
        for seed in x:
            for method in x[seed]:
                np.testing.assert_array_equal(x[seed][method], y[seed][method])
            self.assertGreater(dx["seeds"][seed]["latent"]["nonunique_winner_draws"], 0)
            self.assertEqual(dx["seeds"][seed]["observation"]["nonunique_winner_draws"], 0)
        self.assertEqual(dx, dy)
        with self.assertRaises(ValueError):
            a.posterior_orders(ids, mu, cov, np.zeros(3), [0], 10, 2)

    def test_original_metric_parity_with_id_ties(self):
        source = (BASE / "tanimoto-trial/score_comparison.py").read_text()
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "metrics")
        namespace = {"np": np}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "original-metrics", "exec"), namespace)
        ids = [f"c{i:02d}" for i in range(15)]
        y = np.array([9., 9., 8., 8., 7., 7., 6., 6., 5., 5., 5., 5., 3., 2., 1.])
        pred = np.array([0., 1., 2., 3., 4., 4., 4., 4., 4., 4., 4., 4., 3., 2., 1.])
        chosen = [ids[i] for i in a.rank(pred, ids)[:10]]
        old = namespace["metrics"](y, pred, ids, lambda *_: 0.)
        new = score.selection_metrics(y, ids, chosen)
        self.assertEqual(old["top10_recall"], new["id_top10_recall"])
        self.assertEqual(old["best_true_activity_in_selected10"], new["best_activity"])

    def test_fractional_gold_does_not_choose_favorable_tie_rule(self):
        ids = [f"c{i:02d}" for i in range(12)]
        result = score.selection_metrics(np.ones(12), ids, ids[-5:])
        self.assertEqual(result["id_top10_recall"], .3)
        self.assertAlmostEqual(result["fractional_top10_recall"], 5 / 12)
        self.assertEqual(result["best_any_capture"], 1)
        self.assertEqual(result["best_id_capture"], 0)
        self.assertAlmostEqual(result["fractional_best_capture"], 5 / 12)

    def test_cluster_bootstrap_keeps_two_endpoints_together(self):
        protocol = {"methods": ["gp_mean", "original_policy", "pTop10_latent"], "batches": [10],
                    "seeds": [0, 1], "bootstrap_seed": 0, "bootstrap_repetitions": 5000}
        rows = []
        for task, delta in (("A_Ki", 1.), ("A_EC50", 3.), ("B_Ki", 5.)):
            for method in protocol["methods"]:
                for seed in protocol["seeds"]:
                    m = {name: delta if method == "pTop10_latent" else 0. for name in score.METRICS}
                    rows.append({"task": task, "method": method, "seed": seed, "batch": 10,
                        "status": "completed", "fallback_selected_ids": [], "raw_metrics": m,
                        "fallback_metrics": None, "operational_zero_hit_metrics": m})
        primary = [r for r in score.aggregate(rows, protocol)["comparisons"] if r["primary"]]
        self.assertTrue(all(r["tasks"] == 3 and r["target_clusters"] == 2 for r in primary))
        self.assertTrue(all(r["mean_difference"] == 3. and r["cluster_ci95"] == [2., 5.] for r in primary))

    def test_worker_read_boundary_blocks_synthetic_gold(self):
        import subprocess, sys
        with tempfile.TemporaryDirectory(dir=HERE, prefix="synthetic-boundary-") as directory:
            gold = Path(directory) / "test-gold.json"
            gold.write_text("synthetic sentinel")
            command = "import sys; from selection_worker import deny_gold_and_network; sys.addaudithook(deny_gold_and_network); open(sys.argv[1]).read()"
            result = subprocess.run([sys.executable, "-B", "-c", command, str(gold)], cwd=HERE,
                                    capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"Selection worker cannot read evaluation labels", result.stderr)


class GateBoundaries(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=HERE, prefix="synthetic-gate-")
        self.root = Path(self.tmp.name)
        self.out = self.root / "run"; self.out.mkdir()
        self.protocol = {"tasks": [], "methods": list(a.METHODS), "seeds": list(range(5)),
                         "batches": [5, 10, 20], "source_pins": {}, "input_pins": {},
                         "planned_selection_rows": 3600, "bootstrap_seed": 0, "bootstrap_repetitions": 20}
        self.terminals = []
        ids = [f"c{i:02d}" for i in range(20)]
        for number in range(30):
            task = f"T{number:02d}"
            out = self.out / task; out.mkdir()
            packet = {"task": task, "candidate_ids": ids, "gp_mean": list(range(20)),
                      "rf_mean": list(range(20)), "selected_policy_arm": "gp"}
            packet_path = self.root / (task + ".json"); save(packet_path, packet)
            gold = self.root / (task + "-test-gold.json")
            save(gold, [{"candidate_id": i, "p_activity": float(j)} for j, i in enumerate(ids)])
            self.protocol["tasks"].append({"task": task, "packet": str(packet_path), "n": 20,
                "gold_path": str(gold), "gold_sha256": sha(gold)})
            self.protocol["input_pins"][str(packet_path)] = sha(packet_path)
            rows = [{"task": t, "method": m, "seed": s, "batch": b, "status": "completed",
                     "selected_ids": ids[-b:][::-1], "fallback_selected_ids": [], "failure": None}
                    for t, m, s, b in expected_keys(self.protocol, task)]
            save(out / "selections.json", rows)
            receipt = {"task": task, "status": "completed", "planned_rows": 120, "completed_rows": 120,
                       "selection_sha256": sha(out / "selections.json"), "packet_sha256": sha(packet_path),
                       "artifact_pins": {"selections.json": sha(out / "selections.json")}}
            save(out / "receipt.json", receipt)
            self.terminals.append({**receipt, "receipt_sha256": sha(out / "receipt.json")})
        save(self.out / "selection-seal.json", {"protocol_sha256": "synthetic", "gold_read": False, "tasks": self.terminals})

    def tearDown(self):
        self.tmp.cleanup()

    def no_gold_on_failure(self):
        real_sha = score.sha
        reads = []
        def guarded_sha(path):
            if "test-gold" in str(path):
                reads.append(str(path))
                raise AssertionError("Gold opened before gate completed")
            return real_sha(path)
        with patch.object(score, "sha", guarded_sha):
            with self.assertRaises((ValueError, FileNotFoundError)):
                score.score_after_gate(self.protocol, self.out, "synthetic", lambda p: reads.append(str(p)))
        self.assertEqual(reads, [])

    def resign_last(self, rows):
        import json
        out = self.out / "T29"
        (out / "selections.json").write_text(json.dumps(rows))
        receipt = load(out / "receipt.json")
        receipt["selection_sha256"] = sha(out / "selections.json")
        receipt["artifact_pins"]["selections.json"] = receipt["selection_sha256"]
        (out / "receipt.json").write_text(json.dumps(receipt))
        seal = load(self.out / "selection-seal.json")
        seal["tasks"][-1] = {**receipt, "receipt_sha256": sha(out / "receipt.json")}
        (self.out / "selection-seal.json").write_text(json.dumps(seal))

    def test_complete_all30_gate_then_labels(self):
        calls = []
        def read_gold(p):
            calls.append(p); return load(p)
        rows, _ = score.score_after_gate(self.protocol, self.out, "synthetic", read_gold)
        self.assertEqual((len(rows), len(calls)), (3600, 30))
        result = score.aggregate(rows, self.protocol)
        primary = [r for r in result["comparisons"] if r["primary"]]
        self.assertEqual(len(primary), 2)
        self.assertTrue(all(r["tasks"] == 30 and r["mean_difference"] == 0 for r in primary))

    def test_missing_final_task_blocks_all_gold(self):
        (self.out / "T29/receipt.json").unlink()
        self.no_gold_on_failure()

    def test_corrupt_final_task_blocks_all_gold(self):
        (self.out / "T29/selections.json").write_text("[]")
        self.no_gold_on_failure()

    def test_resigned_duplicate_or_foreign_or_missing_rows_block_gold(self):
        original = load(self.out / "T29/selections.json")
        import copy
        for variant in ("duplicate", "foreign", "missing"):
            rows = copy.deepcopy(original)
            if variant == "duplicate": rows[-1]["selected_ids"][0] = rows[-1]["selected_ids"][1]
            if variant == "foreign": rows[-1]["selected_ids"][0] = "foreign"
            if variant == "missing": rows.pop()
            self.resign_last(rows)
            self.no_gold_on_failure()

    def test_timeout_preserves120_rows_and_separate_fallback(self):
        packet = load(self.protocol["tasks"][0]["packet"])
        partial = load(self.out / "T00/selections.json")[:15]
        rows = complete_rows(self.protocol, packet, partial, "timeout")
        self.assertEqual(len(rows), 120)
        self.assertEqual(sum(r["status"] == "completed" for r in rows), 15)
        self.assertEqual(sum(bool(r["fallback_selected_ids"]) for r in rows), 60)
        self.assertTrue(all(not r["selected_ids"] for r in rows if r["status"] == "failed"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
