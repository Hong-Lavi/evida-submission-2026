"""Synthetic boundary tests; no trial predictions, labels, weights or GPU access."""
import unittest
import sys
from unittest.mock import patch
import pre_score_gate as g
sys.path.insert(0,str(g.TRIAL))
import metrics_common as m

def fixture():
    protocol={'arms':['chemeleon_finetuned','matched_random'],
              'tasks':[{'task':f'SYNTH{i}'} for i in range(30)]}
    completion={'status':'prediction_generation_finished','protocol_sha256':g.EXPECTED,
                'retries':0,'official_test_labels_read':False,
                'attempts':[{'task':t['task'],'arm':a,'status':'completed','returncode':0,
                             'prediction_sha256':'synthetic-hash'} for t in protocol['tasks'] for a in protocol['arms']]}
    return protocol,completion

class Gates(unittest.TestCase):
    def test_complete_60(self):
        p,c=fixture(); self.assertEqual(len(g.validate_terminal(p,c)),60)

    def assert_no_artifacts_open(self, mutate):
        p,c=fixture(); mutate(c)
        # Real gate is entered; only protocol, protocol receipt and completion may load.
        allowed={'protocol.json':p,'protocol-receipt.json':{'sha256':g.EXPECTED},'completion.json':c}
        seen=[]
        def read(path):
            seen.append(path.name)
            if path.name not in allowed: raise AssertionError('Raw artifact accessed before terminal gate')
            return allowed[path.name]
        with patch.object(g,'sha',return_value=g.EXPECTED),patch.object(g,'load',side_effect=read):
            with self.assertRaises(ValueError): g.run({})
        self.assertEqual(seen,['protocol-receipt.json','protocol.json','completion.json'])

    def test_late_missing_stops_before_any_prediction(self):
        self.assert_no_artifacts_open(lambda c:c['attempts'].pop())

    def test_late_running_stops_before_any_prediction(self):
        self.assert_no_artifacts_open(lambda c:c['attempts'][-1].update(status='running'))

    def test_late_unknown_status_stops_before_any_prediction(self):
        self.assert_no_artifacts_open(lambda c:c['attempts'][-1].update(status='corrupt-unrecognized'))

    def test_late_completed_without_hash(self):
        self.assert_no_artifacts_open(lambda c:c['attempts'][-1].update(prediction_sha256=None))

    def test_skipped_with_prediction_rejected(self):
        self.assert_no_artifacts_open(lambda c:c['attempts'][-1].update(status='not_started_time_budget',returncode=None))

    def test_all_skipped_keep60(self):
        p,c=fixture()
        for r in c['attempts']:r.update(status='not_started_time_budget',returncode=None,prediction_sha256=None)
        self.assertEqual(len(g.validate_terminal(p,c)),60)

    def validation_fixture(self):
        d={'train':[{'p_activity':1.},{'p_activity':3.}],
           'validation':[{'p_activity':1.},{'p_activity':2.},{'p_activity':3.}]}
        r={'validation_predictions':[{'prediction':1.5},{'prediction':2.5},{'prediction':3.5}],
           'validation_mae':.5,'mean_validation_mae':2/3,'validation_spearman':1.,'usable':True}
        return d,r

    def test_independent_valid_metrics(self):
        d,r=self.validation_fixture(); self.assertTrue(all(g.validation_check(d,r).values()))

    def test_false_mean_baseline_rejected(self):
        d,r=self.validation_fixture();r['mean_validation_mae']=4.
        with self.assertRaisesRegex(ValueError,'Training-mean'):g.validation_check(d,r)

    def test_false_eligibility_rejected(self):
        d,r=self.validation_fixture();r['usable']=False
        with self.assertRaisesRegex(ValueError,'Eligibility'):g.validation_check(d,r)

    def test_constant_predictions_match_native_zero_spearman(self):
        d,r=self.validation_fixture()
        r.update(validation_predictions=[{'prediction':2.}]*3,validation_mae=2/3,
                 validation_spearman=0.,usable=False)
        self.assertTrue(all(g.validation_check(d,r).values()))

    def test_cluster_interval_keeps_two_endpoints_together(self):
        rows=[{'task':name,'left':{'mae':delta},'right':{'mae':0.}}
              for name,delta in [('A_Ki',1.),('A_EC50',3.),('B_Ki',8.)]]
        v=m.cluster_interval(rows,'left','right','mae',{'bootstrap_seed':20261011,'bootstrap_repetitions':5000})
        self.assertEqual((v['mean_difference'],v['tasks'],v['target_clusters']),(4.,3,2))
        self.assertEqual(v['ci95'],[2.,8.])

    def test_metric_id_ties_are_deterministic(self):
        import numpy as np
        ids=[f'id{i:02d}' for i in range(12)]
        y=np.array([2.]*10+[1.]*2); p=np.zeros(12)
        v=m.metrics(y,p,ids,m.spearman)
        self.assertEqual(v['top10_recall'],1.)
        self.assertEqual(v['spearman'],0.)
        self.assertEqual(v['best_true_activity_in_selected10'],2.)

    def test_spearman_ties_independent_scipy(self):
        from scipy.stats import spearmanr
        y=[1.,1.,2.,3.]; p=[4.,2.,2.,1.]
        self.assertAlmostEqual(m.spearman(y,p),spearmanr(y,p).statistic,places=14)

if __name__=='__main__':unittest.main()
