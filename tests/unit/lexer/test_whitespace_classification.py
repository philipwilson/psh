"""Shell whitespace classification at token-boundary decisions (defect D2).

The lexer must use shell whitespace (space/tab/newline) — not Python's
`str.isspace()` — when deciding standalone `!`, standalone `{`, and comment
starts. A non-breaking space, CR, VT, FF, etc. is an ordinary word character,
so it must NOT turn `!` into the negation operator, `{` into a brace group, or
a following `#` into a comment.
"""

import pytest

from psh.lexer import tokenize
from psh.lexer.token_types import TokenType

# Codepoints that are Python-whitespace but NOT shell separators.
NON_SHELL_WS = [" ", " ", " ", " ", "　", "\x0b", "\x0c", "\r"]


def _types(text):
    return [t.type for t in tokenize(text)]


@pytest.mark.parametrize("ws", NON_SHELL_WS)
def test_bang_before_non_shell_whitespace_is_word(ws):
    """`!<ws>false` — `!` is NOT the EXCLAMATION negation operator."""
    types = _types(f"!{ws}false")
    assert TokenType.EXCLAMATION not in types


@pytest.mark.parametrize("ws", NON_SHELL_WS)
def test_brace_before_non_shell_whitespace_is_word(ws):
    """`{<ws>echo hi; }` — leading `{` is NOT a brace-group LBRACE."""
    types = _types(f"{{{ws}echo hi; }}")
    # The `{` fuses into a word rather than opening a group.
    assert types[0] == TokenType.WORD


@pytest.mark.parametrize("ws", ["\x0b", "\x0c", "\r", " "])
def test_hash_after_non_shell_whitespace_is_not_comment(ws):
    """`a<ws>#b` — `#` after a non-shell-whitespace char is a word char."""
    # If `#b` were a comment, only WORD("a...") + EOF would remain and the `#b`
    # text would be gone. Assert the `#b` survives in the token stream.
    toks = tokenize(f"echo a{ws}#b")
    joined = "".join(t.value for t in toks)
    assert "#b" in joined


def test_brace_before_shell_whitespace_still_group():
    """Regression: `{ echo hi; }` (real space) is still a brace group."""
    types = _types("{ echo hi; }")
    assert types[0] == TokenType.LBRACE


def test_bang_before_space_still_negation():
    """Regression: `! false` (real space) is still the EXCLAMATION operator."""
    types = _types("! false")
    assert TokenType.EXCLAMATION in types


def test_hash_after_space_still_comment():
    """Regression: `echo a #b` (real space) — `#b` is a comment."""
    toks = tokenize("echo a #b")
    joined = "".join(t.value for t in toks)
    assert "#b" not in joined
