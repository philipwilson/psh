"""Conformance tests for ``declare`` attribute combinations (reappraisal #6).

Pins four bash-divergence fixes in the declare/typeset attribute area:

* M1 — ``declare -i`` combined with ``-l``/``-u``: the integer attribute
  arithmetic-evaluates the value FIRST, then the case attribute folds the
  resulting string (``declare -il v=5+3`` -> ``v="8"``). psh used to treat
  the attributes as mutually exclusive and skipped the integer eval.
* M2 — ``declare -p`` attribute-letter ORDER. bash prints flags in the order
  ``a A i n r t x l u`` (the case-fold flags l/u sort last). psh used a
  different order (e.g. printed ``-xi`` for ``declare -ix``).
* M3 — ``-a``/``-A`` combined with ``-i``/``-l``/``-u``: the array is really
  created (even for a scalar value, stored at index 0), and the
  integer/case attrs apply to the ELEMENTS.
* L5 — ``declare -F NAME`` prints just the bare function name (not the full
  ``declare -f NAME`` form); an undefined name is silent with exit 1.

All output verified identical to bash 5.2.
"""

import sys

from conformance_framework import ConformanceTest
from shell_oracle import resolve_bash

BASH = resolve_bash().path


class TestDeclareIntegerCaseCombo(ConformanceTest):
    """M1: -i evaluates arithmetic, then -l/-u case-folds the result."""

    def test_integer_then_lowercase(self):
        self.assert_identical_behavior('declare -il v=5+3; declare -p v')

    def test_integer_then_uppercase_nonnumeric_is_zero(self):
        self.assert_identical_behavior('declare -iu v=ab+cd; declare -p v')

    def test_integer_lowercase_value_is_evaluated(self):
        self.assert_identical_behavior('declare -il v=2+3; echo "$v"')

    def test_integer_uppercase_hex(self):
        self.assert_identical_behavior('declare -iu v=0xff; declare -p v')

    def test_integer_alone_still_works(self):
        self.assert_identical_behavior('declare -i v=5+3; declare -p v')

    def test_lowercase_alone_still_works(self):
        self.assert_identical_behavior('declare -l v=ABC; declare -p v')

    def test_reassign_to_integer_var_evaluates(self):
        self.assert_identical_behavior('declare -i x; x=3+4; echo "$x"')


class TestDeclareAttributeOrder(ConformanceTest):
    """M2: declare -p prints flags in bash order `a A i n r t x l u`."""

    def test_integer_export(self):
        self.assert_identical_behavior('declare -ix v=1; declare -p v')

    def test_integer_readonly(self):
        self.assert_identical_behavior('declare -ir v=1; declare -p v')

    def test_integer_readonly_export(self):
        self.assert_identical_behavior('declare -irx v=1; declare -p v')

    def test_lowercase_integer_order(self):
        self.assert_identical_behavior('declare -li v=5; declare -p v')

    def test_readonly_lowercase_order(self):
        self.assert_identical_behavior('declare -lr v=X; declare -p v')

    def test_export_lowercase_order(self):
        self.assert_identical_behavior('declare -lx v=X; declare -p v')

    def test_export_uppercase_order(self):
        self.assert_identical_behavior('declare -ux v=x; declare -p v')

    def test_indexed_array_integer_order(self):
        self.assert_identical_behavior('declare -ai v=(1 2); declare -p v')


class TestDeclareArrayWithAttributes(ConformanceTest):
    """M3: -a/-A really creates an array; -i/-l/-u apply to the elements."""

    def test_indexed_integer_scalar_value(self):
        self.assert_identical_behavior('declare -ia v=1; declare -p v')

    def test_indexed_integer_array_elements_evaluated(self):
        self.assert_identical_behavior(
            'declare -ia v=(1+1 2+2); echo "${v[0]} ${v[1]}"')

    def test_assoc_integer_element_evaluated(self):
        self.assert_identical_behavior(
            'declare -Ai m=([k]=2+3); echo "${m[k]}"')

    def test_indexed_lowercase_elements(self):
        self.assert_identical_behavior(
            'declare -al v=(ABC DEF); echo "${v[0]} ${v[1]}"')

    def test_indexed_uppercase_elements(self):
        self.assert_identical_behavior(
            'declare -au v=(abc def); echo "${v[0]} ${v[1]}"')

    def test_plain_array_scalar_value_makes_array(self):
        self.assert_identical_behavior('declare -a v=5; declare -p v')


