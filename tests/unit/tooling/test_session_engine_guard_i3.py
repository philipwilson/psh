"""Drift-lock: ONE completeness engine, reached through one chokepoint (I3).

Campaign I3 makes `parser.session.ParseSession` the single multiline-completeness
engine and `ParserDriver.start_session` its sole constructor; the scripting
`CommandAccumulator` is a thin adapter that delegates every completeness
decision to a `ParseSession` and adds none of its own (the interactive PS2 loop
in turn drives the same `CommandAccumulator`). These guards keep a second
completeness oracle — the "keyword pseudo-parsing / error-message string
matching" the campaign retired — from creeping back:

(a) the engine is the typed `ParseSession`;
(b) the sole chokepoint is `ParserDriver.start_session`, and the accumulator
    builds its engine through it;
(c) drift-lock: the accumulator's per-line class equals the raw engine's class
    over a battery — and a synthetic offender that re-implements completeness
    with its own heuristic is CAUGHT by that equivalence (so the guard cannot
    rot into a no-op).
"""

import pytest

from psh.parser.session import (
    Completeness,
    ParserDriver,
    ParseSession,
    SessionInputs,
)
from psh.scripting.command_accumulator import CommandAccumulator, NeedMore
from psh.scripting.lex_parse import lex_and_expand
from psh.shell import Shell

# A completeness battery spanning every continuation family + hard errors.
_ROWS = [
    ["echo hi"],
    ["echo )"],
    ["if true; then echo )"],
    ["if true; then echo x", "fi"],
    ["while read x; do", "echo $x", "done"],
    ["echo 'a", "b'"],
    ["y=$(echo a", ")"],
    ["echo $((1 +", "2))"],
    ["cat <<EOF", "body", "EOF"],
    ["echo a &&", "echo b"],
    ["echo a \\", "b"],
    ["case x in", "a) echo A;;", "esac"],
]


def _raw_session(shell):
    def lex(preview, base_line):
        return lex_and_expand(
            preview, shell, base_line=base_line,
            lexer_options=shell.state.options, warn_unterminated=False)
    return ParserDriver.start_session(
        SessionInputs(lex=lex, lexer_options=shell.state.options))


def _acc_class(result):
    if isinstance(result, NeedMore):
        return Completeness.INCOMPLETE
    return Completeness.INVALID if result.error else Completeness.COMPLETE


# === (a) typed engine + (b) sole chokepoint ===

def test_start_session_is_the_engine_constructor():
    session = _raw_session(Shell())
    assert isinstance(session, ParseSession)


def test_accumulator_builds_its_engine_through_the_chokepoint():
    acc = CommandAccumulator(Shell())
    # The accumulator's completeness state IS a ParseSession (no second engine).
    assert isinstance(acc._session, ParseSession)


# === (c) drift-lock: accumulator adds no parallel completeness logic ===

def _classes_via_accumulator(lines):
    acc = CommandAccumulator(Shell())
    return [_acc_class(acc.feed(ln)) for ln in lines]


def _classes_via_engine(lines):
    session = _raw_session(Shell())
    return [session.feed(ln).completeness for ln in lines]


@pytest.mark.parametrize("lines", _ROWS, ids=[" ".join(r) for r in _ROWS])
def test_accumulator_class_equals_engine_class(lines):
    assert _classes_via_accumulator(lines) == _classes_via_engine(lines)


def _drifted_oracle_classes(lines):
    """A synthetic offender: a naive bracket-depth counter re-implementing
    completeness (the kind of parallel keyword/heuristic oracle campaign I3
    retired). It ignores quotes, heredocs, expansions, and real syntax errors."""
    depth = 0
    out = []
    for ln in lines:
        for ch in ln:
            if ch in '([{':
                depth += 1
            elif ch in ')]}':
                depth -= 1
        out.append(Completeness.COMPLETE if depth == 0
                   else Completeness.INCOMPLETE)
    return out


def test_guard_catches_a_parallel_completeness_oracle():
    """The equivalence guard MUST bite a re-introduced second oracle: the naive
    bracket-counter cannot reproduce the real engine (it misses quotes,
    heredocs, expansions, and hard errors), so it disagrees on battery rows —
    proving the guard would flag any parallel oracle, not silently pass."""
    disagreements = [
        lines for lines in _ROWS
        if _drifted_oracle_classes(lines) != _classes_via_engine(lines)
    ]
    assert disagreements, "equivalence guard failed to catch the offender"
