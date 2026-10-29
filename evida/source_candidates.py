"""Source-local candidate assertions precede chemical resolution and ranking.

Exact quotations and locators are checked mechanically. Candidate relevance and
the relation between a local label and chemical name remain model assertions.
"""
import hashlib
import json
import re

import jsonschema

from .discovery import TEXT, TEXTS, obj

ANCHOR = obj({'artifact_id': TEXT, 'row_index': {'type': 'integer', 'minimum': 0},
              'quote': {'type': 'string', 'minLength': 1, 'maxLength': 2500}})
IDENTITY = obj({'name_type': {'type': 'string', 'enum': ['source_local', 'public_name', 'unknown']},
                'lookup_name': TEXT, 'lookup_anchor': {'anyOf': [ANCHOR, {'type': 'null'}]}})
ROW = obj({'name': {'type': 'string', 'minLength': 1, 'maxLength': 300,
                    'description': 'Exact source name/label only, e.g. C6. Do not append (PMC...) or commentary; the preserved-source namespace is automatic.'},
           'role': {'type': 'string', 'enum': ['candidate', 'reference_treatment']},
           'modality': {'type': 'string', 'enum': ['small_molecule', 'sirna', 'other', 'unknown']},
           'target_context': TEXT, 'mention': ANCHOR, 'identity': IDENTITY,
           'membership_reason': TEXT, 'conditions': TEXTS, 'next_check': TEXT})
RECORD = obj({'question': TEXT, 'rows': {'type': 'array', 'items': ROW, 'minItems': 1, 'maxItems': 100}})
PUBLIC_CANDIDATE_SOURCES = {'pubmed_search','pubmed_abstracts','source_document', 'webpage', 'public_research_page', 'article', 'literature', 'repository_document', 'clinical_trial',
                            'clinical_trial_search', 'drug_label', 'drug_label_search',
                            'binding_measurements', 'gtopdb_pharmacology', 'compound_candidates'}


class SourceBindingError(ValueError):
    def __init__(self, errors):
        self.source_binding_errors = errors
        super().__init__('원문 후보의 이름·인용 대응을 확인해 주세요. source_binding_errors에 실패한 행과 수정 단서가 있습니다. 원 제안은 보존하고 자동으로 이름이나 인용을 바꾸지 않았습니다.')


