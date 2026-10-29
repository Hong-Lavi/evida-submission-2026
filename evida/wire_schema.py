"""Responses strict wire shape; stored scientific contracts stay unchanged."""
import copy
import json


def provider_schema_projection(schema):
    """Omit provider-unsupported uniqueness syntax only on the wire.

    The original function/final schemas still reject duplicates before execution
    or publication. Never deduplicate values, edit enum/const data, or mutate the
    stored scientific contract. Existing $defs must receive the same projection.
    """
    result = copy.deepcopy(schema)

    def visit(node):
        if not isinstance(node, dict):
            return
        if 'uniqueItems' in node:
            if type(node['uniqueItems']) is not bool:
                raise ValueError('uniqueItems must be a boolean in the original schema')
            del node['uniqueItems']
        for key in ('properties', '$defs', 'definitions', 'patternProperties', 'dependentSchemas'):
            for child in node.get(key, {}).values():
                visit(child)
        for key in ('items', 'additionalProperties', 'contains', 'not', 'if', 'then', 'else',
                    'propertyNames', 'additionalItems', 'unevaluatedProperties', 'unevaluatedItems'):
            child = node.get(key)
            if isinstance(child, list):
                for item in child:
                    visit(item)
            else:
                visit(child)
        for key in ('anyOf', 'oneOf', 'allOf', 'prefixItems'):
            for child in node.get(key, []):
                visit(child)

    visit(result)
    return result


def strict_wire_schema(schema):
    """Factor exact repeated/deep subschemas; express one optional ID as required nullable.

    No enum values or descriptions are removed. Provider-unsupported uniqueItems
    is projected out only here; original local acceptance keeps that constraint.
    Missing optional qualification ID is required nullable on the wire only.
    """
    result = provider_schema_projection(schema)
    definitions = result.setdefault('$defs', {})
    by_value = {}

    def walk(node, *, root=False):
        if isinstance(node, list):
            return [walk(value) for value in node]
        if not isinstance(node, dict):
            return node
        node = {key: walk(value) for key, value in node.items()}
        if 'properties' in node:
            missing = set(node['properties']) - set(node.get('required', []))
            if missing:
                if missing != {'generation_contract_artifact_id'}:
                    raise ValueError('Unexpected optional strict-schema fields: ' + repr(sorted(missing)))
                value = node['properties']['generation_contract_artifact_id']
                # This field has no enum/ref in the current author contract.
                if value.get('type') not in ('string', ['string', 'null']):
                    raise ValueError('Qualification ID contract changed')
                node['properties']['generation_contract_artifact_id'] = {**value, 'type': ['string', 'null']}
                node['required'] = [*node.get('required', []), 'generation_contract_artifact_id']
        if not root and ('enum' in node or 'properties' in node or node.get('type') == 'array' or 'anyOf' in node):
            encoded = json.dumps(node, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            if encoded not in by_value:
                name = 'evida_schema_' + str(len(by_value))
                while name in definitions:
                    name += '_'
                by_value[encoded] = name
                definitions[name] = node
            return {'$ref': '#/$defs/' + by_value[encoded]}
        return node

    # Walk the source body, never the definitions we add while traversing it.
    result = walk({key: value for key, value in result.items() if key != '$defs'}, root=True)
    if definitions:
        result['$defs'] = definitions
    return result


def strict_wire_payload(payload):
    """Compile only strict Responses schemas; preserve internal logical payload."""
    wire = dict(payload)
    if 'tools' in payload:
        wire['tools'] = [
            {**tool, 'parameters': strict_wire_schema(tool['parameters'])}
            if tool.get('type') == 'function' and tool.get('strict') is True
            else tool
            for tool in payload['tools']
        ]
    text = payload.get('text', {})
    format_ = text.get('format', {})
    if format_.get('type') == 'json_schema' and format_.get('strict') is True:
        wire['text'] = {**text, 'format': {**format_, 'schema': strict_wire_schema(format_['schema'])}}
    return wire
