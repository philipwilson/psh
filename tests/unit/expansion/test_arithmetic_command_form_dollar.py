"""Bash-pinned tests for $-constructs in the arithmetic COMMAND/loop forms.

Unlike ``$((...))`` (a single ARITH_EXPANSION token, covered by
``test_arithmetic_dollar_expansion.py``), the ``(( ))`` command form, the
C-style ``for ((;;))`` loop, and ``while (( ))`` reconstruct their expression
text token-by-token via ``TokenStream.collect_arithmetic_expression``. That
reconstruction must re-add the ``$`` the lexer strips from VARIABLE tokens —
otherwise ``$1`` collapses to the literal ``1`` and ``${#a[@]}`` fails to parse.

Regression for the v0.515 fix (ground-up appraisal 2026-06-21, finding H2).
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


class TestArithmeticCommandFormDollar:
    def test_positional_in_command_form(self, captured_shell):
        assert run(captured_shell,
                   'set -- 5; (( $1 == 5 )) && echo Y || echo N') == "Y\n"

    def test_arg_count_in_command_form(self, captured_shell):
        assert run(captured_shell,
                   'f(){ (( $# == 2 )) && echo Y || echo N; }; f a b') == "Y\n"

    def test_array_length_in_command_form(self, captured_shell):
        assert run(captured_shell,
                   'arr=(a b c); (( ${#arr[@]} > 0 )) && echo y || echo n') == "y\n"

    def test_string_length_in_command_form(self, captured_shell):
        assert run(captured_shell,
                   's=hello; (( ${#s} == 5 )) && echo five') == "five\n"

    def test_special_var_status_in_command_form(self, captured_shell):
        assert run(captured_shell,
                   'true; (( $? == 0 )) && echo zero') == "zero\n"

    def test_plain_dollar_var_in_command_form(self, captured_shell):
        assert run(captured_shell, 'x=4; (( $x * 2 == 8 )) && echo ok') == "ok\n"


class TestArithmeticCStyleForDollar:
    def test_array_length_bound(self, captured_shell):
        assert run(captured_shell,
                   'arr=(x y z); for ((i=0;i<${#arr[@]};i++)); do '
                   'printf "%s " "${arr[i]}"; done; echo') == "x y z \n"

    def test_positional_bound(self, captured_shell):
        assert run(captured_shell,
                   'set -- 3; for ((i=0;i<$1;i++)); do '
                   'printf "%s " "$i"; done; echo') == "0 1 2 \n"


class TestArithmeticWhileDollar:
    def test_while_array_length_condition(self, captured_shell):
        assert run(captured_shell,
                   'arr=(x y z); i=0; while (( i < ${#arr[@]} )); do '
                   'printf "%s " "${arr[i]}"; i=$((i+1)); done; echo') == "x y z \n"


class TestArithmeticAssocSubscriptDollar:
    def test_assoc_key_increment(self):
        # ((c[$w]++)) must use the VALUE of $w as the key, not the name 'w'.
        r = run_script('declare -A c; w=foo; ((c[$w]++)); ((c[$w]++)); '
                       'echo "${!c[@]}=${c[foo]}"')
        assert r.returncode == 0
        assert r.stdout == "foo=2\n"

    def test_word_count_idiom(self):
        r = run_script('declare -A n; for w in a b a c a b; do ((n[$w]++)); done; '
                       'for k in a b c; do echo "$k=${n[$k]}"; done')
        assert r.returncode == 0
        assert r.stdout == "a=3\nb=2\nc=1\n"
