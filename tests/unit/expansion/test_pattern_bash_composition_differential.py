"""Bash star∘extglob composition battery: the measured-model lock (slot 3.1).

r22 HIGH-7: psh's ``!(...)`` was a local span complement and nullable
extglobs composed freely beside wildcards; bash 5.2's real composition is
SLICE-END-RELATIVE (the star case's continuation bounds, its ``?(``/``*(``
try-then-skip branches, and the end-of-string negation rule all depend on
where the matched slice ends — ``lib/glob/sm_loop.c``). The engine implements
the MEASURED model behind the compile-time routing flag
``pattern_engine._seq_bash_quirk`` (+ per-node ``Extglob.enclosed``), and the
substitution operators implement bash's consumer layer (``pat_subst`` /
``match_upattern`` / ``match_pattern_char`` — see the
``parameter_expansion.py`` module docstring).

This battery is the permanent, default-run lock for all of it:

* the three formerly-divergent ``[[`` anchor rows (H7a/H7b/H7c), both-sides
  pinned;
* the DETERMINISTIC generated corpus (v1: the literal constant lists below,
  no randomness — 64,575 cells = 4,305 deduped patterns x 15 subjects over
  {a,b}), bash spawned ONCE on a batched stdin script, psh evaluated in-process
  through ``match_shell_pattern`` (the exact ``[[``/``case``/name-filter
  path; the ``${...}`` and glob consumers reach the same compiled relations
  through the guarded chokepoints) — pure agreement, no fixed table;
* per-consumer propagation cells (case, all four removal legs, all four
  substitution anchors with TRANSFORMED BYTES, pathname glob against a real
  fixture directory), both-sides pinned where they were red-on-base;
* the newly-measured empty-subject substitution family (the closed
  KNOWN_DIVERGENCES mechanism generalized);
* extglob-off controls;
* engine-level quoted-part truth rows plus RESIDUAL_DIVERGENCES — the
  lexer-seam family pinned in the DIVERGENT direction (successor item,
  slot 3.1 ruling R4: quotes inside an extglob group body survive as raw
  characters in the ``[[`` word, so the engine never sees the protection;
  ``compile_protected`` itself is proven correct here);
* deterministic complexity/recursion guards for the ``_BashMatcher`` path
  (failure messages NAME the pattern).

Runtime budget: the corpus dominates; one bash spawn (~2-4s) + ~0.3s of
in-process cells (measured at introduction; whole module well under 20s).
"""
import itertools

import pytest
from shell_oracle import is_comparable, resolve_bash, run_bash, run_psh

from psh.expansion.pattern import match_shell_pattern
from psh.expansion.pattern_engine import (
    STRING,
    PatternCompiler,
    _seq_bash_quirk,
    compile_pattern,
    count_states,
    fullmatch,
)

_ORACLE = resolve_bash()
_ENV = {"LC_ALL": "C"}


def _run(runner, args, **kw):
    r = runner(args, env=_ENV, **kw)
    assert is_comparable(r), r
    return r


def _tags(out):
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


# --- corpus v1 (DETERMINISTIC: these literal lists ARE the corpus version;
# --- any change is a new corpus version and must be called out in review) ---

_OPS = ["@", "?", "*", "+", "!"]
_ALTS = ["a", "b", "ab", "a|b", "*", "a|*", "a*", "", "a|",
         "?(a)", "!(a)", "@(a|*)"]
_PRE = ["", "*", "?", "a", "*a", "a*", "**", "*?"]
_POST = ["", "a", "*", "?", "a*", "*a", "b"]
_PAIR = ["!(a)", "?(a)", "@(a|*)", "*(a)", "!(*)"]
_PAIR2 = ["!(a)", "?(a)", "@(a|*)", "*(a)", "!(*)", "+(a)", "@(*)", "?(*)"]
_NEST_ALTS = ["*!(a)", "*?(a)", "*@(a|*)", "*(a)b", "a*!(b)", "*"]

SUBJECTS = [""] + ["".join(t) for length in (1, 2, 3)
                   for t in itertools.product("ab", repeat=length)]


