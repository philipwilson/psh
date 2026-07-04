"""Parse-error message quality (reappraisal #17 Tier-2, RD-parser MED-2).

Pins the diagnostics cluster fix:

- the default expect() message renders FRIENDLY token names through the
  shared ``TOKEN_DISPLAY_NAMES`` map ("Expected 'then', got end of input"),
  never a raw ``TokenType.THEN`` enum repr;
- the contextual suggestions are keyed on the STRUCTURED expected token
  type, not string-matched against the (previously leaky) message;
- ``ErrorContext.line`` carries the ABSOLUTE source line when the parser
  is given a ``line_offset`` (multi-line scripts previously reported
  "line 1" for every fragment);
- EOF-shaped errors carry the source line + caret context like every
  other error (they used to render as a bare one-liner).

These assertions are about psh's own error formatting, so there is no
bash comparison.
"""

import pytest

from psh.lexer import tokenize
from psh.lexer.token_types import TokenType
from psh.parser.recursive_descent.helpers import (
    ParseError,
    describe_token,
    token_display_name,
)
from psh.parser.recursive_descent.parser import Parser


def _parse_error(src, **parser_kwargs):
    p = Parser(tokenize(src), source_text=src, **parser_kwargs)
    with pytest.raises(ParseError) as excinfo:
        p.parse()
    return excinfo.value


class TestFriendlyTokenNames:
    @pytest.mark.parametrize("src, expected_fragment", [
        ("if true then echo x fi", "Expected 'then', got end of input"),
        ("while true do echo x done", "Expected 'do', got end of input"),
        ("{ echo noclose", "Expected '}', got end of input"),
        ("case a in a) echo x esac", "Expected 'esac', got end of input"),
    ])
    def test_expect_message_uses_display_names(self, src, expected_fragment):
        err = _parse_error(src)
        assert expected_fragment in err.message

    @pytest.mark.parametrize("src", [
        "if true then echo x fi",
        "while true do echo x done",
        "{ echo noclose",
        "case a in a) echo x esac",
        "echo a |",
        "true &&",
    ])
    def test_no_raw_enum_repr_anywhere(self, src):
        err = _parse_error(src)
        assert "TokenType." not in err.message
        assert "TokenType." not in err.error_context.format_error()

    def test_display_name_map_never_leaks_enum_repr(self):
        for tt in TokenType:
            assert "TokenType." not in token_display_name(tt)

    def test_describe_token_prefers_value(self):
        tok = tokenize("fi")[0]
        assert describe_token(tok) == "'fi'"


class TestSuggestionsKeyedOnTokenType:
    """The suggestion logic keys on the expected token TYPE (it used to
    string-match "Expected TokenType.THEN", coupled to the leaky format)."""

    @pytest.mark.parametrize("src, suggestion", [
        ("if true then echo x fi", "Add ';' before 'then' keyword"),
        ("while true do echo x done", "Add ';' before 'do' keyword"),
        ("{ echo noclose", "Add '}' to close brace group"),
    ])
    def test_suggestion_attached(self, src, suggestion):
        err = _parse_error(src)
        assert suggestion in err.error_context.suggestions

    def test_custom_message_still_gets_suggestion(self):
        # Even when the raise site supplies its own message text, the
        # suggestion keys on the structured expected type.
        from psh.parser.recursive_descent.context import ParserContext
        ctx = ParserContext(tokens=tokenize("x"), source_text="x")
        with pytest.raises(ParseError) as excinfo:
            ctx.consume(TokenType.THEN, "custom message")
        assert ("Add ';' before 'then' keyword"
                in excinfo.value.error_context.suggestions)


class TestAbsoluteLineNumbers:
    def test_line_offset_shifts_reported_line(self):
        # Fragment starting at absolute line 4 (3 lines precede it).
        err = _parse_error("echo )", line_offset=3)
        assert err.error_context.line == 4
        assert "(line 4, column 6)" in err.error_context.format_error()

    def test_zero_offset_keeps_relative_line(self):
        err = _parse_error("echo )")
        assert err.error_context.line == 1

    def test_multiline_fragment_offsets_inner_line(self):
        # Error on the fragment's own line 2, fragment starts at line 10.
        err = _parse_error("if true\nthen echo )\nfi", line_offset=9)
        assert err.error_context.line == 11
        # The caret still points at the fragment-relative source line.
        assert err.error_context.source_line == "then echo )"


class TestEofErrorsGetRichContext:
    """EOF-at-incomplete errors used to lack the source line/caret."""

    @pytest.mark.parametrize("src", ["echo a |", "true &&", "{ echo noclose"])
    def test_source_line_and_caret_present(self, src):
        err = _parse_error(src)
        assert err.at_eof
        assert err.error_context.source_line == src
        formatted = err.error_context.format_error()
        assert f"\n{src}\n" in formatted
        assert any(line.rstrip().endswith("^") and set(line.rstrip()) <= {" ", "^"}
                   for line in formatted.splitlines())

    def test_unclosed_expansion_error_has_location(self):
        err = _parse_error("echo $(foo")
        assert err.at_eof
        assert err.unclosed_expansion == "command"
        assert err.error_context.line == 1
        assert err.error_context.source_line == "echo $(foo"
