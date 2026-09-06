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
    _REPO_ROOT,  # noqa: E402
    Completed,
    DecodeFailure,
    OutputLimitExceeded,
    SpawnFailure,
    Timeout,
    hermetic_shell_env,
    is_comparable,
    resolve_bash,
    run_bash,
    run_psh,
    run_shell_case,
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


# ---------------------------------------------------------------------------
# run_psh / run_bash: the blessed two-shell convenience wrappers (slot 1.2)
# ---------------------------------------------------------------------------

def test_run_psh_runs_the_worktree_psh():
    """run_psh resolves THIS tree's psh regardless of the runner's temp cwd —
    the PYTHONPATH pin defeats the editable-install-imports-MAIN trap.

    The discriminator is the resolved MODULE PATH, not the version string
    (round-3 finding): an editable install and this worktree normally carry the
    SAME version, so a version assertion passes whichever psh the child
    imported — it cannot discriminate, which is the entire point of the
    campaign's ``psh.__file__``-under-the-tree-under-test rule.
    """
    r = run_psh(["-c", "echo psh-ok"])
    assert isinstance(r, Completed)
    assert r.stdout == "psh-ok\n" and r.returncode == 0

    # Ask the CHILD where it imported psh from; it must be under THIS worktree.
    # Interpolate the PARENT's interpreter instead of a bare ``python``: on a
    # python3-only host (the Linux nightly) a bare ``python`` is not on PATH, so
    # the child would print nothing and this pin would fail as an empty-path
    # assertion rather than testing what it claims to.
    where = run_psh(["-c", f"{sys.executable} -c "
                           "'import psh; print(psh.__file__)'"],
                    env={"PYTHONPATH": _REPO_ROOT})
    assert isinstance(where, Completed), where
    child_psh = where.stdout.strip()
    assert child_psh, ("the child printed no path — the probe itself failed, "
                       f"stderr={where.stderr!r}")
    assert child_psh.startswith(_REPO_ROOT + os.sep), (
        f"child imported psh from {child_psh!r}, which is NOT under the tree "
        f"under test ({_REPO_ROOT!r}) — the PYTHONPATH pin is not holding")


def test_run_psh_pins_pythonpath_even_with_temp_cwd():
    """Default cwd is a throwaway temp dir with no psh on it; the wrapper still
    imports psh because PYTHONPATH points at the repo root."""
    r = run_psh(["-c", "import_marker() { :; }; echo $(( 2 + 3 ))"])
    assert isinstance(r, Completed) and r.stdout == "5\n"


def test_run_bash_runs_the_oracle():
    r = run_bash(["-c", "echo bash-ok; echo $BASH_VERSION >&2"])
    assert isinstance(r, Completed)
    assert r.stdout == "bash-ok\n"
    assert r.stderr.strip()  # bash printed its version -> it really is bash


def test_run_psh_and_run_bash_layer_case_env_on_hermetic_base(monkeypatch):
    """The case env is layered onto the hermetic base: an inherited LC_* is
    stripped, an explicitly passed one is honored, on BOTH wrappers."""
    monkeypatch.setenv("LC_CTYPE", "en_US.UTF-8")  # would otherwise leak in
    p = run_psh(["-c", "echo ${MARKER-unset}"], env={"MARKER": "pval"})
    b = run_bash(["-c", "echo ${MARKER-unset}"], env={"MARKER": "bval"})
    assert isinstance(p, Completed) and p.stdout == "pval\n"
    assert isinstance(b, Completed) and b.stdout == "bval\n"


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


def test_timeout_threads_truncation_provenance(monkeypatch):
    """Slot 1.2 item 7: a Timeout whose partial capture ALSO breached the cap
    records ``stdout_truncated`` (diagnostic only — a Timeout is non-comparable
    regardless, so no false-green is possible either way).  A bounded hang
    leaves the flags False.

    A runaway writer would normally be CAP-killed (OutputLimitExceeded) before
    the deadline, so — as in the natural-exit pin — neutralise the watchdog's
    size poll for the capture files; the never-exiting writer then hits the
    DEADLINE with a partial capture the timeout readback finds truncated.

    SCOPE OF THE MONKEYPATCH (integrator ruling, round 2 — accepted; do not
    re-litigate): it disables ONLY the watchdog's mid-flight cap KILL, so the
    case reaches the TIMEOUT path instead.  The child, the deadline, the killpg,
    the real partial capture and its truncation flags are all REAL.
    """
    import shell_oracle
    real_getsize = os.path.getsize
    monkeypatch.setattr(
        shell_oracle.os.path, "getsize",
        lambda p: 0 if str(p).endswith((".oracle-stdout", ".oracle-stderr"))
        else real_getsize(p))
    # The producer is BOUNDED (`head -c`), not open-ended. This row switches off
    # the watchdog's cap kill, so it is the one place in the suite where nothing
    # limits the writer's bytes -- and an unbounded writer here is precisely the
    # shape that filled an unlinked capture file at device speed and killed the
    # Linux nightly with [Errno 28]. The hardened _killpg_sigkill would now
    # reach it, but a row that removes its own safety net should not depend on
    # the kill being correct. `head -c` exits after 8 MiB while `sleep` keeps
    # the shell alive past the 0.5s deadline, so the TIMEOUT path and the
    # truncated partial capture this row exists to pin are both preserved
    # (8 MiB written >> the 16 KiB readback cap). Portable: no GNU `timeout`,
    # because this row also runs in the macOS gate.
    r = run_shell_case([SH, "-c", "yes runaway | head -c 8388608; sleep 30"],
                       timeout=0.5, byte_cap=16 * 1024)
    assert isinstance(r, Timeout)
    assert r.stdout_truncated and not r.stderr_truncated
    assert not is_comparable(r)

    # A quiet hang (no output) times out with the flags left False.
    r2 = run_shell_case([SH, "-c", "sleep 30"], timeout=0.5)
    assert isinstance(r2, Timeout)
    assert not r2.stdout_truncated and not r2.stderr_truncated


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


