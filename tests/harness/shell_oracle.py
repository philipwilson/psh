"""One oracle runner for all bash/psh differential execution (campaign E2).

This module is the SINGLE authority for two decisions the test tree used to
re-derive in ~40 places:

1. **Which bash is the oracle** — ``resolve_bash()`` implements the blessed
   ladder (``BASH_PATH`` env var -> Homebrew paths -> ``bash`` on PATH) and
   records the oracle's version.  Stock macOS ``/bin/bash`` is 3.2 and fails
   bash-4+ syntax used by dozens of comparison cases, so a bare ``bash`` (or a
   hard-coded Homebrew path) is never acceptable in a test — the static ratchet
   ``tests/unit/tooling/test_bash_oracle_resolution.py`` enforces routing
   through this resolver.

2. **How a differential case is executed** — ``run_shell_case()`` returns a
   *typed* :data:`ShellRunResult` (``Completed | SpawnFailure | Timeout |
   DecodeFailure``), never a sentinel string or a fake exit code.  Harness
   failures are therefore distinguishable from shell behavior, and a comparison
   harness can refuse to classify two identical failures as conformance
   (continuation finding G).

The runner owns, structurally:

* **Process-group hygiene** — every case starts in a new session
  (``start_new_session=True``); on timeout the *whole group* is SIGKILLed,
  the child is reaped, and a second ESRCH-tolerant sweep catches stragglers
  that raced into the group.
* **Bounded output** — stdout/stderr are captured to files whose size a
  watchdog polls; breaching the byte cap kills the process group and marks the
  stream ``truncated``.  A runaway case (the historical self-feeding ``cat``
  that wrote 80 GB from an orphaned probe) is bounded to roughly the cap.
* **File-backed standard descriptors** — the child's stdout/stderr are regular
  files, not pipes.  This is deliberate: macOS ``/dev/fd``-family re-opens of
  *pipe* descriptors can fail with EPERM in some execution environments (the
  v0.724-era gate failures around ``history -w /dev/stdout`` and bash's own
  ``/dev/fd/63`` process substitution), while re-opening a regular file is
  always an ordinary vnode open.  stdin is ``/dev/null`` unless case data is
  supplied (also via a file — no writer threads, no pipe deadlocks).
* **A temporary cwd per case** unless the caller pins one.
* **Explicit decode policy** — UTF-8 + ``surrogateescape`` on both streams,
  lossless for byte-comparison; a decode error (impossible with
  surrogateescape, kept for totality) is a typed ``DecodeFailure``.
* **A hermetic environment** — :func:`hermetic_shell_env` strips ALL inherited
  ``LC_*`` and ``LANG`` (continuation finding H: an inherited ``LC_CTYPE``
  from the developer's terminal made three conformance results host-sensitive)
  plus ``DISPLAY``/``XAUTHORITY`` (an inherited DISPLAY lets any X11-capable
  child auto-start XQuartz on macOS — integrator ruling), then applies the
  case-specific values.
"""

import os
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Union

__all__ = [
    "BashOracle",
    "BashOracleUnavailable",
    "Completed",
    "SpawnFailure",
    "Timeout",
    "DecodeFailure",
    "ShellRunResult",
    "resolve_bash",
    "try_resolve_bash",
    "hermetic_shell_env",
    "run_shell_case",
]

# Default per-stream output cap (bytes).  Differential cases legitimately
# produce at most a few KiB; 8 MiB leaves three orders of magnitude of slack
# while making an 80 GB runaway structurally impossible.
DEFAULT_BYTE_CAP = 8 * 1024 * 1024

# How often the watchdog polls the child and the output files while waiting.
_POLL_INTERVAL = 0.05


class BashOracleUnavailable(RuntimeError):
    """No bash executable could be resolved (BASH_PATH, Homebrew, or PATH)."""


@dataclass(frozen=True)
class BashOracle:
    """A resolved bash oracle: absolute path plus its recorded version."""
    path: str
    version: str


@dataclass(frozen=True)
class Completed:
    """The case ran to completion (including nonzero exit / signal death)."""
    stdout: str
    stderr: str
    returncode: int
    duration: float
    stdout_truncated: bool = False
    stderr_truncated: bool = False


