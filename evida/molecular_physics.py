"""Source-bound xTB/CREST execution on retained, explicit 3D molecular states."""
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import time
from .protonation import digest, file_digest, kill_group

TOOLS = {'xtb_geometry', 'crest_conformers'}


def prepare(source, args, tool):
    fields = {'artifact_id', 'state_pointers', 'unpaired_electrons', 'solvent'}
    if tool not in TOOLS or set(args) != fields or source['id'] != args['artifact_id']:
        raise ValueError('Select the exact saved molecular preparation and declared parameters.')
    if source['kind'] != 'molecule_preparation' or digest(source['content']) != source['sha256']:
        raise ValueError('A verified saved Gypsum-DL preparation is required.')
    if type(args['unpaired_electrons']) is not int or not 0 <= args['unpaired_electrons'] <= 4:
        raise ValueError('Unpaired electrons must be an explicit integer 0–4.')
    if args['solvent'] not in ('gas', 'water') or tool == 'crest_conformers' and args['solvent'] != 'gas':
        raise ValueError('xTB supports gas/water here; the current CREST adapter is gas-phase GFN-FF.')
    pointers = args['state_pointers']
    if not isinstance(pointers, list) or not 1 <= len(pointers) <= 4 or len(set(pointers)) != len(pointers):
        raise ValueError('Select one to four distinct saved state pointers.')
    body = json.loads(source['content']); choices = []
    for pointer in pointers:
        match = re.fullmatch(r'/rows/(0|[1-9][0-9]*)/states/(0|[1-9][0-9]*)', pointer)
        if not match: raise ValueError('Use an exact /rows/N/states/M pointer.')
        try:
            row = body['rows'][int(match[1])]; state = row['states'][int(match[2])]
        except (KeyError, IndexError, TypeError): raise ValueError('Saved state does not exist.') from None
        if not all(state.get(k) is True for k in ('rdkit_parse_valid', 'heavy_atom_element_counts_preserved', 'finite_3d_coordinates')):
            raise ValueError('Saved state must have verified composition and finite 3D coordinates.')
        files = [f for f in body['author_files'] if f['sha256'] == state['sdf_sha256']
                 and f['source_pointer'] == row['source_pointer']]
        if len(files) != 1 or digest(files[0]['content'].encode()) != state['sdf_sha256']:
            raise ValueError('The exact author SDF cannot be verified.')
        choices.append({'source_pointer': pointer, 'parent_source_pointer': row['source_pointer'],
            'sdf': files[0]['content'], 'sdf_sha256': state['sdf_sha256'],
            'record_index': state['record_index'], 'smiles': state['exact_author_smiles'],
            'formal_charge': state['formal_charge']})
    return dict(tool=tool, structures=choices, source_artifact_id=source['id'],
        source_artifact_sha256=source['sha256'], unpaired_electrons=args['unpaired_electrons'], solvent=args['solvent'])


def configuration():
    cfg = json.loads((Path(__file__).parents[1]/'configs/molecular-physics-runtime.json').read_text())
    for path, expected in cfg['assets'].items():
        if file_digest(path) != expected: raise ValueError('Molecular physics runtime asset changed.')
    return cfg


def cache_key(root, source, args, tool):
    return digest(json.dumps({'input':prepare(source,args,tool), 'runtime':configuration(),
        'code':{n:file_digest(Path(root)/'evida'/n)for n in
                ('molecular_physics.py','molecular_physics_worker.py','runner.py','science.py')}},sort_keys=True).encode())


def run(request, work):
    cfg=configuration();work=Path(work);work.mkdir(exist_ok=False)
    incoming=work/'request.json';output=work/'result.json'
    incoming.write_text(json.dumps({'input':request,'runtime':cfg}))
    env={'PATH':cfg['bin_directory']+':/usr/bin:/bin','LANG':'C.UTF-8','CUDA_VISIBLE_DEVICES':'',
         'PYTHONNOUSERSITE':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    start=time.monotonic();reason=None;size=0
    p=subprocess.Popen([cfg['python'],'-B',str(Path(__file__).with_name('molecular_physics_worker.py')),str(incoming),str(output)],
        cwd=work,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
    selector=selectors.DefaultSelector();selector.register(p.stdout,selectors.EVENT_READ)
    try:
        with(work/'worker.log').open('xb')as log:
            while p.poll()is None or selector.get_map():
                if(work/'cancel').exists():reason='cancelled'
                elif time.monotonic()-start>cfg['timeout_seconds']:reason='timeout'
                elif sum(f.stat().st_size for f in work.rglob('*')if f.is_file())>cfg['output_limit_bytes']:reason='output_limit'
                if reason:break
                for key,_ in selector.select(.05):
                    chunk=os.read(key.fileobj.fileno(),8192)
                    if not chunk:selector.unregister(key.fileobj);continue
                    log.write(chunk[:max(0,cfg['log_limit_bytes']-size)]);size+=len(chunk)
                    if size>cfg['log_limit_bytes']:reason='log_limit'
    finally:
        selector.close();p.stdout.close();kill_group(p);p.wait(timeout=2)
    if sum(f.stat().st_size for f in work.rglob('*')if f.is_file())>cfg['output_limit_bytes']:reason='output_limit'
    if reason or p.returncode or not output.exists():
        progress=work/'progress.json'
        body=json.loads(progress.read_text())if progress.exists()and progress.stat().st_size<cfg['output_limit_bytes']else{'rows':[]}
        done={r['source_pointer']for r in body['rows']}
        body['rows'].extend({'source_pointer':r['source_pointer'],'status':'not_completed'}for r in request['structures']if r['source_pointer']not in done)
        body.update(status='failed',error=reason or 'author_worker_failure')
    else:body=json.loads(output.read_text())
    body.update(source_artifact_id=request['source_artifact_id'],source_artifact_sha256=request['source_artifact_sha256'],
                elapsed_seconds=round(time.monotonic()-start,4),gpu_used=False,model_calls=0,
                runtime_manifest_sha256=file_digest(Path(__file__).parents[1]/'configs/molecular-physics-runtime.json'))
    return body
