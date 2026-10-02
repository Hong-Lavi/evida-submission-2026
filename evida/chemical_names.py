"""Look up the official chemical name of a stored structure.

A candidate retrieved from ChEMBL carries an internal identifier and often a trade or research
name, but no systematic name. A screen that shows only `CHEMBL103` tells a chemist nothing about
what the molecule is, and a name invented here would be worse than none.

So the name is not generated: the stored structure string is sent to PubChem, which returns the
IUPAC name it holds for that exact structure. That is a database lookup with a CID behind it, and
the CID is kept so a reader can open the record and check. A structure PubChem does not hold comes
back unnamed rather than approximately named.

The same lookup returns PubChem's own preferred title, which is usually the common name a
researcher would recognise. Both are kept: the systematic name identifies the structure, the title
is what people say out loud.
"""
import json
import urllib.parse

ENDPOINT = ('https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/{smiles}'
            '/property/IUPACName,Title,MolecularFormula,InChIKey,CanonicalSMILES/JSON')
MAXIMUM_LOOKUPS = 40

MEANING = ('PubChem이 이 구조에 대해 보유한 이름입니다. 이 화면에서 만든 이름이 아니며, CID로 원 기록을 '
           '열어 확인할 수 있습니다. PubChem에 없는 구조는 이름 없이 남습니다.')

LIMITS = [
    'IUPAC 이름은 구조를 식별하는 체계적 명칭이며, 그 물질의 활성·안전성·가용성에 대해 아무것도 말하지 않습니다.',
    'PubChem이 반환한 구조가 조회에 쓴 구조와 다르면(염·입체 차이 등) 그 사실을 행에 남기고 이름을 붙이지 않습니다.',
    '이름을 찾지 못한 것은 그 물질이 없다는 뜻이 아니라 PubChem에 이 구조가 없다는 뜻입니다.',
]


def _request(smiles, fetch):
    url = ENDPOINT.format(smiles=urllib.parse.quote(smiles, safe=''))
    body = fetch(url)
    # The shared fetch returns (body, receipt) so every request stays recorded; accept both.
    if isinstance(body, tuple):
        body = body[0]
    if isinstance(body, bytes):
        body = body.decode('utf-8', errors='replace')
    rows = (json.loads(body).get('PropertyTable') or {}).get('Properties') or []
    return rows[0] if rows else None


def name_structures(rows, fetch, limit=MAXIMUM_LOOKUPS):
    """Attach `iupac_name` to rows that carry a structure string and lack one.

    `fetch(url) -> bytes|str` is the caller's network function, so the allowed-host check and the
    recording of each request stay where they already are. One request per distinct structure.
    """
    from .structure_depiction import row_smiles

    named, failed, seen = 0, [], {}
    for row in rows:
        if not isinstance(row, dict) or row.get('iupac_name'):
            continue
        smiles = row_smiles(row)
        if not smiles or len(seen) >= limit:
            continue
        if smiles not in seen:
            try:
                seen[smiles] = _request(smiles, fetch)
            except Exception as error:
                seen[smiles] = None
                failed.append({'smiles': smiles, 'reason': type(error).__name__})
        found = seen[smiles]
        if not found:
            continue
        # The returned structure must be the one we asked about; a redirect to a salt or a
        # different stereoisomer would name a different compound.
        returned = found.get('CanonicalSMILES')
        if isinstance(returned, str) and returned and row.get('inchikey') and found.get('InChIKey') \
                and row['inchikey'].split('-')[0] != found['InChIKey'].split('-')[0]:
            row['pubchem_structure_differs'] = {
                'requested_inchikey': row['inchikey'], 'returned_inchikey': found['InChIKey'],
                'meaning': 'PubChem이 다른 골격의 구조를 반환해 이름을 붙이지 않았습니다.'}
            continue
        if found.get('IUPACName'):
            row['iupac_name'] = found['IUPACName']
            named += 1
        if found.get('Title'):
            row['pubchem_title'] = found['Title']
        if found.get('CID'):
            row['pubchem_cid'] = found['CID']
    return {'named': named, 'looked_up': len(seen), 'lookup_failures': failed,
            'lookup_limit': limit, 'meaning': MEANING, 'limits': LIMITS}
