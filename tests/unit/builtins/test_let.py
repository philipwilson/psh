"""Tests for the let builtin (arithmetic evaluation)."""

import subprocess
import sys

import pytest


def _run(script):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', script],
                          capture_output=True, text=True)


class TestLetEvaluation:
    def test_assignment(self, captured_shell):
        rc = captured_shell.run_command('let x=5+3; echo $x')
        assert rc == 0
        assert captured_shell.get_stdout().strip() == "8"

    def test_multiple_expressions(self, captured_shell):
        captured_shell.run_command('let "a=2" "b=a+1"; echo "$a $b"')
        assert captured_shell.get_stdout().strip() == "2 3"

    def test_pre_increment_side_effect(self, captured_shell):
        captured_shell.run_command('x=5; let "++x"; echo $x')
        assert captured_shell.get_stdout().strip() == "6"

    def test_compound_assignment(self, captured_shell):
        captured_shell.run_command('x=10; let "x+=5"; echo $x')
        assert captured_shell.get_stdout().strip() == "15"

    def test_ternary(self, captured_shell):
        captured_shell.run_command('let "y = 1 ? 20 : 30"; echo $y')
        assert captured_shell.get_stdout().strip() == "20"

    def test_quoted_spaces(self, captured_shell):
        captured_shell.run_command('let "x = 5 + 3"; echo $x')
        assert captured_shell.get_stdout().strip() == "8"


class TestLetExitStatus:
    def test_nonzero_result_is_success(self, captured_shell):
        assert captured_shell.run_command('let x=5+3') == 0

    def test_zero_result_is_failure(self, captured_shell):
        assert captured_shell.run_command('let x=0') == 1

    def test_exit_status_follows_last_expression(self, captured_shell):
        assert captured_shell.run_command('let "x=5" "y=0"') == 1
        assert captured_shell.run_command('let "x=0" "y=5"') == 0

    def test_comparison_true(self, captured_shell):
        assert captured_shell.run_command('let "3 > 2"') == 0

    def test_comparison_false(self, captured_shell):
        assert captured_shell.run_command('let "2 > 3"') == 1


class TestLetErrors:
    def test_no_args(self, captured_shell):
        rc = captured_shell.run_command('let')
        assert rc == 1
        assert "expression expected" in captured_shell.get_stderr()

    def test_syntax_error(self, captured_shell):
        rc = captured_shell.run_command('let "1 +"')
        assert rc == 1

    def test_division_by_zero(self, captured_shell):
        rc = captured_shell.run_command('let "x = 1 / 0"')
        assert rc == 1

    def test_is_a_builtin(self, captured_shell):
        captured_shell.run_command('type let')
        assert "let is a shell builtin" in captured_shell.get_stdout()


class TestLetBashParity:
    @pytest.mark.parametrize("script", [
        'let x=5+3; echo "$x $?"',
        'let x=0; echo "$?"',
        'let "a=2" "b=a+1"; echo "$b $?"',
        'let "x=5" "y=0"; echo "$?"',
        'x=10; let "x*=3"; echo "$x"',
        'let "v = (2 + 3) * 4"; echo "$v"',
        'let "3 <= 3"; echo "rc=$?"',
    ])
    def test_matches_bash(self, script):
        psh = _run(script)
        bash = subprocess.run(['bash', '-c', script], capture_output=True, text=True)
        assert psh.stdout == bash.stdout
        assert psh.returncode == bash.returncode
