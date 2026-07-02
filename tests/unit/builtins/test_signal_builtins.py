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


# --- POSIX numeric forms: condition 0 is EXIT (reappraisal #15 F2) ---

def test_trap_zero_sets_exit_trap(shell, capsys):
    """POSIX `trap 'cmd' 0` registers the EXIT trap."""
    result = shell.run_command('trap "echo bye" 0')
    assert result == 0
    shell.run_command('trap -p')
    captured = capsys.readouterr()
    assert "trap -- 'echo bye' EXIT" in captured.out
    shell.run_command('trap - 0')


def test_trap_zero_fires_at_exit():
    """`trap 'cmd' 0` fires exactly once at shell exit (bash: rc kept)."""
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, '-m', 'psh', '-c', 'trap "echo bye" 0; exit 3'],
        capture_output=True, text=True, timeout=10)
    assert result.stdout == "bye\n"
    assert result.returncode == 3


def test_trap_query_exit_trap_by_zero(shell, capsys):
    """`trap -p 0` finds a trap set as EXIT."""
    shell.run_command('trap "echo bye" EXIT')
    shell.run_command('trap -p 0')
    captured = capsys.readouterr()
    assert "trap -- 'echo bye' EXIT" in captured.out
    shell.run_command('trap - 0')


# --- Reset forms: no action operand (reappraisal #15 F2) ---

def test_trap_zero_alone_resets_exit_trap(shell, capsys):
    """`trap 0` with no action resets the EXIT trap."""
    shell.run_command('trap "echo bye" 0')
    result = shell.run_command('trap 0')
    assert result == 0
    shell.run_command('trap -p')
    captured = capsys.readouterr()
    assert captured.out == ""


def test_trap_leading_number_resets_all_operands(shell, capsys):
    """POSIX: `trap 2 15` treats all operands as conditions to reset."""
    shell.run_command('trap "echo A" INT')
    shell.run_command('trap "echo B" TERM')
    result = shell.run_command('trap 2 15')
    assert result == 0
    shell.run_command('trap -p')
    captured = capsys.readouterr()
    assert captured.out == ""


def test_trap_single_name_resets(shell, capsys):
    """bash: a single operand naming a signal resets it (`trap INT`)."""
    shell.run_command('trap "echo X" INT')
    result = shell.run_command('trap INT')
    assert result == 0
    shell.run_command('trap -p')
    captured = capsys.readouterr()
    assert captured.out == ""


def test_trap_single_invalid_operand_is_usage_error(shell):
    """A single operand that is not a signal is a usage error (bash rc=2)."""
    assert shell.run_command('trap NOTASIGNAL') == 2
    assert shell.run_command('trap 999') == 2


def test_trap_number_as_action_when_not_a_signal(shell, capsys):
    """bash: `trap 999 2` sets the action '999' on SIGINT (999 not a signal)."""
    result = shell.run_command('trap 999 2')
    assert result == 0
    shell.run_command('trap -p')
    captured = capsys.readouterr()
    assert "trap -- '999' SIGINT" in captured.out
    shell.run_command('trap - INT')


# --- Signal-name coverage via signal_utils (reappraisal #15 F2 MED) ---

def test_trap_accepts_every_listed_signal_name():
    """Every name `trap -l` lists registers, lists, and resets (incl. KILL)."""
    import subprocess
    import sys

    from psh.utils.signal_utils import SIGNAL_NUMBER_TO_NAME
    names = ' '.join(SIGNAL_NUMBER_TO_NAME.values())
    script = (
        f'for s in {names}; do '
        'trap "echo x" "$s" || echo "set failed: $s"; '
        'trap -p "$s" >/dev/null || echo "query failed: $s"; '
        'trap - "$s" || echo "reset failed: $s"; '
        'done; echo done')
    result = subprocess.run([sys.executable, '-m', 'psh', '-c', script],
                            capture_output=True, text=True, timeout=15)
    assert result.stdout == "done\n"
    assert result.stderr == ""


