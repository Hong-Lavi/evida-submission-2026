"""Independent anonymous PubMed discovery/abstracts. Never a full-text reader."""
from __future__ import annotations
import base64
from contextlib import contextmanager
from datetime import datetime,timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BASE='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
TIMEOUT_SECONDS=20
MAX_BYTES=2*1024*1024
RATE_INTERVAL_SECONDS=1.1
LIMITS=['Search hits are identifiers, abstracts are publication abstracts, and neither is full text or independent confirmation.',
 'Failure or missing abstracts are not zero scientific evidence. Search pagination and untranslated/unreturned records stay explicit.',
 'Primary publication IDs exclude cited-reference IDs. PubMed content and abstracts retain original rights; NCBI access is not a blanket reuse license.',
 'Current PubMed responses are not historical version snapshots. as_of and supplied_only scopes cannot acquire new records through this tool.']

def digest(raw):return hashlib.sha256(raw).hexdigest()
def guard_scope(scope):
    if scope and (scope.get('mode') in ('supplied_only','provided_only') or scope.get('as_of')):
        raise ValueError('PubMed 새 조회는 제공자료 전용/기준일 연구에서 실행하지 않습니다. 당시 판본이 확인된 보존 자료를 사용하세요. 현재 응답을 과거 판본으로 가장하지 않습니다.')

def validate(tool,args):
    if tool=='pubmed_search':
        if set(args)!={'query','offset','limit'} or not isinstance(args['query'],str) or not args['query'].strip() or len(args['query'])>1500:
            raise ValueError('명시한 PubMed 검색식과 offset/limit을 확인하세요.')
        if type(args['offset'])is not int or not 0<=args['offset']<=9999 or type(args['limit'])is not int or not 1<=args['limit']<=20:
            raise ValueError('PubMed 검색 페이지는 offset0–9999, limit1–20입니다.')
        if args['offset']+args['limit']>10000:raise ValueError('PubMed ESearch의 처음10,000개 범위만 직접 페이지 조회합니다.')
    elif tool=='pubmed_abstracts':
        if set(args)!={'artifact_id','source_artifact_sha256','pmids'} or not re.fullmatch(r'[a-f0-9]{64}',args.get('source_artifact_sha256','')):
            raise ValueError('보존 검색 artifact의 실제 SHA와 선택 PMID를 확인하세요.')
        ids=args['pmids']
        if not isinstance(ids,list) or not 1<=len(ids)<=20 or len(set(ids))!=len(ids) or any(not isinstance(v,str)or not re.fullmatch(r'[1-9][0-9]{0,9}',v)for v in ids):
            raise ValueError('중복 없는 실제 검색 PMID1–20개를 선택하세요.')
    else:raise ValueError('Unknown PubMed operation.')

def prepare_abstracts(source,args):
    validate('pubmed_abstracts',args)
    actual=digest(source['content'])
    if source['id']!=args['artifact_id'] or source['kind']!='pubmed_search' or actual!=source['sha256'] or actual!=args['source_artifact_sha256']:
        raise ValueError('같은 연구에 보존한 PubMed 검색 원바이트와 SHA를 선택하세요.')
    body=json.loads(source['content'])
    if body.get('status')!='succeeded' or body.get('semantic_type')!='pubmed_search_hits':raise ValueError('성공한 원 PubMed 검색 결과가 필요합니다.')
    native=body.get('native_responses',[])
    if len(native)!=1 or digest(base64.b64decode(native[0]['base64'],validate=True))!=native[0]['sha256']:
        raise ValueError('PubMed 검색의 원 응답 바이트 결합이 다릅니다.')
    ids=[r['pmid']for r in body['rows']]
    original=json.loads(base64.b64decode(native[0]['base64']))['esearchresult'].get('idlist',[])
    if ids!=original or not set(args['pmids'])<=set(ids):raise ValueError('선택 PMID가 이 실제 검색 반환 페이지에 없습니다.')
    return {'search_artifact_id':source['id'],'search_artifact_sha256':actual,
            'search_response_sha256':native[0]['sha256'],'pmids':args['pmids']}

