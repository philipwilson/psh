# Ground-Up Reappraisal #17 — psh at v0.600.0

**Date:** 2026-07-03
**Baseline:** v0.600.0 (clean main, 10,467 tests passing at release; 11,125 collected; bash oracle 5.2.26; macOS)
**Method:** 13 independent per-subsystem auditors (~2,900 fresh bash-vs-psh probes), each running a
verification pass over the v0.581–v0.600 campaign fixes in its area before hunting the new frontier —
**plus a second adversarial round**: 7 independent verifiers re-ran every HIGH/MED repro from the seven
round-1 reports, re-read the cited root causes, spot-checked HELD claims, and probed uncovered areas.
Unimplemented bash features (docs/missing_features.md) excluded from grading. Probe batteries +
per-subsystem reports (with verification addenda) preserved under `tmp/probes-r17-*/REPORT.md`.
**Context:** This round is both the verification pass for the complete reappraisal-#16 campaign
(20 releases, v0.581–v0.600) and a fresh deep appraisal. It follows #15's campaign (21 releases,
v0.560–v0.580) — 41 releases of fixes since the last cold look at v0.559.

---

## Verdict

**The #16 campaign held completely: every fix from all 20 releases re-probed HELD, with ZERO
campaign-introduced regressions found — the first reappraisal round with a clean regression slate.**
(Contrast #16, which found the v0.576 fd-misrouting regression.) One previously-deferred item
(external reopen-after-closed-fd) now matches bash outright and comes off the ledger.

Overall grades: **Correctness A− (holding), Elegance A− (holding, trending A).** No subsystem below
B+. The defect frontier has visibly moved out of core semantics — word expansion, quoting, control
flow, redirection targets, trap firing, errexit — which now match bash across thousands of probes,
and into three narrower bands: **(1) enforcement/error paths** (readonly enforcement inside the
arithmetic evaluator, error-message chokepoints not fully adopted), **(2) CLI glue** (the stdin
input channel bypassing visitor modes), and **(3) interactive fidelity** (readline-parity details).

Round-2 verification upheld every round-1 finding: **0 refuted HIGHs**, several findings broadened
(readonly-array bypass covers all mutation forms; positional-`$*` corruption bites under default IFS;
`${x-...}`/`${x+...}` join the quote-removal defect), 4 new findings surfaced by deepen probes, and a
handful of examples corrected (the `+foo()` bash confound; the NBSP repro transcription).

## Grade table (#16 → #17)

| Subsystem | #16 (Corr/Eleg) | #17 (Corr/Eleg) | Movement | Headline |
|-----------|-----------------|-----------------|----------|----------|
| Lexer | A−/A− | **B+/A−** | ↓ corr | Core lexing A-grade; frontier moved to the operand-quoting seam (H5) + backtick `\"` (H6); new heredoc-delimiter charclass hole |
| Parser (RD) | A−/A− | **A−/B+–A−** | ~ | Grammar essentially complete; diagnostics layer (enum leaks, split formats, no depth guard) is the blemish |
| Parser (combinator) | A−/A− | **A−/A−** | held | Zero silent misexecution across ~476+32 three-way probes; two honest-fail parity one-liners |
| Expansion | A−/A− | **A−/A−** | held | Operator matrix near-perfect; positional-`$*` per-element gap (H-adjacent) + tilde boundary cluster |
| Engines (arith / pattern) | A−/A− / B+/A− | **A−/A− / B+/A−** | held | Arith evaluation superb; brace-expansion-inside-`[[ ]]` (H4) keeps pattern at B+ |
| Executor | A−/A− | **B+/A−** | ↓ corr | Two silent-wrong-`$?` families in everyday code (H3, arith-error handling); process architecture verified single-source |
| Core/State | B+/A− | **A−/A−** | ↑ corr | Model bash-faithful across ~225 probes; readonly-array-via-arith (H1) is the one silent hole |
| Builtins | A−/A− | **A−/A−** | held | Strongest the surface has graded; echo/printf escape-dialect cluster is the fresh find |
| I/O Redirect | A−/A− (1 regr.) | **A−/A−** | held, clean | Full 4-path × fd matrix HELD; findings are message-text/fd-numbering only |
| Interactive | B+/A− | **B+/A−** | held | History/expansion engine byte-accurate; `ignorespace` privacy leak (H7) + EOF-policy cluster |
| Scripting | B+/A− | **A−/A−** | ↑ corr | Full errexit minefield + trap firing flawless; frontier = trap *actions* cluster |
| Visitor/Formatter | B+/A− | **A− overall (internals A)** | ↑ | Formatter earns A−: flat-string-AST family closed; stdin CLI glue is the HIGH |
| Cross-cutting | B+/A− | **A−/A−** | ↑ | Meta-test infrastructure verified working; Partial-row guard gap found |

## Verification pass: the v0.581–v0.600 campaign

Every auditor re-probed its subsystem's campaign fixes adversarially (varying quoting, paths, and the
written-to dimension that caught v0.576). Result: **all HELD, all 13 subsystems, no regressions.**
Highlights: the v0.581/v0.588 I/O fixes verified across the full builtin/function/compound/external ×
written-fd matrix (31/31); the v0.600 CRLF-heredoc repair is line-boundary-only (no data loss) and
notably *more* robust than bash on mixed line endings; the v0.583 IFS seeding survives save/restore
round-trips; v0.590 int64 + base-N errors match bash byte-for-byte; v0.592's `f() [[ ]]` fix held for
the RD parser (the combinator needs the same one-token fix — F-C1 below).

