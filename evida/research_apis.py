"""Bounded server-side OpenGWAS and CLUE access; no credentials in model inputs."""
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlencode
from .service_access import request_json, gwas_metadata, ORIGINS
from .service_credentials import read_secret, CredentialError


def validate(tool, args):
    if tool == 'gwas_studies':
        ids = args.get('study_ids')
        if not isinstance(ids, list) or not 1 <= len(ids) <= 10 or len(set(ids)) != len(ids):
            raise ValueError('Select one to ten distinct public OpenGWAS study IDs.')
        if any(not isinstance(i, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', i) for i in ids):
            raise ValueError('Use exact public study identifiers from a cited source.')
    elif tool == 'perturbagen_metadata':
        name = args.get('compound_name'); limit = args.get('limit')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120 or any(ord(c)<32 for c in name):
            raise ValueError('Use a public compound name, not a credential or private text.')
        if type(limit) is not int or not 1 <= limit <= 10:
            raise ValueError('Select one to ten matching perturbagen metadata rows.')
    else: raise ValueError('Unknown research API tool.')


def retrieve(tool, args, directory, *, secret_reader=read_secret, request=request_json):
    validate(tool, args)
    if tool == 'gwas_studies':
        service = 'opengwas'
        spec = {'name': 'study-metadata', 'method': 'POST', 'path': '/api/gwasinfo',
                'body': {'id': args['study_ids']}}
    else:
        service = 'clue'
        spec = {'name': 'perturbagen-metadata', 'method': 'GET', 'path': '/api/perts?'+urlencode({'filter': json.dumps({
            'where': {'pert_iname': args['compound_name'].strip()}, 'limit': args['limit'],
            'fields': ['pert_id','pert_iname','moa','canonical_smiles']}, separators=(',', ':'))})}
    result = {'status': 'failed', 'rows': [], 'query': args, 'source': {'url': ORIGINS[service]+spec['path']},
        'source_attribution': 'IEU OpenGWAS' if service == 'opengwas' else 'Broad Institute CLUE',
        'access_documentation': 'https://api.opengwas.io/api/' if service == 'opengwas' else 'https://clue.io/connectopedia',
        'semantic_type': 'retrieved_study_metadata' if service == 'opengwas' else 'retrieved_perturbagen_metadata',
        'limits': ['Metadata is not a causal association, a signature reversal result, or clinical efficacy.',
                   'A missing or failed source does not establish that biological evidence is absent.'],
        'model_calls': 0, 'automatic_retry': False, 'source_receipts': []}
    try: secret = secret_reader(service)
    except CredentialError:
        return {**result, 'access_status': 'CREDENTIAL_PENDING', 'error': '이 자료원의 서버 인증이 필요합니다. 다른 조사 경로는 계속 사용할 수 있습니다.'}
    try: receipt, value = request(service, spec, secret)
    finally: del secret
    result['source_receipts'] = [receipt]
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    (directory/'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False))
    if receipt['status'] != 'JSON_RECEIVED':
        return {**result, 'access_status': receipt['status'], 'error': '해당 자료원 조회를 완료하지 못했습니다. 검색 0건이 아닙니다.'}
    if service == 'opengwas':
        normalized = gwas_metadata(value, args['study_ids'])
        if normalized is None:
            return {**result, 'access_status': 'RESPONSE_SCHEMA_UNVERIFIED'}
        rows = normalized['records']; result.update(missing_requested_ids=normalized['missing_requested_ids'])
    else:
        if not isinstance(value, list) or len(value)>args['limit'] or any(not isinstance(r, dict) or
                not r.get('pert_id') or r.get('pert_iname') != args['compound_name'].strip() for r in value):
            return {**result, 'access_status': 'RESPONSE_SCHEMA_UNVERIFIED'}
        rows = [{k:v for k,v in r.items() if k in ('pert_id','pert_iname','moa','canonical_smiles')} for r in value]
        result['cmap_signature_submission_verified'] = False
    # The response receipt hashes the original HTTP bytes; this hash labels the
    # separately serialized retained JSON, without pretending those bytes are identical.
    normalized_raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    (directory/'response.json').write_bytes(normalized_raw)
    result.update(status='succeeded', access_status='QUERY_VERIFIED', rows=rows,
        normalized_response_sha256=hashlib.sha256(normalized_raw).hexdigest(),
        summary={'returned': len(rows), 'total_matching': None, 'complete_database_search': False})
    return result