def corpus_patterns():
    """The deterministic corpus-v1 pattern list (order-stable, deduped)."""
    seen = set()
    out = []

    def add(p):
        if p not in seen:
            seen.add(p)
            out.append(p)

    # plain wildcard controls (no group)
    for pre in _PRE:
        for post in _POST:
            if pre or post:
                add(pre + post)
    # one group in context
    for pre in _PRE:
        for op in _OPS:
            for alt in _ALTS:
                for post in _POST:
                    add(pre + f"{op}({alt})" + post)
    # two adjacent groups
    for pre in ("", "*"):
        for g1 in _PAIR:
            for g2 in _PAIR:
                add(pre + g1 + g2)
    # two-group chains with context
    for pre in ("", "*", "a", "a*"):
        for g1 in _PAIR2:
            for g2 in _PAIR2:
                for post in ("", "a", "*"):
                    add(pre + g1 + g2 + post)
    # nested star-adjacent alternatives
    for op in "@?*+!":
        for alt in _NEST_ALTS:
            for pre in ("", "*"):
                for post in ("", "a"):
                    add(pre + f"{op}({alt})" + post)
    # groups separated by a literal
    for g1 in ("!(a)", "?(a)", "*(a)"):
        for g2 in ("!(b)", "?(b)", "@(b|*)"):
            add(g1 + "a" + g2)
            add("*" + g1 + "a" + g2)
    # wildcard runs before groups
    for run in ("***", "*?*", "?*", "*??"):
        for g in ("!(a)", "?(a)", "@(a|*)", "*(ab)"):
            add(run + g)
    return out


def test_composition_corpus_engine_matches_bash():
    """Engine full-match == live bash over the whole corpus (one spawn).

    The corpus crosses operator x alternative-nullability x pre/post wildcard
    context x nesting (depth 2, incl. star-adjacent alternatives) with every
    subject over {a,b} of length 0-3. bash runs the batched ``[[`` script
    once from stdin; psh answers in-process through match_shell_pattern —
    the same compiled relation every consumer routes through. Agreement-form:
    bash's answer IS the expectation, so oracle drift is visible."""
    patterns = corpus_patterns()
    cells = [(p, s) for p in patterns for s in SUBJECTS]
    script_lines = ["shopt -s extglob"]
    for pat, subj in cells:
        script_lines.append(f"[[ '{subj}' == {pat} ]] && echo 1 || echo 0")
    r = _run(run_bash, [], stdin_data="\n".join(script_lines) + "\n",
             timeout=60)
    answers = r.stdout.split()
    assert len(answers) == len(cells), (
        f"bash produced {len(answers)} answers for {len(cells)} cells; "
        f"stderr: {r.stderr[:400]!r}")
    mismatches = []
    for (pat, subj), b in zip(cells, answers, strict=True):
        mine = "1" if match_shell_pattern(subj, pat,
                                          extglob_enabled=True) else "0"
        if mine != b:
            mismatches.append((pat, subj, b, mine))
    assert not mismatches, (
        f"{len(mismatches)} corpus divergences (pattern, subject, bash, "
        f"psh), first 20: {mismatches[:20]}")


# --- the three [[ anchor rows (H7a/H7b/H7c), both-sides pinned --------------

@pytest.mark.parametrize("rid,subj,pat,bash_rc", [
    ("H7a", "", "*@(a|*)", 1),
    ("H7b", "a", "*!(a)", 1),
    ("H7c", "", "*!(*)", 0),
])
def test_double_bracket_anchor_rows(rid, subj, pat, bash_rc):
    """The r22 HIGH-7 ``[[`` rows: psh == bash == the measured value.

    Red-on-base: at 29456fdc psh answered the complement of every row
    (slot 3.1 ledger A1). The bash side is ALSO pinned so an oracle-version
    behaviour change fails loudly as oracle drift, not silently."""
    script = f"[[ '{subj}' == {pat} ]]"
    b = _run(run_bash, ["-c", script])
    p = _run(run_psh, ["-c", script])
    assert b.returncode == bash_rc, (rid, "oracle drift", b.returncode)
    assert p.returncode == b.returncode, (rid, b.returncode, p.returncode)


