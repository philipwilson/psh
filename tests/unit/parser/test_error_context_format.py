r"""Unit tests for the parser ErrorContext "Context:" line (psh-specific).

Pins the L9 fix (2026-06-14, reappraisal #6): the diagnostic context line was
built backwards — it placed the FOLLOWING tokens before ``-> HERE <-`` and the
PRECEDING tokens after it, and leaked raw ``TokenType.EOF`` reprs. After the
fix, tokens before the error point render before ``-> HERE <-``, tokens after
render after it, and valueless tokens show friendly placeholders (``<EOF>``).

These assertions are about psh's own error formatting, so there is no bash
comparison.
"""

import pytest

from psh.lexer import tokenize
from psh.parser.recursive_descent.helpers import ParseError
from psh.parser.recursive_descent.parser import Parser


def _parse_error(src):
    p = Parser(tokenize(src), source_text=src)
    with pytest.raises(ParseError) as excinfo:
        p.parse()
    return excinfo.value.error_context


def test_leading_semicolon_context_sides():
    ctx = _parse_error(";echo x")
    # The ';' is at the error point: nothing precedes it; "echo x" follows.
    assert ctx.context_before == []
    assert ctx.context_after == ["echo", "x", "<EOF>"]
    msg = ctx.format_error()
    assert "Context:  -> HERE <- echo x <EOF>" in msg


def test_double_pipe_context_sides():
    ctx = _parse_error("echo x | | echo y")
    assert ctx.context_before == ["echo", "x", "|"]
    assert ctx.context_after == ["echo", "y", "<EOF>"]
    msg = ctx.format_error()
    assert "Context: echo x | -> HERE <- echo y <EOF>" in msg


def test_no_raw_tokentype_repr_leaks():
    # The old format leaked "TokenType.EOF"; the new one must not.
    for src in (";echo x", "echo x | | echo y"):
        msg = _parse_error(src).format_error()
        assert "TokenType." not in msg


def test_eof_rendered_as_placeholder():
    ctx = _parse_error(";echo x")
    assert "<EOF>" in ctx.format_error()
