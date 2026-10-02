"""Public evidence retrieval with explicit original-document boundaries."""
import json
import re
import urllib.error
import xml.etree.ElementTree as ET

from .science import fetch


def article_sections(rows):
    """Navigation over preserved blocks, without ranking or hiding sections."""
    sections = []
    for offset, row in enumerate(rows):
        section = row.get('section', '')
        if not sections or sections[-1]['section'] != section:
            sections.append({'section': section, 'offset': offset, 'blocks': 0})
        sections[-1]['blocks'] += 1
    return sections


def inline_parts(node):
    """Keep chemical subscripts/units without trusting source markup as HTML."""
    parts = []
    if node.text:
        parts.append({'type': 'text', 'text': node.text})
    allowed = {'sub', 'sup', 'bold', 'italic', 'monospace', 'break'}
    for child in node:
        local = child.tag.rsplit('}', 1)[-1]
        children = inline_parts(child)
        if local in allowed:
            parts.append({'type': local, 'children': children})
        else:
            parts.extend(children)
        if child.tail:
            parts.append({'type': 'text', 'text': child.tail})
    return parts


def table_fields(node):
    text = lambda n: ' '.join(''.join(n.itertext()).split())
    return {'xml_id': node.get('id'), 'original_block_xml': ET.tostring(node, encoding='unicode'),
            'table_rows': [[{'kind': c.tag, 'text': text(c), 'inline_parts': inline_parts(c),
                            'rowspan': c.get('rowspan', '1'), 'colspan': c.get('colspan', '1')}
                           for c in tr if c.tag in ('th', 'td')] for tr in node.findall('.//tr')],
            'table_footnotes': [text(n) for n in node.findall('.//table-wrap-foot')]}


def article_presentation(value):
    """Add table presentation only if every stored block identity/text agrees."""
    if not value.get('original_xml') or not value.get('rows'):
        return value
    try:
        parsed = parse_article(value['original_xml'].encode(), value['pmc_id'], value.get('source', {}))
    except (ET.ParseError, ValueError, KeyError):
        return value  # A presentation upgrade cannot make a historical artifact inaccessible.
    old, new = value['rows'], parsed['rows']
    keys = ('row_id', 'xml_id', 'kind', 'section', 'text')
    if len(old) != len(new) or any(any(a.get(k) != b.get(k) for k in keys) for a, b in zip(old, new)):
        return value  # Never silently change a historical locator/block inventory.
    return {**value, 'rows': [{**a, **{k: b[k] for k in ('table_rows', 'embedded_tables', 'citation_markers') if k in b}}
                            for a, b in zip(old, new)],
            'content_coverage': parsed['content_coverage'],
            'limits': parsed['limits'],
            'presentation_note': 'Original XML table/citation/returned-content view; stored artifact, original status and all block locators/text unchanged.'}


def find_entities(arguments):
    query, entity, page = arguments["query"].strip(), arguments["entity"], arguments["page"]
    if not query or len(query) > 500 or entity not in ("target", "disease") or type(page) is not int or page < 0:
        raise ValueError("표적/질환 검색어와 페이지를 확인해 주세요.")
    gql = "query($q:String!,$names:[String!],$page:Pagination){search(queryString:$q,entityNames:$names,page:$page){total hits{id name entity description}}}"
    variables = {"q": query, "names": [entity], "page": {"index": page, "size": 10}}
    raw, receipt = fetch("https://api.platform.opentargets.org/api/v4/graphql", {"query": gql, "variables": variables})
    body = json.loads(raw)
    result = (body.get("data") or {}).get("search") or {}
    rows = result.get("hits", [])
    return {"status": "partial" if body.get("errors") else "succeeded", "semantic_type": "identifier_candidates",
            "source": receipt, "query": gql, "variables": variables, "response": body, "rows": rows,
            "summary": {"returned": len(rows), "total": result.get("total"), "page": page,
                        "has_more": (page + 1) * 10 < result.get("total", 0)},
            "limits": ["검색 결과는 이름에 대응하는 후보입니다. 연구 대상·질환 범위를 확인한 뒤 선택합니다.",
                       "후보 순서가 치료 적합성이나 근거 강도의 순위는 아닙니다."]}