# --- per-consumer propagation (string consumers, batched) -------------------

# (tag, script-line, expected-tag-value) — expected values are the measured
# bash 5.2.26 readings (slot 3.1 grid, tmp/slot31 evidence); each row also
# asserts psh == bash so drift on either side is loud. Rows marked red-on-base
# in the ledger flipped with the fix.
_CONSUMER_ROWS = [
    ("case_h7b", 'case a in\n*!(a)) echo "case_h7b=M";;\n'
                 '*) echo "case_h7b=N";;\nesac', "N"),
    ("case_h7a", 'case "" in\n*@(a|*)) echo "case_h7a=M";;\n'
                 '*) echo "case_h7a=N";;\nesac', "N"),
    ("case_h7c", 'case "" in\n*!(*)) echo "case_h7c=M";;\n'
                 '*) echo "case_h7c=N";;\nesac', "M"),
    ("rem_h7b", 'v=a; printf "rem_h7b=[%s][%s][%s][%s]\\n"'
                ' "${v#*!(a)}" "${v##*!(a)}" "${v%*!(a)}" "${v%%*!(a)}"',
     "[a][a][a][a]"),
    ("rem_h7a", 'v=a; printf "rem_h7a=[%s][%s]\\n"'
                ' "${v#*@(a|*)}" "${v##*@(a|*)}"', "[][]"),
    ("sub_h7b", 'v=a; printf "sub_h7b=[%s][%s][%s][%s]\\n"'
                ' "${v/*!(a)/X}" "${v//*!(a)/X}" "${v/#*!(a)/X}"'
                ' "${v/%*!(a)/X}"', "[Xa][Xa][Xa][a]"),
    ("sub_h7a", 'v=""; printf "sub_h7a=[%s][%s]\\n"'
                ' "${v/*@(a|*)/X}" "${v//*@(a|*)/X}"', "[][]"),
    ("sub_h7c", 'v=""; printf "sub_h7c=[%s][%s]\\n"'
                ' "${v/*!(*)/X}" "${v//*!(*)/X}"', "[X][X]"),
    # the closed empty-subject family, generalized (match_pattern_char gate
    # + pat_subst single-shot + match_upattern pre-test):
    ("emptysub_q", 'v=""; printf "emptysub_q=[%s][%s][%s][%s]\\n"'
                   ' "${v/?(a)/Z}" "${v//?(a)/Z}" "${v/#?(a)/Z}"'
                   ' "${v/%?(a)/Z}"', "[][][][Z]"),
    ("emptysub_at", 'v=""; printf "emptysub_at=[%s][%s][%s][%s]\\n"'
                    ' "${v/@(|a)/Z}" "${v//@(|a)/Z}" "${v/#@(|a)/Z}"'
                    ' "${v/%@(|a)/Z}"', "[][][][]"),
    ("emptysub_star", 'v=""; printf "emptysub_star=[%s][%s][%s][%s]\\n"'
                      ' "${v/*!(a)/Z}" "${v//*!(a)/Z}" "${v/#*!(a)/Z}"'
                      ' "${v/%*!(a)/Z}"', "[Z][Z][Z][Z]"),
    ("pretest_end", 'v=a; printf "pretest_end=[%s]\\n" "${v/%!(a)/Z}"',
     "[a]"),
    ("pretest_end2", 'v=b; printf "pretest_end2=[%s]\\n" "${v/%@(|a)/Z}"',
     "[b]"),
    # extglob-off controls: prefix chars are ordinary; ${} and [[ agree.
    ("off_rem", 'shopt -u extglob\nv="!(a)"; printf "off_rem=[%s]\\n"'
                ' "${v#!(a)}"', "[]"),
    ("off_sub", 'shopt -u extglob\nv=a; printf "off_sub=[%s]\\n"'
                ' "${v/?(a)/Z}"', "[a]"),
    ("off_dbr", "shopt -u extglob\n[[ 'ab' == *!(a) ]]"
                '\nprintf "off_dbr=%s\\n" $?', "0"),
]


