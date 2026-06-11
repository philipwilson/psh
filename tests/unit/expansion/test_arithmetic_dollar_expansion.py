"""Bash-pinned tests for $-construct expansion inside $((...)).

$-constructs in arithmetic are expanded exactly ONCE, by
evaluate_arithmetic() via expand_string_variables() → the shared
_expand_one_dollar scanner. There is no separate pre-expansion pass in
ExpansionManager any more (the old _expand_vars_in_arithmetic /
_expand_command_subs_in_arithmetic scanners produced a double expansion
that rescanned substituted values, which bash does not do, and padded
empty values with '0', which bash also does not do).

Every expectation here was probe-verified against bash 5.2.
"""

import subprocess
import sys


def run(shell, cmd):
    shell.run_command(cmd)
    return shell.get_stdout()


def run_script(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


class TestArithmeticDollarConstructs:
    def test_command_sub(self, captured_shell):
        assert run(captured_shell, 'echo $(($(echo 2)+1))') == "3\n"

    def test_param_expansion_default(self, captured_shell):
        assert run(captured_shell, 'x=; echo $((${x:-3}+1))') == "4\n"

    def test_dollar_and_braced_vars(self, captured_shell):
        assert run(captured_shell,
                   'x=2; y=3; echo $(( $x + ${y} ))') == "5\n"

    def test_nested_arithmetic(self, captured_shell):
        assert run(captured_shell, 'echo $(( $((1+1)) ))') == "2\n"

    def test_bare_name(self, captured_shell):
        assert run(captured_shell, 'x=4; echo $((x+1))') == "5\n"

    def test_command_sub_containing_arithmetic(self, captured_shell):
        assert run(captured_shell, 'echo $(( $(echo $((1+1))) ))') == "2\n"

    def test_special_variable(self, captured_shell):
        assert run(captured_shell, 'false; echo $(( $? + 1 ))') == "2\n"

    def test_backticks(self, captured_shell):
        assert run(captured_shell, 'echo $(( `echo 2` + 1 ))') == "3\n"

    def test_adjacent_braced_vars(self, captured_shell):
        assert run(captured_shell, 'x=3; echo $(( ${x}${x} ))') == "33\n"

    def test_value_substituted_as_expression_text(self, captured_shell):
        # bash substitutes the value text and parses the RESULT:
        # precedence applies to the substituted sub-expression.
        assert run(captured_shell, 'x="1 + 1"; echo $(( $x * 2 ))') == "3\n"

    def test_bare_name_resolves_recursively(self, captured_shell):
        assert run(captured_shell, 'x=y; y=7; echo $(( $x + 1 ))') == "8\n"


class TestArithmeticPositionals:
    def test_positional(self, captured_shell):
        assert run(captured_shell, 'set -- 9 8; echo $(( $1 + 1 ))') == "10\n"

    def test_dollar_digit_takes_one_digit(self, captured_shell):
        # $12 means ${1}2 inside $(( )), as in double quotes — not ${12}
        assert run(captured_shell,
                   'set -- 9 8 7 6 5 4 3 2 1 0 11 12; echo $(( $12 ))') == "92\n"

    def test_adjacent_positionals(self, captured_shell):
        assert run(captured_shell, 'set -- 9; echo $(( $1$1 ))') == "99\n"


class TestArithmeticEmptyValues:
    """bash substitutes empty values verbatim — no '0' padding."""

    def test_empty_var_alone_is_zero(self, captured_shell):
        assert run(captured_shell, 'x=""; echo $(( $x ))') == "0\n"

    def test_empty_var_after_number_vanishes(self, captured_shell):
        assert run(captured_shell, 'x=""; echo $(( 5 $x ))') == "5\n"

    def test_blank_var_after_number_vanishes(self, captured_shell):
        assert run(captured_shell, 'x=" "; echo $(( 5 $x ))') == "5\n"

    def test_empty_command_sub_is_zero(self, captured_shell):
        assert run(captured_shell, 'echo $(( $(true) ))') == "0\n"

    def test_unset_dollar_var_in_sum(self, captured_shell):
        assert run(captured_shell, 'unset z; echo $(( $z + 1 ))') == "1\n"

    def test_unset_braced_var_in_sum(self, captured_shell):
        assert run(captured_shell, 'echo $(( ${unset_v9} + 2 ))') == "2\n"

    def test_command_sub_whitespace_preserved(self, captured_shell):
        assert run(captured_shell, 'echo $(( $(echo " 2 ") + 1 ))') == "3\n"

    def test_empty_var_between_operators_is_error(self):
        # "$x + $x" with x='' leaves "+" dangling: bash errors (exit 1)
        r = run_script('x=""; echo $(( $x + $x ))')
        assert r.returncode == 1
        assert r.stdout == ""


class TestArithmeticNoRescan:
    """Substituted values are NOT rescanned for $-constructs (bash)."""

    def test_value_with_command_sub_text_is_error(self):
        r = run_script('x=$(printf "%s" "\\$(echo 3)"); echo $(( $x + 1 ))')
        assert r.returncode == 1
        assert r.stdout == ""

    def test_value_with_dollar_var_text_is_error(self):
        r = run_script('y=5; x="\\$y"; echo $(( $x + 1 ))')
        assert r.returncode == 1
        assert r.stdout == ""
