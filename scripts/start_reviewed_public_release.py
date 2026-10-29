"""Restart the selected public release without regenerating any study database."""
import argparse
import json
import os
from pathlib import Path
import runpy
import shlex
import subprocess
import sys
import time
from urllib.request import urlopen
from reviewed_science_runtime import RuntimeSelectionError, select_science_runtime
from public_planner_policy import goal_completion_stores

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'audit/evida-final-ui-20261002'
POINTER = BASE / 'active-public-release.json'
SESSION = 'evida-final-public'
SCIENCE_PYTHON = ROOT / 'audit/evida-first-discovery-20260928-81/product-candidate-28/product/.runtime/science/bin/python'
KEY = Path('/data/user_home/GoLANII/EVIDA_finals_2026/.worktrees/first-integration/.secrets/competition-api-key')


def selected_release():
    config = json.loads(POINTER.read_text())
    release = Path(config['release'])
    if not release.is_relative_to(BASE) or not (release / 'release.json').is_file():
        raise SystemExit('Active release must be a prepared directory inside the reviewed release area.')
    manifest = json.loads((release / 'release.json').read_text())
    if not manifest.get('ready_for_preflight'):
        raise SystemExit('Selected release failed preparation.')
    return release


def launch_profile(release):
    manifest = json.loads((release / 'release.json').read_text())
    routes = manifest.get('model_routes_runtime')
    if routes is not None:
        # Competition API by default; submitter-subscription routes only by a visitor's choice.
        runtime = Path(routes).resolve(strict=True)
        if not runtime.is_relative_to(BASE) or not (runtime / 'transport/route_transport.py').is_file():
            raise SystemExit('The selected release has no reviewed model-route runtime.')
        authorization = json.loads((runtime / 'authorization.json').read_text())
        if (authorization.get('status') != 'AUTHORIZED_BY_RESEARCHER'
                or authorization.get('default_route') != 'competition_api'
                or authorization.get('automatic_fallback') is not False):
            raise SystemExit('The selected release has no explicit model-route authorization.')
        return {'model': 'gpt-6-sol', 'effort': 'medium', 'runtime': None, 'routes': runtime}
    value = manifest.get('subscription_runtime')
    if value is None:
        return {'model': 'gpt-6-sol', 'effort': 'medium', 'runtime': None, 'routes': None}
    runtime = Path(value).resolve(strict=True)
    if not runtime.is_relative_to(BASE) or not (runtime / 'transport/claude_transport.py').is_file():
        raise SystemExit('The selected release has no reviewed subscription runtime.')
    authorization = json.loads((runtime / 'authorization.json').read_text())
    if authorization.get('model') != 'claude-opus-5' or authorization.get('effort') not in ('max', 'high'):
        raise SystemExit('The selected release has no explicitly reviewed model/effort profile.')
    return {'model': authorization['model'], 'effort': authorization['effort'], 'runtime': runtime, 'routes': None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8904)
    parser.add_argument('--maximum-calls', type=int, default=60)
    parser.add_argument('--goal-completion-store', action='append', default=[])
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--check-config', action='store_true')
    opts = parser.parse_args()
    release = selected_release()
    selected_goal_stores = goal_completion_stores(
        json.loads((release / 'release.json').read_text()), opts.goal_completion_store)
    try:
        science = select_science_runtime(release, BASE, SCIENCE_PYTHON)
    except RuntimeSelectionError as error:
        raise SystemExit(str(error)) from error
    profile = launch_profile(release)
    if opts.check_config:
        print(json.dumps({'release': str(release), 'preserves_existing_stores': True,
                          'model': profile['model'], 'effort': profile['effort'],
                          'subscription': bool(profile['runtime']),
                          'model_routes': str(profile['routes']) if profile['routes'] else None,
                          'goal_completion_stores': selected_goal_stores,
                          'science_runtime': science, 'credentials_read': False}))
        return
    if opts.serve:
        sys.argv = [str(ROOT / 'scripts/serve_reviewed_public_release.py'),
            '--release', str(release), '--port', str(opts.port), '--public-host', 'evida.ndagentevida.com',
            '--enable-model', '--model', profile['model'], '--effort', profile['effort'],
            '--maximum-calls-per-store', str(opts.maximum_calls),
            '--recover-interrupted']
        for store_name in selected_goal_stores:
            sys.argv.extend(['--goal-completion-store', store_name])
        if profile['routes']:
            sys.argv.extend(['--model-routes', str(profile['routes']), '--credential-file', str(KEY)])
        elif profile['runtime']:
            sys.argv.extend(['--subscription-runtime', str(profile['runtime'])])
        else:
            sys.argv.extend(['--credential-file', str(KEY)])
        runpy.run_path(sys.argv[0], run_name='__main__')
        return
    # A live tmux session may contain ongoing research. Never terminate it here.
    if subprocess.run(['tmux', 'has-session', '-t', SESSION], stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL).returncode == 0:
        raise SystemExit('Reviewed server session already exists; inspect it before any restart.')
    env = {'PATH': '/data/user_home/hsm927/anaconda3/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8',
           'LD_LIBRARY_PATH': '/data/user_home/hsm927/anaconda3/lib', 'PYTHONDONTWRITEBYTECODE': '1'}
    if profile['runtime'] or profile['routes']:
        env['HOME'] = os.environ['HOME']
        env['PATH'] = str(Path(env['HOME']) / '.local/bin') + ':' + env['PATH']
    command = ['/usr/bin/env', '-i', *[f'{k}={v}' for k, v in env.items()], science['executable'],
               str(Path(__file__).resolve()), '--serve', '--port', str(opts.port),
               '--maximum-calls', str(opts.maximum_calls)]
    for store_name in selected_goal_stores:
        command.extend(['--goal-completion-store', store_name])
    log = release / 'service-output.log'
    shell_command = 'exec ' + shlex.join(command) + ' >> ' + shlex.quote(str(log)) + ' 2>&1'
    subprocess.run(['tmux', 'new-session', '-d', '-s', SESSION, shell_command], check=True)
    for _ in range(45):
        try:
            with urlopen(f'http://127.0.0.1:{opts.port}/api/status', timeout=1) as response:
                status = json.load(response)
            record = json.loads((release / 'service-launch.json').read_text())
            cmdline = Path(f"/proc/{record['pid']}/cmdline").read_bytes()
            assert b'start_reviewed_public_release.py' in cmdline
            assert record['port'] == opts.port
            assert (status['gateway']['requested_model'], status['gateway']['requested_effort']) == (profile['model'], profile['effort'])
            if profile['runtime']:
                assert status['gateway']['competition_api'] is False
            if profile['routes']:
                assert status['gateway']['transport_mode'] == 'model_routes'
            print(json.dumps({'release': str(release), 'pid': record['pid'],
                              'url': 'https://evida.ndagentevida.com', 'origin_ready': True}))
            return
        except (OSError, ValueError, AssertionError, KeyError):
            time.sleep(1)
    raise SystemExit('Selected server has not become healthy; inspect its preserved service-output.log.')


if __name__ == '__main__':
    main()
