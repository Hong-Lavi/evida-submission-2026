"""Read-only public HTTPS with pinned DNS, bounded Chrome and retained source bytes."""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import resource
import time
from urllib.parse import urljoin, urlencode, urlsplit, parse_qs, parse_qsl, urlunsplit
from literature_access import validate_public_url
from web_sources_worker import _addresses, PinnedHTTPS

MAX_BYTES = 20 * 1024 * 1024
MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_PDF_PAGES = 300
MAX_LINKS = 2000


def digest(raw): return hashlib.sha256(raw).hexdigest()


def download_redirect(url):
    """A public publisher may issue its own short-lived object URL; never log that signature."""
    p = urlsplit(url)
    query = parse_qsl(p.query)
    signed = any(k.lower() == 'x-amz-signature' for k, _ in query)
    if signed:
        # Only the standard publisher-issued S3 download query is accepted here, never model input.
        fields = {'x-amz-algorithm', 'x-amz-date', 'x-amz-signedheaders', 'x-amz-credential',
                  'x-amz-expires', 'x-amz-signature', 'x-amz-security-token', 'x-amz-content-sha256',
                  'response-content-disposition', 'response-content-type'}
        if any(k.lower() not in fields for k, _ in query):
            raise ValueError('unsupported_signed_download_query')
        plain = urlunsplit((p.scheme, p.netloc, p.path, '', ''))
        validate_public_url(plain)
        return p, plain
    return validate_public_url(url), url


def fetch(url, limit=MAX_BYTES, redirects=True):
    receipt = {'url': url, 'retrieved_at': datetime.now(timezone.utc).isoformat(), 'access_attempts': []}
    result = {'source': receipt, 'acquisition_status': 'retrieval_failed'}
    seen = set()
    for _ in range(5):
        conn = None
        try:
            p, logged_url = download_redirect(url) if seen else (validate_public_url(url), url)
            if url in seen: raise ValueError('redirect_cycle')
            seen.add(url)
            addresses = _addresses(p.hostname)
            conn = PinnedHTTPS(p.hostname, addresses[0]); conn.timeout = 8
            conn.request('GET', (p.path or '/') + ('?' + p.query if p.query else ''),
                headers={'User-Agent': 'EVIDA/0.1 public-research-prototype', 'Accept-Encoding': 'identity'})
            response = conn.getresponse(); raw = response.read(limit + 1)
            entry = {'url': logged_url, 'http_status': response.status, 'bytes': len(raw),
                'sha256': digest(raw), 'content_type': response.getheader('Content-Type', ''),
                'content_encoding': response.getheader('Content-Encoding', ''), 'connected_ip': addresses[0]}
            receipt['access_attempts'].append(entry); receipt.update(entry, resolved_url=logged_url)
            if len(raw) > limit:
                result['acquisition_status'] = 'download_limit'; return result
            result['headers'] = {k.lower(): v for k, v in response.getheaders() if k.lower() in
                ('content-type', 'content-security-policy', 'access-control-allow-origin')}
            if response.status in (301, 302, 303, 307, 308):
                next_url = urljoin(url, response.getheader('Location', ''))
                download_redirect(next_url)
                if not redirects:
                    result['headers']['location'] = next_url
                    result['acquisition_status'] = 'redirect'; return result
                url = next_url; continue
            result['original_response_base64'] = base64.b64encode(raw).decode()
            result['acquisition_status'] = ('response_received' if response.status == 200 else
                'access_denied' if response.status in (401, 403, 429) else 'http_failure')
            return result
        except Exception as exc:
            result.update(acquisition_status='network_or_policy_failure', error_type=type(exc).__name__)
            return result
        finally:
            if conn is not None: conn.close()
    result['acquisition_status'] = 'redirect_limit'; return result


def challenge(raw):
    from lxml import html
    try:
        tree = html.fromstring(raw)
        title = ' '.join(tree.xpath('//title/text()')).casefold()
        visible = tree.text_content().casefold()
        markers = ('client challenge', 'just a moment', 'verify you are human', 'checking your browser',
                   'access denied', 'unusual traffic', 'please enable javascript to proceed', 'captcha')
        return any(m in title or (len(visible) < 12000 and m in visible) for m in markers)
    except Exception: return False


