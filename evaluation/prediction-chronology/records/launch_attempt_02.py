"""Root-authorized execution-boundary repair; original frozen science unchanged.

Run only through require_escalated approval: Codex CLI initializes its own state.
Original 18 local startup failures remain in component-calls, never overwritten.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

import run_component_assay as frozen

ROOT = Path(__file__).resolve().parent
DEST = ROOT / 'attempt-02'


def prepare():
    if DEST.exists():
        raise ValueError('Second invocation already prepared; do not overwrite')
    audit = json.loads((ROOT / 'startup-failure-audit.json').read_text())
    if audit['model_responses_observed'] != 0 or not all(r['appserver_initialization_failed'] for r in audit['rows']):
        raise ValueError('Original attempt classification changed')
    DEST.mkdir()
    for name in ('component-protocol.json', 'component-protocol-receipt.json'):
        shutil.copyfile(ROOT / name, DEST / name)
    protocol = json.loads((ROOT / 'component-protocol.json').read_text())
    for code in protocol['order']:
        out = DEST / 'component-calls' / code; out.mkdir(parents=True)
        original = ROOT / 'component-calls' / code
        shutil.copyfile(original / 'request.json', out / 'request.json')
        (out / 'prepared-input').symlink_to(original / 'prepared-input', target_is_directory=True)
        if frozen.sha(original / 'request.json') != frozen.sha(out / 'request.json'):
            raise ValueError('Science input changed')
    frozen.save(DEST / 'execution-amendment.json', {
        'authorization': 'Root explicitly authorized 2026-10-11 separate invocation via require_escalated tool approval after explaining local startup failure to researcher.',
        'reason': 'Original CLI failed to initialize app-server state on read-only filesystem before model identity or output.',
        'original_attempts_preserved': 18, 'original_model_responses_observed': 0,
        'original_protocol_sha256': frozen.sha(ROOT / 'component-protocol.json'),
        'original_runner_sha256': frozen.sha(ROOT / 'run_component_assay.py'),
        'launcher_sha256': frozen.sha(__file__), 'immutable_indexed_inputs_reused': True,
        'science_model_budget_order_changes': False, 'automatic_retry': False,
        'planned_calls': 18, 'concurrency': 2, 'required_execution_boundary': 'require_escalated approval'})
    print(json.dumps({'status': 'ATTEMPT_02_PREPARED', 'same_protocol_sha256': frozen.sha(DEST / 'component-protocol.json')}))


def run():
    amendment = json.loads((DEST / 'execution-amendment.json').read_text())
    if frozen.sha(__file__) != amendment['launcher_sha256']:
        raise ValueError('Launcher changed')
    frozen.HERE = DEST
    frozen.run()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--prepare', action='store_true'); parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if args.prepare == args.run:
        parser.error('Choose --prepare or --run')
    prepare() if args.prepare else run()
