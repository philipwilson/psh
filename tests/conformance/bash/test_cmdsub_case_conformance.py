"""Conformance tests: grammar-aware command-substitution extents.

A command substitution may contain an unmatched `)` — in case patterns
(`$(case x in x) ...;; esac)`), comments, and heredoc bodies — and bash
finds the real closer by re-invoking its parser (xparse_dolparen). PSH
matches via the grammar-aware extent scanner (find_command_substitution_end
in psh/lexer/pure_helpers.py); these tests pin identical bash behavior for
the forms the user guide claims (Ch. 6 / Ch. 17 command substitution).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from conformance_framework import ConformanceTest


class TestCasePatternsInCommandSub(ConformanceTest):
    """Bare `pattern)` case forms inside $(...) behave like bash."""

    def test_bare_case_pattern_in_cmdsub(self):
        self.assert_identical_behavior(
            'echo $(case x in x) echo inner;; esac)')

    def test_multi_branch_and_alternation(self):
        self.assert_identical_behavior(
            'echo $(case b in a) echo A;; b) echo B;; c) echo C;; esac)')
        self.assert_identical_behavior(
            'echo $(case y in x|y) echo XY;; esac)')

    def test_fallthrough_operators_in_cmdsub(self):
        self.assert_identical_behavior(
            'echo $(case x in x) echo one;;& *) echo two;; esac)')
        self.assert_identical_behavior(
            'echo $(case x in x) echo one;& y) echo two;; esac)')

    def test_nested_and_quoted_contexts(self):
        self.assert_identical_behavior(
            'echo $(echo $(case x in x) echo i;; esac))')
        self.assert_identical_behavior(
            'echo "$(case x in x) echo dq;; esac)"')
        self.assert_identical_behavior(
            'for f in $(case x in x) echo a b;; esac); do echo "<$f>"; done')

    def test_case_keyword_only_at_command_position(self):
        # `case` as an argument is not a keyword; the first ')' closes.
        self.assert_identical_behavior('echo $(echo case in x)')


class TestHiddenParensInCommandSub(ConformanceTest):
    """Parens in comments and heredoc bodies do not close $(...)."""

    def test_comment_hides_paren(self):
        self.assert_identical_behavior('echo $(# comment with )\necho hi)')

    def test_heredoc_body_paren(self):
        self.assert_identical_behavior('echo $(cat <<EOF\n)\nEOF\n)')

    def test_quoted_delimiter_heredoc_body(self):
        self.assert_identical_behavior('echo $(cat <<"EOF"\na ) b\nEOF\n)')

    def test_multiline_case_in_cmdsub(self):
        self.assert_identical_behavior('echo $(case x in\nx) echo nl;;\nesac)')
