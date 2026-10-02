"""Versioned public measurements, labels and trial records; no efficacy scoring.

Provider responses stay intact. Presentation rows are addresses into that source,
not an independently curated evidence set or a count of independent experiments.
"""
import base64
import hashlib
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET

from .science import fetch
from .target_evidence import identifier


def text_query(value, label, maximum=240):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
        raise ValueError(label + '의 공개 검색어를 입력해 주세요.')
    return value.strip()


def page(value):
    if type(value) is not int or not 1 <= value <= 10000:
        raise ValueError('조회 페이지는 1 이상이어야 합니다.')
    return value


def search_labels(arguments):
    query = text_query(arguments['drug_name'], '약물')
    p = page(arguments['page'])
    url = 'https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json?' + urllib.parse.urlencode(
        {'drug_name': query, 'pagesize': 20, 'page': p})
    raw, source = fetch(url)
    body = json.loads(raw)
    rows = body['data']
    meta = body.get('metadata', {})
    following = meta.get('next_page_url')
    return {'status': 'succeeded', 'semantic_type': 'label_identifier_search',
            'source': source, 'response': body, 'original_response_base64': base64.b64encode(raw).decode(), 'rows': rows,
            'summary': {'query': query, 'page': p, 'returned': len(rows),
                        'total': meta.get('total_elements'), 'has_more': following not in (None, '', 'null'),
                        'database_published_date': meta.get('db_published_date')},
            'limits': ['DailyMed에 수록된 라벨의 검색 목록입니다. 등재 자체가 승인·효능을 뜻하지 않습니다.',
                       '같은 성분의 제형·제품·판본을 구분한 뒤 원 SPL을 읽어 적응증·대상·경고·시험을 확인합니다.',
                       '현재 페이지 밖과 다른 관할권의 라벨은 미조회입니다.']}


def label_rows(raw, requested_setid):
    if re.search(br'<!\s*(DOCTYPE|ENTITY)\b', raw, re.I):
        raise ValueError('외부 선언을 포함하는 XML은 이 판독기에서 지원하지 않습니다.')
    root = ET.fromstring(raw)
    ns = {'h': 'urn:hl7-org:v3'}
    def direct(element, name, attr=None):
        child = element.find('h:' + name, ns)
        return None if child is None else child.get(attr) if attr else ''.join(child.itertext()).strip()
    actual = direct(root, 'setId', 'root')
    if not actual or actual.lower() != requested_setid.lower():
        raise ValueError('반환 SPL의 setId가 요청한 라벨과 다릅니다.')
    rows, navigation = [], []
    for ordinal, section in enumerate(root.findall('.//h:section', ns)):
        section_info = {'section_index': ordinal, 'section_xml_id': section.get('ID'),
                        'section_code': direct(section, 'code', 'code'),
                        'section_code_system': direct(section, 'code', 'codeSystem'),
                        'section_title': direct(section, 'title')}
        start = len(rows)
        content = section.find('h:text', ns)
        if content is not None:
            # Serialize the exact section text separately from the original SPL;
            # even empty/unsupported markup remains an accessible original.
            for block_index, block in enumerate(list(content) or [content]):
                tag = block.tag.rsplit('}', 1)[-1]
                base = {**section_info, 'block_index': block_index, 'block_type': tag,
                        'xml_id': block.get('ID'),
                        'locator': f'section[{ordinal}]/text/child[{block_index}]'}
                if tag == 'table':
                    caption = block.find('h:caption', ns)
                    table_caption = ''.join(caption.itertext()).strip() if caption is not None else None
                    for tr_index, tr in enumerate(block.findall('.//h:tr', ns)):
                        cells = [{'type': c.tag.rsplit('}', 1)[-1], 'text': ' '.join(c.itertext()).strip(),
                                  'xml_id': c.get('ID'), 'colspan': c.get('colspan'), 'rowspan': c.get('rowspan')}
                                 for c in tr if c.tag.rsplit('}', 1)[-1] in ('td', 'th')]
                        rows.append({**base, 'row_id': f's{ordinal}:b{block_index}:tr{tr_index}',
                                     'table_row': tr_index, 'caption': table_caption, 'cells': cells})
                else:
                    text = ' '.join(block.itertext()).strip()
                    for offset in range(0, max(1, len(text)), 3000):
                        rows.append({**base, 'row_id': f's{ordinal}:b{block_index}:c{offset}',
                                     'text': text[offset:offset + 3000], 'text_offset_codepoints': offset,
                                     'text_total_codepoints': len(text),
                                     'text_is_fragment': len(text) > 3000})
        navigation.append({**section_info, 'row_offset': start, 'row_count': len(rows) - start})
    return rows, navigation, {'setid': actual, 'document_id': direct(root, 'id', 'root'),
                              'spl_version': direct(root, 'versionNumber', 'value'),
                              'effective_time': direct(root, 'effectiveTime', 'value'),
                              'title': direct(root, 'title'), 'document_type': direct(root, 'code', 'displayName')}


