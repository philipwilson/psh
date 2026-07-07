"""Adversarial performance guards for the shell-pattern matcher.

Both legacy pattern backends are exponential on complementary adversarial
inputs (expansion appraisal finding #6):

* the **regex** path (``pattern.match_shell_pattern`` for non-negation extglob →
  Python ``re``) blows up on ambiguous repetition with a forced-fail tail,
  e.g. ``*(a|aa)c`` on ``"a"*N + "b"`` (0.06s→0.40s→2.7s at N=30/34/38);
* the **backtracking matcher** (``extglob.extglob_fullmatch``, used for negation
  and leftmost-longest substitution) blows up on sequential-optional fan-out,
  e.g. ``?(a)…?(a)!(z)`` on ``"a"*k + "b"`` (0.05s→0.21s→0.87s at k=14/16/18),
  because ``_match_from`` recomputes ``(position, subject-index)`` states.

Since the compiled memoized engine (``pattern_engine``) now backs every extglob
consumer, these are live assertions (no longer ``xfail``). The deterministic,
non-timing state-count guards in ``tests/unit/expansion/test_pattern_engine_matcher.py``
are the primary complexity guarantee; these timing guards are a coarse backstop.

Budgets are chosen with a wide margin: the former exponential backends took
hundreds of milliseconds to seconds at these sizes, the memoized engine takes
well under a millisecond, so the 0.1s budget sits unambiguously between them.
"""
import time

import pytest


def _elapsed(fn):
    start = time.perf_counter()
    fn()
    return time.perf_counter() - start


BUDGET = 0.1  # seconds; exponential backends blow past it, memoized stays << it.


@pytest.mark.timeout(30)
def test_ambiguous_repetition_not_exponential():
    """case / [[ == ]] on ``*(a|aa)c`` vs a forced-fail subject stays fast."""
    from psh.expansion.pattern import match_shell_pattern
    N = 34
    subject = "a" * N + "b"
    dt = _elapsed(lambda: match_shell_pattern(subject, "*(a|aa)c",
                                              extglob_enabled=True))
    assert dt < BUDGET, f"ambiguous repetition took {dt:.3f}s (N={N})"


@pytest.mark.timeout(30)
def test_sequential_optional_not_exponential():
    """Negation-routed matcher on ``?(a)…?(a)!(z)`` stays fast."""
    from psh.expansion.extglob import extglob_fullmatch
    k = 17
    pattern = "?(a)" * k + "!(z)"
    subject = "a" * k + "b"
    dt = _elapsed(lambda: extglob_fullmatch(pattern, subject))
    assert dt < BUDGET, f"sequential-optional matcher took {dt:.3f}s (k={k})"


@pytest.mark.timeout(30)
def test_nested_negation_not_exponential():
    """Nested negation over an ambiguous body stays fast."""
    from psh.expansion.extglob import extglob_fullmatch
    k = 17
    pattern = "!(" + "?(a)" * k + ")"
    subject = "a" * k + "b"
    dt = _elapsed(lambda: extglob_fullmatch(pattern, subject))
    assert dt < BUDGET, f"nested negation took {dt:.3f}s (k={k})"


@pytest.mark.timeout(30)
def test_long_subject_plain_glob_is_linear():
    """A plain glob against a 10k-char subject is not the pathological case.

    This is a NON-xfail sanity guard: plain globs are handled by Python ``re``
    linearly today and must stay cheap after the flip too.
    """
    from psh.expansion.pattern import match_shell_pattern
    subject = "a" * 10_000 + "b"
    dt = _elapsed(lambda: match_shell_pattern(subject, "a*b",
                                              extglob_enabled=True))
    assert dt < 0.5, f"plain glob on long subject took {dt:.3f}s"
