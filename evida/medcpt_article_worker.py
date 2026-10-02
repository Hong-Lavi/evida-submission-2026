"""Bounded offline CPU article encoding; inputs and outputs stay in an isolated product.

Existing exact-text vectors are reused. The worker has no Store/provider access.
"""
import io
import hashlib
import json
from pathlib import Path
import resource
import sys
import time

from semantic_index import (cache_entry, cache_location, canonical, destination, digest,
                            model_spec, write_bytes, write_json)


def main():
    began = time.monotonic()
    product = Path(sys.argv[1]).resolve(strict=True)
    request_path = destination(product, sys.argv[2])
    output_relative = Path(sys.argv[3])
    # Refuse an escaping target before imports, model loads, or any output write.
    destination(product, output_relative / "result.json")
    request_bytes = request_path.read_bytes()
    request_sha = hashlib.sha256(request_bytes).hexdigest()
    if len(sys.argv) > 4 and request_sha != sys.argv[4]:
        raise ValueError("Prepared article request SHA differs")
    request = json.loads(request_bytes)
    projection = request["projection"]
    workspace = projection["workspace_id"]
    documents = projection["documents"]
    if not 0 < len(documents) <= request.get("max_documents", 2000):
        raise ValueError("The retained pool exceeds the reviewed job scope")
    method, signature = model_spec(request["article_assets"], request["assets_receipt"])
    if signature != projection["model_signature"]:
        raise ValueError("Article model fingerprint differs")
    for row in documents:
        actual_content = hashlib.sha256(canonical({"title": row["title"], "text": row["text"]})).hexdigest()
        actual_key = hashlib.sha256(canonical({"content_sha256": actual_content, "model_signature": signature})).hexdigest()
        if actual_content != row["content_sha256"] or actual_key != row["embedding_key"]:
            raise ValueError("Article content does not match its embedding identity")
    result = {"status": "started", "workspace_id": workspace, "device": "cpu",
              "provider_calls": 0, "public_source_requests": 0, "gpu_runs": 0,
              "new_article_encodes": 0, "reused_article_vectors": 0,
              "model_signature": signature, "request_sha256": request_sha,
              "method": method, "documents": []}
    try:
        import numpy as np
        previous = request.get("previous_index")
        if previous:
            manifest = destination(product, previous["manifest"])
            if digest(manifest) != previous["manifest_sha256"] or previous["model_signature"] != signature:
                raise ValueError("Previous index identity differs")
            older = json.loads(manifest.read_text())
            if older["workspace_id"] != workspace:
                raise ValueError("Cannot reuse another workspace's source bindings")
            vector_path = destination(product, manifest.parent.relative_to(product) / older["vectors_file"])
            if digest(vector_path) != older["vectors_sha256"]:
                raise ValueError("Previous article vectors differ")
            prior_vectors = np.load(vector_path, allow_pickle=False)
            if (prior_vectors.shape != (len(older["documents"]), 768)
                    or prior_vectors.dtype != np.float32 or not np.isfinite(prior_vectors).all()):
                raise ValueError("Invalid previous article vector matrix")
            previous_documents = {row["id"]: (offset, row) for offset, row in enumerate(older["documents"])}
            for row in documents:
                if cache_entry(product, workspace, row, signature) is not None:
                    continue
                old = previous_documents.get(row["id"])
                if old is None or (old[1]["title"], old[1]["text"]) != (row["title"], row["text"]):
                    continue
                location = cache_location(workspace, row["embedding_key"])
                buffer = io.BytesIO()
                np.save(buffer, prior_vectors[old[0]:old[0] + 1], allow_pickle=False)
                path = write_bytes(product, location.with_suffix(".npy"), buffer.getvalue())
                write_json(product, location.with_suffix(".json"), {
                    "embedding_key": row["embedding_key"], "content_sha256": row["content_sha256"],
                    "model_signature": signature, "vectors_sha256": digest(path),
                    "full_pair_tokens": None, "encoded_tokens": None, "truncated": None,
                    "encode_seconds": 0, "reused_from_manifest_sha256": digest(manifest),
                    "new_article_encodes": 0})
        missing = [row for row in documents if cache_entry(product, workspace, row, signature) is None]
        if missing:
            asset_receipt = json.loads(Path(request["assets_receipt"]).read_text())
            asset_files = [row for model in asset_receipt["models"] if model["role"] == "article" for row in model["files"]]
            for row in asset_files:
                if digest(row["path"]) != row["sha256"]:
                    raise ValueError("Frozen article asset SHA mismatch")
            import torch
            from transformers import AutoModel, AutoTokenizer
            torch.set_num_threads(4)
            torch.set_num_interop_threads(1)
            assets = request["article_assets"]
            tokenizer = AutoTokenizer.from_pretrained(assets, local_files_only=True, trust_remote_code=False)
            model, loading = AutoModel.from_pretrained(
                assets, local_files_only=True, trust_remote_code=False,
                use_safetensors=True, torch_dtype=torch.float32, output_loading_info=True)
            if any(loading.get(key) for key in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs")):
                raise ValueError("Article model did not load exactly")
            model.eval().requires_grad_(False).to("cpu")
        result["startup_seconds"] = time.monotonic() - began
        vectors = []
        for row in documents:
            entry = cache_entry(product, workspace, row, signature)
            location = cache_location(workspace, row["embedding_key"])
            if entry is not None:
                vector = np.load(destination(product, location.with_suffix(".npy")), allow_pickle=False)
                result["reused_article_vectors"] += 1
            else:
                started = time.monotonic()
                texts = [[row["title"], row["text"]]]
                full = tokenizer(texts, truncation=False, padding=False)
                full_tokens = len(full["input_ids"][0])
                encoded = tokenizer(texts, truncation=True, padding=True, max_length=512, return_tensors="pt")
                with torch.inference_mode():
                    vector = model(**encoded).last_hidden_state[:, 0, :].numpy()
                if vector.shape != (1, 768) or vector.dtype != np.float32 or not np.isfinite(vector).all():
                    raise ValueError("Invalid article embedding")
                buffer = io.BytesIO()
                np.save(buffer, vector, allow_pickle=False)
                path = write_bytes(product, location.with_suffix(".npy"), buffer.getvalue())
                entry = {"embedding_key": row["embedding_key"], "content_sha256": row["content_sha256"],
                         "model_signature": signature, "vectors_sha256": digest(path),
                         "full_pair_tokens": full_tokens, "encoded_tokens": int(encoded["input_ids"].shape[1]),
                         "truncated": full_tokens > 512, "encode_seconds": time.monotonic() - started}
                write_json(product, location.with_suffix(".json"), entry)
                result["new_article_encodes"] += 1
            if vector.shape != (1, 768) or vector.dtype != np.float32 or not np.isfinite(vector).all():
                raise ValueError("Invalid cached article embedding")
            vectors.append(vector)
            result["documents"].append({"document_id": row["id"], **entry})
            write_json(product, output_relative / "progress.json", {
                "status": "encoding", "completed_documents": len(vectors), "total_documents": len(documents),
                "new_article_encodes": result["new_article_encodes"],
                "reused_article_vectors": result["reused_article_vectors"]})
        buffer = io.BytesIO()
        np.save(buffer, np.concatenate(vectors), allow_pickle=False)
        path = write_bytes(product, output_relative / "article-vectors.npy", buffer.getvalue())
        result.update(status="completed", vectors_sha256=digest(path),
                      truncated_documents=sum(row["truncated"] is True for row in result["documents"]),
                      truncation_unknown_documents=sum(row["truncated"] is None for row in result["documents"]))
    except Exception as error:
        result.update(status="failed_no_automatic_retry", error_type=type(error).__name__, detail=str(error))
        raise
    finally:
        result["elapsed_seconds"] = time.monotonic() - began
        result["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        write_json(product, output_relative / "result.json", result)
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
