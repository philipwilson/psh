#!/usr/bin/env python3
"""Battery grammar-v2 edits on top of tip 7bec085c (slot 3.1 Phase C).
Same asserts/idempotence discipline as restore_phase_c.py."""
p = 'tests/unit/expansion/test_pattern_bash_composition_differential.py'
src = open(p).read()

old = '''This battery is the permanent, default-run lock for all of it:

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
  fixture directory), both-sides pinned where they were red-on-base;'''
new = '''The engine also implements the glibc star-JUMP bash inherits (sm_loop.c:
the star scan's inner walk STOPS at the next wildcard star and COMMITS that
position, so a simple-element segment between stars is placed at its
LEFTMOST match and earlier stars never retry — found in verification round
1): it decides which entry position a later wildcard-run's rules see, so
``*a*!(a)`` does NOT match ``aa`` (the committed entry is before the end).

This battery is the permanent, default-run lock for all of it:

* the formerly-divergent ``[[`` anchor rows — H7a/H7b/H7c plus the round-1
  star-jump cells — both-sides pinned;
* the DETERMINISTIC generated corpus, bash spawned ONCE on a batched stdin
  script, psh evaluated in-process through ``match_shell_pattern`` (the
  exact ``[[``/``case``/name-filter path; the ``${...}`` and glob consumers
  reach the same compiled relations through the guarded chokepoints) — pure
  agreement, no fixed table. Grammar v2 = the v1 constant lists below
  (context x operator x alternative-list x depth-2 nesting over {a,b}) PLUS
  the round-1 widened shapes (star-literal-star contexts — the jump
  surface — post-negation continuations, group-in-segment, multi-run
  chains) over BOTH {a,b} and a disjoint {a,c} mirror, subjects to length 4
  on the widened shapes. Cell counts are DERIVED by the generators at run
  time, never asserted as constants, and every exactness claim this battery
  makes is SCOPED to exactly this grammar;
* per-consumer propagation cells (case, all four removal legs, all four
  substitution anchors with TRANSFORMED BYTES, pathname glob against a real
  fixture directory), both-sides pinned where they were red-on-base,
  including star-jump consumer cells;'''
assert src.count(old) == 1, "edit1"
src = src.replace(old, new)

old = '''Runtime budget: the corpus dominates; one bash spawn (~2-4s) + ~0.3s of
in-process cells (measured at introduction; whole module well under 20s).
"""'''
new = '''Runtime budget: the corpus dominates; one bash spawn over ~500k script
lines (~2s measured) + ~2s of in-process cells; whole module well under
20s (measured at grammar v2).
"""'''
assert src.count(old) == 1, "edit2"
src = src.replace(old, new)

old = '''    # wildcard runs before groups
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
    r = _run(run_bash, [], stdin_data="\\n".join(script_lines) + "\\n",
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
        f"psh), first 20: {mismatches[:20]}")'''
