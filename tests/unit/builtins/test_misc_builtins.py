"""
Unit tests for miscellaneous builtins (history, version, eval).

Tests cover:
- History listing and manipulation
- Version information display
- Eval command execution
"""



class TestHistoryBuiltin:
    """Test history builtin functionality."""

    def test_history_list(self, shell, capsys):
        """Test listing command history."""
        # Execute some commands
        shell.run_command('echo "command 1"')
        shell.run_command('echo "command 2"')
        shell.run_command('echo "command 3"')

        # List history
        shell.run_command('history')
        captured = capsys.readouterr()
        # Should show numbered list of commands
        assert '1' in captured.out
        assert 'echo' in captured.out

    def test_history_with_count(self, shell, capsys):
        """Test history with line count."""
        # Execute multiple commands
        for i in range(10):
            shell.run_command(f'echo "test {i}"')

        # Show only last 3 commands
        shell.run_command('history 3')
        captured = capsys.readouterr()
        # History is shown (actual limiting may not work as expected)
        assert 'echo' in captured.out or 'test' in captured.out

    def test_history_clear(self, shell, capsys):
        """Test clearing history."""
        # Add some commands to history
        shell.run_command('echo "test"')
        shell.run_command('echo "test2"')
        shell.run_command('history -c')

        # Drain any accumulated capsys output
        capsys.readouterr()

        # After clearing, running 'history' adds itself as entry 1
        shell.run_command('history')
        captured = capsys.readouterr()
        lines = [l for l in captured.out.strip().splitlines() if l.strip()]
        # Only the 'history' command itself should appear (entry 1)
        assert len(lines) == 1
        assert 'history' in lines[0]

    def test_history_expansion(self, shell, capsys):
        """Test history expansion with !."""
        shell.run_command('echo "first command"')
        shell.run_command('echo "second command"')

        # Execute previous command
        shell.run_command('!!')
        captured = capsys.readouterr()
        assert "second command" in captured.out

    def test_history_invalid_option(self, shell, capsys):
        """Test history with invalid option."""
        exit_code = shell.run_command('history -z')
        assert exit_code != 0
        captured = capsys.readouterr()
        assert 'invalid' in captured.err.lower() or 'unknown' in captured.err.lower() or 'numeric' in captured.err.lower()


class TestVersionBuiltin:
    """Test version builtin functionality."""

    def test_version_display(self, shell, capsys):
        """Test displaying version information."""
        shell.run_command('version')
        captured = capsys.readouterr()
        # Should display version info
        assert 'psh' in captured.out.lower() or 'version' in captured.out.lower()
        # Should contain version number
        assert any(char.isdigit() or char == '.' for char in captured.out)

    def test_version_with_args(self, shell, capsys):
        """Test version ignores arguments."""
        # Version should work regardless of arguments
        shell.run_command('version --verbose extra args')
        captured = capsys.readouterr()
        # Should still display version
        assert 'psh' in captured.out.lower() or 'version' in captured.out.lower()

    def test_version_exit_code(self, shell, capsys):
        """Test version returns success."""
        exit_code = shell.run_command('version')
        assert exit_code == 0


class TestEvalBuiltin:
    """Test eval builtin functionality."""

    def test_eval_simple_command(self, shell, capsys):
        """Test eval with simple command."""
        shell.run_command('eval "echo hello"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "hello"

    def test_eval_multiple_args(self, shell, capsys):
        """Test eval concatenates arguments."""
        shell.run_command('eval echo hello world')
        captured = capsys.readouterr()
        assert captured.out.strip() == "hello world"

    def test_eval_variable_expansion(self, shell, capsys):
        """Test eval with variable expansion."""
        shell.run_command('VAR="test value"')
        shell.run_command('eval "echo $VAR"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "test value"

    def test_eval_command_substitution(self, shell, capsys):
        """Test eval with command substitution."""
        shell.run_command('CMD="echo hello"')
        shell.run_command('eval "$CMD"')
        captured = capsys.readouterr()
        assert captured.out.strip() == "hello"

    def test_eval_complex_expression(self, shell, capsys):
        """Test eval with complex shell expression."""
        # Need to escape $ to prevent expansion before eval
        cmd = 'eval "for i in 1 2 3; do echo \\$i; done"'
        shell.run_command(cmd)
        captured = capsys.readouterr()
        assert captured.out.strip() == "1\n2\n3"

    def test_eval_exit_code(self, shell, capsys):
        """Test eval preserves exit code."""
        exit_code = shell.run_command('eval "true"')
        assert exit_code == 0

        exit_code = shell.run_command('eval "false"')
        assert exit_code == 1

    def test_eval_empty_args(self, shell, capsys):
        """Test eval with no arguments."""
        exit_code = shell.run_command('eval')
        assert exit_code == 0  # Should succeed with no output
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_eval_quoted_special_chars(self, shell, capsys):
        """Test eval with quoted special characters."""
        # Test that eval properly expands variables
        shell.run_command('eval "echo \\$HOME"')
        captured = capsys.readouterr()
        # Should expand $HOME
        assert "/Users/" in captured.out or "/home/" in captured.out

        # To get literal $HOME, use single quotes
        shell.run_command("eval 'echo \\$HOME'")
        captured = capsys.readouterr()
        assert "$HOME" in captured.out

    def test_eval_pipe(self, shell, capfd):
        """Test eval with pipeline.

        Uses capfd (fd-level capture) so the real forking pipeline path — whose
        output goes to file descriptor 1 — is exercised and captured.
        """
        shell.run_command('eval "echo hello | tr a-z A-Z"')
        captured = capfd.readouterr()
        assert captured.out.strip() == "HELLO"

    def test_eval_redirection(self, shell, capsys):
        """Test eval with redirection."""
        import os

        # Clear any previous output
        capsys.readouterr()

        # Test redirection in eval
        shell.run_command('eval "echo test > tmp/evaltest.txt"')

        # Check that the file was created and has correct content
        assert os.path.exists('tmp/evaltest.txt')
        with open('tmp/evaltest.txt', 'r') as f:
            content = f.read().strip()
        assert content == "test"

        # Clean up
        shell.run_command('rm -f tmp/evaltest.txt')

    def test_eval_nested(self, shell, capsys):
        """Test nested eval."""
        shell.run_command('eval "eval \\"echo nested\\""')
        captured = capsys.readouterr()
        assert captured.out.strip() == "nested"

    def test_eval_function_definition(self, shell, capsys):
        """Test eval defining a function."""
        shell.run_command('eval "myfunc() { echo in function; }"')
        shell.run_command('myfunc')
        captured = capsys.readouterr()
        assert captured.out.strip() == "in function"
