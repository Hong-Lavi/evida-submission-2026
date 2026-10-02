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
from .planner_recovery import completed_rounds, prepare_quota_resume, SYNTHESIS_SUFFIX
from .context_delivery import apply_context_delivery
from .catalog_delivery import apply_catalog_delivery
from .model_context import artifact_overview, decision_history, find_rows, model_json, next_model_context, reading_focus, select_columns, working_readings
from .research_loop import active_check, decision_id, validate_hypotheses, validate_loop
from .store import Conflict, dump, now

FUNCTION_TO_TOOL = {"compare_rna_distributions": "rna_weighted_distribution", "compute_properties": "rdkit", "predict_admet": "admet", "review_rna": "rna_observations",
                    "lookup_target": "open_targets", "search_literature": "literature", "read_open_article": "article",
                    "find_entities": "entity_search", "inspect_rna_genes": "rna_gene_review",
                    "read_repository_document": "repository_document", "analyze_rna_seed": "rna_seed_analysis"}
READING_FUNCTIONS = ("inspect_hypothesis_history", "inspect_artifact", "inspect_table_columns", "find_table_rows", "find_table_columns", "read_evidence_bundle", "inspect_article_references", "read_calculation_section")
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
PUBLIC_LOOKUPS = {"rna_tissue_context", "rna_variant_catalog", "intervention_direction_audit","literature_compounds","structure_search","compound_candidates","literature", "open_targets", "entity_search", "article", "repository_document",
                  "disease_targets", "target_disease_evidence", "chembl_search", "bioactivities", "target_structure", "rna_reference"}
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
FUNCTION_TO_TOOL['propose_analogue_structures'] = 'analogue_proposal'
# A name is a live lookup of PubChem's record for a stored structure; refreshed, never cached.
PUBLIC_LOOKUPS.add('chemical_names')
FUNCTION_TO_TOOL['compare_kinetic_conditions'] = 'kinetic_conditions'
FUNCTION_TO_TOOL['infer_regulon_activity'] = 'regulon_activity'
FUNCTION_TO_TOOL['infer_pathway_hypotheses'] = 'pathway_hypotheses'



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
    def __init__(self, root, store, gateway, attempts_root=None):
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
            if set(arguments) - {"synthesis_only", "source_views", "model", "requested_check_operations", "decision_preservation"} or ("synthesis_only" in arguments and type(arguments["synthesis_only"]) is not bool):
                raise ValueError("판단 실행 옵션을 확인해 주세요.")
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
        self.pool.submit(self.run_tool_job, jid, True)
        return jid

    def resume_quota(self, wid, rev, source_id):
        if not self.gateway.status()["available"]:
            raise GatewayError("input_missing", self.gateway.status()["message"])
        prepared = prepare_quota_resume(self, wid, rev, source_id)
        jid = self.store.enqueue(wid, rev, "planner", prepared['arguments'])
        self.pool.submit(self.run_planner, jid, prepared)
        return jid

    def validate_tool(self, wid, tool, arguments):
        spec = next((s for s in CAPABILITIES if s["id"] == tool), None)
        if spec is None:
            raise ValueError("등록되지 않은 도구입니다.")
        name = next(n for n, t in FUNCTION_TO_TOOL.items() if t == tool)
        try:
            jsonschema.validate(arguments, FUNCTION_BY_NAME[name]["parameters"])
        except jsonschema.ValidationError as exc:
            raise ValueError("도구 입력 형식을 확인해 주세요: " + exc.message[:400]) from None
        if tool == 'pathway_hypotheses':
            from .pathway_hypotheses import prepare, verified_resources, load_prior
            source = self.store.artifact(wid, arguments['artifact_id'])
            cfg, _ = verified_resources(self.root)
            prepare(arguments, json.loads(source['content']), load_prior(cfg))
        if tool=='literature_compounds':
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
        elif tool == "rna_gene_review":
            if len(set(arguments["artifact_ids"])) != len(arguments["artifact_ids"]):
                raise ValueError("같은 RNA 자료를 중복 입력하지 마세요.")
            for aid in arguments["artifact_ids"]:
                if self.store.artifact(wid, aid)["kind"] != "rna_observations":
                    raise ValueError("RNA 관측 검토를 완료한 자료가 필요합니다.")

    def cache_key(self, wid, tool, arguments):
        if tool == 'pathway_hypotheses':
            from .pathway_hypotheses import verified_resources
            _, resources = verified_resources(self.root)
            return hashlib.sha256(dump({'tool':tool,'arguments':arguments,
                'source':self.store.artifact(wid,arguments['artifact_id'])['sha256'],
                'resources':resources,'runtime':self.fingerprint,
                'code':{n:hashlib.sha256((self.root/'evida'/n).read_bytes()).hexdigest()
                    for n in ('pathway_hypotheses.py','pathway_hypotheses.R','contracts.py','science.py','runner.py')}}).encode()).hexdigest()
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
        if tool in PUBLIC_LOOKUPS:
            return None  # Live public lookups are refreshed; old responses remain source artifacts.
        if tool in ('molecular_docking', 'rna_sequence_evaluation', 'rna_candidate_generation'):
            fields = ['artifact_id', 'structure_id'] if tool == 'molecular_docking' else ['artifact_id']
            module = 'binding.py' if tool == 'molecular_docking' else 'rna_sequence.py'
            return hashlib.sha256(dump({'tool': tool, 'arguments': arguments,
                'inputs': [{'sha256': self.store.artifact(wid, arguments[k])['sha256'], 'meta': self.store.artifact(wid, arguments[k])['meta']} for k in fields],
                'runtime': self.fingerprint, 'adapter': hashlib.sha256((self.root / 'evida' / module).read_bytes()).hexdigest(),
                'source_parser': hashlib.sha256((self.root / 'evida/science.py').read_bytes()).hexdigest()}).encode()).hexdigest()
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

    def run_tool_job(self, jid, bump):
        job = self.store.start_job(jid)
        if job is None:
            return None
        wid, tool, args = job["workspace"], job["kind"], job["request"]
        try:
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
            if tool == 'article':
                request['figure_cache_dir'] = str(self.root / '.figure-cache')
            if inp:
                (attempt / "input").write_bytes(inp["content"])
            if tool == 'pathway_hypotheses':
                request['input_sha256'] = inp['sha256']
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
                proc = subprocess.run([str(self.science_python), "-m", "evida.science", str(attempt / "request.json")],
                                      cwd=self.root, env=env, stdout=logfile, stderr=subprocess.STDOUT, check=False)
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
            artifact_kind = {'rna_candidate_selection':'rna_sequence_evaluation','rna_region_annotation':'rna_candidate_space','rna_reference_release':'rna_reference_archive'}.get(tool,tool)
            aid = self.store.add_artifact(wid, TOOL_NAMES[tool], artifact_kind, result_bytes,
                {"result_status": status, "summary": result.get("summary"), "limits": result.get("limits", []),
                 "semantic_type": result.get("semantic_type"), "based_rev": job["based_rev"],
                 "consumed_artifacts": ([args['artifact_id'],*[r['artifact_id'] for r in json.loads(inp['content'])['reference_panel']]] if tool=='rna_region_annotation' else [args['artifact_id'],args['catalog_id'],parent_id] if tool=='rna_allele_scenario' else [*args['reference_ids'], *args['prior_candidate_artifact_ids']] if tool=='rna_candidate_space' else [args['artifact_id'],args['reference_id']] if tool=='rna_candidate_selection' else [args['artifact_id'],*args['reference_ids']] if tool=='rna_reference_panel' else [args[k] for k in ['artifact_id','reference_id','guide_id']] if tool=='rna_seed_analysis' else [args['artifact_id'],args['reference_id']] if tool in ('rna_activity_score','rna_author_full') else [args['artifact_id'], args['structure_id']] if tool in ('molecular_docking','binding_pose_review') else args.get("source_artifact_ids",args.get("artifact_ids", [inp["id"]] if inp else []))), "attempt_id": job["attempt"],
                 "arguments": args, "runtime_fingerprint": self.fingerprint, "elapsed_seconds": result.get("elapsed_seconds")},
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
        return {"artifact_id": aid, "title": artifact["title"], "kind": artifact["kind"], "meta": artifact["meta"], "result": value}

    def calculation_section(self, wid, aid, section, offset=0, limit=30):
        artifact = self.store.artifact(wid, aid)
        if artifact['kind'] != 'pathway_hypotheses' or artifact['media_type'] != 'application/json':
            raise ValueError('보존된 경로 계산 결과의 표를 선택해 주세요.')
        from .calculation_sections import read
        value = read(json.loads(artifact['content']), section, offset, limit)
        return {'artifact_id': aid, 'source_sha256': artifact['sha256'], 'title': artifact['title'],
                'kind': artifact['kind'], 'meta': artifact['meta'], 'result': value}

    def frame(self, wid, based_rev, args):
        if not args["current_question"].strip():
            raise ValueError("현재 연구 질문이 비어 있습니다. 기존 의도·작업 분해를 유지하고, 실제 질문 또는 필요한 확인 내용을 표시하세요.")
        validate_hypotheses(args["hypotheses"], self.store.snapshot(wid))
        with self.store.connect(True) as db:
            self.store.event(db, wid, "work_framed", {"based_rev": based_rev, **args})

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
                        "explanation_context", "explanation_answer", "explanation_model_output", "explanation_reading")]
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
        from .discovery import overview as discovery_overview
        context = {"DISCOVERY_OPTIONS":discovery_overview(self.store,wid,state),"JUDGMENT_CONTEXT":context_view(self.store,wid,state),"STATE_REVISION": rev, "ORIGINAL_MESSAGES": messages, "CURRENT_INTENT": state["intent"],
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
        explicit_specs = next((jobs[j]['request']['source_views'] for j in reading_jobs
            if j in jobs and 'source_views' in jobs[j]['request']), [])
        if explicit_specs:
            from .provided_views import build
            context['EXPLICIT_SOURCE_VIEWS'] = build(self, wid, explicit_specs)
        context['FINALIZATION'] = {
            'response_shape':'decision + discovery_review(nullable) + judgment_context(nullable)',
            'candidate_pool_retained':context['DISCOVERY_OPTIONS']['total'],
            'current_job_discovery_review':any(a['kind']=='discovery_review' and a['meta'].get('job_id')==current_job for a in state['artifacts']),
            'current_job_judgment_context':any(a['kind']=='judgment_context' and a['meta'].get('job_id')==current_job for a in state['artifacts']),
            'meaning':'Use the final response to attach reasons/conditions already established. Null means no new record, not no alternatives. Do not regenerate whole candidate pools or turn unknown conditions into an extra research gate.'}
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
        recent = getattr(self, 'context_recent_views', None)
        return apply_context_delivery(context, native_reading_ids=excluded_readings,
            recent_count=recent, force_full=force_full) if recent is not None else context

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
        if request.get('instructions') not in (self.prompt, self.prompt + SYNTHESIS_SUFFIX) or request.get('tools') != model_functions():
            raise ValueError('판단 지시·도구 계약이 바뀌었습니다. 재개가 아닌 새 검토가 필요합니다.')
        if not any(e['kind'] == 'work_framed' and e['body']['based_rev'] == job['based_rev'] for e in state['events']):
            raise ValueError('보존된 작업 분해를 확인하지 못했습니다.')
        rounds = completed_rounds(self.store, state, source_id)
        if source['status'] == 'quota_or_rate_limit':
            matching = [r for r in receipts if r.get('request_sha256') == digest]
            if not job['request'].get('manual_quota_continuation') or not any(
                    r.get('http_status') == 429 and r.get('status') == 'quota_or_rate_limit' for r in matching):
                raise ValueError('HTTP429의 명시적 재개 기록이 필요합니다.')
        if rounds >= 16 or rounds != resume.get('completed_rounds', rounds):
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
            output_schema = model_final_decision()
            protocol = {"component": "structured_coordinator_hypothesis_and_review",
                "method_status": "current_baseline_not_specialist_generator",
                "independent_semantic_verification": False,
                "requested_model": self.gateway.model, "requested_effort": self.gateway.effort,
                "context_delivery": {"recent_views": getattr(self, "context_recent_views", None), "terminal_full_delivery": True},
                "transport_mode": self.gateway.status().get("transport_mode", "unspecified"),
                "resume_from_job": job['request'].get('resume_from_job'),
                "resume_request_sha256": job['request'].get('resume_request_sha256'),
                "resume_completed_rounds": job['request'].get('resume_completed_rounds'),
                "response_budget": 16,
                "explicit_source_view_specs": job['request'].get('source_views', []),
                "requested_check_operations": expected_operations,
                "discovery_completion": "Optional typed review travels with final decision; unassessed pool retained. No forced late formatting call.",
                "context_completion": "Optional context sidecar shares final response and atomic publication; not a universal scientific gate.",
                "prompt": self.prompt, "prompt_sha256": hashlib.sha256(self.prompt.encode()).hexdigest(),
                "decision_schema": output_schema, "functions": model_functions(),
                "code_sha256": {name: hashlib.sha256((self.root / name).read_bytes()).hexdigest()
                    for name in ("evida/runner.py", "evida/planner_recovery.py", "evida/gateway.py", "evida/contracts.py", "evida/research_loop.py", "evida/model_context.py", "evida/context_delivery.py", "evida/prediction_bounds.py", "evida/provided_views.py", "evida/finalization.py", "evida/decision_preservation.py")},
                "meaning": "실제 실행에 사용한 지시·계약·코드 식별 기록. 과학적 타당성이나 독립 검증의 증거가 아니다."}
            if preservation_contract is not None:
                protocol['decision_preservation'] = preservation_contract
            protocol_id = self.store.add_artifact(wid, "판단 생성 방식 · 실행 당시 설정", "protocol_snapshot",
                dump(protocol).encode(), {"based_rev": rev, "job_id": jid}, bump=False)
            if resume is not None:
                conversation = self.planner_resume_input(job, resume)
                framed = True
            else:
                # A decomposition made under earlier conditions still lets research tools run; the
                # model decides whether the new input changes the question. A synthesis-only job
                # keeps the old rule, so it cannot synthesise before any frame exists this job.
                carried = (not job["request"].get("synthesis_only", False)
                           and any(e["kind"] == "work_framed" for e in self.store.snapshot(wid)["events"]))
                context = self.model_context(wid, rev, carried, restore_reading=True, current_job=jid)
                conversation = [{"role": "user", "content": model_json(context)}]
                framed = carried
            first_round = resume['completed_rounds'] if resume is not None else 0
            corrections = 0
            for round_index in range(first_round, RESEARCH_ROUNDS + MAXIMUM_DECISION_CORRECTIONS):
                if self.store.snapshot(wid)["rev"] != rev:
                    self.store.finish_job(jid, "stale", error="새 관측 또는 수정이 저장됐습니다. 이전 요청의 결과는 최신 판단을 바꾸지 않습니다.")
                    return
                synthesize = (job["request"].get("synthesis_only", False) and framed) or round_index == 15
                instructions = self.prompt + (SYNTHESIS_SUFFIX if synthesize else "")
                available_functions = model_functions()
                if not framed:
                    available_functions = [f for f in available_functions if f['name']=='frame_work']
                choice = ({'type':'function','name':'frame_work'} if not framed else
                          'none' if synthesize else 'auto')
                # This statement describes this exact request. The framing call exposes
                # only frame_work; after framing the actual menu can change. Do not let
                # that earlier restriction stand in for the current tool contract.
                callable_names = [f['name'] for f in available_functions]
                if choice == 'none' or round_index >= RESEARCH_ROUNDS:
                    callable_names = []
                elif isinstance(choice, dict):
                    callable_names = [name for name in callable_names if name == choice.get('name')]
                call_context = {'CURRENT_CALL': {
                    'stage': ('decision_correction' if round_index >= RESEARCH_ROUNDS else
                              'frame' if not framed else 'synthesis' if synthesize else 'research'),
                    'tool_choice': choice,
                    'callable_function_names': callable_names,
                    'model_response_number': round_index + 1,
                    'maximum_responses_remaining_including_current':
                        RESEARCH_ROUNDS + MAXIMUM_DECISION_CORRECTIONS - round_index,
                    'research_responses_remaining_including_current':
                        0 if synthesize else max(0, RESEARCH_ROUNDS - round_index),
                    'meaning': 'This is the current request, not a previous call. Only the listed '
                        'functions are callable now; their schemas supply the required arguments. '
                        'An earlier frame-only call does not limit a later research call. '
                        'An empty list means no tool calls are permitted in this response. '
                        'Availability does not establish data access, successful execution, or scientific validity. '
                        'Existing research scope and computation restrictions still apply.'}}
                # Do not append to conversation: only one current-call statement travels
                # with each request. A preserved exact-request resume below stays exact.
                request_input = conversation + [{'role': 'user', 'content': model_json(call_context)}]
                payload = {"instructions": instructions, "input": request_input,
                    "tools": available_functions, "tool_choice": choice, "parallel_tool_calls": False,
                    "text": {"format": {"type": "json_schema", "name": "evida_decision_bundle", "strict": True, "schema": output_schema}}}
                if resume is not None and round_index == first_round:
                    payload = resume['request']
                chosen_model = job["request"].get("model")
                result, receipt = self.gateway.request(payload, model=chosen_model)
                receipt_id = self.store.add_artifact(wid, f"모델 호출 {round_index + 1}", "model_receipt",
                    dump(receipt).encode(), {"based_rev": rev, "job_id": jid,
                                             "requested_model": receipt["requested_model"],
                                             "model_chosen_for_this_research": chosen_model is not None,
                                             "protocol_id": protocol_id}, bump=False)
                output_ids.append(receipt_id)
                # Store public outputs and encrypted continuation, never request headers or hidden reasoning text.
                public_output = [i for i in result.get("output", []) if i.get("type") != "reasoning"]
                self.store.add_artifact(wid, f"모델 제안 원응답 {round_index + 1}", "decision_proposal",
                    dump({"output": public_output, "receipt_id": receipt_id}).encode(), {"based_rev": rev, "job_id": jid}, bump=False)
                calls = [i for i in result.get("output", []) if i.get("type") == "function_call"]
                if calls and round_index >= RESEARCH_ROUNDS:
                    # Past the research budget the model was asked to correct a decision, not to
                    # look something else up. Its reading is preserved and the job pauses.
                    self.store.finish_job(jid, "paused", error=(
                        f"{RESEARCH_ROUNDS}회 모델 왕복 뒤 판단 정정을 요청했으나 새 조회를 "
                        "시도했습니다. 지금까지의 결과를 보존했습니다. 이어서 실행할 수 있습니다."))
                    return
                if calls:
                    tool_outputs = []
                    latest_readings = []
                    for call in calls:
                        args = {}
                        try:
                            name = call["name"]
                            if name not in FUNCTION_BY_NAME:
                                raise ValueError("등록된 함수만 실행할 수 있습니다.")
                            args = json.loads(call["arguments"])
                            if name != "frame_work":
                                self.record_notes(wid, rev, jid, args.pop("research_notes"), call_id=call["call_id"])
                            jsonschema.validate(args, FUNCTION_BY_NAME[name]["parameters"])
                            if name == "frame_work":
                                self.frame(wid, rev, args)
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
                            elif name == 'record_source_candidates':
                                from .source_candidates import record
                                answer=record(self.store,wid,rev,jid,args)
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
                    conversation = next_model_context(self.model_context(wid, rev, framed, restore_reading=restore, current_job=jid, excluded_readings=latest_readings, force_full=(job["request"].get("synthesis_only", False) and framed) or round_index + 1 == 15), result.get("output", []), tool_outputs)
                    continue
                text = "".join(p.get("text", "") for i in result.get("output", []) for p in i.get("content", [])
                               if p.get("type") == "output_text")
                from .finalization import finalize
                try:
                    aid, published = finalize(self.store, wid, rev, jid, json.loads(text), framed, output_ids, protocol_id,
                        expected_operations=expected_operations, decision_preservation=decision_preservation)
                except DecisionPreservationError as rejection:
                    # This is a scope conflict, not a formatting request. The
                    # original draft was retained by finalize; never stitch or
                    # automatically ask a model to rewrite it.
                    preservation_failed = True
                    self.store.finish_job(jid, 'failed', rejection.artifact_id, error=str(rejection))
                    return
                except (ValueError, jsonschema.ValidationError) as rejection:
                    if corrections >= MAXIMUM_DECISION_CORRECTIONS:
                        raise
                    corrections += 1
                    # Preserved so the refused version is inspectable rather than only described.
                    self.store.add_artifact(wid, f"게시되지 않은 판단 {corrections}", "decision_proposal",
                        text.encode(), {"based_rev": rev, "job_id": jid, "published": False,
                                        "rejected_because": str(rejection)[:600],
                                        "protocol_id": protocol_id}, bump=False)
                    conversation = next_model_context(
                        self.model_context(wid, rev, framed, restore_reading=False, current_job=jid),
                        result.get("output", []), []) + [
                        {"role": "user", "content": DECISION_REJECTED.format(reason=str(rejection)[:400])}]
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
            self.store.finish_job(jid, exc.status, error=str(exc))
        except Exception as exc:
            self.store.finish_job(jid, "failed", error=f"{type(exc).__name__}: {str(exc)[:600]}")
        finally:
            if preservation_failed:
                from .decision_preservation import hold_followthrough
                hold_followthrough(self.store,wid)
            else:
                from .interaction import dispatch_followthrough
                dispatch_followthrough(self,wid)
