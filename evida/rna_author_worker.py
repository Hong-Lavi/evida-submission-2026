"""Bounded local full-author workflow on new, explicitly prepared inputs."""
from datetime import datetime, timezone
import csv
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024*1024), b''): h.update(block)
    return h.hexdigest()


def save(path, data):
    with Path(path).open('x') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2); handle.write('\n')


def verify_pdb(path, sense, anti):
    residues = []; last = None
    for line in path.read_text().splitlines():
        if line.startswith('ATOM  '):
            key = (line[21:22], line[22:27])
            if key != last:
                residues.append(line[17:20].strip().upper()); last = key
    sequence = ''.join(r[1:] if r in ('RA','RC','RG','RU') else r for r in residues)
    if sequence != sense+anti:
        raise ValueError('Generated structure sequence differs from the exact duplex input')


def main():
    request, output = map(Path, sys.argv[1:])
    data = json.loads(request.read_text()); cfg = data['configuration']; rows = data['rows']
    work = output.parent; started = time.monotonic()
    assert os.environ['CUDA_VISIBLE_DEVICES'] == str(cfg['physical_gpu'])
    for path, expected in cfg['assets'].items():
        if sha(path) != expected: raise ValueError('Frozen local asset changed: '+Path(path).name)
    import RNA
    assert RNA.__version__ == '2.7.2', 'Exact reviewed ViennaRNA overlay required before structure work'
    # Cooperative lock prevents two EVIDA adapters from loading the same GPU.
    # The live occupancy check also protects jobs that do not use this lock.
    lock = open(cfg['gpu_lock'], 'a')
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    used = int(subprocess.check_output(['/usr/bin/nvidia-smi', '--id='+str(cfg['physical_gpu']),
        '--query-gpu=memory.used', '--format=csv,noheader,nounits'], text=True).strip())
    if used >= 512: raise RuntimeError('Selected GPU is occupied; no scientific computation started')
    save(work/'preflight.json', {'at': datetime.now(timezone.utc).isoformat(),
        'physical_gpu': cfg['physical_gpu'], 'memory_used_mib_before': used,
        'input_sha256': sha(request), 'rows': [r['candidate_id'] for r in rows],
        'actual_efficacy': None, 'technical_label_placeholder': 0})
    pdbs = work/'pdb'; pdbs.mkdir()
    fields = ['siRNA','anti seq','sense seq','mRNA','mRNA_seq','position','efficacy','anti_seq_len']
    with (work/'input.csv').open('x', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows({k:r[k] for k in fields} for r in rows)
    structures = []
    for row in rows:
        folder = work/row['siRNA']; folder.mkdir()
        sense, anti = row['sense seq'].lower(), row['anti seq'].lower()
        plex = subprocess.run([cfg['rna_plex']], input=sense+'\n'+anti+'\n',
            text=True, capture_output=True, check=True, timeout=60)
        (folder/'RNAplex.stdout.txt').write_text(plex.stdout)
        (folder/'RNAplex.stderr.txt').write_text(plex.stderr)
        fields_ = plex.stdout.split(); left, right = fields_[0].split('&')
        s0,s1 = map(int, fields_[1].split(',')); a0,a1 = map(int, fields_[3].split(','))
        ss = '.'*(s0-1)+left+'.'*(len(sense)-s1)
        aa = '.'*(a0-1)+right+'.'*(len(anti)-a1)
        assert len(ss) == len(sense) and len(aa) == len(anti)
        command = [cfg['rna_denovo'], '-database', str(Path(cfg['rosetta_root'])/'main/database'),
            '-sequence', sense+' '+anti, '-secstruct', ss+' '+aa,
            '-minimize_rna', '-constant_seed', '-jran', '11', '-nstruct', '1',
            '-out:file:silent', 'default.out']
        save(folder/'request.json', {'command': command, 'sense': sense, 'antisense': anti})
        with (folder/'rosetta.log').open('x') as log:
            subprocess.run(command, cwd=folder, stdout=log, stderr=subprocess.STDOUT,
                check=True, timeout=1800)
        # The exact reviewed official extraction helper is reused unchanged.
        with (folder/'extract.log').open('x') as log:
            subprocess.run([cfg['python'], cfg['extract_helper'], 'default.out',
                '-rosetta_folder', cfg['rosetta_root'], '1'], cwd=folder,
                stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        pdb = folder/'default.out.1.pdb'; verify_pdb(pdb, sense.upper(), anti.upper())
        target = pdbs/(row['siRNA']+'.pdb'); shutil.copyfile(pdb, target)
        item = {'candidate_id': row['candidate_id'], 'pdb_sha256': sha(target),
            'silent_sha256': sha(folder/'default.out'), 'structure_seed': 11}
        structures.append(item); save(folder/'result.json', item)
    # Verify occupancy again after CPU geometry, before any GPU model import.
    used = int(subprocess.check_output(['/usr/bin/nvidia-smi', '--id='+str(cfg['physical_gpu']),
        '--query-gpu=memory.used', '--format=csv,noheader,nounits'], text=True).strip())
    if used >= 512: raise RuntimeError('GPU became occupied during geometry; preserved structures, no inference')
    sys.path.insert(0, cfg['author_code'])
    import torch
    torch.set_num_threads(2)
    assert torch.cuda.is_available() and torch.cuda.device_count() == 1
    from utils.random_seed import setup_seed
    setup_seed(12)
    from data.get_pdb import Data_Prepare
    def unexpected(*args, **kwargs):
        raise RuntimeError('Author preprocessing requested an unverified additional structure')
    Data_Prepare.get_secondary_structure = unexpected
    Data_Prepare(str(work/'input.csv'), str(pdbs)).process()
    prepared = [json.loads(line) for line in (work/'input.json').read_text().splitlines()]
    assert [r['siRNA'] for r in prepared] == [r['siRNA'] for r in rows], 'Preprocessing omitted/reordered rows'
    for row in prepared:
        assert Path(row['pdb_data_path']).resolve() == (pdbs/(row['siRNA']+'.pdb')).resolve()
        assert len(row['start']) == len(row['chain']) == 101
    from data.dataset import E2EDataset
    from torch.utils.data import DataLoader
    dataset = E2EDataset(str(work/'input.json'), save_dir=str(work/'author-cache'))
    assert len(dataset) == len(rows), 'Author dataset omitted a row'
    loader = DataLoader(dataset, batch_size=3, num_workers=0, collate_fn=E2EDataset.collate_fn)
    scores = []
    for checkpoint in cfg['checkpoints']:
        model = torch.load(checkpoint, map_location='cpu').to('cuda:0').eval()
        values = []; differences = []
        with torch.no_grad():
            for batch in loader:
                batch = {k:v.to('cuda:0') if hasattr(v,'to') else v for k,v in batch.items()}
                low = model.test(**{**batch, 'pct': torch.zeros_like(batch['pct'])})[0]
                high = model.test(**{**batch, 'pct': torch.ones_like(batch['pct'])})[0]
                difference = float((low-high).abs().max()); differences.append(difference)
                assert difference <= 1e-6 and torch.isfinite(low).all()
                values.extend(low.detach().cpu().reshape(-1).tolist())
        assert len(values) == len(rows)
        model_rows = [{'candidate_id': row['candidate_id'], 'checkpoint': Path(checkpoint).name,
            'raw_model_score': value, 'actual_efficacy': None,
            'representation': row['representation'], 'target_start_1_based': row['position']+1,
            'source_chemistry': row['source_chemistry']} for row,value in zip(rows,values)]
        save(work/(Path(checkpoint).stem+'-result.json'), {'rows': model_rows,
            'checkpoint_sha256': sha(checkpoint), 'technical_label_0_vs_1_max_delta': max(differences)})
        scores.extend(model_rows); del model; torch.cuda.empty_cache()
    save(output, {'status':'succeeded', 'semantic_type':'conditional_full_author_ensirna_prediction',
        'reference': data['reference'], 'rows': scores, 'structures': structures,
        'summary': {'candidates':len(rows), 'checkpoints':len(cfg['checkpoints']),
            'elapsed_seconds':time.monotonic()-started, 'representation':'unmodified_19nt_blunt_core_proxy'},
        'protocol': {'input_sha256':sha(request), 'author_commit':cfg['author_commit'],
            'assets':cfg['assets'], 'structure_seed':11, 'nstruct':1,
            'torch':torch.__version__, 'ViennaRNA':RNA.__version__, 'actual_efficacy':None},
        'limits':['RNAplex/Rosetta/RNA-FM와 저자 전처리·5GNN의 실제 조건부 계산입니다.',
            '비수식 19nt blunt core 표현입니다. 원 후보의 수식·돌출부·제형·세포 내 효능을 계산한 것이 아닙니다.',
            '5체크포인트와 구조 seed는 독립 생물학적 증거가 아닙니다. 점수는 성공확률이 아닙니다.',
            '기전·비표적·전달·노출 조건 및 다른 후보는 별도로 유지합니다.']})


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        if len(sys.argv) == 3:
            path = Path(sys.argv[2]).parent/'failure.json'
            if not path.exists(): save(path, {'status':'FAILED', 'error_type':type(error).__name__,
                'message':str(error), 'automatic_retry':False})
        raise
