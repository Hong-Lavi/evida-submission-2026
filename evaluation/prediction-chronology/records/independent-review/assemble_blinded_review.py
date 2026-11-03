"""Assemble already sealed manual judgments; do not infer identities or grade answers."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
name = sys.argv[1]
assert name.isidentifier() and not (HERE / (name + '.json')).exists()
final = '--final' in sys.argv[2:]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


criterion_seal = json.loads((HERE / 'criterion-interpretation-01.seal.json').read_text())
assert all(sha(BASE / path) == expected for path, expected in criterion_seal['files'].items())
sealed = {}
batch_pins = {}
for file in sorted(HERE.glob('manual-batch-*.seal.json')):
    content = json.loads(file.read_text())
    assert content['key_opened'] is False
    batch_pins[file.name] = sha(file)
    for row in content['judgments']:
        assert row['blind_id'] not in sealed
        assert sha(HERE / row['judgment_path']) == row['judgment_sha256']
        sealed[row['blind_id']] = row
rows = []
for number in range(1, 19):
    blind_id = f'B{number:02d}'
    pin = sealed.get(blind_id)
    if pin is None:
        rows.append({'blind_id': blind_id, 'review_status': 'pending', 'case_id': None, 'primary_result': None})
        continue
    record = json.loads((HERE / pin['judgment_path']).read_text())
    visible_dir = BASE / 'attempt-03/blind-review' / blind_id
    assert sha(visible_dir / 'answer.txt') == record['answer_sha256']
    assert sha(visible_dir / 'visible-case.json') == record['visible_case_sha256']
    assert record['key_opened'] is False and record['arm_identity_known'] is False
    rows.append({'blind_id': blind_id, 'review_status': 'sealed', **pin, 'review': record})
if final:
    assert len(sealed) == 18, 'Do not finalize while judgments remain pending'
counts = Counter(row['primary_result'] for row in rows if row['review_status'] == 'sealed')
report = {'status': 'FINAL_BLINDED_REVIEW' if final else 'INCREMENTAL_BLINDED_REVIEW',
          'at_utc': datetime.now(timezone.utc).isoformat(), 'planned_answers': 18,
          'reviewed': len(sealed), 'pending': 18 - len(sealed), 'scientific_primary_counts': dict(counts),
          'identity_key_opened': False, 'criterion_seal_sha256': sha(HERE / 'criterion-interpretation-01.seal.json'),
          'batch_seal_sha256': batch_pins, 'rows': rows,
          'limits': ['Partial format blinding; no arm identity inferred or key opened.',
                     'Scientific content scored manually against fixed P1-P6 expectations; native schema/dispatch validity not independently assessed.',
                     'Six selected developmental cases with synthetic histories and one answer per arm/case; no population accuracy, clinical validity or biological validation claim.',
                     'Returned and attempted execution counts require owner-confirmed terminal coverage; the present count is reviewed visible answers.']}
with (HERE / (name + '.json')).open('x') as handle:
    json.dump(report, handle, ensure_ascii=False, indent=2)
    handle.write('\n')
md = ['# 익명 과학 판정', '',
      f"고정된 18개 분모 중 {len(sealed)}개 답변을 판정·봉인했고, {18-len(sealed)}개가 미완료다. "
      '답변 작성 경로의 이름과 매핑은 열지 않았다. 아래 결과는 선택된 합성 시점 사례에 대한 수동 과학 판정이며, 일반 정확도나 생물학적 검증 결과가 아니다.', '',
      '형식과 답변 길이는 과학 점수에 반영하지 않았다. native schema/dispatch 검증은 이 검토 범위 밖이다. '
      '각 판정의 인용은 원 answer.txt의 정확한 문자열 및 JSON pointer/행 위치로 확인했으며, 원본과 판정 해시를 함께 보존했다.', '',
      '| 익명 ID | 사례 | 과학 판정 | 판정 파일 |', '|---|---|---|---|']
for row in rows:
    if row['review_status'] == 'pending':
        md.append(f"| {row['blind_id']} | 미확인 | 미완료 | — |")
    else:
        md.append(f"| {row['blind_id']} | {row['case_id'].split('_')[0]} | {row['primary_result']} | [{row['blind_id']}]({HERE / row['judgment_path']}) |")
for row in rows:
    if row['review_status'] == 'pending':
        continue
    r = row['review']
    md += ['', f"## {r['blind_id']} — {r['case_id']}", '', r['assigned_instance'], '', r['declared_chronology'], '']
    for c in r['criteria']:
        md.append(f"- {c['id']}: **{c['status']}**. {c['reason']}")
        for e in c['evidence']:
            locator = e.get('json_pointer', 'line ' + str(e['answer_line_start']))
            md.append(f"  - `{locator}`: “{e['quote']}”")
    if r['ambiguities']:
        md += ['', '모호한 점: ' + ' '.join(r['ambiguities'])]
    md += ['', f"[원 답변]({BASE / 'attempt-03/blind-review' / r['blind_id'] / 'answer.txt'}) · answer SHA `{r['answer_sha256']}`"]
with (HERE / (name + '.md')).open('x') as handle:
    handle.write('\n'.join(md) + '\n')
seal = {'status': 'SEALED_BEFORE_UNBLINDING', 'at_utc': datetime.now(timezone.utc).isoformat(),
        'identity_key_opened': False, 'files': {name + ext: sha(HERE / (name + ext)) for ext in ('.json', '.md')}}
with (HERE / (name + '.seal.json')).open('x') as handle:
    json.dump(seal, handle, indent=2)
    handle.write('\n')
print(json.dumps({'name': name, 'reviewed': len(sealed), 'pending': 18-len(sealed), 'scientific_primary_counts': dict(counts), 'seal_sha256': sha(HERE / (name + '.seal.json'))}))
