"""History accessibility must not silently change scientific evidence claims."""
import copy
import json

import unittest
import test_decision_history as fixtures
from evida.evidence_history import view
from evida.research_loop import decision_id


class EvidenceHistoryTests(unittest.TestCase):
    setUp = fixtures.DecisionHistoryTests.setUp
    tearDown = fixtures.DecisionHistoryTests.tearDown
    save = fixtures.DecisionHistoryTests.save
    claim = fixtures.DecisionHistoryTests.claim
    def source(self):
        return self.store.add_artifact(self.wid, 'Synthetic source', 'research_evidence',
                                       b'{"synthetic":true}', {}, bump=False)

    def linked(self, source, relation='supports', condition='human trial endpoint'):
        h = self.claim('H1', 'Literal claim')
        h['evidence'] = [{'source_type':'artifact','source_id':source,'relation':relation,
                          'detail':'Synthetic recorded assessment','applicability':condition}]
        return h

    def test_omission_stays_accessible_over_multiple_generations_without_inference(self):
        source=self.source();h=self.linked(source)
        old_id,_=self.save(self.wid,1,[h]);old_bytes=self.store.artifact(self.wid,old_id)['content']
        new=copy.deepcopy(h);new['evidence']=[]
        self.save(self.wid,1,[new]);current,_=self.save(self.wid,1,[new])
        before=self.store.snapshot(self.wid)
        result=view(self.store,self.wid,'H1',0,2)
        self.assertTrue(result['has_more'])
        previous=view(self.store,self.wid,'H1',2,2)['rows'][0]
        edge=previous['evidence_comparison'][0]
        self.assertEqual(edge['comparison'],'not_in_current_list')
        self.assertEqual(edge['disposition'],'not_inferred')
        self.assertFalse(edge['automatically_reasserted'])
        self.assertEqual(previous['hypothesis']['evidence'][0]['source_id'],source)
        self.assertEqual(self.store.snapshot(self.wid),before)
        self.assertEqual(self.store.artifact(self.wid,old_id)['content'],old_bytes)
        self.assertEqual(decision_id(before),current)

    def test_same_id_changed_claim_or_conditions_never_inherits_support(self):
        source=self.source();h=self.linked(source);self.save(self.wid,1,[h])
        current=copy.deepcopy(h);current['statement']='Changed to rat surrogate'
        current['evidence'][0]['applicability']='rat surrogate, not human benefit'
        self.save(self.wid,1,[current])
        row=view(self.store,self.wid,'H1')['rows'][1]
        self.assertEqual(row['claim_comparison'],'literal_claim_changed')
        self.assertFalse(row['comparison_is_scientific_equivalence'])
        self.assertEqual(row['evidence_comparison'][0]['comparison'],'recorded_link_changed')
        self.assertEqual(row['hypothesis']['evidence'][0]['applicability'],'human trial endpoint')
        self.assertEqual(row['evidence_comparison'][0]['current_links'][0]['edge']['applicability'],current['evidence'][0]['applicability'])

    def test_relation_change_is_not_omission_and_current_read_status_is_not_inferred(self):
        source=self.source();h=self.linked(source);self.save(self.wid,1,[h])
        current=self.linked(source,'challenges','population mismatch')
        self.save(self.wid,1,[current])
        rows=view(self.store,self.wid,'H1')['rows']
        self.assertEqual(rows[1]['evidence_comparison'][0]['comparison'],'recorded_link_changed')
        self.assertEqual(rows[0]['evidence_comparison'][0]['comparison'],'same_recorded_link')
        self.assertEqual(rows[0]['evidence_comparison'][0]['disposition'],'not_inferred')
        self.assertEqual(rows[1]['hypothesis']['assessment'],'inconclusive')

    def test_parts_and_duplicate_conditions_remain_separate(self):
        source=self.source();h=self.linked(source)
        h['assessment_scope']={'synthesis':'synthetic','parts':[]}
        for pid,condition in [('P1','rat10'),('P2','human20')]:
            h['assessment_scope']['parts'].append({**self.claim(pid,pid),
                'evidence':[self.linked(source,condition=condition)['evidence'][0]]})
        self.save(self.wid,1,[h]);n=copy.deepcopy(h);n['assessment_scope']['parts'].pop()
        self.save(self.wid,1,[n]);row=view(self.store,self.wid,'H1')['rows'][1]
        self.assertEqual([r['part_id'] for r in row['evidence_comparison']],['','P1','P2'])
        self.assertEqual([r['comparison'] for r in row['evidence_comparison']],['same_recorded_link','same_recorded_link','not_in_current_list'])

    def test_only_published_lineage_with_explicit_corrupt_and_missing_claim_status(self):
        h=self.linked(self.source());old,_=self.save(self.wid,1,[h])
        draft,_=self.save(self.wid,1,[h],publish=False)
        current,_=self.save(self.wid,1,[self.claim('H2','New explanation')])
        with self.store.connect(True) as db:
            db.execute('UPDATE artifacts SET content=? WHERE id=?',(b'broken fixture',old))
        result=view(self.store,self.wid,'H1')
        self.assertEqual([r['decision_id'] for r in result['rows']],[current,old])
        self.assertIsNone(result['rows'][0]['hypothesis'])
        self.assertEqual(result['rows'][1]['content_status'],'unavailable_or_integrity_failure')
        self.assertNotIn(draft,json.dumps(result))
        with self.store.connect(True) as db:
            db.execute("DELETE FROM events WHERE kind='hypothesis_wording_compared' AND json_extract(body,'$.receipt_id')=?",(current,))
        gap=view(self.store,self.wid,'H1')
        self.assertEqual(len(gap['rows']),1)
        self.assertEqual(gap['lineage_gap']['reason'],'recorded_predecessor_unavailable')

    def test_model_tool_and_navigation_retain_source_without_injecting_body(self):
        source=self.source();h=self.linked(source);self.save(self.wid,1,[h])
        context=self.runner.model_context(self.wid,1,False)
        index=context['DECISION_HISTORY'][0]['hypotheses'][0]
        self.assertEqual(index['evidence_source_ids'],[source])
        self.assertNotIn('evidence',index)
        result=self.runner.read_view(self.wid,'inspect_hypothesis_history',{'hypothesis_id':'H1','offset':0,'limit':4})
        self.assertEqual(result['result'],view(self.store,self.wid,'H1'))
        for offset,limit in [(-1,4),(0,11),(True,1)]:
            with self.assertRaises(ValueError):view(self.store,self.wid,'H1',offset,limit)
