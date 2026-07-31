#!/usr/bin/env python3
"""INSTRUMENT-GENERATED discharge certification (rulings R11-C, R12-D).

WHY THIS EXISTS. Across rounds 4-5 the CODE held while the RECORD slipped:
rows marked DONE that never landed (twice), ruling halves silently dropped.
The root cause of the false DONEs is specific and worth naming, because it is
what this script replaces: edits applied with `str.replace()` inside a
throwaway python block, printing "N9 done" unconditionally. `str.replace`
NO-OPS SILENTLY when its pattern does not match, so the print reported that
the SCRIPT had run, not that the CHANGE had landed -- and the audit then read
the print as the anchor. A claim's evidence must be a property of the TREE,
never a property of the process that was supposed to change it.

WHY IT WAS REWRITTEN (round 6, ruling R12-D). Version 1 checked the tree and
still certified two false rows, 40/40 green. Checking the tree is necessary
but NOT sufficient, because a row only certifies what its PATTERN proves:

  * row N18 backed the claim "offender rows on BOTH typed arms" with a grep
    for the PRODUCTION ARM's own message text. The arm existed; the offender
    test did not. Deleting the arm left 195 tests green.
  * row N13 backed an ordered COMMENT FIX with a pattern (`seeded from LEXER
    EVENTS`) that was ALREADY PRESENT at abd98d50 -- the very tip round 5
    proved the fix un-landed at. The pattern was disjoint from the change it
    was supposed to prove, so it certified nothing and could never fail.

THE STRUCTURAL CURE, and the reason this script cannot repeat that class:
every row that claims an ORDERED CHANGE carries a `since` SHA, and the row is
checked at BOTH ENDS. A pattern that predates `since` FAILS THE ROW no matter
how green it is at HEAD. Concretely:

  * `grep`  + since -- present at HEAD *and absent at `since`* (an addition
                       that is really an addition);
  * `absent`+ since -- absent at HEAD *and present at `since`* (a removal that
                       is really a removal);
  * `testid`+ since -- the NAMED TEST collects at HEAD and did not exist at
                       `since`; this is the only kind allowed to back a
                       "pin/guard/offender row landed" claim. A claim about
                       tests may never be certified by production text.
  * `test`         -- the whole file collects (module-existence rows only);
  * `anchor`       -- the evidence file exists AND self-stamps a SHA, compared
                       against HEAD (a stale anchor is a false anchor: R4-D).

`since` is the SLOT BASE for slot-wide work, and the DISSOLVED TIP of the
round that ordered the change for round-N fixes -- the tighter the `since`,
the stronger the row.

Exit code is non-zero if any row fails. No completion report without a green
run of this script, published in the ledger.

Usage: python3 certify_ledger.py [--json]
"""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path("/Users/pwilson/src/psh-r2-5")
PROBES = ROOT / "tmp" / "r2-5-probes"

# The two `since` anchors used below.
BASE = "e36116c3"    # slot base (v0.760.0) -- for slot-wide work
R6TIP = "ec99b420"   # tip dissolved by round 6 -- for the R12 fix list
R5TIP = "abd98d50"   # tip dissolved by round 5
R4TIP = "a767f476"   # tip dissolved by round 4
R3TIP = "6a70416e"   # tip dissolved by round 3
R2TIP = "575291a1"   # tip dissolved by round 2
R1TIP = "063815ad"   # tip dissolved by round 1
R7TIP = "30ffa09a"   # tip dissolved by round 7 -- for the R14 fix list
R8TIP = "a801ad1a"   # tip dissolved by round 8 -- for the R15 fix list

HEAD = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                      capture_output=True, text=True).stdout.strip()


def R(rid, kind, target, needle="", since=None, note=""):
    return {"row": rid, "kind": kind, "target": target, "needle": needle,
            "since": since, "note": note}


