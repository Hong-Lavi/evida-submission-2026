"""Bounded independent public lookups, preserving individual source receipts.

Only the registered read-only functions below run. This is not an autonomous
search plan: queries and identifiers are fixed before dispatch. A result from
one row can never become another row's input in this bundle.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import threading
import time
import urllib.error

import jsonschema

from .contracts import PUBLIC_LOOKUP_BUNDLE
from .store import dump


LOOKUPS = {
    'search_literature': ('europe_pmc', 'literature'),
    'search_drug_labels': ('dailymed', 'drug_label_search'),
    'read_drug_label': ('dailymed', 'drug_label'),
    'search_clinical_trials': ('clinicaltrials_gov', 'clinical_trial_search'),
    'read_clinical_trial': ('clinicaltrials_gov', 'clinical_trial'),
    'retrieve_archived_rna_reference': ('ensembl115_archive', 'rna_reference_archive'),
    'retrieve_release_rna_reference': ('ensembl_release_archive', 'rna_reference_archive'),
}


def lookup(name, arguments):
    if name == 'retrieve_release_rna_reference':
        from .rna_resources import release_reference
        return release_reference(arguments)
    if name == 'retrieve_archived_rna_reference':
        from .rna_resources import archived_reference
        return archived_reference(arguments)
    if name == 'search_literature':
        from .science import literature
        return literature(arguments)
    from .clinical_sources import HANDLERS
    return HANDLERS[LOOKUPS[name][1]](arguments)


def execute(arguments, output_directory=None, *, parallel=True):
    jsonschema.validate(arguments, PUBLIC_LOOKUP_BUNDLE)
    requests = arguments['lookups']
    if any(not r['purpose'].strip() for r in requests):
        raise ValueError('각 공개 조회의 목적을 적어 주세요.')
    if not arguments['known_inputs_basis'].strip():
        raise ValueError('이미 확인한 검색어·식별자의 근거를 적어 주세요.')
    locks = {provider: threading.Semaphore(1) for provider, _ in LOOKUPS.values()}
    first, unique, positions = {}, [], []
    for item in requests:
        key = dump({'name': item['name'], 'arguments': item['arguments']})
        if key not in first:
            first[key] = len(unique)
            unique.append(item)
        positions.append(first[key])
    destination = Path(output_directory) if output_directory else None
    if destination:
        destination.mkdir(exist_ok=False)
    started = time.monotonic()

    def one(position, item):
        provider, kind = LOOKUPS[item['name']]
        entered = time.monotonic()
        with locks[provider]:
            acquired = time.monotonic()
            receipt = {'provider': provider, 'function': item['name'],
                       'arguments': item['arguments'], 'artifact_kind': kind,
                       'started_at': datetime.now(timezone.utc).isoformat(),
                       'provider_queue_seconds': acquired - entered,
                       'automatic_retry': False}
            try:
                value = lookup(item['name'], item['arguments'])
                receipt.update(status=value.get('status', 'succeeded'), value=value,
                               source=value.get('source'), summary=value.get('summary'))
            except urllib.error.HTTPError as exc:
                receipt.update(status='rate_limited' if exc.code == 429 else 'access_failed',
                               value=None, http_status=exc.code,
                               retry_after=exc.headers.get('Retry-After') if exc.headers else None,
                               error=f'HTTP {exc.code}: {exc.reason}', source_url=exc.url)
            except (TimeoutError, urllib.error.URLError) as exc:
                receipt.update(status='timeout' if isinstance(exc, TimeoutError) or isinstance(getattr(exc, 'reason', None), TimeoutError) else 'network_failed',
                               value=None, error=type(exc).__name__ + ': ' + str(exc)[:700])
            except Exception as exc:
                receipt.update(status='response_or_input_error', value=None,
                               error=type(exc).__name__ + ': ' + str(exc)[:700])
            receipt.update(completed_at=datetime.now(timezone.utc).isoformat(),
                           elapsed_seconds=time.monotonic() - acquired)
            # Each response is retained as soon as it returns, even if a later
            # sibling fails or the worker stops before the aggregate is saved.
            if destination:
                raw = dump(receipt).encode()
                final = destination / f'lookup-{position:02d}.json'
                temporary = destination / f'.lookup-{position:02d}.tmp'
                temporary.write_bytes(raw)
                temporary.replace(final)
                receipt['retained_file'] = final.name
                receipt['retained_file_sha256'] = hashlib.sha256(raw).hexdigest()
            return receipt

    values = [None] * len(unique)
    if parallel:
        with ThreadPoolExecutor(max_workers=min(3, len(unique))) as pool:
            futures = {pool.submit(one, i, item): i for i, item in enumerate(unique)}
            for future in as_completed(futures):
                values[futures[future]] = future.result()
    else:
        for i, item in enumerate(unique):
            values[i] = one(i, item)
    seen, rows = {}, []
    for i, (item, position) in enumerate(zip(requests, positions)):
        value = dict(values[position])
        if position in seen:
            value.pop('value', None)
            value.update(status='same_response', same_response_as=seen[position],
                         returned_status=values[position]['status'])
        else:
            seen[position] = i
        rows.append({'lookup_index': i, 'purpose': item['purpose'], **value})
    succeeded = sum(v['status'] == 'succeeded' for v in values)
    return {'status': 'succeeded' if succeeded == len(values) else 'partial' if succeeded else 'failed',
            'semantic_type': 'independent_public_lookups', 'rows': rows,
            'summary': {'requested': len(rows), 'unique_lookups_executed': len(unique),
                        'successful_lookups': succeeded, 'parallel_workers': min(3, len(unique)) if parallel else 1,
                        'per_provider_concurrency': 1, 'elapsed_seconds': time.monotonic() - started},
            'known_inputs_basis': arguments['known_inputs_basis'],
            'limits': ['각 조회는 미리 정한 공개 검색어·식별자로 실행했습니다. 다음 페이지·새 식별자·다음 질의는 실제 응답을 읽은 뒤 결정합니다.',
                       '현재 URL의 응답은 판본이 달라질 수 있습니다. 조회시각·원 응답 해시·문서 판본을 각 자료에서 확인하세요.',
                       '빈 검색 결과·미조회·429·접근 실패는 치료 효과의 음성이 아닙니다. 자동 재시도하지 않습니다.',
                       '함께 조회한 문헌·라벨·시험등록·참조 서열은 독립적인 반복 실험이 아닙니다.',
                       '각 원 응답은 개별 자료로 보존합니다. 묶음의 첫 전달은 위치·일부 행이며 전체 원문을 읽었다는 뜻이 아닙니다.']}


def retain_sources(runner, wid, job, result):
    """Store native source values separately, then replace bodies with addresses."""
    rows, original = [], {}
    for row in result['rows']:
        entry = dict(row)
        if row['status'] == 'same_response':
            previous = original[row['same_response_as']]
            entry.update(source_artifact_id=previous['source_artifact_id'],
                         source_artifact_sha256=previous['source_artifact_sha256'])
            rows.append(entry)
            continue
        value = entry.pop('value')
        failed = value is None
        content = dump(value if value is not None else {k: v for k, v in row.items() if k != 'value'}).encode()
        kind = 'public_source_failure' if failed else row['artifact_kind']
        aid = runner.store.add_artifact(wid, f"공개 조회 · {row['provider']} · {row['lookup_index'] + 1}", kind, content,
            {'based_rev': job['based_rev'], 'parent_job_id': job['id'], 'attempt_id': job['attempt'],
             'result_status': row['status'], 'arguments': row['arguments'], 'consumed_artifacts': [],
             'summary': row.get('summary'), 'source_function': row['function'],
             'lookup_index': row['lookup_index'], 'purpose': row['purpose']}, bump=False)
        entry.update(source_artifact_id=aid, source_artifact_sha256=hashlib.sha256(content).hexdigest())
        if not failed:
            # Only a bounded first view is carried with the index. Original
            # response bodies/base64 are not reembedded in the conversation.
            preview = runner.inspect(wid, aid, 0, 3)
            encoded = dump(preview).encode()
            if len(encoded) <= 30_000:
                entry['initial_view'] = preview
            else:
                entry['initial_view'] = None
                entry['view_delivery'] = 'deferred_select_source_range'
                entry['view_bytes'] = len(encoded)
            entry['view_sha256'] = hashlib.sha256(encoded).hexdigest()
        original[row['lookup_index']] = entry
        rows.append(entry)
    return {**result, 'rows': rows}