def test_consumer_propagation_and_empty_subject_family():
    """One batched run: every string consumer sees the fixed composition.

    ``shopt -s extglob`` sits on its own line (a ``;``-joined prefix parses
    as one unit BEFORE the option lands — measured, both shells). Rows carry
    the measured bash value AND assert psh equality."""
    lines = ["shopt -s extglob"]
    for _tag, snippet, _exp in _CONSUMER_ROWS:
        lines.append(snippet)
        lines.append("shopt -s extglob")  # restore after off-control rows
    script = "\n".join(lines) + "\n"
    bt = _tags(_run(run_bash, [], stdin_data=script).stdout)
    pt = _tags(_run(run_psh, [], stdin_data=script,
                    stdin_mode="file").stdout)
    problems = []
    for tag, _snippet, expected in _CONSUMER_ROWS:
        if bt.get(tag) != expected:
            problems.append((tag, "oracle drift", expected, bt.get(tag)))
        if pt.get(tag) != bt.get(tag):
            problems.append((tag, "psh!=bash", bt.get(tag), pt.get(tag)))
    assert not problems, problems


# --- pathname glob propagation ----------------------------------------------

def test_glob_propagation(tmp_path):
    """Pathname expansion sees the fixed composition (real fixture glob).

    ``*!(a)`` excludes plain ``a`` (H7b through the glob consumer, red-on-
    base) while agreeing rows pin dotfile/slash policy unchanged."""
    for name in ("a", "ab", "b", "ba", ".ha"):
        (tmp_path / name).write_text("x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a").write_text("x")
    lines = ["shopt -s extglob"]
    pats = ["*!(a)", "!(a)", "!(*)", "*?(a)", "sub/!(a)", ".!(a)"]
    for i, pat in enumerate(pats):
        lines.append(f"printf 'g{i}=[%s]' {pat}; echo")
    script = "\n".join(lines) + "\n"
    bt = _tags(_run(run_bash, [], stdin_data=script,
                    cwd=str(tmp_path)).stdout)
    pt = _tags(_run(run_psh, [], stdin_data=script,
                    cwd=str(tmp_path)).stdout)
    assert bt.get("g0") == "[ab]g0=[b]g0=[ba]g0=[sub]", ("oracle drift", bt)
    diffs = [(f"g{i}", pats[i], bt.get(f"g{i}"), pt.get(f"g{i}"))
             for i in range(len(pats)) if bt.get(f"g{i}") != pt.get(f"g{i}")]
    assert not diffs, diffs


# --- quoted parts: engine truth vs the lexer-seam residual (R4) -------------

def test_quoted_alternative_engine_level():
    """``compile_protected`` handles quoted text inside a negation group.

    These are the ENGINE-level truths for the lexer-seam residual family
    below: when the protection actually reaches the engine (as it does on
    the ``${...}`` operand path), the semantics are bash's. Localizes the
    residual defect to the lexer word seam, not the matcher."""
    neg_a = PatternCompiler.compile_protected(
        [("!(", False), ("a", True), (")", False)])
    assert neg_a.full_match("a", STRING) is False
    assert neg_a.full_match("b", STRING) is True
    neg_star = PatternCompiler.compile_protected(
        [("!(", False), ("*", True), (")", False)])
    assert neg_star.full_match("*", STRING) is False
    assert neg_star.full_match("x", STRING) is True


def test_quoted_alternative_via_parameter_expansion():
    """The ``${...}`` operand path delivers protection to the engine: the
    quoted-alt negation substitution matches bash (closed with the engine
    fix; contrast with the ``[[`` residual below)."""
    script = 'shopt -s extglob\nv=a\nprintf "q=[%s]\\n" "${v/*!("a")/Z}"\n'
    b = _run(run_bash, [], stdin_data=script)
    p = _run(run_psh, [], stdin_data=script)
    assert _tags(b.stdout).get("q") == "[Za]", ("oracle drift", b.stdout)
    assert _tags(p.stdout).get("q") == _tags(b.stdout).get("q")


