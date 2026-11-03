"""Exact saved-record concentration contrasts; source censoring is not uncertainty calibration."""
from __future__ import annotations

import copy
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import math
import re
from urllib.parse import urlparse

import jsonschema

TOOL = 'reported_activity_comparison'
SEMANTIC_TYPE = 'source_record_activity_contrast'


def obj(fields):
    return {'type': 'object', 'properties': fields, 'required': list(fields), 'additionalProperties': False}


TEXT = {'type': 'string', 'minLength': 1, 'maxLength': 1000}
REF = obj({'artifact_id': TEXT, 'json_pointer': TEXT})
SCHEMA = obj({'reference_target_id': TEXT, 'comparator_target_id': TEXT,
              'endpoint': {'type': 'string', 'enum': ['IC50', 'Ki', 'Kd', 'EC50']},
              'reason': {'type': 'string', 'minLength': 1, 'maxLength': 4000},
              'pairs': {'type': 'array', 'minItems': 1, 'maxItems': 60,
                        'items': obj({'reference': REF, 'comparator': REF})}})
SCALES = {u: Decimal(v) for u, v in {'pM': '1e-12', 'nM': '1e-9', 'uM': '1e-6',
          'µM': '1e-6', 'μM': '1e-6', 'mM': '1e-3', 'M': '1'}.items()}
CONDITION_FIELDS = ('assay_organism', 'assay_tax_id', 'assay_type', 'bao_format', 'assay_cell_type',
                    'assay_tissue', 'assay_strain', 'assay_subcellular_fraction', 'cell_chembl_id',
                    'tissue_chembl_id', 'assay_test_type', 'assay_parameters')
