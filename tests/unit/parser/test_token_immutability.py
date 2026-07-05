"""The parser must not mutate caller-owned lexer tokens (finding 14).

create_context() copies the token LIST but not the token OBJECTS, so the old
post-pipe TIME demotion (`tok.type = WORD`) was visible to the caller and to
any other parser implementation reusing the same stream. Both the
recursive-descent and combinator parsers now substitute a WORD copy locally
instead of writing to the token, so parse execution is observationally pure
w.r.t. its token input.

These snapshot every field of every token before and after parsing with BOTH
parsers and assert nothing changed, and pin the preserved runtime meaning of a
post-pipe `time` (an ordinary command word, e.g. external /usr/bin/time).
"""

import dataclasses

import pytest

from psh.lexer import tokenize
from psh.lexer.token_types import TokenType
from psh.parser import Parser
from psh.parser.combinators.parser import ParserCombinatorShellParser
from psh.parser.config import ParserConfig

# Inputs exercising both TIME positions (leading reserved word, and post-pipe
# where bash runs the external `time`) plus ordinary/compound commands.
CASES = [
    "echo a | time cat",
    "time cat",
    "time ls | wc -l",
    "echo a | time -p cat",
    "a | b | time c",
    "echo hi",
    "if true; then echo x; fi",
    "for ((i=0; i<2; i++)); do echo $i; done",
]


def _snapshot(tokens):
    """Deep field-by-field snapshot of every token."""
    return [dataclasses.astuple(t) for t in tokens]


@pytest.mark.parametrize("src", CASES)
def test_rd_parser_does_not_mutate_tokens(src):
    tokens = tokenize(src)
    before = _snapshot(tokens)
    Parser(list(tokens)).parse()
    assert _snapshot(tokens) == before


@pytest.mark.parametrize("src", CASES)
def test_combinator_parser_does_not_mutate_tokens(src):
    tokens = tokenize(src)
    before = _snapshot(tokens)
    ParserCombinatorShellParser(ParserConfig()).parse(list(tokens))
    assert _snapshot(tokens) == before


def test_post_pipe_time_token_stays_time_in_input():
    """The TIME token in `echo a | time cat` is unchanged in the caller's
    stream, but the parsed command still treats `time` as its command word."""
    tokens = tokenize("echo a | time cat")
    time_tok = next(t for t in tokens if t.type == TokenType.TIME)
    prog = Parser(list(tokens)).parse()
    # Caller's token is untouched.
    assert time_tok.type == TokenType.TIME
    # The pipeline is NOT timed (post-pipe `time` is a plain word, not the
    # pipeline timer), and its second stage is the ordinary command `time cat`.
    pipeline = prog.statements[0].pipelines[0]
    assert not pipeline.timed
    second = pipeline.commands[1]
    assert [p.parts[0].text for p in second.words] == ["time", "cat"]
