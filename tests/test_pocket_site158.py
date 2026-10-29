import base64,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from evida.pocket_docking import geometry,prepare
sha=lambda x:hashlib.sha256(x).hexdigest()
def art(id,kind,body):
 raw=body if isinstance(body,bytes)else json.dumps(body).encode();return {'id':id,'kind':kind,'content':raw,'sha256':sha(raw),'meta':{}}
def pocket(points=None):
 raw='\n'.join(f'HETATM{i:5d}  C   STP A   1    {x:8.3f}{y:8.3f}{z:8.3f}  0.00  1.00'for i,(x,y,z)in enumerate(points or[(-3,-3,-3),(3,-3,3),(-3,3,3),(3,3,-3)],1))+'\n';return {'rows':[{'pocket_id':1}],'author_files':[{'name':'input_out/pockets/pocket1_vert.pqr','text':raw,'sha256':sha(raw.encode())}]}
class Tests(unittest.TestCase):
 def test_box_uses_original_bounds_and_padding(self):
  g=geometry(pocket(),1,4);self.assertEqual(g['center_angstrom'],[0,0,0]);self.assertEqual(g['box_size_angstrom'],[14,14,14]);self.assertEqual(g['minimum_angstrom'],[-3,-3,-3]);self.assertEqual(len(g['coordinate_line_numbers_1_based']),4)
 def test_zero_or_edited_pocket_rejected(self):
  b=pocket();b['rows']=[]
  with self.assertRaises(ValueError):geometry(b,1,4)
  b=pocket();b['author_files'][0]['text']+='edited'
  with self.assertRaises(ValueError):geometry(b,1,4)
 def test_geometry_not_silently_clamped(self):
  for points in [[(0,0,0)]*4,[(-30,-30,-30),(30,-30,30),(-30,30,30),(30,30,-30)]]:
   with self.assertRaises(ValueError):geometry(pocket(points),1,4)
 def test_receptor_identity_and_actual_pocket_sha(self):
  st=art('st','target_structure',{'status':'succeeded','original_cif':'original','source':{'sha256':sha(b'original')}});body={**pocket(),'status':'succeeded','source_artifact_id':'different','source_artifact_sha256':st['sha256'],'prepared_pdb':'PDB','preparation':{'selected_chains':['A']}};pk=art('p','structure_pockets',body);m=art('m','molecule_csv',b'cid,smiles\nx,CCO\n');items={'m':m,'st':st,'p':pk}
  class S:
   def artifact(self,wid,aid):return items[aid]
  a={'artifact_id':'m','molecule_artifact_sha256':m['sha256'],'structure_id':'st','structure_artifact_sha256':st['sha256'],'pocket_artifact_id':'p','pocket_artifact_sha256':pk['sha256'],'candidate_ids':['x'],'pocket_id':1,'box_padding_angstrom':4,'exhaustiveness':8,'seed':158}
  with self.assertRaises(ValueError):prepare(S(),'w',a)
  body['source_artifact_id']='st';items['p']=art('p','structure_pockets',body)
  with self.assertRaises(ValueError):prepare(S(),'w',a)
  a['pocket_artifact_sha256']=items['p']['sha256'];self.assertEqual(prepare(S(),'w',a)['geometry']['pocket_id'],1)
if __name__=='__main__':unittest.main()
