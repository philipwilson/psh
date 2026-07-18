"""S1 invariants: the complete lexical word exists before keyword classification.

The §5 `LexicalWord` contract is realized as invariants over the fused WORD
token (campaign S1 design declaration): typed `parts` with per-part protection
(quote_type: None=unquoted, `'`, `"`, `$'`; escapes stay as backslash sequences
in unquoted literal text), and an exact source span (`value` round-trips
`source[position:end_position]`). Classification (`KeywordNormalizer`) runs on
COMPLETE words only and promotes a reserved word only when the word is an
exact unquoted literal.

These are token-level pins; the behavioral (bash-compared) rows live in
`tests/conformance/bash/test_keyword_word_boundary_conformance.py` and the
ordering pin in `test_post_lex_fusion_order_b3.py`.
"""

from dataclasses import replace

from psh.lexer import tokenize
from psh.lexer.keyword_normalizer import KeywordNormalizer
from psh.lexer.token_parts import TokenPart
from psh.lexer.token_types import Token, TokenType, token_lexeme


def _first(src):
    return tokenize(src)[0]


class TestSpanIntegrity:
    """Fused words carry the exact source span; fusion loses no span facts."""

    def test_fused_value_round_trips_source(self):
        cases = [
            'then$x', 'then${x}echo', 'then""', "do''", 'a"b"c',
            'if$x', 'fi$x', 'in$x', '"i"f', "i'n'", 'x$(echo y)z',
            "then$'q'", 'case$x',
        ]
        for src in cases:
            tok = _first(src)
            assert tok.type == TokenType.WORD, (src, tok.type)
            assert src[tok.position:tok.end_position] == tok.value == src, src

    def test_fused_word_mid_stream_span(self):
        src = 'if true; then$x echo hi; fi'
        tok = next(t for t in tokenize(src) if t.value == 'then$x')
        assert src[tok.position:tok.end_position] == 'then$x'
        assert (tok.position, tok.end_position) == (9, 15)


class TestProtectionRuns:
    """Per-part protection (quote context) survives fusion."""

    def test_glued_quote_parts_keep_quote_type(self):
        tok = _first('then"q"')
        assert tok.type == TokenType.WORD
        assert [(p.value, p.quote_type) for p in tok.parts] == [
            ('then', None), ('q', '"')]

    def test_glued_single_and_ansi_c_parts(self):
        tok = _first("then'q'")
        assert [(p.value, p.quote_type) for p in tok.parts] == [
            ('then', None), ('q', "'")]
        tok = _first("then$'q'")
        assert [(p.value, p.quote_type) for p in tok.parts] == [
            ('then', None), ('q', "$'")]

    def test_escape_stays_in_unquoted_literal_run(self):
        # ESCAPED protection is the backslash kept in the unquoted literal
        # text (consumed later by quote removal): the token spells the source.
        tok = _first(r'\if')
        assert (tok.type, tok.value) == (TokenType.WORD, r'\if')
        tok = _first('i\\f')
        assert (tok.type, tok.value) == (TokenType.WORD, 'i\\f')

    def test_expansion_part_typed(self):
        tok = _first('then$x')
        kinds = [(p.value, bool(p.is_expansion)) for p in tok.parts]
        assert kinds == [('then', False), ('x', True)]


