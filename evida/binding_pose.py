"""Review saved poses against deposited alternatives and a fixed-pose CNN score.

Reference geometry never selects the input poses, adjusts them, or changes the
original Vina ranks. A missing same-compound reference remains unknown.
"""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess

from .science import fetch
from .resource_integrity import verify_file


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def configuration():
    return json.loads((Path(__file__).parents[1] / 'configs/binding-resources.json').read_text())


def fixed_geometry(output, original):
    """Accept atom reindexing, reject chemical/coordinate changes; never fit."""
    import numpy as np
    from rdkit import Chem
    output, original = Chem.RemoveHs(output), Chem.RemoveHs(original)
    if Chem.MolToSmiles(output) != Chem.MolToSmiles(original):
        raise ValueError('재점수화 출력의 화학적 구조가 입력과 다릅니다.')
    maps = output.GetSubstructMatches(original, uniquify=False, useChirality=True, maxMatches=10000)
    if not maps or len(maps) == 10000:
        raise ValueError('좌표를 비교할 원자 대응이 없거나 대응 열거가 불완전합니다.')
    target, points = original.GetConformer().GetPositions(), output.GetConformer().GetPositions()
    error, mapping = min((float(np.abs(points[list(m)] - target).max()), m) for m in maps)
    if error > .00011:
        raise ValueError('고정 포즈 재점수화에서 원자 좌표가 SDF 정밀도보다 크게 바뀌었습니다.')
    return {'maximum_delta_angstrom': error, 'original_to_output_atom_indices': list(mapping),
            'atom_order_changed': list(mapping) != list(range(len(mapping))), 'rigid_fit': False}


def deposited_references(structure, site_id, ccd_text):
    """CCD bonds + the selected residue's actual altloc coordinates, not ideals."""
    import gemmi
    from rdkit import Chem
    if sha(structure['original_cif'].encode()) != structure['source']['sha256']:
        raise ValueError('구조 원문 해시가 다릅니다.')
    component = site_id.rsplit(':', 1)[-1]
    if not re.fullmatch(r'[A-Z0-9]{1,5}', component):
        raise ValueError('원 구조의 성분 ID를 확인해 주세요.')
    ccd = gemmi.cif.read_string(ccd_text).sole_block()
    if ccd.find_value('_chem_comp.id').strip("'\"") != component:
        raise ValueError('CCD 성분이 선택 부위와 다릅니다.')
    graph, names = Chem.RWMol(), {}
    for name, element, charge in ccd.find('_chem_comp_atom.', ['atom_id', 'type_symbol', 'charge']):
        if element in ('H', 'D'):
            continue
        if name in names:
            raise ValueError('CCD 원자 이름이 중복됩니다.')
        atom = Chem.Atom(element.title()); atom.SetFormalCharge(int(charge))
        names[name] = graph.AddAtom(atom)
    types = {'SING': Chem.BondType.SINGLE, 'DOUB': Chem.BondType.DOUBLE,
             'TRIP': Chem.BondType.TRIPLE, 'AROM': Chem.BondType.AROMATIC}
    for left, right, order in ccd.find('_chem_comp_bond.', ['atom_id_1', 'atom_id_2', 'value_order']):
        if left in names and right in names:
            if order not in types:
                raise ValueError('현재 비교기가 지원하지 않는 CCD 결합 종류입니다.')
            graph.AddBond(names[left], names[right], types[order])
    template = graph.GetMol(); Chem.SanitizeMol(template)
    if not names:
        raise ValueError('CCD 중원자 그래프가 없습니다.')
    model = gemmi.make_structure_from_block(gemmi.cif.read_string(structure['original_cif']).sole_block())
    selected = [(chain, residue) for chain in model[0] for residue in chain
                if f'{chain.name}:{residue.seqid}:{residue.name}' == site_id]
    if len(selected) != 1:
        raise ValueError('명시한 부위에 대응하는 원 좌표가 하나가 아닙니다.')
    chain, residue = selected[0]
    groups = {}
    for atom in residue:
        if atom.element.is_hydrogen:
            continue
        alt = '' if atom.altloc == '\x00' else atom.altloc
        group = groups.setdefault(alt, {})
        if atom.name in group:
            raise ValueError('같은 대체배치의 원자 이름이 중복됩니다.')
        group[atom.name] = atom
    alternatives = sorted(set(groups) - {''}) or ['']
    references, gaps = [], []
    for alt in alternatives:
        shared = groups.get('', {})
        specific = groups.get(alt, {}) if alt else {}
        if set(shared) & set(specific):
            gaps.append({'altloc': alt, 'reason': 'shared_and_specific_atom_overlap'}); continue
        atoms = {**shared, **specific}
        if set(atoms) != set(names):
            gaps.append({'altloc': alt, 'reason': 'incomplete_heavy_atom_correspondence',
                         'missing': sorted(set(names) - set(atoms)), 'extra': sorted(set(atoms) - set(names))}); continue
        reference = Chem.Mol(template); conf = Chem.Conformer(reference.GetNumAtoms()); conf.Set3D(True)
        for name, index in names.items():
            p = atoms[name].pos; conf.SetAtomPosition(index, (p.x, p.y, p.z))
        reference.AddConformer(conf, assignId=True)
        Chem.AssignStereochemistryFrom3D(reference)
        references.append((reference, {'site_id': site_id, 'altloc': alt,
            'occupancies': sorted({round(a.occ, 4) for a in atoms.values()}),
            'coordinate_sha256': sha(json.dumps(conf.GetPositions().tolist()).encode()),
            'smiles': Chem.MolToSmiles(reference)}))
    return references, gaps


