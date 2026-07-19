"""The one iterative pattern relation — four-relation API, iterative matcher,
protection-direct compilation, and complexity guards (campaign W3, #20 H7).

`CompiledPattern` exposes exactly the relations its consumers need:
  full_match      — case / [[ == ]] / HISTIGNORE / case-mod per char / pathname
  matching_ends   — prefix removal (${v#}=min, ${v##}=max)
  matching_starts — suffix removal (${v%}=max start, ${v%%}=min start)
  span_at         — substitution leftmost-longest length at a position
  matching_spans  — the left-to-right global-substitution walk
The matcher is ITERATIVE (no Python recursion) and polynomial (memoized), and
`compile_protected` consumes per-character ACTIVE/PROTECTED runs directly.
"""
import sys

import pytest

from psh.expansion.pattern_engine import (
    PATHNAME,
    STRING,
    STRING_IC,
    CompiledPattern,
    MatchProfile,
    PatternCompiler,
    count_states,
    compile_pattern,
    runs_to_pattern_string,
)


def _c(pattern, extglob=True):
    return PatternCompiler.compile(pattern, extglob=extglob)


# --- full_match ------------------------------------------------------------

@pytest.mark.parametrize("pat,subj,ok", [
    ("a*c", "abc", True), ("a*c", "ac", True), ("a?c", "ac", False),
    ("[a-c]", "b", True), ("[!a-c]", "b", False),
    ("a@(b|x)c", "abc", True), ("!(abc)", "abd", True), ("!(abc)", "abc", False),
])
def test_full_match(pat, subj, ok):
    assert _c(pat).full_match(subj, STRING) is ok


def test_full_match_newline_semantics_star_and_qmark():
    # `*`/`?` DO match a newline (shell glob, not Python `.`): #20 H7-a parity.
    assert _c("a*b").full_match("a\nb", STRING) is True
    assert _c("a?b").full_match("a\nb", STRING) is True


def test_full_match_nocasematch_via_profile():
    assert _c("ABC").full_match("abc", STRING) is False
    assert _c("ABC").full_match("abc", STRING_IC) is True


# --- matching_ends (prefix removal) ---------------------------------------

def test_matching_ends_prefix_removal():
    cp = _c("a*")
    ends = cp.matching_ends("abc", 0, STRING)
    assert ends == frozenset({1, 2, 3})       # a, ab, abc
    assert min(ends) == 1                      # ${v#a*}  -> "bc"[shortest]
    assert max(ends) == 3                      # ${v##a*} -> ""  [longest]


def test_matching_ends_offset_start():
    # from start=1, the pattern must match text[1:k]
    cp = _c("b*")
    assert cp.matching_ends("abc", 1, STRING) == frozenset({2, 3})


# --- matching_starts (suffix removal) -------------------------------------

def test_matching_starts_suffix_removal():
    cp = _c("*c")
    starts = cp.matching_starts("abc", 3, STRING)
    assert starts == frozenset({0, 1, 2})      # abc, bc, c all end-match *c
    assert max(starts) == 2                     # ${v%*c}  shortest suffix -> "ab"
    assert min(starts) == 0                     # ${v%%*c} longest suffix -> ""


# --- span_at / matching_spans (substitution) ------------------------------

def test_span_at_leftmost_longest():
    assert _c("@(a|aa)").span_at("aaX", 0, STRING) == 2   # longest at pos 0
    assert _c("@(a|aa)").span_at("X", 0, STRING) is None


def test_matching_spans_global_walk():
    spans = list(_c("a").matching_spans("banana", STRING))
    assert spans == [(1, 2), (3, 4), (5, 6)]


# --- iterative matcher: NO RecursionError (H7-b) ---------------------------

def test_deep_literal_pattern_no_recursion_error():
    """A ~5000-literal pattern must not raise RecursionError even at the DEFAULT
    interpreter recursion limit — the matcher is iterative (the recursive matcher
    raised RecursionError at ~1500 literals)."""
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(1000)
    try:
        n = 5000
        assert _c("a" * n).full_match("a" * n, STRING) is True
        assert _c("a" * n).full_match("a" * (n - 1), STRING) is False
    finally:
        sys.setrecursionlimit(old)


