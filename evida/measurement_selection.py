"""Frozen, conditioned finite-pool decisions; no learning or biological interpretation.

The native caller resolves immutable source pointers and verifies declared identities,
conditions and readiness. This pure JSON kernel cannot establish source authority or
measurement validity from a text/flag. Bounds here are identification bounds, never CI.
"""
import copy
from decimal import Decimal, InvalidOperation, localcontext
from functools import wraps
import hashlib
import json
import re

VERSION = 1
SEMANTIC_TYPE = 'conditioned_measurement_selection'
BASE_FIELDS = {'target_id', 'endpoint', 'units', 'matrix', 'construct',
               'measurement_mechanism', 'concentration', 'time'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _keys(value, required, optional=()):
    require(isinstance(value, dict), 'Expected a JSON object.')
    require(set(required) <= value.keys() and value.keys() <= set(required) | set(optional),
            'Missing or unsupported fields: ' + ', '.join(sorted(set(required) - value.keys()) +
                                                         sorted(value.keys() - set(required) - set(optional))))


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def _number(value):
    require(type(value) in (str, int, float), 'Expected a finite decimal value, not Boolean.')
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError('Invalid decimal value.') from None
    require(result.is_finite() and abs(result.adjusted()) <= 100 and len(result.as_tuple().digits) <= 50,
            'Decimal outside supported finite precision/range.')
    return result


def _refs(refs):
    require(isinstance(refs, list), 'Source refs must be a list.')
    for ref in refs:
        _keys(ref, ('artifact_id', 'sha256', 'json_pointer'))
        require(_text(ref['artifact_id']) and isinstance(ref['sha256'], str) and
                re.fullmatch('[0-9a-f]{64}', ref['sha256']) and
                isinstance(ref['json_pointer'], str) and ref['json_pointer'].startswith('/'),
                'Incomplete immutable source pointer.')
    return bool(refs)


def _precision(fn):
    @wraps(fn)
    def bounded(*args, **kwargs):
        with localcontext() as ctx:
            ctx.prec = 120
            return fn(*args, **kwargs)
    return bounded


def _known(value):
    if value is None or value == '' or value == [] or value == {}:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict) and value.get('not_applicable') is True:
        return _text(value.get('reason'))
    return True


def match_context(contract, observed):
    """Literal supported field correspondence; no empty equality or inferred equivalence."""
    _keys(observed, ('values', 'field_refs'))
    require(isinstance(observed['values'], dict) and isinstance(observed['field_refs'], dict),
            'Context values/field_refs must be objects.')
    fields = {}
    for key in sorted(contract['required_fields']):
        expected, actual = contract['values'].get(key), observed['values'].get(key)
        refs = observed['field_refs'].get(key, [])
        authority = _refs(refs) and _refs(contract['field_refs'].get(key, []))
        status = ('unknown' if not _known(expected) or not _known(actual) else
                  'mismatch' if expected != actual else 'match' if authority else 'unknown')
        fields[key] = {'status': status, 'expected': copy.deepcopy(expected),
                       'actual': copy.deepcopy(actual), 'source_refs': copy.deepcopy(refs)}
    statuses = {row['status'] for row in fields.values()}
    return {'status': 'incompatible' if 'mismatch' in statuses else
            'hold_unknown' if 'unknown' in statuses else 'eligible', 'fields': fields,
            'authority': 'Caller-verified literal correspondence; not independent protocol equivalence.'}


def _context(context):
    _keys(context, ('id', 'revision', 'required_fields', 'values', 'field_refs'))
    require(_text(context['id']) and _text(context['revision']), 'Context needs ID/revision.')
    fields = context['required_fields']
    require(isinstance(fields, list) and all(_text(x) for x in fields) and
            len(set(fields)) == len(fields) and BASE_FIELDS <= set(fields),
            'Required context fields must include target/endpoint/units/matrix/construct/mechanism/concentration/time.')
    require(isinstance(context['values'], dict) and isinstance(context['field_refs'], dict), 'Invalid context.')
    for refs in context['field_refs'].values():
        _refs(refs)


