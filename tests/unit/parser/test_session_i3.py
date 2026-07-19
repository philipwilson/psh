"""The incremental completeness engine's contract (campaign I3).

`ParserDriver.start_session(inputs)` returns a `ParseSession` whose `feed(line)`
returns the typed `Completeness` classification — the same `Complete |
Incomplete | Invalid` trichotomy one-shot `parse_outcome()` gives — plus the
gathering payload. These pins cover: the outcome-sum mapping, the bash-faithful
IMMEDIATE mid-construct error (not deferred to structural close), that the
scripting adapter is a pure pass-through of the engine, and that the engine's
completeness CLASS is identical whichever parser is active (the session trials
with recursive descent regardless — the combinator does not compute the
open-construct trail the PS2 prompt needs).
"""

import pytest

from psh.lexer import tokenize
from psh.parser import Parser
from psh.parser.parse_outcome import Complete as OutcomeComplete
from psh.parser.parse_outcome import Invalid as OutcomeInvalid
from psh.parser.session import (
    Completeness,
    ContinuationReason,
    ParserDriver,
    ParseSession,
    SessionInputs,
)
from psh.scripting.command_accumulator import CommandAccumulator, NeedMore
from psh.scripting.lex_parse import lex_and_expand
from psh.shell import Shell


def _make_session(shell):
    def lex(preview, base_line):
        return lex_and_expand(
            preview, shell, base_line=base_line,
            lexer_options=shell.state.options, warn_unterminated=False)
    return ParserDriver.start_session(
        SessionInputs(lex=lex, lexer_options=shell.state.options))


def _feed_all(shell, lines):
    s = _make_session(shell)
    return [s.feed(ln) for ln in lines]


# === start_session returns the engine ===

def test_start_session_returns_a_parse_session():
    s = _make_session(Shell())
    assert isinstance(s, ParseSession)
    assert s.is_empty


# === the three completeness classes ===

def test_complete_command_classifies_complete_with_reusable_parse():
    step = _feed_all(Shell(), ["echo hi"])[-1]
    assert step.completeness is Completeness.COMPLETE
    assert step.error is None
    assert step.program is not None and step.tokens is not None
    assert step.text == "echo hi"


def test_open_compound_classifies_incomplete_with_trail():
    steps = _feed_all(Shell(), ["if true; then echo x"])
    assert steps[-1].completeness is Completeness.INCOMPLETE
    hint = steps[-1].hint
    assert hint.reason is ContinuationReason.INCOMPLETE_STRUCTURE
    assert "then" in hint.constructs


def test_unclosed_expansion_classifies_incomplete_with_kind():
    step = _feed_all(Shell(), ["echo $((1 +"])[-1]
    assert step.completeness is Completeness.INCOMPLETE
    assert step.hint.reason is ContinuationReason.UNCLOSED_EXPANSION
    assert step.hint.detail == "arithmetic"


def test_unclosed_quote_classifies_incomplete():
    step = _feed_all(Shell(), ["echo 'a"])[-1]
    assert step.completeness is Completeness.INCOMPLETE
    assert step.hint.reason is ContinuationReason.UNCLOSED_QUOTE
    assert step.hint.detail == "'"


def test_real_syntax_error_classifies_invalid():
    step = _feed_all(Shell(), ["echo )"])[-1]
    assert step.completeness is Completeness.INVALID
    assert step.error is not None


# === the engine's class matches one-shot parse_outcome (the contract) ===

@pytest.mark.parametrize("buf,one_shot", [
    ("echo hi", OutcomeComplete),
    ("echo a; echo b", OutcomeComplete),
    ("echo )", OutcomeInvalid),
    ("if true; then echo x; fi", OutcomeComplete),
])
def test_session_class_matches_one_shot_outcome(buf, one_shot):
    # A single-line complete/invalid buffer: the session's class equals the
    # one-shot parse_outcome class (the "same outcome sum" contract).
    step = _feed_all(Shell(), [buf])[-1]
    outcome = Parser(list(tokenize(buf)), source_text=buf).parse_outcome()
    assert isinstance(outcome, one_shot)
    if one_shot is OutcomeComplete:
        assert step.completeness is Completeness.COMPLETE
    else:
        assert step.completeness is Completeness.INVALID


# === bash-faithful IMMEDIATE mid-construct error (not deferred) ===

def test_mid_construct_error_is_invalid_at_the_offending_line():
    """`if true; then echo )` — the `)` is a hard error reported on line 0, NOT
    deferred until `fi`. bash does the same (PTY-proven, see the immediate-error
    conformance test); the engine must not swallow it into INCOMPLETE."""
    step = _feed_all(Shell(), ["if true; then echo )"])[0]
    assert step.completeness is Completeness.INVALID


def test_mid_construct_error_after_continuation_is_immediate():
    """`if true; then` (INCOMPLETE) then a bare `)` — the hard error fires on the
    SECOND line, still inside the open `if`, not deferred to `fi`. bash errors on
    the same line (PTY-proven). (A trailing OPERATOR awaiting an operand — `echo
    <`, `echo a &&` — is at_eof/INCOMPLETE instead, a separate pre-existing
    redirect/operator-at-EOF behavior, not covered by this immediate-error pin.)"""
    steps = _feed_all(Shell(), ["if true; then", ")"])
    assert steps[0].completeness is Completeness.INCOMPLETE
    assert steps[1].completeness is Completeness.INVALID


# === the scripting adapter is a pure pass-through of the engine ===

_ROWS = [
    ["echo hi"],
    ["echo )"],
    ["if true; then echo )"],
    ["if true; then echo x", "fi"],
    ["echo 'a", "b'"],
    ["y=$(echo a", ")"],
    ["echo $((1 +", "2))"],
    ["while read x; do", "echo $x", "done"],
    ["cat <<EOF", "body", "EOF"],
    ["echo a &&", "echo b"],
    ["echo a \\", "b"],
]


def _class_of(result):
    if isinstance(result, NeedMore):
        return "INCOMPLETE"
    return "INVALID" if result.error else "COMPLETE"


@pytest.mark.parametrize("lines", _ROWS, ids=[" ".join(r) for r in _ROWS])
def test_accumulator_is_pure_engine_passthrough(lines):
    """The scripting CommandAccumulator adds no completeness logic of its own:
    its per-line class equals the engine's SessionStep class."""
    acc = CommandAccumulator(Shell())
    engine = _make_session(Shell())
    for ln in lines:
        acc_cls = _class_of(acc.feed(ln))
        step = engine.feed(ln)
        eng_cls = step.completeness.name
        assert acc_cls == eng_cls, f"adapter {acc_cls} != engine {eng_cls} on {ln!r}"


# === both-parser session contract: class is identical whichever is active ===

@pytest.mark.parametrize("lines", _ROWS, ids=[" ".join(r) for r in _ROWS])
def test_session_class_parity_across_active_parser(lines):
    """The engine trials with recursive descent REGARDLESS of the active parser
    (only RD computes the open-construct trail), so the completeness CLASS is
    identical under recursive_descent and combinator. Post work-item-1 the
    combinator's own parse_outcome is class-parity with RD, so nothing about
    switching the active parser can change gathering completeness."""
    def drive(parser):
        sh = Shell()
        sh.active_parser = parser
        acc = CommandAccumulator(sh)
        return tuple(_class_of(acc.feed(ln)) for ln in lines)
    assert drive("recursive_descent") == drive("combinator")
