"""Isolated ProLIF CPU contact worker over already prepared immutable inputs."""
import collections
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time


def file_digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb')as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def normalized(value):
    import numpy as np
    if isinstance(value,dict):return {str(k):normalized(v)for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [normalized(v)for v in value]
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    return value


def save(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,allow_nan=False));temp.replace(path)


def main():
    wrapper_path,output=map(Path,sys.argv[1:]);wrapper=json.loads(wrapper_path.read_text());request=wrapper['input']
    versions={key:importlib.metadata.version(key)for key in wrapper['expected_versions']}
    if versions!=wrapper['expected_versions']:raise ValueError('Author runtime versions changed.')
    import prolif as plf
    from rdkit import Chem
    from receptor_graph import molecule_from_graph
    for pathkey,shakey in [('prepared_protein_path','prepared_protein_sha256'),('graph_path','graph_sha256'),('sdf_path','sdf_sha256')]:
        if file_digest(request[pathkey])!=request[shakey]:raise ValueError('Staged contact input SHA mismatch: '+pathkey)
    graph=json.loads(Path(request['graph_path']).read_text())
    protein=plf.Molecule(molecule_from_graph(graph,Path(request['prepared_protein_path']).read_text()))
    protein_atoms={a['rdkit_atom_index']:a for a in graph['atoms']}
    original_chains={prepared:original for original,prepared in request.get('chain_renaming',{}).items()}
    poses=list(plf.sdf_supplier(request['sdf_path']))
    if len(poses)!=len(request['poses']):raise ValueError('Saved SDF pose count changed.')
    body={'status':'running','semantic_type':'saved_pose_interaction_contacts_not_affinity',
        'rows':[],'versions':versions,'parameters':{key:request[key]for key in ('interactions','count','vicinity_cutoff_angstrom')},
        'graph_summary':{'schema':graph['schema'],'atom_count':graph['atom_count'],'bond_count':graph['bond_count'],
            'hydrogen_count':graph['hydrogen_count'],'bond_inference':False,'force':False,
            'coordinate_policy':graph['coordinate_policy']},'total_poses':len(poses)}
    progress=output.parent/'progress.json';save(progress,body)
    fingerprint=plf.Fingerprint(interactions=request['interactions'],count=True,vicinity_cutoff=request['vicinity_cutoff_angstrom'])
    for pose,meta in zip(poses,request['poses']):
        row={**meta,'contacts':[]}
        try:
            if pose is None or pose.GetProp('_Name')!=meta['pose_id']:raise ValueError('Saved pose identity changed.')
            parent=Chem.MolFromSmiles(meta['exact_input_smiles'])
            if parent is None or Chem.MolToSmiles(Chem.RemoveHs(pose))!=Chem.MolToSmiles(parent):
                raise ValueError('Cross-runtime ligand graph/charge changed.')
            # Source Meeko atom indices must still identify the same atoms in the SDF.
            atom_map={entry['rdkit_atom_index']:entry for entry in meta['original_atom_mapping']}
            for mapping in meta['original_atom_mapping']:
                atom=pose.GetAtomWithIdx(mapping['rdkit_atom_index'])
                if atom.GetAtomicNum()!=mapping['atomic_number']:raise ValueError('Saved pose atom index changed.')
                point=pose.GetConformer().GetAtomPosition(mapping['rdkit_atom_index'])
                if sum((a-b)**2 for a,b in zip(point,mapping['original_pdbqt_coordinate_angstrom']))**0.5>0.001:
                    raise ValueError('Saved pose atom coordinates changed after SDF transfer.')
            interactions=fingerprint.generate(pose,protein,metadata=True)
            for(lig_res,prot_res),kinds in interactions.items():
                for kind,occurrences in kinds.items():
                    for occurrence in occurrences:
                        value=normalized(occurrence)
                        value['protein_atom_identity']=[{**{k:protein_atoms[i][k]for k in ('rdkit_atom_index','serial','name','residue_name','chain','residue_number','insertion_code','formal_charge')},
                            'original_chain':original_chains.get(protein_atoms[i]['chain'])}for i in value['parent_indices']['protein']]
                        value['ligand_atom_identity']=[{'rdkit_atom_index':i,
                            'pdbqt_serial':atom_map[i]['pdbqt_serial']if i in atom_map else None,
                            'pdbqt_atom_name':atom_map[i]['pdbqt_atom_name']if i in atom_map else None,
                            'source':'preserved_PDBQT_atom'if i in atom_map else'reconstructed_nonpolar_hydrogen'}for i in value['parent_indices']['ligand']]
                        row['contacts'].append({'ligand_residue':str(lig_res),'protein_residue':str(prot_res),
                            'interaction_type':kind,**value})
            row.update(status='computed',contact_occurrences=len(row['contacts']),
                unique_residue_type_bits=len({(c['protein_residue'],c['interaction_type'])for c in row['contacts']}),
                interaction_type_counts=dict(collections.Counter(c['interaction_type']for c in row['contacts'])))
        except Exception as error:row.update(status='contact_failure',error_type=type(error).__name__,error=str(error)[:600])
        body['rows'].append(row);body['completed_poses']=len(body['rows']);save(progress,body)
    computed=sum(row['status']=='computed'for row in body['rows'])
    body['status']='succeeded'if computed==len(poses)else'partial'if computed else'failed'
    save(output,body)

if __name__=='__main__':main()
