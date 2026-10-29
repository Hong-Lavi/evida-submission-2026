"""Select a pinned release science launcher; no execution or credential access.

Install beside start_reviewed_public_release.py only after deployment review.
A missing field preserves the historical launcher; an invalid field never does.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat


class RuntimeSelectionError(ValueError):
    pass


def _fail(message):
    raise RuntimeSelectionError(message)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail('Duplicate JSON key in runtime configuration.')
        result[key] = value
    return result


def _absolute(value):
    if not isinstance(value, (str, Path)) or not str(value):
        _fail('Runtime path must be a nonempty absolute path.')
    raw = str(value)
    path = Path(raw)
    if not path.is_absolute() or '..' in path.parts or str(path) != raw:
        _fail('Runtime path must be canonical and absolute.')
    return path


def _regular(path, area, *, maximum=4 * 1024 * 1024):
    """Check each component before reading; resolved and lexical bounds must agree."""
    path, area = _absolute(path), _absolute(area)
    if path == area or not path.is_relative_to(area):
        _fail('Runtime file is outside its reviewed area.')
    # Reject symlinks even when they point back inside the allowed area.
    for part in (*reversed(path.parents), path):
        if part.is_symlink():
            _fail('Symlinks are not permitted in reviewed control-file paths.')
    try:
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            _fail('Reviewed runtime file is not regular or exceeds the size limit.')
        if path.resolve(strict=True) != path:
            _fail('Reviewed runtime file resolves to another path.')
        data = path.read_bytes()
    except OSError as error:
        raise RuntimeSelectionError('Reviewed runtime file cannot be read.') from error
    if len(data) > maximum:
        _fail('Reviewed runtime file exceeds the size limit.')
    return data, info


def _digest(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        _fail('Runtime SHA256 must be 64 lowercase hexadecimal characters.')
    return value


def _pinned(path, area, expected):
    expected = _digest(expected)
    data, info = _regular(path, area)
    if hashlib.sha256(data).hexdigest() != expected:
        _fail('Reviewed runtime file SHA256 does not match.')
    return data, info


def _json(data):
    try:
        result = json.loads(data, object_pairs_hook=_object)
    except (ValueError, UnicodeError) as error:
        raise RuntimeSelectionError('Reviewed runtime JSON is invalid.') from error
    if not isinstance(result, dict):
        _fail('Reviewed runtime JSON must be an object.')
    return result


def _relative(root, value):
    if not isinstance(value, str) or not value:
        _fail('Runtime member path must be a nonempty relative path.')
    path = Path(value)
    if path.is_absolute() or '..' in path.parts or str(path) != value or value == '.':
        _fail('Runtime member path is not canonical and relative.')
    return root / path


def select_science_runtime(release, audit_area, legacy_python):
    """Return nonsecret, JSON-serializable selection. Never run selected files.

    audit_area is the reviewed public release area, not the whole workspace.
    Control files must be ordinary files without symlink components. The launcher's
    reviewed contents may explicitly use shared base Python/native dependencies.
    """
    release, audit_area = _absolute(release), _absolute(audit_area)
    release_data, _ = _regular(release / 'release.json', audit_area)
    config = _json(release_data)
    if 'science_runtime' not in config:
        return {'mode': 'legacy', 'executable': str(legacy_python),
                'manifest': None, 'manifest_sha256': None,
                'review_receipt': None, 'review_receipt_sha256': None,
                'fingerprint': None, 'fingerprint_sha256': None}
    value = config['science_runtime']
    fields = {'manifest', 'manifest_sha256', 'review_receipt', 'review_receipt_sha256'}
    if not isinstance(value, dict) or set(value) != fields:
        _fail('science_runtime must contain the four reviewed pin fields.')
    manifest_path = _absolute(value['manifest'])
    runtime = manifest_path.parent
    if (runtime.parent != audit_area or not runtime.name.startswith('science-runtime-')
            or runtime.name == 'science-runtime-' or manifest_path.name != 'runtime-manifest.json'):
        _fail('Runtime manifest must be inside a direct science-runtime-* audit directory.')
    manifest_data, _ = _pinned(manifest_path, runtime, value['manifest_sha256'])
    manifest = _json(manifest_data)
    if type(manifest.get('schema_version')) is not int or manifest['schema_version'] != 1:
        _fail('Unsupported science runtime manifest version.')
    review_path = _absolute(value['review_receipt'])
    if review_path != runtime / 'reviewed-runtime.json':
        _fail('Runtime review receipt must be beside its manifest.')
    review_data, _ = _pinned(review_path, runtime, value['review_receipt_sha256'])
    review = _json(review_data)
    if (type(review.get('schema_version')) is not int or review['schema_version'] != 1
            or review.get('ready') is not True
            or review.get('runtime_manifest_sha256') != value['manifest_sha256']):
        _fail('Runtime review receipt does not approve this exact manifest.')
    for name in ('launcher', 'fingerprint'):
        member = manifest.get(name)
        if not isinstance(member, dict) or not {'path', 'sha256'} <= set(member):
            _fail('Runtime manifest lacks a pinned launcher or fingerprint.')
    executable = _relative(runtime, manifest['launcher']['path'])
    _, info = _pinned(executable, runtime, manifest['launcher']['sha256'])
    if not info.st_mode & 0o111 or not os.access(executable, os.X_OK):
        _fail('Reviewed science launcher is not executable.')
    fingerprint = _relative(runtime, manifest['fingerprint']['path'])
    fingerprint_data, _ = _pinned(fingerprint, runtime, manifest['fingerprint']['sha256'])
    _json(fingerprint_data)
    return {'mode': 'reviewed', 'executable': str(executable),
            'executable_sha256': manifest['launcher']['sha256'],
            'manifest': str(manifest_path), 'manifest_sha256': value['manifest_sha256'],
            'review_receipt': str(review_path), 'review_receipt_sha256': value['review_receipt_sha256'],
            'fingerprint': str(fingerprint), 'fingerprint_sha256': manifest['fingerprint']['sha256']}