def parse_article(raw, pmc_id, receipt):
    # Do not expand document-defined entities. Original XML remains separately retrievable.
    if b"<!ENTITY" in raw.upper():
        raise ValueError("원문 XML의 별도 엔터티 정의를 처리하지 않습니다. 원문 확인이 필요합니다.")
    root = ET.fromstring(raw)
    if root.tag == 'pmc-articleset':
        articles = root.findall('article')
        if len(articles) != 1:
            raise ValueError('요청한 원문 한 개를 식별할 수 없습니다.')
        root = articles[0]
    if root.tag != 'article':
        raise ValueError('검증 가능한 JATS 원문이 아닙니다.')
    text = lambda node: " ".join("".join(node.itertext()).split()) if node is not None else ""
    ids = {n.get("pub-id-type"): text(n) for n in root.findall(".//article-meta/article-id")}
    reported = ids.get("pmc") or ids.get("pmcid")
    if not reported or reported.removeprefix("PMC") != pmc_id.removeprefix("PMC"):
        raise ValueError("원문이 요청한 PMC ID와 다릅니다.")
    article_meta = root.find(".//article-meta")
    rows = []

    def walk(node, section):
        local = node.tag.rsplit("}", 1)[-1]
        if local == 'ref-list':
            return  # Kept as exact references below, not experimental paragraphs.
        if local == "sec":
            title = node.find("title")
            section = section + ([text(title)] if title is not None else [])
        if local in ("p", "table-wrap", "fig", "supplementary-material"):
            kind = "paragraph" if local == "p" else local
            row = {"row_id": f"{pmc_id}:block:{len(rows)}", "xml_id": node.get("id"),
                         "section": " / ".join(section), "kind": kind, "text": text(node),
                         "requires_original_review": local != "p" or any(n.tag.rsplit("}", 1)[-1] in
                             ("table-wrap", "fig", "supplementary-material", "inline-graphic", "disp-formula", "inline-formula") for n in node.iter()),
                         "source_url": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmc_id}/" + (f"#{node.get('id')}" if node.get("id") else "")}
            row['citation_markers'] = [{'reference_ids': n.get('rid','').split(), 'label':text(n)}
                for n in node.iter() if n.tag.rsplit('}',1)[-1]=='xref' and n.get('ref-type')=='bibr']
            if local == 'table-wrap':
                row.update(table_fields(node))
                row['table_interpretation'] = 'Original row/column order and spans preserved. A flattened paragraph is not a reconstructed table or an independent observation.'
            elif local == 'p':
                tables = node.findall('.//table-wrap')
                if tables:
                    row['embedded_tables'] = [{**table_fields(t), 'parent_row_id': row['row_id']} for t in tables]
            if local in ('fig', 'supplementary-material'):
                row['original_block_xml'] = ET.tostring(node, encoding='unicode')
                row['asset_references'] = [dict(n.attrib) for n in node.iter()
                    if n.tag.rsplit('}', 1)[-1] in ('graphic', 'inline-graphic', 'media', 'ext-link')]
            rows.append(row)
            return  # Captions/table cells must not also become independent flattened paragraphs.
        for child in node:
            walk(child, section)

    if article_meta is not None:
        for abstract in article_meta.findall("abstract"):
            walk(abstract, ["Abstract"])
    body = root.find("body")
    if body is not None:
        walk(body, ["Body"])
    for group in root.findall('floats-group'):
        walk(group, ['Figures and tables'])
    back = root.find('back')
    if back is not None:
        walk(back, ['Back matter'])
    licenses = [text(n) for n in root.findall(".//article-meta/permissions")]
    references = [{"id": n.get("id"), "text": text(n)} for n in root.findall(".//ref-list/ref")]
    body_rows = [r for r in rows if r['section'].split(' / ')[0]=='Body' and r['text'].strip()]
    abstract_rows = [r for r in rows if r['section'].split(' / ')[0]=='Abstract' and r['text'].strip()]
    scope = 'body_available' if body_rows else 'abstract_only' if abstract_rows else 'metadata_or_other_content_only'
    coverage = {'scope':scope, 'body_element_present':body is not None,
                'returned_body_blocks':len(body_rows),'returned_abstract_blocks':len(abstract_rows),
                'returned_references':len(references),
                'declared_counts':{n.tag:dict(n.attrib) for n in root.findall('.//article-meta/counts/*')},
                'source_retrieval_is_not_reading_or_complete_paper_verification':True}
    scope_note = ('이 응답에는 논문 본문 XML이 포함되어 있습니다. 실제 읽은 범위와 표·그림 확인은 별도입니다.' if body_rows else
                  '이 응답에는 초록만 있고 논문 본문은 반환되지 않았습니다. 초록에서 확인한 결과와 본문·표·보충자료의 미확인을 구분합니다.' if abstract_rows else
                  '이 응답에는 확인 가능한 논문 본문이 없습니다. 메타데이터·기타 반환 자료만으로 본문 읽기를 완료 처리하지 않습니다.')
    return {"status": "succeeded" if body_rows else "partial",
            "semantic_type": "published_full_text" if body_rows else "published_abstract" if abstract_rows else "published_metadata",
            "source": receipt, "pmc_id": pmc_id, "article_ids": ids,
            "title": text(root.find(".//article-title")), "permissions": licenses, "rows": rows,
            "references": references, "original_xml": raw.decode("utf-8"), "content_coverage":coverage,
            "summary": {"blocks": len(rows), "original_review_blocks": sum(r["requires_original_review"] for r in rows),
                        "reference_count": len(references), "permissions_present": bool(licenses), "content_scope":scope},
            "limits": [scope_note,
                       "공개 출처의 텍스트입니다. 논문의 주장을 독립적으로 검증한 결과는 아닙니다.",
                       "표·그림·보충자료의 의미는 평탄화된 텍스트만으로 판단하지 않고 표시한 원본 위치를 확인해야 합니다.",
                       "반환된 XML 전체를 보존했습니다. 문서의 선언된 표·인용 수와 실제 반환한 내용, 모델에 전달·검토한 범위는 구분합니다."]}


