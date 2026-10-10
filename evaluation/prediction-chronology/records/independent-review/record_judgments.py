"""Validate quotations and seal manually authored blinded judgments; no scoring model."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
BLIND = BASE / 'attempt-03/blind-review'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create(path, value):
    with path.open('x') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')


def get_pointer(value, pointer):
    for part in pointer.strip('/').split('/'):
        key = part.replace('~1', '/').replace('~0', '~')
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


seal = json.loads((HERE / 'criterion-interpretation-01.seal.json').read_text())
assert all(sha(BASE / path) == expected for path, expected in seal['files'].items())
criteria = json.loads((HERE / 'criterion-interpretation-01.json').read_text())
challenges = json.loads((BASE / 'fixed-challenges.json').read_text())
cases = {case['id']: case for case in challenges['cases'] if case['group'] == 'chronology'}
draft = Path(sys.argv[1]).resolve()
assert draft.is_relative_to(HERE)
judgments = json.loads(draft.read_text())
(HERE / 'judgments').mkdir(exist_ok=True)
written = []
for record in judgments:
    blind_id = record['blind_id']
    assert blind_id in [f'B{i:02d}' for i in range(1, 19)]
    folder = BLIND / blind_id
    visible = json.loads((folder / 'visible-case.json').read_text())
    assert visible['case']['visible_facts'] == cases[record['case_id']]['visible_facts']
    answer = (folder / 'answer.txt').read_text()
    try:
        parsed = json.loads(answer)
        structure = 'parseable JSON; native schema/dispatch not independently assessed'
    except json.JSONDecodeError:
        parsed = None
        structure = 'prose or non-JSON; no scientific penalty for format'
    for criterion in record['criteria']:
        assert criterion['id'] in [x['id'] for x in criteria['cases'][record['case_id']]['criteria']]
        for evidence in criterion['evidence']:
            quote = evidence['quote']
            if 'json_pointer' in evidence:
                assert parsed is not None
                value = get_pointer(parsed, evidence['json_pointer'])
                assert isinstance(value, str) and quote in value, (blind_id, evidence)
            assert quote in answer, (blind_id, quote)
            start = answer.index(quote)
            evidence['answer_line_start'] = answer.count('\n', 0, start) + 1
            evidence['answer_line_end'] = answer.count('\n', 0, start + len(quote)) + 1
            evidence['quote_utf8_sha256'] = hashlib.sha256(quote.encode()).hexdigest()
    expected_ids = [x['id'] for x in criteria['cases'][record['case_id']]['criteria']]
    assert [x['id'] for x in record['criteria']] == expected_ids
    if record['primary_result'] == 'pass':
        assert all(x['status'] == 'pass' for x in record['criteria']) and not record['failure_conditions_observed']
    record.update({'reviewed_at_utc': datetime.now(timezone.utc).isoformat(),
                   'criterion_interpretation_sha256': sha(HERE / 'criterion-interpretation-01.json'),
                   'visible_case_sha256': sha(folder / 'visible-case.json'),
                   'answer_sha256': sha(folder / 'answer.txt'),
                   'visible_structure_only': structure,
                   'native_schema_validity': 'not independently assessed under permitted blinded input scope',
                   'arm_identity_known': False, 'key_opened': False,
                   'manual_semantic_judgment': True, 'automated_semantic_grading': False})
    path = HERE / 'judgments' / (blind_id + '-judgment-01.json')
    create(path, record)
    written.append({'blind_id': blind_id, 'case_id': record['case_id'], 'primary_result': record['primary_result'],
                    'judgment_path': str(path.relative_to(HERE)), 'judgment_sha256': sha(path)})
batch_seal = {'at_utc': datetime.now(timezone.utc).isoformat(),
              'status': 'SEALED_BLINDED_INCREMENTAL_JUDGMENTS', 'key_opened': False,
              'manual_draft_sha256': sha(draft), 'judgments': written}
create(HERE / (draft.stem + '.seal.json'), batch_seal)
print(json.dumps(written, ensure_ascii=False))