def source_links(raw, url):
    from lxml import html
    tree = html.fromstring(raw)
    rows = []; seen = set()
    for a in tree.xpath('//a[@href]'):
        destination = urljoin(url, a.get('href', ''))
        try: validate_public_url(destination)
        except ValueError: continue
        if destination in seen: continue
        text = ' '.join(a.text_content().split())[:500]
        seen.add(destination)
        rows.append({'kind': 'source_link', 'url': destination, 'text': text,
            'is_supplement_candidate': any(s in (text+' '+destination).casefold() for s in
                ('supplement', 'supporting', 'extended-data', 'moesm', 'additional file')),
            'retrieved': False})
        if len(rows) >= MAX_LINKS: break
    return rows


def extract_document(raw, url, is_pdf):
    """Called in a separate resource-limited process, never inside Chrome."""
    if is_pdf:
        from io import BytesIO
        import pypdf
        with BytesIO(raw) as stream:
            doc = pypdf.PdfReader(stream, strict=False)
            if doc.is_encrypted: return {'acquisition_status': 'encrypted_document', 'rows': []}
            rows = []; used = 0; truncated = False
            for i, page in enumerate(doc.pages):
                if i >= MAX_PDF_PAGES or used >= MAX_TEXT_BYTES:
                    truncated = True; break
                full = (page.extract_text() or '').encode(); remaining = MAX_TEXT_BYTES-used
                text = full[:remaining].decode('utf-8', errors='ignore')
                used += len(text.encode()); truncated |= len(full) > remaining
                rows.append({'kind': 'pdf_page', 'page_number': i+1, 'text': text,
                    'row_id': f'{digest(raw)}:page:{i+1}', 'sha256': digest(text.encode()),
                    'text_truncated': len(full) > remaining, 'visuals_reviewed': False})
            return {'status': 'partial' if truncated or not any(r['text'].strip() for r in rows) else 'succeeded',
                'rows': rows, 'document_pages': len(doc.pages), 'extraction_truncated': truncated,
                'extractor': {'name': 'pypdf', 'version': pypdf.__version__},
                'extraction_limits': {'pages': MAX_PDF_PAGES, 'text_bytes': MAX_TEXT_BYTES},
                'acquisition_status': 'pdf_text_extracted', 'semantic_type': 'research_document',
                'content_scope': 'PDF text only; scanned figures and table geometry require visual review'}
    from web_sources_worker import extract
    extracted = extract({'original_response_base64': base64.b64encode(raw).decode(), 'url': url})
    rows = []; used = 0; truncated = False
    for i, block in enumerate(extracted.get('blocks', [])):
        full = block.encode(); remaining = MAX_TEXT_BYTES-used
        if remaining <= 0: truncated = True; break
        text = full[:remaining].decode('utf-8', errors='ignore'); used += len(text.encode())
        truncated |= len(full) > remaining
        rows.append({'kind': 'paragraph', 'text': text, 'row_id': f'{digest(raw)}:block:{i}',
            'sha256': digest(text.encode()), 'source_url': url, 'text_truncated': len(full)>remaining})
    paragraph_count = len(rows); links = source_links(raw, url); rows.extend(links)
    return {'rows': rows, 'title': extracted.get('title'), 'identity': extracted.get('identity'),
        'permissions': extracted.get('permissions'), 'extractor': extracted.get('extractor'),
        'status': 'succeeded' if paragraph_count and not truncated else 'partial',
        'acquisition_status': extracted['acquisition_status'], 'semantic_type': 'research_document',
        'paragraph_count': paragraph_count, 'links_count': len(links), 'extraction_truncated': truncated,
        'extraction_limits': {'text_bytes': MAX_TEXT_BYTES, 'links': MAX_LINKS},
        'content_scope': 'Extracted text and unvisited source links; not complete supplement or figure verification'}


