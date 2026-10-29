"""Model-authored request coverage after a preserved publication; no scientific oracle.

Only the explicitly unbounded Runner uses this lifecycle. It neither executes a
prescribed tool sequence nor waits for real-world efficacy before a proposal is ready.
"""
from copy import deepcopy
import hashlib
import json
import jsonschema

TEXT={'type':'string'}
def obj(properties):
 return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
STATUS=['request_satisfied','continue_internal_work','awaiting_researcher_input']
ASSESSMENTS=['addressed','conditional_plan_sufficient','internal_work_remaining','requires_researcher_choice','not_applicable']
SCHEMA=obj({
 'decision_id':TEXT,
 'goal_status':{'type':'string','enum':STATUS},
 'coverage':{'type':'array','items':obj({
   'request_requirement':TEXT,
   'assessment':{'type':'string','enum':ASSESSMENTS},
   'basis_refs':{'type':'array','items':TEXT},
   'reason':TEXT,
   'next_internal_action':TEXT})},
 'reason':TEXT,
 'next_goal':TEXT,
 'core_use':{'type':'array','items':obj({'id':TEXT,'application':TEXT})}
})
GUIDANCE = (
 'Review the just-published conditional decision against ORIGINAL_MESSAGES and the current '
 'researcher goal, not just its selected local hypothesis. The publication remains preserved. '
 'Decompose the actual request into its meaningful requirements; there is no mandatory disease, '
 'modality, fixed pipeline, number of requirements, tools or citations. Decide whether the '
 'researcher-requested explanation, evidence-based candidate/hold decision and discriminating '
 'next observation have been sufficiently proposed under explicit conditions. Real patient '
 'benefit, a new wet-lab result or proof of a mechanism is NOT required to complete a research '
 'proposal request. A defensible conditional plan can satisfy a requirement before its external '
 'observation happens. An unresolved stronger claim is not automatically a missing requirement. '
 'Preserve useful partial findings, alternatives and uncertainty. A local plan alone does not '
 'satisfy an independent requirement still needed for the original request. If an important '
 'remaining request requirement can be advanced now by source reading, comparison, input '
 'binding, interpretation of retained computations or a justified registered computation, '
 'choose continue_internal_work and name the next decision-relevant action. Do not merely '
 'repeat a prior query or demand every source or tool. Access failure on one branch does not '
 'suspend independent work. Only choose awaiting_researcher_input if an actual researcher '
 'choice/private input is essential and no independent internal requirement can advance. '
 'When all request requirements are addressed, inapplicable with a reason or adequately '
 'covered by conditional external plans, choose request_satisfied. This is your authored '
 'request-coverage judgment, not independent scientific validation. Use the delivered shared '
 'reasoning core for information selection, comparison and conditional updates when applicable; '
 'record actual perspective IDs/applications in core_use, or leave it empty rather than invent '
 'usage. Source-derived method perspectives are not biological evidence. basis_refs refer '
 'only to saved artifact IDs; the published decision can document a proposal, not establish '
 'that its scientific claims are true. Do not alter the original goal or invent a measurement '
 'to make coverage pass. Return only the goal coverage object, not another final decision or '
 'a callable function. For addressed requirements next_internal_action may be empty. '
 'If continuing, next_goal must explain what could change the current choice or next check.'
)

def prompt(decision_id):
 return {'goal_completion_review':{'version':'goal-completion-v1','decision_id':decision_id,
   'guidance':GUIDANCE,'meaning':'Reviewing a preserved publication; no automatic scientific grade or efficacy assertion.'}}

def validate(value,*,decision_id,known_artifacts,allowed_core_ids):
 jsonschema.validate(value,SCHEMA)
 if value['decision_id']!=decision_id:raise ValueError('Goal review must bind the exact published decision.')
 if not value['coverage']:raise ValueError('Review the actual request requirements; do not return empty coverage.')
 if not value['reason'].strip():raise ValueError('Explain the request-coverage judgment.')
 for row in value['coverage']:
  if not row['request_requirement'].strip()or not row['reason'].strip():raise ValueError('Each request requirement needs its own reason.')
  if not set(row['basis_refs']).issubset(known_artifacts):raise ValueError('Goal review cites an unknown artifact.')
  if row['assessment']=='internal_work_remaining'and not row['next_internal_action'].strip():raise ValueError('A remaining internal requirement needs a concrete next action.')
 states={r['assessment']for r in value['coverage']}
 if value['goal_status']=='continue_internal_work':
  if 'internal_work_remaining'not in states or not value['next_goal'].strip():raise ValueError('Continue only with a named remaining internal requirement and next goal.')
 elif value['goal_status']=='request_satisfied':
  if states&{'internal_work_remaining','requires_researcher_choice'}:raise ValueError('Unresolved internal work or essential researcher input cannot be called satisfied.')
 elif value['goal_status']=='awaiting_researcher_input':
  if 'requires_researcher_choice'not in states or 'internal_work_remaining'in states:raise ValueError('Await researcher only after independent internal work is accounted for.')
 used=[r['id']for r in value['core_use']]
 if len(used)!=len(set(used))or not set(used).issubset(allowed_core_ids)or any(not r['application'].strip()for r in value['core_use']):raise ValueError('Record only actually delivered core perspective IDs and their application.')
 return deepcopy(value)

