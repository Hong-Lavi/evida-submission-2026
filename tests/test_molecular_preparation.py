"""Source/parameter/failure guarantees for new author computational adapters."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from evida.molecular_preparation import prepare,run,configuration
from evida.contracts import FUNCTION_BY_NAME,model_functions

def source(smiles='CCCOCCC'):
 raw=json.dumps({'rows':[{'id':'fixture','smiles':smiles}]}).encode()
 return {'id':'source','kind':'literature_compounds','sha256':hashlib.sha256(raw).hexdigest(),'content':raw,'meta':{}}

def args(smiles='CCCOCCC',gypsum=False):
 result={'artifact_id':'source','structures':[{'source_pointer':'/rows/0/smiles','smiles':smiles}]}
 if gypsum:result.update(ph_min=7.4,ph_max=7.4,precision=1.0,max_variants=4,random_seed=144)
 return result

class MolecularTests(unittest.TestCase):
 def test_saved_structure_is_exact_not_model_rewritten(self):
  s=source();a=args();a['structures'][0]['smiles']='CCN'
  with self.assertRaises(ValueError):prepare(s,a,'synthetic_complexity')
  s['content']+=b' '
  with self.assertRaises(ValueError):prepare(s,args(),'synthetic_complexity')
 def test_seed_and_branch_limits_explicit(self):
  for key,value in [('random_seed',True),('random_seed',-1),('max_variants',17),('ph_min',float('nan'))]:
   a=args(gypsum=True);a[key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):prepare(source(),a,'molecule_preparation')
 def test_model_or_path_injection_rejected(self):
  a=args();a['weights']='/tmp/unapproved'
  with self.assertRaises(ValueError):prepare(source(),a,'synthetic_complexity')
 def test_both_functions_reach_actual_menu(self):
  menu={f['name']for f in model_functions()}
  for name in ('score_synthetic_complexity','prepare_molecular_states'):
   self.assertIn(name,FUNCTION_BY_NAME);self.assertIn(name,menu)
 def test_invalid_structure_is_failed_not_zero_complexity(self):
  with tempfile.TemporaryDirectory()as d:
   body=run(prepare(source('not-a-molecule'),args('not-a-molecule'),'synthetic_complexity'),Path(d)/'run')
   self.assertEqual(body['status'],'failed');self.assertEqual(body['rows'][0]['status'],'author_failure')
   self.assertNotIn('scscore',body['rows'][0])
 def test_real_author_reference_values_with_scalar_compatibility(self):
  for smi,expected in [('CCCOCCC',1.4322608053642631),('CCCNc1ccccc1',1.8913059057522013)]:
   with self.subTest(smi=smi),tempfile.TemporaryDirectory()as d:
    b=run(prepare(source(smi),args(smi),'synthetic_complexity'),Path(d)/'run')
    self.assertEqual(b['status'],'succeeded');self.assertAlmostEqual(b['rows'][0]['scscore'],expected,places=12)
 def test_timeout_retains_all_missing_rows(self):
  cfg=configuration();cfg['timeout_seconds']=.0001
  with tempfile.TemporaryDirectory()as d,patch('evida.molecular_preparation.configuration',return_value=cfg):
   b=run(prepare(source(),args(),'synthetic_complexity'),Path(d)/'run')
   self.assertEqual(b['status'],'failed');self.assertEqual(b['error'],'timeout')
   self.assertEqual(len(b['rows']),1);self.assertEqual(b['rows'][0]['status'],'not_completed')

if __name__=='__main__':unittest.main()
