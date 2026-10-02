"""Explicit known-site docking with public structures and actual pose checks.

The method evaluates poses under a recorded rigid-receptor preparation. It
does not convert a docking score into efficacy, affinity or selectivity.
"""
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import re
import string
import subprocess
import sys

from .science import fetch, molecule_rows

# How close another component has to sit to the site's own ligand before the preparation refuses.
NEARBY_ANGSTROM = 8.0
# The search box every docking run uses. It lives here as well as at the call site because the
# preparation has to know what volume the search will explore before it deletes anything from it.
DOCKING_BOX_ANGSTROM = [22, 22, 22]


def _inside_box(position, center):
    return all(abs(position[axis] - center[axis]) <= DOCKING_BOX_ANGSTROM[axis] / 2
               for axis in range(3))


def structure_summary(cif):
    import gemmi
    structure = gemmi.make_structure_from_block(gemmi.cif.read_string(cif).sole_block())
    if len(structure) != 1:
        raise ValueError('단일 좌표 모형의 구조가 필요합니다. NMR/다중 모형은 별도 선택이 필요합니다.')
    rows = []
    for chain in structure[0]:
        residues = [r for r in chain if r.het_flag == 'A' and gemmi.find_tabulated_residue(r.name).is_amino_acid()]
        if residues:
            ids = [r.seqid.num for r in residues]
            rows.append({'kind': 'protein_chain', 'chain': chain.name, 'modeled_residues': len(residues),
                         'first_residue': str(residues[0].seqid), 'last_residue': str(residues[-1].seqid),
                         'internal_numbering_gaps': [[a, b] for a, b in zip(ids, ids[1:]) if b > a + 1],
                         'sequence_modeled': ''.join(gemmi.find_tabulated_residue(r.name).one_letter_code for r in residues)})
        for residue in chain:
            if residue.het_flag == 'A' or residue.is_water():
                continue
            atoms = [a for a in residue if not a.is_hydrogen()]
            if not atoms:
                continue
            center = [sum(getattr(a.pos, k) for a in atoms) / len(atoms) for k in ('x', 'y', 'z')]
            rows.append({'kind': 'bound_component', 'ligand_id': f'{chain.name}:{residue.seqid}:{residue.name}',
                         'chain': chain.name, 'residue': str(residue.seqid), 'component': residue.name,
                         'heavy_atoms': len(atoms), 'center_angstrom': center,
                         'occupancies': sorted({round(a.occ, 4) for a in atoms}),
                         'alternate_locations': sorted({a.altloc for a in atoms if a.altloc != '\x00'})})
    return structure, rows


def fetch_structure(arguments):
    pdb_id = str(arguments['pdb_id']).upper()
    assembly = arguments['assembly_id']
    if not re.fullmatch(r'[0-9][A-Z0-9]{3}', pdb_id) or type(assembly) is not int or not 1 <= assembly <= 50:
        raise ValueError('PDB 식별자와 생물학적 조립체 번호를 확인해 주세요.')
    raw, source = fetch(f'https://files.rcsb.org/download/{pdb_id}-assembly{assembly}.cif')
    cif = raw.decode('utf-8')
    structure, rows = structure_summary(cif)
    metadata_raw, metadata_source = fetch(f'https://data.rcsb.org/rest/v1/core/entry/{pdb_id}')
    metadata = json.loads(metadata_raw)
    if metadata.get('rcsb_id', '').upper() != pdb_id:
        raise ValueError('구조 메타데이터의 식별자가 요청과 다릅니다.')
    return {'status': 'succeeded', 'semantic_type': 'public_biological_assembly',
            'pdb_id': pdb_id, 'assembly_id': assembly, 'source': source,
            'metadata_source': metadata_source, 'metadata_response': metadata, 'original_cif': cif,
            'rows': rows, 'summary': {'title': metadata.get('struct', {}).get('title'),
                                    'resolution_angstrom': metadata.get('rcsb_entry_info', {}).get('resolution_combined'),
                                    'protein_chains': sum(r['kind'] == 'protein_chain' for r in rows),
                                    'bound_components': sum(r['kind'] == 'bound_component' for r in rows),
                                    'coordinate_models': len(structure)},
            'limits': ['공개 구조의 특정 생물학적 조립체입니다. 유전자명만으로 실험 도메인·변이·상태가 같다고 보지 않습니다.',
                       '좌표가 있는 잔기만 표시합니다. 원전의 결측·구성체·완충액과 결합 부위의 적합성을 확인해야 합니다.',
                       '공결정 성분은 결합 부위의 후보이며 효과·선택성의 자동 증거가 아닙니다.']}