new = '''    # wildcard runs before groups
    for run in ("***", "*?*", "?*", "*??"):
        for g in ("!(a)", "?(a)", "@(a|*)", "*(ab)"):
            add(run + g)
    return out


def widened_patterns(second):
    """Grammar-v2 widening (round 1): star-literal-star contexts — the
    glibc star-jump surface — post-negation continuations, group-in-segment
    shapes, and multi-run chains, over alphabet {'a', *second*}. Mirrors
    the Phase C corpus3 generator (slot 3.1 ledger)."""
    b = second
    ops = ["@", "?", "*", "+", "!"]
    alts = ["a", b, "*", f"a|{b}", "a|*", "", "a*"]
    pre = ["*a*", f"*{b}*", f"*a{b}*", f"*a*{b}*", "a*a*", "*a?*", "*?a*",
           "**a*", "*a**", "*@(a)*", f"*!({b})a*", f"*a@({b})*",
           f"*a*{b}", f"a*{b}*a*"]
    post = ["", "a", "?a", "a?", "*a", "a*", b, "@(a)", "?(a)" + b, "*",
            "?", "??"]
    seen = set()
    out = []

    def add(p):
        if p not in seen:
            seen.add(p)
            out.append(p)

    for pr in pre:
        for op in ops:
            for alt in alts:
                for po in post:
                    add(pr + f"{op}({alt})" + po)
    for pr in pre:
        for po in post:
            if "(" not in pr + po:
                add(pr + po)
    for chain in (f"*a*{b}*", "*a*a*"):
        for op in ("!", "?", "@"):
            for alt in ("a", "*"):
                for po in ("", "a", "?a"):
                    add(chain + f"{op}({alt})" + po)
    return out


def _subjects(alphabet, max_len):
    return [""] + ["".join(t) for length in range(1, max_len + 1)
                   for t in itertools.product(alphabet, repeat=length)]


def test_composition_corpus_engine_matches_bash():
    """Engine full-match == live bash over the grammar-v2 corpus (one spawn).

    Three buckets: the v1 grammar x {a,b} subjects len 0-3; the widened
    (round-1) grammar x {a,b} subjects len 0-4; the widened grammar's
    disjoint-alphabet mirror x {a,c} subjects len 0-4. bash runs ONE batched
    ``[[`` script from stdin; psh answers in-process through
    match_shell_pattern — the same compiled relation every consumer routes
    through. Agreement-form: bash's answer IS the expectation, so oracle
    drift is visible; the failure message carries the DERIVED cell count."""
    cells = []
    for pats, subs in (
            (corpus_patterns(), SUBJECTS),
            (widened_patterns("b"), _subjects("ab", 4)),
            (widened_patterns("c"), _subjects("ac", 4))):
        cells.extend((p, s) for p in pats for s in subs)
    script_lines = ["shopt -s extglob"]
    for pat, subj in cells:
        script_lines.append(f"[[ '{subj}' == {pat} ]] && echo 1 || echo 0")
    r = _run(run_bash, [], stdin_data="\\n".join(script_lines) + "\\n",
             timeout=120)
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
        f"{len(mismatches)} divergences over {len(cells)} grammar-v2 cells "
        f"(pattern, subject, bash, psh), first 20: {mismatches[:20]}")'''
assert src.count(old) == 1, "edit3"
src = src.replace(old, new)

old = '''@pytest.mark.parametrize("rid,subj,pat,bash_rc", [
    ("H7a", "", "*@(a|*)", 1),
    ("H7b", "a", "*!(a)", 1),
    ("H7c", "", "*!(*)", 0),
])
def test_double_bracket_anchor_rows(rid, subj, pat, bash_rc):
    """The r22 HIGH-7 ``[[`` rows: psh == bash == the measured value.

    Red-on-base: at 29456fdc psh answered the complement of every row
    (slot 3.1 ledger A1). The bash side is ALSO pinned so an oracle-version
    behaviour change fails loudly as oracle drift, not silently."""'''
new = '''@pytest.mark.parametrize("rid,subj,pat,bash_rc", [
    ("H7a", "", "*@(a|*)", 1),
    ("H7b", "a", "*!(a)", 1),
    ("H7c", "", "*!(*)", 0),
    # Round-1 star-jump cells (R7 B-1/B-2): the committed segment placement
    # keeps the negation special away from these entries.
    ("B1", "aa", "*a*!(a)?a", 1),
    ("B2", "aa", "*a*!(a)", 1),
    ("B2b", "ba", "*a*!(a)", 0),
])
def test_double_bracket_anchor_rows(rid, subj, pat, bash_rc):
    """The r22 HIGH-7 + round-1 star-jump ``[[`` rows: psh == bash == the
    measured value.

    Red-on-base: at 29456fdc psh answered the complement of every H7 row
    (slot 3.1 ledger A1); B2 was wrong at base AND at the round-1 tip, B1
    regressed at the round-1 tip (ledger C-0) — all fixed by the star-jump
    port. The bash side is ALSO pinned so an oracle-version behaviour
    change fails loudly as oracle drift, not silently."""'''
