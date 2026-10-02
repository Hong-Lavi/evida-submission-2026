"""User-started local indexing jobs, isolated from scientific state and providers."""
import atexit
import json
from pathlib import Path
import sqlite3
import subprocess
import threading
import time
import uuid

from .semantic_index import (cache_entry, collect, destination, digest, model_spec,
                             workspace_directory, write_bytes, write_json)


class IndexBusy(ValueError):
    pass


def configuration(root):
    value = json.loads((Path(root) / "configs/semantic-literature.json").read_text())
    if value.get("enabled") is not True or value.get("incremental", {}).get("enabled") is not True:
        raise ValueError("이 환경에서는 문헌 검색 준비를 사용할 수 없습니다.")
    return value


class IncrementalIndex:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        self.lock = threading.Lock()
        self.active = None
        self.jobs = {}
        self.process = None
        atexit.register(self.close)

    def close(self):
        process = self.process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    def projection(self, store, workspace):
        config = configuration(self.root)
        unused, signature = model_spec(config["incremental"]["article_assets"], config["query_assets_receipt"])
        return config, collect(store, workspace, signature)

    def status(self, store, workspace):
        from .semantic_literature import _index, availability
        state = store.snapshot(workspace)
        visible = availability(self.root, state)
        result = {**visible, "available": bool(visible.get("available")), "running": False,
                  "indexed_documents": visible.get("indexed_documents", 0),
                  "indexed_search_records": visible.get("indexed_search_records", 0),
                  "retained_documents": 0, "pending_documents": 0,
                  "retained_search_records": sum(row["kind"] == "literature" for row in state["artifacts"]),
                  "stale_source_records": 0, "can_build": False,
                  "language": "English", "state": "unindexed", "message": "보존한 문헌으로 검색을 준비할 수 있습니다."}
        try:
            config, projection = self.projection(store, workspace)
            result["retained_documents"] = len(projection["documents"])
            result["unsupported_sources_or_rows"] = len(projection["unsupported_sources_or_rows"])
            try:
                existing = _index(self.root, workspace)
            except (ValueError, OSError, KeyError, TypeError):
                existing = None
            previous = existing[1] if existing else None
            old_sources = previous["source_artifact_sha256"] if previous else {}
            new_sources = projection["source_artifact_sha256"]
            result["stale_source_records"] = sum(new_sources.get(key) != value for key, value in old_sources.items())
            result["pending_search_records"] = sum(old_sources.get(key) != value for key, value in new_sources.items())
            old_text = {row["id"]: (row["title"], row["text"]) for row in previous["documents"]} if previous else {}
            result["pending_documents"] = sum(old_text.get(row["id"]) != (row["title"], row["text"])
                                               for row in projection["documents"])
            ready = bool(previous) and old_sources == new_sources and result["pending_documents"] == 0
            within_limit = len(projection["documents"]) <= config["incremental"].get("max_documents", 2000)
            result["can_build"] = bool(projection["documents"]) and within_limit and not ready
            result["state"] = "ready" if ready else ("pending" if previous else "unindexed")
            if not projection["documents"]:
                result.update(state="empty", message="의미 검색에 넣을 보존 제목·초록이 아직 없습니다.")
            elif not within_limit:
                result.update(state="unindexed", message="보존 문헌 수가 현재 준비 범위를 넘습니다. 기존 원자료는 그대로 볼 수 있습니다.")
            elif ready:
                result["message"] = "보존 문헌의 의미 검색을 사용할 수 있습니다."
            elif previous:
                result["message"] = "새로 보존한 문헌을 검색에 추가할 수 있습니다."
        except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError):
            result.update(state="failed", can_build=False, available=False,
                          indexed_documents=0, indexed_search_records=0,
                          reason="source_integrity_or_projection_unavailable",
                          message="보존 원자료와 검색 준비 내용을 확인하지 못했습니다. 기존 원자료 보기는 유지됩니다.")
        with self.lock:
            job = dict(self.jobs.get(workspace, {}))
        if job.get("running"):
            result.update(state="building", running=True, can_build=False,
                          message="보존 문헌의 검색을 준비하고 있습니다. 연구를 이동해도 이 준비는 계속됩니다.")
            try:
                progress_path = destination(self.root, Path(job["directory"]) / "progress.json")
                if progress_path.exists():
                    progress = json.loads(progress_path.read_text())
                    result["completed_documents"] = progress["completed_documents"]
                    result["total_documents"] = progress["total_documents"]
            except (OSError, ValueError, KeyError):
                pass
        elif job.get("status") == "failed":
            result.update(state="failed", message=job["message"])
        if job:
            result["last_build"] = {key: job[key] for key in (
                "status", "new_article_encodes", "reused_article_vectors", "elapsed_seconds") if key in job}
        return result

    def start(self, store, workspace):
        state = self.status(store, workspace)
        with self.lock:
            if self.active == workspace:
                # The same explicit request observes its already-running job.
                return {**state, "state": "building", "running": True, "can_build": False}
            if self.active is not None:
                raise IndexBusy("다른 연구의 문헌 검색을 준비하고 있습니다. 완료 후 다시 선택해 주세요.")
            if not state["can_build"]:
                return state
            config, projection = self.projection(store, workspace)
            # Every target is checked before starting the child process.
            directory = workspace_directory(workspace) / "builds" / uuid.uuid4().hex
            destination(self.root, directory / "request.json")
            request = {"projection": projection, "article_assets": config["incremental"]["article_assets"],
                       "assets_receipt": config["query_assets_receipt"],
                       "max_documents": config["incremental"].get("max_documents", 2000)}
            # A verified older index can contribute exact vectors without re-encoding.
            from .semantic_literature import _index
            previous = _index(self.root, workspace)
            if previous:
                previous_signature = previous[1].get("model_signature", config["incremental"].get("legacy_article_model_signature"))
                request["previous_index"] = {"manifest": str(previous[2].relative_to(self.root)),
                                             "manifest_sha256": digest(previous[2]),
                                             "model_signature": previous_signature}
            write_json(self.root, directory / "request.json", request)
            self.jobs[workspace] = {"status": "building", "running": True, "directory": str(directory)}
            self.active = workspace
            thread = threading.Thread(target=self._build,
                                      args=(store, workspace, config, projection, directory), daemon=True)
            thread.start()
        return self.status(store, workspace)

    def _build(self, store, workspace, config, projection, directory):
        began = time.monotonic()
        job = {"directory": str(directory), "running": False}
        try:
            environment = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "CUDA_VISIBLE_DEVICES": "",
                           "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                           "HF_HUB_DISABLE_TELEMETRY": "1", "TOKENIZERS_PARALLELISM": "false",
                           "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "4", "MKL_NUM_THREADS": "4"}
            request_sha = digest(destination(self.root, directory / "request.json"))
            command = [config["python"], "-B", str(self.root / "evida/medcpt_article_worker.py"),
                       str(self.root), str(directory / "request.json"), str(directory), request_sha]
            self.process = subprocess.Popen(command, env=environment, stdin=subprocess.DEVNULL,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
            try:
                stdout, stderr = self.process.communicate(timeout=config["incremental"]["timeout_seconds"])
            except subprocess.TimeoutExpired:
                self.process.kill()
                stdout, stderr = self.process.communicate()
                write_bytes(self.root, directory / "stdout.jsonl", stdout)
                write_bytes(self.root, directory / "stderr.txt", stderr)
                raise TimeoutError("Bounded local indexing time reached") from None
            write_bytes(self.root, directory / "stdout.jsonl", stdout)
            write_bytes(self.root, directory / "stderr.txt", stderr)
            if self.process.returncode != 0:
                raise RuntimeError("Local article encoding failed")
            result_path = destination(self.root, directory / "result.json")
            computed = json.loads(result_path.read_text())
            if (computed["status"] != "completed" or computed["workspace_id"] != workspace
                    or computed["request_sha256"] != request_sha
                    or [(row["document_id"], row["embedding_key"]) for row in computed["documents"]]
                    != [(row["id"], row["embedding_key"]) for row in projection["documents"]]):
                raise ValueError("Local article receipt mismatch")
            vectors = destination(self.root, directory / "article-vectors.npy")
            if digest(vectors) != computed["vectors_sha256"]:
                raise ValueError("Article vector output SHA mismatch")
            index = {**projection, "schema": "evida-semantic-literature-index-v2",
                     "vectors_file": "article-vectors.npy", "vectors_sha256": computed["vectors_sha256"],
                     "encoder_method": "MedCPT article CLS, title/abstract pair, float32 raw inner product, max512 tokens",
                     "truncated_documents": computed["truncated_documents"], "full_text_read_claimed": False,
                     "computation_receipt_sha256": digest(result_path)}
            # Reserve the existing SQLite store only for the final source reread
            # and pointer publication. No scientific row is written. This closes
            # the interval in which a source writer could commit between the
            # last SHA check and the atomic index-pointer replacement, in either
            # DELETE or WAL journal mode. Encoding never holds this lock.
            database = Path(store.path).resolve(strict=True)
            with sqlite3.connect(database.as_uri() + "?mode=rw", uri=True, timeout=2) as publication_lock:
                publication_lock.execute("BEGIN IMMEDIATE")
                unused, current = self.projection(store, workspace)
                if current != projection:
                    raise ValueError("Retained source scope changed while preparing the index")
                manifest = write_json(self.root, directory / "manifest.json", index)
                write_json(self.root, workspace_directory(workspace) / "current.json", {
                    "workspace_id": workspace, "manifest": str(manifest.relative_to(self.root)),
                    "manifest_sha256": digest(manifest)})
            job.update(status="completed", new_article_encodes=computed["new_article_encodes"],
                       reused_article_vectors=computed["reused_article_vectors"])
        except Exception as error:
            job.update(status="failed", error_type=type(error).__name__,
                       message="문헌 검색 준비를 완료하지 못했습니다. 기존 자료와 판단은 유지됩니다. 필요하면 준비를 다시 선택해 주세요.")
        finally:
            job["elapsed_seconds"] = time.monotonic() - began
            self.process = None
            try:
                write_json(self.root, directory / "publication.json", job)
            finally:
                with self.lock:
                    self.jobs[workspace] = job
                    self.active = None
