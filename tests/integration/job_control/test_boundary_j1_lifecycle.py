"""Boundary campaign J1: job/signal/shutdown lifecycle (bash-pinned).

Behavioral pins for the three findings the J1 slot closes. Each was RED on
base 9b725f14 (v0.745.0) and matches live bash 5.2.26:

- H11 (AsyncJobPolicy): a background PIPELINE member ignores SIGINT/SIGQUIT
  like a standalone async command — the policy applies to EVERY member of a
  backgrounded job, not just role SINGLE. Base killed the member (rc 130/131).
- H12 (ForegroundJobSession): a foreground SUBSHELL killed by a signal prints
  bash's abnormal-termination diagnostic (``Terminated: 15`` &c). Base was
  SILENT — the subshell path bypassed report_abnormal_termination.
- H19 (typed no_hup / huponexit): ``shopt -s huponexit`` is a real option and
  ``disown -h`` keeps the job in the table (typed Job.no_hup). Base rejected
  the option / had no typed field.

These involve real signals and processes, so they run psh in a subprocess and
live under tests/integration/job_control/ (auto-marked serial).
"""
import subprocess
import sys


def _psh(script: str, timeout: float = 12):
    result = subprocess.run(
        [sys.executable, "-m", "psh", "-c", script],
        capture_output=True, text=True, timeout=timeout,
    )
    return result.stdout, result.stderr, result.returncode


# ---- H11: background pipeline member ignores INT/QUIT (async-list rule) ------

def test_bg_pipeline_member_ignores_sigint():
    # cat is the LAST member; sleep feeds it. Non-interactive (`-c`) => job
    # control off => the async policy ignores SIGINT for every member, so cat
    # keeps reading until sleep's pipe closes and exits 0 (base: killed, 130).
    out, err, rc = _psh(
        "sleep 0.4 | cat & p=$!; sleep 0.15; kill -INT $p 2>/dev/null; "
        "wait $p; echo rc=$?")
    assert out == "rc=0\n", (out, err)


def test_bg_pipeline_member_ignores_sigquit():
    out, err, rc = _psh(
        "sleep 0.4 | cat & p=$!; sleep 0.15; kill -QUIT $p 2>/dev/null; "
        "wait $p; echo rc=$?")
    assert out == "rc=0\n", (out, err)


def test_bg_pipeline_member_still_dies_on_sigterm():
    # Only INT/QUIT are ignored; SIGTERM still kills (rc 143), matching bash.
    out, err, rc = _psh(
        "sleep 0.4 | cat & p=$!; sleep 0.15; kill -TERM $p 2>/dev/null; "
        "wait $p; echo rc=$?")
    assert out == "rc=143\n", (out, err)


def test_bg_single_async_stdin_is_devnull_but_pipeline_leader_is_not():
    # /dev/null-stdin stays a SINGLE-only policy (bash): a standalone `cat &`
    # reads nothing; a bg pipeline leader keeps the real stdin.
    out, _, _ = _psh("printf 'hi\\n' | { cat & wait; }; echo end")
    assert out == "end\n", out  # bg single cat got /dev/null, printed nothing
    out2, _, _ = _psh("printf 'hi\\n' | { cat | tr a-z A-Z & wait; }")
    assert out2 == "HI\n", out2  # pipeline leader read the real stdin


# ---- B1: `set -m` (monitor) enables job control -> NO async signal policy ----
# The async-list INT/QUIT-ignore applies only when job control is OFF. Under
# `set -m` (even non-interactively) job control is ON, so a bg member is killed
# by a stray signal (rc 130/131), matching bash. `_job_control_off` now consults
# the `monitor` option. RED sides: the SINGLE-under-set-m row is red-on-base
# (base ignored monitor for SINGLE too); the pipeline-under-set-m row is red at
# the pre-B1 tip (H11 introduced the leak for pipeline members).

def test_setm_single_member_still_dies_on_sigint():
    out, err, rc = _psh(
        "set -m; sleep 0.4 & p=$!; sleep 0.15; kill -INT $p 2>/dev/null; "
        "wait $p; echo rc=$?")
    assert out == "rc=130\n", (out, err)


def test_setm_single_member_still_dies_on_sigquit():
    out, err, rc = _psh(
        "set -m; sleep 0.4 & p=$!; sleep 0.15; kill -QUIT $p 2>/dev/null; "
        "wait $p; echo rc=$?")
    assert out == "rc=131\n", (out, err)


def test_setm_pipeline_member_still_dies_on_sigint():
    out, err, rc = _psh(
        "set -m; sleep 0.4 | cat & p=$!; sleep 0.15; kill -INT $p 2>/dev/null; "
        "wait $p; echo rc=$?")
    assert out == "rc=130\n", (out, err)


