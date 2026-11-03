"""Source-linked exposure/assay comparison with explicit unknown translation.

Dimensional calculations, not a PK/PD fit or a predicted efficacy score. A
reported total-plasma value and a nominal cell-assay threshold do not establish
equivalent unbound concentrations at their respective sites of action.
"""
import math
import re
import json


class SourceBindingError(ValueError):
    def __init__(self, errors):
        self.source_binding_errors = errors
        super().__init__('출처 연결을 먼저 고쳐 주세요. 각 오류의 artifact_id·path·message를 확인하세요. '
                         '원값이나 경로를 자동 수정하지 않았습니다. path는 저장된 JSON 본문 기준이며 '
                         '조회 응답의 result/content 포장 키를 임의로 붙이지 않습니다.')


def positive(value, label):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f'{label}: 양의 유한한 수가 필요합니다. 검출한계·결측은 숫자0으로 대체하지 않습니다.')
    return value


def verify_source(binding, value, sources):
    """Check the exact locator/quote and number, not scientific entailment."""
    aid = binding['artifact_id']
    if aid not in sources:
        raise ValueError('계산 값의 출처가 선택한 자료 목록에 없습니다.')
    located = sources[aid]
    traversed = []
    try:
        for key in binding['path']:
            if isinstance(located, list):
                if type(key) is not int or key < 0:
                    raise ValueError('배열의 원문 위치는 음수가 아닌 정수여야 합니다.')
                located = located[key]
            elif isinstance(located, dict) and isinstance(key, str):
                located = located[key]
            else:
                raise ValueError('원문 위치의 자료형이 다릅니다.')
            traversed.append(key)
    except (IndexError, KeyError, TypeError):
        available = ('keys=' + json.dumps(list(located)[:12], ensure_ascii=False)
                     if isinstance(located, dict) else
                     'array_length=' + str(len(located)) if isinstance(located, list) else
                     'type=' + type(located).__name__)
        raise ValueError('원문 위치 오류: ' + aid + ' path=' + json.dumps(binding['path'], ensure_ascii=False)
                         + '; reached=' + json.dumps(traversed, ensure_ascii=False) + '; ' + available
                         + '. path는 저장된 JSON 본문 기준입니다. 조회 응답의 result/content 포장 키를 임의로 덧붙이지 마세요.') from None
    quote = binding['quote']
    if not isinstance(located, str) or not quote.strip() or quote not in located:
        raise ValueError('보존 원문에 정확히 있는 문구로 계산 값의 출처를 연결해 주세요.')
    numbers = [float(x) for x in re.findall(r'(?<![\w.])[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?(?![\w.])', quote)]
    if not any(x == value for x in numbers):
        raise ValueError('입력 수치가 지정한 원문 문구에 없습니다.')
    return {'artifact_id': aid, 'path': binding['path'], 'quote': quote,
            'exact_locator_quote_and_number_verified': True,
            'unit_population_metric_and_scientific_support': 'requires_semantic_review_not_proven_by_substring_check'}


