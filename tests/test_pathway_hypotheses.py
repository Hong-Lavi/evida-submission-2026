from copy import deepcopy
import unittest
from evida.pathway_hypotheses import prepare


class PathwayInputTests(unittest.TestCase):
    def setUp(self):
        self.source = {'status':'succeeded','semantic_type':'inferred_regulon_activity',
            'rows':[{'source':'TF','resource':'dorothea','score':-2.},
                    {'source':'TF','resource':'collectri','score':3.},
                    {'source':'OTHER','resource':'dorothea','score':1.}],
            'conditions':['Synthetic unit-test input, not biological evidence']}
        self.prior = [{'source':a,'target':b,'interaction':sign} for a,sign,b in
            [('UP1',-1,'TF'),('UP2',1,'UP1'),('TF',1,'DOWN')]]
        self.arguments={'artifact_id':'source','resource':'dorothea','tf_ids':['TF'],
            'selection_reason':'Synthetic parser test','ancestor_steps':1,'conditions':['Synthetic']}

    def test_choice_and_declared_boundary_do_not_erase_pool_or_expand_downstream(self):
        original=deepcopy(self.source)
        result=prepare(self.arguments,self.source,self.prior)
        self.assertEqual(result['selected_inferred_observations'][0]['score'],-2.)
        self.assertEqual(result['network'],[self.prior[0]])
        self.assertEqual(result['search_scope']['unselected_TF_resource_rows_retained_in_source'],2)
        self.assertFalse(result['search_scope']['global_search_complete'])
        self.assertEqual(self.source,original)
        more=prepare({**self.arguments,'ancestor_steps':2},self.source,self.prior)
        self.assertEqual(more['network'],self.prior[:2])

    def test_absent_scores_priors_or_failed_source_are_not_filled_as_zero(self):
        with self.assertRaises(ValueError):prepare({**self.arguments,'tf_ids':['MISSING']},self.source,self.prior)
        with self.assertRaises(ValueError):prepare({**self.arguments,'tf_ids':['OTHER']},self.source,self.prior)
        with self.assertRaises(ValueError):prepare(self.arguments,{**self.source,'status':'failed'},self.prior)
        bad=deepcopy(self.source);bad['rows'][0]['score']=float('nan')
        with self.assertRaises(ValueError):prepare(self.arguments,bad,self.prior)

    def test_compute_review_boundary_preserves_no_biological_negative_claim(self):
        edges=[{'source':'UP'+str(i),'interaction':1,'target':'TF'} for i in range(15001)]
        with self.assertRaisesRegex(ValueError,'경로 없음의 근거가 아닙니다'):
            prepare(self.arguments,self.source,edges)