def read_label(arguments):
    setid = identifier(arguments['setid'], r'[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}', 'SPL')
    url = f'https://dailymed.nlm.nih.gov/dailymed/services/v2/spls/{setid}.xml'
    raw, source = fetch(url)
    rows, navigation, identity = label_rows(raw, setid)
    return {'status': 'succeeded', 'semantic_type': 'reported_product_label', 'source': source,
            'original_xml': raw.decode('utf-8-sig'), 'original_response_base64': base64.b64encode(raw).decode(),
            'rows': rows, 'section_navigation': navigation,
            'summary': {**identity, 'returned_rows': len(rows), 'sections': len(navigation),
                        'label_url': f'https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={setid}'},
            'limits': ['현재 회수된 미국 SPL 원문입니다. 연구자의 대상·제형·관할권과 일치하는지 확인합니다.',
                       '문서 effectiveTime·판본과 본문 안의 개정 날짜는 다른 필드입니다. 서로 덮어쓰지 않습니다.',
                       '텍스트·표의 위치를 보존한 표현이며 그림 픽셀 판독이나 승인 상태의 독립 검증이 아닙니다.',
                       '등록된 적응증·시험 결과를 새로운 후보 또는 다른 대상의 효능으로 전이하지 않습니다.']}


def _json_rows(value, path=()):
    """Exact, bounded JSON subtrees, retaining null/empty values and typed paths."""
    encoded = json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    pointer = '/' + '/'.join(str(p).replace('~', '~0').replace('/', '~1') for p in path)
    if len(encoded) <= 2500 or not isinstance(value, (dict, list)):
        if isinstance(value, str) and len(value) > 2500:
            for start in range(0, len(value), 2500):
                yield {'path': list(path), 'json_pointer': pointer, 'value': value[start:start + 2500],
                       'fragment_offset_codepoints': start, 'source_string_codepoints': len(value)}
        else:
            yield {'path': list(path), 'json_pointer': pointer, 'value': value}
    else:
        for key, child in value.items() if isinstance(value, dict) else enumerate(value):
            yield from _json_rows(child, (*path, key))


def trial_rows(body):
    rows, navigation = [], []
    for section, contents in body.items():
        modules = contents.items() if isinstance(contents, dict) else [(None, contents)]
        for module, value in modules:
            path = (section,) if module is None else (section, module)
            start = len(rows)
            for row in _json_rows(value, path):
                rows.append({'row_id': f'json:{len(rows)}', 'section': section, 'module': module, **row})
            navigation.append({'section': section, 'module': module, 'row_offset': start, 'row_count': len(rows)-start})
    return rows, navigation


