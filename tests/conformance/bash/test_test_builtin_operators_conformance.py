"""Conformance tests for test/[ binary operators (R14.A).

Pins two common idioms that psh used to reject with "binary operator
expected" (exit 2), now matching bash:

  - ``==`` as a synonym for ``=`` in test/[ (literal string equality, NO
    globbing — unlike ``[[ ]]``).
  - the 3-argument XSI binary primaries ``-a``/``-o`` (`[ s1 -a s2 ]` is the
    AND of the two operands' string non-emptiness; ``-o`` the OR).

Exit code is surfaced via ``echo $?`` so assert_identical_behavior (which
compares stdout/stderr/exit) checks the boolean result, not just emptiness.
"""


from conformance_framework import ConformanceTest


class TestEqualsEqualsSynonym(ConformanceTest):
    """== behaves as = in test/[ (bash extension; no glob)."""

    def test_double_equals_match(self):
        self.assert_identical_behavior('[ foo == foo ]; echo $?')

    def test_double_equals_mismatch(self):
        self.assert_identical_behavior('[ foo == bar ]; echo $?')

    def test_double_equals_in_test_word(self):
        self.assert_identical_behavior('test foo == foo; echo $?')

    def test_double_equals_is_literal_not_glob(self):
        # In test/[ (unlike [[ ]]) the right side is a literal string.
        self.assert_identical_behavior('[ abc == "a*" ]; echo $?')

    def test_double_equals_in_logical_expression(self):
        self.assert_identical_behavior('[ a == b -o c == c ]; echo $?')


class TestThreeArgAndOr(ConformanceTest):
    """3-argument -a / -o are AND/OR of operand string non-emptiness."""

    def test_and_both_nonempty(self):
        self.assert_identical_behavior('[ a -a b ]; echo $?')

    def test_and_second_empty(self):
        self.assert_identical_behavior('[ a -a "" ]; echo $?')

    def test_and_first_empty(self):
        self.assert_identical_behavior('[ "" -a b ]; echo $?')

    def test_or_one_nonempty(self):
        self.assert_identical_behavior('[ a -o "" ]; echo $?')

    def test_or_both_empty(self):
        self.assert_identical_behavior('[ "" -o "" ]; echo $?')

    def test_multiarg_and_still_combines_expressions(self):
        # The >3-arg -a combines whole expressions (unary tests here), which
        # must keep working alongside the new 3-arg primary.
        self.assert_identical_behavior('[ -n x -a -n y ]; echo $?')
