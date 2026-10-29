"""Isolated network or local parser worker. Never execute source scripts or instructions."""
from __future__ import annotations
import base64
import hashlib
import http.client
import ipaddress
import json
import resource
import socket
import ssl
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urljoin
if __package__:
    from .web_sources import API_HOSTS, PUBLISHER_HOSTS, MAX_DOWNLOAD, MAX_REDIRECTS, validate_url, normalize_doi
else:
    from web_sources import API_HOSTS, PUBLISHER_HOSTS, MAX_DOWNLOAD, MAX_REDIRECTS, validate_url, normalize_doi

def _addresses(host):
    values = list(dict.fromkeys(r[4][0] for r in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)))
    if not values:
        raise ValueError('no_public_dns_address')
    for value in values:
        ip = ipaddress.ip_address(value)
        if (not ip.is_global or ip.is_multicast or ip.is_reserved or '%' in value or
            (isinstance(ip, ipaddress.IPv6Address) and (ip.ipv4_mapped or ip.sixtofour or ip.teredo))):
            raise ValueError('non_public_dns_address')
    return values

class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, 443, timeout=15, context=ssl.create_default_context())
        self.address = address
    def connect(self):
        family = socket.AF_INET6 if ipaddress.ip_address(self.address).version == 6 else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect((self.address, 443))
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
            if ipaddress.ip_address(self.sock.getpeername()[0]) != ipaddress.ip_address(self.address):
                raise ValueError('unexpected_connected_peer')
        except BaseException:
            sock.close()
            raise

def _progress(receipt):
    if __name__ == '__main__':
        print(json.dumps({'progress': receipt}), flush=True)


def fetch(payload):
    url = payload['url']; hosts = API_HOSTS if payload.get('api') else PUBLISHER_HOSTS
    receipt = {'url': url, 'retrieved_at': datetime.now(timezone.utc).isoformat(), 'access_attempts': []}
    result = {'source': receipt, 'acquisition_status': 'retrieval_failed'}
    visited = set()
    for hop in range(MAX_REDIRECTS + 1):
        conn = None
        try:
            parsed = validate_url(url, hosts)
            if url in visited:
                raise ValueError('redirect_cycle')
            visited.add(url)
            addresses = _addresses(parsed.hostname)
            conn = PinnedHTTPS(parsed.hostname, addresses[0])
            target = (parsed.path or '/') + ('?' + parsed.query if parsed.query else '')
            conn.request('GET', target, headers={'User-Agent': 'EVIDA/0.1 public-research-prototype',
                'Accept': 'text/html,application/xhtml+xml,application/json;q=0.9', 'Accept-Encoding': 'identity'})
            response = conn.getresponse()
            attempt = {'url': url, 'http_status': response.status, 'connected_ip': addresses[0],
                'content_type': response.getheader('Content-Type', ''),
                'content_encoding': response.getheader('Content-Encoding', '').lower()}
            attempt['response_complete'] = False
            receipt['access_attempts'].append(attempt)
            _progress(receipt)
            raw = response.read(MAX_DOWNLOAD + 1)
            attempt.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), response_complete=len(raw) <= MAX_DOWNLOAD)
            _progress(receipt)
            if len(raw) > MAX_DOWNLOAD:
                result['acquisition_status'] = 'download_limit'
                return result
            receipt.update({k: attempt[k] for k in ('http_status', 'content_type', 'content_encoding', 'bytes', 'sha256', 'response_complete')})
            receipt['resolved_url'] = url
            result['original_response_base64'] = base64.b64encode(raw).decode('ascii')
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location:
                    result['acquisition_status'] = 'invalid_redirect'
                    return result
                destination = urljoin(url, location); attempt['redirect_to'] = destination
                try:
                    validate_url(destination, hosts)
                except ValueError:
                    result['acquisition_status'] = 'redirect_refused'
                    return result
                if hop == MAX_REDIRECTS:
                    result['acquisition_status'] = 'redirect_limit'
                    return result
                url = destination
                # Re-resolve and pin every new hop; no Authorization/Cookie state.
                continue
            result['acquisition_status'] = ('response_received' if response.status == 200 else
                'access_denied' if response.status in (401, 403, 429) else 'http_failure')
            return result
        except Exception as exc:
            receipt['error_type'] = type(exc).__name__
            # Avoid dumping environment values, authentication data or arbitrary exception contents.
            result['acquisition_status'] = 'network_or_policy_failure'
            return result
        finally:
            if conn is not None:
                conn.close()
    return result

