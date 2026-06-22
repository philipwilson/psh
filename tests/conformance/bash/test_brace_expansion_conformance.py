"""
Brace expansion conformance tests (bash compatibility).

Pins two behaviors verified against bash:

1. Char-range backslash: a cross-case character range that spans the backslash
   (ASCII 92, e.g. ``{Z..a}``) emits an *empty but kept* word at the backslash
   position -- bash does NOT output a literal ``\\``, and unlike an empty list
   item the empty word is not dropped.

2. Stray-brace neighbors: stray/unmatched ``{``/``}`` around a valid brace
   group are literal text and do not prevent expanding the valid group
   (``}{a,b}{`` -> ``}a{ }b{``).
"""

import os
import sys

# Add parent directory to path for framework import
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestCharRangeBackslash(ConformanceTest):
    """Cross-case char ranges spanning the backslash match bash."""

    def test_z_to_a(self):
        self.assert_identical_behavior('echo {Z..a}')

    def test_a_to_z_full_span(self):
        self.assert_identical_behavior('echo {A..z}')

    def test_y_to_b(self):
        self.assert_identical_behavior('echo {Y..b}')

    def test_reverse_a_to_z(self):
        self.assert_identical_behavior('echo {a..Z}')

    def test_range_with_step(self):
        self.assert_identical_behavior('echo {Z..a..2}')

    def test_word_count_preserves_empty(self):
        self.assert_identical_behavior('set -- {Z..a}; echo "$#"')

    def test_pure_letter_range_unaffected(self):
        self.assert_identical_behavior('echo {a..e}')


class TestStrayBraceNeighbors(ConformanceTest):
    """Stray braces around a valid group are literal; the group still expands."""

    def test_stray_both_sides(self):
        self.assert_identical_behavior('echo }{a,b}{')

    def test_stray_close_inside_word(self):
        self.assert_identical_behavior('echo a}{b,c}d')

    def test_leading_stray_close(self):
        self.assert_identical_behavior('echo }{a,b}')

    def test_trailing_stray_open(self):
        self.assert_identical_behavior('echo {a,b}{')

    def test_leading_stray_open(self):
        self.assert_identical_behavior('echo {{a,b}')

    def test_nested_group_with_stray_neighbors(self):
        self.assert_identical_behavior('echo }{a,{b,c}}{')

    def test_no_group_stays_literal_open(self):
        self.assert_identical_behavior('echo {a,b')

    def test_no_group_stays_literal_close(self):
        self.assert_identical_behavior('echo a,b}')

    def test_valid_group_unaffected(self):
        self.assert_identical_behavior('echo x{a,b}y')

    def test_param_expansion_not_brace_expanded(self):
        self.assert_identical_behavior('HOME=/h; echo ${HOME}/{a,b}')


class TestLiteralBraceSuffix(ConformanceTest):
    """A literal ``}``/``]`` suffix on a brace group ATTACHES to each expanded
    item — it is not a shell operator (brace expansion is per-word). Previously
    psh space-joined them (``arr[{1,2}]`` -> ``arr[1 2]``) via a vestigial
    'detach' path left over from the token-stream migration (reappraisal #14)."""

    def test_array_subscript_form(self):
        self.assert_identical_behavior('echo arr[{1,2}]')

    def test_bracketed(self):
        self.assert_identical_behavior('echo [{1,2}]')

    def test_close_brace_suffix(self):
        self.assert_identical_behavior('echo {a,b}]')

    def test_double_brace(self):
        self.assert_identical_behavior('echo {{a,b}}')

    def test_sequence_with_bracket_suffix(self):
        self.assert_identical_behavior('echo x{1..3}]')

    def test_prefix_and_bracket_suffix(self):
        self.assert_identical_behavior('echo pre{a,b}suf]')

    def test_escaped_semicolon_attaches(self):
        # An escaped operator sits in the word and attaches to each item (bash).
        self.assert_identical_behavior(r'echo {a,b}\;')

    def test_dot_suffix_regression(self):
        self.assert_identical_behavior('echo {a,b}.txt')

    def test_adjacent_groups_regression(self):
        self.assert_identical_behavior('echo {a,b}{c,d}')