def delivery(core):
 return None if core is None else {'version':core.get('version'),'stage':core.get('stage'),'sha256':core.get('sha256'),
  'perspective_catalog_sha256':core.get('perspective_catalog_sha256'),
  'card_ids':[x['id']for x in core.get('cards',[])],
  'perspective_ids':[x['id']for x in core.get('perspectives',[])],
  'meaning':'Delivered method context identity, not proof of application or scientific improvement.'}

def continuation(review,decision_id,review_id):
 return {'GOAL_COVERAGE_FOLLOWUP':{'published_checkpoint_id':decision_id,'coverage_review_id':review_id,
   'remaining_requirements':[r for r in review['coverage']if r['assessment']=='internal_work_remaining'],
   'next_goal':review['next_goal'],'reason':review['reason'],
   'instructions':'Keep the published checkpoint and all original evidence. Continue the original request using the named decision-relevant internal work, normal registered functions and shared core. Do not invent a source/input, redo an uninformative query, or perform an external experiment. Update the proposal only when a real result changes it. A future external plan can satisfy a research-proposal request; no need to prove efficacy or exhaust every source. The next useful publication will receive the same goal-coverage review.'}}

def finish_current(store,wid,rev,jid,decision_id,review_id,*,require_current=True):
 """Bind the new completion boundary under the ordinary Store write transaction.

 Preserve explicit cancellation/failure and same-revision publication changes.
 No model/tool/HTTP action occurs under the lock.
 """
 from .store import now,dump
 with store.connect(True)as db:
  row=db.execute('SELECT * FROM jobs WHERE id=? AND workspace=?',(jid,wid)).fetchone()
  if row is None:raise ValueError('Goal review job missing.')
  if row['status']not in ('queued','running'):return 'EXISTING_TERMINAL_PRESERVED'
  w=store.workspace(db,wid)
  latest=db.execute("SELECT json_extract(body,'$.receipt_id')AS aid FROM events WHERE workspace=?AND kind='decision_published'ORDER BY seq DESC LIMIT 1",(wid,)).fetchone()
  current=bool(require_current and w['rev']==rev and w['decision_rev']==rev and latest and latest['aid']==decision_id)
  status='succeeded'if current else'stale';error=None if current else'Goal coverage applies to a previous revision or publication; preserved without completing the current request.'
  db.execute('UPDATE jobs SET status=?,output_id=?,error=?,updated=?WHERE id=?',(status,decision_id,error,now(),jid))
  store.event(db,wid,'job_finished',{'job_id':jid,'kind':row['kind'],'status':status,'output_id':decision_id,'error':error})
  store.event(db,wid,'goal_coverage_review_finished'if current else'goal_coverage_stale',{'job_id':jid,'decision_id':decision_id,'goal_review_id':review_id,'state_rev':rev,'scientific_validation':False})
  return status

def pending_from_request(request,prompt_text):
 """Recognize only this exact new phase; old finite request rules remain separate."""
 from .model_context import unpack
 from .wire_schema import strict_wire_schema
 expected={'type':'json_schema','name':'evida_goal_coverage_review','strict':True}
 fmt=request.get('text',{}).get('format',{})
 if fmt.get('name')!='evida_goal_coverage_review':return None
 if (request.get('instructions')!=prompt_text+'\n\nCURRENT GOAL COVERAGE REVIEW:\n'+GUIDANCE
     or request.get('tools')!=[]or request.get('tool_choice')!='none'
     or request.get('parallel_tool_calls')is not False
     or {k:v for k,v in fmt.items()if k!='schema'}!=expected
     or fmt.get('schema')not in (SCHEMA,strict_wire_schema(SCHEMA))):
  raise ValueError('Preserved goal review instructions/tools/schema changed; use a normal new review.')
 current=[]
 for m in request.get('input',[]):
  if m.get('role')!='user'or not isinstance(m.get('content'),str):continue
  try:v=unpack(json.loads(m['content']))
  except (ValueError,TypeError):continue
  if isinstance(v,dict)and 'CURRENT_CALL'in v:current.append(v['CURRENT_CALL'])
 if len(current)!=1:raise ValueError('Exact current goal-review stage statement required.')
 c=current[0];p=c.get('goal_completion_review',{});aid=p.get('decision_id')
 if (c.get('stage')!='goal_review'or c.get('tool_choice')!='none'or c.get('callable_function_names')!=[]
     or p!=prompt(aid)['goal_completion_review']or not isinstance(aid,str)or not aid.startswith('art_')):
  raise ValueError('Preserved goal-review stage/decision binding changed.')
 return {'decision_id':aid}

