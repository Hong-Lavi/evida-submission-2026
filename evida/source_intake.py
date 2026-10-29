"""Preserved researcher files and literal text extraction, without interpretation."""
from __future__ import annotations

import codecs
import hashlib
import io
import logging
import re

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 200
MAX_ROWS = 20000
MAX_CHARACTERS = 4 * 1024 * 1024
WALL_SECONDS = 45
CPU_SECONDS = 30
MEMORY_BYTES = 768 * 1024 * 1024
SEMANTIC_TYPE = 'researcher_uploaded_source_document'


def upload_metadata(content, title, supplied):
    if len(content) > MAX_BYTES:
        raise ValueError('파일은 10 MiB 이내로 올려 주세요.')
    filename = str(supplied.get('original_filename') or title).replace('\\', '/').rsplit('/', 1)[-1][:180]
    if not filename or any(ord(c) < 32 for c in filename):
        raise ValueError('문서 파일 이름을 확인해 주세요.')
    format_ = supplied.get('document_format')
    if format_ is None:
        format_ = 'pdf' if filename.lower().endswith('.pdf') else 'text' if filename.lower().endswith('.txt') else None
    if format_ not in ('text', 'pdf'):
        raise ValueError('문서는 UTF-8 TXT 또는 문자층 PDF 형식을 선택해 주세요.')
    declarations = {}
    for key in ('context', 'citation'):
        value = supplied.get(key, '')
        if not isinstance(value, str) or len(value) > 20000:
            raise ValueError('문서의 대상·조건·출처는 20,000자 이내 텍스트로 적어 주세요.')
        declarations[key] = value
    return {'original_filename': filename, 'document_format': format_,
            'source_mode': 'researcher_upload', 'origin': 'researcher_upload',
            'scientific_context_verified': False, 'bibliographic_identity_verified': False,
            'supplied_metadata': declarations}


def text_rows(raw):
    """UTF-8 paragraphs refer to untouched byte spans, including CR/LF endings."""
    bom = raw.startswith(codecs.BOM_UTF8)
    start = len(codecs.BOM_UTF8) if bom else 0
    text = raw[start:].decode('utf-8', errors='strict')
    if '\x00' in text:
        raise ValueError('NUL 문자가 있는 파일은 UTF-8 문서로 읽지 않습니다. 원본을 확인해 주세요.')
    if len(text) > MAX_CHARACTERS:
        raise ValueError('문서 문자층이 추출 범위(4 Mi 문자)를 넘습니다. 원본은 보존됩니다.')
    rows, lines = [], []
    # Only physical CR/LF delimit lines; scientific Unicode separators remain literal.
    for match in re.finditer(rb'[^\r\n]*(?:\r\n|\r|\n|$)', raw[start:]):
        if not match.group():
            continue
        lines.append((start + match.start(), start + match.end()))
    paragraph = None
    def append(first, last):
        a, b = lines[first][0], lines[last][1]
        rows.append({'row_id': f'text:paragraph:{len(rows) + 1}', 'kind': 'text_paragraph',
                     'paragraph_number': len(rows) + 1, 'text': raw[a:b].decode('utf-8'),
                     'byte_start': a, 'byte_end': b, 'line_start': first + 1, 'line_end': last + 1,
                     'requires_original_review': False})
        if len(rows) > MAX_ROWS:
            raise ValueError('문단 수가 추출 범위(20,000개)를 넘습니다. 원본은 보존됩니다.')
    for i, (a, b) in enumerate(lines):
        if raw[a:b].decode('utf-8').strip():
            if paragraph is None:
                paragraph = i
        elif paragraph is not None:
            append(paragraph, i - 1)
            paragraph = None
    if paragraph is not None:
        append(paragraph, len(lines) - 1)
    return rows, {'encoding': 'utf-8', 'bom_present': bom, 'physical_lines': len(lines),
                  'paragraphs': len(rows), 'characters': len(text),
                  'line_endings': {'crlf': raw.count(b'\r\n'), 'lf': raw.count(b'\n') - raw.count(b'\r\n'),
                                   'cr': raw.count(b'\r') - raw.count(b'\r\n')},
                  'byte_span_convention': 'zero-based, end-exclusive, original bytes; BOM and blank separators remain in original'}, {}


