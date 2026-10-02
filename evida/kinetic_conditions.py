"""Source-bound Michaelis–Menten implications; no inferred clinical effect."""
import math
from .exposure_requirements import verify_source, SourceBindingError


def obj(fields):
    return {'type': 'object', 'properties': fields, 'required': list(fields), 'additionalProperties': False}


TEXT = {'type': 'string'}
POSITIVE = {'type': 'number', 'exclusiveMinimum': 0}
SOURCE = obj({'artifact_id': TEXT, 'path': {'type': 'array', 'minItems': 1, 'maxItems': 20,
    'items': {'anyOf': [TEXT, {'type': 'integer', 'minimum': 0}]}},
    'quote': {'type': 'string', 'minLength': 1, 'maxLength': 3000}})
MODEL = obj({'id': TEXT, 'label': TEXT, 'conditions': TEXT,
    'km': obj({'value': POSITIVE, 'unit': {'type': 'string', 'enum': ['nM', 'uM', 'mM']}, 'source': SOURCE}),
    'vmax': obj({'value': POSITIVE, 'unit': {'type': 'string', 'enum': ['nmol/min/mg', 'umol/min/mg', 'nmol/min', 'umol/min']}, 'source': SOURCE})})
SCHEMA = obj({'source_artifact_ids': {'type': 'array', 'items': TEXT, 'minItems': 1, 'maxItems': 12},
    'reference': MODEL, 'comparators': {'type': 'array', 'minItems': 1, 'maxItems': 12, 'items': MODEL},
    'substrate_unit': {'type': 'string', 'enum': ['nM', 'uM', 'mM']},
    'substrate_values': {'type': 'array', 'items': POSITIVE, 'minItems': 1, 'maxItems': 100},
    'comparison_assumptions': {'type': 'array', 'items': TEXT, 'minItems': 1}})


def positive(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError('모수와 기질 농도는 양의 유한한 수여야 합니다. 결측을0으로 바꾸지 않습니다.')
    return value


def compare(arguments, sources):
    models = [arguments['reference'], *arguments['comparators']]
    if len({m['id'] for m in models}) != len(models) or any(not m['id'].strip() for m in models):
        raise ValueError('기준과 비교 모수 집합의 ID는 비어 있거나 중복될 수 없습니다.')
    scales = {'nM': .001, 'uM': 1., 'mM': 1000.}
    rates = {'nmol/min/mg': (1., 'nmol/min/mg'), 'umol/min/mg': (1000., 'nmol/min/mg'),
             'nmol/min': (1., 'nmol/min'), 'umol/min': (1000., 'nmol/min')}
    bindings, errors, normalized = [], [], []
    for m in models:
        for key in ['km', 'vmax']:
            p = m[key]; positive(p['value'])
            try: bindings.append(verify_source(p['source'], p['value'], sources))
            except ValueError as e: errors.append({'artifact_id': p['source']['artifact_id'], 'path': p['source']['path'], 'message': str(e)})
        km = m['km']['value'] * scales[m['km']['unit']]
        scale, basis = rates[m['vmax']['unit']]
        vmax = m['vmax']['value'] * scale
        positive(km); positive(vmax)
        normalized.append({'id': m['id'], 'label': m['label'], 'conditions': m['conditions'],
                           'km_uM': km, 'vmax': vmax, 'vmax_unit': basis})
    if errors: raise SourceBindingError(errors)
    ref = normalized[0]
    if any(m['vmax_unit'] != ref['vmax_unit'] for m in normalized):
        raise ValueError('질량으로 정규화한 속도와 총속도를 직접 비교할 수 없습니다. 원 기준을 확인하세요.')
    substrate = [positive(positive(s) * scales[arguments['substrate_unit']]) for s in arguments['substrate_values']]
    rows, crossings = [], []
    for m in normalized[1:]:
        denominator = m['vmax'] - ref['vmax']
        crossing = None if denominator == 0 else (ref['vmax'] * m['km_uM'] - m['vmax'] * ref['km_uM']) / denominator
        if crossing is not None and not math.isfinite(crossing):
            raise ValueError('주어진 모수 범위에서 유한한 교차점을 계산하지 못했습니다.')
        crossings.append({'comparator_id': m['id'], 'algebraic_crossing_uM': crossing,
            'positive_substrate_crossing': crossing is not None and crossing > 0,
            'equal_functions': m['vmax'] == ref['vmax'] and m['km_uM'] == ref['km_uM'],
            'meaning': 'Positive crossing is not required for two curves to differ; no measured activation or statistical significance inferred.'})
        for s in substrate:
            r = ref['vmax'] / (1 + ref['km_uM'] / s)
            v = m['vmax'] / (1 + m['km_uM'] / s)
            ratio = v / r
            if not all(math.isfinite(x) and x > 0 for x in [r, v, ratio, 1 / ratio]):
                raise ValueError('계산 범위를 확인하세요. 비유한 값을0이나 관측값으로 바꾸지 않습니다.')
            rows.append({'comparator_id': m['id'], 'substrate_uM': s,
                'reference_rate': r, 'comparator_rate': v, 'rate_unit': ref['vmax_unit'],
                'conditional_rate_ratio': ratio, 'amount_multiplier_for_equal_rate': 1 / ratio,
                'result_kind': 'conditional_mean_parameter_calculation_not_measurement'})
    return {'status': 'succeeded', 'semantic_type': 'conditional_parameter_calculation',
        'method': 'Michaelis-Menten v=Vmax*S/(Km+S)', 'parameters': normalized,
        'rows': rows, 'crossings': crossings, 'source_bindings': bindings,
        'comparison_assumptions': arguments['comparison_assumptions'],
        'source_semantics': 'Exact location, quote and numeric presence checked; fitted quantity, units and biological comparability still require source review.',
        'limits': ['Mean parameters are not raw-data refitting or confidence intervals.',
                  'Amount multipliers assume linear amount scaling and are not measured protein changes.',
                  'Substrate, preparation, residual compound and normalization must match for direct transfer.',
                  'One point can be compatible with multiple explanations; even multiple points need adequate precision and appropriate models.',
                  'No probability, in-vivo flux, dosing recommendation or clinical efficacy inferred.']}
