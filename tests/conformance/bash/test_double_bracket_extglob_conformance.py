"""Conformance tests: extended-glob (extglob) patterns in ``[[ ]]``.

Inside a ``[[ ]]`` ``==``/``!=`` pattern operand bash interprets the
extended-glob operators ``?(...)`` ``*(...)`` ``+(...)`` ``@(...)``
``!(...)`` UNCONDITIONALLY — independent of the ``extglob`` shell option
(verified against bash with the option both on and off). None of the
commands below run ``shopt -s extglob``, so they also pin that the support
is unconditional in ``[[ ]]``.

Earlier psh raised a parse error here (the lexer only consumed an extglob
group when ``shopt -s extglob`` was set, so the ``(`` of the group became a
stray ``LPAREN``). The lexer now recognizes extglob groups whenever
``bracket_depth > 0`` (``recognizers/literal.extglob_active``) and the
``[[ ]]`` evaluator matches with extglob always on
(``enhanced_test_evaluator._pattern_match``). These tests pin identical
bash behavior.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from conformance_framework import ConformanceTest


class TestDoubleBracketExtglobOperators(ConformanceTest):
    """Each extglob operator works in a ``[[ ]]`` == operand (no shopt)."""

    def test_at_one_of(self):
        # @(...) — exactly one of the alternatives
        self.assert_identical_behavior('[[ abc == a@(b|x)c ]]; echo $?')
        self.assert_identical_behavior('[[ axc == a@(b|x)c ]]; echo $?')
        self.assert_identical_behavior('[[ ayc == a@(b|x)c ]]; echo $?')

    def test_question_zero_or_one(self):
        # ?(...) — zero or one occurrence
        self.assert_identical_behavior('[[ aXc == a?(X)c ]]; echo $?')
        self.assert_identical_behavior('[[ ac == a?(X)c ]]; echo $?')
        self.assert_identical_behavior('[[ aXXc == a?(X)c ]]; echo $?')

    def test_star_zero_or_more(self):
        # *(...) — zero or more occurrences
        self.assert_identical_behavior('[[ aXXc == a*(X)c ]]; echo $?')
        self.assert_identical_behavior('[[ ac == a*(X)c ]]; echo $?')

    def test_plus_one_or_more(self):
        # +(...) — one or more occurrences
        self.assert_identical_behavior('[[ aXc == a+(X)c ]]; echo $?')
        self.assert_identical_behavior('[[ aXXc == a+(X)c ]]; echo $?')
        self.assert_identical_behavior('[[ ac == a+(X)c ]]; echo $?')

    def test_bang_anything_except(self):
        # !(...) — anything except the alternatives
        self.assert_identical_behavior('[[ abc == a!(z)c ]]; echo $?')
        self.assert_identical_behavior('[[ azc == a!(z)c ]]; echo $?')
        self.assert_identical_behavior('[[ foo == !(bar) ]]; echo $?')
        self.assert_identical_behavior('[[ bar == !(bar) ]]; echo $?')


class TestDoubleBracketExtglobShapes(ConformanceTest):
    """Negation, combination, nesting, and leading/trailing groups."""

    def test_not_equal_operator(self):
        self.assert_identical_behavior('[[ abc != a@(b|x)c ]]; echo $?')
        self.assert_identical_behavior('[[ ayc != a@(b|x)c ]]; echo $?')

    def test_adjacent_groups(self):
        self.assert_identical_behavior('[[ abc == a@(b|x)@(c|d) ]]; echo $?')
        self.assert_identical_behavior('[[ axd == a@(b|x)@(c|d) ]]; echo $?')
        self.assert_identical_behavior('[[ aye == a@(b|x)@(c|d) ]]; echo $?')

    def test_group_with_trailing_glob(self):
        self.assert_identical_behavior('[[ foobar == @(foo|bar)* ]]; echo $?')
        self.assert_identical_behavior('[[ barbaz == @(foo|bar)* ]]; echo $?')
        self.assert_identical_behavior('[[ bazfoo == @(foo|bar)* ]]; echo $?')

    def test_nested_groups(self):
        self.assert_identical_behavior('[[ abcd == a@(b@(c)d) ]]; echo $?')
        self.assert_identical_behavior('[[ axyd == a@(b@(c)d|xyd) ]]; echo $?')

    def test_combined_operators(self):
        self.assert_identical_behavior('[[ aXbYc == a?(X)b*(Y)c ]]; echo $?')
        self.assert_identical_behavior('[[ abc == a?(X)b*(Y)c ]]; echo $?')


class TestDoubleBracketExtglobQuotingInteraction(ConformanceTest):
    """A quoted extglob group is a LITERAL; a variable's value is live."""

    def test_quoted_group_is_literal(self):
        self.assert_identical_behavior('[[ "a@(b)c" == "a@(b)c" ]]; echo $?')
        self.assert_identical_behavior('[[ abc == "a@(b|x)c" ]]; echo $?')
        self.assert_identical_behavior('[[ "a@(b|x)c" == a@(b|x)c ]]; echo $?')

    def test_variable_holding_group(self):
        # Unquoted $p is a live extglob pattern; "$p" is literal.
        self.assert_identical_behavior('p="a@(b|x)c"; [[ abc == $p ]]; echo $?')
        self.assert_identical_behavior('p="a@(b|x)c"; [[ abc == "$p" ]]; echo $?')