def test_deep_star_pattern_no_recursion_error():
    """Deep alternating stars (`*a*a…`) also stay iterative."""
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(1000)
    try:
        pat = "*a" * 1000
        assert _c(pat).full_match("a" * 2000, STRING) is True
    finally:
        sys.setrecursionlimit(old)


# --- complexity guard: polynomial, never exponential (H7-c) ----------------

def test_plain_glob_states_polynomial_not_exponential():
    """The adversarial PLAIN glob `*a*a…*b` was exponential on the old regex
    path (seconds / timeout). Through the engine it is polynomial in states."""
    for n in (10, 20, 40, 80):
        pat = "*a" * 14 + "*b"
        subj = "a" * n
        states = count_states(compile_pattern(pat, extglob=False), subj)
        assert states <= 40 * (n + 2), f"n={n} states={states}"


def test_adversarial_plain_glob_is_fast():
    """The specific #20 H7-c case must return quickly (was a hard timeout)."""
    import time
    pat = "*a" * 14 + "*b"
    t = time.perf_counter()
    assert _c(pat, extglob=False).full_match("a" * 60, STRING) is False
    assert time.perf_counter() - t < 1.0


# --- MatchProfile ----------------------------------------------------------

def test_for_pathname_star_does_not_cross_slash():
    assert _c("a*b").full_match("a/b", PATHNAME) is False
    assert _c("a*b").full_match("a/b", STRING) is True


def test_match_profile_is_typed_and_frozen():
    p = MatchProfile(for_pathname=True, ic=True)
    assert (p.for_pathname, p.ic) == (True, True)
    with pytest.raises(Exception):
        p.ic = False  # frozen


# --- compile_protected: protection consumed directly (carry-2) -------------

def _fm_protected(parts, subj, profile=STRING):
    return PatternCompiler.compile_protected(parts).full_match(subj, profile)


def test_protected_metachar_is_literal_beside_active():
    # "*"* : PROTECTED '*' (literal) beside ACTIVE '*' (wildcard). #20 H6.
    parts = [("*", True), ("*", False)]
    assert _fm_protected(parts, "*abc") is True     # leading literal '*'
    assert _fm_protected(parts, "abc") is False


@pytest.mark.parametrize("parts,subj,ok", [
    # [a"-"c] : quoted '-' is a literal member {a,-,c}, NOT a range a-c.
    ([("[a", False), ("-", True), ("c]", False)], "b", False),
    ([("[a", False), ("-", True), ("c]", False)], "-", True),
    ([("[a", False), ("-", True), ("c]", False)], "a", True),
    # ["^"a] : quoted '^' is a literal member {^,a}, NOT negation.
    ([("[", False), ("^", True), ("a]", False)], "a", True),
    ([("[", False), ("^", True), ("a]", False)], "x", False),
    ([("[", False), ("^", True), ("a]", False)], "^", True),
    # ["!"a] : quoted '!' is a literal member {!,a}, NOT negation.
    ([("[", False), ("!", True), ("a]", False)], "!", True),
    ([("[", False), ("!", True), ("a]", False)], "x", False),
    # Unquoted range/negation keep their class meaning.
    ([("[a-c]", False)], "b", True),
    ([("[!a]", False)], "x", True),
])
def test_carry2_quoted_class_special_is_literal_member(parts, subj, ok):
    assert _fm_protected(parts, subj) is ok


def test_runs_to_pattern_string_leaves_slash_raw():
    # '/' is never a glob metacharacter and is always a separator, so it is not
    # escaped even when PROTECTED — the pathname component split depends on it.
    assert runs_to_pattern_string([("a/b", True), ("*", False)]) == "a/b*"


def test_runs_to_pattern_string_doubles_active_backslash():
    # A residual value backslash (ACTIVE) stays literal via doubling.
    assert runs_to_pattern_string([("a\\b", False)]) == "a\\\\b"


def test_compiled_pattern_reused_across_profiles():
    cp = _c("A*")
    assert cp.full_match("abc", STRING) is False
    assert cp.full_match("abc", STRING_IC) is True   # same compiled AST reused


def test_public_compiledpattern_type():
    assert isinstance(_c("x"), CompiledPattern)
