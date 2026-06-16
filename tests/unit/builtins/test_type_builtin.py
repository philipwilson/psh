"""Tests for the type builtin command."""

import os


class TestTypeBuiltin:
    """Test the type builtin functionality."""

    def test_type_builtin(self, captured_shell):
        """Test type recognizes builtins."""
        result = captured_shell.run_command('type echo')
        assert result == 0
        assert 'echo is a shell builtin' in captured_shell.get_stdout()

    def test_type_external_command(self, captured_shell):
        """Test type finds external commands."""
        result = captured_shell.run_command('type ls')
        assert result == 0
        output = captured_shell.get_stdout()
        assert 'ls is /' in output
        assert '/ls' in output

    def test_type_alias(self, captured_shell):
        """Test type recognizes aliases."""
        captured_shell.run_command('alias ll="ls -l"')
        captured_shell.clear_output()

        result = captured_shell.run_command('type ll')
        assert result == 0
        assert "ll is aliased to `ls -l'" in captured_shell.get_stdout()

    def test_type_function(self, captured_shell):
        """Test type recognizes functions."""
        captured_shell.run_command('greet() { echo "Hello $1"; }')
        captured_shell.clear_output()

        result = captured_shell.run_command('type greet')
        assert result == 0
        assert 'greet is a function' in captured_shell.get_stdout()

    def test_type_not_found(self, captured_shell):
        """Test type with non-existent command."""
        result = captured_shell.run_command('type nonexistent_command_xyz')
        assert result == 1
        assert 'nonexistent_command_xyz: not found' in captured_shell.get_stderr()

    def test_type_multiple_names(self, captured_shell):
        """Test type with multiple command names."""
        result = captured_shell.run_command('type echo ls')
        assert result == 0
        output = captured_shell.get_stdout()
        assert 'echo is a shell builtin' in output
        assert 'ls is /' in output

    def test_type_t_option(self, captured_shell):
        """Test type -t option for type only output."""
        # Test builtin
        result = captured_shell.run_command('type -t echo')
        assert result == 0
        assert captured_shell.get_stdout().strip() == 'builtin'

        captured_shell.clear_output()

        # Test file
        result = captured_shell.run_command('type -t ls')
        assert result == 0
        assert captured_shell.get_stdout().strip() == 'file'

        captured_shell.clear_output()

        # Test alias
        captured_shell.run_command('alias myalias="echo test"')
        captured_shell.clear_output()
        result = captured_shell.run_command('type -t myalias')
        assert result == 0
        assert captured_shell.get_stdout().strip() == 'alias'

        captured_shell.clear_output()

        # Test function
        captured_shell.run_command('myfunc() { echo test; }')
        captured_shell.clear_output()
        result = captured_shell.run_command('type -t myfunc')
        assert result == 0
        assert captured_shell.get_stdout().strip() == 'function'

    def test_type_a_option(self, captured_shell):
        """Test type -a option to show all locations."""
        # Create an alias that shadows a command
        captured_shell.run_command('alias test="echo aliased test"')
        captured_shell.clear_output()

        result = captured_shell.run_command('type -a test')
        assert result == 0
        output = captured_shell.get_stdout()
        lines = output.strip().split('\n')
        # Should show alias first, then builtin
        assert "test is aliased to `echo aliased test'" in lines[0]
        assert 'test is a shell builtin' in lines[1]

    def test_type_p_option(self, captured_shell):
        """Test type -p option for path only."""
        # -p should not show builtins or aliases
        result = captured_shell.run_command('type -p echo')
        assert result == 0
        # Should have no output for builtin
        assert captured_shell.get_stdout().strip() == ''

        captured_shell.clear_output()

        # But should show path for external command — R14.A: the BARE path,
        # with no "ls is " banner (the old format wrongly printed "ls is /…").
        result = captured_shell.run_command('type -p ls')
        assert result == 0
        out = captured_shell.get_stdout().strip()
        assert out.endswith('/ls')
        assert ' is ' not in out and out.startswith('/')

    def test_type_P_option(self, captured_shell):
        """Test type -P option to force PATH search."""
        # Even for builtins, -P forces PATH search, printing the BARE path.
        result = captured_shell.run_command('type -P echo')
        assert result == 0
        out = captured_shell.get_stdout().strip()
        assert out.endswith('/echo')
        assert ' is ' not in out and out.startswith('/')

    def test_type_f_option(self, captured_shell):
        """Test type -f option to suppress function lookup."""
        # Create a function
        captured_shell.run_command('ls() { echo "function ls"; }')
        captured_shell.clear_output()

        # Without -f, should find function
        result = captured_shell.run_command('type ls')
        assert result == 0
        assert 'ls is a function' in captured_shell.get_stdout()

        captured_shell.clear_output()

        # With -f, should skip function and find external command
        result = captured_shell.run_command('type -f ls')
        assert result == 0
        output = captured_shell.get_stdout()
        assert 'function' not in output
        assert 'ls is /' in output

    def test_type_alias_precedence(self, captured_shell):
        """Test that aliases take precedence over functions and builtins."""
        # Create function and alias with same name
        captured_shell.run_command('echo() { echo "function echo"; }')
        captured_shell.run_command('alias echo="echo aliased"')
        captured_shell.clear_output()

        # Type should show alias first
        result = captured_shell.run_command('type echo')
        assert result == 0
        assert 'echo is aliased to `echo aliased\'' in captured_shell.get_stdout()

    def test_type_with_slash(self, captured_shell, temp_dir):
        """Test type with path containing slash."""
        # Create an executable script
        script_path = os.path.join(temp_dir, 'myscript.sh')
        with open(script_path, 'w') as f:
            f.write('#!/bin/sh\necho test\n')
        os.chmod(script_path, 0o755)

        result = captured_shell.run_command(f'type {script_path}')
        assert result == 0
        assert f'{script_path} is {script_path}' in captured_shell.get_stdout()

    def test_type_empty_path(self, captured_shell):
        """Test type behavior with empty PATH."""
        # Save original PATH
        captured_shell.run_command('OLD_PATH=$PATH')
        captured_shell.run_command('PATH=""')
        captured_shell.clear_output()

        # Should still find builtins
        result = captured_shell.run_command('type echo')
        assert result == 0
        assert 'echo is a shell builtin' in captured_shell.get_stdout()

        # Restore PATH
        captured_shell.run_command('PATH=$OLD_PATH')
