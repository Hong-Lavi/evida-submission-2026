"""Exact retained-source projection and isolated writes for optional indexing.

This module does not call a provider, open a network connection or change a Store.
Public identifiers deduplicate rows only inside the requested workspace.
"""
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import tempfile


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def destination(root, relative):
    root = Path(root).resolve(strict=True)
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Expected an isolated relative destination")
    path = root / relative
    if (not path.parent.resolve().is_relative_to(root)
            or not path.resolve().is_relative_to(root) or path.is_symlink()):
        raise ValueError("Refusing a write through an external or target symlink")
    return path


def write_bytes(root, relative, data):
    path = destination(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path = destination(root, relative)
    fd, temporary = tempfile.mkstemp(prefix=".semantic-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        destination(root, relative)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def write_json(root, relative, value):
    return write_bytes(root, relative, json.dumps(value, ensure_ascii=False, indent=2).encode() + b"\n")


class _Plain(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, value):
        self.parts.append(value)


def plain(value):
    if not isinstance(value, str):
        raise ValueError("Retained literature title/abstract must be text")
    parser = _Plain()
    parser.feed(value)
    return re.sub(r"\s+", " ", unescape(" ".join(parser.parts))).strip()


def aliases(row):
    result = []
    for field, prefix, transform in (("pmid", "PMID:", str),
                                     ("pmcid", "PMCID:", lambda x: str(x).upper()),
                                     ("doi", "DOI:", lambda x: str(x).strip().lower())):
        if row.get(field):
            result.append(prefix + transform(row[field]))
    if row.get("id"):
        result.append(str(row.get("source", "EPMC")) + ":" + str(row["id"]))
    return result


def model_spec(assets, receipt_path):
    """Describe frozen assets; the isolated worker verifies every file before use."""
    assets = Path(assets).resolve(strict=True)
    receipt = json.loads(Path(receipt_path).read_text())
    candidates = [entry for entry in receipt["models"]
                  if entry["role"] == "article" and all(
                      Path(row["path"]).parent.resolve() == assets for row in entry["files"])]
    if len(candidates) != 1 or len(candidates[0]["files"]) < 7:
        raise ValueError("Missing frozen article assets")
    model = candidates[0]
    method = {"model_id": model["model_id"], "revision": model["revision"],
              "asset_sha256": {Path(row["path"]).name: row["sha256"] for row in model["files"]},
              "normalization": "html-data-unescape-collapse-whitespace-v1",
              "input": "title/abstract tokenizer pair", "max_tokens": 512,
              "pooling": "CLS", "dtype": "float32", "normalized": False}
    return method, hashlib.sha256(canonical(method)).hexdigest()


def workspace_directory(workspace):
    return Path("semantic-literature-data/incremental") / hashlib.sha256(workspace.encode()).hexdigest()


def collect(store, workspace, model_signature):
    """Project every supported retained literature row, keeping all exact locators."""
    snapshot = store.snapshot(workspace)
    if snapshot["id"] != workspace:
        raise ValueError("Workspace identity mismatch")
    metadata = sorted((row for row in snapshot["artifacts"] if row["kind"] == "literature"),
                      key=lambda row: (row.get("created", ""), row["id"]))
    raw_rows, sources, unsupported = [], {}, []
    for meta in metadata:
        record = store.artifact(workspace, meta["id"])
        content = record["content"]
        content = content if isinstance(content, bytes) else content.encode()
        if (record["id"] != meta["id"] or record.get("workspace", workspace) != workspace
                or record["kind"] != "literature" or record["sha256"] != meta["sha256"]
                or hashlib.sha256(content).hexdigest() != meta["sha256"]):
            raise ValueError("Retained source identity or SHA mismatch")
        sources[meta["id"]] = meta["sha256"]
        value = json.loads(content)
        try:
            rows = value["response"]["resultList"]["result"]
        except (KeyError, TypeError):
            unsupported.append({"artifact_id": meta["id"], "sha256": meta["sha256"],
                                "reason": "unsupported_literature_shape"})
            continue
        if not isinstance(rows, list) or value.get("rows") != rows:
            raise ValueError("Retained literature projection differs from original rows")
        for offset, row in enumerate(rows):
            locator = {"artifact_id": meta["id"], "sha256": meta["sha256"],
                       "json_pointer": "/response/resultList/result/" + str(offset), "row_index": offset}
            identifiers = aliases(row)
            title, abstract = plain(row.get("title") or ""), plain(row.get("abstractText") or "")
            if not identifiers or not (title or abstract):
                unsupported.append({**locator, "reason": "missing_identifier_or_text"})
                continue
            raw_rows.append({"row": row, "title": title, "text": abstract,
                             "aliases": identifiers, "locator": locator})
    parents, seen = list(range(len(raw_rows))), {}
    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index
    for offset, entry in enumerate(raw_rows):
        for identifier in entry["aliases"]:
            if identifier in seen:
                parents[root(offset)] = root(seen[identifier])
            seen[identifier] = offset
    groups = {}
    for offset, entry in enumerate(raw_rows):
        groups.setdefault(root(offset), []).append(entry)
    documents = []
    for entries in groups.values():
        identifiers = sorted({name for entry in entries for name in entry["aliases"]})
        # Conflicting authoritative IDs require source review, never a title guess.
        if any(sum(name.startswith(prefix) for name in identifiers) > 1
               for prefix in ("PMID:", "PMCID:")):
            raise ValueError("Conflicting public identifiers in retained literature")
        identifier = next((name for name in identifiers if name.startswith("PMID:")), identifiers[0])
        chosen = max(entries, key=lambda entry: len(entry["row"].get("abstractText") or ""))
        content_sha = hashlib.sha256(canonical({"title": chosen["title"], "text": chosen["text"]})).hexdigest()
        vector_key = hashlib.sha256(canonical({"content_sha256": content_sha,
                                              "model_signature": model_signature})).hexdigest()
        documents.append({"id": identifier, "title": chosen["title"], "text": chosen["text"],
                          "selected_source": chosen["locator"],
                          "all_source_locators": [entry["locator"] for entry in entries],
                          "public_aliases": identifiers, "content_sha256": content_sha,
                          "embedding_key": vector_key})
    documents.sort(key=lambda row: row["id"])
    if len({row["id"] for row in documents}) != len(documents):
        raise ValueError("Duplicate retained document identity")
    return {"schema": "evida-semantic-literature-projection-v2", "workspace_id": workspace,
            "model_signature": model_signature, "source_artifact_sha256": sources,
            "source_scope_sha256": hashlib.sha256(canonical(sources)).hexdigest(),
            "documents": documents, "raw_supported_rows": len(raw_rows),
            "unsupported_sources_or_rows": unsupported,
            "scope": "Only retained title/abstract search results; unreturned hits and unsearched topics are outside this index."}


def cache_location(workspace, key):
    if not re.fullmatch(r"[a-f0-9]{64}", key):
        raise ValueError("Invalid embedding identity")
    return workspace_directory(workspace) / "cache" / key


def cache_entry(product, workspace, document, model_signature):
    location = cache_location(workspace, document["embedding_key"])
    receipt_path = destination(product, location.with_suffix(".json"))
    if not receipt_path.exists():
        return None
    receipt = json.loads(receipt_path.read_text())
    vector = destination(product, location.with_suffix(".npy"))
    if (receipt["embedding_key"] != document["embedding_key"]
            or receipt["content_sha256"] != document["content_sha256"]
            or receipt["model_signature"] != model_signature
            or receipt["vectors_sha256"] != digest(vector)):
        raise ValueError("Cached article vector is not the verified retained text")
    return receipt
