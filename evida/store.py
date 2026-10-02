"""Durable research state. Short transactions; no model/tool work inside locks."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def uid(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            # DELETE journal is deliberate: do not assume this shared filesystem supports WAL.
            db.executescript("""
            CREATE TABLE IF NOT EXISTS workspaces (
              id TEXT PRIMARY KEY, title TEXT NOT NULL, rev INTEGER NOT NULL,
              created TEXT NOT NULL, intent TEXT NOT NULL, decision TEXT,
              decision_rev INTEGER, review_status TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, workspace TEXT NOT NULL,
              kind TEXT NOT NULL, created TEXT NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS commands (
              workspace TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
              result TEXT NOT NULL, PRIMARY KEY(workspace,id));
            CREATE TABLE IF NOT EXISTS artifacts (
              id TEXT PRIMARY KEY, workspace TEXT NOT NULL, title TEXT NOT NULL,
              kind TEXT NOT NULL, sha256 TEXT NOT NULL, media_type TEXT NOT NULL,
              created TEXT NOT NULL, meta TEXT NOT NULL, content BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY, workspace TEXT NOT NULL, based_rev INTEGER NOT NULL,
              kind TEXT NOT NULL, request TEXT NOT NULL, status TEXT NOT NULL,
              created TEXT NOT NULL, updated TEXT NOT NULL, output_id TEXT,
              error TEXT, cache_key TEXT, attempt TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS events_workspace ON events(workspace,seq);
            CREATE INDEX IF NOT EXISTS jobs_cache ON jobs(workspace,cache_key,status);
            CREATE TABLE IF NOT EXISTS research_checks (
              workspace TEXT NOT NULL, decision_id TEXT NOT NULL, check_id TEXT NOT NULL,
              job_id TEXT NOT NULL UNIQUE, review_job_id TEXT,
              PRIMARY KEY(workspace,decision_id,check_id));
            CREATE TABLE IF NOT EXISTS followthrough_requests (
              id TEXT PRIMARY KEY, workspace TEXT NOT NULL, requested_rev INTEGER NOT NULL,
              created TEXT NOT NULL, message_id TEXT, status TEXT NOT NULL,
              blocking_jobs TEXT NOT NULL, job_id TEXT, error TEXT, superseded_by TEXT);
            """)

    @contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def event(db, workspace, kind, body):
        db.execute("INSERT INTO events(workspace,kind,created,body) VALUES(?,?,?,?)",
                   (workspace, kind, now(), dump(body)))

    @staticmethod
    def workspace(db, wid):
        row = db.execute("SELECT * FROM workspaces WHERE id=?", (wid,)).fetchone()
        if row is None:
            raise KeyError("워크스페이스를 찾지 못했습니다.")
        return dict(row)

    def create(self, title):
        wid = uid("ws")
        with self.connect(True) as db:
            db.execute("INSERT INTO workspaces VALUES(?,?,1,?,?,NULL,NULL,?)",
                       (wid, title, now(), "[]", "awaiting_input"))
            self.event(db, wid, "created", {"title": title})
        return self.snapshot(wid)

    def list(self):
        """Every workspace, and whether it reached a published judgment.

        Without that last field every row looks alike, so a screen cannot tell a finished research
        from one that stopped at retrieval, and the onboarding panel that offers to open a completed
        result had to name workspace ids in its source - which renders it empty wherever those ids
        are not mounted.
        """
        with self.connect() as db:
            return [{**dict(r), 'has_decision': bool(r['has_decision'])} for r in db.execute(
                "SELECT id,title,rev,created,review_status,"
                "decision IS NOT NULL AS has_decision FROM workspaces ORDER BY created DESC")]

    def snapshot(self, wid):
        with self.connect() as db:
            state = self.workspace(db, wid)
            state["intent"] = json.loads(state["intent"])
            state["decision"] = json.loads(state["decision"]) if state["decision"] else None
            state["events"] = [{**dict(r), "body": json.loads(r["body"])} for r in db.execute(
                "SELECT * FROM events WHERE workspace=? ORDER BY seq", (wid,))]
            state["artifacts"] = [self.artifact_meta(r) for r in db.execute(
                "SELECT id,workspace,title,kind,sha256,media_type,created,meta,length(content) bytes, "
                "CASE WHEN kind='article' AND json_valid(content) THEN json_extract(content,'$.title') END source_title "
                "FROM artifacts WHERE workspace=? ORDER BY created", (wid,))]
            state["jobs"] = [{**dict(r), "request": json.loads(r["request"])} for r in db.execute(
                "SELECT * FROM jobs WHERE workspace=? ORDER BY created", (wid,))]
            state["event_cursor"] = state["events"][-1]["seq"] if state["events"] else 0
            state["research_checks"] = [dict(r) for r in db.execute(
                "SELECT * FROM research_checks WHERE workspace=?", (wid,))]
            state['followthrough_requests'] = [{**dict(r),'blocking_jobs':json.loads(r['blocking_jobs'])}
                for r in db.execute('SELECT * FROM followthrough_requests WHERE workspace=? ORDER BY created',(wid,))]
            from .input_provenance import annotate_events
            state["events"] = annotate_events(state["events"])
            from .input_changes import review_inputs
            state["input_changes"] = review_inputs(state)
            return state

    def command(self, wid, expected_rev, command_id, body):
        body = json.loads(dump(body))
        payload = dump(body)
        with self.connect(True) as db:
            old = db.execute("SELECT * FROM commands WHERE workspace=? AND id=?",
                             (wid, command_id)).fetchone()
            if old:
                if old["payload"] != payload:
                    raise Conflict("같은 요청 ID에 다른 내용이 들어왔습니다.")
                return json.loads(old["result"])
            state = self.workspace(db, wid)
            if state["rev"] != expected_rev:
                raise Conflict("다른 수정이 먼저 저장되었습니다. 최신 내용을 확인해 다시 적용해 주세요.")
            kind = body.get("kind")
            if 'review_requested' in body and type(body['review_requested']) is not bool:
                raise ValueError('후속 검토 선택을 확인해 주세요.')
            event = {**body, "state_rev": expected_rev + 1, "message_id": uid("msg")}
            if "provenance_correction" in body:
                from .input_provenance import validate_correction
                prior_events = [{"kind": row["kind"], "body": json.loads(row["body"])}
                                for row in db.execute("SELECT kind,body FROM events WHERE workspace=? ORDER BY seq", (wid,))]
                validate_correction(body, prior_events)
            if kind == "intent_edit":
                records = body.get("records")
                if not isinstance(records, list) or len(records) > 100:
                    raise ValueError("의도 기록 형식이 올바르지 않습니다.")
                if 'base_records' in body:
                    baseline = json.loads(state['intent'])
                    previous_edit = db.execute("SELECT body FROM events WHERE workspace=? AND kind='intent_edit' ORDER BY seq DESC LIMIT 1", (wid,)).fetchone()
                    if not baseline and previous_edit is None:
                        frame = db.execute("SELECT body FROM events WHERE workspace=? AND kind='work_framed' ORDER BY seq DESC LIMIT 1", (wid,)).fetchone()
                        frame = json.loads(frame['body']) if frame else None
                        if frame and frame.get('based_rev') == expected_rev:
                            baseline = frame.get('intent_records', [])
                    if body['base_records'] != baseline:
                        raise Conflict('편집 중 연구 의도가 바뀌었습니다. 최신 내용을 열어 다시 적용해 주세요.')
                    from .intent_records import field_edit
                    records, edit_meta = field_edit(baseline, records,
                        json.loads(previous_edit['body']) if previous_edit else None, event['message_id'])
                    event.update(edit_meta)
                    event['records'] = records
                else:
                    # Legacy clients explicitly replace the whole intent list.
                    for record in records:
                        if not isinstance(record, dict) or not record.get("label") or not record.get("text"):
                            raise ValueError("의도 항목에는 이름과 내용이 필요합니다.")
                        record.setdefault("id", uid("intent"))
                        record["origin"] = "researcher"
                db.execute("UPDATE workspaces SET intent=? WHERE id=?", (dump(records), wid))
            elif kind in ("message", "observation", "correction"):
                if not isinstance(body.get("text"), str) or not body["text"].strip():
                    raise ValueError("추가할 내용을 입력해 주세요.")
                if len(body["text"]) > 40000:
                    raise ValueError("내용은 40,000자 이내로 입력해 주세요.")
                event["origin"] = "synthetic" if body.get("synthetic") else "researcher_report"
                if body.get("research_context") is not None:
                    from .research_loop import validate_feedback
                    context = body["research_context"]
                    if not isinstance(context, dict):
                        raise ValueError("관측의 연결 정보가 올바르지 않습니다.")
                    source = db.execute("SELECT content,sha256,kind FROM artifacts WHERE workspace=? AND id=?",
                                        (wid, context.get("decision_id"))).fetchone()
                    if (not source or source["kind"] != "decision_proposal"
                            or hashlib.sha256(source["content"]).hexdigest() != source["sha256"]):
                        raise ValueError("관측과 연결할 기존 판단 자료를 찾지 못했습니다.")
                    published = db.execute("SELECT body FROM events WHERE workspace=? AND kind='decision_published'", (wid,)).fetchall()
                    if not any(json.loads(row["body"])["receipt_id"] == context.get("decision_id") for row in published):
                        raise ValueError("게시된 판단에 관측을 연결해 주세요.")
                    validate_feedback(context, json.loads(source["content"]))
                if body.get('context_update') is not None:
                    update=body['context_update']
                    required={'context_artifact_id','context_id','field','before','after','reason'}
                    if kind!='correction' or not isinstance(update,dict) or set(update)!=required:
                        raise ValueError('조건 정정 형식을 확인해 주세요.')
                    source=db.execute('SELECT content,kind,sha256 FROM artifacts WHERE workspace=? AND id=?',(wid,update['context_artifact_id'])).fetchone()
                    if not source or source['kind']!='judgment_context' or hashlib.sha256(source['content']).hexdigest()!=source['sha256']:
                        raise ValueError('원 조건 기록이 없습니다.')
                    context=json.loads(source['content'])['context']
                    original=next((c for c in context['contexts'] if c['id']==update['context_id']),None)
                    fields={'organism','target_construct_variant','transcript_version','tissue_cell','intervention_chemistry_formulation','dose_route','time','assay_buffer','comparator'}
                    if not original or update['field'] not in fields or update['before']!=original[update['field']]:
                        raise ValueError('정정 전 원 조건과 일치하지 않습니다.')
                    if not all(isinstance(update[k],str) and update[k].strip() for k in ('after','reason')):
                        raise ValueError('새 조건과 정정 이유가 필요합니다.')
                    rc=body.get('research_context',{})
                    if not rc or not any(b['context_id']==update['context_id'] and b['hypothesis_id'] in rc['hypothesis_ids'] for b in context['bindings']):
                        raise ValueError('정정할 조건과 가설의 연결이 다릅니다.')
            else:
                raise ValueError("지원하지 않는 수정 종류입니다.")
            db.execute("UPDATE workspaces SET rev=rev+1,review_status='needs_review' WHERE id=?", (wid,))
            self.event(db, wid, kind, event)
            result = {"state_rev": expected_rev + 1, "message_id": event["message_id"]}
            if body.get('review_requested'):
                from .interaction import register_followthrough
                result['review_request_id'] = register_followthrough(self,db,wid,expected_rev+1,event['message_id'])
            db.execute("INSERT INTO commands VALUES(?,?,?,?)", (wid, command_id, payload, dump(result)))
            return result

    @staticmethod
    def artifact_meta(row):
        return {**dict(row), "meta": json.loads(row["meta"])}

    def add_artifact(self, wid, title, kind, content, meta, media="application/json", bump=True):
        aid, digest = uid("art"), hashlib.sha256(content).hexdigest()
        with self.connect(True) as db:
            self.workspace(db, wid)
            db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?)",
                       (aid, wid, title, kind, digest, media, now(), dump(meta), content))
            self.event(db, wid, "artifact_added", {"artifact_id": aid, "title": title, "kind": kind})
            if bump:
                db.execute("UPDATE workspaces SET rev=rev+1,review_status='needs_review' WHERE id=?", (wid,))
        return aid

    def artifact(self, wid, aid):
        with self.connect() as db:
            row = db.execute("SELECT * FROM artifacts WHERE id=? AND workspace=?", (aid, wid)).fetchone()
            if row is None:
                raise KeyError("이 워크스페이스의 자료가 아닙니다.")
            result = self.artifact_meta(row)
            if hashlib.sha256(result["content"]).hexdigest() != result["sha256"]:
                raise ValueError("저장 자료의 무결성 검사가 실패했습니다.")
            return result

    def enqueue(self, wid, expected_rev, kind, request, cache_key=None):
        jid, attempt = uid("job"), uid("attempt")
        with self.connect(True) as db:
            state = self.workspace(db, wid)
            if state["rev"] != expected_rev:
                raise Conflict("자료가 변경되었습니다. 최신 상태에서 실행해 주세요.")
            if kind == "planner" and db.execute("SELECT 1 FROM jobs WHERE workspace=? AND kind IN ('planner','research_check') "
                    "AND status IN ('queued','running')", (wid,)).fetchone():
                raise Conflict("이 연구의 모델 작업이 이미 진행 중입니다.")
            if kind == "planner" and request.get('resume_from_job'):
                latest = db.execute("SELECT id FROM jobs WHERE workspace=? AND kind='planner' ORDER BY created DESC LIMIT 1", (wid,)).fetchone()
                if not latest or latest['id'] != request['resume_from_job']:
                    raise Conflict("다른 작업이 먼저 시작됐습니다. 중복 재개하지 않습니다.")
            db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,NULL,NULL,?,?)",
                       (jid, wid, expected_rev, kind, dump(request), "queued", now(), now(), cache_key, attempt))
            self.event(db, wid, "job_queued", {"job_id": jid, "kind": kind, "based_rev": expected_rev})
        return jid

    def start_job(self, jid):
        with self.connect(True) as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
            if not row or row["status"] != "queued":
                return None
            db.execute("UPDATE jobs SET status='running',updated=? WHERE id=?", (now(), jid))
            self.event(db, row["workspace"], "job_started", {"job_id": jid, "kind": row["kind"]})
            return {**dict(row), "request": json.loads(row["request"])}

    def claim_check(self, wid, expected_rev, source_decision, check_id):
        """One execution per published check, including repeated UI/network requests."""
        with self.connect(True) as db:
            old = db.execute("SELECT job_id FROM research_checks WHERE workspace=? AND decision_id=? AND check_id=?",
                             (wid, source_decision, check_id)).fetchone()
            if old:
                return old["job_id"], False
            current = self.workspace(db, wid)
            if current["rev"] != expected_rev or current["decision_rev"] != expected_rev or not current["decision"]:
                raise Conflict("연구 조건이 바뀌었습니다. 현재 판단을 확인해 주세요.")
            published = db.execute("SELECT body FROM events WHERE workspace=? AND kind='decision_published' ORDER BY seq DESC LIMIT 1",
                                   (wid,)).fetchone()
            if not published or json.loads(published["body"])["receipt_id"] != source_decision:
                raise Conflict("다른 판단이 먼저 저장되었습니다. 현재 판단을 확인해 주세요.")
            if db.execute("SELECT 1 FROM jobs WHERE workspace=? AND kind IN ('planner','research_check') AND status IN ('queued','running')",
                          (wid,)).fetchone():
                raise Conflict("현재 연구 판단 또는 후속 확인이 진행 중입니다.")
            check = next((c for c in json.loads(current["decision"]).get("research_loop", {}).get("next_checks", [])
                          if c["id"] == check_id), None)
            if check is None or check["operation"]["kind"] != "tool":
                raise ValueError("직접 실행 가능한 확인이 아닙니다. 필요한 자료나 관측을 연결해 주세요.")
            jid, attempt = uid("job"), uid("attempt")
            request = {"decision_id": source_decision, "check": check}
            db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,NULL,NULL,NULL,?)",
                       (jid, wid, expected_rev, "research_check", dump(request), "queued", now(), now(), attempt))
            db.execute("INSERT INTO research_checks VALUES(?,?,?,?,NULL)", (wid, source_decision, check_id, jid))
            self.event(db, wid, "research_check_requested", {"job_id": jid, "decision_id": source_decision,
                       "check_id": check_id, "question": check["question"], "purpose": check["purpose"]})
            return jid, True

    def link_check_review(self, jid, review_job_id):
        with self.connect(True) as db:
            db.execute("UPDATE research_checks SET review_job_id=? WHERE job_id=?", (review_job_id, jid))

    def finish_job(self, jid, status, output_id=None, error=None):
        with self.connect(True) as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
            if row is None:
                raise KeyError(jid)
            db.execute("UPDATE jobs SET status=?,output_id=?,error=?,updated=? WHERE id=?",
                       (status, output_id, error, now(), jid))
            self.event(db, row["workspace"], "job_finished",
                       {"job_id": jid, "kind": row["kind"], "status": status, "output_id": output_id, "error": error})

    def reusable(self, wid, cache_key):
        with self.connect() as db:
            rows = db.execute("SELECT output_id FROM jobs WHERE workspace=? AND cache_key=? "
                              "AND status IN ('succeeded','reused') ORDER BY updated DESC", (wid, cache_key)).fetchall()
        for row in rows:
            try:
                artifact = self.artifact(wid, row["output_id"])
                if artifact["meta"].get("result_status") == "succeeded":
                    return artifact
            except (ValueError, KeyError):
                continue
        return None

    def publish_decision(self, wid, based_rev, proposal, receipt_id):
        with self.connect(True) as db:
            return self._publish_decision(db, wid, based_rev, proposal, receipt_id)

    def _publish_decision(self, db, wid, based_rev, proposal, receipt_id):
        current = self.workspace(db, wid)
        if current["rev"] != based_rev:
            self.event(db, wid, "decision_stale", {"based_rev": based_rev, "current_rev": current["rev"],
                                                   "receipt_id": receipt_id})
            return False
        from .research_loop import compare_hypothesis_wording
        prior_publication = db.execute("SELECT body FROM events WHERE workspace=? AND kind='decision_published' ORDER BY seq DESC LIMIT 1", (wid,)).fetchone()
        prior_frame = db.execute("SELECT seq,body FROM events WHERE workspace=? AND kind='work_framed' ORDER BY seq DESC LIMIT 1", (wid,)).fetchone()
        if current['decision']:
            reference = json.loads(current['decision']).get('research_loop', {}).get('hypotheses', [])
            origin = {'decision_id': json.loads(prior_publication['body'])['receipt_id'] if prior_publication else None,
                      'state_revision': current['decision_rev'], 'kind': 'previous_published_decision'}
        elif prior_frame:
            reference = json.loads(prior_frame['body']).get('hypotheses', [])
            origin = {'event_sequence': prior_frame['seq'], 'kind': 'latest_frame'}
        else:
            reference, origin = [], {'kind': 'no_prior_claims'}
        self.event(db, wid, 'hypothesis_wording_compared', {
            'receipt_id': receipt_id, 'reference': origin,
            'comparisons': compare_hypothesis_wording(reference, proposal.get('research_loop', {}).get('hypotheses', [])),
            'meaning': 'Literal wording comparison only; no automatic scientific reassessment or semantic equivalence judgment.'})
        # A model's draft cannot silently overwrite a researcher's explicitly edited records.
        previous = json.loads(current["intent"])
        edited = db.execute("SELECT body FROM events WHERE workspace=? AND kind='intent_edit' ORDER BY seq DESC LIMIT 1", (wid,)).fetchone()
        from .intent_records import override_ids
        edited_ids, deleted_ids = override_ids(json.loads(edited['body']) if edited else None)
        protected = {r["id"]: r for r in previous if r["id"] in edited_ids}
        proposed = {r["id"]: r for r in proposal["intent_records"] if r['id'] not in deleted_ids}
        proposed.update(protected)
        db.execute("UPDATE workspaces SET decision=?,decision_rev=?,review_status='reviewed',intent=? WHERE id=?",
                   (dump(proposal), based_rev, dump(list(proposed.values())), wid))
        self.event(db, wid, "decision_published", {"receipt_id": receipt_id, "state_rev": based_rev})
        return True

    def recover(self):
        # Process restart is not proof a remote request failed. Never silently bill twice.
        with self.connect(True) as db:
            rows = db.execute("SELECT * FROM jobs WHERE status IN ('running','queued')").fetchall()
            for row in rows:
                db.execute("UPDATE jobs SET status='interrupted',error=?,updated=? WHERE id=?",
                           ("프로세스 재시작으로 중단됨. 완료 자료를 확인한 뒤 다시 실행할 수 있습니다.", now(), row["id"]))
                self.event(db, row["workspace"], "job_interrupted", {"job_id": row["id"], "kind": row["kind"]})
            pending = db.execute("SELECT id,workspace FROM followthrough_requests WHERE status='pending'").fetchall()
            for row in pending:
                reason = '재시작 전 접수한 검토입니다. 원 실행·완료 자료를 확인한 뒤 이어서 검토를 선택해 주세요.'
                db.execute("UPDATE followthrough_requests SET status='needs_confirmation',error=? WHERE id=?",(reason,row['id']))
                self.event(db,row['workspace'],'followthrough_attention',{'request_id':row['id'],'reason':reason})
        return len(rows)
