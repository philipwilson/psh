"""wait -p / disown -a,-r / bg multi-jobspec / fg try-finally (campaign item 3).

bash-pinned (5.2.26):
- `wait -p VAR pid` sets VAR to the reported pid WITHOUT needing -n;
- `disown -a` / `disown -r` on an empty (or all-not-running) table succeed;
- `bg` resumes every named jobspec;
- `fg` reclaims the terminal even when the wait is interrupted.
"""

import signal
import subprocess
import sys

from psh.executor.job_control import JobManager, JobState


def _psh(script: str):
    result = subprocess.run(
        [sys.executable, "-m", "psh", "-c", script],
        capture_output=True, text=True, timeout=15,
    )
    return result.stdout, result.stderr, result.returncode


# ---- wait -p without -n ------------------------------------------------------

def test_wait_p_sets_var_for_pid_without_n():
    out, err, rc = _psh(
        'sleep 0.2 & p=$!; wait -p FIN $p; [ "$FIN" = "$p" ] && echo match; echo rc=$?')
    assert "match" in out


def test_wait_p_sets_var_for_jobspec_without_n():
    out, err, rc = _psh(
        'sleep 0.2 & p=$!; wait -p FIN %1; [ "$FIN" = "$p" ] && echo match')
    assert "match" in out


def test_wait_p_last_operand_reported():
    # With two operands, VAR is the pid of the LAST operand (the one whose
    # status is returned).
    out, err, rc = _psh(
        'sleep 0.1 & a=$!; sleep 0.2 & b=$!; wait -p FIN $a $b; '
        '[ "$FIN" = "$b" ] && echo match')
    assert "match" in out


def test_wait_n_p_still_works():
    # The -n path must keep assigning VAR (regression pin for test_wait_n).
    out, err, rc = _psh(
        '(exit 0) & p=$!; wait -n -p done; [ "$done" = "$p" ] && echo match')
    assert "match" in out


# wait -p sets VAR only when a job is actually reported. bash UNSETS the
# variable up front (it ends truly unset, not merely unchanged, and not empty)
# and sets it only on a reported pid. Truth table vs bash 5.2.26:
#   non-child pid / invalid pid / %nonexistent / bare wait-for-all -> UNSET
#   real or reaped child                                            -> pid
# (with and without -n). The bug was that a non-child pid still set VAR=pid,
# because reported_pid was assigned before the is-it-our-child check.

def test_wait_p_unset_for_non_child_pid():
    out, err, rc = _psh(
        'FIN=seed; wait -p FIN 99999999 2>/dev/null; echo "state=${FIN-UNSET}"')
    assert "state=UNSET" in out


def test_wait_p_unset_for_nonexistent_jobspec():
    out, err, rc = _psh(
        'FIN=seed; wait -p FIN %9 2>/dev/null; echo "state=${FIN-UNSET}"')
    assert "state=UNSET" in out


def test_wait_p_unset_for_bare_wait_for_all():
    out, err, rc = _psh(
        'FIN=seed; sleep 0.1 & wait -p FIN 2>/dev/null; echo "state=${FIN-UNSET}"')
    assert "state=UNSET" in out


def test_wait_p_unset_for_non_child_pid_with_n():
    out, err, rc = _psh(
        'FIN=seed; wait -n -p FIN 99999999 2>/dev/null; echo "state=${FIN-UNSET}"')
    assert "state=UNSET" in out


# ---- disown -a / -r on an empty table ---------------------------------------

def test_disown_a_empty_succeeds():
    out, err, rc = _psh("disown -a; echo rc=$?")
    assert "rc=0" in out
    assert err.strip() == ""


def test_disown_r_empty_succeeds():
    out, err, rc = _psh("disown -r; echo rc=$?")
    assert "rc=0" in out
    assert err.strip() == ""


