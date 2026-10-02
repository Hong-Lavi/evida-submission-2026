"""Bounded keyword or one-hop citation retrieval, with an open frontier.

One retrieval edge is not a stopping rule for research or proof of claim support.
The product can choose a returned source as a new seed without fixed graph depth.
"""
import json
from pathlib import Path
import re
from urllib.parse import unquote

from .service_access import request_json
from .service_credentials import CredentialError, read_secret

FIELDS = ["lens_id", "title", "external_ids", "year_published", "abstract",
          "publication_type", "references", "references_count", "references_resolved_count",
          "scholarly_citations", "scholarly_citations_count", "retraction_updates"]
LIMITS = [
    "검색·인용 목록과 초록의 회수입니다. 원문 읽기·주장 지지·임상 효능 검증이 아닙니다.",
    "같은 논문의 다른 보고와 같은 연구군은 독립 근거로 더하지 않습니다.",
    "반환 페이지 밖, 미해결 인용과 다른 인용 깊이, 인용망 밖 검색은 열린 범위로 남습니다.",
    "조회 0건은 해당 검색식·출처·시점의 결과이며, 관련 과학 근거 전체가 없다는 뜻이 아닙니다.",
]

# Last Lens ID character is an ISO 7064 check digit, 0–9 or X.
# https://support.lens.org/knowledge-base/the-lens-id/
LENS_ID = re.compile(r"(?:[0-9]{3}-){4}[0-9]{2}[0-9X]")


def search_query(text):
    """Recognize exact public identifiers before full-text keyword search."""
    candidate = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", text, flags=re.I)
    candidate = unquote(candidate).strip()
    if re.fullmatch(r"10\.[0-9]{4,9}/\S+", candidate, flags=re.I):
        return {"term": {"ids.doi": candidate}}, "exact_doi"
    if LENS_ID.fullmatch(text):
        return {"term": {"lens_id": text}}, "exact_lens_id"
    return text, "keyword"


def retrieve(arguments, directory, *, request=request_json, secret_reader=read_secret):
    mode, text, seed = arguments["mode"], arguments["query"], arguments["lens_id"]
    offset, limit = arguments["offset"], arguments["limit"]
    if type(offset) is not int or offset < 0 or offset > 9950 or type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("조회 범위를 확인해 주세요.")
    if mode == "search":
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 1000 or seed:
            raise ValueError("공개 문헌 검색어를 넣고 인용 출발 ID는 비워 주세요.")
        query, interpretation = search_query(text.strip())
    elif mode in ("references", "citing"):
        if text or not isinstance(seed, str) or not LENS_ID.fullmatch(seed):
            raise ValueError("Lens 원 식별자를 확인하고 검색어는 비워 주세요.")
        query = {"term": {"referenced_by" if mode == "references" else "reference.lens_id": seed}}
        interpretation = "citation_identifier"
    else:
        raise ValueError("검색·참고문헌·후속 인용 중 조회 방식을 선택해 주세요.")
    spec = {"name": "lens-" + mode, "method": "POST", "path": "/scholarly/search",
            "body": {"query": query, "from": offset, "size": limit, "include": FIELDS}}
    result = {"status": "failed", "rows": [], "query": arguments,
        "query_interpretation": interpretation, "executed_public_query": query,
        "summary": {"returned": None, "source_total": None, "mode": mode},
        "source": {"url": "https://api.lens.org/scholarly/search"},
        "semantic_type": "retrieved_literature_metadata_not_read_or_validated",
        "limits": LIMITS, "source_attribution": "The Lens; underlying publication rights retained",
        "source_receipts": [], "automatic_ranking": False}
    try:
        secret = secret_reader("lens")
    except CredentialError:
        return {**result, "access_status": "CREDENTIAL_PENDING", "error": "Lens 연결을 확인해야 합니다. 검색 0건이 아닙니다."}
    try:
        receipt, value = request("lens", spec, secret)
    finally:
        del secret
    result["source_receipts"] = [receipt]
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    (directory / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    if receipt["status"] != "JSON_RECEIVED":
        return {**result, "access_status": receipt["status"], "error": "Lens 조회를 마치지 못했습니다. 원 수신 상태를 확인하세요."}
    (directory / "response.json").write_text(json.dumps(value, ensure_ascii=False, indent=2))
    rows = value.get("data") if isinstance(value, dict) else None
    total = value.get("total") if isinstance(value, dict) else None
    valid = (isinstance(rows, list) and type(total) is int and total >= 0 and len(rows) <= limit
        and len(rows) <= max(0, total-offset) and
        all(isinstance(r, dict) and isinstance(r.get("lens_id"), str) and LENS_ID.fullmatch(r["lens_id"]) for r in rows))
    if not valid or len({r["lens_id"] for r in rows}) != len(rows):
        return {**result, "access_status": "RESPONSE_SCHEMA_UNVERIFIED", "error": "문헌 식별자·개수·페이지 범위를 확인해야 합니다."}
    # Retain every original returned field. Separate addresses/provenance from
    # scientific claims so tracing an edge never manufactures an assessment.
    return {**result, "status": "succeeded", "access_status": "QUERY_VERIFIED", "rows": rows,
        "summary": {"returned": len(rows), "source_total": total, "mode": mode,
            "source_offset": offset, "source_has_more": offset + len(rows) < total},
        "citation_relation": None if mode == "search" else {
            "seed_lens_id": seed, "direction": mode, "claim_support_checked": False},
        "frontier": {"next_source_offset": offset + len(rows) if offset+len(rows)<total else None,
            "unresolved_references_checked": False, "full_text_read": False,
            "other_depths_and_independent_search_remain_open": True}}
