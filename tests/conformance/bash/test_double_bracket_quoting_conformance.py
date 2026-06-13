"""Conformance tests: per-part quoting in ``[[ ]]`` test expressions.

In ``[[ ]]``, for ``==``/``!=``/``=~`` the RHS is a PATTERN when unquoted
and a LITERAL when quoted — and this is decided PER PART, not for the
operand as a whole. ``[[ abc == ab"?" ]]`` is false (the ``?`` is a quoted
literal) while ``[[ abc == ab? ]]`` is true (unquoted ``?`` is a glob).
A single quote-type sentinel could not express this; the operands are
multi-part Words carrying per-part quote context and the evaluator reads it
directly (T3.1, 2026-06-14). These tests pin identical bash behavior.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from conformance_framework import ConformanceTest


class TestPerPartPatternQuoting(ConformanceTest):
    """== / != honor quoting per part of the RHS pattern."""

    def test_quoted_glob_metachar_is_literal(self):
        # The quoted '?' is a literal '?', the rest unquoted.
        self.assert_identical_behavior('[[ abc == ab"?" ]]; echo $?')
        self.assert_identical_behavior('[[ "ab?" == ab"?" ]]; echo $?')
        self.assert_identical_behavior('[[ abc == ab? ]]; echo $?')

    def test_mixed_part_pattern(self):
        # a (glob) + "b" (literal) + * (glob)
        self.assert_identical_behavior('[[ abc == a"b"* ]]; echo $?')
        self.assert_identical_behavior('[[ axc == a"b"* ]]; echo $?')
        self.assert_identical_behavior('[[ a*b == a"*"b ]]; echo $?')
        self.assert_identical_behavior('[[ "a*b" == a"*"b ]]; echo $?')

    def test_wholly_quoted_vs_unquoted(self):
        self.assert_identical_behavior('[[ ax == a* ]]; echo $?')
        self.assert_identical_behavior('[[ ax == "a*" ]]; echo $?')
        self.assert_identical_behavior("[[ ax == 'a*' ]]; echo $?")

    def test_negated_pattern(self):
        self.assert_identical_behavior('[[ abc != a* ]]; echo $?')
        self.assert_identical_behavior('[[ abc != "a*" ]]; echo $?')

    def test_variable_quoted_vs_unquoted(self):
        self.assert_identical_behavior("p='a*'; [[ aXX == $p ]]; echo $?")
        self.assert_identical_behavior('p=\'a*\'; [[ aXX == "$p" ]]; echo $?')


class TestPerPartRegexQuoting(ConformanceTest):
    """=~ matches quoted sub-parts literally, unquoted parts as live regex."""

    def test_quoted_regex_metachar_is_literal(self):
        self.assert_identical_behavior('[[ "a.c" =~ a"."c ]]; echo $?')
        self.assert_identical_behavior('[[ "axc" =~ a"."c ]]; echo $?')
        self.assert_identical_behavior('[[ "axc" =~ a.c ]]; echo $?')

    def test_wholly_quoted_regex_is_literal(self):
        self.assert_identical_behavior('[[ ab =~ a. ]]; echo $?')
        self.assert_identical_behavior('[[ ab =~ "a." ]]; echo $?')
        self.assert_identical_behavior('[[ "a." =~ "a." ]]; echo $?')

    def test_backslash_escape_in_regex(self):
        # \. is a literal dot in the regex; the LHS keeps its backslash.
        self.assert_identical_behavior(r'[[ "a.c" =~ a\.c ]]; echo $?')
        self.assert_identical_behavior(r'[[ "axc" =~ a\.c ]]; echo $?')
        self.assert_identical_behavior(r'[[ "a\.c" =~ a\.c ]]; echo $?')

    def test_variable_regex_quoted_vs_unquoted(self):
        self.assert_identical_behavior("p='a.'; [[ axc =~ $p ]]; echo $?")
        self.assert_identical_behavior('p=\'a.\'; [[ axc =~ "$p" ]]; echo $?')


class TestSubjectQuoteRemoval(ConformanceTest):
    """The LHS subject undergoes quote-aware quote removal (not blanket
    backslash stripping)."""

    def test_double_quoted_backslash_literal(self):
        self.assert_identical_behavior(r'[[ "a\.c" == "a\.c" ]]; echo $?')
        self.assert_identical_behavior(r'[[ "a\.c" == a\\.c ]]; echo $?')

    def test_unquoted_backslash_escape_removed(self):
        self.assert_identical_behavior(r'[[ ab\? == "ab?" ]]; echo $?')

    def test_escaped_dollar_in_double_quotes(self):
        self.assert_identical_behavior(r'x=foo; [[ "\$x" == "\$x" ]]; echo $?')
