"""Researcher-declared source boundaries on normal worker admission.

Dates are declarations, not automatic verification of uploads or model memory.
Existing records remain intact.
"""
from datetime import date

LOCAL_TOOLS = frozenset({
    'pocket_docking', 'pose_interactions', 'protonation_states', 'rdkit', 'admet', 'source_document', 'compound_selection',
    'analogue_proposal', 'proposal_qualification', 'exposure_requirements',
    'kinetic_conditions', 'reported_activity_comparison', 'next_observation_selection',
})


def validate(value):
    if not isinstance(value, dict) or set(value) != {'mode', 'as_of', 'note'}:
        raise ValueError('근거 범위에는 mode, as_of, note를 기록하세요.')
    if value['mode'] not in ('supplied_only', 'unrestricted'):
        raise ValueError('제공한 근거만 사용하거나 공개 근거 조회를 허용하는 범위를 선택하세요.')
    if not isinstance(value['note'], str) or not value['note'].strip() or len(value['note']) > 2000:
        raise ValueError('근거 범위의 이유를 2,000자 이내로 기록하세요.')
    if value['as_of'] is not None:
        if not isinstance(value['as_of'], str):
            raise ValueError('근거 기준일은 YYYY-MM-DD 또는 null이어야 합니다.')
        try:
            parsed = date.fromisoformat(value['as_of'])
        except ValueError:
            raise ValueError('근거 기준일은 YYYY-MM-DD여야 합니다.') from None
        if parsed.isoformat() != value['as_of']:
            raise ValueError('근거 기준일은 YYYY-MM-DD여야 합니다.')
    return dict(value)


def view(state):
    for event in reversed(state.get('events', [])):
        body = event.get('body', {})
        if event.get('kind') == 'message' and 'evidence_scope' in body:
            return {**validate(body['evidence_scope']),
                    'message_id': body.get('message_id'),
                    'meaning': 'Researcher-declared boundary. Uploaded-source dates and model-memory hindsight require separate review.',
                    'permitted_computations': sorted(LOCAL_TOOLS)}
    return None


def check_tool(state, tool):
    scope = view(state)
    if scope and scope['mode'] == 'supplied_only' and tool not in LOCAL_TOOLS:
        raise ValueError('이 연구는 제공한 근거만 사용합니다. 새 외부 조회는 실행하지 않았습니다. '
                         '저장된 원문을 읽고 후보를 기록하거나 허용된 계산을 사용하세요. '
                         '조회 범위의 변경은 연구자가 새 메시지로 지정해야 합니다.')
