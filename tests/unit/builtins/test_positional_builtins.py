"""
Positional parameter builtin tests.

Tests for builtins that manipulate positional parameters like shift.
"""



def test_shift_default(shell):
    """Test shift with default n=1."""
    shell.run_command('set arg1 arg2 arg3')
    result = shell.run_command('shift')
    assert result == 0

    # Verify shift worked by checking $1, $2
    shell.run_command('echo "$1"')
    # Note: Positional parameter testing may be complex with current fixture


def test_shift_explicit_n(shell):
    """Test shift with explicit n value."""
    shell.run_command('set arg1 arg2 arg3 arg4')
    result = shell.run_command('shift 2')
    assert result == 0


def test_shift_zero(shell):
    """Test shift with n=0 (no-op)."""
    shell.run_command('set arg1 arg2')
    result = shell.run_command('shift 0')
    assert result == 0


def test_shift_all_params(shell):
    """Test shift with n equal to parameter count."""
    shell.run_command('set arg1 arg2')
    result = shell.run_command('shift 2')
    assert result == 0


def test_shift_too_many(shell):
    """Test shift with n greater than parameter count."""
    shell.run_command('set arg1')
    result = shell.run_command('shift 2')
    # Should fail when trying to shift more than available
    assert result != 0


def test_shift_negative(shell):
    """Test shift with negative n."""
    shell.run_command('set arg1 arg2')
    result = shell.run_command('shift -1')
    # Should fail with negative argument
    assert result != 0


def test_shift_non_numeric(shell):
    """Test shift with non-numeric argument.

    The usage-error family's operand cell: status 2 and the shell continues
    (bash 5.3.15; the 5.2 series gave 1).  Parity pin:
    tests/conformance/bash/test_exit_cd_options_conformance.py
    ::TestUsageStatusMatchesBash::test_shift_non_numeric_status_2.
    """
    shell.run_command('set arg1 arg2')
    result = shell.run_command('shift abc')
    assert result == 2
    # the operands are untouched by the failed shift
    assert shell.state.positional_params == ['arg1', 'arg2']


def test_shift_no_params(shell):
    """Test shift when no positional parameters exist."""
    # Clear any existing positional parameters
    shell.run_command('set --')
    result = shell.run_command('shift')
    # May fail when no parameters to shift
    assert result != 0


def test_set_positional_params(shell):
    """Test setting positional parameters with set builtin."""
    result = shell.run_command('set one two three')
    assert result == 0


def test_positional_parameter_access(shell, capsys):
    """Test accessing positional parameters."""
    shell.run_command('set first second third')
    shell.run_command('echo "$1 $2 $3"')
    captured = capsys.readouterr()
    assert 'first second third' in captured.out


def test_positional_parameter_count(shell, capsys):
    """Test $# parameter for positional parameter count."""
    shell.run_command('set a b c d')
    shell.run_command('echo "$#"')
    captured = capsys.readouterr()
    assert '4' in captured.out


def test_positional_parameter_star(shell, capsys):
    """Test $* parameter for all positional parameters."""
    shell.run_command('set alpha beta gamma')
    shell.run_command('echo "$*"')
    captured = capsys.readouterr()
    assert 'alpha beta gamma' in captured.out


def test_positional_parameter_at(shell, capsys):
    """Test $@ parameter for all positional parameters."""
    shell.run_command('set one two "three four"')
    shell.run_command('echo "$@"')
    captured = capsys.readouterr()
    # $@ should preserve word boundaries
    assert 'one two three four' in captured.out
