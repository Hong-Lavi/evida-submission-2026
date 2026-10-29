"""Read-only qualification of saved generation output in the science worker.

Native sources can contain many assays per parent, repeated BindingDB rows, CSV
selections with no assay data, and guided rows whose display IDs repeat. None of
these is permission to invent a single assay or substitute the nearest molecule
for the actual generation parent.
"""
import sqlite3  # load stdlib before chemistry's linked libraries
import copy
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from .proposal_qualification import qualify


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def generation_contract(request, source_sha, proposal_sha):
    args = request['arguments']
    aid = args.get('generation_contract_artifact_id')
    if not aid:
        return False, None
    raw = Path(request['qualification_contract_path']).read_bytes()
    if digest(raw) != request['qualification_contract_sha256']:
        raise ValueError('Generation contract content SHA mismatch')
    value = json.loads(raw)
    expected = {'source_artifact_id': args['source_artifact_id'], 'source_sha256': source_sha,
                'proposal_artifact_id': args['artifact_id'], 'proposal_sha256': proposal_sha}
    if any(value.get(k) != v for k, v in expected.items()):
        raise ValueError('Generation contract is not bound to these exact saved outputs')
    required = value.get('require_parent_core_preservation')
    if type(required) is not bool:
        raise ValueError('Explicit preservation policy must be boolean')
    evidence = value.get('protocol_evidence') or {}
    content = evidence.get('content')
    if not isinstance(content, str) or not content or digest(content.encode()) != evidence.get('sha256'):
        raise ValueError('Generation policy requires retained protocol text with exact SHA')
    return required, {'artifact_id': aid, 'sha256': digest(raw), **expected,
                      'require_parent_core_preservation': required,
                      'protocol_sha256': evidence['sha256'], 'protocol_locator': evidence.get('locator'),
                      'meaning': 'Retained generation/review requirement, not an activity certificate'}


def native_result(proposal):
    return (proposal.get('semantic_type') == 'proposed_structure'
            or isinstance(proposal.get('guided_search'), dict))


def _row_id(row):
    return row.get('id') or row.get('candidate_id') or row.get('parent_id') or row.get('row_id')


def _ref(aid, sha, pointer, **extra):
    return {'artifact_id': aid, 'sha256': sha, 'json_pointer': pointer, **extra}


def _original(row):
    return copy.deepcopy({k: v for k, v in row.items() if not k.startswith('_qualification_')})


def recover_source_measurements(source, request):
    """Join a selected CSV to its exact saved pool, never by name or endpoint."""
    pool = request.get('qualification_source_pool')
    status = {'status': request.get('qualification_source_pool_status', 'not_applicable'),
              'matched_rows': 0, 'unresolved_rows': 0}
    if not pool:
        return source, status
    raw = Path(pool['path']).read_bytes()
    meta = request['qualification_source_meta']
    if (digest(raw) != pool['sha256'] or meta.get('source_pool_id') != pool['artifact_id']
            or meta.get('source_pool_sha256') != pool['sha256']):
        raise ValueError('Saved source pool content SHA mismatch')
    from .science import analogue_source
    from rdkit import Chem, rdBase
    value = analogue_source(raw, pool['meta'])
    by_id = defaultdict(list)
    for index, row in enumerate(value.get('rows') or []):
        by_id[_row_id(row)].append((index, row))

    def representation(smiles):
        if not isinstance(smiles, str) or not smiles.strip():
            return None
        with rdBase.BlockLogs():
            mol = Chem.MolFromSmiles(smiles)
        return Chem.MolToSmiles(mol, isomericSmiles=True) if mol is not None and mol.GetNumHeavyAtoms() else None

    source = copy.deepcopy(source)
    declared_ids = meta.get('candidate_ids')
    for row in source.get('rows') or []:
        cid, smiles = _row_id(row), representation(row.get('smiles'))
        candidates = by_id.get(cid, [])
        same = bool(smiles and candidates and isinstance(declared_ids, list) and cid in declared_ids
                    and all(representation(parent.get('smiles')) == smiles for _, parent in candidates))
        row['_qualification_pool_match_status'] = 'exact_id_and_structure' if same else 'identity_unresolved'
        if not same:
            status['unresolved_rows'] += 1
            continue
        row['_qualification_measurement_sources'] = [
            {'original_parent': copy.deepcopy(parent),
             'source_ref': _ref(pool['artifact_id'], pool['sha256'], '/rows/' + str(index), row_id=cid)}
            for index, parent in candidates]
        status['matched_rows'] += 1
    status['source_ref'] = {'artifact_id': pool['artifact_id'], 'sha256': pool['sha256']}
    status['meaning'] = 'Exact candidate identity/structure links only; mixed assays remain separate and equivalence unknown.'
    return source, status