assert src.count(old) == 1, "edit4"
src = src.replace(old, new)

old = '''    ("pretest_end", 'v=a; printf "pretest_end=[%s]\\\\n" "${v/%!(a)/Z}"',
     "[a]"),
    ("pretest_end2", 'v=b; printf "pretest_end2=[%s]\\\\n" "${v/%@(|a)/Z}"',
     "[b]"),'''
new = '''    ("pretest_end", 'v=a; printf "pretest_end=[%s]\\\\n" "${v/%!(a)/Z}"',
     "[a]"),
    ("pretest_end2", 'v=b; printf "pretest_end2=[%s]\\\\n" "${v/%@(|a)/Z}"',
     "[b]"),
    # round-1 star-jump consumer cells (R7 B-1/B-2 through ${} and case):
    ("rem_jump", 'v=aa; printf "rem_jump=[%s][%s][%s][%s]\\\\n"'
                 ' "${v#*a*!(a)}" "${v##*a*!(a)}" "${v%*a*!(a)}"'
                 ' "${v%%*a*!(a)}"', "[a][a][a][a]"),
    ("sub_jump", 'v=aa; printf "sub_jump=[%s][%s][%s][%s]\\\\n"'
                 ' "${v/*a*!(a)/Z}" "${v//*a*!(a)/Z}" "${v/#*a*!(a)/Z}"'
                 ' "${v/%*a*!(a)/Z}"', "[Za][ZZ][Za][aa]"),
    ("subc_jump", 'v=aa; printf "subc_jump=[%s]\\\\n" "${v/*a*!(a)?a/Z}"',
     "[aa]"),
    ("case_jump", 'case aa in\\n*a*!(a)) echo "case_jump=M";;\\n'
                  '*) echo "case_jump=N";;\\nesac', "N"),
    ("case_jump2", 'case ba in\\n*a*!(a)) echo "case_jump2=M";;\\n'
                   '*) echo "case_jump2=N";;\\nesac', "M"),'''
assert src.count(old) == 1, "edit5"
src = src.replace(old, new)

old = '''RESIDUAL_DIVERGENCES = [
    ("lex_q1", "[[ 'a' == !(\\"a\\") ]]\\nprintf 'lex_q1=%s\\\\n' $?",
     "1", "0"),
    ("lex_q3", "[[ '*' == !(\\"*\\") ]]\\nprintf 'lex_q3=%s\\\\n' $?",
     "1", "0"),
]'''
new = '''RESIDUAL_DIVERGENCES = [
    ("lex_q1", "[[ 'a' == !(\\"a\\") ]]\\nprintf 'lex_q1=%s\\\\n' $?",
     "1", "0"),
    ("lex_q3", "[[ '*' == !(\\"*\\") ]]\\nprintf 'lex_q3=%s\\\\n' $?",
     "1", "0"),
    # Same lexer-seam family through the CASE consumer (round-1 nit N13;
    # pre-existing at base): the quoted alt reaches the matcher raw.
    ("lex_case_q1", 'case a in\\n!("a")) echo "lex_case_q1=M";;\\n'
                    '*) echo "lex_case_q1=N";;\\nesac',
     "N", "M"),
]'''
assert src.count(old) == 1, "edit6"
src = src.replace(old, new)

old = '''    flagged = ["*!(a)", "*?(a)", "**(a)", "*@(a|*)", "*?@(a)", "a*!(b)c",
               "@(*!(a))", "!(*!(a))a"]'''
new = '''    flagged = ["*!(a)", "*?(a)", "**(a)", "*@(a|*)", "*?@(a)", "a*!(b)c",
               "@(*!(a))", "!(*!(a))a", "*a*!(a)", "*a*b*@(a)?a"]'''
assert src.count(old) == 1, "edit7"
src = src.replace(old, new)

open(p, 'w').write(src)
print("battery restored (7 edits)")
