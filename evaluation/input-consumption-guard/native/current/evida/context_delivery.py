"""Limit repeated view delivery while keeping exact source addresses and pins.

Recent-observation delivery adapts the mechanism independently exercised with the
MIT SWE-agent LastNObservations processor. It is not scientific relevance ranking.
Stored evidence, notes, decisions and native function call/result pairs are intact.
"""
from copy import deepcopy


def apply_context_delivery(context, *, native_reading_ids=(), recent_count=2, force_full=False):
    if type(recent_count) is not int or recent_count < 1:
        raise ValueError('Keep at least one recent observation')
    output = dict(context)
    views = context['WORKING_READINGS']
    catalog = context['COMPLETED_VIEWS']
    positions = {view['reading_id']: index for index, view in enumerate(catalog)}
    focus = context.get('READING_FOCUS') or {}
    pinned = set(focus.get('reading_ids', []))
    eligible = {view['reading_id'] for view in views}
    # Native outputs are delivered separately and never rewritten by this policy.
    recent = set(sorted(eligible, key=lambda key: positions.get(key, -1))[-recent_count:])
    delivered, references = [], []
    for view in views:
        if force_full or view['reading_id'] in pinned | recent:
            delivered.append(view)
        else:
            reference = {key: deepcopy(value) for key, value in view.items() if key != 'content'}
            reference['content_view'] = 'saved_reference_only; original body remains available'
            reference['restore_with'] = 'focus_readings(reading_ids=[this ID and any other IDs still needed]); selection replaces the previous focus'
            reference['scientific_status'] = 'not a relevance exclusion, support judgment or missing result'
            delivered.append(reference)
            references.append(view['reading_id'])
    output['WORKING_READINGS'] = delivered
    output['CONTEXT_DELIVERY'] = {
        'policy': 'recent_views_plus_explicit_pins_v1', 'recent_history_count': recent_count,
        'saved_reference_ids': references, 'explicit_pin_ids': sorted(pinned),
        'native_reading_ids': list(native_reading_ids), 'full_delivery_for_terminal_without_tools': force_full,
        'meaning': 'Delivery state only. Every source and saved view remains retrievable. '
            'Review source conditions, unresolved discrepancies and sources outside this focus. '
            'Pin the exact views needed together; aging is not grounds to dismiss evidence. '
            'Notes and candidate ranks are not substitutes for checking originals.',
    }
    return output