ROWS = [
    # --- D1/D2/D3: the original three fixes -------------------------------
    R("D1 session from lexer events", "grep",
      "psh/parser/session.py", "_lexer_pending_heredocs", BASE),
    R("D1 regex no longer the session oracle", "absent",
      "psh/parser/session.py", "open_heredoc_specs", BASE),
    R("D2 executable heredoc type", "grep",
      "psh/ast_nodes/redirects.py", "class HeredocRedirect", BASE),
    R("D2 body is required kw-only", "grep",
      "psh/ast_nodes/redirects.py",
      "heredoc_content: str = field(kw_only=True)", BASE),
    R("D2 plain Redirect lost the body field", "absent",
      "psh/ast_nodes/redirects.py", "heredoc_content: Optional[str]", BASE),
    R("D2 typed error replaces late discovery", "grep",
      "psh/io_redirect/file_redirect.py", "class NonExecutableRedirectError",
      BASE),
    R("D2 late-discovery RuntimeError gone", "absent",
      "psh/io_redirect/file_redirect.py",
      "heredoc redirect reached execution without a collected ", BASE),
    R("D3 TokenPart frozen", "grep",
      "psh/lexer/token_parts.py", "@dataclass(frozen=True)", BASE),
    R("D3 Position frozen (R4-A)", "grep",
      "psh/lexer/position.py", "@dataclass(frozen=True)", BASE),
    R("D3 Token.parts coerced to tuple", "grep",
      "psh/lexer/token_types.py", "object.__setattr__(self, 'parts', tuple",
      BASE),

    # --- R7-A / R9-A / R10-A: the lexer table family ----------------------
    # The bare `('<<', TokenType.HEREDOC)` spelling ALSO matches the
    # pre-existing DIGIT-fd table 80 lines up, so it was green at base and
    # certified nothing (the round-6 mis-anchor class, found by re-anchoring).
    # These patterns are ordered pairs unique to the NAMED-fd table, whose
    # neighbours differ between the two tables.
    R("R7-A named-fd `<<`", "grep",
      "psh/lexer/recognizers/operator.py",
      "            ('>|', TokenType.REDIRECT_CLOBBER),\n"
      "            ('<<', TokenType.HEREDOC),\n", R2TIP),
    R("R7-A named-fd `<<-`", "grep",
      "psh/lexer/recognizers/operator.py",
      "            ('<<-', TokenType.HEREDOC_STRIP),\n"
      "            ('>>', TokenType.REDIRECT_APPEND),\n", R2TIP),
    R("R9-A named-fd `<<<`", "grep",
      "psh/lexer/recognizers/operator.py",
      "            ('<<<', TokenType.HERE_STRING),\n"
      "            ('<<-', TokenType.HEREDOC_STRIP),\n"
      "            ('>>', TokenType.REDIRECT_APPEND),\n", R3TIP),
    R("R9-A var_fd threaded (RD heredoc)", "grep",
      "psh/parser/recursive_descent/parsers/redirections.py",
      "var_fd=token.var_fd", BASE),
    R("R10-A operand-less hard error", "grep",
      "psh/parser/recursive_descent/parsers/redirections.py",
      "_operand_less_redirect_error", R3TIP),
    # Re-anchored at R15-B: these three rows matched the arms' OLD message
    # text, which round 8 required rewriting for users. They back "the arm
    # exists" claims, so the pattern must still identify the ARM uniquely --
    # the guard claims are the testid rows elsewhere.
    R("R9-B var_fd route typed", "grep",
      "psh/io_redirect/file_redirect.py",
      'f"here-document `{{{name}}}{rtype}` was never collected. "', R8TIP),
    R("N11 redirect_heredoc direct-call typed", "grep",
      "psh/io_redirect/file_redirect.py", "(redirect_heredoc). ", R8TIP),

    # --- the two arms, and (separately) the GUARDS that prove them --------
    # R12-D: an arm-exists grep may back an "arm exists" claim and NOTHING
    # more. The "offender rows on both arms" claim is backed by the two
    # `testid` rows below it -- that split is the whole lesson of round 6.
    R("N18 operand-less `{v}<<<` ARM exists", "grep",
      "psh/io_redirect/file_redirect.py",
      "has no operand, so there ", R8TIP,
      "arm existence ONLY -- the guard claim is the testid row below"),
    R("N18 offender row for the `{v}<<<` arm (R12-C)", "testid",
      "tests/unit/io_redirect/test_heredoc_executable_type.py"
      "::test_operand_less_here_string_offender_raises_typed_on_the_var_fd_route",
      "", R6TIP,
      "mutation-proved: tmp/r2-5-probes/mutation_herestring_offender.py"),
    R("N18 positive control (operand-BEARING `{v}<<<` still works)", "testid",
      "tests/unit/io_redirect/test_heredoc_executable_type.py"
      "::test_here_string_with_an_operand_is_NOT_an_offender", "", R6TIP),
    R("R11-A offender row for the redirect_heredoc arm", "testid",
      "tests/unit/io_redirect/test_heredoc_executable_type.py"
      "::test_redirect_heredoc_rejects_the_non_executable_state", "", R3TIP),
    R("R11-A direct redirect_heredoc coverage restored", "testid",
      "tests/unit/io_redirect/test_heredoc_executable_type.py"
      "::test_redirect_heredoc_materializes_the_body_on_the_default_fd",
      "", R5TIP),
    R("C1 offender bites at the BUILTIN-STREAM backend too", "testid",
      "tests/unit/io_redirect/test_heredoc_executable_type.py"
      "::test_synthetic_offender_raises_at_the_BUILTIN_STREAM_backend",
      "", R2TIP),

    # --- guards -----------------------------------------------------------
    R("parity guard forward", "testid",
      "tests/unit/lexer/test_fd_prefix_table_parity.py"
      "::test_named_fd_table_covers_the_digit_fd_table", "", R2TIP),
    R("parity guard REVERSE (N3/N16)", "testid",
      "tests/unit/lexer/test_fd_prefix_table_parity.py"
      "::test_digit_fd_table_covers_the_named_fd_table", "", R4TIP),
    R("visitor census not a hand list (N12)", "grep",
      "tests/unit/visitor/test_ast_coverage_matrix.py",
      "_visitors_defining_visit_redirect", R4TIP),
    R("transitive frozen census", "testid",
      "tests/unit/lexer/test_lexical_value_graph_frozen.py"
      "::test_no_unfrozen_dataclass_is_reachable_from_a_lexed_unit", "", BASE),
    R("bounced-row preservation by name", "grep",
      "tests/unit/parser/test_session_lexer_heredoc_equivalence.py",
      "_BOUNCED_ROW_CLASSES", R1TIP),

    # --- docs -------------------------------------------------------------
    # Re-anchored at R14-B/N9: the enumeration was rewritten to SPLIT consumers
    # by which of the module's two jobs they use, because listing the formatter
    # as a scanner consumer (it uses the algebra) and omitting three algebra
    # consumers made the census disagree with itself.
    R("N9 consumers enumerated AND split by job", "grep",
      "psh/utils/heredoc_detection.py", "CONSUMERS, enumerated from a census",
      R7TIP),
    R("N9 the oracle is listed under the ALGEBRA, not the scanner", "grep",
      "psh/utils/heredoc_detection.py",
      "the COMPLETENESS ORACLE (``parser/session.py``)", R7TIP),
    R("N9(a) stale module-docstring oracle claim gone", "absent",
      "psh/utils/heredoc_detection.py", "the completeness\n  oracle here",
      R2TIP),
    R("N9(b) open_heredoc_specs' OWN docstring fixed (R12-B)", "absent",
      "psh/utils/heredoc_detection.py", "CommandAccumulator", R6TIP,
      "the half that was falsely discharged three times"),
    R("N9(b) its true role stated", "grep",
      "psh/utils/heredoc_detection.py",
      "CALL SITES are the cmdhist joiner's two in", R7TIP),
    R("N13(a) session step numbers correct (R12-A)", "grep",
      "psh/parser/session.py", "trial parse at step 5", R6TIP,
      "the pattern round 6 proved predated the change is NOT this one"),
    R("N13(a) stale step-4 comment gone", "absent",
      "psh/parser/session.py", "parse at step 4", R6TIP),
    R("N13(a) stale step-2 heredoc comment gone", "absent",
      "psh/parser/session.py", "a heredoc?\" (step 2", R6TIP),
    R("N13(b) import split unified (R12-A / round-6 NIT 8)", "grep",
      "psh/parser/session.py", "from ..utils import HeredocTermination",
      R6TIP),
    R("N13(b) deep import gone", "absent",
      "psh/parser/session.py",
      "from ..utils.heredoc_detection import HeredocTermination", R6TIP),
    R("N17 io_redirect/CLAUDE.md named-fd forms", "grep",
      "psh/io_redirect/CLAUDE.md", "Named-fd here-documents and here-strings",
      R3TIP),
    R("N4 _try_var_fd_redirect docstring", "grep",
      "psh/lexer/recognizers/operator.py", "``{NAME}<<``", R5TIP),
    R("lexer/CLAUDE.md Position", "grep",
      "psh/lexer/CLAUDE.md", "position.py#Position", BASE),
    R("parser/CLAUDE.md one grammar", "grep",
      "psh/parser/CLAUDE.md", "ONE heredoc grammar", BASE),

    # --- pins (module existence; the CLAIM-bearing rows are testid above) --
    R("PTY pin module", "test",
      "tests/system/interactive/test_heredoc_detection_interactive_pty.py"),
    R("named-fd battery", "test",
      "tests/unit/io_redirect/test_named_fd_heredoc.py"),
    R("executable-type + fd-kind offenders", "test",
      "tests/unit/io_redirect/test_heredoc_executable_type.py"),
    R("declared non-interactive deltas", "test",
      "tests/unit/scripting/test_heredoc_declared_deltas_noninteractive.py"),
    R("equivalence corpus", "test",
      "tests/unit/parser/test_session_lexer_heredoc_equivalence.py"),
    R("frozen value graph", "test",
      "tests/unit/lexer/test_lexical_value_graph_frozen.py"),
    R("fd-prefix table parity", "test",
      "tests/unit/lexer/test_fd_prefix_table_parity.py"),
    R("unclosed-$( EOF delta", "test",
      "tests/unit/scripting/test_heredoc_in_unclosed_substitution_eof.py"),

    # --- the MEDIUM-3 PTY pin and the R12-E combinator half ---------------
    R("MEDIUM-3 PTY pin (the red-on-base battery)", "testid",
      "tests/system/interactive/test_heredoc_detection_interactive_pty.py"
      "::test_interactive_heredoc_detection_matches_bash", "", BASE),
    R("MEDIUM-3 escaped spelling IS a corpus row", "grep",
      "tests/system/interactive/test_heredoc_detection_interactive_pty.py",
      '("escaped_lt", [r"echo \\<<EOF"]', BASE),
    # R12-E's pin, widened at R14-A from the escaped spellings to every family
    # the mechanism can reach. The two rows below are the differential and the
    # literal-value assertion; the third proves the TABLE still carries both
    # answers, so the axis cannot be quietly re-narrowed to one kind.
    R("R14-A diag differential, all families", "testid",
      "tests/unit/scripting/test_heredoc_declared_deltas_noninteractive.py"
      "::test_diagnostic_line_numbers_match_bash", "", R7TIP),
    R("R14-A diag literal line numbers, all families", "testid",
      "tests/unit/scripting/test_heredoc_declared_deltas_noninteractive.py"
      "::test_diagnostic_line_numbers_are_the_expected_literals", "", R7TIP),
    R("R14-A the diag table keeps both answers", "testid",
      "tests/unit/scripting/test_heredoc_declared_deltas_noninteractive.py"
      "::test_the_diag_table_names_both_answers", "", R7TIP),
    R("R14-A subscript-shift family IS in the diag table", "grep",
      "tests/unit/scripting/test_heredoc_declared_deltas_noninteractive.py",
      '(_MOVED, "subscript_shift_valid"', R7TIP),
    R("R14-A the diag table names its CONTROL families", "grep",
      "tests/unit/scripting/test_heredoc_declared_deltas_noninteractive.py",
      '(_CONTROL, "arith_dollar"', R7TIP),
    # --- R15: the ALIAS route (round-8 blockers 1+2) ---------------------
    R("POST-STATE: nothing claims the arm is unreachable (R15-B)",
      "postcheck", "no-unreachable-claim"),
    R("R15-A alias route outcome pinned", "testid",
      "tests/unit/scripting/test_heredoc_alias_route.py"
      "::test_alias_heredoc_outcome_is_report_and_carry_on", "", R7TIP),
    R("R15-A alias limitation reported", "testid",
      "tests/unit/scripting/test_heredoc_alias_route.py"
      "::test_alias_heredoc_reports_the_limitation", "", R7TIP),
    R("R15-B the alias message is written for a user", "testid",
      "tests/unit/scripting/test_heredoc_alias_route.py"
      "::test_the_alias_message_is_written_for_a_user", "", R7TIP),
    R("R15-A alias-vs-bash divergence declared", "testid",
      "tests/unit/scripting/test_heredoc_alias_route.py"
      "::test_divergence_alias_heredoc_body_is_not_collected", "", R7TIP),
    R("R15-A alias controls (non-vacuity)", "testid",
      "tests/unit/scripting/test_heredoc_alias_route.py"
      "::test_controls_are_unaffected_and_match_bash", "", R7TIP),
    R("R15-A R9-B's synthetic-only premise corrected in the guard", "grep",
      "tests/unit/io_redirect/test_heredoc_executable_type.py",
      "UNIVERSE CORRECTION (round-8 blocker 1)", R7TIP),
    R("NIT 7 null-command divergence declared", "testid",
      "tests/unit/io_redirect/test_named_fd_heredoc.py"
      "::test_divergence_null_command_named_fd_keeps_the_descriptor",
      "", R7TIP),
    R("NIT 7 its pre-existence control", "testid",
      "tests/unit/io_redirect/test_named_fd_heredoc.py"
      "::test_the_null_command_divergence_is_pre_existing", "", R7TIP),
    R("NIT 11 consumer grouping no longer asserts a partition", "grep",
      "psh/utils/heredoc_detection.py", "The grouping is NOT a\npartition",
      R7TIP),
    R("N5 frozen-graph corpus is a class, not a line", "grep",
      "tests/unit/lexer/test_lexical_value_graph_frozen.py",
      '("two_heredocs_one_command"', R7TIP),

    # --- POST-STATE rows (R12-D-AMENDED) ---------------------------------
    # These ask the ruling's question of the whole file. Each one would have
    # gone RED on all three occasions the corresponding edit-presence grep
    # went green.
    R("POST-STATE: no oracle-scans-the-text claim survives (N9)",
      "postcheck", "oracle-scan-claim"),
    R("POST-STATE: session step cross-refs match their markers (N13)",
      "postcheck", "session-step-numbers"),
    R("POST-STATE: every latency claim is parser-scoped (R12-E)",
      "postcheck", "latency-claims-scoped"),

    # --- evidence anchors (must self-stamp THIS head) ---------------------
    R("PTY matrix anchor", "anchor", "pty-matrix-final.txt"),
    R("base-vs-tip identity anchor", "anchor", "base-tip-identity-final.txt"),
    R("degenerate sweep anchor", "anchor", "degenerate-sweep-final.txt"),
    R("second-grammar census anchor", "anchor",
      "second-grammar-census-final.txt"),
    R("`{v}<<<` arm mutation-proof transcript", "anchor",
      "mutation-herestring-offender.txt"),
    R("ruff anchor (self-stamped, NIT 11)", "anchor", "ruff-final.txt"),
    R("mypy anchor (self-stamped, NIT 11)", "anchor", "mypy-final.txt"),
    R("full gate anchor", "anchor", "gate-final.txt"),
    R("compare-bash anchor", "anchor", "compare-bash-final.txt"),
    R("R14-A diag-axis sweep anchor", "anchor", "diag-axis-sweep-final.txt"),
    R("post-state historical proof anchor", "anchor",
      "mutation-poststate.txt"),
    R("R15-A alias-axis anchor", "anchor", "alias-heredoc-axis.txt"),
]