@dataclass(frozen=True)
class SpawnFailure:
    """The shell process could not be started (missing/denied executable...).

    This is a HARNESS failure, not shell behavior: it must never enter a
    stdout/status/stderr comparison.
    """
    message: str


@dataclass(frozen=True)
class Timeout:
    """The case exceeded its deadline; its process group was SIGKILLed.

    Partial output (bounded by the byte cap) is preserved for diagnostics but
    must not be compared as if the case had completed.
    """
    timeout: float
    stdout: str
    stderr: str


@dataclass(frozen=True)
class DecodeFailure:
    """Captured bytes could not be decoded under the declared policy."""
    message: str


ShellRunResult = Union[Completed, SpawnFailure, Timeout, DecodeFailure]


_ORACLE_CACHE: Optional[BashOracle] = None


def _bash_version(path: str) -> str:
    """First line of ``bash --version``, e.g. ``5.2.26(1)-release``."""
    try:
        out = subprocess.run(
            [path, "-c", 'printf %s "$BASH_VERSION"'],
            stdin=subprocess.DEVNULL, capture_output=True,
            timeout=10, encoding="utf-8", errors="surrogateescape",
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return out or "unknown"


def resolve_bash() -> BashOracle:
    """Resolve the blessed bash oracle: BASH_PATH -> Homebrew -> PATH.

    The result (path + version) is cached for the process.  Raises
    :class:`BashOracleUnavailable` when no candidate exists — a comparison
    against a nonexistent oracle is a harness failure, not a skipped detail.
    """
    global _ORACLE_CACHE
    if _ORACLE_CACHE is not None:
        return _ORACLE_CACHE

    candidates: List[str] = []
    env_path = os.environ.get("BASH_PATH")
    if env_path:
        candidates.append(env_path)
    candidates += [
        "/opt/homebrew/bin/bash",   # Apple Silicon Homebrew
        "/usr/local/bin/bash",      # Intel mac Homebrew
    ]
    for cand in candidates:
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            _ORACLE_CACHE = BashOracle(cand, _bash_version(cand))
            return _ORACLE_CACHE

    path_bash = shutil.which("bash")
    if path_bash:
        _ORACLE_CACHE = BashOracle(path_bash, _bash_version(path_bash))
        return _ORACLE_CACHE

    raise BashOracleUnavailable(
        "no bash oracle found: BASH_PATH unset/invalid, no Homebrew bash, "
        "no bash on PATH")


def try_resolve_bash() -> Optional[BashOracle]:
    """Like :func:`resolve_bash` but returns None when unavailable.

    For module-level ``pytest.mark.skipif`` guards, where an unavailable
    oracle should skip the file rather than error its collection.
    """
    try:
        return resolve_bash()
    except BashOracleUnavailable:
        return None


def hermetic_shell_env(case_env: Optional[Dict[str, str]] = None,
                       base: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Build a hermetic child environment for a differential case.

    Starts from ``base`` (default: a copy of ``os.environ``), removes every
    inherited ``LC_*`` variable, ``LANG``, and ``DISPLAY``/``XAUTHORITY``,
    then applies ``case_env``.  A case that wants a locale therefore states it
    explicitly; nothing leaks in from the developer's terminal or CI host.
    (Inherited ``LC_CTYPE`` was the root cause of the three host-sensitive
    conformance failures — continuation finding H.)
    """
    env = dict(os.environ if base is None else base)
    for name in list(env):
        if name == "LANG" or name.startswith("LC_"):
            del env[name]
    env.pop("DISPLAY", None)
    env.pop("XAUTHORITY", None)
    if case_env:
        env.update(case_env)
    return env


def _killpg_sigkill(pid: int) -> None:
    """SIGKILL the process group led by ``pid``; tolerate it being gone."""
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _read_capped(path: str, byte_cap: int):
    """Return (bytes up to cap, truncated?) for a capture file."""
    with open(path, "rb") as f:
        data = f.read(byte_cap)
        truncated = bool(f.read(1))
    return data, truncated


def run_shell_case(argv: Sequence[str], *,
                   stdin_data: Union[str, bytes, None] = None,
                   env: Optional[Dict[str, str]] = None,
                   cwd: Optional[str] = None,
                   timeout: float = 10.0,
                   byte_cap: int = DEFAULT_BYTE_CAP) -> ShellRunResult:
    """Run one shell case and return a typed :data:`ShellRunResult`.

    ``argv`` is the complete command line (e.g. ``[oracle.path, '-c', cmd]``).
    ``env`` is used AS GIVEN — build it with :func:`hermetic_shell_env` unless
    the case deliberately needs the ambient environment.  ``cwd=None`` runs
    the case in a fresh temporary directory (removed afterwards).
    """
    if env is None:
        env = hermetic_shell_env()

    with tempfile.TemporaryDirectory(prefix="psh-oracle-") as workdir:
        run_cwd = cwd if cwd is not None else workdir
        out_path = os.path.join(workdir, ".oracle-stdout")
        err_path = os.path.join(workdir, ".oracle-stderr")
        in_path = os.path.join(workdir, ".oracle-stdin")

        if stdin_data is not None:
            with open(in_path, "wb") as f:
                f.write(stdin_data.encode("utf-8", "surrogateescape")
                        if isinstance(stdin_data, str) else stdin_data)
            stdin_file = open(in_path, "rb")
        else:
            stdin_file = open(os.devnull, "rb")

        out_file = open(out_path, "wb")
        err_file = open(err_path, "wb")
        start = time.monotonic()
        try:
            try:
                proc = subprocess.Popen(
                    list(argv), stdin=stdin_file, stdout=out_file,
                    stderr=err_file, env=env, cwd=run_cwd,
                    start_new_session=True)
            except (OSError, ValueError) as exc:
                return SpawnFailure(f"{type(exc).__name__}: {exc}")
        finally:
            stdin_file.close()
            out_file.close()
            err_file.close()

        # Wait with a watchdog: poll for exit, deadline, and output-cap breach.
        deadline = start + timeout
        timed_out = False
        while True:
            if proc.poll() is not None:
                break
            if time.monotonic() >= deadline:
                timed_out = True
                break
            try:
                if (os.path.getsize(out_path) > byte_cap
                        or os.path.getsize(err_path) > byte_cap):
                    # Runaway output: kill the whole group NOW; report as a
                    # completed-but-truncated run (the exit status below is
                    # the SIGKILL delivered here).
                    _killpg_sigkill(proc.pid)
            except OSError:
                pass
            time.sleep(_POLL_INTERVAL)

        if timed_out:
            # Kill the whole session (killpg), reap, then sweep once more for
            # stragglers that forked into the group during the first kill.
            _killpg_sigkill(proc.pid)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            _killpg_sigkill(proc.pid)
            out_bytes, _ = _read_capped(out_path, byte_cap)
            err_bytes, _ = _read_capped(err_path, byte_cap)
            return Timeout(
                timeout=timeout,
                stdout=out_bytes.decode("utf-8", "surrogateescape"),
                stderr=err_bytes.decode("utf-8", "surrogateescape"))

        returncode = proc.returncode
        # The child exited, but grandchildren it spawned into the session may
        # linger and keep writing; sweep the group defensively.
        _killpg_sigkill(proc.pid)
        duration = time.monotonic() - start

        try:
            out_bytes, out_trunc = _read_capped(out_path, byte_cap)
            err_bytes, err_trunc = _read_capped(err_path, byte_cap)
        except OSError as exc:  # pragma: no cover - capture file vanished
            return SpawnFailure(f"capture readback failed: {exc}")
        try:
            stdout = out_bytes.decode("utf-8", "surrogateescape")
            stderr = err_bytes.decode("utf-8", "surrogateescape")
        except (UnicodeDecodeError, ValueError) as exc:  # pragma: no cover
            # surrogateescape makes this unreachable; kept for totality so the
            # decode policy can never silently change into an exception.
            return DecodeFailure(f"{type(exc).__name__}: {exc}")

        return Completed(stdout=stdout, stderr=stderr, returncode=returncode,
                         duration=duration, stdout_truncated=out_trunc,
                         stderr_truncated=err_trunc)
