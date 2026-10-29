"""A new explicit fpocket site seam; the co-crystal docking entry stays unchanged."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys


TIMEOUT_SECONDS=300
OUTPUT_LIMIT_BYTES=64*1024*1024
LOG_LIMIT_BYTES=1024*1024

def digest(raw):return hashlib.sha256(raw).hexdigest()
def verified(source):
    if digest(source['content'])!=source['sha256']:raise ValueError('Actual stored source bytes do not match their artifact SHA.')
    return json.loads(source['content'])

def geometry(body,pocket_id,padding):
    if type(pocket_id)is not int or pocket_id<1 or type(padding)not in(int,float)or not math.isfinite(padding)or not 2<=padding<=8:
        raise ValueError('명시 pocket ID와2–8Å padding을 선택하세요.')
    rows=[r for r in body.get('rows',[])if r.get('pocket_id')==pocket_id]
    if len(rows)!=1:raise ValueError('실제로 반환된 유일한 pocket을 선택하세요. 0개 결과에서 부위를 만들지 않습니다.')
    suffix=f'/pocket{pocket_id}_vert.pqr'
    files=[f for f in body.get('author_files',[])if f.get('name','').endswith(suffix)]
    if len(files)!=1:raise ValueError('선택한 pocket의 원저자 alpha-sphere PQR가 보존되지 않았습니다.')
    f=files[0];raw=f['text'].encode()
    if len(raw)>2*1024*1024 or digest(raw)!=f['sha256']:raise ValueError('보존 pocket PQR 바이트/SHA가 다릅니다.')
    points=[];lines=[]
    for n,line in enumerate(f['text'].splitlines(),1):
        if not line.startswith(('ATOM  ','HETATM')):continue
        try:point=[float(line[a:b])for a,b in [(30,38),(38,46),(46,54)]]
        except ValueError:raise ValueError('원 PQR 좌표를 정해진 PDB 열에서 읽지 못했습니다.')from None
        if any(not math.isfinite(x)for x in point):raise ValueError('Pocket coordinates must be finite.')
        points.append(point);lines.append(n)
    if not 4<=len(points)<=5000:raise ValueError('선택 pocket의 보존 alpha-sphere 좌표가 부족하거나 범위를 넘었습니다.')
    low=[min(p[k]for p in points)for k in range(3)];high=[max(p[k]for p in points)for k in range(3)]
    center=[(a+b)/2 for a,b in zip(low,high)];box=[b-a+2*padding for a,b in zip(low,high)]
    if any(not 12<=v<=40 for v in box):raise ValueError('원 pocket extent+명시 padding의 box가 지원 범위12–40Å 밖입니다. 자동 확대/축소하지 않습니다.')
    return {'pocket_id':pocket_id,'author_file':f['name'],'author_file_sha256':f['sha256'],
       'coordinate_line_numbers_1_based':lines,'alpha_sphere_centers_angstrom':points,
       'minimum_angstrom':low,'maximum_angstrom':high,'box_padding_angstrom':padding,
       'center_angstrom':center,'box_size_angstrom':box,
       'calculation':'axis_min/max of retained alpha-sphere centers; center=(min+max)/2; box=max-min+2*explicit_padding',
       'meaning':'Explicit geometric computational site, not a validated binding/functional site.'}

def prepare(store,wid,args):
    molecule=store.artifact(wid,args['artifact_id']);structure=store.artifact(wid,args['structure_id']);pockets=store.artifact(wid,args['pocket_artifact_id'])
    for source,key in [(molecule,'molecule_artifact_sha256'),(structure,'structure_artifact_sha256'),(pockets,'pocket_artifact_sha256')]:
        if digest(source['content'])!=source['sha256']or source['sha256']!=args[key]:raise ValueError('명시한 입력 ID의 실제 Store 바이트 SHA가 다릅니다.')
    if molecule['kind']!='molecule_csv'or structure['kind']!='target_structure'or pockets['kind']!='structure_pockets':raise ValueError('원 후보 CSV·원 구조·완료 fpocket artifact를 각각 선택하세요.')
    structure_body=verified(structure);body=verified(pockets)
    if body.get('status')!='succeeded' or structure_body.get('status')!='succeeded':raise ValueError('완료한 실제 구조·포켓 결과가 필요합니다.')
    if body.get('source_artifact_id')!=structure['id']or body.get('source_artifact_sha256')!=structure['sha256']:
        raise ValueError('fpocket 결과가 이 원 구조 artifact와 결합되지 않았습니다.')
    if digest(structure_body['original_cif'].encode())!=structure_body['source']['sha256']:raise ValueError('원 receptor mmCIF 바이트/SHA가 다릅니다.')
    pdb=body.get('prepared_pdb');chains=body.get('preparation',{}).get('selected_chains')
    if not isinstance(pdb,str)or not pdb or not isinstance(chains,list)or not chains or len(chains)!=len(set(chains)):raise ValueError('fpocket에 실제 사용한 단백질 PDB와 명시 사슬이 필요합니다.')
    ids=args['candidate_ids']
    if not isinstance(ids,list)or not 1<=len(ids)<=3 or len(ids)!=len(set(ids)):raise ValueError('중복 없는 후보1–3개를 선택하세요.')
    if args['exhaustiveness']not in(8,16)or type(args['seed'])is not int or not 1<=args['seed']<=2147483647:raise ValueError('명시한 bounded docking 설정을 확인하세요.')
    g=geometry(body,args['pocket_id'],args['box_padding_angstrom'])
    return {'molecule_artifact_id':molecule['id'],'molecule_artifact_sha256':molecule['sha256'],
      'structure_artifact_id':structure['id'],'structure_artifact_sha256':structure['sha256'],
      'pocket_artifact_id':pockets['id'],'pocket_artifact_sha256':pockets['sha256'],
      'structure_data':structure_body,'prepared_pocket_pdb':pdb,'prepared_pocket_pdb_sha256':digest(pdb.encode()),
      'selected_chains':chains,'geometry':g,'parameters':{k:args[k]for k in ['candidate_ids','exhaustiveness','seed']}}

def prepare_receptor(structure_data,binding,work):
    import gemmi
    if digest(structure_data['original_cif'].encode())!=structure_data['source']['sha256']:
        raise ValueError('Original receptor CIF bytes changed in the staged request.')
    from .protein_computation_worker import protein_pdb
    # Rebuild with the exact fixed fpocket preparation algorithm, before Meeko.
    reproduced,prep=protein_pdb({'cif':structure_data['original_cif'],'chain_ids':binding['selected_chains']})
    if digest(reproduced.encode())!=binding['prepared_pocket_pdb_sha256']or reproduced!=binding['prepared_pocket_pdb']:
        raise ValueError('원 receptor에서 재현한 PDB와 fpocket 원 입력 PDB가 다릅니다.')
    original=gemmi.make_structure_from_block(gemmi.cif.read_string(structure_data['original_cif']).sole_block())
    if len(original)!=1:raise ValueError('Single retained coordinate model required.')
    center=binding['geometry']['center_angstrom'];box=binding['geometry']['box_size_angstrom'];points=binding['geometry']['alpha_sphere_centers_angstrom'];nearby=[]
    for chain in original[0]:
        for residue in chain:
            protein=residue.het_flag=='A'and gemmi.find_tabulated_residue(residue.name).is_amino_acid()
            if protein and chain.name in binding['selected_chains']:continue
            if residue.is_water():continue
            xyz=[(a.pos.x,a.pos.y,a.pos.z)for a in residue if not a.is_hydrogen()]
            if not xyz:continue
            inside=any(all(abs(p[k]-center[k])<=box[k]/2 for k in range(3))for p in xyz)
            close=min(math.dist(p,q)for p in xyz for q in points)<8
            if inside or close:nearby.append({'chain':chain.name,'residue':str(residue.seqid),'name':residue.name,'protein_partner':protein,'inside_box':inside,'within8A_of_retained_sphere':close})
    if nearby:raise ValueError('선택 pocket 주변의 미포함 파트너/리간드/금속을 지워 진행하지 않습니다: '+json.dumps(nearby,ensure_ascii=False))
    (work/'receptor-source.pdb').write_text(reproduced)
    with(work/'receptor-preparation.log').open('wb')as log:
        proc=subprocess.run([sys.executable,'-m','evida.receptor_graph_worker',str(work)],stdout=log,stderr=subprocess.STDOUT,timeout=240,check=False)
    receptor=work/'receptor.pdbqt'
    if proc.returncode or not receptor.is_file():raise ValueError('Meeko graph-preserving receptor preparation failed; original receptor/pocket bytes remain retained.')
    site={'site_mode':'explicit_fpocket_geometry','pocket_id':binding['geometry']['pocket_id'],
          'center_angstrom':center,'box_size_angstrom':box,'geometry_provenance':binding['geometry']}
    return receptor,{'site':site,'chain_renaming':{c:c for c in binding['selected_chains']},
      'fpocket_source_artifact_id':binding['pocket_artifact_id'],'fpocket_source_artifact_sha256':binding['pocket_artifact_sha256'],
      'prepared_pocket_pdb_sha256':binding['prepared_pocket_pdb_sha256'],'preparation':prep,
      'graph_retention':{'status':'retained','file':'receptor-graph.json'}if(work/'receptor-graph.json').exists()else{'status':'unavailable'},
      'limitations':['Explicit apo selected-chain computational site; no co-crystal ligand defines this site.',
                     'Waters omitted as recorded by fpocket preparation. Nearby nonwater partners/components are not silently deleted.',
                     'Rigid receptor, original missing atoms/residues not repaired. Pocket selection does not establish functional ligandability.']}

def run(content,meta,binding,work):
    from .binding import dock_molecules
    if digest(content)!=binding['molecule_artifact_sha256']:raise ValueError('Staged candidate CSV SHA changed.')
    args={**binding['parameters'],'site_id':f"fpocket:{binding['geometry']['pocket_id']}"}
    result=dock_molecules(content,meta,binding['structure_data'],args,Path(work),
       receptor_preparer=lambda structure,site,folder:prepare_receptor(structure,binding,folder),
       progress_callback=lambda rows:_progress(Path(work).parent/'progress.json',{'status':'docking','rows':rows}))
    result['pocket_source_binding']={k:v for k,v in binding.items()if k not in ('structure_data','prepared_pocket_pdb')}
    result['limits'].append('Selected fpocket geometry is an explicit computational site hypothesis; no deposited reference pose or measured affinity/efficacy is implied.')
    return result

# A separate process bounds only the new pocket path. Existing co-crystal calls
# retain their original behavior and interface.
_execute=run

def _progress(path,value):
    tmp=Path(path).with_suffix('.part');tmp.write_text(json.dumps(value,ensure_ascii=False));tmp.replace(path)

def run(content,meta,binding,work):
    import base64
    import os
    import selectors
    import time
    from .protonation import kill_group,file_digest
    work=Path(work);work.mkdir(parents=True,exist_ok=False)
    incoming=work/'worker-input.json';output=work/'worker-result.json';progress=work/'progress.json'
    incoming.write_text(json.dumps({'content_base64':base64.b64encode(content).decode(),'meta':meta,'binding':binding}))
    _progress(progress,{'status':'starting','rows':[],'selected_pocket_id':binding['geometry']['pocket_id']})
    start=time.monotonic();timeout=TIMEOUT_SECONDS;output_limit=OUTPUT_LIMIT_BYTES;log_limit=LOG_LIMIT_BYTES
    proc=subprocess.Popen([sys.executable,'-B','-m','evida.pocket_docking_worker',str(incoming),str(output)],
         cwd=work,env={**os.environ,'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2'},
         stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
    sel=selectors.DefaultSelector();sel.register(proc.stdout,selectors.EVENT_READ);reason=None;logged=0
    try:
        with(work/'worker.log').open('xb')as log:
            while proc.poll()is None or sel.get_map():
                if(work/'cancel').exists():reason='cancelled'
                elif time.monotonic()-start>timeout:reason='timeout'
                elif sum(p.stat().st_size for p in work.rglob('*')if p.is_file())>output_limit:reason='output_limit'
                if reason:break
                for key,_ in sel.select(.05):
                    chunk=os.read(key.fileobj.fileno(),8192)
                    if not chunk:sel.unregister(key.fileobj);continue
                    log.write(chunk[:max(0,log_limit-logged)]);logged+=len(chunk)
                    if logged>log_limit:reason='log_limit';break
    finally:
        sel.close();proc.stdout.close();kill_group(proc);proc.wait(timeout=2)
    if sum(p.stat().st_size for p in work.rglob('*')if p.is_file())>output_limit:reason='output_limit'
    if reason or proc.returncode or not output.is_file()or output.stat().st_size>output_limit:
        last=json.loads(progress.read_text())if progress.is_file()and progress.stat().st_size<2*1024*1024 else{'rows':[]}
        result={'status':'failed','error':reason or'author_worker_failure','rows':last.get('rows',[]),'last_progress':last,
          'pocket_source_binding':{k:v for k,v in binding.items()if k not in('structure_data','prepared_pocket_pdb')},
          'retained_files':[{'name':str(p.relative_to(work)),'bytes':p.stat().st_size,'sha256':file_digest(p)}for p in sorted(work.rglob('*'))if p.is_file()],
          'limits':['Incomplete bounded computation; retained partial rows/files do not establish a completed docking result.']}
    else:result=json.loads(output.read_text())
    result.update(elapsed_seconds=round(time.monotonic()-start,6),timeout_seconds=timeout,output_limit_bytes=output_limit,log_limit_bytes=log_limit,
      cpu_threads=2,model_calls=0,gpu_used=False,cancel_marker='pocket-docking/cancel')
    _progress(progress,{'status':result['status'],'rows':result.get('rows',[]),'error':result.get('error'),'elapsed_seconds':result['elapsed_seconds']})
    return result