def comparable_reference(molecule, reference):
    """Geometric comparison may normalize protonation only, recorded explicitly."""
    from rdkit import Chem
    from rdkit.Chem.MolStandardize import rdMolStandardize
    molecule, reference = Chem.RemoveHs(molecule), Chem.RemoveHs(reference)
    if Chem.MolToSmiles(molecule) == Chem.MolToSmiles(reference):
        return molecule, reference, 'same_declared_chemical_state'
    uncharger = rdMolStandardize.Uncharger()
    left, right = uncharger.uncharge(molecule), uncharger.uncharge(reference)
    if (left.GetNumHeavyAtoms() == molecule.GetNumHeavyAtoms()
            and right.GetNumHeavyAtoms() == reference.GetNumHeavyAtoms()
            and Chem.MolToSmiles(left) == Chem.MolToSmiles(right)):
        return left, right, 'charge_normalized_for_geometry_only_not_native_protonation'
    return None


def review_poses(docking, structure, arguments, work):
    from rdkit import Chem
    from rdkit.Chem import rdMolAlign
    from meeko import PDBQTMolecule, RDKitMolCreate
    if docking.get('semantic_type') != 'rigid_receptor_docking_and_pose_checks':
        raise ValueError('실제 완료한 도킹 자료가 필요합니다.')
    protocol = docking['protocol']
    if (protocol['structure_sha256'] != structure['source']['sha256']
            or sha(structure['original_cif'].encode()) != protocol['structure_sha256']):
        raise ValueError('원 도킹과 같은 구조 좌표를 선택해 주세요.')
    ids = arguments['candidate_ids']
    if not ids or len(ids) != len(set(ids)) or len(ids) > 12:
        raise ValueError('중복 없는 후보 1–12개를 선택해 주세요.')
    selected = [r for r in docking['rows'] if r['candidate_id'] in ids]
    if len(selected) != len(ids) or any(r.get('status') != 'succeeded' for r in selected):
        raise ValueError('실제 도킹이 완료된 후보를 선택해 주세요.')
    work.mkdir(exist_ok=False)
    source_files = docking.get('raw_output_files', {})
    site_id = protocol['preparation']['site']['ligand_id']
    component = protocol['preparation']['site']['component']
    if not re.fullmatch(r'[A-Z0-9]{1,5}', component):
        raise ValueError('원 공결정 성분 ID가 잘못됐습니다.')
    references, reference_gaps, source = [], [], None
    try:
        ccd, source = fetch(f'https://files.rcsb.org/ligands/download/{component}.cif')
        (work / 'reference-ccd.cif').write_bytes(ccd)
        references, reference_gaps = deposited_references(structure, site_id, ccd.decode())
    except Exception as exc:
        reference_gaps.append({'reason': type(exc).__name__, 'detail': str(exc)[:350]})
    inputs, rows, pose_files = {}, [], {}
    writer = Chem.SDWriter(str(work / 'saved-poses.sdf'))
    for number, item in enumerate(selected, 1):
        raw = source_files.get(item['pose_file'])
        if not isinstance(raw, str):
            raise ValueError('보존한 전체 포즈 파일이 없습니다.')
        mols = RDKitMolCreate.from_pdbqt_mol(PDBQTMolecule(raw, skip_typing=True))
        if len(mols) != 1 or mols[0] is None:
            raise ValueError('원 포즈의 결합 차수/전하를 복원하지 못했습니다.')
        molecule = mols[0]
        if molecule.GetNumConformers() != len(item['pose_scores_kcal_mol']):
            raise ValueError('포즈 수와 원 점수 수가 다릅니다.')
        pose_files[item['pose_file']] = sha(raw.encode())
        for index in range(molecule.GetNumConformers()):
            name = f'candidate-{number}-pose-{index + 1}'
            pose = Chem.Mol(molecule); conf = Chem.Conformer(molecule.GetConformer(index)); conf.Set3D(True)
            pose.RemoveAllConformers(); pose.AddConformer(conf, assignId=True); pose.SetProp('_Name', name)
            writer.write(pose); inputs[name] = pose
            comparisons = []
            for reference, metadata in references:
                comparable = comparable_reference(pose, reference)
                if comparable:
                    left, right, policy = comparable
                    comparisons.append({**metadata, 'comparison_policy': policy,
                        'rmsd_angstrom': float(rdMolAlign.CalcRMS(left, right)), 'rigid_fit': False})
            rows.append({'id': name, 'candidate_id': item['candidate_id'], 'original_vina_rank': index + 1,
                'original_vina_score_kcal_mol': item['pose_scores_kcal_mol'][index],
                'native_reference_status': 'COMPARED' if comparisons else 'DIFFERENT_COMPOUND_OR_UNAVAILABLE_REFERENCE',
                'reference_comparisons': comparisons,
                'nearest_reference_rmsd_angstrom': min((r['rmsd_angstrom'] for r in comparisons), default=None),
                'CNNscore': None, 'CNNaffinity': None, 'cnn_rank': None,
                'coordinate_verification': None})
    writer.close()
    rescore = {'requested': arguments['run_rescoring'], 'status': 'NOT_REQUESTED'}
    if arguments['run_rescoring']:
        receptor_text = source_files.get('receptor.pdbqt')
        expected = protocol.get('receptor_files_sha256', {}).get('receptor.pdbqt')
        if not receptor_text or not expected:
            rescore.update(status='EXACT_RECORDED_RECEPTOR_MISSING',
                next_action='기존 포즈/기준 비교는 보존합니다. 원 수용체가 보존되는 새 도킹을 명시적으로 실행한 뒤 재점수화하세요. 수용체를 임의 재구성하지 않았습니다.')
        elif sha(receptor_text.encode()) != expected:
            raise ValueError('보존 수용체 해시가 원 도킹과 다릅니다.')
        else:
            config = configuration(); binary = Path(config['gnina']['binary'])
            verify_file(binary, config['gnina']['sha256'])
            receptor = work / 'receptor.pdbqt'; receptor.write_text(receptor_text)
            output = work / 'rescored.sdf'
            command = [str(binary), '--score_only', '--no_gpu', '--cpu', '2', '--seed', '20260926',
                       '--cnn_scoring', 'rescore', '--addH', '0', '--scoring', 'vina',
                       '-r', str(receptor), '-l', str(work / 'saved-poses.sdf'), '-o', str(output)]
            rescore.update(binary_sha256=config['gnina']['sha256'], command=command,
                           version=config['gnina']['version'], receptor_sha256=expected)
            try:
                with (work / 'rescore.log').open('xb') as log:
                    completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=1800,
                        env={'PATH': '/usr/bin:/bin', 'OMP_NUM_THREADS': '2', 'OPENBLAS_NUM_THREADS': '2'})
                rescore['returncode'] = completed.returncode
                if completed.returncode != 0 or not output.is_file():
                    raise ValueError('GNINA가 결과를 완료하지 못했습니다.')
                by_id, seen, scored = {r['id']: r for r in rows}, set(), []
                for mol in Chem.SDMolSupplier(str(output), removeHs=False):
                    if mol is None:
                        raise ValueError('재점수화 출력의 구조를 읽지 못했습니다.')
                    name = mol.GetProp('_Name')
                    if name in seen or name not in by_id:
                        raise ValueError('재점수화 후보 포즈 대응이 바뀌었습니다.')
                    seen.add(name)
                    values = {'coordinate_verification': fixed_geometry(mol, inputs[name]),
                              'CNNscore': float(mol.GetProp('CNNscore')), 'CNNaffinity': float(mol.GetProp('CNNaffinity')),
                              'gnina_empirical_score': float(mol.GetProp('minimizedAffinity'))}
                    scored.append((name, values))
                if seen != set(by_id):
                    raise ValueError('재점수화 출력에 누락 포즈가 있습니다.')
                for name, values in scored:
                    by_id[name].update(values)
                for cid in ids:
                    ranked = sorted((r for r in rows if r['candidate_id'] == cid), key=lambda r: (-r['CNNscore'], r['original_vina_rank']))
                    for rank, row in enumerate(ranked, 1):
                        row['cnn_rank'] = rank
                rescore.update(status='COMPLETED', fixed_pose_count=len(seen), output_sha256=sha(output.read_bytes()))
            except Exception as exc:
                rescore.update(status='FAILED_OUTPUT_PRESERVED', error_type=type(exc).__name__, detail=str(exc)[:350])
    comparisons = []
    for cid in ids:
        same = [r for r in rows if r['candidate_id'] == cid]
        top = next(r for r in same if r['original_vina_rank'] == 1)
        cnn_top = next((r for r in same if r['cnn_rank'] == 1), None)
        distances = [r['nearest_reference_rmsd_angstrom'] for r in same if r['nearest_reference_rmsd_angstrom'] is not None]
        comparisons.append({'candidate_id': cid, 'original_top_pose': top['id'],
            'original_top_native_rmsd_angstrom': top['nearest_reference_rmsd_angstrom'],
            'closest_returned_native_rmsd_angstrom': min(distances, default=None),
            'cnn_top_pose': cnn_top['id'] if cnn_top else None,
            'cnn_top_original_rank': cnn_top['original_vina_rank'] if cnn_top else None,
            'cnn_top_native_rmsd_angstrom': cnn_top['nearest_reference_rmsd_angstrom'] if cnn_top else None,
            'pose_order_changed': cnn_top['id'] != top['id'] if cnn_top else None})
    return {'status': 'partial' if reference_gaps or rescore['status'] not in ('NOT_REQUESTED','COMPLETED') else 'succeeded',
        'semantic_type': 'saved_pose_ranking_and_same_compound_reference_review',
        'protocol': {'original_docking_protocol': protocol, 'original_pose_hashes': pose_files,
            'reference_site_id': site_id, 'reference_source': source,
            'reference_scope': 'Only the selected deposited residue, each explicit altloc. CCD supplies bonds, never ideal coordinates. Assembly copies are not independent experiments.',
            'reference_coordinate_gaps': reference_gaps, 'rescoring': rescore,
            'native_diagnostic_distance_angstrom': 2, 'native_not_used_to_select_or_adjust_poses': True,
            'versions': {n: importlib.metadata.version(n) for n in ('rdkit','meeko','gemmi')}},
        'rows': rows, 'candidate_comparisons': comparisons,
        'summary': {'candidates': len(ids), 'saved_poses': len(rows),
            'same_compound_reference_candidates': sum(c['original_top_native_rmsd_angstrom'] is not None for c in comparisons),
            'rescoring_status': rescore['status'], 'changed_pose_order_candidates': sum(c['pose_order_changed'] is True for c in comparisons)},
        'limits': ['포즈 재현·순위 비교입니다. 후보 간 실제 친화도·선택성·세포 효능의 순위가 아닙니다.',
            '다른 화합물/서열의 공결정 좌표에 RMSD를 강제로 대응하지 않습니다. 기준 부재는 실패 점수가 아닙니다.',
            '기준 구조를 아는 개발 사례이며 GNINA 학습자료 중복을 배제하지 않았습니다. 일반 성능 검증이 아닙니다.',
            'Vina·CNN·구조 검사는 같은 입력에 의존합니다. 독립 증거로 합산하거나 CNNscore를 성공 확률로 읽지 않습니다.',
            '원 순위와 모든 반환 포즈를 유지합니다. 포즈 순위 문제인지 구조/화학 상태인지, 기능·노출·변이 근거와 함께 다음 판단을 정해야 합니다.']}