def strings(value):
    """Values only: a schema key cannot serve as a quoted source statement."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in strings(v)]
    return []


def source_namespace(value, row, artifact):
    if artifact['kind'] == 'source_document':
        return 'uploaded-sha256:' + value['source_sha256']
    ids = row.get('article_ids') or value.get('article_ids') or {}
    pmc = row.get('pmc_id') or row.get('pmcid') or ids.get('pmcid')
    if not pmc and artifact['kind'] == 'article':
        pmc = value.get('pmc_id')
    if pmc and re.fullmatch(r'PMC\d+(?:\.\d+)?', str(pmc), re.I):
        return 'pmc:' + str(pmc).upper().split('.')[0]
    doi = row.get('doi') or ids.get('doi')
    if doi and re.fullmatch(r'10\.\d{4,9}/\S+', str(doi).strip(), re.I):
        return 'doi:' + str(doi).strip().lower()
    if artifact['kind'] in ('pubmed_search','pubmed_abstracts'):
        pmid=row.get('pmid') or ids.get('pmid')
        if isinstance(pmid,str) and re.fullmatch(r'[1-9][0-9]{0,9}',pmid):return 'pubmed:'+pmid
    if artifact['kind'] in ('webpage', 'public_research_page'):
        # checked_anchor has verified the retained response bytes before reaching here.
        # A source-local label belongs to the document, not to an extraction paragraph.
        source = value.get('source', {})
        url = source.get('resolved_url') or source.get('url')
        if isinstance(url, str) and url.strip():
            return 'web-response-sha256:' + source['sha256'] + ':url-sha256:' + hashlib.sha256(url.encode()).hexdigest()
        return 'artifact:' + artifact['id'] + ':sha256:' + artifact['sha256']
    # Unknown publication identity stays tied to immutable content, never label alone.
    return 'artifact:' + artifact['sha256'] + ':row:' + str(row.get('row_id', 'unknown'))


def checked_anchor(store, wid, anchor, name):
    artifact = store.artifact(wid, anchor['artifact_id'])
    if artifact['kind'] not in PUBLIC_CANDIDATE_SOURCES:
        raise ValueError('후보 이름은 보존된 원문 본문 행에 연결해 주세요.')
    value = json.loads(artifact['content'])
    rows = value.get('rows', [])
    index = anchor['row_index']
    if type(index) is not int or index < 0 or index >= len(rows):
        raise ValueError('원문 행 위치가 없습니다.')
    row = rows[index]
    from .literal_source_binding import LITERAL_KINDS, row_binding
    texts, binding = row_binding(store, wid, artifact, value, index) if artifact['kind'] in LITERAL_KINDS else (strings(row), None)
    quote = anchor['quote']
    quote_present = bool(quote.strip()) and any(quote in text for text in texts)
    if quote.strip().casefold() == name.casefold():
        # A quotation consisting only of C6 must not borrow the C6 prefix of C6-3.
        # Exact structured table cells still work despite flattened C41.6 text.
        quote_present = quote_present and any(re.search(r'(?<![\w-])'+re.escape(name)+r'(?![\w-])',text,re.I) for text in texts)
    name_present = bool(re.search(r'(?<![\w-])'+re.escape(name)+r'(?![\w-])',quote,re.I))
    if not quote_present or not name_present:
        hint = 'Use an exact source quotation that includes the raw source label; retain the scientific interpretation separately.'
        decorated = re.fullmatch(r'(.+)\s+\(PMC\d+\)',name,re.I)
        if decorated:
            hint = 'The name contains an added publication suffix. Use the raw source label only; the system already qualifies it by publication.'
        elif name in texts:
            hint = 'This exact name exists as a structured cell in this source row. A flattened table can concatenate adjacent numbers. Quote the exact name cell itself, or a genuine sentence containing it, rather than adding word boundaries to the flattened table.'
        raise SourceBindingError([{'artifact_id':artifact['id'],'row_index':index,'name':name,
            'quote_present':quote_present,'name_in_quote':name_present,'hint':hint}])
    return {**anchor, 'locator': 'rows/' + str(index), 'source_sha256': artifact['sha256'],
            'row_id': row.get('row_id'), 'namespace': source_namespace(value, row, artifact),
            **({'source_binding': binding} if binding else {})}


def record(store, wid, rev, jid, arguments):
    jsonschema.validate(arguments, RECORD)
    from .store import Conflict, dump
    if store.snapshot(wid)['rev'] != rev:
        raise Conflict('연구 조건이 바뀌어 이전 입력의 후보 기록을 적용하지 않았습니다.')
    rows = []; errors = []
    seen = set()
    for row_number, assertion in enumerate(arguments['rows']):
        if not all(assertion[k].strip() for k in ('name', 'target_context', 'membership_reason', 'next_check')):
            raise ValueError('이름·연구 맥락·목록에 남기는 이유·다음 확인이 필요합니다.')
        name = assertion['name'].strip()
        try:
            mention = checked_anchor(store, wid, assertion['mention'], name)
        except SourceBindingError as exc:
            errors.extend({**e,'candidate_row':row_number,'field':'mention'} for e in exc.source_binding_errors)
            continue
        identity = dict(assertion['identity'])
        lookup = identity['lookup_name'].strip()
        if lookup:
            if identity['lookup_anchor'] is None:
                raise ValueError('구조 조회명도 정확한 원문 위치에 연결해 주세요.')
            if identity['name_type'] == 'source_local' and lookup.casefold() == name.casefold():
                raise ValueError('논문 안의 물질 번호를 전역 화학명으로 조회하지 않습니다. 원문의 화학명이나 식별자를 확인해 주세요.')
            try:
                identity['lookup_anchor'] = checked_anchor(store, wid, identity['lookup_anchor'], lookup)
            except SourceBindingError as exc:
                errors.extend({**e,'candidate_row':row_number,'field':'identity.lookup_anchor'} for e in exc.source_binding_errors)
                continue
        elif identity['lookup_anchor'] is not None:
            raise ValueError('조회명이 없으면 조회명 인용은 null로 남겨 주세요.')
        identity['lookup_name'] = lookup
        key = mention['namespace'] + '|' + name.casefold()
        cid = 'source-candidate:' + hashlib.sha256(key.encode()).hexdigest()[:24]
        if cid in seen:
            raise ValueError('같은 원문 후보의 중복 행은 합쳐서 기록해 주세요.')
        seen.add(cid)
        rows.append({**assertion, 'name': name, 'mention': mention, 'identity': identity,
                     'candidate_id': cid, 'identity_basis': key,
                     'structure_status': 'not_resolved', 'smiles': None,
                     'review_status': 'unreviewed', 'target_activity_verified': False})
    if errors:
        raise SourceBindingError(errors)
    value = {'status': 'recorded', 'question': arguments['question'], 'rows': rows,
             'semantic_type': 'source_anchored_candidate_assertions_not_validation',
             'summary': {'candidates': len(rows), 'rule': 'Source membership is a reasoned assertion; no ranking or efficacy inferred.'}}
    aid = store.add_artifact(wid, '원문 후보 · ' + arguments['question'][:100], 'source_candidates',
        dump(value).encode(), {'based_rev': rev, 'job_id': jid, 'omission_deletes_options': False,
                              'scientific_validation': False, 'summary': value['summary']}, bump=False)
    return {'status': 'recorded', 'artifact_id': aid, 'rows': rows, 'scientific_validation': False,
            'next': 'Use this artifact and the retained name in resolve_literature_compounds only when chemical resolution is useful. siRNA reference drugs are not small-molecule calculations.'}


def validate_resolution_sources(store, wid, source_ids):
    """Recheck new literal-source assertions before a chemical lookup/reuse."""
    for aid in source_ids:
        artifact = store.artifact(wid, aid)
        if artifact['kind'] != 'source_candidates':
            continue
        value = json.loads(artifact['content'])
        for row in value.get('rows', []):
            for anchor, name in [(row['mention'], row['name']), (row['identity'].get('lookup_anchor'), row['identity'].get('lookup_name'))]:
                if not anchor or 'source_binding' not in anchor:
                    continue
                checked = checked_anchor(store, wid, {k: anchor[k] for k in ('artifact_id','row_index','quote')}, name)
                if checked['source_sha256'] != anchor['source_sha256'] or checked.get('source_binding') != anchor['source_binding']:
                    raise ValueError('화학 식별 전 원문 후보의 보존 출처 결속이 달라졌습니다.')
