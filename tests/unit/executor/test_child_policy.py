"""Tests for apply_child_signal_policy() and run_child_shell()."""

import signal
import subprocess
import sys
import textwrap
from unittest.mock import MagicMock, call, patch

import pytest

from psh.core.exceptions import (
    FunctionReturn,
    LoopBreak,
    LoopContinue,
    TopLevelAbort,
)
from psh.executor.child_policy import (
    CHILD_EXIT_EXCEPTIONS,
    apply_child_signal_policy,
    map_child_exception,
)


class TestMapChildException:
    """The ONE child-exit taxonomy (H10): a control-flow/exit exception at a
    forked child's top → the child's exit code. Every fork site delegates
    here, so these pins guard the single mapping."""

    def test_top_level_abort_maps_to_status(self):
        assert map_child_exception(TopLevelAbort(2)) == 2

    def test_function_return_maps_to_exit_code(self):
        assert map_child_exception(FunctionReturn(3)) == 3

    def test_loop_break_maps_to_exit_status(self):
        assert map_child_exception(LoopBreak(exit_status=1)) == 1

    def test_loop_break_none_status_maps_to_zero(self):
        assert map_child_exception(LoopBreak(exit_status=None)) == 0

    def test_loop_continue_maps_to_exit_status(self):
        assert map_child_exception(LoopContinue(exit_status=0)) == 0

    def test_system_exit_int_maps_to_code(self):
        assert map_child_exception(SystemExit(4)) == 4

    def test_system_exit_none_maps_to_zero(self):
        # THE divergence the launcher copy got wrong (it mapped None → 1).
        # Python's own convention: a bare sys.exit()/SystemExit(None) → 0.
        assert map_child_exception(SystemExit(None)) == 0
        assert map_child_exception(SystemExit()) == 0

    def test_system_exit_nonint_noncode_maps_to_one(self):
        assert map_child_exception(SystemExit("boom")) == 1

    def test_unknown_exception_reraises(self):
        # Not one of the CHILD_EXIT_EXCEPTIONS: callers catch exactly that
        # group before delegating, so an unexpected type re-raises here.
        with pytest.raises(RuntimeError):
            map_child_exception(RuntimeError("x"))

    def test_taxonomy_tuple_is_the_five_families(self):
        assert set(CHILD_EXIT_EXCEPTIONS) == {
            TopLevelAbort, FunctionReturn, LoopBreak, LoopContinue, SystemExit,
        }


