"""Lexer command-position feeding for `f() [[` and `for x do` (reappraisal #16 g).

Token-level pins for the two spots where the grammar context matters:

- After a `)` the lexer returns to command position, so `[[` is tokenized as
  the DOUBLE_LBRACKET test operator (not a plain WORD) at the start of a
  function body / case body.
- `do` closing a no-`in` loop header (`for x do`, `for x; do`) is normalized to
  the DO keyword, and `pending_in` is cleared so a later `in` in the body stays
  a WORD. The normalizer must be idempotent because it runs twice (lexer
  pipeline, then the parser's create_context).
"""

from psh.lexer import tokenize
from psh.lexer.keyword_normalizer import KeywordNormalizer
from psh.lexer.token_types import TokenType


def _types(text):
    return [(t.type, t.value) for t in tokenize(text)]


def test_double_bracket_after_function_header():
    """`f() [[` — `[[` is the test operator, not a WORD."""
    types = _types('f() [[ -n x ]]')
    assert (TokenType.DOUBLE_LBRACKET, '[[') in types
    assert (TokenType.DOUBLE_RBRACKET, ']]') in types


def test_double_bracket_after_case_pattern():
    """`x) [[` at the start of a case body is the test operator."""
    types = _types('case x in x) [[ -n y ]];; esac')
    assert (TokenType.DOUBLE_LBRACKET, '[[') in types


def test_bracket_still_word_when_not_command_position():
    """A glob `[abc]` in argument position is untouched (regression)."""
    types = _types('echo [abc]*')
    assert (TokenType.DOUBLE_LBRACKET, '[[') not in types


def test_for_no_in_do_is_keyword():
    """`for x do` — `do` (no separator) normalizes to the DO keyword."""
    toks = tokenize('for x do echo hi; done')
    do = [t for t in toks if t.value == 'do'][0]
    assert do.type == TokenType.DO


def test_for_no_in_semicolon_do_clears_pending_in():
    """`for x; do echo in` — the body `in` stays a WORD (pending_in cleared)."""
    toks = tokenize('for x; do echo in; done')
    in_tok = [t for t in toks if t.value == 'in'][0]
    assert in_tok.type == TokenType.WORD


def test_normalizer_idempotent_for_no_in_loop():
    """A second normalization pass (parser create_context) must not re-break
    the body `in` after `do` was already typed on the first pass."""
    once = tokenize('for x do echo in; done')          # already normalized
    twice = KeywordNormalizer().normalize(list(once))
    in_tok = [t for t in twice if t.value == 'in'][0]
    do_tok = [t for t in twice if t.value == 'do'][0]
    assert do_tok.type == TokenType.DO
    assert in_tok.type == TokenType.WORD


def test_explicit_in_form_unaffected():
    """`for x in a` still recognizes IN (regression)."""
    toks = tokenize('for x in a b; do echo $x; done')
    assert any(t.type == TokenType.IN for t in toks)
