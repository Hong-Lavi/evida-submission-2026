import base64, hashlib, json, os, subprocess, unittest
from unittest.mock import patch, Mock
from evida import web_sources as w
from evida import web_sources_worker as worker
URL='https://www.frontiersin.org/journals/pharmacology/articles/10.1000/test/full'
TEXT=' '.join(['A scientific paragraph has enough different words to describe observations methods limitations interpretation controls measurements references and uncertainties clearly.']*4)
HTML=('<html><head><title>Example</title><meta name="citation_doi" content="10.1000/test"></head><body>'+''.join('<p>'+TEXT+'</p>' for _ in range(4))+'</body></html>').encode()
def fetched(raw=HTML,status='response_received',http=200):
 return {'acquisition_status':status,'original_response_base64':base64.b64encode(raw).decode(),'source':{'url':URL,'resolved_url':URL,'http_status':http,'content_type':'text/html','content_encoding':'','sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'access_attempts':[]}}
def extracted():
 return {'acquisition_status':'text_acquired','title':'Example','permissions':[],'identity':{'status':'unique','normalized_dois':['10.1000/test']},'extractor':{'version':'2.0.0'},'blocks':[TEXT],'substantive_paragraphs':4}
class WebSourceTests(unittest.TestCase):
 def test_url_boundary(self):
  for u in ['http://www.frontiersin.org/','https://localhost/','https://127.0.0.1/','https://[::1]/','https://a:b@www.frontiersin.org/','https://@www.frontiersin.org/','https://www.frontiersin.org:444/','https://www.frontiersin.org.evil.test/','https://www.frontiersin.org\\@evil.test/','https://www.frontiersin.org/authorize','https://www.frontiersin.org/\nfoo','file:///etc/passwd']:
   with self.subTest(url=u),self.assertRaises(ValueError):w.validate_url(u)
 def test_dns_public_and_private_mixed_rejected(self):
  for ip in ['127.0.0.1','10.1.1.1','169.254.169.254','::1','::ffff:127.0.0.1','ff02::1','2002:7f00:1::']:
   with self.subTest(ip=ip),patch.object(worker.socket,'getaddrinfo',return_value=[(2,1,6,'',('193.62.193.80',443)),(2,1,6,'',(ip,443))]):
    with self.assertRaises(ValueError):worker._addresses('www.frontiersin.org')
 def test_success_rows_and_recovery_stay_separate(self):
  with patch.object(w,'_worker',side_effect=[fetched(),extracted()]),patch.object(w,'_recover_identifier',return_value={'status':'matched','article_ids':{'pmcid':'PMC1'},'full_text_read':False}):r=w.read_webpage({'url':URL})
  self.assertEqual(r['status'],'succeeded');self.assertEqual(r['rows'][0]['text'],TEXT);self.assertEqual(r['rows'][0]['sha256'],hashlib.sha256(TEXT.encode()).hexdigest());self.assertEqual(r['article_ids'],{'doi':'10.1000/test'});self.assertEqual(r['content_coverage']['read_blocks'],[]);self.assertIn('not_dom_anchor',r['content_coverage']['locator_type'])
 def test_refusal_no_extraction_or_recovery(self):
  for status,http in [('access_denied',403),('access_denied',429),('redirect_refused',303)]:
   with patch.object(w,'_worker',return_value=fetched(status=status,http=http)) as run,patch.object(w,'_recover_identifier') as recover:
    r=w.read_webpage({'url':URL});self.assertEqual(r['rows'],[]);self.assertEqual(run.call_count,1);recover.assert_not_called()
 def test_challenge_never_recovered(self):
  e=extracted();e.update(acquisition_status='challenge',blocks=[])
  with patch.object(w,'_worker',side_effect=[fetched(),e]),patch.object(w,'_recover_identifier') as recover:
   r=w.read_webpage({'url':URL});self.assertEqual(r['status'],'failed');self.assertEqual(r['rows'],[]);recover.assert_not_called()
 def test_metadata_only_is_partial(self):
  e=extracted();e.update(acquisition_status='metadata_only',blocks=[])
  with patch.object(w,'_worker',side_effect=[fetched(),e]):r=w.read_webpage({'url':URL});self.assertEqual(r['status'],'partial');self.assertEqual(r['rows'],[])
 def test_conflicting_identity_never_recovered(self):
  e=extracted();e['identity']={'status':'conflicting','normalized_dois':['10.1000/a','10.1000/b']}
  with patch.object(w,'_worker',side_effect=[fetched(),e]),patch.object(w,'_recover_identifier') as recover:
   r=w.read_webpage({'url':URL});self.assertEqual(r['article_ids'],{});recover.assert_not_called()
 def test_non_html_and_encoding_not_extracted(self):
  for k,v in [('content_type','application/pdf'),('content_encoding','gzip')]:
   f=fetched();f['source'][k]=v
   with patch.object(w,'_worker',return_value=f) as run:self.assertEqual(w.read_webpage({'url':URL})['rows'],[]);self.assertEqual(run.call_count,1)
 def test_worker_timeout_typed(self):
  with patch.object(w.subprocess,'run',side_effect=subprocess.TimeoutExpired('worker',1)):self.assertEqual(w._worker('extract',{},.1)['worker_error'],'wall_timeout')
 def test_timeout_keeps_received_http_progress(self):
  progress=b'{"progress":{"url":"https://www.nature.com/a","access_attempts":[{"http_status":200,"response_complete":false}]}}\n'
  with patch.object(w.subprocess,'run',side_effect=subprocess.TimeoutExpired('worker',1,output=progress)):
   r=w._worker('fetch',{},.1);self.assertEqual(r['source']['access_attempts'][0]['http_status'],200);self.assertFalse(r['source']['access_attempts'][0]['response_complete'])
 def test_pinned_socket_avoids_second_dns_and_preserves_sni(self):
  sock=Mock();tls=Mock();tls.getpeername.return_value=('193.62.193.80',443);context=Mock();context.wrap_socket.return_value=tls
  with patch.object(worker.ssl,'create_default_context',return_value=context),patch.object(worker.socket,'socket',return_value=sock),patch.object(worker.socket,'getaddrinfo',side_effect=AssertionError('second DNS forbidden')):
   conn=worker.PinnedHTTPS('www.frontiersin.org','193.62.193.80');conn.connect()
   sock.connect.assert_called_once_with(('193.62.193.80',443));context.wrap_socket.assert_called_once_with(sock,server_hostname='www.frontiersin.org')
 def test_worker_does_not_copy_login_environment(self):
  with patch.dict(os.environ,{'SECRET_TOKEN':'never-copy'}),patch.object(w.subprocess,'run',return_value=Mock(returncode=0,stdout=b'{}')) as run:w._worker('extract',{},1);self.assertNotIn('SECRET_TOKEN',run.call_args.kwargs['env'])
 def test_recovery_exact_and_unambiguous(self):
  for hits,status in [([{'doi':'10.1000/wrong','pmcid':'PMC1'}],'unresolved'),([{'doi':'10.1000/test','pmcid':'PMC1'},{'doi':'10.1000/test','pmcid':'PMC2'}],'unresolved'),([{'doi':'10.1000/test','pmcid':'PMC1','source':'MED','id':'123'}],'matched')]:
   f=fetched(json.dumps({'hitCount':len(hits),'resultList':{'result':hits}}).encode())
   with patch.object(w,'_worker',return_value=f):self.assertEqual(w._recover_identifier('10.1000/test',5)['status'],status)
 def test_recovery_truncated_inventory_unresolved(self):
  b={'hitCount':21,'resultList':{'result':[{'doi':'10.1000/test','pmcid':'PMC1'}]}}
  with patch.object(w,'_worker',return_value=fetched(json.dumps(b).encode())):self.assertEqual(w._recover_identifier('10.1000/test',5)['status'],'unresolved')
 def test_redirect_target_not_connected(self):
  response=Mock(status=303);response.read.return_value=b'go';response.getheader.side_effect=lambda k,d=None:{'Location':'https://idp.nature.com/authorize'}.get(k,d)
  conn=Mock();conn.getresponse.return_value=response
  with patch.object(worker,'_addresses',return_value=['193.62.193.80']),patch.object(worker,'PinnedHTTPS',return_value=conn) as cls:
   r=worker.fetch({'url':URL});self.assertEqual(r['acquisition_status'],'redirect_refused');self.assertEqual(cls.call_count,1);self.assertEqual(r['source']['access_attempts'][0]['sha256'],hashlib.sha256(b'go').hexdigest())
 def test_byte_cap(self):
  response=Mock(status=200);response.read.return_value=b'x'*(w.MAX_DOWNLOAD+1);response.getheader.return_value='';conn=Mock();conn.getresponse.return_value=response
  with patch.object(worker,'_addresses',return_value=['193.62.193.80']),patch.object(worker,'PinnedHTTPS',return_value=conn):r=worker.fetch({'url':URL});self.assertEqual(r['acquisition_status'],'download_limit');self.assertNotIn('original_response_base64',r)
 def test_doi_normalization_does_not_strip_version(self):self.assertEqual(w.normalize_doi('https://doi.org/10.7554/eLife.102451.3'),'10.7554/elife.102451.3')
class LocalExtractionTests(unittest.TestCase):
 def extract(self,html):return w._worker('extract',{'original_response_base64':base64.b64encode(html).decode(),'url':URL},25)
 def test_navigation_and_garbage_rejected(self):
  for raw in [b'<html><title>Menu</title><nav>'+b'<a href="/">Menu link</a>'*2000+b'</nav></html>',b'<html><title>X</title>'+b'<p>'+b'lorem '*10000+b'</p></html>']:self.assertEqual(self.extract(raw)['blocks'],[])
 def test_challenge_with_doi_is_not_text(self):
  r=self.extract(HTML.replace(b'<title>Example</title>',b'<title>Client Challenge</title>'));self.assertEqual(r['acquisition_status'],'challenge');self.assertEqual(r['blocks'],[])
 def test_doi_conflict_and_missing_preserved(self):
  for raw,status in [(HTML.replace(b'</head>',b'<meta name="citation_doi" content="10.1000/other"></head>'),'conflicting'),(HTML.replace(b'name="citation_doi"',b'name="reference_doi"'),'unknown'),(HTML.replace(b'</head>',b'<meta name="citation_doi" content="https://doi.org/10.1000/TEST"></head>'),'unique')]:self.assertEqual(self.extract(raw)['identity']['status'],status)
 def test_body_reference_metadata_is_not_primary(self):
  raw=HTML.replace(b'</body>',b'<meta name="citation_doi" content="10.1000/reference"></body>')
  self.assertEqual(self.extract(raw)['identity']['normalized_dois'],['10.1000/test'])
 def test_versions_resources_and_local_text(self):
  r=self.extract(HTML);self.assertEqual(r['extractor']['version'],'2.0.0');self.assertIn('worker_peak_rss_kib',r['resources']);self.assertEqual(r['acquisition_status'],'text_acquired')
if __name__=='__main__':unittest.main()
