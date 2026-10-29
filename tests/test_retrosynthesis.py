import copy
import hashlib
import json
import unittest
from evida.retrosynthesis import prepare


class RetrosynthesisInputTests(unittest.TestCase):
    def setUp(self):
        raw=json.dumps({'rows':[{'id':'source-a','smiles':'CCO'}]}).encode()
        self.source={'id':'a','kind':'literature_compounds','sha256':hashlib.sha256(raw).hexdigest(),'content':raw}
        self.args={'artifact_id':'a','structures':[{'source_pointer':'/rows/0/smiles','smiles':'CCO'}],
                   'time_limit_seconds':30,'iteration_limit':50,'max_transforms':4,'random_seed':138}

    def test_changed_structure_or_bytes_cannot_reuse_source_binding(self):
        for change in ('smiles','bytes','pointer'):
            args=copy.deepcopy(self.args);source=dict(self.source)
            if change=='smiles':args['structures'][0]['smiles']='CCN'
            if change=='bytes':source['content']=b'{}'
            if change=='pointer':args['structures'][0]['source_pointer']='/rows/1/smiles'
            with self.subTest(change=change),self.assertRaises(ValueError):prepare(source,args)

    def test_explicit_parameters_preserved_and_outside_limits_rejected(self):
        bound=prepare(self.source,self.args)
        self.assertEqual(bound['source_artifact_sha256'],self.source['sha256'])
        self.assertEqual(bound['structures'][0]['candidate_id'],'source-a')
        for field,value in [('time_limit_seconds',121),('iteration_limit',201),('max_transforms',0),('random_seed',True)]:
            args={**self.args,field:value}
            with self.subTest(field=field),self.assertRaises(ValueError):prepare(self.source,args)


if __name__=='__main__':unittest.main()
