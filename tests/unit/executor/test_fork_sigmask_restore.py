"""ProcessLauncher must restore the signal mask when fork() fails.

Regression test for the v0.300 try/finally around the fork in
ProcessLauncher.launch(): pthread_sigmask(SIG_BLOCK, ...) precedes
os.fork(), and before the fix a fork failure (EAGAIN under process
pressure) left SIGINT/SIGTERM/SIGHUP/SIGQUIT blocked in the shell
forever.
"""

import errno
import os
import signal

import pytest

from psh.executor.child_policy import fork_with_signal_window
from psh.executor.process_launcher import ProcessConfig, ProcessRole


def _current_mask():
    """Query the calling thread's signal mask (SIG_BLOCK with empty set)."""
    return signal.pthread_sigmask(signal.SIG_BLOCK, set())


class TestForkFailureRestoresMask:

    def test_mask_restored_when_fork_raises(self, shell, monkeypatch):
        before = _current_mask()
        # Sanity: the signals the launcher blocks are not already blocked,
        # otherwise this test could pass vacuously.
        assert signal.SIGINT not in before
        assert signal.SIGTERM not in before

        def failing_fork():
            # Fail at the worst moment: AFTER the launcher has blocked
            # signals (we are called between SIG_BLOCK and the parent path).
            assert signal.SIGINT in _current_mask(), \
                "launcher should have blocked signals before fork()"
            raise OSError(errno.EAGAIN, "Resource temporarily unavailable")

        monkeypatch.setattr(os, 'fork', failing_fork)

        config = ProcessConfig(role=ProcessRole.SINGLE)
        with pytest.raises(OSError):
            shell.process_launcher.launch(lambda: 0, config)

        after = _current_mask()
        assert after == before, (
            f"signal mask leaked after failed fork: before={before} after={after}")

    def test_helper_mask_restored_when_fork_raises(self, monkeypatch):
        """fork_with_signal_window() itself (used by ALL three fork sites:
        ProcessLauncher, command substitution, process substitution) must
        restore the mask when os.fork() raises."""
        before = _current_mask()
        assert signal.SIGINT not in before

        def failing_fork():
            assert signal.SIGINT in _current_mask(), \
                "helper should have blocked signals before fork()"
            raise OSError(errno.EAGAIN, "Resource temporarily unavailable")

        monkeypatch.setattr(os, 'fork', failing_fork)
        with pytest.raises(OSError):
            fork_with_signal_window()

        assert _current_mask() == before

    def test_helper_parent_mask_restored_on_success(self, monkeypatch):
        """Parent path: mask blocked for the (fake) fork, restored after."""
        before = _current_mask()

        def fake_fork():
            assert signal.SIGTERM in _current_mask()
            return 12345  # parent path; no real child created

        monkeypatch.setattr(os, 'fork', fake_fork)
        assert fork_with_signal_window() == 12345
        assert _current_mask() == before

    def test_helper_child_keeps_signals_blocked(self, monkeypatch):
        """Child path (pid 0): the mask must stay blocked — it is unblocked
        later by apply_child_signal_policy() after handlers are reset."""
        before = _current_mask()
        monkeypatch.setattr(os, 'fork', lambda: 0)
        try:
            assert fork_with_signal_window() == 0
            assert signal.SIGINT in _current_mask()
            assert signal.SIGTERM in _current_mask()
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, before)

    def test_mask_restored_after_successful_launch(self, shell):
        """The normal path must also leave the parent's mask untouched."""
        before = _current_mask()
        config = ProcessConfig(role=ProcessRole.SINGLE, foreground=False)
        pid, _pgid = shell.process_launcher.launch(lambda: 0, config)
        try:
            assert _current_mask() == before
        finally:
            # Reap the child so it doesn't linger as a zombie.
            try:
                os.waitpid(pid, 0)
            except OSError:
                pass


@pytest.mark.serial
class TestForkFailureHandledGracefully:
    """A fork failure (EAGAIN under process pressure) must not crash the
    shell: it reports an error, yields a sensible nonzero status, leaves
    the parent's signal mask intact, and the shell keeps running.

    Determinism: the fork is mocked to raise OSError(EAGAIN) — we never
    exhaust real process limits. These run in-process against the
    ``captured_shell`` fixture and monkeypatch ``fork_with_signal_window``
    at the two module references the launcher resolves. They are
    ``serial``-marked because they exercise the process-creation /
    signal-mask machinery.
    """

    def _patch_fork_to_fail(self, monkeypatch):
        """Make every fork site raise EAGAIN, deterministically."""
        from psh.executor import child_policy, process_launcher

        def boom():
            raise OSError(errno.EAGAIN, "Resource temporarily unavailable")

        # The launcher imported the helper by name (`from .child_policy
        # import ... fork_with_signal_window`), so patch BOTH the
        # definition and the launcher's bound reference.
        monkeypatch.setattr(child_policy, "fork_with_signal_window", boom)
        monkeypatch.setattr(
            process_launcher, "fork_with_signal_window", boom)

    def test_external_command_fork_failure_does_not_crash(
            self, captured_shell, monkeypatch):
        """`/bin/echo hi` with a failing fork: error reported, nonzero
        status, shell survives to run the next command."""
        before = _current_mask()
        self._patch_fork_to_fail(monkeypatch)

        rc = captured_shell.run_command('/bin/echo hi')
        # Graceful: nonzero status, no traceback escaping to the caller.
        assert rc != 0, "fork failure should yield a nonzero exit status"
        # An error was reported to stderr (message format is psh's errno
        # style; we only assert the failure surfaced, not exact wording).
        assert captured_shell.get_stderr() != ""

        # The shell is still usable afterwards and the parent's signal
        # mask was restored (no leaked block from the fork window).
        assert _current_mask() == before, "signal mask leaked after fork failure"

    def test_shell_keeps_running_after_fork_failure(
            self, captured_shell, monkeypatch):
        """After a fork failure on an external command, a subsequent
        builtin (no fork) still runs and produces its output."""
        self._patch_fork_to_fail(monkeypatch)
        # First command forks (and fails); the trailing builtin does not.
        rc = captured_shell.run_command('/bin/false; echo STILL_ALIVE')
        assert rc == 0, "trailing builtin should run and succeed"
        assert "STILL_ALIVE" in captured_shell.get_stdout()

    def test_pipeline_fork_failure_does_not_crash(
            self, captured_shell, monkeypatch):
        """A fork failure inside a pipeline is handled: nonzero status,
        mask restored, no crash."""
        before = _current_mask()
        self._patch_fork_to_fail(monkeypatch)

        rc = captured_shell.run_command('/bin/echo a | /bin/cat')
        assert rc != 0, "pipeline fork failure should yield nonzero status"
        assert _current_mask() == before, "signal mask leaked after pipeline fork failure"
        assert captured_shell.get_stderr() != ""