# === POST-STATE PREDICATES (ruling R12-D-AMENDED) ==========================
#
# The amendment is sharper than `since` alone, and the difference is exactly
# what fooled three audits: a `since`-checked grep proves MY EDIT LANDED and is
# genuinely new; it does NOT prove the ORDERED POST-STATE holds. An edit can
# land beside a surviving instance of the very text it was ordered to remove --
# which is what happened when the N9 fix landed in the module docstring while
# `open_heredoc_specs`' own docstring kept the stale sentence, and the
# edit-presence grep passed anyway.
#
# A post-state row asks the ruling's question of the WHOLE FILE, never of the
# hunk, so it cannot be satisfied by adding text somewhere else.


def head_text(path):
    """Commit content of *path* at the CURRENT ROOT's HEAD (round-7 nit 16).

    Resolves HEAD dynamically rather than using the module-level constant,
    because `mutation_poststate.py` repoints ROOT at historical worktrees to
    prove these predicates go red there; a pinned SHA would silently read the
    wrong tree's content and turn that proof into a lie. Falls back to the
    working tree only for paths untracked at HEAD.
    """
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()
    r = subprocess.run(["git", "show", f"{sha}:{path}"], cwd=ROOT,
                       capture_output=True, text=True)
    if r.returncode == 0:
        return r.stdout
    p = ROOT / path
    return p.read_text() if p.exists() else ""

