"""Start a fresh research workspace from hash-verified public source files."""
import hashlib

from .store import uid


def import_saved_example(store, examples, name):
    if name not in examples:
        raise ValueError("등록된 공개 사례를 선택해 주세요.")
    example = examples[name]
    verified = []
    # Check the entire input set before creating a workspace. Never copy old
    # calculations, model answers or synthetic measurements into a fresh run.
    for source in example["sources"]:
        with store.connect() as db:
            row = db.execute("SELECT id,workspace FROM artifacts WHERE sha256=? AND kind=? ORDER BY created LIMIT 1",
                             (source["sha256"], source["kind"])).fetchone()
        if row is None:
            raise ValueError("보존된 공개 원자료가 없습니다. 공개 자료 불러오기를 사용해 주세요.")
        artifact = store.artifact(row["workspace"], row["id"])
        if hashlib.sha256(artifact["content"]).hexdigest() != source["sha256"]:
            raise ValueError("보존된 원자료 해시가 다릅니다. 새 연구를 만들지 않았습니다.")
        verified.append((source, artifact))
    state = store.create(example["title"] + " · 새 실행")
    wid = state["id"]
    store.command(wid, state["rev"], uid("cmd"),
                  {"kind": "message", "text": example["request"], "synthetic": True})
    for source, artifact in verified:
        store.add_artifact(wid, source["title"], source["kind"], artifact["content"],
            {**source["meta"], "original_filename": source["filename"],
             "source": artifact["meta"].get("source"), "source_url": source["url"],
             "source_mode": "verified_saved_public_source", "rights": source["rights"],
             "preserved_source_artifact": artifact["id"], "verified_sha256": source["sha256"]},
            source["media_type"])
    return store.snapshot(wid)
