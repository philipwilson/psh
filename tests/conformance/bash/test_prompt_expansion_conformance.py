"""
Conformance tests for prompt expansion (PS1/PS2), exercised via `${var@P}`.

A prompt undergoes backslash-escape decoding AND parameter/command/arithmetic
expansion (bash's default `promptvars`). psh decoded only the `\\`-escapes, so
`$(...)`, `$VAR`, and `$((...))` in PS1 were left literal (reappraisal #13 MED).

Order matters and bash protects escape output from the `$`-pass: a `\\$`-produced
`$` does not start a command substitution, and an escape's value is not
re-interpreted. These are pinned via the `${var@P}` prompt-expansion operator
(`\\[`/`\\]` non-printing markers are intentionally excluded — bash's `@P` omits
them while psh emits readline markers, an unrelated rendering detail).

Verified against bash 5.2.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest


class TestPromptParameterExpansion(ConformanceTest):
    def test_command_substitution(self):
        self.assert_identical_behavior("X='$(echo HI)'; echo \"${X@P}\"")

    def test_variable_expansion(self):
        self.assert_identical_behavior("Y=hi; X='$Y-end'; echo \"${X@P}\"")

    def test_braced_variable(self):
        self.assert_identical_behavior("Y=hi; X='pre${Y}post'; echo \"${X@P}\"")

    def test_arithmetic_expansion(self):
        self.assert_identical_behavior("X='$((1+2))'; echo \"${X@P}\"")

    def test_unset_variable_empty(self):
        self.assert_identical_behavior("X='$NOPE_XYZ-tail'; echo \"${X@P}\"")


class TestPromptEscapeProtection(ConformanceTest):
    """Escape output is not re-expanded; escapes still decode."""

    def test_backslash_dollar_is_literal(self):
        # \$ -> $ must NOT start a command substitution.
        self.assert_identical_behavior("X='\\$(echo HI)'; echo \"${X@P}\"")

    def test_user_host_escapes(self):
        # Computed identically by psh and bash on the same host.
        self.assert_identical_behavior("X='\\u@\\h'; echo \"${X@P}\"")

    def test_dollar_prompt_char(self):
        self.assert_identical_behavior("X='\\$ '; echo \"${X@P}\"")

    def test_mixed_escape_and_expansion(self):
        self.assert_identical_behavior("Y=hi; X='$Y \\u'; echo \"${X@P}\"")


class TestPromptNoExpansion(ConformanceTest):
    def test_plain_text(self):
        self.assert_identical_behavior("X='just text > '; echo \"${X@P}\"")