def _observation(row, candidate, context):
    _keys(row, ('id', 'lineage_id', 'candidate_id', 'structure_id', 'material_id',
                'context', 'source_refs', 'observed', 'valid', 'precise_enough', 'relation', 'value'),
          ('independent_unit_id', 'inspection_status'))
    require(all(_text(row[k]) for k in ('id', 'lineage_id', 'candidate_id', 'structure_id')),
            'Observation identity/lineage missing.')
    require(all(type(row[k]) is bool for k in ('observed', 'valid', 'precise_enough')), 'Observation flags must be Boolean.')
    matched = match_context(context, row['context'])
    reasons = []
    if row['candidate_id'] != candidate['id'] or row['structure_id'] != candidate['structure_id']:
        reasons.append('candidate_or_structure_mismatch_no_parent_inheritance')
    material = candidate['material']
    if not _text(row['material_id']) or not _text(material['id']) or row['material_id'] != material['id']:
        reasons.append('material_identity_unknown_or_mismatch')
    if not _refs(row['source_refs']):
        reasons.append('observation_provenance_missing')
    if matched['status'] != 'eligible':
        reasons.append('observation_context_' + matched['status'])
    if not row['observed'] or not row['valid']:
        reasons.append('unobserved_or_invalid_measurement')
    if row['relation'] not in ('=', '<', '<=', '>', '>='):
        reasons.append('missing_or_unsupported_relation')
    try:
        point = _number(row['value'])
    except ValueError:
        point = None
        reasons.append('invalid_numeric_measurement')
    return {'id': row['id'], 'lineage_id': row['lineage_id'], 'condition_review': matched,
            'reasons': reasons, 'eligible': not reasons,
            'point_label_eligible': not reasons and row['relation'] == '=',
            'precise_enough': row['precise_enough'], '_point': point}


def _candidate(row, context):
    _keys(row, ('id', 'structure_id', 'parent_group_id', 'origin', 'parent_candidate_id',
                'identity_refs', 'material', 'measurement_context', 'observations'))
    require(all(_text(row[k]) for k in ('id', 'structure_id', 'parent_group_id')) and
            row['origin'] in ('original', 'generated'), 'Invalid candidate identity.')
    require(row['parent_candidate_id'] is None or _text(row['parent_candidate_id']), 'Invalid parent ID.')
    require(row['origin'] != 'generated' or row['parent_candidate_id'] not in (None, row['id']),
            'Generated identity requires a distinct declared parent.')
    identity = _refs(row['identity_refs'])
    material = row['material']
    _keys(material, ('id', 'ready', 'identity_verified', 'source_refs'))
    require(material['id'] is None or _text(material['id']), 'Material ID must be null or nonempty.')
    require(type(material['ready']) is bool and type(material['identity_verified']) is bool,
            'Material readiness must be explicitly Boolean.')
    material_refs = _refs(material['source_refs'])
    matched = match_context(context, row['measurement_context'])
    holds = []
    if not identity:
        holds.append('candidate_identity_refs_missing')
    if matched['status'] != 'eligible':
        holds.append('new_measurement_context_' + matched['status'])
    if not (_text(material['id']) and material['ready'] and material['identity_verified'] and material_refs):
        holds.append('physical_material_verification_required')
    require(isinstance(row['observations'], list), 'Historical observations must be a list.')
    labels = [_observation(x, row, context) for x in row['observations']]
    lineages = [x['lineage_id'] for x in labels]
    for label in labels:
        if lineages.count(label['lineage_id']) > 1:
            label.update(eligible=False, point_label_eligible=False)
            label['reasons'].append('duplicated_original_observation_lineage')
        label.pop('_point')
    return {'id': row['id'], 'condition_review': matched, 'holds': holds,
            'planned_eligible': identity and matched['status'] != 'incompatible',
            'physically_ready': not holds, 'historical_label_reviews': labels}


