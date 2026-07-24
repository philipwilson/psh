"""Behavior tests for the shared oracle runner (campaign E2/E3; slot 1.1).

Covers the typed result contract (Completed | OutputLimitExceeded |
SpawnFailure | Timeout | DecodeFailure), the ``is_comparable`` authority,
process-group timeout AND output-cap cleanup, bounded output, the hermetic
environment builder, per-case temporary cwd — and the continuation-G / HIGH-1
self-tests: the conformance analyzer must REFUSE to classify two identical
harness failures (spawn failures OR two runaway cap-kills) as conformant.

Outcome-algebra invariant (slot 1.1): ``Completed`` is the ONLY comparable
outcome and by construction can never be truncated — a cap breach is a distinct
``OutputLimitExceeded`` and "Completed but truncated" is unrepresentable.
"""
import os
import signal
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "conformance"))

from conformance_framework import (  # noqa: E402
    ConformanceResult,
    ConformanceTestFramework,
    OracleHarnessFailure,
)
from shell_oracle import (  # noqa: E402
    Completed,
    DecodeFailure,
    OutputLimitExceeded,
    SpawnFailure,
    Timeout,
    hermetic_shell_env,
    is_comparable,
    resolve_bash,
    run_shell_case,
    try_resolve_bash,
)

SH = "/bin/sh"  # POSIX sh for runner mechanics; the bash ORACLE is resolved


# ---------------------------------------------------------------------------
# resolve_bash
# ---------------------------------------------------------------------------

def test_resolve_bash_returns_executable_with_version():
    oracle = resolve_bash()
    assert os.path.isfile(oracle.path) and os.access(oracle.path, os.X_OK)
    # A real recorded version, not a placeholder ("5.2.26(1)-release" style).
    assert oracle.version and oracle.version[0].isdigit()


def test_try_resolve_bash_matches_resolve():
    assert try_resolve_bash() == resolve_bash()


# ---------------------------------------------------------------------------
# run_shell_case: typed outcomes
# ---------------------------------------------------------------------------

def test_completed_captures_streams_and_status():
    r = run_shell_case([SH, "-c", "echo out; echo err >&2; exit 3"])
    assert isinstance(r, Completed)
    assert (r.stdout, r.stderr, r.returncode) == ("out\n", "err\n", 3)
    # Invariant: Completed carries NO truncation flags — a truncated run is an
    # OutputLimitExceeded, not a Completed (slot 1.1).
    assert not hasattr(r, "stdout_truncated")
    assert not hasattr(r, "stderr_truncated")


def test_spawn_failure_is_typed_not_exit_code():
    r = run_shell_case(["/nonexistent/shell-binary-xyz", "-c", "echo hi"])
    assert isinstance(r, SpawnFailure)
    assert "FileNotFoundError" in r.message


