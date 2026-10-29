"""Literal local/web source linkage; synthetic documents and stubbed chemical lookup."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evida.store import Store,dump
from evida.source_intake import extract,upload_metadata
from evida.source_candidates import checked_anchor,record,validate_resolution_sources
from evida.research_loop import check_anchor
from evida.literature_compounds import collect
from evida.discovery import catalog
from tests.test_source_intake import pdf_fixture

TEXT='C6 (chemical example) changed the assay; the control did not respond.'


def upload(store,wid,raw,filename='synthetic.txt'):
    meta=upload_metadata(raw,filename,{'citation':'GhostName PMC999999 DOI 10.1234/unverified'})
    rid=store.add_artifact(wid,filename,'source_file',raw,meta,media='application/octet-stream',bump=False)
    value=extract(raw,rid,hashlib.sha256(raw).hexdigest(),meta)
    aid=store.add_artifact(wid,'Synthetic extracted source','source_document',dump(value).encode(),{'consumed_artifacts':[rid]},bump=False)
    return rid,aid,value


def web_source(store,wid):
    raw=('<html><p>'+TEXT+'</p></html>').encode();sha=hashlib.sha256(raw).hexdigest()
    value={'status':'succeeded','semantic_type':'webpage_text','acquisition_status':'text_acquired',
           'source':{'url':'https://example.org/synthetic','resolved_url':'https://example.org/synthetic-final','sha256':sha},
           'original_response_base64':base64.b64encode(raw).decode(),
           'content_coverage':{'scope':'extracted_webpage_text','complete_paper_verified':False,'tables_figures_supplements_verified':False},
           'rows':[{'row_id':'GhostName','text':TEXT,'sha256':hashlib.sha256(TEXT.encode()).hexdigest(),'citation':'GhostName'}]}
    aid=store.add_artifact(wid,'Synthetic saved webpage','webpage',dump(value).encode(),{},bump=False)
    return aid,value


def arguments(aid,name='C6',quote=TEXT,index=0):
    anchor={'artifact_id':aid,'row_index':index,'quote':quote}
    return {'question':'Synthetic source candidate check','rows':[{'name':name,'role':'candidate','modality':'small_molecule','target_context':'Synthetic assay',
        'mention':anchor,'identity':{'name_type':'source_local','lookup_name':'chemical example','lookup_anchor':anchor},
        'membership_reason':'Source assertion only, not efficacy.','conditions':['Synthetic source conditions'],'next_check':'Check chemical identity and counterevidence.'}]}


class LiteralSourceAssertionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'db');self.wid=self.store.create('Synthetic source assertion')['id']

    def test_upload_namespace_and_raw_byte_range_survive_reextraction_and_paragraphs(self):
        raw=b'\xef\xbb\xbf'+(TEXT+'\r\n\r\n'+TEXT+'\r\n').encode()
        rid,aid,value=upload(self.store,self.wid,raw)
        a=checked_anchor(self.store,self.wid,arguments(aid)['rows'][0]['mention'],'C6')
        b=checked_anchor(self.store,self.wid,arguments(aid,index=1)['rows'][0]['mention'],'C6')
        other=self.store.add_artifact(self.wid,'Re-extracted copy','source_document',dump(value).encode(),{},bump=False)
        c=checked_anchor(self.store,self.wid,arguments(other)['rows'][0]['mention'],'C6')
        self.assertEqual(a['namespace'],b['namespace']);self.assertEqual(a['namespace'],c['namespace'])
        self.assertTrue(a['namespace'].startswith('uploaded-sha256:'));self.assertNotIn('pmc:',a['namespace'])
        binding=a['source_binding'];loc=binding['location'];self.assertEqual(raw[loc['byte_start']:loc['byte_end']].decode(),value['rows'][0]['text'])
        self.assertFalse(binding['bibliographic_identity_verified']);self.assertEqual(binding['original']['artifact_id'],rid)
        _,other,_=upload(self.store,self.wid,raw+b'Other document\r\n')
        self.assertNotEqual(a['namespace'],checked_anchor(self.store,self.wid,arguments(other)['rows'][0]['mention'],'C6')['namespace'])
        for index in (-1,99):
            with self.assertRaises(ValueError):checked_anchor(self.store,self.wid,arguments(aid,index=index)['rows'][0]['mention'],'C6')

    def test_web_document_namespace_retains_labels_across_blocks_and_reextraction(self):
        aid,value=web_source(self.store,self.wid)
        second='C6 (chemical example) had another reported observation.'
        raw=('<html><p>'+TEXT+'</p><p>'+second+'</p></html>').encode()
        value['original_response_base64']=base64.b64encode(raw).decode()
        value['source']['sha256']=hashlib.sha256(raw).hexdigest()
        value['rows'].append({'row_id':'second-block','text':second,'sha256':hashlib.sha256(second.encode()).hexdigest()})
        def save(v):
            return self.store.add_artifact(self.wid,'Synthetic preserved webpage','webpage',dump(v).encode(),{},bump=False)
        def assertion(aid,index=0,quote=TEXT):
            return record(self.store,self.wid,1,'synthetic',arguments(aid,index=index,quote=quote))['rows'][0]
        aid=save(value);first=assertion(aid);other_block=assertion(aid,1,second)
        self.assertEqual(first['candidate_id'],other_block['candidate_id'])
        reextracted=copy.deepcopy(value);reextracted['rows'][0]['row_id']='new-extraction-block-label'
        reextracted['extractor']={'version':'synthetic reextraction'}
        self.assertEqual(first['candidate_id'],assertion(save(reextracted))['candidate_id'])
        duplicate=arguments(aid);duplicate['rows'].append(arguments(aid,index=1,quote=second)['rows'][0])
        with self.assertRaisesRegex(ValueError,'중복'):record(self.store,self.wid,1,'synthetic',duplicate)
        different=copy.deepcopy(value);different['source']['resolved_url']='https://example.org/different-document'
        self.assertNotEqual(first['candidate_id'],assertion(save(different))['candidate_id'])
        changed=copy.deepcopy(value);changed_raw=raw+b'<!-- revised document -->'
        changed['original_response_base64']=base64.b64encode(changed_raw).decode()
        changed['source']['sha256']=hashlib.sha256(changed_raw).hexdigest()
        self.assertNotEqual(first['candidate_id'],assertion(save(changed))['candidate_id'])
        fallback=copy.deepcopy(value);fallback['source'].pop('resolved_url')
        by_requested=assertion(save(fallback))
        fallback['source']['resolved_url']=fallback['source']['url']
        self.assertEqual(by_requested['candidate_id'],assertion(save(fallback))['candidate_id'])
        no_url=copy.deepcopy(value);no_url['source'].pop('resolved_url');no_url['source'].pop('url')
        no_url_id=save(no_url);a=assertion(no_url_id);b=assertion(no_url_id,1,second)
        self.assertEqual(a['candidate_id'],b['candidate_id']);self.assertTrue(a['mention']['namespace'].startswith('artifact:'+no_url_id))
        self.assertNotEqual(a['candidate_id'],assertion(save(no_url))['candidate_id'])
        doi=copy.deepcopy(value);doi['article_ids']={'doi':'10.1234/verified-fixture'}
        self.assertEqual(assertion(save(doi))['mention']['namespace'],'doi:10.1234/verified-fixture')

    def test_literal_text_only_in_both_paths_and_legacy_table_cells_still_work(self):
        _,doc,value=upload(self.store,self.wid,(TEXT+'\n').encode())
        value['rows'][0]['citation']='GhostName';value['rows'][0]['pmc_id']='PMC999999'
        doc=self.store.add_artifact(self.wid,'GhostName','source_document',dump(value).encode(),{},bump=False)
        web,_=web_source(self.store,self.wid)
        for aid in (doc,web):
            bad={'artifact_id':aid,'row_index':0,'quote':'GhostName'}
            with self.assertRaises(ValueError):checked_anchor(self.store,self.wid,bad,'GhostName')
            self.assertEqual(check_anchor(self.store,self.wid,bad)['status'],'rejected')
            good=arguments(aid)['rows'][0]['mention']
            self.assertEqual(check_anchor(self.store,self.wid,good)['status'],'verified')
            self.assertIn('source_binding',checked_anchor(self.store,self.wid,good,'C6'))
        article=self.store.add_artifact(self.wid,'Legacy structured table','article',dump({'rows':[{'text':'C41.6','table_cells':[['C4','1.6']]}]}).encode(),{},bump=False)
        checked_anchor(self.store,self.wid,{'artifact_id':article,'row_index':0,'quote':'C4'},'C4')
        self.assertEqual(check_anchor(self.store,self.wid,{'artifact_id':article,'row_index':0,'quote':'C4'})['status'],'verified')

    def test_tampered_original_and_text_locator_rejected_before_resolution(self):
        rid,doc,value=upload(self.store,self.wid,(TEXT+'\n').encode())
        rec=record(self.store,self.wid,1,'fixture',arguments(doc))
        validate_resolution_sources(self.store,self.wid,[rec['artifact_id']])
        bad=copy.deepcopy(value);bad['rows'][0]['byte_end']-=1
        altered=self.store.add_artifact(self.wid,'Bad locator','source_document',dump(bad).encode(),{},bump=False)
        self.assertEqual(check_anchor(self.store,self.wid,arguments(altered)['rows'][0]['mention'])['status'],'rejected')
        with self.store.connect(True) as db:db.execute('UPDATE artifacts SET content=? WHERE id=?',(b'tampered',rid))
        with self.assertRaises(ValueError):validate_resolution_sources(self.store,self.wid,[rec['artifact_id']])
        self.assertEqual(check_anchor(self.store,self.wid,arguments(doc)['rows'][0]['mention'])['status'],'rejected')
        with self.assertRaises(ValueError):checked_anchor(self.store,self.wid,arguments(rid)['rows'][0]['mention'],'C6')

    def test_pdf_physical_pages_and_web_response_hash_preserved(self):
        rid,doc,value=upload(self.store,self.wid,pdf_fixture(),'synthetic.pdf')
        anchor={'artifact_id':doc,'row_index':0,'quote':'Synthetic source response'}
        with patch('pypdf.PdfReader', side_effect=AssertionError('No PDF reparse in anchor path')):
            bound=checked_anchor(self.store,self.wid,anchor,'Synthetic')['source_binding']
            self.assertEqual(check_anchor(self.store,self.wid,anchor)['status'],'verified')
        self.assertFalse(bound['verification']['text_reextracted'])
        self.assertEqual(bound['location']['page_number'],1);self.assertEqual(bound['original']['artifact_id'],rid)
        self.assertEqual(value['rows'][1]['page_number'],2);self.assertEqual(value['rows'][1]['text'],'')
        with self.assertRaises(ValueError):checked_anchor(self.store,self.wid,{**anchor,'row_index':1},'Synthetic')
        web,value=web_source(self.store,self.wid)
        bound=checked_anchor(self.store,self.wid,arguments(web)['rows'][0]['mention'],'C6')['source_binding']
        self.assertEqual(bound['original']['sha256'],value['source']['sha256'])
        self.assertFalse(bound['extraction']['content_coverage']['complete_paper_verified'])
        value['original_response_base64']=base64.b64encode(b'tampered').decode()
        altered=self.store.add_artifact(self.wid,'Changed web response','webpage',dump(value).encode(),{},bump=False)
        with self.assertRaises(ValueError):checked_anchor(self.store,self.wid,arguments(altered)['rows'][0]['mention'],'C6')

    def test_stubbed_resolution_retains_uploaded_provenance_and_unreviewed_candidate(self):
        _,doc,_=upload(self.store,self.wid,(TEXT+'\n').encode())
        saved=record(self.store,self.wid,1,'fixture',arguments(doc));artifact=self.store.artifact(self.wid,saved['artifact_id'])
        source={'artifact_id':artifact['id'],'sha256':artifact['sha256'],'kind':artifact['kind'],'value':json.loads(artifact['content'])}
        response={'PropertyTable':{'Properties':[{'CID':1,'SMILES':'CCO'}]}}
        with patch('evida.literature_compounds.fetch',return_value=(dump(response).encode(),{'url':'synthetic stub; no network'})):
            result=collect({'names':['C6'],'reason':'Synthetic identity transfer','target_context':'fixture'},[source])
        mention=result['rows'][0]['name_mentions'][0]
        self.assertEqual(mention['source_binding'],saved['rows'][0]['mention']['source_binding'])
        self.assertEqual(mention['quote'],TEXT);self.assertEqual(result['source_origins'],['researcher_upload'])
        self.assertFalse(result['rows'][0]['target_activity_verified'])
        self.store.add_artifact(self.wid,'Stubbed identity result','literature_compounds',dump(result).encode(),{},bump=False)
        molecule=next(o for o in catalog(self.store,self.wid)['options'] if o['kind']=='molecule')
        self.assertEqual(molecule['origin'],'uploaded_source_and_structure');self.assertIsNone(molecule['assessment'])
