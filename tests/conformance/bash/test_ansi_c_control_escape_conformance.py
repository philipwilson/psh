r"""Conformance tests for ANSI-C ``$'\cX'`` control-char escapes (bash).

Pins the M8 fix (2026-06-14, reappraisal #6): ``$'\cX'`` produces a control
character. bash maps it as ``0x7f if X == '?' else ord(X) & 0x1f`` — so
``\cI`` -> TAB (0x09), ``\cA`` -> 0x01, ``\cJ`` -> newline (0x0a),
``\cM`` -> CR (0x0d), ``\c@`` -> NUL, ``\cz``/``\cZ`` -> 0x1a (case-
insensitive), ``\c?`` -> 0x7f, ``\c\`` -> 0x1c. Previously psh left
``\cX`` literal.

Output is piped through ``od -An -tx1`` so the comparison is over the exact
bytes (control characters are otherwise invisible). All expectations verified
against bash 5.2.
"""

import sys

from conformance_framework import ConformanceTest


class TestAnsiCControlEscape(ConformanceTest):
    r"""``$'\cX'`` control-character escapes match bash byte-for-byte."""

    def test_ctrl_i_is_tab(self):
        r"""``\cI`` -> TAB (0x09)."""
        self.assert_identical_behavior(r"""printf '%s' $'a\cIb' | od -An -tx1""")

    def test_ctrl_a(self):
        r"""``\cA`` -> 0x01."""
        self.assert_identical_behavior(r"""printf '%s' $'a\cAb' | od -An -tx1""")

    def test_ctrl_j_is_newline(self):
        r"""``\cJ`` -> newline (0x0a)."""
        self.assert_identical_behavior(r"""printf '%s' $'a\cJb' | od -An -tx1""")

    def test_ctrl_m_is_cr(self):
        r"""``\cM`` -> CR (0x0d)."""
        self.assert_identical_behavior(r"""printf '%s' $'a\cMb' | od -An -tx1""")

    def test_ctrl_z_lowercase(self):
        r"""``\cz`` -> 0x1a (case-insensitive)."""
        self.assert_identical_behavior(r"""printf '%s' $'a\czb' | od -An -tx1""")

    def test_ctrl_z_uppercase(self):
        r"""``\cZ`` -> 0x1a."""
        self.assert_identical_behavior(r"""printf '%s' $'a\cZb' | od -An -tx1""")

    def test_ctrl_question_is_del(self):
        r"""``\c?`` -> 0x7f (the special case)."""
        self.assert_identical_behavior(r"""printf '%s' $'a\c?b' | od -An -tx1""")

    def test_ctrl_at_is_nul(self):
        r"""``\c@`` -> NUL (0x00).

        Not an ``assert_identical_behavior`` case: bash's ``printf %s``
        truncates its output at an embedded NUL (a separate, pre-existing
        printf difference — psh's printf does not truncate), which would
        mask the escape. So this checks psh directly: the escape must
        produce the byte 0x00 between 'a' and 'b'.
        """
        import subprocess
        result = subprocess.run(
            [sys.executable, '-m', 'psh', '-c', r"""printf '%s' $'a\c@b'"""],
            capture_output=True)
        assert result.stdout == b'a\x00b'

    def test_ctrl_backslash(self):
        r"""``\c\`` -> 0x1c (control-backslash, consumes the backslash)."""
        self.assert_identical_behavior(r"""printf '%s' $'a\c\zb' | od -An -tx1""")

    def test_ctrl_digit(self):
        r"""``\c1`` -> 0x11 (``& 0x1f``, not letter mapping)."""
        self.assert_identical_behavior(r"""printf '%s' $'a\c1b' | od -An -tx1""")

    def test_ctrl_lowercase_letter(self):
        r"""``\ca`` -> 0x01 (lowercase folds like uppercase)."""
        self.assert_identical_behavior(r"""printf '%s' $'a\cab' | od -An -tx1""")
