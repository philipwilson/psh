"""Shutdown phases are MANDATORY: an EXIT trap cannot cancel them (slot 4A.2).

`Shell.shutdown(reason)` runs the EXIT trap, then the route's history policy,
then job disposition (hangup + detached reap), then `close()` -- bash's own
`exit_shell` order.  A trap body's own `exit N` re-enters the `exit` builtin,
no-ops on the shutdown latch and raises `SystemExit`; that is the NORMAL route,
and it used to propagate straight out of the try, so job disposition, detached
reaping AND the history save were all skipped -- permanently, because the latch
made a later `shutdown()` a no-op (MEDIUM-1).

The phases now hold that signal, finish, and re-raise it.  Every red pin below
was verified to FAIL at base tip d1e4f1ae before it was written, and the
`*_without_trap` controls prove each observable is reachable at all, so a red
cell cannot be vacuous.

Behavioral sibling of tests/unit/core/test_shutdown_f2.py (idempotence,
first-reason-wins, at-most-once, status override); the PTY half is
tests/system/interactive/test_pty_shutdown_phases_4a2.py, and the deterministic
job cells follow the synthetic-job shape of
tests/unit/executor/test_boundary_j1_job_lifecycle.py -- a fabricated Job plus a
patched `os.killpg`, so no real signal is ever delivered and these stay
xdist-safe.
"""
import os
import signal

import pytest

from psh.core.process_lease import LeaseRestoreError, get_coordinator
from psh.shell import Shell

TRAP_EXIT_7 = "trap 'exit 7' EXIT"


def _shell(*, interactive=False, huponexit=False, histfile=None, trap=None):
    shell = Shell(norc=True)
    if histfile is not None:
        shell.run_command(f"export HISTFILE={histfile}")
    if interactive:
        shell.state.options['interactive'] = True
    if huponexit:
        shell.state.options['huponexit'] = True
    if trap is not None:
        shell.run_command(trap)
    return shell


def _make_job(jm, pid, cmd="sleep 5"):
    job = jm.create_job(pid, cmd)
    job.add_process(pid, cmd)
    return job


def _collect_killpg(monkeypatch):
    sent = []
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: sent.append((pgid, sig)))
    return sent


def _shutdown(shell, reason):
    """Drive shutdown, returning the SystemExit code the trap requested (or
    None).  Capturing it here is what keeps a trap's `exit N` from killing the
    test runner."""
    try:
        shell.shutdown(reason)
    except SystemExit as exc:
        return exc.code
    return None


# ---- the bypass family: red at base, each phase its own cell ----------------

def test_huponexit_hangup_survives_a_trap_that_exits(monkeypatch):
    shell = _shell(interactive=True, huponexit=True, trap=TRAP_EXIT_7)
    try:
        job = _make_job(shell.job_manager, 7007)
        sent = _collect_killpg(monkeypatch)
        assert _shutdown(shell, 'exit-builtin') == 7
        assert (job.pgid, signal.SIGHUP) in sent
    finally:
        shell.close()


def test_huponexit_hangup_without_trap_is_the_control(monkeypatch):
    """Anti-vacuity control for the cell above: the observable is reachable."""
    shell = _shell(interactive=True, huponexit=True)
    try:
        job = _make_job(shell.job_manager, 7008)
        sent = _collect_killpg(monkeypatch)
        assert _shutdown(shell, 'exit-builtin') is None
        assert (job.pgid, signal.SIGHUP) in sent
    finally:
        shell.close()


def test_received_sighup_fanout_survives_a_trap_that_exits(monkeypatch):
    """The 'signal-hup' route's UNCONDITIONAL fan-out (bash's
    hangup_all_jobs) is not the EXIT trap's to cancel.  Composition cell: at a
    real terminal this is the interactive shell that receives SIGHUP while an
    EXIT trap runs `exit N` (bash fans out and saves history there; psh did
    neither)."""
    shell = _shell(interactive=True, trap=TRAP_EXIT_7)   # huponexit OFF
    try:
        job = _make_job(shell.job_manager, 1414)
        sent = _collect_killpg(monkeypatch)
        assert _shutdown(shell, 'signal-hup') == 7
        assert (job.pgid, signal.SIGHUP) in sent
    finally:
        shell.close()


