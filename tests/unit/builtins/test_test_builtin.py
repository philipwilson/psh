"""
Unit tests for test builtin and [ command.

Tests cover:
- File tests (-f, -d, -e, -r, -w, -x, etc.)
- String tests (-z, -n, =, !=)
- Numeric tests (-eq, -ne, -lt, -gt, -le, -ge)
- Logical operators (-a, -o, !)
- Both 'test' and '[' syntax
"""

import os

import pytest


class TestFileTests:
    """Test file-related test conditions."""

    @pytest.fixture(autouse=True)
    def _isolate_cwd(self, tmp_path, monkeypatch):
        """Give each file test its own working directory.

        These tests create fixed-name files/dirs (``testdir``, ``regular.txt``,
        …) and remove them with relative paths. Run in the shared cwd under
        pytest-xdist they collide across workers (a `testdir` created by one
        test is removed by another, raising FileNotFoundError). Per-test temp
        cwd isolation removes the collision (CLAUDE.md parallel-safety rule 2).
        """
        monkeypatch.chdir(tmp_path)

    def test_file_exists(self, shell, capsys):
        """Test -e (file exists)."""
        # Create a test file
        shell.run_command('touch testfile')

        # Test with 'test'
        exit_code = shell.run_command('test -e testfile')
        assert exit_code == 0

        # Test with '['
        exit_code = shell.run_command('[ -e testfile ]')
        assert exit_code == 0

        # Non-existent file
        exit_code = shell.run_command('test -e nonexistent')
        assert exit_code != 0

        # Clean up
        os.remove('testfile')

    def test_regular_file(self, shell, capsys):
        """Test -f (regular file)."""
        # Create a regular file
        shell.run_command('touch regular.txt')

        exit_code = shell.run_command('[ -f regular.txt ]')
        assert exit_code == 0

        # Directory is not a regular file
        shell.run_command('mkdir testdir')
        exit_code = shell.run_command('[ -f testdir ]')
        assert exit_code != 0

        # Clean up
        os.remove('regular.txt')
        os.rmdir('testdir')

    def test_directory(self, shell, capsys):
        """Test -d (directory)."""
        # Create a directory
        shell.run_command('mkdir testdir')

        exit_code = shell.run_command('test -d testdir')
        assert exit_code == 0

        # File is not a directory
        shell.run_command('touch file.txt')
        exit_code = shell.run_command('test -d file.txt')
        assert exit_code != 0

        # Clean up
        os.rmdir('testdir')
        os.remove('file.txt')

    def test_readable_file(self, shell, capsys):
        """Test -r (readable)."""
        shell.run_command('touch readable.txt')
        shell.run_command('chmod 644 readable.txt')

        exit_code = shell.run_command('[ -r readable.txt ]')
        assert exit_code == 0

        # Clean up
        os.remove('readable.txt')

    def test_writable_file(self, shell, capsys):
        """Test -w (writable)."""
        shell.run_command('touch writable.txt')
        shell.run_command('chmod 644 writable.txt')

        exit_code = shell.run_command('test -w writable.txt')
        assert exit_code == 0

        # Clean up
        os.remove('writable.txt')

    def test_executable_file(self, shell, capsys):
        """Test -x (executable)."""
        shell.run_command('touch script.sh')
        shell.run_command('chmod 755 script.sh')

        exit_code = shell.run_command('[ -x script.sh ]')
        assert exit_code == 0

        # Non-executable
        shell.run_command('chmod 644 script.sh')
        exit_code = shell.run_command('[ -x script.sh ]')
        assert exit_code != 0

        # Clean up
        os.remove('script.sh')

    def test_file_size(self, shell, capsys):
        """Test -s (file has size > 0)."""
        # Empty file
        shell.run_command('touch empty.txt')
        exit_code = shell.run_command('test -s empty.txt')
        assert exit_code != 0

        # Non-empty file
        shell.run_command('echo "content" > nonempty.txt')
        exit_code = shell.run_command('test -s nonempty.txt')
        assert exit_code == 0

        # Clean up
        os.remove('empty.txt')
        os.remove('nonempty.txt')