@contextmanager
def rate_slot(path):
    # Internal Runner path only, never a caller-supplied path/command. The same
    # product's independent PubMed workers share one conservative anonymous rate.
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(path,os.O_CREAT|os.O_RDWR|os.O_CLOEXEC|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'r+')as lock:
        if os.fstat(lock.fileno()).st_uid!=os.getuid() or not stat.S_ISREG(os.fstat(lock.fileno()).st_mode):raise ValueError('Invalid internal NCBI rate lock.')
        fcntl.flock(lock,fcntl.LOCK_EX)
        try:
            value=lock.read(128).strip();previous=float(value)if value else 0
            delay=RATE_INTERVAL_SECONDS-(time.time()-previous)
            if delay>0:time.sleep(min(delay,RATE_INTERVAL_SECONDS))
            lock.seek(0);lock.truncate();lock.write(str(time.time()));lock.flush()
            yield
        finally:fcntl.flock(lock,fcntl.LOCK_UN)

def request(endpoint,params,work,rate_lock):
    if endpoint not in ('esearch.fcgi','efetch.fcgi'):raise ValueError('Fixed PubMed endpoint required.')
    params={**params,'tool':'EVIDA_pubmed'}
    url=BASE+endpoint+'?'+urllib.parse.urlencode(params)
    started=time.monotonic();receipt={'url':url,'retrieved_at':datetime.now(timezone.utc).isoformat(),
      'timeout_seconds':TIMEOUT_SECONDS,'response_limit_bytes':MAX_BYTES,'retries':0,'api_key_used':False,
      'anonymous_rate_interval_seconds':RATE_INTERVAL_SECONDS}
    class FixedRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            target=urllib.parse.urlparse(newurl)
            if target.scheme!='https'or target.hostname!='eutils.ncbi.nlm.nih.gov':raise ValueError('PubMed redirected outside its explicit official API.')
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    try:
        with rate_slot(rate_lock):
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),FixedRedirect())
            req=urllib.request.Request(url,headers={'User-Agent':'EVIDA/anonymous-public-research','Accept':'application/json, application/xml'})
            with opener.open(req,timeout=TIMEOUT_SECONDS)as response:
                raw=response.read(MAX_BYTES+1);receipt.update(http_status=response.status,resolved_url=response.url,content_type=response.headers.get('Content-Type'))
        if len(raw)>MAX_BYTES:raise ValueError('PubMed response exceeds the explicit byte bound.')
        receipt.update(bytes=len(raw),sha256=digest(raw),elapsed_seconds=round(time.monotonic()-started,6))
        name='search.json'if endpoint=='esearch.fcgi'else'abstracts.xml';path=Path(work)/name;tmp=path.with_suffix(path.suffix+'.part');tmp.write_bytes(raw);tmp.replace(path)
        return raw,receipt
    except Exception as exc:
        receipt.update(status='failed',error_type=type(exc).__name__,error=str(exc)[:500],http_status=getattr(exc,'code',receipt.get('http_status')),elapsed_seconds=round(time.monotonic()-started,6))
        return None,receipt

def article_rows(raw,requested):
    root=ET.fromstring(raw);found={}
    for ordinal,a in enumerate(root.findall('PubmedArticle'),1):
        def text(node):return ' '.join(''.join(node.itertext()).split())if node is not None else None
        pmid=text(a.find('./MedlineCitation/PMID'))
        if pmid not in requested:raise ValueError('PubMed returned a primary PMID outside the exact request.')
        if pmid in found:raise ValueError('PubMed returned duplicate primary PMID records.')
        primary={}
        for item in a.findall('./PubmedData/ArticleIdList/ArticleId'):
            key=item.get('IdType');v=(item.text or'').strip()
            if key in primary and primary[key]!=v:raise ValueError('Conflicting primary publication identifiers.')
            primary[key]=v
        if primary.get('pubmed')and primary['pubmed']!=pmid:raise ValueError('Primary PMID identifiers disagree.')
        pmc=primary.get('pmc');pmc=pmc if pmc and re.fullmatch(r'PMC[0-9]+',pmc)else None
        record_locator=f'/PubmedArticleSet/PubmedArticle[{ordinal}]'
        blocks=[]
        for n,e in enumerate(a.findall('./MedlineCitation/Article/Abstract/AbstractText'),1):
            statement=text(e)or'';blocks.append({'label':e.get('Label')or e.get('NlmCategory')or'abstract',
                'text':statement,'locator':record_locator+f'/MedlineCitation/Article/Abstract/AbstractText[{n}]',
                'normalized_text_sha256':digest(statement.encode())})
        row={'row_id':f'pubmed:{pmid}:abstract_record','pmid':pmid,'pmc_id':pmc,'doi':primary.get('doi'),
            'article_ids':{'pmid':pmid,**({'pmcid':pmc}if pmc else{}),**({'doi':primary['doi']}if primary.get('doi')else{})},
            'title':text(a.find('./MedlineCitation/Article/ArticleTitle')),
            'journal':text(a.find('./MedlineCitation/Article/Journal/Title')),
            'publication_date_text':text(a.find('./MedlineCitation/Article/Journal/JournalIssue/PubDate')),
            'abstract':'\n'.join(b['text']for b in blocks),'abstract_blocks':blocks,
            'copyright_information':text(a.find('./MedlineCitation/Article/Abstract/CopyrightInformation')),
            'scope':'publication_abstract_not_full_text','status':'returned'if blocks else'abstract_not_reported',
            'full_text_returned':False,'cited_reference_count':len(a.findall('./PubmedData/ReferenceList/Reference')),
            'source_locator':record_locator,'response_sha256':digest(raw),
            'element_serialization_sha256':digest(ET.tostring(a,encoding='utf-8')),
            'primary_id_policy':'Direct PubmedData/ArticleIdList only; cited-reference IDs excluded.'}
        found[pmid]=row
    return [found.get(pmid,{'row_id':f'pubmed:{pmid}:not_returned','pmid':pmid,'status':'record_not_returned','scope':'requested_identifier_only','full_text_returned':False})for pmid in requested]

