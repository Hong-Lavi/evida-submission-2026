"""A workspace list has to say which entries reached a published judgment.

The public demo mounts 27 workspaces and 9 of them carry no decision - re-run attempts that failed,
screen-check fixtures, an empty roadmap check. The catalog orders by creation time descending, and
the two fixtures are rebuilt at every server start, so they always hold the newest timestamps and
always lead the list. A judge following the submitted link therefore lands first on "데모 · 다섯
단계 예시 (실제 연구 결과 아님)" and then on "특발성 폐섬유증 · 순위 화면 확인용 고정 자료",
while the six real cases sit at positions three to eight.

The screen cannot fix that, because store.list() never said which rows carry a judgment: it returns
id, title, rev, created and review_status, so every entry looks alike. That is why the onboarding
panel offering "완료 결과 열기" has to name two workspace ids in its source, and why that panel
renders empty on any deployment that does not happen to mount those two ids - which the public demo
does not.

So the list reports it. A researcher wants the same thing for their own work: which of these got to
a judgment and which stopped before one.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import jsonschema
from evida.contracts import DECISION
from evida.research_loop import validate_loop
from evida.store import Store, dump

from test_integrity import proposal
from test_research_loop import hypothesis


class ListTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'state.db')

    def tearDown(self):
        self.temp.cleanup()

    def publish(self, title):
        wid = self.store.create(title)['id']
        aid = self.store.add_artifact(wid, '합성 CSV', 'molecule_csv', b'cid,smiles\nf,CCO\n', {},
                                      'text/csv', bump=False)
        p = proposal(1)
        p['research_loop']['hypotheses'] = [hypothesis(aid)]
        p['research_loop']['next_checks'] = []
        jsonschema.validate(p, DECISION)
        validate_loop(p['research_loop'], self.store.snapshot(wid))
        pid = self.store.add_artifact(wid, '합성 판단', 'decision_proposal', dump(p).encode(), {},
                                      bump=False)
        self.store.publish_decision(wid, 1, p, pid)
        return wid

    def test_a_new_workspace_has_not_reached_a_judgment(self):
        self.store.create('아직 판단 없는 연구')
        row = self.store.list()[0]
        self.assertIn('has_decision', row)
        self.assertFalse(row['has_decision'])

    def test_the_field_is_a_boolean_not_a_blob(self):
        self.store.create('아직 판단 없는 연구')
        self.assertIsInstance(self.store.list()[0]['has_decision'], bool)

    def test_the_other_fields_are_still_there(self):
        self.store.create('연구')
        row = self.store.list()[0]
        for field in ('id', 'title', 'rev', 'created', 'review_status'):
            self.assertIn(field, row)

    def test_a_published_judgment_shows_up(self):
        wid = self.publish('판단까지 간 연구')
        row = next(r for r in self.store.list() if r['id'] == wid)
        self.assertTrue(row['has_decision'])

    def test_the_two_kinds_are_reported_separately(self):
        decided = self.publish('판단까지 간 연구')
        self.store.create('멈춘 연구')
        rows = {r['id']: r['has_decision'] for r in self.store.list()}
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[decided])
        self.assertEqual(sum(1 for v in rows.values() if v), 1)


if __name__ == '__main__':
    unittest.main()