class TestDeclareFunctionNames(ConformanceTest):
    """L5: declare -F NAME prints the bare name; missing name is silent."""

    def test_declare_F_with_name_prints_bare_name(self):
        self.assert_identical_behavior('f() { :; }; declare -F f')

    def test_declare_F_missing_name_silent_exit_1(self):
        self.assert_identical_behavior(
            'f() { :; }; declare -F nonexist; echo "exit=$?"')

    def test_declare_f_missing_name_silent_exit_1(self):
        self.assert_identical_behavior(
            'f() { :; }; declare -f nonexist; echo "exit=$?"')


class TestDeclareCaseFlagMutualExclusion(ConformanceTest):
    """R13.A: -u and -l are mutually exclusive.

    Both in ONE declaration cancel (apply neither, and clear any case
    attribute the name already carried); across SEPARATE declarations the
    last one wins. Previously psh kept both flags and folded by flag order.
    """

    def test_both_flags_one_declaration_cancel(self):
        self.assert_identical_behavior('declare -ul y; y=HeLLo; echo $y')

    def test_both_flags_reversed_order_cancel(self):
        self.assert_identical_behavior('declare -lu y; y=HeLLo; echo $y')

    def test_upper_then_lower_last_wins(self):
        self.assert_identical_behavior(
            'declare -u y; declare -l y; y=HeLLo; echo $y')

    def test_lower_then_upper_last_wins(self):
        self.assert_identical_behavior(
            'declare -l y; declare -u y; y=HeLLo; echo $y')

    def test_both_flags_clear_preexisting_case(self):
        self.assert_identical_behavior(
            'declare -u y=X; declare -ul y; y=HeLLo; echo $y')

    def test_both_flags_clear_preexisting_on_unset(self):
        self.assert_identical_behavior(
            'declare -u y; declare -ul y; y=HeLLo; echo $y')

    def test_plus_flag_removes_case_on_unset(self):
        self.assert_identical_behavior(
            'declare -u y; declare +u y; y=HeLLo; echo $y')


class TestIntegerAttributeArithmeticErrors(ConformanceTest):
    """R14.B: an -i assignment with a malformed RHS / division by zero fails
    (status 1 + message) instead of silently storing 0; an undefined variable
    still resolves to 0 (not an error). Driven via script files (bash's `-c
    'a;b'` form abandons the rest of the line on the error — a separate quirk —
    so the standalone exit code is compared here)."""

    def _assert_arith_error(self, cmd):
        # exit 1 + something on stderr in both; the message WORDING differs
        # (bash "division by 0" vs psh "Division by zero"), so not compared.
        import subprocess
        psh = subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                             capture_output=True, text=True)
        bash = subprocess.run([BASH, '-c', cmd], capture_output=True, text=True)
        assert psh.returncode == bash.returncode == 1
        assert psh.stderr and bash.stderr

    def test_division_by_zero_fails(self):
        self._assert_arith_error('declare -i n; n=1/0')

    def test_syntax_error_fails(self):
        self._assert_arith_error('declare -i n; n=2+')

    def test_undefined_variable_is_zero_not_error(self):
        self.assert_identical_behavior('declare -i n; n=abc; echo "n=$n"')

    def test_valid_arithmetic_still_works(self):
        self.assert_identical_behavior('declare -i n; n=3+4*2; echo "n=$n"')


class TestDeclarePAssocReparseable(ConformanceTest):
    """R14.B: `declare -p` of an associative array quotes keys that need it
    and adds bash's trailing space, so the output is re-parseable. Single-key
    cases are byte-comparable to bash (multi-key order is bash hash order vs
    psh sorted — an accepted divergence, so those are tested for round-trip)."""

    def test_space_key_is_quoted(self):
        self.assert_identical_behavior('declare -A h=(["a b"]=v); declare -p h')

    def test_simple_key_stays_bare(self):
        self.assert_identical_behavior('declare -A h=([x]=1); declare -p h')

    def test_dotted_key_stays_bare(self):
        self.assert_identical_behavior('declare -A h=([a.b]=1); declare -p h')

    def test_roundtrip_reparseable(self):
        # psh-only: declare -p output evals back to the same array.
        self.assert_identical_behavior(
            'declare -A h=(["a b"]="v1" [k]="v2"); eval "$(declare -p h)"; '
            'echo "${h[a b]}|${h[k]}"')
