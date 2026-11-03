"""Navigation records are not full scientific readings or prior tool arguments.

All originals stay in the artifact store. Large catalog fields are replaced by
explicit, hashed addresses; current decisions and native tool returns are not
processed by this module.
"""
from copy import deepcopy
import hashlib
import json


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def field_reference(value, artifact_id, field_path):
    raw = encoded(value)
    entry = {'content_view': 'catalog_reference_not_read', 'artifact_id': artifact_id,
             'field_path': list(field_path), 'original_json_bytes': len(raw),
             'original_value_sha256': hashlib.sha256(raw).hexdigest(),
             'restore_with': 'inspect_artifact: use artifact_id; original metadata and result are returned',
             'meaning': 'Omitted from repeated navigation only; not excluded, evaluated, or evidence of absence.'}
    if isinstance(value, dict):
        entry['available_keys'] = list(value)
    if isinstance(value, (dict, list)):
        entry['item_count'] = len(value)
    return entry


def catalog_fields(value, artifact_id, field_path, *, field_bytes=1600):
    """Keep small conditions verbatim; point to each large top-level field."""
    if not isinstance(value, dict):
        return (deepcopy(value) if len(encoded(value)) <= field_bytes
                else field_reference(value, artifact_id, field_path))
    return {key: (deepcopy(child) if len(encoded(child)) <= field_bytes
                  else field_reference(child, artifact_id, [*field_path, key]))
            for key, child in value.items()}


def compact_artifact_catalog(entry, matching_view=False):
    output = {key: deepcopy(entry[key]) for key in
              ('artifact_id', 'title', 'kind', 'sha256', 'available_result_fields', 'total_rows', 'rows_loaded')
              if key in entry}
    aid = entry['artifact_id']
    meta = entry.get('meta', {})
    output['available_meta_fields'] = list(meta)
    meta_keys = ('source_artifact_id', 'input_artifact_id', 'consumed_artifacts', 'function',
                 'based_rev', 'source_url', 'url', 'scientific_context_verified')
    output['meta'] = catalog_fields({key: meta[key] for key in meta_keys if key in meta}, aid, ['meta'])
    summary = entry.get('summary_view', {})
    output['available_summary_fields'] = list(summary)
    summary_keys = ('status', 'semantic_type', 'contrast', 'context', 'limits', 'permissions', 'pmc_id', 'title')
    output['summary_view'] = catalog_fields({key: summary[key] for key in summary_keys if key in summary}, aid, ['result'])
    output['content_view'] = 'navigation_only; inspect_artifact returns original metadata and result; no source has been excluded'
    if matching_view:
        # Only duplicate navigation moves to its hash-matched view. Conditions,
        # contrast, limits and scientific metadata remain at this address.
        output.pop('title', None)
        output.pop('available_meta_fields', None)
        output['meta'] = {key: value for key, value in output['meta'].items()
                          if key not in ('source_artifact_id', 'function', 'based_rev')}
        output['catalog_location'] = 'COMPLETED_VIEWS: matching reading_id and sha256'
    return output


def compact_view_catalog(entry):
    output = {key: deepcopy(entry[key]) for key in
              ('reading_id', 'sha256', 'title', 'function', 'source_artifact_id', 'based_rev', 'job_id')
              if key in entry}
    if 'arguments' in entry:
        output['arguments_sha256'] = hashlib.sha256(encoded(entry['arguments'])).hexdigest()
    output['content_view'] = 'saved_view_index; inspect_artifact(reading_id) restores the exact arguments and result'
    return output


def apply_catalog_delivery(context):
    """Preserve all catalog identities, current claims, focus and exact readings."""
    output = dict(context)
    views = {(item.get('reading_id'), item.get('sha256')) for item in context['COMPLETED_VIEWS']}
    output['RELEVANT_EVIDENCE'] = [compact_artifact_catalog(item,
        item.get('kind') == 'tool_reading' and bool(item.get('sha256')) and
        (item.get('artifact_id'), item.get('sha256')) in views)
        for item in context['RELEVANT_EVIDENCE']]
    output['COMPLETED_VIEWS'] = [compact_view_catalog(item) for item in context['COMPLETED_VIEWS']]
    output['CATALOG_DELIVERY'] = {
        'policy': 'source_addresses_without_repeated_view_catalog_v2',
        'all_artifact_ids_preserved': True,
        'all_reading_ids_preserved': True,
        'originals': 'inspect_artifact reads source content/metadata (some raw provider fields have existing display adapters); use row/column tools for tables.',
        'meaning': 'This index does not establish reading, relevance, support, or opposition. '
                   'Inspect conditions and counterevidence needed for the actual question. '
                   'Current intent, hypotheses, notes and explicit reading pins are unchanged.'}
    return output