# Successor-visible residual divergences (slot 3.1 ruling R4: LEXER item).
# Each row: (tag, script, bash_value, psh_value). The lexer emits quotes
# inside an extglob group body as RAW characters of one unquoted word (the
# `[[` seam then matches against the literal spelling `!("a")`), so the
# protection never reaches the engine. Pinned in the DIVERGENT direction:
# the lexer fix must flip these rows LOUDLY and move them to equality.
RESIDUAL_DIVERGENCES = [
    ("lex_q1", "[[ 'a' == !(\"a\") ]]\nprintf 'lex_q1=%s\\n' $?",
     "1", "0"),
    ("lex_q3", "[[ '*' == !(\"*\") ]]\nprintf 'lex_q3=%s\\n' $?",
     "1", "0"),
]


def test_residual_divergences_still_divergent():
    """The lexer-seam quoted-alt rows remain EXACTLY as documented.

    If a change (the successor lexer fix, or anything else) flips one, this
    fails loudly so the row is deliberately promoted to the equality lock
    rather than drifting. Engine-level truth for the same cells is pinned
    green above — the defect lives in the ``[[`` word's part structure."""
    script = "shopt -s extglob\n" + "\n".join(
        row[1] for row in RESIDUAL_DIVERGENCES) + "\n"
    bt = _tags(_run(run_bash, [], stdin_data=script).stdout)
    pt = _tags(_run(run_psh, [], stdin_data=script).stdout)
    for tag, _script, bash_val, psh_val in RESIDUAL_DIVERGENCES:
        assert bt.get(tag) == bash_val, (tag, "oracle drift", bt.get(tag))
        assert pt.get(tag) == psh_val, (tag, "psh reading moved", pt.get(tag))


# --- deterministic guards for the _BashMatcher path -------------------------

def test_bash_matcher_flag_predicate():
    """_seq_bash_quirk pins: exactly wildcard-run∘group adjacency routes to
    the measured matcher (this predicate is ALSO the regex-oracle exclusion
    in test_pattern_engine_matcher.py — one decider)."""
    flagged = ["*!(a)", "*?(a)", "**(a)", "*@(a|*)", "*?@(a)", "a*!(b)c",
               "@(*!(a))", "!(*!(a))a"]
    unflagged = ["abc", "a*", "*a*", "!(a)", "?(a)b", "@(a|b)*", "?@(a)",
                 "a!(b)c", r"\*!(a)", "*(a)", "*a!(b)"]
    for pat in flagged:
        assert _seq_bash_quirk(compile_pattern(pat)) is True, pat
    for pat in unflagged:
        assert _seq_bash_quirk(compile_pattern(pat)) is False, pat


def test_bash_matcher_states_stay_polynomial():
    """The memoized _BashMatcher evaluates polynomially many states.

    Bounds calibrated at introduction (linear for single trailing groups,
    ~N^2/2 for the `**(a)b` inclusive branch). Failure names the pattern."""
    linear = ["*!(a)", "*?(a|b)", "*@(a|*)"]
    for pat in linear:
        for n in (16, 64, 256):
            subj = "a" * n
            states = count_states(compile_pattern(pat), subj)
            assert states <= 8 * (n + 2), (
                f"pattern {pat!r} on 'a'*{n}: {states} states (bound "
                f"{8 * (n + 2)}) — the _BashMatcher memo regressed")
    for n in (16, 64, 128):
        subj = "a" * n
        states = count_states(compile_pattern("**(a)b"), subj)
        assert states <= (n + 2) ** 2, (
            f"pattern '**(a)b' on 'a'*{n}: {states} states (bound "
            f"{(n + 2) ** 2}) — the _BashMatcher memo regressed")


def test_bash_matcher_recursion_contract():
    """Flagged-pattern recursion is bounded by PATTERN structure.

    A 100-unit star∘negation chain evaluates fine at the default recursion
    limit; a pathological 1000-unit chain raises a clean RecursionError —
    an EXPECTED shell error under strict-errors (the same taxonomy as
    extglob nesting depth; declared in slot 3.1). Subject length and star
    count alone never recurse (non-flagged patterns keep the iterative
    paths — pinned by the existing matcher/relations suites)."""
    assert fullmatch(compile_pattern("*!(a)" * 100), "aaa") is True
    with pytest.raises(RecursionError):
        fullmatch(compile_pattern("*!(a)" * 1000), "aaa")