Meta-fixes verified rigorous: mypy single-glob genuinely covers all 240 files (guarded); conformance
meta-test rejects vacuous probes; golden corpus healthy (578 cases, 0 duplicates); README statistics
exactly accurate.

---

## Findings

### HIGH (7)

**H1 — Readonly array elements are silently writable through every arithmetic entry point.**
*(4 agents: core, executor, engines, builtins; round-2 verified + broadened.)*
`readonly -a a=(1 2); (( a[0]=9 ))` / `$((a[0]=9))` / `let 'a[0]=9'` — and every mutation form
(`(( a[0]++ ))`, `(( a[0]+=5 ))`, `(( ++a[1] ))`) — silently write, indexed AND associative
(bash: `a: readonly variable`, rc 1, unchanged). Silent even under strict-errors. Root:
`psh/expansion/arithmetic/evaluator.py:143` `set_array_element` mutates `var.value.set(...)`
(~:159–161) with no `is_readonly` check; the parallel SimpleCommand path (`psh/executor/array.py:252`)
checks correctly, and round-2's control group proved the nameref fallthrough path checks too — the
hole is exactly this branch. **Fix:** enforce readonly in `set_array_element` (raise
`ShellArithmeticError(f"{name}: readonly variable")`, mirroring the ArraySubscriptError conversion);
structurally, converge on ONE core set-array-element-with-enforcement API used by both callers.

**H2 — Visitor/analysis modes on stdin EXECUTE the input instead of analyzing it.**
`printf 'echo SIDEEFFECT\n' | psh --security` runs the script (also `--format`, `--lint`,
`--metrics`); `--security -c ...` and script-file forms are correct. `--security` executing untrusted
input defeats the mode's purpose. Root: `psh/__main__.py:343-365` stdin branch never checks
`visitor_mode` (the -c and file branches do, :321/:337). Related MED folded into the same fix:
`--validate` on stdin "works" only via a second divergent line-by-line implementation inside
`source_processor.py` (:92-96, :116-122, :284-295) that prints the syntax error AND "No issues found -
AST is valid!" with exit 0. **Fix:** extract one `handle_visitor_mode_for_content()` chokepoint called
from all three entry sites; the divergent validate path then becomes dead code — delete it.

**H3 — `break`/`continue` reached via `&&`/`||` reports a stale `$?`.**
`for i in 0 1 2 3; do [ $i -ge 2 ] && break; done; echo $?` → bash 0, psh 1 (also while/until/
arith-for, and `continue`). Bash truth table (independently re-derived in round 2): a successful
break/continue is a command that RESETS `$?` to 0. psh raises `LoopBreak(level)` with
`exit_status=None` (`psh/builtins/loop_control.py:108/:135`) and the loop's `_break_status`
(`psh/executor/control_flow.py:121-125`) falls back to the PREVIOUS iteration's status (`:293` never
completed on the breaking iteration). Only bites on a non-first iteration after a prior failure —
which is exactly why 34 existing loop-control tests pass. **Fix:** raise with `exit_status=0`; give
`LoopContinue` a status field; pin in golden_cases.yaml.

