"""ParseInputs / ParserState split (campaign S4 §8).

Pins the typed separation of immutable caller context (frozen ``ParseInputs``)
from mutable per-call state (``ParserState``), the delegating accessor surface on
``ParserContext``, and the RD ``Parser`` SINGLE-USE contract (remediation
MEDIUM-11): the cursor is bound at construction and consumed by the first
``parse()``, so a second ``parse()``/``parse_outcome()`` raises rather than
silently returning an empty ``Program``.
"""

import dataclasses

import pytest

from psh.lexer import tokenize
from psh.parser import ParseInputs, Parser, ParserState
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


# === RD Parser is SINGLE-USE (remediation MEDIUM-11) ===
#
# Red-on-base: at db6dfb13 a second `.parse()` on one instance returned an EMPTY
# Program (the cursor is consumed by the first parse and never reset) — a silent
# wrong. The contract now raises a loud programming-error instead. The error is
# a plain RuntimeError (an INTERNAL-DEFECT class under strict-errors), DISTINCT
# from the user-facing ParseError (a PshError). The combinator stays reusable.

def test_second_parse_raises_single_use_error():
    p = Parser(list(tokenize("echo hi")))
    first = p.parse()
    assert len(first.statements) == 1          # first parse is normal
    with pytest.raises(RuntimeError, match="single-use"):
        p.parse()                              # was: empty Program, now raises


def test_single_use_error_is_not_a_parse_error():
    # It must NOT be a ParseError/PshError (those are swallowed to exit 1 /
    # pass through strict-errors); a reuse is an internal defect, so it is a
    # bare RuntimeError that strict-errors re-raises loudly.
    from psh.core.exceptions import PshError
    from psh.parser import ParseError
    p = Parser(list(tokenize("echo hi")))
    p.parse()
    with pytest.raises(RuntimeError) as excinfo:
        p.parse()
    assert not isinstance(excinfo.value, ParseError)
    assert not isinstance(excinfo.value, PshError)


def test_parse_outcome_shares_the_single_use_budget():
    # parse_outcome() routes through parse() once, so it consumes the single use:
    # a subsequent parse() OR parse_outcome() on the same instance raises.
    p = Parser(list(tokenize("echo hi")))
    from psh.parser import Complete
    assert isinstance(p.parse_outcome(), Complete)
    with pytest.raises(RuntimeError, match="single-use"):
        p.parse()

    q = Parser(list(tokenize("echo hi")))
    q.parse_outcome()
    with pytest.raises(RuntimeError, match="single-use"):
        q.parse_outcome()                      # RuntimeError propagates uncaught


def test_failed_parse_still_consumes_the_single_use():
    # A parse that RAISED still counts as used — the cursor is left mid-stream,
    # so re-parsing would resume from a broken position.
    from psh.parser import ParseError
    p = Parser(list(tokenize("if")))
    with pytest.raises(ParseError):
        p.parse()
    with pytest.raises(RuntimeError, match="single-use"):
        p.parse()


def test_fresh_parser_over_same_tokens_parses_again():
    # Single-use is per INSTANCE: a new Parser over the same source parses fine.
    toks = list(tokenize("echo hi"))
    assert len(Parser(list(toks)).parse().statements) == 1
    assert len(Parser(list(toks)).parse().statements) == 1


# === token subject stays a mutable list (the `time`-slot rewrite) ===

def test_tokens_is_a_mutable_list_not_in_frozen_inputs():
    ctx = _ctx("echo a | time cat")
    assert isinstance(ctx.tokens, list)
    # The parser rewrites a non-leading `time` slot in place; that requires a
    # mutable list. Prove the slot is assignable (observationally-pure copy).
    original = ctx.tokens[0]
    ctx.tokens[0] = original   # no error: it is a real list slot
    assert ctx.tokens[0] is original
