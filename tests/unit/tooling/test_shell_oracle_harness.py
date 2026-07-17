"""Behavior tests for the shared oracle runner (campaign E2/E3).

Covers the typed result contract (Completed | SpawnFailure | Timeout |
DecodeFailure), process-group timeout cleanup, bounded output, the hermetic
environment builder, per-case temporary cwd — and the continuation-G
self-test: the conformance analyzer must REFUSE to classify two identical
harness failures as conformant.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "conformance"))

from conformance_framework import (  # noqa: E402
    ConformanceResult,
    ConformanceTestFramework,
    OracleHarnessFailure,
)
from shell_oracle import (  # noqa: E402
    Completed,
    SpawnFailure,
    Timeout,
    hermetic_shell_env,
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
    assert not r.stdout_truncated and not r.stderr_truncated


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
    """A runaway writer is killed at the cap, well before the timeout."""
    start = time.monotonic()
    r = run_shell_case([SH, "-c", "yes runaway"],
                       timeout=30, byte_cap=64 * 1024)
    elapsed = time.monotonic() - start
    assert isinstance(r, Completed)
    assert r.stdout_truncated
    assert len(r.stdout.encode("utf-8", "surrogateescape")) <= 64 * 1024
    assert r.returncode < 0  # died by the cap-breach SIGKILL, not exit
    assert elapsed < 20, "cap breach must not wait for the timeout"


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
