"""Researcher reports and preserved source identities, never experimental certification."""
import copy
import hashlib

# Explicit scientific files/results; internal model, decision and review records are excluded.
SOURCE_KINDS = frozenset('''source_file source_document molecule_csv rna_table article webpage
repository_document literature lens_literature binding_measurements bioactivities chembl_search
chemical_names chemical_sirna_evidence clinical_trial clinical_trial_search compound_candidates
compound_selection disease_targets drug_label drug_label_search entity_search gtopdb_pharmacology
literature_compounds open_targets public_lookup_bundle rdkit admet molecular_docking
pathway_hypotheses pathway_robustness regulon_activity analogue_proposal
rna_activity_score rna_allele_scenario rna_author_full rna_author_mod rna_candidate_generation
rna_candidate_selection rna_candidate_space rna_chemistry_evidence rna_delivery_response
rna_delivery_simulation rna_duplex rna_duplex_seed rna_duplex_transcriptome rna_gene_review
rna_observations rna_reference rna_reference_archive rna_reference_panel rna_reference_release
rna_region_annotation rna_seed_analysis rna_seed_sites rna_sequence_evaluation rna_tissue_context
rna_transcriptome_search rna_variant_catalog rna_weighted_distribution structure_search
target_context target_disease_evidence target_structure'''.split())
REPORT_FIELDS = frozenset(('measurement_validity', 'intervention_status', 'precision', 'context_match'))
SOURCE_FIELDS = ('source_artifact_ids', 'source_artifact_hashes', 'source_artifact_refs')


def validate_report(report):
    if not isinstance(report, dict) or not REPORT_FIELDS <= set(report) or set(report) - REPORT_FIELDS - {'assessment_basis'}:
        raise ValueError('관측 보고의 측정·개입·정밀도·조건 일치를 모두 지정해 주세요.')
    for key in ('measurement_validity', 'intervention_status'):
        if report[key] not in ('validated', 'failed', 'unknown'):
            raise ValueError('측정·개입 보고는 validated/failed/unknown 중 하나입니다.')
    if report['precision'] not in ('adequate', 'insufficient', 'unknown'):
        raise ValueError('정밀도 보고는 adequate/insufficient/unknown 중 하나입니다.')
    if report['context_match'] is not None and type(report['context_match']) is not bool:
        raise ValueError('조건 일치 보고는 true/false/null 중 하나입니다.')
    if 'assessment_basis' in report and (not isinstance(report['assessment_basis'], str) or len(report['assessment_basis']) > 10000):
        raise ValueError('관측 보고 근거는 10,000자 이내의 설명으로 남겨 주세요.')


def bind_command(db, wid, body, event):
    """Called in the command transaction; only the server constructs source receipts."""
    if any(k in body for k in SOURCE_FIELDS[1:]):
        raise ValueError('자료 해시와 원자료 정보는 서버가 확인해 기록합니다.')
    if 'measurement_report' not in body and 'source_artifact_ids' not in body:
        return
    if not body.get('research_context'):
        raise ValueError('관측 보고와 자료를 원 판단·확인에 연결해 주세요.')
    if 'measurement_report' in body:
        validate_report(body['measurement_report'])
    if 'source_artifact_ids' in body:
        aids = body['source_artifact_ids']
        if (not isinstance(aids, list) or len(aids) > 24
                or any(not isinstance(a, str) or not a or len(a) > 128 for a in aids)
                or len(set(aids)) != len(aids)):
            raise ValueError('중복 없는 원자료 ID를 24개 이내로 선택해 주세요.')
        refs = []
        for aid in aids:
            row = db.execute('SELECT id,title,kind,sha256,content FROM artifacts WHERE workspace=? AND id=?', (wid, aid)).fetchone()
            if row is None or row['kind'] not in SOURCE_KINDS:
                raise ValueError('현재 연구에 보존된 과학 원자료·계산 결과만 연결할 수 있습니다.')
            if hashlib.sha256(row['content']).hexdigest() != row['sha256']:
                raise ValueError('관측 원자료의 저장 해시가 일치하지 않습니다.')
            refs.append({k: row[k] for k in ('id', 'title', 'kind', 'sha256')})
        event['source_artifact_refs'] = refs
        event['source_artifact_hashes'] = {r['id']: r['sha256'] for r in refs}


def preserved_fields(body):
    return {key: copy.deepcopy(body[key]) for key in ('measurement_report', 'reported_subject_refs', 'subject_binding') + SOURCE_FIELDS if key in body}


def compare_report(body, assessment):
    """Literal reported-state differences; neither side certifies scientific validity."""
    if 'measurement_report' not in body:
        return None
    report = body['measurement_report']
    validate_report(report)
    differences = [{'field': key, 'reported': report[key], 'interpreted': assessment[key]}
                   for key in sorted(REPORT_FIELDS) if report[key] != assessment[key]]
    return {'message_id': body['message_id'], 'differences': differences,
            'report_is_researcher_declaration': True, 'scientific_validation': False}


def guarded_calculation(problem, retained, assessment, body, *, calculation_version='1'):
    """Version 1: reported unknown/failure cannot be promoted to a passing filter."""
    from .next_observation import select, hold_calculation
    calculated = select(problem, retained, assessment, calculation_version=calculation_version)
    guard = None
    if assessment is not None and 'measurement_report' in body:
        comparison = compare_report(body, assessment)
        passes = {'measurement_validity': 'validated', 'intervention_status': 'validated',
                  'precision': 'adequate', 'context_match': True}
        conflicts = [d for d in comparison['differences']
                     if d['interpreted'] == passes[d['field']] and d['reported'] != passes[d['field']]]
        guard = {'version': '1', 'applied': bool(conflicts), 'conflicts': conflicts,
                 'meaning': 'Conservative exclusion hold for an explicit researcher report; neither report nor model interpretation is experimental certification.'}
        if conflicts:
            calculated = select(problem, retained, None, calculation_version=calculation_version)
            if calculation_version == '2':
                hold_calculation(calculated, 'report_confirmation_required', assessment['check_id'])
            else:
                calculated['summary'].update(selection_status='report_confirmation_required', selected_check_ids=[],
                                             cost=0, common_next_decisions=[])
                calculated.update(rows=[], unresolvable_pairs=[], conditional_exclusions=[])
    return calculated, guard