def _measurements(row, ref):
    """Keep each original measurement and its own reported context verbatim."""
    found = []
    for index, activity in enumerate(row.get('activities') or []):
        found.append({'source_ref': {**ref, 'json_pointer': ref['json_pointer'] + '/activities/' + str(index)},
                      'assay_id': activity.get('assay_chembl_id') or activity.get('assay_id'),
                      'assay_context': copy.deepcopy(activity.get('assay_context')),
                      'original_measurement': copy.deepcopy(activity)})
    raw = row.get('raw') or {}
    if 'affinity' in raw:
        found.append({'source_ref': {**ref, 'json_pointer': ref['json_pointer'] + '/raw'},
                      'assay_id': row.get('assay_id'),
                      'assay_context': copy.deepcopy(row.get('assay_context')),
                      'original_measurement': copy.deepcopy(raw)})
    for index, measurement in enumerate(row.get('measurements') or []):
        found.append({'source_ref': {**ref, 'json_pointer': ref['json_pointer'] + '/measurements/' + str(index)},
                      'assay_id': measurement.get('assay_chembl_id') or measurement.get('assay_id'),
                      'assay_context': copy.deepcopy(measurement.get('assay_context')),
                      'original_measurement': copy.deepcopy(measurement)})
    return found


def _paths(row):
    paths = copy.deepcopy(row.get('paths') or [])
    for recorded in row.get('all_observed_materialized_paths') or []:
        parent = recorded.get('parent') or {}
        paths.append({**copy.deepcopy(recorded), 'parent_id': parent.get('parent_id'),
                      'parent_smiles': parent.get('parent_smiles')})
    if paths:
        return paths
    if row.get('transformed_from'):
        return [{'parent_id': row['transformed_from'], 'role': 'transformation_parent',
                 'transformation': row.get('transformation'),
                 'declaration': 'transformed_from'}]
    # MMP donors are actual origins; declared_comparators/nearest_retrieved are not.
    return [{'parent_id': row[field], 'role': role, 'declaration': field}
            for field, role in (('core_from', 'core_donor'), ('substituent_from', 'substituent_donor'))
            if row.get(field)]


