"""Bounded scientific publisher HTML acquisition; extraction is not paper reading."""
from __future__ import annotations
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit

PUBLISHER_HOSTS = frozenset({'www.frontiersin.org', 'journals.plos.org', 'www.nature.com',
    'link.springer.com', 'elifesciences.org', 'respiratory-research.biomedcentral.com',
    'pmc.ncbi.nlm.nih.gov'})
API_HOSTS = frozenset({'www.ebi.ac.uk'})
MAX_DOWNLOAD = 5 * 1024 * 1024
MAX_REDIRECTS = 4
TOTAL_SECONDS = 90
WORKER = Path(__file__).with_name('web_sources_worker.py')

def validate_url(url, hosts=PUBLISHER_HOSTS):
    if not isinstance(url, str) or len(url) > 3000 or any(ord(c) < 33 for c in url) or '\\' in url:
        raise ValueError('올바른 공개 자료 주소가 필요합니다.')
    p = urlsplit(url)
    if (p.scheme != 'https' or p.hostname not in hosts or p.username is not None or
            p.password is not None or p.port not in (None, 443)):
        raise ValueError('지원하는 과학 출판사의 HTTPS 주소가 필요합니다.')
    if re.search(r'/(?:authorize|oauth|login|signin)(?:/|$)', p.path, re.I):
        raise ValueError('인증 페이지로 이동하지 않습니다.')
    return p

def normalize_doi(value):
    if not isinstance(value, str):
        return None
    value = re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', value.strip(), flags=re.I).casefold()
    return value if re.fullmatch(r'10\.\d{4,9}/[^\s<>"\x00-\x1f]+', value) else None

def _progress_source(output):
    if not output:
        return {}
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
            if isinstance(value, dict) and isinstance(value.get('progress'), dict):
                return value['progress']
        except (ValueError, UnicodeDecodeError):
            continue
    return {}


def _worker(mode, payload, timeout):
    # Do not forward login/session credentials to a parser/network subprocess.
    env = {'PYTHONDONTWRITEBYTECODE': '1', 'LANG': 'C.UTF-8'}
    if os.environ.get('LD_LIBRARY_PATH'):
        env['LD_LIBRARY_PATH'] = os.environ['LD_LIBRARY_PATH']
    try:
        proc = subprocess.run([sys.executable, '-B', str(WORKER), mode],
            input=json.dumps(payload).encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=max(.01, timeout), env=env, check=False)
    except subprocess.TimeoutExpired as exc:
        return {'worker_error': 'wall_timeout', 'mode': mode, 'source': _progress_source(exc.stdout)}
    if proc.returncode:
        return {'worker_error': 'process_limit_or_failure', 'mode': mode, 'returncode': proc.returncode,
                'source': _progress_source(proc.stdout)}
    # Worker output is bounded by downloaded text and its configured process memory.
    try:
        result = json.loads(proc.stdout.splitlines()[-1])
        if not isinstance(result, dict):
            raise ValueError('not an object')
        return result
    except (ValueError, UnicodeDecodeError, IndexError):
        return {'worker_error': 'invalid_worker_response', 'mode': mode}

def _recover_identifier(doi, remaining):
    query = 'DOI:"' + doi + '"'
    url = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?' + urlencode(
        {'query': query, 'format': 'json', 'resultType': 'core', 'pageSize': 20})
    fetched = _worker('fetch', {'url': url, 'api': True}, min(20, remaining))
    receipt = fetched.get('source', {})
    result = {'status': 'unresolved', 'query': query, 'source': receipt,
              'article_ids': {}, 'full_text_read': False, 'access_status': fetched.get('acquisition_status')}
    if fetched.get('worker_error'):
        result['error'] = fetched['worker_error']
        return result
    if fetched.get('acquisition_status') != 'response_received':
        return result
    try:
        body = json.loads(base64.b64decode(fetched['original_response_base64'], validate=True))
        hits = body.get('resultList', {}).get('result', [])
        result['hit_count'] = body.get('hitCount')
        matches = [r for r in hits if normalize_doi(r.get('doi')) == doi]
        result['matching_records'] = [{k: r[k] for k in ('id', 'source', 'doi', 'pmid', 'pmcid', 'title') if k in r} for r in matches]
        # More hits than requested, unknown count, or conflicting IDs remain unresolved.
        if type(body.get('hitCount')) is not int or body['hitCount'] > len(hits):
            result['reason'] = 'incomplete_search_inventory'
            return result
        pmcs = {r['pmcid'] for r in matches if re.fullmatch(r'PMC\d+', str(r.get('pmcid', '')))}
        pmids = {str(r.get('pmid') or (r.get('id') if r.get('source') == 'MED' else '')) for r in matches}
        pmids = {value for value in pmids if re.fullmatch(r'\d+', value)}
        if not matches or len(pmcs) != 1 or len(pmids) > 1:
            result['reason'] = 'missing_or_ambiguous_identifiers'
            return result
        result.update(status='matched', article_ids={'doi': doi, 'pmcid': next(iter(pmcs))})
        if len(pmids) == 1:
            result['article_ids']['pmid'] = next(iter(pmids))
    except (ValueError, TypeError, KeyError, AttributeError):
        result['reason'] = 'invalid_identifier_response'
    return result

