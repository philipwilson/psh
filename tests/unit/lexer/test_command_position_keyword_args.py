"""Keyword-SPELLED arguments must not restore lexer command position.

A WORD whose value merely spells a reserved word (`if`, `while`, `case`, ...)
only opens command position / case state when it is ITSELF at command position
(a genuine keyword). As an ordinary argument (`echo if [[ x`) it must not flip
the classification of the following token, so `[[` stays a plain WORD and the
input parses like bash (`echo if [[ x` prints `if [[ x`), instead of `[[` being
mis-lexed as the DOUBLE_LBRACKET test operator and causing a parse error.

This pins the eligibility gate in
`ModularLexer._update_command_position_context` (lexer defect D1). The lexer
now matches the KeywordNormalizer, which only promotes a WORD to a keyword at
command position.
"""

import pytest

from psh.lexer import tokenize
from psh.lexer.token_types import TokenType


def _types(text):
    return [(t.type, t.value) for t in tokenize(text)]


# Every keyword the lexer treats as a command-position setter, as an argument.
@pytest.mark.parametrize("kw", [
    "if", "while", "until", "for", "then", "else", "elif", "do", "time",
])
def test_keyword_arg_does_not_enable_double_bracket(kw):
    """`echo <kw> [[ x` — the arg does not turn on `[[` recognition."""
    types = _types(f"echo {kw} [[ x")
    assert (TokenType.DOUBLE_LBRACKET, "[[") not in types
    # The `[[` survives as an ordinary word (possibly fused into a composite).
    assert any(val == "[[" and typ != TokenType.DOUBLE_LBRACKET
               for typ, val in types)


def test_case_arg_does_not_open_case_state():
    """`echo case x in` — an argument `case` must not open case tracking.

    If it did, a later `[` would be mis-lexed as a glob character class inside
    a (phantom) case pattern. We assert no double-bracket / test-operator
    appears and the words survive intact.
    """
    types = _types("echo case x in")
    assert (TokenType.DOUBLE_LBRACKET, "[[") not in types
    values = [v for _, v in types]
    assert values[:4] == ["echo", "case", "x", "in"]


def test_keyword_arg_after_separator_still_gated():
    """`false; echo if [[ x` — separator resets to command position, but the
    keyword-arg `if` is not itself at command position, so `[[` stays a word."""
    types = _types("false; echo if [[ x")
    assert (TokenType.DOUBLE_LBRACKET, "[[") not in types


# --- Regression guards: genuine keywords at command position still work ------

def test_real_if_enables_double_bracket():
    """A genuine `if` at command position keeps `[[` recognition on."""
    types = _types("if [[ -n x ]]; then echo y; fi")
    assert (TokenType.DOUBLE_LBRACKET, "[[") in types
    assert (TokenType.DOUBLE_RBRACKET, "]]") in types


def test_real_while_enables_double_bracket():
    types = _types("while [[ -n x ]]; do break; done")
    assert (TokenType.DOUBLE_LBRACKET, "[[") in types


def test_time_prefix_enables_double_bracket():
    """`time [[ ... ]]` — `time` at command position keeps `[[` on."""
    types = _types("time [[ -n x ]]")
    assert (TokenType.DOUBLE_LBRACKET, "[[") in types


def test_keyword_after_then_enables_double_bracket():
    """A keyword after `then` (itself at command position) still works."""
    types = _types("if x; then while [[ -n y ]]; do break; done; fi")
    assert (TokenType.DOUBLE_LBRACKET, "[[") in types


def test_real_case_opens_case_state():
    """A genuine `case` still tracks case state (glob `[` inside pattern)."""
    types = _types("case x in [a-z]) echo hi;; esac")
    # Inside the case pattern `[a-z]` the `[` is a glob class, not LBRACKET.
    assert (TokenType.LBRACKET, "[") not in types
