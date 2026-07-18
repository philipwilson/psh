"""The typed parse outcome sum ``Complete | Incomplete | Invalid`` (campaign S4).

Pins the classification (the single decision point ``outcome_from_parse``), the
``ExpectedInput`` payload that drives PS2 continuation, ``materialize`` as the
terminal raising adapter, combinator parity, and that a substitution-origin
error survives as an ``Invalid`` (the I3 producer contract).
"""

import dataclasses

import pytest

from psh.ast_nodes import Program
from psh.lexer import tokenize
from psh.parser import (
    Complete,
    ExpectedInput,
    Incomplete,
    Invalid,
    ParseError,
    Parser,
    SubstitutionSyntaxError,
    is_substitution_origin,
    materialize,
)
from psh.parser.combinators.parser import ParserCombinatorShellParser
from psh.parser.config import ParserConfig


def _rd_outcome(src):
    return Parser(list(tokenize(src)), source_text=src).parse_outcome()


def _comb_outcome(src):
    return ParserCombinatorShellParser(ParserConfig()).parse_outcome(list(tokenize(src)))


# === Classification (recursive descent) ===

def test_complete_carries_the_program():
    outcome = _rd_outcome("echo hi")
    assert isinstance(outcome, Complete)
    assert isinstance(outcome.program, Program)


def test_incomplete_on_unclosed_compound():
    outcome = _rd_outcome("if true; then echo x")
    assert isinstance(outcome, Incomplete)
    assert isinstance(outcome.expected, ExpectedInput)
    assert outcome.expected.unclosed_expansion is None
    assert "then" in outcome.expected.constructs
    assert isinstance(outcome.error, ParseError) and outcome.error.at_eof


def test_invalid_on_real_syntax_error():
    outcome = _rd_outcome("echo )")
    assert isinstance(outcome, Invalid)
    assert isinstance(outcome.error, ParseError)
    assert not outcome.error.at_eof


@pytest.mark.parametrize("src,kind", [
    ("echo $(", "command"),
    ("echo ${", "parameter"),
    ("echo $((", "arithmetic"),
    ("echo `", "backtick"),
])
def test_incomplete_reports_unclosed_expansion_kind(src, kind):
    outcome = _rd_outcome(src)
    assert isinstance(outcome, Incomplete)
    assert outcome.expected.unclosed_expansion == kind


def test_empty_input_is_complete():
    outcome = _rd_outcome("")
    assert isinstance(outcome, Complete)
    assert outcome.program.statements == []


# === ExpectedInput / open-construct trail ===

def test_expected_input_carries_nested_construct_trail():
    outcome = _rd_outcome("for i in 1 2 3; do if true; then")
    assert isinstance(outcome, Incomplete)
    # The trail reflects the still-open constructs from outer to inner: the
    # outer for-loop and the inner if retitled to 'then' once THEN was consumed.
    assert outcome.expected.constructs == ("for", "then")


# === materialize: the terminal raising adapter ===

def test_materialize_complete_returns_program():
    prog = materialize(_rd_outcome("echo hi"))
    assert isinstance(prog, Program)


def test_materialize_incomplete_raises_the_error():
    outcome = _rd_outcome("if true; then")
    with pytest.raises(ParseError) as ei:
        materialize(outcome)
    assert ei.value is outcome.error


def test_materialize_invalid_raises_the_error():
    outcome = _rd_outcome("echo )")
    with pytest.raises(ParseError) as ei:
        materialize(outcome)
    assert ei.value is outcome.error


def test_parse_equals_materialize_of_parse_outcome():
    # parse() is the terminal materialization over the same parse.
    src = "echo hi; echo there"
    prog = Parser(list(tokenize(src))).parse()
    mat = materialize(Parser(list(tokenize(src))).parse_outcome())
    assert isinstance(prog, Program) and isinstance(mat, Program)
    assert len(prog.statements) == len(mat.statements)


# === substitution-origin survives as Invalid (I3 producer contract) ===

def test_substitution_origin_error_survives_as_invalid_or_incomplete():
    # A substitution-body syntax error is tagged; whichever outcome variant it
    # lands in, the origin fact is preserved on .error for the I3 consumer.
    outcome = _rd_outcome("echo $(for)")
    err = outcome.error
    assert isinstance(err, SubstitutionSyntaxError)
    assert is_substitution_origin(err)


# === deep nesting classifies as Invalid, not Incomplete ===

def test_deeply_nested_closed_input_is_invalid():
    # Spaced parens so they stay nested subshells (unspaced `((` is arithmetic).
    # A bare Parser under Python's default recursion limit converts the
    # RecursionError into a clean ParseError — Invalid, never Incomplete.
    src = "( " * 1200 + " echo x " + " )" * 1200
    outcome = _rd_outcome(src)
    assert isinstance(outcome, Invalid)
    assert not outcome.error.at_eof


# === combinator parity ===

def test_combinator_parse_outcome_complete():
    assert isinstance(_comb_outcome("echo hi"), Complete)


def test_combinator_parse_outcome_invalid():
    assert isinstance(_comb_outcome("echo )"), Invalid)


def test_combinator_parse_outcome_incomplete_at_eof():
    # The combinator raises on an EOF token, which classifies as Incomplete via
    # ParseError.at_eof (it does not compute an open-construct trail).
    outcome = _comb_outcome("if")
    assert isinstance(outcome, Incomplete)
    assert outcome.expected.constructs == ()


# === the variants are frozen typed values ===

@pytest.mark.parametrize("outcome,attr", [
    (Complete(Program()), "program"),
    (Incomplete(ExpectedInput(), None), "error"),
    (Invalid(None), "error"),
])
def test_outcome_variants_are_frozen(outcome, attr):
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(outcome, attr, "mutated")
