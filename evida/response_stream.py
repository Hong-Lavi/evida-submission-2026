"""SSE terminal-response contract reused from the actual RNA65 transport repair."""
import json


class StreamProviderError(ValueError):
    """Public provider diagnostic, distinct from a broken/truncated transport."""
    def __init__(self, error, response=None):
        self.code = str(error.get('code') or 'provider_stream_error')[:100]
        self.error_type = str(error.get('type') or 'unknown')[:100]
        self.response = response
        super().__init__('Provider returned a structured stream error.')


def read_response_stream(response, raw, maximum_bytes=16 * 1024 * 1024):
    """Require the full terminal response, not a completed-looking text delta."""
    data, terminal, event_types = [], None, {}
    while True:
        line = response.readline(maximum_bytes - len(raw) + 1)
        if not line:
            break
        raw.extend(line)
        if len(raw) > maximum_bytes:
            raise ValueError('Stream exceeded safe recording bounds.')
        framed = line.rstrip(b'\r\n')
        if framed.startswith(b'data:'):
            value = framed[5:]
            data.append(value[1:] if value.startswith(b' ') else value)
        elif not framed and data:
            encoded = b'\n'.join(data)
            data = []
            if encoded == b'[DONE]':
                continue
            event = json.loads(encoded)
            if not isinstance(event, dict):
                raise ValueError('Invalid stream event object.')
            kind = event.get('type', 'unknown')
            event_types[kind] = event_types.get(kind, 0) + 1
            if kind in {'response.completed', 'response.incomplete', 'response.failed'}:
                if terminal is not None or not isinstance(event.get('response'), dict):
                    raise ValueError('Ambiguous terminal stream response.')
                terminal = event['response']
                if terminal.get('status') != kind.removeprefix('response.'):
                    raise ValueError('Conflicting stream terminal status.')
            elif kind == 'error':
                error = event.get('error', event)
                raise StreamProviderError(error if isinstance(error, dict) else {}, terminal)
    if data or terminal is None:
        raise ValueError('Stream ended without a complete terminal response.')
    return terminal, event_types
