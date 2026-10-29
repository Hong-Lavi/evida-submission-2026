import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from rdkit import Chem
from rdkit.Chem import AllChem,rdMolInterchange
from meeko import MoleculePreparation,PDBQTWriterLegacy
from evida.receptor_graph import SCHEMA,pdb_atoms,molecule_from_graph
from evida.pose_interactions import prepare,stage_poses,run_author,configuration
from unittest.mock import patch
from evida.runner import Runner
from evida.gateway import Gateway
from evida.store import Store
from evida.contracts import FUNCTION_BY_NAME,model_functions
ROOT=Path(__file__).resolve().parents[1]
def sha(x):return hashlib.sha256(x.encode()).hexdigest()
def mol(smiles):
 m=Chem.AddHs(Chem.MolFromSmiles(smiles));p=AllChem.ETKDGv3();p.randomSeed=17;assert AllChem.EmbedMolecule(m,p)==0;return m
def fixture():
 m=mol('CC(=O)[O-]')
 for i,a in enumerate(m.GetAtoms()):
  p=Chem.AtomPDBResidueInfo();p.SetSerialNumber(i+1);p.SetName((a.GetSymbol()+str(i+1)).rjust(4));p.SetResidueName('SYN');p.SetChainId('A');p.SetResidueNumber(1);a.SetMonomerInfo(p)
 pdb=Chem.MolToPDBBlock(m);atoms=[]
 for i,row in enumerate(pdb_atoms(pdb)):
  a=m.GetAtomWithIdx(i);m.GetConformer().SetAtomPosition(i,row['coordinates_angstrom']);atoms.append({**row,'rdkit_atom_index':i,'atomic_number':a.GetAtomicNum(),'formal_charge':a.GetFormalCharge(),'isotope':a.GetIsotope(),'aromatic':a.GetIsAromatic()})
 graph={'schema':SCHEMA,'prepared_pdb_sha256':sha(pdb),'rdkit_mol_json':rdMolInterchange.MolToJSON(m),'atoms':atoms,'bonds':[{'begin_atom_index':b.GetBeginAtomIdx(),'end_atom_index':b.GetEndAtomIdx(),'bond_type':str(b.GetBondType()),'aromatic':b.GetIsAromatic()}for b in m.GetBonds()],'atom_count':m.GetNumAtoms(),'bond_count':m.GetNumBonds(),'hydrogen_count':sum(a.GetAtomicNum()==1 for a in m.GetAtoms()),'coordinate_policy':'Synthetic software fixture, not biological evidence'}
 return m,pdb,graph
def publish(store,wid,available=True):
 _,pdb,graph=fixture();cif='Synthetic software-only structure';sid=store.add_artifact(wid,'Synthetic structure','target_structure',json.dumps({'original_cif':cif,'source':{'sha256':sha(cif)}}).encode(),{},bump=False)
 text,ok,error=PDBQTWriterLegacy.write_string(MoleculePreparation().prepare(mol('CCO'))[0]);assert ok,error
 poses=''.join(f'MODEL {i+1}\nREMARK VINA RESULT: {-5+i}.000 0.000 0.000\n{text}ENDMDL\n'for i in range(2));raw={'receptor-prepared.pdb':pdb,'candidate-1-poses.pdbqt':poses}
 if available:raw['receptor-graph.json']=json.dumps(graph)
 value={'status':'succeeded','semantic_type':'rigid_receptor_docking_and_pose_checks','protocol':{'structure_sha256':sha(cif),'receptor_files_sha256':{n:sha(v)for n,v in raw.items()if n.startswith('receptor')}},'rows':[{'candidate_id':'synthetic_A','status':'succeeded','input_smiles':'CCO','pose_file':'candidate-1-poses.pdbqt','pose_count':2,'pose_scores_kcal_mol':[-5.,-4.]}],'raw_output_files':raw}
 aid=store.add_artifact(wid,'Synthetic saved poses, no docking performed','molecular_docking',json.dumps(value).encode(),{'consumed_artifacts':[sid],'synthetic':True},bump=False)
 return aid,sid,{'artifact_id':aid,'structure_id':sid,'candidate_ids':['synthetic_A'],'interactions':['Hydrophobic','HBDonor','HBAcceptor','VdWContact'],'count':True,'vicinity_cutoff_angstrom':6.0}
class GraphTests(unittest.TestCase):
 def test_identity_and_tamper_rejection(self):
  original,pdb,g=fixture();restored=molecule_from_graph(g,pdb);self.assertEqual(Chem.MolToSmiles(restored),Chem.MolToSmiles(original));self.assertEqual(restored.GetNumAtoms(),original.GetNumAtoms())
  for field in ['source','charge','bond','duplicate_bond','hydrogens','coordinates','native_coordinates']:
   v=copy.deepcopy(g);source=pdb
   if field=='source':source+='\n'
   elif field=='charge':v['atoms'][0]['formal_charge']+=1
   elif field=='bond':v['bonds'][0]['bond_type']='TRIPLE'
   elif field=='duplicate_bond':v['bonds'][1]=v['bonds'][0]
   elif field=='hydrogens':v['hydrogen_count']+=1
   elif field=='coordinates':v['atoms'][0]['coordinates_angstrom'][0]+=1
   else:
    m=rdMolInterchange.JSONToMols(v['rdkit_mol_json'])[0];m.GetConformer().SetAtomPosition(0,(20,20,20));v['rdkit_mol_json']=rdMolInterchange.MolToJSON(m)
   with self.subTest(field=field),self.assertRaises(ValueError):molecule_from_graph(v,source)
 def test_registration_and_strict_inputs(self):
  self.assertIn('inspect_pose_interactions',FUNCTION_BY_NAME);self.assertTrue(any(f['name']=='inspect_pose_interactions'for f in model_functions()))
  with tempfile.TemporaryDirectory()as t:
   s=Store(Path(t)/'s.db');w=s.create('Synthetic software fixture')['id'];aid,_,a=publish(s,w)
   for key,value in [('count',False),('interactions',['invented']),('candidate_ids',['missing']),('vicinity_cutoff_angstrom',float('nan'))]:
    with self.subTest(key=key),self.assertRaises(ValueError):prepare(s,w,{**a,key:value})
   with s.connect(True)as db:db.execute('UPDATE artifacts SET sha256=? WHERE id=?',('0'*64,aid))
   with self.assertRaises(ValueError):prepare(s,w,a)
