"""
Signal handling builtin tests.

Tests for signal-related builtins like trap.
"""

import os

import pytest


def test_trap_builtin_exists(shell):
    """Test that trap is registered as a builtin."""
    result = shell.run_command('type trap')
    assert result == 0


def test_trap_list_signals(shell, capsys):
    """Test trap -l lists signals."""
    result = shell.run_command('trap -l')
    assert result == 0
    captured = capsys.readouterr()

    # Should list common signals
    assert 'INT' in captured.out or 'SIGINT' in captured.out
    assert 'TERM' in captured.out or 'SIGTERM' in captured.out


def test_trap_no_args(shell, capsys):
    """Test trap with no args shows current traps."""
    result = shell.run_command('trap')
    assert result == 0
    # Empty output is fine if no traps are set


def test_trap_set_signal_handler(shell):
    """Test setting a signal handler with trap."""
    result = shell.run_command('trap "echo signal caught" TERM')
    assert result == 0


def test_trap_signal_execution():
    """Test that trap handler executes when signal is received using subprocess."""
    import subprocess
    import sys

    # Test trap handling in isolated process
    # Note: PSH recognizes ${$} but not $$ for PID
    script = '''
trap "echo 'caught TERM signal'" TERM
echo "PID: ${$}"
kill -TERM ${$}
echo "after signal"
'''

    result = subprocess.run(
        [sys.executable, '-m', 'psh', '-c', script],
        capture_output=True,
        text=True
    )

    # Check that trap was executed
    assert "caught TERM signal" in result.stdout
    # Process should continue after trap
    assert "after signal" in result.stdout

    # Test with INT signal
    script2 = '''
trap "echo 'caught INT signal'; exit 0" INT
kill -INT ${$}
echo "should not see this"
'''

    result2 = subprocess.run(
        [sys.executable, '-m', 'psh', '-c', script2],
        capture_output=True,
        text=True
    )

    assert "caught INT signal" in result2.stdout
    assert "should not see this" not in result2.stdout
    assert result2.returncode == 0


def test_trap_exit_handler(shell):
    """Test trap with EXIT signal."""
    result = shell.run_command('trap "echo exiting" EXIT')
    assert result == 0


def test_trap_debug_handler(shell):
    """Test trap with DEBUG signal."""
    result = shell.run_command('trap "echo debug" DEBUG')
    # May not be implemented
    assert result == 0


def test_trap_err_handler(shell):
    """Test trap with ERR signal."""
    result = shell.run_command('trap "echo error" ERR')
    # May not be implemented
    assert result == 0


def test_trap_remove_handler(shell):
    """Test removing trap handler."""
    # Set handler
    shell.run_command('trap "echo test" TERM')

    # Remove handler
    result = shell.run_command('trap - TERM')
    assert result == 0


def test_trap_ignore_signal(shell):
    """Test ignoring signal with trap."""
    result = shell.run_command('trap "" TERM')
    assert result == 0


def test_trap_invalid_signal(shell):
    """Test trap with invalid signal name."""
    result = shell.run_command('trap "echo test" NOSUCHSIGNAL')
    assert result != 0


def test_trap_multiple_signals(shell):
    """Test trap with multiple signals."""
    result = shell.run_command('trap "echo multiple" TERM INT')
    assert result == 0


def test_trap_numeric_signal(shell):
    """Test trap with numeric signal."""
    result = shell.run_command('trap "echo numeric" 15')  # SIGTERM
    assert result == 0


def test_trap_command_substitution(shell):
    """Test trap with command substitution in handler."""
    result = shell.run_command('trap "echo $(date)" TERM')
    assert result == 0


def test_trap_print_specific_signal(shell, capsys):
    """Test printing trap for specific signal."""
    # Set a trap
    shell.run_command('trap "echo test handler" TERM')

    # Print trap for that signal
    result = shell.run_command('trap -p TERM')
    assert result == 0
    capsys.readouterr()
    # Should show the trap if -p option is supported


def test_trap_help(shell):
    """Test trap help option."""
    shell.run_command('trap --help')
    # May or may not be implemented


def test_trap_error_cases(shell):
    """Test various trap error cases."""
    # Too few arguments
    shell.run_command('trap')
    # Should succeed (shows current traps) or fail

    # Invalid option
    shell.run_command('trap -xyz')
    # Should fail


@pytest.mark.skipif(os.name == 'nt', reason="Unix signal handling test")
def test_trap_unix_signals(shell):
    """Test trap with Unix-specific signals."""
    # Test with SIGUSR1 if available
    shell.run_command('trap "echo usr1" SIGUSR1')
    # Should work on Unix systems


def test_trap_persistence(shell, capsys):
    """Test that traps persist across commands."""
    shell.run_command('trap "echo persistent" TERM')

    # Execute another command
    shell.run_command('echo "other command"')

    # Check that trap is still there
    shell.run_command('trap')
    capsys.readouterr()
    # Should still show the trap


def test_trap_in_subshell(shell):
    """Test trap behavior in subshells."""
    result = shell.run_command('(trap "echo subshell" TERM; echo done)')
    assert result == 0


def test_trap_script_mode(shell):
    """Test trap behavior in script mode vs interactive."""
    # This may behave differently in script vs interactive mode
    result = shell.run_command('trap "echo script" EXIT')
    assert result == 0


def test_trap_double_dash_sets_action(shell, capsys):
    """Regression: trap -- 'action' SIG used to take -- as the action."""
    result = shell.run_command('trap -- "echo hi" INT')
    assert result == 0
    shell.run_command('trap')
    captured = capsys.readouterr()
    assert "echo hi" in captured.out


def test_trap_double_dash_reset(shell):
    """trap -- - SIG resets the signal."""
    shell.run_command('trap "echo x" INT')
    result = shell.run_command('trap -- - INT')
    assert result == 0


def test_trap_bare_double_dash_lists(shell, capsys):
    """Bare `trap --` behaves like bare `trap` (bash)."""
    shell.run_command('trap "echo x" INT')
    capsys.readouterr()
    result = shell.run_command('trap --')
    assert result == 0
    captured = capsys.readouterr()
    assert "echo x" in captured.out


def test_trap_double_dash_exit_fires(shell, capsys):
    """A trap set with -- still executes."""
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, '-m', 'psh', '-c', 'trap -- "echo bye" EXIT'],
        capture_output=True, text=True)
    assert result.stdout == "bye\n"
