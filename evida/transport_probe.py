"""Two small live transport checks, not a product/scientific quality evaluation."""
import json
from datetime import datetime, timezone
from pathlib import Path

from .contracts import obj, TEXT, function
from .gateway import Gateway, GatewayError
from .store import dump


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / 'audit' / ('terra-transport-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    output.mkdir(parents=True, exist_ok=False)
    gateway = Gateway(json.loads((root/'configs/api_policy.json').read_text()), enabled=True,
                      model='gpt-5.6-terra', effort='high', max_output_tokens=1500)
    record = {'purpose': 'connection_function_and_strict_json_only', 'requested_model': gateway.model,
              'requested_effort': gateway.effort, 'calls': [], 'scientific_validation': False,
              'automatic_retry': False, 'status': 'started'}
    def save():
        (output/'receipt.json').write_text(dump(record)+'\n')
    try:
        start = [{'role': 'user', 'content': 'Connection test only. Call echo once with text OK. No research.'}]
        tools = [function('echo', 'Return the provided text unchanged.', obj({'text': TEXT}))]
        first, receipt = gateway.request({'input': start, 'tools': tools,
            'tool_choice': {'type': 'function', 'name': 'echo'}, 'parallel_tool_calls': False})
        record['calls'].append(receipt); save()
        calls = [c for c in first['output'] if c['type'] == 'function_call']
        if len(calls) != 1 or calls[0]['name'] != 'echo' or json.loads(calls[0]['arguments']) != {'text': 'OK'}:
            raise ValueError('Unexpected connection function response')
        c = calls[0]
        second, receipt = gateway.request({'input': start + first['output'] +
            [{'type': 'function_call_output', 'call_id': c['call_id'], 'output': 'OK'}],
            'instructions': 'Connection test only. Return JSON status OK.', 'tools': tools,
            'tool_choice': 'none', 'text': {'format': {'type': 'json_schema', 'name': 'connection_result',
            'strict': True, 'schema': obj({'status': {'type': 'string', 'enum': ['OK']}})}}})
        record['calls'].append(receipt); save()
        texts = [part['text'] for item in second['output'] for part in item.get('content', []) if part['type'] == 'output_text']
        if len(texts) != 1 or json.loads(texts[0]) != {'status': 'OK'}:
            raise ValueError('Unexpected strict JSON response')
        record['status'] = 'passed'
    except (GatewayError, ValueError, KeyError) as exc:
        record['status'] = 'failed'; record['error_type'] = type(exc).__name__
        if isinstance(exc, GatewayError) and exc.receipt:
            record['calls'].append(exc.receipt)
    finally:
        record['known_tokens'] = sum((c.get('usage') or {}).get('total_tokens', 0) for c in record['calls'])
        save()
    print(dump({'status': record['status'], 'calls': len(record['calls']), 'known_tokens': record['known_tokens'],
                'receipt': str(output/'receipt.json')}))
    if record['status'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