def _post_oracle_scan_claim(_row):
    """POST-STATE: no line in heredoc_detection.py claims the completeness
    oracle consumes the text-level SCANNER, and the ALGEBRA consumers it does
    name are real.

    Absence-over-the-file, per R12-D-AMENDED. It must respect a distinction the
    file itself draws: since 2.5 the oracle is NOT a scanner consumer (it asks
    the lexer), but it IS still an ALGEBRA consumer -- `session.py#feed` calls
    `PendingHeredocQueue.feed_line`, the one production caller of
    `heredoc_terminator_matches`. So the lines naming the oracle among the
    terminator-rule sharers are TRUE and must survive; only an AFFIRMATIVE
    scanner claim is forbidden. A predicate that deleted those would trade one
    false statement for another.
    """
    text = head_text("psh/utils/heredoc_detection.py")
    problems = []
    if "CommandAccumulator" in text:
        problems.append("names CommandAccumulator as a seeder")
    for m in re.finditer(r"[^.]*completeness\s+oracle's\s+scan", text):
        if "NOT" not in m.group(0):
            problems.append(f"un-negated scan claim: {m.group(0).strip()[:60]}")
    for path in ("psh/parser/session.py",
                 "psh/scripting/input_preprocessing.py",
                 "psh/lexer/heredoc_collector.py",
                 "psh/lexer/cmdsub_scanner.py"):
        if "feed_line" not in head_text(path):
            problems.append(f"named algebra consumer {path} no longer calls "
                            f"feed_line -- the enumeration went stale")
    return (not problems), ("post-state holds; 4 algebra consumers verified"
                            if not problems else "; ".join(problems))


