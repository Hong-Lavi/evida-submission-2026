"""Guard the production request boundary without making provider calls."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError

import jsonschema
from evida.contracts import model_final_decision, model_functions
from evida.gateway import Gateway, GatewayError
from evida.wire_schema import strict_wire_schema

POLICY = json.loads((Path(__file__).resolve().parents[1] / 'configs/api_policy.json').read_text())


def expanded(value, root):
    if isinstance(value, list):
        return [expanded(v, root) for v in value]
    if not isinstance(value, dict):
        return value
    if '$ref' in value:
        return expanded(root['$defs'][value['$ref'].split('/')[-1]], root)
    return {k: expanded(v, root) for k, v in value.items() if k != '$defs'}


def required_optional_id(value):
    if isinstance(value, list):
        return [required_optional_id(v) for v in value]
    if not isinstance(value, dict):
        return value
    result = {k: required_optional_id(v) for k, v in value.items()
              if not (k == 'uniqueItems' and type(v) is bool)}
    missing = set(result.get('properties', {})) - set(result.get('required', []))
    if missing:
        assert missing == {'generation_contract_artifact_id'}
        result['required'] += ['generation_contract_artifact_id']
    return result


class WireSchemaTests(unittest.TestCase):
    def test_every_tool_and_final_preserves_constraints_and_fits_static_limits(self):
        for cards in (False, True):
            schemas = [model_final_decision(reasoning_core=cards)] + [
                f['parameters'] for f in model_functions(reasoning_core=cards)]
            for schema in schemas:
                before = copy.deepcopy(schema)
                wire = strict_wire_schema(schema)
                self.assertEqual(schema, before)
                self.assertEqual(expanded(wire, wire), required_optional_id(before))
                jsonschema.Draft202012Validator.check_schema(wire)
                enums = 0
                pending = [wire]
                while pending:
                    node = pending.pop()
                    if isinstance(node, list):
                        pending.extend(node)
                    elif isinstance(node, dict):
                        enums += len(node.get('enum', []))
                        if 'properties' in node:
                            self.assertEqual(set(node['properties']), set(node['required']))
                        pending.extend(node.values())
                self.assertLessEqual(enums, 1000)

    def test_forced_frame_omits_final_only_on_wire_and_records_exact_request(self):
        seen = []
        def answer(body):
            seen.append(body)
            return {'model': 'gpt-6-sol', 'status': 'completed', 'output': []}, {}
        payload = {'input': [{'role': 'user', 'content': 'synthetic fixture'}],
            'tools': [f for f in model_functions() if f['name'] == 'frame_work'],
            'tool_choice': {'type': 'function', 'name': 'frame_work'},
            'text': {'format': {'type': 'json_schema', 'name': 'fixture',
                'strict': True, 'schema': model_final_decision()}}}
        original = copy.deepcopy(payload)
        with tempfile.TemporaryDirectory() as directory:
            gateway = Gateway(POLICY, enabled=True, model='gpt-6-sol',
                transport=answer, requests_dir=directory)
            _, receipt = gateway.request(payload)
            self.assertEqual(payload, original)
            self.assertNotIn('text', seen[0])
            self.assertIn('text', payload)  # CLI logical-input contract is intact.
            raw = (Path(directory) / receipt['request_record'] / 'request.json').read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), receipt['request_sha256'])
            self.assertEqual(json.loads(raw), seen[0])
            payload['tool_choice'] = 'none'
            gateway.request(payload)
            self.assertIn('text', seen[-1])
            self.assertIn('$defs', seen[-1]['text']['format']['schema'])

    def test_http_error_keeps_only_machine_metadata_and_never_secret_or_text(self):
        sentinel = 'synthetic-test-credential-not-a-real-key'
        def failed(body):
            error = {'code': 'invalid_json_schema', 'type': 'invalid_request_error',
                'param': 'text.format.schema', 'message': 'provider free text is not retained'}
            if include_secret:
                error['message'] = sentinel
            raise HTTPError('https://example.invalid', 400, 'Bad Request', {},
                io.BytesIO(json.dumps({'error': error}).encode()))
        gateway = Gateway(POLICY, enabled=True, model='gpt-6-sol', transport=failed)
        gateway.set_credential(sentinel)
        for include_secret in (False, True):
            with self.assertRaises(GatewayError) as caught:
                gateway.request({'input': []})
            receipt = caught.exception.receipt
            self.assertEqual(receipt['http_status'], 400)
            self.assertNotIn(sentinel, json.dumps(receipt))
            self.assertNotIn('provider free text', json.dumps(receipt))
            self.assertEqual('provider_error' in receipt, not include_secret)


if __name__ == '__main__':
    unittest.main()