def test_setm_pipeline_member_still_dies_on_sigquit():
    out, err, rc = _psh(
        "set -m; sleep 0.4 | cat & p=$!; sleep 0.15; kill -QUIT $p 2>/dev/null; "
        "wait $p; echo rc=$?")
    assert out == "rc=131\n", (out, err)


def test_no_monitor_bg_pipeline_member_still_ignores_int():
    # Regression guard: the B1 monitor fix must NOT break the H11 no-monitor
    # case — a bg pipeline member with job control OFF still ignores INT (rc 0).
    out, err, rc = _psh(
        "sleep 0.4 | cat & p=$!; sleep 0.15; kill -INT $p 2>/dev/null; "
        "wait $p; echo rc=$?")
    assert out == "rc=0\n", (out, err)


# ---- H12: foreground subshell signal death prints bash's diagnostic ---------

def test_fg_subshell_sigterm_prints_terminated():
    out, err, rc = _psh("( kill -s TERM $BASHPID ); echo after=$?")
    assert rc == 0
    assert out == "after=143\n", (out, err)
    # psh emits the bare signal description (bash adds a PID/command header —
    # documented format difference); the description must be present.
    assert "Terminated" in err, err


def test_fg_subshell_sigquit_prints_quit():
    out, err, rc = _psh("( kill -s QUIT $BASHPID ); echo after=$?")
    assert out == "after=131\n", (out, err)
    assert "Quit" in err, err


def test_fg_subshell_sigint_is_silent():
    # bash does NOT announce a foreground SIGINT death; psh must stay silent.
    out, err, rc = _psh("( kill -s INT $BASHPID ); echo after=$?")
    assert out == "after=130\n", (out, err)
    assert "Interrupt" not in err and err.strip() == "", err


def test_fg_subshell_normal_exit_no_diagnostic():
    out, err, rc = _psh("( exit 5 ); echo after=$?")
    assert out == "after=5\n", (out, err)
    assert err.strip() == "", err


# ---- B2: a pipeline-MEMBER subshell announces only via the status member -----
# Routing subshell.py through ForegroundJobSession made a subshell that is a
# pipeline member self-announce its death (spurious). Fix: a forked-child
# subshell does not self-announce AND re-raises its body's fatal signal so the
# enclosing pipeline announces the status-determining member, exactly like bash.

def test_pipeline_nonfinal_subshell_death_is_silent():
    # `( kill ) | cat`: the subshell is NOT the status member (cat is, exit 0),
    # so bash announces nothing. RED at the pre-B2 tip (spurious "Terminated").
    out, err, rc = _psh("( kill -s TERM $BASHPID ) | cat; echo after=$?")
    assert "Terminated" not in err, err
    assert out == "after=0\n", (out, err)


def test_pipeline_middle_subshell_death_is_silent():
    out, err, rc = _psh("echo x | ( kill -s TERM $BASHPID ) | cat; echo after=$?")
    assert "Terminated" not in err, err


def test_pipeline_final_subshell_death_is_announced():
    # `cat | ( kill )`: the subshell IS the status member, so bash announces —
    # psh now propagates the signal so the pipeline sees it and announces.
    out, err, rc = _psh("cat </dev/null | ( kill -s TERM $BASHPID ); echo after=$?")
    assert "Terminated" in err, err
    assert out == "after=143\n", (out, err)


def test_pipefail_nonfinal_subshell_death_is_announced():
    # Under pipefail the failing non-final subshell IS status-determining.
    out, err, rc = _psh(
        "set -o pipefail; ( kill -s TERM $BASHPID ) | cat; echo after=$?")
    assert "Terminated" in err, err


def test_pipeline_member_subshell_pipestatus_reflects_signal():
    out, err, rc = _psh(
        "( kill -s TERM $BASHPID ) | cat; echo ps=${PIPESTATUS[0]},${PIPESTATUS[1]}")
    assert out == "ps=143,0\n", (out, err)


# ---- H19: huponexit option + disown -h keep-in-table -------------------------

def test_huponexit_is_a_real_shopt_option():
    # RED on base: `shopt -s huponexit` errored (unknown option) there.
    out, err, rc = _psh("shopt -s huponexit && echo ok; shopt huponexit")
    assert rc == 0, (out, err)
    assert "ok" in out, out


def test_disown_h_keeps_job_in_table():
    # -h leaves the job listed (marked Job.no_hup); plain disown removes it.
    out_h, _, _ = _psh("sleep 3 & disown -h; jobs")
    assert "sleep 3" in out_h, out_h
    out_plain, _, _ = _psh("sleep 3 & disown; jobs")
    assert "sleep 3" not in out_plain, out_plain
