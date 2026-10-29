import base64
import json
import unittest
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs
from evida.science import literature

class LiteratureCursorContractTests(unittest.TestCase):
    def invoke(self, arguments):
        raw = b'{"hitCount":33,"nextCursorMark":"opaque+/= value","resultList":{"result":[{"id":"37479139","title":"ENVISION"}]}}'
        with patch('evida.science.fetch', return_value=(raw, {'url':'preserved'})) as fetch:
            result = literature(arguments)
        params = parse_qs(urlparse(fetch.call_args.args[0]).query, keep_blank_values=True)
        self.assertEqual(base64.b64decode(result['original_response_base64']), raw)
        self.assertEqual(result['summary']['next_cursor'], 'opaque+/= value')
        self.assertEqual(result['rows'], json.loads(raw)['resultList']['result'])
        return params

    def test_ui_empty_cursor_requests_first_page(self):
        params = self.invoke({'query':'givosiran ENVISION','cursor':''})
        self.assertEqual(params['cursorMark'], ['*'])

    def test_omitted_cursor_requests_first_page(self):
        params = self.invoke({'query':'givosiran ENVISION'})
        self.assertEqual(params['cursorMark'], ['*'])

    def test_provider_cursor_is_preserved_without_stripping_or_reconstruction(self):
        cursor = 'opaque+/= value'
        params = self.invoke({'query':'givosiran ENVISION','cursor':cursor})
        self.assertEqual(params['cursorMark'], [cursor])

if __name__ == '__main__':
    unittest.main()