class WarningCapture(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.messages = []
        self.total = 0

    def emit(self, record):
        self.total += 1
        if len(self.messages) < 100:
            self.messages.append(record.getMessage()[:1000])


def pdf_rows(raw):
    from pypdf import PdfReader
    from .source_formats import pdf_pages
    reader = PdfReader(io.BytesIO(raw))
    if reader.is_encrypted:
        raise ValueError('암호화 PDF의 문자층은 추출하지 않습니다. 보존한 원본을 확인해 주세요.')
    if len(reader.pages) > MAX_PAGES:
        raise ValueError('PDF 추출은 200쪽까지 지원합니다. 전체 원본은 보존됩니다.')
    rows, details, versions = pdf_pages(raw, '')
    for row in rows:
        # A local upload has no authenticated publisher URL; UI uses the bound original.
        row.pop('source_url', None)
    if sum(len(row['text']) for row in rows) > MAX_CHARACTERS:
        raise ValueError('PDF 문자층이 추출 범위(4 Mi 문자)를 넘습니다. 원본은 보존됩니다.')
    return rows, details, versions


def extract(raw, source_id, source_sha256, metadata):
    """Always retain a typed extraction result for parse errors and empty text."""
    result = {'status': 'failed', 'semantic_type': SEMANTIC_TYPE, 'origin': 'researcher_upload',
              'source_artifact_id': source_id, 'source_sha256': source_sha256,
              'filename': metadata['original_filename'], 'title': metadata['original_filename'],
              'document_format': metadata['document_format'],
              'supplied_metadata': metadata.get('supplied_metadata', {}),
              'scientific_context_verified': False, 'bibliographic_identity_verified': False,
              'rows': [], 'summary': {'blocks': 0, 'text_characters': 0},
              'extraction': {'status': 'failed', 'ocr_performed': False, 'warnings': [], 'warning_count': 0,
                             'limits': {'bytes': MAX_BYTES, 'pages': MAX_PAGES, 'rows': MAX_ROWS,
                                        'characters': MAX_CHARACTERS, 'cpu_seconds': CPU_SECONDS,
                                        'wall_seconds': WALL_SECONDS, 'memory_bytes': MEMORY_BYTES}},
              'versions': {}, 'limits': ['연구자가 제공한 문서의 문자층입니다. 출처 신원·주장·과학적 의미를 검증한 결과가 아닙니다.',
                  '업로드·추출과 실제로 읽은 범위는 다릅니다. 선택한 문단·페이지를 원본과 함께 확인하세요.']}
    capture = WarningCapture()
    logger = logging.getLogger('pypdf')
    logger.addHandler(capture)
    try:
        if hashlib.sha256(raw).hexdigest() != source_sha256:
            raise ValueError('추출 입력이 보존한 원본 해시와 다릅니다.')
        if len(raw) > MAX_BYTES:
            raise ValueError('원본이 추출 크기 범위(10 MiB)를 넘습니다.')
        if metadata['document_format'] == 'text':
            rows, details, versions = text_rows(raw)
            result['extraction']['method'] = 'strict_utf8_literal_paragraphs'
        elif metadata['document_format'] == 'pdf':
            rows, details, versions = pdf_rows(raw)
            result['extraction']['method'] = 'pypdf_layout_text_physical_pages'
            result['limits'].append('PDF는 문자층만 추출했습니다. OCR·그림·표 구조 판독은 하지 않았으며, 회전 문자·배치·패널 대응은 원본 확인이 필요합니다.')
        else:
            raise ValueError('지원하지 않는 문서 형식입니다.')
        characters = sum(len(r['text']) for r in rows)
        any_text = any(r['text'].strip() for r in rows)
        partial = bool(capture.total or details.get('empty_text_pages'))
        extraction_status = 'no_text' if not any_text else 'partial_text' if partial else 'text_extracted'
        result.update(status='succeeded' if extraction_status == 'text_extracted' else 'partial', rows=rows,
                      versions=versions, summary={'blocks': len(rows), 'text_characters': characters, **details})
        result['extraction']['status'] = extraction_status
        if not any_text:
            result['limits'].insert(0, '읽을 수 있는 문자층이 없습니다. 근거가 없다는 뜻이 아니며 보존한 원본을 확인해 주세요.')
        elif partial:
            result['limits'].insert(0, '일부 문자층 추출에 한계가 있습니다. 빈 페이지와 추출 경고를 원본에서 확인해 주세요.')
    except Exception as exc:
        result.update(error_type=type(exc).__name__, error=str(exc)[:1000])
        result['limits'].insert(0, '문자층 추출을 완료하지 못했습니다. 원본 파일은 그대로 보존되어 있습니다.')
    finally:
        logger.removeHandler(capture)
        result['extraction'].update(warnings=capture.messages, warning_count=capture.total,
                                    warnings_truncated=capture.total > len(capture.messages))
    return result


def worker(request, raw):
    # This worker has its own process; these limits never affect the web server.
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    return extract(raw, request['arguments']['artifact_id'], request['source_sha256'], request['input_meta'])


def original(store, wid, artifact_id):
    artifact = store.artifact(wid, artifact_id)
    if artifact['kind'] == 'source_document':
        import json
        value = json.loads(artifact['content'])
        source = store.artifact(wid, value['source_artifact_id'])
        if source['sha256'] != value['source_sha256']:
            raise ValueError('문서 추출본과 원본의 해시 결속이 다릅니다.')
        artifact = source
    if artifact['kind'] != 'source_file':
        raise ValueError('연구자가 제공한 원본 문서를 선택해 주세요.')
    return artifact
