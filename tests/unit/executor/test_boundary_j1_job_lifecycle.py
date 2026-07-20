"""Boundary campaign J1: typed job-lifecycle units (H11/H19).

In-process unit pins for the typed representations that the subprocess-level
behavioral pins (tests/integration/job_control/test_boundary_j1_lifecycle.py)
exercise end-to-end:

- ``AsyncJobPolicy.for_launch`` — the async signal/stdin decision (pure).
- ``JobManager.hangup_jobs`` — honors ``Job.no_hup``, SIGCONT-before-SIGHUP
  for a stopped job (the huponexit exit-HUP policy).
- ``JobManager.detach_running_job`` / ``reap_detached`` + ``reap_registry`` —
  reap ownership SEPARATE from the user-visible job table.
- ``Shell._dispose_jobs_at_exit`` — the ONE shutdown path honors the policy,
  gated on interactive + huponexit.
"""
import os
import signal

from psh.executor.job_control import JobManager, JobState
from psh.executor.process_launcher import (
    AsyncJobPolicy,
    ProcessRole,
)


def _exited(code: int) -> int:
    return code << 8


def _stopped(sig: int = signal.SIGSTOP) -> int:
    return (sig << 8) | 0x7f


# ---- AsyncJobPolicy: the pure async decision (H11) --------------------------

def test_async_policy_active_only_for_bg_with_job_control_off():
    assert AsyncJobPolicy.for_launch(background=True, job_control_off=True) == \
        AsyncJobPolicy(ignore_int_quit=True, redirect_stdin_from_devnull=True)
    # any other combination is inactive
    assert AsyncJobPolicy.for_launch(background=False, job_control_off=True) == \
        AsyncJobPolicy.INACTIVE
    assert AsyncJobPolicy.for_launch(background=True, job_control_off=False) == \
        AsyncJobPolicy.INACTIVE
    assert AsyncJobPolicy.INACTIVE.ignore_int_quit is False
    assert AsyncJobPolicy.INACTIVE.redirect_stdin_from_devnull is False


def test_async_policy_stdin_is_single_only_but_signal_is_every_member():
    """The two dispositions are independent (the whole point of H11): the
    signal-ignore applies to every leaf member, the /dev/null redirect only to
    a standalone command. Verified via the config-shaped predicates the
    launcher applies (apply() itself sets real signal handlers, so it is
    exercised by the subprocess behavioral pins, not in-process)."""
    policy = AsyncJobPolicy.for_launch(background=True, job_control_off=True)
    # stdin redirect: SINGLE yes, pipeline members no
    def wants_devnull(role):
        return policy.redirect_stdin_from_devnull and role is ProcessRole.SINGLE
    assert wants_devnull(ProcessRole.SINGLE)
    assert not wants_devnull(ProcessRole.PIPELINE_LEADER)
    assert not wants_devnull(ProcessRole.PIPELINE_MEMBER)
    # signal ignore: every leaf role, regardless of position
    def wants_ignore(is_shell_process):
        return policy.ignore_int_quit and not is_shell_process
    assert wants_ignore(is_shell_process=False)
    assert not wants_ignore(is_shell_process=True)  # compound re-arms via traps


# ---- Job.no_hup is a real typed field (H19) ---------------------------------

def test_job_no_hup_defaults_false_and_is_typed():
    jm = JobManager()
    job = jm.create_job(4321, "sleep 5")
    assert job.no_hup is False
    job.no_hup = True
    assert job.no_hup is True


# ---- hangup_jobs: the exit-HUP policy (H19) ---------------------------------

def _make_job(jm, pid, cmd="sleep 5"):
    job = jm.create_job(pid, cmd)
    job.add_process(pid, cmd)
    return job


def test_hangup_jobs_skips_no_hup(monkeypatch):
    jm = JobManager()
    keep = _make_job(jm, 1001)          # gets HUP
    disowned = _make_job(jm, 2002)      # disown -h: exempt
    disowned.no_hup = True

    sent = []
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: sent.append((pgid, sig)))
    jm.hangup_jobs()

    assert (keep.pgid, signal.SIGHUP) in sent
    assert all(pgid != disowned.pgid for pgid, _ in sent)


