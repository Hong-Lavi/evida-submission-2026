"""Source-backed pharmacology lookup; credentials live only in this worker."""
from pathlib import Path
import json
import re
from urllib.parse import urlencode

from .gtopdb_evidence import interaction_evidence
from .service_access import request_json, ORIGINS
from .service_credentials import CredentialError, read_secret

LIMITS = [
    "결합 지표·큐레이션 작용·효능은 서로 다른 근거입니다. 이 결과만으로 치료 후보를 추천하거나 배제하지 않습니다.",
    "사람 표적 표기는 사람 임상시험을 뜻하지 않습니다. 실험 조건 빈칸은 미확인으로 남습니다.",
    "참고문헌 재사용은 다른 DB와 중복될 수 있습니다. 같은 PMID만으로 서로 다른 assay까지 합치지 않습니다.",
    "지정한 표적·종의 반환 범위입니다. 다른 종·표적과 GtoPdb 밖의 자료는 미조회 상태입니다.",
]


def retrieve(arguments, directory, *, request=request_json, secret_reader=read_secret):
    gene, species = arguments["gene_symbol"], arguments["species"]
    if not isinstance(gene, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9.-]{0,39}", gene):
        raise ValueError("표적의 유전자 기호를 확인해 주세요.")
    if species not in ("Human", "Mouse", "Rat"):
        raise ValueError("조회할 표적 종을 확인해 주세요.")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    result = {"status": "failed", "query": arguments, "rows": [], "summary": {"record_count": None},
              "semantic_type": "curated_pharmacology_observations_not_efficacy",
              "limits": list(LIMITS), "source_receipts": [], "automatic_ranking": False,
              "source_attribution": "IUPHAR/BPS Guide to PHARMACOLOGY",
              "license": "Database ODbL; contents CC BY-SA 4.0; source attribution retained."}
    try:
        secret = secret_reader("gtopdb")
    except CredentialError:
        return {**result, "access_status": "CREDENTIAL_PENDING", "error": "GtoPdb 키 연결이 필요합니다. 조회 0건이 아닙니다."}

    def call(name, path):
        spec = {"name": name, "method": "GET", "path": path}
        receipt, value = request("gtopdb", spec, secret)
        result["source_receipts"].append(receipt)
        (directory / (name + "-receipt.json")).write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
        if receipt["status"] != "JSON_RECEIVED":
            result.update(access_status=receipt["status"], error="자료 조회를 완료하지 못했습니다. 원 수신 상태를 확인하세요.")
            return None
        (directory / (name + "-response.json")).write_text(json.dumps(value, ensure_ascii=False, indent=2))
        return value

    try:
        targets = call("resolve-target", "/services/targets?" + urlencode({"geneSymbol": gene}))
        if targets is None:
            return result
        if not isinstance(targets, list) or not all(isinstance(x, dict) and type(x.get("targetId")) is int for x in targets):
            return {**result, "error": "표적 응답 형식을 확인해야 합니다.", "access_status": "RESPONSE_SCHEMA_UNVERIFIED"}
        if len(targets) != 1:
            return {**result, "status": "partial", "target_matches": targets,
                    "summary": {"record_count": None, "target_matches": len(targets)},
                    "error": "표적을 하나로 확인하지 못했습니다. 약리 근거가 없다는 뜻이 아닙니다."}
        target = targets[0]
        path = f"/services/targets/{target['targetId']}/interactions?" + urlencode({"species": species})
        rows = call("interactions", path)
        if rows is None:
            return result
        try:
            evidence = interaction_evidence(rows, target_id=target["targetId"], species=species,
                                            source_url=ORIGINS["gtopdb"] + path)
        except ValueError:
            return {**result, "access_status": "RESPONSE_SCHEMA_UNVERIFIED",
                    "error": "표적·종·상호작용 식별자를 확인해야 합니다. 원 응답은 보존했습니다."}
        return {**result, "status": "succeeded", "rows": evidence["records"],
                "target": {**target, "queried_gene_symbol": gene}, "access_status": "QUERY_VERIFIED",
                "source": {"url": ORIGINS["gtopdb"] + path},
                "summary": {"record_count": len(rows), "gene_symbol": gene, "species": species,
                            "unresolved_action_count": sum(x["curated_action"]["status"] == "unresolved" for x in evidence["records"]),
                            "automatic_rank_or_exclusion": False},
                "unqueried_scope": evidence["unqueried_scope"]}
    finally:
        del secret
