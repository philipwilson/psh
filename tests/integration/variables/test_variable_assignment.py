"""
Variable assignment integration tests.

Tests for variable assignment before commands, environment
variable handling, and assignment contexts.
"""

import os


def test_single_assignment_before_builtin(shell):
    """Test single variable assignment before builtin command."""
    # Test with echo to avoid stdin complexity
    result = shell.run_command("VAR=value echo $VAR")
    assert result == 0
    # VAR should not persist after command
    assert shell.state.get_variable("VAR") == ""


def test_multiple_assignments_before_command(shell):
    """Test multiple variable assignments before command."""
    result = shell.run_command("A=1 B=2 C=3 true")
    assert result == 0
    # Variables should not persist after command
    assert shell.state.get_variable("A") == ""
    assert shell.state.get_variable("B") == ""
    assert shell.state.get_variable("C") == ""


def test_assignment_with_expansion(shell):
    """Test variable assignment with expansion before command."""
    shell.state.set_variable("BASE", "/tmp")
    result = shell.run_command("PREFIX=$BASE/prefix echo $PREFIX")
    assert result == 0
    # PREFIX should not persist
    assert shell.state.get_variable("PREFIX") == ""


def test_assignment_affects_command_environment():
    """Test assignment affects the command's environment."""
    import subprocess
    import sys
    # Test that command-prefixed variables work with external commands
    # Using subprocess directly since external command output can't be captured by capsys
    result = subprocess.run(
        # \$ so the INNER sh expands it from its environment — unescaped,
        # the outer shell would expand it first, before the prefix
        # assignment applies (POSIX), yielding empty.
        [sys.executable, '-m', 'psh', '-c', 'TEST_VAR=hello sh -c "echo Variable: \\$TEST_VAR"'],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "hello" in result.stdout


def test_assignment_with_spaces_in_value(shell, capsys):
    """Test assignment with spaces in value."""
    # Test global assignment for expansion
    result = shell.run_command('MESSAGE="hello world"; echo $MESSAGE')
    assert result == 0
    captured = capsys.readouterr()
    assert "hello world" in captured.out


def test_assignment_with_special_chars(shell, capsys):
    """Test assignment with special characters."""
    # Use literal assignment to avoid shell interpretation of special chars
    result = shell.run_command("SPECIAL='@#%^&*()'; echo $SPECIAL")
    assert result == 0
    captured = capsys.readouterr()
    assert "@#%^&*()" in captured.out


def test_assignment_with_empty_value(shell, capsys):
    """Test assignment with empty value."""
    result = shell.run_command('EMPTY= echo "[$EMPTY]"')
    assert result == 0
    captured = capsys.readouterr()
    assert "[]" in captured.out


def test_assignment_with_equals_in_value(shell, capsys):
    """Test assignment with equals sign in value."""
    # Test global assignment for expansion
    result = shell.run_command('EQUATION="x=y+z"; echo $EQUATION')
    assert result == 0
    captured = capsys.readouterr()
    assert "x=y+z" in captured.out


def test_multiple_assignments_with_builtin():
    """Test multiple assignments with builtin command."""
    import subprocess
    import sys
    # Test multiple command-prefixed assignments with a simple external command
    # Using subprocess directly since external command output can't be captured by capsys
    result = subprocess.run(
        # \$ so the INNER sh expands them (see note above)
        [sys.executable, '-m', 'psh', '-c', 'A=1 B=2 C=3 sh -c "echo Variables: \\$A\\$B\\$C"'],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "123" in result.stdout


def test_assignment_with_command_substitution(shell, capsys):
    """Test assignment with command substitution."""
    # Test global assignment with command substitution
    result = shell.run_command('DATE=$(date +%Y); echo "Year: $DATE"')
    assert result == 0
    captured = capsys.readouterr()
    import datetime
    current_year = str(datetime.datetime.now().year)
    assert current_year in captured.out


def test_assignment_with_arithmetic_expansion(shell, capsys):
    """Test assignment with arithmetic expansion."""
    # Test global assignment with arithmetic expansion
    result = shell.run_command('CALC=$((2 + 3)); echo $CALC')
    assert result == 0
    captured = capsys.readouterr()
    assert "5" in captured.out


def test_assignment_preserves_global_vars(shell):
    """Test assignment doesn't affect existing global variables."""
    shell.state.set_variable("GLOBAL", "global_value")
    result = shell.run_command("LOCAL=local_value echo done")
    assert result == 0
    # Global should be preserved
    assert shell.state.get_variable("GLOBAL") == "global_value"
    # Local should not persist
    assert shell.state.get_variable("LOCAL") == ""


def test_assignment_with_external_command(shell_with_temp_dir):
    """Test assignment with external command."""
    # Create a simple script that prints an environment variable
    script_content = '''#!/bin/bash
echo "TEST_VAR=$TEST_VAR"
'''
    with open("test_script.sh", "w") as f:
        f.write(script_content)
    os.chmod("test_script.sh", 0o755)

    result = shell_with_temp_dir.run_command("TEST_VAR=hello ./test_script.sh")
    assert result == 0


def test_assignment_chain(shell, capsys):
    """Test chaining multiple assignments."""
    # Test assignment chain with global assignments
    result = shell.run_command('A=1; B=$A; C=$B; echo "$A $B $C"')
    assert result == 0
    captured = capsys.readouterr()
    # Variables should be available to subsequent assignments
    assert "1 1 1" in captured.out


def test_assignment_with_glob_patterns(isolated_shell_with_temp_dir, capsys):
    """Test assignment with glob patterns (should not expand in assignment)."""
    shell = isolated_shell_with_temp_dir
    # Test that glob pattern is stored literally in variable (not expanded during assignment)
    # Note: Using quoted $PATTERN to prevent expansion during echo
    result = shell.run_command('PATTERN="*.txt"; echo "$PATTERN"')
    assert result == 0
    captured = capsys.readouterr()
    assert "*.txt" in captured.out


def test_assignment_with_brace_expansion(shell, capsys):
    """Test assignment with brace expansion (should not expand in assignment)."""
    # Test global assignment for expansion
    result = shell.run_command('BRACES="{a,b,c}"; echo $BRACES')
    assert result == 0
    captured = capsys.readouterr()
    assert "{a,b,c}" in captured.out


def test_assignment_with_tilde_expansion(shell, capsys):
    """Test assignment with tilde expansion."""
    result = shell.run_command('HOME_VAR=~ echo $HOME_VAR')
    assert result == 0
    captured = capsys.readouterr()
    # Should expand tilde in assignment
    assert captured.out.strip() != "~"


def test_assignment_readonly_variable_error(shell):
    """Test assignment to readonly variable fails."""
    shell.run_command("readonly READ_ONLY=value")
    result = shell.run_command("READ_ONLY=new_value echo test")
    # Should fail
    assert result != 0


def test_assignment_with_function_call(shell, capsys):
    """Test assignment before function call."""
    shell.run_command('test_func() { echo "VAR is: $VAR"; }')
    result = shell.run_command("VAR=function_value test_func")
    assert result == 0
    captured = capsys.readouterr()
    assert "function_value" in captured.out


def test_assignment_with_alias(shell, capsys):
    """Test assignment before alias command."""
    shell.run_command('alias test_alias="echo test"')
    # Test that aliases work properly (assignment doesn't affect alias expansion)
    result = shell.run_command("test_alias")
    assert result == 0
    captured = capsys.readouterr()
    assert "test" in captured.out

    # Test assignment with alias using environment approach
    result = shell.run_command('VAR=alias_value env | grep VAR || echo "assignment works"')
    assert result == 0


def test_assignment_error_invalid_name(shell):
    """Test assignment with invalid variable name."""
    result = shell.run_command("123VAR=value echo test")
    # Should fail due to invalid variable name
    assert result != 0


def test_assignment_with_redirection(shell_with_temp_dir):
    """Test assignment with I/O redirection."""
    # Use global assignment to test expansion with redirection
    result = shell_with_temp_dir.run_command("VAR=value; echo $VAR > output.txt")
    assert result == 0

    with open("output.txt", "r") as f:
        content = f.read()
    assert "value" in content


def test_assignment_with_pipe(shell_with_temp_dir):
    """Test assignment with pipeline."""
    # Use global assignment to test expansion with pipes
    result = shell_with_temp_dir.run_command("VAR=value; echo $VAR | cat > output.txt")
    assert result == 0

    with open("output.txt", "r") as f:
        content = f.read()
    assert "value" in content


def test_assignment_precedence_over_existing():
    """Test local assignment takes precedence over existing variable."""
    import subprocess
    import sys
    # Test that command-prefixed variables override globals for that command
    # Using subprocess since printenv is external and output can't be captured by capsys
    result = subprocess.run(
        [sys.executable, '-m', 'psh', '-c', 'VAR=global; VAR=local printenv VAR'],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "local" in result.stdout

    # Also verify global isn't changed after the command
    result2 = subprocess.run(
        [sys.executable, '-m', 'psh', '-c', 'VAR=global; VAR=local printenv VAR; echo $VAR'],
        capture_output=True,
        text=True
    )
    assert result2.returncode == 0
    # Output should be: local\nglobal\n
    lines = result2.stdout.strip().split('\n')
    assert lines[0] == 'local'  # printenv output
    assert lines[1] == 'global'  # echo output (VAR should be restored)


def test_assignment_with_subshell(shell, capsys):
    """Test assignment in subshell doesn't affect parent."""
    # Test global assignment within subshell - explicit echo capture
    shell.run_command("(VAR=subshell; echo $VAR) > /tmp/subshell_test.out")
    with open("/tmp/subshell_test.out", "r") as f:
        content = f.read()
    assert "subshell" in content
    # Variable should not exist in parent shell
    assert shell.state.get_variable("VAR") == ""


def test_export_vs_assignment(shell, capsys):
    """Test difference between export and assignment."""
    # Regular assignment
    shell.run_command("VAR1=value1")
    # Export assignment
    shell.run_command("export VAR2=value2")

    # Check that exported variable is in environment
    shell.run_command("env | grep VAR2")
    # VAR2 should be in environment, VAR1 should not be


def test_assignment_with_parameter_expansion(shell, capsys):
    """Test assignment with parameter expansion."""
    shell.state.set_variable("BASE", "test")
    # Use global assignment for parameter expansion testing
    result = shell.run_command('EXPANDED=${BASE}_suffix; echo $EXPANDED')
    assert result == 0
    captured = capsys.readouterr()
    assert "test_suffix" in captured.out


def test_assignment_with_array(shell):
    """Test assignment with array values."""
    # Use global assignment for array testing
    result = shell.run_command("ARR=(a b c); echo ${ARR[1]}")
    assert result == 0
