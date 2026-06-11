"""Interactive signal handlers must be restored when the REPL exits.

Regression tests for the v0.300 lifecycle fix: InteractiveManager.
run_interactive_loop() installs process-global signal handlers via
SignalManager.setup_signal_handlers() but previously never called
restore_default_handlers() on any exit path. When psh IS the process the
handlers die with it, but an EMBEDDED Shell (a Shell object inside another
Python process — e.g. this test suite) must hand the host's signal
dispositions back when the loop ends.

These tests stub the REPL body (no PTY needed): the lifecycle under test is
setup -> loop -> restore at the run_interactive_loop() boundary.
"""

import signal

import pytest

# The interactive handler set installed by _setup_interactive_mode_handlers().
INTERACTIVE_SIGNALS = [
    signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT,
    signal.SIGTSTP, signal.SIGTTOU, signal.SIGTTIN,
    signal.SIGCHLD, signal.SIGPIPE, signal.SIGWINCH,
]

pytestmark = pytest.mark.serial  # mutates process-global signal dispositions


def _snapshot():
    return {sig: signal.getsignal(sig) for sig in INTERACTIVE_SIGNALS}


@pytest.fixture
def embedded_loop(shell, monkeypatch):
    """A shell whose interactive loop can run in-process without a PTY."""
    shell.state.is_script_mode = False
    im = shell.interactive_manager
    # Don't perturb the test process's process group / terminal.
    monkeypatch.setattr(im.signal_manager, 'ensure_foreground', lambda: None)
    return shell


class TestHandlerRestorationOnLoopExit:

    def test_handlers_restored_after_normal_exit(self, embedded_loop, monkeypatch):
        shell = embedded_loop
        im = shell.interactive_manager
        before = _snapshot()
        seen_inside = {}

        def fake_run():
            seen_inside.update(_snapshot())
            return 0  # immediate EOF-style exit

        monkeypatch.setattr(im.repl_loop, 'run', fake_run)
        im.run_interactive_loop()

        # Handlers really were installed while the loop ran...
        assert seen_inside[signal.SIGINT] != before[signal.SIGINT]
        assert callable(seen_inside[signal.SIGCHLD])
        # ...and every one is back to the host's disposition afterwards.
        assert _snapshot() == before

    def test_handlers_restored_when_exit_builtin_raises_system_exit(
            self, embedded_loop, monkeypatch):
        """The `exit` builtin leaves the loop via SystemExit; the finally at
        the run_interactive_loop boundary must still restore handlers."""
        shell = embedded_loop
        im = shell.interactive_manager
        before = _snapshot()

        def fake_run():
            raise SystemExit(3)

        monkeypatch.setattr(im.repl_loop, 'run', fake_run)
        with pytest.raises(SystemExit):
            im.run_interactive_loop()

        assert _snapshot() == before

    def test_handlers_restored_on_unexpected_exception(self, embedded_loop, monkeypatch):
        shell = embedded_loop
        im = shell.interactive_manager
        before = _snapshot()

        def fake_run():
            raise RuntimeError("repl blew up")

        monkeypatch.setattr(im.repl_loop, 'run', fake_run)
        with pytest.raises(RuntimeError):
            im.run_interactive_loop()

        assert _snapshot() == before


class TestLifecycleReentrancy:

    def test_loop_can_run_twice_on_one_shell(self, embedded_loop, monkeypatch):
        """restore closes the SIGCHLD/SIGWINCH self-pipes; a second
        run_interactive_loop() must recreate them and still restore."""
        shell = embedded_loop
        im = shell.interactive_manager
        before = _snapshot()
        notifier_fds = []

        def fake_run():
            notifier_fds.append(im.signal_manager._sigchld_notifier.get_fd())
            return 0

        monkeypatch.setattr(im.repl_loop, 'run', fake_run)
        im.run_interactive_loop()
        # After restore the self-pipe is closed (fd marked -1)...
        assert im.signal_manager._sigchld_notifier.get_fd() == -1
        im.run_interactive_loop()

        # ...but both runs had a live notifier fd while the loop was active.
        assert len(notifier_fds) == 2
        assert all(fd >= 0 for fd in notifier_fds)
        assert _snapshot() == before

    def test_double_setup_restores_true_originals(self, embedded_loop):
        """psh's __main__ installs handlers, then run_interactive_loop runs
        setup again. Restoration must return to the PRE-psh dispositions,
        not to the handlers the first setup installed."""
        shell = embedded_loop
        sm = shell.interactive_manager.signal_manager
        before = _snapshot()

        sm.setup_signal_handlers()   # e.g. __main__ startup
        sm.setup_signal_handlers()   # e.g. run_interactive_loop
        sm.restore_default_handlers()

        assert _snapshot() == before