**H4 — Brace expansion runs inside `[[ ]]`, hard-breaking the regex-interval idiom.**
`[[ 192 =~ ^[0-9]{1,3}$ ]]` → hard parse error rc 2 (bash: matches); `[[ ab == a{b,c} ]]` and range
braces `{1..3}` likewise. Confined to `[[ ]]` (case patterns and assignments are correct). Root:
`psh/expansion/brace_expansion_tokens.py` `TokenBraceExpander` tracks an assignment zone but has no
DOUBLE_LBRACKET..DOUBLE_RBRACKET region (`_reset_types` :69-79, `_word_like` :60-67). Same
"context-not-fed-to-token-transforms" family #16 named the top systemic gap. **Fix:** suppress brace
expansion between `[[` and `]]` (a region flag of the same shape as the existing assignment zone).

**H5 — Parameter-expansion value-word quote/escape removal is incomplete; `:=` stores a corrupted value.**
`${x:-a"b"c}` → `a"b"c` (bash `abc`); `${x:-"$HOME"/bin}` keeps quotes; `${x:-a'$y'b}` expands inside
single quotes AND keeps them; `${x:="a"b}` **stores** `"a"b` (data loss); round-2 broadened to the
no-colon forms `${x-...}`/`${x+...}`. Whole-value-quoted defaults work (why it survived 16 rounds).
Root: `psh/expansion/operands.py:38` `_expand_operand` strips only a whole-operand quote pair; the
correct quote-by-quote walk already exists at `operands.py:218` (`_expand_pattern_operand` — why
`${v#"pat"}` is fine). **Fix:** converge the two walkers (quote-aware walk minus glob-escaping,
threading the enclosing-dquote context).

**H6 (leaning MED) — Backtick body inside double quotes doesn't unescape `\"`.**
`echo "`echo \"q\"`"` → psh `"q"` (bash `q`). Contrasts verified: bare backticks and `$()` in dquotes
both correct — precisely backtick-inside-dquotes. Root: `psh/lexer/expansion_parser.py:317` unescape
set is `` `$\ `` only; `quote_context` is threaded in (quote_parser.py:161) but never consulted — a
live dead-parameter. **Fix:** when quote_context is `"`, add `"` to the unescape set.

