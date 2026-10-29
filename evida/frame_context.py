"""Use one question-frame applicability rule for context and reading selection."""


def current_research_frame(state, rev, *, question_reassessment_required):
    current = next((e['body'] for e in reversed(state['events'])
                    if e['kind'] == 'work_framed' and e['body']['based_rev'] == rev), None)
    if current is not None:
        return current
    if question_reassessment_required:
        return None
    earlier = next((e['body'] for e in reversed(state['events'])
                    if e['kind'] == 'work_framed'), None)
    if earlier is None:
        return None
    return {**earlier, 'carried_from_rev': earlier['based_rev'], 'current_rev': rev}