def read_article(arguments):
    pmc_id = arguments["pmc_id"].upper()
    if not re.fullmatch(r"PMC[0-9]+", pmc_id):
        raise ValueError("검색 결과에서 확인한 PMC ID가 필요합니다.")
    urls = [f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmc_id}/fullTextXML",
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id={pmc_id.removeprefix('PMC')}" ]
    attempts = []
    for index, url in enumerate(urls):
        try:
            raw, receipt = fetch(url)
        except urllib.error.HTTPError as exc:
            attempts.append({'url': url, 'status': 'failed', 'http_status': exc.code,
                'error_type': type(exc).__name__, 'error': str(exc)[:250]})
            # This is an explicitly named official API, not a bypass of an
            # authorization challenge or a retry loop against the same service.
            if index == 0 and exc.code in (404, 500, 502, 503, 504):
                continue
            break
        except (urllib.error.URLError, TimeoutError) as exc:
            attempts.append({'url': url, 'status': 'failed', 'error_type': type(exc).__name__, 'error': str(exc)[:250]})
            if index == 0:
                continue
            break
        # A wrong/missing identity, unsafe XML or malformed document is an
        # integrity failure. It does not trigger another retrieval route.
        result = parse_article(raw, pmc_id, receipt)
        attempts.append({'url': url, 'status': result['status'], 'source': receipt})
        result['access_attempts'] = attempts
        result['retrieval_policy'] = 'Europe PMC JATS; one official NCBI EFetch alternative after an access/service gap. Identity, permissions and original XML preserved; no authentication bypass.'
        return result
    return {'status': 'failed', 'semantic_type': 'published_full_text', 'pmc_id': pmc_id,
        'rows': [], 'access_attempts': attempts, 'error': '공개 원문 접근을 완료하지 못했습니다.',
        'limits': ['접근 실패는 논문의 주장에 반하는 근거가 아닙니다. 초록과 실제 원문 열람 범위를 구분해 주세요.']}
