"""
Command builtin tests.

Tests for the command builtin which executes commands while bypassing
function definitions and sometimes aliases.
"""



def test_command_builtin_exists(shell):
    """Test that command is registered as a builtin."""
    result = shell.run_command('type command')
    assert result == 0


def test_command_execute_builtin(shell, capsys):
    """Test executing a builtin with command."""
    result = shell.run_command('command echo hello')
    assert result == 0
    captured = capsys.readouterr()
    assert 'hello' in captured.out


def test_command_execute_external(shell):
    """Test executing external command with command builtin."""
    # Test with a common external command
    result = shell.run_command('command cat /dev/null')
    # May fail if command is not found or not implemented
    assert result == 0 or result == 126  # 126 = command not found
def test_command_bypass_function(shell, capsys):
    """Test that command bypasses functions."""
    # Define a function that shadows echo
    shell.run_command('echo() { printf "function echo"; }')

    # Normal call should use function
    shell.run_command('echo test')
    captured = capsys.readouterr()
    function_output = captured.out

    # Command should bypass function and use builtin
    shell.run_command('command echo test')
    captured = capsys.readouterr()
    builtin_output = captured.out

    # Outputs should be different
    assert function_output != builtin_output
    assert 'test' in builtin_output


def test_command_with_options(shell):
    """Test command builtin with various options."""
    # Test -v option (if supported)
    result = shell.run_command('command -v echo')
    assert result == 0


def test_command_default_path(shell):
    """Test command with -p option (default PATH)."""
    result = shell.run_command('command -p echo hello')
    assert result == 0


def test_command_nonexistent(shell):
    """Test command with non-existent command."""
    result = shell.run_command('command nonexistent_command_xyz')
    assert result != 0


def test_command_with_arguments(shell, capsys):
    """Test command with multiple arguments."""
    result = shell.run_command('command echo one two three')
    assert result == 0
    captured = capsys.readouterr()
    assert 'one two three' in captured.out


def test_command_verbose_option(shell, capsys):
    """Test command -v option for command identification."""
    result = shell.run_command('command -v echo')
    assert result == 0
    captured = capsys.readouterr()
    # Should print path or type of echo command
    assert 'echo' in captured.out


def test_command_verbose_description(shell, capsys):
    """Test command -V option for verbose description."""
    result = shell.run_command('command -V echo')
    assert result == 0
    captured = capsys.readouterr()
    # Should print detailed description
    assert 'echo' in captured.out


def test_command_error_handling(shell):
    """Test command error handling."""
    # Test with invalid option
    result = shell.run_command('command -xyz echo')
    # May or may not be implemented - just ensure no crash

    # bash: bare `command` succeeds silently (verified: rc 0)
    result = shell.run_command('command')
    assert result == 0


def test_command_search_order(shell):
    """Test that command searches in correct order."""
    # Should find builtins before external commands
    result = shell.run_command('command -v test')
    assert result == 0


def test_command_with_redirection(shell_with_temp_dir):
    """Test command with I/O redirection."""
    output_file = "command_output.txt"
    result = shell_with_temp_dir.run_command(f'command echo "redirected" > {output_file}')
    assert result == 0

    # Check file was created
    import os
    assert os.path.exists(output_file)


def test_command_with_environment(shell, capsys):
    """Test command with environment variable assignment."""
    result = shell.run_command('VAR=test command echo "$VAR"')
    assert result == 0
    # Environment variable should be available to the command


def test_command_help(shell):
    """Test command builtin help."""
    shell.run_command('command --help')
    # May succeed or fail depending on implementation


