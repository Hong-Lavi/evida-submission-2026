"""Optional semantic reading order over an explicit retained-source index.

Nothing is added to a model prompt, decision, source pool or recommendation.
The subprocess gets only offline CPU settings, never the server environment.
"""
import atexit
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import selectors
import subprocess
import threading
import time


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, value):
        self.parts.append(value)


def _plain(value):
    parser = _Text()
    parser.feed(value or "")
    return re.sub(r"\s+", " ", unescape(" ".join(parser.parts))).strip()


def _index(root, workspace):
    root = Path(root).resolve()
    config_path = root / "configs/semantic-literature.json"
    if not config_path.exists():
        return None
    config = json.loads(config_path.read_text())
    entry = config.get("indexes", {}).get(workspace)
    if config.get("incremental", {}).get("enabled") is True:
        from .semantic_index import destination, workspace_directory
        pointer = destination(root, workspace_directory(workspace) / "current.json")
        if pointer.exists():
            entry = json.loads(pointer.read_text())
            if entry.get("workspace_id") != workspace:
                raise ValueError("이 연구의 문헌 색인이 아닙니다.")
    if config.get("enabled") is not True or not entry:
        return None
    path = (root / entry["manifest"]).resolve()
    if not path.is_relative_to(root / "semantic-literature-data"):
        raise ValueError("문헌 색인의 위치를 확인할 수 없습니다.")
    if digest(path) != entry["manifest_sha256"]:
        raise ValueError("문헌 색인이 준비된 내용과 다릅니다.")
    index = json.loads(path.read_text())
    if index.get("workspace_id") != workspace:
        raise ValueError("이 연구에 연결한 문헌 색인이 아닙니다.")
    return config, index, path


def availability(root, snapshot):
    try:
        config = json.loads((Path(root) / "configs/semantic-literature.json").read_text())
        incremental = config.get("enabled") is True and config.get("incremental", {}).get("enabled") is True
    except (ValueError, OSError):
        incremental = False
    extra = {"indexing_enabled": True, "state": "unindexed", "can_build": any(
        row["kind"] == "literature" for row in snapshot["artifacts"])} if incremental else {}
    try:
        prepared = _index(root, snapshot["id"])
    except (ValueError, OSError, KeyError, TypeError):
        # An optional index must never break the existing source view.
        return {**extra, "available": False, "reason": "index_unavailable"}
    if not prepared:
        return {**extra, "available": False}
    unused, index, path = prepared
    current = {row["id"]: row for row in snapshot["artifacts"]}
    expected = index["source_artifact_sha256"]
    if any(identifier not in current or current[identifier]["sha256"] != value
           for identifier, value in expected.items()):
        return {**extra, "available": False, "reason": "source_scope_changed"}
    new_searches = [row for row in current.values()
                    if row["kind"] == "literature" and row["id"] not in expected]
    return {**extra, "state": "pending" if new_searches else "ready",
            "available": True, "indexed_documents": len(index["documents"]),
            "indexed_search_records": len(expected), "unindexed_search_records": len(new_searches),
            "language": "English", "method": "MedCPT semantic relevance",
            "meaning": "초록 내용과 검색어가 가까운 순서입니다. 근거 강도나 치료 추천 순위가 아닙니다."}


def _check_sources(store, workspace, index):
    originals = {}
    for identifier, expected in index["source_artifact_sha256"].items():
        record = store.artifact(workspace, identifier)
        content = record["content"]
        content = content if isinstance(content, bytes) else content.encode()
        if record["kind"] != "literature" or record["sha256"] != expected or hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("이 연구의 원자료와 문헌 색인이 일치하지 않습니다.")
        originals[identifier] = json.loads(content)
    for document in index["documents"]:
        source = document["selected_source"]
        row = originals[source["artifact_id"]]
        for component in source["json_pointer"].strip("/").split("/"):
            row = row[int(component)] if isinstance(row, list) else row[component]
        if (_plain(row.get("title", "")) != document["title"]
                or _plain(row.get("abstractText", "")) != document["text"]):
            raise ValueError("반환할 초록과 보존한 원행이 일치하지 않습니다.")


