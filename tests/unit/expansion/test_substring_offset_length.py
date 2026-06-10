"""Batch 3 substring offset/length correctness fixes.

Covers arithmetic offsets/lengths (parens, expressions, variables), the
out-of-range negative offset returning empty, and the out-of-range negative
length raising an error with a non-zero exit status.
"""



class TestSubstringArithmeticOffsets:
    def _eval(self, shell, capsys, cmd):
        assert shell.run_command(cmd) == 0
        return capsys.readouterr().out.strip()

    def test_parenthesized_negative_offset(self, shell, capsys):
        assert self._eval(shell, capsys, 'x=0123456789; echo "${x:(-3):2}"') == "78"

    def test_arithmetic_offset(self, shell, capsys):
        assert self._eval(shell, capsys, 'x=0123456789; echo "${x:1+1:2}"') == "23"

    def test_parenthesized_offset(self, shell, capsys):
        assert self._eval(shell, capsys, 'x=0123456789; echo "${x:(3):2}"') == "34"

    def test_space_negative_offset(self, shell, capsys):
        assert self._eval(shell, capsys, 'x=0123456789; echo "${x: -3:2}"') == "78"

    def test_variable_offset(self, shell, capsys):
        assert self._eval(shell, capsys, 'x=0123456789; n=2; echo "${x:n:3}"') == "234"

    def test_arithmetic_length(self, shell, capsys):
        assert self._eval(shell, capsys, 'x=0123456789; echo "${x:0:2+1}"') == "012"


class TestSubstringBounds:
    def test_out_of_range_negative_offset_is_empty(self, shell, capsys):
        assert shell.run_command('x=abc; echo "[${x: -10}]"') == 0
        assert capsys.readouterr().out.strip() == "[]"

    def test_in_range_negative_length_trims(self, shell, capsys):
        assert shell.run_command('x=abc; echo "[${x:0:-1}]"') == 0
        assert capsys.readouterr().out.strip() == "[ab]"

    def test_out_of_range_negative_length_errors(self, shell, capsys):
        rc = shell.run_command('x=abc; echo "${x:0:-5}"')
        assert rc != 0
        assert "substring expression < 0" in capsys.readouterr().err


class TestSubstringRegression:
    def _eval(self, shell, capsys, cmd):
        assert shell.run_command(cmd) == 0
        return capsys.readouterr().out.strip()

    def test_basic(self, shell, capsys):
        assert self._eval(shell, capsys, 'x=hello; echo "${x:1:3}"') == "ell"

    def test_offset_only(self, shell, capsys):
        assert self._eval(shell, capsys, 'x=hello; echo "${x:2}"') == "llo"

    def test_empty_offset(self, shell, capsys):
        assert self._eval(shell, capsys, 'x=hello; echo "${x::2}"') == "he"