INDEX = r'(?:0|[1-9][0-9]*)'


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def loads(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, '출처 JSON 키가 중복됐습니다.')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('출처 JSON 숫자가 유한하지 않습니다: ' + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def validate_arguments(arguments):
    try:
        jsonschema.validate(arguments, SCHEMA)
    except jsonschema.ValidationError as exc:
        raise ValueError('보고 농도 대비 입력을 확인해 주세요: ' + exc.message[:300]) from None
    require(arguments['reason'].strip(), '비교 이유를 남겨 주세요.')
    for key in ('reference_target_id', 'comparator_target_id'):
        require(arguments[key].strip() == arguments[key] and arguments[key], '명시한 표적 ID를 확인해 주세요.')
    require(arguments['reference_target_id'] != arguments['comparator_target_id'], '서로 다른 두 표적을 명시해 주세요.')
    keys = [digest(p) for p in arguments['pairs']]
    require(len(keys) == len(set(keys)), '같은 원행 쌍을 중복 선택하지 마세요.')


def pointer(value, path):
    # Only literal native paths are accepted; no escape, negative or noncanonical indexes.
    require(isinstance(path, str) and path.startswith('/rows/'), '보존된 측정 원행 위치를 선택해 주세요.')
    try:
        for token in path[1:].split('/'):
            if isinstance(value, list):
                require(re.fullmatch(INDEX, token), '원행 번호가 올바르지 않습니다.')
                value = value[int(token)]
            else:
                require(isinstance(value, dict) and token in value, '선택한 원행 경로가 없습니다.')
                value = value[token]
    except (IndexError, KeyError):
        raise ValueError('선택한 원행 경로가 없습니다.') from None
    require(isinstance(value, dict), '하나의 측정 객체를 선택해 주세요.')
    return value


def prepare(store, wid, arguments):
    """Resolve selected native records and qualification links inside this workspace only."""
    validate_arguments(arguments)
    sources = {}
    def get(aid):
        require(isinstance(aid, str) and aid.strip() == aid and aid, '자료 ID를 확인해 주세요.')
        if aid not in sources:
            artifact = store.artifact(wid, aid)
            require(hashlib.sha256(artifact['content']).hexdigest() == artifact['sha256'], '원자료 바이트 해시가 다릅니다.')
            sources[aid] = {'kind': artifact['kind'], 'sha256': artifact['sha256'], 'value': loads(artifact['content'])}
        return sources[aid]

    def resolve(ref, depth=0):
        require(depth < 2, '원측정 연결은 보존 출처에 직접 연결해야 합니다.')
        source = get(ref['artifact_id']); kind = source['kind']; value = source['value']; path = ref['json_pointer']
        if kind == 'proposal_qualification':
            require(re.fullmatch(r'/rows/' + INDEX + '/actual_parents/' + INDEX + '/reported_measurements/' + INDEX, path),
                    '부모의 보존 측정 한 행을 선택해 주세요.')
            selected = pointer(value, path); original = selected.get('source_ref') or {}
            require(original.get('artifact_id') and original.get('sha256') and original.get('json_pointer'), '부모 원측정 연결이 완전하지 않습니다.')
            target = get(original['artifact_id'])
            require(target['sha256'] == original['sha256'], '부모 원측정의 보존 해시가 다릅니다.')
            resolved = resolve({k: original[k] for k in ('artifact_id', 'json_pointer')}, depth + 1)
            require(selected.get('original_measurement') == resolved['raw_record'], '부모 측정 사본이 원자료와 다릅니다.')
            resolved['selected_via'] = {'artifact_id': ref['artifact_id'], 'artifact_sha256': source['sha256'],
                                      'json_pointer': path, 'row_sha256': digest(selected)}
            return resolved
        patterns = {'bioactivities': r'/rows/' + INDEX,
                    'compound_candidates': r'/rows/' + INDEX + '/activities/' + INDEX}
        require(kind in patterns and re.fullmatch(patterns[kind], path), '공개 활성 원행 또는 후보의 원측정을 선택해 주세요.')
        raw = copy.deepcopy(pointer(value, path))
        require(len(encoded(raw)) <= 65536, '선택한 측정 행이 허용 크기를 넘었습니다.')
        receipt = value.get('source') or {}; url = receipt.get('url') or receipt.get('resolved_url') or ''
        parsed = urlparse(url)
        namespace = 'chembl' if parsed.hostname == 'www.ebi.ac.uk' and parsed.path.startswith('/chembl/api/data/activity') else None
        response = value.get('response') if kind == 'bioactivities' else value.get('original_activity_response')
        records = (response or {}).get('activities') or []
        original = {k: v for k, v in raw.items() if k != 'assay_context'}
        matching = [r for r in records if r.get('activity_id') == raw.get('activity_id')]
        require(len(matching) == 1 and matching[0] == original, '측정 행과 보존된 원 응답이 일치하지 않거나 중복됐습니다.')
        context = raw.get('assay_context')
        require(context is None or isinstance(context, dict), 'assay 조건은 원 객체 또는 null이어야 합니다.')
        # Enriched rows are copies. Only a retained assay response establishes which
        # structured conditions were actually returned. Older candidate artifacts
        # retain the copy but not that response; keep those fields unverified.
        assay_response = value.get('assay_response')
        condition_context = None
        context_status = 'unverified_copy' if context is not None else 'unreported'
        context_ref = None
        if assay_response is not None:
            require(isinstance(assay_response, dict) and isinstance(assay_response.get('assays'), list),
                    '보존 assay 원응답 형식을 확인해 주세요.')
            found = [(i, r) for i, r in enumerate(assay_response['assays'])
                     if isinstance(r, dict) and r.get('assay_chembl_id') == raw.get('assay_chembl_id')]
            require(len(found) <= 1, 'assay 원응답의 식별자가 중복됐습니다.')
            if found:
                position, original_context = found[0]
                require(context == original_context, 'assay 조건 사본이 보존 원응답과 다릅니다.')
                condition_context = copy.deepcopy(original_context)
                context_status = 'retained_assay_response'
                context_ref = {'artifact_id': ref['artifact_id'], 'artifact_sha256': source['sha256'],
                               'json_pointer': '/assay_response/assays/' + str(position),
                               'row_sha256': digest(original_context)}
            else:
                require(context is None, '조건 사본에 대응하는 보존 assay 원응답이 없습니다.')
        # A returned response may contain repeated measurements for the same source record.
        keyfields = ('document_chembl_id', 'record_id', 'molecule_chembl_id', 'canonical_smiles',
                     'target_chembl_id', 'assay_chembl_id', 'standard_type')
        ambiguous = sum(all(r.get(k) == raw.get(k) for k in keyfields) for r in records) != 1
        official = pointer(value, '/'.join(path.split('/')[:3])).get('smiles') if kind == 'compound_candidates' else None
        return {'source_ref': {'artifact_id': ref['artifact_id'], 'artifact_sha256': source['sha256'], 'sha256': source['sha256'],
                              'json_pointer': path, 'row_sha256': digest(raw)},
                'namespace': namespace, 'raw_record': raw, 'official_smiles': official,
                'condition_context': condition_context, 'assay_context_status': context_status,
                'assay_context_source_ref': context_ref,
                'source_record_ambiguous': ambiguous, 'source_receipt': copy.deepcopy(receipt)}

    pairs = [{side: resolve(p[side]) for side in ('reference', 'comparator')} for p in arguments['pairs']]
    return {'schema_version': 1, 'arguments': copy.deepcopy(arguments), 'pairs': pairs,
            'source_hashes': {aid: s['sha256'] for aid, s in sources.items()}}


def canonical_structure(smiles):
    if not isinstance(smiles, str) or not smiles.strip():
        return None
    from rdkit import Chem
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)