def rebind_resumed_checkpoint(store,wid,rev,jid,decision_id,review_id,goal_status):
 """A resumed review may accept an immutable checkpoint owned by its failed ancestor.

 Re-publish identical validated canonical bytes under the current planner, retaining
 every old artifact/sidecar/receipt. This restores the ordinary current publisher
 proof without treating the repeated content as new science or independent evidence.
 """
 from .store import uid,now,dump
 with store.connect(True)as db:
  job=db.execute('SELECT * FROM jobs WHERE id=?AND workspace=?',(jid,wid)).fetchone()
  if not job or job['status']not in ('queued','running'):return None
  source=db.execute('SELECT * FROM artifacts WHERE id=?AND workspace=?',(decision_id,wid)).fetchone()
  if not source or source['kind']!='decision_proposal':raise ValueError('Published checkpoint missing.')
  meta=json.loads(source['meta']);origin=meta.get('job_id')
  if origin==jid:return decision_id
  chain=set();parent=json.loads(job['request']).get('resume_from_job')
  while parent:
   if parent in chain:raise ValueError('Resume ownership chain is cyclic.')
   chain.add(parent);row=db.execute('SELECT request FROM jobs WHERE id=?AND workspace=?',(parent,wid)).fetchone()
   if row is None:raise ValueError('Resume ownership ancestor missing.')
   parent=json.loads(row['request']).get('resume_from_job')
  if origin not in chain:raise ValueError('Checkpoint is not owned by the preserved resume chain.')
  w=store.workspace(db,wid);latest=db.execute("SELECT json_extract(body,'$.receipt_id')AS aid FROM events WHERE workspace=?AND kind='decision_published'ORDER BY seq DESC LIMIT 1",(wid,)).fetchone()
  raw=source['content'];raw=raw.encode()if isinstance(raw,str)else bytes(raw)
  if hashlib.sha256(raw).hexdigest()!=source['sha256']:raise ValueError('Original checkpoint SHA mismatch.')
  proposal=json.loads(raw)
  if w['rev']!=rev or w['decision_rev']!=rev or not latest or latest['aid']!=decision_id or json.loads(w['decision'])!=proposal or json.loads(w['intent'])!=proposal['intent_records']:return None
  receipt_ids=[r['id']for r in db.execute("SELECT id FROM artifacts WHERE workspace=?AND kind='model_receipt'AND json_extract(meta,'$.job_id')=?ORDER BY created,id",(wid,jid))]
  protocol=db.execute("SELECT id FROM artifacts WHERE workspace=?AND kind='protocol_snapshot'AND json_extract(meta,'$.job_id')=?ORDER BY created DESC LIMIT 1",(wid,jid)).fetchone()
  new_id=uid('art');new_meta={**meta,'based_rev':rev,'job_id':jid,'model_receipts':list(dict.fromkeys(meta.get('model_receipts',[])+receipt_ids)),
   'protocol_id':protocol['id']if protocol else meta.get('protocol_id'),'reaffirmed_from':decision_id,
   'reaffirmed_from_sha256':source['sha256'],'goal_coverage_review_id':review_id,'science_content_unchanged':True}
  db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?)',(new_id,wid,'원목표 검토 후 유지한 판단','decision_proposal',source['sha256'],source['media_type'],now(),dump(new_meta),raw))
  store.event(db,wid,'artifact_added',{'artifact_id':new_id,'title':'원목표 검토 후 유지한 판단','kind':'decision_proposal'})
  if not store._publish_decision(db,wid,rev,proposal,new_id):raise ValueError('Resumed checkpoint publication binding changed.')
  db.execute('UPDATE workspaces SET review_status=?WHERE id=?',(w['review_status'],wid))
  store.event(db,wid,'goal_coverage_rebound',{'prior_decision_id':decision_id,'decision_id':new_id,'goal_review_id':review_id,'sha256':source['sha256'],'science_content_unchanged':True})
  return new_id


def finish_error_if_live(store,wid,jid,status,error):
 """Only the None goal-review exception seam: never overwrite explicit terminal state."""
 from .store import now
 with store.connect(True)as db:
  row=db.execute('SELECT * FROM jobs WHERE id=?AND workspace=?',(jid,wid)).fetchone()
  if row is None:raise ValueError('Goal review job missing.')
  if row['status']not in ('queued','running'):
   store.event(db,wid,'goal_review_late_error_preserved',{'job_id':jid,'preserved_status':row['status'],'late_error_status':status,'late_error_recorded_as_event':True})
   return False
  db.execute('UPDATE jobs SET status=?,output_id=NULL,error=?,updated=?WHERE id=?',(status,error,now(),jid))
  store.event(db,wid,'job_finished',{'job_id':jid,'kind':row['kind'],'status':status,'output_id':None,'error':error})
  return True
