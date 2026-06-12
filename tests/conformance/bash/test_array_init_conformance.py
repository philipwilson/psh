"""
Array initializer expansion conformance tests.

Pins the headline fixes from the 2026-06-11 code quality assessment
(Concrete Correctness Risk #1): array initializers ``a=(...)`` must use
the same quote-aware expansion pipeline as command arguments — quoted
glob patterns stay literal, unquoted expansions split on $IFS, and
``set -f`` suppresses globbing.
"""

import os
import sys

# Add parent directory to path for framework import
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestArrayInitializerExpansion(ConformanceTest):
    """Array initialization expansion semantics."""

    def test_quoted_glob_stays_literal(self):
        """A quoted glob pattern in an initializer is not expanded."""
        self.assert_identical_behavior(
            'd=$(mktemp -d); cd "$d"; touch p1.txt p2.txt; '
            'a=("*.txt" *.txt); echo ${#a[@]} "${a[0]}" "${a[1]}" "${a[2]}"; '
            'cd /; rm -rf "$d"')

    def test_ifs_splitting_in_initializer(self):
        """Unquoted expansions in initializers split on $IFS."""
        self.assert_identical_behavior(
            'x="a:b:c"; IFS=:; a=($x); echo ${#a[@]} "${a[1]}"')

    def test_noglob_suppresses_initializer_globbing(self):
        """set -f keeps glob patterns literal inside initializers."""
        self.assert_identical_behavior(
            'd=$(mktemp -d); cd "$d"; touch p1.txt; '
            'set -f; a=(*.txt); echo ${#a[@]} "${a[0]}"; '
            'set +f; cd /; rm -rf "$d"')

    def test_quoted_array_splice_preserves_elements(self):
        """b=("${a[@]}") preserves elements; b=(${a[@]}) resplits."""
        self.assert_identical_behavior(
            'a=("x y" z); b=("${a[@]}"); c=(${a[@]}); '
            'echo ${#b[@]} ${#c[@]} "${b[0]}"')

    def test_scalar_element_assignment_no_glob_no_split(self):
        """a[0]=* stays literal: scalar assignment context, not a list."""
        self.assert_identical_behavior(
            'x="1 2"; a[0]=*; a[1]=$x; echo "${a[0]}" "${a[1]}" ${#a[@]}')

    def test_quoted_bracket_element_is_literal(self):
        """a=("[0]"=x): quoting the brackets makes a literal element, not an
        explicit-index assignment (fallback audit 2026-06-12 — the deleted
        legacy string re-parser wrongly assigned a[0]=x here)."""
        self.assert_identical_behavior(
            'a=("[0]"=x); echo ${#a[@]} "${a[0]}"')

    def test_fully_quoted_bracket_element_is_literal(self):
        """a=("[0]=x") is one literal element."""
        self.assert_identical_behavior(
            'a=("[0]=x"); echo ${#a[@]} "${a[0]}"')

    def test_unquoted_explicit_index_assignment(self):
        """a=([1]=x [3]=y z): unquoted explicit indices assign sparsely."""
        self.assert_identical_behavior(
            'a=([1]=x [3]=y z); echo ${#a[@]} "${a[1]}" "${a[3]}" "${a[4]}" '
            '"${!a[@]}"')