def _ps_can_enumerate_processes() -> bool:
    """``_descendant_pids`` walks ``ps -eo pid=,ppid=`` and, by design, finds
    NOTHING when ``ps`` cannot be spawned (a cleanup helper never raises into
    a test). Under a macOS seatbelt that denies ``ps`` the sweep therefore has
    no table to walk and the escaped writer survives — an environment fact,
    not a harness defect, so the row SKIPS there (D4). Probed through the
    runner itself: this module is oracle-bearing and may not spawn directly.
    """
    r = run_shell_case(["ps", "-eo", "pid=,ppid="], timeout=10)
    return isinstance(r, Completed) and bool(r.stdout.strip())


def test_cap_kill_reaches_a_writer_that_left_the_process_group():
    """The escaped-pgroup offender: killpg on the leader is NOT enough.

    ``run_shell_case`` starts the shell with ``start_new_session=True``, so it
    leads a group -- but a shell with JOB CONTROL ``setpgid``s the commands it
    launches into groups of their OWN, which ``killpg`` on the leader never
    reaches. Under ``set -m`` the writer below gets its own group, exactly as a
    psh job does (measured: psh pgid 40910, its `yes` child pgid 40919).

    Left alive it keeps writing to a capture file the harness has ALREADY
    unlinked, so nothing is visible on disk while free space drains at hundreds
    of MB/s and then fully recovers once it dies. That is what repeatedly killed
    the Linux nightly with ``[Errno 28]`` while ``df`` looked healthy either
    side, and it drained this suite's own gate host too: running THIS module
    used to consume ~7.8 GB and leave a live `yes` behind; it now costs ~2 MB
    and leaves nothing.

    RED before the descendant sweep in ``_killpg_sigkill``, green after.
    """
    if not _ps_can_enumerate_processes():
        pytest.skip("`ps -eo pid=,ppid=` cannot be spawned or prints nothing "
                    "here (sandboxed gate), so the descendant sweep has no "
                    "process table to walk")
    r = run_shell_case(
        [SH, "-c", "set -m; yes escaped & echo pid=$! >&2; wait"],
        timeout=30, byte_cap=64 * 1024)
    assert isinstance(r, OutputLimitExceeded)
    escaped_pid = int(r.stderr.split("pid=")[1].split()[0])
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(escaped_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        os.kill(escaped_pid, 9)  # never leave it filling the disk
        raise AssertionError(
            f"writer {escaped_pid} left the shell's process group and survived "
            "the cap kill; it is still filling an unlinked capture file")


def test_child_pwd_is_truthful_and_agrees_across_shells(tmp_path):
    """The child's ``$PWD`` names the directory it actually runs in.

    Round-3 finding: ``hermetic_shell_env`` copied ``os.environ`` while the
    runner runs each case in a FRESH temporary cwd, so the child inherited a
    STALE ``PWD``.  bash revalidates it against the real cwd, psh trusts the
    environment — so ``echo $PWD`` reported different directories for the two
    shells purely as a harness artifact: a manufactured divergence of exactly
    the HIGH-1 shape (the harness, not the shell, decides the verdict), waiting
    for the first ``$PWD``-touching row among the migrated modules.
    """
    # 1. Dir-agnostic invariant: in EACH shell, $PWD == $(pwd).
    same = 'if [ "$PWD" = "$(pwd)" ]; then echo MATCH; else echo "STALE:$PWD"; fi'
    for run in (run_psh, run_bash):
        r = run(["-c", same])
        assert isinstance(r, Completed), r
        assert r.stdout == "MATCH\n", f"{run.__name__}: {r.stdout!r}"

    # 2. Pinned to a SHARED cwd, both shells report the identical $PWD.
    shared = str(tmp_path)
    p = run_psh(["-c", "echo $PWD"], cwd=shared)
    b = run_bash(["-c", "echo $PWD"], cwd=shared)
    assert isinstance(p, Completed) and isinstance(b, Completed)
    assert p.stdout == b.stdout, f"psh {p.stdout!r} != bash {b.stdout!r}"
    assert p.stdout.strip() == os.path.abspath(shared)

    # 3. A case-supplied PWD still wins (a caller may fabricate one on purpose).
    forced = run_psh(["-c", "echo $PWD"], env={"PWD": "/fabricated/by/caller"})
    assert isinstance(forced, Completed)
    assert forced.stdout == "/fabricated/by/caller\n"

    # 4. OLDPWD is dropped too, and the shells AGREE about that: with no prior
    #    directory, `cd -` fails identically in both rather than silently
    #    jumping to a stale inherited path.
    oldpwd = 'cd - 2>/dev/null || echo NO-OLDPWD'
    po = run_psh(["-c", oldpwd])
    bo = run_bash(["-c", oldpwd])
    assert isinstance(po, Completed) and isinstance(bo, Completed)
    assert po.stdout == bo.stdout == "NO-OLDPWD\n", (po.stdout, bo.stdout)


def test_stdin_mode_pipe_gives_a_real_non_seekable_pipe():
    """Typed-case pin for ``stdin_mode='pipe'`` (round-2 blocker 1).

    The DEFAULT file mode makes fd 0 a regular, SEEKABLE file — right for almost
    every case, but it silently retargets any case whose SUBJECT is
    non-seekability (``/dev/stdin`` as a script operand, the #15 I2 binary
    sniff, ``read``/``mapfile`` over-read). Pipe mode restores a real FIFO on
    fd 0 while still delivering the data and EOF.
    """
    probe = ('if [ -p /dev/stdin ]; then echo FD0=PIPE; else echo FD0=REGFILE;'
             ' fi; cat')
    piped = run_shell_case([SH, "-c", probe], stdin_data="payload\n",
                           stdin_mode="pipe")
    assert isinstance(piped, Completed), piped
    assert piped.stdout == "FD0=PIPE\npayload\n"

    # Default (and explicit "file") stay seekable-regular — unchanged behavior.
    filed = run_shell_case([SH, "-c", probe], stdin_data="payload\n")
    assert isinstance(filed, Completed), filed
    assert filed.stdout == "FD0=REGFILE\npayload\n"
    explicit = run_shell_case([SH, "-c", probe], stdin_data="payload\n",
                              stdin_mode="file")
    assert isinstance(explicit, Completed) and explicit.stdout == filed.stdout


def test_stdin_mode_pipe_delivers_eof_with_no_data():
    """No ``stdin_data`` in pipe mode still closes the write end, so a reader
    sees EOF instead of hanging (the deadlock the file default exists to avoid).
    """
    r = run_shell_case([SH, "-c", "cat; echo done"], stdin_mode="pipe",
                       timeout=5)
    assert isinstance(r, Completed), r
    assert r.stdout == "done\n"


def test_stdin_mode_pipe_survives_a_child_that_never_reads():
    """A child that ignores stdin leaves the writer parked on the pipe; the case
    must still complete normally (daemon thread, EPIPE swallowed on close).
    """
    r = run_shell_case([SH, "-c", "echo ignored-stdin"], stdin_data="x" * 4096,
                       stdin_mode="pipe", timeout=10)
    assert isinstance(r, Completed), r
    assert r.stdout == "ignored-stdin\n"


def test_stdin_mode_rejects_unknown_value():
    with pytest.raises(ValueError, match="stdin_mode"):
        run_shell_case([SH, "-c", "true"], stdin_mode="socket")


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


def test_natural_exit_past_cap_is_output_limit_without_killpg(monkeypatch):
    """Round-2 coverage debt (slot 1.2 item 6): a writer that exceeds the cap
    but EXITS ON ITS OWN — the watchdog never had to kill it — is still a
    NON-comparable OutputLimitExceeded, but with ``killpg=False`` /
    ``signal=None`` and the process's own exit status preserved.  This is the
    second OutputLimitExceeded branch (run_shell_case:446), which only the
    poll-timing race exercised before.

    Determinism: neutralise ONLY the watchdog's size poll (return 0 for the two
    capture files) so the finite writer reaches natural completion; the readback
    path — independent of the poll — then detects the truncation from the file
    itself.  Everything else keeps its real size.

    SCOPE OF THE MONKEYPATCH (integrator ruling, round 2 — accepted; do not
    re-litigate): it disables ONLY the watchdog's mid-flight cap KILL, which is
    what makes the natural-exit branch reachable deterministically instead of by
    poll-timing luck.  The child, its real output, the capture files, the capped
    readback, and the truncation classification are all REAL — nothing about the
    asserted outcome is simulated.
    """
    import shell_oracle
    real_getsize = os.path.getsize
    monkeypatch.setattr(
        shell_oracle.os.path, "getsize",
        lambda p: 0 if str(p).endswith((".oracle-stdout", ".oracle-stderr"))
        else real_getsize(p))
    # printf writes 2048 bytes in one burst then exits 0; cap is 1024.
    r = run_shell_case([SH, "-c", "printf '%2048d' 0"],
                       timeout=10, byte_cap=1024)
    assert isinstance(r, OutputLimitExceeded)
    assert not is_comparable(r)
    assert r.stdout_truncated and not r.stderr_truncated
    assert r.killpg is False and r.signal is None
    assert r.returncode == 0  # exited on its OWN — success status preserved
    assert len(r.stdout.encode("utf-8", "surrogateescape")) <= 1024


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