def qualify_native(source, proposal, wid, source_id, source_sha, proposal_id, proposal_sha,
                   *, core_preservation_required=False):
    from rdkit import Chem, DataStructs, rdBase
    from rdkit.Chem import rdFingerprintGenerator
    from rdkit.Chem.Scaffolds import MurckoScaffold

    def molecule(smiles):
        if not isinstance(smiles, str) or not smiles.strip():
            return None
        with rdBase.BlockLogs():
            value = Chem.MolFromSmiles(smiles)
        return value if value is not None and value.GetNumHeavyAtoms() else None

    def canonical(mol, stereo=True):
        return Chem.MolToSmiles(mol, isomericSmiles=stereo) if mol is not None else None

    fp = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048, includeChirality=True)
    source_rows = source.get('rows') or source.get('parents') or []
    parents = defaultdict(list)
    for index, row in enumerate(source_rows):
        if not isinstance(row, dict):
            raise ValueError('Source row must be a saved object')
        ident = _row_id(row)
        if isinstance(ident, str) and ident:
            parents[ident].append((row, molecule(row.get('smiles')), index))
    prints = [(pid, mol, fp.GetFingerprint(mol)) for pid, entries in parents.items()
              for _, mol, _ in entries if mol is not None]
    main = proposal.get('rows') or []
    ids = [_row_id(row) for row in main]
    if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('Stable, distinct main proposal IDs required')
    selected = proposal.get('selected_ids', ids)
    if (not isinstance(selected, list) or any(not isinstance(i, str) for i in selected)
            or len(set(selected)) != len(selected) or not set(selected) <= set(ids)):
        raise ValueError('Selected IDs not in the preserved proposal rows')
    entries = [('rows', i, row) for i, row in enumerate(main)]
    guided = (proposal.get('guided_search') or {}).get('rows') or []
    entries.extend(('guided_search/rows', i, row) for i, row in enumerate(guided))
    context = copy.deepcopy(source.get('assay_context') or {})
    qualified, groups = [], defaultdict(list)
    for branch, index, original in entries:
        row_id = _row_id(original)
        if not isinstance(row_id, str) or not row_id:
            raise ValueError('Stable proposal row ID required')
        key = branch + '/' + str(index)
        mol = molecule(original.get('smiles'))
        issues, findings, links, unresolved = [], [], [], []
        if mol is None:
            issues.append('proposal_structure_unresolved')
        paths = _paths(original)
        by_parent = defaultdict(list)
        for path in paths:
            pid = path.get('parent_id') or (path.get('parent') or {}).get('parent_id')
            stated = path.get('parent_smiles') or (path.get('parent') or {}).get('parent_smiles')
            output = path.get('generated_smiles') or path.get('smiles')
            if output is not None and (molecule(output) is None or canonical(molecule(output)) != canonical(mol)):
                raise ValueError('Observed generation path output does not match proposal structure')
            candidates = parents.get(pid, [])
            declared_branch = path.get('parent_branch')
            generated_parent = (declared_branch in ('guided_search', 'guided_search/rows')
                                or (not declared_branch and branch != 'rows' and original.get('round', 1) > 1))
            if generated_parent:
                # A display ID is reused in historic rounds. Require recorded structure and
                # earlier round; never attach a same-named main proposal by accident.
                previous = path.get('parent_round')
                candidates = [(r, molecule(r.get('smiles')), j) for j, r in enumerate(guided)
                              if _row_id(r) == pid and isinstance(previous, int)
                              and r.get('round') == previous and previous < original.get('round', 0)
                              and stated and canonical(molecule(r.get('smiles'))) == canonical(molecule(stated))]
            representations = {canonical(m) for _, m, _ in candidates}
            if not candidates or len(representations) != 1 or None in representations:
                unresolved.append({'parent_id': pid, 'status': 'unresolved_generated_parent' if generated_parent
                                   else 'parent_identity_unresolved', 'recorded_path': copy.deepcopy(path)})
                continue
            if stated and canonical(molecule(stated)) not in representations:
                raise ValueError('Parent ID is bound to a different structure')
            by_parent[(pid, generated_parent)].append((path, candidates))
        if unresolved or not by_parent:
            issues.append('actual_generation_parent_unresolved')
        for (pid, generated_parent), declared in by_parent.items():
            candidates = declared[0][1]
            parent, pmol, parent_index = candidates[0]
            parent_paths = [p for p, _ in declared]
            # A substituent donor's full Murcko scaffold is not the protected core.
            core_checked = any(p.get('role') != 'substituent_donor' for p in parent_paths)
            core = MurckoScaffold.GetScaffoldForMol(pmol)
            has_core = bool(core.GetNumHeavyAtoms()) and core_checked
            heavy = mol.HasSubstructMatch(core, useChirality=False) if mol is not None and has_core else None
            stereo = mol.HasSubstructMatch(core, useChirality=True) if mol is not None and has_core else None
            loss = heavy is True and stereo is False
            if heavy is False:
                findings.append('parent_core_changed')
                if core_preservation_required:
                    issues.append('protected_core_changed')
            if loss:
                findings.append('parent_core_stereo_lost_or_changed')
                if core_preservation_required:
                    issues.append('parent_core_stereo_lost_or_changed')
            if not has_core and core_checked:
                findings.append('parent_core_unavailable')
                if core_preservation_required:
                    issues.append('parent_core_unavailable')
            aid, sha, prefix = (proposal_id, proposal_sha, '/guided_search/rows/') if generated_parent else (source_id, source_sha, '/rows/')
            records, originals = [], []
            for raw_parent, _, ordinal in candidates:
                ref = _ref(aid, sha, prefix + str(ordinal), row_id=pid)
                if not generated_parent and source.get('semantic_type') == 'molecule_csv':
                    ref = {'artifact_id': aid, 'sha256': sha, 'row_id': pid,
                           'logical_csv_record_0_based': raw_parent.get('source_ref', {}).get('logical_csv_record_0_based')}
                originals.append({'source_ref': ref, 'original_parent': _original(raw_parent)})
                records.extend(_measurements(raw_parent, ref))
                for recovered in raw_parent.get('_qualification_measurement_sources') or []:
                    records.extend(_measurements(recovered['original_parent'], recovered['source_ref']))
                if raw_parent.get('_qualification_pool_match_status') == 'identity_unresolved':
                    issues.append('original_measurement_source_unresolved')
            links.append({'parent_id': pid, 'parent_kind': 'generated_unmeasured' if generated_parent else 'source_structure',
                          'source_ref': originals[0]['source_ref'],
                          'original_parent': _original(parent), 'original_source_rows': originals,
                          'measurement_source_rows': copy.deepcopy(parent.get('_qualification_measurement_sources') or []),
                          'reported_measurements': records, 'core_heavy_match': heavy, 'core_stereo_match': stereo,
                          'core_stereo_loss_or_change': loss,
                          'actual_parent_similarity': DataStructs.TanimotoSimilarity(fp.GetFingerprint(pmol), fp.GetFingerprint(mol)) if mol is not None else None,
                          'actual_generation_paths': copy.deepcopy(parent_paths)})
        reported = [r for link in links for r in link['reported_measurements']]
        assay_ids = sorted({r['assay_id'] for r in reported if r.get('assay_id')})
        if not reported and not context:
            issues.append('assay_context_unresolved')
        elif any(not r.get('assay_id') or not r.get('assay_context')
                 or not any((r.get('assay_context') or {}).get(k)
                            or r['original_measurement'].get(k)
                            for k in ('target_id', 'target', 'target_chembl_id'))
                 for r in reported):
            issues.append('assay_context_incomplete')
        unspecified = ([{'type': str(s.type), 'centeredOn': s.centeredOn, 'specified': str(s.specified)}
                        for s in Chem.FindPotentialStereo(mol) if str(s.specified) == 'Unspecified']
                       if mol is not None else [])
        connectivity = canonical(mol, False)
        group = digest(connectivity.encode()) if connectivity else None
        if group:
            groups[group].append(key)
        hold = bool(set(issues) & {'proposal_structure_unresolved', 'protected_core_changed', 'parent_core_stereo_lost_or_changed'})
        conditional = bool(issues) or bool(unspecified)
        prediction = {k: copy.deepcopy(v) for k, v in original.items()
                      if k.startswith('predicted_') or k in ('nearest_training_similarity', 'inside_applicability')}
        nearest = max((DataStructs.TanimotoSimilarity(fp.GetFingerprint(mol), p) for _, _, p in prints), default=None) if mol is not None else None
        exact = [{'parent_id': pid, 'source_ref': (
                    {'artifact_id': source_id, 'sha256': source_sha, 'row_id': pid,
                     'logical_csv_record_0_based': parent.get('source_ref', {}).get('logical_csv_record_0_based')}
                    if source.get('semantic_type') == 'molecule_csv' else
                    _ref(source_id, source_sha, '/rows/' + str(j), row_id=pid)),
                  'original_parent': _original(parent)}
                 for pid, values in parents.items() for parent, pmol, j in values
                 if mol is not None and pmol is not None and canonical(pmol) == canonical(mol)]
        qualified.append({'candidate_id': row_id, 'qualification_row_id': key,
                          'branch': 'main' if branch == 'rows' else 'guided_search', 'round': original.get('round'),
                          'original_smiles': original.get('smiles'), 'canonical_isomeric_smiles': canonical(mol),
                          'original_prediction': prediction, 'original_row_locator': _ref(proposal_id, proposal_sha, '/' + key),
                          'original_selected': branch == 'rows' and row_id in selected,
                          'proposal_status': 'identity_hold' if hold else 'stereo_resolution_needed' if unspecified else 'source_or_parent_unresolved' if issues else 'proposed_unmeasured',
                          'identity_status': 'hold' if hold else 'conditional' if conditional else 'inspectable_proposal',
                          'issues': sorted(set(issues)), 'structural_findings': sorted(set(findings)),
                          'core_preservation_required': core_preservation_required, 'unspecified_stereo': unspecified,
                          'connectivity_group': group, 'connectivity_smiles': connectivity,
                          'actual_parents': links, 'unresolved_actual_parents': unresolved,
                          'declared_comparators': copy.deepcopy(original.get('declared_comparators') or []),
                          'nearest_reported_comparator': {'candidate_id': original.get('nearest_retrieved'),
                                                          'smiles': original.get('nearest_retrieved_smiles'),
                                                          'generation_parent_inferred_from_similarity': False},
                          'nearest_source_parent_similarity': nearest, 'training_binding_verified': False,
                          'nearest_train_similarity': None, 'near_0_4': None,
                          'similarity_scope': 'Descriptive source similarity, not calibrated prediction reliability',
                          'measurement_status': 'new_comparison_not_performed', 'measured': False,
                          'exact_source_matches': exact, 'reported_assay_context': context,
                          'reported_assay_ids': assay_ids, 'reported_measurement_count': len(reported),
                          'assay_equivalence': 'not_established', 'complete_protocol_verified': False,
                          'predicted_values_are_not_parent_measurements': True,
                          'next_action': {'status': 'conditions_unresolved_not_ready' if issues or not reported else 'conditional_proposal_not_executed',
                                          'identity_precondition': 'Resolve structure, material/purity and complete assay protocol before comparison',
                                          'comparison': 'Confirm original parent measurements and run parent and analogue in the same assay batch with controls',
                                          'acceptance_margin': 'not_invented; depends on confirmed assay range/precision',
                                          'review_routes': {'credible_parent_relative_improvement': 'Review the matched biochemical claim; no disease efficacy inference',
                                                            'equal_or_worse': 'Reconsider the prediction-guided hypothesis',
                                                            'parent_not_reproduced_or_interference': 'Keep unresolved and check the measurement explanation'}}})
    for row in qualified:
        row['connectivity_group_members'] = groups.get(row['connectivity_group'], [])
    return {'status': 'qualified_with_preserved_holds', 'semantic_type': 'source_linked_proposal_qualification',
            'workspace': wid, 'source_ref': {'artifact_id': source_id, 'sha256': source_sha},
            'proposal_ref': {'artifact_id': proposal_id, 'sha256': proposal_sha},
            'original_row_ids': ids, 'original_selected_ids': copy.deepcopy(selected), 'selected_ids': copy.deepcopy(selected),
            'selected_row_keys': [r['qualification_row_id'] for r in qualified if r['original_selected']],
            'rows': qualified, 'connectivity_groups': dict(groups), 'rank_or_selection_changed': False,
            'source_and_proposal_written': False, 'new_fit_inference_generation': 0, 'measured': False,
            'summary': {'rows': len(qualified), 'main_rows': len(main), 'guided_rows': len(guided), 'selected': len(selected),
                        'holds': sum(r['identity_status'] == 'hold' for r in qualified),
                        'selected_holds': sum(r['identity_status'] == 'hold' and r['original_selected'] for r in qualified)},
            'limits': ['No generation, model fit, new prediction, measured activity or efficacy.',
                       'Each source assay retains its conditions; an equal endpoint is not evidence of assay equivalence.',
                       'Nearest comparator is not an actual generation parent without a retained generation path.',
                       'Native results without an exact retained training packet have unknown verified training similarity.']}


