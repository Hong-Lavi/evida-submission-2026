"""Local research workbench. Only the product process receives its gateway key."""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import mimetypes
import re
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .contracts import CAPABILITIES
from .gateway import Gateway, GatewayError
from .runner import Runner
from .research_loop import decision_id
from .science import fetch
from .store import Conflict, Store, dump, uid



LOOPBACK = re.compile(r"(?:127\.0\.0\.1|localhost)(?::\d+)?", re.IGNORECASE)


def host_allowed(host, public_hosts=()):
    """Loopback always; a configured public name as well, and nothing else.

    The list is empty unless a public instance was started deliberately, so the default stays what
    it was: this server answers only a browser on the same machine."""
    host = (host or "").strip()
    if LOOPBACK.fullmatch(host):
        return True
    name = host.rsplit(":", 1)[0] if host.count(":") == 1 and host.rsplit(":", 1)[1].isdigit() else host
    return any(name.lower() == allowed.lower() for allowed in public_hosts if allowed)


def origin_allowed(origin, host):
    """An Origin that is present has to be this same page.

    Loopback is served over http and a public host over https, so each name accepts the one scheme
    it is actually reached by rather than both."""
    if not origin:
        return True
    return origin == ("http://" if LOOPBACK.fullmatch(host or "") else "https://") + host