class RetentionFailureTests(unittest.TestCase):
 def test_optional_graph_capture_failure_keeps_native_preparation_and_explicit_unavailable(self):
  from evida.receptor_graph_worker import run
  from meeko import Polymer
  old_build=Polymer._build_padded_mols;old_pdb=Polymer.to_pdb
  with tempfile.TemporaryDirectory()as t:
   work=Path(t)
   def native():
    (work/'receptor.pdbqt').write_text('Synthetic native preparation already completed')
    (work/'receptor-prepared.pdb').write_text('Synthetic native PDB already completed')
   with patch('evida.receptor_graph_worker.main',side_effect=native):run(work)
   self.assertEqual((work/'receptor.pdbqt').read_text(),'Synthetic native preparation already completed')
   failure=json.loads((work/'receptor-graph-unavailable.json').read_text());self.assertEqual(failure['status'],'unavailable');self.assertTrue(failure['native_preparation_preserved']);self.assertFalse((work/'receptor-graph.json').exists())
  self.assertIs(Polymer._build_padded_mols,old_build);self.assertIs(Polymer.to_pdb,old_pdb)

class AuthorBoundaryTests(unittest.TestCase):
 def test_timeout_cancel_and_output_limit_retain_every_source_pose(self):
  import subprocess
  actual_popen=subprocess.Popen;cfg=configuration()
  with tempfile.TemporaryDirectory()as t:
   s=Store(Path(t)/'s.db');w=s.create('Synthetic process boundary fixture')['id'];_,_,a=publish(s,w);bundle=prepare(s,w,a)
   for mode in ['timeout','cancelled','output_limit']:
    request=stage_poses(bundle,Path(t)/('inputs_'+mode));work=Path(t)/mode;bounded=dict(cfg)
    if mode=='timeout':bounded['timeout_seconds']=0.000001
    if mode=='output_limit':bounded['output_limit_bytes']=1
    def launch(*args,**kwargs):
     process=actual_popen(*args,**kwargs)
     if mode=='cancelled':(work/'pose-interactions.cancel').write_text('operator cancellation fixture')
     return process
    with self.subTest(mode=mode),patch('evida.pose_interactions.configuration',return_value=bounded),patch('evida.pose_interactions.subprocess.Popen',side_effect=launch):
     body=run_author(request,work)
     self.assertEqual(body['status'],'failed');self.assertEqual(body['error'],mode,(work/'worker.log').read_text());self.assertEqual(len(body['rows']),2)
     self.assertEqual([r['original_vina_score_kcal_mol']for r in body['rows']],[-5.,-4.])

class WorkerTests(unittest.TestCase):
 def test_registered_worker_all_poses_reading_mapping_and_cache(self):self.exercise(True)
 def test_legacy_missing_graph_is_failed_and_not_reprepared(self):self.exercise(False)
 def exercise(self,available):
  with tempfile.TemporaryDirectory()as t:
   s=Store(Path(t)/'s.db');w=s.create('Synthetic contact software fixture')['id'];aid,sid,a=publish(s,w,available);r=Runner(ROOT,s,Gateway(json.loads((ROOT/'configs/api_policy.json').read_text()),False),Path(t)/'attempts')
   try:
    r.validate_tool(w,'pose_interactions',a);key=r.cache_key(w,'pose_interactions',a);jid=s.enqueue(w,1,'pose_interactions',a,key);rid=r.run_tool_job(jid,False)
    if not rid:self.fail(str(s.snapshot(w)['jobs']))
    artifact=s.artifact(w,rid);v=json.loads(artifact['content']);self.assertEqual(set(artifact['meta']['consumed_artifacts']),{aid,sid})
    if available:
     self.assertEqual(v['status'],'succeeded',v);self.assertEqual(len(v['rows']),2);self.assertEqual([x['original_vina_score_kcal_mol']for x in v['rows']],[-5.,-4.]);self.assertTrue(all(x['original_atom_mapping']and not x['rigid_fit']for x in v['rows']))
     reading=r.read_view(w,'inspect_artifact',{'artifact_id':rid,'offset':0,'limit':1});self.assertEqual(reading['result']['total_rows'],2);self.assertTrue(reading['result']['has_more'])
     again=s.enqueue(w,1,'pose_interactions',a,key);self.assertEqual(r.run_tool_job(again,False),rid);self.assertEqual(len(list((Path(t)/'attempts').glob('*/request.json'))),1)
    else:
     self.assertEqual(v['status'],'failed');self.assertEqual(v['availability'],'missing_authoritative_receptor_graph');self.assertFalse(list((Path(t)/'attempts').glob('*/prolif/request.json')))
   finally:r.pool.shutdown(wait=True);r.explanation_pool.shutdown(wait=True)
if __name__=='__main__':unittest.main()