def test_timeout_kills_whole_process_group():
    """On timeout the runner SIGKILLs the SESSION, including grandchildren."""
    r = run_shell_case(
        [SH, "-c", "sleep 30 & echo pid=$!; wait"], timeout=0.5)
    assert isinstance(r, Timeout)
    bg_pid = int(r.stdout.split("pid=")[1].strip())
    # The background grandchild must die with the group; poll briefly for the
    # kill + reparent-reap to land.
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(bg_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        os.kill(bg_pid, 9)  # cleanup before failing loudly
        raise AssertionError(
            f"grandchild {bg_pid} survived the timeout killpg sweep")


def test_output_cap_is_structural_not_advisory():
    """A runaway writer is killed at the cap, well before the timeout.

    FLIPPED in slot 1.1: a cap breach used to return ``Completed`` with a
    truncation flag (the HIGH-1 defect — it then compared as behavior). It now
    returns a distinct, NON-comparable ``OutputLimitExceeded``.
    """
    start = time.monotonic()
    r = run_shell_case([SH, "-c", "yes runaway"],
                       timeout=30, byte_cap=64 * 1024)
    elapsed = time.monotonic() - start
    assert isinstance(r, OutputLimitExceeded)
    assert not is_comparable(r)  # truncated captures never enter a comparison
    assert r.stdout_truncated
    assert len(r.stdout.encode("utf-8", "surrogateescape")) <= 64 * 1024
    assert r.byte_cap == 64 * 1024
    # Termination provenance is the load-bearing assertion (killpg + SIGKILL);
    # returncode is diagnostic and may be None if the post-kill wait raced, so
    # don't pin it strictly.
    assert r.killpg and r.signal == signal.SIGKILL
    assert r.returncode is None or r.returncode < 0  # cap-breach SIGKILL
    assert elapsed < 20, "cap breach must not wait for the timeout"


def test_output_cap_kills_whole_process_group():
    """child/grandchild cleanup on the CAP path (mirror of the timeout pin).

    A cap breach SIGKILLs the whole session, not just the flooding leader — a
    quiet grandchild forked before the breach must die with the group.
    """
    r = run_shell_case(
        [SH, "-c", "sleep 30 & echo pid=$! >&2; yes runaway"],
        timeout=30, byte_cap=64 * 1024)
    assert isinstance(r, OutputLimitExceeded) and r.killpg
    bg_pid = int(r.stderr.split("pid=")[1].strip())
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(bg_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        os.kill(bg_pid, 9)  # cleanup before failing loudly
        raise AssertionError(
            f"grandchild {bg_pid} survived the output-cap killpg sweep")


def test_output_limit_records_termination_provenance():
    """OutputLimitExceeded records which stream overflowed + the kill details.

    Drive the breach on STDERR: stderr_truncated is set, stdout_truncated is
    not, and the configured cap + kill provenance are all carried for triage.
    """
    r = run_shell_case([SH, "-c", "yes runaway >&2"],
                       timeout=30, byte_cap=32 * 1024)
    assert isinstance(r, OutputLimitExceeded)
    assert r.stderr_truncated and not r.stdout_truncated
    assert len(r.stderr.encode("utf-8", "surrogateescape")) <= 32 * 1024
    assert r.byte_cap == 32 * 1024
    assert r.killpg is True and r.signal == signal.SIGKILL


def test_stdin_data_is_delivered_and_default_is_devnull():
    r = run_shell_case([SH, "-c", "cat"], stdin_data="fed\n")
    assert isinstance(r, Completed) and r.stdout == "fed\n"
    # No stdin_data -> /dev/null: cat terminates immediately instead of
    # hanging on an inherited descriptor.
    r2 = run_shell_case([SH, "-c", "cat"], timeout=5)
    assert isinstance(r2, Completed) and r2.stdout == ""


def test_each_case_gets_fresh_temporary_cwd():
    r1 = run_shell_case([SH, "-c", "pwd; touch marker"])
    r2 = run_shell_case([SH, "-c", "pwd; ls"])
    assert isinstance(r1, Completed) and isinstance(r2, Completed)
    d1, d2 = r1.stdout.strip(), r2.stdout.splitlines()[0].strip()
    assert d1 != d2, "cases must not share a working directory"
    assert d1 != os.getcwd() and d2 != os.getcwd()
    assert "marker" not in r2.stdout, "case workdirs must not leak files"
    assert not os.path.exists(d1), "case workdir must be removed afterwards"


def test_surrogateescape_round_trips_undecodable_bytes():
    r = run_shell_case([SH, "-c", r"printf 'a\377b'"])
    assert isinstance(r, Completed)
    assert r.stdout.encode("utf-8", "surrogateescape") == b"a\xffb"


# ---------------------------------------------------------------------------
# Outcome algebra: the "Completed means genuinely completed" invariant and the
# is_comparable authority (slot 1.1 / HIGH-1)
# ---------------------------------------------------------------------------

def test_completed_cannot_be_constructed_truncated():
    """Synthetic offender at the TYPE level: 'Completed but truncated' is now
    structurally unrepresentable — the truncation flags are gone from Completed.
    """
    with pytest.raises(TypeError):
        Completed(stdout="x", stderr="", returncode=0, duration=0.0,
                  stdout_truncated=True)  # type: ignore[call-arg]


def test_all_outcomes_are_slotted():
    """Every outcome dataclass is slotted (frozen+slots): no __dict__ to forge."""
    for cls in (Completed, OutputLimitExceeded, SpawnFailure, Timeout,
                DecodeFailure):
        assert hasattr(cls, "__slots__"), f"{cls.__name__} must be slotted"
    c = Completed(stdout="x", stderr="", returncode=0, duration=0.0)
    assert not hasattr(c, "__dict__")


def test_completed_truncation_cannot_be_forged():
    """Slots close the three forge paths a bare frozen dataclass leaves open —
    a truncated observation can never be laundered into a Completed.
    """
    c = Completed(stdout="x", stderr="", returncode=0, duration=0.0)
    ole = OutputLimitExceeded(
        stdout="y\n", stderr="", byte_cap=1, duration=0.0,
        stdout_truncated=True, stderr_truncated=False, killpg=True,
        signal=signal.SIGKILL, returncode=-9)

    # 1. __dict__ injection: no __dict__ exists on a slotted instance.
    with pytest.raises(AttributeError):
        c.__dict__["stdout_truncated"] = True  # type: ignore[attr-defined]

    # 2. object.__setattr__ bypass: the slot layout admits no such attribute.
    with pytest.raises(AttributeError):
        object.__setattr__(c, "stdout_truncated", True)

    # 3. __class__ surgery: differing slot layouts reject the re-type, so a
    #    truncated OutputLimitExceeded can never masquerade as Completed.
    with pytest.raises(TypeError):
        object.__setattr__(ole, "__class__", Completed)

    # dataclasses.replace on real fields still works (slots don't break it).
    import dataclasses
    assert dataclasses.replace(c, returncode=7).returncode == 7


def test_is_comparable_only_accepts_completed():
    """The sole comparison authority: exactly Completed is comparable."""
    ole = OutputLimitExceeded(
        stdout="y\n", stderr="", byte_cap=1, duration=0.0,
        stdout_truncated=True, stderr_truncated=False, killpg=True,
        signal=signal.SIGKILL, returncode=-9)
    assert is_comparable(Completed(stdout="", stderr="", returncode=0,
                                   duration=0.0))
    assert not is_comparable(ole)
    assert not is_comparable(Timeout(timeout=1.0, stdout="", stderr=""))
    assert not is_comparable(SpawnFailure("nope"))
    assert not is_comparable(DecodeFailure("undecodable"))


def test_decode_failure_is_typed_and_non_comparable():
    """DecodeFailure is unreachable via run_shell_case (surrogateescape) but
    stays in the union as a typed, non-comparable outcome for totality.
    """
    d = DecodeFailure("UnicodeDecodeError: boom")
    assert d.message == "UnicodeDecodeError: boom"
    assert not is_comparable(d)


# ---------------------------------------------------------------------------
# hermetic_shell_env
# ---------------------------------------------------------------------------

def test_hermetic_env_strips_all_locale_and_display():
    base = {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": "/keep/me",
        "LANG": "en_GB.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "LC_CTYPE": "C.UTF-8",
        "LC_COLLATE": "de_DE.UTF-8",
        "LC_NUMERIC": "fr_FR.UTF-8",
        "DISPLAY": ":0",
        "XAUTHORITY": "/home/x/.Xauthority",
    }
    env = hermetic_shell_env(base=base)
    assert env["PATH"] == "/usr/bin:/bin"
    assert env["PYTHONPATH"] == "/keep/me"
    for name in ("LANG", "LC_ALL", "LC_CTYPE", "LC_COLLATE", "LC_NUMERIC",
                 "DISPLAY", "XAUTHORITY"):
        assert name not in env, f"{name} must be stripped"


def test_hermetic_env_applies_case_values_after_strip():
    base = {"LC_CTYPE": "C.UTF-8", "PATH": "/bin"}
    env = hermetic_shell_env({"LC_ALL": "C", "LC_CTYPE": "en_US.UTF-8"},
                             base=base)
    assert env["LC_ALL"] == "C"
    assert env["LC_CTYPE"] == "en_US.UTF-8"  # the CASE's value, not inherited


def test_hermetic_env_defaults_to_os_environ_base(monkeypatch):
    monkeypatch.setenv("LC_MESSAGES", "sv_SE.UTF-8")
    monkeypatch.setenv("E23_HERMETIC_CANARY", "yes")
    env = hermetic_shell_env()
    assert "LC_MESSAGES" not in env
    assert env["E23_HERMETIC_CANARY"] == "yes"


# ---------------------------------------------------------------------------
# Continuation finding G: identical harness failures are NEVER conformance
# ---------------------------------------------------------------------------

def test_identical_spawn_failures_never_classify_identical():
    """Synthetic offender: both shells fail to spawn IDENTICALLY.

    The pre-typed framework rendered any exception as exit 127 + an
    'Execution error: ...' string on both sides, and the analyzer compared
    them byte-for-byte: two '[Errno 24] Too many open files' results
    classified IDENTICAL. The typed runner must classify TEST_ERROR instead.
    """
    fw = ConformanceTestFramework(
        psh_path=["/nonexistent/shell-binary-xyz"],
        bash_path=["/nonexistent/shell-binary-xyz"])
    result = fw.compare_behavior("echo hi")
    assert result.conformance == ConformanceResult.TEST_ERROR
    assert result.conformance != ConformanceResult.IDENTICAL
    assert result.psh_result is None and result.bash_result is None
    assert "harness failure" in result.notes


def test_identical_timeouts_never_classify_identical():
    fw = ConformanceTestFramework(
        psh_path=[SH], bash_path=[SH])  # same binary both sides: max symmetry
    result = fw.compare_behavior("sleep 30", timeout=0.5)
    assert result.conformance == ConformanceResult.TEST_ERROR
    assert "Timeout" in result.notes


def test_yes_discriminator_is_test_error_not_identical():
    """HIGH-1 discriminator: two runaway ``yes`` runs both breach the output
    cap (rc -9, 8 MiB truncated). On base this classified IDENTICAL; the typed
    OutputLimitExceeded outcome makes it TEST_ERROR.

    This is THE reappraisal #22 HIGH-1 first-half repro; it must stay RED on
    base and green here.
    """
    fw = ConformanceTestFramework()  # real psh vs the resolved bash oracle
    result = fw.compare_behavior("yes", timeout=5)
    assert result.conformance == ConformanceResult.TEST_ERROR
    assert result.conformance != ConformanceResult.IDENTICAL
    assert result.psh_result is None and result.bash_result is None
    assert "OutputLimitExceeded" in result.notes


def test_two_output_limit_runs_never_classify_identical(monkeypatch):
    """Synthetic offender (framework level, simulated — no 8 MiB run): even a
    byte-identical truncated capture with the same rc on both sides classifies
    TEST_ERROR, because a truncated capture is not a comparable observation.
    """
    fw = ConformanceTestFramework(psh_path=[SH], bash_path=[SH])
    offender = OutputLimitExceeded(
        stdout="y\n" * 4096, stderr="", byte_cap=64, duration=0.1,
        stdout_truncated=True, stderr_truncated=False, killpg=True,
        signal=signal.SIGKILL, returncode=-9)
    monkeypatch.setattr(fw, "_run_typed", lambda *a, **k: offender)
    result = fw.compare_behavior("yes")
    assert result.conformance == ConformanceResult.TEST_ERROR
    assert result.conformance != ConformanceResult.IDENTICAL
    assert result.psh_result is None and result.bash_result is None
    assert "OutputLimitExceeded" in result.notes


def test_one_sided_harness_failure_is_test_error_with_real_side_kept():
    fw = ConformanceTestFramework(
        psh_path=[SH], bash_path=["/nonexistent/shell-binary-xyz"])
    result = fw.compare_behavior("echo hi")
    assert result.conformance == ConformanceResult.TEST_ERROR
    assert result.psh_result is not None and result.psh_result.stdout == "hi\n"
    assert result.bash_result is None
    assert "bash harness failure" in result.notes


def test_run_in_shell_raises_typed_harness_failure():
    fw = ConformanceTestFramework(psh_path=[SH])
    try:
        fw.run_in_shell("echo hi", ["/nonexistent/shell-binary-xyz"])
    except OracleHarnessFailure as exc:
        assert isinstance(exc.result, SpawnFailure)
    else:
        raise AssertionError("spawn failure must raise, not fake a result")


def test_genuine_exit_124_now_compares_as_behavior():
    """`exit 124` is real shell behavior, not the old timeout sentinel."""
    fw = ConformanceTestFramework(psh_path=[SH], bash_path=[SH])
    result = fw.compare_behavior("exit 124")
    assert result.conformance == ConformanceResult.IDENTICAL
