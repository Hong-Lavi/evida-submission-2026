"""Bounded next-action calculation under explicit, unvalidated scientific declarations."""
from __future__ import annotations

import copy
import itertools
import math

SEMANTIC_TYPE = 'declared_conditional_next_action_not_scientific_validation'
CALCULATION_VERSION = '2'
PENDING_LIMIT = 298  # All subsets of 1..3 out of at most 12 checks.


def obj(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def array(item, maximum=12, minimum=0):
    return {'type': 'array', 'items': item, 'minItems': minimum, 'maxItems': maximum}


TEXT = {'type': 'string', 'minLength': 1, 'maxLength': 2000}
ID = {'type': 'string', 'minLength': 1, 'maxLength': 128}
IDS = array(ID)
BOOL = {'type': 'boolean'}
INDEX = {'type': 'integer', 'minimum': 0}
NUMBER = {'type': 'number', 'minimum': 0}
MEMBER = obj({'hypothesis_id': ID, 'alternative_ids': IDS, 'part_ids': IDS})
WORLD = obj({'id': ID, 'description': TEXT, 'members': array(MEMBER, minimum=1),
             'adequate_decision_ids': array(ID, minimum=1)})
PREDICTION = obj({'world_id': ID, 'coverage': {'type': 'string', 'enum': ['complete', 'partial', 'unknown']},
    'conditions_satisfied': BOOL, 'condition_basis': TEXT, 'outcome_indices': array(INDEX, 8),
    'origin': {'type': 'string', 'enum': ['prospective', 'previously_recorded', 'reconstructed_after_result']},
    'basis': TEXT, 'source_artifact_ids': IDS})
ACTION = obj({'check_id': ID, 'available': BOOL, 'design_validated': BOOL, 'precision_plan_defined': BOOL,
    'declaration_basis': TEXT, 'precision_rule': TEXT, 'incremental_cost': {'type': 'number', 'exclusiveMinimum': 0},
    'shared_control_ids': array(ID, 24), 'adequate_outcome_indices': array(INDEX, 8, 1),
    'predictions': array(PREDICTION)})
PROBLEM = obj({'id': ID, 'immediate_decision': TEXT,
    'declaration': obj({'kind': {'type': 'string', 'enum': ['model_assumptions', 'researcher_assumptions', 'synthetic_fixture']},
                        'basis': TEXT, 'conditions': array(TEXT, 24, 1)}),
    'decisions': array(obj({'id': ID, 'label': TEXT, 'adequacy_basis': TEXT}), minimum=1),
    'worlds': array(WORLD, minimum=1), 'actions': array(ACTION),
    'shared_controls': array(obj({'id': ID, 'cost': NUMBER, 'declaration_basis': TEXT}), 24),
    'cost_unit': TEXT, 'budget': NUMBER, 'max_checks': {'type': 'integer', 'minimum': 1, 'maximum': 3}})
RESULT = obj({'message_id': ID, 'check_id': ID, 'outcome_index': {'anyOf': [INDEX, {'type': 'null'}]},
    'context_match': BOOL, 'intervention_status': {'type': 'string', 'enum': ['validated', 'failed', 'unknown']},
    'measurement_validity': {'type': 'string', 'enum': ['validated', 'failed', 'unknown']},
    'precision': {'type': 'string', 'enum': ['adequate', 'insufficient', 'unknown']}, 'assessment_basis': TEXT})
# Strict provider functions need an object root. Mode semantics are checked below.
SCHEMA = obj({'mode': {'type': 'string', 'enum': ['plan', 'review_result']}, 'artifact_id': ID,
    'source_artifact_ids': IDS, 'problem': {'anyOf': [PROBLEM, {'type': 'null'}]},
    'result': {'anyOf': [RESULT, {'type': 'null'}]}})
# Saved calculations without a version retain the original numeric-only contract.
SCHEMA_V1 = copy.deepcopy(SCHEMA)
ACTION['properties']['incremental_cost'] = {'anyOf': [
    {'type': 'number', 'exclusiveMinimum': 0}, {'type': 'null'}]}
PROBLEM['properties']['shared_controls']['items']['properties']['cost'] = {
    'anyOf': [copy.deepcopy(NUMBER), {'type': 'null'}]}


def require(condition, reason):
    if not condition:
        raise ValueError('다음 관측 선택 입력: ' + reason)


def identifier(value):
    require(isinstance(value, str) and 0 < len(value) <= 128 and value == value.strip(), '비어 있지 않은 고유 ID를 확인해 주세요.')


def ids(values, maximum=12, minimum=0):
    require(isinstance(values, list) and minimum <= len(values) <= maximum, 'ID 목록의 개수 범위를 확인해 주세요.')
    for value in values:
        identifier(value)
    require(len(set(values)) == len(values), '중복된 ID가 있습니다.')


def indices(values, minimum=0):
    require(isinstance(values, list) and minimum <= len(values) <= 8, '결과 목록은 최대 8개입니다.')
    require(all(type(x) is int and x >= 0 for x in values), '결과 번호는 0 이상의 정수입니다.')
    require(len(set(values)) == len(values), '결과 번호가 중복됐습니다.')


def finite(value, positive=False):
    require(type(value) in (int, float), '비용·예산은 유한한 숫자여야 합니다.')
    try:
        valid = math.isfinite(value) and (value > 0 if positive else value >= 0)
    except OverflowError:
        valid = False
    require(valid, '비용·예산의 부호 또는 유한성을 확인해 주세요.')


def validate_version(value):
    require(value in ('1', '2'), '알 수 없는 계산 규칙 버전입니다.')
    return value


def schema_for(calculation_version):
    return SCHEMA_V1 if validate_version(calculation_version) == '1' else SCHEMA


def validate_problem(p, *, calculation_version=CALCULATION_VERSION):
    """Semantic checks supplement the strict wire schema, including NaN and IDs."""
    nullable_costs = validate_version(calculation_version) == '2'
    require(isinstance(p, dict), '선언한 조건표가 필요합니다.')
    identifier(p.get('id'))
    for field, maximum, minimum in [('worlds', 12, 1), ('actions', 12, 0), ('decisions', 12, 1), ('shared_controls', 24, 0)]:
        rows = p.get(field)
        require(isinstance(rows, list) and minimum <= len(rows) <= maximum and all(isinstance(x, dict) for x in rows), field + ' 범위를 확인해 주세요.')
        ids([x.get('check_id' if field == 'actions' else 'id') for x in rows], maximum, minimum)
    worlds = {w['id'] for w in p['worlds']}
    decisions = {d['id'] for d in p['decisions']}
    controls = {c['id'] for c in p['shared_controls']}
    for w in p['worlds']:
        ids(w.get('adequate_decision_ids'), minimum=1)
        require(set(w['adequate_decision_ids']) <= decisions, '정의되지 않은 다음 판단입니다.')
        require(isinstance(w.get('members'), list) and 1 <= len(w['members']) <= 12, '상황별 가설 연결이 필요합니다.')
        ids([m.get('hypothesis_id') for m in w['members']])
        for m in w['members']:
            ids(m.get('alternative_ids')); ids(m.get('part_ids'))
    for a in p['actions']:
        for field in ('available', 'design_validated', 'precision_plan_defined'):
            require(type(a.get(field)) is bool, field + '는 명시적인 Boolean 선언이어야 합니다.')
        require('incremental_cost' in a, '검사 비용은 숫자 또는 명시적인 미상이어야 합니다.')
        if not nullable_costs or a['incremental_cost'] is not None:
            finite(a['incremental_cost'], True)
        ids(a.get('shared_control_ids'), 24)
        require(set(a['shared_control_ids']) <= controls, '정의되지 않은 공통 대조 비용입니다.')
        indices(a.get('adequate_outcome_indices'), 1)
        rows = a.get('predictions')
        require(isinstance(rows, list) and len(rows) <= 12 and all(isinstance(x, dict) for x in rows), '상황별 예상 목록을 확인해 주세요.')
        ids([r.get('world_id') for r in rows])
        for r in rows:
            require(r['world_id'] in worlds, '예상이 정의되지 않은 상황을 참조합니다.')
            require(r.get('coverage') in ('complete', 'partial', 'unknown'), '예상 범위가 올바르지 않습니다.')
            require(type(r.get('conditions_satisfied')) is bool, '조건 적용 여부는 명시적인 Boolean입니다.')
            indices(r.get('outcome_indices'), 1 if r['coverage'] == 'complete' else 0)
            require(set(r['outcome_indices']) <= set(a['adequate_outcome_indices']), '예상 결과가 선언한 유효 결과 범위 밖입니다.')
            require(r.get('origin') in ('prospective', 'previously_recorded', 'reconstructed_after_result'), '예상 시점 표시가 올바르지 않습니다.')
            ids(r.get('source_artifact_ids'))
    for c in p['shared_controls']:
        require('cost' in c, '공통 대조 비용은 숫자 또는 명시적인 미상이어야 합니다.')
        if not nullable_costs or c['cost'] is not None:
            finite(c['cost'])
    finite(p.get('budget'))
    require(type(p.get('max_checks')) is int and 1 <= p['max_checks'] <= 3, '선택할 확인은 최대 3개입니다.')
    try:
        values = [a['incremental_cost'] for a in p['actions']] + [c['cost'] for c in p['shared_controls']]
        total = math.fsum(v for v in values if v is not None) if nullable_costs else math.fsum(values)
    except OverflowError:
        total = math.inf
    require(math.isfinite(total), '총 선언 비용이 유한한 범위를 넘었습니다.')
    declaration = p.get('declaration')
    require(isinstance(declaration, dict) and declaration.get('kind') in ('model_assumptions', 'researcher_assumptions', 'synthetic_fixture'), '가정의 선언 출처가 필요합니다.')
    conditions = declaration.get('conditions')
    require(isinstance(conditions, list) and 1 <= len(conditions) <= 24 and all(isinstance(x, str) and x.strip() for x in conditions), '구체적인 조건 가정이 필요합니다.')


def allowed(world, action):
    pred = next((p for p in action['predictions'] if p['world_id'] == world['id']), None)
    return set(pred['outcome_indices'] if pred and pred['coverage'] == 'complete' and pred['conditions_satisfied']
               else action['adequate_outcome_indices'])


def common(worlds):
    return set.intersection(*(set(w['adequate_decision_ids']) for w in worlds)) if worlds else set()


def cost(problem, actions):
    shared = set().union(*(set(a['shared_control_ids']) for a in actions)) if actions else set()
    return math.fsum([a['incremental_cost'] for a in actions] + [c['cost'] for c in problem['shared_controls'] if c['id'] in shared])


def branches(worlds, actions):
    rows = []
    for outcomes in itertools.product(*(a['adequate_outcome_indices'] for a in actions)):
        retained = [w for w in worlds if all(o in allowed(w, a) for a, o in zip(actions, outcomes))]
        if not retained:
            continue  # Out-of-model observations are handled by update, without exclusion.
        decisions = sorted(common(retained))
        if not decisions:
            return False, []
        rows.append({'outcome_by_check': dict(zip((a['check_id'] for a in actions), outcomes)),
                     'retained_configuration_ids': [w['id'] for w in retained], 'common_next_decisions': decisions})
    return bool(rows), rows


def _select_v1(problem, retained_ids=None, result=None):
    """Original numeric-cost rules, including the historical guard summaries."""
    validate_problem(problem, calculation_version='1')
    retained_ids = [w['id'] for w in problem['worlds']] if retained_ids is None else retained_ids
    ids(retained_ids, minimum=1)
    require(set(retained_ids) <= {w['id'] for w in problem['worlds']}, '원 조건표에 없는 남은 상황입니다.')
    worlds = [w for w in problem['worlds'] if w['id'] in retained_ids]
    summary = {'selection_status': '', 'selected_check_ids': [], 'cost': 0, 'cost_unit': problem['cost_unit'],
               'retained_configuration_ids': [w['id'] for w in worlds], 'common_next_decisions': [],
               'declaration_kind': problem['declaration']['kind']}
    output = {'summary': summary, 'rows': [], 'unresolvable_pairs': [], 'conditional_exclusions': [],
              'limits': ['명시한 조건표와 유효 결과를 전제로 한 계산입니다. 선언된 측정 적절성은 실험 검증이 아닙니다.',
                         '공존하거나 아직 포함하지 않은 기전은 남아 있습니다. 이 계산은 보존된 판단의 조건을 자동 갱신하지 않습니다.']}
    if result is not None:
        identifier(result.get('check_id')); identifier(result.get('message_id'))
        action = next((a for a in problem['actions'] if a['check_id'] == result['check_id']), None)
        require(action is not None, '결과가 원 조건표에 없는 확인을 참조합니다.')
        require(type(result.get('context_match')) is bool, '결과 조건 일치 여부를 확인해 주세요.')
        for field in ('intervention_status', 'measurement_validity'):
            require(result.get(field) in ('validated', 'failed', 'unknown'), '결과 신뢰도 선언이 올바르지 않습니다.')
        require(result.get('precision') in ('adequate', 'insufficient', 'unknown'), '정밀도는 adequate/insufficient/unknown 중 하나입니다.')
        require('outcome_index' in result and (result['outcome_index'] is None or type(result['outcome_index']) is int and result['outcome_index'] >= 0), '미측정은 null, 관측은 원 결과 번호로 명시해 주세요.')
        guard = ('context_unresolved' if not result['context_match'] else
                 'repair_intervention' if result['intervention_status'] == 'failed' else
                 'repair_readout' if result['measurement_validity'] == 'failed' else
                 'validity_unresolved' if result['intervention_status'] != 'validated' or result['measurement_validity'] != 'validated'
                 or not action['design_validated'] or not action['precision_plan_defined'] else
                 'precision_check' if result['precision'] != 'adequate' else None)
        if guard:
            summary['selection_status'] = guard
            return output
        if result['outcome_index'] is not None:
            surviving = [w for w in worlds if result['outcome_index'] in allowed(w, action)]
            if result['outcome_index'] not in action['adequate_outcome_indices'] or not surviving:
                summary['selection_status'] = 'model_gap'
                return output
            output['conditional_exclusions'] = [{'configuration_id': w['id'], 'reason': 'Complete applicable declared set omits this adequate outcome; conditional model calculation only.'}
                                                 for w in worlds if w not in surviving]
            worlds = surviving
            summary['retained_configuration_ids'] = [w['id'] for w in worlds]
    decisions = sorted(common(worlds))
    if decisions:
        summary.update(selection_status='decision_region_reached', common_next_decisions=decisions)
        return output
    actions = sorted((a for a in problem['actions'] if a['available'] and a['design_validated'] and a['precision_plan_defined']), key=lambda a: a['check_id'])
    pairs = []
    for left, right in itertools.combinations(worlds, 2):
        if not set(left['adequate_decision_ids']).intersection(right['adequate_decision_ids']):
            tests = [a['check_id'] for a in actions if allowed(left, a).isdisjoint(allowed(right, a))]
            pairs.append({'configuration_ids': [left['id'], right['id']], 'check_ids': tests})
    output['unresolvable_pairs'] = [p['configuration_ids'] for p in pairs if not p['check_ids']]
    best = None
    for size in range(1, min(problem['max_checks'], len(actions)) + 1):
        for group in itertools.combinations(actions, size):
            price = cost(problem, group)
            key = (price, size, tuple(a['check_id'] for a in group))
            if price > problem['budget'] or best is not None and key >= best[0]:
                continue
            closes, rows = branches(worlds, group)
            if closes:
                best = (key, rows)
    if best:
        summary.update(selection_status='conditional_plan', selected_check_ids=list(best[0][2]), cost=best[0][0])
        output['rows'] = best[1]
        return output
    partial = []
    for action in actions:
        cover = sum(action['check_id'] in p['check_ids'] for p in pairs)
        price = cost(problem, [action])
        if cover and price <= problem['budget']:
            partial.append((-cover / price, price, action['check_id']))
    if partial:
        chosen = min(partial)
        summary.update(selection_status='partial_only', selected_check_ids=[chosen[2]], cost=chosen[1])
        output['limits'].append('부분 선택은 구별 가능한 판단 쌍/비용 기준이며 전체 판단 도달을 보장하지 않습니다.')
    else:
        summary['selection_status'] = 'stop_specific_claim'
    return output


def _pending_metadata(options, counts=None):
    return {'pending_cost_options': options, 'pending_cost_options_total': len(options),
            'pending_cost_options_limit': PENDING_LIMIT, 'pending_cost_options_omitted': 0,
            'pending_cost_filter': counts or {'evaluated': 0, 'full_supersets_excluded': 0,
                                             'partial_multicheck_excluded': 0, 'noninformative_excluded': 0}}


def _assessment(scope, cost_status, known_subtotal, unknown_ids, budget_status, required):
    return {'scope': scope, 'cost_status': cost_status, 'known_subtotal': known_subtotal,
            'unknown_component_ids': unknown_ids, 'budget_status': budget_status,
            'required_information': required}


def hold_calculation(output, status, check_id=None):
    """A v2 validity guard is an unpriced follow-up, never the earlier funded plan."""
    output['summary'].update(selection_status=status, selected_check_ids=[], cost=None, common_next_decisions=[])
    output.update(rows=[], unresolvable_pairs=[], conditional_exclusions=[], **_pending_metadata([]))
    requests = {
        'repair_readout': ('readout_repair', '실패한 판독을 복구하거나 재검증할 방법·가용성과 비용'),
        'repair_intervention': ('intervention_repair', '실패한 개입 조건을 복구할 방법·가용성과 비용'),
        'precision_check': ('precision_check', '구별에 필요한 정밀도와 이를 확보할 추가 확인의 범위·비용'),
        'context_unresolved': ('context_confirmation', '관측과 원 확인의 조건이 연결되는지 및 필요한 확인의 범위'),
        'validity_unresolved': ('validity_confirmation', '개입·측정의 성립 조건과 이를 확인할 방법·가용성'),
        'model_gap': ('model_review', '원 예상표 밖 관측을 검토할 근거와 필요한 추가 확인'),
        'report_confirmation_required': ('report_confirmation', '보고 원문과 결과 해석이 다른 조건 및 필요한 확인'),
        'subject_confirmation_required': ('subject_confirmation', '관측한 후보·측정 조건과 원 확인 대상의 연결'),
    }
    kind, question = requests[status]
    repairing = status in ('repair_readout', 'repair_intervention')
    required = [question, '반복 검사와 필요한 대조를 포함한 추가 비용 및 현재 사용할 예산' if repairing
                else '확인 후 추가 실험이 필요하면 그 비용·가용성과 사용할 예산']
    output['resource_assessment'] = _assessment('repair' if repairing else 'declared_plan', 'unknown', None,
        [kind + ':' + check_id] if repairing and check_id else [], 'unresolved', required)
    return output


def _cost_information(problem, actions):
    shared = set().union(*(set(a['shared_control_ids']) for a in actions)) if actions else set()
    components = [('action:' + a['check_id'], a['incremental_cost']) for a in actions]
    components.extend(('shared_control:' + c['id'], c['cost']) for c in problem['shared_controls'] if c['id'] in shared)
    unknown = sorted(key for key, value in components if value is None)
    subtotal = math.fsum(value for _, value in components if value is not None)
    required = []
    action_count = sum(key.startswith('action:') for key in unknown)
    control_count = len(unknown) - action_count
    if action_count:
        required.append(f'이 조합에서 비용이 미정인 검사 {action_count}개의 추가 비용을 확인해 주세요.')
    if control_count:
        required.append(f'필요한 공통 대조 {control_count}개의 미정 비용과 재사용 가능 여부를 확인해 주세요.')
    budget_status = 'over_declared_budget' if subtotal > problem['budget'] else 'unresolved' if unknown else 'within_declared_budget'
    return subtotal, unknown, budget_status, required


def _select_v2(problem, retained_ids=None, result=None):
    validate_problem(problem, calculation_version='2')
    retained_ids = [w['id'] for w in problem['worlds']] if retained_ids is None else retained_ids
    ids(retained_ids, minimum=1)
    require(set(retained_ids) <= {w['id'] for w in problem['worlds']}, '원 조건표에 없는 남은 상황입니다.')
    worlds = [w for w in problem['worlds'] if w['id'] in retained_ids]
    summary = {'selection_status': '', 'selected_check_ids': [], 'cost': 0, 'cost_unit': problem['cost_unit'],
               'retained_configuration_ids': [w['id'] for w in worlds], 'common_next_decisions': [],
               'declaration_kind': problem['declaration']['kind']}
    output = {'calculation_version': '2', 'summary': summary, 'rows': [], 'unresolvable_pairs': [], 'conditional_exclusions': [],
              'resource_assessment': _assessment('declared_plan', 'not_applicable', None, [], 'not_applicable', []),
              **_pending_metadata([]),
              'limits': ['명시한 조건표와 유효 결과를 전제로 한 계산입니다. 선언된 측정 적절성은 실험 검증이 아닙니다.',
                         '공존하거나 아직 포함하지 않은 기전은 남아 있습니다. 이 계산은 보존된 판단의 조건을 자동 갱신하지 않습니다.']}
    if result is not None:
        identifier(result.get('check_id')); identifier(result.get('message_id'))
        action = next((a for a in problem['actions'] if a['check_id'] == result['check_id']), None)
        require(action is not None, '결과가 원 조건표에 없는 확인을 참조합니다.')
        require(type(result.get('context_match')) is bool, '결과 조건 일치 여부를 확인해 주세요.')
        for field in ('intervention_status', 'measurement_validity'):
            require(result.get(field) in ('validated', 'failed', 'unknown'), '결과 신뢰도 선언이 올바르지 않습니다.')
        require(result.get('precision') in ('adequate', 'insufficient', 'unknown'), '정밀도는 adequate/insufficient/unknown 중 하나입니다.')
        require('outcome_index' in result and (result['outcome_index'] is None or type(result['outcome_index']) is int and result['outcome_index'] >= 0), '미측정은 null, 관측은 원 결과 번호로 명시해 주세요.')
        guard = ('context_unresolved' if not result['context_match'] else
                 'repair_intervention' if result['intervention_status'] == 'failed' else
                 'repair_readout' if result['measurement_validity'] == 'failed' else
                 'validity_unresolved' if result['intervention_status'] != 'validated' or result['measurement_validity'] != 'validated'
                 or not action['design_validated'] or not action['precision_plan_defined'] else
                 'precision_check' if result['precision'] != 'adequate' else None)
        if guard:
            return hold_calculation(output, guard, action['check_id'])
        if result['outcome_index'] is not None:
            surviving = [w for w in worlds if result['outcome_index'] in allowed(w, action)]
            if result['outcome_index'] not in action['adequate_outcome_indices'] or not surviving:
                return hold_calculation(output, 'model_gap', action['check_id'])
            output['conditional_exclusions'] = [{'configuration_id': w['id'], 'reason': 'Complete applicable declared set omits this adequate outcome; conditional model calculation only.'}
                                                 for w in worlds if w not in surviving]
            worlds = surviving
            summary['retained_configuration_ids'] = [w['id'] for w in worlds]
    decisions = sorted(common(worlds))
    if decisions:
        summary.update(selection_status='decision_region_reached', common_next_decisions=decisions)
        output['resource_assessment'] = _assessment('no_further_check', 'not_applicable', None, [], 'not_applicable', [])
        return output
    actions = sorted((a for a in problem['actions'] if a['available'] and a['design_validated'] and a['precision_plan_defined']), key=lambda a: a['check_id'])
    pairs = []
    for left, right in itertools.combinations(worlds, 2):
        if not set(left['adequate_decision_ids']).intersection(right['adequate_decision_ids']):
            tests = [a['check_id'] for a in actions if allowed(left, a).isdisjoint(allowed(right, a))]
            pairs.append({'configuration_ids': [left['id'], right['id']], 'check_ids': tests})
    output['unresolvable_pairs'] = [p['configuration_ids'] for p in pairs if not p['check_ids']]
    best, partial, pending = None, [], []
    counts = {'evaluated': 0, 'full_supersets_excluded': 0, 'partial_multicheck_excluded': 0, 'noninformative_excluded': 0}
    closures = {}
    def closure(group):
        key = tuple(a['check_id'] for a in group)
        if key not in closures:
            closures[key] = branches(worlds, group)
        return closures[key]
    for size in range(1, min(problem['max_checks'], len(actions)) + 1):
        for group in itertools.combinations(actions, size):
            subtotal, unknown, budget_status, required = _cost_information(problem, group)
            check_ids = tuple(a['check_id'] for a in group)
            cover = sum(bool(set(check_ids).intersection(pair['check_ids'])) for pair in pairs)
            if unknown:
                counts['evaluated'] += 1
                closes, _ = closure(group)
                redundant = closes and any(closure(subset)[0] for length in range(1, size)
                                           for subset in itertools.combinations(group, length))
                if redundant:
                    counts['full_supersets_excluded'] += 1
                elif not closes and size > 1 and cover:
                    counts['partial_multicheck_excluded'] += 1
                elif closes or cover:
                    pending.append({'check_ids': list(check_ids), 'cost': None, 'known_subtotal': subtotal,
                        'unknown_component_ids': unknown, 'budget_status': budget_status,
                        'resolution': 'full' if closes else 'partial', 'distinguished_pair_count': cover,
                        'required_information': required})
                else:
                    counts['noninformative_excluded'] += 1
                continue
            key = (subtotal, size, check_ids)
            if size == 1 and cover and subtotal <= problem['budget']:
                partial.append((-cover / subtotal, subtotal, check_ids[0]))
            if subtotal > problem['budget'] or best is not None and key >= best[0]:
                continue
            closes, rows = closure(group)
            if closes:
                best = (key, rows)
    pending.sort(key=lambda option: tuple(option['check_ids']))
    output.update(_pending_metadata(pending, counts))
    if best:
        summary.update(selection_status='conditional_plan', selected_check_ids=list(best[0][2]), cost=best[0][0])
        output['rows'] = best[1]
    elif partial:
        chosen = min(partial)
        summary.update(selection_status='partial_only', selected_check_ids=[chosen[2]], cost=chosen[1])
        output['limits'].append('부분 선택은 구별 가능한 판단 쌍/비용 기준이며 전체 판단 도달을 보장하지 않습니다.')
    else:
        useful_pending = any(p['budget_status'] == 'unresolved' for p in pending)
        summary['selection_status'] = ('needs_cost_information' if useful_pending else
                                       'needs_budget_adjustment' if pending else 'stop_specific_claim')
        if pending:
            summary['cost'] = None
            output['resource_assessment'] = _assessment('declared_plan', 'unknown', None,
                sorted({key for option in pending for key in option['unknown_component_ids']}),
                'unresolved' if useful_pending else 'over_declared_budget',
                ['유용한 대안별 미정 비용을 확인한 뒤 선언 예산과 비교해 주세요.'] if useful_pending
                else ['알려진 비용만으로 선언 예산을 넘습니다. 대안 범위 또는 사용할 예산을 확인해 주세요.'])
    if summary['selected_check_ids']:
        output['resource_assessment'] = _assessment('declared_plan', 'known', summary['cost'], [], 'within_declared_budget', [])
    if pending:
        output['limits'].append('비용 미상 대안은 확인할 견적과 함께 보존합니다. 선택과 비용 순위는 비용이 모두 알려진 조합에 한정됩니다.')
    return output


def select(problem, retained_ids=None, result=None, *, calculation_version=CALCULATION_VERSION):
    """Calculate a saved rule version without revising its declarations or history."""
    implementation = _select_v1 if validate_version(calculation_version) == '1' else _select_v2
    return implementation(problem, retained_ids, result)
