"""Private, file-backed CLI attempts with a detached, bounded recorder process.

No model API, scheduler or retry lives here. Reconnecting observes the same
attempt, including its original deadline. Credentials are removed before disk;
the original byte hash and explicit omissions distinguish derivatives from raw.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, BinaryIO, Callable, Iterator, Mapping

from lavi_research_os.io import atomic_write_json, atomic_write_text, read_json
from lavi_research_os.models import utc_now


RECORDING_CONTRACT = "private-cli-attempt-v1"
MAX_PARSE_BYTES = 4 * 1024 * 1024
_DIRECTORY: ContextVar[Path | None] = ContextVar("lros_attempt_directory", default=None)
_SECRET = re.compile(
    rb"(?i)(?:\b(?:sk-(?:ant-)?|gh[pousr]_|github_pat_|eyJ)[A-Za-z0-9_.-]{8,}"
    rb"|\b(?:bearer)[ \t]+[^\s\"',}]+"
    rb"|[\"']?(?:access_token|refresh_token|oauth_token|api_key|authorization|password|client_secret|CLAUDE_CODE_OAUTH_TOKEN)[\"']?\s*[:=]\s*[\"']?[^\s\"',}]+)"
)


def redact_bytes(value: bytes, secrets: tuple[bytes, ...] = ()) -> tuple[bytes, int]:
    count = 0
    for secret in secrets:
        if len(secret) >= 8 and secret in value:
            count += value.count(secret)
            value = value.replace(secret, b"[REDACTED]")
    value, found = _SECRET.subn(b"[REDACTED]", value)
    return value, count + found


def process_identity(pid: int) -> dict[str, Any]:
    identity: dict[str, Any] = {"pid": pid, "host": socket.gethostname()}
    try:
        identity["boot_id"] = (
            Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        )
        identity["pid_namespace"] = os.stat(f"/proc/{pid}/ns/pid").st_ino
        stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        identity["start_ticks"] = stat[19]
        identity["state"] = stat[0]
    except (OSError, IndexError):
        identity["state"] = "UNOBSERVABLE"
    return identity


def process_state(recorded: Mapping[str, Any]) -> str:
    observer = process_identity(os.getpid())
    if any(
        recorded.get(k) != observer.get(k) for k in ("host", "boot_id", "pid_namespace")
    ):
        return "UNOBSERVABLE"
    current = process_identity(int(recorded["pid"]))
    if current.get("state") == "UNOBSERVABLE":
        return "NOT_PRESENT_IN_OBSERVED_NAMESPACE"
    if current.get("start_ticks") != recorded.get("start_ticks"):
        return "PID_REUSED"
    return "EXITED" if current.get("state") == "Z" else "RUNNING"


@contextmanager
def provider_workspace(directory: Path, *, prefix: str = "lros-call-") -> Iterator[str]:
    """The provider sees an empty workspace; recorder artifacts stay outside it."""
    directory = directory.resolve()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    # Persist the workspace name so a lost coordinator reconnects with identical
    # argv and stdin paths. Do not auto-remove workspaces on task disconnect.
    with (directory / "workspace.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = directory / "workspace.json"
        if path.exists():
            workspace = str(read_json(path)["path"])
        else:
            workspace = tempfile.mkdtemp(prefix=prefix)
            atomic_write_json(path, {"path": workspace})
    token = _DIRECTORY.set(directory)
    try:
        yield workspace
    finally:
        _DIRECTORY.reset(token)


@dataclass(frozen=True)
class RecordedProcess:
    returncode: int
    directory: Path
    report: Mapping[str, Any]

    @property
    def stdout(self) -> str:
        return bounded_text(self.directory / "stdout.bin")

    @property
    def stderr(self) -> str:
        return bounded_text(self.directory / "stderr.bin")


def bounded_text(path: Path, limit: int = MAX_PARSE_BYTES) -> str:
    if not path.is_file():
        return ""
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        return ""  # never silently treat a chopped record as a complete response
    return data.decode("utf-8", errors="replace")


def attempt_directory(workspace: Path) -> Path:
    return (_DIRECTORY.get() or workspace / ".lros-attempt").resolve()


def record_no_call(workspace: Path, *, reason: str, profile: Mapping[str, Any]) -> None:
    root = attempt_directory(workspace)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not (root / "start.json").exists():
        atomic_write_json(
            root / "no-call.json",
            {
                "attempt_number": 0,
                "execution_status": "NO_CALL",
                "reason": reason,
                "profile_sha256": hashlib.sha256(
                    json.dumps(profile, sort_keys=True).encode()
                ).hexdigest(),
                "observed_at": utc_now(),
            },
        )


def run_recorded(
    command: list[str],
    *,
    input: str,
    timeout: float | None,
    cwd: Path,
    env: Mapping[str, str],
    profile: Mapping[str, Any] | None = None,
    extra_output: Path | None = None,
) -> RecordedProcess:
    """Launch once or reattach. Never reset the attempt's deadline or budget."""
    root = attempt_directory(cwd)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    prompt = input.encode()
    secrets = tuple(
        v.encode()
        for k, v in env.items()
        if re.search(r"TOKEN|SECRET|PASSWORD|KEY", k) and v
    )
    command_json = json.dumps(command, ensure_ascii=False).encode()
    if redact_bytes(prompt, secrets)[1] or redact_bytes(command_json, secrets)[1]:
        record_no_call(cwd, reason="CREDENTIAL_IN_INPUT", profile=profile or {})
        raise ValueError("credential-shaped input cannot be persisted or sent")
    request = {
        "command": command,
        "input_sha256": hashlib.sha256(prompt).hexdigest(),
        "input_bytes": len(prompt),
        "timeout_seconds": timeout,
        "profile": dict(profile or {}),
        "cwd": str(cwd),
        "extra_output": str(extra_output) if extra_output else None,
    }
    request_hash = hashlib.sha256(
        json.dumps(request, sort_keys=True).encode()
    ).hexdigest()
    worker: subprocess.Popen[bytes] | None = None
    with (root / "launch.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (root / "start.json").exists():
            if read_json(root / "start.json")["request_sha256"] != request_hash:
                raise ValueError(
                    "recorded attempt request changed; refusing duplicate call"
                )
        else:
            now = time.time()
            safe_argv = [
                f"<json-schema sha256={hashlib.sha256(arg.encode()).hexdigest()} bytes={len(arg.encode())}>"
                if i and command[i - 1] == "--json-schema"
                else arg
                for i, arg in enumerate(command)
            ]
            atomic_write_json(
                root / "start.json",
                {
                    "contract": RECORDING_CONTRACT,
                    "request_sha256": request_hash,
                    "profile_sha256": hashlib.sha256(
                        json.dumps(profile or {}, sort_keys=True).encode()
                    ).hexdigest(),
                    "input_sha256": request["input_sha256"],
                    "input_bytes": len(prompt),
                    "argv_sha256": hashlib.sha256(command_json).hexdigest(),
                    "safe_argv": safe_argv,
                    "started_at": utc_now(),
                    "deadline_unix": None if timeout is None else now + timeout,
                    "timeout_seconds": timeout,
                    "coordinator": process_identity(os.getpid()),
                    "artifacts": {
                        name: str(root / name)
                        for name in (
                            "stdout.bin",
                            "stderr.bin",
                            "last-message.bin",
                            "terminal.json",
                        )
                    },
                },
            )
            atomic_write_text(root / "input.txt", input)
            atomic_write_json(root / "request.json", request)
            worker_env = dict(env)
            source = '/data/user_home/hsm927/projects/EVIDA_finals_research_2026/audit/evida-ten-hour-improvement-20260928-78/lros-runtime/engine/src'
            worker_env["PYTHONPATH"] = (
                source + os.pathsep + worker_env.get("PYTHONPATH", "")
            )
            try:
                worker = subprocess.Popen(
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        str(root),
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=worker_env,
                    start_new_session=True,
                )
                atomic_write_json(root / "worker.json", process_identity(worker.pid))
            except OSError as exc:
                atomic_write_json(
                    root / "terminal.json",
                    {
                        "execution_status": "START_FAILED",
                        "returncode": None,
                        "os_errno": exc.errno,
                        "finished_at": utc_now(),
                    },
                )
    try:
        while not (root / "terminal.json").exists():
            if (root / "worker.json").exists():
                state = process_state(read_json(root / "worker.json"))
                if state != "RUNNING":
                    # terminal is published before the worker exits. It may have
                    # appeared between the loop test and the process observation.
                    # Re-read after that observation before declaring loss.
                    if (root / "terminal.json").is_file():
                        break
                    return RecordedProcess(
                        -1,
                        root,
                        {
                            "execution_status": "RECORDER_UNOBSERVABLE",
                            "process_state": state,
                            "recording_directory": str(root),
                            "returncode": None,
                        },
                    )
            else:
                # An interruption between claim and worker launch never licenses
                # an automatic second invocation.
                return RecordedProcess(
                    -1,
                    root,
                    {
                        "execution_status": "LAUNCH_UNCONFIRMED",
                        "recording_directory": str(root),
                        "returncode": None,
                    },
                )
            time.sleep(0.05)
    except KeyboardInterrupt:
        atomic_write_json(root / "cancel.json", {"requested_at": utc_now()})
        deadline = time.monotonic() + 10
        while not (root / "terminal.json").exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not (root / "terminal.json").exists():
            raise
    if worker is not None:
        worker.wait()
    report = dict(read_json(root / "terminal.json"))
    expected_streams = {"stdout", "stderr"} | ({"last-message"} if extra_output else set())
    if report.get("returncode") is not None and not expected_streams <= set(
        report.get("streams", {})
    ):
        report["execution_status"] = "RECORDING_INCOMPLETE"
        report["integrity_error"] = "STREAM_MANIFEST_MISSING"
    for name, manifest in report.get("streams", {}).items():
        path = root / f"{name}.bin"
        if not path.is_file() or _file_digest(path) != manifest.get("stored_sha256"):
            report["execution_status"] = "RECORDING_INCOMPLETE"
            report["integrity_error"] = "STREAM_HASH_MISMATCH"
        if manifest.get("oversized_lines_omitted", 0):
            report["execution_status"] = "RECORDING_INCOMPLETE"
            report["integrity_error"] = "OVERSIZED_RECORD_OMITTED"
    report["recording_directory"] = str(root)
    return RecordedProcess(
        int(report["returncode"]) if report.get("returncode") is not None else -1,
        root,
        report,
    )


def _record_stream(
    stream: BinaryIO,
    path: Path,
    secrets: tuple[bytes, ...],
    stop: threading.Event | None = None,
    on_record: Callable[[bytes], None] | None = None,
) -> None:
    digest = hashlib.sha256()
    size = omissions = oversized = 0
    buffer = bytearray()
    # Bounded logical lines allow credential matches across read boundaries.
    # Oversized lines are hashed but omitted in full, never partially redacted.
    dropping = False
    with path.open("wb") as output:
        os.chmod(path, 0o600)
        while True:
            if stop is not None and not select.select([stream], [], [], 0.05)[0]:
                if stop.is_set():
                    break
                continue
            chunk = os.read(stream.fileno(), 65536)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
            for piece in chunk.splitlines(keepends=True):
                ended = piece.endswith(b"\n")
                if not dropping:
                    buffer.extend(piece)
                    if len(buffer) > MAX_PARSE_BYTES:
                        buffer.clear()
                        dropping = True
                        oversized += 1
                if ended:
                    if dropping:
                        output.write(b"[OMITTED_OVERSIZED_LINE]\n")
                    else:
                        safe, count = redact_bytes(bytes(buffer), secrets)
                        omissions += count
                        output.write(safe)
                        if on_record is not None:
                            on_record(bytes(buffer))
                    buffer.clear()
                    dropping = False
                    output.flush()
        if buffer:
            safe, count = redact_bytes(bytes(buffer), secrets)
            omissions += count
            output.write(safe)
        elif dropping:
            output.write(b"[OMITTED_OVERSIZED_LINE]\n")
        output.flush()
        os.fsync(output.fileno())
    atomic_write_json(
        path.with_suffix(".manifest.json"),
        {
            "original_sha256": digest.hexdigest(),
            "original_bytes": size,
            "stored_sha256": _file_digest(path),
            "credential_redactions": omissions,
            "oversized_lines_omitted": oversized,
            "representation": "redacted_derivative"
            if omissions or oversized
            else "original_bytes",
        },
    )


def _file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _worker(root: Path) -> None:
    os.umask(0o077)
    with (root / "worker.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        request = read_json(root / "request.json")
        start = read_json(root / "start.json")
        secrets = tuple(
            v.encode()
            for k, v in os.environ.items()
            if re.search(r"TOKEN|SECRET|PASSWORD|KEY", k) and v
        )
        stop = threading.Event()
        output_limit = threading.Event()
        output_limit_evidence: dict[str, Any] = {}

        def inspect_control(line: bytes) -> None:
            from lavi_research_os.providers.output_limits import claude_output_limit_event
            if output_limit.is_set():
                return
            observed = claude_output_limit_event(line)
            if observed is not None:
                output_limit_evidence.update(observed)
                output_limit_evidence['observed_at'] = utc_now()
                output_limit.set()

        guard_claude = request.get('profile', {}).get('provider_id') == 'anthropic-claude'
        threads: list[threading.Thread] = []
        fifo: BinaryIO | None = None
        extra = Path(request["extra_output"]) if request.get("extra_output") else None
        terminal: dict[str, Any] = {
            "execution_status": "START_FAILED",
            "returncode": None,
        }
        child: subprocess.Popen[bytes] | None = None
        try:
            if (
                hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
                != start["request_sha256"]
                or _file_digest(root / "input.txt") != start["input_sha256"]
            ):
                terminal["execution_status"] = "RECORDING_INCOMPLETE"
                terminal["integrity_error"] = "REQUEST_HASH_MISMATCH"
                return
            if extra:
                os.mkfifo(extra, 0o600)
                fifo = os.fdopen(
                    os.open(extra, os.O_RDWR | os.O_NONBLOCK), "rb", buffering=0
                )
                thread = threading.Thread(
                    target=_record_stream,
                    args=(fifo, root / "last-message.bin", secrets, stop),
                )
                thread.start()
                threads.append(thread)
            with (root / "input.txt").open("rb") as stdin:
                child = subprocess.Popen(
                    request["command"],
                    stdin=stdin,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=request["cwd"],
                    start_new_session=True,
                )
            identity = process_identity(child.pid)
            atomic_write_json(root / "provider-process.json", identity)
            for stream, name in (
                (child.stdout, "stdout.bin"),
                (child.stderr, "stderr.bin"),
            ):
                assert stream is not None
                thread = threading.Thread(
                    target=_record_stream, args=(stream, root / name, secrets),
                    kwargs={'on_record': inspect_control if guard_claude and name == 'stdout.bin' else None},
                )
                thread.start()
                threads.append(thread)
            status = "EXITED"
            # WNOWAIT observes completion without reaping the group leader.
            # Its PID cannot be reused before the owned group is cleaned up.
            while (
                os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                is None
            ):
                cancelled = (root / "cancel.json").exists()
                expired = start["deadline_unix"] is not None and time.time() >= start["deadline_unix"]
                limited = output_limit.is_set()
                if cancelled or expired or limited:
                    status = "OUTPUT_LIMIT" if limited else "CANCELLED" if cancelled else "TIMEOUT"
                    # Child has not been reaped: its PID/group cannot be reused.
                    os.killpg(child.pid, signal.SIGTERM)
                    time.sleep(0.1)
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    break
                time.sleep(0.05)
            # Kill any surviving members of the owned process group. No provider
            # process may outlive a completed attempt and keep pipes open.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            terminal = {"execution_status": status, "returncode": child.wait()}
        except OSError as exc:
            terminal["os_errno"] = exc.errno
            terminal["limit_kind"] = "ARGV_LIMIT" if exc.errno == errno.E2BIG else None
        finally:
            # An I/O failure after launch must not leave an owned child alive.
            # A non-None returncode means this worker already reaped that PID.
            if child is not None and child.returncode is None:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                terminal["returncode"] = child.wait()
            stop.set()
            for thread in threads:
                thread.join(timeout=5)
            if any(thread.is_alive() for thread in threads):
                terminal["execution_status"] = "RECORDING_INCOMPLETE"
            if output_limit.is_set():
                if terminal['execution_status'] != 'RECORDING_INCOMPLETE':
                    terminal['execution_status'] = 'OUTPUT_LIMIT'
                terminal['limit_kind'] = 'PROVIDER_OUTPUT_LIMIT'
                terminal['output_limit_control'] = output_limit_evidence
                atomic_write_json(root / 'output-limit-stop.json', {
                    **output_limit_evidence, 'provider_identity': identity,
                    'stopped_at': utc_now(), 'automatic_retry': False,
                    'limit': 'Stops after observable control event; no guarantee that provider-internal next request was not already sent.',
                })
            if fifo:
                fifo.close()
            if extra:
                extra.unlink(missing_ok=True)
            terminal["finished_at"] = utc_now()
            terminal["streams"] = {
                name: read_json(path)
                for name in ("stdout", "stderr", "last-message")
                if (path := root / f"{name}.manifest.json").is_file()
            }
            expected = {"stdout", "stderr"} | ({"last-message"} if extra else set())
            if child is not None and not expected <= set(terminal["streams"]):
                terminal["execution_status"] = "RECORDING_INCOMPLETE"
                terminal["integrity_error"] = "STREAM_MANIFEST_MISSING"
            atomic_write_json(root / "terminal.json", terminal)
            if child is not None:
                for stream in (child.stdout, child.stderr):
                    if stream is not None:
                        stream.close()


if __name__ == "__main__":
    _worker(Path(sys.argv[1]))
