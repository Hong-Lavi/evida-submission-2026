"""Read public repository documentation without treating it as executable guidance."""
import base64
import hashlib
import io
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile

from .science import MAX_DOWNLOAD, fetch
from .source_formats import pdf_pages, xlsx_rows

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def docx_blocks(raw, source_url):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        info = archive.getinfo('word/document.xml')
        if info.file_size > MAX_DOWNLOAD:
            raise ValueError('문서 XML이 현재 처리 범위보다 큽니다. 원문 확인이 필요합니다.')
        xml = archive.read(info)
    if b'<!ENTITY' in xml.upper():
        raise ValueError('문서 엔터티 정의는 처리하지 않습니다. 원문 확인이 필요합니다.')
    root = ET.fromstring(xml)
    body = root.find(W + 'body')
    if body is None:
        raise ValueError('DOCX 본문을 확인할 수 없습니다.')

    def text(node):
        return ''.join(n.text or '' for n in node.iter(W + 't'))

    rows = []
    for index, node in enumerate(body):
        kind = node.tag.rsplit('}', 1)[-1]
        if kind == 'sectPr':
            continue
        graphical = any(n.tag.rsplit('}', 1)[-1] in ('drawing', 'pict', 'oMath', 'oMathPara') for n in node.iter())
        item = {'row_id': f'docx:block:{index}', 'kind': kind, 'text': text(node),
                'source_url': source_url, 'original_block_index': index,
                'requires_original_review': graphical or kind != 'p'}
        if kind == 'tbl':
            item['table_cells'] = [[text(cell) for cell in row.findall(W + 'tc')] for row in node.findall(W + 'tr')]
        if item['text'] or graphical or kind != 'p':
            rows.append(item)
    return rows


def read_repository_document(arguments):
    record_id, filename = arguments['record_id'], arguments['filename']
    if not re.fullmatch(r'[0-9]+', record_id):
        raise ValueError('확인한 Zenodo 레코드 번호가 필요합니다.')
    if len(filename) > 300 or any(c in filename for c in ('/', '\\', '\x00')):
        raise ValueError('레코드에 표시된 파일 이름이 필요합니다.')
    raw_record, receipt = fetch(f'https://zenodo.org/api/records/{record_id}')
    record = json.loads(raw_record)
    if str(record.get('id')) != record_id:
        raise ValueError('반환된 레코드 번호가 요청과 다릅니다.')
    metadata = record.get('metadata') or {}
    files = [{'filename': f['key'], 'bytes': f.get('size'), 'checksum': f.get('checksum'),
              'readable_here': f['key'].lower().endswith(('.docx', '.pdf', '.xlsx'))} for f in record.get('files', [])]
    result = {'status': 'succeeded', 'semantic_type': 'repository_documentation', 'source': receipt,
              'record_id': record_id, 'title': metadata.get('title'), 'doi': metadata.get('doi'),
              'permissions': metadata.get('license'), 'metadata_response': record,
              'files': files, 'filename': filename,
              'limits': ['원 저자의 자료 설명입니다. 관측의 독립 검증이나 보편적인 판정 기준이 아닙니다.',
                         '권리 정보와 원문을 보존합니다. 원본의 그림·수식·표 배치는 별도로 확인해야 합니다.']}
    if not filename:
        result.update(rows=files, summary={'files': len(files), 'document_loaded': False})
        return result
    entry = next((f for f in files if f['filename'] == filename), None)
    if entry is None or not entry['readable_here']:
        raise ValueError('이 레코드의 DOCX·PDF·XLSX 파일을 지정해 주세요. 다른 형식은 원문에서 확인할 수 있습니다.')
    url = f'https://zenodo.org/api/records/{record_id}/files/{urllib.parse.quote(filename, safe="")}/content'
    raw, file_receipt = fetch(url)
    checksum = entry['checksum']
    if checksum:
        algorithm, expected = checksum.split(':', 1)
        if algorithm not in ('md5', 'sha256') or hashlib.new(algorithm, raw).hexdigest() != expected:
            raise ValueError('다운로드 파일이 레코드의 체크섬과 일치하지 않습니다.')
    suffix = filename.rsplit('.', 1)[-1].lower()
    details, versions = {}, {}
    if suffix == 'pdf':
        rows, details, versions = pdf_pages(raw, url)
        result['limits'].append('PDF는 페이지별 문자층이며 OCR·그림 판독은 하지 않았습니다. 패널·후보·측정의 대응은 추출 순서만으로 확정하지 마세요. 문자층이 비어도 근거가 없다는 뜻은 아닙니다.')
    elif suffix == 'xlsx':
        rows, details, versions = xlsx_rows(raw, url)
        result['limits'].append('엑셀 값·좌표·자료형·병합/숨김 정보를 보존했습니다. 수식을 실행하거나 빈 셀을 0으로 바꾸지 않았습니다. 그림·차트·삽입 개체의 존재를 기록하되 내용을 판독하지 않았습니다. 헤더의 과학적 의미와 후보 대응은 별도 해석이 필요합니다.')
    else:
        rows = docx_blocks(raw, url)
        result['original_docx_base64'] = base64.b64encode(raw).decode('ascii')
    result.update(source=file_receipt, metadata_source=receipt, rows=rows,
                  document_format=suffix, versions=versions,
                  original_file_base64=base64.b64encode(raw).decode('ascii'),
                  original_sha256=hashlib.sha256(raw).hexdigest(),
                  summary={'blocks': len(rows), 'document_loaded': True, 'document_format': suffix,
                           'original_review_blocks': sum(r['requires_original_review'] for r in rows), **details})
    return result
