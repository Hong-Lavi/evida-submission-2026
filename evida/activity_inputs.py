"""Preserve reported measurements and select one endpoint for point fitting.

The selection uses input coverage before fitting. It changes no estimator,
fingerprint, split, or model acceptance threshold. Every excluded observation
keeps its original value, relation, endpoint and source position.
"""
from collections import Counter, defaultdict
import math
import re

ENDPOINTS = ('IC50', 'Ki', 'Kd', 'EC50', 'AC50', 'XC50', 'ED50', 'Potency')
_NUMBER = re.compile(r'^\s*(<=|>=|<|>|=|~|≤|≥|≈)?\s*([+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*$')
_INVERSE = {'=': '=', '<': '>', '>': '<', '<=': '>=', '>=': '<=', '~': '~'}


def nanomolar(value):
    """A boundary stays a boundary under the decreasing -log10 transform."""
    match = _NUMBER.fullmatch(str(value))
    if not match:
        return {'raw_value': value, 'status': 'invalid_numeric_value', 'point_value': None}
    relation = {'≤': '<=', '≥': '>=', '≈': '~'}.get(match[1], match[1]) or '='
    number = float(match[2])
    if not math.isfinite(number) or not 0 < number < 1e9:
        return {'raw_value': value, 'status': 'invalid_numeric_value', 'point_value': None}
    transformed = 9 - math.log10(number)
    return {'raw_value': value, 'reported_relation': relation, 'reported_value_nm': number,
            'p_relation': _INVERSE[relation], 'p_threshold': transformed,
            'point_value': transformed if relation == '=' else None,
            'status': 'exact' if relation == '=' else 'approximate' if relation == '~' else 'bound'}


def _finite_point(value):
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) and 0 < number < 15 else None


def observations(value, extra_sources=()):
    """Read both source formats, including BindingDB as the primary input."""
    records = []
    for source_index, source in enumerate((value, *(extra_sources or ()))):
        if not isinstance(source, dict):
            continue
        source_info = source.get('source') or {}
        for row_index, row in enumerate(source.get('rows') or []):
            raw = row.get('raw') or {}
            is_binding = source.get('semantic_type') == 'reported_bindingdb_measurements' or 'affinity_type' in raw
            if is_binding:
                parsed = nanomolar(raw.get('affinity'))
                duplicate = row.get('same_returned_representation_as_row') is not None
                records.append({**parsed, 'source': 'bindingdb', 'source_index': source_index,
                    'source_url': source_info.get('url') if isinstance(source_info, dict) else None,
                    'source_row_index': row_index, 'source_row_id': row.get('row_id'),
                    'candidate_id': row.get('candidate_id'), 'smiles': row.get('smiles') or raw.get('smile'),
                    'endpoint': str(raw.get('affinity_type') or '').strip() or None,
                    'assay_id': None, 'assay_context': row.get('assay_context'),
                    'doi': raw.get('doi'), 'pmid': raw.get('pmid'),
                    'duplicate_representation': duplicate})
                continue
            for activity_index, activity in enumerate(row.get('activities') or []):
                relation = activity.get('standard_relation')
                point = _finite_point(activity.get('pchembl_value'))
                # ChEMBL supplies pChEMBL for exact standard measurements. If a
                # local record explicitly contradicts that contract, retain it
                # for review instead of treating its supplied pChEMBL as exact.
                exact = point is not None and relation in (None, '=')
                parsed = nanomolar(str(relation or '') + str(activity.get('standard_value')))
                if activity.get('standard_units') != 'nM':
                    parsed = {'raw_value': activity.get('standard_value'), 'point_value': None}
                status = ('exact' if exact else (parsed.get('status') or 'unusable_reported_relation')
                          if relation not in (None, '=') else 'no_pchembl_value')
                records.append({**parsed, 'source': 'chembl', 'source_index': source_index,
                    'source_url': source_info.get('url') if isinstance(source_info, dict) else None,
                    'source_row_index': row_index, 'activity_index': activity_index,
                    'source_row_id': activity.get('activity_id'),
                    'candidate_id': row.get('candidate_id'), 'smiles': row.get('smiles'),
                    'endpoint': activity.get('standard_type') or activity.get('type'),
                    'raw_value': activity.get('standard_value'), 'raw_pchembl_value': activity.get('pchembl_value'),
                    'reported_relation': relation, 'reported_units': activity.get('standard_units'),
                    'p_relation': '=' if exact else parsed.get('p_relation'),
                    'p_threshold': point if exact else parsed.get('p_threshold'),
                    'point_value': point if exact else None, 'status': status,
                    'relation_basis': 'explicit_standard_relation' if relation else 'pchembl_source_contract',
                    'assay_id': activity.get('assay_chembl_id'),
                    'assay_context': activity.get('assay_context'),
                    'assay_description': activity.get('assay_description'),
                    'target_chembl_id': activity.get('target_chembl_id'),
                    'target_organism': activity.get('target_organism'),
                    'document_chembl_id': activity.get('document_chembl_id'),
                    'duplicate_representation': False})
    return records


