"""Census-pinned behavior of the lexer's fallback word collector (B6).

An instrumented census (2026-06-12: 15k-input characterization corpus +
the full test suite + ~71k fuzz inputs) established two facts about the
tokenize loop's tail:

1. The operator-debris collector (historically ``_handle_fallback_word``,
   now ``OperatorDebrisWordRecognizer``) is LIVE for exactly four
   word-start character classes — ``]``, ``+``, ``=``, ``[`` — all of which produce
   bash-correct behavior (each shape below was probe-verified against
   bash 5.2). These tests pin the exact token streams so the fallback's
   looser terminator set (``= + [ ]`` do not terminate fallback words)
   is never accidentally folded into the literal recognizer's stricter
   grammar.

2. The post-fallback "no recognizer consumed the character" branch is
   UNREACHABLE (zero hits anywhere), so it now raises instead of
   silently dropping the character (v0.300 fail-loudly policy).
"""

import pytest

from psh.lexer import tokenize
from psh.lexer.modular_lexer import ModularLexer


def _words(text):
    return [(t.type.name, t.value) for t in tokenize(text)
            if t.type.name != 'EOF']


class TestFallbackWordClasses:
    """One pin per census class; bash-verified shapes."""

    def test_closing_bracket_word(self):
        # `[ x = y ]` — the closing `]` of a test command
        assert _words('echo ]') == [('WORD', 'echo'), ('WORD', ']')]

    def test_closing_bracket_composite(self):
        # `a]b` — WORD 'a' + adjacent WORD ']b', re-joined by the parser
        assert _words('a]b') == [('WORD', 'a'), ('WORD', ']b')]

    def test_sparse_array_element_prefix(self):
        # a=([1]=x z): the `]=x` after the LBRACKET/index is a fallback word
        assert _words('a=([1]=x z)') == [
            ('WORD', 'a='), ('LPAREN', '('), ('LBRACKET', '['),
            ('WORD', '1'), ('WORD', ']=x'), ('WORD', 'z'), ('RPAREN', ')'),
        ]

    def test_plus_equals_append(self):
        # vars+=(x): WORD 'vars' + WORD '+=' re-joined by the parser
        assert _words('vars+=(x)') == [
            ('WORD', 'vars'), ('WORD', '+='), ('LPAREN', '('),
            ('WORD', 'x'), ('RPAREN', ')'),
        ]

    def test_plus_option_word(self):
        # set +x
        assert _words('set +x') == [('WORD', 'set'), ('WORD', '+x')]

    def test_bare_equals_word(self):
        # [ x = y ] — the '=' and closing ']' are fallback words
        assert _words('[ x = y ]') == [
            ('LBRACKET', '['), ('WORD', 'x'), ('WORD', '='), ('WORD', 'y'),
            ('WORD', ']'),
        ]

    def test_assignment_continuation(self):
        # a=b=c: WORD 'a=b' + adjacent WORD '=c' (parser re-joins; the
        # command assigns b=c to a, like bash)
        assert _words('a=b=c') == [('WORD', 'a=b'), ('WORD', '=c')]

    def test_case_pattern_glob_class(self):
        toks = _words('case 5 in [0-9]*) echo d;; esac')
        assert ('WORD', '[0-9]*') in toks


class TestNoSilentDrop:
    """The 'nothing consumed this character' branch must fail loudly."""

    def test_unconsumed_character_raises(self):
        # The branch is unreachable through real input (census), so reach
        # it by stubbing out every consumer the loop tries. The
        # operator-debris collector is now the lowest-priority recognizer,
        # so stubbing registry.recognize covers it too.
        lexer = ModularLexer('x')
        lexer.registry.recognize = lambda *a, **k: None
        with pytest.raises(RuntimeError, match='no progress'):
            lexer.tokenize()
