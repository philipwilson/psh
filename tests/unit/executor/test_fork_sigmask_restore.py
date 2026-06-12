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