def side_record(bound):
    raw = copy.deepcopy(bound['raw_record'])
    fields = {'target_id': 'target_chembl_id', 'document_id': 'document_chembl_id', 'record_id': 'record_id',
              'activity_id': 'activity_id', 'molecule_id': 'molecule_chembl_id', 'canonical_smiles': 'canonical_smiles',
              'assay_id': 'assay_chembl_id', 'value': 'standard_value', 'relation': 'standard_relation',
              'units': 'standard_units', 'endpoint': 'standard_type', 'assay_description': 'assay_description',
              'assay_context': 'assay_context'}
    return {**{k: raw.get(v) for k, v in fields.items()}, **copy.deepcopy(bound)}


def known(value):
    return value is not None and value != '' and value != [] and value != {}


def review_conditions(a, b):
    matched, unknown, mismatches = [], [], []
    for field in ('target_organism', 'target_tax_id', 'assay_type', 'bao_format', 'bao_endpoint'):
        av, bv = a['raw_record'].get(field), b['raw_record'].get(field)
        if not known(av) or not known(bv): unknown.append('activity.' + field)
        elif str(av) == str(bv): matched.append('activity.' + field)
        else: mismatches.append({'field': 'activity.' + field, 'reference': av, 'comparator': bv})
    for field in CONDITION_FIELDS:
        av, bv = (a.get('condition_context') or {}).get(field), (b.get('condition_context') or {}).get(field)
        if not known(av) or not known(bv): unknown.append(field)
        elif av == bv: matched.append(field)
        else: mismatches.append({'field': field, 'reference': av, 'comparator': bv})
    # Free text and target/construct distinctions are preserved for the researcher.
    # Matching the returned structured fields never verifies the complete protocol.
    unknown.append('complete_protocol_and_construct_comparability')
    return {'status': 'known_mismatch' if mismatches else 'unknown_remaining', 'matched_fields': matched,
            'mismatches': mismatches, 'unknown_fields': unknown, 'complete_protocol_verified': False,
            'assay_context_authority': {side: row.get('assay_context_status', 'unverified_copy')
                                        for side, row in [('reference', a), ('comparator', b)]}}


