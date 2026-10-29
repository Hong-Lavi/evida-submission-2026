"""Public goal-management observations, never scientific relevance or a forced stop.

No model call, evidence removal, tool scheduling or count-based completion. The
coordinator chooses which link matters for the actual researcher goal.
"""
from collections import Counter
import json

GUIDANCE = (
    'Select the next research decision under ORIGINAL_MESSAGES and CURRENT_FRAME, then choose '
    'the information that could change it. In existing research_notes.next_goal state that '
    'decision, why this particular source/range/computation is needed now, and what sufficient '
    'finding would let you proceed or retain an explicit uncertainty. A new page is not itself '
    'a new research decision. Preserve alternatives without requiring exhaustive adjudication '
    'before a useful branch can advance. '
    'Separate a prerequisite for the active claim from an optional audit or an independent '
    'branch. If a denominator/method/identity is necessary for the claim, read it; if it only '
    'limits a stronger claim, keep that limit and examine the independent useful branch. '
    'Do not equate every unread row with a blocker or treat a source-access investigation as '
    'a biological hypothesis. Access failures stop that source or denied operation, not '
    'unrelated authorized research. '
    'For a disease-to-candidate goal, decide when the available mechanism/direction evidence '
    'supports comparing concrete candidates, which exact source-bound inputs a meaningful '
    'calculation needs, and which next observation could separate remaining explanations. '
    'These are research decisions, not mandatory tool counts or a fixed modality. Use actual '
    'registered computations when their inputs and decision relevance are established; do '
    'not invent an input or run a calculation merely to fill a missing stage. '
    'Publish a useful conditional decision when supported, with unresolved branches and '
    'outcome-conditioned next actions. A partial or unavailable branch is not a reason to '
    'conceal the useful result; it is also not permission to claim the whole goal complete. '
    'Do not force a final by elapsed calls or infer scientific sufficiency from these counts.')


def build(context):
    catalog = context.get('COMPLETED_VIEWS', [])
    recent = catalog[-8:]
    evidence = context.get('RELEVANT_EVIDENCE', [])
    # Counts/addresses refer to retained artifacts only, never valid candidates,
    # successful measurements, support, coverage, or independently read sources.
    kinds = Counter(a.get('kind', 'unknown') for a in evidence)
    def byte_size(value):
        return len(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode())
    return {
        'version': 'goal-supervision-v1',
        'authority': 'ORIGINAL_MESSAGES and current researcher corrections; CURRENT_FRAME is provisional decomposition',
        'guidance': GUIDANCE,
        'retained_artifact_counts_by_kind': dict(kinds),
        'recent_operation_names': [v.get('function', 'unknown') for v in recent],
        'recent_reading_ids': [v['reading_id'] for v in recent if 'reading_id' in v],
        'published_decision_present': context.get('PREVIOUS_DECISION') is not None,
        'context_observations': {
            'prior_public_finding_count': len(context.get('PRIOR_NOTE_FINDINGS', [])),
            'prior_public_findings_utf8_json_bytes': byte_size(context.get('PRIOR_NOTE_FINDINGS', [])),
            'completed_view_count': len(catalog),
            'visible_working_readings_utf8_json_bytes': byte_size(context.get('WORKING_READINGS', [])),
            'meaning': 'Application context field sizes only, not token counts, actual transport size or measured model burden. Use focus_readings for needed comparisons; every original remains retrievable.'},
        'scientific_sufficiency_assessed': False,
        'automatic_stop': False, 'forced_tool': None, 'automatic_retry': False,
    }
