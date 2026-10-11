"""Retrieve the figures of an open-access article the research already read.

The article record keeps each `fig` block with its caption, its anchor in the source, and the
file names the publisher used, but not the images. Europe PMC serves those files from the same
allowlisted host the article itself came from, through the shared `fetch` guard.

What this does NOT do: it never looks for a figure the record does not name, never substitutes a
different file, and never changes the stored article. The caption and the source anchor stay the
evidence; a picture is a convenience for the reader.
"""
import hashlib
import json
import re
import struct
import zlib
from datetime import datetime, timezone
from pathlib import Path

HREF = '{http://www.w3.org/1999/xlink}href'
IMAGE_SUFFIXES = ('.jpg', '.jpeg', '.png', '.gif', '.tif', '.tiff')
MEDIA = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif'}
ENDPOINT = 'https://www.ebi.ac.uk/europepmc/webservices/rest/{pmc}/supplementaryFiles?includeInlineImage=true'


def figure_rows(value):
    """Figure blocks of a stored article, with the file names the publisher declared."""
    rows = value.get('rows') if isinstance(value.get('rows'), list) else []
    figures = []
    for row in rows:
        if not isinstance(row, dict) or row.get('kind') != 'fig':
            continue
        files, thumbs = [], []
        for asset in row.get('asset_references') or []:
            name = (asset or {}).get(HREF) or (asset or {}).get('href')
            if not isinstance(name, str) or not name.lower().endswith(IMAGE_SUFFIXES):
                continue
            (thumbs if (asset or {}).get('content-type') == 'thumb' else files).append(name)
        if files or thumbs:
            figures.append({'xml_id': row.get('xml_id'), 'section': row.get('section'),
                            'caption': row.get('text'), 'source_url': row.get('source_url'),
                            'files': files, 'thumbnails': thumbs})
    return figures


_DESCRIPTOR = b'PK\x07\x08'


def _recorded_crc(blob, data_end, header_crc):
    """The entry's CRC: in the local header, or in the trailing descriptor when it was streamed."""
    if header_crc:
        return header_crc
    tail = blob[data_end:data_end + 16]
    if tail[:4] == _DESCRIPTOR:
        tail = tail[4:]
    return struct.unpack('<I', tail[:4])[0] if len(tail) >= 4 else None


def _entries(blob, wanted=None, max_entry_bytes=4 * 1024 * 1024, max_total_bytes=16 * 1024 * 1024):
    """Read a streamed zip: the sizes sit in trailing descriptors, so scan local headers.

    Nothing about that scan proves an entry is whole. `PK\\x03\\x04` also occurs inside compressed
    data, a truncated deflate stream decompresses without raising, and a stored entry whose size
    is only in the descriptor would otherwise swallow whatever follows it. So each entry is read
    to the end of the blob, the deflate stream must report that it ended, and the result is
    checked against the recorded CRC32. An entry that fails is dropped: a partial figure that
    reports itself as retrieved is worse than a missing one.
    """
    starts, index = [], 0
    while True:
        index = blob.find(b'PK\x03\x04', index)
        if index < 0:
            break
        starts.append(index)
        index += 4
    found, total_bytes = {}, 0
    for head in starts:
        if head + 30 > len(blob):
            continue
        (_, method, _, _, header_crc, csize, _,
         name_length, extra) = struct.unpack('<HHHHIIIHH', blob[head + 6:head + 30])
        name = blob[head + 30:head + 30 + name_length].decode('latin1')
        if wanted is not None and name not in wanted:
            continue
        start = head + 30 + name_length + extra
        body = blob[start:]
        try:
            if method == 8:
                stream = zlib.decompressobj(-15)
                data = stream.decompress(body, max_entry_bytes + 1)
                if len(data) > max_entry_bytes or not stream.eof:
                    continue  # cut short: decompressing a partial stream does not raise
                data_end = start + len(body) - len(stream.unused_data)
            elif method == 0:
                size = csize if csize else body.find(_DESCRIPTOR)
                if size < 0 or size > max_entry_bytes:
                    continue  # neither a recorded size nor a descriptor: the extent is unknown
                data, data_end = body[:size], start + size
            else:
                continue
        except zlib.error:
            continue  # a truncated or unsupported entry must not lose the others
        recorded = _recorded_crc(blob, data_end, header_crc)
        if recorded is None or zlib.crc32(data) != recorded:
            continue  # a false header match inside file data lands here too
        if total_bytes + len(data) > max_total_bytes:
            continue
        found[name] = data
        total_bytes += len(data)
    return found


def media_type(name):
    return MEDIA.get(Path(name).suffix.lower(), 'application/octet-stream')


def cache_name(pmc_id, filename):
    key = hashlib.sha256(f'{pmc_id}/{filename}'.encode()).hexdigest()[:40]
    return f'{key}{Path(filename).suffix.lower()}'