def quantity(side):
    raw = side['raw_record']; value = side['value']
    if type(value) not in (str, int, float): return None, 'non_numeric_concentration'
    try: number = Decimal(str(value))
    except InvalidOperation: return None, 'non_numeric_concentration'
    if not number.is_finite() or number <= 0: return None, 'nonpositive_or_nonfinite_concentration'
    if abs(number.adjusted()) > 100: return None, 'concentration_outside_numeric_range'
    if len(number.as_tuple().digits) > 50: return None, 'concentration_exceeds_50_significant_digits'
    if side['units'] not in SCALES: return None, 'unsupported_concentration_unit'
    if side['relation'] not in ('=', '<', '<=', '>', '>='): return None, 'unsupported_or_missing_relation'
    if known(raw.get('standard_upper_value')): return None, 'additional_reported_range_requires_review'
    if known(raw.get('data_validity_comment')) or known(raw.get('data_validity_description')): return None, 'source_validity_flag'
    if raw.get('potential_duplicate') not in (None, 0, False, '0'): return None, 'source_potential_duplicate'
    if raw.get('standard_flag') not in (None, 1, True, '1'): return None, 'source_standardization_flag'
    # All supported units are exact powers of ten: adjust the exponent without
    # applying Decimal's ambient precision (which could falsely turn a ratio into 1).
    parts = number.as_tuple()
    n = Decimal((parts.sign, parts.digits, parts.exponent + SCALES[side['units']].as_tuple().exponent))
    r = side['relation']
    if r == '=': return (n, n, True, True), None
    if r in ('<', '<='): return (Decimal(0), n, False, r == '<='), None
    return (n, None, r == '>=', False), None


def public_interval(low, high, lc, hc, log=False):
    lo = None if (log and low == 0) else low
    if log:
        lo = None if lo is None else lo.log10()
        high = None if high is None else high.log10()
    point = lo if lo is not None and high is not None and lo == high and lc and hc else None
    def number(value):
        out = None if value is None else float(value)
        require(out is None or math.isfinite(out), '수치 표현 범위를 넘었습니다.')
        return out
    return {'kind': 'point' if point is not None else 'interval', 'point': number(point),
            'lower': number(lo), 'upper': number(high), 'lower_closed': lc, 'upper_closed': hc,
            'lower_unbounded': lo is None, 'upper_unbounded': high is None,
            'point_decimal': str(point) if point is not None else None,
            'lower_decimal': str(lo) if lo is not None else None,
            'upper_decimal': str(high) if high is not None else None}


def compare_pair(bound, arguments, index=0):
    a, b = (side_record(bound[s]) for s in ('reference', 'comparator'))
    reasons = []
    if a['namespace'] != 'chembl' or b['namespace'] != 'chembl': reasons.append('unsupported_or_missing_source_namespace')
    for field in ('document_id', 'record_id', 'molecule_id'):
        if not known(a[field]) or not known(b[field]): reasons.append('missing_' + field)
        elif a[field] != b[field]: reasons.append('different_' + field)
    for side, target in ((a, arguments['reference_target_id']), (b, arguments['comparator_target_id'])):
        if side['target_id'] != target: reasons.append('declared_target_mismatch')
        if side['endpoint'] != arguments['endpoint']: reasons.append('endpoint_mismatch')
        if not known(side['assay_id']): reasons.append('missing_assay_id')
        if not known(side['activity_id']): reasons.append('missing_activity_id')
        if side.get('source_record_ambiguous'): reasons.append('ambiguous_source_record_measurements')
        context = side.get('condition_context') or {}
        for key, expected in [('assay_chembl_id', side['assay_id']), ('document_chembl_id', side['document_id']),
                              ('target_chembl_id', side['target_id'])]:
            if known(context.get(key)) and context[key] != expected: reasons.append('assay_context_identity_mismatch')
    ca, cb = canonical_structure(a['canonical_smiles']), canonical_structure(b['canonical_smiles'])
    if ca is None or cb is None: reasons.append('structure_unresolved')
    elif ca != cb: reasons.append('stereo_structure_mismatch')
    for side, cs in ((a, ca), (b, cb)):
        if side.get('official_smiles') and canonical_structure(side['official_smiles']) != cs:
            reasons.append('official_activity_structure_mismatch')
    conditions = review_conditions(a, b)
    if conditions['mismatches']: reasons.append('known_condition_mismatch')
    qa, ea = quantity(a); qb, eb = quantity(b)
    if ea: reasons.append('reference_' + ea)
    if eb: reasons.append('comparator_' + eb)
    row = {'pair_index': index, 'candidate_id': a['molecule_id'], 'source_record_id': a['record_id'],
           'document_id': a['document_id'], 'reference': a, 'comparator': b, 'canonical_isomeric_smiles': ca,
           'condition_review': conditions, 'status': 'unresolved', 'reasons': sorted(set(reasons)),
           'ratio': None, 'log10_ratio': None, 'direction': 'unresolved'}
    if reasons: return row
    with localcontext() as context:
        context.prec = 120  # More than twice the accepted concentration precision.
        al, au, alc, auc = qa; bl, bu, blc, buc = qb
        low = Decimal(0) if au is None else bl / au
        high = None if bu is None or al == 0 else bu / al
        lc = low > 0 and blc and auc
        hc = high is not None and buc and alc
        row['ratio'] = public_interval(low, high, lc, hc)
        row['log10_ratio'] = public_interval(low, high, lc, hc, log=True)
        row['status'] = 'computed_exact' if row['ratio']['kind'] == 'point' else 'computed_interval'
        if low > 1 or (low == 1 and not lc): row['direction'] = 'reference_lower'
        elif high is not None and (high < 1 or (high == 1 and not hc)): row['direction'] = 'comparator_lower'
        elif low == high == 1 and lc and hc: row['direction'] = 'equal'
    return row