def _rank(arm, pool):
    _keys(arm, ('id', 'kind', 'reason', 'source_refs'), ('scores', 'order', 'prediction_context'))
    require(_text(arm['id']) and _text(arm['reason']) and _refs(arm['source_refs']), 'Arm ID/reason/provenance required.')
    require(arm['kind'] in ('prediction', 'source_evidence'), 'Unsupported selection arm.')
    if arm['kind'] == 'prediction':
        require('scores' in arm and 'order' not in arm and 'prediction_context' in arm, 'Prediction arm needs scores/context.')
        scores = arm['scores']
        require(isinstance(scores, dict) and set(scores) == set(pool), 'Prediction scores must cover identical eligible pool.')
        return sorted(pool, key=lambda x: (-_number(scores[x]), x))
    require('order' in arm and 'scores' not in arm and 'prediction_context' not in arm, 'Evidence arm needs only explicit order.')
    order = arm['order']
    require(isinstance(order, list) and len(order) == len(pool) and set(order) == set(pool), 'Order must cover pool once.')
    return list(order)


@_precision
def freeze_plan(spec):
    """Freeze original B and both arms, including held planned materials and real union cost."""
    _keys(spec, ('schema_version', 'context', 'candidates', 'arms', 'budget', 'cost_items',
                 'purpose', 'utility', 'inspection_ledger', 'next_check'))
    require(spec['schema_version'] == VERSION and type(spec['schema_version']) is int, 'Unsupported schema version.')
    digest(spec)  # Reject non-JSON/nonfinite inputs before computation.
    _context(spec['context'])
    require(spec['purpose'] in ('assay_calibration', 'ranking_evaluation', 'explanation_discrimination'), 'Unknown purpose.')
    _keys(spec['utility'], ('direction', 'minimum_difference'), ('bounds', 'top_q'))
    require(spec['utility']['direction'] in ('higher', 'lower') and
            _number(spec['utility']['minimum_difference']) >= 0, 'Invalid utility direction/margin.')
    if 'bounds' in spec['utility']:
        b = spec['utility']['bounds']
        require(isinstance(b, list) and len(b) == 2 and _number(b[0]) <= _number(b[1]), 'Invalid utility bounds.')
    if 'top_q' in spec['utility']:
        require(type(spec['utility']['top_q']) is int and spec['utility']['top_q'] > 0, 'Invalid frozen top_q.')
    require(isinstance(spec['inspection_ledger'], list), 'Inspection ledger required, including an explicit empty list.')
    require(isinstance(spec['candidates'], list) and 0 < len(spec['candidates']) <= 1000, 'Pool must contain 1–1000 candidates.')
    candidates = sorted(copy.deepcopy(spec['candidates']), key=lambda x: x['id'])
    ids = [x['id'] for x in candidates]
    require(len(ids) == len(set(ids)), 'Candidate IDs must be unique.')
    structures = [x['structure_id'] for x in candidates]
    require(len(structures) == len(set(structures)), 'Same structure cannot inflate the distinct compound pool; lots/doses are observations or costs.')
    reviews = [_candidate(x, spec['context']) for x in candidates]
    historical_lineages = [r['lineage_id'] for c in reviews for r in c['historical_label_reviews']]
    for candidate in reviews:
        for label in candidate['historical_label_reviews']:
            if historical_lineages.count(label['lineage_id']) > 1:
                label.update(eligible=False, point_label_eligible=False)
                label['reasons'] = sorted(set(label['reasons'] + ['duplicated_original_observation_lineage']))
    materials = [x['material']['id'] for x in candidates if x['material']['id'] is not None]
    require(len(materials) == len(set(materials)), 'Same physical material cannot be duplicated as independent candidates.')
    pool = [x['id'] for x in reviews if x['planned_eligible']]
    _keys(spec['budget'], ('B', 'maximum_cost', 'cost_unit'))
    B = spec['budget']['B']
    require(type(B) is int and 0 < B <= 1000 and _number(spec['budget']['maximum_cost']) >= 0 and
            _text(spec['budget']['cost_unit']), 'Invalid candidate/cost budget.')
    require(isinstance(spec['arms'], list) and len(spec['arms']) == 2, 'Minimum API compares exactly two frozen arms.')
    require(len({x['id'] for x in spec['arms']}) == 2, 'Arm IDs must differ.')
    arms = []
    for arm in spec['arms']:
        order = _rank(arm, pool)
        prediction_review = match_context(spec['context'], arm['prediction_context']) if arm['kind'] == 'prediction' else None
        usable = prediction_review is None or prediction_review['status'] == 'eligible'
        selected = order[:B] if usable and len(order) >= B else []
        arms.append({'id': arm['id'], 'kind': arm['kind'], 'planned_ids': selected,
                     'reason': arm['reason'], 'source_refs': copy.deepcopy(arm['source_refs']),
                     'status': 'frozen' if selected else 'unavailable_no_refill',
                     'prediction_context_review': prediction_review,
                     'physically_ready_ids': [x for x in selected if next(r for r in reviews if r['id'] == x)['physically_ready']]})
    union = sorted({x for arm in arms for x in arm['planned_ids']})
    items = spec['cost_items']
    require(isinstance(items, list) and bool(items), 'Physical cost items are required.')
    seen, covered, cost, control_holds = set(), set(), Decimal(0), []
    for item in items:
        _keys(item, ('id', 'kind', 'candidate_ids', 'cost', 'ready', 'source_refs'))
        require(_text(item['id']) and item['id'] not in seen, 'Physical cost item IDs must be unique.')
        seen.add(item['id'])
        require(item['kind'] in ('measurement', 'control') and isinstance(item['candidate_ids'], list) and
                len(set(item['candidate_ids'])) == len(item['candidate_ids']) and
                set(item['candidate_ids']) <= set(ids) and type(item['ready']) is bool, 'Invalid physical cost item.')
        refs = _refs(item['source_refs'])
        amount = _number(item['cost'])
        require(amount >= 0, 'Negative physical cost.')
        used = item['kind'] == 'control' or bool(set(item['candidate_ids']) & set(union))
        if used:
            cost += amount
            covered.update(set(item['candidate_ids']) & set(union))
            if not (item['ready'] and refs):
                control_holds.append(item['id'])
    require(covered == set(union), 'Missing cost coverage for planned measurement union.')
    require(any(x['kind'] == 'control' for x in items), 'Controls require explicit physical cost items.')
    spec = copy.deepcopy(spec)
    spec['candidates'] = candidates
    spec['context']['required_fields'] = sorted(spec['context']['required_fields'])
    spec['cost_items'] = sorted(items, key=lambda x: x['id'])
    holds = [x['id'] for x in reviews if x['id'] in union and not x['physically_ready']]
    budget_ok = cost <= _number(spec['budget']['maximum_cost'])
    result = {'schema_version': VERSION, 'semantic_type': SEMANTIC_TYPE, 'spec': spec,
              'candidate_reviews': reviews, 'pool_ids': pool, 'arms': arms,
              'planned_measurement_union': union, 'material_holds': holds,
              'cost': {'total': str(cost), 'unit': spec['budget']['cost_unit'], 'within_budget': budget_ok,
                       'candidate_B_per_arm': B, 'union_candidate_count': len(union),
                       'unready_physical_items': sorted(control_holds)},
              'ranking_value': 'ranking_value_unproven',
              'readiness_authority': 'Declared input readiness; native caller verifies actual source/material authority.'}
    result['seal'] = digest(result)
    return result


