r"""
Conformance tests for heredoc DELIMITER handling.

A heredoc delimiter can be written several ways, and quoting/escaping ANY part
of it makes the body literal (no expansion). Before v0.488 psh mis-handled the
escaped/quoted spellings (reappraisal #13):

  - `<<\EOF` (and `<<-\EOF`, `<<EO\F`) recorded the delimiter verbatim with the
    backslash, so the body terminator never matched and the heredoc swallowed
    everything to EOF -> empty output (real-lexer bug);
  - `<<"E F"` (a quoted delimiter with a non-word char) was not recognized by
    the line-gathering completeness oracle, so the body was fed as commands.

The terminator line must also match the delimiter EXACTLY (only `<<-` strips
leading tabs) — a line like `EOF ` with trailing whitespace is body content.

Verified against bash 5.2. (A composite multi-token delimiter like `<<E"O"F` —
quote segments spliced into an unquoted word — remains unsupported; it is very
rare and needs the parser to consume multiple delimiter tokens.)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestHeredocEscapedDelimiterConformance(ConformanceTest):
    """A backslash anywhere in the delimiter quotes the body (no expansion)."""

    def test_backslash_prefixed_delimiter(self):
        self.assert_identical_behavior("x=V\ncat <<\\EOF\nval=$x\nEOF")

    def test_backslash_prefixed_strip_tabs(self):
        self.assert_identical_behavior(
            "x=V\ncat <<-\\EOF\n\tval=$x\n\tEOF")

    def test_backslash_mid_word_delimiter(self):
        self.assert_identical_behavior("x=V\ncat <<EO\\F\nval=$x\nEOF")


class TestHeredocQuotedDelimiterConformance(ConformanceTest):
    """Quoted delimiters, including ones with non-word characters."""

    def test_quoted_delimiter_with_space(self):
        self.assert_identical_behavior("x=V\ncat <<\"E F\"\nval=$x\nE F")

    def test_single_quoted_delimiter(self):
        self.assert_identical_behavior("x=V\ncat <<'EOF'\nval=$x\nEOF")

    def test_double_quoted_delimiter(self):
        self.assert_identical_behavior("x=V\ncat <<\"EOF\"\nval=$x\nEOF")


class TestHeredocTerminatorConformance(ConformanceTest):
    """The terminator must match exactly; trailing whitespace makes it body."""

    def test_trailing_whitespace_is_body(self):
        self.assert_identical_behavior(
            "cat <<EOF\nline\nEOF \nmore\nEOF")

    def test_strip_tabs_terminator(self):
        self.assert_identical_behavior(
            "cat <<-EOF\n\tindented\n\tEOF")


class TestHeredocExpandingConformance(ConformanceTest):
    """Unquoted delimiters still expand the body (regression guard)."""

    def test_plain_delimiter_expands(self):
        self.assert_identical_behavior("x=V\ncat <<EOF\nval=$x\nEOF")

    def test_plain_delimiter_with_pipe(self):
        self.assert_identical_behavior(
            "cat <<EOF | tr a-z A-Z\nhello\nEOF")
