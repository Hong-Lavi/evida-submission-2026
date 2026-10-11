"""Exact native state methods extracted for an offline publication replay.

The full production Runner constructor and model/tool dispatch are outside this
package. Method bodies below are unchanged from their pinned native sources.
"""
import json
from .contracts import CAPABILITIES
from .catalog_delivery import apply_catalog_delivery
from .context_delivery import apply_context_delivery
from .model_context import artifact_overview, decision_history, reading_focus, working_readings
from .research_loop import validate_hypotheses
from .store import dump


class Runner:
    def frame(self, wid, based_rev, args, *, require_intent_review=False, expected_intent_snapshot=None):
        if not args["current_question"].strip():
            raise ValueError("현재 연구 질문이 비어 있습니다. 기존 의도·작업 분해를 유지하고, 실제 질문 또는 필요한 확인 내용을 표시하세요.")
        state = self.store.snapshot(wid)
        validate_hypotheses(args["hypotheses"], state)
        from .intent_dependencies import bind_frame, input_snapshot, transaction_state
        before = input_snapshot(state)['snapshot_sha256']
        if expected_intent_snapshot and before != expected_intent_snapshot:
            raise ValueError('질문을 구성하는 동안 의도 또는 게시 판단이 바뀌었습니다. 최신 입력을 검토하세요.')
        binding = bind_frame(self.store, wid, state, args, required=require_intent_review)
        with self.store.connect(True) as db:
            current = transaction_state(self.store, db, wid)
            if current['rev'] != based_rev or input_snapshot(current)['snapshot_sha256'] != before:
                raise ValueError('질문을 저장하기 전 연구 상태가 바뀌었습니다.')
            self.store.event(db, wid, "work_framed", {"based_rev": based_rev, **args,
                **({'intent_dependencies': binding} if binding is not None else {})})


    def model_context(self, wid, rev, framed, restore_reading=False, current_job=None, excluded_readings=(), force_full=False):
        state = self.store.snapshot(wid)
        reading_jobs = []
        cursor = current_job
        jobs = {j['id']: j for j in state['jobs']}
        while cursor and cursor not in reading_jobs:
            reading_jobs.append(cursor)
            cursor = jobs.get(cursor, {}).get('request', {}).get('resume_from_job')
        messages = [e for e in state["events"] if e["kind"] in ("message", "observation", "correction", "intent_edit")]
        evidence = [artifact_overview(self.store.artifact(wid, a["id"])) for a in state["artifacts"]
                    if a["kind"] not in ("model_receipt", "decision_proposal", "research_notes", "protocol_snapshot",
                        "explanation_context", "explanation_answer", "explanation_model_output", "explanation_reading")]
        notes = next((self.store.artifact(wid, a["id"]) for a in reversed(state["artifacts"])
                      if a["kind"] == "research_notes"), None)
        findings = {}
        for entry in state["artifacts"]:
            if entry["kind"] == "research_notes":
                prior = json.loads(self.store.artifact(wid, entry["id"])["content"])
                for finding in prior["findings"]:
                    findings[dump(finding)] = {**finding, "note_id": entry["id"], "noted_at": entry["created"]}
        frame = next((e["body"] for e in reversed(state["events"]) if e["kind"] == "work_framed" and e["body"]["based_rev"] == rev), None)
        if frame is None:
            # Every command raises rev, including a continuation that says only "carry on", so a
            # rev-bound frame vanished on each continuation and every new job reframed from
            # scratch - one live case framed five times and never reached a review. The latest
            # decomposition is carried forward, marked with the conditions it was made under;
            # the model keeps it when the new input does not change the question and reframes
            # when it does.
            earlier = next((e["body"] for e in reversed(state["events"]) if e["kind"] == "work_framed"), None)
            if earlier is not None:
                frame = {**earlier, "carried_from_rev": earlier["based_rev"], "current_rev": rev}
        previous_reading = next((a for a in reversed(state["artifacts"]) if a["kind"] == "tool_reading"), None) if restore_reading else None
        focus = reading_focus(state['events'], rev, reading_jobs)
        from .judgment_context import view as context_view
        from .hypothesis_review import view as hypothesis_review_view
        from .discovery import overview as discovery_overview
        from .intent_dependencies import model_view as intent_dependency_view
        context = {"DISCOVERY_OPTIONS":discovery_overview(self.store,wid,state),"JUDGMENT_CONTEXT":context_view(self.store,wid,state),"STATE_REVISION": rev, "ORIGINAL_MESSAGES": messages, "CURRENT_INTENT": state["intent"],
                "INTENT_DEPENDENCIES": intent_dependency_view(self.store, wid, state),
                "HYPOTHESIS_REVIEW": hypothesis_review_view(self.store,wid,state),
                "PREVIOUS_DECISION": state["decision"], "RELEVANT_EVIDENCE": evidence,
                "INPUT_CHANGES": state["input_changes"],
                "DECISION_HISTORY": decision_history(state["events"], lambda aid: self.store.artifact(wid, aid)),
                "HYPOTHESIS_WORDING_HISTORY": [e['body'] for e in state['events']
                    if e['kind'] == 'hypothesis_wording_compared'],
                "REGISTERED_CAPABILITIES": CAPABILITIES, "EXISTING_WORK": state["jobs"],
                "RESEARCH_CHECK_RUNS": state["research_checks"], "WORK_ALREADY_FRAMED": framed,
                "CURRENT_FRAME": frame, "CURRENT_RESEARCH_NOTES": json.loads(notes["content"]) if notes else None,
                "PRIOR_NOTE_FINDINGS": list(findings.values()),
                "READING_FOCUS": {k: focus[k] for k in ('current_question', 'reading_ids')} if focus else None,
                "WORKING_READINGS": working_readings(state["artifacts"], reading_jobs, excluded_readings,
                    lambda aid: self.store.artifact(wid, aid), focus=focus),
                "COMPLETED_VIEWS": [{**a["meta"], "reading_id": a["id"], "sha256": a["sha256"], "title": a["title"]} for a in state["artifacts"] if a["kind"] == "tool_reading"],
                "RESTORED_READING": {"reading_id": previous_reading["id"], "meta": previous_reading["meta"],
                    "content": json.loads(self.store.artifact(wid, previous_reading["id"])["content"])} if previous_reading else None,
                "IMPORTANT": "응용프로그램이 구성한 현재 연구 상태다. ORIGINAL_MESSAGES가 연구자의 실제 요청이다. 자료 목록은 내용 열람이 아니며 연구 메모는 모델의 잠정 정리다. 원자료·과거 도구 전달본은 ID로 재조회할 수 있다. DECISION_HISTORY는 과거 게시 판단의 목록이며 최신 상태나 독립 과학 근거가 아니다. 가설 ID는 decision_id와 함께 구별하고 원 판단은 inspect_artifact로 읽는다."}

        context = apply_catalog_delivery(context)
        explicit_specs = next((jobs[j]['request']['source_views'] for j in reading_jobs
            if j in jobs and 'source_views' in jobs[j]['request']), [])
        if explicit_specs:
            from .provided_views import build
            context['EXPLICIT_SOURCE_VIEWS'] = build(self, wid, explicit_specs)
        context['FINALIZATION'] = {
            'response_shape':'decision + discovery_review(nullable) + judgment_context(nullable) + hypothesis_review(required, schema_version=2) + intent_review(required)',
            'intent_review': {
                'uses':'Declare actual intent IDs and why they were used for current question (question/current_question), '
                    'recommendation (recommendation/recommendation), and each exact hypothesis/check ID. '
                    'For frame_work, only question/current_question is required. Empty intent_ids means unknown linkage, not independence. '
                    'IDs may refer to existing inputs or your explicit new/updated provisional intent_records in this frame/final. '
                    'Preserve protected researcher records and deleted IDs; keep inferred origins. '
                    'Server binds content, hashes and revision; do not supply invented hashes.',
                'reassessments':'Account for INTENT_DEPENDENCIES.required_reassessments in the final response. '
                    'For frame_work account only for question entries. Use changed, retained with a reason under the new conditions, '
                    'removed for an absent old item, or unknown. Retained/changed refer to exact consumer content, not scientific proof. '
                    'Unknown is valid and remains pending review. Do not change a question merely to satisfy the tracker.',
                'new_structure':'If final intent_records differ from the current frame/received structure, reassess question/current_question '
                    'and any prior consumers of changed IDs even if the incoming pending list was empty. '
                    'Use retained with a new-condition reason when the exact question still applies. '
                    'The server stores received input separately from model-authored structure; it does not confirm the latter as human input or science.',
                'question':'If question_reassessment_required is true, frame_work must reconsider the top question before further research. '
                    'No previous consumption record does not mean no impact. Preserve all original evidence and counterevidence.'},
            'hypothesis_review': {
                'responsibility':'Author the review in this same final response for the hypotheses and next checks you generate. '
                    'Account for every exact final ID in scope.hypotheses and scope.checks.',
                'coverage':'reviewed requires linked causal_steps/observations; not_reviewed or not_applicable requires an explicit '
                    'item-specific reason and remains visible as such. Empty scope is valid only when the decision has no items.',
                'unknowns':'Absent citations do not justify inventing evidence or omitting the item. Use empty anchors and unknown '
                    'assessments, preserve missing assumptions, and record unknown predictions explicitly.',
                'references':'Use an empty part_id for a whole hypothesis and exact declared IDs for named parts. '
                    'Anchor paths address the saved artifact, not a result wrapper in a tool view.',
                'causal_conditions':'Link each causal step to its own source conditions and measurement time. '
                    'Do not collapse measurements at different times into one observed causal sequence.',
                'meaning':'Authored review coverage is not independent scientific verification.'},
            'candidate_pool_retained':context['DISCOVERY_OPTIONS']['total'],
            'current_job_discovery_review':any(a['kind']=='discovery_review' and a['meta'].get('job_id')==current_job for a in state['artifacts']),
            'current_job_judgment_context':any(a['kind']=='judgment_context' and a['meta'].get('job_id')==current_job for a in state['artifacts']),
            'meaning':'The optional discovery/context records may be null; the hypothesis review must account for the final items. '
                'Use existing readings, preserve unknown conditions, and do not regenerate candidate pools or invent scientific judgments.'}
        requested = jobs.get(current_job, {}).get('request', {}).get('requested_check_operations')
        if requested:
            from .finalization import requested_operations
            context['REQUESTED_CHECK_OPERATIONS'] = {
                'by_check_id': requested_operations(state, requested),
                'meaning': 'Explicitly requested operation-type correction for existing checks. '
                    'Preserve the scientific question, evidence and outcome links. '
                    'A new measurement proposal is external_observation even when the laboratory work is external. '
                    'These routing instructions are not empirical observations.'}
        preservation = jobs.get(current_job, {}).get('request', {}).get('decision_preservation')
        if preservation is not None:
            from .decision_preservation import bind
            context['DECISION_PRESERVATION'] = bind(self.store, wid, preservation)
        recent = getattr(self, 'context_recent_views', None)
        return apply_context_delivery(context, native_reading_ids=excluded_readings,
            recent_count=recent, force_full=force_full) if recent is not None else context

