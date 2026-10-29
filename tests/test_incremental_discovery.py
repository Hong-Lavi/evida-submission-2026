import copy
import json
from pathlib import Path
import tempfile
import unittest

from evida.contracts import model_functions, RESEARCH_NOTES
from evida.discovery import catalog, record_review
from evida.incremental_discovery import record_notes
from evida.store import Conflict, Store, dump


class IncrementalDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "state.sqlite3")
        self.wid = self.store.create("storage fixture")["id"]
        self.source = self.store.add_artifact(self.wid, "source", "literature",
            dump({"status": "succeeded", "rows": []}).encode(), {}, bump=False)
        self.notes = {"findings": [{"text": "Mechanism proposal with unresolved tissue applicability.",
            "source_ids": [self.source], "discovery_option": {
                "option_id": "mechanism:test", "label": "Explicit test mechanism"}}],
            "open_questions": ["Which tissue?"], "next_goal": "Check context"}

    def tearDown(self):
        self.tmp.cleanup()

    def test_increment_survives_restart_without_becoming_recommendation(self):
        record_review(self.store, self.wid, 1, "previous",
            {"question": "prior", "new_options": [], "assessments": [], "unsearched_scope": ["unsearched alternative"]})
        aid = record_notes(self.store, self.wid, 1, "job", self.notes, call_id="call-1")
        self.store = Store(self.store.path)
        pool = catalog(self.store, self.wid)
        self.assertEqual((pool["total"], pool["reviewed"]), (1, 0))
        self.assertEqual(pool["unsearched_scope"], ["unsearched alternative"])
        self.assertIsNone(pool["options"][0]["assessment"])
        self.assertEqual(json.loads(self.store.artifact(self.wid, aid)["content"]), self.notes)
        count = len(self.store.snapshot(self.wid)["artifacts"])
        self.assertEqual(record_notes(self.store, self.wid, 1, "job", self.notes, call_id="call-1"), aid)
        self.assertEqual(len(self.store.snapshot(self.wid)["artifacts"]), count)
        changed = copy.deepcopy(self.notes); changed["next_goal"] = "Something else"
        with self.assertRaises(Conflict):
            record_notes(self.store, self.wid, 1, "job", changed, call_id="call-1")

    def test_failed_second_write_rolls_back_notes_and_events(self):
        before = self.store.snapshot(self.wid)
        with self.store.connect(True) as db:
            db.execute("CREATE TRIGGER fail_review BEFORE INSERT ON artifacts WHEN NEW.kind='discovery_review' "
                       "BEGIN SELECT RAISE(ABORT,'injected review write failure'); END")
        with self.assertRaisesRegex(Exception, "injected"):
            record_notes(self.store, self.wid, 1, "job", self.notes, call_id="call-1")
        after = self.store.snapshot(self.wid)
        self.assertEqual(before["artifacts"], after["artifacts"])
        self.assertEqual(before["events"], after["events"])
        with self.store.connect(True) as db:
            db.execute("DROP TRIGGER fail_review")
        record_notes(self.store, self.wid, 1, "job", self.notes, call_id="call-1")
        self.assertEqual(catalog(self.store, self.wid)["total"], 1)

    def test_legacy_or_null_notes_do_not_invent_options(self):
        for index, marker in enumerate(("absent", None)):
            value = copy.deepcopy(self.notes)
            if marker == "absent":
                del value["findings"][0]["discovery_option"]
            else:
                value["findings"][0]["discovery_option"] = None
            record_notes(self.store, self.wid, 1, "job", value, call_id=str(index))
        self.assertEqual(catalog(self.store, self.wid)["total"], 0)

    def test_unavailable_source_and_stale_context_publish_nothing(self):
        before = len(self.store.snapshot(self.wid)["artifacts"])
        bad = copy.deepcopy(self.notes); bad["findings"][0]["source_ids"] = ["invented"]
        with self.assertRaises(ValueError):
            record_notes(self.store, self.wid, 1, "job", bad, call_id="bad")
        with self.assertRaises(Conflict):
            record_notes(self.store, self.wid, 0, "job", self.notes, call_id="stale")
        self.assertEqual(len(self.store.snapshot(self.wid)["artifacts"]), before)

    def test_model_schema_is_strict_but_preserved_notes_stay_compatible(self):
        original = copy.deepcopy(RESEARCH_NOTES)
        functions = model_functions()
        for f in functions:
            if f["name"] == "frame_work":
                continue
            item = f["parameters"]["properties"]["research_notes"]["properties"]["findings"]["items"]
            self.assertIn("discovery_option", item["required"])
        self.assertEqual(RESEARCH_NOTES, original)
        self.assertNotIn("discovery_option", RESEARCH_NOTES["properties"]["findings"]["items"]["required"])


if __name__ == "__main__":
    unittest.main()
