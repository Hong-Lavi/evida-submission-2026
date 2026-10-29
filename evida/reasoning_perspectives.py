"""Optional source-derived perspectives within the shared reasoning core.

The catalog explains how published arguments informed the method. Its examples
are not evidence for the current research. Selection and output stay with the
normal orchestrator; this module never executes a scientific tool.
"""
from copy import deepcopy
import hashlib
import json
import re
from pathlib import Path


STAGE_GUIDANCE = {
    'frame': (
        'Clarify the desired change, population/model, disease stage and practical constraints. '
        'Distinguish what the researcher said from your assumptions. Identify what is unknown '
        'and which kind of information would change the next decision. An empty initial '
        'hypothesis list is valid; do not invent mechanisms or designs before investigating.'),
    'research': (
        'Use the current question, actual returned observations and remaining uncertainty to '
        'choose the next investigation. In research_notes explain why this source or computation '
        'is informative, its verified inputs, and how different results could change a hypothesis '
        'or next experiment. Execute the registered function, read its actual result, and integrate '
        'it with source conditions and counterevidence before deciding the next action. '
        'Choose complementary tools when they answer different unresolved links, not to fill a checklist.'),
    'synthesis': (
        'Connect the original goal to the collected evidence and actual computations, then to '
        'consensus and alternative explanations, candidates and a discriminating next comparison. '
        'Explain why each proposed explanation accounts for the observations. Separate source facts, '
        'model-dependent predictions and new proposals. For each result branch state what changes '
        'in the research decision and which uncertainty remains. Unperformed computations stay unperformed.'),
    'goal_review': (
        'Review whether the actual original research request is sufficiently addressed by the preserved '
        'conditional proposal. Use applicable shared principles to connect information choice, alternatives, '
        'candidate reasoning, computations and outcome-conditioned next actions. These are request-dependent '
        'links, not mandatory pipeline boxes. External observations may remain proposed. Identify only '
        'decision-relevant internal work still needed; do not demand proof of patient efficacy or exhaustive '
        'sources. Record applicable delivered principle IDs, without inventing use or treating them as evidence.'),
    'decision_correction': (
        'Repair the named contract error while preserving the source facts, failed runs, counterevidence '
        'and scientific uncertainty. Do not invent a result, threshold or tool execution to make a schema pass.'),
}


def load(*, excluded_cases=(), request_text='', restricted=False):
    catalog = json.loads(Path(__file__).with_suffix('.json').read_text())
    excluded = {str(value).casefold() for value in excluded_cases}
    # Accept both the paper identity and an extraction trace identity such as
    # P139-PMC6028240. They name the same construction source.
    excluded.update(pmc for value in tuple(excluded)
                    for pmc in re.findall(r'pmc\d+', value))
    mentioned = request_text.casefold()
    delivered = []
    for item in catalog['perspectives']:
        # Exclude the entire derived perspective, not just erase an excluded
        # example and retain its outcome-derived generalization in an evaluation.
        examples = item['worked_examples']
        identities = {value.casefold() for e in examples for value in (
            e['case_id'], *[s['id'] for s in e['source_refs']])}
        identities.update(v.casefold() for v in item.get('construction_case_ids', []))
        if identities & excluded or any(value in mentioned for value in identities):
            continue
        item = deepcopy(item)
        item.pop('construction_case_ids', None)
        # Exact full provenance is bound by the catalog hash in each context and
        # protocol. Avoid repeatedly sending internal audit paths/duplicate hashes
        # to the model while retaining the historical argument and source links.
        for example in item['worked_examples']:
            for key in ('trace_relative_path', 'source_xml_sha256', 'review_relative_path'):
                example.pop(key, None)
        if restricted:
            item['worked_examples'] = []
            item['example_delivery_note'] = (
                'Historical outcomes withheld for bounded-source research. The general method '
                'and pretrained model are not time-blinded or independent of construction sources.')
        if catalog.get('version') == 'source-argument-perspectives-full-corpus-v1':
            # All perspectives remain selectable. Detailed historical reasoning is
            # read on demand, avoiding repeated delivery of every example per call.
            item = {key:item[key] for key in ('id','title_ko','when_to_use','principle')}
            item['worked_examples'] = []
            item['detail_function'] = 'read_reasoning_principle'
            item['detail_instruction'] = 'Read this ID for information selection, discriminating comparison, result-conditioned updates and exact source locations before applying it.'
            if restricted:
                item['example_delivery_note'] = 'Historical cases withheld; the general method and pretrained model are not time-blinded.'
        delivered.append(item)
    return delivered


def read_detail(principle_id, section, offset=0, limit=10, *, excluded_cases=(), request_text='', restricted=False):
    if principle_id not in {p['id'] for p in load(excluded_cases=excluded_cases, request_text=request_text, restricted=restricted)}:
        raise ValueError('현재 연구에 전달된 추론 관점 ID를 선택해 주세요.')
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError('조회 범위를 확인해 주세요.')
    path = Path(__file__).with_name('reasoning_principle_details.json')
    detail = json.loads(path.read_text())[principle_id]
    if section == 'principle':
        value = deepcopy(detail['perspective']); value.pop('construction_case_ids', None)
        if restricted:
            # Detailed stage examples can contain historical results even when
            # their citations and worked_examples have been removed. Deliver
            # the general perspective and source-bounded operations instead.
            value = {k:value[k] for k in ('id','title_ko','when_to_use','principle')}
            value['worked_examples'] = []
            value['stage_use'] = {
                'investigate': STAGE_GUIDANCE['research'],
                'generate': value['principle'],
                'compare': 'Use only the supplied observations to state competing predictions, the changed factor, controls and the observation that distinguishes the explanations.',
                'update': 'For each possible result, state which explanation gains or loses support, under the supplied measurement and intervention conditions. Keep an unsuccessful measurement separate from a valid negative result.'}
            value['source_scope'] = 'Historical stage examples and source cases withheld; apply this general perspective to the supplied evidence.'
        rows = [value]
    elif section == 'sources': rows = [] if restricted else detail['source_locations']
    elif section == 'cases': rows = [] if restricted else detail['case_coverage']
    else: raise ValueError('원리·원문 위치·사례 목록 중 하나를 선택해 주세요.')
    return {'principle_id':principle_id,'section':section,'rows':rows[offset:offset+limit],
            'total_rows':len(rows),'offset':offset,'catalog_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'historical_examples_suppressed':restricted,
            'purpose':'Understand how this reasoning perspective was derived and where it applies. Retrieve current scientific evidence for the current research goal.'}


def allowed_ids(core):
    return {c['id'] for key in ('cards', 'perspectives') for c in core.get(key, [])}


def cards_required(core):
    # Historical frozen contexts retain their original contract. New runs treat
    # cards as optional perspectives, not mandatory evidence for every hypothesis.
    return core.get('cards_required', core.get('cards_enabled', False))


def for_stage(core, stage):
    if core is None or core.get('version') != 'reasoning-core-v2':
        return core
    value = deepcopy(core)
    value.pop('sha256', None)
    value['stage'] = stage
    value['stage_guidance'] = STAGE_GUIDANCE[stage]
    value['sha256'] = hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return value