class TestLauncherChildExitTaxonomy:
    """ProcessLauncher's child body maps a body-level exit exception through
    the shared taxonomy (H10). The launcher forks-and-exits by design, so
    drive it in a subprocess: launch a body raising SystemExit(None)/(4) and
    report the child's wait status. On the pre-H10 tree the None case exited
    1 (the divergent launcher copy); after H10 it delegates to
    map_child_exception → 0.
    """

    DRIVER = textwrap.dedent('''
        import os
        from psh.shell import Shell
        from psh.executor.process_launcher import ProcessConfig, ProcessRole

        shell = Shell(norc=True)
        launcher = shell.process_launcher

        def spawn(body):
            cfg = ProcessConfig(role=ProcessRole.SINGLE, foreground=False)
            pid, _ = launcher.launch(body, cfg)
            _, status = os.waitpid(pid, 0)
            return os.WEXITSTATUS(status)

        def raise_none():
            raise SystemExit(None)

        def raise_int():
            raise SystemExit(4)

        print('none=%d' % spawn(raise_none), flush=True)
        print('int=%d' % spawn(raise_int), flush=True)
    ''')

    def test_launcher_system_exit_none_is_zero(self):
        result = subprocess.run(
            [sys.executable, '-c', self.DRIVER],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        lines = result.stdout.splitlines()
        assert 'none=0' in lines   # SystemExit(None) → 0 (was 1 pre-H10)
        assert 'int=4' in lines    # SystemExit(4) → 4


class TestApplyChildSignalPolicy:
    """Unit tests for the unified child signal policy."""

    def _make_mocks(self):
        """Create mock signal_manager and state."""
        signal_manager = MagicMock()
        state = MagicMock()
        state.in_forked_child = False
        return signal_manager, state

    def test_sets_in_forked_child_flag(self):
        """Policy sets state.in_forked_child = True."""
        signal_manager, state = self._make_mocks()
        apply_child_signal_policy(signal_manager, state)
        assert state.in_forked_child is True

    def test_calls_reset_child_signals_once(self):
        """Policy calls signal_manager.reset_child_signals() exactly once."""
        signal_manager, state = self._make_mocks()
        apply_child_signal_policy(signal_manager, state)
        signal_manager.reset_child_signals.assert_called_once()

    def test_shell_process_gets_sigttou_ign(self):
        """Shell processes get SIGTTOU=SIG_IGN after reset."""
        signal_manager, state = self._make_mocks()
        with patch('psh.executor.child_policy.signal') as mock_signal:
            mock_signal.SIGTTOU = signal.SIGTTOU
            mock_signal.SIG_IGN = signal.SIG_IGN
            apply_child_signal_policy(signal_manager, state, is_shell_process=True)
            # Last signal.signal call should set SIGTTOU to SIG_IGN
            sigttou_calls = [
                c for c in mock_signal.signal.call_args_list
                if c == call(signal.SIGTTOU, signal.SIG_IGN)
            ]
            # Called twice: once before reset (temporary), once after (shell process)
            assert len(sigttou_calls) == 2

    def test_leaf_process_gets_sigttou_from_reset(self):
        """Leaf processes (is_shell_process=False) only set SIGTTOU=SIG_IGN once (temporary)."""
        signal_manager, state = self._make_mocks()
        with patch('psh.executor.child_policy.signal') as mock_signal:
            mock_signal.SIGTTOU = signal.SIGTTOU
            mock_signal.SIG_IGN = signal.SIG_IGN
            apply_child_signal_policy(signal_manager, state, is_shell_process=False)
            sigttou_calls = [
                c for c in mock_signal.signal.call_args_list
                if c == call(signal.SIGTTOU, signal.SIG_IGN)
            ]
            # Only once: the temporary ignore before reset
            assert len(sigttou_calls) == 1

    def test_default_is_not_shell_process(self):
        """Default is_shell_process=False (leaf process behavior)."""
        signal_manager, state = self._make_mocks()
        with patch('psh.executor.child_policy.signal') as mock_signal:
            mock_signal.SIGTTOU = signal.SIGTTOU
            mock_signal.SIG_IGN = signal.SIG_IGN
            apply_child_signal_policy(signal_manager, state)
            sigttou_calls = [
                c for c in mock_signal.signal.call_args_list
                if c == call(signal.SIGTTOU, signal.SIG_IGN)
            ]
            assert len(sigttou_calls) == 1

    def test_call_order(self):
        """Policy sets state flag, then temporary SIGTTOU, then resets, then optionally re-ignores."""
        signal_manager, state = self._make_mocks()
        call_order = []

        def track_in_forked_child(value):
            call_order.append('set_flag')

        def track_reset():
            call_order.append('reset_signals')

        type(state).in_forked_child = property(
            fget=lambda s: False,
            fset=lambda s, v: call_order.append('set_flag')
        )
        signal_manager.reset_child_signals.side_effect = lambda: call_order.append('reset_signals')

        with patch('psh.executor.child_policy.signal') as mock_signal:
            mock_signal.SIGTTOU = signal.SIGTTOU
            mock_signal.SIG_IGN = signal.SIG_IGN
            mock_signal.signal.side_effect = lambda *a: call_order.append('signal_call')
            apply_child_signal_policy(signal_manager, state, is_shell_process=True)

        assert call_order == ['set_flag', 'signal_call', 'reset_signals', 'signal_call']


class TestCommandSubstitutionSignals:
    """Integration test: command substitution child has proper signal disposition."""

    def test_command_sub_basic_works(self):
        """Basic command substitution still works after policy change."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c', 'echo $(echo hello)'],
            capture_output=True, text=True, timeout=10,
        )
        assert result.stdout.strip() == 'hello'
        assert result.returncode == 0

    def test_process_sub_basic_works(self):
        """Basic process substitution still works after policy change."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c', 'cat <(echo test)'],
            capture_output=True, text=True, timeout=10,
        )
        assert result.stdout.strip() == 'test'
        assert result.returncode == 0