def _post_session_step_numbers(_row):
    """POST-STATE: every cross-reference to a numbered step in session.py#feed
    agrees with that function's OWN `# N.` markers.

    The ordered change was "the step numbers are correct". A grep for the
    corrected phrase passes with a second stale reference still in the file --
    which is the shape N13 actually had. The mapping is DERIVED from the
    markers rather than hardcoded, so this stays true if steps are renumbered.
    """
    text = head_text("psh/parser/session.py")
    markers = {}
    for m in re.finditer(r"^\s*#\s*(\d)\.\s+(.{0,40})", text, re.M):
        markers[m.group(1)] = m.group(2).strip()
    if len(markers) < 5:
        return False, f"expected 5 step markers, found {sorted(markers)}"
    lex = next((n for n, d in markers.items() if d.startswith("Lex")), None)
    hd = next((n for n, d in markers.items()
               if d.startswith("Open heredoc")), None)
    parse = next((n for n, d in markers.items() if "real oracle" in d), None)
    problems = []
    for phrase, want, what in (
            ("trial parse at step ", parse, "trial parse"),
            ('a heredoc?" (step ', hd, "open-heredoc decision"),
            ("tokens lexed at step ", lex, "the lex"),
            ("captured at step ", lex, "the captured lex error")):
        for m in re.finditer(re.escape(phrase) + r"(\d)", text):
            if m.group(1) != want:
                problems.append(f"{what} cited as step {m.group(1)}, "
                                f"markers say {want}")
    if "parse at step 4" in text:
        problems.append("the original stale phrase is back")
    return (not problems), (f"markers lex={lex} heredoc={hd} parse={parse}; "
                            f"all cross-refs agree"
                            if not problems else "; ".join(problems))