def prepare_receptor(structure_data, site_id, work):
    import gemmi
    cif = structure_data['original_cif']
    if hashlib.sha256(cif.encode()).hexdigest() != structure_data['source']['sha256']:
        raise ValueError('구조 원문과 수신 해시가 다릅니다.')
    structure, rows = structure_summary(cif)
    sites = [r for r in rows if r.get('ligand_id') == site_id]
    if len(sites) != 1 or sites[0]['heavy_atoms'] < 6:
        raise ValueError('구조에서 확인한 하나의 유기 공결정 성분 부위를 선택해 주세요.')
    site = sites[0]
    if len(structure[0]) > 62:
        raise ValueError('현재 준비기가 지원하는 사슬 수를 넘었습니다.')
    center = site['center_angstrom']
    # The coordinates of the component this site is named after, read before anything is deleted.
    # The guard below asks how close another component sits to *these atoms*. It used to ask how
    # close it sits to the centre of the box, and those are different questions: in 1RO6 the
    # catalytic zinc and manganese sit 9.12 and 9.40 A from the box centre - past the old 8 A
    # guard - and 3.26 and 3.55 A from rolipram, the ligand that defines the site. Both were
    # removed in silence, so every score computed on that receptor was a score on a PDE4B with
    # its catalytic metals taken out.
    site_positions = []
    for chain in structure[0]:
        if chain.name != site['chain']:
            continue
        for residue in chain:
            if str(residue.seqid) == site['residue'] and residue.name == site['component']:
                site_positions += [(a.pos.x, a.pos.y, a.pos.z) for a in residue
                                   if not a.is_hydrogen()]
    if not site_positions:
        raise ValueError('선택한 부위 성분의 좌표를 구조에서 찾지 못했습니다.')
    removed, renamed, nearby = [], {}, []
    for index, chain in enumerate(structure[0]):
        original_chain = chain.name
        chain.name = (string.ascii_uppercase + string.ascii_lowercase + string.digits)[index]
        renamed[original_chain] = chain.name
        for j in reversed(range(len(chain))):
            residue = chain[j]
            amino = residue.het_flag == 'A' and gemmi.find_tabulated_residue(residue.name).is_amino_acid()
            if amino:
                continue
            record = {'chain': original_chain, 'residue': str(residue.seqid), 'name': residue.name}
            positions = [(a.pos.x, a.pos.y, a.pos.z) for a in residue if not a.is_hydrogen()]
            metal = any(a.element.is_metal for a in residue)
            is_the_site = (original_chain == site['chain'] and record['residue'] == site['residue']
                           and residue.name == site['component'])
            if positions and not residue.is_water():
                to_site = min(math.dist(p, s) for p in positions for s in site_positions)
                to_center = min(math.dist(p, center) for p in positions)
                inside = any(_inside_box(p, center) for p in positions)
                record.update(minimum_distance_to_site_component_angstrom=round(to_site, 2),
                              minimum_distance_to_box_center_angstrom=round(to_center, 2),
                              inside_docking_box=inside, metal=metal)
                # Two ways a removal changes the system being modelled. A component in contact
                # with the ligand is part of the site as deposited. A metal anywhere in the search
                # box is worse: Vina's scoring has no coordination term, so deleting it does not
                # approximate the chemistry, it replaces it with a cavity.
                if not is_the_site and (to_site < NEARBY_ANGSTROM or (metal and inside)):
                    nearby.append(record)
            removed.append(record)
            del chain[j]
    if nearby:
        raise ValueError(
            '선택 부위의 리간드에 접해 있거나 탐색 상자 안에 있는 성분/금속이 있습니다. '
            '제거해 진행하지 않고 준비 조건을 확인해야 합니다. Vina 점수 함수에는 금속 배위 항이 '
            '없으므로 금속을 지우는 것은 근사가 아니라 빈 공간으로 바꾸는 것입니다: '
            + json.dumps(nearby, ensure_ascii=False))
    if not any(len(c) for c in structure[0]):
        raise ValueError('준비할 단백질 사슬이 없습니다.')
    structure.remove_alternative_conformations()
    receptor = work / 'receptor-source.pdb'
    structure.write_pdb(str(receptor))
    output = work / 'receptor'
    command = [sys.executable, str(Path(sys.executable).parent / 'mk_prepare_receptor.py'),
               '--read_pdb', str(receptor), '-o', str(output), '-p', '--write_pdb', str(work / 'receptor-prepared.pdb')]
    with (work / 'receptor-preparation.log').open('wb') as log:
        completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=240, check=False)
    if completed.returncode != 0 or not output.with_suffix('.pdbqt').exists():
        raise ValueError('Meeko 구조 준비가 끝나지 않았습니다. 결측/잔기/양성자화 조건을 검토해야 합니다. 실패 기록은 실행 폴더에 보존했습니다.')
    return output.with_suffix('.pdbqt'), {'site': site, 'chain_renaming': renamed, 'removed_components': removed,
        'alternate_location_policy': 'Gemmi first conformer; original mmCIF retained',
        'hydrogen_charge_preparation': 'Meeko 0.7.1 default residue templates and Gasteiger; no allow_bad_res',
        'limitations': ['Rigid receptor; removed waters and co-crystal ligand(s)', 'Terminal truncations/alternate states and protonation require scientific review; no implicit missing-atom repair']}