def evaluate(bundle):
    validate_arguments(bundle['arguments'])
    require(len(bundle['pairs']) == len(bundle['arguments']['pairs']), '선택 쌍 분모가 전달 중 달라졌습니다.')
    rows = [compare_pair(p, bundle['arguments'], i) for i, p in enumerate(bundle['pairs'])]
    # Selection is explicit but repeating a source activity cannot create another paired record.
    seen = {}
    for i, row in enumerate(rows):
        for side in ('reference', 'comparator'):
            r = row[side]; key = (r['namespace'], r['activity_id'])
            if key[1] is not None: seen.setdefault(key, set()).add(i)
    repeated = {i for group in seen.values() if len(group) > 1 for i in group}
    for i in repeated:
        rows[i].update(status='unresolved', ratio=None, log10_ratio=None, direction='unresolved')
        rows[i]['reasons'] = sorted(set(rows[i]['reasons'] + ['repeated_source_activity_selection']))
    from rdkit import rdBase
    return {'status': 'succeeded', 'semantic_type': SEMANTIC_TYPE, 'schema_version': 1,
            **{k: bundle['arguments'][k] for k in ('reference_target_id', 'comparator_target_id', 'endpoint', 'reason')},
            'formula': {'ratio': 'comparator_concentration / reference_concentration', 'log10_ratio': 'log10(ratio)',
                        'interval_meaning': 'Arithmetic bounds from source reporting relations.'},
            'rows': rows, 'summary': {'requested_pairs': len(rows), **{s: sum(r['status'] == s for r in rows)
                          for s in ('computed_exact', 'computed_interval', 'unresolved')}},
            'provenance': {'source_hashes': copy.deepcopy(bundle['source_hashes']), 'input_bundle_sha256': digest(bundle),
                           'namespace': 'chembl', 'structure_method': 'RDKit canonical isomeric SMILES; no normalization',
                           'rdkit_version': rdBase.rdkitVersion,
                           'arithmetic_precision': {'maximum_source_significant_digits': 50, 'decimal_precision': 120,
                                                    'presentation': 'Float fields for display; decimal strings preserve arithmetic precision.'},
                           'source_scope': 'Saved curated source records; source record correspondence is not physical sample equivalence.'},
            'limits': ['보존된 두 표적의 원보고 농도 대비입니다. 원 문헌·기록·입체구조를 맞추고 보고 부등호를 유지했습니다.',
                       '조건 미기재는 미확인입니다. 이 비율과 산술 범위는 선택성 인증·예측 정확도·통계적 신뢰구간이 아닙니다.',
                       '측정되지 않은 표적은 미확인으로 남고 활성 0으로 계산하지 않습니다.']}