class TestStringTests:
    """Test string-related test conditions."""

    def test_string_empty(self, shell, capsys):
        """Test -z (string is empty)."""
        # Empty string
        exit_code = shell.run_command('test -z ""')
        assert exit_code == 0

        exit_code = shell.run_command('[ -z "" ]')
        assert exit_code == 0

        # Non-empty string
        exit_code = shell.run_command('test -z "hello"')
        assert exit_code != 0

    def test_string_not_empty(self, shell, capsys):
        """Test -n (string is not empty)."""
        # Non-empty string
        exit_code = shell.run_command('test -n "hello"')
        assert exit_code == 0

        # Empty string
        exit_code = shell.run_command('[ -n "" ]')
        assert exit_code != 0

    def test_string_equality(self, shell, capsys):
        """Test string = string."""
        # Equal strings
        exit_code = shell.run_command('test "hello" = "hello"')
        assert exit_code == 0

        exit_code = shell.run_command('[ "abc" = "abc" ]')
        assert exit_code == 0

        # Different strings
        exit_code = shell.run_command('test "hello" = "world"')
        assert exit_code != 0

    def test_string_inequality(self, shell, capsys):
        """Test string != string."""
        # Different strings
        exit_code = shell.run_command('test "hello" != "world"')
        assert exit_code == 0

        # Equal strings
        exit_code = shell.run_command('[ "same" != "same" ]')
        assert exit_code != 0

    def test_string_with_variables(self, shell, capsys):
        """Test strings with variable expansion."""
        shell.run_command('VAR="test"')

        exit_code = shell.run_command('[ "$VAR" = "test" ]')
        assert exit_code == 0

        exit_code = shell.run_command('test -z "$UNSET_VAR"')
        assert exit_code == 0


class TestNumericTests:
    """Test numeric comparison conditions."""

    def test_numeric_equal(self, shell, capsys):
        """Test -eq (equal)."""
        exit_code = shell.run_command('test 5 -eq 5')
        assert exit_code == 0

        exit_code = shell.run_command('[ 10 -eq 20 ]')
        assert exit_code != 0

    def test_numeric_not_equal(self, shell, capsys):
        """Test -ne (not equal)."""
        exit_code = shell.run_command('test 5 -ne 10')
        assert exit_code == 0

        exit_code = shell.run_command('[ 7 -ne 7 ]')
        assert exit_code != 0

    def test_numeric_less_than(self, shell, capsys):
        """Test -lt (less than)."""
        exit_code = shell.run_command('test 5 -lt 10')
        assert exit_code == 0

        exit_code = shell.run_command('[ 10 -lt 5 ]')
        assert exit_code != 0

    def test_numeric_greater_than(self, shell, capsys):
        """Test -gt (greater than)."""
        exit_code = shell.run_command('test 10 -gt 5')
        assert exit_code == 0

        exit_code = shell.run_command('[ 5 -gt 10 ]')
        assert exit_code != 0

    def test_numeric_less_equal(self, shell, capsys):
        """Test -le (less than or equal)."""
        exit_code = shell.run_command('test 5 -le 10')
        assert exit_code == 0

        exit_code = shell.run_command('test 5 -le 5')
        assert exit_code == 0

        exit_code = shell.run_command('[ 10 -le 5 ]')
        assert exit_code != 0

    def test_numeric_greater_equal(self, shell, capsys):
        """Test -ge (greater than or equal)."""
        exit_code = shell.run_command('test 10 -ge 5')
        assert exit_code == 0

        exit_code = shell.run_command('test 5 -ge 5')
        assert exit_code == 0

        exit_code = shell.run_command('[ 5 -ge 10 ]')
        assert exit_code != 0


class TestLogicalOperators:
    """Test logical operators in test expressions."""

    def test_logical_and(self, shell, capsys):
        """Test -a (logical AND)."""
        # Both true
        exit_code = shell.run_command('test -n "hello" -a -n "world"')
        assert exit_code == 0

        # One false
        exit_code = shell.run_command('[ -n "hello" -a -z "hello" ]')
        assert exit_code != 0

    def test_logical_or(self, shell, capsys):
        """Test -o (logical OR)."""
        # One true
        exit_code = shell.run_command('test -n "hello" -o -z "hello"')
        assert exit_code == 0

        # Both false
        exit_code = shell.run_command('[ -z "hello" -o -z "world" ]')
        assert exit_code != 0

    def test_negation(self, shell, capsys):
        """Test ! (negation)."""
        # Negate true
        exit_code = shell.run_command('test ! -n "hello"')
        assert exit_code != 0

        # Negate false
        exit_code = shell.run_command('[ ! -z "hello" ]')
        assert exit_code == 0

    def test_parentheses(self, shell, capsys):
        """Test parentheses for grouping."""
        # Complex expression with grouping
        exit_code = shell.run_command('test \\( -n "a" -a -n "b" \\) -o -z "c"')
        assert exit_code == 0