def test_disown_r_without_a_disowns_running():
    # `disown -r` (no -a) must operate on all running jobs, not fall through to
    # the current-job path. Capture the pids first so the now-untracked jobs
    # can be killed by pid (disown removes them, so `kill %n` no longer works).
    out, err, rc = _psh(
        "sleep 5 & a=$!; sleep 6 & b=$!; disown -r; jobs; echo rc=$?; "
        "kill $a $b 2>/dev/null")
    assert "sleep" not in out       # both running jobs disowned
    assert "rc=0" in out


# ---- bg with multiple jobspecs (unit-level; -c cannot make stopped jobs) -----

def test_bg_resumes_multiple_jobspecs(monkeypatch):
    from psh.builtins.job_control import BgBuiltin

    jm = JobManager()
    j1 = jm.create_job(pgid=111, command="sleep 5")
    j1.add_process(111, "sleep 5")
    j2 = jm.create_job(pgid=222, command="sleep 6")
    j2.add_process(222, "sleep 6")
    for job in (j1, j2):
        for proc in job.processes:
            job.update_process_status(proc.pid, 0x7f)  # WIFSTOPPED
        job.update_state()
        assert job.state is JobState.STOPPED

    cont = []
    monkeypatch.setattr("os.killpg", lambda pgid, sig: cont.append((pgid, sig)))

    class Shell:
        pass
    shell = Shell()
    shell.job_manager = jm
    shell.state = type("S", (), {"stdout": sys.stdout, "stderr": sys.stderr})()

    lines = []
    builtin = BgBuiltin()
    monkeypatch.setattr(builtin, "write_line", lambda msg, sh: lines.append(msg))
    rc = builtin.execute(["bg", "%1", "%2"], shell)

    assert rc == 0
    assert (111, signal.SIGCONT) in cont
    assert (222, signal.SIGCONT) in cont
    assert j1.state is JobState.RUNNING and j2.state is JobState.RUNNING


def test_bg_reports_bad_jobspec_but_resumes_good(monkeypatch):
    from psh.builtins.job_control import BgBuiltin

    jm = JobManager()
    j1 = jm.create_job(pgid=111, command="sleep 5")
    j1.add_process(111, "sleep 5")
    j1.update_process_status(111, 0x7f)  # WIFSTOPPED
    j1.update_state()
    assert j1.state is JobState.STOPPED

    monkeypatch.setattr("os.killpg", lambda pgid, sig: None)

    class Shell:
        pass
    shell = Shell()
    shell.job_manager = jm

    errors = []
    builtin = BgBuiltin()
    monkeypatch.setattr(builtin, "write_line", lambda msg, sh: None)
    monkeypatch.setattr(builtin, "error", lambda msg, sh: errors.append(msg))
    rc = builtin.execute(["bg", "%1", "%9"], shell)

    assert rc == 1                       # one bad spec -> failure
    assert any("no such job" in e for e in errors)
    assert j1.state is JobState.RUNNING  # the good one still resumed


# ---- fg reclaims the terminal even if the wait raises -----------------------

def test_fg_restores_terminal_on_wait_exception(monkeypatch):
    from psh.builtins.job_control import FgBuiltin

    jm = JobManager()
    job = jm.create_job(pgid=333, command="sleep 9")
    job.add_process(333, "sleep 9")

    restored = []
    monkeypatch.setattr(jm, "transfer_terminal_control", lambda pgid, ctx="": True)
    monkeypatch.setattr(jm, "restore_shell_foreground",
                        lambda: restored.append(True))

    def boom(job, collect_all_statuses=False):
        raise KeyboardInterrupt

    monkeypatch.setattr(jm, "wait_for_job", boom)

    class Shell:
        pass
    shell = Shell()
    shell.job_manager = jm
    shell.state = type("S", (), {"supports_job_control": True})()

    builtin = FgBuiltin()
    monkeypatch.setattr(builtin, "write_line", lambda msg, sh: None)

    try:
        builtin.execute(["fg", "%1"], shell)
    except KeyboardInterrupt:
        pass

    # The finally block reclaimed the terminal despite the interrupted wait.
    assert restored == [True]