def compare(arguments, sources):
    # Report distinct invalid bindings together; do not spend another model turn
    # discovering each wrapper mistake. No paths or quotes are silently repaired.
    bindings = [(arguments['assay_benchmark']['source'], arguments['assay_benchmark']['value'])]
    bindings.extend((b['source'], b['molecular_weight_g_mol']) for b in arguments['mass_bases'])
    for item in arguments['exposures']:
        if item.get('derivation'):
            d = item['derivation']
            bindings.extend((d['source'], d[k]) for k in ('percent_min', 'percent_max'))
        else:
            bindings.append((item['source'], item['value']))
    errors, seen, error_keys = [], set(), set()
    for binding, value in bindings:
        identity = json.dumps([binding, value], ensure_ascii=False, sort_keys=True)
        if identity in seen:
            continue
        seen.add(identity)
        try:
            verify_source(binding, value, sources)
        except ValueError as exc:
            message = str(exc)
            error_key = json.dumps([binding['artifact_id'], binding['path'], message], ensure_ascii=False)
            if error_key not in error_keys:
                error_keys.add(error_key)
                errors.append({'artifact_id': binding['artifact_id'], 'path': binding['path'],
                               'message': message[:2000]})
    if errors:
        raise SourceBindingError(errors)
    threshold = arguments['assay_benchmark']
    benchmark = positive(threshold['value'], '시험 비교 농도')
    if threshold['unit'] not in ('uM', 'nM'):
        raise ValueError('시험 비교 농도는 uM 또는 nM이어야 합니다. 결합 에너지를 농도로 바꾸지 않습니다.')
    benchmark_um = benchmark if threshold['unit'] == 'uM' else benchmark / 1000
    evidence = [verify_source(threshold['source'], benchmark, sources)]
    mass_bases = arguments['mass_bases']
    if len({b['id'] for b in mass_bases}) != len(mass_bases):
        raise ValueError('서로 다른 분자량 가정의 ID를 구분해 주세요.')
    for basis in mass_bases:
        positive(basis['molecular_weight_g_mol'], '분자량')
        evidence.append(verify_source(basis['source'], basis['molecular_weight_g_mol'], sources))
    exposures = arguments['exposures']
    if not exposures or len({r['id'] for r in exposures}) != len(exposures):
        raise ValueError('중복 없는 실제 노출 자료를 선택해 주세요.')
    rows, gaps = [], []
    by_id = {r['id']: r for r in exposures}
    for record in exposures:
        derivation = record.get('derivation')
        if derivation is not None:
            if derivation['kind'] != 'percent_of_reported_concentration':
                raise ValueError('지원하는 파생 계산은 원문에 보고된 농도의 백분율입니다.')
            base = by_id.get(derivation['base_exposure_id'])
            if base is None or base.get('derivation') is not None or base['statistic'] == 'AUC':
                raise ValueError('같은 입력의 직접 보고 농도를 기준으로 선택해 주세요. AUC·연쇄 파생·순환 참조는 허용하지 않습니다.')
            if 'value' in record or 'source' in record or 'unit' in record:
                raise ValueError('직접 보고와 파생 계산을 한 행에 혼합하지 않습니다.')
            base_value = positive(base['value'], '기준 보고 농도')
            low = positive(derivation['percent_min'], '보고 백분율 하한')
            high = positive(derivation['percent_max'], '보고 백분율 상한')
            if low > high:
                raise ValueError('백분율 범위의 순서를 확인해 주세요.')
            evidence.append(verify_source(base['source'], base_value, sources))
            evidence.extend(verify_source(derivation['source'], x, sources) for x in (low, high))
            values = [base_value * low / 100, base_value * high / 100]
            unit, interval = base['unit'], None
            if unit in ('ug*h/mL', 'ng*h/mL'):
                raise ValueError('AUC를 파생 농도의 기준값으로 사용하지 않습니다.')
            record_bindings = [base['source'], derivation['source']]
            calculation = {**derivation, 'base_reported_value': base_value,
                'base_reported_unit': unit, 'base_statistic': base['statistic'],
                'base_context': base['context'], 'base_source': base['source'],
                'equation': 'base_reported_concentration * reported_percent / 100',
                'range_interpretation': 'Arithmetic endpoints from an author-reported relative range; not an independent absolute measurement, confidence interval or concentration-time curve.'}
        else:
            value = positive(record['value'], '보고 노출')
            evidence.append(verify_source(record['source'], value, sources))
            values, unit, interval = [value], record['unit'], record['interval_hours']
            record_bindings, calculation = [record['source']], None
        auc = unit in ('ug*h/mL', 'ng*h/mL')
        if auc != (record['statistic'] == 'AUC'):
            raise ValueError('AUC와 농도는 다른 양입니다. 원 단위와 통계량을 구분해 주세요.')
        if auc:
            positive(interval, 'AUC의 실제 적분 구간')
            values = [x / interval for x in values]
        elif interval is not None:
            raise ValueError('농도에 AUC 적분 구간을 임의 적용하지 않습니다.')
        mass = unit in ('ug/mL', 'ng/mL', 'ug*h/mL', 'ng*h/mL')
        if unit not in ('uM', 'nM', 'ug/mL', 'ng/mL', 'ug*h/mL', 'ng*h/mL'):
            raise ValueError('지원하지 않는 노출 단위입니다.')
        bases = mass_bases if mass else [None]
        if mass and not bases:
            gaps.append({'exposure_id': record['id'], 'required': '보고 질량이 어느 화학형/분자량 기준인지 확인하거나 명시적 감도 시나리오를 제공해 주세요.'})
        for basis in bases:
            converted, factors = [], []
            for value in values:
                positive(value, '비교용 농도')
                concentration_um = (value * (1000 if unit.startswith('ug') else 1) / basis['molecular_weight_g_mol']
                                    if mass else value if unit == 'uM' else value / 1000)
                positive(concentration_um, '변환 농도')
                required = benchmark_um / concentration_um
                if not math.isfinite(required):
                    raise ValueError('계산 가능한 수치 범위를 벗어났습니다.')
                converted.append(concentration_um)
                factors.append(required)
            rows.append({'exposure_id': record['id'], 'label': record['label'],
                         'reported_value': record.get('value'), 'reported_unit': unit,
                         'value_origin': 'derived_from_reported_relative_range' if derivation else 'directly_reported',
                         'derived_value_range': values if derivation else None,
                         'derivation': calculation,
                         'reported_statistic': record['statistic'], 'interval_hours': interval,
                         'comparison_concentration_uM': converted[0] if not derivation else None,
                         'comparison_concentration_uM_range': sorted(converted) if derivation else None,
                         'comparison_statistic': 'AUC_divided_by_interval_mean' if auc else record['statistic'],
                         'exposure_context': record['context'],
                         'mass_basis_id': basis['id'] if basis else None,
                         'mass_basis_label': basis['label'] if basis else '보고된 몰농도',
                         'mass_basis_status': basis['status'] if basis else 'no_mass_conversion',
                         'assay_benchmark_uM': benchmark_um,
                         'required_effective_translation_factor': factors[0] if not derivation else None,
                         'required_effective_translation_factor_range': sorted(factors) if derivation else None,
                         'actual_translation_factor': None,
                         'efficacy_prediction': None, 'automatic_candidate_rejection': False,
                         'source_bindings': [*record_bindings, threshold['source'], *([basis['source']] if basis else [])]})
    return {'status': 'partial' if gaps else 'succeeded',
            'semantic_type': 'source_linked_exposure_requirement_scenarios',
            'context': arguments['context'], 'assay_benchmark': threshold, 'rows': rows,
            'mass_bases': mass_bases, 'unresolved_inputs': gaps, 'verified_source_locations': evidence,
            'summary': {'exposure_records': len(exposures), 'scenario_rows': len(rows),
                        'derived_exposure_records': sum(r.get('derivation') is not None for r in exposures),
                        'measured_site_exposure': False, 'efficacy_prediction': False,
                        'unknown_translation_is_not_zero': True},
            'comparison_assumption': 'Conditional equality of unbound effect-site concentrations between in-vivo and assay systems. Equal concentration does not establish equal effect; an average concentration is not a validated efficacy threshold.',
            'criterion_is_required_for_efficacy': False,
            'effect_equivalence_established': False,
            'equations': {'ug_per_ml_to_uM': '1000 * mass_concentration / molecular_weight',
                          'ng_per_ml_to_uM': 'mass_concentration / molecular_weight',
                          'auc_mean': 'reported_AUC / its_actual_time_interval; not Cmax or trough',
                          'relative_range': 'reported_base_concentration * each_reported_percent / 100; ratio endpoints invert concentration endpoints',
                          'required_effective_factor': 'nominal_assay_benchmark_uM / comparison_exposure_uM',
                          'factor_definition': '(unbound_effect_site_in_vivo / reported_plasma_concentration) / (unbound_effect_site_in_assay / nominal_assay_concentration)',
                          'conditional_decomposition': '(Kp_uu_in_vivo * fu_plasma) / (Kp_uu_assay * fu_medium), only if these compartments and binding relationships apply'},
            'limits': ['이 계산은 두 실험계의 자유 작용부위 농도가 같다는 가정에서 비교한 값입니다. 효능의 필요조건·실제 조직 자유농도·표적 관여·임상 효과를 입증하거나 예측하지 않습니다.',
                       '분자량 기준 미확인은 서로 다른 시나리오로 남깁니다. 염·모체의 존재만으로 원 PK 분석의 질량 기준을 확정하지 않습니다.',
                       '혈장/배지 결합과 조직/세포 내 분포가 모두 필요할 수 있습니다. 미측정 전달계수를1이나0으로 가정하지 않습니다.',
                       'Cmax는 최고점, AUC/시간은 평균입니다. 지속 노출이나 48시간 세포시험 효과와의 동등성은 별도 동역학·조건 확인이 필요합니다.',
                       '보고된 백분율의 산술 범위는 별도의 직접 측정값·신뢰구간·개인별 예측·시간 경과 곡선이 아닙니다. 기준 농도와 백분율이 같은 집단·조건에 적용되는지 원문으로 판단해야 합니다.',
                       '원문 문구·위치·숫자 일치는 검사하지만 문구가 해당 단위·집단·종말점을 뒷받침하는지는 원 조건과 함께 검토해야 합니다.',
                       '현재 요구 계수가 크거나 작다는 이유만으로 기전을 폐기하거나 후보를 임상적으로 유효하다고 판단하지 않습니다.']}
