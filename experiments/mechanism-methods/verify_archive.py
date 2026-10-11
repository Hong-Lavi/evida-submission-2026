"""Verify the packaged, already completed method outputs; no solver calls."""
import ast
import csv
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
ast.parse((root / 'verify_archive.py').read_text())
manifest = json.loads((root / 'MANIFEST.json').read_text())
for name, record in manifest['files'].items():
    data = (root / name).read_bytes()
    assert len(data) == record['bytes'], name
    assert hashlib.sha256(data).hexdigest() == record['public_sha256'], name

def rows(name):
    with (root / name).open(newline='') as file:
        return list(csv.DictReader(file))

assert len(rows('caspo/toy/outputs/networks.csv')) == 5
assert len(rows('caspo/toy/outputs/behaviors.csv')) == 3
assert len({r['id'] for r in rows('caspo/toy/outputs/designs.csv')}) == 1
assert len(rows('caspo/four-model/inputs/networks.csv')) == 4
assert len(rows('caspo/four-model/outputs/behaviors.csv')) == 4
assert {(r['TR:B'], r['TR:D']) for r in rows('caspo/four-model/outputs/designs.csv')} == {('0','1'), ('1','0')}

expected = {
    'distinct_actions_plan': ('conditional_plan', {'B_suppression', 'D_suppression'}),
    'same_action_stop': ('decision_region_reached', set()),
    'failed_intervention_hold': ('repair_intervention', set()),
    'insufficient_precision_hold': ('precision_check', set()),
}
for name, (status, checks) in expected.items():
    inp = json.loads((root / f'caspo/native-comparison/{name}.input.json').read_text())
    out = json.loads((root / f'caspo/native-comparison/{name}.output.json').read_text())
    assert len(inp['problem']['worlds']) == 4 and len(inp['problem']['actions']) == 3
    assert out['summary']['selection_status'] == status
    assert set(out['summary']['selected_check_ids']) == checks
    if name.endswith('_hold'):
        assert len(out['summary']['retained_configuration_ids']) == 4
        assert not out['conditional_exclusions']

synthetic = [
    ('baseline.json', 'optimal'), ('without-A.json', 'optimal'),
    ('parent-control-ilp.json', 'infeasible'),
    ('parent-control-flow-exclusive.json', 'infeasible'),
    ('parent-control-flow-nonexclusive.json', 'optimal'),
]
for name, status in synthetic:
    result = json.loads((root / 'corneto/synthetic/outputs' / name).read_text())
    assert result['status'] == status, name
real = json.loads((root / 'corneto/real-three-query-summary.json').read_text())
assert len(real['queries']) == 3 and all(x['status'] == 'optimal' for x in real['queries'])
assert all(x['weighted_absolute_sign_error'] == 0 for x in real['queries'])
account = json.loads((root / 'corneto/execution-accounting.json').read_text())
assert account['actual_corneto_solver_invocations_total'] == 14
assert sum(account['breakdown'].values()) == 14
assert account['real_denominator'] == {'matched_source_input_cases':1,'solver_queries':3}
print('PASS: SHA256, Toy 5/3/1, four-model design, four native calls, two synthetic controls, real 1 input/3 queries, 14-call accounting')
