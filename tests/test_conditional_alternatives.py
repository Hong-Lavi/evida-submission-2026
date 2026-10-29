"""References/history remain valid without pretending to adjudicate science."""
import copy
import tempfile
import unittest
from pathlib import Path
from test_assessment_scope import scoped
from test_research_loop import seed
from evida.store import Store, dump
from evida.research_loop import validate_loop
from evida.evidence_history import compare_edges
from evida.model_context import hypothesis_index


class ConditionalAlternativesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.temp.name)/'state.db')
        self.wid,self.aid,self.pid,self.original=seed(self.store)
        self.p=scoped(self.original)
        h=self.p['research_loop']['hypotheses'][0]
        h['conditional_alternatives']=[{
            'id':name,'statement':statement,'part_ids':['stage'],
            'conditions':['Controlled test, matched specimen and units.'],
            'observable':'Same measured activity in the same specimen.',
            'prediction':prediction,'prediction_origin':'reconstructed_after_result',
            'assessment':'inconclusive','rationale':'Synthetic explanation, not a scientific finding.',
            'evidence':copy.deepcopy(h['evidence']),
            'relations':[{'alternative_id':other,'relation':'can_coexist','conditions':'Both effects can occur.'}],
            'unknowns':['Relative contributions unmeasured.']}
            for name,other,statement,prediction in [('amount','per_unit','Amount changes.','Proportional increase.'),
                                                  ('per_unit','amount','Per-unit activity changes.','Change after matched normalization.')]]
        self.p['research_loop']['next_checks'][0]['outcome_links']=[{
            'outcome_index':0,'effects':[{'hypothesis_id':'h1','alternative_ids':['amount'],
            'part_ids':['stage'],'relation':'unresolved','rationale':'One value cannot separate coexisting causes.'}],
            'followup_check_ids':[]}]

    def tearDown(self):
        self.temp.cleanup()

    def publish(self,p):
        validate_loop(p['research_loop'],self.store.snapshot(self.wid))
        aid=self.store.add_artifact(self.wid,'Synthetic condition test','decision_proposal',dump(p).encode(),{},bump=False)
        self.assertTrue(self.store.publish_decision(self.wid,p['based_on_state_rev'],p,aid))

    def test_same_observable_coexisting_explanations_and_single_alternative_allowed(self):
        validate_loop(self.p['research_loop'],self.store.snapshot(self.wid))
        p=copy.deepcopy(self.p);h=p['research_loop']['hypotheses'][0]
        h['conditional_alternatives']=h['conditional_alternatives'][:1]
        h['conditional_alternatives'][0]['relations']=[]
        validate_loop(p['research_loop'],self.store.snapshot(self.wid))

    def test_bad_outcome_or_cross_scope_reference_is_rejected(self):
        for field,value in [('outcome_index',100),('followup_check_ids',['missing'])]:
            loop=copy.deepcopy(self.p['research_loop']);loop['next_checks'][0]['outcome_links'][0][field]=value
            with self.assertRaises(ValueError):validate_loop(loop,self.store.snapshot(self.wid))
        for field,value in [('alternative_ids',['missing']),('part_ids',['identity']),('hypothesis_id','missing')]:
            loop=copy.deepcopy(self.p['research_loop']);loop['next_checks'][0]['outcome_links'][0]['effects'][0][field]=value
            with self.assertRaises(ValueError):validate_loop(loop,self.store.snapshot(self.wid))

    def test_publish_preserves_explanations_and_does_not_automatically_resolve_parent(self):
        original=self.store.artifact(self.wid,self.pid)['content']
        self.publish(self.p)
        after=self.store.snapshot(self.wid)['decision']['research_loop']['hypotheses'][0]
        self.assertEqual(after['conditional_alternatives'],self.p['research_loop']['hypotheses'][0]['conditional_alternatives'])
        self.assertEqual(after['assessment'],'proposed')
        self.assertEqual(self.store.artifact(self.wid,self.pid)['content'],original)

    def test_history_keeps_explanation_condition_changes_separate_from_parent(self):
        before=self.p['research_loop']['hypotheses'][0]
        after=copy.deepcopy(before)
        after['conditional_alternatives'][0]['conditions']=['Changed preparation.']
        rows=compare_edges(before,after)
        changed=[r for r in rows if r.get('explanation_id')=='amount']
        self.assertTrue(changed)
        self.assertTrue(all(r['comparison']=='recorded_link_changed' for r in changed))
        self.assertTrue(all(r['comparison']=='same_recorded_link' for r in rows if not r.get('explanation_id')))
        index=hypothesis_index(before)
        self.assertEqual(index['conditional_alternatives'][0]['conditions'],before['conditional_alternatives'][0]['conditions'])
        self.assertNotIn('evidence',index['conditional_alternatives'][0])
