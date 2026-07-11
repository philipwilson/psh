"""Property + unit tests for the memoized pattern matcher.

The strongest guarantee is set-level: ``reachable_ends(compile(p), s)`` must
equal the legacy backtracking matcher's ``extglob._extglob_consume(p, s)`` for
every (pattern, subject). Because ALL consumers (full match, prefix/suffix
removal, leftmost-longest substitution) are derived from that reachable-end set,
set equality proves consumer equivalence for the matcher path. We generate
thousands of random patterns/subjects with FIXED seeds so the corpus is
reproducible, and separately check the new full-match against the legacy REGEX
backend on negation-free patterns (surfacing any pre-existing inconsistency
between the two old backends before the flip).
"""
import random
import re

import pytest

from psh.expansion.extglob import (
    _contains_negation,
    _extglob_consume,
    contains_extglob,
    extglob_fullmatch,
    extglob_to_regex,
)
from psh.expansion.pattern_engine import (
    compile_pattern,
    count_states,
    fullmatch,
    match_at,
    reachable_ends,
)

# --- targeted unit cases (semantics documented in the campaign) -------------

@pytest.mark.parametrize("pat,subj,expected", [
    ("abc", "abc", True), ("a*c", "abc", True), ("a*c", "abXc", True),
    ("a?c", "abc", True), ("a?c", "ac", False),
    ("[abc]", "b", True), ("[!abc]", "b", False), ("[a-c]", "b", True),
    ("a@(b|x)c", "abc", True), ("a@(b|x)c", "ayc", False),
    ("a?(b)c", "ac", True), ("a?(b)c", "abbc", False),
    ("a*(b)c", "abbbc", True), ("a*(b)c", "abxbc", False),
    ("a+(b)c", "ac", False), ("a+(b)c", "abc", True),
    ("!(abc)", "abc", False), ("!(abc)", "abd", True),
    ("a!(x)c", "abc", True), ("a!(x)c", "axc", False),
    ("*(a|aa)c", "aaaaac", True), ("*(a|aa)c", "aaaaab", False),
    ("@()", "", True), ("@()", "x", False),
    ("!()", "", False), ("!()", "x", True),
])
def test_fullmatch_targeted(pat, subj, expected):
    assert fullmatch(compile_pattern(pat), subj) is expected


def test_reachable_ends_prefix_lengths():
    # a*(b) against "abbb": reachable prefix ends are {1,2,3,4} (a, ab, abb, abbb)
    ends = reachable_ends(compile_pattern("a*(b)"), "abbb")
    assert ends == frozenset({1, 2, 3, 4})


def test_match_at_leftmost_longest():
    # @(a|aa) at pos 0 of "aaX" -> longest extent 2.
    assert match_at(compile_pattern("@(a|aa)"), "aaX", 0) == 2
    assert match_at(compile_pattern("@(a|aa)"), "X", 0) is None


def test_for_pathname_star_does_not_cross_slash():
    assert fullmatch(compile_pattern("a*b"), "a/b", for_pathname=True) is False
    assert fullmatch(compile_pattern("a*b"), "a/b", for_pathname=False) is True


def test_nocasematch_folds_literals_and_sets():
    assert fullmatch(compile_pattern("ABC"), "abc", ic=True) is True
    assert fullmatch(compile_pattern("[a-z]"), "B", ic=True) is True


# --- random-corpus property tests -------------------------------------------

_SUBJ_ALPHABET = "ab"
_TOKENS = [
    "a", "b", "*", "?", "[ab]", "[!a]", "[a-b]",
    "@(a|b)", "@(a|ab)", "*(a)", "*(ab)", "+(a)", "+(ab)",
    "?(a)", "?(b|ab)", "!(a)", "!(ab)", "@(a|@(b))", "*(a|aa)",
]


def _rand_pattern(rng, max_tokens=5):
    return "".join(rng.choice(_TOKENS)
                   for _ in range(rng.randint(1, max_tokens)))


def _rand_subject(rng, alphabet, max_len=6):
    return "".join(rng.choice(alphabet) for _ in range(rng.randint(0, max_len)))


def _cases(seed, count, alphabet=_SUBJ_ALPHABET):
    rng = random.Random(seed)
    for _ in range(count):
        yield _rand_pattern(rng), _rand_subject(rng, alphabet)