def prepare(value, minimum_records=1, extra_sources=(), endpoint=None):
    records = observations(value, extra_sources)
    eligible = defaultdict(list)
    for index, record in enumerate(records):
        if record['duplicate_representation']:
            record['fit_exclusion'] = 'duplicate_representation'
        elif record['point_value'] is None:
            record['fit_exclusion'] = record['status']
        elif record['endpoint'] not in ENDPOINTS:
            record['fit_exclusion'] = 'unresolved_endpoint'
        elif not isinstance(record['smiles'], str) or not record['smiles'].strip():
            record['fit_exclusion'] = 'missing_structure'
        else:
            eligible[record['endpoint']].append(index)
    coverage = {kind: len({records[i]['smiles'] for i in indices}) for kind, indices in eligible.items()}
    if endpoint is not None and endpoint not in ENDPOINTS:
        raise ValueError('Select a reported activity endpoint.')
    selected = endpoint or (min(coverage, key=lambda kind: (-coverage[kind], ENDPOINTS.index(kind))) if coverage else None)
    groups = defaultdict(list)
    for kind, indices in eligible.items():
        for index in indices:
            if kind != selected:
                records[index]['fit_exclusion'] = 'different_endpoint'
            else:
                groups[records[index]['smiles']].append(index)
    rows = []
    for smiles, indices in groups.items():
        # Retain the established source preference within the same endpoint.
        preferred = [i for i in indices if records[i]['source'] == 'chembl']
        used = preferred if len(preferred) >= minimum_records else [i for i in indices if records[i]['source'] == 'bindingdb']
        for index in set(indices) - set(used):
            records[index]['fit_exclusion'] = 'same_structure_preferred_source'
        if len(used) < minimum_records:
            for index in used:
                records[index]['fit_exclusion'] = 'too_few_records'
            continue
        points = sorted(records[i]['point_value'] for i in used)
        middle = len(points) // 2
        median = points[middle] if len(points) % 2 else (points[middle - 1] + points[middle]) / 2
        first = records[used[0]]
        rows.append({'candidate_id': first['candidate_id'] or smiles, 'smiles': smiles,
                     'p_activity': round(median, 3), 'records': len(used), 'source': first['source'],
                     'assay_types': [selected], 'endpoint': selected, 'measurement_indices': used})
    summary = {'reported_records': len(records), 'selected_endpoint': selected,
               'endpoint_selection': 'explicit' if endpoint else 'largest_exact_structure_coverage_before_fit',
               'tie_order': list(ENDPOINTS), 'eligible_structure_counts_by_endpoint': coverage,
               'point_fit_structures': len(rows),
               'retained_bound_records': sum(r['status'] == 'bound' for r in records),
               'retained_approximate_records': sum(r['status'] == 'approximate' for r in records),
               'exclusion_counts': dict(Counter(r['fit_exclusion'] for r in records if 'fit_exclusion' in r)),
               'conditions': 'One reported endpoint. Assay, species and action conditions retain their source-specific meaning; equal endpoint names alone do not establish assay equivalence.'}
    return {'rows': rows, 'measurements': records, 'summary': summary}