def _verify(plan):
    require(isinstance(plan, dict) and plan.get('schema_version') == VERSION, 'Unsupported sealed plan.')
    plain = {k: v for k, v in plan.items() if k != 'seal'}
    require(plan.get('seal') == digest(plain), 'Plan changed after sealing; review and reseal required.')
    require(freeze_plan(plan['spec']) == plan, 'Sealed derived selection does not match spec.')


def handoff(plan):
    """Preserve source/design distinction and review-draft explanation versions as data."""
    _verify(plan)
    check = plan['spec']['next_check']
    _keys(check, ('specimen', 'controls', 'readout', 'precision', 'engine2_refs', 'branches'))
    gates = []
    for key in ('specimen', 'controls', 'readout', 'precision'):
        field = check[key]
        _keys(field, ('description', 'basis', 'source_refs', 'ready'))
        require(field['basis'] in ('source', 'design', 'unknown') and type(field['ready']) is bool, 'Invalid field basis/readiness.')
        refs = _refs(field['source_refs'])
        if not (_text(field['description']) and field['ready'] and refs and field['basis'] != 'unknown'):
            gates.append(key + '_review_required')
    require(isinstance(check['engine2_refs'], list), 'Explanation review refs must be a list.')
    explanation_ids = set()
    for ref in check['engine2_refs']:
        _keys(ref, ('id', 'revision', 'source_ref'))
        require(_text(ref['id']) and _text(ref['revision']) and ref['id'] not in explanation_ids, 'Invalid explanation ID/revision.')
        _refs([ref['source_ref']])
        explanation_ids.add(ref['id'])
    if not explanation_ids:
        gates.append('engine2_explanation_refs_missing')
    require(isinstance(check['branches'], list), 'Explanation branches must be a list.')
    kinds = set()
    branch_ids = set()
    for row in check['branches']:
        _keys(row, ('id', 'kind', 'condition', 'action', 'explanation_ids', 'scientific_judgment'))
        require(_text(row['id']) and row['id'] not in branch_ids and _text(row['condition']) and _text(row['action']), 'Invalid branch.')
        require(row['kind'] in ('valid_improvement', 'valid_no_improvement', 'invalid_measurement',
                               'insufficient_precision', 'applicability_unknown') and
                isinstance(row['explanation_ids'], list) and set(row['explanation_ids']) <= explanation_ids and
                row['scientific_judgment'] in ('hold', 'review'), 'Invalid explanation branch binding.')
        if row['kind'] in ('invalid_measurement', 'insufficient_precision'):
            require(row['scientific_judgment'] == 'hold', 'Invalid/imprecise observations cannot refute biology.')
        branch_ids.add(row['id'])
        kinds.add(row['kind'])
    if not {'invalid_measurement', 'insufficient_precision', 'valid_improvement', 'valid_no_improvement'} <= kinds:
        gates.append('observation_branches_incomplete')
    gates += ['material:' + x for x in plan['material_holds']]
    gates += ['physical_item:' + x for x in plan['cost']['unready_physical_items']]
    if not plan['cost']['within_budget']:
        gates.append('physical_budget_exceeded')
    if any(x['status'] != 'frozen' for x in plan['arms']):
        gates.append('comparison_arm_unavailable')
    return {'schema_version': VERSION, 'plan_seal': plan['seal'], 'status': 'preparation_required' if gates else 'declared_ready',
            'planned_ids': plan['planned_measurement_union'], 'unresolved_gates': sorted(gates),
            'next_check': copy.deepcopy(check), 'cost': copy.deepcopy(plan['cost']),
            'interpretation': 'Explanation branches are supplied design data; no biological judgment executed.'}