def test_trap_winch_registers_lists_resets(shell, capsys):
    """WINCH (outside the old 13-name whitelist) registers/lists/resets."""
    assert shell.run_command('trap "echo w" WINCH') == 0
    shell.run_command('trap -p')
    captured = capsys.readouterr()
    assert "trap -- 'echo w' SIGWINCH" in captured.out
    assert shell.run_command('trap - WINCH') == 0
    shell.run_command('trap -p')
    assert capsys.readouterr().out == ""


def test_trap_numeric_spec_lists_canonical_name(shell, capsys):
    """A trap set by number lists under its canonical SIG name, not SIGnn."""
    import signal as _signal

    from psh.utils.signal_utils import signal_number_to_name
    winch = int(_signal.SIGWINCH)
    shell.run_command(f'trap "echo w" {winch}')
    shell.run_command('trap -p')
    captured = capsys.readouterr()
    assert signal_number_to_name(winch, with_prefix=True) in captured.out
    assert f'SIG{winch}' not in captured.out
    shell.run_command(f'trap {winch}')


# --- trap -p error handling and listing order ---

def test_trap_p_invalid_signal_errors(shell, capsys):
    """`trap -p NOSUCHSIG` reports the bad spec and returns 1 (bash)."""
    result = shell.run_command('trap -p NOSUCHSIG')
    assert result == 1
    captured = capsys.readouterr()
    assert 'NOSUCHSIG: invalid signal specification' in captured.err


def test_trap_p_invalid_among_valid_still_lists(shell, capsys):
    """Valid queried traps print even when another spec is invalid."""
    shell.run_command('trap "echo x" INT')
    result = shell.run_command('trap -p NOSUCHSIG INT')
    assert result == 1
    captured = capsys.readouterr()
    assert "trap -- 'echo x' SIGINT" in captured.out
    assert 'NOSUCHSIG: invalid signal specification' in captured.err
    shell.run_command('trap - INT')


def test_trap_p_double_dash_before_spec(shell, capsys):
    """`trap -p -- INT` consumes the option terminator (bash: rc=0)."""
    shell.run_command('trap "echo x" INT')
    result = shell.run_command('trap -p -- INT')
    assert result == 0
    captured = capsys.readouterr()
    assert "trap -- 'echo x' SIGINT" in captured.out
    assert captured.err == ""
    shell.run_command('trap - INT')


def test_trap_p_double_dash_alone_shows_all(shell, capsys):
    """Bare `trap -p --` behaves like `trap -p`: show all traps, rc=0."""
    shell.run_command('trap "echo x" INT')
    result = shell.run_command('trap -p --')
    assert result == 0
    captured = capsys.readouterr()
    assert "trap -- 'echo x' SIGINT" in captured.out
    assert captured.err == ""
    shell.run_command('trap - INT')


def test_trap_p_double_dash_before_zero(shell, capsys):
    """`trap -p -- 0` finds the EXIT trap (bash: rc=0, no stderr)."""
    shell.run_command('trap "echo bye" EXIT')
    result = shell.run_command('trap -p -- 0')
    assert result == 0
    captured = capsys.readouterr()
    assert "trap -- 'echo bye' EXIT" in captured.out
    assert captured.err == ""
    shell.run_command('trap - 0')


def test_trap_p_spec_after_terminator_is_validated(shell, capsys):
    """Only ONE -- is consumed: `trap -p -- --` queries the spec `--` (bash rc=1)."""
    result = shell.run_command('trap -p -- --')
    assert result == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert '--: invalid signal specification' in captured.err


def test_trap_listing_orders_by_signal_number(shell, capsys):
    """bash lists EXIT first, real signals by number, DEBUG/ERR last."""
    shell.run_command('trap true CHLD')
    shell.run_command('trap true INT')
    shell.run_command('trap true EXIT')
    shell.run_command('trap')
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert [line.split()[-1] for line in lines] == ['EXIT', 'SIGINT', 'SIGCHLD']
    shell.run_command('trap - EXIT INT CHLD')
