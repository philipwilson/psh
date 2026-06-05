"""Batch 2 arithmetic correctness fixes.

Covers: 64-bit power wrapping (no artificial exponent cap), double-quoted
operands inside $(( )), array subscripts (read + assignment), and the octal
error-token text.
"""

import pytest


class TestArithmeticPowerWrapping:
    def _eval(self, shell, capsys, cmd):
        assert shell.run_command(cmd) == 0
        return capsys.readouterr().out.strip()

    def test_two_pow_64_wraps_to_zero(self, shell, capsys):
        assert self._eval(shell, capsys, 'echo $((2 ** 64))') == "0"

    def test_two_pow_100_wraps_to_zero(self, shell, capsys):
        assert self._eval(shell, capsys, 'echo $((2 ** 100))') == "0"

    def test_small_power_unaffected(self, shell, capsys):
        assert self._eval(shell, capsys, 'echo $((2 ** 10))') == "1024"

    def test_negative_base_power(self, shell, capsys):
        assert self._eval(shell, capsys, 'echo $(((-2) ** 3))') == "-8"

    def test_negative_exponent_still_errors(self, shell, capsys):
        assert shell.run_command('echo $((2 ** -1))') != 0


class TestArithmeticQuotedOperand:
    def _eval(self, shell, capsys, cmd):
        assert shell.run_command(cmd) == 0
        return capsys.readouterr().out.strip()

    def test_quoted_number(self, shell, capsys):
        assert self._eval(shell, capsys, 'echo $(( "5" ))') == "5"

    def test_quoted_operands_in_expr(self, shell, capsys):
        assert self._eval(shell, capsys, 'echo $(( "2" + "3" ))') == "5"


class TestArithmeticArraySubscript:
    def _eval(self, shell, capsys, cmd):
        assert shell.run_command(cmd) == 0
        return capsys.readouterr().out.strip()

    def test_read_element(self, shell, capsys):
        assert self._eval(shell, capsys, 'a=(10 20 30); echo $(( a[1] ))') == "20"

    def test_scalar_index_zero(self, shell, capsys):
        assert self._eval(shell, capsys, 'a=5; echo $(( a[0] ))') == "5"

    def test_expression_index(self, shell, capsys):
        assert self._eval(shell, capsys, 'a=(10 20 30); i=2; echo $(( a[i] + a[0] ))') == "40"

    def test_compound_assignment(self, shell, capsys):
        assert self._eval(shell, capsys, 'a=(10 20 30); (( a[1] += 5 )); echo "${a[1]}"') == "25"

    def test_assign_creates_element(self, shell, capsys):
        assert self._eval(shell, capsys, 'declare -a a; (( a[3] = 7 )); echo "${a[3]}"') == "7"


class TestArithmeticOctalError:
    def test_octal_error_token_no_extra_zero(self, shell, capsys):
        # The error token should be "08", not "008".
        assert shell.run_command('echo $(( 08 ))') != 0
        err = capsys.readouterr().err
        assert 'error token is "08"' in err
        assert '"008"' not in err