def read_trial(arguments):
    nct = identifier(arguments['nct_id'], r'NCT[0-9]{8}', '임상시험')
    raw, source = fetch(f'https://clinicaltrials.gov/api/v2/studies/{nct}')
    body = json.loads(raw)
    protocol = body.get('protocolSection', {})
    identity = protocol.get('identificationModule', {})
    if identity.get('nctId') != nct:
        raise ValueError('반환 임상시험 ID가 요청과 다릅니다.')
    rows, navigation = trial_rows(body)
    return {'status': 'succeeded', 'semantic_type': 'registered_trial_protocol_and_reported_results',
            'source': source, 'response': body, 'original_response_base64': base64.b64encode(raw).decode(),
            'rows': rows, 'section_navigation': navigation,
            'summary': {'nct_id': nct, 'title': identity.get('briefTitle'),
                        'overall_status': protocol.get('statusModule', {}).get('overallStatus'),
                        'last_update_posted': protocol.get('statusModule', {}).get('lastUpdatePostDateStruct'),
                        'has_results': body.get('hasResults'),
                        'results_modules': list(body.get('resultsSection', {})),
                        'returned_rows': len(rows)},
            'limits': ['등록자 제공 프로토콜·결과 원 기록입니다. 등록 상태 자체가 효능이나 승인 근거는 아닙니다.',
                       '계획된 평가항목과 보고된 결과를 구분하고 대상·기간·분모·분석집단·단위·부작용을 함께 읽습니다.',
                       'hasResults=false 또는 필드 부재는 음성 결과가 아닙니다. 논문·규제문서와 공통 시험을 별개 반복으로 세지 않습니다.',
                       '다른 시험의 서로 다른 대상·기간 결과를 직접 비교한 우월성으로 해석하지 않습니다.']}


def search_trials(arguments):
    condition = text_query(arguments['condition'], '질환')
    intervention = arguments['intervention'].strip()
    if intervention:
        intervention = text_query(intervention, '개입')
    token = arguments['page_token']
    if not isinstance(token, str) or len(token) > 2000:
        raise ValueError('임상시험 조회의 다음 페이지 표식을 확인해 주세요.')
    query = {'query.cond': condition, 'pageSize': 20, 'countTotal': 'true', 'format': 'json'}
    if intervention:
        query['query.intr'] = intervention
    if token:
        query['pageToken'] = token
    raw, source = fetch('https://clinicaltrials.gov/api/v2/studies?' + urllib.parse.urlencode(query))
    body = json.loads(raw)
    rows = []
    for study in body.get('studies', []):
        p = study.get('protocolSection', {})
        ident = p.get('identificationModule', {})
        rows.append({'nct_id': ident.get('nctId'), 'title': ident.get('briefTitle'),
                     'status': p.get('statusModule'), 'conditions': p.get('conditionsModule'),
                     'design': p.get('designModule'), 'interventions': p.get('armsInterventionsModule'),
                     'has_results': study.get('hasResults')})
    return {'status': 'succeeded', 'semantic_type': 'trial_registry_search', 'source': source,
            'response': body, 'original_response_base64': base64.b64encode(raw).decode(), 'rows': rows,
            'summary': {'condition': condition, 'intervention': intervention, 'returned': len(rows),
                        'total': body.get('totalCount'), 'next_page_token': body.get('nextPageToken'),
                        'has_more': bool(body.get('nextPageToken'))},
            'limits': ['등록 시험의 검색 목록입니다. 관련 대상·개입·설계를 확인한 뒤 해당 NCT 원 기록을 읽습니다.',
                       '검색어/현재 페이지 밖은 미조회이며, 결과 미게시와 음성 결과를 구분합니다.',
                       '같은 시험의 논문·등록·라벨은 독립적인 세 번의 시험이 아닙니다.']}


