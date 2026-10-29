"""Serve an explicit prepared release; no snapshot regeneration and no live-store mounts."""
import argparse
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import sqlite3
import stat
import sys
import threading
from public_planner_policy import goal_completion_stores, planner_options


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--release', required=True, type=Path)
    parser.add_argument('--port', required=True, type=int)
    parser.add_argument('--public-host', action='append', default=[])
    parser.add_argument('--enable-model', action='store_true')
    parser.add_argument('--read-only', action='store_true',
                        help='Preview only: reject every HTTP write and keep model execution disabled.')
    parser.add_argument('--model', default='gpt-6-sol')
    parser.add_argument('--effort', default='medium')
    parser.add_argument('--maximum-calls-per-store', type=int, default=60)
    parser.add_argument('--goal-completion-store', action='append', default=[],
                        help='Reviewed opt-in: continue normal planning without a response-count stop; resource quotas stay unchanged.')
    parser.add_argument('--credential-file', type=Path,
                        help='Owner-only product credential, read only when models are enabled.')
    parser.add_argument('--subscription-runtime', type=Path,
                        help='Explicit reviewed Claude subscription bridge; competition credentials are excluded.')
    parser.add_argument('--model-routes', type=Path,
                        help='Competition API by default plus explicitly chosen submitter-subscription routes. '
                             'The competition key stays in this process memory, never in the environment.')
    parser.add_argument('--recover-interrupted', action='store_true',
                        help='On this same release after its owner exits, retain and mark old jobs interrupted.')
    opts = parser.parse_args()
    if opts.read_only and opts.enable_model:
        parser.error('--read-only cannot enable model execution')
    if opts.subscription_runtime and (not opts.enable_model or opts.credential_file):
        parser.error('Subscription execution requires enabled models and excludes competition credentials')
    if opts.model_routes and (not opts.enable_model or not opts.credential_file or opts.subscription_runtime):
        parser.error('Model routes need enabled models and the competition credential file, '
                     'and replace the single-route subscription runtime')
    if opts.enable_model and not opts.subscription_runtime and not opts.credential_file:
        parser.error('API model execution requires an approved owner-only --credential-file; environment credentials are excluded.')
    release = opts.release.resolve()
    manifest = json.loads((release / 'release.json').read_text())
    if not manifest.get('ready_for_preflight'):
        raise SystemExit('Release preparation failed; inspect release.json before serving.')
    product = (release / 'product').resolve()
    if not product.is_relative_to(release):
        raise SystemExit('Product must be inside the explicit release.')
    stores = {name: (release / value).resolve() for name, value in manifest['stores'].items()}
    selected_goal_stores = goal_completion_stores(manifest, opts.goal_completion_store)
    interrupted_stores = {}
    for name, path in stores.items():
        if not path.is_relative_to(release / 'stores') or not path.is_file():
            raise SystemExit(f'Refuse an original/external store path: {name}')
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
            jobs = db.execute("SELECT id FROM jobs WHERE status IN ('queued','running')").fetchall()
            if jobs:
                interrupted_stores[name] = [row[0] for row in jobs]
    if interrupted_stores:
        if not opts.recover_interrupted:
            raise SystemExit('Active jobs present; initial deployment requires quiescent copies.')
        previous = json.loads((release / 'service-launch.json').read_text())
        if previous['release'] != str(release):
            raise SystemExit('Recovery must refer to this same previously served release.')
        # After a reboot the recorded pid can belong to an unrelated process; only a live
        # public-release server counts as the previous owner.
        try:
            command = Path(f"/proc/{previous['pid']}/cmdline").read_bytes()
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            command = b''
        if b'reviewed_public_release' in command:
            raise SystemExit('Previous owner still exists; preserve its work.')
        preserved = release / 'restart-preservation' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        preserved.mkdir(parents=True)
        for name in interrupted_stores:
            with sqlite3.connect(stores[name].as_uri() + '?mode=ro', uri=True) as source:
                with sqlite3.connect(preserved / (name + '.sqlite3')) as target:
                    source.backup(target)
        (preserved / 'interrupted-jobs.json').write_text(json.dumps(interrupted_stores, indent=2) + '\n')
    policy = json.loads((product / 'configs/api_policy.json').read_text())
    if opts.enable_model and any(name in os.environ for name in (
            'EVIDA_COMPETITION_API_KEY', 'OPENAI_API_KEY', 'CODEX_API_KEY',
            'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_BASE_URL', policy['secret_env'])):
        raise SystemExit('Credential/provider environment overrides are excluded from model execution; use the reviewed owner-only filepath.')
    competition_key = None
    if opts.enable_model and not opts.subscription_runtime and opts.credential_file:
        keyfile = opts.credential_file
        for path in (keyfile, keyfile.parent):
            info = path.stat()
            if path.is_symlink() or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise SystemExit('Credential file and its directory must be owner-only.')
        if not keyfile.is_file() or not 0 < keyfile.stat().st_size <= 8192:
            raise SystemExit('Invalid credential file; value withheld.')
        key = keyfile.read_text().strip()
        if not key or not all(33 <= ord(c) <= 126 for c in key):
            raise SystemExit('Invalid credential format; value withheld.')
        # Every API branch uses process memory; child processes never inherit the key.
        competition_key = key
        del key
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(product))
    import evida
    assert Path(evida.__file__).resolve().is_relative_to(product)
    from evida.server import Application
    from evida.workspace_catalog import WorkspaceCatalog, catalog_handler
    subscription_gateway = None
    if opts.subscription_runtime:
        runtime = opts.subscription_runtime.resolve(strict=True)
        if not runtime.is_relative_to(Path(__file__).resolve().parents[1] / 'audit'):
            raise SystemExit('Subscription runtime must be an explicitly reviewed local audit.')
        os.environ['EVIDA_SUBSCRIPTION_PRODUCT'] = str(product)
        sys.path.insert(0, str(runtime / 'transport'))
        from claude_transport import ClaudeProductGateway
        route_authorization = json.loads((runtime / 'authorization.json').read_text())
        provider_calls = Path(route_authorization.get('provider_calls', runtime / 'provider-calls')).resolve()
        if not provider_calls.is_relative_to(Path(__file__).resolve().parents[1] / 'audit/evida-final-ui-20261002'):
            raise SystemExit('Subscription request records must remain in the reviewed local stage.')
        subscription_gateway = ClaudeProductGateway(provider_calls)
        if (opts.model, opts.effort) != (subscription_gateway.model, subscription_gateway.effort):
            raise SystemExit('Requested subscription identity differs from the approved bridge.')
    route_gateways = quota = None
    if opts.model_routes:
        runtime = opts.model_routes.resolve(strict=True)
        if not runtime.is_relative_to(Path(__file__).resolve().parents[1] / 'audit/evida-final-ui-20261002'):
            raise SystemExit('Model routes must be an explicitly reviewed local audit.')
        os.environ['EVIDA_SUBSCRIPTION_PRODUCT'] = str(product)
        sys.path.insert(0, str(runtime / 'transport'))
        from route_transport import build_subscription_routes
        from evida.model_routes import RouteGateway, QuotaState
        route_gateways = build_subscription_routes(runtime)
        quota = QuotaState(release / 'model-routes-state' / 'competition-quota.json')
    os.chdir(product)
    apps = {}
    semantic_reader = None
    server = None
    try:
        for name, path in stores.items():
            apps[name] = Application(product, db_path=path,
                enable_model=opts.enable_model and subscription_gateway is None,
                model='gpt-6-sol' if subscription_gateway else opts.model,
                effort='medium' if subscription_gateway else opts.effort,
                maximum_requests=opts.maximum_calls_per_store if name == 'new_research' or name.startswith('live_') else 1,
                **planner_options(name, selected_goal_stores))
            if competition_key is not None:
                apps[name].gateway.set_credential(competition_key)
            if subscription_gateway:
                apps[name].gateway = subscription_gateway
                apps[name].runner.gateway = subscription_gateway
            if route_gateways is not None:
                routed = RouteGateway(apps[name].gateway, route_gateways, quota)
                apps[name].gateway = routed
                apps[name].runner.gateway = routed
            if semantic_reader is None:
                semantic_reader = apps[name]._semantic_literature
            else:
                apps[name]._semantic_literature.close()
                apps[name]._semantic_literature = semantic_reader
        catalog = WorkspaceCatalog(apps, manifest['primary'])
        handler = catalog_handler(catalog, opts.public_host)
        if opts.read_only:
            class ReadOnlyPreview(handler):
                def reject_write(self):
                    body = json.dumps({'error': 'READ_ONLY_PREVIEW',
                                       'message': 'This preview supports browsing and local drafts.'}).encode('utf-8')
                    self.send_response(405)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.send_header('Content-Length', str(len(body)))
                    self.send_header('Allow', 'GET, HEAD, OPTIONS')
                    self.end_headers()
                    self.wfile.write(body)

                do_POST = reject_write
                do_PUT = reject_write
                do_PATCH = reject_write
                do_DELETE = reject_write

            handler = ReadOnlyPreview
        server = ThreadingHTTPServer(('127.0.0.1', opts.port), handler)
        if not opts.enable_model:
            browser_cases = []
            for case in ('ipf','pde4b','als','gaucher','preeclampsia','ttr_sirna'):
                app = apps.get('live_' + case)
                if app is None:
                    continue
                workspaces = app.store.list()
                if len(workspaces) != 1:
                    raise ValueError(f'Explicit browser workspace mapping needed for {case}.')
                browser_cases.append({'case': case, 'synthetic': False,
                    'base': f'http://127.0.0.1:{opts.port}', 'workspace': workspaces[0]['id']})
            (release / 'servers.json').write_text(json.dumps(browser_cases, indent=2) + '\n')
        record = {'at': datetime.now(timezone.utc).isoformat(), 'pid': os.getpid(), 'port': opts.port,
                  'product': str(product), 'release': str(release), 'model_enabled': opts.enable_model,
                  'read_only_preview': opts.read_only,
                  'model': opts.model, 'effort': opts.effort, 'workspaces': len(catalog.list()),
                  'transport_mode': (subscription_gateway.transport_mode if subscription_gateway
                                     else 'model_routes' if route_gateways is not None else 'competition_gateway'),
                  'subscription_routes': [{'id': r.route_id, 'model': r.model, 'effort': r.effort,
                                           'maximum_calls': r.maximum_calls} for r in route_gateways or ()],
                  'competition_key_in_environment': policy['secret_env'] in os.environ,
                  'goal_completion_stores': selected_goal_stores,
                  'planner_profile_scope': 'Only named stores; model routes and resource quotas unchanged.',
                  'maximum_calls_per_spending_store': None if subscription_gateway else opts.maximum_calls_per_store,
                  'maximum_shared_subscription_calls': 60 if subscription_gateway else None,
                  'limit_scope': 'Shared persistent subscription stage across stores.' if subscription_gateway else 'Per Application/store, not a process-wide aggregate.',
                  'semantic_worker_scope': 'One optional query worker and one indexing job across all stores.',
                  'recovered_as_interrupted_without_dispatch': interrupted_stores,
                  'public_hosts': opts.public_host, 'all_stores_inside_release': True}
        history = release / 'service-history'
        history.mkdir(exist_ok=True)
        (history / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '.json')).write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + '\n')
        (release / 'service-launch.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(record, ensure_ascii=False), flush=True)
        def stop(_signum, _frame):
            threading.Thread(target=server.shutdown, daemon=True).start()
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        server.serve_forever()
    finally:
        if server:
            server.server_close()
        for app in apps.values():
            app._semantic_literature.close()
            for name in ('pool','planner_pool','research_pool','explanation_pool'):
                pool = getattr(app.runner, name, None)
                if pool:
                    pool.shutdown(wait=True)
            app.lock.close()


if __name__ == '__main__':
    main()
