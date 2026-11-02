"""Public goal-management observations, never scientific relevance or a forced stop.

No model call, evidence removal, tool scheduling or count-based completion. The
coordinator chooses which link matters for the actual researcher goal.
"""
from collections import Counter
import json
import re
from urllib.parse import urlsplit, urlunsplit

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


def build(context, *, source_observations=None):
    catalog = context.get('COMPLETED_VIEWS', [])
    recent = catalog[-8:]
    evidence = context.get('RELEVANT_EVIDENCE', [])
    # Counts/addresses refer to retained artifacts only, never valid candidates,
    # successful measurements, support, coverage, or independently read sources.
    kinds = Counter(a.get('kind', 'unknown') for a in evidence)
    def byte_size(value):
        return len(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode())
    return {
        'version': 'goal-supervision-v2',
        'source_attempt_observations': source_attempt_observations(catalog) if source_observations is None else source_observations,
        'strategic_reconsideration': {
            'instruction': 'Under ORIGINAL_MESSAGES and CURRENT_FRAME, reconsider the research decision before another acquisition. Use existing research_notes.next_goal to say what new information this source/range can add beyond retained readings, why it could change the next action, and what you will do if it remains unavailable. Inspect retained source_navigation link offsets before reacquiring a page to find its links. If an unresolved source only limits a stronger claim, choose whether a useful conditional checkpoint or an independent branch is warranted; if it is essential, explain that dependency. Repeated sources are observations, not a forced switch or scientific sufficiency verdict. Do not fabricate inputs, conclusions or successful access.',
            'model_decides': True, 'forced_action': None, 'automatic_stop': False},
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


def _source_key(arguments):
    pmc = arguments.get('pmc_id')
    url = arguments.get('url')
    if isinstance(pmc, str) and re.fullmatch(r'(?:PMC)?[0-9]+', pmc, re.I):
        return 'pmc:' + pmc.upper().removeprefix('PMC')
    if isinstance(url, str):
        parsed = urlsplit(url)
        match = re.search(r'/articles/PMC([0-9]+)(?:/|$)', parsed.path, re.I)
        if parsed.hostname in ('pmc.ncbi.nlm.nih.gov', 'www.ncbi.nlm.nih.gov') and match:
            return 'pmc:' + match.group(1)
        return 'url:' + urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip('/'), parsed.query, ''))
    query = arguments.get('query')
    if isinstance(query, str):
        return 'query:' + ' '.join(query.casefold().split())
    return None


def source_attempt_observations(catalog):
    """Group stored view metadata by source, preserving new ranges and failures.

    A repeated document can contain genuinely new information. These are factual
    retrieval addresses, never a productivity score or a scientific stop gate.
    """
    artifact_sources = {}
    groups = {}
    for position, view in enumerate(catalog):
        args = view.get('arguments') or {}
        if not isinstance(args, dict):
            continue
        key = _source_key(args)
        aid = view.get('source_artifact_id')
        if key is None:
            key = artifact_sources.get(args.get('artifact_id'))
        if key is None:
            continue
        if aid:
            artifact_sources[aid] = key
        delivery = view.get('delivery') or {}
        selected = {k: args[k] for k in ('pmc_id','url','engine','query','artifact_id','offset','limit','render_mode') if k in args}
        signature = json.dumps({'function': view.get('function'), 'arguments': selected}, sort_keys=True)
        group = groups.setdefault(key, {'source_key': key, 'view_count': 0, 'operations': {}, 'latest_views': [], 'last_position': position})
        group['view_count'] += 1
        group['operations'][signature] = group['operations'].get(signature, 0) + 1
        group['latest_views'].append({'reading_id': view.get('reading_id'), 'function': view.get('function'),
            'arguments': selected, 'status': delivery.get('status'),
            'offset': delivery.get('offset'), 'total_rows': delivery.get('total_rows'), 'has_more': delivery.get('has_more')})
        group['latest_views'] = group['latest_views'][-8:]
        group['last_position'] = position
    repeated = []
    for group in sorted(groups.values(), key=lambda g: g['last_position']):
        if group['view_count'] < 2:
            continue
        repeated.append({'source_key': group['source_key'], 'view_count': group['view_count'],
            'distinct_operations': len(group['operations']),
            'repeated_exact_operations': [{'operation': json.loads(k), 'view_count': n} for k, n in group['operations'].items() if n > 1],
            'latest_views': group['latest_views']})
    return {'revisited_sources': repeated[-8:], 'canonicalization': 'PMC identity across article and page tools; otherwise URL without fragment or casefolded exact query. Does not equate DOI with PMC, search variants, changed content, or new ranges.',
        'meaning': 'Retained view addresses and delivery status only. A revisit can be useful; distinct ranges are preserved. These counts do not assess new scientific information, evidence quality, coverage, or completion.',
        'automatic_stop': False, 'forced_tool': None}
