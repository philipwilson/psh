"""C1 pins for the word-fusion helper (lexer/word_fusion.py).

These lock the equivalence the fused-word design rests on: mapping the parts
produced by ``sub_token_to_parts`` through ``WordBuilder.token_part_to_word_part``
must build the SAME Word AST that the parser's ``build_composite_word`` builds
from the un-fused adjacent tokens. If this holds per token kind, it holds for
any run (both sides process each token independently and concatenate).

The helper is not yet wired into the lexer at this step (fusion lands in a
later commit); these tests exercise it directly against the current token
stream so the equivalence is proven before any behavior moves.
"""

import pytest

from psh.ast_nodes import Word
from psh.lexer import tokenize
from psh.lexer.token_types import TokenType
from psh.lexer.word_fusion import WORD_LIKE_TYPES, sub_token_to_parts
from psh.parser.recursive_descent.support.word_builder import WordBuilder


def _first_word_run(src):
    """The first maximal run of adjacent word-like tokens in ``src``."""
    toks = [t for t in tokenize(src) if t.type != TokenType.EOF]
    run = []
    for t in toks:
        if not run:
            if t.type in WORD_LIKE_TYPES:
                run = [t]
            continue
        if t.type in WORD_LIKE_TYPES and t.adjacent_to_previous:
            run.append(t)
        else:
            break
    return run


def _fused_word(run):
    """Word built the fused way: concat sub_token_to_parts, then map."""
    parts = [p for tok in run for p in sub_token_to_parts(tok)]
    containing = run[0]  # line 1 for single-line inputs -> stable nested-parse offset
    return Word(parts=[WordBuilder.token_part_to_word_part(p, containing, None)
                       for p in parts])


# Single-line inputs whose leading word is a multi-token composite spanning
# every word-like flavor. Kept single-line so nested-substitution line offsets
# are identical on both sides of the equivalence.
EQUIVALENCE_CASES = [
    'pre$var',                 # literal + simple variable
    'pre$var"post"',           # literal + variable + double-quoted literal
    "pre'lit'post",            # literal + single-quoted + literal
    "pre$'x'post",             # literal + ANSI-C + literal
    'pre"a$x b"post',          # literal + double-quoted-with-expansion + literal
    'pre$(cmd)',               # literal + command substitution
    'pre`cmd`',                # literal + backtick
    'pre$((1+2))',             # literal + arithmetic
    'pre<(cmd)',               # literal + process substitution (in)
    'pre>(cmd)',               # literal + process substitution (out)
    '$x$y',                    # variable + variable
    'a=b=c',                   # operator-debris WORD + WORD
    'vars+=',                  # operator-debris WORD + WORD
    '${v}post',                # braced variable + literal
    '${v:-d}post',             # braced parameter-expansion + literal
    'pre""post',               # literal + EMPTY quoted string + literal
    'a$x"b"$(c)d',             # 5-way mixed run
    '[ab]',                    # bracket word (LBRACKET/WORD/RBRACKET)
]


@pytest.mark.parametrize('src', EQUIVALENCE_CASES)
def test_fusion_maps_to_same_word_ast_as_build_composite_word(src):
    run = _first_word_run(src)
    assert len(run) >= 2, f"{src!r} did not tokenize to a multi-token run: {run}"
    expected = WordBuilder.build_composite_word(run, ctx=None)
    got = _fused_word(run)
    assert repr(got) == repr(expected), (
        f"{src!r}\n  expected: {expected!r}\n  got:      {got!r}")


def test_single_token_word_equivalence():
    """A run of one word-like token maps identically too (build_word_from_token)."""
    for src in ['plain', '"dq"', "'sq'", '$var', '${var}', '$(cmd)',
                '$((1))', '`cmd`', '<(cmd)']:
        run = _first_word_run(src)
        assert len(run) == 1, f"{src!r} -> {run}"
        tok = run[0]
        qt = tok.quote_type if tok.type == TokenType.STRING else None
        expected = WordBuilder.build_word_from_token(tok, qt, ctx=None)
        got = _fused_word(run)  # 1-token run: concat of one sub_token_to_parts
        assert repr(got) == repr(expected), (
            f"{src!r}\n  expected: {expected!r}\n  got: {got!r}")


def test_unclosed_marker_survives_fusion():
    """EOF-truncated expansions keep their ``*_unclosed`` part after fusion."""
    for src, marker in [('pre$(', 'command_unclosed'),
                        ('pre${', 'parameter_unclosed'),
                        ('pre$((', 'arithmetic_unclosed')]:
        run = _first_word_run(src)
        parts = [p for tok in run for p in sub_token_to_parts(tok)]
        etypes = [p.expansion_type for p in parts]
        assert marker in etypes, f"{src!r}: {etypes}"


def test_word_like_types_matches_legacy_peek_set():
    """The canonical set == the old peek_composite_sequence set minus the
    emit-dead PARAM_EXPANSION (guards against silent membership drift)."""
    legacy = {
        TokenType.WORD, TokenType.STRING, TokenType.VARIABLE,
        TokenType.COMMAND_SUB, TokenType.COMMAND_SUB_BACKTICK,
        TokenType.ARITH_EXPANSION, TokenType.PARAM_EXPANSION,
        TokenType.PROCESS_SUB_IN, TokenType.PROCESS_SUB_OUT,
        TokenType.LBRACKET, TokenType.RBRACKET,
    }
    assert WORD_LIKE_TYPES == legacy - {TokenType.PARAM_EXPANSION}