def extract(payload):
    raw = base64.b64decode(payload['original_response_base64'], validate=True)
    if len(raw) > MAX_DOWNLOAD:
        return {'worker_error': 'input_limit'}
    # Local extraction cannot make subresource/network requests.
    def no_network(*args, **kwargs):
        raise RuntimeError('extractor_network_disabled')
    socket.socket = no_network
    import importlib.metadata
    from lxml import html
    import trafilatura
    start = time.perf_counter(); cpu = time.process_time()
    tree = html.fromstring(raw, parser=html.HTMLParser(no_network=True, recover=True, huge_tree=False))
    title = ' '.join(' '.join(tree.xpath('//title/text()')).split())
    candidates = []
    permissions = []
    for meta in tree.xpath('//head/meta'):
        key = (meta.get('name') or meta.get('property') or '').lower()
        value = meta.get('content', '')
        if key == 'citation_doi':
            candidates.append({'field': key, 'raw': value, 'normalized': normalize_doi(value)})
        if key in ('dc.rights', 'dcterms.rights', 'copyright', 'citation_license') and value:
            permissions.append({'field': key, 'text': value})
    for link in tree.xpath('//head/link[@rel="license"]'):
        permissions.append({'field': 'link_rel_license', 'url': link.get('href', '')})
    dois = sorted({x['normalized'] for x in candidates if x['normalized']})
    invalid = any(x['normalized'] is None for x in candidates)
    identity = {'status': 'conflicting' if len(dois) > 1 else 'unique' if len(dois) == 1 and not invalid else 'unknown',
                'normalized_dois': dois, 'candidates': candidates}
    visible = ' '.join(' '.join(tree.xpath('//body//text()[not(ancestor::script) and not(ancestor::style)]')).split())
    challenge_markers = ('client challenge', 'just a moment', 'verify you are human', 'checking your browser',
                         'access denied', 'unusual traffic', 'please enable javascript to proceed', 'captcha')
    challenge = any(m in title.casefold() or (len(visible) < 12000 and m in visible.casefold()) for m in challenge_markers)
    paragraphs = [' '.join(p.text_content().split()) for p in tree.xpath('//p[not(ancestor::nav) and not(ancestor::footer) and not(ancestor::header)]')]
    substantial = [p for p in paragraphs if len(p) >= 100 and len(set(p.casefold().split())) >= 12]
    result = {'title': title, 'permissions': permissions, 'identity': identity,
        'extractor': {'name': 'trafilatura', 'version': importlib.metadata.version('trafilatura'),
                      'lxml_version': importlib.metadata.version('lxml')},
        'substantive_paragraphs': len(substantial), 'blocks': [], 'acquisition_status':
            'challenge' if challenge else 'metadata_only' if identity['status'] == 'unique' else 'insufficient_content'}
    if not challenge and len(substantial) >= 3:
        data = trafilatura.extract(raw, url=payload['url'], output_format='json', with_metadata=True,
            include_comments=False, include_tables=True, include_links=True, include_formatting=True)
        value = json.loads(data) if data else {}
        text = value.get('text', '')
        blocks = [' '.join(line.split()) for line in text.splitlines() if line.strip()]
        if len(text) >= 500 and blocks:
            result.update(acquisition_status='text_acquired', blocks=blocks)
            # This is an extractor title, not independently verified article identity.
            result['title'] = value.get('title') or title
    result['resources'] = {'wall_seconds': time.perf_counter()-start, 'cpu_seconds': time.process_time()-cpu,
        'worker_peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'limits': {'address_space_mib': 768, 'cpu_seconds': 15}}
    return result

def main():
    # Set limits before importing third-party parsers or processing input.
    resource.setrlimit(resource.RLIMIT_AS, (768*1024*1024, 768*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    payload = json.load(sys.stdin)
    try:
        result = fetch(payload) if sys.argv[1] == 'fetch' else extract(payload)
    except Exception as exc:
        result = {'worker_error': 'worker_failed', 'error_type': type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False))
if __name__ == '__main__':
    main()