def read_webpage(arguments):
    url = arguments.get('url')
    validate_url(url)
    deadline = time.monotonic() + TOTAL_SECONDS
    fetched = _worker('fetch', {'url': url, 'api': False}, 45)
    result = {'status': 'failed', 'semantic_type': 'webpage_text', 'acquisition_status':
        fetched.get('acquisition_status', 'retrieval_failed'), 'source': fetched.get('source') or {'url': url},
        'title': '', 'article_ids': {}, 'permissions': [], 'rows': [],
        'content_coverage': {'scope': 'none', 'returned_blocks': 0, 'read_blocks': [],
            'complete_paper_verified': False, 'tables_figures_supplements_verified': False,
            'source_retrieval_is_not_reading_or_complete_paper_verification': True},
        'limits': ['추출한 웹 본문의 각 위치에서 주장의 근거와 적용 조건을 확인합니다.',
                   '표·그림·보충자료가 필요한 주장은 연결된 공개 원문에서 해당 위치를 이어서 확인합니다.']}
    if 'original_response_base64' in fetched:
        result['original_response_base64'] = fetched['original_response_base64']
    if fetched.get('worker_error'):
        result['error'] = fetched['worker_error']
    if fetched.get('acquisition_status') != 'response_received':
        return result
    content_type = fetched['source'].get('content_type', '').split(';')[0].strip().lower()
    if content_type not in ('text/html', 'application/xhtml+xml'):
        result['acquisition_status'] = 'unsupported_content_type'
        return result
    if fetched['source'].get('content_encoding') not in ('', 'identity'):
        result['acquisition_status'] = 'unsupported_content_encoding'
        return result
    extracted = _worker('extract', {'original_response_base64': fetched['original_response_base64'],
        'url': fetched['source']['resolved_url']}, min(25, deadline-time.monotonic()))
    if extracted.get('worker_error'):
        result.update(acquisition_status='extraction_failed', error=extracted['worker_error'])
        return result
    result.update({k: extracted[k] for k in ('title', 'permissions', 'identity', 'extractor', 'resources') if k in extracted})
    result['acquisition_status'] = extracted['acquisition_status']
    if extracted.get('identity', {}).get('status') == 'unique':
        result['article_ids']['doi'] = extracted['identity']['normalized_dois'][0]
    if extracted['acquisition_status'] != 'text_acquired':
        result['status'] = 'partial' if extracted['acquisition_status'] == 'metadata_only' else 'failed'
        return result
    source_hash = result['source']['sha256']
    for text in extracted.get('blocks', []):
        result['rows'].append({'row_id': f'{source_hash}:html:{len(result["rows"])}', 'kind': 'paragraph',
            'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest(),
            'source_url': result['source']['resolved_url'], 'section': 'Extracted webpage text',
            'requires_original_review': True})
    result.update(status='succeeded')
    result['content_coverage'].update(scope='extracted_webpage_text', returned_blocks=len(result['rows']),
        characters=sum(len(r['text']) for r in result['rows']),
        locator_type='immutable_extraction_block_not_dom_anchor',
        original_html_paragraphs=extracted.get('substantive_paragraphs'))
    result['summary'] = {'blocks': len(result['rows']), 'content_scope': 'extracted_webpage_text',
                         'primary_identity': extracted.get('identity', {}).get('status', 'unknown')}
    if result['article_ids'].get('doi') and deadline > time.monotonic():
        result['identifier_recovery'] = _recover_identifier(result['article_ids']['doi'], deadline-time.monotonic())
    else:
        result['identifier_recovery'] = {'status': 'not_attempted', 'reason': 'primary_doi_unresolved',
                                         'article_ids': {}, 'full_text_read': False}
    return result
