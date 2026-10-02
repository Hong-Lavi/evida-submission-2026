"""Navigate preserved bibliography and in-text locators without fetching a citation."""
import xml.etree.ElementTree as ET

from .public_evidence import article_presentation


def reference_view(value, reference_ids, offset, limit):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError('참고문헌 조회 범위를 확인해 주세요.')
    if (not isinstance(reference_ids,list) or len(reference_ids)>50
            or any(not isinstance(i,str) or not i or len(i)>200 for i in reference_ids)):
        raise ValueError('원문에 표시된 참고문헌 ID를 선택해 주세요.')
    references = value.get('references')
    if not isinstance(references,list):
        raise ValueError('이 원문에는 보존된 참고문헌 목록이 없습니다.')
    presented = article_presentation(value)
    nodes = []
    raw = value.get('original_xml')
    if raw and '<!ENTITY' not in raw.upper():
        try:
            parsed = ET.fromstring(raw)
            candidates = parsed.findall('.//ref-list/ref')
            text = lambda n:' '.join(''.join(n.itertext()).split())
            if len(candidates)==len(references) and all(
                    r.get('id')==n.get('id') and r.get('text')==text(n)
                    for r,n in zip(references,candidates)):
                nodes = candidates
        except ET.ParseError: pass
    rows = []
    for i,reference in enumerate(references):
        if reference_ids and reference.get('id') not in reference_ids: continue
        row = {'row_id':f"{value.get('pmc_id','article')}:reference:{i}",
            'original_reference_index':i,'reference_id':reference.get('id'),
            'text':reference.get('text'),'source_pointer':['references',i],
            'article_ids':[],'external_links':[],'citation_contexts':[],
            'bibliography_entry_is_not_source_reading':True}
        if nodes:
            node=nodes[i]
            display=node.find('.//mixed-citation')
            if display is not None:
                row['display_citation']=text(display)
                row['display_citation_origin']='original_xml/ref-list/ref/citation-alternatives-or-direct/mixed-citation'
            row['article_ids']=[{'type':n.get('pub-id-type'),'value':text(n)} for n in node.iter()
                                if n.tag.rsplit('}',1)[-1]=='pub-id']
            row['external_links']=[{'url':n.get('{http://www.w3.org/1999/xlink}href'),'text':text(n)}
                                   for n in node.iter() if n.tag.rsplit('}',1)[-1]=='ext-link']
            row['original_label']=text(node.find('label')) if node.find('label') is not None else None
        for block_index,block in enumerate(presented.get('rows',[])):
            for marker in block.get('citation_markers',[]):
                if reference.get('id') and reference['id'] in marker['reference_ids']:
                    row['citation_contexts'].append({'row_id':block.get('row_id'),'offset':block_index,
                        'xml_id':block.get('xml_id'),'section':block.get('section'),'citation_label':marker['label']})
        rows.append(row)
    known={r.get('id') for r in references}
    return {'status':'succeeded','view_kind':'article_references','pmc_id':value.get('pmc_id'),
        'title':value.get('title'),'source':value.get('source'), 'rows':rows[offset:offset+limit],
        'total_rows':len(rows),'source_total_references':len(references),'offset':offset,
        'has_more':offset+limit<len(rows),'selected_reference_ids':reference_ids,
        'unresolved_reference_ids':[i for i in reference_ids if i not in known],
        'exact_xml_enrichment':bool(nodes),'original_article_unchanged':True,
        'citation_context_mapping':'checked_preserved_blocks' if all('citation_markers' in r for r in presented.get('rows',[])) else 'unavailable_for_historical_block_layout',
        'limits':['인용 목록과 본문의 위치를 읽었습니다. 인용된 논문 자체를 읽거나 그 주장을 검증한 것은 아닙니다.',
                  '목록 밖 문헌은 미검색입니다. DOI·PMID 등 실제 식별자로 다음 원전 검색·읽기를 이어갈 수 있습니다.']}
