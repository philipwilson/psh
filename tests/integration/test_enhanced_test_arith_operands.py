"""[[ ]] numeric operators arithmetic-evaluate their operands (bash).

Regression for reappraisal #15 H1: ``-eq/-ne/-lt/-le/-gt/-ge`` operands
went through a plain ``int()``, so ``[[ 1+1 -eq 2 ]]`` failed with
"integer expression expected" where bash runs FULL arithmetic (including
recursive name resolution, base literals, array elements, and assignment
side effects). Evaluation failures report an error and fail the statement
with status 1 (bash), not status 2. The ``test``/``[`` BUILTIN is
unchanged: bash does not arithmetic-evaluate there and neither does psh.
"""

import pytest


class TestArithmeticOperands:
    @pytest.mark.parametrize("cmd,expected_rc", [
        ('[[ 1+1 -eq 2 ]]', 0),
        ('[[ 1+1 -ne 3 ]]', 0),
        ('i=3; [[ i+1 -lt 5 ]]', 0),
        ('[[ 6/2 -le 3 ]]', 0),
        ('[[ 6%4 -gt 1 ]]', 0),
        ('[[ 2**3 -ge 8 ]]', 0),
        ('[[ 2 -eq 1+1 ]]', 0),           # RHS evaluated too
        ('x=3+4; [[ $x -eq 7 ]]', 0),     # expression from a variable value
        ('[[ "1+1" -eq 2 ]]', 0),         # quoting does not suppress arithmetic
        ('[[ 2#101 -eq 5 ]]', 0),         # base literal
        ('[[ 0x10 -eq 16 ]]', 0),         # hex literal
        ('a=(7); [[ a[0] -eq 7 ]]', 0),   # array element
        ('i=2; [[ i*3 -eq 6 ]]', 0),
        ('[[ "" -eq 0 ]]', 0),            # empty operand evaluates to 0
        ('unset zz; [[ zz -eq 0 ]]', 0),  # unset name evaluates to 0
        ('x=" 7 "; [[ $x -eq 7 ]]', 0),   # surrounding whitespace tolerated
        ('[[ -5 -lt -4 ]]', 0),
    ])
    def test_operand_evaluates(self, captured_shell, cmd, expected_rc):
        assert captured_shell.run_command(cmd) == expected_rc
        assert captured_shell.get_stderr() == ""

    def test_recursive_name_resolution(self, captured_shell):
        # x holds the NAME y; bash resolves the chain.
        assert captured_shell.run_command('y=5; x=y; [[ x -eq 5 ]]') == 0
        assert captured_shell.get_stderr() == ""

    def test_assignment_side_effect(self, captured_shell):
        captured_shell.run_command('x=0; [[ x+=1 -eq 1 ]]; echo "x=$x rc=$?"')
        assert captured_shell.get_stdout() == "x=1 rc=0\n"

    def test_works_in_function_and_eval(self, captured_shell):
        captured_shell.run_command(
            'f() { [[ $1 -eq 7 ]]; }; f 3+4; echo rc=$?')
        assert captured_shell.get_stdout() == "rc=0\n"
        assert captured_shell.run_command('eval "[[ 1+1 -eq 2 ]]"') == 0

    def test_works_in_command_substitution(self):
        # Command substitution forks (fd-level I/O) — run in a subprocess.
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c',
             'echo $(x=2+2; [[ $x -eq 4 ]]; echo rc=$?)'],
            capture_output=True, text=True)
        assert result.stdout == "rc=0\n"
        assert result.stderr == ""


class TestArithmeticOperandErrors:
    """Evaluation failures: message on stderr, [[ status 1, shell continues."""

    @pytest.mark.parametrize("cmd", [
        '[[ 08 -eq 8 ]]',            # value too great for base
        'x=08; [[ $x -eq 8 ]]',
        '[[ @@ -eq 2 ]]',            # operand expected
        'x="1 2"; [[ $x -eq 2 ]]',   # trailing-token syntax error
        '[[ 1/0 -eq 0 ]]',           # division by zero
        "y=5; [[ '\\$y' -eq 5 ]]",   # literal $ never rescanned (bash)
    ])
    def test_error_is_status_1_and_continues(self, captured_shell, cmd):
        captured_shell.run_command(f'{cmd}; echo rc=$?')
        assert captured_shell.get_stdout() == "rc=1\n"
        assert captured_shell.get_stderr().startswith("psh: [[: ")

    def test_test_builtin_unchanged(self, captured_shell):
        # bash's test/[ does NOT arithmetic-evaluate: still a usage error.
        assert captured_shell.run_command('[ 1+1 -eq 2 ]') == 2
        assert "integer expression expected" in captured_shell.get_stderr()
        captured_shell.clear_output()
        assert captured_shell.run_command('test 1+1 -eq 2') == 2
        captured_shell.clear_output()
        assert captured_shell.run_command('[ 2 -eq 2 ]') == 0
