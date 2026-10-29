"""Execute registered tools and an explicitly configured model against durable snapshots."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import jsonschema

from .contracts import CAPABILITIES, DECISION, FINAL_DECISION, FUNCTION_BY_NAME, RESEARCH_NOTES, TOOL_NAMES, model_functions, model_final_decision
from .gateway import GatewayError
from .decision_preservation import DecisionPreservationError
from .schema_feedback import schema_feedback
from .validation_help import correction_reason
from .provenance_repair import repair_instruction
from .planner_recovery import completed_rounds, prepare_quota_resume, recorded_response_budget, SYNTHESIS_SUFFIX
from .context_delivery import apply_context_delivery
from .catalog_delivery import apply_catalog_delivery
from .model_context import artifact_overview, decision_history, find_rows, model_json, next_model_context, reading_focus, select_columns, working_readings
from .research_loop import active_check, decision_id, validate_hypotheses, validate_loop
from .store import Conflict, dump, now
from .private_supervision import checked_limit, response_indices, response_state, ActionMonitor

FUNCTION_TO_TOOL = {'predict_rna_interactions':'rna_interactions', 'inspect_pose_interactions':'pose_interactions', 'enumerate_protonation_states': 'protonation_states', "compare_rna_distributions": "rna_weighted_distribution", "compute_properties": "rdkit", "predict_admet": "admet", "review_rna": "rna_observations",
                    "read_scientific_webpage": "webpage",
                    "lookup_target": "open_targets", "search_literature": "literature", "read_open_article": "article",
                    "find_entities": "entity_search", "inspect_rna_genes": "rna_gene_review",
                    "read_repository_document": "repository_document", "analyze_rna_seed": "rna_seed_analysis"}
READING_FUNCTIONS = ("inspect_hypothesis_history", "inspect_artifact", "inspect_table_columns", "find_table_rows", "find_table_columns", "read_evidence_bundle", "inspect_article_references", "read_calculation_section", "read_reasoning_principle")
FUNCTION_TO_TOOL.update({"lookup_disease_targets": "disease_targets", "read_target_disease_evidence": "target_disease_evidence",
                        "find_chembl_entities": "chembl_search", "read_bioactivities": "bioactivities",
                        "fetch_binding_structure": "target_structure", "dock_molecules": "molecular_docking",
                        "retrieve_rna_reference": "rna_reference", "evaluate_rna_guides": "rna_sequence_evaluation",
                        "generate_rna_candidates": "rna_candidate_generation"})
FUNCTION_TO_TOOL["score_full_author_rna"]="rna_author_full"
FUNCTION_TO_TOOL["score_modified_author_rna"]="rna_author_mod"
FUNCTION_TO_TOOL.update({"retrieve_archived_rna_reference":"rna_reference_archive", "search_rna_offtargets":"rna_transcriptome_search", "score_rna_activity":"rna_activity_score", "simulate_rna_delivery":"rna_delivery_simulation"})
FUNCTION_TO_TOOL['search_rna_seed_sites']='rna_seed_sites'
FUNCTION_TO_TOOL['review_docking_poses']='binding_pose_review'
FUNCTION_TO_TOOL['compare_rna_references']='rna_reference_panel'
FUNCTION_TO_TOOL['retrieve_release_rna_reference']='rna_reference_release'
FUNCTION_TO_TOOL.update({'read_rna_tissue_context':'rna_tissue_context','list_rna_reference_variants':'rna_variant_catalog','compare_rna_allele_scenario':'rna_allele_scenario'})
FUNCTION_TO_TOOL.update({'enumerate_rna_candidate_space':'rna_candidate_space', 'evaluate_selected_rna_candidates':'rna_candidate_selection'})
FUNCTION_TO_TOOL['audit_intervention_directions']='intervention_direction_audit'
FUNCTION_TO_TOOL['read_rna_chemistry_evidence']='rna_chemistry_evidence'
FUNCTION_TO_TOOL['retrieve_chemical_sirna_evidence']='chemical_sirna_evidence'
FUNCTION_TO_TOOL.update({'collect_compound_candidates':'compound_candidates','materialize_compound_candidates':'compound_selection','name_candidate_structures':'chemical_names'})
FUNCTION_TO_TOOL.update({'resolve_literature_compounds':'literature_compounds','find_binding_structures':'structure_search'})
FUNCTION_TO_TOOL.update({"search_duplex_strand_transcriptome":"rna_duplex_transcriptome", "propose_rna_duplexes":"rna_duplex", "search_duplex_strand_seeds":"rna_duplex_seed", "annotate_rna_candidate_regions":"rna_region_annotation", "analyze_delivery_response":"rna_delivery_response"})
FUNCTION_TO_TOOL.update({'search_pubmed':'pubmed_search','read_pubmed_abstracts':'pubmed_abstracts','dock_pocket_molecules':'pocket_docking'})
PUBLIC_LOOKUPS = {"rna_tissue_context", "rna_variant_catalog", "intervention_direction_audit","literature_compounds","structure_search","compound_candidates","literature", "open_targets", "entity_search", "article", "repository_document",
                  "disease_targets", "target_disease_evidence", "chembl_search", "bioactivities", "target_structure", "rna_reference", "webpage"}
FUNCTION_TO_TOOL.update({'read_binding_measurements': 'binding_measurements', 'search_drug_labels': 'drug_label_search',
                         'read_drug_label': 'drug_label', 'search_clinical_trials': 'clinical_trial_search',
                         'read_clinical_trial': 'clinical_trial'})
PUBLIC_LOOKUPS.update(('binding_measurements', 'drug_label_search', 'drug_label', 'clinical_trial_search', 'clinical_trial'))
FUNCTION_TO_TOOL['collect_public_evidence'] = 'public_lookup_bundle'
PUBLIC_LOOKUPS.add('public_lookup_bundle')
FUNCTION_TO_TOOL['read_target_context'] = 'target_context'
PUBLIC_LOOKUPS.add('target_context')
FUNCTION_TO_TOOL['compare_exposure_requirements'] = 'exposure_requirements'
FUNCTION_TO_TOOL['read_curated_pharmacology'] = 'gtopdb_pharmacology'
PUBLIC_LOOKUPS.add('gtopdb_pharmacology')
FUNCTION_TO_TOOL['search_lens_literature'] = 'lens_literature'
PUBLIC_LOOKUPS.add('lens_literature')
PUBLIC_LOOKUPS.update(('pubmed_search','pubmed_abstracts'))
FUNCTION_TO_TOOL['propose_analogue_structures'] = 'analogue_proposal'
FUNCTION_TO_TOOL['qualify_saved_proposals'] = 'proposal_qualification'
# A name is a live lookup of PubChem's record for a stored structure; refreshed, never cached.
PUBLIC_LOOKUPS.add('chemical_names')
FUNCTION_TO_TOOL['compare_kinetic_conditions'] = 'kinetic_conditions'
FUNCTION_TO_TOOL['infer_regulon_activity'] = 'regulon_activity'
FUNCTION_TO_TOOL['infer_pathway_hypotheses'] = 'pathway_hypotheses'
FUNCTION_TO_TOOL['query_pathway_node_states'] = 'pathway_node_states'
FUNCTION_TO_TOOL['compare_pathway_explanations'] = 'pathway_robustness'
FUNCTION_TO_TOOL['select_next_observation'] = 'next_observation_selection'
FUNCTION_TO_TOOL['extract_source_document'] = 'source_document'
FUNCTION_TO_TOOL['compare_reported_activity_pairs'] = 'reported_activity_comparison'
FUNCTION_TO_TOOL.update({'prepare_molecular_states':'molecule_preparation','score_synthetic_complexity':'synthetic_complexity'})
FUNCTION_TO_TOOL.update({'optimize_molecular_geometry':'xtb_geometry','sample_molecular_conformers':'crest_conformers'})
FUNCTION_TO_TOOL.update({'search_public_web':'public_web_search','read_public_research_page':'public_research_page'})
FUNCTION_TO_TOOL['plan_synthesis_routes'] = 'retrosynthesis'
FUNCTION_TO_TOOL.update({'find_structure_pockets':'structure_pockets','simulate_protein_dynamics':'protein_dynamics','analyze_saved_trajectory':'trajectory_analysis'})
PUBLIC_LOOKUPS.update(('public_web_search','public_research_page'))
FUNCTION_TO_TOOL.update({'read_gwas_studies':'gwas_studies','find_perturbagen_metadata':'perturbagen_metadata'})
PUBLIC_LOOKUPS.update(('gwas_studies','perturbagen_metadata'))



# A decision the model returned can be structurally wrong in a way that only cross-field checks
# catch - two options given the same priority inside one comparison group, a scope target naming a
# part its hypothesis does not have. Rejecting it ends the job, and twenty rounds of retrieval go
# unpublished with it, which is how arun that read 88 sources ends with an empty stage 2.
#
# This is NOT a retry of a failed call. The provider call succeeded and returned; our own
# validation refused the content. Showing the model what we refused and asking for a corrected
# decision is a different request, and it is bounded: after this many corrections the job fails
# with the original reason.
MAXIMUM_DECISION_CORRECTIONS = 2
# The research budget. Correction rounds run past it on purpose: the model reliably spends all
# sixteen and returns its decision on the last one, so a correction that needs a round inside the
# budget never gets one. A correction is not research - it rewrites a field of an answer already
# written - so it may not call tools, and the guard below enforces that.
RESEARCH_ROUNDS = 16
_DEFAULT_RESPONSE_LIMIT = object()
# The three refusals seen in real runs, each with the smallest edit that resolves it. Naming
# them beats a generic "fix it": the model has one round and no way to ask what we meant.
DECISION_REJECTED = (
    '방금 반환한 판단은 게시되지 않았습니다. 사유: {reason}\n'
    '조사 결과와 읽은 자료는 그대로 남아 있습니다. 같은 판단을 그 한 곳만 고쳐 다시 반환해 주세요. '
    '**새로 조회하지 말고** 지금까지 읽은 것으로 바로잡으면 됩니다. 도구를 호출하면 이 작업은 '
    '거기서 멈춥니다.\n'
    '- 우선순위가 겹쳤다면: 같은 comparison_group 안에서 서로 다른 번호를 주거나, 한쪽 priority를 '
    'null로 두세요. 순위를 못 정하겠으면 null이 정답입니다.\n'
    '- 부분 판단 연결이 어긋났다면: 그 가설의 assessment_scope.parts에 **실제로 있는** part id만 '
    '가리키세요. 없으면 그 연결을 빼세요.\n'
    '- 평가의 출처가 이 연구에 없다면: support_source_ids·challenge_source_ids에서 이 연구가 실제로 '
    '만든 artifact id만 남기세요. 기억에서 쓴 id나 외부 식별자는 빼세요. 남는 것이 없으면 빈 '
    '목록으로 두고 그 사실을 reason에 적으세요.\n'
    '판단의 과학적 내용은 바꾸지 마세요. 형식이 맞지 않는 한 곳만 고치는 것입니다.')

class Runner:
    def __init__(self, root, store, gateway, attempts_root=None, *, response_limit=_DEFAULT_RESPONSE_LIMIT):
        if response_limit is not _DEFAULT_RESPONSE_LIMIT:
            checked_limit(response_limit)
        self._response_limit_setting = response_limit
        self.root, self.store, self.gateway = Path(root), store, gateway
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="evida")
        self.explanation_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="evida-explanation")
        self.science_lock = threading.Lock()
        self.science_python = self.root / ".runtime/science/bin/python"
        self.attempts_root = Path(attempts_root) if attempts_root else self.root / "runs/attempts"
        self.fingerprint = json.loads((self.root / "configs/science-runtime.json").read_text())
        actual = json.loads(subprocess.check_output([str(self.science_python), str(self.root / "scripts/fingerprint_science.py")],
            cwd=self.root, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}, text=True))
        if any(actual[key] != self.fingerprint[key] for key in ("python", "packages", "weights")):
            raise ValueError("과학 실행 환경이 검증한 버전과 다릅니다. 재사용 전에 실제 환경을 다시 확인해야 합니다.")
        # Optional activity predictors verify their versions before fitting. Their presence
        # also identifies cached calculations, including a retained unavailable-model result.
        self.fingerprint['activity_prediction_packages'] = actual.get('activity_prediction_packages', {})
        self.native_library_directory = None
        native = self.fingerprint.get("native_libraries")
        if native:
            directory = Path(native["directory"]).resolve(strict=True)
            for item in native["files"]:
                library = directory / item["name"]
                if library.parent != directory or hashlib.sha256(library.read_bytes()).hexdigest() != item["sha256"]:
                    raise ValueError("과학 실행 환경의 고정 native library가 다릅니다. 실제 환경을 확인해야 합니다.")
            self.native_library_directory = str(directory)
        self.prompt = (self.root / "configs/planner.md").read_text()
        delivery_path = self.root / "configs/context-delivery.json"
        self.context_recent_views = json.loads(delivery_path.read_text())["recent_views"] if delivery_path.exists() else None
        if self.context_recent_views is not None and (type(self.context_recent_views) is not int or self.context_recent_views < 1):
            raise ValueError("최근 조회본 전달 설정을 확인해 주세요.")

    def start(self, wid, rev, tool, arguments):
        if tool == "planner":
            if not self.gateway.status()["available"]:
                raise GatewayError("input_missing", self.gateway.status()["message"])
            current = self.store.snapshot(wid)
            existing = current["jobs"]
            if any(j["kind"] in ("planner", "research_check") and j["status"] in ("queued", "running") for j in existing):
                raise Conflict("현재 판단 작업이 진행 중입니다. 새 메시지는 지금도 저장할 수 있습니다.")
            if set(arguments) - {"synthesis_only", "source_views", "model", "requested_check_operations", "decision_preservation", "reasoning_excluded_cases"} or ("synthesis_only" in arguments and type(arguments["synthesis_only"]) is not bool):
                raise ValueError("판단 실행 옵션을 확인해 주세요.")
            excluded = arguments.get('reasoning_excluded_cases', [])
            if (not isinstance(excluded, list) or len(excluded) > 30
                    or not all(isinstance(case, str) and 0 < len(case) <= 100 for case in excluded)):
                raise ValueError('추론 예시에서 제외할 사례는 이름 목록으로 지정하세요.')
            # A route that cannot run now (spent competition allowance, unavailable subscription)
            # is refused before anything is recorded, so the visitor can choose another by hand.
            route_check = getattr(self.gateway, "check_model_available", None)
            if route_check is not None:
                chosen = arguments.get("model") or self.workspace_model(wid)
                if chosen is None or chosen in self.gateway.approved_models():
                    route_check(chosen)
            if 'requested_check_operations' in arguments:
                from .finalization import requested_operations
                requested_operations(current, arguments['requested_check_operations'])
            if 'decision_preservation' in arguments:
                from .decision_preservation import bind
                bind(self.store, wid, arguments['decision_preservation'])
            # Checked here as well as in the gateway, so an unapproved name is refused before a
            # job is queued rather than after the researcher has been told the run started.
            if arguments.get("model") is not None and arguments["model"] not in self.gateway.approved_models():
                raise ValueError("현재 실행 정책에 승인되지 않은 모델입니다.")
            if 'source_views' in arguments:
                from .provided_views import build
                build(self, wid, arguments['source_views'])
            jid = self.store.enqueue(wid, rev, tool, arguments)
            self.pool.submit(self.run_planner, jid)
            return jid
        self.validate_tool(wid, tool, arguments)
        jid = self.store.enqueue(wid, rev, tool, arguments, self.cache_key(wid, tool, arguments))
        try:
            self.pool.submit(self.run_tool_job, jid, True)
        except Exception as exc:
            if tool == 'source_document':
                self.store.finish_job(jid, 'failed', error='문서 추출을 시작하지 못했습니다: ' + str(exc)[:400])
            raise
        return jid

    def workspace_model(self, wid):
        """The route this research chose earlier; only a multi-route gateway has one."""
        if getattr(self.gateway, "check_model_available", None) is None:
            return None
        from .model_routes import workspace_model
        return workspace_model(self.store, wid, self.gateway)

    def resume_quota(self, wid, rev, source_id):
        if not self.gateway.status()["available"]:
            raise GatewayError("input_missing", self.gateway.status()["message"])
        prepared = prepare_quota_resume(self, wid, rev, source_id)
        jid = self.store.enqueue(wid, rev, "planner", prepared['arguments'])
        self.pool.submit(self.run_planner, jid, prepared)
        return jid

    def validate_tool(self, wid, tool, arguments):
        from .evidence_scope import check_tool
        check_tool(self.store.snapshot(wid), tool)
        spec = next((s for s in CAPABILITIES if s["id"] == tool), None)
        if spec is None:
            raise ValueError("등록되지 않은 도구입니다.")
        name = next(n for n, t in FUNCTION_TO_TOOL.items() if t == tool)
        try:
            jsonschema.validate(arguments, FUNCTION_BY_NAME[name]["parameters"])
        except jsonschema.ValidationError as exc:
            raise ValueError("도구 입력 형식을 확인해 주세요: " + exc.message[:400]) from None
        if tool in ('pubmed_search','pubmed_abstracts'):
            from .ncbi_pubmed import guard_scope,validate,prepare_abstracts
            from .evidence_scope import view as source_scope
            guard_scope(source_scope(self.store.snapshot(wid)))
            validate(tool,arguments)
            if tool=='pubmed_abstracts':prepare_abstracts(self.store.artifact(wid,arguments['artifact_id']),arguments)
        if tool=='pocket_docking':
            from .pocket_docking import prepare
            prepare(self.store,wid,arguments)
        if tool == 'reported_activity_comparison':
            from .reported_activity_comparison import prepare
            prepare(self.store, wid, arguments)
        if tool == 'next_observation_selection':
            from .next_observation_binding import prepare
            prepare(self.store, wid, arguments)
        if tool == 'proposal_qualification':
            proposal=self.store.artifact(wid,arguments['artifact_id'])
            source=self.store.artifact(wid,arguments['source_artifact_id'])
            value=json.loads(proposal['content'])
            if value.get('source_artifact_id')!=source['id'] or not isinstance(value.get('rows'),list) or not value['rows']:
                raise ValueError('실제 생성 행과 대응하는 원출처를 선택해 주세요.')
            if arguments.get('generation_contract_artifact_id'):
                contract=json.loads(self.store.artifact(wid,arguments['generation_contract_artifact_id'])['content'])
                expected={'source_artifact_id':source['id'],'source_sha256':source['sha256'],
                          'proposal_artifact_id':proposal['id'],'proposal_sha256':proposal['sha256']}
                if any(contract.get(k)!=v for k,v in expected.items()):
                    raise ValueError('생성계약의 원출처·제안 ID와 SHA가 이 입력과 다릅니다.')
        if tool == 'pathway_hypotheses':
            from .pathway_hypotheses import prepare, verified_resources, load_prior
            source = self.store.artifact(wid, arguments['artifact_id'])
            cfg, _ = verified_resources(self.root)
            prepare(arguments, json.loads(source['content']), load_prior(cfg))
        if tool == 'pathway_node_states':
            from .pathway_node_states import prepare
            source = self.store.artifact(wid, arguments['artifact_id'])
            if source['kind'] != 'pathway_hypotheses':
                raise ValueError('보존된 경로 계산 결과를 선택해 주세요.')
            prepare(json.loads(source['content']), arguments, artifact_sha256=source['sha256'])
        if tool == 'pathway_robustness':
            from .pathway_robustness import compare_saved_pathways
            compare_saved_pathways(self.store, wid, arguments['artifact_ids'])
        if tool=='literature_compounds':
            from .source_candidates import validate_resolution_sources
            validate_resolution_sources(self.store, wid, arguments['source_artifact_ids'])
            for aid in arguments['source_artifact_ids']:
                if self.store.artifact(wid,aid)['kind'] not in ('article','literature','source_candidates'):
                    raise ValueError('실제로 받은 공개 문헌/원문 자료만 사용할 수 있습니다.')
        if tool == 'exposure_requirements':
            from .exposure_requirements import compare
            sources = {aid: json.loads(self.store.artifact(wid, aid)['content'])
                       for aid in arguments['source_artifact_ids']}
            compare(arguments, sources)  # Exact source/units checked before enqueuing.
        if tool == 'kinetic_conditions':
            from .kinetic_conditions import compare
            sources = {aid: json.loads(self.store.artifact(wid, aid)['content'])
                       for aid in arguments['source_artifact_ids']}
            compare(arguments, sources)
        if tool == 'regulon_activity':
            from .regulon_activity import prepare, verified_resources
            sources = {aid: json.loads(self.store.artifact(wid, aid)['content'])
                       for aid in arguments['source_artifact_ids']}
            prepare(arguments, sources)
            verified_resources(self.root)
        if tool == 'rna_seed_analysis':
            for field,kind in [('reference_id','rna_seed_reference'),('guide_id','rna_guide')]:
                if self.store.artifact(wid,arguments[field])['kind']!=kind:
                    raise ValueError('출처가 확인된 RNA 참조·가이드 자료가 필요합니다.')
            guide=json.loads(self.store.artifact(wid,arguments['guide_id'])['content'])
            source=self.store.artifact(wid,arguments['artifact_id'])
            filename=source['meta'].get('original_filename')
            if filename not in guide.get('verified_input_filenames',[]):
                raise ValueError('이 처리표와 가이드 서열의 대응이 아직 확인되지 않았습니다.')
            if guide.get('verified_input_sha256',{}).get(filename)!=source['sha256']:
                raise ValueError('서열과 대응하는 처리표의 원본 해시 확인이 필요합니다.')
        if tool == 'pose_interactions':
            from .pose_interactions import prepare, configuration
            contact_input=prepare(self.store,wid,arguments)
            if contact_input['availability']=='ready':configuration()
        if tool == 'retrosynthesis':
            from .retrosynthesis import prepare, configuration
            prepare(self.store.artifact(wid,arguments['artifact_id']), arguments)
            configuration()
        if tool in ('structure_pockets','protein_dynamics','trajectory_analysis'):
            from .protein_computation import prepare, configuration
            prepare(self.store.artifact(wid,arguments['artifact_id']), arguments, tool)
            configuration()
        if tool in ('xtb_geometry','crest_conformers'):
            from .molecular_physics import prepare, configuration
            prepare(self.store.artifact(wid,arguments['artifact_id']),arguments,tool)
            configuration()
        if tool in ('molecule_preparation','synthetic_complexity'):
            from .molecular_preparation import prepare, configuration
            prepare(self.store.artifact(wid,arguments['artifact_id']),arguments,tool)
            configuration()
        if tool == 'rna_interactions':
            from .rna_interaction import prepare, configuration
            prepare(self.store.artifact(wid,arguments['artifact_id']),self.store.artifact(wid,arguments['reference_id']),arguments)
            configuration()
        if tool == 'protonation_states':
            from .protonation import prepare, configuration
            prepare(self.store.artifact(wid, arguments['artifact_id']), arguments)
            configuration()
        if spec["input_kind"]:
            artifact = self.store.artifact(wid, arguments.get("artifact_id", ""))
            if artifact["kind"] != spec["input_kind"] and not (spec["input_kind"] == "rna_reference" and artifact["kind"] == "rna_reference_archive") and not (spec["input_kind"] == "compound_candidates" and artifact["kind"] in ("literature_compounds", "binding_measurements")):
                raise ValueError("이 도구가 요구하는 자료 종류와 다릅니다.")
        if tool in ('rna_duplex','rna_transcriptome_search','rna_activity_score','rna_author_full','rna_seed_sites','rna_reference_panel'):
            if self.store.artifact(wid,arguments['artifact_id'])['kind'] not in ('rna_sequence_evaluation','rna_candidate_generation'):
                raise ValueError('완료한 RNA 가이드 계산을 선택해 주세요.')
            if tool in ('rna_activity_score','rna_author_full') and self.store.artifact(wid,arguments['reference_id'])['kind'] not in ('rna_reference','rna_reference_archive'):
                raise ValueError('원 전사체 참조가 필요합니다.')
            if tool == 'rna_reference_panel':
                if len(set(arguments['reference_ids'])) != len(arguments['reference_ids']):
                    raise ValueError('전사체 참조를 중복 선택하지 마세요.')
                for aid in arguments['reference_ids']:
                    if self.store.artifact(wid,aid)['kind'] not in ('rna_reference','rna_reference_archive'):
                        raise ValueError('실제 전사체 참조 자료를 선택해 주세요.')
        if tool == 'rna_candidate_space':
            for field, kinds in [('reference_ids', ('rna_reference', 'rna_reference_archive')),
                                 ('prior_candidate_artifact_ids', ('rna_sequence_evaluation', 'rna_candidate_generation'))]:
                if len(set(arguments[field])) != len(arguments[field]):
                    raise ValueError('같은 입력을 중복 선택하지 마세요.')
                for aid in arguments[field]:
                    if self.store.artifact(wid, aid)['kind'] not in kinds:
                        raise ValueError('원 전사체 서열과 이전 후보 계산을 구분해 주세요.')
        if tool == 'rna_candidate_selection':
            if self.store.artifact(wid, arguments['reference_id'])['kind'] not in ('rna_reference', 'rna_reference_archive'):
                raise ValueError('후보 열거에 사용한 실제 전사체 서열이 필요합니다.')
        if tool == 'rna_allele_scenario':
            if self.store.artifact(wid, arguments['artifact_id'])['kind'] not in ('rna_sequence_evaluation', 'rna_candidate_generation'):
                raise ValueError('실제 후보 계산을 선택해 주세요.')
            catalog = self.store.artifact(wid, arguments['catalog_id'])
            if catalog['kind'] != 'rna_variant_catalog':
                raise ValueError('공개 변이 목록을 선택해 주세요.')
            value = json.loads(catalog['content'])
            parent = self.store.artifact(wid, value['reference_artifact_id'])
            if parent['kind'] not in ('rna_reference', 'rna_reference_archive'):
                raise ValueError('시나리오의 원 참조가 필요합니다.')
        if tool in ('molecular_docking', 'binding_pose_review'):
            structure = self.store.artifact(wid, arguments['structure_id'])
            if structure['kind'] != 'target_structure' or json.loads(structure['content']).get('status') != 'succeeded':
                raise ValueError('먼저 실제 표적 구조를 조회하고 확인해 주세요.')
        elif tool == "open_targets":
            if not isinstance(arguments.get("target_id"), str):
                raise ValueError("표적 ID가 필요합니다.")
        elif tool == "literature":
            if not isinstance(arguments.get("query"), str) or not arguments["query"].strip():
                raise ValueError("검색 질문을 입력해 주세요.")
        elif tool == "webpage":
            from .web_sources import validate_url
            validate_url(arguments['url'])
        elif tool in ('public_web_search', 'public_research_page'):
            from .literature_access import validate
            validate(tool, arguments)
        elif tool in ('gwas_studies', 'perturbagen_metadata'):
            from .research_apis import validate
            validate(tool, arguments)
        elif tool == "rna_gene_review":
            if len(set(arguments["artifact_ids"])) != len(arguments["artifact_ids"]):
                raise ValueError("같은 RNA 자료를 중복 입력하지 마세요.")
            for aid in arguments["artifact_ids"]:
                if self.store.artifact(wid, aid)["kind"] != "rna_observations":
                    raise ValueError("RNA 관측 검토를 완료한 자료가 필요합니다.")

    def _next_observation_cache_key(self, bundle):
        from .next_observation_binding import digest
        return digest({'tool': 'next_observation_selection', 'input_bundle': bundle,
            'runtime': self.fingerprint,
            'code': {name: hashlib.sha256((self.root / 'evida' / name).read_bytes()).hexdigest()
                     for name in ('next_observation.py', 'next_observation_binding.py', 'measurement_report.py', 'check_subject_binding.py', 'contracts.py', 'runner.py', 'science.py', 'observation_amendment.py')}})

    def cache_key(self, wid, tool, arguments):
        if tool=='pocket_docking':
            from .pocket_docking import prepare
            bundle=prepare(self.store,wid,arguments)
            return hashlib.sha256(dump({'tool':tool,'input':bundle,'arguments':arguments,
                'code':{n:hashlib.sha256((self.root/'evida'/n).read_bytes()).hexdigest()for n in
                  ('pocket_docking.py','pocket_docking_worker.py','binding.py','protein_computation_worker.py','receptor_graph.py','receptor_graph_worker.py')},
                'runtime':self.fingerprint}).encode()).hexdigest()
        if tool == 'reported_activity_comparison':
            # Small exact arithmetic: retain each explicit selection and its fresh
            # transitive source binding without cross-version reuse.
            return None
        if tool == 'source_document':
            # Retain each requested extraction with its actual parser version.
            # Do not reuse across optional parser upgrades outside the pinned core.
            return None
        if tool == 'next_observation_selection':
            from .next_observation_binding import prepare
            return self._next_observation_cache_key(prepare(self.store, wid, arguments))
        if tool == 'analogue_proposal':
            ids = list(dict.fromkeys([arguments['artifact_id'], *(arguments.get('source_artifact_ids') or [])]))
            names = ('analogue_proposal.py', 'activity_inputs.py', 'activity_model.py',
                     'activity_selection.py', 'activity_gp.py', 'guided_search.py',
                     'generation_source_binding.py', 'science.py', 'runner.py',
                     'vendor/tanimoto_gp/tanimoto_gp.py', 'vendor/tanimoto_gp/tanimoto_functions.py')
            return hashlib.sha256(dump({'tool': tool, 'arguments': arguments,
                'inputs': [{'id': aid, 'sha256': self.store.artifact(wid, aid)['sha256'],
                            'meta': self.store.artifact(wid, aid)['meta']} for aid in ids],
                'code': {name: hashlib.sha256((self.root/'evida'/name).read_bytes()).hexdigest()
                         for name in names},
                'model_config': hashlib.sha256((self.root/'configs/activity-models.json').read_bytes()).hexdigest(),
                'runtime': self.fingerprint}).encode()).hexdigest()
        if tool == 'pathway_robustness':
            return hashlib.sha256(dump({'tool':tool,'arguments':arguments,
                'sources':{aid:self.store.artifact(wid,aid)['sha256'] for aid in arguments['artifact_ids']},
                'code':{name:hashlib.sha256((self.root/'evida'/name).read_bytes()).hexdigest()
                    for name in ('pathway_robustness.py','contracts.py','science.py','runner.py')},
                'runtime':self.fingerprint}).encode()).hexdigest()
        if tool == 'proposal_qualification':
            ids=[arguments['artifact_id'],arguments['source_artifact_id']]
            if arguments.get('generation_contract_artifact_id'):ids.append(arguments['generation_contract_artifact_id'])
            source = self.store.artifact(wid, arguments['source_artifact_id'])
            pool, pool_status = self.qualification_source_pool(wid, source)
            if pool:
                ids.append(pool['id'])
            return hashlib.sha256(dump({'tool':tool,'arguments':arguments,'inputs':[{"id":aid,"sha256":self.store.artifact(wid,aid)['sha256'],'meta':self.store.artifact(wid,aid)['meta']} for aid in ids], 'source_pool_status': pool_status, 'code':{n:hashlib.sha256((self.root/'evida'/n).read_bytes()).hexdigest() for n in ('proposal_qualification.py','proposal_qualification_worker.py','science.py','runner.py')},'runtime':self.fingerprint}).encode()).hexdigest()
        if tool == 'pathway_hypotheses':
            from .pathway_hypotheses import verified_resources
            _, resources = verified_resources(self.root)
            return hashlib.sha256(dump({'tool':tool,'arguments':arguments,
                'source':self.store.artifact(wid,arguments['artifact_id'])['sha256'],
                'resources':resources,'runtime':self.fingerprint,
                'code':{n:hashlib.sha256((self.root/'evida'/n).read_bytes()).hexdigest()
                    for n in ('pathway_hypotheses.py','pathway_hypotheses.R','pathway_node_states.py','pathway_lp.py','contracts.py','science.py','runner.py')}}).encode()).hexdigest()
        if tool == 'pathway_node_states':
            from .pathway_hypotheses import verified_resources
            source = self.store.artifact(wid, arguments['artifact_id'])
            packet = json.loads(source['content']).get('solver_package')
            # A legacy artifact can report missing retained input without loading
            # the optional solver runtime or searching its former attempt folder.
            resources = verified_resources(self.root)[1] if packet is not None else None
            return hashlib.sha256(dump({'tool':tool,'arguments':arguments,'source':source['sha256'],
                'package': packet.get('sha256') if isinstance(packet, dict) else None,
                'resources':resources,'runtime':self.fingerprint,
                'code':{n:hashlib.sha256((self.root/'evida'/n).read_bytes()).hexdigest()
                    for n in ('pathway_node_states.py','pathway_lp.py','pathway_hypotheses.py','contracts.py','science.py','runner.py')}}).encode()).hexdigest()
        if tool == 'regulon_activity':
            from .regulon_activity import verified_resources
            _, resources = verified_resources(self.root)
            return hashlib.sha256(dump({'tool':tool,'arguments':arguments,
                'sources':{aid:self.store.artifact(wid,aid)['sha256'] for aid in arguments['source_artifact_ids']},
                'resources':resources,
                'code':{name:hashlib.sha256((self.root/'evida'/name).read_bytes()).hexdigest()
                    for name in ('regulon_activity.py','regulon_activity.R','contracts.py','science.py','runner.py')},
                'runtime':self.fingerprint}).encode()).hexdigest()
        if tool == 'kinetic_conditions':
            return hashlib.sha256(dump({'tool': tool, 'arguments': arguments,
                'sources': {aid: self.store.artifact(wid, aid)['sha256'] for aid in arguments['source_artifact_ids']},
                'code': {name: hashlib.sha256((self.root/'evida'/name).read_bytes()).hexdigest()
                         for name in ('kinetic_conditions.py','exposure_requirements.py','contracts.py','science.py','runner.py')},
                'runtime': self.fingerprint}).encode()).hexdigest()
        if tool == 'exposure_requirements':
            return hashlib.sha256(dump({'tool':tool,'arguments':arguments,
                'sources':{aid:self.store.artifact(wid,aid)['sha256'] for aid in arguments['source_artifact_ids']},
                'code':{name:hashlib.sha256((self.root/'evida'/name).read_bytes()).hexdigest()
                        for name in ('exposure_requirements.py','contracts.py','science.py','runner.py')},
                'runtime':self.fingerprint}).encode()).hexdigest()
        if tool == 'binding_pose_review':
            from .resource_integrity import verify_file
            config = json.loads((self.root/'configs/binding-resources.json').read_text())
            if arguments['run_rescoring']:
                verify_file(Path(config['gnina']['binary']), config['gnina']['sha256'])
            # The CCD is fetched from the primary source during this review.
            # Preserve its receipt; do not silently reuse a previous online response.
            return None
        if tool == 'rna_allele_scenario':
            catalog = self.store.artifact(wid, arguments['catalog_id'])
            ids = [arguments['artifact_id'], arguments['catalog_id'], json.loads(catalog['content'])['reference_artifact_id']]
            return hashlib.sha256(dump({'tool':tool,'arguments':arguments,
                'inputs':[{"id":aid,"sha256":self.store.artifact(wid,aid)['sha256']} for aid in ids],
                'code':{name:hashlib.sha256((self.root/'evida'/name).read_bytes()).hexdigest()
                        for name in ('rna_alleles.py','rna_context.py','rna_sequence.py','science.py','runner.py')},
                'runtime':self.fingerprint}).encode()).hexdigest()
        if tool in ('rna_candidate_space', 'rna_candidate_selection'):
            ids = ([*arguments['reference_ids'], *arguments['prior_candidate_artifact_ids']]
                   if tool == 'rna_candidate_space' else [arguments['artifact_id'], arguments['reference_id']])
            return hashlib.sha256(dump({'tool': tool, 'arguments': arguments,
                'inputs': [{'id': aid, 'sha256': self.store.artifact(wid, aid)['sha256']} for aid in ids],
                'code': {name: hashlib.sha256((self.root/'evida'/name).read_bytes()).hexdigest()
                         for name in ('rna_candidate_space.py', 'rna_sequence.py', 'science.py', 'runner.py')},
                'runtime': self.fingerprint}).encode()).hexdigest()
        if tool=='rna_reference_panel':
            ids=[arguments['artifact_id'],*arguments['reference_ids']]
            return hashlib.sha256(dump({'tool':tool,'arguments':arguments,
                'inputs':[{"id":aid,"sha256":self.store.artifact(wid,aid)['sha256']} for aid in ids],
                'code':{name:hashlib.sha256((self.root/'evida'/name).read_bytes()).hexdigest()
                        for name in ('rna_reference_panel.py','rna_sequence.py','science.py')},
                'runtime':self.fingerprint}).encode()).hexdigest()
        if tool=='compound_selection':
            source=self.store.artifact(wid,arguments['artifact_id'])
            return hashlib.sha256(dump({'tool':tool,'arguments':arguments,'source_sha256':source['sha256'],'source_meta':source['meta'],'runtime':self.fingerprint,
                'code':{n:hashlib.sha256((self.root/'evida'/n).read_bytes()).hexdigest() for n in ['compound_discovery.py','runner.py','science.py']}}).encode()).hexdigest()
        if tool == 'chemical_sirna_evidence':
            cfg=json.loads((self.root/'configs/rna-resources.json').read_text())['chemical_evidence']
            from .resource_integrity import verify_file
            verify_file(cfg['path'], cfg['sha256'])
            return hashlib.sha256(dump({'tool':tool,'arguments':arguments,'resource':cfg,
                'code':{n:hashlib.sha256((self.root/'evida'/n).read_bytes()).hexdigest()
                        for n in ('chemical_sirna.py','science.py','runner.py')}}).encode()).hexdigest()
        if tool == 'rna_author_mod':
            from .rna_author_mod import configuration
            cfg=configuration(verify=True)
            source=self.store.artifact(wid,arguments['artifact_id'])
            return hashlib.sha256(dump({'tool':tool,'arguments':arguments,'configuration':cfg,
                'source_sha256':source['sha256'],'source_attempt':source['meta'].get('attempt_id'),
                'code':{n:hashlib.sha256((self.root/'evida'/n).read_bytes()).hexdigest() for n in
                    ('rna_author_mod.py','rna_author_mod_worker.py','rna_author.py','rna_author_worker.py','science.py','runner.py')}}).encode()).hexdigest()
        if tool == 'rna_author_full':
            from .rna_author import configuration
            cfg=configuration(verify=True)
            return hashlib.sha256(dump({'tool':tool,'arguments':arguments,'configuration':cfg,
                'inputs':{k:self.store.artifact(wid,arguments[k])['sha256'] for k in ('artifact_id','reference_id')},
                'code':{n:hashlib.sha256((self.root/'evida'/n).read_bytes()).hexdigest() for n in
                    ('rna_author.py','rna_author_worker.py','rna_resources.py','science.py','runner.py')}}).encode()).hexdigest()
        if tool == 'rna_chemistry_evidence':
            return hashlib.sha256((self.root/'resources/rna-evidence/nair2017.json').read_bytes()+dump(arguments).encode()).hexdigest()
        if tool in ('rna_reference_archive','rna_reference_release','rna_transcriptome_search','rna_activity_score','rna_delivery_simulation','rna_seed_sites'):
            fields=[k for k in ('artifact_id','reference_id') if k in arguments]
            modules={'rna_reference_archive':['rna_resources.py'],'rna_reference_release':['rna_resources.py'],'rna_transcriptome_search':['rna_resources.py','rna_sequence.py'],
                     'rna_activity_score':['rna_activity.py','rna_activity_worker.py','rna_resources.py'], 'rna_delivery_simulation':['rna_delivery.py'],
                     'rna_seed_sites':['rna_seed_sites.py','rna_seed.py','rna_resources.py','vendor/seedmatchr/get_seed.R']}[tool]
            config=json.loads((self.root/'configs/rna-resources.json').read_text()) if tool!='rna_delivery_simulation' else None
            if config is not None:
                from .resource_integrity import verify_resources
                if tool == 'rna_reference_release':
                    from .rna_resources import selected_release_configuration
                    config = selected_release_configuration(config, arguments['release'])
                verify_resources(config, 'rna_reference_archive' if tool == 'rna_reference_release' else tool)
                modules = [*modules, 'resource_integrity.py']
            return hashlib.sha256(dump({'tool':tool,'arguments':arguments,'inputs':[{"sha256":self.store.artifact(wid,arguments[k])['sha256']} for k in fields],
                'runtime':self.fingerprint,'additional_runtime':(__import__('evida.rna_seed',fromlist=['runtime_fingerprint']).runtime_fingerprint() if tool=='rna_seed_sites' else None),'configuration':config,'modules':{m:hashlib.sha256((self.root/'evida'/m).read_bytes()).hexdigest() for m in modules},
                'worker':hashlib.sha256((self.root/'evida/science.py').read_bytes()).hexdigest()}).encode()).hexdigest()
        if tool in ('rna_duplex','rna_duplex_seed','rna_duplex_transcriptome','rna_region_annotation','rna_delivery_response'):
            cfg=json.loads((self.root/'configs/rna-resources.json').read_text())
            extra=[]
            if tool=='rna_duplex_seed':
                from .resource_integrity import verify_resources
                verify_resources(cfg,'rna_seed_sites')
                from .rna_seed import runtime_fingerprint
                extra.append(runtime_fingerprint())
            if tool=='rna_duplex_transcriptome':
                from .resource_integrity import verify_resources
                verify_resources(cfg,'rna_transcriptome_search')
            if tool=='rna_region_annotation':
                from .resource_integrity import verify_file
                verify_file(cfg['genomic_annotation']['path'],cfg['genomic_annotation']['sha256'])
            ids=[arguments['artifact_id']] if arguments.get('artifact_id') else []
            if tool=='rna_region_annotation':
                pool=json.loads(self.store.artifact(wid,arguments['artifact_id'])['content'])
                ids.extend(r['artifact_id'] for r in pool['reference_panel'])
            names=['rna_duplex.py','rna_regions.py','rna_delivery_response.py','rna_delivery.py',
                   'rna_seed_sites.py','rna_resources.py','resource_integrity.py','science.py','runner.py']
            return hashlib.sha256(dump({'tool':tool,'arguments':arguments,
                'sources':[{'id':aid,'sha256':self.store.artifact(wid,aid)['sha256']} for aid in ids],
                'configuration':cfg,'runtime':self.fingerprint,'extra_runtime':extra,
                'code':{n:hashlib.sha256((self.root/'evida'/n).read_bytes()).hexdigest() for n in names}}).encode()).hexdigest()
        if tool == 'pose_interactions':
            from .pose_interactions import prepare, cache_key
            return cache_key(self.root,prepare(self.store,wid,arguments),arguments)
        if tool in ('structure_pockets','protein_dynamics','trajectory_analysis'):
            from .protein_computation import cache_key
            return cache_key(self.root,self.store.artifact(wid,arguments['artifact_id']),arguments,tool)
        if tool == 'retrosynthesis':
            from .retrosynthesis import cache_key
            return cache_key(self.root,self.store.artifact(wid,arguments['artifact_id']),arguments)
        if tool in ('xtb_geometry','crest_conformers'):
            from .molecular_physics import cache_key
            return cache_key(self.root,self.store.artifact(wid,arguments['artifact_id']),arguments,tool)
        if tool in ('molecule_preparation','synthetic_complexity'):
            from .molecular_preparation import cache_key
            return cache_key(self.root,self.store.artifact(wid,arguments['artifact_id']),arguments,tool)
        if tool == 'rna_interactions':
            from .rna_interaction import cache_key
            return cache_key(self.root,self.store.artifact(wid,arguments['artifact_id']),self.store.artifact(wid,arguments['reference_id']),arguments)
        if tool == 'protonation_states':
            from .protonation import cache_key
            return cache_key(self.root, self.store.artifact(wid, arguments['artifact_id']), arguments)
        if tool in PUBLIC_LOOKUPS:
            return None  # Live public lookups are refreshed; old responses remain source artifacts.
        if tool in ('molecular_docking', 'rna_sequence_evaluation', 'rna_candidate_generation'):
            fields = ['artifact_id', 'structure_id'] if tool == 'molecular_docking' else ['artifact_id']
            module = 'binding.py' if tool == 'molecular_docking' else 'rna_sequence.py'
            return hashlib.sha256(dump({'tool': tool, 'arguments': arguments,
                'inputs': [{'sha256': self.store.artifact(wid, arguments[k])['sha256'], 'meta': self.store.artifact(wid, arguments[k])['meta']} for k in fields],
                'runtime': self.fingerprint, 'adapter': hashlib.sha256((self.root / 'evida' / module).read_bytes()).hexdigest(),
                'source_parser': hashlib.sha256((self.root / 'evida/science.py').read_bytes()).hexdigest(),
                **({'receptor_graph_adapter':{n:hashlib.sha256((self.root/'evida'/n).read_bytes()).hexdigest()for n in ('receptor_graph.py','receptor_graph_worker.py')}}if tool=='molecular_docking'else{})}).encode()).hexdigest()
        if tool == "rna_gene_review":
            inputs = [self.store.artifact(wid, aid) for aid in arguments["artifact_ids"]]
            return hashlib.sha256(dump({"tool": tool, "arguments": arguments,
                "inputs": [{"sha256": a["sha256"], "meta": a["meta"]} for a in inputs], "runtime": self.fingerprint,
                "adapter": hashlib.sha256((self.root / "evida/rna_analysis.py").read_bytes()).hexdigest()}).encode()).hexdigest()
        if tool == 'rna_seed_analysis':
            from .rna_seed import runtime_fingerprint
            inputs=[self.store.artifact(wid,arguments[k]) for k in ['artifact_id','reference_id','guide_id']]
            vendor=self.root/'evida/vendor/seedmatchr'
            return hashlib.sha256(dump({'tool':tool,'arguments':arguments,
                'inputs':[{'sha256':a['sha256'],'meta':a['meta']} for a in inputs],
                'runtime':runtime_fingerprint(),'adapter':hashlib.sha256((self.root/'evida/rna_seed.py').read_bytes()).hexdigest(),
                'observation_adapter':hashlib.sha256((self.root/'evida/science.py').read_bytes()).hexdigest(),
                'author_files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(vendor.glob('*.R'))}}).encode()).hexdigest()
        if tool == "rna_weighted_distribution":
            artifact = self.store.artifact(wid, arguments["artifact_id"])
            return hashlib.sha256(dump({"tool": tool, "arguments": arguments,
                "input_sha256": artifact["sha256"], "input_meta": artifact["meta"],
                "runtime": self.fingerprint,
                "adapter_sha256": hashlib.sha256((self.root / "evida/rna_distribution.py").read_bytes()).hexdigest(),
                "worker_sha256": hashlib.sha256((self.root / "evida/science.py").read_bytes()).hexdigest()}).encode()).hexdigest()
        artifact = self.store.artifact(wid, arguments["artifact_id"])
        key = {"tool": tool, "arguments": arguments, "input_sha256": artifact["sha256"],
               "input_meta": artifact["meta"], "runtime": self.fingerprint,
               "adapter_sha256": hashlib.sha256((self.root / "evida/science.py").read_bytes()).hexdigest()}
        return hashlib.sha256(dump(key).encode()).hexdigest()

    def qualification_source_pool(self, wid, source):
        """Follow only a saved, exact CSV-to-source binding inside this workspace."""
        meta = source['meta']
        if source['kind'] != 'molecule_csv' or not meta.get('source_pool_id'):
            return None, 'not_applicable'
        if not meta.get('source_pool_sha256'):
            return None, 'source_pool_sha_unrecorded'
        try:
            pool = self.store.artifact(wid, meta['source_pool_id'])
        except (KeyError, ValueError):
            return None, 'source_pool_unavailable'
        if pool['sha256'] != meta['source_pool_sha256']:
            return None, 'source_pool_sha_mismatch'
        if pool['kind'] not in ('compound_candidates', 'binding_measurements', 'literature_compounds'):
            return None, 'source_pool_kind_unresolved'
        return pool, 'exact_saved_source_pool'

    def run_tool_job(self, jid, bump):
        job = self.store.start_job(jid)
        if job is None:
            return None
        wid, tool, args = job["workspace"], job["kind"], dict(job["request"])
        amendment_id = args.pop('_observation_amendment_id', None) if tool == 'next_observation_selection' else None
        try:
            if tool == 'literature_compounds':
                from .source_candidates import validate_resolution_sources
                validate_resolution_sources(self.store, wid, args['source_artifact_ids'])
            next_observation_bundle = None
            next_observation_binding = None
            if tool == 'next_observation_selection':
                from .next_observation_binding import prepare, digest
                # Classification corrections can arrive after enqueue. Bind once at
                # execution, then use these exact bytes for both reuse and the worker.
                next_observation_bundle = prepare(self.store, wid, args, amendment_id=amendment_id, own_job=jid)
                execution_key = self._next_observation_cache_key(next_observation_bundle)
                next_observation_binding = {'queued_cache_key': job['cache_key'],
                    'execution_cache_key': execution_key,
                    'input_bundle_sha256': digest(next_observation_bundle),
                    'rebound_at_execution': execution_key != job['cache_key']}
                with self.store.connect(True) as db:
                    db.execute('UPDATE jobs SET cache_key=? WHERE id=?', (execution_key, jid))
                    self.store.event(db, wid, 'next_observation_input_bound',
                                     {'job_id': jid, **next_observation_binding})
                job['cache_key'] = execution_key
            if tool in ('pubmed_search','pubmed_abstracts'):
                from .ncbi_pubmed import guard_scope
                from .evidence_scope import view as source_scope
                guard_scope(source_scope(self.store.snapshot(wid)))
            if job["cache_key"]:
                old = self.store.reusable(wid, job["cache_key"])
                if old:
                    self.store.finish_job(jid, "reused", old["id"])
                    return old["id"]
            attempt = self.attempts_root / job["attempt"]
            attempt.mkdir(parents=True, exist_ok=False)
            inp = self.store.artifact(wid, args["artifact_id"]) if args.get("artifact_id") else None
            request = {"tool": tool, "arguments": args, "input_meta": inp["meta"] if inp else {},
                       "input_path": str(attempt / "input") if inp else None, "output_path": str(attempt / "result.json")}
            if tool == 'proposal_qualification':
                source=self.store.artifact(wid,args['source_artifact_id'])
                path=attempt/'qualification-source';path.write_bytes(source['content'])
                request.update(workspace=wid,qualification_source_path=str(path),qualification_source_sha256=source['sha256'],qualification_source_meta=source['meta'],qualification_proposal_sha256=inp['sha256'])
                pool, pool_status = self.qualification_source_pool(wid, source)
                request['qualification_source_pool_status'] = pool_status
                if pool:
                    pool_path = attempt / 'qualification-source-pool'
                    pool_path.write_bytes(pool['content'])
                    request['qualification_source_pool'] = {
                        'artifact_id': pool['id'], 'sha256': pool['sha256'],
                        'path': str(pool_path), 'meta': pool['meta']}
                if args.get('generation_contract_artifact_id'):
                    contract=self.store.artifact(wid,args['generation_contract_artifact_id'])
                    contract_path=attempt/'qualification-contract';contract_path.write_bytes(contract['content'])
                    request.update(qualification_contract_path=str(contract_path),qualification_contract_sha256=contract['sha256'])
            if tool == 'article':
                request['figure_cache_dir'] = str(self.root / '.figure-cache')
            if inp:
                (attempt / "input").write_bytes(inp["content"])
            if tool == 'reported_activity_comparison':
                from .reported_activity_comparison import prepare, digest
                bundle = prepare(self.store, wid, args)
                request['reported_activity_input'] = bundle
                request['reported_activity_input_sha256'] = digest(bundle)
            if tool in ('pubmed_search','pubmed_abstracts'):
                from .evidence_scope import view as source_scope
                request['pubmed_source_scope']=source_scope(self.store.snapshot(wid))
                request['pubmed_rate_lock']=str(self.attempts_root.parent/'ncbi-anonymous-rate.lock')
                if tool=='pubmed_abstracts':
                    from .ncbi_pubmed import prepare_abstracts
                    request['pubmed_search_binding']=prepare_abstracts(inp,args)
            if tool=='pocket_docking':
                from .pocket_docking import prepare
                request['pocket_docking_input']=prepare(self.store,wid,args)
            if tool == 'pose_interactions':
                from .pose_interactions import prepare
                request['pose_interaction_input']=prepare(self.store,wid,args)
            if tool in ('structure_pockets','protein_dynamics','trajectory_analysis'):
                from .protein_computation import prepare
                request['protein_computation_input'] = prepare(inp,args,tool)
            if tool == 'retrosynthesis':
                from .retrosynthesis import prepare
                request['retrosynthesis_input'] = prepare(inp,args)
            if tool in ('xtb_geometry','crest_conformers'):
                from .molecular_physics import prepare
                request['molecular_physics_input']=prepare(inp,args,tool)
            if tool in ('molecule_preparation','synthetic_complexity'):
                from .molecular_preparation import prepare
                request['molecular_preparation_input']=prepare(inp,args,tool)
            if tool == 'rna_interactions':
                from .rna_interaction import prepare
                reference=self.store.artifact(wid,args['reference_id'])
                request['intarna_input']=prepare(inp,reference,args)
                reference_path=attempt/'reference.json';reference_path.write_bytes(reference['content'])
                request['reference_path']=str(reference_path)
            if tool == 'protonation_states':
                from .protonation import prepare
                request['protonation_input'] = prepare(inp, args)
            if tool == 'source_document':
                request['source_sha256'] = inp['sha256']
            if tool == 'next_observation_selection':
                from .next_observation_binding import stage
                request['next_observation_input'] = stage(next_observation_bundle, attempt)
                request['next_observation_input_binding'] = next_observation_binding
            if tool in ('pathway_hypotheses', 'pathway_node_states'):
                request['input_sha256'] = inp['sha256']
            if tool == 'pathway_robustness':
                request['pathway_runs']=[]
                for i,aid in enumerate(args['artifact_ids']):
                    source=self.store.artifact(wid,aid)
                    path=attempt/f'pathway-run-{i}.json';path.write_bytes(source['content'])
                    request['pathway_runs'].append({'id':aid,'kind':source['kind'],'title':source['title'],
                        'sha256':source['sha256'],'meta':source['meta'],'path':str(path)})
            if tool=='rna_author_mod':
                from .rna_author_mod import stage_parent
                request['modification_transfer_path']=stage_parent(self.root,inp,args,attempt)
            # analogue_proposal names these optionally: a target with no retrieved binding records
            # still proposes, it just trains the activity model on ChEMBL alone.
            if tool in ('literature_compounds', 'exposure_requirements', 'kinetic_conditions',
                        'regulon_activity', 'analogue_proposal'):
                request['public_source_inputs']=[]
                for i,aid in enumerate(args.get('source_artifact_ids') or []):
                    source=self.store.artifact(wid,aid);path=attempt/f'public-source-{i}.json';path.write_bytes(source['content'])
                    request['public_source_inputs'].append({'artifact_id':aid,'sha256':source['sha256'],'kind':source['kind'],'path':str(path)})
            if tool == 'rna_allele_scenario':
                catalog = self.store.artifact(wid, args['catalog_id'])
                parent_id = json.loads(catalog['content'])['reference_artifact_id']
                parent = self.store.artifact(wid, parent_id)
                cp = attempt/'variant-catalog.json'; cp.write_bytes(catalog['content'])
                rp = attempt/'original-reference.json'; rp.write_bytes(parent['content'])
                request.update(catalog_path=str(cp), reference_path=str(rp))
            if tool in ('molecular_docking', 'binding_pose_review'):
                structure = self.store.artifact(wid, args['structure_id'])
                structure_path = attempt / 'structure.json'
                structure_path.write_bytes(structure['content'])
                request['structure_path'] = str(structure_path)
            if tool in ('rna_activity_score', 'rna_author_full', 'rna_candidate_selection'):
                reference=self.store.artifact(wid,args['reference_id'])
                reference_path=attempt/'reference.json';reference_path.write_bytes(reference['content'])
                request['reference_path']=str(reference_path)
            if tool in ('rna_reference_panel', 'rna_candidate_space', 'rna_region_annotation'):
                request['reference_inputs']=[]
                ids=([r['artifact_id'] for r in json.loads(inp['content'])['reference_panel']] if tool=='rna_region_annotation' else args['reference_ids'])
                for i,aid in enumerate(ids):
                    ref=self.store.artifact(wid,aid);path=attempt/f'reference-{i}.json'
                    path.write_bytes(ref['content'])
                    request['reference_inputs'].append({'artifact_id':aid,'sha256':ref['sha256'],'path':str(path)})
            if tool == 'rna_candidate_space':
                request['prior_candidate_inputs'] = []
                for i, aid in enumerate(args['prior_candidate_artifact_ids']):
                    old = self.store.artifact(wid, aid); path = attempt/f'prior-{i}.json'
                    path.write_bytes(old['content'])
                    request['prior_candidate_inputs'].append({'artifact_id': aid, 'sha256': old['sha256'], 'path': str(path)})
            if tool == "rna_gene_review":
                request["inputs"] = []
                for i, aid in enumerate(args["artifact_ids"]):
                    artifact = self.store.artifact(wid, aid)
                    path = attempt / f"input-{i}.json"
                    path.write_bytes(artifact["content"])
                    request["inputs"].append({"artifact_id": aid, "sha256": artifact["sha256"], "path": str(path)})
            if tool == 'rna_seed_analysis':
                request['input_meta']={**request['input_meta'],'actual_input_sha256':inp['sha256']}
                request['seed_inputs']={}
                for field in ['reference_id','guide_id']:
                    artifact=self.store.artifact(wid,args[field]);path=attempt/(field+'.json')
                    path.write_bytes(artifact['content'])
                    request['seed_inputs'][field]={'artifact_id':artifact['id'],'sha256':artifact['sha256'],'path':str(path)}
            (attempt / "request.json").write_text(dump(request))
            env = {"PATH": str(self.science_python.parent) + ":/usr/bin:/bin", "LANG": "C.UTF-8",
                   "PYTHONPATH": str(self.root), "CUDA_VISIBLE_DEVICES": "", "OMP_NUM_THREADS": "2",
                   "OPENBLAS_NUM_THREADS": "2", "MKL_NUM_THREADS": "2", "NUMEXPR_NUM_THREADS": "2",
                   "MPLCONFIGDIR": str(attempt / "matplotlib"), "XDG_CACHE_HOME": str(attempt / "cache")}
            if self.native_library_directory:
                env["LD_LIBRARY_PATH"] = self.native_library_directory
            # Serialize scientific processes to avoid competing for memory or CPU. Model waits do not hold this lock.
            with self.science_lock, (attempt / "worker.log").open("wb") as logfile:
                from .source_intake import WALL_SECONDS
                proc = subprocess.run([str(self.science_python), "-m", "evida.science", str(attempt / "request.json")],
                                      cwd=self.root, env=env, stdout=logfile, stderr=subprocess.STDOUT, check=False,
                                      **({'timeout': WALL_SECONDS} if tool == 'source_document' else {}))
            output = attempt / "result.json"
            if proc.returncode != 0 or not output.exists():
                raise RuntimeError(f"과학 도구 프로세스가 결과를 완료하지 못했습니다 (exit={proc.returncode}).")
            result = json.loads(output.read_text())
            status = result.get("status", "failed")
            result_bytes=output.read_bytes()
            if tool == 'public_lookup_bundle':
                from .public_lookup_bundle import retain_sources
                result = retain_sources(self,wid,job,result)
                result_bytes = dump(result).encode()
            if tool == 'rna_interactions':
                raw_csv=result.pop('raw_csv_text',None)
                if raw_csv is not None:
                    from .rna_interaction import digest
                    csv_bytes=raw_csv.encode()
                    if digest(csv_bytes)!=result['raw_csv_sha256']:
                        raise ValueError('Author CSV byte identity changed during retention.')
                    result['author_csv_artifact_id']=self.store.add_artifact(wid,'IntaRNA 원본 전체 열 · CSV','rna_interaction_csv',csv_bytes,
                        {'delimiter':';','encoding':'utf-8','source_mode':'IntaRNA_unmodified_sequence_proxy','original_sha256':result['raw_csv_sha256'],
                         'consumed_artifacts':[args['artifact_id'],args['reference_id']],'input_binding':result['source_binding'],'attempt_id':job['attempt']},'text/csv',bump=False)
                result_bytes=dump(result).encode()
            if tool in ('protonation_states','molecule_preparation'):
                from .protonation import state_csv
                csv_text, bindings, exclusions = state_csv(result)
                result['downstream_state_transfer'] = {'included_states': len(bindings),
                    'excluded_states': exclusions, 'excluded_count': len(exclusions),
                    'policy': 'RDKit parse and heavy-atom element counts must both be verified true; raw states retained.'}
                if bindings:
                    csv_id = self.store.add_artifact(wid, '전하상태 · 무결성 확인 구조', 'molecule_csv', csv_text.encode(),
                        {'id_column':'cid','smiles_column':'smiles','encoding':'utf-8','delimiter':',',
                         'source_mode':('author_protonation_enumeration' if tool=='protonation_states' else 'author_3d_state_preparation'),'source_pool_id':inp['id'],
                         'source_pool_sha256':inp['sha256'],'consumed_artifacts':[inp['id']],
                         'state_bindings':bindings,'parameters':result.get('parameters'),
                         'runtime_manifest_sha256':result.get('runtime_receipt',{}).get('manifest_sha256'),
                         'attempt_id':job['attempt'],'scientific_context_verified':False}, 'text/csv', bump=False)
                    result['molecule_csv_artifact_id'] = csv_id
                result_bytes = dump(result).encode()
            if tool=='compound_selection' and status=='succeeded':
                csv_id=self.store.add_artifact(wid,'발굴 후보 · 계산용 구조','molecule_csv',result['csv_text'].encode(),
                    {'id_column':'cid','smiles_column':'smiles','encoding':'utf-8','delimiter':',',
                     'source_mode':'source_backed_discovery','source_pool_id':inp['id'],'source_pool_sha256':inp['sha256'],
                     'consumed_artifacts':[inp['id']],'candidate_ids':result['candidate_ids'],
                     'selection_reason':result['selection_reason'],'based_rev':job['based_rev'],
                     'attempt_id':job['attempt'],'scientific_context_verified':False},'text/csv',bump=False)
                result['molecule_csv_artifact_id']=csv_id
                result_bytes=dump(result).encode()
            if tool=='analogue_proposal' and status=='succeeded' and result.get('csv_text'):
                # The proposals and the compounds they came from, in one CSV, so the docking that
                # judges them runs both under the same receptor preparation and the same seed.
                # Each proposal declares a list of comparators. Flatten those lists for the
                # candidate index; keep the full per-proposal mapping alongside it.
                parent_ids = sorted({parent for parents in result['proposal_parents'].values()
                                     for parent in parents})
                csv_id=self.store.add_artifact(wid,'제안 구조 · 부모 포함 계산용','molecule_csv',result['csv_text'].encode(),
                    {'id_column':'cid','smiles_column':'smiles','encoding':'utf-8','delimiter':',',
                     'source_mode':'recombination_of_retrieved_structures','source_pool_id':inp['id'],
                     'source_pool_sha256':inp['sha256'],'consumed_artifacts':[inp['id']],
                     'proposal_parents':result['proposal_parents'],
                     'proposal_heavy_atoms':result.get('heavy_atoms') or {},
                     'candidate_ids':[*result['proposal_parents'],*parent_ids],
                     'selection_reason':result.get('reason',''),'based_rev':job['based_rev'],
                     'attempt_id':job['attempt'],'scientific_context_verified':False},'text/csv',bump=False)
                result['molecule_csv_artifact_id']=csv_id
                result_bytes=dump(result).encode()
            if tool=='molecular_docking' and status in ('succeeded','partial') and (inp['meta'] or {}).get('proposal_parents'):
                from .proposal_docking import compare
                result['proposal_comparison']=compare(result,inp['meta']['proposal_parents'],
                                                     inp['meta'].get('proposal_heavy_atoms'))
                result_bytes=dump(result).encode()
            artifact_kind = {'pocket_docking':'molecular_docking','rna_candidate_selection':'rna_sequence_evaluation','rna_region_annotation':'rna_candidate_space','rna_reference_release':'rna_reference_archive'}.get(tool,tool)
            if tool == 'next_observation_selection':
                # Primary decision, bound review, prior results and all scientific sources.
                # The generic source-list fallback omits the primary when a list is present.
                args_for_consumption = request['next_observation_input']['consumed_artifacts']
            else:
                args_for_consumption = None
            aid = self.store.add_artifact(wid, TOOL_NAMES[tool], artifact_kind, result_bytes,
                {"result_status": status, "summary": result.get("summary"), "limits": result.get("limits", []),
                 "semantic_type": result.get("semantic_type"), "based_rev": job["based_rev"],
                 "consumed_artifacts": list(request['reported_activity_input']['source_hashes']) if tool == 'reported_activity_comparison' else (args_for_consumption if args_for_consumption is not None else list(dict.fromkeys([args['artifact_id'], *(args.get('source_artifact_ids') or [])])) if tool=='analogue_proposal' else [args['artifact_id'],args['source_artifact_id'],*([args['generation_contract_artifact_id']] if args.get('generation_contract_artifact_id') else []), *([request['qualification_source_pool']['artifact_id']] if request.get('qualification_source_pool') else [])] if tool=='proposal_qualification' else [args['artifact_id'],*[r['artifact_id'] for r in json.loads(inp['content'])['reference_panel']]] if tool=='rna_region_annotation' else [args['artifact_id'],args['catalog_id'],parent_id] if tool=='rna_allele_scenario' else [*args['reference_ids'], *args['prior_candidate_artifact_ids']] if tool=='rna_candidate_space' else [args['artifact_id'],args['reference_id']] if tool=='rna_candidate_selection' else [args['artifact_id'],*args['reference_ids']] if tool=='rna_reference_panel' else [args[k] for k in ['artifact_id','reference_id','guide_id']] if tool=='rna_seed_analysis' else [args['artifact_id'],args['reference_id']] if tool in ('rna_activity_score','rna_author_full','rna_interactions') else [args['artifact_id'], args['structure_id'],args['pocket_artifact_id']] if tool=='pocket_docking' else [args['artifact_id'], args['structure_id']] if tool in ('molecular_docking','binding_pose_review','pose_interactions') else args.get("source_artifact_ids",args.get("artifact_ids", [inp["id"]] if inp else []))), "attempt_id": job["attempt"],
                 "arguments": args, "runtime_fingerprint": self.fingerprint, "elapsed_seconds": result.get("elapsed_seconds"),
                 **({'next_observation_input_binding': next_observation_binding,
                     'consumed_source_messages': request['next_observation_input']['consumed_source_messages'],
                     **({'observation_amendment': result['observation_amendment']} if result.get('observation_amendment') else {})}
                    if tool == 'next_observation_selection' else {})},
                bump=bump)
            self.store.finish_job(jid, status, aid, result.get("error"))
            return aid
        except Exception as exc:
            self.store.finish_job(jid, "failed", error=f"{type(exc).__name__}: {str(exc)[:500]}")
            return None
        finally:
            from .interaction import dispatch_followthrough
            dispatch_followthrough(self,wid)

    def inspect(self, wid, aid, offset=0, limit=30, candidate_query=None, depict=False):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("자료 조회 범위가 올바르지 않습니다.")
        artifact = self.store.artifact(wid, aid)
        if artifact['kind'] == 'source_file':
            state = self.store.snapshot(wid)
            jobs = [j for j in state['jobs'] if j['kind'] == 'source_document' and j['request'].get('artifact_id') == aid]
            last = jobs[-1] if jobs else None
            documents = [a['id'] for a in state['artifacts'] if a['kind'] == 'source_document'
                         and aid in a['meta'].get('consumed_artifacts', [])]
            return {'artifact_id': aid, 'title': artifact['title'], 'kind': artifact['kind'], 'meta': artifact['meta'],
                    'result': {'semantic_type': 'source_preserved_original', 'origin': 'researcher_upload',
                               'source_artifact_id': aid, 'source_sha256': artifact['sha256'],
                               'filename': artifact['meta'].get('original_filename'),
                               'document_format': artifact['meta'].get('document_format'),
                               'supplied_metadata': artifact['meta'].get('supplied_metadata', {}),
                               'source_document_artifact_ids': documents,
                               'extraction_job': {k: last[k] for k in ('id', 'status', 'error', 'output_id')} if last else None,
                               'bytes': len(artifact['content']), 'scientific_context_verified': False,
                               'limits': ['연구자가 제공한 원본 파일입니다. 문자층 추출 결과에서 문단·페이지를 읽을 수 있습니다. 원본 보존은 읽기 완료나 과학적 검증이 아닙니다.']}}
        if artifact["kind"] == "molecule_csv":
            import csv
            import io
            from .science import molecule_rows
            header, rows = molecule_rows(artifact["content"], artifact["meta"])
            preamble = list(csv.reader(io.StringIO(artifact["content"].decode(artifact["meta"].get("encoding", "utf-8-sig"))),
                                      delimiter=artifact["meta"].get("delimiter", ",")))[:artifact["meta"].get("header_record", 0)]
            return {"artifact_id": aid, "title": artifact["title"], "kind": artifact["kind"], "meta": artifact["meta"],
                    "result": {"semantic_type": "source_table_values", "header": header, "preamble_records": preamble,
                               "rows": rows[offset:offset + limit], "total_rows": len(rows), "offset": offset,
                               "has_more": offset + limit < len(rows),
                               "limits": ["원 CSV 값을 읽은 결과입니다. 구조 유효성·효능·단위 해석을 검증한 결과가 아닙니다."]}}
        if artifact['media_type'] in ('image/png','image/jpeg','image/webp'):
            return {'artifact_id':aid,'title':artifact['title'],'kind':artifact['kind'],'meta':artifact['meta'],
                    'result':{'semantic_type':'preserved_original_image','visual_reading':False,
                              'limits':['원 이미지가 보존되어 화면에서 열 수 있습니다. 이 텍스트 조회는 그림 판독이 아닙니다. 검토 기록과 원 조건을 따로 확인하세요.']}}
        if artifact["media_type"] != "application/json":
            content = artifact["content"]
            if content[:2] == b"\x1f\x8b":
                import gzip
                import io
                with gzip.GzipFile(fileobj=io.BytesIO(content)) as stream:
                    content = stream.read(8001)
            return {"artifact_id": aid, "title": artifact["title"], "meta": artifact["meta"],
                    "preview": content[:8000].decode(artifact["meta"].get("encoding", "utf-8"), errors="replace"),
                    "preview_only": len(content) > 8000}
        value = json.loads(artifact["content"])
        if artifact['kind'] == 'proposal_qualification':
            # The complete lists remain downloadable; the reading pages actual rows.
            value.pop('connectivity_groups', None)
            value.pop('original_row_ids', None)
            value.pop('selected_row_keys', None)
        if isinstance(value, dict):
            value.pop('original_response_base64', None)
        if artifact['kind'] == 'article' and isinstance(value, dict):
            from .public_evidence import article_presentation
            value = article_presentation(value)
            if depict and value.get('pmc_id'):
                # Figure navigation covers the whole article even when text is paged.
                from .article_figures import index_for
                value['figures'] = index_for(value, value['pmc_id'], self.root / '.figure-cache')
        if artifact['kind'] == 'pathway_hypotheses' and isinstance(value, dict):
            from .calculation_sections import presentation
            value = presentation(value)
        if artifact['kind'] == 'pathway_node_states' and isinstance(value, dict):
            from .pathway_node_states import presentation
            value = presentation(value)
        rows = value.get("rows") if isinstance(value, dict) else None
        if candidate_query is not None:
            original_count = len(value['rows'])
            if artifact['kind'] == 'rna_candidate_space':
                from .rna_candidate_space import filtered_rows
                rows = filtered_rows(value, candidate_query)
            elif artifact['kind'] == 'rna_variant_catalog':
                from .rna_alleles import filtered_variants
                rows = filtered_variants(value, candidate_query)
            else:
                raise ValueError('이 자료는 후보/변이 목록 검색을 지원하지 않습니다.')
            value.update(candidate_query=candidate_query, retained_total_rows=original_count)
        if rows is not None:
            if artifact['kind'] == 'article':
                from .public_evidence import article_sections
                value['section_navigation'] = article_sections(rows)
            value = {**value, "rows": rows[offset:offset + limit], "total_rows": len(rows),
                     "offset": offset, "has_more": offset + limit < len(rows)}
            if artifact['kind'] in ('pubmed_search','pubmed_abstracts'):
                value.pop('native_responses',None)
                value['original_access']='Exact native EUtils bytes/SHA are retained in the downloadable artifact; current rows are search IDs or publication abstracts, not full text.'
            # Literature rows also appear inside the raw response; avoid unintentional double inclusion.
            if artifact['kind'] in ('binding_measurements', 'drug_label_search', 'drug_label', 'clinical_trial_search', 'clinical_trial', 'target_context'):
                if artifact['kind'] == 'clinical_trial' and depict:
                    # Keep the posted outcomes and adverse events, which the reader needs to judge
                    # the trial, before the raw response is dropped to avoid duplicating rows.
                    # This is read from the whole response rather than the paged rows, so it does
                    # not shrink with offset/limit: it is for the screen only. A model request
                    # asks for the rows it wants, and a trial with many posted outcomes would
                    # otherwise add hundreds of kilobytes to a context it never asked to spend.
                    from .clinical_sources import reported_results
                    derived = reported_results(value)
                    if derived is not None:
                        value['reported_results'] = derived
                value.pop('response', None)
                value.pop('original_xml', None)
                value.pop('original_response_base64', None)
                value['original_access'] = 'Native response bytes and hash are preserved in the downloadable artifact; presentation rows reference its fields.'
            # A candidate list without a picture of the structure is hard to read, but a drawing
            # is for a person: it must never enter a model request, where it would only consume
            # context. Only the browser view asks for it.
            if depict:
                from .structure_depiction import attach as attach_depictions
                value = attach_depictions(value, artifact['kind'], self.root / '.structure-cache',
                                          self.science_python, self.root)
            if artifact["kind"] == "literature":
                value.pop("response", None)
            if artifact["kind"] == "repository_document":
                value.pop("original_docx_base64", None)
                value.pop("original_file_base64", None)
                value.pop("metadata_response", None)
            if artifact["kind"] in ("article", "entity_search"):
                value.pop("original_xml", None)
                value.pop("response", None)
                value.pop("references", None)
            if artifact['kind'] in ('disease_targets', 'target_disease_evidence', 'chembl_search', 'bioactivities', 'intervention_direction_audit'):
                value.pop('response', None)
                value.pop('assay_response', None)
                value.pop('original_mechanism_response', None)
            if artifact['kind'] in ('target_structure', 'rna_reference', 'rna_reference_archive'):
                for key in ('original_cif', 'metadata_response', 'sequence_response', 'sequence_5to3'):
                    value.pop(key, None)
            if artifact['kind']=='structure_search':
                value.pop('response',None)
            if artifact['kind']=='literature_compounds':
                value.pop('lookups',None)
            if artifact['kind']=='compound_candidates':
                for key in ('original_activity_response','structure_response'):
                    value.pop(key,None)
            if artifact['kind'] == 'molecular_docking':
                value.pop('raw_output_files', None)
        if artifact['kind'] == 'rna_tissue_context':
            value.pop('original_responses', None)
        if artifact['kind'] == 'rna_allele_scenario':
            value['scenario'].pop('sequence_5to3', None)
        if artifact['kind']=='compound_selection':
            value.pop('csv_text',None)
        if artifact['kind'] == 'admet':
            from .prediction_bounds import review_prediction_bounds
            value['prediction_domain_check'] = review_prediction_bounds(value)
        if artifact['kind'] in ('public_web_search', 'public_research_page'):
            value.pop('original_response_base64', None)
            value.pop('original_rendered_html_base64', None)
            if isinstance(value.get('browser'), dict):
                value['browser'].pop('network_attempts', None)
            value['original_access'] = 'Original HTTP bytes, rendered DOM and hashes remain in the saved artifact. Only requested rows are delivered here.'
        if artifact['kind'] in ('structure_pockets','protein_dynamics'):
            for key in ('author_files','prepared_pdb','trajectory_files'):
                value.pop(key, None)
            value['original_access'] = 'Exact prepared coordinates, topology and trajectory or author pocket files remain in the downloadable artifact; trajectory analysis accepts this saved artifact directly.'
        return {"artifact_id": aid, "title": artifact["title"], "kind": artifact["kind"], "meta": artifact["meta"], "result": value}

    def calculation_section(self, wid, aid, section, offset=0, limit=30):
        artifact = self.store.artifact(wid, aid)
        if artifact['kind'] != 'pathway_hypotheses' or artifact['media_type'] != 'application/json':
            raise ValueError('보존된 경로 계산 결과의 표를 선택해 주세요.')
        from .calculation_sections import read
        value = read(json.loads(artifact['content']), section, offset, limit)
        return {'artifact_id': aid, 'source_sha256': artifact['sha256'], 'title': artifact['title'],
                'kind': artifact['kind'], 'meta': artifact['meta'], 'result': value}

    def frame(self, wid, based_rev, args, *, require_intent_review=False, expected_intent_snapshot=None):
        if not args["current_question"].strip():
            raise ValueError("현재 연구 질문이 비어 있습니다. 기존 의도·작업 분해를 유지하고, 실제 질문 또는 필요한 확인 내용을 표시하세요.")
        state = self.store.snapshot(wid)
        validate_hypotheses(args["hypotheses"], state)
        from .intent_dependencies import bind_frame, input_snapshot, transaction_state
        before = input_snapshot(state)['snapshot_sha256']
        if expected_intent_snapshot and before != expected_intent_snapshot:
            raise ValueError('질문을 구성하는 동안 의도 또는 게시 판단이 바뀌었습니다. 최신 입력을 검토하세요.')
        binding = bind_frame(self.store, wid, state, args, required=require_intent_review)
        with self.store.connect(True) as db:
            current = transaction_state(self.store, db, wid)
            if current['rev'] != based_rev or input_snapshot(current)['snapshot_sha256'] != before:
                raise ValueError('질문을 저장하기 전 연구 상태가 바뀌었습니다.')
            self.store.event(db, wid, "work_framed", {"based_rev": based_rev, **args,
                **({'intent_dependencies': binding} if binding is not None else {})})

    def focus_readings(self, wid, rev, jid, args):
        if len(args['reading_ids']) != len(set(args['reading_ids'])):
            raise ValueError('각 reading_id는 한 번씩 지정하세요.')
        state = self.store.snapshot(wid)
        frame = next((e['body'] for e in reversed(state['events'])
                      if e['kind'] == 'work_framed' and e['body']['based_rev'] == rev), None)
        if not frame:
            raise ValueError('현재 상태에서 먼저 frame_work로 질문을 표시하세요.')
        readings = {a['id']: a for a in state['artifacts'] if a['kind'] == 'tool_reading'
                    and a['meta'].get('function') != 'focus_readings'}
        if any(aid not in readings for aid in args['reading_ids']):
            raise ValueError('이 작업 공간의 실제 원문 전달본 reading_id만 선택할 수 있습니다.')
        body = {'based_rev': rev, 'job_id': jid, 'current_question': frame['current_question'],
                'reading_ids': args['reading_ids'], 'existing_reading_ids': list(readings)}
        with self.store.connect(True) as db:
            if db.execute('SELECT rev FROM workspaces WHERE id=?', (wid,)).fetchone()[0] != rev:
                raise ValueError('연구 조건이 변경되어 이전 질문의 자료 선택을 적용하지 않았습니다.')
            self.store.event(db, wid, 'reading_focus_set', body)
        return {'status': 'applied', 'current_question': frame['current_question'],
                'reading_ids': args['reading_ids'], 'originals_and_history_preserved': True,
                'new_views_retained': True}

    def read_view(self, wid, name, args):
        if name == 'read_reasoning_principle':
            from .reasoning_perspectives import read_detail
            state = self.store.snapshot(wid); scope = state.get('evidence_scope') or {}
            protocols = [a for a in state['artifacts'] if a['kind']=='protocol_snapshot']
            if not protocols:
                raise ValueError('먼저 추론 관점이 전달된 실행을 시작해 주세요.')
            if protocols:
                protocol = json.loads(self.store.artifact(wid, protocols[-1]['id'])['content'])
                delivered = protocol.get('reasoning_core') or {}
                if args['principle_id'] not in {p['id'] for p in delivered.get('perspectives', [])}:
                    raise ValueError('이 실행에 전달된 추론 관점만 읽을 수 있습니다.')
                actual_hash = hashlib.sha256((self.root/'evida/reasoning_perspectives.json').read_bytes()).hexdigest()
                if delivered.get('perspective_catalog_sha256') != actual_hash:
                    raise ValueError('실행 당시 추론 원리 버전과 현재 파일이 다릅니다. 원 실행 기록을 보존하세요.')
                for path in ('evida/reasoning_principle_details.json', 'evida/reasoning_corpus_coverage.json'):
                    if protocol.get('code_sha256', {}).get(path) != hashlib.sha256((self.root/path).read_bytes()).hexdigest():
                        raise ValueError('실행 당시 추론 상세·사례 버전과 현재 파일이 다릅니다. 원 실행 기록을 보존하세요.')
            excluded = set()
            for job in state.get('jobs', []):
                request = job.get('request') or {}
                if isinstance(request, str): request = json.loads(request)
                excluded.update(request.get('reasoning_excluded_cases', []))
            result = read_detail(args['principle_id'], args['section'], args['offset'], args['limit'],
                excluded_cases=excluded, request_text=state.get('title',''),
                restricted=bool(scope.get('as_of') or scope.get('mode')=='supplied_only'))
            return {'kind':'reasoning_principle','title':'추론 관점과 원문 사례','result':result}
        if name == 'read_calculation_section':
            return self.calculation_section(wid, args['artifact_id'], args['section'], args['offset'], args['limit'])
        if name == 'inspect_hypothesis_history':
            from .evidence_history import view
            result = view(self.store, wid, args['hypothesis_id'], args['offset'], args['limit'])
            return {'artifact_id': result['current_decision_id'], 'kind': 'hypothesis_evidence_history',
                    'title': '가설의 이전 근거와 적용 조건', 'result': result}
        if name == 'inspect_article_references':
            from .article_references import reference_view
            artifact=self.store.artifact(wid,args['artifact_id'])
            if artifact['kind']!='article':raise ValueError('보존한 공개 원문을 선택해 주세요.')
            value=reference_view(json.loads(artifact['content']),args['reference_ids'],args['offset'],args['limit'])
            return {'artifact_id':artifact['id'],'source_sha256':artifact['sha256'],
                    'title':artifact['title'],'kind':'article','meta':artifact['meta'],'result':value}
        if name == 'read_evidence_bundle':
            from .evidence_bundle import execute
            return execute(self,wid,args)
        if name not in ('find_table_rows', 'find_table_columns'):
            view = self.inspect(wid, args['artifact_id'], args['offset'], args['limit'])
            return select_columns(view, args['columns']) if name == 'inspect_table_columns' else view
        artifact = self.store.artifact(wid, args['artifact_id'])
        if artifact['kind'] == 'molecule_csv':
            from .science import molecule_rows
            _, rows = molecule_rows(artifact['content'], artifact['meta'])
            value = self.inspect(wid, artifact['id'], 0, 1)['result']
        elif artifact['media_type'] == 'application/json':
            value = json.loads(artifact['content'])
            rows = value.get('rows') if isinstance(value, dict) else None
            if isinstance(rows, list):
                # Match against untouched rows, using the same envelope as
                # paged reads. Raw provider bodies must not silently reintroduce
                # every unselected row beside the requested selection.
                value = self.inspect(wid, artifact['id'], 0, 1)['result']
        else:
            raise ValueError('조회할 수 있는 표가 아닙니다.')
        selected = find_rows(rows, args['column_path'], args['values'], args['offset'], args['limit'])
        value = {**value, **selected}
        # The raw artifact and its original-file download stay unchanged.
        for key in ('original_file_base64', 'original_docx_base64', 'metadata_response',
                    'original_xml', 'response', 'references'):
            value.pop(key, None)
        if artifact['kind'] == 'admet':
            from .prediction_bounds import review_prediction_bounds
            value['prediction_domain_check'] = review_prediction_bounds(value)
        view = {'artifact_id': artifact['id'], 'title': artifact['title'], 'kind': artifact['kind'],
                'meta': artifact['meta'], 'result': value}
        if name == 'find_table_columns':
            # Always include the matched field so an exact selection is auditable.
            paths = list(args['columns'])
            if args['column_path'] not in paths:
                paths.insert(0, args['column_path'])
            return select_columns(view, paths)
        return view

    def check_readiness(self, wid, check):
        operation = check["operation"]
        if operation["kind"] != "tool":
            return {"executable": False, "reason": {"researcher_input": "연구자의 정보가 필요합니다.",
                    "external_observation": "새 관측을 받은 뒤 검토합니다.",
                    "unconnected_method": "방법의 입력·연결 확인이 필요합니다."}[operation["kind"]]}
        try:
            name, args = operation["name"], operation["arguments"]
            jsonschema.validate(args, FUNCTION_BY_NAME[name]["parameters"])
            if name == 'read_evidence_bundle':
                for item in args['reads']:
                    self.store.artifact(wid,item['arguments']['artifact_id'])
                    if not item['purpose'].strip():raise ValueError('함께 읽을 목적이 필요합니다.')
            elif name == 'read_reasoning_principle':
                self.read_view(wid, name, args)
            elif name in READING_FUNCTIONS:
                source = self.store.artifact(wid, args["artifact_id"])
                if name=='inspect_article_references' and source['kind']!='article':
                    raise ValueError('보존한 공개 원문을 선택해 주세요.')
                if name in ("inspect_table_columns", "find_table_rows", "find_table_columns") and source["kind"] != "molecule_csv" and (source["media_type"] != "application/json" or
                        not isinstance(json.loads(source["content"]).get("rows"), list)):
                    raise ValueError("열을 선택할 수 있는 JSON 표가 필요합니다.")
            else:
                self.validate_tool(wid, FUNCTION_TO_TOOL[name], args)
        except (ValueError, KeyError, jsonschema.ValidationError) as exc:
            return {"executable": False, "reason": str(exc)[:500]}
        return {"executable": True, "reason": "실행 후 결과를 반영해 판단을 검토합니다."}

    def start_check(self, wid, rev, source_decision, check_id):
        if type(rev) is not int or not isinstance(source_decision, str) or not isinstance(check_id, str):
            raise ValueError("다음 확인의 판단 ID와 버전이 필요합니다.")
        state = self.store.snapshot(wid)
        # A repeated request returns the existing job, even if its results changed the revision.
        old = next((r for r in state["research_checks"] if r["decision_id"] == source_decision and r["check_id"] == check_id), None)
        if old:
            return old["job_id"]
        check = active_check(state, check_id)
        if source_decision != decision_id(state):
            raise Conflict("현재 판단이 바뀌었습니다. 다음 확인을 다시 선택해 주세요.")
        readiness = self.check_readiness(wid, check)
        if not readiness["executable"]:
            raise ValueError(readiness["reason"])
        jid, created = self.store.claim_check(wid, rev, source_decision, check_id)
        if created:
            self.pool.submit(self.run_check, jid)
        return jid

    def run_check(self, jid):
        job = self.store.start_job(jid)
        if job is None:
            return
        wid, rev = job["workspace"], job["based_rev"]
        try:
            before = self.store.snapshot(wid)
            if before["rev"] != rev or decision_id(before) != job["request"]["decision_id"]:
                self.store.finish_job(jid, "stale", error="확인 시작 전에 연구 조건 또는 판단이 바뀌었습니다.")
                return
            check = job["request"]["check"]
            operation = check["operation"]
            name, args = operation["name"], operation["arguments"]
            if name in READING_FUNCTIONS:
                view = self.read_view(wid, name, args)
                status = view.get("status","succeeded")
                aid = self.store.add_artifact(wid, check["question"], "evidence_view", dump(view).encode(),
                    {"result_status": status, "consumed_artifacts": (list(dict.fromkeys(r["arguments"]["artifact_id"] for r in args["reads"])) if name=="read_evidence_bundle" else [args["artifact_id"]]),
                     "based_rev": rev, "check_id": check["id"], "scope": "requested view only; interpretation pending"})
            else:
                tool = FUNCTION_TO_TOOL[name]
                self.validate_tool(wid, tool, args)
                tid = self.store.enqueue(wid, rev, tool, args, self.cache_key(wid, tool, args))
                aid = self.run_tool_job(tid, True)
                status = next(j["status"] for j in self.store.snapshot(wid)["jobs"] if j["id"] == tid)
            self.store.finish_job(jid, status, aid)
            after = self.store.snapshot(wid)
            new_artifact = aid is not None and aid not in {a["id"] for a in before["artifacts"]}
            expected_rev = rev + int(new_artifact)
            # Do not restart a paid interpretation after a concurrent researcher change.
            if after["rev"] != expected_rev or decision_id(after) != job["request"]["decision_id"]:
                with self.store.connect(True) as db:
                    self.store.event(db, wid, "research_check_review_pending", {"job_id": jid, "reason": "실행 중 연구 맥락이 바뀌어 결과를 보존했습니다. 현재 조건에서 검토가 필요합니다."})
                return
            if self.gateway.status()["available"]:
                try:
                    from .provided_views import completed_check
                    review_arguments, delivery = completed_check(self, wid, aid)
                    with self.store.connect(True) as db:
                        self.store.event(db, wid, "research_check_result_delivery", {
                            "job_id": jid, "delivery": delivery})
                    review = self.start(wid, expected_rev, "planner", review_arguments)
                    self.store.link_check_review(jid, review)
                except (Conflict, GatewayError) as exc:
                    # Keep the completed tool's status when interpretation cannot start.
                    with self.store.connect(True) as db:
                        self.store.event(db, wid, "research_check_review_pending", {"job_id": jid, "reason": str(exc)[:500]})
            else:
                with self.store.connect(True) as db:
                    self.store.event(db, wid, "research_check_review_pending", {"job_id": jid, "reason": "도구 결과는 보존했습니다. 모델 연결 후 의미를 검토할 수 있습니다."})
        except Conflict as exc:
            self.store.finish_job(jid, "stale", error=str(exc)[:600])
        except Exception as exc:
            self.store.finish_job(jid, "failed", error=str(exc)[:600])
        finally:
            from .interaction import dispatch_followthrough
            dispatch_followthrough(self,wid)

    def model_context(self, wid, rev, framed, restore_reading=False, current_job=None, excluded_readings=(), force_full=False):
        state = self.store.snapshot(wid)
        reading_jobs = []
        cursor = current_job
        jobs = {j['id']: j for j in state['jobs']}
        while cursor and cursor not in reading_jobs:
            reading_jobs.append(cursor)
            cursor = jobs.get(cursor, {}).get('request', {}).get('resume_from_job')
        messages = [e for e in state["events"] if e["kind"] in ("message", "observation", "correction", "intent_edit")]
        evidence = [artifact_overview(self.store.artifact(wid, a["id"])) for a in state["artifacts"]
                    if a["kind"] not in ("model_receipt", "decision_proposal", "research_notes", "protocol_snapshot",
                        "explanation_context", "explanation_answer", "explanation_model_output", "explanation_reading",
                        "reassessment_delivery", "reassessment_draft", "reassessment_bundle",
                        "measurement_selection_plan", "measurement_selection_evaluation")]
        notes = next((self.store.artifact(wid, a["id"]) for a in reversed(state["artifacts"])
                      if a["kind"] == "research_notes"), None)
        findings = {}
        for entry in state["artifacts"]:
            if entry["kind"] == "research_notes":
                prior = json.loads(self.store.artifact(wid, entry["id"])["content"])
                for finding in prior["findings"]:
                    findings[dump(finding)] = {**finding, "note_id": entry["id"], "noted_at": entry["created"]}
        frame = next((e["body"] for e in reversed(state["events"]) if e["kind"] == "work_framed" and e["body"]["based_rev"] == rev), None)
        if frame is None:
            # Every command raises rev, including a continuation that says only "carry on", so a
            # rev-bound frame vanished on each continuation and every new job reframed from
            # scratch - one live case framed five times and never reached a review. The latest
            # decomposition is carried forward, marked with the conditions it was made under;
            # the model keeps it when the new input does not change the question and reframes
            # when it does.
            earlier = next((e["body"] for e in reversed(state["events"]) if e["kind"] == "work_framed"), None)
            if earlier is not None:
                frame = {**earlier, "carried_from_rev": earlier["based_rev"], "current_rev": rev}
        previous_reading = next((a for a in reversed(state["artifacts"]) if a["kind"] == "tool_reading"), None) if restore_reading else None
        focus = reading_focus(state['events'], rev, reading_jobs)
        from .judgment_context import view as context_view
        from .hypothesis_review import view as hypothesis_review_view
        from .discovery import overview as discovery_overview
        from .intent_dependencies import model_view as intent_dependency_view
        from .check_subject_binding import view as subject_view
        context = {"CHECK_SUBJECT_BINDINGS":subject_view(self.store,wid),"DISCOVERY_OPTIONS":discovery_overview(self.store,wid,state),"JUDGMENT_CONTEXT":context_view(self.store,wid,state),"STATE_REVISION": rev, "ORIGINAL_MESSAGES": messages, "CURRENT_INTENT": state["intent"],
                "INTENT_DEPENDENCIES": intent_dependency_view(self.store, wid, state),
                "HYPOTHESIS_REVIEW": hypothesis_review_view(self.store,wid,state),
                "PREVIOUS_DECISION": state["decision"], "RELEVANT_EVIDENCE": evidence,
                "INPUT_CHANGES": state["input_changes"],
                "DECISION_HISTORY": decision_history(state["events"], lambda aid: self.store.artifact(wid, aid)),
                "HYPOTHESIS_WORDING_HISTORY": [e['body'] for e in state['events']
                    if e['kind'] == 'hypothesis_wording_compared'],
                "REGISTERED_CAPABILITIES": CAPABILITIES, "EXISTING_WORK": state["jobs"],
                "RESEARCH_CHECK_RUNS": state["research_checks"], "WORK_ALREADY_FRAMED": framed,
                "CURRENT_FRAME": frame, "CURRENT_RESEARCH_NOTES": json.loads(notes["content"]) if notes else None,
                "PRIOR_NOTE_FINDINGS": list(findings.values()),
                "READING_FOCUS": {k: focus[k] for k in ('current_question', 'reading_ids')} if focus else None,
                "WORKING_READINGS": working_readings(state["artifacts"], reading_jobs, excluded_readings,
                    lambda aid: self.store.artifact(wid, aid), focus=focus),
                "COMPLETED_VIEWS": [{**a["meta"], "reading_id": a["id"], "sha256": a["sha256"], "title": a["title"]} for a in state["artifacts"] if a["kind"] == "tool_reading"],
                "RESTORED_READING": {"reading_id": previous_reading["id"], "meta": previous_reading["meta"],
                    "content": json.loads(self.store.artifact(wid, previous_reading["id"])["content"])} if previous_reading else None,
                "IMPORTANT": "응용프로그램이 구성한 현재 연구 상태다. ORIGINAL_MESSAGES가 연구자의 실제 요청이다. 자료 목록은 내용 열람이 아니며 연구 메모는 모델의 잠정 정리다. 원자료·과거 도구 전달본은 ID로 재조회할 수 있다. DECISION_HISTORY는 과거 게시 판단의 목록이며 최신 상태나 독립 과학 근거가 아니다. 가설 ID는 decision_id와 함께 구별하고 원 판단은 inspect_artifact로 읽는다."}

        context = apply_catalog_delivery(context)
        if getattr(self, 'response_limit', RESEARCH_ROUNDS) is None:
            monitor = next((a for a in reversed(state['artifacts'])
                            if a['kind'] == 'supervision_progress'), None)
            context['ORCHESTRATION_PROGRESS'] = {
                'response_limit': None,
                'latest_observation': json.loads(self.store.artifact(wid, monitor['id'])['content']) if monitor else None,
                'observation_based_rev': monitor['meta'].get('based_rev') if monitor else None,
                'decision_duty': 'Use the current researcher goal, framed question, actual tool returns, unresolved evidence and source conditions to choose the next action. Review repeated actions for new information; a changed explanation in research_notes alone does not make an identical query informative. A failed source is an access gap, not a biological negative. Use complementary available sources or identify the exact missing input/tool. Choose a final decision when the evidence supports a useful candidate/hypothesis and a discriminating next experiment with outcome-conditioned next steps; unresolved points remain explicit.'}
        explicit_specs = next((jobs[j]['request']['source_views'] for j in reading_jobs
            if j in jobs and 'source_views' in jobs[j]['request']), [])
        if explicit_specs:
            from .provided_views import build
            context['EXPLICIT_SOURCE_VIEWS'] = build(self, wid, explicit_specs)
        context['FINALIZATION'] = {
            'response_shape':'decision + discovery_review(nullable) + judgment_context(nullable) + hypothesis_review(required, schema_version=2) + intent_review(required)',
            'intent_review': {
                'uses':'Declare actual intent IDs and why they were used for current question (question/current_question), '
                    'recommendation (recommendation/recommendation), and each exact hypothesis/check ID. '
                    'For frame_work, only question/current_question is required. Empty intent_ids means unknown linkage, not independence. '
                    'IDs may refer to existing inputs or your explicit new/updated provisional intent_records in this frame/final. '
                    'Preserve protected researcher records and deleted IDs; keep inferred origins. '
                    'Server binds content, hashes and revision; do not supply invented hashes.',
                'reassessments':'Account for INTENT_DEPENDENCIES.required_reassessments in the final response. '
                    'For frame_work account only for question entries. Use changed, retained with a reason under the new conditions, '
                    'removed for an absent old item, or unknown. Retained/changed refer to exact consumer content, not scientific proof. '
                    'Unknown is valid and remains pending review. Do not change a question merely to satisfy the tracker.',
                'new_structure':'If final intent_records differ from the current frame/received structure, reassess question/current_question '
                    'and any prior consumers of changed IDs even if the incoming pending list was empty. '
                    'Use retained with a new-condition reason when the exact question still applies. '
                    'The server stores received input separately from model-authored structure; it does not confirm the latter as human input or science.',
                'question':'If question_reassessment_required is true, frame_work must reconsider the top question before further research. '
                    'No previous consumption record does not mean no impact. Preserve all original evidence and counterevidence.'},
            'hypothesis_review': {
                'responsibility':'Author the review in this same final response for the hypotheses and next checks you generate. '
                    'Account for every exact final ID in scope.hypotheses and scope.checks.',
                'coverage':'reviewed requires linked causal_steps/observations; not_reviewed or not_applicable requires an explicit '
                    'item-specific reason and remains visible as such. Empty scope is valid only when the decision has no items.',
                'unknowns':'Absent citations do not justify inventing evidence or omitting the item. Use empty anchors and unknown '
                    'assessments, preserve missing assumptions, and record unknown predictions explicitly.',
                'references':'Use an empty part_id for a whole hypothesis and exact declared IDs for named parts. '
                    'Anchor paths address the saved artifact, not a result wrapper in a tool view.',
                'causal_conditions':'Link each causal step to its own source conditions and measurement time. '
                    'Do not collapse measurements at different times into one observed causal sequence.',
                'meaning':'Authored review coverage is not independent scientific verification.'},
            'candidate_pool_retained':context['DISCOVERY_OPTIONS']['total'],
            'current_job_discovery_review':any(a['kind']=='discovery_review' and a['meta'].get('job_id')==current_job for a in state['artifacts']),
            'current_job_judgment_context':any(a['kind']=='judgment_context' and a['meta'].get('job_id')==current_job for a in state['artifacts']),
            'meaning':'The optional discovery/context records may be null; the hypothesis review must account for the final items. '
                'Use existing readings, preserve unknown conditions, and do not regenerate candidate pools or invent scientific judgments.'}
        requested = jobs.get(current_job, {}).get('request', {}).get('requested_check_operations')
        if requested:
            from .finalization import requested_operations
            context['REQUESTED_CHECK_OPERATIONS'] = {
                'by_check_id': requested_operations(state, requested),
                'meaning': 'Explicitly requested operation-type correction for existing checks. '
                    'Preserve the scientific question, evidence and outcome links. '
                    'A new measurement proposal is external_observation even when the laboratory work is external. '
                    'These routing instructions are not empirical observations.'}
        preservation = jobs.get(current_job, {}).get('request', {}).get('decision_preservation')
        if preservation is not None:
            from .decision_preservation import bind
            context['DECISION_PRESERVATION'] = bind(self.store, wid, preservation)
        from .reassessment import view as reassessment_view, delivery_manifest, _source_ids
        context['REASSESSMENT'] = reassessment_view(self.store, wid, job_id=current_job)
        context['REASSESSMENT']['instructions'] = (
            'Review the subjects needed for the current research action using actual source conditions. '
            'plan.required marks which judgments need review before they can be current; it is not a requirement '
            'to reassess every historical alternative before completing the current action. Keep out-of-scope '
            'historical content unchanged and omit its draft, or explicitly record unknown. Finalization preserves '
            'it as unknown/review_not_returned. It does not block the reviewed path or its useful next observation. '
            'Stage upstream hypotheses, then '
            'mechanism assessments, then linked candidates. Use record_reassessment_reviews, batching independent '
            'subjects at the same dependency layer; consume its returned '
            'draft before judging a dependent subject. Keep stable subject IDs. Retained requires a reason under '
            'current inputs; changed requires the exact new content; unknown remains a visible next-review obligation. '
            'Use research evidence/condition input IDs from this view and actual delivery IDs below. '
            'scope_complete refers to completion within your explicitly declared bounded review, not universal '
            'biological knowledge or experimental confirmation. Unmeasured conditions remain explicit in '
            'conditional claims. An unfinished review stays unknown until completed. '
            'Declared scope is your assertion, not proof of completeness. Preserve counterevidence and independent '
            'support paths. Source listing is not reading. Finish with reassessment_review_ids for the staged drafts '
            'you actually consumed and reproduce their exact content in the final hypothesis/discovery fields. '
            'Keep final intent records consistent with the reviewed frame. The final decision may still propose '
            'a useful observation while missing reassessments stay unknown.')
        recent = getattr(self, 'context_recent_views', None)
        context = apply_context_delivery(context, native_reading_ids=excluded_readings,
            recent_count=recent, force_full=force_full) if recent is not None else context
        from .goal_supervision import build as goal_supervision
        context['GOAL_SUPERVISION'] = goal_supervision(context)
        visible = delivery_manifest([{'role': 'user', 'content': model_json(context)}])
        context['DELIVERED_REASSESSMENT_VIEWS'] = [
            {'view_id': key, 'kind': item['kind'], 'sha256': item['sha256'],
             'source_ids': sorted(_source_ids(item['value']))} for key, item in visible['views'].items()]
        context['NATIVE_REASSESSMENT_VIEW_IDS'] = list(excluded_readings)
        context['MEASUREMENT_SELECTION_CONTRACT'] = (self.root / 'configs/measurement-selection.md').read_text()
        if state.get('evidence_scope'):
            context['EVIDENCE_SCOPE'] = {**state['evidence_scope'],
                'instruction': 'Use only supplied source documents and allowed computations in supplied_only mode. '
                    'Do not introduce biological claims from model memory as source-backed evidence. '
                    'Source dates are manually curated. Historical replay is not prospective discovery. '
                    'The researcher will supply any withheld outcome after the plan is frozen.'}
        return context

    def record_judgment_context(self,wid,rev,jid,args):
        from .judgment_context import validate
        state=self.store.snapshot(wid)
        if state['rev']!=rev:raise Conflict('조건이 변경되어 이전 문맥 제안을 게시하지 않았습니다.')
        frame=next((e['body'] for e in reversed(state['events']) if e['kind']=='work_framed' and e['body']['based_rev']==rev),None)
        if frame is None:raise ValueError('현재 질문의 가설을 먼저 frame_work로 정리해 주세요.')
        validate(args,state,frame['hypotheses'])
        previous=next((a['id'] for a in reversed(state['artifacts']) if a['kind']=='judgment_context'),None)
        aid=self.store.add_artifact(wid,'가설 조건·관측·재검토 경로','judgment_context',
            dump({'schema_version':'1','context':args,'hypothesis_wording':frame['hypotheses'],'supersedes':previous,
                  'semantic_type':'model_authored_context_and_review_links_not_scientific_validation'}).encode(),
            {'based_rev':rev,'job_id':jid,'supersedes':previous},bump=False)
        return {'status':'recorded','artifact_id':aid,'scientific_validation':False,'originals_preserved':True}

    @property
    def response_limit(self):
        setting = getattr(self, '_response_limit_setting', _DEFAULT_RESPONSE_LIMIT)
        return RESEARCH_ROUNDS if setting is _DEFAULT_RESPONSE_LIMIT else setting

    def record_notes(self, wid, rev, jid, notes, call_id=None):
        from .incremental_discovery import record_notes
        return record_notes(self.store, wid, rev, jid, notes, call_id=call_id)

    def planner_resume_input(self, job, resume):
        """Continue only an unchanged, framed request with its recorded failure hash."""
        state = self.store.snapshot(job['workspace'])
        source_id = job['request'].get('resume_from_job')
        source = next((j for j in state['jobs'] if j['id'] == source_id), None)
        if not source or source['kind'] != 'planner' or source['status'] not in ('failed','interrupted','paused','quota_or_rate_limit'):
            raise ValueError('중단된 원 판단 작업을 확인해야 합니다.')
        if source['based_rev'] != job['based_rev'] or state['rev'] != job['based_rev']:
            raise ValueError('중단 후 연구 조건이 바뀌었습니다. 현재 조건으로 새 판단이 필요합니다.')
        request = resume['request']
        digest = hashlib.sha256(dump(request).encode()).hexdigest()
        if digest != job['request'].get('resume_request_sha256'):
            raise ValueError('보존된 재개 요청의 해시가 다릅니다.')
        receipts = [json.loads(self.store.artifact(job['workspace'], a['id'])['content'])
                    for a in state['artifacts'] if a['kind'] == 'model_receipt' and a['meta'].get('job_id') == source_id]
        if not any(r.get('request_sha256') == digest and r.get('requested_model') == self.gateway.model
                   and r.get('requested_effort') == self.gateway.effort for r in receipts):
            raise ValueError('동일 모델·설정의 실제 실패 요청을 확인하지 못했습니다.')
        from .goal_completion import pending_from_request
        pending_goal = pending_from_request(request, self.prompt)
        if pending_goal is None and (request.get('instructions') not in (self.prompt, self.prompt + SYNTHESIS_SUFFIX) or request.get('tools') not in (model_functions(), model_functions(reasoning_core=True))):
            raise ValueError('판단 지시·도구 계약이 바뀌었습니다. 재개가 아닌 새 검토가 필요합니다.')
        if pending_goal is not None and (getattr(self, 'response_limit', RESEARCH_ROUNDS) is not None
                or decision_id(state) != pending_goal['decision_id']):
            raise ValueError('원래 무상한 목표 검토의 동일 게시 판단만 재개할 수 있습니다.')
        if not any(e['kind'] == 'work_framed' and e['body']['based_rev'] == job['based_rev'] for e in state['events']):
            raise ValueError('보존된 작업 분해를 확인하지 못했습니다.')
        rounds = completed_rounds(self.store, state, source_id)
        if source['status'] == 'quota_or_rate_limit':
            matching = [r for r in receipts if r.get('request_sha256') == digest]
            if not job['request'].get('manual_quota_continuation') or not any(
                    r.get('http_status') == 429 and r.get('status') == 'quota_or_rate_limit' for r in matching):
                raise ValueError('HTTP429의 명시적 재개 기록이 필요합니다.')
        original_budget = recorded_response_budget(self.store, state, source_id)
        if (getattr(self, 'response_limit', RESEARCH_ROUNDS) != original_budget
                or (original_budget is not None and rounds >= original_budget)
                or rounds != resume.get('completed_rounds', rounds)):
            raise ValueError('원래 응답 예산을 확인해야 합니다.')
        resume['completed_rounds'] = rounds
        return request['input']

    def run_planner(self, jid, resume=None):
        job = self.store.start_job(jid)
        if job is None:
            return
        wid, rev = job["workspace"], job["based_rev"]
        output_ids = []
        protocol_id = None
        preservation_failed = False
        pending_goal_review = None
        try:
            state = self.store.snapshot(wid)
            if state["rev"] != rev:
                self.store.finish_job(jid, "stale", error="시작 전 연구 조건이 바뀌었습니다. 최신 내용으로 실행해 주세요.")
                return
            from .finalization import requested_operations
            expected_operations = requested_operations(state, job['request'].get('requested_check_operations'))
            from .decision_preservation import bind
            decision_preservation = job['request'].get('decision_preservation')
            preservation_contract = bind(self.store, wid, decision_preservation)
            from .reasoning_core import context as reasoning_context_for, preserved_context
            if resume is not None:
                reasoning_context = preserved_context(resume['request'])
            else:
                request_text = '\n'.join([state.get('title', ''), *[
                    e['body'].get('text', '') for e in state['events'] if e['body'].get('text')]])
                reasoning_context = reasoning_context_for(request_text,
                    excluded_cases=job['request'].get('reasoning_excluded_cases', []),
                    evidence_scope=state.get('evidence_scope'))
            use_reasoning = reasoning_context is not None
            output_schema = model_final_decision(reasoning_core=use_reasoning)
            protocol = {"component": "structured_coordinator_hypothesis_and_review",
                "method_status": "current_baseline_not_specialist_generator",
                "independent_semantic_verification": False,
                "requested_model": self.gateway.model, "requested_effort": self.gateway.effort,
                "context_delivery": {"recent_views": getattr(self, "context_recent_views", None), "terminal_full_delivery": True},
                "transport_mode": self.gateway.status().get("transport_mode", "unspecified"),
                "resume_from_job": job['request'].get('resume_from_job'),
                "resume_request_sha256": job['request'].get('resume_request_sha256'),
                "resume_completed_rounds": job['request'].get('resume_completed_rounds'),
                "response_budget": checked_limit(getattr(self, "response_limit", RESEARCH_ROUNDS)),
                "response_limit_mode": "unbounded" if getattr(self, "response_limit", RESEARCH_ROUNDS) is None else "finite",
                "explicit_source_view_specs": job['request'].get('source_views', []),
                "requested_check_operations": expected_operations,
                "discovery_completion": "Optional typed review travels with final decision; unassessed pool retained. No forced late formatting call.",
                "context_completion": "Optional context sidecar shares final response and atomic publication; not a universal scientific gate.",
                "hypothesis_review_completion": "Required v2 review accounts for every final hypothesis/check; explicit unreviewed scope remains visible. No automatic scientific assessment.",
                "prompt": self.prompt, "prompt_sha256": hashlib.sha256(self.prompt.encode()).hexdigest(),
                "decision_schema": output_schema, "functions": model_functions(reasoning_core=use_reasoning),
                "code_sha256": {name: hashlib.sha256((self.root / name).read_bytes()).hexdigest()
                    for name in ("evida/runner.py", "evida/planner_recovery.py", "evida/gateway.py", "evida/contracts.py", "evida/research_loop.py", "evida/model_context.py", "evida/context_delivery.py", "evida/prediction_bounds.py", "evida/provided_views.py", "evida/finalization.py", "evida/hypothesis_review.py", "evida/hypothesis_reference_resolution.py", "evida/decision_preservation.py", "evida/intent_dependencies.py", "evida/reassessment.py", "evida/measurement_selection.py", "evida/measurement_selection_native.py", "configs/measurement-selection.md")},
                "meaning": "실제 실행에 사용한 지시·계약·코드 식별 기록. 과학적 타당성이나 독립 검증의 증거가 아니다."}
            protocol['code_sha256']['evida/goal_supervision.py'] = hashlib.sha256(
                (self.root / 'evida/goal_supervision.py').read_bytes()).hexdigest()
            protocol['code_sha256']['evida/next_check_guidance.py'] = hashlib.sha256(
                (self.root / 'evida/next_check_guidance.py').read_bytes()).hexdigest()
            protocol['reasoning_core'] = reasoning_context
            if getattr(self, 'response_limit', RESEARCH_ROUNDS) is None:
                protocol['goal_completion'] = {'version': 'goal-completion-v1',
                    'enabled': True, 'partial_publication_is_goal_completion': False,
                    'meaning': 'Same-route authored request-coverage review; no independent scientific validation.'}
                protocol['code_sha256']['evida/goal_completion.py'] = hashlib.sha256(
                    (self.root / 'evida/goal_completion.py').read_bytes()).hexdigest()
            for path in ('evida/reasoning_core.py', 'evida/reasoning_cards.json',
                         'evida/private_supervision.py',
                         'evida/reasoning_perspectives.py', 'evida/reasoning_perspectives.json',
                         'evida/reasoning_principle_details.json', 'evida/reasoning_corpus_coverage.json'):
                protocol['code_sha256'][path] = hashlib.sha256((self.root / path).read_bytes()).hexdigest()
            if preservation_contract is not None:
                protocol['decision_preservation'] = preservation_contract
            protocol_id = self.store.add_artifact(wid, "판단 생성 방식 · 실행 당시 설정", "protocol_snapshot",
                dump(protocol).encode(), {"based_rev": rev, "job_id": jid}, bump=False)
            if resume is not None:
                conversation = self.planner_resume_input(job, resume)
                framed = True
            else:
                # Reuse a bound question on continuation; missing consumption or
                # changed intent requires reconsideration, not a forced wording change.
                from .intent_dependencies import view as intent_dependency_view
                carried = (not job["request"].get("synthesis_only", False)
                           and not intent_dependency_view(self.store, wid)['question_reassessment_required'])
                context = self.model_context(wid, rev, carried, restore_reading=True, current_job=jid)
                conversation = [{"role": "user", "content": model_json(context)}]
                framed = carried
            first_round = resume['completed_rounds'] if resume is not None else 0
            corrections = 0
            transport_corrections = 0
            response_limit = checked_limit(getattr(self, "response_limit", RESEARCH_ROUNDS))
            action_monitor = ActionMonitor()
            from .goal_completion import pending_from_request
            pending_goal_review = pending_from_request(resume['request'], self.prompt) if resume else None
            for round_index in response_indices(first_round, response_limit, MAXIMUM_DECISION_CORRECTIONS):
                from .model_context import delivered_intent_snapshot
                expected_intent_snapshot = delivered_intent_snapshot(conversation)
                # An exact preserved old request keeps its old response contract.
                require_intent_review = resume is None or expected_intent_snapshot is not None
                if self.store.snapshot(wid)["rev"] != rev:
                    self.store.finish_job(jid, "stale", error="새 관측 또는 수정이 저장됐습니다. 이전 요청의 결과는 최신 판단을 바꾸지 않습니다.")
                    return
                control = response_state(round_index, response_limit, corrections,
                    synthesis_only=job["request"].get("synthesis_only", False), framed=framed,
                    correction_limit=MAXIMUM_DECISION_CORRECTIONS)
                correcting, synthesize = control["correcting"], control["synthesize"]
                if response_limit is None:
                    live_job = next((j for j in self.store.snapshot(wid).get('jobs', []) if j['id'] == jid), None)
                    if live_job is not None and live_job.get('status') not in ('running', 'queued'):
                        return  # Preserve an explicit cancellation/terminal record, do not overwrite it.
                instructions = self.prompt + (SYNTHESIS_SUFFIX if synthesize else "")
                available_functions = model_functions(reasoning_core=use_reasoning)
                if not framed:
                    available_functions = [f for f in available_functions if f['name']=='frame_work']
                choice = ('none' if synthesize else
                          {'type':'function','name':'frame_work'} if not framed else 'auto')
                # This statement describes this exact request. The framing call exposes
                # only frame_work; after framing the actual menu can change. Do not let
                # that earlier restriction stand in for the current tool contract.
                callable_names = [f['name'] for f in available_functions]
                if choice == 'none':
                    callable_names = []
                elif isinstance(choice, dict):
                    callable_names = [name for name in callable_names if name == choice.get('name')]
                call_context = {'CURRENT_CALL': {
                    'stage': ('decision_correction' if correcting else
                              'frame' if not framed else 'synthesis' if synthesize else 'research'),
                    'tool_choice': choice,
                    'callable_function_names': callable_names,
                    'model_response_number': round_index + 1,
                    'maximum_responses_remaining_including_current':
                        control["maximum_remaining"],
                    'research_responses_remaining_including_current':
                        control["research_remaining"],
                    'meaning': 'This is the current request, not a previous call. Only the listed '
                        'functions are callable now; their schemas supply the required arguments. '
                        'An earlier frame-only call does not limit a later research call. '
                        'An empty list means no tool calls are permitted in this response. '
                        'A response containing frame_work must contain only that one function call; '
                        'wait for the resulting current context before issuing research calls. '
                        'Availability does not establish data access, successful execution, or scientific validity. '
                        'Existing research scope and computation restrictions still apply.'}}
                if response_limit is None:
                    call_context['CURRENT_CALL']['unbounded_supervision'] = {
                        'response_limit': None, 'count_forced_synthesis': False,
                        'goal_reconsideration': 'Choose goal/question revision as an explicit model action when evidence warrants it; no iteration schedule.',
                        'termination': 'Publish useful conditional checkpoints, then review original-request coverage. Complete only when the requested proposal is sufficiently addressed or only essential researcher input remains; preserve goal revision/stale, explicit cancellation, provider refusal and real failure. No call-count deadline.'}
                if pending_goal_review is not None:
                    from .goal_completion import SCHEMA as goal_schema, GUIDANCE as goal_guidance, prompt as goal_prompt
                    available_functions, choice = [], 'none'
                    instructions = self.prompt + '\n\nCURRENT GOAL COVERAGE REVIEW:\n' + goal_guidance
                    call_context['CURRENT_CALL'].update(stage='goal_review', tool_choice='none',
                        callable_function_names=[],
                        goal_completion_review=goal_prompt(pending_goal_review['decision_id'])['goal_completion_review'])
                request_output_schema = goal_schema if pending_goal_review is not None else output_schema
                from .next_check_guidance import next_check_contract_hint
                if pending_goal_review is None:
                    call_context['CURRENT_CALL']['next_check_proposal_contract'] = next_check_contract_hint(output_schema)
                if reasoning_context is not None:
                    # A preserved request is replayed byte-for-byte on the first
                    # resume call. Subsequent v2 calls receive the same core with
                    # guidance for their actual stage, bound in the request receipt.
                    if not (resume is not None and round_index == first_round):
                        from .reasoning_perspectives import for_stage
                        reasoning_context = for_stage(reasoning_context, call_context['CURRENT_CALL']['stage'])
                    call_context['CURRENT_CALL']['reasoning_core'] = reasoning_context
                # Do not append to conversation: only one current-call statement travels
                # with each request. A preserved exact-request resume below stays exact.
                request_input = conversation + [{'role': 'user', 'content': model_json(call_context)}]
                payload = {"instructions": instructions, "input": request_input,
                    "tools": available_functions, "tool_choice": choice, "parallel_tool_calls": False,
                    "text": {"format": {"type": "json_schema", "name": "evida_goal_coverage_review" if pending_goal_review is not None else "evida_decision_bundle", "strict": True, "schema": request_output_schema}}}
                if resume is not None and round_index == first_round:
                    payload = resume['request']
                from .reassessment import delivery_manifest, record_delivery
                reassessment_received = delivery_manifest(payload['input'])
                if reassessment_received['snapshot_sha256']:
                    record_delivery(self.store, wid, jid, reassessment_received)
                else:
                    reassessment_received = None  # Exact historical replay has no new binding.
                chosen_model = job["request"].get("model")
                # A follow-up that carries no model stays on the route this research chose;
                # a preserved quota resume replays its own original route only.
                inherited_model = (self.workspace_model(wid)
                                   if chosen_model is None and "resume_from_job" not in job["request"] else None)
                result, receipt = self.gateway.request(payload, model=chosen_model or inherited_model)
                receipt_id = self.store.add_artifact(wid, f"모델 호출 {round_index + 1}", "model_receipt",
                    dump(receipt).encode(), {"based_rev": rev, "job_id": jid,
                                             "requested_model": receipt["requested_model"],
                                             "model_chosen_for_this_research": (chosen_model or inherited_model) is not None,
                                             "model_route": chosen_model or inherited_model,
                                             "protocol_id": protocol_id,
                                             "stage": call_context["CURRENT_CALL"]["stage"]}, bump=False)
                output_ids.append(receipt_id)
                # Store public outputs and encrypted continuation, never request headers or hidden reasoning text.
                public_output = [i for i in result.get("output", []) if i.get("type") != "reasoning"]
                self.store.add_artifact(wid, f"모델 제안 원응답 {round_index + 1}",
                    "goal_coverage_proposal" if pending_goal_review is not None else "decision_proposal",
                    dump({"output": public_output, "receipt_id": receipt_id}).encode(), {"based_rev": rev, "job_id": jid}, bump=False)
                if response_limit is None:
                    self.store.add_artifact(wid, "연구 진행 점검", "supervision_progress",
                        dump(action_monitor.observe(result)).encode(),
                        {"based_rev": rev, "job_id": jid, "response_limit": None}, bump=False)
                rejection = result.get('schema_rejection')
                if rejection is not None:
                    # A verified subscription response may fail its inner JSON
                    # contract before normal function dispatch. Keep the exact
                    # rejected output, execute none of it, and use the same
                    # bounded correction path as an ordinary invalid proposal.
                    self.store.add_artifact(wid, "모델 응답 형식 검사 · 실행하지 않음",
                        "model_output_validation_error", dump(rejection).encode(),
                        {"based_rev": rev, "job_id": jid, "receipt_id": receipt_id,
                         "protocol_id": protocol_id, "executed": False}, bump=False)
                    if response_limit is not None and transport_corrections >= MAXIMUM_DECISION_CORRECTIONS:
                        self.store.finish_job(jid, 'failed', error='모델 응답 형식 정정 상한에 도달했습니다. 원 응답과 결과를 보존했습니다.')
                        return
                    transport_corrections += 1
                    feedback = model_json({'status': 'invalid_input', 'executed': False,
                        'message': 'Returned inner JSON did not satisfy the supplied contract. '
                            'No proposed action ran. Correct the stated fields using the same evidence and schema.',
                        'validation': rejection})
                    rejected_calls = [{'type': 'function_call_output', 'call_id': item['call_id'],
                        'output': feedback} for item in public_output if item.get('type') == 'function_call']
                    conversation = next_model_context(self.model_context(wid, rev, framed,
                        restore_reading=True, current_job=jid), public_output, rejected_calls)
                    if not rejected_calls:
                        conversation.append({'role': 'user', 'content': feedback})
                        corrections += 1
                    continue
                if pending_goal_review is not None:
                    from .goal_completion import validate as validate_goal, delivery as core_delivery, continuation as goal_continuation, finish_current, rebind_resumed_checkpoint
                    from .reasoning_perspectives import allowed_ids
                    goal_text = ''.join(part.get('text', '') for item in public_output
                        for part in item.get('content', []) if part.get('type') == 'output_text')
                    try:
                        if any(item.get('type') == 'function_call' for item in public_output):
                            raise ValueError('Goal coverage review cannot execute functions; name remaining internal work instead.')
                        review = validate_goal(json.loads(goal_text),
                            decision_id=pending_goal_review['decision_id'],
                            known_artifacts={a['id'] for a in self.store.snapshot(wid)['artifacts']},
                            allowed_core_ids=allowed_ids(reasoning_context) if reasoning_context else set())
                    except (ValueError, jsonschema.ValidationError) as rejection:
                        correction = {'error_type': type(rejection).__name__, 'message': str(rejection),
                            'decision_id': pending_goal_review['decision_id'], 'executed': False}
                        self.store.add_artifact(wid, '원목표 검토 형식·참조 확인', 'goal_coverage_validation_error',
                            dump(correction).encode(), {'based_rev': rev, 'job_id': jid,
                                'receipt_id': receipt_id, 'protocol_id': protocol_id}, bump=False)
                        conversation = next_model_context(self.model_context(wid, rev, framed,
                            restore_reading=True, current_job=jid), public_output, []) + [
                            {'role': 'user', 'content': model_json({'GOAL_REVIEW_CORRECTION': correction})}]
                        continue
                    fresh = self.store.snapshot(wid)
                    live = next((j for j in fresh['jobs'] if j['id'] == jid), None)
                    applies = (fresh['rev'] == rev and decision_id(fresh) == pending_goal_review['decision_id']
                        and live is not None and live['status'] in ('queued', 'running'))
                    review_id = self.store.add_artifact(wid, '원목표 연결 검토', 'goal_coverage_review',
                        dump({'review': review, 'core_delivery': core_delivery(reasoning_context),
                            'independent_scientific_validation': False}).encode(),
                        {'based_rev': rev, 'job_id': jid, 'protocol_id': protocol_id,
                            'receipt_id': receipt_id, 'decision_id': pending_goal_review['decision_id'],
                            'goal_status': review['goal_status'], 'applies_to_current_snapshot': applies}, bump=False)
                    if not applies:
                        finish_current(self.store, wid, rev, jid, pending_goal_review['decision_id'],
                            review_id, require_current=False)
                        return
                    if review['goal_status'] != 'continue_internal_work':
                        current_aid = rebind_resumed_checkpoint(self.store, wid, rev, jid,
                            pending_goal_review['decision_id'], review_id, review['goal_status'])
                        if current_aid is None:
                            finish_current(self.store, wid, rev, jid, pending_goal_review['decision_id'], review_id, require_current=False)
                            return
                        if current_aid != pending_goal_review['decision_id']:
                            self.store.add_artifact(wid, '원목표 검토와 유지한 판단 연결', 'goal_coverage_binding',
                                dump({'goal_review_id': review_id, 'reviewed_decision_id': pending_goal_review['decision_id'],
                                    'current_decision_id': current_aid, 'science_content_unchanged': True}).encode(),
                                {'based_rev': rev, 'job_id': jid, 'decision_id': current_aid,
                                    'goal_status': review['goal_status'], 'goal_review_id': review_id}, bump=False)
                        finish_current(self.store, wid, rev, jid, current_aid, review_id)
                        return
                    conversation = next_model_context(self.model_context(wid, rev, framed,
                        restore_reading=True, current_job=jid), public_output, []) + [
                        {'role': 'user', 'content': model_json(goal_continuation(review,
                            pending_goal_review['decision_id'], review_id))}]
                    pending_goal_review = None
                    continue
                calls = [i for i in result.get("output", []) if i.get("type") == "function_call"]
                if calls and correcting:
                    # Every correction uses the saved reading, including an early
                    # rejected decision. Preserve its response without executing new tools.
                    self.store.finish_job(jid, "paused", error=(
                        "판단 정정 단계에서 새 조회를 "
                        "시도했습니다. 지금까지의 결과를 보존했습니다. 이어서 실행할 수 있습니다."))
                    return
                if calls:
                    if len(calls) > 1 and any(c.get('name') == 'frame_work' for c in calls):
                        # No partial frame mutation and no silent loss of later calls.
                        # The model must receive the resulting frame context before
                        # authoring research under that newly structured intent.
                        rejected = [{'type': 'function_call_output', 'call_id': c['call_id'],
                            'output': model_json({'status': 'invalid_input',
                                'message': 'frame_work는 한 응답에 단독으로 호출하세요. 이 응답의 모든 호출은 실행하지 않았습니다. '
                                           '새 질문 문맥을 받은 뒤 다음 조회를 요청하세요.'})} for c in calls]
                        conversation = next_model_context(self.model_context(wid, rev, framed,
                            restore_reading=True, current_job=jid), result.get('output', []), rejected)
                        continue
                    tool_outputs = []
                    latest_readings = []
                    for call in calls:
                        args = {}
                        try:
                            name = call["name"]
                            if name not in FUNCTION_BY_NAME:
                                raise ValueError("등록된 함수만 실행할 수 있습니다.")
                            from .intent_dependencies import input_snapshot
                            if (expected_intent_snapshot and expected_intent_snapshot !=
                                    input_snapshot(self.store.snapshot(wid))['snapshot_sha256']):
                                self.store.finish_job(jid, 'stale', error='의도·질문 또는 같은 버전의 게시 판단이 바뀌었습니다. 원 응답은 보존했습니다.')
                                return
                            args = json.loads(call["arguments"])
                            if name != "frame_work":
                                self.record_notes(wid, rev, jid, args.pop("research_notes"), call_id=call["call_id"])
                            jsonschema.validate(args, FUNCTION_BY_NAME[name]["parameters"])
                            if name == "frame_work":
                                if reasoning_context is not None:
                                    from .reasoning_core import validate_hypothesis_designs
                                    from .reasoning_perspectives import allowed_ids, cards_required
                                    validate_hypothesis_designs(args['hypotheses'], required=True, allow_empty=True,
                                        allowed_cards=allowed_ids(reasoning_context),
                                        cards_required=cards_required(reasoning_context),
                                        source_ids={a['id'] for a in self.store.snapshot(wid)['artifacts']})
                                self.frame(wid, rev, args, require_intent_review=require_intent_review,
                                           expected_intent_snapshot=expected_intent_snapshot)
                                framed = True
                                answer = {"status": "displayed", "based_rev": rev}
                            elif not framed:
                                answer = {"status": "input_missing", "message": "먼저 frame_work로 의도와 조사 작업 분해를 표시하세요."}
                            elif name == 'inspect_discovery_options':
                                from .discovery import inspect as inspect_options
                                answer=inspect_options(self.store,wid,**args)
                            elif name == 'record_discovery_review':
                                from .discovery import record_review
                                answer=record_review(self.store,wid,rev,jid,args)
                            elif name == 'inspect_reassessment_plan':
                                from .reassessment import view as reassessment_view
                                answer = reassessment_view(self.store, wid, job_id=jid)
                            elif name == 'record_reassessment_reviews':
                                from .reassessment import record_review as record_reassessment
                                if reassessment_received is None:
                                    raise ValueError('이 요청에는 현재 재검토 입력 전달이 없습니다.')
                                batch = []
                                for review in args['reviews']:
                                    try:
                                        batch.append(record_reassessment(self.store, wid, rev, jid, review, reassessment_received))
                                    except (ValueError, KeyError, jsonschema.ValidationError) as exc:
                                        batch.append({'subject': review.get('subject'), 'status': 'invalid_input', 'message': str(exc)[:700]})
                                answer = {'kind': 'reassessment_draft_batch', 'results': batch,
                                          'published': False, 'retry_automatically': False,
                                          'validation_help': 'invalid_input identifies an argument validation error. '
                                              'No draft was saved for that item. Review the stated cause and revise '
                                              'the arguments within the authorized job; do not resubmit an identical '
                                              'failed item. Permission, provider and execution-policy refusals remain '
                                              'separate stop conditions.'}
                            elif name == 'record_source_candidates':
                                from .source_candidates import record
                                answer=record(self.store,wid,rev,jid,args)
                            elif name == 'freeze_measurement_selection':
                                from .measurement_selection_native import freeze
                                answer = freeze(self.store, wid, rev, jid, json.loads(args['spec_json']), reassessment_received)
                            elif name == 'evaluate_measurement_selection':
                                from .measurement_selection_native import evaluate
                                answer = evaluate(self.store, wid, rev, jid, args['plan_artifact_id'],
                                                  args['outcome_artifact_id'], reassessment_received)
                            elif name == 'record_judgment_context':
                                answer=self.record_judgment_context(wid,rev,jid,args)
                            elif name == 'focus_readings':
                                answer = self.focus_readings(wid, rev, jid, args)
                            elif name in READING_FUNCTIONS:
                                answer = self.read_view(wid, name, args)
                            else:
                                if self.store.snapshot(wid)["rev"] != rev:
                                    raise Conflict("연구 조건이 변경되어 이 작업을 시작하지 않았습니다.")
                                tool = FUNCTION_TO_TOOL[name]
                                self.validate_tool(wid, tool, args)
                                tid = self.store.enqueue(wid, rev, tool, args, self.cache_key(wid, tool, args))
                                aid = self.run_tool_job(tid, False)
                                answer = self.inspect(wid, aid, limit=12) if aid else {"status": "failed", "job_id": tid}
                        except (ValueError, KeyError, jsonschema.ValidationError) as exc:
                            answer = {"status": "invalid_input", "message": str(exc)[:700]}
                            if getattr(exc, 'source_binding_errors', None):
                                answer['source_binding_errors'] = exc.source_binding_errors
                        if name not in ("frame_work", "focus_readings"):
                            reading_id = self.store.add_artifact(wid, "도구 전달본 · " + name, "tool_reading", dump(answer).encode(),
                                {"based_rev": rev, "job_id": jid, "call_id": call["call_id"], "function": name,
                                 "arguments": args, "source_artifact_id": answer.get("artifact_id"), "view_only": True,
                                 "source_artifact_ids": [r['source_artifact_id'] for r in answer.get('rows',[]) if r.get('source_artifact_id')] if name=='read_evidence_bundle' else [],
                                 "delivery": {k: answer.get("result", {}).get(k) for k in
                                    ("status", "total_rows", "offset", "has_more", "selected_columns", "selection", "source_total_rows")},
                                 "preview_only": answer.get("preview_only", False)}, bump=False)
                            latest_readings.append(reading_id)
                        tool_outputs.append({"type": "function_call_output", "call_id": call["call_id"], "output": model_json(answer)})
                    restore = all(call["name"] == "frame_work" for call in calls)
                    conversation = next_model_context(self.model_context(wid, rev, framed, restore_reading=restore, current_job=jid, excluded_readings=latest_readings, force_full=(job["request"].get("synthesis_only", False) and framed) or (response_limit is not None and round_index + 1 == response_limit - 1)), result.get("output", []), tool_outputs)
                    continue
                text = "".join(p.get("text", "") for i in result.get("output", []) for p in i.get("content", [])
                               if p.get("type") == "output_text")
                from .finalization import finalize
                try:
                    aid, published = finalize(self.store, wid, rev, jid, json.loads(text), framed, output_ids, protocol_id,
                        expected_operations=expected_operations, decision_preservation=decision_preservation,
                        require_intent_review=require_intent_review, expected_intent_snapshot=expected_intent_snapshot,
                        reassessment_received=reassessment_received, reasoning_context=reasoning_context)
                except DecisionPreservationError as rejection:
                    # This is a scope conflict, not a formatting request. The
                    # original draft was retained by finalize; never stitch or
                    # automatically ask a model to rewrite it.
                    preservation_failed = True
                    self.store.finish_job(jid, 'failed', rejection.artifact_id, error=str(rejection))
                    return
                except (ValueError, jsonschema.ValidationError) as rejection:
                    if response_limit is not None and corrections >= MAXIMUM_DECISION_CORRECTIONS:
                        raise
                    corrections += 1
                    reason = (schema_feedback(rejection) if isinstance(rejection, jsonschema.ValidationError)
                              else correction_reason(rejection, draft=text, reasoning_context=reasoning_context))
                    # Artifact metadata is part of the model catalog. Keep the
                    # original long error in a retrievable body, not that catalog.
                    rejection_id = self.store.add_artifact(wid, "판단 구조·의미 검사 원문", "decision_validation_error",
                        dump({"error_type": type(rejection).__name__, "message": str(rejection)}).encode(),
                        {"based_rev": rev, "job_id": jid, "protocol_id": protocol_id}, bump=False)
                    # Preserved so the refused version is inspectable rather than only described.
                    self.store.add_artifact(wid, f"게시되지 않은 판단 {corrections}", "decision_proposal",
                        text.encode(), {"based_rev": rev, "job_id": jid, "published": False,
                                        "rejected_because": str(rejection)[:600],
                                        "rejection_artifact_id": rejection_id,
                                        "protocol_id": protocol_id}, bump=False)
                    repair = repair_instruction(rejection, response_limit,
                        synthesis_only=job["request"].get("synthesis_only", False))
                    conversation = next_model_context(
                        self.model_context(wid, rev, framed, restore_reading=False, current_job=jid, force_full=True),
                        result.get("output", []), []) + [
                        {"role": "user", "content": repair or DECISION_REJECTED.format(reason=reason)}]
                    continue
                if published and response_limit is None:
                    # Keep the exact checkpoint visible and historical. A separate same-route
                    # request review decides continuation; publication alone is not whole-goal completion.
                    pending_goal_review = {'decision_id': aid}
                    self.store.add_artifact(wid, '부분 판단 게시 · 원목표 연결 검토 중',
                        'goal_coverage_pending', dump({'decision_id': aid, 'status': 'goal_review_pending',
                            'meaning': 'Published conditional checkpoint; original request coverage is being reviewed.'}).encode(),
                        {'based_rev': rev, 'job_id': jid, 'decision_id': aid, 'goal_status': 'goal_review_pending'}, bump=False)
                    conversation = next_model_context(self.model_context(wid, rev, framed,
                        restore_reading=True, current_job=jid), result.get('output', []), [])
                    continue
                self.store.finish_job(jid, "succeeded" if published else "stale", aid)
                return
            self.store.finish_job(jid, "paused", error=f"{RESEARCH_ROUNDS}회 모델 왕복 결과를 보존했습니다. 추가 조사가 필요하면 이어서 실행할 수 있습니다.")
        except DecisionPreservationError as exc:
            preservation_failed = True
            self.store.finish_job(jid, 'failed', error=str(exc))
        except GatewayError as exc:
            if exc.receipt:
                self.store.add_artifact(wid, "모델 호출 상태", "model_receipt", dump(exc.receipt).encode(),
                                       {"based_rev": rev, "job_id": jid, "protocol_id": protocol_id}, bump=False)
            if getattr(self, 'response_limit', RESEARCH_ROUNDS) is None and pending_goal_review is not None:
                from .goal_completion import finish_error_if_live
                finish_error_if_live(self.store, wid, jid, exc.status, str(exc))
            else:
                self.store.finish_job(jid, exc.status, error=str(exc))
        except Exception as exc:
            if getattr(self, 'response_limit', RESEARCH_ROUNDS) is None and pending_goal_review is not None:
                from .goal_completion import finish_error_if_live
                finish_error_if_live(self.store, wid, jid, 'failed', f'{type(exc).__name__}: {str(exc)[:600]}')
            else:
                self.store.finish_job(jid, "failed", error=f"{type(exc).__name__}: {str(exc)[:600]}")
        finally:
            if preservation_failed:
                from .decision_preservation import hold_followthrough
                hold_followthrough(self.store,wid)
            else:
                from .interaction import dispatch_followthrough
                dispatch_followthrough(self,wid)
