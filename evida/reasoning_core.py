"""Shared, replaceable hypothesis/design contract and source-backed perspectives.

The checker verifies the declared comparison, not biological truth or whether an
unreported confounder exists. Passing it does not authorise an experiment.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata

import jsonschema
from .validation_help import declaration_error


def obj(properties):
    return {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


TEXT = {'type': 'string', 'minLength': 1}
TEXTS = {'type': 'array', 'items': TEXT}
NUMBER = {'anyOf': [{'type': 'number'}, {'type': 'null'}]}
PREDICTION = {'anyOf': [
    obj({'kind': {'type': 'string', 'enum': ['direction']},
         'value': {'type': 'string', 'enum': ['increase', 'no_change', 'decrease', 'presence', 'absence']}}),
    obj({'kind': {'type': 'string', 'enum': ['interval']},
         'lower': NUMBER, 'upper': NUMBER,
         'lower_inclusive': {'type': 'boolean'}, 'upper_inclusive': {'type': 'boolean'}}),
]}
SCHEMA = obj({
    'version': {'type': 'string', 'enum': ['reasoning-design-v1']},
    'H1': TEXT, 'H0': TEXT,
    'hypothesis_level': {'type': 'string', 'enum': ['target', 'pathway', 'modality', 'programme', 'condition']},
    'specimen': TEXT,
    'factors': {'type': 'array', 'minItems': 2, 'items': obj({'id': TEXT, 'name': TEXT})},
    'changed_variable_id': TEXT,
    'arms': {'type': 'array', 'minItems': 2, 'maxItems': 2, 'items': obj({
        'id': TEXT, 'role': {'type': 'string', 'enum': ['intervention', 'reference']},
        'levels': {'type': 'array', 'minItems': 2, 'items': obj({'factor_id': TEXT, 'value': TEXT})}})},
    'controls': {'type': 'array', 'minItems': 1, 'items': obj({
        'id': TEXT, 'role': {'type': 'string', 'enum': ['reference', 'engagement', 'positive', 'assay']},
        'description': TEXT, 'validity_criterion': TEXT})},
    'readout': obj({'name': TEXT, 'contrast': TEXT, 'unit': TEXT, 'timepoint': TEXT}),
    'predictions': obj({'H1': PREDICTION, 'H0': PREDICTION}),
    'prediction_basis': obj({'origin': {'type': 'string', 'enum': ['proposed', 'source_reported']},
                             'source_ids': TEXTS, 'rationale': TEXT}),
    'refuting_result': obj({'prediction': {'type': 'string', 'enum': ['H0']},
                            'description': TEXT, 'valid_control_ids': {'type': 'array', 'minItems': 1, 'items': TEXT}}),
    'experiment_failure': obj({'invalid_control_ids': {'type': 'array', 'minItems': 1, 'items': TEXT},
                                'description': TEXT}),
    'next_actions': obj({outcome: TEXT for outcome in ('supports', 'refutes', 'inconclusive', 'experiment_failure')}),
    'unresolved_requirements': TEXTS,
    'interpretation_limits': {'type': 'array', 'minItems': 1, 'items': TEXT},
    'cards_used': {'type': 'array', 'items': obj({'id': TEXT, 'application': TEXT})},
})


def _plain(value):
    return re.sub(r'\s+', ' ', value).strip().casefold()


def _unique(items, field, label):
    values = [item[field] for item in items]
    if len(set(values)) != len(values) or any(not _plain(v) for v in values):
        raise ValueError(f'{label}: 비어 있거나 중복된 ID입니다.')
    return set(values)


def _prediction_bounds(p):
    lo = -math.inf if p['lower'] is None else p['lower']
    hi = math.inf if p['upper'] is None else p['upper']
    if any(v is not None and not math.isfinite(v) for v in (p['lower'], p['upper'])):
        raise ValueError('예상 구간에는 유한한 수 또는 null 경계가 필요합니다.')
    if lo > hi or (lo == hi and not (p['lower_inclusive'] and p['upper_inclusive'])):
        raise ValueError('예상 구간이 비어 있거나 뒤집혔습니다.')
    return lo, hi


def predictions_differ(a, b):
    """Disjoint declared outcomes on one shared measurement, not prose inequality."""
    if a['kind'] != b['kind']:
        raise ValueError('H1/H0의 예상은 같은 측정에서 같은 표현 형식으로 비교하세요.')
    if a['kind'] == 'direction':
        groups = ({'increase', 'no_change', 'decrease'}, {'presence', 'absence'})
        if not any(a['value'] in group and b['value'] in group for group in groups):
            raise ValueError('변화 방향과 유무를 서로 다른 관측처럼 비교할 수 없습니다.')
        return a['value'] != b['value']
    alo, ahi = _prediction_bounds(a)
    blo, bhi = _prediction_bounds(b)
    return (ahi < blo or bhi < alo
            or ahi == blo and not (a['upper_inclusive'] and b['lower_inclusive'])
            or bhi == alo and not (b['upper_inclusive'] and a['lower_inclusive']))


def validate_design(design, *, allowed_cards=None, cards_required=False, source_ids=None):
    jsonschema.validate(design, SCHEMA)
    # JSON minLength alone accepts whitespace. Check recursively without altering records.
    def nonblank(value):
        if isinstance(value, str) and not value.strip():
            raise ValueError('실험 설계의 필수 내용이 공백입니다.')
        if isinstance(value, dict):
            for v in value.values(): nonblank(v)
        if isinstance(value, list):
            for v in value: nonblank(v)
    nonblank(design)
    if _plain(design['H1']) == _plain(design['H0']):
        raise ValueError('H1과 H0가 같은 주장입니다.')
    factors = _unique(design['factors'], 'id', '비교 변수')
    _unique(design['arms'], 'id', '비교군')
    if {a['role'] for a in design['arms']} != {'intervention', 'reference'}:
        raise ValueError('개입군과 기준군을 하나씩 명시하세요.')
    levels = []
    for arm in design['arms']:
        if _unique(arm['levels'], 'factor_id', '군별 조건') != factors:
            raise ValueError('두 군의 모든 변화·고정 조건을 같은 변수 목록으로 명시하세요.')
        levels.append({v['factor_id']: _plain(v['value']) for v in arm['levels']})
    changed = {key for key in factors if levels[0][key] != levels[1][key]}
    if changed != {design['changed_variable_id']}:
        raise ValueError('실제로 달라지는 변수는 명시한 한 개여야 합니다. 두 군의 조건 표를 수정하세요.')
    controls = _unique(design['controls'], 'id', '통제')
    if not any(c['role'] == 'reference' for c in design['controls']):
        raise ValueError('기준군의 역할과 유효성 기준을 통제에 명시하세요.')
    if not any(c['role'] in {'engagement', 'positive', 'assay'} for c in design['controls']):
        raise ValueError('표적 개입 또는 측정이 실제로 작동했는지 확인할 통제가 필요합니다.')
    valid = design['refuting_result']['valid_control_ids']
    if len(valid) != len(set(valid)) or set(valid) != controls:
        raise declaration_error('H1 반박은 명시한 모든 통제가 유효할 때만 해석하세요.',
            path='/reasoning_design/refuting_result/valid_control_ids',
            allowed_references=sorted(controls), actual_reference=valid,
            issue='Require every control declared in this same design, exactly once. This does not certify that any control passed.')
    invalid = design['experiment_failure']['invalid_control_ids']
    if len(invalid) != len(set(invalid)) or set(invalid) != controls:
        raise declaration_error('실험 실패는 명시한 통제 중 하나라도 유효하지 않을 때로 구분하세요.',
            path='/reasoning_design/experiment_failure/invalid_control_ids',
            allowed_references=sorted(controls), actual_reference=invalid,
            issue='List every declared control exactly once: failure of any one invalidates interpretation. Do not change the scientific claims.')
    if _plain(design['experiment_failure']['description']) == _plain(design['refuting_result']['description']):
        raise ValueError('실험 실패를 가설 반박과 같은 결과로 기록할 수 없습니다.')
    if not predictions_differ(design['predictions']['H1'], design['predictions']['H0']):
        raise ValueError('H1과 H0의 예상이 겹칩니다. 동일 조건에서 구별되는 관측을 설계하세요.')
    basis = design['prediction_basis']
    if basis['origin'] == 'source_reported' and not basis['source_ids']:
        raise ValueError('원문 보고 예상에는 조회한 원자료를 연결하세요.')
    if source_ids is not None and not set(basis['source_ids']).issubset(source_ids):
        raise ValueError('예상의 근거 자료가 이 연구에 없습니다.')
    used = _unique(design['cards_used'], 'id', '사용 카드')
    if cards_required and not used:
        raise ValueError('사용한 추론 카드와 현재 가설에 적용한 이유를 기록하세요.')
    if allowed_cards is not None and not used.issubset(allowed_cards):
        raise ValueError('이번 실행에 전달되지 않은 카드를 사용했다고 기록할 수 없습니다.')
    return {'status': 'declared_contrast_pass',
            'prediction_resolution': 'qualitative' if design['predictions']['H1']['kind'] == 'direction' else 'numeric',
            'unresolved_requirements': design['unresolved_requirements'],
            'meaning': '기록한 조건·예상의 구별 가능성 검사이며 생물학적 타당성·실험 준비 완료 판정이 아닙니다.'}


def validate_hypothesis_designs(hypotheses, *, required=False, allowed_cards=None,
                                cards_required=False, source_ids=None, allow_empty=False):
    if required and not hypotheses and not allow_empty:
        raise ValueError('가설과 반박 가능한 비교를 최소 하나 명시하세요.')
    checks = {}
    for index, h in enumerate(hypotheses):
        if 'reasoning_design' not in h:
            if required:
                raise ValueError(f"가설 {h['id']}에 reasoning_design을 명시하세요.")
            continue
        try:
            checks[h['id']] = validate_design(h['reasoning_design'], allowed_cards=allowed_cards,
                cards_required=cards_required, source_ids=source_ids)
        except ValueError as error:
            details = getattr(error, 'declaration_help', None)
            if details is not None:
                details['path'] = f'/research_loop/hypotheses/{index}' + details['path']
                details['hypothesis_id'] = h['id']
            raise
    return checks


def require_designs(array_schema, *, allow_empty=False):
    array_schema['minItems'] = 0 if allow_empty else 1
    variants = array_schema['items']['anyOf']
    array_schema['items']['anyOf'] = [v for v in variants if 'reasoning_design' in v['properties']]


SKELETON = (
    'Use ONE reasoning core to frame the research goal, choose information and computations, '
    'integrate evidence, generate hypotheses, design experiments and revise the next judgment. '
    'Before each investigation identify the unresolved question, why the chosen information or '
    'calculation can address it, which verified inputs it needs and how its result could change '
    'the next decision. Use the registered tools and preserve the actual output, conditions '
    'and limits; a plausible tool name or requested computation is not a completed result. '
    'Investigate the public web and original scientific sources by default: web discovery, '
    'Chrome-rendered pages, public full text and authorised scholarly APIs are complementary '
    'access routes, not a fixed database fence. Select the access route for the needed evidence; '
    'check search relevance, retrieve the actual document and needed supplements, and cite the '
    'read locations rather than search snippets. An unvisited link is not an acquired supplement. '
    'Lens is optional and must not be a prerequisite for research. Credentials stay in the '
    'server-side adapters, never in model input, URLs, source documents or browser sessions. '
    'A missing credential or denied external source is an operational limitation on that source. '
    'Record it and request the needed owner action; do not bypass it, retry it secretly, or change '
    'the model/provider. Continue independent authorized research with its actual available evidence '
    'and report any resulting coverage gap. Do not turn API availability or a document lookup '
    'into a biological H1/H0 experiment or let it replace the researcher\'s scientific goal. '
    'The initial frame_work is a goal and investigation plan. When evidence is insufficient, '
    'set hypotheses to an empty array and proceed with justified information gathering; do not '
    'invent a hypothesis or experiment merely to fill the initial frame. Hypotheses supplied '
    'in a frame still need a valid design, and the final research decision must include at '
    'least one grounded or explicitly proposed hypothesis with its discriminating design. '
    'Generate the expert-consensus explanation AND plausible alternatives, not just failure factors. '
    'Each hypothesis has a reasoning_design: H1 versus a bounded H0; exactly one factor differs '
    'between two arms and all declared other factors stay constant. Compare predictions on the SAME '
    'readout, contrast, unit and timepoint. State which valid controls make the H0 prediction a '
    'refuter, and separately what invalidates the experiment. experiment_failure.invalid_control_ids '
    'lists all controls: if any one is invalid, do not infer refutation. Give the next action for support, '
    'refutation, inconclusive results and experiment failure. Missing thresholds are unresolved '
    'requirements, not invented source facts. Qualitative predictions need an uncertainty/noise '
    'criterion before execution. Cards are perspectives with historical examples, never evidence '
    'for the current case or universal biological rules. Record only delivered card IDs and the '
    'specific application. The source-derived perspectives also apply to investigation choice, '
    'evidence integration and re-judgement. When one helps, record its delivered perspective identifier '
    'and application in cards_used or explain its use in research_notes. The perspectives are '
    'optional: leave cards_used empty when none fits; never invent applicability. '
    'The checker tests the declared structure, not biological truth. '
    'For each proposed external observation set design_hypothesis_id to the exact hypothesis '
    'whose comparison it executes; its question, controls and predictions must agree. '
    'Use separate single-factor contrasts for different causal questions. '
    'Never import a worked-example outcome as pre-outcome evidence in a retrospective study. '
    'Communicate to the researcher in their language, leading with the concrete proposed action, '
    'the evidence supporting that choice, its applicable conditions and the next decision for each outcome. '
    'Give a useful positive proposal when evidence supports one. Place detailed qualifications beside '
    'the specific claim they constrain; avoid a narrative dominated by repeated negative disclaimers. '
    'For an unresolved question, name the information or comparison that advances the original goal. '
    'When existing therapy is discovered, investigate documented remaining limitations and develop a '
    'justified improvement question, candidate and discriminating comparison. Preserve actual successes '
    'as well as counterevidence, and never invent a limitation to manufacture an unmet need.'
)


def load_cards():
    path = Path(__file__).with_name('reasoning_cards.json')
    return json.loads(path.read_text())['cards']


# These aliases describe existing catalog metadata, not disease/target associations.
# Workflow and modality cues alone cannot establish a card's conditional applicability.
_MODALITY_CUES = {
    'small_molecule': ('small molecule', 'small molecules', '저분자', '저분자화합물', '소분자'),
    'sirna': ('sirna', 'short interfering rna', 'small interfering rna'),
}
_SITUATION_CUES = {
    'resistance': ('resistance', '내성'),
    'compensation': ('compensation', '보상 경로', '반대 경로'),
    'substrate_reduction': ('substrate reduction', '기질 감소', '원료 공급'),
    'biomarker': ('biomarker', 'biomarkers', '바이오마커', '생체표지자'),
    'selectivity': ('selectivity', '선택성'),
    'compartment': ('compartment', 'compartments', '구획'),
    'engagement': ('target engagement', '표적 작용 확인', '표적 결합 확인'),
    'orthogonal_assays': ('orthogonal assay', 'orthogonal assays', '독립된 검사', '독립 검사'),
    'target_assignment': ('target assignment', '표적 배정', '표적 지정'),
    'combination': ('combination', '병용', '조합'),
    'active_comparator': ('active comparator', '활성 대조', '대안 치료'),
    'external_control': ('external control', 'historical control', '외부 대조군', '역사적 대조군'),
    'surrogate': ('surrogate', '대리 지표', '중간 지표'),
    'heterogeneity': ('heterogeneity', '이질성'),
    'subgroup': ('subgroup', 'subgroups', '하위 집단', '아형'),
    'replication': ('replication', '재현'),
    'endpoint_hierarchy': ('endpoint hierarchy', '종점 우선순위'),
    'safety': ('safety', '안전성'),
    'withdrawal': ('withdrawal', '투여 중단'),
    'dose_interval': ('dose interval', 'dosing interval', '투여 간격'),
}
_STOPWORDS = set(('a an the and or of in on for from to by with without under at as is are '
    'has have its this that it be not than may one same which whether use using generate '
    'hypothesis hypotheses mechanism mechanisms target targets candidate candidates find '
    'discover want would like disease treatment compound compounds small molecule molecules '
    'general generation discrimination learning sirna 기전 타겟 표적 후보 질병 치료 화합물 '
    '대한 대해 찾기 찾고 찾고싶어요 싶어요 싶습니다 합니다 하고 이를 위한 같은 다시 상태').split())


def _retrieval_text(text):
    return re.sub(r'[_\-‐‑–—]+', ' ', unicodedata.normalize('NFKC', text).casefold())


def _retrieval_terms(text):
    # Split script boundaries ("siRNA를") while preserving full Korean words.
    words = re.findall(r'[a-z0-9]+|[가-힣]+|[^\W\d_]+', _retrieval_text(text))
    terms = set()
    for word in words:
        if re.fullmatch(r'[가-힣]+', word):
            for suffix in ('에서는', '으로', '에서', '에는', '에게', '은', '는', '이', '가', '을', '를', '의', '에', '와', '과', '도'):
                if word.endswith(suffix) and len(word) - len(suffix) >= 2:
                    word = word[:-len(suffix)]
                    break
        if len(word) >= 2 and word not in _STOPWORDS:
            terms.add(word)
    return terms


def _cue_matches(text, cues):
    matches = {}
    normalized = _retrieval_text(text)
    for tag, aliases in cues.items():
        # Korean scientific nouns may have attached particles; Latin cues need boundaries.
        found = [alias for alias in aliases if re.search(
            (r'(?<![a-z0-9])' + re.escape(_retrieval_text(alias)) + r'(?![a-z0-9])'), normalized)]
        if found:
            matches[tag] = found
    return matches


def retrieve_cards(request_text, *, excluded_cases=(), maximum=5):
    """Deterministic multilingual lexical/cue retrieval; no provider or outcome index.

    A score measures text/cue overlap, never evidence for a biological hypothesis.
    No-match method perspectives are explicitly marked and carry no outcome examples.
    """
    if maximum <= 0:
        return []
    normalized = _retrieval_text(request_text)
    excluded = {_retrieval_text(case) for case in excluded_cases}
    cards = load_cards()
    # Preserve programme exclusion for attached Korean particles and case variants too.
    for card in cards:
        excluded.update(_retrieval_text(e['case_id']) for e in card['worked_examples']
                        if _retrieval_text(e['case_id']) in normalized)
    eligible = [card for card in cards if not any(
        _retrieval_text(e['case_id']) in excluded for e in card['worked_examples'])]
    modalities = _cue_matches(request_text, _MODALITY_CUES)
    situations = _cue_matches(request_text, _SITUATION_CUES)
    terms = _retrieval_terms(request_text)
    # Index conditions and titles, not worked examples/outcomes, sources or evaluation cases.
    vocabulary = {card['id']: _retrieval_terms(' '.join([
        card['when_to_use'], card.get('title_ko', ''), *card['situation_tags']])) for card in cards}
    frequency = {term: sum(term in words for words in vocabulary.values())
                 for term in terms}
    ranked = []
    for card in eligible:
        matched_terms = sorted(term for term in terms & vocabulary[card['id']]
                               if frequency[term] <= len(cards) / 2)
        matched_situations = sorted(set(situations) & set(card['situation_tags']))
        matched_modalities = sorted(set(modalities) & {tag.casefold() for tag in card['modality_tags']})
        score = sum(math.log(1 + len(cards) / frequency[term]) for term in matched_terms)
        score += 4 * len(matched_situations)
        if score <= 0:
            continue
        # Prefer a stated modality only after contextual relevance; it cannot create a match.
        rationale = {'kind': 'context_match', 'score': round(score, 6),
                     'matched_terms': matched_terms, 'matched_situation_tags': matched_situations,
                     'matched_modality_tags': matched_modalities,
                     'cue_aliases': {tag: situations[tag] for tag in matched_situations},
                     'meaning': 'Text/cue overlap only; conditional applicability and biological support are unverified.'}
        ranked.append((score, bool(matched_modalities), card['id'], card, rationale))
    ranked.sort(key=lambda row: (-row[0], -row[1], row[2]))
    if ranked:
        result = []
        for _, _, _, card, rationale in ranked[:maximum]:
            result.append({**deepcopy(card), 'retrieval_rationale': rationale})
        return result
    # Explicit method-policy fallback, independent of catalog/ID order. Never fill a
    # partly matched result with unrelated cards. Specific case conditions remain unknown.
    perspectives = (['target_assignment'] if 'small_molecule' in modalities else [])
    perspectives += ['causal_chain', 'endpoint_hierarchy']
    limit = min(maximum, len(perspectives))
    # Exclusions can remove a preferred example-bearing card. Substitute other
    # existing method perspectives, never the excluded card with its example erased.
    perspectives += ['engagement', 'active_comparator', 'external_control', 'heterogeneity', 'safety']
    result = []
    for perspective in perspectives:
        choices = sorted((c for c in eligible if perspective in c['situation_tags']), key=lambda c: c['id'])
        if not choices:
            continue
        card = deepcopy(choices[0])
        card['worked_examples'] = []
        card['example_delivery_note'] = 'Outcome examples withheld for unmatched general method perspectives.'
        card['retrieval_rationale'] = {'kind': 'generic_fallback', 'score': 0,
            'matched_terms': [], 'matched_situation_tags': [],
            'matched_modality_tags': sorted(set(modalities) & {tag.casefold() for tag in card['modality_tags']}),
            'fallback_perspective': perspective,
            'meaning': 'No contextual match. General method perspective only; its case conditions are not established and it is not disease-specific evidence.'}
        result.append(card)
        if len(result) >= limit:
            break
    return result


def context(request_text, *, cards_enabled=True, excluded_cases=(), evidence_scope=None):
    cards = retrieve_cards(request_text, excluded_cases=excluded_cases) if cards_enabled else []
    restricted = bool(evidence_scope and (evidence_scope.get('as_of') or evidence_scope.get('mode') == 'supplied_only'))
    if restricted:
        for card in cards:
            card['worked_examples'] = []
            card['example_delivery_note'] = 'Historical outcome examples withheld for bounded-source research. '
            card['example_delivery_note'] += 'General method perspectives and pretrained-model hindsight are not blinded.'
    from .reasoning_perspectives import load as load_perspectives
    value = {'version': 'reasoning-core-v2', 'cards_enabled': cards_enabled,
             'cards_required': False,
             'skeleton': SKELETON, 'cards': cards,
             'perspectives': (load_perspectives(excluded_cases=excluded_cases,
                 request_text=request_text, restricted=restricted) if cards_enabled else []),
             'perspective_status': 'source-derived optional analyst abstractions; not parameter training or demonstrated quality improvement',
             'perspective_catalog_sha256': hashlib.sha256(Path(__file__).with_name('reasoning_perspectives.json').read_bytes()).hexdigest(),
             'retrieval': 'multilingual_condition_cues_v2_explicit_method_fallback',
             'retrieval_status': ('disabled' if not cards_enabled else
                                  cards[0]['retrieval_rationale']['kind'] if cards else 'no_cards_delivered'),
             'excluded_cases': sorted(excluded_cases),
             'historical_examples_suppressed': restricted}
    from .reasoning_perspectives import for_stage
    return for_stage(value, 'frame')


def preserved_context(payload):
    for item in reversed(payload.get('input', [])):
        content = item.get('content')
        if not isinstance(content, str):
            continue
        try:
            from .model_context import unpack
            value = unpack(json.loads(content)).get('CURRENT_CALL', {}).get('reasoning_core')
        except (ValueError, AttributeError):
            continue
        if value is not None:
            return value
    return None


def view(store, wid, state):
    """Display the exact delivered cards, not today's catalog under old records."""
    records = [a for a in state['artifacts'] if a['kind'] == 'reasoning_design_review'
               and a['meta'].get('decision_id') == state.get('decision_id')]
    if not records:
        return None
    value = json.loads(store.artifact(wid, records[-1]['id'])['content'])
    return {**value, 'artifact_id': records[-1]['id']}