def _interval(row, review, utility):
    if not review['eligible']:
        return tuple(_number(x) for x in utility['bounds']) if 'bounds' in utility else (None, None)
    point, relation = review['_point'], row['relation']
    lower = point if relation in ('=', '>', '>=') else None
    upper = point if relation in ('=', '<', '<=') else None
    if utility['direction'] == 'lower':
        lower, upper = -upper if upper is not None else None, -lower if lower is not None else None
    if 'bounds' in utility:
        lo, hi = (_number(x) for x in utility['bounds'])
        lower, upper = max(lower, lo) if lower is not None else lo, min(upper, hi) if upper is not None else hi
        require(lower <= upper, 'Measurement contradicts preregistered utility bounds.')
    return lower, upper


@_precision
def evaluate(plan, outcome_bundle=None):
    """Evaluate signed mean difference with fixed B, cancellation and censoring bounds."""
    _verify(plan)
    if outcome_bundle is None:
        rows = []
        inspection = 'no_outcomes'
    else:
        _keys(outcome_bundle, ('schema_version', 'plan_seal', 'inspection_status', 'rows'))
        require(type(outcome_bundle['schema_version']) is int and outcome_bundle['schema_version'] == VERSION and
                outcome_bundle['plan_seal'] == plan['seal'],
                'Outcomes must bind the exact frozen plan.')
        inspection = outcome_bundle['inspection_status']
        require(inspection in ('held_out_after_seal', 'retrospective'), 'Outcome inspection history required.')
        rows = outcome_bundle['rows']
        require(isinstance(rows, list), 'Outcome rows must be a list.')
    spec, B = plan['spec'], plan['spec']['budget']['B']
    candidates = {x['id']: x for x in spec['candidates']}
    seen, lineages, source_rows, reviews, intervals = set(), set(), set(), {}, {}
    for row in rows:
        require(row.get('candidate_id') in candidates and row.get('candidate_id') not in seen,
                'Outcome candidate outside pool or repeated; aggregate repeats explicitly upstream.')
        seen.add(row['candidate_id'])
        review = _observation(row, candidates[row['candidate_id']], spec['context'])
        require(row['lineage_id'] not in lineages, 'Same original observation cannot label multiple candidates.')
        raw_refs = {(r['artifact_id'], r['sha256'], r['json_pointer']) for r in row['source_refs']}
        require(not source_rows & raw_refs, 'Same source observation pointer cannot label multiple candidates.')
        source_rows.update(raw_refs)
        lineages.add(row['lineage_id'])
        intervals[row['candidate_id']] = _interval(row, review, spec['utility'])
        review.pop('_point')
        reviews[row['candidate_id']] = review
    left, right = (set(arm['planned_ids']) for arm in plan['arms'])
    differing = sorted(left ^ right)
    missing = [x for x in differing if not reviews.get(x, {}).get('eligible')]
    lower = upper = Decimal(0)
    for cid in differing:
        lo, hi = intervals.get(cid, tuple(_number(x) for x in spec['utility']['bounds'])
                                if 'bounds' in spec['utility'] else (None, None))
        if cid in right:
            lo, hi = -hi if hi is not None else None, -lo if lo is not None else None
        lower = lower + lo / B if lower is not None and lo is not None else None
        upper = upper + hi / B if upper is not None and hi is not None else None
    complete_arms = len(left) == len(right) == B
    if not complete_arms:
        lower = upper = None
    precise = bool(differing) and all(reviews.get(x, {}).get('eligible') and
                                    reviews[x]['precise_enough'] for x in differing)
    same = complete_arms and not differing
    finite = lower is not None and upper is not None
    status = ('zero_by_identical_selection' if same else 'unresolved' if not finite else
              'finite_pool_point_contrast' if lower == upper else 'finite_pool_identification_bounds')
    margin = _number(spec['utility']['minimum_difference'])
    prediction = any(x['kind'] == 'prediction' for x in plan['arms'])
    verdict = 'ranking_value_unproven'
    if prediction and precise and finite and not missing:
        verdict = ('finite_pool_left_advantage_observed' if lower > margin else
                   'finite_pool_right_advantage_observed' if upper < -margin else 'finite_pool_advantage_not_established')
    whole = bool(plan['pool_ids']) and set(plan['pool_ids']) <= reviews.keys() and all(
        reviews[x]['point_label_eligible'] for x in plan['pool_ids'])
    capture = None
    if whole and 'top_q' in spec['utility']:
        q = spec['utility']['top_q']
        require(type(q) is int and 0 < q <= len(plan['pool_ids']), 'Invalid frozen top_q.')
        points = {x: intervals[x][0] for x in plan['pool_ids']}
        cutoff = sorted(points.values(), reverse=True)[q - 1]
        above = sum(v > cutoff for v in points.values())
        ties = sum(v == cutoff for v in points.values())
        weights = {x: Decimal(1) if v > cutoff else Decimal(q - above) / ties if v == cutoff else Decimal(0)
                   for x, v in points.items()}
        capture = {arm['id']: str(sum((weights[x] for x in arm['planned_ids']), Decimal(0)) / q)
                   for arm in plan['arms']}
    next_check = handoff(plan)
    if next_check['status'] != 'declared_ready':
        verdict = 'ranking_value_unproven'
    return {'schema_version': VERSION, 'plan_seal': plan['seal'], 'status': status,
            'ranking_value': verdict, 'inspection_status': inspection, 'fixed_B': B,
            'differing_ids': differing, 'required_measurements': missing,
            'outcome_reviews': reviews, 'whole_pool_gold': whole, 'top_set_capture': capture,
            'contrast': {'lower': str(lower) if lower is not None else None,
                         'upper': str(upper) if upper is not None else None,
                         'meaning': 'Left minus right mean utility; conservative closed outer bounds (including strict censoring), not statistical confidence intervals.'},
            'claim_scope': 'This frozen finite pool and declared assay only; no prospective/general efficacy validation.',
            'handoff': next_check}
