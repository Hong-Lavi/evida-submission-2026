import base64
import copy
import hashlib
import json
import unittest
from evida.protein_computation import prepare


def source(kind,body):
    raw=json.dumps(body).encode()
    return {'id':'a','kind':kind,'content':raw,'sha256':hashlib.sha256(raw).hexdigest()}


class ProteinInputTests(unittest.TestCase):
    def setUp(self):
        self.body={'status':'succeeded','original_cif':'retained-source-fixture',
            'source':{'sha256':hashlib.sha256(b'retained-source-fixture').hexdigest()},
            'rows':[{'kind':'protein_chain','chain':'A','internal_numbering_gaps':[]}]}
        self.args={'artifact_id':'a','chain_ids':['A'],'temperature_kelvin':300,'ph':7.,
            'steps':500,'timestep_femtoseconds':2.,'random_seed':133}

    def test_unknown_or_duplicate_chains_and_changed_source_rejected(self):
        for chains in [['B'],['A','A']]:
            with self.subTest(chains=chains),self.assertRaises(ValueError):
                prepare(source('target_structure',self.body),{**self.args,'chain_ids':chains},'protein_dynamics')
        broken=copy.deepcopy(self.body);broken['original_cif']='changed'
        with self.assertRaises(ValueError):prepare(source('target_structure',broken),self.args,'protein_dynamics')

    def test_unmodeled_internal_gap_does_not_silently_become_complete_dynamics(self):
        body=copy.deepcopy(self.body);body['rows'][0]['internal_numbering_gaps']=[[20,25]]
        with self.assertRaises(ValueError):prepare(source('target_structure',body),self.args,'protein_dynamics')
        # Pocket geometry of the observed atoms remains separately callable.
        prepare(source('target_structure',body),{'artifact_id':'a','chain_ids':['A']},'structure_pockets')

    def test_trajectory_requires_completed_source_and_exact_binary(self):
        pdb='ATOM fixture';dcd=b'DCD fixture'
        body={'status':'succeeded','simulation_conditions':{'total_picoseconds':1.},'trajectory_files':{
            'topology_pdb':{'text':pdb,'sha256':hashlib.sha256(pdb.encode()).hexdigest()},
            'trajectory_dcd':{'base64':base64.b64encode(dcd).decode(),'sha256':hashlib.sha256(dcd).hexdigest()}}}
        args={'artifact_id':'a','alignment':'ca'}
        self.assertEqual(prepare(source('protein_dynamics',body),args,'trajectory_analysis')['simulation_conditions']['total_picoseconds'],1.)
        body['status']='partial'
        with self.assertRaises(ValueError):prepare(source('protein_dynamics',body),args,'trajectory_analysis')
        body['status']='succeeded';body['trajectory_files']['trajectory_dcd']['sha256']='wrong'
        with self.assertRaises(ValueError):prepare(source('protein_dynamics',body),args,'trajectory_analysis')


if __name__=='__main__':unittest.main()
