"""Integer division/modulo use pure integer math with C semantics (bash).

Regression for reappraisal #15 H3: ``/`` and ``%`` were computed via
``int(left/right)`` — float division silently loses precision for
|operands| >= 2**53 ($((9223372036854775807/3)) was off by 170). C
semantics, verified against bash 5.2: division truncates toward zero
(Python's ``//`` floors), and the remainder takes the dividend's sign.
"""


class TestIntegerDivisionPrecision:
    def test_int64_max_div_3(self, captured_shell):
        captured_shell.run_command('echo $((9223372036854775807 / 3))')
        assert captured_shell.get_stdout() == "3074457345618258602\n"

    def test_int64_max_mod_large_prime(self, captured_shell):
        captured_shell.run_command('echo $((9223372036854775807 % 1000000007))')
        assert captured_shell.get_stdout() == "291172003\n"

    def test_near_min_div_truncates_toward_zero(self, captured_shell):
        # Floor division would give ...904; C truncation gives ...903 (bash).
        captured_shell.run_command('echo $((-9223372036854775807 / 2))')
        assert captured_shell.get_stdout() == "-4611686018427387903\n"


class TestCSignSemantics:
    def test_division_truncates_toward_zero(self, captured_shell):
        captured_shell.run_command('echo $((-7/2)) $((7/-2)) $((-7/-2))')
        assert captured_shell.get_stdout() == "-3 -3 3\n"

    def test_remainder_takes_dividend_sign(self, captured_shell):
        captured_shell.run_command('echo $((-7%2)) $((7%-2)) $((-7%-2))')
        assert captured_shell.get_stdout() == "-1 1 -1\n"


class TestAllArithmeticEntryPoints:
    """The same engine backs $(( )), (( )), let, and declare -i."""

    def test_dparen_assignment(self, captured_shell):
        captured_shell.run_command(
            'x=9223372036854775807; ((y=x/3)); echo $y')
        assert captured_shell.get_stdout() == "3074457345618258602\n"

    def test_dparen_compound_divide(self, captured_shell):
        captured_shell.run_command(
            'x=9223372036854775807; ((x/=3)); echo $x')
        assert captured_shell.get_stdout() == "3074457345618258602\n"

    def test_let(self, captured_shell):
        captured_shell.run_command('let "z=9223372036854775807/3"; echo $z')
        assert captured_shell.get_stdout() == "3074457345618258602\n"

    def test_declare_i(self, captured_shell):
        captured_shell.run_command(
            'declare -i w=9223372036854775807/3; echo $w')
        assert captured_shell.get_stdout() == "3074457345618258602\n"
