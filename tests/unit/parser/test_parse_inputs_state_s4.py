"""ParseInputs / ParserState split (campaign S4 §8).

Pins the typed separation of immutable caller context (frozen ``ParseInputs``)
from mutable per-call state (``ParserState``), the delegating accessor surface on
``ParserContext``, and the "a parser instance retains no per-call state after
return" invariant.
"""

import dataclasses

import pytest

from psh.lexer import tokenize
from psh.parser import ParseInputs, ParserState, Parser
from psh.parser.config import ParserConfig
from psh.parser.recursive_descent.context import ParserContext


def _ctx(src):
    return ParserContext(tokens=list(tokenize(src)), source_text=src)


# === ParseInputs is the frozen immutable caller context ===

def test_parse_inputs_is_frozen():
    inputs = ParseInputs(source_text="x", line_offset=2)
    with pytest.raises(dataclasses.FrozenInstanceError):
        inputs.line_offset = 9
    with pytest.raises(dataclasses.FrozenInstanceError):
        inputs.source_text = "y"


def test_parse_inputs_carries_the_caller_context():
    opts = {"extglob": True}
    inputs = ParseInputs(source_text="echo", line_offset=3, lexer_options=opts,
                         heredocs={}, config=ParserConfig())
    assert inputs.source_text == "echo"
    assert inputs.line_offset == 3
    assert inputs.lexer_options is opts
    assert inputs.heredocs == {}
    assert isinstance(inputs.config, ParserConfig)


def test_parse_inputs_has_no_tokens_field():
    # The token stream is the parse SUBJECT (owned mutably by ParserContext),
    # not part of the immutable caller context — the §8 signature confirms it.
    names = {f.name for f in dataclasses.fields(ParseInputs)}
    assert "tokens" not in names
    assert names == {"source_text", "line_offset", "lexer_options",
                     "heredocs", "config"}


# === ParserState is the mutable per-call state ===

def test_parser_state_defaults_and_mutability():
    state = ParserState()
    assert state.cursor == 0
    assert state.nesting_depth == 0
    assert state.substitution_depth == 0
    assert state.open_constructs == []
    state.cursor = 5
    state.nesting_depth = 2
    state.open_constructs.append("if")
    assert (state.cursor, state.nesting_depth, state.open_constructs) == (5, 2, ["if"])


def test_parser_state_fields_are_exactly_the_four_per_call_facts():
    names = {f.name for f in dataclasses.fields(ParserState)}
    assert names == {"cursor", "nesting_depth", "substitution_depth", "open_constructs"}


# === ParserContext composes inputs + state + the token subject ===

def test_context_composes_inputs_and_state():
    ctx = _ctx("echo hi")
    assert isinstance(ctx.inputs, ParseInputs)
    assert isinstance(ctx.state, ParserState)
    assert isinstance(ctx.tokens, list)   # the mutable parse subject


def test_context_delegates_immutable_reads_to_inputs():
    opts = {"extglob": False}
    ctx = ParserContext(tokens=list(tokenize("echo")), source_text="echo",
                        line_offset=4, lexer_options=opts)
    assert ctx.source_text == ctx.inputs.source_text == "echo"
    assert ctx.line_offset == ctx.inputs.line_offset == 4
    assert ctx.lexer_options is ctx.inputs.lexer_options is opts


def test_context_current_is_the_state_cursor_both_directions():
    ctx = _ctx("echo a b")
    assert ctx.current == ctx.state.cursor == 0
    ctx.current = 3
    assert ctx.state.cursor == 3
    ctx.state.cursor = 1
    assert ctx.current == 1


def test_context_depth_props_are_the_state_counters():
    ctx = _ctx("echo")
    ctx.nesting_depth += 2
    ctx.substitution_depth += 1
    assert ctx.state.nesting_depth == 2
    assert ctx.state.substitution_depth == 1


def test_context_open_constructs_trail_lives_in_state():
    ctx = _ctx("echo")
    ctx.push_construct("if")
    ctx.retitle_construct("then")
    assert ctx.state.open_constructs == ["then"]
    assert ctx.open_constructs is ctx.state.open_constructs
    ctx.pop_construct()
    assert ctx.state.open_constructs == []


# === "retains no per-call state after return" ===

def test_two_parsers_have_independent_state():
    p1 = Parser(list(tokenize("if true; then echo 1; fi")))
    p2 = Parser(list(tokenize("echo 2")))
    p1.parse()
    # p2's cursor/open trail are untouched by p1's parse (separate ParserState).
    assert p2.ctx.state.cursor == 0
    assert p2.ctx.state.open_constructs == []
    p2.parse()
    assert p2.ctx.at_end()


def test_fresh_parser_starts_from_a_fresh_state():
    src = "for i in 1 2 3; do echo $i; done"
    a = Parser(list(tokenize(src)))
    assert a.ctx.state.cursor == 0 and a.ctx.state.open_constructs == []
    a.parse()
    # A brand-new parser over the same source also starts fresh — nothing is
    # shared between parser instances.
    b = Parser(list(tokenize(src)))
    assert b.ctx.state.cursor == 0 and b.ctx.state.open_constructs == []


def test_open_constructs_balanced_to_empty_on_success():
    p = Parser(list(tokenize("if true; then echo x; fi")))
    p.parse()
    assert p.ctx.state.open_constructs == []


# === token subject stays a mutable list (the `time`-slot rewrite) ===

def test_tokens_is_a_mutable_list_not_in_frozen_inputs():
    ctx = _ctx("echo a | time cat")
    assert isinstance(ctx.tokens, list)
    # The parser rewrites a non-leading `time` slot in place; that requires a
    # mutable list. Prove the slot is assignable (observationally-pure copy).
    original = ctx.tokens[0]
    ctx.tokens[0] = original   # no error: it is a real list slot
    assert ctx.tokens[0] is original
