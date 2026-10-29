"""Literal lineage checks; synthetic text is not a scientific judgment test."""
import copy
import tempfile
import unittest
from pathlib import Path

from evida.store import Store, dump
from test_research_loop import seed


class WordingLineageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name)/'state.db')
        self.wid, self.aid, self.pid, self.p = seed(self.store)

    def tearDown(self):
        self.temp.cleanup()

    def publish(self, p):
        aid = self.store.add_artifact(self.wid, 'synthetic judgment', 'decision_proposal',
                                      dump(p).encode(), {}, bump=False)
        return aid, self.store.publish_decision(self.wid, p['based_on_state_rev'], p, aid)

    def test_changed_prediction_keeps_previous_bytes_and_records_both(self):
        prior = self.store.artifact(self.wid, self.pid)
        self.store.command(self.wid, 1, 'synthetic-input', {'kind':'observation','text':'Synthetic update','synthetic':True})
        p = copy.deepcopy(self.p)
        p['based_on_state_rev'] = 2
        old = p['research_loop']['hypotheses'][0]['expected_observation']
        p['research_loop']['hypotheses'][0]['expected_observation'] = 'A different conditional prediction.'
        aid, published = self.publish(p)
        self.assertTrue(published)
        self.assertEqual(self.store.artifact(self.wid,self.pid)['content'], prior['content'])
        event = next(e['body'] for e in reversed(self.store.snapshot(self.wid)['events']) if e['kind']=='hypothesis_wording_compared')
        self.assertEqual(event['receipt_id'], aid)
        self.assertEqual(event['reference']['decision_id'],self.pid)
        self.assertEqual(event['comparisons'][0]['changed_fields'],[{'field':'expected_observation','before':old,'after':'A different conditional prediction.'}])
        self.assertEqual(self.store.snapshot(self.wid)['decision'],p)

    def test_omitted_is_not_rejected_and_new_id_is_not_retrospective(self):
        p = copy.deepcopy(self.p)
        p['research_loop']['hypotheses'][0]['id'] = 'new-explanation'
        self.publish(p)
        event = next(e['body'] for e in reversed(self.store.snapshot(self.wid)['events']) if e['kind']=='hypothesis_wording_compared')
        self.assertEqual({c['id']:c['status'] for c in event['comparisons']},
                         {'h1':'not_in_current','new-explanation':'not_in_reference'})

    def test_stale_publication_adds_no_current_wording_comparison(self):
        count = sum(e['kind']=='hypothesis_wording_compared' for e in self.store.snapshot(self.wid)['events'])
        self.store.command(self.wid,1,'edit',{'kind':'correction','text':'Changed input'})
        _,published = self.publish(self.p)
        self.assertFalse(published)
        self.assertEqual(sum(e['kind']=='hypothesis_wording_compared' for e in self.store.snapshot(self.wid)['events']),count)


if __name__=='__main__':
    unittest.main()