class SemanticLiterature:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.process = None
        self.failed = False
        self.lock = threading.Lock()
        self.ready = None
        from .semantic_index_service import IncrementalIndex
        self.indexer = IncrementalIndex(self.root)
        atexit.register(self.close)

    def status(self, store, workspace):
        return self.indexer.status(store, workspace)

    def start_index(self, store, workspace):
        return self.indexer.start(store, workspace)

    def close(self):
        self.indexer.close()
        process, self.process = self.process, None
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()

    def _receive(self, timeout=40):
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            if not selector.select(timeout):
                raise TimeoutError("Local query encoder timed out")
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("Local query encoder exited")
        return json.loads(line)

    def _start(self, config):
        if self.failed:
            raise ValueError("의미 검색을 완료하지 못했습니다. 기존 원자료 보기를 이용해 주세요.")
        if self.process is not None:
            return
        environment = {
            "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "CUDA_VISIBLE_DEVICES": "",
            "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1", "TOKENIZERS_PARALLELISM": "false",
            "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "4", "MKL_NUM_THREADS": "4",
        }
        try:
            self.process = subprocess.Popen(
                [config["python"], "-B", str(self.root / "evida/medcpt_query_worker.py"),
                 config["query_assets"], config["query_assets_receipt"]],
                env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, bufsize=1, close_fds=True)
            self.ready = self._receive()
            if self.ready.get("status") != "ready" or self.ready.get("device") != "cpu":
                raise RuntimeError("Unexpected local encoder state")
        except Exception:
            self.failed = True
            self.close()
            raise ValueError("의미 검색을 준비하지 못했습니다. 기존 원자료 보기를 이용해 주세요.") from None

    def search(self, store, workspace, query, offset=0, limit=10):
        query = str(query).strip()
        if (not query or len(query) > 1024 or not re.search(r"[A-Za-z]", query)
                or re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", query)):
            raise ValueError("찾을 문헌 내용을 짧은 영문 검색어로 입력해 주세요.")
        if not 0 <= offset <= 2000 or not 1 <= limit <= 30:
            raise ValueError("문헌 범위를 다시 선택해 주세요.")
        prepared = _index(self.root, workspace)
        if not prepared:
            raise ValueError("이 연구에는 의미 검색용 문헌 묶음이 없습니다. 기존 원자료는 그대로 볼 수 있습니다.")
        config, index, manifest = prepared
        state = store.snapshot(workspace)
        scope = availability(self.root, state)
        if not scope["available"]:
            raise ValueError("이 연구의 원자료가 색인 범위와 다릅니다. 기존 원자료를 확인해 주세요.")
        _check_sources(store, workspace, index)
        vectors = (manifest.parent / index["vectors_file"]).resolve()
        if not vectors.is_relative_to(manifest.parent) or digest(vectors) != index["vectors_sha256"]:
            raise ValueError("문헌 색인의 계산 자료를 확인할 수 없습니다.")
        if not self.lock.acquire(timeout=1):
            raise ValueError("다른 문헌 검색을 처리하고 있습니다. 잠시 뒤 다시 선택해 주세요.")
        began = time.monotonic()
        try:
            self._start(config)
            request = {"query": query, "document_ids": [row["id"] for row in index["documents"]],
                       "vectors_file": str(vectors), "vectors_sha256": index["vectors_sha256"]}
            self.process.stdin.write(json.dumps(request) + "\n")
            self.process.stdin.flush()
            result = self._receive()
            if result.get("status") == "query_too_long":
                raise ValueError("검색어가 읽을 수 있는 길이를 넘었습니다. 조금 더 짧게 입력해 주세요.")
            if result.get("status") != "completed":
                raise RuntimeError("Local query calculation failed")
            order = result["order"]
            if sorted(order) != list(range(len(index["documents"]))) or len(result["scores"]) != len(order):
                raise RuntimeError("Invalid local retrieval order")
        except ValueError:
            raise
        except Exception:
            self.failed = True
            self.close()
            raise ValueError("의미 검색을 완료하지 못했습니다. 기존 자료와 판단은 유지됩니다.") from None
        finally:
            self.lock.release()
        rows = []
        for rank in range(offset, min(offset + limit, len(order))):
            document = index["documents"][order[rank]]
            rows.append({"rank": rank + 1, "document_id": document["id"],
                         "title": document["title"], "abstract": document["text"],
                         "source": document["selected_source"],
                         "all_source_locators": document["all_source_locators"],
                         "semantic_retrieval_value": result["scores"][rank],
                         "source_kind": "retained_literature_search_result",
                         "full_text_read_claimed": False})
        return {"status": "completed", "workspace_id": workspace, "query": query,
                "scope": scope, "rows": rows, "total_indexed": len(order),
                "offset": offset, "limit": limit, "has_more": offset + len(rows) < len(order),
                "method": "MedCPT query/article CLS raw inner product",
                "index_sha256": digest(manifest), "provider_calls": 0, "public_source_requests": 0,
                "scientific_state_changed": False, "telemetry": {
                    "elapsed_seconds": time.monotonic() - began,
                    "worker_startup_seconds": self.ready["load_seconds"],
                    **{key: result[key] for key in ("query_encode_seconds", "ranking_seconds", "query_cached", "local_query_encodes", "peak_rss_kib")}}}