def test_hangup_jobs_conts_stopped_before_hup(monkeypatch):
    jm = JobManager()
    job = _make_job(jm, 3003)
    job.update_process_status(job.processes[0].pid, _stopped())
    job.update_state()
    assert job.state == JobState.STOPPED

    sent = []
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: sent.append((pgid, sig)))
    jm.hangup_jobs()

    # SIGCONT must precede SIGHUP so the stopped job wakes to act on it (bash).
    assert sent == [(job.pgid, signal.SIGCONT), (job.pgid, signal.SIGHUP)]


def test_hangup_jobs_skips_done(monkeypatch):
    jm = JobManager()
    job = _make_job(jm, 4004)
    job.update_process_status(job.processes[0].pid, _exited(0))
    job.update_state()
    assert job.state == JobState.DONE

    sent = []
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: sent.append((pgid, sig)))
    jm.hangup_jobs()
    assert sent == []


# ---- reap ownership SEPARATE from the job table (H19) -----------------------

def test_detach_running_job_preserves_reap_ownership():
    jm = JobManager()
    job = _make_job(jm, 5005)
    pid = job.processes[0].pid

    jm.detach_running_job(job)

    # Gone from the user-visible table AND the job lookup index...
    assert job.job_id not in jm.jobs
    assert jm.get_job_by_pid(pid) is None
    # ...but reap ownership survives.
    assert pid in jm.reap_registry
    assert jm.reap_registry[pid] == job.pgid


def test_detach_done_job_registers_nothing():
    jm = JobManager()
    job = _make_job(jm, 6006)
    job.update_process_status(job.processes[0].pid, _exited(0))
    job.update_state()
    jm.detach_running_job(job)
    assert jm.reap_registry == {}          # nothing running to keep reaping
    assert job.job_id not in jm.jobs


def test_reap_detached_drops_exited_and_gone_keeps_running(monkeypatch):
    """reap_detached reaps a child that exited (WNOHANG returns its pid),
    drops one already reaped elsewhere (ECHILD), and KEEPS a still-running one
    (WNOHANG returns 0). Deterministic via a mocked os.waitpid keyed by pid."""
    jm = JobManager()
    jm.reap_registry = {111: 111, 222: 222, 333: 333}

    def fake_waitpid(pid, flags):
        assert flags == os.WNOHANG
        if pid == 111:          # exited: reapable now
            return (111, _exited(0))
        if pid == 222:          # still running
            return (0, 0)
        raise OSError(10, "No child processes")  # 333: ECHILD

    monkeypatch.setattr(os, "waitpid", fake_waitpid)
    jm.reap_detached()

    assert 111 not in jm.reap_registry   # reaped -> dropped
    assert 222 in jm.reap_registry       # still running -> kept
    assert 333 not in jm.reap_registry   # already gone (ECHILD) -> dropped


# ---- Shell.shutdown honors the policy, gated on interactive+huponexit (H19) --

def _shell():
    from psh.shell import Shell
    return Shell()


def test_dispose_jobs_at_exit_hups_when_interactive_and_huponexit(monkeypatch):
    shell = _shell()
    try:
        shell.state.options['interactive'] = True
        shell.state.options['huponexit'] = True
        job = _make_job(shell.job_manager, 7007)
        sent = []
        monkeypatch.setattr(os, "killpg",
                            lambda pgid, sig: sent.append((pgid, sig)))
        shell._dispose_jobs_at_exit()
        assert (job.pgid, signal.SIGHUP) in sent
    finally:
        shell.close()


def test_dispose_jobs_at_exit_no_hup_when_not_interactive(monkeypatch):
    shell = _shell()
    try:
        shell.state.options['interactive'] = False
        shell.state.options['huponexit'] = True
        _make_job(shell.job_manager, 8008)
        sent = []
        monkeypatch.setattr(os, "killpg",
                            lambda pgid, sig: sent.append((pgid, sig)))
        shell._dispose_jobs_at_exit()
        assert sent == []          # a non-interactive script never HUPs (bash)
    finally:
        shell.close()


def test_dispose_jobs_at_exit_no_hup_when_option_off(monkeypatch):
    shell = _shell()
    try:
        shell.state.options['interactive'] = True
        shell.state.options['huponexit'] = False
        _make_job(shell.job_manager, 9009)
        sent = []
        monkeypatch.setattr(os, "killpg",
                            lambda pgid, sig: sent.append((pgid, sig)))
        shell._dispose_jobs_at_exit()
        assert sent == []
    finally:
        shell.close()
