"""Small explicit API checks, separate from live product and model environments.

Default invocation only prepares requests. --execute performs each request once.
Credentials are headers only; provider error bodies and account details are not logged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .service_credentials import CredentialError, read_secret

ORIGINS = {
    "typesafe": "https://api.typesafe.ai",
    "opengwas": "https://api.opengwas.io",
    "clue": "https://api.clue.io",
    "lens": "https://api.lens.org",
    "gtopdb": "https://www.guidetopharmacology.org",
}
MAX_RESPONSE = 2_000_000
GWAS_IDS = ["ieu-a-1284", "ebi-a-GCST90103634"]
RATE_HEADERS = {
    "retry-after", "x-allowance-remaining", "x-allowance-limit", "x-allowance-reset",
    "x-rate-limit-remaining-request-per-minute", "x-rate-limit-retry-after-seconds",
    "x-rate-limit-retry-after-millis", "x-rate-limit-reset-date",
    "x-rate-limit-remaining-request-per-month", "x-rate-limit-remaining-record-per-month",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def plans():
    clue_filter = {"where": {"pert_iname": "sirolimus"}, "limit": 1,
                   "fields": ["pert_id", "pert_iname", "moa", "canonical_smiles"]}
    return {
        "typesafe": [{"name": "bounded-evaluation", "method": "POST", "path": "/v1/systemone",
            "purpose": "Synthetic access check, not a scientific performance trial.",
            "body": {"model": "jev-1.13.0", "state": "A database download is temporarily unavailable. No search has been performed.",
                "questions": {"is_zero_result": {"type": "noul", "instructions":
                    "Does this state establish that a completed search found zero matching records?"}}}}],
        "opengwas": [
            {"name": "authentication", "method": "GET", "path": "/api/user", "purpose": "Verify JWT; account response is not retained."},
            {"name": "kidney-metadata", "method": "POST", "path": "/api/gwasinfo", "body": {"id": GWAS_IDS},
             "purpose": "Inspect two eGFR datasets for renal-outcome feasibility. Neither is assumed to represent ADPKD progression or to justify MR."}],
        "clue": [{"name": "perturbagen-metadata", "method": "GET",
            "path": "/api/perts?" + urllib.parse.urlencode({"filter": json.dumps(clue_filter, separators=(",", ":"))}),
            "purpose": "One sirolimus metadata row; this does not test submission of a CMap signature job."}],
        "lens": [
            {"name": kind, "method": "POST", "path": f"/{kind}/search",
             "body": {"query": "tolvaptan", "size": 1, "include": fields},
             "purpose": "One record only, no pagination or bulk download."}
            for kind, fields in [("scholarly", ["lens_id", "title", "external_ids", "year_published"]),
                                 ("patent", ["lens_id", "biblio.invention_title", "biblio.publication_reference"])]],
        "gtopdb": [{"name": "example-target", "method": "GET", "path": "/services/targets/54",
                    "purpose": "One target from the approval email example; no-key control plus header authentication. Not a disease efficacy test."}],
    }


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def quota_headers(headers):
    # Keep numbers/time-like values only, never arbitrary provider header content.
    return {key.lower(): value for key, value in headers.items()
            if key.lower() in RATE_HEADERS and len(value) < 100
            and re.fullmatch(r"[\d\s.,:/+TZ-]+", value)}


def request_json(service, spec, secret=None, *, opener=None):
    origin = ORIGINS[service]
    path = spec["path"]
    if not path.startswith("/") or path.startswith("//") or "#" in path:
        raise ValueError("Invalid API path.")
    url = origin + path
    if secret and (secret in url or secret in json.dumps(spec)):
        raise CredentialError("A credential must never be part of a request URL or body.")
    headers = {"Accept": "application/json", "User-Agent": "EVIDA-access-check/1.0"}
    if secret:
        if service == "clue":
            headers["user_key"] = secret
        elif service == "gtopdb":
            headers["GTP-API-Key"] = secret
        else:
            headers["Authorization"] = "Bearer " + secret
    body = json.dumps(spec["body"], ensure_ascii=False).encode() if "body" in spec else None
    if body is not None:
        if len(body) > 4000:
            raise ValueError("This check permits only a small request body.")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=spec["method"])
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    started = time.monotonic()
    receipt = {"name": spec["name"], "request": spec, "origin": origin, "started_at": now(),
               "authenticated_request": bool(secret), "automatic_retry": False,
               "status": "NOT_EXECUTED", "record_count": None}
    data = None
    try:
        with opener.open(req, timeout=30) as response:
            receipt.update(http_status=response.status, quota=quota_headers(response.headers))
            raw = response.read(MAX_RESPONSE + 1)
            receipt.update(response_bytes=len(raw))
            if len(raw) > MAX_RESPONSE:
                receipt["status"] = "RESPONSE_TOO_LARGE"
            elif secret and (secret.encode() in raw or urllib.parse.quote(secret, safe="").encode() in raw):
                receipt["status"] = "CREDENTIAL_IN_RESPONSE_WITHHELD"
            else:
                receipt["response_sha256"] = hashlib.sha256(raw).hexdigest()
                try:
                    data = json.loads(raw)
                    if isinstance(data, dict) and (data.get("error") or data.get("errors")):
                        receipt["status"], data = "PROVIDER_ERROR_BODY_WITHHELD", None
                    elif response.status == 200:
                        receipt["status"] = "JSON_RECEIVED"
                    else:
                        receipt["status"], data = "UNEXPECTED_HTTP_STATUS", None
                except (UnicodeError, ValueError):
                    receipt["status"] = "INVALID_JSON"
    except urllib.error.HTTPError as exc:
        receipt.update(http_status=exc.code, quota=quota_headers(exc.headers),
                       status={401: "AUTHENTICATION_FAILED", 403: "ACCESS_DENIED", 429: "RATE_LIMITED"}.get(exc.code, "HTTP_ERROR"))
        # Error bodies/redirect locations can echo credentials. Do not persist them.
        exc.close()
    except (OSError, urllib.error.URLError, TimeoutError):
        receipt["status"] = "NETWORK_OR_TIMEOUT"
    receipt.update(completed_at=now(), elapsed_seconds=round(time.monotonic() - started, 3))
    return receipt, data


def gwas_metadata(data, requested_ids):
    """Normalize a bounded requested set without treating missing studies as negative evidence."""
    if not 1 <= len(requested_ids) <= 10:
        raise ValueError("Select one to ten study identifiers before a metadata query.")
    rows = data if isinstance(data, list) else list(data.values()) if isinstance(data, dict) else None
    if rows is None or not all(isinstance(x, dict) and x.get("id") in requested_ids and x.get("trait") for x in rows):
        return None
    fields = {"id", "trait", "year", "population", "sample_size", "ncase", "ncontrol", "unit", "consortium", "pmid", "build", "nsnp", "category", "subcategory", "is_nc", "sex", "ontology", "note", "author"}
    return {"records": [{k: v for k, v in x.items() if k in fields} for x in rows],
            "missing_requested_ids": sorted(set(requested_ids) - {x["id"] for x in rows}),
            "selection_status": "METADATA_CANDIDATES_ONLY"}


def check_response(service, name, data):
    """Return a checked, non-account response and exact scope; schema failures stay unknown."""
    if service == "typesafe":
        answer = data.get("answers", {}).get("is_zero_result", {}) if isinstance(data, dict) else {}
        value = answer.get("noul")
        if (not isinstance(data, dict) or data.get("model") != "jev-1.13.0"
                or answer.get("type") != "noul" or type(value) not in (int, float)
                or not math.isfinite(value) or not 0 <= value <= 1):
            return None
        return {"model": data["model"], "answers": {"is_zero_result": answer}, "usage": data.get("usage", {})}
    if service == "opengwas":
        if name == "authentication":
            return {"authenticated": True, "account_body_retained": False} if isinstance(data, dict) and data else None
        return gwas_metadata(data, GWAS_IDS)
    if service == "clue":
        if not isinstance(data, list) or len(data) > 1 or not all(isinstance(x, dict) and x.get("pert_id") and x.get("pert_iname") for x in data):
            return None
        return {"records": [{k: v for k, v in x.items() if k in {"pert_id", "pert_iname", "moa", "canonical_smiles"}} for x in data],
                "cmap_signature_submission_verified": False}
    if service == "lens":
        if not isinstance(data, dict) or not isinstance(data.get("data"), list) or len(data["data"]) > 1:
            return None
        if not all(isinstance(x, dict) and x.get("lens_id") for x in data["data"]):
            return None
        fields = {"lens_id", "title", "external_ids", "year_published", "biblio"}
        return {"records": [{k: v for k, v in x.items() if k in fields} for x in data["data"]], "total_reported": data.get("total")}
    if service == "gtopdb" and name == "example-target":
        if (not isinstance(data, dict) or type(data.get("targetId")) is not int
                or data["targetId"] != 54 or not isinstance(data.get("name"), str) or not data["name"].strip()):
            return None
        fields = {"targetId", "name", "abbreviation", "type", "nomenclature", "familyIds"}
        return {"records": [{k: v for k, v in data.items() if k in fields}],
                "scope": "Single target identity only; no interaction or therapeutic efficacy assessment."}
    return None


def run_service(service, directory, *, secret_reader=read_secret, request=request_json):
    directory.mkdir(parents=True, exist_ok=False)
    result = {"service": service, "status": "CREDENTIAL_PENDING", "authentication_verified": False,
              "query_verified": False, "record_count": None, "steps": [], "scientific_validation": False,
              "product_ui_integration": False, "at": now()}

    def retain():
        (directory / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    try:
        secret = secret_reader(service)
    except CredentialError:
        retain()
        return result
    control_denied = False
    for spec in plans()[service]:
        if service in {"clue", "gtopdb"}:
            control, _ = request(service, spec)
            result["steps"].append({**control, "name": "no-key-control"})
            retain()
            if control["status"] in ("RATE_LIMITED", "NETWORK_OR_TIMEOUT"):
                result["status"] = control["status"]
                break
            control_denied = control.get("http_status") in (401, 403)
        receipt, data = request(service, spec, secret)
        if service == "typesafe" and isinstance(data, dict):
            model = data.get("model")
            if isinstance(model, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,80}", model):
                receipt["actual_model"] = model
            usage = data.get("usage", {})
            if isinstance(usage, dict):
                receipt["usage"] = {k: v for k, v in usage.items()
                                    if k in {"input_tokens", "output_tokens"} and type(v) is int and v >= 0}
        checked = check_response(service, spec["name"], data) if receipt["status"] == "JSON_RECEIVED" else None
        if checked is not None:
            receipt.update(status="VERIFIED_RESPONSE", response=checked)
            if "records" in checked:
                receipt["record_count"] = len(checked["records"])
            if service not in {"clue", "gtopdb"} or control_denied:
                result["authentication_verified"] = True
            if spec["name"] != "authentication":
                result["query_verified"] = True
        elif receipt["status"] == "JSON_RECEIVED":
            receipt["status"] = "RESPONSE_SCHEMA_UNVERIFIED"
        result["steps"].append(receipt)
        result["status"] = receipt["status"]
        retain()
        if checked is None:
            break
        if any(str(receipt.get("quota", {}).get(k)) == "0" for k in (
                "x-allowance-remaining", "x-rate-limit-remaining-request-per-minute",
                "x-rate-limit-remaining-request-per-month", "x-rate-limit-remaining-record-per-month")):
            result["next_dispatch_held_for_quota"] = True
            break
    del secret
    expected = len(plans()[service])
    successful = sum(s["status"] == "VERIFIED_RESPONSE" for s in result["steps"])
    if successful == expected and result["authentication_verified"] and result["query_verified"]:
        result["status"] = "AUTH_AND_QUERY_VERIFIED"
    elif service in {"clue", "gtopdb"} and result["query_verified"]:
        result["status"] = "QUERY_VERIFIED_AUTH_NOT_PROVEN"
    elif successful:
        result["status"] = "PARTIAL_VERIFICATION"
    counts = [s["record_count"] for s in result["steps"] if s.get("record_count") is not None]
    result["record_count"] = sum(counts) if counts else None
    retain()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", choices=list(ORIGINS), action="append")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    selected = args.service or list(ORIGINS)
    prepared = {"at": now(), "execute": args.execute, "services": {k: plans()[k] for k in selected},
                "maximum_requests": {"typesafe": 1, "opengwas": 2, "clue": 2, "lens": 2, "gtopdb": 2},
                "automatic_retry": False, "secret_storage": "owner-only files outside repository"}
    (args.output / "plan.json").write_text(json.dumps(prepared, ensure_ascii=False, indent=2) + "\n")
    if args.execute:
        for service in selected:
            value = run_service(service, args.output / service)
            print(json.dumps({k: value[k] for k in ["service", "status", "authentication_verified", "query_verified", "record_count"]}))
    else:
        print("Prepared only: " + str(args.output / "plan.json"))


if __name__ == "__main__":
    main()
