"""Source-bound all-pose ProLIF contact analysis, never an affinity ranking."""
import hashlib
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import time

INTERACTIONS = {'Hydrophobic','HBDonor','HBAcceptor','PiStacking','Anionic','Cationic','CationPi','PiCation','VdWContact'}
LIMITS = ['Contacts are geometry/chemical-state descriptors, not affinity, efficacy, BBB or probabilities.',
          'Overlapping contact types and atom groups are not independent biological evidence.',
          'All saved poses, original Vina scores/ranks and failures are retained; no winning candidate inferred.',
          'Protein graph comes from recorded Meeko preparation; original docking remains immutable.']

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def file_digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()

def kill_group(process):
    # The session leader may already have exited while a descendant holds its pipe.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

def configuration():
    path = Path(__file__).parents[1] / 'configs/pose-interactions-runtime.json'
    cfg = json.loads(path.read_text())
    # Runtime locations are deployment-owned, never supplied by the model or HTTP arguments.
    for name, expected in cfg['assets'].items():
        if file_digest(name) != expected:
            raise ValueError('ProLIF runtime asset fingerprint mismatch: ' + Path(name).name)
    return cfg

def run_author(request, work):
    """Use only fixed runtime manifest. Fixed work/pose-interactions.cancel is the operator cancel seam."""
    cfg = configuration()
    work = Path(work); work.mkdir(exist_ok=False)
    request_path, output = work / 'request.json', work / 'result.json'
    request_path.write_text(json.dumps({'input': request, 'expected_versions': cfg['packages']}))
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'CUDA_VISIBLE_DEVICES': '',
           'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'OMP_NUM_THREADS': '1',
           'OPENBLAS_NUM_THREADS': '1', 'XDG_CACHE_HOME': str(work / 'cache')}
    started = time.monotonic()
    receipt = {'manifest_sha256': digest((Path(__file__).parents[1] / 'configs/pose-interactions-runtime.json').read_bytes()),
               'timeout_seconds': cfg['timeout_seconds'], 'output_limit_bytes': cfg['output_limit_bytes'],
               'log_limit_bytes': cfg['log_limit_bytes'], 'cancel_file': 'pose-interactions.cancel'}
    (work / 'runtime-receipt.json').write_text(json.dumps(receipt))
    process = subprocess.Popen([cfg['python'], '-B', str(Path(__file__).with_name('pose_interactions_worker.py')),
                                str(request_path), str(output)], cwd=work, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
    reason = None; count = 0
    selector = selectors.DefaultSelector(); selector.register(process.stdout, selectors.EVENT_READ)
    try:
        with (work / 'worker.log').open('xb') as log:
            while process.poll() is None or selector.get_map():
                if (work / 'pose-interactions.cancel').exists(): reason = 'cancelled'
                elif time.monotonic() - started > cfg['timeout_seconds']: reason = 'timeout'
                elif any(p.exists() and p.stat().st_size > cfg['output_limit_bytes'] for p in (output, work / 'progress.json')): reason = 'output_limit'
                if reason:
                    kill_group(process)
                    break
                for key, _ in selector.select(0.05):
                    block = os.read(key.fileobj.fileno(), 8192)
                    if not block: selector.unregister(key.fileobj); continue
                    log.write(block[:max(0, cfg['log_limit_bytes'] - count)]); count += len(block)
                    if count > cfg['log_limit_bytes']: reason = 'log_limit'
    finally:
        # Close the pipe without waiting for descendants to close inherited copies.
        selector.close(); process.stdout.close()
        kill_group(process)
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            raise RuntimeError('Author process did not exit within bounded cleanup.')
    if any(p.exists() and p.stat().st_size > cfg['output_limit_bytes'] for p in (output, work / 'progress.json')):
        reason = 'output_limit'
    if reason or process.returncode or not output.exists():
        # Completed rows are committed incrementally, including interrupted runs.
        progress = work / 'progress.json'
        body = json.loads(progress.read_text()) if progress.exists() and progress.stat().st_size <= cfg['output_limit_bytes'] else {'rows': []}
        if progress.exists():
            body['retained_progress'] = {'file': 'progress.json', 'sha256': file_digest(progress),
                                         'bytes': progress.stat().st_size}
        completed = {row['pose_id'] for row in body.get('rows', [])}
        body['rows'].extend({**row, 'contacts': [],
                             'status': 'not_completed', 'reason': reason or 'author_worker_failure'}
                            for row in request['poses'] if row['pose_id'] not in completed)
        body['parameters'] = {k: request[k] for k in ('interactions', 'count', 'vicinity_cutoff_angstrom')}
        body.update(status='failed', error=reason or 'author_worker_failure', limits=LIMITS,
                    semantic_type='saved_pose_interaction_contacts_not_affinity')
    else:
        body = json.loads(output.read_text())
    body['runtime_receipt'] = receipt
    body['runtime_fingerprint'] = {'packages': cfg['packages'], 'python_version': cfg['python_version'],
                                   'assets_sha256': digest(json.dumps(cfg['assets'], sort_keys=True).encode()),
                                   'asset_count': len(cfg['assets'])}
    body['source_artifact_id'] = request['source_artifact_id']
    body['source_artifact_sha256'] = request['source_artifact_sha256']
    body['elapsed_seconds'] = round(time.monotonic() - started, 6)
    body['model_calls'] = 0; body['gpu_used'] = False
    return body


def verified(store, wid, aid):
    source=store.artifact(wid,aid)
    if digest(source['content'])!=source['sha256']:
        raise ValueError('Store source content SHA mismatch.')
    return source,json.loads(source['content'])


def prepare(store,wid,args):
    if set(args)!={'artifact_id','structure_id','candidate_ids','interactions','count','vicinity_cutoff_angstrom'}:
        raise ValueError('Explicit named source and contact parameters required.')
    ids,kinds=args['candidate_ids'],args['interactions']
    if not isinstance(ids,list)or not 1<=len(ids)<=12 or not all(isinstance(v,str)and v for v in ids)or len(set(ids))!=len(ids):
        raise ValueError('Choose unique saved candidate IDs,1..12.')
    if not isinstance(kinds,list)or not kinds or not all(isinstance(k,str)for k in kinds)or len(set(kinds))!=len(kinds)or set(kinds)-INTERACTIONS:
        raise ValueError('Choose explicit supported interaction types.')
    if args['count']is not True:raise ValueError('All atom groups require count=True.')
    cutoff=args['vicinity_cutoff_angstrom']
    if type(cutoff)not in (float,int)or not math.isfinite(cutoff)or not 2<=cutoff<=10:
        raise ValueError('Finite vicinity cutoff2..10 angstrom required.')
    parent,docking=verified(store,wid,args['artifact_id']);structure_source,structure=verified(store,wid,args['structure_id'])
    if parent['kind']!='molecular_docking'or docking.get('semantic_type')!='rigid_receptor_docking_and_pose_checks'or structure_source['kind']!='target_structure':
        raise ValueError('Saved docking and exact target structure required.')
    if args['structure_id']not in parent['meta'].get('consumed_artifacts',[]):
        raise ValueError('Target structure was not consumed by this docking.')
    target_sha=digest(structure['original_cif'].encode());protocol=docking['protocol']
    if target_sha!=structure['source']['sha256']or target_sha!=protocol['structure_sha256']:
        raise ValueError('Exact target source SHA mismatch.')
    selected=[(i,r)for i,r in enumerate(docking['rows'])if r['candidate_id']in ids]
    if len(selected)!=len(ids)or len({r['candidate_id']for _,r in selected})!=len(ids):
        raise ValueError('Missing or ambiguous saved candidate identity.')
    raw=docking.get('raw_output_files',{});expected=protocol.get('receptor_files_sha256',{})
    availability='ready'
    for name in ('receptor-prepared.pdb','receptor-graph.json'):
        if not isinstance(raw.get(name),str)or not expected.get(name):availability='missing_authoritative_receptor_graph'
        elif digest(raw[name].encode())!=expected[name]:raise ValueError('Recorded receptor file SHA mismatch: '+name)
    rows=[]
    for index,row in selected:
        record={'source_pointer':f'/rows/{index}','candidate_id':row['candidate_id'],
                'saved_status':row.get('status'),'original_error':row.get('error')}
        if row.get('status')=='succeeded':
            filename=row.get('pose_file','');text=raw.get(filename);scores=row.get('pose_scores_kcal_mol')
            if not re.fullmatch(r'candidate-[1-9][0-9]*-poses\.pdbqt',filename)or not isinstance(text,str):
                raise ValueError('Recorded pose file missing.')
            if not isinstance(scores,list)or len(scores)!=row.get('pose_count')or not 1<=len(scores)<=5 or any(type(v)not in (int,float)or not math.isfinite(v)for v in scores):
                raise ValueError('Saved pose count/score correspondence differs.')
            record.update(exact_input_smiles=row['input_smiles'],pose_file=filename,
                          pose_pdbqt=text,pose_pdbqt_sha256=digest(text.encode()),pose_scores_kcal_mol=scores)
        rows.append(record)
    return {'source_artifact_id':parent['id'],'source_artifact_sha256':parent['sha256'],
            'structure_artifact_id':structure_source['id'],'structure_artifact_sha256':structure_source['sha256'],
            'target_source_sha256':target_sha,'availability':availability,'rows':rows,
            'chain_renaming':protocol.get('preparation',{}).get('chain_renaming',{}),
            'prepared_protein_pdb':raw.get('receptor-prepared.pdb'),
            'prepared_protein_sha256':expected.get('receptor-prepared.pdb'),
            'graph_json':raw.get('receptor-graph.json'),'graph_sha256':expected.get('receptor-graph.json'),
            **{k:args[k]for k in ('interactions','count','vicinity_cutoff_angstrom')}}


def cache_key(root,bundle,args):
    cfg=configuration()if bundle['availability']=='ready'else{'author_not_invoked':'missing_authoritative_receptor_graph'}
    return digest(json.dumps({'arguments':args,'source_sha':bundle['source_artifact_sha256'],
        'structure_sha':bundle['structure_artifact_sha256'],'runtime':cfg,
        'code':{name:file_digest(Path(root)/'evida'/name)for name in ('pose_interactions.py','pose_interactions_worker.py','receptor_graph.py','science.py','runner.py')}},sort_keys=True).encode())


def unavailable(bundle):
    return {'status':'failed','availability':bundle['availability'],
        'error':'Authoritative prepared receptor graph unavailable; original records were not re-prepared.',
        'semantic_type':'saved_pose_interaction_contacts_not_affinity','source_artifact_id':bundle['source_artifact_id'],
        'source_artifact_sha256':bundle['source_artifact_sha256'],
        'target_source_sha256':bundle['target_source_sha256'],
        'parameters':{k:bundle[k]for k in ('interactions','count','vicinity_cutoff_angstrom')},
        'structure_artifact_id':bundle['structure_artifact_id'],'structure_artifact_sha256':bundle['structure_artifact_sha256'],
        'rows':[{'source_pointer':r['source_pointer'],'candidate_id':r['candidate_id'],
                 'status':'unavailable_authoritative_graph','original_pose_scores_kcal_mol':r.get('pose_scores_kcal_mol'),
                 'contacts':[]}for r in bundle['rows']],
        'limits':LIMITS,'next_action':'Use a separately retained, explicitly prepared receptor graph; no historical scientific artifact is modified.',
        'model_calls':0,'gpu_used':False}


def stage_poses(bundle,work):
    import numpy as np
    from rdkit import Chem
    from meeko import PDBQTMolecule,RDKitMolCreate
    from scipy.optimize import linear_sum_assignment
    work=Path(work);work.mkdir(exist_ok=False)
    protein=work/'protein.pdb';protein.write_text(bundle['prepared_protein_pdb'])
    graph=work/'graph.json';graph.write_text(bundle['graph_json'])
    writer=Chem.SDWriter(str(work/'poses.sdf'));poses=[];failures=[]
    numbers={'C':6,'A':6,'N':7,'NA':7,'O':8,'OA':8,'S':16,'SA':16,'P':15,'F':9,'Cl':17,'Br':35,'I':53,'H':1,'HD':1}
    for row in bundle['rows']:
        if row['saved_status']!='succeeded':
            failures.append({'source_pointer':row['source_pointer'],'candidate_id':row['candidate_id'],
                'pose_id':row['source_pointer']+':uncomputed','status':'saved_docking_failed',
                'error':row['original_error'],'contacts':[]});continue
        try:
            mols=RDKitMolCreate.from_pdbqt_mol(PDBQTMolecule(row['pose_pdbqt'],skip_typing=True))
            if len(mols)!=1 or mols[0]is None:raise ValueError('Cannot recover one saved ligand graph.')
            molecule=mols[0];expected=Chem.MolFromSmiles(row['exact_input_smiles'])
            if expected is None or Chem.MolToSmiles(Chem.RemoveHs(molecule))!=Chem.MolToSmiles(expected)or molecule.GetNumConformers()!=len(row['pose_scores_kcal_mol']):
                raise ValueError('Saved pose graph, charge or count mismatch.')
            blocks=row['pose_pdbqt'].split('ENDMDL')
            for index,score in enumerate(row['pose_scores_kcal_mol']):
                meta={'pose_id':f"{row['source_pointer']}:pose:{index}",'candidate_id':row['candidate_id'],
                    'source_pointer':row['source_pointer'],'pose_index_0_based':index,
                    'original_vina_rank':index+1,'original_vina_score_kcal_mol':score,
                    'source_pose_file_sha256':row['pose_pdbqt_sha256'],'exact_input_smiles':row['exact_input_smiles']}
                try:
                    pose=Chem.Mol(molecule);conf=Chem.Conformer(molecule.GetConformer(index));conf.Set3D(True)
                    pose.RemoveAllConformers();pose.AddConformer(conf,assignId=True)
                    original=[]
                    for line in blocks[index].splitlines():
                        if line.startswith(('ATOM','HETATM')):
                            original.append({'serial':int(line[6:11]),'name':line[12:16].strip(),
                                'atomic_number':numbers[line.split()[-1]],
                                'coordinate':[float(line[30:38]),float(line[38:46]),float(line[46:54])]})
                    coords=conf.GetPositions();atomic=np.array([a.GetAtomicNum()for a in pose.GetAtoms()])
                    heavy=[a for a in original if a['atomic_number']>1]
                    if len(heavy)!=sum(atomic>1):raise ValueError('Saved heavy atom coverage differs.')
                    distance=np.linalg.norm(np.array([a['coordinate']for a in original])[:,None,:]-coords[None,:,:],axis=2)
                    distance[np.array([a['atomic_number']for a in original])[:,None]!=atomic[None,:]]=1e6
                    left,right=linear_sum_assignment(distance)
                    if len(left)!=len(original)or float(distance[left,right].max())>0.001:
                        raise ValueError('Saved heavy/polar-H coordinates changed; no fitting allowed.')
                    meta['original_atom_mapping']=[{'pdbqt_serial':original[a]['serial'],'pdbqt_atom_name':original[a]['name'],
                        'rdkit_atom_index':int(b),'atomic_number':original[a]['atomic_number'],
                        'coordinate_delta_angstrom':float(distance[a,b]),'original_pdbqt_coordinate_angstrom':original[a]['coordinate']}for a,b in zip(left,right)]
                    meta['hydrogen_policy']='Saved polar-H coordinates checked; nonpolar H reconstructed by recorded Meeko ligand graph. No receptor H changed.'
                    meta['rigid_fit']=False;meta['sdf_record_index']=len(poses)
                    pose.SetProp('_Name',meta['pose_id']);writer.write(pose);poses.append(meta)
                except Exception as error:
                    failures.append({**meta,'status':'pose_reconstruction_failed','error':str(error)[:500],'contacts':[]})
        except Exception as error:
            for index,score in enumerate(row['pose_scores_kcal_mol']):
                failures.append({'pose_id':f"{row['source_pointer']}:pose:{index}",'source_pointer':row['source_pointer'],
                    'candidate_id':row['candidate_id'],'pose_index_0_based':index,'original_vina_rank':index+1,
                    'original_vina_score_kcal_mol':score,'status':'candidate_reconstruction_failed','error':str(error)[:500],'contacts':[]})
    writer.close()
    return {k:bundle[k]for k in ('source_artifact_id','source_artifact_sha256','structure_artifact_id','structure_artifact_sha256','interactions','count','vicinity_cutoff_angstrom')}|{
        'prepared_protein_path':str(protein),'prepared_protein_sha256':bundle['prepared_protein_sha256'],
        'graph_path':str(graph),'graph_sha256':bundle['graph_sha256'],'sdf_path':str(work/'poses.sdf'),
        'sdf_sha256':file_digest(work/'poses.sdf'),'poses':poses,'failures':failures,
        'chain_renaming':bundle.get('chain_renaming',{}),
        'reconstruction_versions':{k:importlib.metadata.version(k)for k in ('meeko','rdkit')}}


def analyze(bundle,work):
    if bundle['availability']!='ready':return unavailable(bundle)
    staged=stage_poses(bundle,Path(work)/'pose-inputs')
    if staged['poses']:
        result=run_author(staged,Path(work)/'prolif')
    else:
        result={'status':'failed','error':'No saved poses passed exact reconstruction checks.','rows':[]}
    result['rows'].extend(staged['failures'])
    if staged['failures']and result.get('status')=='succeeded':result['status']='partial'
    result.update(semantic_type='saved_pose_interaction_contacts_not_affinity',
        source_artifact_id=bundle['source_artifact_id'],source_artifact_sha256=bundle['source_artifact_sha256'],
        structure_artifact_id=bundle['structure_artifact_id'],structure_artifact_sha256=bundle['structure_artifact_sha256'],
        target_source_sha256=bundle['target_source_sha256'],graph_sha256=bundle['graph_sha256'],prepared_protein_sha256=bundle['prepared_protein_sha256'],
        reconstruction_versions=staged['reconstruction_versions'],limits=LIMITS,model_calls=0,gpu_used=False)
    result['summary']={'saved_candidates':len(bundle['rows']),'computed_poses':sum(r.get('status')=='computed'for r in result['rows']),
        'failed_or_uncomputed_rows':sum(r.get('status')!='computed'for r in result['rows']),
        'contact_occurrences':sum(len(r.get('contacts',[]))for r in result['rows'])}
    return result
