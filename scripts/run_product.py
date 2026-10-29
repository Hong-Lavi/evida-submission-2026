#!/usr/bin/env python3
"""Launch with an owner-only credential filepath; no credential value enters the environment."""
import argparse
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--enable-model', action='store_true')
    parser.add_argument('--model', default='gpt-6-sol')
    parser.add_argument('--effort', default='medium', choices=['medium', 'high', 'xhigh', 'max'])
    parser.add_argument('--key-file', type=Path, help='Owner-only credential filepath; never pass the value itself')
    parser.add_argument('--check', action='store_true', help='Metadata/configuration check; reads no credential bytes and makes no model calls')
    parser.add_argument('--probe-model', action='store_true', help='Two explicit transport calls for the chosen model; not scientific validation')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from evida.local_credential import inspect_owner_credential, reject_credential_environment
    reject_credential_environment()
    if args.key_file:
        inspect_owner_credential(args.key_file)
    python = root / '.runtime/science/bin/python'
    if args.check:
        print(json.dumps({'runtime_exists': python.is_file(), 'credential_configured': bool(args.key_file),
                          'requested_model': args.model, 'effort': args.effort,
                          'credential_bytes_read': False, 'network_calls': 0,
                          'gateway_compatibility': 'not_checked'}, ensure_ascii=False))
        return
    if not python.is_file():
        raise SystemExit('Prepare the product .runtime/science environment before execution.')
    if args.enable_model and not args.key_file:
        raise SystemExit('Model execution requires an owner-only --key-file path. Never paste a credential value.')
    if args.probe_model and not args.enable_model:
        raise SystemExit('An actual transport probe requires explicit --enable-model.')
    env = {k: os.environ[k] for k in ('PATH', 'LANG', 'LC_ALL', 'TZ', 'SSL_CERT_FILE') if k in os.environ}
    env['PYTHONPATH'] = str(root)
    module = 'evida.transport_probe' if args.probe_model else 'evida.server'
    command = [str(python), '-m', module, '--model', args.model, '--effort', args.effort]
    if not args.probe_model:
        command += ['--port', str(args.port)]
    if args.enable_model:
        if not args.probe_model:
            command += ['--enable-model']
        command += ['--credential-file', str(args.key_file.absolute())]
    os.chdir(root)
    os.execve(str(python), command, env)


if __name__ == '__main__':
    main()
