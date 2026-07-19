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
    compile_pattern,
    count_states,
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
    """A long LITERAL chain must not raise RecursionError even at the DEFAULT
    interpreter recursion limit: a run of single-continuation nodes
    (Literal/AnyChar/Bracket) is consumed by an inner while-loop, not recursion
    (the former recursive matcher raised RecursionError at ~1500 literals; #20
    H7-b). 20000 literals is far past any recursion limit."""
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(1000)
    try:
        n = 20000
        assert _c("a" * n).full_match("a" * n, STRING) is True
        assert _c("a" * n).full_match("a" * (n - 1), STRING) is False
        # AnyChar and Bracket chains are single-continuation too.
        assert _c("?" * n).full_match("z" * n, STRING) is True
        assert _c("[ab]" * n).full_match("ab" * (n // 2), STRING) is True
    finally:
        sys.setrecursionlimit(old)


def test_many_stars_no_exponential_blowup():
    """Many Star nodes (`*a*a…`) memoize to polynomial state, so the adversarial
    `*a…*b` that made the old regex path exponential is fast. (Star/Extglob
    branches recurse to a depth bounded by the pattern's branch count, well
    within psh's runtime recursion limit; the UNBOUNDED literal case above is
    the one made fully iterative.)"""
    pat = "*a" * 200 + "*b"
    assert _c(pat, extglob=False).full_match("a" * 400 + "b", STRING) is True
    assert _c(pat, extglob=False).full_match("a" * 400, STRING) is False


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
    import dataclasses
    p = MatchProfile(for_pathname=True, ic=True)
    assert (p.for_pathname, p.ic) == (True, True)
    with pytest.raises(dataclasses.FrozenInstanceError):
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


# --- pathname glob: carry-2 + nocaseglob (in-process; tests THIS tree) ------
# Expected values are bash 5.2-verified (tmp/boundary-ledgers/W3-probes/
# pathname-stage3.txt). Run in-process so the worktree GlobExpander is exercised
# (a subprocess `-m psh` from a tempdir imports the editable-installed MAIN).

def _mkfiles(names):
    import os
    for n in names:
        open(os.path.join(os.getcwd(), n), 'w').close()


def test_pathname_carry2_quoted_dash_is_literal_member(isolated_shell_with_temp_dir):
    sh = isolated_shell_with_temp_dir
    _mkfiles(['a', 'b', 'c', '-x'])
    # [a"-"c]* : _pattern_from_runs yields the canonical [a\-c]* ; {a,-,c} members
    # -> matches '-x', 'a', 'c' (NOT 'b'), bash collation order.
    assert sh.expansion_manager.glob_expander.expand(r'[a\-c]*') == ['-x', 'a', 'c']


def test_pathname_carry2_quoted_caret_is_literal_member(isolated_shell_with_temp_dir):
    sh = isolated_shell_with_temp_dir
    _mkfiles(['^x', 'ax', 'zx'])
    # ["^"a]* -> [\^a]* : members {^,a}, NOT negation -> '^x','ax' (NOT 'zx').
    assert sh.expansion_manager.glob_expander.expand(r'[\^a]*') == ['^x', 'ax']


def test_pathname_carry2_quoted_bang_is_literal_member(isolated_shell_with_temp_dir):
    sh = isolated_shell_with_temp_dir
    _mkfiles(['!x', 'ax', 'zx'])
    assert sh.expansion_manager.glob_expander.expand(r'[\!a]*') == ['!x', 'ax']


def test_pathname_nocaseglob_keeps_upper_class_case_sensitive(
        isolated_shell_with_temp_dir):
    sh = isolated_shell_with_temp_dir
    _mkfiles(['abc', 'XYZ'])
    sh.run_command('shopt -s nocaseglob')
    # bash: nocaseglob keeps [[:upper:]] case-sensitive -> only 'XYZ'.
    assert sh.expansion_manager.glob_expander.expand('*[[:upper:]]*') == ['XYZ']


def test_pathname_nocaseglob_folds_literals(isolated_shell_with_temp_dir):
    # Non-case-colliding names (APFS is case-insensitive): the lowercase-'b'
    # file 'qbq' is matched by the uppercase-'B' pattern ONLY under nocaseglob.
    sh = isolated_shell_with_temp_dir
    _mkfiles(['qbq', 'xyz'])
    assert sh.expansion_manager.glob_expander.expand('*B*') == []   # case-sensitive
    sh.run_command('shopt -s nocaseglob')
    assert sh.expansion_manager.glob_expander.expand('*B*') == ['qbq']  # folds


def test_pathname_trailing_slash_directories_only(isolated_shell_with_temp_dir):
    import os
    sh = isolated_shell_with_temp_dir
    os.mkdir('d1'); os.mkdir('d2'); open('f1', 'w').close()
    # dir*/ restricts to directories and appends '/'.
    assert sh.expansion_manager.glob_expander.expand('d*/') == ['d1/', 'd2/']


def test_pathname_backslash_in_value_stays_literal(isolated_shell_with_temp_dir):
    sh = isolated_shell_with_temp_dir
    _mkfiles(['aQb', 'a\\Zb'])
    # x='a\*b' -> field ACTIVE 'a\*b' -> encoder doubles the backslash ->
    # a\\*b -> literal backslash + wildcard: matches 'a\Zb', not 'aQb'.
    sh.run_command(r"x='a\*b'")
    out = sh.expansion_manager.glob_expander.expand(r'a\\*b')
    assert out == ['a\\Zb']


# --- BOUNCE blocker 1 pins: star count never consumes recursion frames -----
# bash 5.2 truth (probe transcripts: tmp/boundary-ledgers/W3-probes/
# starprobe-red-at-6a2653bf.txt [5 rows RED at the pre-fix tip with
# 'maximum recursion depth exceeded'] and starprobe-green-postfix.txt).
# The matcher recursed ONE FRAME PER STAR; the fix makes star handling
# iterative (two-pointer boolean / forward position-set DP), so 50,000-star
# patterns match at ANY recursion limit, like base and bash.

_N_STARS = 50000


def test_engine_50k_stars_full_match_at_default_limit():
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(1000)
    try:
        cp = _c("*" * _N_STARS, extglob=False)
        assert cp.full_match("abc", STRING) is True
        assert cp.full_match("", STRING) is True
    finally:
        sys.setrecursionlimit(old)


def test_engine_50k_stars_matching_ends_at_default_limit():
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(1000)
    try:
        cp = _c("*" * _N_STARS, extglob=False)
        # All-stars reaches every position: ${x#...} -> min 0, ${x##...} -> max.
        assert cp.matching_ends("abc", 0, STRING) == frozenset({0, 1, 2, 3})
    finally:
        sys.setrecursionlimit(old)


def test_engine_50k_star_chain_at_default_limit():
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(1000)
    try:
        cp = _c("*a" * _N_STARS, extglob=False)
        assert cp.full_match("a" * _N_STARS, STRING) is True   # exact chain
        assert cp.full_match("abc", STRING) is False           # needs 50k a's
    finally:
        sys.setrecursionlimit(old)


def test_shell_param_removal_50k_stars(captured_shell):
    # bash: ${x#<50k stars>} -> 'abc' (shortest = empty), ${x##...} -> ''.
    stars = "*" * _N_STARS
    rc = captured_shell.run_command(
        f'x=abc; printf "%s|%s|" "${{x#{stars}}}" "${{x##{stars}}}"')
    assert rc == 0
    assert captured_shell.get_stdout() == "abc||"
    assert captured_shell.get_stderr() == ""


def test_shell_case_50k_stars(captured_shell):
    stars = "*" * _N_STARS
    rc = captured_shell.run_command(
        f'case abc in {stars}) echo M;; *) echo N;; esac')
    assert rc == 0
    assert captured_shell.get_stdout() == "M\n"


def test_shell_case_50k_star_chain_no_match(captured_shell):
    chain = "*a" * _N_STARS
    rc = captured_shell.run_command(
        f'case abc in {chain}) echo Y;; *) echo N;; esac')
    assert rc == 0
    assert captured_shell.get_stdout() == "N\n"


def test_shell_pathname_50k_stars(isolated_shell_with_temp_dir):
    sh = isolated_shell_with_temp_dir
    _mkfiles(['a', 'b'])
    # bash: an all-stars pattern expands to every non-hidden name.
    assert sh.expansion_manager.glob_expander.expand("*" * _N_STARS) == ['a', 'b']


# --- extglob NESTING bound: the one remaining (structural) recursion -------

def test_matcher_extglob_nesting_bound_raises_recursion_error():
    """The structural bound: extglob NESTING depth is the ONLY recursion left
    in the matcher. Past the interpreter limit it raises RecursionError — the
    EXPECTED-shell-error type under strict-errors (taxonomy in
    psh/core/CLAUDE.md), never a corrupted state. The AST is built
    programmatically (an iterative loop) so this pins the MATCHER's bound
    without the parser's own (matching-depth) recursion. Shell-level failure
    mode probed vs bash 5.2 and archived (tmp/boundary-ledgers/W3-probes/
    nesting-bound-probe.txt): at nesting depth 30,000 psh fails CLEANLY
    (command rc 1, diagnostic, shell continues) while bash SEGFAULTS
    (rc -11); the slow full-shell row lives in the nightly benchmark tier
    (tests/performance/benchmarks/test_pattern_engine_performance.py)."""
    from psh.expansion.pattern_engine import Extglob, Literal, Sequence
    seq = Sequence((Literal("x"),))
    for _ in range(2000):
        seq = Sequence((Extglob("@", (seq,)),))
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(1000)
    try:
        with pytest.raises(RecursionError):
            CompiledPattern(seq).full_match("x", STRING)
    finally:
        sys.setrecursionlimit(old)


def test_compile_extglob_nesting_bound_raises_recursion_error():
    """The COMPILER recurses once per extglob nesting level too (it is the
    tighter gate: the matcher can never out-recurse a pattern that compiled).
    Past the limit it raises the same expected RecursionError."""
    depth = 2000
    pat = "@(" * depth + "x" + ")" * depth
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(1000)
    try:
        with pytest.raises(RecursionError):
            compile_pattern(pat)
    finally:
        sys.setrecursionlimit(old)


def test_extglob_nesting_within_bound_matches(captured_shell):
    # Control: nesting well within the bound matches (bash parity, depth 100).
    depth = 100
    pat = "@(" * depth + "x" + ")" * depth
    captured_shell.run_command("shopt -s extglob")
    rc = captured_shell.run_command(f"[[ x == {pat} ]] && echo M")
    assert rc == 0
    assert captured_shell.get_stdout() == "M\n"