def binding_measurements(arguments):
    uniprot = identifier(arguments['uniprot_id'], r'(?:[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2}|[OPQ][0-9][A-Z0-9]{3}[0-9])(?:-[0-9]+)?', 'UniProt')
    cutoff = arguments['cutoff_nm']
    if type(cutoff) is not int or not 1 <= cutoff <= 1000000:
        raise ValueError('BindingDB 조회 문턱은 1–1,000,000nM의 정수로 명시해 주세요.')
    url = 'https://bindingdb.org/rest/getLigandsByUniprots?' + urllib.parse.urlencode(
        {'uniprot': uniprot, 'cutoff': cutoff, 'response': 'application/json'})
    raw, source = fetch(url)
    body = json.loads(raw) if raw.strip() else None
    # The provider's public key contains the historical spelling "Linds".
    values = [] if body is None else (body.get('getLindsByUniprotsResponse') or {}).get('affinities', [])
    if isinstance(values, dict):
        values = [values]
    if not isinstance(values, list) or any(not isinstance(v, dict) for v in values):
        raise ValueError('BindingDB 응답 형식을 확인해야 합니다.')
    if body is not None and 'getLindsByUniprotsResponse' not in body:
        raise ValueError('BindingDB 응답에 요청한 자료 컨테이너가 없습니다.')
    seen, rows = {}, []
    for i, value in enumerate(values):
        digest = hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        first = seen.setdefault(digest, i)
        rows.append({'row_id': f'bindingdb:{i}', 'candidate_id': 'BDBM:' + str(value['monomerid']) if value.get('monomerid') else None,
                     'smiles':value.get('smile'), 'structure_status':'available' if value.get('smile') else 'unavailable',
                     'raw': value, 'exact_representation_sha256': digest,
                     'same_returned_representation_as_row': first if first != i else None,
                     'assay_context': None,
                     'doi_role': 'unclassified_provider_reference_not_assumed_primary_article'})
    return {'status': 'succeeded', 'semantic_type': 'reported_bindingdb_measurements',
            'target_context': 'UniProt:' + uniprot,
            'source': source, 'response': body, 'original_response_base64': base64.b64encode(raw).decode(), 'rows': rows,
            'summary': {'uniprot_id': uniprot, 'query_cutoff_nm': cutoff, 'returned_rows': len(rows),
                        'unique_returned_representations': len(seen),
                        'exact_repeat_rows': len(rows)-len(seen), 'assay_context_available': False},
            'limits': ['명시한 활성 검색 문턱 내의 반환 기록입니다. 문턱 밖·미수록은 음성이나 제외가 아닙니다.',
                       '원 affinity 관계기호·값·유형을 보존합니다. Ki/Kd/IC50/EC50은 다른 지표이며 직접 합산·순위화하지 않습니다.',
                       '이 endpoint의 cutoff 단위는 nM입니다. 개별 assay·종·표적 상태·측정 조건은 미제공이므로 원전을 이어 확인해야 합니다.',
                       '동일 반환 표현을 표시했지만 삭제하지 않았습니다. 다른 행도 독립 실험인지 미확인입니다.',
                       'DOI는 데이터셋/등록 자료일 수 있습니다. PMID/DOI만으로 ChEMBL·논문과 독립인 근거라고 세지 않습니다.']}


HANDLERS = {'drug_label_search': search_labels, 'drug_label': read_label,
            'clinical_trial_search': search_trials, 'clinical_trial': read_trial,
            'binding_measurements': binding_measurements}


# The paged artifact view drops the raw registry response so rows are not duplicated, but the
# reported outcomes and adverse events are exactly what a reader needs to judge a trial. This
# derives only the parts the screen shows, copying every value as posted; nothing is recomputed,
# no group is merged and no ordering is presented as a safety ranking.
def reported_results(value, top=12):
    results = (value or {}).get('response', {}).get('resultsSection')
    if not isinstance(results, dict):
        return None
    outcomes = [o for o in (results.get('outcomeMeasuresModule') or {}).get('outcomeMeasures') or []
                if isinstance(o, dict)]
    adverse = results.get('adverseEventsModule') if isinstance(results.get('adverseEventsModule'), dict) else None
    kept = None
    if adverse:
        def by_affected_share(event):
            shares = [int(s.get('numAffected') or 0) / int(s['numAtRisk'])
                      for s in event.get('stats') or []
                      if str(s.get('numAtRisk') or '0').isdigit() and int(s['numAtRisk']) > 0]
            return max(shares, default=0.0)
        kept = {'frequencyThreshold': adverse.get('frequencyThreshold'),
                'timeFrame': adverse.get('timeFrame'),
                'eventGroups': adverse.get('eventGroups') or [],
                'seriousEventsTotal': len(adverse.get('seriousEvents') or []),
                'otherEventsTotal': len(adverse.get('otherEvents') or []),
                'seriousEvents': sorted(adverse.get('seriousEvents') or [], key=by_affected_share,
                                        reverse=True)[:top],
                'otherEvents': sorted(adverse.get('otherEvents') or [], key=by_affected_share,
                                      reverse=True)[:top]}
    return {'outcomeMeasures': outcomes, 'adverseEvents': kept,
            'outcomeMeasuresTotal': len(outcomes), 'outcomes_truncated': False,
            'shown_events_per_list': top,
            'meaning': 'Registry-posted values copied as recorded. Event lists are truncated by '
                       'reported frequency for display; the totals state the full counts. This is '
                       'not a safety comparison or a significance test.'}