class Application:
    def __init__(self, root, db_path=None, enable_model=False, model="gpt-5.6-terra", effort="high",
                 maximum_requests=None):
        self.root = Path(root)
        self.store = Store(db_path or self.root / "runs/evida.sqlite3")
        self.lock = self.store.path.with_suffix(".lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            raise RuntimeError("같은 연구 저장소를 사용하는 제품 프로세스가 이미 실행 중입니다.") from None
        self.store.recover()
        self.gateway = Gateway(json.loads((self.root / "configs/api_policy.json").read_text()),
                               enable_model, model, effort, maximum_requests=maximum_requests)
        self.runner = Runner(root, self.store, self.gateway)
        self.examples = json.loads((self.root / "configs/public-examples.json").read_text())
        from .semantic_literature import SemanticLiterature
        self._semantic_literature = SemanticLiterature(self.root)

    def import_example(self, name):
        if name not in self.examples:
            raise ValueError("등록된 공개 사례가 아닙니다.")
        example = self.examples[name]
        state = self.store.create(example["title"])
        wid = state["id"]
        self.store.command(wid, state["rev"], uid("cmd"),
                           {"kind": "message", "text": example["request"], "synthetic": True})
        for source in example["sources"]:
            try:
                body, receipt = fetch(source["url"])
                if hashlib.sha256(body).hexdigest() != source["sha256"]:
                    raise ValueError("공개 파일 내용이 조사 때와 바뀌었습니다. 새 판본 확인이 필요합니다.")
                self.store.add_artifact(wid, source["title"], source["kind"], body,
                    {**source["meta"], "source": receipt, "original_filename": source["filename"],
                     "source_mode": "public_download", "rights": source["rights"]}, source["media_type"])
            except Exception as exc:
                with self.store.connect(True) as db:
                    self.store.event(db, wid, "source_import_failed", {"title": source["title"], "error": str(exc)[:600]})
        return self.store.snapshot(wid)


def handler_for(app, public_hosts=()):
    # Empty unless a public instance was started deliberately; see host_allowed.
    public_hosts = tuple(public_hosts or ())

    class Handler(BaseHTTPRequestHandler):
        server_version = "EVIDA"

        def log_message(self, fmt, *args):
            # Do not print URLs, query text, request bodies or authentication material.
            pass

        def check_local(self):
            host = self.headers.get("Host", "")
            if not host_allowed(host, public_hosts):
                raise ValueError("허용되지 않은 호스트입니다.")
            if self.command == "POST":
                if self.headers.get("X-Evida-Request") != "1":
                    raise ValueError("화면에서 요청을 다시 실행해 주세요.")
                if not origin_allowed(self.headers.get("Origin"), host):
                    raise ValueError("다른 출처의 수정 요청입니다.")
                if self.headers.get_content_type() != "application/json":
                    raise ValueError("JSON 요청만 지원합니다.")

        def send(self, value, status=200, media="application/json", download=None):
            data = dump(value).encode() if media == "application/json" and not isinstance(value, bytes) else value
            self.send_response(status)
            self.send_header("Content-Type", media + ("; charset=utf-8" if media.startswith("text/") else ""))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            if download:
                self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{urllib.parse.quote(download)}")
            self.end_headers()
            self.wfile.write(data)

        def body(self):
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 15 * 1024 * 1024:
                raise ValueError("요청 크기를 확인해 주세요.")
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict):
                raise ValueError("요청은 객체여야 합니다.")
            return value

        def do_GET(self):
            self.dispatch(False)

        def do_POST(self):
            self.dispatch(True)

        def dispatch(self, post):
            try:
                self.check_local()
                parsed = urllib.parse.urlparse(self.path)
                route = parsed.path.strip("/").split("/")
                query = urllib.parse.parse_qs(parsed.query)
                if not post and parsed.path == "/api/status":
                    return self.send({"gateway": app.gateway.status(), "capabilities": CAPABILITIES,
                                      "examples": [{"id": k, "title": v["title"], "description": v["description"]}
                                                   for k, v in app.examples.items()]})
                if route == ["api", "workspaces"]:
                    if post:
                        title = str(self.body().get("title", "새 연구"))[:160].strip() or "새 연구"
                        return self.send(app.store.create(title), 201)
                    return self.send(app.store.list())
                if route == ["api", "team-examples"] and post:
                    from .saved_examples import import_saved_example
                    return self.send(import_saved_example(app.store, app.examples, self.body().get("id")), 201)
                if route == ["api", "examples"] and post:
                    return self.send(app.import_example(self.body().get("id")), 201)
                if len(route) >= 3 and route[:2] == ["api", "workspaces"]:
                    wid = route[2]
                    if len(route) == 3 and not post:
                        state = app.store.snapshot(wid)
                        from .semantic_literature import availability as semantic_availability
                        state['semantic_literature'] = semantic_availability(app.root, state)
                        state["decision_id"] = decision_id(state)
                        from .research_progress import view as progress_view
                        state['research_progress'] = progress_view(app.store, wid, state)
                        state['explanations'] = []
                        for artifact in [a for a in state['artifacts'] if a['kind']=='explanation_answer'][-8:]:
                            value = json.loads(app.store.artifact(wid,artifact['id'])['content'])
                            state['explanations'].append({**value,'artifact_id':artifact['id'],'created':artifact['created']})
                        from .judgment_context import view as context_view
                        state['judgment_context']=context_view(app.store,wid,state)
                        from .discovery import overview
                        state['discovery']=overview(app.store,wid,state,for_ui=True)
                        state["check_readiness"] = {c["id"]: app.runner.check_readiness(wid, c) for c in
                            (state["decision"] or {}).get("research_loop", {}).get("next_checks", [])}
                        from .planner_recovery import prepare_quota_resume
                        latest = next((j for j in reversed(state['jobs']) if j['kind'] == 'planner'), None)
                        state['quota_resume'] = None
                        if latest and latest['status'] == 'quota_or_rate_limit':
                            try:
                                prepared = prepare_quota_resume(app.runner, wid, state['rev'], latest['id'])
                                state['quota_resume'] = {'source_job': latest['id'], 'remaining_rounds': 16 - prepared['completed_rounds']}
                            except (ValueError, OSError, KeyError):
                                pass
                        return self.send(state)
                    if len(route)==4 and route[3]=='hypothesis-history' and not post:
                        from .evidence_history import view as history_view
                        return self.send(history_view(app.store,wid,query.get('hypothesis_id',[''])[0],
                            int(query.get('offset',['0'])[0]),int(query.get('limit',['4'])[0])))
                    if len(route)==4 and route[3]=='semantic-literature' and not post:
                        return self.send(app._semantic_literature.search(app.store, wid,
                            query.get('query',[''])[0], int(query.get('offset',['0'])[0]),
                            int(query.get('limit',['10'])[0])))
                    if len(route)==5 and route[3]=='semantic-literature':
                        if route[4]=='status' and not post:
                            return self.send(app._semantic_literature.status(app.store, wid))
                        if route[4]=='index' and post:
                            self.body()  # Consume the explicit empty JSON action; no model command.
                            from .semantic_index_service import IndexBusy
                            try:
                                return self.send(app._semantic_literature.start_index(app.store, wid), 202)
                            except IndexBusy as error:
                                return self.send({'error': str(error)}, 409)
                    if len(route)==4 and route[3]=='mechanism-ranking' and not post:
                        # Screen only: the computed order stays out of the model context.
                        from .discovery import mechanism_ranking_view
                        return self.send(mechanism_ranking_view(app.store,wid,
                            with_support=query.get('support')==['1']))
                    if len(route)==4 and route[3]=='candidate-structures' and not post:
                        # Screen only, like the ranking: a drawing must not enter a model request.
                        from .discovery import candidate_structures_view
                        return self.send(candidate_structures_view(app.store,wid,option_id=query.get('option_id',[None])[0]))
                    if len(route)==4 and route[3]=='discovery-options' and not post:
                        from .discovery import inspect as inspect_options
                        return self.send(inspect_options(app.store,wid,query.get('query',[''])[0],query.get('kind',[''])[0],
                            int(query.get('offset',['0'])[0]),int(query.get('limit',['20'])[0])))
                    if len(route) == 4 and post:
                        body = self.body()
                        if route[3] in ('discovery-select','discovery-proposals'):
                            from .discovery import choice_command
                            result = choice_command(app.store,wid,body,proposal=route[3]=='discovery-proposals')
                            from .interaction import dispatch_followthrough
                            dispatch_followthrough(app.runner,wid)
                            return self.send(result)
                        if route[3] == "commands":
                            if type(body.get("expected_rev")) is not int or not isinstance(body.get("command_id"), str):
                                raise ValueError("수정 요청의 버전 또는 ID가 없습니다.")
                            result = app.store.command(wid, body["expected_rev"], body["command_id"], body["body"])
                            from .interaction import dispatch_followthrough
                            dispatch_followthrough(app.runner,wid)
                            return self.send(result)
                        if route[3] == 'review-requests':
                            from .interaction import request_followthrough, dispatch_followthrough
                            result = request_followthrough(app.store,wid,body.get('expected_rev'),body.get('command_id'))
                            dispatch_followthrough(app.runner,wid)
                            return self.send(result,202)
                        if route[3] == 'explanations':
                            if not app.runner.gateway.status()['available']:
                                raise ValueError(app.runner.gateway.status()['message'])
                            from .interaction import enqueue_explanation, run_explanation
                            result, created = enqueue_explanation(app.store,wid,body.get('expected_rev'),
                                                                  body.get('command_id'),body.get('question'))
                            if created:
                                app.runner.explanation_pool.submit(run_explanation,app.runner,result['job_id'])
                            return self.send(result,202)
                        if route[3] == "jobs":
                            return self.send({"job_id": app.runner.start(wid, body["expected_rev"], body["tool"], body.get("arguments", {}))}, 202)
                        if route[3] == "resume-planner":
                            return self.send({"job_id": app.runner.resume_quota(wid, body["expected_rev"], body["source_job"])}, 202)
                        if route[3] == "research-checks":
                            return self.send({"job_id": app.runner.start_check(wid, body["expected_rev"], body["decision_id"], body["check_id"])}, 202)
                        if route[3] == "artifacts":
                            kind = body.get("kind")
                            if kind not in ("molecule_csv", "rna_table"):
                                raise ValueError("첫 구현은 기존 후보 CSV와 RNA 처리표 업로드를 지원합니다.")
                            content = base64.b64decode(body["content_base64"], validate=True)
                            if len(content) > 10 * 1024 * 1024:
                                raise ValueError("파일은 10 MiB 이내로 올려 주세요.")
                            meta = body.get("meta", {})
                            if not isinstance(meta, dict):
                                raise ValueError("자료 메타데이터 형식이 올바르지 않습니다.")
                            title = str(body.get("title", "사용자 자료"))[:180]
                            return self.send({"artifact_id": app.store.add_artifact(wid, title, kind, content,
                                {**meta, "source_mode": "researcher_upload", "scientific_context_verified": False},
                                "application/octet-stream" if kind == "rna_table" else "text/csv")}, 201)
                    if len(route) == 5 and route[3] == "artifacts" and not post:
                        if query.get('references')==['1']:
                            return self.send(app.runner.read_view(wid,'inspect_article_references',{
                                'artifact_id':route[4], 'reference_ids':query.get('reference_id',[]),
                                'offset':int(query.get('offset',['0'])[0]),'limit':int(query.get('limit',['30'])[0])}))
                        if query.get("original") == ["1"]:
                            artifact = app.store.artifact(wid, route[4])
                            if artifact['kind'] != 'repository_document':
                                raise ValueError('원본 문서가 보존된 자료를 선택해 주세요.')
                            document = json.loads(artifact['content'])
                            encoded = document.get('original_file_base64') or document.get('original_docx_base64')
                            if not encoded:
                                raise ValueError('파일 목록에는 원본 본문이 없습니다.')
                            raw = base64.b64decode(encoded, validate=True)
                            if document.get('original_sha256') and hashlib.sha256(raw).hexdigest() != document['original_sha256']:
                                raise ValueError('보존된 원본의 해시를 확인할 수 없습니다.')
                            filename = Path(document['filename']).name
                            media = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
                            return self.send(raw, media=media, download=None if media == 'application/pdf' else filename)
                        if 'figure' in query:
                            # A figure image already retrieved for this article, served from cache.
                            artifact = app.store.artifact(wid, route[4])
                            if artifact['kind'] != 'article':
                                raise ValueError('그림은 공개 원문 자료에서만 볼 수 있습니다.')
                            document = json.loads(artifact['content'])
                            from .article_figures import figure_rows, load
                            named = {name for figure in figure_rows(document)
                                     for name in figure['files'] + figure['thumbnails']}
                            wanted = query['figure'][0]
                            if wanted not in named:
                                raise ValueError('이 원문이 가리키는 그림 파일이 아닙니다.')
                            try:
                                data, media = load(document.get('pmc_id'), wanted,
                                                   app.root / '.figure-cache')
                            except KeyError:
                                return self.send({'error': '이 그림은 아직 회수되지 않았습니다.'}, 404)
                            return self.send(data, media=media)
                        if query.get("image") == ["1"]:
                            artifact = app.store.artifact(wid, route[4])
                            if artifact['media_type'] not in ('image/png','image/jpeg','image/webp'):
                                raise ValueError('표시할 수 있는 원 이미지가 아닙니다.')
                            return self.send(artifact['content'], media=artifact['media_type'])
                        if query.get("download") == ["1"]:
                            artifact = app.store.artifact(wid, route[4])
                            filename = artifact["meta"].get("original_filename") or (artifact["id"] + ".json")
                            return self.send(artifact["content"], media=artifact["media_type"], download=Path(filename).name)
                        if 'calculation_section' in query:
                            return self.send(app.runner.calculation_section(wid, route[4], query['calculation_section'][0],
                                int(query.get('offset', [0])[0]), int(query.get('limit', [30])[0])))
                        return self.send(app.runner.inspect(wid, route[4], int(query.get("offset", [0])[0]),
                                                            int(query.get("limit", [30])[0]), query.get("candidate_query", [None])[0],
                                                            depict=True))
                    if len(route) == 4 and route[3] == "export" and not post:
                        state = app.store.snapshot(wid)
                        return self.send(dump(state).encode(), download=f"evida-{wid}.json")
                if not post:
                    relative = "index.html" if parsed.path in ("/", "/index.html") else parsed.path.lstrip("/")
                    root = (app.root / "web").resolve()
                    file = (root / relative).resolve()
                    if not file.is_relative_to(root) or not file.is_file():
                        return self.send({"error": "페이지가 없습니다."}, 404)
                    return self.send(file.read_bytes(), media=mimetypes.guess_type(file.name)[0] or "application/octet-stream")
                self.send({"error": "지원하지 않는 요청입니다."}, 404)
            except Conflict as exc:
                self.send({"error": str(exc)}, 409)
            except GatewayError as exc:
                self.send({"error": str(exc), "status": exc.status}, 409)
            except (ValueError, KeyError, TypeError) as exc:
                self.send({"error": str(exc)[:700]}, 400)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                self.send({"error": "요청 처리 중 오류가 발생했습니다. 저장한 연구 자료는 유지됩니다."}, 500)
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--enable-model", action="store_true")
    parser.add_argument("--model", default="gpt-5.6-terra")
    parser.add_argument("--effort", default="high", choices=["high", "xhigh", "max"])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    app = Application(root, args.db, args.enable_model, args.model, args.effort)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(app))
    print(f"EVIDA ready: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.runner.pool.shutdown(wait=True)
        app.runner.explanation_pool.shutdown(wait=True)
        app.lock.close()


if __name__ == "__main__":
    main()