def test_history_save_survives_a_trap_that_exits(tmp_path):
    """Ruling (b): bash writes the histfile even when the EXIT trap runs
    `exit N` (PTY-probed on both the `exit` and EOF routes).  The ROUTE owns
    the history policy; the trap gets no vote."""
    histfile = tmp_path / "histfile"
    shell = _shell(interactive=True, histfile=str(histfile), trap=TRAP_EXIT_7)
    try:
        shell.run_command('echo CANARY_CMD >/dev/null')
        assert _shutdown(shell, 'exit-builtin') == 7
        assert histfile.exists()
        assert 'CANARY_CMD' in histfile.read_text()
    finally:
        shell.close()


def test_history_save_without_trap_is_the_control(tmp_path):
    histfile = tmp_path / "histfile"
    shell = _shell(interactive=True, histfile=str(histfile))
    try:
        shell.run_command('echo CANARY_CMD >/dev/null')
        assert _shutdown(shell, 'exit-builtin') is None
        assert 'CANARY_CMD' in histfile.read_text()
    finally:
        shell.close()


def test_detached_reap_survives_a_trap_that_exits():
    """The detached-child reap is its own phase step.  A pid that is not our
    child makes `reap_detached` take its ECHILD arm and DROP the registration,
    so the registry emptying is a real observable of the real method with no
    fork of our own."""
    shell = _shell(trap=TRAP_EXIT_7)
    try:
        shell.job_manager.reap_registry[999_999] = 999_999
        assert _shutdown(shell, 'exit-builtin') == 7
        assert shell.job_manager.reap_registry == {}
    finally:
        shell.close()


def test_history_route_gating_is_unchanged_for_non_trap_exits(tmp_path):
    """Must-not-flip: `_HISTORY_SAVING_SHUTDOWNS` still decides.  A route that
    never saved history does not start saving it because the phases are now
    mandatory -- 'mandatory' means the phase RUNS, not that its policy changed."""
    histfile = tmp_path / "histfile"
    shell = _shell(interactive=True, histfile=str(histfile), trap=TRAP_EXIT_7)
    try:
        shell.run_command('echo CANARY_CMD >/dev/null')
        assert _shutdown(shell, 'main-exit') == 7
        assert not histfile.exists()
    finally:
        shell.close()


# ---- phase ORDER and phase ISOLATION ---------------------------------------

def test_phases_run_in_bash_order_under_a_trap_that_exits(tmp_path, monkeypatch):
    """History before job disposition before close -- bash's `exit_shell`
    order, which psh already had and which the phase split preserves."""
    histfile = tmp_path / "histfile"
    shell = _shell(interactive=True, huponexit=True, histfile=str(histfile),
                   trap=TRAP_EXIT_7)
    try:
        steps = []
        hm = shell.interactive_manager.history_manager
        jm = shell.job_manager
        monkeypatch.setattr(hm, 'save_to_file',
                            lambda *a, **k: steps.append('history'))
        monkeypatch.setattr(jm, 'hangup_jobs', lambda: steps.append('hangup'))
        monkeypatch.setattr(jm, 'reap_detached', lambda: steps.append('reap'))
        _make_job(jm, 4242)
        assert _shutdown(shell, 'exit-builtin') == 7
        assert steps == ['history', 'hangup', 'reap']
    finally:
        shell.close()


def test_a_failing_history_phase_does_not_cancel_job_disposition(monkeypatch):
    """Phase isolation: a shell that cannot write its histfile still owes its
    jobs a SIGHUP.  The history failure is what escapes (no trap here)."""
    shell = _shell(interactive=True, huponexit=True)
    try:
        hm = shell.interactive_manager.history_manager

        def boom(*a, **k):
            raise OSError("INJECTED histfile failure")

        monkeypatch.setattr(hm, 'save_to_file', boom)
        job = _make_job(shell.job_manager, 5150)
        sent = _collect_killpg(monkeypatch)
        with pytest.raises(OSError, match="INJECTED"):
            shell.shutdown('exit-builtin')
        assert (job.pgid, signal.SIGHUP) in sent
    finally:
        shell.close()


