"""Tests for apply_child_signal_policy()."""

import signal
import subprocess
import sys
from unittest.mock import MagicMock, call, patch

from psh.executor.child_policy import apply_child_signal_policy


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
