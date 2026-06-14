"""Conformance tests for `read -N count` (bash).

Pins the L5 fix (reappraisal #7): `read -N N` reads EXACTLY N characters,
ignoring the line delimiter entirely and NOT splitting/trimming on IFS. This
differs from `-n N`, which reads at MOST N characters but stops early at the
delimiter. EOF before reaching the count assigns the partial input and
returns 1. All expectations verified against bash 5.2.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestReadExactChars(ConformanceTest):
    """`read -N` reads exactly N chars, ignoring delimiter and IFS."""

    def test_exact_count_basic(self):
        """-N 3 reads exactly three characters."""
        self.assert_identical_behavior(
            r"""printf 'abcdef' | { read -N 3 x; printf '[%s]' "$x"; }""")

    def test_delimiter_is_ignored(self):
        """A newline does not stop -N: it is read as one of the N chars."""
        self.assert_identical_behavior(
            r"""printf 'ab\ncd' | { read -N 4 x; printf '[%s]' "$x"; }""")

    def test_leading_whitespace_not_trimmed(self):
        """IFS whitespace is NOT trimmed from the result of -N."""
        self.assert_identical_behavior(
            r"""printf '  abc  ' | { read -N 4 x; printf '[%s]' "$x"; }""")

    def test_no_ifs_splitting_across_vars(self):
        """All N chars go to the first variable; -N never splits on IFS."""
        self.assert_identical_behavior(
            r"""printf 'a b c' | { read -N 5 x y; printf 'x=[%s] y=[%s]' "$x" "$y"; }""")

    def test_eof_before_count_returns_one(self):
        """EOF before N chars: partial input assigned, exit status 1."""
        self.assert_identical_behavior(
            r"""printf 'ab' | { read -N 5 x; printf 'rc=%s [%s]' "$?" "$x"; }""")

    def test_count_zero(self):
        """-N 0 reads nothing and succeeds."""
        self.assert_identical_behavior(
            r"""printf 'abc' | { read -N 0 x; printf 'rc=%s [%s]' "$?" "$x"; }""")

    def test_n_lowercase_still_stops_at_delimiter(self):
        """Regression: -n still stops at the newline delimiter."""
        self.assert_identical_behavior(
            r"""printf 'ab\ncd' | { read -n 3 x; printf '[%s]' "$x"; }""")
