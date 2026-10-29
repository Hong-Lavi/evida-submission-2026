"""Publication and runner regressions using tiny synthetic research records.

No model, network, scientific runtime or computation is used. The real TTR02
draft replay is recorded separately rather than relabelled as a test fixture.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from evida.decision_preservation import DecisionPreservationError, bind, pointer_value
from evida.finalization import commit, finalize, prepare
from evida.interaction import request_followthrough
from evida.planner_recovery import prepare_quota_resume
from evida.runner import Runner
from evida.store import Store, dump
from test_requested_operation_correction import synthetic_decision, synthetic_bundle, start_runner


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def case(tmp_path):
    store = Store(tmp_path/'synthetic.sqlite3')
    wid = store.create('Synthetic bounded-revision test')['id']
    source = store.add_artifact(wid,'Synthetic source','literature',b'{"rows":[]}',{},bump=False)
    old = synthetic_decision(1)
    check = old['research_loop']['next_checks'][0]
    check['operation'] = {'kind':'external_observation','request':'Synthetic future measurement.',
                          'grounded_in':[source]}
    check['possible_outcomes'] = [{'observation':r,'implication':'Synthetic implication.'}
                                 for r in ('supports','challenges','unresolved')]
    check['outcome_links'] = [{'outcome_index':i,'effects':[], 'followup_check_ids':[]}
                             for i in range(3)]
    prior, published = finalize(store,wid,1,'synthetic-original',synthetic_bundle(old),True,[],None)
    assert published
    requirement = {'reference_decision_id':prior,'reference_sha256':store.artifact(wid,prior)['sha256'],
                   'protected_fields':['/research_loop/next_checks',
                                       '/research_loop/hypotheses/0/statement']}
    store.command(wid,1,'synthetic-correction',{'kind':'message','text':'Synthetic citation-only correction.',
                                             'synthetic':True})
    new = deepcopy(old);new['based_on_state_rev']=2
    new['research_loop']['hypotheses'][0]['evidence']=[{'source_type':'artifact','source_id':source,
        'relation':'context','detail':'Synthetic corrected citation.','applicability':'Fixture only.'}]
    return store,wid,old,new,requirement


def test_allowed_citation_revision_is_published_without_merging(case):
    store,wid,old,new,requirement=case
    frozen=deepcopy(new)
    aid,published=finalize(store,wid,2,'synthetic-revision',synthetic_bundle(new),True,[],None,decision_preservation=requirement)
    assert published and store.snapshot(wid)['decision']==new==frozen
    assert json.loads(store.artifact(wid,requirement['reference_decision_id'])['content'])==old
    assert json.loads(store.artifact(wid,aid)['content'])==frozen
    assert any(e['kind']=='decision_preservation_checked' for e in store.snapshot(wid)['events'])


@pytest.mark.parametrize('change',['kind','branch','grounding','check_removed','field_missing','hypothesis'])
def test_regression_holds_original_and_retains_exact_failed_bundle(case,change):
    store,wid,old,new,requirement=case
    check=new['research_loop']['next_checks'][0]
    if change=='kind':check['operation']={'kind':'researcher_input','question':'Synthetic prerequisite?'}
    elif change=='branch':
        check['possible_outcomes'].pop();check['outcome_links'].pop()
    elif change=='grounding':check['operation']['grounded_in']=[]
    elif change=='check_removed':new['research_loop']['next_checks']=[]
    elif change=='field_missing':del new['research_loop']['next_checks']
    else:new['research_loop']['hypotheses'][0]['statement']='Changed synthetic scientific claim.'
    bundle={'decision':new,'discovery_review':{'question':'Must not be published','new_options':[],
        'assessments':[],'unsearched_scope':['Synthetic']},'judgment_context':None}
    frozen=deepcopy(bundle);before=store.snapshot(wid)
    with pytest.raises(DecisionPreservationError) as refused:
        finalize(store,wid,2,'synthetic-revision',bundle,True,['synthetic-receipt'],None,
                 decision_preservation=requirement)
    after=store.snapshot(wid)
    assert after['decision']==old and after['rev']==2 and after['decision_rev']==1
    assert after['artifacts'][:-1]==before['artifacts'] and after['events'][:-1]==before['events']
    failure=store.artifact(wid,refused.value.artifact_id)
    assert failure['kind']=='decision_scope_rejection' and not failure['meta']['published']
    assert json.loads(failure['content'])['proposal']==frozen==bundle
    assert not any(a['kind']=='discovery_review' for a in after['artifacts'])


def test_without_opt_in_a_normal_research_revision_can_change_checks(case):
    store,wid,_,new,_=case
    new['research_loop']['next_checks']=[]
    aid,published=finalize(store,wid,2,'normal-research',synthetic_bundle(new),True,[],None)
    assert published and store.snapshot(wid)['decision']==new
    assert not any(e['kind']=='decision_preservation_checked' for e in store.snapshot(wid)['events'])


@pytest.mark.parametrize('reference',['unknown','foreign','unpublished','old_published','wrong_hash','tampered_bytes'])
def test_reference_is_bound_to_current_published_record(case,reference):
    store,wid,old,new,requirement=case
    if reference=='unknown':requirement['reference_decision_id']='unknown'
    elif reference in ('foreign','unpublished'):
        target=store.create('Other synthetic workspace')['id'] if reference=='foreign' else wid
        aid=store.add_artifact(target,'Unpublished','decision_proposal',dump(old).encode(),{},bump=False)
        if reference=='foreign':store.publish_decision(target,1,old,aid)
        requirement.update(reference_decision_id=aid,reference_sha256=store.artifact(target,aid)['sha256'])
    elif reference=='old_published':finalize(store,wid,2,'intervening',synthetic_bundle(new),True,[],None)
    elif reference=='wrong_hash':requirement['reference_sha256']='0'*64
    else:
        with store.connect(True) as db:
            db.execute('UPDATE artifacts SET content=? WHERE id=?',(b'{}',requirement['reference_decision_id']))
    runner=start_runner(store,ROOT)
    before=store.snapshot(wid)
    with pytest.raises(DecisionPreservationError):
        runner.start(wid,2,'planner',{'decision_preservation':requirement})
    assert store.snapshot(wid)==before and runner.pool.submissions==[]


@pytest.mark.parametrize('field',['research_loop','/research_loop/no_such_field',
    '/research_loop/next_checks/-1','/research_loop/next_checks/00','/research_loop/~2bad'])
def test_bad_protected_pointer_is_rejected_before_dispatch(case,field):
    store,wid,_,_,requirement=case
    requirement['protected_fields']=[field]
    with pytest.raises(DecisionPreservationError):bind(store,wid,requirement)


def test_pointer_handles_escaped_object_keys_without_negative_array_aliases():
    assert pointer_value({'a/b':{'~value':[4]}},'/a~1b/~0value/0')==4
    with pytest.raises(ValueError):pointer_value([1,2],'/-1')


def test_commit_rechecks_reference_after_prepare_even_at_same_revision(case):
    store,wid,old,new,requirement=case
    proposal,records=prepare(store,wid,2,synthetic_bundle(new),True,decision_preservation=requirement)
    intermediate=deepcopy(new);intermediate['recommendation']='Another published synthetic judgment.'
    finalize(store,wid,2,'intervening',synthetic_bundle(intermediate),True,[],None)
    before=store.snapshot(wid)
    with pytest.raises(DecisionPreservationError):
        commit(store,wid,2,'old-reference',proposal,records,[],None,decision_preservation=requirement)
    assert store.snapshot(wid)==before


class OneResponseGateway:
    model='synthetic-offline-model'
    effort='synthetic'
    def __init__(self,value):self.value=value;self.calls=[]
    def status(self):return {'available':True,'transport_mode':'offline_test'}
    def approved_models(self):return [self.model]
    def request(self,payload,model=None):
        self.calls.append(payload)
        assert len(self.calls)==1,'A scope violation must never make a correction call.'
        return ({'output':[{'type':'message','content':[{'type':'output_text','text':dump(self.value)}]}]},
                {'requested_model':self.model,'status':'COMPLETED','semantic_type':'synthetic_test'})


def test_real_runner_delivers_contract_then_stops_without_correction_or_followthrough(case):
    store,wid,old,new,requirement=case
    # Queue an independent request before the planner: there is no failed-job
    # blocker in it, so the generic finally dispatcher would otherwise run it.
    pending=request_followthrough(store,wid,2,'synthetic-pending')['review_request_id']
    runner=start_runner(store,ROOT);runner.context_recent_views=2
    runner.prompt='Synthetic offline runner';new['research_loop']['next_checks'][0]['outcome_links'].pop()
    runner.gateway=OneResponseGateway(synthetic_bundle(new))
    jid=runner.start(wid,2,'planner',{'decision_preservation':requirement})
    with store.connect(True) as db:store.event(db,wid,'work_framed',{'based_rev':2})
    context=runner.model_context(wid,2,True,current_job=jid)
    assert context['DECISION_PRESERVATION']['reference_decision_id']==requirement['reference_decision_id']
    assert context['PREVIOUS_DECISION']==old
    runner.run_planner(jid)
    after=store.snapshot(wid);job=next(j for j in after['jobs'] if j['id']==jid)
    assert job['status']=='failed' and len(runner.gateway.calls)==1
    assert after['decision']==old and len(after['jobs'])==1
    assert runner.pool.submissions==[('run_planner',(jid,))]
    assert next(r for r in after['followthrough_requests'] if r['id']==pending)['status']=='needs_confirmation'
    assert store.artifact(wid,job['output_id'])['kind']=='decision_scope_rejection'
    protocol=next(a for a in after['artifacts'] if a['kind']=='protocol_snapshot')
    saved=json.loads(store.artifact(wid,protocol['id'])['content'])
    assert saved['decision_preservation']==context['DECISION_PRESERVATION']
    assert 'evida/decision_preservation.py' in saved['code_sha256']


def test_reference_changed_after_enqueue_stops_before_any_model_request(case):
    store,wid,_,new,requirement=case
    runner=start_runner(store,ROOT);runner.prompt='Synthetic stale-reference fixture'
    runner.gateway=OneResponseGateway(synthetic_bundle(new))
    jid=runner.start(wid,2,'planner',{'decision_preservation':requirement})
    newer=deepcopy(new);newer['recommendation']='Intervening synthetic judgment at the same state revision.'
    finalize(store,wid,2,'intervening',synthetic_bundle(newer),True,[],None)
    runner.run_planner(jid)
    state=store.snapshot(wid)
    assert next(j for j in state['jobs'] if j['id']==jid)['status']=='failed'
    assert runner.gateway.calls==[] and state['decision']==newer
    assert not any(a['kind']=='protocol_snapshot' for a in state['artifacts'])


def test_manual_quota_continuation_retains_the_opt_in_contract(case,tmp_path):
    from evida.contracts import DECISION,model_functions
    store,wid,_,_,requirement=case
    runner=start_runner(store,ROOT);runner.prompt='Synthetic quota fixture'
    gateway=SimpleNamespace(transport_mode='competition_gateway',model='synthetic',effort='synthetic',max_output_tokens=1000,
                            policy={},requests_dir=tmp_path/'requests')
    runner.gateway=gateway
    request={'model':gateway.model,'reasoning':{'effort':gateway.effort},'max_output_tokens':1000,
             'store':False,'include':['reasoning.encrypted_content'],'instructions':runner.prompt,
             'tools':model_functions(),'parallel_tool_calls':False,'tool_choice':'auto',
             'text':{'format':{'type':'json_schema','name':'evida_decision','strict':True,'schema':DECISION}}}
    raw=dump(request).encode();record='request_'+'a'*16
    receipt={'status':'quota_or_rate_limit','http_status':429,'request_record':record,
             'request_sha256':hashlib.sha256(raw).hexdigest(),'requested_model':gateway.model,
             'requested_effort':gateway.effort,'started_at':'2020-01-01T00:00:00+00:00',
             'diagnostic_headers':{'retry-after':'1'}}
    directory=gateway.requests_dir/record;directory.mkdir(parents=True)
    (directory/'request.json').write_bytes(raw);(directory/'receipt.json').write_text(dump(receipt))
    jid=store.enqueue(wid,2,'planner',{'decision_preservation':requirement})
    store.start_job(jid);store.finish_job(jid,'quota_or_rate_limit')
    for body in ({'status':'RETURNED','response_status':'completed'},receipt):
        store.add_artifact(wid,'Synthetic receipt','model_receipt',dump(body).encode(),{'job_id':jid},bump=False)
    prepared=prepare_quota_resume(runner,wid,2,jid)
    assert prepared['arguments']['decision_preservation']==requirement
    assert store.snapshot(wid)['jobs'][0]['status']=='quota_or_rate_limit'
