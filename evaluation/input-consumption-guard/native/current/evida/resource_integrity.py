"""Verify frozen scientific assets before computation or reuse of a cached result."""
import hashlib
from pathlib import Path


def signature(path):
    s = path.stat()
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def _verified(path_string, expected, before):
    path = Path(path_string)
    with path.open('rb') as f:
        h = hashlib.sha256()
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
        digest = h.hexdigest()
    if signature(path) != before:
        raise ValueError('검사 중 과학 자료 파일이 변경됐습니다. 실행하지 않았습니다.')
    if digest != expected:
        raise ValueError('과학 자료 파일 해시가 고정된 원자료와 다릅니다: '+path.name)
    return digest


def verify_file(path, expected):
    path = Path(path).resolve(strict=True)
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError('원자료 해시가 준비되지 않았습니다.')
    # Filesystem timestamps can have coarse resolution. Matching stat values
    # alone do not prove content identity, including for a result-cache hit.
    return _verified(str(path), expected, signature(path))


def verify_resources(cfg, tool):
    pairs = []
    if tool in ('rna_reference_archive', 'rna_transcriptome_search'):
        ref = cfg['reference']
        pairs += [(ref['annotations'], ref['annotations_sha256'])]
        if tool == 'rna_reference_archive':
            pairs += [(ref['fasta'], ref['fasta_sha256'])]
        else:
            r = cfg['risearch']
            pairs += [(r['binary'], r['binary_sha256']), (r['index'], r['index_sha256'])]
    elif tool == 'rna_activity_score':
        r = cfg['activity']
        pairs += [(r[name], r[name+'_sha256']) for name in ('weights', 'rna_fm_head', 'sequence3mer_head')]
    elif tool == 'rna_seed_sites':
        r=cfg['seed_sites']
        pairs += [(r[name],r[name+'_sha256']) for name in ('database','fasta','expression')]
        pairs += [(Path(__file__).parent/'vendor/seedmatchr/get_seed.R',r['author_get_seed_sha256'])]
    return {Path(path).name: verify_file(path, digest) for path, digest in pairs}
