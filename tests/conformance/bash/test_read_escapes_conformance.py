"""Conformance tests for `read` backslash-escape semantics (bash).

Pins the H3 fix (2026-06-14, reappraisal #6): `read` without -r must NOT do
C-style escape translation. A backslash simply removes the special meaning of
the next character (``\\t`` -> ``t``, NOT a TAB; ``\\n`` -> ``n``, NOT a
newline; ``\\\\`` -> ``\\``). A backslash before the line delimiter is line
continuation (both removed, reading continues onto the next line). A
backslash-escaped IFS character is protected from word splitting and
trimming. With -r, backslashes are fully literal and no continuation happens.

Inputs are built with ``printf '%s\\n' 'LITERAL'`` so the single-quoted data
reaches `read` verbatim with no printf escape interpretation, and multiple
arguments emit successive newline-terminated lines (for continuation tests).
All expectations verified against bash 5.2.
"""


from conformance_framework import ConformanceTest


class TestReadBackslashEscapes(ConformanceTest):
    """read (no -r) strips backslashes; it does not translate C-escapes."""

    def test_backslash_t_is_literal_t(self):
        r"""``\t`` -> ``t``, not a TAB (the headline H3 bug)."""
        self.assert_identical_behavior(
            r"""printf '%s\n' 'a\tb' | { read x; printf '[%s]' "$x"; }""")

    def test_backslash_n_is_literal_n(self):
        r"""``\n`` -> ``n``, not a newline."""
        self.assert_identical_behavior(
            r"""printf '%s\n' 'a\nb' | { read x; printf '[%s]' "$x"; }""")

    def test_backslash_backslash_collapses(self):
        r"""``\\`` -> ``\`` (one backslash)."""
        self.assert_identical_behavior(
            r"""printf '%s\n' 'a\\b' | { read x; printf '[%s]' "$x"; }""")

    def test_backslash_other_char_drops_backslash(self):
        r"""``\x`` -> ``x`` (backslash removed before an ordinary char)."""
        self.assert_identical_behavior(
            r"""printf '%s\n' 'a\xb' | { read x; printf '[%s]' "$x"; }""")

    def test_raw_mode_t_is_literal(self):
        r"""-r: ``\t`` stays ``\t`` verbatim."""
        self.assert_identical_behavior(
            r"""printf '%s\n' 'a\tb' | { read -r x; printf '[%s]' "$x"; }""")

    def test_raw_mode_backslash_backslash_literal(self):
        r"""-r: ``\\`` stays ``\\``."""
        self.assert_identical_behavior(
            r"""printf '%s\n' 'a\\b' | { read -r x; printf '[%s]' "$x"; }""")


class TestReadEscapedDelimiters(ConformanceTest):
    """Backslash-escaped IFS characters are protected from splitting."""

    def test_escaped_space_suppresses_split(self):
        r"""``a\ b`` -> single field "a b"; second var stays empty."""
        self.assert_identical_behavior(
            r"""printf '%s\n' 'a\ b' | { read x y; """
            r"""printf 'x=[%s] y=[%s]' "$x" "$y"; }""")

    def test_escaped_space_raw_is_literal(self):
        r"""-r: the backslash is literal so it splits at the space."""
        self.assert_identical_behavior(
            r"""printf '%s\n' 'a\ b' | { read -r x y; """
            r"""printf 'x=[%s] y=[%s]' "$x" "$y"; }""")

    def test_escaped_custom_ifs_char(self):
        r"""IFS=: with ``a\:b:c`` -> field "a:b" then "c"."""
        self.assert_identical_behavior(
            r"""printf '%s\n' 'a\:b:c' | { IFS=: read x y; """
            r"""printf 'x=[%s] y=[%s]' "$x" "$y"; }""")

    def test_read_array_escaped_space(self):
        r"""read -a: ``a\ b c`` -> two elements, "a b" and "c"."""
        self.assert_identical_behavior(
            r"""printf '%s\n' 'a\ b c' | { read -a A; """
            r"""printf '%d:[%s][%s]' "${#A[@]}" "${A[0]}" "${A[1]}"; }""")

    def test_single_var_keeps_escaped_leading_space(self):
        r"""Leading ``\ `` is protected from IFS trimming."""
        self.assert_identical_behavior(
            r"""printf '%s\n' '\ x' | { read v; printf '[%s]' "$v"; }""")

    def test_single_var_keeps_escaped_trailing_space(self):
        r"""Trailing ``\ `` is protected from IFS trimming."""
        self.assert_identical_behavior(
            r"""printf '%s\n' 'x\ ' | { read v; printf '[%s]' "$v"; }""")


class TestReadLineContinuation(ConformanceTest):
    r"""Backslash-<newline> is line continuation (non-raw only).

    ``printf '%s\n' 'a\' 'b'`` emits two lines: ``a\`` and ``b``; the
    trailing backslash escapes the newline.
    """

    def test_continuation_joins_lines(self):
        r"""``a\`` then ``b`` -> "ab" (backslash and newline removed)."""
        self.assert_identical_behavior(
            r"""printf '%s\n' 'a\' 'b' | { read x; printf '[%s]' "$x"; }""")

    def test_double_continuation(self):
        r"""Two continuations chain -> "abc"."""
        self.assert_identical_behavior(
            r"""printf '%s\n' 'a\' 'b\' 'c' | { read x; printf '[%s]' "$x"; }""")

    def test_raw_mode_no_continuation(self):
        r"""-r: the trailing backslash is literal; reading stops at the nl."""
        self.assert_identical_behavior(
            r"""printf '%s\n' 'a\' 'b' | { read -r x; printf '[%s]' "$x"; }""")

    def test_escaped_backslash_then_newline_is_not_continuation(self):
        r"""``a\\`` -> the backslash is escaped, not a continuation."""
        self.assert_identical_behavior(
            r"""printf '%s\n' 'a\\' 'b' | { read x; printf '[%s]' "$x"; }""")


class TestReadReplyTrimming(ConformanceTest):
    """A defaulted REPLY keeps the whole line; explicit vars are trimmed."""

    def test_default_reply_not_trimmed(self):
        """`read` (no var) leaves leading/trailing whitespace in REPLY."""
        self.assert_identical_behavior(
            r"""printf '%s\n' '  hi there  ' | { read; printf '[%s]' "$REPLY"; }""")

    def test_explicit_reply_is_trimmed(self):
        """`read REPLY` trims like any single named variable."""
        self.assert_identical_behavior(
            r"""printf '%s\n' '  hi  ' | { read REPLY; printf '[%s]' "$REPLY"; }""")

    def test_single_named_var_trimmed(self):
        self.assert_identical_behavior(
            r"""printf '%s\n' '  hi  ' | { read v; printf '[%s]' "$v"; }""")
