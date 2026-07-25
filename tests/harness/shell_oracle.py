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
   *typed* :data:`ShellRunResult`, never a sentinel string or a fake exit code.
   Harness failures are therefore distinguishable from shell behavior, and a
   comparison harness can refuse to classify two identical failures as
   conformance (continuation finding G).

The outcome algebra (remediation slot 1.1) — exactly one of these, and only
the first is ever comparable:

* :class:`Completed` — the case ran to genuine completion (any exit status,
  including signal death), and its captured output is a **faithful, untruncated**
  record.  **This is the ONLY outcome that may enter a stdout/status/stderr
  comparison.**  The invariant "Completed means genuinely completed" is enforced
  structurally: ``Completed`` carries no truncation flags, so a truncated or
  harness-terminated run is *unrepresentable* as ``Completed``.  Every outcome
  is ``@dataclass(frozen=True, slots=True)`` — no ``__dict__``, so the frozen
  guarantee cannot be forged by ``__dict__`` injection, ``object.__setattr__``,
  or ``__class__`` surgery (a truncated ``OutputLimitExceeded`` cannot be
  re-typed into a ``Completed``).
* :class:`OutputLimitExceeded` — a stream breached the byte cap.  When the
  watchdog caught the overflow mid-run it SIGKILLed the whole process group
  (``killpg=True``, ``signal=SIGKILL``); when the process had already exited on
  its own by the time the capped readback saw the overflow, no kill was needed
  (``killpg=False``, ``signal=None``).  Either way the capture is truncated at
  ``byte_cap`` and therefore NOT comparable.  (This is the runaway-``yes`` /
  self-feeding-``cat`` case that used to masquerade as ``Completed`` and let two
  8 MiB cap-kills classify IDENTICAL — reappraisal #22 HIGH-1.)
* :class:`Timeout` — the deadline was exceeded; the process group was SIGKILLed.
  Partial output is preserved for diagnostics but is not comparable.
* :class:`SpawnFailure` — the shell process could not be started.
* :class:`DecodeFailure` — captured bytes could not be decoded under the policy
  (unreachable with surrogateescape, kept for totality).

:func:`is_comparable` is the SOLE AUTHORITY on that first-vs-rest split: every
comparison path calls it BEFORE comparing, so a non-comparable observation
yields a TEST_ERROR-class result, never IDENTICAL/DIFFERENT.

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
  always an ordinary vnode open.  stdin defaults to ``/dev/null`` (or, with
  case data, a regular SEEKABLE file — no writer threads, no pipe deadlocks).
  A case whose SUBJECT is non-seekability (``/dev/stdin`` as a script operand,
  the binary sniff, ``read``/``mapfile`` over-read) opts into a real pipe with
  ``stdin_mode="pipe"``; the default is unchanged.
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
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Union

__all__ = [
    "BashOracle",
    "BashOracleUnavailable",
    "Completed",
    "OutputLimitExceeded",
    "SpawnFailure",
    "Timeout",
    "DecodeFailure",
    "ShellRunResult",
    "is_comparable",
    "resolve_bash",
    "try_resolve_bash",
    "hermetic_shell_env",
    "run_shell_case",
    "run_psh",
    "run_bash",
]

# The psh worktree root (this file lives at ``<root>/tests/harness/``).  Used by
# :func:`run_psh` to pin ``PYTHONPATH`` so ``python -m psh`` always resolves the
# tree under test, never an editable-installed psh elsewhere.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

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


@dataclass(frozen=True, slots=True)
class Completed:
    """The case ran to genuine completion (including nonzero exit / signal death).

    INVARIANT — "Completed means genuinely completed": a ``Completed``
    observation is a faithful, UNTRUNCATED record of what the shell produced,
    and it is the ONLY :data:`ShellRunResult` that may enter a behavioral
    comparison.  There are deliberately NO truncation flags here: a run whose
    capture was truncated at the byte cap is an :class:`OutputLimitExceeded`,
    which makes "``Completed`` but truncated" structurally unrepresentable.
    """
    stdout: str
    stderr: str
    returncode: int
    duration: float


@dataclass(frozen=True, slots=True)
class OutputLimitExceeded:
    """A stream breached the byte cap; the capture is truncated, NOT comparable.

    The captured ``stdout``/``stderr`` are bounded at ``byte_cap`` and are
    therefore not a faithful record of what the shell would have produced, so
    this observation must never enter a stdout/status/stderr comparison
    (:func:`is_comparable` returns False for it).  Termination provenance:

    * ``killpg`` — True when the watchdog SIGKILLed the whole process group
      because it observed the overflow while the case was still running;
      False when the case had already exited on its own by the time the capped
      readback saw the overflow (no kill was needed, but the capture is still
      truncated).
    * ``signal`` — ``signal.SIGKILL`` when ``killpg`` is True, else ``None``.
    * ``returncode`` — the leader's wait status if known (negative for the
      cap-breach SIGKILL), kept for diagnostics only.
    * ``stdout_truncated`` / ``stderr_truncated`` — which stream(s) overflowed.
    """
    stdout: str
    stderr: str
    byte_cap: int
    duration: float
    stdout_truncated: bool
    stderr_truncated: bool
    killpg: bool
    signal: Optional[int] = None
    returncode: Optional[int] = None


@dataclass(frozen=True, slots=True)
class SpawnFailure:
    """The shell process could not be started (missing/denied executable...).

    This is a HARNESS failure, not shell behavior: it must never enter a
    stdout/status/stderr comparison.
    """
    message: str


@dataclass(frozen=True, slots=True)
class Timeout:
    """The case exceeded its deadline; its process group was SIGKILLed.

    Partial output (bounded by the byte cap) is preserved for diagnostics but
    must not be compared as if the case had completed.  ``stdout_truncated`` /
    ``stderr_truncated`` record whether the preserved partial capture ALSO hit
    the byte cap before the deadline — purely diagnostic provenance (a Timeout
    is non-comparable regardless), threaded through so a slow runaway is
    distinguishable from a slow-but-bounded hang.  They default to False so a
    hand-built ``Timeout(timeout=, stdout=, stderr=)`` stays valid.
    """
    timeout: float
    stdout: str
    stderr: str
    stdout_truncated: bool = False
    stderr_truncated: bool = False


@dataclass(frozen=True, slots=True)
class DecodeFailure:
    """Captured bytes could not be decoded under the declared policy."""
    message: str


ShellRunResult = Union[
    Completed, OutputLimitExceeded, SpawnFailure, Timeout, DecodeFailure]


def is_comparable(result: ShellRunResult) -> bool:
    """The SOLE AUTHORITY on whether ``result`` may enter a comparison.

    Only :class:`Completed` is comparable, and (by construction) a ``Completed``
    observation is never truncated or harness-terminated.  Every other outcome
    — :class:`OutputLimitExceeded`, :class:`Timeout`, :class:`SpawnFailure`,
    :class:`DecodeFailure` — is a non-comparable harness observation that must
    yield a TEST_ERROR-class result, never IDENTICAL/DIFFERENT.  Comparison
    paths call this BEFORE any stdout/status/stderr comparison.
    """
    return isinstance(result, Completed)


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

    ``PWD``/``OLDPWD`` are dropped for the same reason, and it is not
    hypothetical: the runner runs each case in a fresh temporary cwd, so an
    inherited ``PWD`` is STALE.  bash revalidates it against the real cwd and
    silently corrects, while psh trusts the environment — so ``echo $PWD``
    manufactured a psh-vs-bash divergence that is an artifact of the harness,
    not of either shell.  :func:`run_shell_case` sets ``PWD`` to the actual run
    directory instead (a caller that deliberately wants a stale or fabricated
    ``PWD`` still just passes one in ``case_env``, which wins).
    """
    env = dict(os.environ if base is None else base)
    for name in list(env):
        if name == "LANG" or name.startswith("LC_"):
            del env[name]
    env.pop("DISPLAY", None)
    env.pop("XAUTHORITY", None)
    env.pop("PWD", None)
    env.pop("OLDPWD", None)
    if case_env:
        env.update(case_env)
    return env


def _killpg_sigkill(pid: int) -> None:
    """SIGKILL the process group led by ``pid``; tolerate it being gone."""
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _feed_pipe(write_fd: int, payload: bytes) -> None:
    """Write ``payload`` to ``write_fd`` and close it (delivering EOF).

    Runs on a daemon thread for ``stdin_mode='pipe'``.  A child that never
    reads leaves this parked on a full pipe — harmless: the thread is a daemon,
    the write end is closed here on every exit path, and a child that dies
    (timeout/cap killpg) makes the write fail with EPIPE, which is swallowed.
    """
    try:
        if payload:
            os.write(write_fd, payload)
    except OSError:
        pass                      # EPIPE: the child exited/was killed first
    finally:
        try:
            os.close(write_fd)    # EOF for the reader
        except OSError:
            pass


def _read_capped(path: str, byte_cap: int):
    """Return (bytes up to cap, truncated?) for a capture file."""
    with open(path, "rb") as f:
        data = f.read(byte_cap)
        truncated = bool(f.read(1))
    return data, truncated


def run_shell_case(argv: Sequence[str], *,
                   stdin_data: Union[str, bytes, None] = None,
                   stdin_mode: str = "file",
                   env: Optional[Dict[str, str]] = None,
                   cwd: Optional[str] = None,
                   timeout: float = 10.0,
                   byte_cap: int = DEFAULT_BYTE_CAP) -> ShellRunResult:
    """Run one shell case and return a typed :data:`ShellRunResult`.

    ``argv`` is the complete command line (e.g. ``[oracle.path, '-c', cmd]``).
    ``env`` is used AS GIVEN — build it with :func:`hermetic_shell_env` unless
    the case deliberately needs the ambient environment.  ``cwd=None`` runs
    the case in a fresh temporary directory (removed afterwards).

    ``stdin_mode`` selects the KIND of descriptor the child gets on fd 0 — a
    load-bearing distinction for any case whose SUBJECT is seekability
    (``/dev/stdin`` as a script, the binary sniff, ``read``/``mapfile``
    over-read):

    * ``"file"`` (default, unchanged): fd 0 is a regular, SEEKABLE file
      (``/dev/null`` when no data). No writer threads, no pipe deadlocks —
      the reason this is the default.
    * ``"pipe"``: fd 0 is a real PIPE (``S_ISFIFO``), so ``/dev/stdin`` is
      non-seekable exactly as under ``subprocess.run(..., input=...)``.  The
      data is written by a daemon thread and the write end closed to deliver
      EOF; if the child never reads, the thread parks harmlessly on a full
      pipe and the normal timeout/killpg path still applies.
    """
    if env is None:
        env = hermetic_shell_env()
    if stdin_mode not in ("file", "pipe"):
        raise ValueError(f"stdin_mode must be 'file' or 'pipe', got {stdin_mode!r}")

    payload: Optional[bytes] = None
    if stdin_data is not None:
        payload = (stdin_data.encode("utf-8", "surrogateescape")
                   if isinstance(stdin_data, str) else stdin_data)

    with tempfile.TemporaryDirectory(prefix="psh-oracle-") as workdir:
        run_cwd = cwd if cwd is not None else workdir
        out_path = os.path.join(workdir, ".oracle-stdout")
        err_path = os.path.join(workdir, ".oracle-stderr")
        in_path = os.path.join(workdir, ".oracle-stdin")

        # Give the child a TRUTHFUL $PWD for the directory it actually runs in.
        # hermetic_shell_env drops the (stale) inherited one; without this the
        # shells diverge on `echo $PWD` purely as a harness artifact — bash
        # revalidates PWD against the real cwd, psh trusts the environment.
        # An explicit caller-supplied PWD still wins (it is already in `env`).
        if "PWD" not in env:
            env = dict(env, PWD=os.path.abspath(run_cwd))

        writer: Optional[threading.Thread] = None
        pipe_write_fd: Optional[int] = None
        if stdin_mode == "pipe":
            pipe_read_fd, pipe_write_fd = os.pipe()
            stdin_file = None
        elif payload is not None:
            with open(in_path, "wb") as f:
                f.write(payload)
            stdin_file = open(in_path, "rb")
        else:
            stdin_file = open(os.devnull, "rb")

        out_file = open(out_path, "wb")
        err_file = open(err_path, "wb")
        start = time.monotonic()
        try:
            try:
                proc = subprocess.Popen(
                    list(argv),
                    stdin=(pipe_read_fd if stdin_mode == "pipe" else stdin_file),
                    stdout=out_file, stderr=err_file, env=env, cwd=run_cwd,
                    start_new_session=True)
            except (OSError, ValueError) as exc:
                if pipe_write_fd is not None:
                    os.close(pipe_write_fd)
                return SpawnFailure(f"{type(exc).__name__}: {exc}")
        finally:
            if stdin_file is not None:
                stdin_file.close()
            if stdin_mode == "pipe":
                os.close(pipe_read_fd)   # the child owns it now
            out_file.close()
            err_file.close()

        if pipe_write_fd is not None:
            writer = threading.Thread(
                target=_feed_pipe, args=(pipe_write_fd, payload or b""),
                daemon=True)
            writer.start()

        # Wait with a watchdog: poll for exit, deadline, and output-cap breach.
        deadline = start + timeout
        timed_out = False
        capped = False
        while True:
            if proc.poll() is not None:
                break
            if time.monotonic() >= deadline:
                timed_out = True
                break
            try:
                if (os.path.getsize(out_path) > byte_cap
                        or os.path.getsize(err_path) > byte_cap):
                    # Runaway output: kill the whole group NOW and report a
                    # non-comparable OutputLimitExceeded (never Completed).
                    _killpg_sigkill(proc.pid)
                    capped = True
                    break
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
            out_bytes, out_trunc = _read_capped(out_path, byte_cap)
            err_bytes, err_trunc = _read_capped(err_path, byte_cap)
            return Timeout(
                timeout=timeout,
                stdout=out_bytes.decode("utf-8", "surrogateescape"),
                stderr=err_bytes.decode("utf-8", "surrogateescape"),
                stdout_truncated=out_trunc,
                stderr_truncated=err_trunc)

        if capped:
            # Reap the SIGKILLed leader, then sweep the group once more for
            # grandchildren that forked into the session before the kill landed.
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            _killpg_sigkill(proc.pid)
            duration = time.monotonic() - start
            out_bytes, out_trunc = _read_capped(out_path, byte_cap)
            err_bytes, err_trunc = _read_capped(err_path, byte_cap)
            return OutputLimitExceeded(
                stdout=out_bytes.decode("utf-8", "surrogateescape"),
                stderr=err_bytes.decode("utf-8", "surrogateescape"),
                byte_cap=byte_cap,
                duration=duration,
                stdout_truncated=out_trunc,
                stderr_truncated=err_trunc,
                killpg=True,
                signal=signal.SIGKILL,
                returncode=proc.returncode)

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

        # A case that wrote past the cap and exited on its OWN between polls (so
        # the watchdog never had to kill it) still produced a truncated capture.
        # Surface it as OutputLimitExceeded, never Completed, so the "Completed
        # is never truncated" invariant is airtight regardless of poll timing.
        if out_trunc or err_trunc:
            return OutputLimitExceeded(
                stdout=stdout, stderr=stderr, byte_cap=byte_cap,
                duration=duration, stdout_truncated=out_trunc,
                stderr_truncated=err_trunc, killpg=False, signal=None,
                returncode=returncode)

        return Completed(stdout=stdout, stderr=stderr, returncode=returncode,
                         duration=duration)


def run_psh(args: Sequence[str], *,
            stdin_data: Union[str, bytes, None] = None,
            stdin_mode: str = "file",
            env: Optional[Dict[str, str]] = None,
            cwd: Optional[str] = None,
            timeout: float = 10.0,
            byte_cap: int = DEFAULT_BYTE_CAP) -> ShellRunResult:
    """Run THIS worktree's psh (``python -m psh <args>``) through the runner.

    The blessed way for a differential test to launch psh: ``PYTHONPATH`` is
    pinned to the repo root so ``-m psh`` resolves the tree under test
    regardless of the runner's temporary cwd (the editable-install-imports-MAIN
    trap), and the child gets the same process-group / byte-cap / hermetic-env
    hygiene as every other case.  ``args`` is everything AFTER ``python -m psh``
    (e.g. ``['-c', cmd]`` or ``['--norc', script]``).  ``env`` is layered onto
    the hermetic base (:func:`hermetic_shell_env`); put shell-visible variables
    (``HISTFILE``, ``PS4``, ``LC_ALL`` …) there.  Returns the typed
    :data:`ShellRunResult` — the caller asserts :func:`is_comparable` before
    comparing, exactly as for a bash run.
    """
    case_env = hermetic_shell_env(env)
    existing = case_env.get("PYTHONPATH")
    case_env["PYTHONPATH"] = (
        _REPO_ROOT if not existing else _REPO_ROOT + os.pathsep + existing)
    return run_shell_case([sys.executable, "-m", "psh", *args],
                          stdin_data=stdin_data, stdin_mode=stdin_mode,
                          env=case_env, cwd=cwd,
                          timeout=timeout, byte_cap=byte_cap)


def run_bash(args: Sequence[str], *,
             stdin_data: Union[str, bytes, None] = None,
             stdin_mode: str = "file",
             env: Optional[Dict[str, str]] = None,
             cwd: Optional[str] = None,
             timeout: float = 10.0,
             byte_cap: int = DEFAULT_BYTE_CAP) -> ShellRunResult:
    """Run the resolved bash oracle (``bash <args>``) through the runner.

    ``args`` is everything AFTER the bash path (e.g. ``['-c', cmd]``).  The
    oracle binary comes from :func:`resolve_bash` (BASH_PATH -> Homebrew ->
    PATH), never a bare ``bash`` or a hard-coded path.  ``env`` is layered onto
    the hermetic base.  Returns the typed :data:`ShellRunResult`.
    """
    return run_shell_case([resolve_bash().path, *args],
                          stdin_data=stdin_data, stdin_mode=stdin_mode,
                          env=hermetic_shell_env(env),
                          cwd=cwd, timeout=timeout, byte_cap=byte_cap)
