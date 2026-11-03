"""Independent event-schedule replay of real product state functions.

No test module, model, network, GPU or scientific truth oracle is used. The two
arms receive identical substantive scripted proposals. The new arm additionally
receives its required declared-consumption sidecar, authored by this fixture.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
FAMILIES = [
    {"id": "valid_unchanged", "between_prepare_commit": "none", "expected_publish": True},
    {"id": "different_revision_correction", "between_prepare_commit": "correction", "expected_publish": False},
    {"id": "same_revision_reframe", "between_prepare_commit": "reframe", "expected_publish": False},
    {"id": "same_revision_publication", "between_prepare_commit": "publication", "expected_publish": False},
    {"id": "transaction_abort", "between_prepare_commit": "sqlite_abort_trigger", "expected_publish": False},
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def fingerprint(product):
    return {str(p.relative_to(product)): sha(p.read_bytes())
            for folder in ("evida", "configs", "scripts") for p in sorted((product / folder).rglob("*"))
            if p.is_file() and p.suffix in (".py", ".md", ".json", ".R", ".sql")}


def make_plan(current, improved, output):
    if output.exists():
        raise FileExistsError("Existing replay preserved; choose a new directory")
    output.mkdir(parents=True)
    plan = {"status": "PREPARED_NOT_EXECUTED", "script_sha256": sha(Path(__file__).read_bytes()),
            "families": FAMILIES, "model_calls": 0, "network_calls": 0,
            "independent_unit": "five predeclared software event families, not scientific tasks",
            "arms": {name: {"product": str(path.resolve().relative_to(HERE)), "files": fingerprint(path.resolve())}
                     for name, path in (("current", current), ("improved", improved))},
            "expected": "Accept a valid unchanged proposal; reject stale prepared proposals after input/context/publication changes; roll back atomic failures; retain source and original proposals.",
            "interface_difference": "Improved receives required intent_review metadata; substantive source, intent, question and decision are identical. This evaluates enforcement with scripted declarations, not a model's ability to author them.",
            "not_measured": ["scientific judgment", "effect-direction accuracy", "model compliance", "real production concurrency frequency"]}
    save(output / "plan.json", plan)
    return {"status": plan["status"], "plan": str(output / "plan.json"), "families": len(FAMILIES), "model_calls": 0}


def verify(plan):
    if sha(Path(__file__).read_bytes()) != plan["script_sha256"]:
        raise ValueError("Replay script changed after plan")
    for arm, info in plan["arms"].items():
        if fingerprint(HERE / info["product"]) != info["files"]:
            raise ValueError(f"Product code changed after plan: {arm}; preserve this plan and freeze a new one")


def one_arm(plan_path, arm):
    plan = json.loads(plan_path.read_text())
    product = HERE / plan["arms"][arm]["product"]
    if fingerprint(product) != plan["arms"][arm]["files"]:
        raise ValueError("Product code differs from lock")
    sys.path.insert(0, str(product))
    from evida.store import Store, dump
    from evida.runner import Runner
    from evida.finalization import prepare, commit, finalize
    new = arm == "improved"
    if (product / "evida/intent_dependencies.py").exists() != new:
        raise ValueError("Locked product does not match the declared interface arm")
    output = plan_path.parent / arm
    output.mkdir(exist_ok=False)
    rows = []
    for spec in plan["families"]:
        directory = output / spec["id"]
        directory.mkdir()
        row = {"arm": arm, "family": spec["id"], "status": "RUNNING", "model_calls": 0,
               "expected_publish": spec["expected_publish"], "actual_publish": None, "checks": {}}
        started = time.monotonic()
        runner = None
        trace = []
        try:
            store = Store(directory / "state.sqlite3")
            wid = store.create("Synthetic software-state replay; no scientific result")["id"]
            # Offline bootstrap only; the pinned native state methods are unchanged.
            runner = Runner.__new__(Runner)
            runner.store = store
            delivery_path = product / "configs/context-delivery.json"
            runner.context_recent_views = json.loads(delivery_path.read_text())["recent_views"]
            source_bytes = b'{"synthetic":true,"observation":"fixed supplied record; no efficacy claim"}'
            source_id = store.add_artifact(wid, "Fixed synthetic source", "source_text", source_bytes,
                                           {"synthetic": True, "scientific_validation": False}, bump=False)
            intents = [
                {"id": "goal", "label": "Goal", "text": "Review endpoint A using the supplied source", "origin": "inferred", "source_refs": []},
                {"id": "boundary", "label": "Boundary", "text": "Retain source and prior decisions", "origin": "inferred", "source_refs": []},
            ]
            question = "What does the supplied record establish about endpoint A?"

            def token():
                context = runner.model_context(wid, store.snapshot(wid)["rev"], True)
                return context.get("INTENT_DEPENDENCIES", {}).get("input_snapshot", {}).get("snapshot_sha256")

            def review(*, frame=False, first=False):
                consumers = [("question", "current_question")]
                if not frame:
                    consumers.append(("recommendation", "recommendation"))
                return {
                    "uses": [{"consumer_kind": kind, "consumer_id": identifier,
                              "intent_ids": ["goal", "boundary"],
                              "reason": "Scripted replay declaration; not an actual model judgment."}
                             for kind, identifier in consumers],
                    "reassessments": ([{"consumer_kind": "question", "consumer_id": "current_question",
                                         "outcome": "changed", "reason": "Scripted initial framing; no earlier bound question."}]
                                      if first else []),
                }

            def frame(text, first=False):
                args = {"intent_records": intents, "current_question": text,
                        "hypotheses": [], "task_brief": [], "questions": []}
                kwargs = {}
                if new:
                    args["intent_review"] = review(frame=True, first=first)
                    kwargs = {"require_intent_review": True, "expected_intent_snapshot": token()}
                runner.frame(wid, store.snapshot(wid)["rev"], args, **kwargs)
                trace.append({"event": "frame", "question": text, "revision": store.snapshot(wid)["rev"]})

            def bundle(recommendation, first=False):
                value = {"decision": {
                    "based_on_state_rev": store.snapshot(wid)["rev"], "intent_records": intents,
                    "action": "defer", "recommendation": recommendation,
                    "reason": "Scripted state-replay fixture; scientific content is intentionally fixed.",
                    "evidence_refs": [source_id], "alternatives": [], "changed": [], "preserved": [],
                    "unknowns": [], "next_actions": [], "questions": [],
                    "research_loop": {"hypotheses": [], "next_checks": [], "revision_rationale": "Software replay only"}},
                    "discovery_review": None, "judgment_context": None,
                    "hypothesis_review": {"schema_version": "2", "causal_steps": [], "observations": [],
                                          "scope": {"hypotheses": [], "checks": []}}}
                if new:
                    value["intent_review"] = review(first=first)
                return value

            def publish(value):
                kwargs = {"require_intent_review": True, "expected_intent_snapshot": token()} if new else {}
                return finalize(store, wid, store.snapshot(wid)["rev"], "scripted-replay", value,
                                True, [], None, **kwargs)

            frame(question, first=True)
            first_id, initial_published = publish(bundle("Initial preserved proposal", first=True))
            if not initial_published:
                raise ValueError("Initial setup could not publish")
            first_bytes = store.artifact(wid, first_id)["content"]
            value = bundle("Prepared pending proposal")
            save(directory / "scripted-proposal.json", value)
            kwargs = {"require_intent_review": True, "expected_intent_snapshot": token()} if new else {}
            revision = store.snapshot(wid)["rev"]
            proposal, sidecars = prepare(store, wid, revision, value, True, **kwargs)
            prepared_bytes = dump(proposal).encode()
            trace.append({"event": "prepare", "revision": revision, "proposal_sha256": sha(prepared_bytes)})
            event = spec["between_prepare_commit"]
            if event == "correction":
                store.command(wid, revision, "scripted-correction", {"kind": "correction", "text": "Endpoint B now matters; keep earlier records."})
            elif event == "reframe":
                frame("A new question was framed at the same state revision.")
            elif event == "publication":
                other_id, other_ok = publish(bundle("Intervening published proposal"))
                if not other_ok:
                    raise ValueError("Intervening publication setup failed")
                row["intervening_decision_id"] = other_id
            elif event == "sqlite_abort_trigger":
                with store.connect(True) as db:
                    db.execute("CREATE TRIGGER replay_abort_publication BEFORE UPDATE ON workspaces BEGIN SELECT RAISE(ABORT, 'scripted publication abort'); END")
            before_commit = store.snapshot(wid)
            save(directory / "before-commit.json", before_commit)
            trace.append({"event": event, "revision": before_commit["rev"]})
            try:
                pending_id, published = commit(store, wid, revision, "scripted-pending", proposal, sidecars, [], None)
                row["actual_publish"] = published
                pending = store.artifact(wid, pending_id)
                row["pending_decision_id"] = pending_id
                row["checks"]["pending_proposal_preserved"] = pending["content"] == prepared_bytes
                row["checks"]["stale_has_no_attached_sidecars"] = published or not pending["meta"]["finalization_records"]
            except sqlite3.IntegrityError as exc:
                if event != "sqlite_abort_trigger" or "scripted publication abort" not in str(exc):
                    raise
                row["actual_publish"] = False
                row["checks"]["atomic_rollback"] = store.snapshot(wid) == before_commit
            after = store.snapshot(wid)
            save(directory / "after-commit.json", after)
            row["checks"]["expected_publication_outcome"] = row["actual_publish"] == spec["expected_publish"]
            row["checks"]["source_bytes_preserved"] = store.artifact(wid, source_id)["content"] == source_bytes
            row["checks"]["initial_decision_preserved"] = store.artifact(wid, first_id)["content"] == first_bytes
            if not spec["expected_publish"]:
                row["checks"]["current_decision_not_replaced"] = after["decision"] == before_commit["decision"]
            row["status"] = "PASS" if all(row["checks"].values()) else "PROPERTY_FAILURE"
        except Exception as exc:
            row.update(status="HARNESS_OR_INTERFACE_FAILURE", error_type=type(exc).__name__, error=str(exc)[:600])
        finally:
            # No worker pools, gateway or scientific runtime are constructed here.
            pass
        row["elapsed_seconds"] = round(time.monotonic() - started, 3)
        save(directory / "trace.json", trace)
        save(directory / "result.json", row)
        rows.append(row)
    if fingerprint(product) != plan["arms"][arm]["files"]:
        raise ValueError("Product code changed during replay; results cannot be attributed to the locked version")
    loaded = {}
    for name, module in tuple(sys.modules.items()):
        if name == "evida" or name.startswith("evida."):
            path = Path(module.__file__).resolve()
            if not path.is_relative_to(product.resolve()):
                raise ValueError("A native module was loaded from outside the frozen arm")
            loaded[str(path.relative_to(product.resolve()))] = sha(path.read_bytes())
    save(output / "results.json", {"arm": arm, "rows": rows, "model_calls": 0,
                                   "passed": sum(r["status"] == "PASS" for r in rows), "denominator": len(rows),
                                   "native_modules_loaded": loaded})


def run(plan_path):
    plan = json.loads(plan_path.read_text())
    verify(plan)
    save(plan_path.parent / "started.json", {"model_calls": 0, "automatic_retry": False})
    for arm in ("current", "improved"):
        # Separate Python processes keep product modules from crossing arms.
        completed = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "_arm",
                                    "--plan", str(plan_path.resolve()), "--arm", arm], capture_output=True, text=True)
        save(plan_path.parent / f"{arm}-process.json", {"returncode": completed.returncode,
            "stdout": completed.stdout, "stderr": completed.stderr, "model_calls": 0})
        if completed.returncode:
            raise RuntimeError(f"{arm} replay failed; preserve its process record, do not silently restart")
    verify(plan)
    results = {arm: json.loads((plan_path.parent / arm / "results.json").read_text()) for arm in ("current", "improved")}
    summary = {"status": "SOFTWARE_REPLAY_COMPLETED", "model_calls": 0, "network_calls": 0,
               "independent_event_families": len(plan["families"]),
               "not_scientific_or_model_performance": True, "arms": results}
    save(plan_path.parent / "comparison.json", summary)
    return {"status": summary["status"], "model_calls": 0,
            "arms": {arm: {k: value[k] for k in ("passed", "denominator")} for arm, value in results.items()}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("plan")
    prepare_parser.add_argument("--current", type=Path, required=True)
    prepare_parser.add_argument("--improved", type=Path, required=True)
    prepare_parser.add_argument("--out", type=Path, required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--plan", type=Path, required=True)
    arm_parser = sub.add_parser("_arm")
    arm_parser.add_argument("--plan", type=Path, required=True)
    arm_parser.add_argument("--arm", choices=["current", "improved"], required=True)
    args = parser.parse_args()
    if args.command == "plan":
        result = make_plan(args.current, args.improved, args.out)
    elif args.command == "run":
        result = run(args.plan)
    else:
        one_arm(args.plan, args.arm)
        result = {"status": "ARM_FINISHED", "arm": args.arm, "model_calls": 0}
    print(json.dumps(result, indent=2))