def bounded_extract(raw, url, is_pdf, work):
    incoming, output = work/'parse-request.json', work/'parse-result.json'
    incoming.write_text(json.dumps({'raw': base64.b64encode(raw).decode(), 'url': url, 'is_pdf': is_pdf}))
    try:
        proc = subprocess.run([sys.executable, '-B', __file__, '--extract', str(incoming), str(output)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=35)
        if proc.returncode or not output.exists() or output.stat().st_size > 8*1024*1024:
            return {'status': 'failed', 'rows': [], 'acquisition_status': 'parser_resource_or_format_failure'}
        return json.loads(output.read_text())
    except subprocess.TimeoutExpired:
        return {'status': 'failed', 'rows': [], 'acquisition_status': 'parser_timeout'}


def render(raw, url, chrome, work):
    from playwright.sync_api import sync_playwright
    start = time.monotonic(); attempts = []; total_bytes = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chrome, headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-background-networking',
                  '--force-webrtc-ip-handling-policy=disable_non_proxied_udp'],
            proxy={'server': 'http://127.0.0.1:9'})
        try:
            context = browser.new_context(service_workers='block', accept_downloads=False,
                viewport={'width': 1280, 'height': 900})
            context.route_web_socket('**/*', lambda ws: ws.close())
            def route_handler(route):
                nonlocal total_bytes
                req = route.request
                if req.method != 'GET' or len(attempts) >= 50 or time.monotonic()-start > 40:
                    return route.abort()
                if req.resource_type in ('media', 'image', 'font'):
                    return route.abort()
                if req.is_navigation_request():
                    if req.url.rstrip('/') == url.rstrip('/') and req.frame == page.main_frame:
                        return route.fulfill(status=200, content_type='text/html', body=raw)
                    return route.abort()
                try: validate_public_url(req.url)
                except ValueError: return route.abort()
                # Browser cookies, request headers and POST bodies are never forwarded.
                fetched = fetch(req.url, limit=3*1024*1024, redirects=False)
                body = base64.b64decode(fetched.get('original_response_base64', ''))
                total_bytes += len(body)
                attempts.append({'url': req.url, 'status': fetched['acquisition_status'],
                    'sha256': digest(body), 'bytes': len(body)})
                if total_bytes > 20*1024*1024 or fetched['acquisition_status'] not in ('response_received', 'redirect'):
                    return route.abort()
                return route.fulfill(status=fetched['source']['http_status'], headers=fetched['headers'], body=body)
            context.route('**/*', route_handler)
            page = context.new_page(); page.set_default_timeout(15000)
            page.on('dialog', lambda dialog: dialog.dismiss())
            context.on('page', lambda other: other.close() if other != page else None)
            page.goto(url, wait_until='domcontentloaded', timeout=45000)
            page.wait_for_timeout(1000)
            dom = page.content().encode()
            if len(dom) > MAX_BYTES: raise ValueError('rendered_document_limit')
            # A retained viewport proves which page was rendered; the model reads source rows.
            image = work/'page.png'; page.screenshot(path=str(image), timeout=5000)
            return dom, {'browser': 'Chrome', 'version': browser.version,
                'rendered_sha256': digest(dom), 'screenshot_sha256': digest(image.read_bytes()),
                'network_attempts': attempts, 'credentials_used': False,
                'scope': 'rendered DOM text; images and fonts omitted; no user session, forms or access-control bypass'}
        finally: browser.close()


