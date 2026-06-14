"""Conformance tests: extended-glob (extglob) patterns in the parameter-
expansion removal operators ``${v#pat}`` ``${v##pat}`` ``${v%pat}``
``${v%%pat}``.

With ``shopt -s extglob`` enabled, the removal operators interpret the
extended-glob operators ``?(...)`` ``*(...)`` ``+(...)`` ``@(...)``
``!(...)`` in their pattern (matching bash). Earlier psh had two bugs in
the PREFIX path (``#``/``##``):

* the extglob→regex converter ``$``-anchored the pattern, so even
  ``##`` matched the whole string only and ``#`` behaved like ``##``;
* the naive ``.*`` → ``.*?`` rewrite used for "shortest match" never
  touched extglob quantifiers, so ``#`` could not find a short prefix.

The prefix removal now scans candidate prefixes (shortest/longest) using
a full-match regex, mirroring the already-correct suffix path. These tests
pin identical bash behavior for both plain globs and extglob operators.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from conformance_framework import ConformanceTest


class TestExtglobPrefixRemoval(ConformanceTest):
    """``${v#pat}`` / ``${v##pat}`` with extglob operators."""

    def test_plus_one_or_more_shortest(self):
        # +(o) shortest prefix: strips one 'o'
        self.assert_identical_behavior(
            'shopt -s extglob; v=ooo; echo "${v#+(o)}"')

    def test_plus_one_or_more_longest(self):
        # +(o) longest prefix: strips all 'o's
        self.assert_identical_behavior(
            'shopt -s extglob; v=ooo; echo "${v##+(o)}"')

    def test_star_zero_or_more_shortest(self):
        # *(o) shortest prefix matches empty -> value unchanged
        self.assert_identical_behavior(
            'shopt -s extglob; v=ooo; echo "${v#*(o)}"')

    def test_star_zero_or_more_longest(self):
        self.assert_identical_behavior(
            'shopt -s extglob; v=ooo; echo "${v##*(o)}"')

    def test_question_zero_or_one(self):
        self.assert_identical_behavior(
            'shopt -s extglob; v=ooo; echo "${v#?(o)}"')

    def test_literal_then_extglob(self):
        # f+(o): literal f followed by run of o's
        self.assert_identical_behavior(
            'shopt -s extglob; v=fooo; echo "${v#f+(o)}"')
        self.assert_identical_behavior(
            'shopt -s extglob; v=fooo; echo "${v##f+(o)}"')

    def test_run_of_a_shortest_and_longest(self):
        self.assert_identical_behavior(
            'shopt -s extglob; v=aaabbb; echo "${v#+(a)}"')
        self.assert_identical_behavior(
            'shopt -s extglob; v=aaabbb; echo "${v##+(a)}"')

    def test_alternation(self):
        self.assert_identical_behavior(
            'shopt -s extglob; v=abcabc; echo "${v#@(a|b)}"')
        self.assert_identical_behavior(
            'shopt -s extglob; v=abcabc; echo "${v##@(a|b)}"')

    def test_negation(self):
        self.assert_identical_behavior(
            'shopt -s extglob; v=xabc; echo "${v#!(x)}"')
        self.assert_identical_behavior(
            'shopt -s extglob; v=xabc; echo "${v##!(x)}"')

    def test_extglob_off_is_literal(self):
        # Without extglob, +(a) is a literal pattern (no removal here).
        self.assert_identical_behavior('v=aaabbb; echo "${v#+(a)}"')


class TestPlainGlobPrefixRemoval(ConformanceTest):
    """Plain-glob ``#``/``##`` still match bash (regression guard)."""

    def test_star(self):
        self.assert_identical_behavior('v=aaabbb; echo "${v#*}"')
        self.assert_identical_behavior('v=aaabbb; echo "${v##*}"')

    def test_star_with_prefix(self):
        self.assert_identical_behavior('v=aaabbb; echo "${v#a*}"')
        self.assert_identical_behavior('v=aaabbb; echo "${v##a*}"')

    def test_question_and_class(self):
        self.assert_identical_behavior('v=aaabbb; echo "${v#?}"')
        self.assert_identical_behavior('v=aaabbb; echo "${v#[ab]}"')
        self.assert_identical_behavior('v=aaabbb; echo "${v##[ab]*}"')

    def test_no_match_and_empty_pattern(self):
        self.assert_identical_behavior('v=abc; echo "${v#z}"')
        self.assert_identical_behavior('v=abc; echo "${v#}"')
        self.assert_identical_behavior('v=abc; echo "${v##}"')

    def test_full_string(self):
        self.assert_identical_behavior('v=abc; echo "${v#abc}"')


class TestExtglobSuffixRemovalUnaffected(ConformanceTest):
    """``%``/``%%`` suffix removal continues to match bash."""

    def test_plus_one_or_more(self):
        self.assert_identical_behavior(
            'shopt -s extglob; v=ooo; echo "${v%+(o)}"')
        self.assert_identical_behavior(
            'shopt -s extglob; v=ooo; echo "${v%%+(o)}"')

    def test_alternation(self):
        self.assert_identical_behavior(
            'shopt -s extglob; v=abcabc; echo "${v%@(b|c)}"')