def _post_latency_claims_scoped(_row):
    """POST-STATE (R12-E): every committed statement that the escaped-``\\<<``
    divergence is terminal-only is scoped to ``rd``.

    The ordered change was a NARROWING, and an edit-presence grep for the added
    words would pass even with an unqualified sentence surviving elsewhere in
    the same file. So every occurrence in all three files is checked, and the
    row refuses to pass vacuously if the claim disappears entirely.
    """
    files = ("tests/system/interactive/"
             "test_heredoc_detection_interactive_pty.py",
             "tests/unit/tooling/test_no_direct_spawn_in_oracle_modules.py",
             "psh/parser/CLAUDE.md")
    pat = re.compile(r"observable only at a (?:terminal|prompt)")
    problems, found = [], 0
    for f in files:
        text = head_text(f)
        for m in pat.finditer(text):
            found += 1
            window = text[max(0, m.start() - 400):m.end() + 400]
            if not re.search(r"`?(?:--parser )?rd`?\b", window):
                problems.append(f"{f}: UNSCOPED latency claim at offset "
                                f"{m.start()}")
    if not found:
        return False, "no latency claim found at all -- row would be vacuous"
    return (not problems), (f"{found} occurrences, all parser-scoped"
                            if not problems else "; ".join(problems))


def _post_no_unreachable_claim(_row):
    """POST-STATE (R15-B): no committed text claims the non-executable-heredoc
    arm is unreachable from live input, and no runtime message carries the
    falsified assurance or a raw value repr.

    Round 8 falsified "Every live parse path builds a HeredocRedirect" with
    `alias foo='cat <<EOF'; foo`. An edit-presence grep on the corrected
    sentence would pass with one of the five sites still saying the old thing,
    so this asks the whole question across all of them.
    """
    problems = []
    banned = ("Every live parse path builds a HeredocRedirect",
              "Every LIVE heredoc-aware parse path")
    for path in ("psh/io_redirect/file_redirect.py",
                 "psh/io_redirect/manager.py",
                 "psh/io_redirect/CLAUDE.md",
                 "psh/ast_nodes/redirects.py"):
        text = head_text(path)
        for phrase in banned:
            if phrase in text:
                problems.append(f"{path}: falsified claim still present "
                                f"({phrase!r})")
    # The user-facing hint must exist and must name the cause.
    fr = head_text("psh/io_redirect/file_redirect.py")
    if "_ALIAS_HEREDOC_HINT" not in fr:
        problems.append("the shared user-facing hint is gone")
    for needed in ("ALIAS whose expansion introduces",
                   "Write the here-document directly"):
        if needed not in fr:
            problems.append(f"hint no longer says {needed!r}")
    # And the arms must USE it rather than re-inlining a repr.
    if fr.count("_ALIAS_HEREDOC_HINT") < 4:
        problems.append("not every arm appends the shared hint "
                        f"(found {fr.count('_ALIAS_HEREDOC_HINT')} uses)")
    return (not problems), ("post-state holds across 4 files"
                            if not problems else "; ".join(problems))


