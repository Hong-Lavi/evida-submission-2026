"""Candidate: omit only schema-proven optional, empty conditional-alternative lists.
No dispatch, persistence, schema relaxation, unknown-field removal or science edits.
"""
import copy
import hashlib
import json
import jsonschema


def _hash(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


def normalize_final_body(body, schema):
    """Return independent canonical object + audit receipt; strict final validation.

    A narrowly allowlisted location, not a recursive 'delete empty arrays' rule.
    Optionality is proven by matching an extended variant to an existing variant
    that omits exactly this property, with every other contract unchanged.
    """
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)
    try:
        validator.validate(body)
    except jsonschema.ValidationError:
        before = 'FAIL'
    else:
        before = 'PASS'
    canonical = copy.deepcopy(body)
    item_schema = schema['properties']['decision']['properties']['research_loop']['properties']['hypotheses']['items']
    variants = item_schema.get('anyOf', [])
    key = 'conditional_alternatives'
    def permits_omission():
        for extended in variants:
            prop = extended.get('properties', {}).get(key)
            if not prop or prop.get('type') != 'array' or prop.get('minItems', 0) < 1:
                continue
            reduced = copy.deepcopy(extended)
            del reduced['properties'][key]
            reduced['required'] = [name for name in reduced.get('required', []) if name != key]
            if any(reduced == base and key not in base.get('properties', {}) for base in variants):
                return True
        return False
    operations = []
    hypotheses = canonical.get('decision', {}).get('research_loop', {}).get('hypotheses', []) if isinstance(canonical, dict) else []
    if permits_omission() and isinstance(hypotheses, list):
        for index, hypothesis in enumerate(hypotheses):
            if isinstance(hypothesis, dict) and key in hypothesis and hypothesis[key] == []:
                del hypothesis[key]
                operations.append({'op':'remove', 'path':f'/decision/research_loop/hypotheses/{index}/{key}', 'original_value':[], 'reason':'Schema has an otherwise identical variant omitting this optional extension.'})
    # No result is returned for malformed nonempty, required, or unknown members.
    validator.validate(canonical)
    restored = copy.deepcopy(canonical)
    for operation in operations:
        index = int(operation['path'].split('/')[4])
        restored['decision']['research_loop']['hypotheses'][index][key] = []
    assert restored == body
    return canonical, {'status':'STRICT_SCHEMA_PASS', 'schema_before':before, 'schema_after':'PASS', 'operations':operations, 'original_object_sha256':_hash(body), 'canonical_object_sha256':_hash(canonical), 'schema_sha256':_hash(schema), 'reinserting_empty_fields_restores_original':True, 'scientific_acceptance':'NOT_ASSESSED', 'hold_or_dispatch_change':False}