class TestCommandVLookup:
    """`command -v` / `command -V` lookup (bash-pinned).

    Regression: psh only checked builtins and PATH, so functions, aliases,
    and keywords were reported "not found" (rc 1), and the not-found
    message was hardcoded as `bash: type: ...`.

    bash lookup order (like `type`): alias > keyword > function > builtin
    > PATH. rc is 0 if at least one name was found, 1 otherwise.
    """

    def test_v_function_prints_name(self, captured_shell):
        result = captured_shell.run_command('f(){ :; }; command -v f')
        assert result == 0
        assert captured_shell.get_stdout() == "f\n"

    def test_V_function_prints_definition(self, captured_shell):
        result = captured_shell.run_command('f(){ echo hi; }; command -V f')
        assert result == 0
        out = captured_shell.get_stdout()
        assert out.startswith("f is a function\n")
        assert "echo hi" in out

    def test_v_alias_prints_definition_line(self, captured_shell):
        result = captured_shell.run_command(
            'alias x="echo hello"; command -v x')
        assert result == 0
        assert captured_shell.get_stdout() == "alias x='echo hello'\n"

    def test_V_alias(self, captured_shell):
        result = captured_shell.run_command(
            'alias x="echo hello"; command -V x')
        assert result == 0
        assert captured_shell.get_stdout() == "x is aliased to `echo hello'\n"

    def test_alias_beats_function(self, captured_shell):
        result = captured_shell.run_command(
            'f(){ :; }; alias f="echo aliased"; command -v f')
        assert result == 0
        assert captured_shell.get_stdout() == "alias f='echo aliased'\n"

    def test_v_builtin_prints_name(self, captured_shell):
        result = captured_shell.run_command('command -v true')
        assert result == 0
        assert captured_shell.get_stdout() == "true\n"

    def test_V_builtin(self, captured_shell):
        result = captured_shell.run_command('command -V true')
        assert result == 0
        assert captured_shell.get_stdout() == "true is a shell builtin\n"

    def test_v_keyword(self, captured_shell):
        result = captured_shell.run_command('command -v if')
        assert result == 0
        assert captured_shell.get_stdout() == "if\n"

    def test_V_keyword(self, captured_shell):
        result = captured_shell.run_command('command -V if')
        assert result == 0
        assert captured_shell.get_stdout() == "if is a shell keyword\n"

    def test_v_external_prints_path(self, captured_shell):
        result = captured_shell.run_command('command -v ls')
        assert result == 0
        out = captured_shell.get_stdout()
        assert out.startswith('/') and out.endswith('/ls\n')

    def test_V_external(self, captured_shell):
        result = captured_shell.run_command('command -V ls')
        assert result == 0
        out = captured_shell.get_stdout()
        assert out.startswith('ls is /') and out.endswith('/ls\n')

    def test_v_slash_path(self, captured_shell):
        result = captured_shell.run_command('command -v /bin/ls')
        assert result == 0
        assert captured_shell.get_stdout() == "/bin/ls\n"

    def test_v_not_found_silent_rc1(self, captured_shell):
        result = captured_shell.run_command('command -v nosuchcmd_zz123')
        assert result == 1
        assert captured_shell.get_stdout() == ""
        assert captured_shell.get_stderr() == ""

    def test_V_not_found_message_rc1(self, captured_shell):
        result = captured_shell.run_command('command -V nosuchcmd_zz123')
        assert result == 1
        assert captured_shell.get_stdout() == ""
        err = captured_shell.get_stderr()
        assert 'command: nosuchcmd_zz123: not found' in err
        assert 'bash:' not in err
        assert 'type:' not in err

    def test_v_multiple_names_rc0_if_any_found(self, captured_shell):
        result = captured_shell.run_command(
            'command -v nosuch_zz1 true nosuch_zz2')
        assert result == 0
        assert captured_shell.get_stdout() == "true\n"

    def test_v_multiple_names_all_found(self, captured_shell):
        result = captured_shell.run_command('f(){ :; }; command -v f true')
        assert result == 0
        assert captured_shell.get_stdout() == "f\ntrue\n"

    def test_v_multiple_names_rc1_if_none_found(self, captured_shell):
        result = captured_shell.run_command('command -v nosuch_zz1 nosuch_zz2')
        assert result == 1

    def test_v_no_names_rc0(self, captured_shell):
        result = captured_shell.run_command('command -v')
        assert result == 0
        assert captured_shell.get_stdout() == ""


class TestCommandFlagParsing:
    """parse_flags convergence (R9.D): clustered flags + bash-aligned errors."""

    def test_clustered_flags_accepted(self, captured_shell):
        # bash accepts clustered -vp / -pv; -v wins (prints the name).
        result = captured_shell.run_command('command -vp true')
        assert result == 0
        assert captured_shell.get_stdout() == "true\n"

    def test_invalid_option_message_and_rc(self, captured_shell):
        result = captured_shell.run_command('command -x true')
        assert result == 2
        err = captured_shell.get_stderr()
        assert 'command: -x: invalid option' in err
        assert 'command: usage: command [-pVv] command [arg ...]' in err