def retrieve(tool,args,work,rate_lock,scope=None,binding=None):
    guard_scope(scope);validate(tool,args);work=Path(work);work.mkdir(parents=True,exist_ok=False)
    (work/'progress.json').write_text(json.dumps({'status':'requesting','tool':tool,'model_calls':0}))
    if tool=='pubmed_search':endpoint='esearch.fcgi';params={'db':'pubmed','term':args['query'],'retmode':'json','retstart':args['offset'],'retmax':args['limit']}
    else:
        if not binding or binding['pmids']!=args['pmids']:raise ValueError('PubMed abstract request requires verified search provenance.')
        endpoint='efetch.fcgi';params={'db':'pubmed','id':','.join(args['pmids']),'retmode':'xml'}
    raw,source=request(endpoint,params,work,rate_lock)
    if raw is None:result={'status':'failed','semantic_type':'pubmed_access_failure','rows':[],'source':source,'returned_count':None,'error':source['error'],'error_type':source['error_type'],'failure_is_not_zero_hits':True}
    else:
        native={'sha256':digest(raw),'bytes':len(raw),'base64':base64.b64encode(raw).decode(),'media_type':source.get('content_type'),'source':source}
        try:
            if tool=='pubmed_search':
                body=json.loads(raw);data=body.get('esearchresult')
                if not isinstance(data,dict)or data.get('ERROR')or body.get('error'):raise ValueError('PubMed did not return a valid search result.')
                ids=data.get('idlist');count=int(data['count'])
                if not isinstance(ids,list)or len(ids)!=len(set(ids))or any(not re.fullmatch(r'[1-9][0-9]{0,9}',v)for v in ids):raise ValueError('PubMed returned invalid/duplicate PMID hits.')
                rows=[{'row_id':f'pubmed:{p}:search_hit','pmid':p,'article_ids':{'pmid':p},'scope':'identifier_search_hit_only','abstract_returned':False,'full_text_returned':False,'response_sha256':digest(raw)}for p in ids]
                result={'status':'succeeded','semantic_type':'pubmed_search_hits','query':args['query'],'query_translation':data.get('querytranslation'),'source':source,
                  'rows':rows,'summary':{'returned':len(rows),'matching_hits':count,'offset':args['offset'],'limit':args['limit']},'has_more':args['offset']+len(rows)<count,'native_responses':[native]}
            else:
                rows=article_rows(raw,args['pmids']);missing=[r['pmid']for r in rows if r['status']=='record_not_returned'];result={'status':'partial'if missing else'succeeded','semantic_type':'pubmed_publication_abstracts',
                  'source':source,'search_binding':binding,'rows':rows,'summary':{'requested':len(args['pmids']),'returned_records':len(rows)-len(missing),'missing_pmids':missing,'abstracts_present':sum(bool(r.get('abstract_blocks'))for r in rows),'full_text_records':0},'native_responses':[native]}
        except (ValueError,KeyError,TypeError,ET.ParseError)as exc:
            result={'status':'failed','semantic_type':'pubmed_response_parse_failure','rows':[],'source':source,'returned_count':None,'error':str(exc)[:700],'error_type':type(exc).__name__,'failure_is_not_zero_hits':True,'native_responses':[native]}
    result['limits']=LIMITS;result['model_calls']=0;result['gpu_used']=False
    (work/'progress.json').write_text(json.dumps({'status':result['status'],'rows':len(result['rows']),'model_calls':0}));return result