def run(request, content):
    args, wid = request['arguments'], request['workspace']
    source_raw = Path(request['qualification_source_path']).read_bytes()
    source_sha = request['qualification_source_sha256']
    proposal_sha = request['qualification_proposal_sha256']
    if digest(source_raw) != source_sha or digest(content) != proposal_sha:
        raise ValueError('Worker snapshot content SHA mismatch')
    proposal = json.loads(content)
    source_id, proposal_id = args['source_artifact_id'], args['artifact_id']
    if proposal.get('source_artifact_id') != source_id:
        raise ValueError('Retained proposal does not identify the selected source')
    if proposal.get('source_sha256') and proposal['source_sha256'] != source_sha:
        raise ValueError('Proposal is not bound to this exact source snapshot')
    if not isinstance(proposal.get('rows'), list) or not proposal['rows']:
        raise ValueError('Retained proposal has no actual output rows')
    required, contract_ref = generation_contract(request, source_sha, proposal_sha)
    from .science import analogue_source
    source = analogue_source(source_raw, request['qualification_source_meta'])
    if not isinstance(source, dict):
        raise ValueError('Saved source must identify its source rows')
    native = native_result(proposal)
    if native:
        source, pool_review = recover_source_measurements(source, request)
        result = qualify_native(source, proposal, wid, source_id, source_sha, proposal_id, proposal_sha,
                                core_preservation_required=required)
        result['measurement_source_recovery'] = pool_review
    else:
        class Snapshots:
            def artifact(self, workspace, aid):
                if workspace != wid or aid not in (source_id, proposal_id):
                    raise ValueError('Foreign worker snapshot')
                raw = source_raw if aid == source_id else content
                return {'workspace': wid, 'content': raw, 'sha256': digest(raw)}
        result = qualify(Snapshots(), wid, source_id, source_sha, proposal_id, proposal_sha,
                         core_preservation_required=required)
    result['qualification_status'], result['status'] = result['status'], 'succeeded'
    rows, selected = result['rows'], set(result['selected_ids'])
    selected_rows = [r for r in rows if r.get('original_selected', r['candidate_id'] in selected)]
    selected_positions = {r['candidate_id']: (index, r) for index, r in enumerate(rows)
                          if r.get('original_selected', r['candidate_id'] in selected)}
    result['selected_preview'] = [
        {'candidate_id': cid, 'proposal_status': selected_positions[cid][1]['proposal_status'],
         'original_rank': rank, 'row_index': selected_positions[cid][0]}
        for rank, cid in enumerate(result['selected_ids'][:100], 1)]
    result['selected_preview_total'] = len(result['selected_ids'])
    result['selected_preview_has_more'] = len(result['selected_ids']) > 100
    result['reported_assay_context'] = copy.deepcopy(source.get('assay_context') or {})
    # Count proposal rows with retained parent measurements, not distinct parents.
    # The reviewed source-local format stores original values in label; its
    # pIC50 summary alone is not enough to claim underlying measurement records.
    measured_parent_rows = sum(any(
        p.get('reported_measurements')
        or (p.get('original_parent', {}).get('label') or {}).get('source_values_nm')
        for p in row['actual_parents']) for row in rows)
    result['summary'].update({
        'source_conditions_known': bool(rows) and all(not set(r['issues']) & {'assay_context_unresolved', 'assay_context_incomplete'} for r in rows),
        'complete_protocol_verified': False,
        'training_binding_verified': bool(rows) and all(r['training_binding_verified'] for r in rows),
        'status_counts': dict(Counter(r['proposal_status'] for r in rows)),
        'selected_status_counts': dict(Counter(r['proposal_status'] for r in selected_rows)),
        'unresolved': sum(r['identity_status'] != 'inspectable_proposal' for r in rows),
        'unresolved_meaning': 'Hold, stereo or unresolved source/parent; overlapping issues counted once',
        'stereo_resolution_needed': sum(r['proposal_status'] == 'stereo_resolution_needed' for r in rows),
        'core_preservation_required': required,
        'core_changes_observed': sum('parent_core_changed' in r['structural_findings'] for r in rows),
        'parents_with_original_measurements': measured_parent_rows,
        'proposal_rows_with_parent_measurements': measured_parent_rows,
        'new_comparison_performed': False,
        'full_rows_access': 'inspect_artifact with artifact_id of this result, offset and limit'})
    result['generation_contract_ref'] = contract_ref
    result['retained_source_conversion'] = {
        'native_adapter_used': native, 'source_artifact_id': source_id, 'source_sha256': source_sha,
        'proposal_artifact_id': proposal_id, 'proposal_sha256': proposal_sha,
        'selection_meaning': 'Original selected_ids or returned main-row order; guided rows retain branch/row identity. No new recommendation.',
        'meaning': 'Preserved source fields; no recovered assay conditions, generation, prediction or selection'}
    return result