class TestCompleteWordEligibility:
    """Reserved words: only a complete, unquoted, exact literal is promoted."""

    def test_exact_unquoted_literals_promoted(self):
        assert _first('then').type == TokenType.THEN
        assert _first('in').type == TokenType.IN
        assert _first('if').type == TokenType.IF

    def test_quoted_spellings_never_promoted(self):
        for src in ('"if"', "'if'", "$'if'", '"in"', "'then'"):
            tok = _first(src)
            assert tok.type == TokenType.STRING, (src, tok.type)
            assert not tok.is_keyword

    def test_composite_spellings_never_promoted(self):
        for src in ('then$x', 'then""', '"i"f', 'in$x', 'fi$x'):
            tok = _first(src)
            assert tok.type == TokenType.WORD, (src, tok.type)
            assert not tok.is_keyword

    def test_synthetic_composite_word_not_promoted(self):
        # Defense-in-depth: even a WORD whose VALUE spells a keyword exactly
        # is not promoted when it carries parts (a composite word) or a
        # quote_type — the eligibility gate reads the word's completeness
        # facts, not just its spelling. (No real lexer output produces these
        # shapes; this is the synthetic-offender guard for the gate.)
        base = _first('then')
        assert base.type == TokenType.THEN  # sanity: promotable spelling
        composite = Token(
            type=TokenType.WORD, value='then', position=0, end_position=4,
            parts=[TokenPart(value='th'), TokenPart(value='en')])
        out = KeywordNormalizer().normalize([composite])
        assert out[0].type == TokenType.WORD and not out[0].is_keyword

        quoted = Token(type=TokenType.WORD, value='then', position=0,
                       end_position=6, quote_type='"')
        out = KeywordNormalizer().normalize([quoted])
        assert out[0].type == TokenType.WORD and not out[0].is_keyword

    def test_normalize_idempotent_on_fused_streams(self):
        for src in ('if true; then$x echo hi; fi',
                    'case in in (in) echo y;; esac',
                    'for in in a b; do echo $in; done',
                    'in', 'true; in'):
            once = tokenize(src)  # fuse + normalize
            twice = KeywordNormalizer().normalize(once)
            assert [(t.type, t.value) for t in twice] == \
                [(t.type, t.value) for t in once], src


class TestBareInClassification:
    """`in` is the reserved word at command position; exceptions preserved."""

    def test_bare_in_typed_in(self):
        for src, idx in (('in', 0), ('true; in', 2), ('{ in; }', 1)):
            tok = tokenize(src)[idx]
            assert (tok.type, tok.value) == (TokenType.IN, 'in'), src

    def test_subject_exceptions_stay_words(self):
        toks = tokenize('for in in a b; do echo $in; done')
        in_types = [t.type for t in toks
                    if t.value == 'in' and t.type != TokenType.VARIABLE]
        assert in_types == [TokenType.WORD, TokenType.IN]
        toks = tokenize('case in in in) echo y;; esac')
        in_types = [t.type for t in toks if t.value == 'in']
        # subject WORD, header IN, pattern WORD (pattern-after-in is not
        # command position)
        assert in_types == [TokenType.WORD, TokenType.IN, TokenType.WORD]

    def test_paren_pattern_in_typed_but_accepted_shape(self):
        toks = tokenize('case in in (in) echo y;; esac')
        in_types = [t.type for t in toks if t.value == 'in']
        # subject WORD, header IN, parenthesized pattern arrives keyword-typed
        # (both parsers' case-pattern sites accept keyword-typed tokens)
        assert in_types == [TokenType.WORD, TokenType.IN, TokenType.IN]

    def test_redirection_prefix_loses_command_start(self):
        toks = tokenize('>/dev/null in')
        tok = next(t for t in toks if t.value == 'in')
        assert tok.type == TokenType.WORD


class TestTokenLexeme:
    """token_lexeme reproduces the exact source spelling."""

    def test_span_slice_authoritative(self):
        src = 'for "in" in a; do :; done'
        tok = tokenize(src)[1]
        assert tok.type == TokenType.STRING
        assert token_lexeme(tok, src) == '"in"'

    def test_reconstruction_without_source(self):
        src = 'for "in" in a; do :; done'
        tok = tokenize(src)[1]
        assert token_lexeme(tok) == '"in"'
        vtok = tokenize('for $v in a; do :; done')[1]
        assert token_lexeme(vtok) == '$v'
        ansi = tokenize("$'if'")[0]
        assert token_lexeme(ansi) == "$'if'"
        # synthetic: value-carrying types return value verbatim
        word = replace(tokenize('plain')[0])
        assert token_lexeme(word) == 'plain'
