"""Real synthetic subprocess death; no actual pool or evaluation label is read."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from acquisition import METHODS
from common import HERE, load, save, sha
import run_selection as run
from score_selection import gate


FIXTURE_WORKER = '''import json, os, signal, sys
from pathlib import Path
p = Path(sys.argv[1]); out = Path(sys.argv[2]); packet = json.loads(p.read_text())
with (out / 'launch-marker.json').open('x') as f: json.dump({'launches': 1}, f)
behavior = packet['fixture_behavior']
if behavior == 'input_change': p.write_text('{}'); raise SystemExit(0)
if behavior == 'source_change': Path(packet['source_sentinel']).write_text('changed'); raise SystemExit(0)
methods = ['rf_mean','gp_mean','original_policy','random','qPO_latent','qPO_observation','pTop10_latent','pTop10_observation']
def rows(ms, seeds):
 return [{'task':packet['task'],'method':m,'seed':s,'batch':b,'status':'completed',
          'selected_ids':packet['candidate_ids'][-b:][::-1],'fallback_selected_ids':[],'failure':None}
         for m in ms for s in seeds for b in [5,10,20]]
def write(name, value):
 with (out/name).open('x') as f: json.dump(value,f)
def truncate_and_die(name):
 with (out/name).open('x') as f: f.write('[{"task":'); f.flush(); os.fsync(f.fileno())
 os.kill(os.getpid(),signal.SIGKILL)
if behavior == 'baseline_kill': truncate_and_die('baseline.json')
write('baseline.json',rows(methods[:4],range(5)))
if behavior == 'posterior_kill': truncate_and_die('posterior-seed-0.json')
for seed in range(5):
 data=rows(methods[4:],[seed])
 if behavior == 'structural_invalid' and seed == 0:
  data[0]['selected_ids'][0]=data[0]['selected_ids'][1]
 if behavior == 'extra_nan' and seed == 0: data[0]['unexpected']=float('nan')
 if behavior == 'object_instead_of_list' and seed == 0: data={'rows':data}
 if behavior == 'missing_field' and seed == 0: del data[0]['status']
 write(f'posterior-seed-{seed}.json',data)
'''


class RunnerRecovery(unittest.TestCase):
    def fixture(self, mode):
        directory = HERE / "revision-02"
        directory.mkdir(exist_ok=True)
        root = Path(tempfile.mkdtemp(dir=directory, prefix="synthetic-" + mode + "-"))
        (root / "selection_worker.py").write_text(FIXTURE_WORKER)
        sentinel = root / "source-sentinel.txt"; sentinel.write_text("unchanged")
        protocol = {"tasks": [], "methods": list(METHODS), "seeds": list(range(5)),
            "batches": [5, 10, 20], "mc_draws": 8192, "task_timeout_seconds": 10,
            "source_pins": {str(root / "selection_worker.py"): sha(root / "selection_worker.py"),
                            str(sentinel): sha(sentinel)},
            "input_pins": {}, "planned_selection_rows": 3600}
        for i in range(30):
            task = f"SYNTHETIC{i:02d}"
            faults = ["baseline_kill", "posterior_kill", "structural_invalid", "extra_nan", "object_instead_of_list", "missing_field"]
            behavior = faults[i] if mode == "killed" and i < len(faults) else mode if mode != "killed" and i == 0 else "valid"
            packet = {"task": task, "candidate_ids": [f"c{j:02d}" for j in range(20)],
                "gp_mean": list(range(20)), "rf_mean": list(range(20)), "selected_policy_arm": "gp",
                "fixture_behavior": behavior, "source_sentinel": str(sentinel)}
            path = root / (task + ".json"); save(path, packet)
            protocol["tasks"].append({"task": task, "packet": str(path), "n": 20,
                "gold_path": str(root / (task + "-test-gold.json"))})
            protocol["input_pins"][str(path)] = sha(path)
        save(root / "protocol.json", protocol)
        return root, protocol

    def run_guarded(self, root, protocol, expect_error=False):
        opened = []
        original = Path.open
        def guarded(path, *args, **kwargs):
            if "test-gold" in str(path) or "evaluation-only" in str(path):
                opened.append(str(path))
                raise AssertionError("Gold access during selection")
            return original(path, *args, **kwargs)
        with patch.object(run, "HERE", root), patch.object(run, "frozen_protocol", return_value=protocol), \
                patch.object(Path, "open", guarded), redirect_stdout(io.StringIO()):
            if expect_error:
                with self.assertRaisesRegex(ValueError, "Pinned file changed"):
                    run.main()
            else:
                run.main()
                self.assertEqual(len(gate(protocol, root / "run-01", sha(root / "protocol.json"))), 3600)
        self.assertEqual(opened, [])

    def test_real_killed_and_truncated_workers_preserve_all30_seal_and_zero_gold(self):
        root, protocol = self.fixture("killed")
        self.run_guarded(root, protocol)
        seal = load(root / "run-01/selection-seal.json")
        self.assertEqual(len(seal["tasks"]), 30)
        self.assertEqual(sum(r["planned_rows"] for r in seal["tasks"]), 3600)
        self.assertEqual(sum(r["completed_rows"] for r in seal["tasks"]), 3372)
        self.assertEqual([r["completed_rows"] for r in seal["tasks"][:7]], [0, 60, 108, 108, 108, 108, 120])
        for index, filename in ((0, "baseline.json"), (1, "posterior-seed-0.json")):
            terminal = seal["tasks"][index]
            path = root / "run-01" / terminal["task"] / filename
            self.assertEqual(path.read_bytes(), b'[{"task":')
            self.assertEqual(terminal["worker_failure"], "worker_exit_-9")
            detail = next(e for e in terminal["artifact_errors"] if e["artifact"] == filename)
            self.assertEqual(detail["error_type"], "JSONDecodeError")
            self.assertEqual(detail["original_sha256"], sha(path))
        self.assertIsNone(seal["tasks"][2]["worker_failure"])
        self.assertEqual(seal["tasks"][2]["failure"], "invalid_worker_artifact")
        self.assertEqual(len(list((root / "run-01").glob("*/launch-marker.json"))), 30)
        save(root / "regression-result.json", {"status": "PASS", "planned_tasks": 30,
             "terminal_tasks": 30, "planned_rows": 3600, "completed_rows": 3372,
             "failed_rows": 228, "worker_launches": 30, "automatic_retries": 0,
             "truncated_original_bytes_preserved": True, "scorer_full_gate_passed": True,
             "gold_reads": 0, "actual_dataset_reads": 0, "seal_sha256": sha(root / "run-01/selection-seal.json")})

    def test_source_and_input_mutation_remain_fail_closed(self):
        for mode in ("source_change", "input_change"):
            root, protocol = self.fixture(mode)
            self.run_guarded(root, protocol, expect_error=True)
            self.assertFalse((root / "run-01/selection-seal.json").exists())
            self.assertEqual(len(list((root / "run-01").glob("*/launch-marker.json"))), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