def fetch_figures(pmc_id, wanted, cache_dir, fetch):
    """Download the named files once and cache them. Returns a record of what was retrieved.

    The response is a streamed archive that can arrive truncated for a large article; files that
    do arrive are kept and the rest are reported missing rather than guessed at.
    """
    if not re.fullmatch(r'PMC\d+', str(pmc_id or '')):
        raise ValueError('PMC 식별자를 확인해 주세요.')
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    needed = [name for name in dict.fromkeys(wanted)
              if not (cache / cache_name(pmc_id, name)).exists()]
    retrieved, missing = {}, []
    source = None
    if needed:
        # science.fetch returns (body, provenance); keep the provenance in the record.
        blob, source = fetch(ENDPOINT.format(pmc=pmc_id))
        available = _entries(blob, set(needed))
        for name in needed:
            data = available.get(name)
            if not data:
                missing.append(name)
                continue
            path = cache / cache_name(pmc_id, name)
            temporary = path.with_suffix(path.suffix + '.tmp')
            temporary.write_bytes(data)
            temporary.replace(path)
            retrieved[name] = data
    record = []
    for name in dict.fromkeys(wanted):
        path = cache / cache_name(pmc_id, name)
        if path.exists():
            data = path.read_bytes()
            record.append({'file': name, 'bytes': len(data), 'media_type': media_type(name),
                           'sha256': hashlib.sha256(data).hexdigest(),
                           'cached_as': path.name,
                           'newly_retrieved': name in retrieved})
        elif name not in missing:
            missing.append(name)
    return {'pmc_id': pmc_id, 'files': record, 'not_returned': missing,
            'source': source or {'url': ENDPOINT.format(pmc=pmc_id), 'note': 'all files already cached'},
            'meaning': 'Figure images of an article already read, retrieved from the same public '
                       'host. Not returned means the archive did not contain the file in this '
                       'response, which is not a statement about the article.'}


def retrieve_for_article(value, cache_dir, fetch, maximum_figures=8):
    """One bounded archive attempt per article version, including failed attempts.

    Only exact declared image filenames qualify. No silent retry after failure or
    interruption. This auxiliary result never changes native XML or article status.
    """
    pmc_id = value.get('pmc_id')
    figures = figure_rows(value)
    wanted = []
    for figure in figures[:maximum_figures]:
        names = [n for n in figure['files'] + figure['thumbnails'] if media_type(n).startswith('image/')]
        if names:
            wanted.append(names[0])
    wanted = list(dict.fromkeys(wanted))
    base = {'pmc_id': pmc_id, 'requested_files': wanted,
            'declared_figures': len(figures), 'maximum_figures': maximum_figures,
            'automatic_retry': False, 'visual_interpretation': False,
            'meaning': '원문이 명시한 그림·캡션·위치의 회수 기록입니다. 이미지 해석과 과학적 검증은 별도입니다.'}
    if not wanted:
        return {**base, 'status': 'no_declared_browser_image', 'files': [], 'not_returned': []}
    try:
        cache = Path(cache_dir)
        cache.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(json.dumps([pmc_id, value.get('original_xml'), wanted],
                                        ensure_ascii=False).encode()).hexdigest()
        receipt = cache / f'article-{key}.json'
        try:
            with receipt.open('x') as stream:
                json.dump({**base, 'status': 'started', 'files': [], 'not_returned': wanted,
                           'started_at': datetime.now(timezone.utc).isoformat()}, stream, ensure_ascii=False)
        except FileExistsError:
            return {**json.loads(receipt.read_text()), 'reused_receipt': True}
        try:
            result = fetch_figures(pmc_id, wanted, cache, fetch)
            status = 'succeeded' if not result['not_returned'] else 'partial' if result['files'] else 'not_returned'
            record = {**base, **result, 'status': status}
        except Exception as exc:
            record = {**base, 'status': 'failed', 'files': [], 'not_returned': wanted,
                      'error_type': type(exc).__name__, 'error': str(exc)[:500]}
        record['completed_at'] = datetime.now(timezone.utc).isoformat()
        temporary = receipt.with_suffix('.tmp')
        temporary.write_text(json.dumps(record, ensure_ascii=False))
        temporary.replace(receipt)
        return record
    except Exception as exc:
        return {**base, 'status': 'cache_error', 'files': [], 'not_returned': wanted,
                'error_type': type(exc).__name__, 'error': str(exc)[:500]}


def index_for(value, pmc_id, cache_dir):
    """What the screen needs: caption, anchor and whether the image is cached."""
    cache = Path(cache_dir)
    figures = []
    for figure in figure_rows(value):
        files = [{'file': name, 'cached': (cache / cache_name(pmc_id, name)).exists(),
                  'media_type': media_type(name)}
                 for name in (figure['files'] + figure['thumbnails'])]
        figures.append({**figure, 'available': files})
    return figures


def load(pmc_id, filename, cache_dir):
    path = Path(cache_dir) / cache_name(pmc_id, filename)
    if not path.is_file():
        raise KeyError(filename)
    return path.read_bytes(), media_type(filename)
