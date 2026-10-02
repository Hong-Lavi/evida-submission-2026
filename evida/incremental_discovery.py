"""Persist explicitly marked findings without adding a model/tool round.

Notes and their unreviewed options share one transaction. This does not extract
scientific meaning from arbitrary prose or certify that a citation supports it.
"""
import hashlib
import json

import jsonschema

from .contracts import RESEARCH_NOTES
from .discovery import catalog, validate_review
from .store import Conflict, dump, now, uid


def _prior(db, wid, jid, call_id, rev, digest):
    if call_id is None:
        return None
    for row in db.execute(
        "SELECT id,sha256,meta FROM artifacts WHERE workspace=? AND kind='research_notes'", (wid,)
    ):
        meta = json.loads(row["meta"])
        if meta.get("job_id") == jid and meta.get("model_call_id") == call_id:
            if row["sha256"] != digest or meta.get("based_rev") != rev:
                raise Conflict("같은 호출의 연구 메모 내용이나 조건이 달라졌습니다.")
            return row["id"]
    return None


def _insert(store, db, wid, aid, title, kind, content, meta):
    db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?)",
        (aid, wid, title, kind, hashlib.sha256(content).hexdigest(),
         "application/json", now(), dump(meta), content))
    store.event(db, wid, "artifact_added", {"artifact_id": aid, "title": title, "kind": kind})


def record_notes(store, wid, rev, jid, notes, *, call_id=None):
    jsonschema.validate(notes, RESEARCH_NOTES)
    content = dump(notes).encode()
    digest = hashlib.sha256(content).hexdigest()
    with store.connect() as db:
        existing = _prior(db, wid, jid, call_id, rev, digest)
    if existing:
        return existing
    state = store.snapshot(wid)
    known = {a["id"] for a in state["artifacts"]} | {
        e["body"]["message_id"] for e in state["events"] if e["body"].get("message_id")}
    if any(source not in known for f in notes["findings"] for source in f["source_ids"]):
        raise ValueError("연구 메모의 출처가 현재 연구에 없습니다.")
    options = {}
    for finding in notes["findings"]:
        marker = finding.get("discovery_option")
        if marker is None:
            continue
        key = marker["option_id"]
        if key in options:
            option = options[key]
            if option["label"] != marker["label"]:
                raise ValueError("하나의 선택지 ID에 서로 다른 이름을 붙일 수 없습니다.")
            if finding["text"] != option["description"]:
                option["description"] += "\n" + finding["text"]
            option["source_ids"] = list(dict.fromkeys(option["source_ids"] + finding["source_ids"]))
        else:
            options[key] = {"option_id": key, "kind": key.split(":", 1)[0],
                "label": marker["label"], "description": finding["text"],
                "source_ids": list(finding["source_ids"])}
    review = None
    if options:
        review = {"question": notes["next_goal"] or "탐색 중 발견한 선택지",
            "new_options": list(options.values()), "assessments": [],
            # An incremental discovery cannot silently clear previous search gaps.
            "unsearched_scope": catalog(store, wid, state)["unsearched_scope"]}
        validate_review(store, wid, rev, review)
    aid, review_id = uid("art"), uid("art") if review else None
    meta = {"based_rev": rev, "job_id": jid, "model_call_id": call_id,
            "semantic_type": "model_authored_notes_not_validation",
            "discovery_review_id": review_id}
    with store.connect(True) as db:
        existing = _prior(db, wid, jid, call_id, rev, digest)
        if existing:
            return existing
        if review and store.workspace(db, wid)["rev"] != rev:
            raise Conflict("연구 조건이 바뀌어 이전 조건의 선택지를 게시하지 않았습니다.")
        store.workspace(db, wid)
        _insert(store, db, wid, aid, "이어갈 연구 메모", "research_notes", content, meta)
        if review:
            _insert(store, db, wid, review_id, "탐색 중 발견한 선택지", "discovery_review",
                dump(review).encode(), {**meta, "source_notes_id": aid,
                    "semantic_type": "explicit_model_proposal_not_scientific_validation",
                    "incremental": True, "omission_deletes_options": False})
    return aid