def test_reachable_ends_equal_legacy_matcher():
    """reachable_ends(new) == _extglob_consume(old) on a large random corpus.

    This is the load-bearing equivalence: every consumer derives from this set.
    """
    mismatches = []
    for pat, subj in _cases(seed=1234, count=6000):
        new = set(reachable_ends(compile_pattern(pat), subj))
        old = set(_extglob_consume(pat, subj))
        if new != old:
            mismatches.append((pat, subj, sorted(new), sorted(old)))
    assert not mismatches, (
        f"{len(mismatches)} matcher divergences, first 10: {mismatches[:10]}")


def test_reachable_ends_equal_legacy_matcher_with_slashes():
    """Same, with for_pathname and subjects that contain '/'."""
    mismatches = []
    for pat, subj in _cases(seed=99, count=3000, alphabet="ab/"):
        new = set(reachable_ends(compile_pattern(pat), subj, for_pathname=True))
        old = set(_extglob_consume(pat, subj, for_pathname=True))
        if new != old:
            mismatches.append((pat, subj, sorted(new), sorted(old)))
    assert not mismatches, (
        f"{len(mismatches)} fp divergences, first 10: {mismatches[:10]}")


def test_reachable_ends_equal_legacy_matcher_nocase():
    """Same, case-insensitive, mixed-case subjects."""
    mismatches = []
    for pat, subj in _cases(seed=7, count=3000, alphabet="aAbB"):
        new = set(reachable_ends(compile_pattern(pat), subj, ic=True))
        old = set(_extglob_consume(pat, subj, ic=True))
        if new != old:
            mismatches.append((pat, subj, sorted(new), sorted(old)))
    assert not mismatches, (
        f"{len(mismatches)} ic divergences, first 10: {mismatches[:10]}")


def test_new_fullmatch_agrees_with_regex_converter_on_nonneg():
    """New full-match == the regex converter for negation-free extglob.

    ``pattern_engine`` (the production matcher for case / [[ == ]] / removal /
    substitution) and ``extglob_to_regex`` (the production glob→regex converter
    still used by ``pattern.py``'s regex path) must agree on every non-negation
    extglob pattern — a standing consistency check between the two live
    backends. Negation is not expressible as a Python regex, so it is excluded;
    plain globs are compared elsewhere.
    """
    mismatches = []
    for pat, subj in _cases(seed=555, count=6000):
        if _contains_negation(pat) or not contains_extglob(pat):
            continue
        new = fullmatch(compile_pattern(pat), subj)
        regex_str = extglob_to_regex(pat, anchored=True, from_start=True)
        try:
            old = bool(re.fullmatch(regex_str, subj))
        except re.error:
            old = False
        if new != old:
            mismatches.append((pat, subj, new, old))
    assert not mismatches, (
        f"{len(mismatches)} new-vs-regex divergences, first 10: {mismatches[:10]}")


def test_new_fullmatch_agrees_with_legacy_extglob_fullmatch():
    """New full-match == legacy extglob_fullmatch across ALL random patterns
    (including negation) — the matcher-path public entry the consumers call."""
    mismatches = []
    for pat, subj in _cases(seed=2024, count=6000):
        new = fullmatch(compile_pattern(pat), subj)
        old = extglob_fullmatch(pat, subj)
        if new != old:
            mismatches.append((pat, subj, new, old))
    assert not mismatches, (
        f"{len(mismatches)} fullmatch divergences, first 10: {mismatches[:10]}")


# --- complexity guard (deterministic, not timing) ---------------------------

def test_states_are_polynomial_on_adversarial_inputs():
    """The memoized matcher evaluates O(nodes * positions) states, NOT
    exponentially, on the inputs that break the legacy backends."""
    # *(a|aa)c on "a"*N + "b": legacy regex is exponential.
    for N in (10, 20, 40, 80):
        subj = "a" * N + "b"
        states = count_states(compile_pattern("*(a|aa)c"), subj)
        # Small constant node count; states must grow ~linearly, never 2**N.
        assert states <= 40 * (N + 2), f"N={N} states={states}"
    # ?(a)*k + !(z) on "a"*k + "b": legacy matcher is exponential.
    for k in (10, 20, 40, 80):
        pat = "?(a)" * k + "!(z)"
        subj = "a" * k + "b"
        states = count_states(compile_pattern(pat), subj)
        assert states <= 20 * (k + 2) ** 2, f"k={k} states={states}"
