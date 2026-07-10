"""R2 (Phase C) pins: immutable tokens, SourceSpan/SourceMap invariants, and
the declared-field sentinel conventions that replaced dynamic setattr+hasattr.

Locks the source-faithful-token contract:
- Token is frozen (never mutated after the lexer produces them).
- SourceSpan derives from the token offsets and reconstructs the lexeme.
- SourceMap is the one offset -> (line, column) + line-text service.
- heredoc_key / array_init absence is signalled by None (a declared field),
  NOT by a missing attribute — a token WITHOUT one must not be treated as
  carrying one.
"""

import dataclasses

import pytest

from psh.lexer import tokenize, tokenize_with_heredocs
from psh.lexer.keyword_normalizer import KeywordNormalizer
from psh.lexer.position import SourceMap
from psh.lexer.token_parts import TokenPart
from psh.lexer.token_types import SourceSpan, Token, TokenType


class TestFrozenTokens:
    def test_token_is_frozen(self):
        assert Token.__dataclass_params__.frozen is True

    def test_token_cannot_be_mutated(self):
        t = Token(TokenType.WORD, "x", 0, 1)
        with pytest.raises(dataclasses.FrozenInstanceError):
            t.type = TokenType.IF
        with pytest.raises(dataclasses.FrozenInstanceError):
            t.value = "y"
        with pytest.raises(dataclasses.FrozenInstanceError):
            t.is_keyword = True

    def test_replace_makes_a_new_token_and_leaves_original(self):
        t = Token(TokenType.WORD, "if", 0, 2)
        t2 = dataclasses.replace(t, type=TokenType.IF, is_keyword=True)
        assert t.type is TokenType.WORD and t.is_keyword is False
        assert t2.type is TokenType.IF and t2.is_keyword is True
        assert t2 is not t

    def test_replace_preserves_token_parts(self):
        t = Token(TokenType.WORD, "x", 0, 1, parts=[TokenPart(value="x")])
        t2 = dataclasses.replace(t, line=9)
        assert t2.line == 9 and t2.parts == t.parts

    def test_tokenize_output_is_immutable(self):
        for tok in tokenize("echo hi | cat && for x in a; do :; done"):
            with pytest.raises(dataclasses.FrozenInstanceError):
                tok.value = "mutated"


class TestSourceSpan:
    def test_span_derives_from_offsets(self):
        t = Token(TokenType.WORD, "echo", 3, 7)
        assert t.span == SourceSpan(3, 7)
        assert (t.span.start, t.span.end) == (t.position, t.end_position)

    def test_span_reconstructs_word_lexemes(self):
        src = "echo hello world"
        for tok in tokenize(src):
            if tok.type == TokenType.WORD:
                assert src[tok.span.start:tok.span.end] == tok.value

    def test_spans_are_monotonic_nondecreasing(self):
        toks = tokenize("a | b && c ; d > e")
        starts = [t.span.start for t in toks]
        assert starts == sorted(starts)
        for t in toks:
            assert t.span.end >= t.span.start


class TestSourceMap:
    def test_location_line_and_column(self):
        sm = SourceMap("ab\ncde\nf")
        assert (sm.location(0).line, sm.location(0).column) == (1, 1)  # 'a'
        assert (sm.location(3).line, sm.location(3).column) == (2, 1)  # 'c'
        assert (sm.location(4).line, sm.location(4).column) == (2, 2)  # 'd'
        assert (sm.location(7).line, sm.location(7).column) == (3, 1)  # 'f'

    def test_location_clamps_out_of_range(self):
        sm = SourceMap("abc")
        assert sm.location(100).offset == 3
        assert sm.location(-5).offset == 0

    def test_line_text_matches_splitlines(self):
        src = "one\ntwo\nthree"
        sm = SourceMap(src)
        for i, expected in enumerate(src.splitlines(), start=1):
            assert sm.line_text(i) == expected
        assert sm.line_text(0) is None
        assert sm.line_text(99) is None

    def test_line_starts_monotonic(self):
        sm = SourceMap("a\nbb\nccc\n")
        assert sm.line_starts == sorted(sm.line_starts)
        assert sm.line_starts[0] == 0


class TestHeredocKeySentinel:
    """Absence of a collected heredoc body is None, not a missing attribute."""

    def test_plain_token_heredoc_key_is_none(self):
        assert Token(TokenType.WORD, "x", 0, 1).heredoc_key is None
        assert Token(TokenType.HEREDOC, "<<", 0, 2).heredoc_key is None

    def test_uncollected_heredoc_body_is_scanned_not_normalized(self):
        # heredoc_key is None => the body lines are still in the token stream,
        # so the normalizer must enter heredoc mode and NOT reclassify a body
        # word that happens to spell a keyword. If a None key were wrongly read
        # as "collected", the body's `if` (after `;`) would become an IF token.
        toks = [
            Token(TokenType.HEREDOC, "<<", 0, 2),
            Token(TokenType.WORD, "EOF", 3, 6),      # delimiter
            Token(TokenType.WORD, "x", 7, 8),        # body
            Token(TokenType.SEMICOLON, ";", 8, 9),   # body
            Token(TokenType.WORD, "if", 10, 12),     # body spelling a keyword
            Token(TokenType.WORD, "EOF", 13, 16),    # closes the heredoc
        ]
        result = KeywordNormalizer().normalize(toks)
        assert result[4].type == TokenType.WORD  # 'if' stayed a body word

    def test_collected_heredoc_key_is_set_and_maps(self):
        toks, hmap = tokenize_with_heredocs("cat <<EOF\nhi\nEOF\n")
        ops = [t for t in toks
               if t.type in (TokenType.HEREDOC, TokenType.HEREDOC_STRIP)]
        assert ops and ops[0].heredoc_key is not None
        assert ops[0].heredoc_key in dict(hmap)


class TestArrayInitSentinel:
    def test_plain_token_array_init_is_none(self):
        assert Token(TokenType.WORD, "x", 0, 1).array_init is None

    def test_array_init_is_carried_when_set(self):
        marker = object()
        t = Token(TokenType.WORD, "a=(1 2)", 0, 7, array_init=marker)
        assert t.array_init is marker
