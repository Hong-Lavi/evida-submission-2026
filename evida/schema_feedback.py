"""Bounded structural feedback from an existing rejection; never repair its input.

Instance values and jsonschema's object/schema repr are deliberately excluded.
Alternatives keep their branch boundaries: fixing every branch is not required.
"""
import json
import re
from itertools import islice

MAX_SCHEMA_FEEDBACK_CHARS = 2400


def _pointer(parts):
    return ''.join('/' + str(p).replace('~', '~0').replace('/', '~1') for p in parts)


def _type(value):
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'boolean'
    if isinstance(value, dict):
        return 'object'
    if isinstance(value, list):
        return 'array'
    if isinstance(value, str):
        return 'string'
    if isinstance(value, int):
        return 'integer'
    if isinstance(value, float):
        return 'number'
    return 'non_json'


def _branch_priority(schema, instance):
    """Prefer matching literal tags for diagnostics only; never accept a branch."""
    if not isinstance(schema, dict) or not isinstance(instance, dict):
        return (0, 0)
    matches = mismatches = 0
    for name, field in schema.get('properties', {}).items():
        if name not in instance or not isinstance(field, dict):
            continue
        for keyword in ('const', 'enum'):
            if keyword not in field:
                continue
            values = [field[keyword]] if keyword == 'const' else field[keyword]
            matched = any(type(instance[name]) is type(v) and instance[name] == v for v in values)
            matches += int(matched)
            mismatches += int(not matched)
    return (mismatches, -matches)


def _node(error, width, depth=0):
    result = {'pointer': _pointer(error.absolute_path), 'validator': error.validator,
              'schema_pointer': _pointer(error.absolute_schema_path)}
    keyword = error.validator
    if keyword in ('anyOf', 'oneOf'):
        result['alternatives_rule'] = ('at_least_one_branch' if keyword == 'anyOf'
                                       else 'exactly_one_branch')
        result['branch_errors_are_not_combined_requirements'] = True
        if not error.context:
            # oneOf also rejects when multiple alternatives pass. An empty
            # context must not become a made-up list of missing requirements.
            result['detail'] = 'Consult the schema alternatives; no child rejection details.'
        elif depth >= 3:
            result['details_omitted'] = True
        else:
            groups = {}
            for child in error.context:
                branch = next(iter(child.schema_path), None)
                groups.setdefault(branch, []).append(child)
            variants = error.schema.get(keyword, [])
            ordered = sorted(groups.items(), key=lambda pair: _branch_priority(
                variants[pair[0]] if isinstance(pair[0], int) and 0 <= pair[0] < len(variants) else {},
                error.instance))
            result['branches'] = []
            for branch, children in islice(ordered, width):
                errors = []
                for child in children[:width]:
                    diagnostic = _node(child, width, depth + 1)
                    # jsonschema emits one required error per missing key;
                    # each diagnostic already lists that object's missing keys.
                    if diagnostic not in errors:
                        errors.append(diagnostic)
                result['branches'].append({
                    'branch_index': branch,
                    'errors': errors,
                    'details_omitted': len(children) > width,
                })
            if len(groups) > width:
                result['details_omitted'] = True
            if [b for b, _ in ordered] != list(groups):
                result['diagnostic_order'] = 'matching_literal_tags_first_not_branch_acceptance'
    elif keyword == 'required' and isinstance(error.instance, dict):
        required = error.validator_value
        missing = [name for name in required if name not in error.instance]
        result['missing_required'] = missing[:width]
        if len(missing) > width:
            result['details_omitted'] = True
    elif keyword == 'type':
        result['expected_type'] = error.validator_value
        result['actual_type'] = _type(error.instance)
    elif keyword == 'additionalProperties' and error.validator_value is False and isinstance(error.instance, dict):
        properties = error.schema.get('properties', {})
        patterns = error.schema.get('patternProperties', {})
        unexpected = [name for name in error.instance if name not in properties
                      and not any(re.search(pattern, name) for pattern in patterns)]
        result['unexpected_properties'] = unexpected[:width]
        if len(unexpected) > width:
            result['details_omitted'] = True
    elif keyword in ('enum', 'const'):
        values = error.validator_value if keyword == 'enum' else [error.validator_value]
        result['allowed_values'] = values[:width]
        if len(values) > width:
            result['details_omitted'] = True
    elif keyword in ('minItems', 'maxItems', 'minLength', 'maxLength', 'minimum',
                     'maximum', 'exclusiveMinimum', 'exclusiveMaximum'):
        result['constraint'] = error.validator_value
    return result


def schema_feedback(error):
    """Return valid JSON within the total character budget, with exact pointers.

Only the already-raised error and its contextual alternatives are summarized;
this is not an exhaustive validation report. Long paths are omitted explicitly,
never shortened into a pointer that would identify a different field.
"""
    def encode(diagnostic):
        return json.dumps({'kind': 'schema_validation', 'scope': 'raised_error_only',
                           'diagnostic': diagnostic}, ensure_ascii=False,
                          separators=(',', ':'))

    for width in (4, 2, 1):
        diagnostic = _node(error, width)
        text = encode(diagnostic)
        if len(text) <= MAX_SCHEMA_FEEDBACK_CHARS:
            return text
    # Unusually long property names or allowed values still cannot crowd out
    # the structural location. The full original error is stored separately.
    diagnostic = {'pointer': _pointer(error.absolute_path), 'validator': error.validator,
                  'details_omitted': True}
    if error.validator in ('anyOf', 'oneOf'):
        diagnostic['alternatives_rule'] = ('at_least_one_branch' if error.validator == 'anyOf'
                                           else 'exactly_one_branch')
    text = encode(diagnostic)
    if len(text) > MAX_SCHEMA_FEEDBACK_CHARS:
        diagnostic.pop('pointer')
        diagnostic['pointer_omitted_due_to_budget'] = True
        text = encode(diagnostic)
    return text
