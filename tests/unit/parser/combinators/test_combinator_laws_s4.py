"""Combinator algebra LAWS (campaign S4 §8).

The three named laws — ``optional`` preserves committed failure, ``then``/``map``
preserve failure position, ``many`` rejects success without progress — were ALL
VIOLATED on the base combinator core (demonstrated red in
``tmp/boundary-ledgers/S4-probes/law_probe_base.txt``: swallowed cut, position
reset to 0, infinite loop). These are property-style pins over representative
parser values (not single examples), plus a synthetic-offender self-test per law
that RUNS a deliberately-wrong reimplementation and shows it produces exactly the
violation the real combinator now avoids.

Grammar consequence: NONE observable in the current grammar (``committed=True``
is dormant grammar-wide, no ``many`` wraps an empty-capable parser, and the
farthest-error position only feeds diagnostics that named the same token) — the
base-vs-fixed combinator error differential is byte-identical
(``S4-probes/comb_err_{base,fixed}.txt``). The fixes are correctness repairs to
the algebra, pinned here at the property level.
"""

import pytest

from psh.parser.combinators.core import (
    ParseFailure,
    Parser,
    ParseSuccess,
    many,
    optional,
)

# --- Representative parser factories (property-style coverage) ---

def _committed_fail(reach):
    """A parser that fails COMMITTED, reaching ``pos + reach``."""
    return Parser(lambda toks, pos: ParseFailure(pos + reach, "cut", committed=True))


def _recoverable_fail(reach):
    """A parser that fails recoverably, reaching ``pos + reach``."""
    return Parser(lambda toks, pos: ParseFailure(pos + reach, "soft"))


def _succeed_at(advance):
    """A parser that succeeds, advancing the cursor by ``advance``."""
    return Parser(lambda toks, pos: ParseSuccess(("v", pos), pos + advance))


# === Law 1: optional preserves committed failure ===

@pytest.mark.parametrize("start", [0, 1, 5])
@pytest.mark.parametrize("reach", [0, 1, 3])
def test_law_optional_preserves_committed(start, reach):
    result = optional(_committed_fail(reach)).parse([], start)
    assert result.success is False
    assert result.committed is True
    assert result.position == start + reach


@pytest.mark.parametrize("start", [0, 2, 7])
def test_law_optional_recoverable_failure_becomes_absent(start):
    result = optional(_recoverable_fail(2)).parse([], start)
    assert result.success is True
    assert result.value is None
    assert result.position == start


def test_law_optional_success_passes_through():
    result = optional(_succeed_at(1)).parse([], 0)
    assert result.success is True
    assert result.position == 1


def test_law_optional_offender_swallows_committed():
    """Synthetic offender (the base behavior): swallow committed → success."""
    def buggy_optional(parser):
        def run(toks, pos):
            res = parser.parse(toks, pos)
            return res if res.success else ParseSuccess(None, pos)  # BUG: swallows cut
        return Parser(run)

    offender = buggy_optional(_committed_fail(2)).parse([], 0)
    real = optional(_committed_fail(2)).parse([], 0)
    # The offender turns the cut into a success; the real combinator keeps it.
    assert offender.success is True
    assert real.success is False and real.committed is True


# === Law 2: then / map preserve failure position ===

@pytest.mark.parametrize("start", [0, 4])
@pytest.mark.parametrize("reach", [0, 2, 5])
def test_law_map_preserves_failure_position(start, reach):
    result = _recoverable_fail(reach).map(lambda v: v).parse([], start)
    assert result.success is False
    assert result.position == start + reach


@pytest.mark.parametrize("first_adv,second_reach", [(1, 0), (2, 3), (3, 1)])
def test_law_then_preserves_second_failure_position(first_adv, second_reach):
    result = _succeed_at(first_adv).then(_recoverable_fail(second_reach)).parse([], 0)
    assert result.success is False
    # first parser advanced to first_adv; second failed reaching +second_reach.
    assert result.position == first_adv + second_reach


def test_law_then_preserves_first_failure_position():
    result = _recoverable_fail(2).then(_succeed_at(1)).parse([], 3)
    assert result.success is False
    assert result.position == 5  # 3 (start) + 2 (reach); not reset to start


def test_law_map_offender_resets_position():
    """Synthetic offender (the base behavior): reset the failure to the start."""
    def buggy_map(parser, fn):
        def run(toks, pos):
            res = parser.parse(toks, pos)
            if res.success:
                return ParseSuccess(fn(res.value), res.position)
            return ParseFailure(pos, res.error)  # BUG: discards the reach
        return Parser(run)

    offender = buggy_map(_recoverable_fail(3), lambda v: v).parse([], 0)
    real = _recoverable_fail(3).map(lambda v: v).parse([], 0)
    assert offender.position == 0     # offender lost the reach
    assert real.position == 3         # law-abiding: reach preserved


# === Law 3: many rejects success without progress ===

def test_law_many_terminates_on_zero_width_success():
    """A zero-width success must not loop forever; it ends the repetition."""
    zero_width = Parser(lambda toks, pos: ParseSuccess("x", pos))
    result = many(zero_width).parse([], 0)  # MUST return (base hangs here)
    assert result.success is True
    assert result.value == []
    assert result.position == 0


def test_law_many_collects_progressing_matches():
    def step(toks, pos):
        if pos < 3:
            return ParseSuccess(pos, pos + 1)
        return ParseFailure(pos, "end")

    result = many(Parser(step)).parse([], 0)
    assert result.value == [0, 1, 2]
    assert result.position == 3


def test_law_many_propagates_committed_failure_mid_repetition():
    """A committed failure inside the repetition is a real error, not the end."""
    calls = {"n": 0}

    def step(toks, pos):
        calls["n"] += 1
        if calls["n"] == 1:
            return ParseSuccess(pos, pos + 1)
        return ParseFailure(pos, "boom", committed=True)

    result = many(Parser(step)).parse([], 0)
    assert result.success is False
    assert result.committed is True


def test_law_many_offender_without_guard_does_not_terminate():
    """Synthetic offender (the base behavior): no progress guard → non-terminating.

    Run the guard-less loop with a hard step ceiling on a zero-width success and
    show it hits the ceiling (never breaks on its own), proving the progress
    guard is load-bearing — without actually hanging the test.
    """
    zero_width = Parser(lambda toks, pos: ParseSuccess("x", pos))

    def buggy_many_steps(parser, ceiling):
        pos, steps = 0, 0
        while steps < ceiling:
            res = parser.parse([], pos)
            if not res.success:
                break
            pos = res.position  # zero-width: never advances
            steps += 1
        return steps

    assert buggy_many_steps(zero_width, 1000) == 1000  # ceiling reached = infinite
