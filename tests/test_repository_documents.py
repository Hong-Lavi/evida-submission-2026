import base64
import hashlib
import io
import json
import unittest
import zipfile
from unittest.mock import patch

from evida.repository_documents import docx_blocks, read_repository_document


def document():
    stream = io.BytesIO()
    xml = b'''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
    <w:p><w:r><w:t>Original statement</w:t></w:r></w:p>
    <w:p><w:r><w:drawing/></w:r></w:p>
    <w:tbl><w:tr><w:tc><w:p><w:r><w:t>0</w:t></w:r></w:p></w:tc><w:tc><w:p/></w:tc></w:tr></w:tbl>
    </w:body></w:document>'''
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('word/document.xml', xml)
    return stream.getvalue()


class RepositoryDocuments(unittest.TestCase):
    def test_preserves_original_document_tables_and_image_locations(self):
        raw = document()
        record = {'id': 123, 'metadata': {'title': 'Fixture', 'license': {'id': 'cc-by-4.0'}},
                  'files': [{'key': 'guide.docx', 'size': len(raw), 'checksum': 'md5:' + hashlib.md5(raw).hexdigest()}]}
        with patch('evida.repository_documents.fetch', side_effect=[(json.dumps(record).encode(), {'url': 'record'}), (raw, {'url': 'file'})]):
            result = read_repository_document({'record_id': '123', 'filename': 'guide.docx'})
        self.assertEqual(base64.b64decode(result['original_docx_base64']), raw)
        self.assertEqual(result['rows'][2]['table_cells'], [['0', '']])
        self.assertTrue(result['rows'][1]['requires_original_review'])
        self.assertTrue(result['rows'][2]['requires_original_review'])
        self.assertEqual(result['permissions'], {'id': 'cc-by-4.0'})

    def test_listing_does_not_fetch_files_and_absent_license_stays_unknown(self):
        record = {'id': 123, 'metadata': {}, 'files': [{'key': 'plot.pdf', 'size': 2}]}
        with patch('evida.repository_documents.fetch', return_value=(json.dumps(record).encode(), {})) as fetch:
            result = read_repository_document({'record_id': '123', 'filename': ''})
        self.assertEqual(fetch.call_count, 1)
        self.assertIsNone(result['permissions'])
        self.assertTrue(result['rows'][0]['readable_here'])

    def test_wrong_identity_and_checksum_are_failures(self):
        with patch('evida.repository_documents.fetch', return_value=(b'{"id":124}', {})):
            with self.assertRaises(ValueError): read_repository_document({'record_id': '123', 'filename': ''})
        record = {'id': 123, 'files': [{'key': 'guide.docx', 'checksum': 'md5:bad'}]}
        with patch('evida.repository_documents.fetch', side_effect=[(json.dumps(record).encode(), {}), (document(), {})]):
            with self.assertRaises(ValueError): read_repository_document({'record_id': '123', 'filename': 'guide.docx'})


if __name__ == '__main__':
    unittest.main()
