"""Explicit execution repair: same science, valid newly rooted input packets."""
import argparse
import json
from pathlib import Path
import shutil

import run_component_assay as frozen
from lavi_research_os.c1.indexed_input import prepare_indexed_input, restore_indexed_input, IndexedInputCodexAdapter
from lavi_research_os.providers.codex import CodexSubscriptionAdapter

ROOT = Path(__file__).resolve().parent
DEST = ROOT / 'attempt-03'


def prepare():
    if DEST.exists():
        raise ValueError('Third invocation already prepared; preserve original')
    second = json.loads((ROOT / 'attempt-02/component-terminal.json').read_text())
    if second['actual_provider_calls'] != 0:
        raise ValueError('Second invocation unexpectedly called provider')
    DEST.mkdir()
    for name in ('component-protocol.json', 'component-protocol-receipt.json'):
        shutil.copyfile(ROOT / name, DEST / name)
    protocol = json.loads((ROOT / 'component-protocol.json').read_text())
    packets = {}
    for code in protocol['order']:
        out = DEST / 'component-calls' / code; out.mkdir(parents=True)
        original = ROOT / 'component-calls' / code
        shutil.copyfile(original / 'request.json', out / 'request.json')
        payload = json.loads((out / 'request.json').read_text())
        paths = [[k] for k in payload]
        packet = out / 'prepared-input'
        prepare_indexed_input(packet, frozen.TASK, payload, document_paths=paths, required_paths=paths,
                              navigation=True, catalog_directory=True)
        if restore_indexed_input(packet) != payload or frozen.sha(original / 'request.json') != frozen.sha(out / 'request.json'):
            raise ValueError('Science input changed')
        # Constructor/restore are local verifications only, never provider calls.
        IndexedInputCodexAdapter(CodexSubscriptionAdapter(model='gpt-6-astra', reasoning_effort='max',
            timeout_seconds=1800, allow_web_search=False), packet)
        for file in sorted(packet.rglob('*')):
            if file.is_file():
                packets[str(file)] = frozen.sha(file)
    frozen.save(DEST / 'execution-amendment.json', {
        'authorization': 'Root-authorized same frozen comparison outside sandbox; reported separate local packet-root repair before calls.',
        'original_attempt': '18 local CLI startup failures before model output, all retained',
        'attempt_02': '18 local packet-root verification failures with provider_calls=0, all retained',
        'repair': 'Regenerate indexed transport in actual new read directories, with byte-identical request payload/task/schema. No symlink or weakened verification.',
        'original_protocol_sha256': frozen.sha(ROOT / 'component-protocol.json'),
        'original_runner_sha256': frozen.sha(ROOT / 'run_component_assay.py'),
        'launcher_sha256': frozen.sha(__file__), 'new_packet_file_sha256': packets,
        'offline_preflight': 'All 18 payload bytes equal original; lossless restoration and adapter constructor passed before any provider call',
        'science_model_budget_order_changes': False, 'automatic_retry': False,
        'planned_calls': 18, 'concurrency': 2, 'required_execution_boundary': 'require_escalated approval'})
    print(json.dumps({'status': 'ATTEMPT_03_OFFLINE_PREFLIGHT_PASSED', 'same_payloads': 18,
                      'same_protocol_sha256': frozen.sha(DEST / 'component-protocol.json')}))


def run():
    amendment = json.loads((DEST / 'execution-amendment.json').read_text())
    if frozen.sha(__file__) != amendment['launcher_sha256']:
        raise ValueError('Launcher changed')
    for path, expected in amendment['new_packet_file_sha256'].items():
        if frozen.sha(path) != expected:
            raise ValueError('New rooted packet changed')
    frozen.HERE = DEST
    frozen.run()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--prepare', action='store_true'); parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if args.prepare == args.run:
        parser.error('Choose --prepare or --run')
    prepare() if args.prepare else run()
