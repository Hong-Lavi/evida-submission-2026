"""Two source tables must remain available together after sequential reads."""
import hashlib
import json
import unittest
from evida.model_context import model_json, unpack, working_readings


class WorkingReadingsTests(unittest.TestCase):
    def fixture(self, rid, source, offset=0, job="active", columns=None):
        args = {"artifact_id": source, "offset": offset, "limit": 2}
        if columns is not None: args["columns"] = columns
        body = {"artifact_id": source, "result": {"rows": [
            {"candidate_id": "duplicate", "value": None, "raw": "NA"},
            {"candidate_id": "duplicate", "value": 0, "raw": "0"}],
            "offset": offset, "total_rows": 4, "has_more": offset == 0}}
        content = json.dumps(body).encode()
        a = {"id": rid, "kind": "tool_reading", "sha256": hashlib.sha256(content).hexdigest(),
             "meta": {"job_id": job, "function": "inspect_artifact", "arguments": args,
                      "source_artifact_id": source}, "content": content}
        return a

    def test_keeps_other_table_and_distinct_pages_with_original_values(self):
        artifacts = [self.fixture("old", "A", job="prior"), self.fixture("a1", "A"),
                     self.fixture("a2", "A", offset=2), self.fixture("b1", "B")]
        rows = {a["id"]: a for a in artifacts}
        retained = working_readings(artifacts, "active", ["b1"], rows.__getitem__)
        self.assertEqual([r["reading_id"] for r in retained], ["a1", "a2"])
        self.assertEqual(unpack(json.loads(model_json(retained))), retained)
        self.assertEqual(retained[0]["content"], json.loads(rows["a1"]["content"]))
        self.assertTrue(retained[0]["content"]["result"]["has_more"])
        self.assertIsNone(retained[0]["content"]["result"]["rows"][0]["value"])
        self.assertEqual(retained[0]["content"]["result"]["rows"][1]["value"], 0)

    def test_identical_reread_deduplicates_but_other_projection_survives(self):
        artifacts = [self.fixture("a-old", "A"), self.fixture("b", "B"),
                     self.fixture("a-new", "A"), self.fixture("a-columns", "A", columns=[["value"]])]
        artifacts[2]["meta"]["arguments"] = dict(reversed(list(artifacts[2]["meta"]["arguments"].items())))
        rows = {a["id"]: a for a in artifacts}
        retained = working_readings(artifacts, "active", ["a-new"], rows.__getitem__)
        self.assertEqual({r["reading_id"] for r in retained}, {"b", "a-columns"})
        self.assertEqual(working_readings(artifacts, None, [], rows.__getitem__), [])

    def test_explicit_resume_keeps_original_job_pages_without_repeating_execution(self):
        artifacts = [self.fixture('first','source',job='failed',offset=0),
                     self.fixture('last','source',job='resumed',offset=2),
                     self.fixture('unrelated','other',job='other')]
        rows = {a['id']:a for a in artifacts}
        retained = working_readings(artifacts, ['failed','resumed'], [], rows.__getitem__)
        self.assertEqual([r['reading_id'] for r in retained], ['first','last'])
        self.assertEqual(unpack(json.loads(model_json(retained))), retained)


if __name__ == "__main__":
    unittest.main()
