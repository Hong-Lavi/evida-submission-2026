"""Mechanical search-scope diagnostics; never a scientific relevance/truth judge.

Preserves all returned hits. Recognizes simple unquoted site:host[/path] terms.
Quoted phrases/complex boolean semantics remain unassessed. Positive-site union is
conservative: a hit outside every named site cannot satisfy any such positive term.
"""
import re
from urllib.parse import parse_qs, urlsplit


def _scope(value):
    value=value.rstrip('.,;')
    if '://' in value or any(c in value for c in '?@#*\\'):
        return None
    try:
        p=urlsplit('https://'+value)
        if not p.hostname or p.port is not None:
            return None
        host=p.hostname.rstrip('.').encode('idna').decode().casefold()
        if not re.fullmatch(r'[a-z0-9.-]+',host) or '.' not in host:
            return None
        return {'host':host,'path':p.path.rstrip('/')}
    except (ValueError,UnicodeError):return None


def site_terms(query):
    # Quoted text is literal query content; do not invent operator semantics for it.
    unquoted=re.sub(r'"[^"\n]*"|\'[^\'\n]*\'', ' ', query)
    positive=[];negative=[]
    for m in re.finditer(r'(?<!\S)(-?)site:([^\s()]+)',unquoted,re.I):
        scope=_scope(m.group(2))
        if scope is not None:
            target=negative if m.group(1) else positive
            if scope not in target:target.append(scope)
    return positive,negative


def _matches(url,scope):
    try:
        p=urlsplit(url)
        host=(p.hostname or '').rstrip('.').encode('idna').decode().casefold()
        host_ok=host==scope['host'] or host.endswith('.'+scope['host'])
        path=scope['path']
        return host_ok and (not path or p.path==path or p.path.startswith(path+'/'))
    except (TypeError,ValueError,UnicodeError):return False


def assess_search_scope(query,rows,*,echoed_query=None):
    positive,negative=site_terms(query)
    assessed=bool(positive or negative)
    checks=[]
    for index,row in enumerate(rows):
        url=row.get('url')
        positive_match=any(_matches(url,s) for s in positive) if positive else None
        negative_match=any(_matches(url,s) for s in negative)
        checks.append({'row_index':index,'in_any_positive_site':positive_match,
                       'in_excluded_site':negative_match,
                       'explicit_site_scope_match':((not positive or positive_match) and not negative_match)
                                                   if assessed else None})
    matched=sum(c['explicit_site_scope_match'] is True for c in checks) if assessed else None
    echo_status='not_available' if echoed_query is None else 'matches' if echoed_query==query else 'mismatch'
    status=('not_assessed_no_simple_site_operator' if not assessed else
            'no_hits_returned_scope_unassessable' if not rows else
            'no_returned_hit_in_explicit_site_scope' if matched==0 else
            'partial_explicit_site_scope_match' if matched<len(rows) else 'all_returned_hits_in_explicit_site_scope')
    return {'explicit_site_scope_status':status,'returned_hits':len(rows),
            'explicit_site_scope_matches':matched,'positive_site_terms':positive,'negative_site_terms':negative,
            'response_query_echo_status':echo_status,'row_scope_checks':checks,
            'scientific_relevance':'not_assessed','scientific_truth':'not_assessed',
            'all_returned_rows_preserved':True,
            'scope':'Mechanical URL/site and optional query-echo check only; positive sites use conservative union. '
                    'Matching a site does not establish topical relevance, study identity, claim support or scientific validity.'}