class TestRunChildShell:
    """Semantics of the shared substitution-child runner.

    run_child_shell() forks-and-exits by design, so it cannot be called
    in-process under pytest. These tests run a small driver in a
    subprocess: the driver forks via fork_with_signal_window(), runs a
    body through run_child_shell(), and the parent half reports the
    child's wait status — exactly the shape of the real call sites.
    """

    DRIVER = textwrap.dedent('''
        import os
        from psh.shell import Shell
        from psh.executor.child_policy import (
            fork_with_signal_window, run_child_shell,
        )

        shell = Shell(norc=True)

        def spawn(body, **kwargs):
            pid = fork_with_signal_window()
            if pid == 0:
                run_child_shell(shell, body, **kwargs)
            _, status = os.waitpid(pid, 0)
            return os.WEXITSTATUS(status)

        def returns_five(child):
            return 5

        def raises_system_exit(child):
            raise SystemExit(3)

        def raises_system_exit_none(child):
            raise SystemExit(None)

        def raises_runtime(child):
            raise RuntimeError('boom')

        def checks_child_flag(child):
            # The runner must mark the child shell as a forked child.
            return 0 if child.state.in_forked_child else 9

        def runs_command(child):
            # The child shell is a working psh: body output reaches fd 1.
            return child.run_command('echo child-ran', add_to_history=False)

        # flush=True throughout: a buffered parent print would be
        # duplicated by the next forked child's exit-time flush.
        print('return5=%d' % spawn(returns_five), flush=True)
        print('sysexit3=%d' % spawn(raises_system_exit), flush=True)
        print('sysexit_none=%d' % spawn(raises_system_exit_none), flush=True)
        print('raise=%d' % spawn(raises_runtime, error_label='unit-test child'),
              flush=True)
        print('flag=%d' % spawn(checks_child_flag), flush=True)
        print('command=%d' % spawn(runs_command), flush=True)
    ''')

    def _run_driver(self):
        return subprocess.run(
            [sys.executable, '-c', self.DRIVER],
            capture_output=True, text=True, timeout=30,
        )

    def test_runner_exit_code_semantics(self):
        """Body return / SystemExit / unexpected exception map to exit codes."""
        result = self._run_driver()
        assert result.returncode == 0, result.stderr
        lines = result.stdout.splitlines()
        assert 'return5=5' in lines           # body return value -> exit code
        assert 'sysexit3=3' in lines          # SystemExit(3) -> 3
        assert 'sysexit_none=0' in lines      # SystemExit(None) -> 0
        assert 'raise=1' in lines             # unexpected exception -> 1
        assert 'flag=0' in lines              # in_forked_child was set
        assert 'command=0' in lines           # child shell executes commands
        assert 'child-ran' in lines           # ... whose output reaches fd 1

    def test_runner_reports_unexpected_exception_on_stderr(self):
        """An unexpected body exception is reported on fd 2 with the label."""
        result = self._run_driver()
        assert 'psh: unit-test child error: boom' in result.stderr

    def test_process_sub_exit_builtin_terminates_child_only(self):
        """`exit` inside <(...) terminates the substitution child, not psh."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c', 'cat <(exit 3); echo after:$?'],
            capture_output=True, text=True, timeout=10,
        )
        assert result.stdout.strip() == 'after:0'
        assert result.returncode == 0

    def test_command_sub_exit_builtin_status(self):
        """`exit 7` in $(...) becomes the substitution's status."""
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c', 'x=$(exit 7); echo $?'],
            capture_output=True, text=True, timeout=10,
        )
        assert result.stdout.strip() == '7'
        assert result.returncode == 0
