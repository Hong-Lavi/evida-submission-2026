"""Real, bounded scientific adapters. No credential access or model substitute."""
from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.metadata
import io
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REVISION = "downstream-integration-2"
MAX_DOWNLOAD = 20 * 1024 * 1024


def fetch(url, payload=None, *, timeout=90, max_download=MAX_DOWNLOAD):
    # These adapters construct URLs from fixed public hosts, never an LLM URL.
    allowed = {"api.platform.opentargets.org", "gtexportal.org", "www.ebi.ac.uk", "zenodo.org", "ftp.ncbi.nlm.nih.gov",
               "files.rcsb.org", "data.rcsb.org", "rest.ensembl.org", "search.rcsb.org", "pubchem.ncbi.nlm.nih.gov",
               "eutils.ncbi.nlm.nih.gov", "bindingdb.org", "www.bindingdb.org",
               "dailymed.nlm.nih.gov", "clinicaltrials.gov"}
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in allowed or parsed.username or parsed.password:
        raise ValueError("허용된 공개 자료 주소가 아닙니다.")
    class PublicRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            target = urllib.parse.urlparse(newurl)
            if target.scheme != "https" or target.hostname not in allowed:
                raise ValueError("공개 자료의 리디렉션 주소를 확인해야 합니다.")
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    req = urllib.request.Request(url, data=json.dumps(payload).encode() if payload else None,
                                 headers={"User-Agent": "EVIDA/0.1 public-research-prototype",
                                          "Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), PublicRedirect())
    with opener.open(req, timeout=timeout) as response:
        body = response.read(max_download + 1)
        if len(body) > max_download:
            raise ValueError("자료가 현재 다운로드 범위보다 큽니다.")
        return body, {"url": url, "resolved_url": response.url, "http_status": response.status,
                      "retrieved_at": datetime.now(timezone.utc).isoformat(),
                      "sha256": hashlib.sha256(body).hexdigest()}


def molecule_rows(content, meta):
    encoding = meta.get("encoding", "utf-8-sig")
    delimiter = meta.get("delimiter", ",")
    if encoding not in ("utf-8-sig", "utf-8", "cp1252") or delimiter not in (",", ";", "\t"):
        raise ValueError("자료의 문자 인코딩·구분자를 확인해 주세요.")
    records = list(csv.reader(io.StringIO(content.decode(encoding)), delimiter=delimiter))
    header_index = meta.get("header_record", 0)
    if type(header_index) is not int or not 0 <= header_index < len(records):
        raise ValueError("CSV 헤더 위치가 올바르지 않습니다.")
    header = records[header_index]
    smiles_name = meta.get("smiles_column", "smiles")
    if header.count(smiles_name) != 1:
        raise ValueError("SMILES 열 이름이 없거나 중복입니다. 열 대응을 확인해 주세요.")
    smiles_idx = header.index(smiles_name)
    id_name = meta.get("id_column", "cid")
    id_idx = header.index(id_name) if header.count(id_name) == 1 else None
    digest = hashlib.sha256(content).hexdigest()
    rows = []
    for ordinal, row in enumerate(records[header_index + 1:], header_index + 1):
        source = {"sha256": digest, "logical_csv_record_0_based": ordinal}
        # Empty or malformed records are evidence too; keep them as explicit outcomes.
        rows.append({"row_id": f"{digest[:12]}:{ordinal}", "source_ref": source,
                     "candidate_id": row[id_idx] if id_idx is not None and id_idx < len(row) else None,
                     "smiles": row[smiles_idx] if smiles_idx < len(row) else None,
                     "raw_values": row, "width_matches": len(row) == len(header)})
    if len(rows) > 10000:
        raise ValueError("첫 구현은 한 번에 10,000행까지 처리합니다. 원자료는 보존됩니다.")
    return header, rows


def analogue_source(content, meta):
    """Read either a preserved JSON view or a native molecule CSV with its mapping.

    Selection publishes CSV, whereas discovery publishes JSON. Both are valid
    sources of structures; treating the former as JSON prevents generation before
    any chemistry runs. A JSON parse error remains an error, not a CSV fallback.
    """
    prefix = content.removeprefix(b'\xef\xbb\xbf').lstrip()
    if prefix.startswith((b'{', b'[')):
        return json.loads(content)

    header, parsed = molecule_rows(content, meta)
    rows = []
    for entry in parsed:
        # Preserve arbitrary CSV columns without interpreting a column named
        # "activities" as structured JSON or bypassing the selected SMILES
        # mapping through an alternative structure column.
        columns = {name: value for name, value in zip(header, entry['raw_values'])
                   if header.count(name) == 1}
        row = {**entry, 'source_columns': columns}
        for name in ('name', 'source_target'):
            if name in columns:
                row[name] = columns[name]
        if not row['width_matches']:
            row.update(status='invalid_input', smiles=None, reason='CSV 행과 헤더 너비가 다름')
        elif not row['smiles'] or not row['smiles'].strip():
            row.update(status='input_missing', smiles=None, reason='SMILES 누락')
        rows.append(row)
    return {'semantic_type': 'molecule_csv', 'header': header, 'rows': rows,
            'source_pool_id': meta.get('source_pool_id')}


def rdkit_properties(content, meta):
    from rdkit import Chem, rdBase
    from rdkit.Chem import Crippen, Descriptors, Lipinski, QED, rdMolDescriptors
    header, rows = molecule_rows(content, meta)
    for row in rows:
        row["properties"] = None
        if not row["width_matches"]:
            row.update(status="invalid_input", reason="CSV 행과 헤더 너비가 다름")
        elif not row["smiles"] or not row["smiles"].strip():
            row.update(status="input_missing", reason="SMILES 누락")
        else:
            with rdBase.BlockLogs():
                mol = Chem.MolFromSmiles(row["smiles"])
            if mol is None:
                row.update(status="invalid_input", reason="RDKit이 구조를 해석하지 못함")
            else:
                row.update(status="succeeded", reason=None, properties={
                    "MolWt": Descriptors.MolWt(mol), "LogP": Crippen.MolLogP(mol),
                    "TPSA": rdMolDescriptors.CalcTPSA(mol), "HBD": Lipinski.NumHDonors(mol),
                    "HBA": Lipinski.NumHAcceptors(mol), "QED": QED.qed(mol)})
    succeeded = sum(r["status"] == "succeeded" for r in rows)
    return {"status": "succeeded", "semantic_type": "calculated_property", "header": header,
            "rows": rows, "summary": {"total_rows": len(rows), "calculated": succeeded,
                                       "not_calculated": len(rows) - succeeded},
            "versions": {"rdkit": rdBase.rdkitVersion},
            "columns": {"MolWt": "g/mol", "LogP": "Wildman–Crippen calculated logP", "TPSA": "Å²",
                        "HBD": "count", "HBA": "count", "QED": "dimensionless descriptor"},
            "limits": ["계산 물성·QED는 실측 약효나 치료 성공 확률이 아닙니다.",
                       "원행·원 SMILES를 유지하며 중복 후보를 삭제하지 않았습니다."]}


def admet_predictions(content, meta):
    from admet_ai import ADMETModel
    import admet_ai
    import torch
    torch.set_num_threads(2)
    prior = json.loads(content)
    if prior.get("semantic_type") != "calculated_property":
        raise ValueError("ADMET 입력에는 먼저 실행한 RDKit 결과가 필요합니다.")
    rows = prior["rows"]
    unique = list(dict.fromkeys(r["smiles"] for r in rows if r["status"] == "succeeded"))
    root = Path(admet_ai.__file__).parent
    endpoint_rows = list(csv.DictReader((root / "resources/data/admet.csv").open()))
    model = ADMETModel(include_physchem=False, drugbank_path=None, num_workers=0)
    prediction = model.predict(smiles=unique) if unique else None
    endpoints = list(prediction.columns) if prediction is not None else []
    # Metadata column names are read from the installed release, never guessed by position.
    matching = [r for r in endpoint_rows if any(v in endpoints for v in r.values())]
    outputs = []
    for row in rows:
        item = {"row_id": row["row_id"], "candidate_id": row["candidate_id"],
                "source_ref": row["source_ref"], "smiles": row["smiles"], "status": row["status"],
                "predictions": None, "reason": row.get("reason")}
        if row["status"] == "succeeded":
            if prediction is None or row["smiles"] not in prediction.index:
                item.update(status="failed", reason="검증 입력에 대한 모델 출력이 누락됨")
            else:
                values = prediction.loc[row["smiles"]].to_dict()
                item["predictions"] = {k: float(v) if math.isfinite(float(v)) else None for k, v in values.items()}
                if any(v is None for v in item["predictions"].values()):
                    item.update(status="partial", reason="정의되지 않은 예측값 있음")
        outputs.append(item)
    return {"status": "succeeded", "semantic_type": "model_prediction", "rows": outputs,
            "summary": {"total_rows": len(rows), "unique_model_inputs": len(unique), "endpoints": len(endpoints)},
            "endpoint_metadata": matching, "device": "cpu", "reference_percentiles": "disabled",
            "versions": {n: importlib.metadata.version(n) for n in ("admet-ai", "chemprop", "torch")},
            "weights": [{"path": str(p.relative_to(root)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                        for p in sorted(root.rglob("*.pt"))],
            "limits": ["사전학습 모델 예측입니다. 이 후보군에서의 보정·실험 성능은 평가하지 않았습니다.",
                       "분류·회귀 항목의 뜻과 단위가 다릅니다. 하나의 치료 성공 확률로 합치지 않습니다.",
                       "DrugBank 참조 백분위는 계산하지 않았습니다."]}


def rna_observations(content, meta):
    if content[:2] == b"\x1f\x8b":
        with gzip.GzipFile(fileobj=io.BytesIO(content)) as stream:
            content = stream.read(MAX_DOWNLOAD + 1)
        if len(content) > MAX_DOWNLOAD:
            raise ValueError("압축 해제된 자료가 현재 처리 범위보다 큽니다.")
    required = ["ensembl_gene_id", "baseMean", "log2FoldChange", "lfcSE", "stat", "pvalue", "padj", "symbol"]
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")), delimiter="\t")
    if reader.fieldnames != required:
        if not reader.fieldnames or any(reader.fieldnames.count(n) != 1 for n in required):
            raise ValueError("차등발현표 열 대응을 확인해야 합니다. 알려진 열 이름이 필요합니다.")
    digest = hashlib.sha256(content).hexdigest()
    rows, missing, invalid = [], {n: 0 for n in required[1:-1]}, {n: 0 for n in required[1:-1]}
    seen, duplicates = set(), 0
    for ordinal, raw in enumerate(reader, 1):
        gene = raw["ensembl_gene_id"]
        duplicates += gene in seen
        seen.add(gene)
        values, states = {}, {}
        for key in required[1:-1]:
            text = raw.get(key)
            if text is None or text.strip() in ("", "NA", "NaN", "nan", "NULL"):
                values[key], states[key] = None, "missing"
                missing[key] += 1
            else:
                try:
                    value = float(text)
                    if not math.isfinite(value):
                        raise ValueError()
                    values[key], states[key] = value, "reported"
                except ValueError:
                    values[key], states[key] = None, "invalid_numeric"
                    invalid[key] += 1
        rows.append({"row_id": f"{digest[:12]}:{ordinal}", "gene_id": gene, "symbol": raw["symbol"],
                     "source_ref": {"decompressed_sha256": digest, "logical_tsv_record_0_based": ordinal},
                     "raw_values": raw, "values": values, "value_states": states,
                     "reference_mapping": "not_run"})
    return {"status": "succeeded", "semantic_type": "reported_observation", "rows": rows,
            "summary": {"total_rows": len(rows), "distinct_gene_ids": len(seen),
                        "duplicate_id_rows": duplicates, "missing_by_column": missing, "invalid_by_column": invalid},
            "contrast": meta.get("contrast"), "context": meta.get("context", "사용자 자료 — 맥락 확인 필요"),
            "limits": ["공개 처리표의 관측 검토입니다. 새로운 차등발현 모형을 적합하지 않았습니다.",
                       "표의 행은 유전자이며 생물학적 반복 시료가 아닙니다. 결측을 0으로 바꾸지 않았습니다.",
                       "SeedMatchR·참조 주석 대응·치료 후보 간 직접 비교 검정은 아직 실행하지 않았습니다.",
                       "랫드 관측을 인간 ATTR-CM 치료 효능으로 해석하지 않습니다."]}


def open_targets(arguments):
    target_id = arguments.get("target_id", "")
    if not re.fullmatch(r"ENSG\d{11}", target_id):
        raise ValueError("확인된 인간 Ensembl 표적 ID가 필요합니다.")
    query = "query($id:String!){target(ensemblId:$id){id approvedSymbol approvedName proteinIds{id source} tractability{label modality value}}}"
    raw, receipt = fetch("https://api.platform.opentargets.org/api/v4/graphql",
                         {"query": query, "variables": {"id": target_id}})
    body = json.loads(raw)
    target = (body.get("data") or {}).get("target")
    status = "partial" if body.get("errors") else "succeeded"
    return {"status": status, "semantic_type": "database_attribute", "response": body,
            "source": receipt, "query": query, "variables": {"id": target_id},
            "summary": {"symbol": target.get("approvedSymbol") if target else None,
                        "records": len(target.get("tractability", [])) if target else 0,
                        "lookup_status": "returned_records" if target else "target_not_resolved"},
            "limits": ["표적 수준의 tractability 속성입니다. 질환별 효능·치료 성공 확률이 아닙니다.",
                       "RNA 전용 평가 항목의 부재는 RNA 관련 근거 전체의 부재가 아닙니다."]}


def literature(arguments):
    query = arguments.get("query", "").strip()
    if not query or len(query) > 1000:
        raise ValueError("검색 질문은 1–1,000자로 입력해 주세요.")
    cursor = arguments.get("cursor", "*")
    if cursor in ("", None):
        cursor = "*"  # The product's empty first-page value is not a provider cursor.
    params = {"query": query, "format": "json", "resultType": "core", "pageSize": 8,
              "cursorMark": cursor}
    raw, receipt = fetch("https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urllib.parse.urlencode(params))
    body = json.loads(raw)
    rows = body.get("resultList", {}).get("result", [])
    import base64
    return {"status": "succeeded", "semantic_type": "literature_search", "response": body,
            "original_response_base64": base64.b64encode(raw).decode(),
            "source": receipt, "rows": rows,
            "summary": {"returned": len(rows), "hit_count": body.get("hitCount"),
                        "next_cursor": body.get("nextCursorMark")},
            "limits": ["검색 결과·초록이며 모든 원문을 검토한 결과가 아닙니다.",
                       "논문 유형·정정 여부·적용 조건과 원문을 확인해 주장별 근거로 사용해야 합니다."]}


def main():
    request = json.loads(Path(sys.argv[1]).read_text())
    started = time.monotonic()
    content = Path(request["input_path"]).read_bytes() if request.get("input_path") else b""
    handlers = {"rdkit": rdkit_properties, "admet": admet_predictions, "rna_observations": rna_observations}
    try:
        tool = request["tool"]
        if tool in handlers:
            result = handlers[tool](content, request.get("input_meta", {}))
        elif tool == 'gtopdb_pharmacology':
            from .gtopdb import retrieve
            result = retrieve(request['arguments'], Path(request['output_path']).parent / 'gtopdb-responses')
        elif tool == 'lens_literature':
            from .lens_sources import retrieve
            result = retrieve(request['arguments'], Path(request['output_path']).parent / 'lens-responses')
        elif tool == 'public_lookup_bundle':
            from .public_lookup_bundle import execute
            result = execute(request['arguments'], Path(request['output_path']).parent / 'public-responses')
        elif tool in ('binding_measurements', 'drug_label_search', 'drug_label', 'clinical_trial_search', 'clinical_trial'):
            from .clinical_sources import HANDLERS
            result = HANDLERS[tool](request['arguments'])
        elif tool == "rna_weighted_distribution":
            from .rna_distribution import analyze
            result = analyze(json.loads(content))
        elif tool == 'chemical_names':
            from .chemical_names import name_structures
            value = json.loads(content)
            rows = value.get('rows') if isinstance(value, dict) else None
            if not isinstance(rows, list):
                raise ValueError('구조를 가진 보존 후보 목록을 선택해 주세요.')
            report = name_structures(rows, fetch, request['arguments'].get('maximum_lookups') or 40)
            result = {'status': 'succeeded', 'rows': rows, **report,
                      'source_artifact_id': request['arguments']['artifact_id']}
        elif tool == 'analogue_proposal':
            from .analogue_proposal import propose
            from .activity_model import fit, score
            source = analogue_source(content, request.get('input_meta', {}))
            result = propose(source, request['arguments'])
            result['source_artifact_id'] = request['arguments']['artifact_id']
            extra = [json.loads(Path(x['path']).read_bytes()) for x in request.get('public_source_inputs') or []]
            fitted = fit(source, extra_sources=[x for x in extra
                                                if x.get('semantic_type') == 'reported_bindingdb_measurements'])
            result['activity_model'] = {k: v for k, v in fitted.items()
                                        if k not in ('model', 'fingerprint') and not k.startswith('_')}
            result['activity_model']['scoring'] = score(result.get('rows') or [], fitted)
            if request['arguments'].get('guided_rounds'):
                from .guided_search import search
                from .analogue_proposal import propose_from
                base = Path(request['output_path']).parent / 'guided'

                def one_round(seed_rows, number):
                    return (propose_from(seed_rows, request['arguments'],
                                         work=str(base / f'round{number}')).get('rows') or [])

                result['guided_search'] = search(source, fitted,
                                                 {'rounds': request['arguments']['guided_rounds'],
                                                  'beam': request['arguments'].get('guided_beam')},
                                                 one_round)
        elif tool == 'literature_compounds':
            from .literature_compounds import collect
            sources=[{**x,'value':json.loads(Path(x['path']).read_bytes())} for x in request['public_source_inputs']]
            result=collect(request['arguments'],sources)
        elif tool == 'structure_search':
            from .structure_search import search
            result=search(request['arguments'])
        elif tool == 'compound_candidates':
            from .compound_discovery import collect
            result=collect(request['arguments'])
        elif tool == 'compound_selection':
            from .compound_discovery import materialize
            result=materialize(json.loads(content),request['arguments'])
        elif tool == "open_targets":
            result = open_targets(request["arguments"])
        elif tool == 'target_context':
            from .target_context import retrieve
            result = retrieve(request['arguments'],Path(request['output_path']).parent/'public-sources')
        elif tool == "literature":
            result = literature(request["arguments"])
        elif tool in ('disease_targets', 'target_disease_evidence', 'chembl_search', 'bioactivities'):
            from .target_evidence import disease_targets, target_disease_evidence, chembl_search, bioactivities
            result = {'disease_targets': disease_targets, 'target_disease_evidence': target_disease_evidence,
                      'chembl_search': chembl_search, 'bioactivities': bioactivities}[tool](request['arguments'])
        elif tool == 'intervention_direction_audit':
            from .intervention_direction import audit
            result = audit(json.loads(content), request['arguments'])
        elif tool == 'target_structure':
            from .binding import fetch_structure
            result = fetch_structure(request['arguments'])
        elif tool == 'molecular_docking':
            from .binding import dock_molecules
            result = dock_molecules(content, request['input_meta'], json.loads(Path(request['structure_path']).read_text()),
                                    request['arguments'], Path(request['output_path']).parent / 'docking')
        elif tool == 'binding_pose_review':
            from .binding_pose import review_poses
            result = review_poses(json.loads(content), json.loads(Path(request['structure_path']).read_text()),
                                  request['arguments'], Path(request['output_path']).parent / 'pose-review')
        elif tool == 'chemical_sirna_evidence':
            from .chemical_sirna import retrieve
            result=retrieve(request['arguments'])
        elif tool == 'rna_chemistry_evidence':
            result=json.loads((Path(__file__).parents[1]/'resources/rna-evidence/nair2017.json').read_text())
        elif tool == 'rna_reference_archive':
            from .rna_resources import archived_reference
            result=archived_reference(request['arguments'])
        elif tool == 'rna_reference_release':
            from .rna_resources import release_reference
            result=release_reference(request['arguments'])
        elif tool == 'rna_transcriptome_search':
            from .rna_resources import search_offtargets
            result=search_offtargets(json.loads(content),request['arguments'],Path(request['output_path']).parent/'offtargets')
        elif tool == 'rna_duplex_transcriptome':
            from .rna_duplex import scan_full_strands
            result = scan_full_strands(json.loads(content), request['arguments'], Path(request['output_path']).parent/'duplex-transcriptome')
        elif tool == 'rna_duplex':
            from .rna_duplex import propose
            result=propose(json.loads(content),request['arguments'])
        elif tool == 'rna_duplex_seed':
            from .rna_duplex import scan_strands
            result=scan_strands(json.loads(content),request['arguments'],Path(request['output_path']).parent/'strand-seeds')
        elif tool == 'pathway_hypotheses':
            from .pathway_hypotheses import analyze
            if hashlib.sha256(content).hexdigest() != request['input_sha256']:
                raise ValueError('경로 추론의 원 조절 패턴 전달 해시가 다릅니다.')
            result = analyze(request['arguments'], json.loads(content), Path(__file__).parents[1],
                Path(request['output_path']).parent/'pathways')
        elif tool in ('exposure_requirements', 'kinetic_conditions', 'regulon_activity'):
            if tool == 'kinetic_conditions':
                from .kinetic_conditions import compare
            elif tool == 'exposure_requirements':
                from .exposure_requirements import compare
            sources = {}
            for item in request['public_source_inputs']:
                raw = Path(item['path']).read_bytes()
                if hashlib.sha256(raw).hexdigest() != item['sha256']:
                    raise ValueError('조건 계산의 출처 전달 해시가 다릅니다.')
                sources[item['artifact_id']] = json.loads(raw)
            if tool == 'regulon_activity':
                from .regulon_activity import analyze
                result = analyze(request['arguments'], sources, Path(__file__).parents[1],
                                 Path(request['output_path']).parent/'regulon')
            else:
                result = compare(request['arguments'], sources)
        elif tool == 'rna_delivery_response':
            from .rna_delivery_response import analyze
            result=analyze(request['arguments'])
        elif tool == 'rna_region_annotation':
            from .rna_regions import annotate
            refs=[]
            for item in request['reference_inputs']:
                raw=Path(item['path']).read_bytes()
                if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('Reference transfer hash differs')
                refs.append((item['artifact_id'],json.loads(raw)))
            config=json.loads((Path(__file__).parents[1]/'configs/rna-resources.json').read_text())
            result=annotate(json.loads(content),refs,config,request['arguments']['artifact_id'])
        elif tool == 'rna_seed_sites':
            from .rna_seed_sites import analyze
            result=analyze(json.loads(content),request['arguments'],Path(request['output_path']).parent/'seed-sites')
        elif tool == 'rna_author_mod':
            from .rna_author_mod import run_modified
            result=run_modified(request['modification_transfer_path'],Path(request['output_path']).parent/'modified-author')
        elif tool == 'rna_author_full':
            from .rna_author import run_author
            result=run_author(json.loads(content),json.loads(Path(request['reference_path']).read_text()),request['arguments'],Path(request['output_path']).parent/'full-author')
        elif tool == 'rna_activity_score':
            from .rna_activity import run_activity
            result=run_activity(json.loads(content),json.loads(Path(request['reference_path']).read_text()),request['arguments'],Path(request['output_path']).parent/'activity')
        elif tool == 'rna_delivery_simulation':
            from .rna_delivery import simulate
            result=simulate(request['arguments'])
        elif tool == 'rna_reference':
            from .rna_sequence import retrieve_reference
            result = retrieve_reference(request['arguments'])
        elif tool == 'rna_tissue_context':
            from .rna_context import tissue_context
            result = tissue_context(json.loads(content), request['arguments'], Path(request['output_path']).parent/'public-sources')
        elif tool == 'rna_variant_catalog':
            from .rna_alleles import variant_catalog
            config = json.loads((Path(__file__).parents[1]/'configs/rna-resources.json').read_text())
            result = variant_catalog(json.loads(content), request['arguments']['artifact_id'], config, Path(request['output_path']).parent/'public-sources')
        elif tool == 'rna_allele_scenario':
            from .rna_alleles import compare_scenario
            result = compare_scenario(json.loads(content), json.loads(Path(request['catalog_path']).read_text()),
                json.loads(Path(request['reference_path']).read_text()), request['arguments'])
        elif tool == 'rna_candidate_space':
            from .rna_candidate_space import enumerate_space
            def verified_inputs(items):
                result = []
                for item in items:
                    raw = Path(item['path']).read_bytes()
                    if hashlib.sha256(raw).hexdigest() != item['sha256']:
                        raise ValueError('전달본 해시가 원 입력과 다릅니다.')
                    result.append((item['artifact_id'], json.loads(raw)))
                return result
            result = enumerate_space(verified_inputs(request['reference_inputs']),
                request['arguments']['paired_length'], verified_inputs(request['prior_candidate_inputs']))
        elif tool == 'rna_candidate_selection':
            from .rna_candidate_space import select_and_evaluate
            args = request['arguments']
            result = select_and_evaluate(json.loads(content), args['reference_id'],
                json.loads(Path(request['reference_path']).read_text()), args['candidate_ids'],
                args['chemistry'], args['reason'])
        elif tool == 'rna_reference_panel':
            from .rna_reference_panel import compare
            references=[]
            for item in request['reference_inputs']:
                raw=Path(item['path']).read_bytes()
                if hashlib.sha256(raw).hexdigest()!=item['sha256']:
                    raise ValueError('전사체 전달본 해시가 원 입력과 다릅니다.')
                references.append((item['artifact_id'],json.loads(raw)))
            result=compare(json.loads(content),references,request['arguments']['candidate_ids'])
        elif tool in ('rna_sequence_evaluation', 'rna_candidate_generation'):
            from .rna_sequence import evaluate, generate
            result = (generate(json.loads(content), request['arguments']) if tool == 'rna_candidate_generation'
                      else evaluate(json.loads(content), request['arguments']['guides'], request['arguments']['chemistry']))
        elif tool in ("article", "entity_search"):
            from .public_evidence import find_entities, read_article
            result = (read_article if tool == "article" else find_entities)(request["arguments"])
            if tool == 'article' and request.get('figure_cache_dir') and result.get('status') in ('succeeded', 'partial'):
                # Runs in the credential-free article worker, never from a lazy UI GET.
                from .article_figures import retrieve_for_article
                result['figure_retrieval'] = retrieve_for_article(result, request['figure_cache_dir'],
                    lambda url: fetch(url, timeout=25, max_download=8 * 1024 * 1024))
        elif tool == "repository_document":
            from .repository_documents import read_repository_document
            result = read_repository_document(request["arguments"])
        elif tool == "rna_gene_review":
            from .rna_analysis import review_genes
            inputs = [{**item, "result": json.loads(Path(item["path"]).read_text())} for item in request["inputs"]]
            result = review_genes(inputs, request["arguments"]["genes"])
        elif tool == 'rna_seed_analysis':
            from .rna_seed import analyze
            extra=request['seed_inputs']
            reference=json.loads(Path(extra['reference_id']['path']).read_text())
            guide=json.loads(Path(extra['guide_id']['path']).read_text())
            result=analyze(rna_observations(content,request['input_meta']),request['input_meta'],reference,guide,
                Path(request['output_path']).parent/'seed-analysis',Path(__file__).parent/'vendor/seedmatchr')
            result['consumed_sources']={k:{n:v for n,v in entry.items() if n!='path'} for k,entry in extra.items()}
        else:
            raise ValueError("등록되지 않은 도구입니다.")
        result.update(adapter_revision=REVISION, elapsed_seconds=round(time.monotonic() - started, 5))
    except Exception as exc:
        # Provider credentials are never in the job. GtoPdb reads its service key
        # only within its dedicated adapter, whose transport redacts errors.
        result = {"status": "failed", "error_type": type(exc).__name__, "error": str(exc)[:1000],
                  "adapter_revision": REVISION, "elapsed_seconds": round(time.monotonic() - started, 5)}
    Path(request["output_path"]).write_text(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
