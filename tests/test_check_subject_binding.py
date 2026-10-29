"""Exact-record software controls; no biological-equivalence claim."""
import copy,json,tempfile,unittest
from pathlib import Path
from evida.store import Store,dump
from evida.check_subject_binding import view
from evida.next_observation_binding import prepare,evaluate
from tests.test_next_observation import publish_fixture,result_fixture

def publish_subjects(store,wid,refs):
    from evida.finalization import commit
    from evida.hypothesis_review import prepare as review_prepare
    args,loop=publish_fixture(store,wid)
    prior=store.artifact(wid,args['artifact_id'])
    review=json.loads(store.artifact(wid,prior['meta']['finalization_records']['hypothesis_review'])['content'])['review']
    loop['next_checks'][1]['subject_refs']=copy.deepcopy(refs)
    rev=store.snapshot(wid)['rev'];record=review_prepare(store,wid,rev,review,loop)
    aid,ok=commit(store,wid,rev,'synthetic-subject-publication',{'based_on_state_rev':rev,'intent_records':[],'research_loop':loop},[record],[],None)
    assert ok
    args['artifact_id']=aid
    return args,loop

def keep_result(store,wid,value):
    aid=store.add_artifact(wid,'Synthetic conditional result','next_observation_selection',dump(value).encode(),{},bump=False)
    jid=store.enqueue(wid,store.snapshot(wid)['rev'],'next_observation_selection',{})
    store.finish_job(jid,'succeeded',aid)
    return aid

class CheckSubjectTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'test.db');self.wid=self.store.create('Synthetic subjects')['id']
        self.a=self.add({'rows':[{'candidate_id':'proposed-1','smiles':'CCO'}]})
        self.b=self.add({'rows':[{'candidate_id':'proposed-1','smiles':'CCC'}]})
        self.refs=[{'role':'candidate','artifact_id':self.a,'json_pointer':'/rows/0'}]
        self.args,self.loop=publish_subjects(self.store,self.wid,self.refs)
        self.parent=keep_result(self.store,self.wid,evaluate(prepare(self.store,self.wid,self.args)))
    def add(self,value,kind='analogue_proposal',wid=None):
        return self.store.add_artifact(wid or self.wid,'Synthetic raw',kind,dump(value).encode(),{},bump=False)
    def save(self,**fields):
        body={'kind':'observation','text':'Synthetic software control only','synthetic':True,'research_context':{'decision_id':self.args['artifact_id'],'check_id':'function','hypothesis_ids':['h'],'comparison':'unclear'},**fields}
        return self.store.command(self.wid,self.store.snapshot(self.wid)['rev'],'cmd-'+str(self.store.snapshot(self.wid)['rev']),body)['message_id']
    def result(self,mid,parent=None):
        return evaluate(prepare(self.store,self.wid,{'mode':'review_result','artifact_id':parent or self.parent,'source_artifact_ids':[],'problem':None,'result':result_fixture(message_id=mid)}))
    def test_exact_unknown_mismatch_and_attachments(self):
        for report,status,count in [(None,'unknown',3),(self.refs,'same_record',2),([{**self.refs[0],'artifact_id':self.b}],'mismatch',3)]:
            out=self.result(self.save(source_artifact_ids=[self.b],**({} if report is None else {'reported_subject_refs':report})))
            self.assertEqual(out['subject_guard']['comparison']['status'],status)
            self.assertEqual(len(out['summary']['retained_configuration_ids']),count)
            event=out['observed_events'][0];self.assertEqual(event['source_artifact_ids'],[self.b])
            self.assertIsInstance(event['subject_binding']['expected'],list)
            self.assertFalse(event['subject_binding']['comparison']['biological_identity_verified'])
            if status!='same_record':self.assertEqual(out['conditional_exclusions'],[])
        import jsonschema
        from evida.contracts import NEXT_CHECK
        jsonschema.validate(self.loop['next_checks'][1],NEXT_CHECK)
    def test_historical_target_chain_duplicate_and_correction(self):
        original=self.store.artifact(self.wid,self.args['artifact_id'])['content']
        publish_subjects(self.store,self.wid,[{**self.refs[0],'artifact_id':self.b}])
        mid=self.save(reported_subject_refs=self.refs);out=self.result(mid)
        self.assertEqual(out['subject_guard']['comparison']['status'],'same_record')
        self.assertEqual(self.store.artifact(self.wid,self.args['artifact_id'])['content'],original)
        parent=keep_result(self.store,self.wid,out)
        with self.assertRaisesRegex(ValueError,'반복'):self.result(mid,parent)
        with self.assertRaises(ValueError):self.result(self.save(kind='correction',reported_subject_refs=self.refs),parent)
        out=self.result(self.save(reported_subject_refs=[]),parent)
        self.assertEqual(len(out['summary']['retained_configuration_ids']),2)
        self.assertEqual(len(view(self.store,self.wid)),2)
    def test_rna_context_partial_report_and_chemistry(self):
        value={'reference':{'transcript_id':'ENSTsynthetic','version':8},'protocol':{'chemistry':'unknown'},'rows':[{'id':'g1','guide_5to3':'ACGU','chemistry':'unknown'}]}
        rna=self.add(value,'rna_candidate_generation');refs=[{'role':'candidate','artifact_id':rna,'json_pointer':'/rows/0'},{'role':'condition','artifact_id':rna,'json_pointer':'/reference'}]
        self.args,_=publish_subjects(self.store,self.wid,refs);self.parent=keep_result(self.store,self.wid,evaluate(prepare(self.store,self.wid,self.args)))
        out=self.result(self.save(reported_subject_refs=refs[:1]));snapshot=out['observed_events'][0]['subject_binding']['expected'][0]
        self.assertEqual(snapshot['context']['reference'],value['reference']);self.assertEqual(snapshot['snapshot']['chemistry'],'unknown')
        self.assertEqual(out['subject_guard']['comparison']['status'],'unknown')
        changed=copy.deepcopy(value);changed['rows'][0]['chemistry']='synthetic modification';other=self.add(changed,'rna_candidate_generation')
        out=self.result(self.save(reported_subject_refs=[{**refs[0],'artifact_id':other},refs[1]]))
        self.assertEqual(out['subject_guard']['comparison']['status'],'mismatch')
    def test_invalid_references_and_forgery_are_atomic(self):
        foreign=self.add({'rows':[{'id':'x'}]},wid=self.store.create('Foreign')['id'])
        internal=self.add({'rows':[{'id':'x'}]},'model_receipt');huge=self.add({'rows':[{'text':'x'*25000}]})
        bad=[None]+[[{**self.refs[0],'json_pointer':p}] for p in ('','/rows','/rows/01','/rows/-1','/rows/10','/guided_search/rows/0','/reference')]
        bad += [[{**self.refs[0],'artifact_id':aid}] for aid in (foreign,internal,huge,'missing')]+[self.refs*2,[{**self.refs[0],'artifact_sha256':'fake'}]]
        before=self.store.snapshot(self.wid)
        for refs in bad:
            with self.subTest(refs=refs),self.assertRaises(ValueError):self.save(reported_subject_refs=refs)
            self.assertEqual(before,self.store.snapshot(self.wid))
        with self.assertRaises(ValueError):self.save(subject_binding={})
        with self.store.connect(True) as db:db.execute('UPDATE artifacts SET content=? WHERE id=?',(b'{}',self.a))
        with self.assertRaisesRegex(ValueError,'SHA'):self.save(reported_subject_refs=self.refs)
    def test_failure_guard_and_transfer_tamper(self):
        report={'measurement_validity':'failed','intervention_status':'validated','precision':'adequate','context_match':True}
        mid=self.save(reported_subject_refs=self.refs,measurement_report=report);out=self.result(mid)
        self.assertTrue(out['report_guard']['applied']);self.assertFalse(out['subject_guard']['applied'])
        self.assertEqual(len(out['summary']['retained_configuration_ids']),3)
        bundle=prepare(self.store,self.wid,{'mode':'review_result','artifact_id':self.parent,'source_artifact_ids':[],'problem':None,'result':result_fixture(message_id=mid)})
        bundle['events'][-1]['body']['subject_binding']['comparison']['status']='mismatch'
        with self.assertRaises(ValueError):evaluate(bundle)
    def test_existing_version_one_history_is_not_reinterpreted(self):
        # A genuinely legacy check has no subject declaration; retain its saved v1 guard.
        from evida.measurement_report import guarded_calculation
        args,_=publish_fixture(self.store,self.wid)
        self.args=args
        plan=evaluate(prepare(self.store,self.wid,args));plan['report_guard_version']='1';plan.pop('subject_guard')
        self.parent=keep_result(self.store,self.wid,plan)
        mid=self.save()
        result=self.result(mid);result['report_guard_version']='1';result.pop('subject_guard')
        expected,guard=guarded_calculation(args['problem'],None,result['result_assessment'],{})
        self.assertEqual(result['summary'],expected['summary']);self.assertEqual(result['report_guard'],guard)
        parent=keep_result(self.store,self.wid,result);raw=self.store.artifact(self.wid,parent)['content']
        later=self.save()
        after=self.result(later,parent)
        self.assertEqual(after['summary']['retained_configuration_ids'],result['summary']['retained_configuration_ids'])
        self.assertEqual(self.store.artifact(self.wid,parent)['content'],raw)