def test_a_second_phase_failure_is_recorded_as_a_note(monkeypatch):
    """The FIRST terminal signal is the one re-raised; a later phase failure
    must not vanish silently."""
    shell = _shell(interactive=True, huponexit=True, trap=TRAP_EXIT_7)
    try:
        monkeypatch.setattr(shell.job_manager, 'hangup_jobs',
                            lambda: (_ for _ in ()).throw(
                                OSError("INJECTED hangup failure")))
        with pytest.raises(SystemExit) as caught:
            shell.shutdown('exit-builtin')
        assert caught.value.code == 7          # the trap still sets the status
        notes = getattr(caught.value, '__notes__', [])
        assert any('INJECTED hangup failure' in note for note in notes), notes
    finally:
        shell.close()


# ---- must-hold guard rails --------------------------------------------------

def test_close_still_runs_and_releases_ownership_under_a_trap_that_exits():
    shell = _shell(trap=TRAP_EXIT_7)
    try:
        shell.run_command('echo warm >/dev/null')      # take the owner token
        assert _shutdown(shell, 'exit-builtin') == 7
        assert get_coordinator().current_owner() is not shell.state
    finally:
        shell.close()


def test_a_close_failure_outranks_the_held_trap_exit():
    """Precedence: a LeaseRestoreError is a loud internal defect and must not
    be silenced by an exit status.  The trap's SystemExit survives as
    __context__ so neither fact is lost."""
    shell = _shell(trap=TRAP_EXIT_7)
    real_close = shell.close

    def boom():
        real_close()
        raise LeaseRestoreError("INJECTED restore failure", [])

    shell.close = boom                                  # type: ignore[method-assign]
    with pytest.raises(LeaseRestoreError):
        try:
            shell.shutdown('exit-builtin')
        except LeaseRestoreError as exc:
            assert isinstance(exc.__context__, SystemExit)
            assert exc.__context__.code == 7
            raise


def test_the_latch_still_makes_a_later_shutdown_a_no_op(monkeypatch):
    """__main__'s `finally: shutdown('main-exit')` after the exit builtin
    already shut down: still a no-op, and the reason is still the first one."""
    shell = _shell(interactive=True, huponexit=True, trap=TRAP_EXIT_7)
    try:
        assert _shutdown(shell, 'exit-builtin') == 7
        assert shell._shutdown_reason == 'exit-builtin'
        job = _make_job(shell.job_manager, 6060)
        sent = _collect_killpg(monkeypatch)
        shell.shutdown('main-exit')                     # no-op: nothing re-runs
        assert sent == []
        assert shell._shutdown_reason == 'exit-builtin'
        assert job is not None
    finally:
        shell.close()


def test_exit_trap_still_fires_at_most_once_across_the_phases():
    shell = _shell(trap="trap 'X=$((X+1)); exit 7' EXIT")
    try:
        shell.run_command('X=0')
        assert _shutdown(shell, 'exit-builtin') == 7
        assert shell.state.get_variable('X') == '1'
    finally:
        shell.close()


def test_a_substitution_abort_in_the_trap_is_still_swallowed(monkeypatch):
    """Must-not-flip (slot 2.4): a substitution-body syntax error in the EXIT
    trap's own text is reported and swallowed at `execute_exit_trap`, so it
    was never a phase-cancelling signal -- and the later phases run."""
    shell = _shell(interactive=True, huponexit=True,
                   trap="trap 'echo $(fi)' EXIT")
    try:
        job = _make_job(shell.job_manager, 8080)
        sent = _collect_killpg(monkeypatch)
        assert _shutdown(shell, 'exit-builtin') is None
        assert (job.pgid, signal.SIGHUP) in sent
    finally:
        shell.close()
