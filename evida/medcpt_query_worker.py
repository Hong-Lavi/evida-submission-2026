"""Offline CPU query encoder. JSON-lines stdin/stdout; no product/API access."""
from collections import OrderedDict
import hashlib
import json
from pathlib import Path
import resource
import sys
import time


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def send(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def main():
    started = time.monotonic()
    assets, receipt_path = map(Path, sys.argv[1:3])
    receipt = json.loads(receipt_path.read_text())
    files = [row for model in receipt["models"] for row in model["files"]
             if Path(row["path"]).parent.resolve() == assets.resolve()]
    assert len(files) >= 7
    for row in files:
        assert digest(row["path"]) == row["sha256"]
    import numpy as np
    import torch
    from transformers import AutoModel, AutoTokenizer
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    tokenizer = AutoTokenizer.from_pretrained(assets, local_files_only=True, trust_remote_code=False)
    model, loading = AutoModel.from_pretrained(
        assets, local_files_only=True, trust_remote_code=False,
        use_safetensors=True, torch_dtype=torch.float32, output_loading_info=True)
    assert not any(loading.get(key) for key in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs"))
    model.eval().requires_grad_(False).to("cpu")
    queries, matrices = OrderedDict(), {}
    send({"status": "ready", "device": "cpu", "load_seconds": time.monotonic() - started,
          "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})
    for line in sys.stdin:
        try:
            request = json.loads(line)
            query = request["query"]
            assert isinstance(query, str) and 0 < len(query) <= 1024
            ids = request["document_ids"]
            assert len(ids) == len(set(ids)) and 0 < len(ids) <= 2000
            key = (request["vectors_file"], request["vectors_sha256"])
            if key not in matrices:
                assert digest(key[0]) == key[1]
                values = np.load(key[0], allow_pickle=False)
                assert values.dtype == np.float32 and values.shape == (len(ids), 768)
                assert np.isfinite(values).all()
                matrices[key] = values
            articles = matrices[key]
            assert articles.shape == (len(ids), 768)
            query_key = hashlib.sha256(query.encode()).hexdigest()
            began = time.monotonic()
            cached = query_key in queries
            if cached:
                vector, token_count = queries.pop(query_key)
            else:
                tokens = tokenizer(query, return_tensors="pt", truncation=False)
                token_count = int(tokens["input_ids"].shape[1])
                if token_count > 64:
                    send({"status": "query_too_long", "query_tokens": token_count})
                    continue
                with torch.inference_mode():
                    vector = model(**tokens).last_hidden_state[:, 0, :].numpy()
                assert vector.shape == (1, 768) and np.isfinite(vector).all()
            queries[query_key] = (vector, token_count)
            while len(queries) > 32:
                queries.popitem(last=False)
            encoded = time.monotonic()
            scores = (vector @ articles.T)[0]
            order = np.lexsort((np.asarray(ids), -scores))
            send({"status": "completed", "order": order.tolist(),
                  "scores": [float(scores[index]) for index in order],
                  "query_tokens": token_count, "query_cached": cached,
                  "query_encode_seconds": encoded - began,
                  "ranking_seconds": time.monotonic() - encoded,
                  "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  "local_query_encodes": 0 if cached else 1})
        except Exception as error:
            send({"status": "error", "error_type": type(error).__name__})


if __name__ == "__main__":
    main()
