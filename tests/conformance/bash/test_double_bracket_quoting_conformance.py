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


class TestDoubleQuoteLiteralSharedAcrossSites(ConformanceTest):
    """A double-quoted literal part is expanded by ONE shared recipe
    (``enhanced_test_evaluator._expand_dquote_literal``, R19 T7): its variables
    expand, then the double-quote escapes are stripped (a backslash before a
    non-special char stays literal). The subject (LHS), the ``==``/``!=``
    pattern (RHS) and the ``=~`` regex (RHS) all feed that one recipe, so a
    given double-quoted literal reads identically in every role — these pins
    lock the three sites together so the dedup cannot silently drift one."""

    def test_dquote_var_expands_then_literal_in_pattern(self):
        # The var expands INSIDE the double-quoted literal; the result is a
        # glob LITERAL (its `*` matches itself, not as a wildcard).
        self.assert_identical_behavior('p="a*"; [[ "a*" == "$p" ]]; echo $?')
        self.assert_identical_behavior('p="a*"; [[ ax == "$p" ]]; echo $?')

    def test_dquote_var_expands_then_literal_in_regex(self):
        # Same double-quoted literal as a =~ RHS: matched literally (the `.`
        # is not a regex wildcard).
        self.assert_identical_behavior('p="a.c"; [[ "a.c" =~ "$p" ]]; echo $?')
        self.assert_identical_behavior('p="a.c"; [[ axc =~ "$p" ]]; echo $?')

    def test_dquote_escaped_metachar_same_in_all_roles(self):
        # `"a\.c"` keeps its backslash (double-quote escape rule) whether it
        # is the pattern RHS, the regex RHS, or the subject LHS.
        self.assert_identical_behavior(r'[[ "a\.c" == "a\.c" ]]; echo $?')
        self.assert_identical_behavior(r'[[ "a\.c" =~ "a\.c" ]]; echo $?')
        self.assert_identical_behavior(r's="a\.c"; [[ "$s" == "a\.c" ]]; echo $?')
