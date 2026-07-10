"""C1 pins for the word-fusion helper (lexer/word_fusion.py).

These lock the equivalence the fused-word design rests on: mapping the parts
``sub_token_to_parts`` produces (through ``WordBuilder.token_part_to_word_part``)
must build the SAME Word AST the live parser builds for the same input. The
oracle is the parser's own output — an independent path from the manual mapping
under test.
"""

import pytest
from lexer_test_helpers import tokenize_unfused

from psh.ast_nodes import Word
from psh.lexer import tokenize
from psh.lexer.token_types import TokenType
from psh.lexer.word_fusion import WORD_LIKE_TYPES, sub_token_to_parts
from psh.parser import parse
from psh.parser.recursive_descent.support.word_builder import WordBuilder


def _first_word_run(src):
    """The first maximal run of adjacent word-like tokens in the PRE-fusion
    stream (the public ``tokenize`` now fuses the run into one token)."""
    toks = [t for t in tokenize_unfused(src) if t.type != TokenType.EOF]
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


def _parser_first_word(src):
    """Oracle: the Word the live parser builds for ``src`` as the sole argument
    of ``:`` (the whole input is then one shell word to compare against)."""
    ast = parse(tokenize(f': {src}'))
    cmd = ast.statements[0].pipelines[0].commands[0]
    return cmd.words[1]


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
]


@pytest.mark.parametrize('src', EQUIVALENCE_CASES)
def test_fusion_maps_to_same_word_ast_as_parser(src):
    run = _first_word_run(src)
    assert len(run) >= 2, f"{src!r} did not tokenize to a multi-token run: {run}"
    expected = _parser_first_word(src)
    got = _fused_word(run)
    assert repr(got) == repr(expected), (
        f"{src!r}\n  expected: {expected!r}\n  got:      {got!r}")


def test_single_token_word_equivalence():
    """A run of one word-like token maps identically too."""
    for src in ['plain', '"dq"', "'sq'", '$var', '${var}', '$(cmd)',
                '$((1))', '`cmd`', '<(cmd)']:
        run = _first_word_run(src)
        assert len(run) == 1, f"{src!r} -> {run}"
        expected = _parser_first_word(src)
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


def test_word_like_types_membership():
    """Pin the canonical fusion set (guards against silent membership drift).
    It is the old peek_composite_sequence set minus the retired PARAM_EXPANSION."""
    assert WORD_LIKE_TYPES == {
        TokenType.WORD, TokenType.STRING, TokenType.VARIABLE,
        TokenType.COMMAND_SUB, TokenType.COMMAND_SUB_BACKTICK,
        TokenType.ARITH_EXPANSION,
        TokenType.PROCESS_SUB_IN, TokenType.PROCESS_SUB_OUT,
        TokenType.LBRACKET, TokenType.RBRACKET,
    }
