"""Direct unit coverage for the extracted formatter quoting/escaping helpers.

These statics used to live inline on ``FormatterVisitor``; they were moved to
``psh.visitor.formatter_quoting`` (reappraisal #18 elegance). The formatter's
byte-for-byte output is locked by the round-trip suites elsewhere; this file
pins the extracted functions in isolation so the escaping rules are legible and
regressions point straight at the helper.
"""

from psh.visitor.formatter_quoting import (
    WORD_LIST_FORCE_QUOTE,
    escape_ansi_c,
    escape_double_quoted,
    format_word_list_item,
    quote_scalar,
)


class TestEscapeDoubleQuoted:
    def test_plain_text_unchanged(self):
        assert escape_double_quoted("hello world") == "hello world"

    def test_double_quote_escaped(self):
        assert escape_double_quoted('a"b') == 'a\\"b'

    def test_backtick_escaped(self):
        assert escape_double_quoted("a`b") == "a\\`b"

    def test_backslash_before_dollar_stays_single(self):
        # "a\$b" stored as a\$b — lexer keeps the backslash verbatim.
        assert escape_double_quoted("a\\$b") == "a\\$b"

    def test_backslash_before_backslash_doubles(self):
        # Stored `a\\b` (2 backslashes): the first backslash pairs with the
        # following one so it doubles; the second precedes `b` so stays single
        # -> 3 emitted backslashes, which re-lex back to the stored 2.
        assert escape_double_quoted("a\\\\b") == "a\\\\\\b"

    def test_trailing_backslash_doubles(self):
        # A lone trailing backslash would pair with the closing quote.
        assert escape_double_quoted("a\\") == "a\\\\"

    def test_backslash_before_escaped_quote_doubles(self):
        assert escape_double_quoted('a\\"') == 'a\\\\\\"'


class TestEscapeAnsiC:
    def test_plain_text_unchanged(self):
        assert escape_ansi_c("hello") == "hello"

    def test_tab_and_newline(self):
        assert escape_ansi_c("a\tb\nc") == "a\\tb\\nc"

    def test_single_quote_escaped(self):
        assert escape_ansi_c("q'x") == "q\\'x"

    def test_backslash_escaped(self):
        assert escape_ansi_c("a\\b") == "a\\\\b"

    def test_escape_char_uses_capital_E(self):
        assert escape_ansi_c("\x1b[0m") == "\\E[0m"

    def test_low_control_char_hex(self):
        assert escape_ansi_c("\x01") == "\\x01"

    def test_del_char_hex(self):
        assert escape_ansi_c("\x7f") == "\\x7f"

    def test_named_controls(self):
        assert escape_ansi_c("\a\b\f\v\r") == "\\a\\b\\f\\v\\r"


class TestFormatWordListItem:
    def test_empty_becomes_empty_double_quotes(self):
        assert format_word_list_item("") == '""'

    def test_plain_item_unquoted(self):
        assert format_word_list_item("plain") == "plain"

    def test_glob_chars_not_quoted(self):
        # Globs / `$` must stay unquoted so expansion still happens.
        assert format_word_list_item("*.txt") == "*.txt"
        assert format_word_list_item("$var") == "$var"

    def test_whitespace_forces_double_quotes(self):
        assert format_word_list_item("a b") == '"a b"'

    def test_operator_chars_force_quotes(self):
        assert format_word_list_item("a;b") == '"a;b"'

    def test_force_quote_set_contents(self):
        assert WORD_LIST_FORCE_QUOTE == set(" \t\n;|&<>()'\"`")


class TestQuoteScalar:
    def test_no_quote_type_returns_text(self):
        assert quote_scalar("foo", None) == "foo"
        assert quote_scalar("foo", "") == "foo"

    def test_single_quote(self):
        assert quote_scalar("a b", "'") == "'a b'"

    def test_double_quote(self):
        assert quote_scalar("a b", '"') == '"a b"'

    def test_ansi_c_prefix(self):
        assert quote_scalar("a\\tb", "$'") == "$'a\\tb'"
