"""One valid first response, then remaining frozen jobs with concurrency two."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import dataclasses
import json
import os
from pathlib import Path
import threading
import time

import jsonschema
import run_component_assay as f
from lavi_research_os.rounds import isolate_from_orchestrator
from lavi_research_os.providers.codex import CodexSubscriptionAdapter
from lavi_research_os.providers.base import ProviderError
from lavi_research_os.providers.recording import provider_workspace
from lavi_research_os.c1.indexed_input import IndexedInputCodexAdapter, restore_indexed_input

ROOT = Path(__file__).resolve().parent
DEST = ROOT / 'attempt-03'


def main():
    protocol = json.loads((ROOT / 'component-protocol.json').read_text())
    amendment = json.loads((DEST / 'execution-amendment.json').read_text())
    for path, expected in {**protocol['frozen_files'], **amendment['new_packet_file_sha256']}.items():
        if f.sha(path) != expected:
            raise ValueError('Frozen input changed: ' + path)
    if f.sha(ROOT / 'component-protocol.json') != json.loads((ROOT / 'component-protocol-receipt.json').read_text())['sha256']:
        raise ValueError('Protocol changed')
    f.verify_runtime()
    # Preflight every packet and payload before even the first adapter call.
    for code in protocol['order']:
        out = DEST / 'component-calls' / code
        payload = json.loads((out / 'request.json').read_text())
        if restore_indexed_input(out / 'prepared-input') != payload:
            raise ValueError('Packet restoration failed')
        IndexedInputCodexAdapter(CodexSubscriptionAdapter(model='gpt-6-astra', reasoning_effort='max',
            timeout_seconds=1800, allow_web_search=False), out / 'prepared-input')
    removed = isolate_from_orchestrator()
    if any(os.environ.get(k) for k in ('EVIDA_COMPETITION_API_KEY', 'OPENAI_API_KEY', 'CODEX_API_KEY', 'ANTHROPIC_API_KEY')):
        raise ValueError('API environment forbidden')
    f.save(DEST / 'controlled-execution-receipt.json', {'at_utc': f.utc(),
        'driver_sha256': f.sha(__file__), 'protocol_sha256': f.sha(ROOT / 'component-protocol.json'),
        'execution_amendment_sha256': f.sha(DEST / 'execution-amendment.json'),
        'offline_preflight_packets': 18, 'first_job_then_concurrency': [1, 2],
        'root_instruction': 'Wait for first real response before remaining calls; stop any further setup failure; no science/input/model/budget changes.',
        'isolated_environment_names': removed, 'automatic_retry': False})
    stopped = threading.Event()
    def one(code):
        out = DEST / 'component-calls' / code
        receipt = {'blind_id': code, 'requested_model': 'gpt-6-astra', 'requested_effort': 'max',
                   'provider_attempts': 0, 'at_utc': f.utc(), 'request_sha256': f.sha(out / 'request.json')}
        if stopped.is_set():
            receipt['status'] = 'NOT_ATTEMPTED_AFTER_FAILURE'
            f.save(out / 'receipt.json', receipt); return receipt
        payload = json.loads((out / 'request.json').read_text()); began = time.monotonic()
        try:
            adapter = IndexedInputCodexAdapter(CodexSubscriptionAdapter(model='gpt-6-astra', reasoning_effort='max',
                timeout_seconds=1800, allow_web_search=False), out / 'prepared-input')
            receipt['provider_attempts'] = 1
            with provider_workspace(out / 'provider') as workspace:
                response = adapter.complete_json(task=f.TASK, payload=payload, schema=f.ENVELOPE, workspace=Path(workspace))
            f.save(out / 'provider-response.json', dataclasses.asdict(response))
            receipt.update(actual_model=response.actual_model, identity_source=response.identity_source,
                           identity_observation=response.identity_observation, quality_flags=list(response.quality_flags))
            if response.actual_model != 'gpt-6-astra' or 'PROVIDER_EXECUTION_DEGRADED' in response.quality_flags:
                raise ValueError('Actual identity/degraded execution rejected')
            answer = response.payload['answer']; (out / 'answer.txt').write_text(answer)
            receipt['schema_status'] = 'not_applicable_prose'
            if payload['response_contract'] is not None:
                try:
                    parsed = json.loads(answer); jsonschema.validate(parsed, payload['response_contract'])
                    f.save(out / 'parsed-scientific-records.json', parsed); receipt['schema_status'] = 'valid'
                except (ValueError, jsonschema.ValidationError) as error:
                    receipt.update(schema_status='invalid', schema_error_type=type(error).__name__)
            receipt['status'] = 'COMPLETED'
            blind = DEST / 'blind-review' / code
            f.save(blind / 'visible-case.json', {'scientific_request': f.QUESTION, 'case': payload['case'],
                                               'source_sha256': payload['source_identity']['sha256_of_original_bytes']})
            (blind / 'answer.txt').write_text(answer)
        except Exception as error:
            receipt.update(status='FAILED', error_type=type(error).__name__)
            stopped.set()  # Stop queue after ANY setup/provider error, not only auth/quota.
            if isinstance(error, ProviderError):
                receipt['provider_failure'] = {'reason': error.reason.value, 'actual_model': error.actual_model,
                    'identity_source': error.identity_source, 'content_status': error.content_status}
        receipt['elapsed_seconds'] = round(time.monotonic() - began, 3)
        f.save(out / 'receipt.json', receipt)
        print(json.dumps({k: receipt.get(k) for k in ('blind_id', 'status', 'actual_model', 'schema_status', 'elapsed_seconds', 'provider_failure')}), flush=True)
        return receipt
    order = protocol['order']
    receipts = [one(order[0])]
    # No pilot inspection or adaptation: only successful transport/identity allows continuation.
    if receipts[0]['status'] != 'COMPLETED':
        receipts.extend(one(code) for code in order[1:])
    else:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(one, code) for code in order[1:]]
            receipts.extend(future.result() for future in as_completed(futures))
    by_id = {r['blind_id']: r for r in receipts}
    f.save(DEST / 'component-terminal.json', {'at_utc': f.utc(), 'protocol_sha256': f.sha(ROOT / 'component-protocol.json'),
        'planned_responses': 18, 'receipts': [by_id[code] for code in order],
        'observed_model_responses': sum(r['status'] == 'COMPLETED' for r in receipts),
        'scientific_review_performed': False, 'prior_setup_errors_are_not_model_answer_failures': True})


if __name__ == '__main__':
    main()
