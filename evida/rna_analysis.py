"""Inspect explicit genes across existing processed contrasts; no hidden pooling."""


def review_genes(inputs, genes):
    if not genes or any(not isinstance(g, str) or not g.strip() for g in genes):
        raise ValueError("확인할 유전자 ID 또는 이름을 명시해 주세요.")
    genes = list(dict.fromkeys(genes))
    rows, sources = [], []
    for entry in inputs:
        result = entry["result"]
        if result.get("semantic_type") != "reported_observation" or not isinstance(result.get("rows"), list):
            raise ValueError("기존 RNA 처리표의 관측 검토 결과가 필요합니다.")
        aid = entry["artifact_id"]
        sources.append({"artifact_id": aid, "sha256": entry["sha256"], "contrast": result.get("contrast"),
                        "context": result.get("context"), "total_input_rows": len(result["rows"])})
        for gene in genes:
            matches = [r for r in result["rows"] if gene == r.get("gene_id") or gene == r.get("symbol")]
            if not matches:
                rows.append({"input_artifact_id": aid, "requested_gene": gene, "status": "not_found_in_table",
                             "matching_rows": 0, "observation": None})
            else:
                for match in matches:
                    rows.append({"input_artifact_id": aid, "requested_gene": gene, "status": "reported_row",
                                 "matching_rows": len(matches), "observation": match})
    return {"status": "succeeded", "semantic_type": "processed_contrast_gene_review", "rows": rows,
            "sources": sources, "matching_policy": "exact gene ID or case-sensitive symbol; no implicit ortholog/version mapping",
            "summary": {"input_tables": len(inputs), "requested_genes": genes, "returned_rows": len(rows),
                        "unmatched_requests": sum(r["status"] == "not_found_in_table" for r in rows)},
            "limits": ["기존 처리표의 원행을 대조 조건별로 읽은 결과입니다. 새로운 차등발현 분석이나 후보 간 유의성 검정이 아닙니다.",
                       "같은 대조군·시료·배치 또는 종의 대응을 가정하지 않고, 여러 표를 독립 반복으로 합치지 않았습니다.",
                       "행 미발견·결측·보고된 0과 중복 대응을 구별합니다. 전사체 변화만으로 작용 기전이나 치료 효능을 확정하지 않습니다."]}