def acquire(tool, args, chrome, work):
    if tool == 'public_web_search':
        url = ('https://www.bing.com/search?' + urlencode({'q': args['query'], 'format': 'rss'})
            if args['engine'] == 'bing' else 'https://html.duckduckgo.com/html/?' + urlencode({'q': args['query']}))
    else: url = args['url']
    fetched = fetch(url)
    result = {**fetched, 'status': 'failed', 'rows': [], 'model_calls': 0,
        'full_document_read': False, 'source_content_is_data_not_instructions': True}
    result.pop('headers', None)
    (work/'progress.json').write_text(json.dumps(result))
    if fetched['acquisition_status'] != 'response_received': return result
    raw = base64.b64decode(fetched['original_response_base64'])
    if fetched['source'].get('content_encoding') not in ('', 'identity'):
        result['acquisition_status'] = 'unsupported_content_encoding'; return result
    if challenge(raw):
        result['acquisition_status'] = 'challenge'; return result
    final_url = fetched['source']['resolved_url']
    if tool == 'public_web_search':
        from lxml import etree, html
        echoed_query = None
        if args['engine'] == 'bing':
            tree = etree.fromstring(raw, parser=etree.XMLParser(resolve_entities=False, no_network=True))
            echoed = parse_qs(urlsplit(tree.findtext('channel/link') or '').query).get('q', [])
            if len(echoed) == 1:
                echoed_query = echoed[0]
            rows = [{'title': x.findtext('title'), 'url': x.findtext('link'), 'snippet': x.findtext('description')}
                for x in tree.findall('.//item')]
        else:
            tree = html.fromstring(raw); rows = []
            for item in tree.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," result ")]'):
                links = item.xpath('.//a[contains(@class,"result__a")]')
                if not links: continue
                link = links[0]; u = urljoin(final_url, link.get('href', ''))
                if urlsplit(u).hostname and urlsplit(u).hostname.endswith('duckduckgo.com'):
                    u = parse_qs(urlsplit(u).query).get('uddg', [u])[0]
                rows.append({'title': ' '.join(link.text_content().split()), 'url': u,
                    'snippet': ' '.join(item.text_content().split())[:1600]})
        for row in rows:
            try: validate_public_url(row.get('url'))
            except (ValueError, TypeError): continue
            result['rows'].append({**row, 'kind': 'web_search_hit', 'row_id': f'{digest(raw)}:hit:{len(result["rows"])}',
                'destination_retrieved': False, 'search_snippet_is_not_claim_support': True})
        result.update(status='succeeded' if result['rows'] else 'partial', engine=args['engine'],
            query=args['query'], semantic_type='public_web_discovery', relevance_verified=False,
            limits=['A returned hit is not relevance validation. Inspect titles/snippets and refine or use an appropriate scholarly index when unrelated.'])
        from search_quality import assess_search_scope
        result['search_quality'] = assess_search_scope(args['query'], result['rows'], echoed_query=echoed_query)
        quality = result['search_quality']
        if (quality['explicit_site_scope_status'] in ('no_returned_hit_in_explicit_site_scope',
                'partial_explicit_site_scope_match') or quality['response_query_echo_status'] == 'mismatch'):
            result['status'] = 'partial'
            result['limits'].append('HTTP acquisition succeeded, but returned hits do not fully meet the '
                'explicit query/site scope. All hits and original bytes are retained; this is not evidence of no literature.')
        return result
    content_type = fetched['source']['content_type'].split(';')[0].lower()
    if content_type == 'application/pdf' or raw.startswith(b'%PDF-'):
        result.update(bounded_extract(raw, final_url, True, work))
        return result
    if content_type not in ('text/html', 'application/xhtml+xml'):
        result['acquisition_status'] = 'unsupported_content_type'; return result
    if args['render_mode'] == 'chrome':
        raw, browser = render(raw, final_url, chrome, work)
        result.update(browser=browser, original_rendered_html_base64=base64.b64encode(raw).decode())
        if challenge(raw): result['acquisition_status'] = 'challenge'; return result
    # All extraction is offline after acquisition; extracted text is never labelled fully read.
    result.update(bounded_extract(raw, final_url, False, work))
    return result


if __name__ == '__main__':
    if sys.argv[1] == '--extract':
        resource.setrlimit(resource.RLIMIT_AS, (768*1024*1024, 768*1024*1024))
        resource.setrlimit(resource.RLIMIT_CPU, (25, 25))
        resource.setrlimit(resource.RLIMIT_FSIZE, (8*1024*1024, 8*1024*1024))
        incoming, output = map(Path, sys.argv[2:]); p = json.loads(incoming.read_text())
        output.write_text(json.dumps(extract_document(base64.b64decode(p['raw']), p['url'], p['is_pdf'])))
        sys.exit(0)
    incoming, output = map(Path, sys.argv[1:]); p = json.loads(incoming.read_text())
    try: result = acquire(p['tool'], p['arguments'], p['chrome'], output.parent)
    except Exception as exc:
        import traceback
        (output.parent/'error.txt').write_text(traceback.format_exc())
        progress = output.parent/'progress.json'
        result = json.loads(progress.read_text()) if progress.exists() else {'rows': []}
        result.update(status='failed', error_type=type(exc).__name__, model_calls=0)
    output.write_text(json.dumps(result, ensure_ascii=False))
