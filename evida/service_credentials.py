"""Owner-only, file-backed service credentials; never export keys to model workers."""
from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path
import stat
import sys
import tempfile

SERVICES = {
    "typesafe": "TYPESAFE_API_KEY_FILE",
    "opengwas": "OPENGWAS_JWT_FILE",
    "clue": "CLUE_API_KEY_FILE",
    "lens": "LENS_API_TOKEN_FILE",
    "gtopdb": "GTOPDB_API_KEY_FILE",
}
DEFAULT_DIRECTORY = Path.home() / ".config" / "evida" / "credentials"
REPOSITORY = Path(__file__).resolve().parents[1]


class CredentialError(RuntimeError):
    pass


def private_directory(directory: Path, *, create: bool = False) -> Path:
    directory = directory.expanduser().absolute()
    if directory.resolve().is_relative_to(REPOSITORY):
        raise CredentialError("Credentials must be stored outside the research repository.")
    if create:
        old = os.umask(0o077)
        try:
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        finally:
            os.umask(old)
    try:
        info = directory.lstat()
    except OSError:
        raise CredentialError("Credential directory is not available.") from None
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o077):
        raise CredentialError("Credential directory must be owned by this user with mode 700.")
    return directory


def validate_secret(value: str) -> str:
    value = value.strip()
    if not 12 <= len(value) <= 16384 or any(c.isspace() or not c.isprintable() for c in value):
        raise CredentialError("Expected one non-empty token, without spaces or line breaks.")
    return value


def save_secret(service: str, value: str, directory: Path = DEFAULT_DIRECTORY, *, replace: bool = False) -> Path:
    if service not in SERVICES:
        raise CredentialError("Unknown service.")
    value = validate_secret(value)
    directory = private_directory(directory, create=True)
    path = directory / (service + ".key")
    if replace:
        if path.exists() or path.is_symlink():
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077):
                raise CredentialError("Unsafe existing credential was preserved.")
        fd, temporary_name = tempfile.mkstemp(prefix=".credential-", dir=directory)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(value + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        return path
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        raise CredentialError("An existing credential was preserved; no overwrite was made.") from None
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def credential_path(service: str, directory: Path = DEFAULT_DIRECTORY) -> Path:
    if service not in SERVICES:
        raise CredentialError("Unknown service.")
    configured = os.environ.get(SERVICES[service])
    return Path(configured).expanduser() if configured else directory / (service + ".key")


def read_secret(service: str, directory: Path = DEFAULT_DIRECTORY) -> str:
    path = credential_path(service, directory).absolute()
    private_directory(path.parent)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        raise CredentialError("Credential file is missing or cannot be opened safely.") from None
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077
                or info.st_size > 16385):
            raise CredentialError("Credential file must be a private, owner-only regular file.")
        raw = handle.read(16386)
    try:
        return validate_secret(raw.decode("utf-8"))
    except UnicodeError:
        raise CredentialError("Credential file encoding is invalid.") from None


def main() -> int:
    parser = argparse.ArgumentParser(description="Store service API credentials without displaying them.")
    parser.add_argument("services", nargs="*", choices=list(SERVICES))
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    parser.add_argument("--replace", action="store_true", help="Explicitly replace only the named service credentials.")
    args = parser.parse_args()
    if args.replace and not args.services:
        parser.error("Name the service(s) to replace; implicit replacement of all keys is disabled.")
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        parser.error("Run in an interactive terminal. Piped or echoed secret input is disabled.")
    try:
        directory = private_directory(args.directory, create=True)
        print("키는 화면에 표시되지 않습니다. 서비스별로 붙여넣고 Enter를 누르세요. 빈 입력은 건너뜁니다.")
        for service in args.services or list(SERVICES):
            if (directory / (service + ".key")).exists() and not args.replace:
                print(service + ": 기존 파일 보존")
                continue
            value = getpass.getpass(service + " 키 (숨김): ")
            if not value.strip():
                print(service + ": 건너뜀")
                continue
            path = save_secret(service, value, directory, replace=args.replace)
            del value
            print(service + ": 저장 완료 → " + str(path))
        print("저장 절차 완료. 키 값을 채팅에 보내지 말고 ‘저장 완료’라고 알려주세요.")
    except (CredentialError, KeyboardInterrupt, EOFError) as exc:
        print(str(exc) if isinstance(exc, CredentialError) else "입력이 중단되었습니다. 저장된 키는 유지됩니다.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
