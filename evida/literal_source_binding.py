"""Locations and original-byte bindings for literal uploaded/web text rows.

Not a second scientific anchor system: callers retain their existing quotation
checks. This supplies the only eligible text and a reproducible source receipt.
"""
import base64
import copy
import hashlib
import json

LITERAL_KINDS = frozenset({'source_document', 'webpage', 'public_research_page'})


def row_binding(store, wid, artifact, value, index):
    rows = value.get('rows', [])
    if type(index) is not int or index < 0 or index >= len(rows):
        raise ValueError('보존 본문의 행 범위를 확인해 주세요.')
    row = rows[index]
    if not isinstance(row, dict) or not isinstance(row.get('text'), str):
        raise ValueError('보존 본문의 문자층 행이 없습니다.')
    binding = {'source_kind': artifact['kind'], 'artifact_id': artifact['id'],
               'artifact_sha256': artifact['sha256'], 'row_index': index, 'row_id': row.get('row_id'),
               'text_locator': '/rows/' + str(index) + '/text', 'location': {},
               'scientific_validation': False}
    if artifact['kind'] == 'source_document':
        from .source_intake import original, text_rows
        raw = original(store, wid, artifact['id'])
        binding.update(origin='researcher_upload', filename=value.get('filename'), original={'artifact_id': raw['id'], 'sha256': raw['sha256']},
                       supplied_metadata=copy.deepcopy(value.get('supplied_metadata', {})),
                       bibliographic_identity_verified=False,
                       extraction={'document_format': value.get('document_format'),
                                   'details': copy.deepcopy(value.get('extraction', {})),
                                   'limits': copy.deepcopy(value.get('limits', []))})
        if value.get('document_format') == 'text':
            expected_rows, _, _ = text_rows(raw['content'])
            if index >= len(expected_rows):
                raise ValueError('원본에 없는 문단입니다.')
            keys = ('row_id','text','paragraph_number','byte_start','byte_end','line_start','line_end')
            if any(row.get(k) != expected_rows[index][k] for k in keys):
                raise ValueError('본문 문단·byte 범위가 보존 원본과 다릅니다.')
            binding['location'] = {k: row[k] for k in keys if k not in ('row_id','text')}
        elif value.get('document_format') == 'pdf':
            # Intake already performed bounded PDF extraction in its isolated worker.
            # Do not reparse untrusted PDF bytes in the coordinator for each citation.
            pages = value.get('summary', {}).get('pages')
            if (type(pages) is not int or pages != len(rows) or not 0 <= index < pages
                    or row.get('kind') != 'pdf_page' or row.get('page_number') != index + 1
                    or row.get('row_id') != f'pdf:page:{index+1}'):
                raise ValueError('보존 PDF 추출본의 물리 페이지 범위가 다릅니다.')
            worker_job = None
            with store.connect() as db:
                for job in db.execute("SELECT id,status,request FROM jobs WHERE workspace=? AND kind='source_document' AND output_id=?", (wid, artifact['id'])):
                    if job['status'] in ('succeeded','partial','reused') and json.loads(job['request']).get('artifact_id') == raw['id']:
                        worker_job = {'id': job['id'], 'status': job['status']}
                        break
            binding['verification'] = {'original_bytes_sha256_verified': True,
                'extraction_artifact_sha256_verified': True, 'text_reextracted': False,
                'locator_basis': 'preserved_physical_page_extraction_receipt',
                'bounded_intake_job': worker_job,
                'meaning': 'Physical page location belongs to the retained extraction; text/panel fidelity still requires original review.'}
            binding['location'] = {'page_number': index+1, 'requires_original_review': True}
        else:
            raise ValueError('지원하는 보존 문서 형식을 확인해 주세요.')
    elif artifact['kind'] in ('webpage', 'public_research_page'):
        source = value.get('source', {})
        try:
            raw = base64.b64decode(value['original_response_base64'], validate=True)
        except (KeyError, ValueError, TypeError):
            raise ValueError('웹 본문의 보존된 원 응답이 없습니다.') from None
        if hashlib.sha256(raw).hexdigest() != source.get('sha256'):
            raise ValueError('웹 본문 원 응답 해시가 다릅니다.')
        if row.get('sha256') != hashlib.sha256(row['text'].encode()).hexdigest():
            raise ValueError('웹 본문 문자 행의 해시가 다릅니다.')
        if artifact['kind'] == 'public_research_page':
            if row.get('kind') not in ('paragraph', 'pdf_page'):
                raise ValueError('검색 요약과 미방문 링크는 원문 본문이 아닙니다.')
            rendered = value.get('original_rendered_html_base64')
            if rendered is not None:
                rendered_raw = base64.b64decode(rendered, validate=True)
                if hashlib.sha256(rendered_raw).hexdigest() != value.get('browser', {}).get('rendered_sha256'):
                    raise ValueError('Chrome 렌더링 본문의 해시가 다릅니다.')
        binding.update(origin='fetched_webpage', original={'url': source.get('url'), 'resolved_url': source.get('resolved_url'),
                       'sha256': source['sha256']},
                       extraction={'content_coverage': copy.deepcopy(value.get('content_coverage', {})),
                                   'acquisition_status': value.get('acquisition_status'),
                                   'limits': copy.deepcopy(value.get('limits', []))})
        binding['location'] = {'block_index': index, 'requires_original_review': True,
                               'locator_type': 'immutable_extraction_block_not_dom_anchor'}
        if row.get('kind') == 'pdf_page':
            binding['location'] = {'page_number': row['page_number'], 'requires_original_review': True}
    else:
        raise ValueError('문자층 원문 종류가 아닙니다.')
    return [row['text']], binding