class TestSpecialCases:
    """Test special cases and error conditions."""

    def test_empty_test(self, shell, capsys):
        """Test with no arguments."""
        exit_code = shell.run_command('test')
        assert exit_code != 0

        exit_code = shell.run_command('[  ]')
        assert exit_code != 0

    def test_single_argument(self, shell, capsys):
        """Test with single argument (tests if non-empty)."""
        exit_code = shell.run_command('test "hello"')
        assert exit_code == 0

        exit_code = shell.run_command('test ""')
        assert exit_code != 0

        exit_code = shell.run_command('[ "x" ]')
        assert exit_code == 0

    def test_lone_bang_is_nonempty_string(self, shell, capsys):
        """R13.A: a lone `!` is the one-argument non-empty-string test (exit 0),
        not negation-of-empty (bash/POSIX)."""
        assert shell.run_command('test !') == 0
        assert shell.run_command('[ ! ]') == 0
        # `!` still negates a following operand
        assert shell.run_command('test ! -e /nonexistent_xyz_psh') == 0
        assert shell.run_command("test ! ''") == 0

    def test_v_variable_is_set(self, shell, capsys):
        """R13.A: `test -v VAR` / `[ -v VAR ]` reports whether a variable is set
        (previously always returned the sentinel exit 2)."""
        shell.run_command('vv=5')
        assert shell.run_command('test -v vv') == 0
        assert shell.run_command('[ -v vv ]') == 0
        shell.run_command('unset nope_xyz')
        assert shell.run_command('test -v nope_xyz') == 1

    def test_v_array_element(self, shell, capsys):
        """`test -v arr[i]` checks element existence."""
        shell.run_command('arr=(a b c)')
        assert shell.run_command('test -v "arr[1]"') == 0
        assert shell.run_command('test -v "arr[9]"') == 1

    def test_bracket_spacing(self, shell, capsys):
        """Test [ requires spaces."""
        # Correct spacing
        exit_code = shell.run_command('[ -n "test" ]')
        assert exit_code == 0

        # Missing closing bracket should fail
        exit_code = shell.run_command('[ -n "test"')
        assert exit_code != 0

    def test_invalid_operator(self, shell, capsys):
        """Test invalid operators."""
        exit_code = shell.run_command('test 5 -foo 10')
        assert exit_code != 0
        captured = capsys.readouterr()
        # Now checks for the actual error message
        assert 'binary operator expected' in captured.err

    def test_file_comparison(self, shell, capsys):
        """Test file comparison operators."""
        try:
            # Create test files
            shell.run_command('touch file1')
            shell.run_command('sleep 0.1')  # Ensure different timestamps
            shell.run_command('touch file2')

            # file2 should be newer
            exit_code = shell.run_command('[ file2 -nt file1 ]')
            assert exit_code == 0

            # file1 should be older
            exit_code = shell.run_command('test file1 -ot file2')
            assert exit_code == 0
        finally:
            # Clean up
            if os.path.exists('file1'):
                os.remove('file1')
            if os.path.exists('file2'):
                os.remove('file2')


class TestErrorPrefix:
    """Error messages carry the invocation name, matching bash (R9.D).

    bash reports `[: 1: unary operator expected` when invoked as `[` and
    `test: 1: unary operator expected` when invoked as `test`.
    """

    def test_bracket_errors_use_bracket_prefix(self, captured_shell):
        captured_shell.run_command('[ 1 -eq ]')
        assert captured_shell.get_stderr().startswith('[: ')

    def test_test_errors_use_test_prefix(self, captured_shell):
        captured_shell.run_command('test 1 -eq')
        assert captured_shell.get_stderr().startswith('test: ')
