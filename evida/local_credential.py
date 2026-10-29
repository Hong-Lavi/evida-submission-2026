"""Owner-only local-launch credential. Values stay in the product process memory."""
import os
from pathlib import Path
import stat

FORBIDDEN_ENVIRONMENT = ('EVIDA_COMPETITION_API_KEY', 'OPENAI_API_KEY', 'CODEX_API_KEY',
                         'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_BASE_URL')


def reject_credential_environment():
    # Check presence only; never read, copy, return or print an environment secret.
    if any(name in os.environ for name in FORBIDDEN_ENVIRONMENT):
        raise ValueError('Local launch requires an owner-only credential file; credential/provider environment overrides are excluded.')


def _check(info, *, directory=False):
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if (not expected(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077
            or (not directory and not 0 < info.st_size <= 8192)):
        raise ValueError('Credential file and its directory must be owner-only regular resources of bounded size.')


def inspect_owner_credential(path):
    """Metadata only: no file body is read by --check."""
    path = Path(path)
    _check(path.parent.stat(follow_symlinks=False), directory=True)
    _check(path.stat(follow_symlinks=False))
    return path


def read_owner_credential(path):
    """Revalidate opened descriptors, reject symlinks and never expose a value in errors."""
    path = inspect_owner_credential(path)
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        _check(os.fstat(parent), directory=True)
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            _check(os.fstat(fd))
            raw = os.read(fd, 8193)
        finally:
            os.close(fd)
    finally:
        os.close(parent)
    if len(raw) > 8192:
        raise ValueError('Credential format is invalid; value withheld.')
    try:
        value = raw.decode('ascii').strip()
    except UnicodeError:
        raise ValueError('Credential format is invalid; value withheld.') from None
    if not value or not all(33 <= ord(c) <= 126 for c in value):
        raise ValueError('Credential format is invalid; value withheld.')
    return value