def dock_molecules(content, meta, structure_data, arguments, work):
    from rdkit import Chem
    from rdkit.Chem import AllChem
    from vina import Vina
    from meeko import MoleculePreparation, PDBQTWriterLegacy, PDBQTMolecule, RDKitMolCreate
    from posebusters import PoseBusters
    work.mkdir(exist_ok=False)
    header, inputs = molecule_rows(content, meta)
    id_column = meta.get('id_column', 'cid')
    smiles_column = meta.get('smiles_column', 'smiles')
    if id_column not in header or smiles_column not in header:
        raise ValueError('후보 ID와 SMILES 열을 확인해 주세요.')
    selected = arguments['candidate_ids']
    if not selected or len(selected) != len(set(selected)) or len(selected) > 12:
        raise ValueError('중복 없는 후보 1–12개를 선택해 주세요.')
    chosen = [r for r in inputs if r.get('candidate_id') in selected]
    if len(chosen) != len(selected) or {r['candidate_id'] for r in chosen} != set(selected):
        raise ValueError('후보 ID의 누락 또는 중복이 있습니다. 원행을 확인해 주세요.')
    receptor, preparation = prepare_receptor(structure_data, arguments['site_id'], work)
    exhaustiveness = arguments['exhaustiveness']
    if exhaustiveness not in (8, 16, 32) or type(arguments['seed']) is not int or not 1 <= arguments['seed'] <= 2147483647:
        raise ValueError('도킹 계산량과 난수 시드를 확인해 주세요.')
    center = preparation['site']['center_angstrom']
    protocol = {'method': 'AutoDock Vina rigid receptor, known co-crystal site', 'pdb_id': structure_data['pdb_id'],
                'assembly_id': structure_data['assembly_id'], 'structure_sha256': structure_data['source']['sha256'],
                'center_angstrom': center, 'box_size_angstrom': DOCKING_BOX_ANGSTROM, 'seed': arguments['seed'],
                'seed_roles': {'initial_conformer_generation': arguments['seed'],
                               'vina_search_stream_initialization': arguments['seed'],
                               'coupled_in_this_interface': True,
                               'candidate_order': [r['candidate_id'] for r in chosen],
                               'search_stream_policy': 'One Vina instance, retained candidate order; not independent streams per candidate'},
                'conformer_scope': 'One ETKDG/MMFF initial conformer per candidate. Small rings and unregistered torsions stay fixed during Vina search; more exhaustiveness is not a conformer ensemble.',
                'exhaustiveness': exhaustiveness, 'cpu': 2, 'requested_poses': 5,
                'versions': {p: importlib.metadata.version(p) for p in ('vina', 'meeko', 'gemmi', 'posebusters', 'rdkit')},
                'preparation': preparation}
    receptor_files = {name: (work / name).read_text() for name in
                      ('receptor.pdbqt', 'receptor-source.pdb', 'receptor-prepared.pdb')}
    protocol['receptor_files_sha256'] = {name: hashlib.sha256(raw.encode()).hexdigest()
                                        for name, raw in receptor_files.items()}
    (work / 'protocol.json').write_text(json.dumps(protocol, indent=2) + '\n')
    v = Vina(sf_name='vina', cpu=2, seed=arguments['seed'], verbosity=0)
    v.set_receptor(str(receptor))
    # Compute all atom-type maps before setting any one ligand.
    v.compute_vina_maps(center=center, box_size=DOCKING_BOX_ANGSTROM)
    rows, files = [], dict(receptor_files)
    for index, source in enumerate(chosen):
        row = {'candidate_id': source['candidate_id'], 'input_smiles': source['smiles'], 'source_row': source}
        try:
            if not source['width_matches']:
                raise ValueError('원 CSV 행의 열 수가 헤더와 다릅니다.')
            mol = Chem.MolFromSmiles(source['smiles']) if source['smiles'] else None
            if mol is None or len(Chem.GetMolFrags(mol)) != 1 or not 1 <= mol.GetNumHeavyAtoms() <= 100:
                raise ValueError('단일 성분의 유효한 소분자 구조가 필요합니다. 염/양성자화는 자동 변경하지 않습니다.')
            row['chemical_state'] = {'canonical_isomeric_smiles': Chem.MolToSmiles(mol),
                'formal_charge': Chem.GetFormalCharge(mol),
                'stereocenters': Chem.FindMolChiralCenters(mol, includeUnassigned=True),
                'hydrogen_state': 'As supplied; RDKit adds implicit H for 3D preparation',
                'pH_population': None, 'other_microstates_or_tautomers_enumerated': False}
            mol = Chem.AddHs(mol)
            params = AllChem.ETKDGv3(); params.randomSeed = arguments['seed']
            if AllChem.EmbedMolecule(mol, params) != 0:
                raise ValueError('3D conformer 생성 실패')
            if AllChem.MMFFHasAllMoleculeParams(mol):
                optimize_status = AllChem.MMFFOptimizeMolecule(mol, maxIters=500)
            else:
                raise ValueError('현재 MMFF 준비가 지원하지 않는 구조입니다.')
            if optimize_status != 0:
                raise ValueError('초기 conformer 최적화가 수렴하지 않았습니다.')
            setups = MoleculePreparation().prepare(mol)
            if len(setups) != 1:
                raise ValueError('여러 준비 상태의 명시적 비교가 필요합니다.')
            pdbqt, ok, error = PDBQTWriterLegacy.write_string(setups[0])
            if not ok:
                raise ValueError(error)
            input_name = f'candidate-{index + 1}-initial.pdbqt'
            (work / input_name).write_text(pdbqt)
            files[input_name] = pdbqt
            row.update(initial_structure_file=input_name,
                       initial_structure_sha256=hashlib.sha256(pdbqt.encode()).hexdigest(),
                       initial_conformer_seed=arguments['seed'],
                       search_stream_seed=arguments['seed'], candidate_execution_index=index,
                       torsion_tree=[line for line in pdbqt.splitlines()
                                     if line.startswith(('BRANCH', 'ENDBRANCH', 'TORSDOF'))])
            v.set_ligand_from_string(pdbqt)
            v.dock(exhaustiveness=exhaustiveness, n_poses=5)
            poses = v.poses(n_poses=5); energies = v.energies(n_poses=5).tolist()
            pose_name = f'candidate-{index + 1}-poses.pdbqt'
            (work / pose_name).write_text(poses); files[pose_name] = poses
            reconstructed = RDKitMolCreate.from_pdbqt_mol(PDBQTMolecule(poses, skip_typing=True))
            top = reconstructed[0] if len(reconstructed) == 1 else None
            if top is None:
                raise ValueError('포즈의 원래 결합 차수/전하 복원 실패')
            top = Chem.Mol(top); first = Chem.Conformer(top.GetConformer(0))
            top.RemoveAllConformers(); top.AddConformer(first, assignId=True)
            check = PoseBusters(config='dock').bust(top, mol_cond=str(work / 'receptor-source.pdb'), full_report=True)
            checks = json.loads(check.to_json(orient='records'))[0]
            sd = Chem.SDWriter(str(work / f'candidate-{index + 1}-top.sdf')); sd.write(top); sd.close()
            files[f'candidate-{index + 1}-top.sdf'] = (work / f'candidate-{index + 1}-top.sdf').read_text()
            row.update(status='succeeded', vina_score_kcal_mol=energies[0][0], pose_scores_kcal_mol=[e[0] for e in energies],
                       pose_count=len(energies), posebusters=checks, pose_file=pose_name,
                       interpretation='Docking score and pose validity under recorded conditions; no measured affinity/efficacy/selectivity')
        except Exception as exc:
            row.update(status='failed', error=str(exc)[:600])
        rows.append(row)
    succeeded = sum(r['status'] == 'succeeded' for r in rows)
    return {'status': 'succeeded' if succeeded == len(rows) else 'partial' if succeeded else 'failed',
            'semantic_type': 'rigid_receptor_docking_and_pose_checks', 'protocol': protocol, 'rows': rows,
            'raw_output_files': files, 'summary': {'requested': len(rows), 'computed': succeeded, 'failed': len(rows) - succeeded},
            'limits': ['점수는 기록한 준비·포켓·탐색 조건의 계산 결과이며 측정 친화도, 선택성, 세포 효과가 아닙니다.',
                       '공결정 포즈 재현과 양성/음성 대조를 별도 확인하고 assay·조건이 대응하는 측정 근거와 대조해야 합니다.',
                       '단백질 유연성, 물/보조인자, 리간드 양성자화·타우토머의 다른 상태는 이 실행에서 비교하지 않았습니다.',
                       '후보당 초기 conformer1개이며 작은 고리·고정 결합 기하는 도킹 중 바뀌지 않습니다. 현재 시드는 초기 구조와 탐색에 함께 쓰므로 둘의 영향을 분리한 비교는 아닙니다.',
                       'PoseBusters는 기하·입체 충돌 점검입니다. 통과해도 생물학적 결합을 증명하지 않습니다.']}