POSTCHECKS = {
    "no-unreachable-claim": _post_no_unreachable_claim,
    "oracle-scan-claim": _post_oracle_scan_claim,
    "session-step-numbers": _post_session_step_numbers,
    "latency-claims-scoped": _post_latency_claims_scoped,
}


def at(sha, path):
    """File content at *sha*, or '' when the path did not exist there."""
    r = subprocess.run(["git", "show", f"{sha}:{path}"], cwd=ROOT,
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def collects(nodeid):
    r = subprocess.run([sys.executable, "-m", "pytest", nodeid,
                        "--collect-only", "-q", "-p", "no:randomly"],
                       cwd=ROOT, capture_output=True, text=True)
    # NB: match on the SUMMARY line, not anywhere in stdout -- `-q
    # --collect-only` prints test IDs, and several of this slot's test names
    # contain the word "error", which made the first version of this check
    # report FAIL on two passing rows.
    summary = [ln for ln in r.stdout.splitlines() if "collected" in ln]
    ok = (r.returncode == 0 and bool(summary)
          and "error" not in summary[-1].lower())
    return ok, (summary[-1] if summary else r.stdout[-120:])


def check(row):
    kind, target, needle, since = (row["kind"], row["target"],
                                   row["needle"], row["since"])

    if kind in ("grep", "absent"):
        # Read COMMIT CONTENT at HEAD, not the working tree (round-7 nit 16).
        # A dirty tracked file would otherwise let the certification describe my
        # editor rather than the commit the ledger names -- and "I checked the
        # tree was clean first" is a property of the process, which is precisely
        # the kind of evidence this instrument exists to stop accepting.
        text = at(HEAD, target)
        if not text and not (ROOT / target).exists():
            return False, f"missing file {target} at HEAD"
        present = needle in text
        if kind == "grep":
            if not present:
                return False, f"NOT FOUND at HEAD: {needle!r}"
            if since and needle in at(since, target):
                return False, (f"NOT AN ORDERED CHANGE: pattern already "
                               f"present at {since} -- this row certifies "
                               f"nothing (the N13 class)")
            return True, ("found; absent at " + since if since else "found")
        if present:
            return False, f"STILL PRESENT at HEAD: {needle!r}"
        if since and needle not in at(since, target):
            return False, (f"NOT AN ORDERED REMOVAL: pattern was already "
                           f"absent at {since}")
        return True, ("removed; was present at " + since if since
                      else "absent")

    if kind == "testid":
        ok, detail = collects(target)
        if not ok:
            return False, f"does not collect: {detail}"
        if since:
            path, _, name = target.partition("::")
            if name and name in at(since, path):
                return False, (f"NOT AN ORDERED ADDITION: test {name} already "
                               f"existed at {since}")
        return True, (detail + (f"; new since {since}" if since else ""))

    if kind == "test":
        return collects(target)

    if kind == "postcheck":
        fn = POSTCHECKS.get(target)
        if fn is None:
            return False, f"no such postcheck {target}"
        return fn(row)

    if kind == "anchor":
        p = PROBES / target
        if not p.exists():
            return False, f"missing anchor {target}"
        if HEAD[:8] not in p.read_text():
            return False, f"anchor does NOT self-stamp HEAD {HEAD[:8]}"
        return True, f"self-stamps {HEAD[:8]}"

    return False, f"unknown kind {kind}"


# Claim words that make a row a statement ABOUT TEST CODE. The N18 defect was
# not a typo -- it was a row whose WORDS claimed "offender rows on both arms"
# while its PATTERN read a production file. Care did not prevent it (the row
# passed a hand audit and a 40/40 certification), so the rule is mechanical:
# a row that claims test code must be answered by test code.
# Matched on WORD BOUNDARIES, not as substrings. The first version matched
# substrings and false-FAILed a legitimate row whose id contained "grouping" --
# which contains "pin". An instrument that can produce false FAILs is as
# dangerous as one that produces false PASSes (this script's own B60 lesson),
# and the cure is to make the rule mean what it says rather than to reword the
# row until the rule stops mis-firing.
_TEST_CLAIM_WORDS = ("offender row", "pin", "pins", "pinned", "guard",
                     "guards", "battery", "corpus", "coverage")


def self_check():
    """Structural rules the ROWS table itself must satisfy.

    Runs before any row is evaluated: a certification whose ROWS are malformed
    must not be able to report a green tally.
    """
    problems = []
    for row in ROWS:
        rid, kind, target = row["row"], row["kind"], row["target"]
        claims_tests = any(re.search(rf"\b{re.escape(w)}\b", rid.lower())
                          for w in _TEST_CLAIM_WORDS)
        if claims_tests and kind in ("grep", "absent") \
                and not target.startswith("tests/"):
            problems.append(
                f"{rid!r}: claims test code but reads {target} "
                f"(the N18 class -- use kind=testid or grep into tests/)")
        if kind in ("grep", "absent") and not row["since"]:
            problems.append(f"{rid!r}: tree-change row with no `since` SHA "
                            f"(the N13 class -- unordered patterns certify "
                            f"nothing)")
        if kind == "testid" and "::" not in target:
            problems.append(f"{rid!r}: testid row must name a node id")
    return problems


def main():
    problems = self_check()
    if problems:
        print("ROWS TABLE IS MALFORMED — refusing to certify:")
        for p in problems:
            print(f"  * {p}")
        return 2

    results = []
    for row in ROWS:
        ok, detail = check(row)
        results.append({**row, "ok": ok, "detail": detail})
    failed = [r for r in results if not r["ok"]]
    kinds = {}
    for r in results:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    if "--json" in sys.argv:
        print(json.dumps({"head": HEAD, "rows": len(results),
                          "failed": len(failed), "kinds": kinds,
                          "results": results}, indent=2))
    else:
        print(f"CERTIFICATION at HEAD {HEAD[:8]}")
        for r in results:
            mark = "PASS" if r["ok"] else "FAIL"
            print(f"  [{mark}] {r['row']:56.56} {r['detail'][:64]}")
        print("\nBY KIND: " + "  ".join(f"{k}={v}" for k, v in
                                        sorted(kinds.items())))
        ordered = sum(1 for r in results if r["since"])
        print(f"ORDERED-CHANGE ROWS (checked at both ends): {ordered}")
        print(f"\nROWS {len(results)}   PASSED {len(results)-len(failed)}   "
              f"FAILED {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