**H7 — `HISTCONTROL=ignorespace` silently broken in real use (privacy leak), masked by a
false-positive test.** Typing `␣echo secret` records it (bash drops it). Root:
`psh/scripting/source_processor.py:233` calls `add_history(command_string.strip())` — the strip
removes the leading space BEFORE the ignorespace check (`history_manager.py:101`) can see it. The
existing test drives the leaf method directly, bypassing the stripping caller (same false-positive
shape as #13's nested-`$LINENO`). **Fix:** pass the un-stripped string; normalize after the semantic
check; test through `run_command`.

### MED (clustered)

**Arithmetic error-handling family** *(one chokepoint fix)*: readonly scalar in `(( r=9 ))` escapes as
`unexpected error` and aborts `-c` lists (`executor/core.py:398-420` catches only
ValueError/ArithmeticError); same at all three C-style-for arithmetic sites
(`control_flow.py:328/:347/:368`); `execute_for` misses NamerefCycleError (:287); ternary
middle-branch rejects comma expressions in EVERY consumer (`arithmetic/parser.py:94`,
`parse_ternary`→`parse_comma`); and — round-2's new find — **arithmetic expansion errors
(`$((1/0))`) abort a script FILE where bash continues** (`command.py:529-534` sys.exits under
script mode), refuting the notion that the expansion path was the correct reference. **Fix:** one
`arithmetic_error_to_status()` helper adopted by every arithmetic surface, with
report-rc1-continue semantics in all input modes.

**Trap-action cluster** *(scripting)*: `return`/`break`/`continue` inside a trap action are swallowed
by the blanket `except Exception` at `trap_manager.py:263` (wrong control flow + spurious
`trap: error executing trap` leak — the highest-value scripting fix); `$BASH_COMMAND` is never
populated (grep-empty; DEBUG/ERR call sites exist); RETURN trap still rejected (known-deferred
since #14; `_PSEUDO_SIGNALS` already reserves it); DEBUG fires one fewer time on function entry
under functrace.

**Raw-Python-repr diagnostic family** *(io + builtins)*: function-call and builtin-in-pipeline
redirect-setup failures leak `[Errno N] ...` reprs — the FD_LEVEL_WINDOW path is the one of four
dispatch sites not routed through `format_redirect_error` (`command.py:683` has no try/except);
`exec` failure messages hand-roll strings and leak `[Errno 13]` instead of using the v0.598
`report_exec_failure` chokepoint (`builtins/core.py:217-222`); `read` after `exec 0<&-` leaks a raw
EBADF repr; empty-string redirect targets produce three different malformed messages
(`manager.py:112` `if target:` falsy-empty bug). **Fix:** route all four dispatch sites through the
documented one-message-shape; `if target is not None`.

**Recursion ceiling** *(executor + scripting + crosscut)*: function recursion caps at ~40–90 (bash
5000+), surfaces misleading "arithmetic error: expression too deeply nested" from whichever frame is
deepest, and RecursionError is missing from `_EXPECTED_SHELL_ERRORS` (`internal_errors.py:53`) so
strict-errors mode (the suite default) emits a raw Python traceback. Statement parser also lacks the
depth guard the arithmetic parser has (~90-deep nesting → RecursionError; flat chains are safely
iterative). **Fix:** raise the interpreter limit + classify RecursionError as expected + convert at
the function-call boundary (implicit FUNCNEST); add the parser depth guard.

**Positional/tilde expansion cluster** *(expansion; round-2 broadened)*: value-operators on `"${*}"`
apply to the IFS-joined string, not per-element — case-mod and substitution families missing from the
per-element branch (`variable.py:209-229`); anchored substitutions diverge under DEFAULT IFS
(`"${*/#ab/X}"`), so promote toward HIGH; `$@` and array `[*]` paths are correct — classic divergent
path. Tilde: prefix not terminated by `:` (`tilde.py:55/:28`) and wrongly expanded when adjacent to
quoted/expansion parts (`word_expander.py:191-193`); both share one boundary rule that should live in
one helper.

**echo/printf escape dialects** *(builtins)*: `\c` short-circuits BEFORE processing earlier escapes
(`echo -e 'a\tb\cd'` leaves `\t` literal); octal dialects conflated both directions (`printf '%b'
'\41'` literal — bash 0x21; `echo -e '\101'` over-interprets — bash literal). One root:
`escapes.py`'s multi-pass str.replace helper (+ `\x01BACKSLASH\x01` placeholder hazard). **Fix:** one
left-to-right dialect-parameterized scanner (printf_formatter's `_process_format_escape` is the model).

**Script-fd placement** *(io)*: script-file mode parks the source fd on fd 10 — exactly bash's
`{var}` allocation base — causing `exec {fd}>/dev/null` → 11 (bash 10) and spurious EBADF rc 1 when a
script uses `exec 10>&-`. Since the script is eagerly read at load, **close the fd after
`_load_lines()`** and retire the `_relocate_high` hack entirely.

**Parser diagnostics + robustness** *(RD)*: bare `}` at command position silently partial-executes a
bash-rejected program (`helpers.py:23/29` RBRACE in WORD_LIKE); parse-error cluster — raw
`TokenType.THEN` leaks on the most common beginner mistakes (`context.py:104`), suggestions
string-match the leaky format (:172), two error-render formats, fragment-relative `(line 1, ...)`
(:126); `! time cmd` / `time time` / `cmd | time cmd` rejected (fixed-order prefixes,
`commands.py:336`); function-name validation bidirectionally off (`a=b()` accepted + phantom
function; `foo+bar()` rejected).

**Heredoc edges** *(lexer; round-2 new)*: delimiters with punctuation/glob chars truncated or
unrecognized (`<<E*F` stores delimiter `E` → silent empty body; `<<@X` not a heredoc at all) —
`HEREDOC_MARKER_RE` charclass (`heredoc_detection.py:24`) vs bash's any-non-blank, a 3-site agreement
change; unterminated heredoc yields silent empty body instead of bash's content-to-EOF + warning
(`heredoc_collector.py:144`).

**Lexer whitespace over-breadth**: NBSP/FF/VT/CR and all Unicode Z* treated as token separators
(`unicode_support.py:59`) — `echo a<NBSP>b` splits into two words (copy-paste hazard); bash uses
space+tab. Restrict to `' \t'` (also a hot-loop win: frozenset vs unicodedata).

**Interactive policy cluster**: `set -o ignoreeof` accepted but a no-op (Ctrl-D always exits;
`repl_loop.py:72-74`); no "There are stopped jobs." exit guard (`builtins/core.py:29-59` + REPL EOF —
one shared should-we-exit chokepoint closes both); kill-ring doesn't coalesce consecutive kills
(`edit_buffer.py:141+`); meta-word ops use whitespace not alnum boundaries (`edit_buffer.py:108-194`).

**Combinator parity one-liners**: `f() [[ ... ]]` body rejected — add DOUBLE_LBRACKET to the guard
tuple (`structures.py:119`); `! ! cmd` — loop the `optional(exclamation)` (`pipelines.py:88`). Both
honest-fail; also broader contexts (`if ! ! true`, pipelines).

**Assorted**: fg-pipeline LAST-member signal death unreported (`pipeline.py:281-317`); `trap '' SIG`
lost across the direct `exec` builtin for managed signals (`builtins/core.py:216` — reconciliation
exists only in the forked-child policy); `declare -n` accepts invalid targets silently
(`function_support.py:298-303`; bash uses two distinct messages); `test`/`[` too-many-arguments
correct rc 2 but SILENT (`test_command.py:192-193`); globstar `**` traverses symlinked dirs
(`glob.py:132`, Python glob semantics — converge the three directory walkers);
`${#arr[@]}` on an unset array doesn't trigger `set -u`.

**Docs/meta cluster** *(crosscut)*: FUNCNAME ch17 row is a stale "Partial" (full stack works) and the
staleness meta-test doesn't guard Partial rows — extend it (highest-leverage meta fix); failglob
under `-c` diverges + `GlobNoMatchError` docstring half-true (`exceptions.py:104`); expand_aliases
non-interactive divergence deliberate but undocumented for users (`shell.py:359-370`); coproc missing
from missing_features.md; stale xfail reason strings in test_history.py.

### LOW (sample)

Double `^C` on interrupt at prompt; PS1 `\j`/`\l`/`\D{}` literal; completion gaps (no command/$var
completion — the known complete/compgen roadmap); `[[ str < str ]]` byte-vs-locale collation flips
booleans in default locale (elevates the LC_COLLATE deferral's visibility); `${v:}` error parity;
empty `=~` regex; `$((++5))`; declare -p assoc key order + control-char quoting presentation;
cmdsub NUL retention; `$LINENO` on continuation lines; alias-of-keyword strictness; `--validate`
exit codes; DebugASTVisitor near-dead (retire); arith error-message wording drift; help/type wording;
`psh:` vs `bash: line N:` prefix (documented-deferred, ~39 sites; one prefix helper would close it).

### Byte-model cliff (deferred M8, new evidence)

`printf '\uD800'` hard-fails with a Python codec error ("surrogates not allowed") — the str-based
byte model's sharpest edge yet observed (`printf '\xff'` emits 2 UTF-8 bytes vs bash's 1). Still
architectural/deferred, but the surrogate crash is a genuine crash cliff worth a guard.

---

## Known-deferred ledger status

RESOLVED (off the ledger): external-command reopen-after-closed-fd (now matches bash).
STILL OPEN (re-confirmed, unchanged): declare -g NAME+=value over a local shadow; `((cmd);cmd)`
disambiguation; time -p on compounds; function-NAME-no-parens non-brace bodies; C-locale/LC_COLLATE
collation (now with the `[[ < ]]` boolean evidence); test underscore digit-separators; declare -i
bad-assign fatal-vs-continue; @A/@a on unset elements; pushd -n edges; type -P hashed; HISTSIZE=0
save path; append-only history vs truncate-on-assignment; wcwidth; vi repeat counts; `[ -o X -a -o X ]`.
RETURN trap: promoted from deferred to the Tier-2 trap cluster (infrastructure half-exists).

## Themes

1. **The campaign discipline works.** 41 releases of fixes, re-probed adversarially by 13 auditors and
   7 second-round verifiers: zero regressions. The truth-table-first + adversarial-verify + serial-
   integration pattern is validated; the pins are catching what they were designed to catch.
2. **The frontier moved from semantics to enforcement and glue.** Core word expansion, control flow,
   redirection, trap firing, and errexit now match bash near-universally. What's left concentrates in
   enforcement checks skipped on secondary paths (H1), error-path rendering (the repr-leak family),
   CLI wiring (H2), and readline-fidelity details.
3. **The second divergent path is still the #1 defect factory — but now in error/enforcement code.**
   H1 (array.py checks, evaluator doesn't), H5 (two operand walkers), H2's validate twin, exec vs
   report_exec_failure, FD_LEVEL_WINDOW vs the other three dispatch sites, echo-vs-printf dialects.
   The established antidote (converge on one chokepoint, add a drift-lock) applies directly.
4. **False-positive tests that drive leaf methods instead of real entry points** masked H7 (and H3's
   coincidental passes). When pinning behavior, pin through `run_command`/the CLI, not the helper.
5. **The meta-test/drift-lock investment is paying off** (adopt(), option registry, mypy glob, visitor
   coverage matrix all verified genuinely rigorous) — and should be extended to the two gaps found:
   Partial compatibility rows and deliberate-divergence documentation.

## Recommended next tier

**Tier 1 (HIGH, roughly file-disjoint clusters):**
1. H1 readonly-in-arithmetic enforcement (one core API; unlocks the M-cluster's readonly scalar too) —
   `expansion/arithmetic/evaluator.py` + `executor/core.py`.
2. H2 stdin visitor-mode chokepoint + delete the divergent validate path — `__main__.py`,
   `source_processor.py`.
3. H3 break/continue exit-status — `builtins/loop_control.py`, `executor/control_flow.py`.
4. H4 brace-expansion `[[ ]]` region — `expansion/brace_expansion_tokens.py`.
5. H5 operand quote-walk convergence — `expansion/operands.py` (+H6 one-liner in
   `lexer/expansion_parser.py`).
6. H7 ignorespace strip-ordering — `scripting/source_processor.py` (+ entry-path test).

**Tier 2 (MED clusters):** arithmetic-error chokepoint (incl. script-abort + ternary-comma);
trap-action cluster (control-flow re-raise, $BASH_COMMAND, RETURN); repr-leak family (4 sites + one
message ladder); recursion ceiling + taxonomy + parser depth guard; positional-`$*` per-element +
tilde-boundary helper; echo/printf escape scanner; script-fd eager close; parser `}` +
diagnostics cluster; heredoc delimiter charclass + unterminated warning; whitespace set; interactive
policy cluster; combinator two one-liners; globstar walker convergence; pipeline signal report;
trap-across-exec; declare -n validation; test too-many-args; docs/meta cluster (Partial-row guard
first).

**Deferred (unchanged posture):** byte-model M8 (add a surrogate-crash guard), locale collation,
wcwidth, vi repeat counts, ((cmd);cmd), SHELLOPTS/BASHOPTS, caller/enable, DebugASTVisitor retirement.

## Probe/coverage summary

~2,900 fresh probes round 1 (lexer ~460×29 batteries; RD ~280; combinator ~476 three-way; expansion
~540×16; engines ~470; executor ~190; core ~225; builtins ~370×15; io ~290×50 scripts; interactive
~80 PTY/in-process assertions; scripting ~160; visitor ~275 incl. 178-case idempotence corpus;
crosscut ~30 doc claims + full mypy/ruff/meta-tests) + round-2 verification probes across all seven
round-1 reports (32-probe combinator deepen, 12k-launch stress controls, etc.). All probe scripts
re-runnable under `tmp/probes-r17-*/`.

*Operational note:* rounds 1–2 of this appraisal were repeatedly killed by a macOS 26.5.1 bug —
`/bin/bash`/`/bin/zsh` segfaulting intermittently at exec under heavy process churn, taking the
hosting session down (diagnosed against crash reports; psh and the Homebrew oracle exonerated). The
26.5.2 update fixed it: the final 13-agent parallel wave ran to completion with zero failures.
