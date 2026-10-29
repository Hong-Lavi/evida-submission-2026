import base64,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from evida import ncbi_pubmed as pub
sha=lambda x:hashlib.sha256(x).hexdigest()
def art(id,kind,body):
 raw=body if isinstance(body,bytes)else json.dumps(body).encode();return {'id':id,'kind':kind,'content':raw,'sha256':sha(raw),'meta':{}}
def search():
 raw=b'{"esearchresult":{"count":"1","idlist":["123"]}}';return art('s','pubmed_search',{'status':'succeeded','semantic_type':'pubmed_search_hits','rows':[{'pmid':'123'}],'native_responses':[{'base64':base64.b64encode(raw).decode(),'sha256':sha(raw)}]})
class Tests(unittest.TestCase):
 def test_primary_ids_are_not_cited_reference_ids(self):
  raw=b'<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID><Article><ArticleTitle>T</ArticleTitle></Article></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType="pmc">PMC123</ArticleId></ArticleIdList><ReferenceList><Reference><ArticleIdList><ArticleId IdType="pmc">PMC999</ArticleId></ArticleIdList></Reference></ReferenceList></PubmedData></PubmedArticle></PubmedArticleSet>';r=pub.article_rows(raw,['123','456']);self.assertEqual(r[0]['pmc_id'],'PMC123');self.assertNotIn('PMC999',json.dumps(r));self.assertEqual(r[0]['status'],'abstract_not_reported');self.assertFalse(r[0]['full_text_returned']);self.assertEqual(r[1]['status'],'record_not_returned')
 def test_actual_search_sha_and_native_ids(self):
  s=search();a={'artifact_id':'s','source_artifact_sha256':s['sha256'],'pmids':['123']};self.assertEqual(pub.prepare_abstracts(s,a)['pmids'],['123'])
  for bad in [{**a,'source_artifact_sha256':'0'*64},{**a,'pmids':['999']}]:
   with self.assertRaises(ValueError):pub.prepare_abstracts(s,bad)
  b=json.loads(s['content']);b['rows'][0]['pmid']='999';bad=art('s','pubmed_search',b)
  with self.assertRaises(ValueError):pub.prepare_abstracts(bad,{**a,'source_artifact_sha256':bad['sha256'],'pmids':['999']})
 def test_scope_blocks_before_network(self):
  for scope in [{'mode':'supplied_only'},{'mode':'provided_only'},{'mode':'unrestricted','as_of':'2020-01-01'}]:
   with patch.object(pub,'request')as network,tempfile.TemporaryDirectory()as t:
    with self.assertRaises(ValueError):pub.retrieve('pubmed_search',{'query':'x','offset':0,'limit':1},Path(t)/'x',Path(t)/'lock',scope)
    network.assert_not_called()
 def test_failure_is_not_zero_hits(self):
  a={'query':'x','offset':0,'limit':1}
  with tempfile.TemporaryDirectory()as t,patch.object(pub,'request',return_value=(None,{'error':'HTTP503','error_type':'HTTPError'})):
   r=pub.retrieve('pubmed_search',a,Path(t)/'x',Path(t)/'lock');self.assertEqual(r['status'],'failed');self.assertIsNone(r['returned_count'])
  raw=b'{"esearchresult":{"count":"0","idlist":[]}}'
  with tempfile.TemporaryDirectory()as t,patch.object(pub,'request',return_value=(raw,{'http_status':200})):
   r=pub.retrieve('pubmed_search',a,Path(t)/'x',Path(t)/'lock');self.assertEqual(r['status'],'succeeded');self.assertEqual(r['summary']['matching_hits'],0)
 def test_parse_failure_retains_original_bytes(self):
  raw=b'not XML';a={'artifact_id':'s','source_artifact_sha256':'a'*64,'pmids':['123']}
  with tempfile.TemporaryDirectory()as t,patch.object(pub,'request',return_value=(raw,{'http_status':200})):
   r=pub.retrieve('pubmed_abstracts',a,Path(t)/'x',Path(t)/'lock',binding={'pmids':['123']});self.assertEqual(r['status'],'failed');self.assertEqual(base64.b64decode(r['native_responses'][0]['base64']),raw)
 def test_exact_named_bounds(self):
  for a in [{'query':'x','offset':0,'limit':21},{'query':'x','offset':9999,'limit':2},{'query':'x','offset':0,'limit':1,'url':'https://other'}]:
   with self.assertRaises(ValueError):pub.validate('pubmed_search',a)
if __name__=='__main__':unittest.main()
