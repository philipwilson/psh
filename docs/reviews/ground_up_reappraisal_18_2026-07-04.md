# Ground-Up Reappraisal #18 — psh v0.617.0

**Date:** 2026-07-04 · **Oracle:** bash 5.2.26 (`/opt/homebrew/bin/bash`, macOS arm64)
**Method:** 14 first-round auditors (13 per-subsystem + 1 dedicated verifier for an
independent external review) — ~5,600 bash-diffed probes through the real CLI — followed by a
**full second adversarial round**: 8 verifiers re-ran every HIGH/MED repro, read every cited
root cause in source, re-derived the bash truth tables independently, and spot-checked
positive ("this works") claims. Per-subsystem reports live in `tmp/probes-r18-*/REPORT.md`
with probe batteries alongside; verifier verdicts in `tmp/probes-r18-verify-*/VERDICT.md`.
This round additionally cross-checked an independent external review
(`docs/reviews/codebase_appraisal_2026-07-04.md`) claim-by-claim — see §5.

---

## 1. Executive verdict

**Correctness A− (holding) · Elegance A− (holding). No subsystem below B+.**

The v0.601–617 campaign held completely: **zero regressions found in 17 releases of fixes**
(every recently-fixed area was re-probed adversarially — CRLF, brace-in-`[[ ]]`,
backtick-in-dquotes, ignorespace, stdin visitor modes, discard-line arithmetic,
lazy `$BASH_COMMAND`, jobs-guard, `"${*^}"`, time-after-pipe all HELD). For the first time in
eighteen rounds, the **non-interactive engine produced zero crashes and zero hangs across the
entire probe corpus** (~5,600 probes, plus a 500-expression arithmetic fuzzer and a
1,250-case assignment fuzzer that found *zero* divergences). The two crash-class items left
are a known stdin-decode traceback (2-line fix) and one interactive termios defect.

The finding mass has visibly moved outward again: from core semantics (#15), through
enforcement/error paths (#16–17), to **process/fd edges, feature-completeness gaps, and
assurance infrastructure**. 6 HIGH (vs 7 in #17), all verified, none refuted; ~35 verified MED.

| Subsystem | #17 (Corr/Eleg) | **#18 (Corr/Eleg)** | Δ | HIGH/MED |
|---|---|---|---|---|
| Lexer | B+ / A− | **A− / A−** | ↑ | 0/1→LOW |
| Parser (RD) | A− / B+–A− | **A− / A−** | ↑eleg | 1/2 |
| Parser (combinator) | A− / A− | **B+ / B+** | ↓ | 0/3 |
| Expansion | A− / A− | **A− / A−** | = | 0/2 |
| Engines (arith+pattern) | A−,B+ / A− | **A− / A−** | ↑pattern | 0/5 |
| Executor | B+ / A− | **B+ / A−** | = | 2/3 |
| Core/State | A− / A− | **B+ / A−** | ↓ | 1/6 |
| Builtins | A− / A− | **A− / A−** | = | 0/6(+1) |
| I/O & Redirection | A− / A− | **A− / A−** | = | 1/3 |
| Interactive | B+ / A− | **B+ / A−** | = | 1/5 |
| Scripting/CLI | A− / A− | **A− / A−** | = | 0/3 |
| Visitor/Formatter | A− / A−–A | **A− / A−** | = | 0/1 |
| Cross-cutting | A− / A− | **A− / A−** | = | 0/2 |

Grade-movement notes: the **lexer** finally earned its A− back (zero HIGH, all historical fix
areas held, ~460 adversarial probes clean). The **combinator** dropped on drift, not decay —
three undocumented parity gaps opened silently as RD grew (all honest rc-2 rejects; one is
the v0.613 `time`-mid-pipeline feature that never got a parity case), plus the honest
observation that its grammar modules are "recursive descent in disguise" that barely compose
the A-grade combinator algebra in `core.py`. **Core** dropped on one genuinely bad HIGH
(array wipe, below) plus an attribute-plumbing cluster with a duplicated helper at its root.

## 2. Verification-round outcomes (why these findings are trustworthy)

8 verifiers re-ran ~45 findings: **0 refuted**, and the round *earned its keep* four distinct ways:

- **3 wrong fixes prevented before they shipped:**
  1. engines MED-2's proposed `arith_assignment_discard` routing would have killed whole
     eval/`-c` strings — readonly-in-`$(( ))` actually follows the word-arith
     (`fatal_expansion_status`) model. The report's supporting bash claim about `declare -i`
     was also false.
  2. builtins MED-3's literal `cd ""` short-circuit would have regressed bash's
     CDPATH-empty-search (`CDPATH=/usr; cd ""` legitimately cds to /usr — in psh today too).
  3. io MED-3's fix targeted the wrong subsystem entirely — `[[ -e <(cmd) ]]` fails because
     `[[ ]]` **tokenizes `<(cmd)` as literal text** (never builds a ProcessSubstitution
     node); the proposed `process_sub_scope` wrap could not have worked.
- **1 new defect from positive-claim spot-checks:** `read -t` abandons its deadline once ≥1
  byte is buffered on a non-tty (bash 0.34s vs psh 5.38s, rc 1 not 142; affects plain/`-n`/
  `-N`/`-d`) — hid behind the auditor's "read: clean" grade, and independently corroborates
  the external review's claim 3a.
- **~8 blast-radius corrections**, all wider: array-wipe reaches the tempenv path
  (*permanent* destruction where bash is temporary); bg-trap failures extend to HUP/USR2 and
  to bg-subshell EXIT-on-signal-death; the case-charclass mis-lex covers trailing-glob and
  nested forms; `-aA` corruption round-trips into *neither* shell; `[ -x DIR ]`-class breakage
  got two independent "promote toward HIGH" recommendations; the `read -s` hang is harder to
  escape than reported (Ctrl-C/Ctrl-D are swallowed — `setraw` clears ISIG/ICANON too).
- **1 downgrade:** the lexer's same-line-alias MED is already documented in ch17 as an
  intentional educational choice (auditor missed it) → LOW/documented.

## 3. HIGH findings (all verifier-confirmed)

**H1 — Scalar assignment to an existing array silently destroys it.** `a=(1 2 3); a=x` wipes
all elements and leaves a corrupt ARRAY-attributed scalar (bash: assigns `a[0]`, keeps the
rest). Verified wider: `declare a=x`, `read a`, function-local arrays — and worst,
`a=x cmd` (tempenv) destroys the array **permanently** where bash's effect is temporary.
Root: `psh/core/scope.py:386` blind value overwrite. The verifier traced the one-line
chokepoint fix (scalar→element-0, preserve container) through the tempenv apply/restore
path and proved it sufficient for every variant. *(core)*

**H2+H3 — The background-job trap cluster.** Traps set *inside* any backgrounded
subshell/brace/function never fire (TERM/INT/USR1/HUP/USR2 — default disposition or silent
swallow instead), and EXIT traps in bg brace/functions are dropped (bg subshells drop them
too on untrapped-signal death). Inherited-trap reset behavior is *correct* (matches bash);
external children are correct — the gap is precisely that the in-process bg child body lacks
the trap-firing/pending-pump discipline the main shell already has. One shared child-body
trap runner fixes the entire cluster. Roots: `child_policy` SIG_DFL reset never re-armed on
body re-trap; `process_launcher.py:313-317` finally never calls `execute_exit_trap`.
Related MEDs (same fix campaign): bg stdin should be `/dev/null` (POSIX async rule — psh bg
jobs steal parent stdin), bg SIGINT/SIGQUIT-ignore missing, `wait <reaped-pid>` forgets the
remembered status. *(executor)*

**H4 — Parenthesized subexpressions in C-for headers fail to parse.**
`for ((i=0; i<(n-1); i++))` — plausible everyday bash — aborts the whole script with a parse
error. RD-only: **the educational combinator parser handles it correctly.** Root: three
arithmetic-section collectors with two stop strategies; the `;`-terminated ones treat any
balanced `)` at depth 0 as a terminator (`arithmetic.py:85` + `token_stream.py:247`
post-decrement re-check), compounded by greedy `))` lexing. Fix = consolidate onto the
peek-based `_double_rparen_stop` discipline (also the top parser elegance item). *(parser-rd)*

**H5 — Redirect fds are close-on-exec when `open()` lands on the target fd.**
`cat /dev/fd/3 3<data` → `Bad file descriptor`; same for `paste … 3<a 4<b`, exec
reopen-after-close of std fds, and `exec 3>o3` inheritance. Trigger verified precisely: fires
when the target fd equals the lowest free fd (the fd-3/4 idioms; `exec 200>lock` is safe).
Root: `_dup2_preserve_target`'s `opened==target` shortcut skips the `dup2` that would have
cleared O_CLOEXEC (PEP-446 mechanics verified per-syscall; the `{var}>` path is immune via
F_DUPFD). One-line fix: `os.set_inheritable(target_fd, True)` in the shortcut.
Related MED: `exec >&-` after `exec >file` never reaches the Python stream, so builtins keep
writing to the old file — the "close must reach the stream universe" primitive exists twice
(builtin, compound) and is missing its third copy (exec). *(io)*

**H6 — Interactive `read -s` hangs on Enter, and Ctrl-C can't rescue it.** The canonical
`read -sp "Password: " pw` never returns: `tty.setraw` clears ICRNL (Enter's `\r` never
becomes the `\n` delimiter) *and* ISIG/ICANON — so Ctrl-C raises no SIGINT and Ctrl-D is not
EOF; both are swallowed as password characters. Only a literal Ctrl-J escapes. 100%
deterministic under two independent pty harnesses. bash stays canonical with only ECHO
cleared — that's the fix. Existing read -s tests exercise only the non-tty path. *(interactive)*

**P1 — promotion candidate (two verifiers concur):** `-r`/`-w`/`-x` are false for **all
non-regular files including directories** — `[ -x /usr/bin ]`, `[ -w /tmp ]`, `[ -r . ]`,
`[[ -r /dev/null ]]` all wrong. One code path (`test_command.py:246/249/252` — an
`os.path.isfile` guard where `os.access` alone is correct), shared by `test`/`[`/`[[`.
Everyday-idiom breakage; fix is deleting the guard.

## 4. MED findings (verified) — by fix-shaped cluster

**Arithmetic error-path edges** *(engines — the strongest subsystem otherwise: 1,750 fuzz
cases clean, full 64-bit/base/precedence/discard-line parity)*:
compound assignment reads LHS after RHS side-effect (`$((c+=c++))` → 11 vs bash 10; read
current *before* evaluating RHS); readonly-in-`$(( ))` continues the line where bash
discards (route via `fatal_expansion_status` — **not** assignment-discard); self-referencing
expression vars (`x="x+1"; ((x))`) hit Python's RecursionError as "unexpected error" and
abort the line (bash: bounded "expression recursion level exceeded", rc 1, continues — add a
depth counter, which also removes an internal-error leak); `${a[1//]}` on an unset array
never validates the subscript (bash errors + discards); multi-line `eval` discards the whole
string on a word-arith error instead of resuming at the next line (source already does this
right — route eval through the same line-oriented processor).

**test/[/[[ semantics** *(builtins)*: `-nt`/`-ot` lack bash's existence-asymmetry — breaks
the `[[ $src -nt $dst ]]` rebuild idiom — and the logic is **duplicated identically-buggy in
two files** (`test_command.py` + `utils/file_tests.py` used by `[[ ]]`); POSIX 3/4-arg
disambiguation wrong (`test ! = x` → rc 0 *with* an error printed; binary-`$2` must win);
plus P1 above.

**Core attribute plumbing**: assoc `+=`/reassign leaks a spurious `-a` (`declare -aA`,
re-inputtable into neither shell) — two array-creation paths disagree on the attribute
invariant; `local -ul` uppercases via a **duplicate divergent `_apply_attributes`**
(`builtins/shell_state.py:322` vs the correct `scope.py:507` chokepoint — delete the copy);
`declare -g`/`export` of a tempenv-collided name is discarded on function return (restore()
clobbers the body's global write; also with a `local` shadow); `m[""]=x` accepted (bash:
bad subscript; LOW-defensible); UID/EUID/PPID not readonly; HOSTNAME/OSTYPE/MACHTYPE/
HOSTTYPE/**BASHPID**/SRANDOM absent.

**Parser/lexer narrow fixes**: empty/degenerate `[[ ]]` operands accepted (`[[ ! ]]` silently
rc 0; the empty-test fallback fires only for operand-directly-on-`]]` — replace with the
existing "Expected test operand" error); `function NAME` rejects non-brace compound bodies
(lexer command-position not reset after the prefix — the known systemic gap's clearest
remaining bite); `[[:alpha:]])` starting a case pattern **on its own line** mis-lexes as `[[`
(the standard multi-line case layout; also trailing-glob and nested forms; the `[` branch has
the `in_case_pattern` guard, the `[[` branch doesn't — one-line mirror fix); combinator
parity: C-for empty-middle, `time` mid-pipeline (v0.613 drift), over-strict function names.

**Expansion gaps**: `${x~}`/`${x~~}`/`${x~pat}` case-toggle operators unimplemented (fatal
bad-substitution; bash semantics pinned by the verifier); Unicode case modification changes
string length (`straße`→`STRASSE` vs bash's 1:1 `STRAßE`; the fix needs a proper exclusion
set — a naive len==1 guard diverges on titlecase digraphs ǅǈǋǲ and İ).

**Glue/traps/CLI**: a pending signal trap is dropped at end-of-input when no EXIT trap is
set (`trap cleanup TERM; …; kill -TERM $$` as the last statement — flush pending traps in
`execute_as_main` before the EXIT trap); PS4 is never expanded (5 verbatim emission sites;
the user guide ships `PS4='+ line ${LINENO}: '` as a working example); all 5 analysis modes
skip line-continuation preprocessing (valid executable scripts → false syntax errors);
binary stdin still tracebacks across 4 channels (the file path already has surrogateescape —
2-line fix); invocation option parser gaps (`-o pipefail`, `+x`, `-xc` forms); `source` of a
directory/no-perm file returns 126 (bash: 1); `read -t` post-first-byte deadline (above).

**Interactive cluster**: `$-` lacks `m`/`set -o monitor` off despite working job control;
`PROMPT_COMMAND` unimplemented (zero references); bg completion notices always say "Done"
(the correct `Terminated: 15`/`Killed: 9`/`Exit 3` formatter **already exists** but is wired
only to the foreground path); command completion is doc-claimed but absent (path-only —
fix the doc or the engine); no trailing space after unique file completion.

LOW items (selected): `declare -p` doesn't `$'…'`-quote control bytes; `set` omits function
definitions; internal debug options leak into `set -o`; xtrace depth prefix static for
cmd-sub nesting; C-r prompt wording; no bracketed paste; `kill -l EXIT`; jobs `-r/-s`;
`source` no-arg rc 1 vs 2; multi-line eval LINENO anchoring; procsub-in-for-list divergence.

## 5. The independent review, reconciled

`docs/reviews/codebase_appraisal_2026-07-04.md` (external, same-day) was verified
claim-by-claim (`tmp/probes-r18-indie/REPORT.md`). **High-accuracy review: all 9 numbered
findings have real, reproducible kernels; most CONFIRMED exactly** — the `read` defects,
pipeline fd-0 collision (plus a *worse* bonus: psh crashes with a raw AttributeError if
started with fd 0 closed), env-builtin array isolation (a psh-internal-contract violation,
not a bash divergence — bash's `env` can't run functions), conformance-runner
untrustworthiness (hardcoded 364 of 1,471 collected tests, `main()` never gates on defects,
metrics stale from 12 June), `run_tests.py` masking mechanisms, identifier-policy
duplication (~10 `isalpha` sites; `é=1` accepted even under `set -o posix`),
`differences/README.md` listing *implemented* features (arrays, `[[ ]]`, procsub, extglob,
declare, local, mapfile, shopt) as "Not Implemented", and README carrying three conflicting
test counts.

Where the evidence pushed back: the **"Blocker: gate fails and hangs" framing is
environment-specific, not deterministic** — the 4-fds-per-Shell eager allocation is real but
GC-reclaimed (sawtooth, verified by stress probe; explicit `close()` → zero), this host runs
`ulimit -n` 1,048,576, and the gate shipped 11 green ceremonies in the 48h before the
review. The *hang trap* is real but dormant (an orphaned `sleep 300` from the disown test's
non-`finally` cleanup would wedge the runner's untimed `communicate()` — only after a prior
test failure). The `--parser`/`--validate` `select` demo is stale (combinator executes
select now) though the underlying code divergence is confirmed; the rc-3 translation is
materially more guarded than described; extglob backtracking is real but *bash is worse*
(0.75s vs 3.79s at n=35). A fresh gate run was executed as part of this reappraisal — see §7.

Verdict: the review's code-quality and assurance-hygiene findings are excellent, mostly new,
and adopted into the roadmap below; its release-readiness score (6.8/10) weighted the
gate-failure narrative more heavily than the evidence supports on this host.

## 6. Improvement roadmap

**Tier 1 — behavioral HIGHs (file-mostly-disjoint, one release each):**
1. Array-wipe chokepoint fix (`scope.py:386` scalar→element-0; verifier-proven sufficient
   incl. tempenv) + the `-aA` attribute invariant + duplicate `_apply_attributes` deletion
   (one campaign: core assignment plumbing).
2. Background-child trap runner (H2+H3) + POSIX async rules (bg stdin `/dev/null`,
   SIGINT/SIGQUIT-ignore) + `wait` remembered status.
3. RD arithmetic-collector consolidation (H4; also deletes the two-strategy divergence).
4. `_dup2_preserve_target` inheritability one-liner (H5) + exec-close stream primitive
   (extract the shared "close reaches the stream universe" helper).
5. `read -s` canonical-mode fix (H6) + `read -t` deadline threading (the two read defects
   share a file) — and an interactive-pty conformance probe for both.
6. `test`/`[`/`[[` file-ops: drop the isfile guard (P1), add `-nt`/`-ot` asymmetry,
   consolidate the duplicated copies into `utils/file_tests.py`, fix 3/4-arg dispatch.
7. Binary-stdin surrogateescape (2 lines, kills a traceback class across 4 channels) +
   fd-0-closed startup crash guard.

**Tier 2 — MED clusters:** arithmetic error-path edges (with the verifier-corrected
routings); tempenv-vs-`declare -g` restore policy; pending-trap flush at EOF; case-charclass
`[[` guard; empty-`[[ ]]` operand error; `function NAME` command-position reset; PS4
expansion helper (one site, 5 consumers); analysis-mode line-continuation preprocessing;
CLI option-parser completion (`-o`/`+`/cluster forms, with the CDPATH-aware `cd ""` fix);
`${x~}` toggle operators + length-safe case mapping (with the digraph exclusion set);
missing vars (BASHPID computed-special, HOSTNAME/OSTYPE/…, UID readonly); interactive
cluster (monitor flag, PROMPT_COMMAND, bg-notice formatter wiring, completion doc-truth,
trailing space); mapfile `-C`; history file flags (or honest errors); `ulimit` builtin;
combinator parity triple + a randomized RD-vs-combinator differential in the nightly (the
drift-detector both parser auditors asked for).

**Tier 3 — assurance (the independent review's core contribution):**
replace the conformance runner with pytest discovery + a JSON hook that fails on defects;
harden `run_tests.py` (subprocess timeout, never strip INTERNALERROR, tighten the rc-3
translation, stream to a file); `finally`-based cleanup + exact-PID kills in process-spawning
tests (disown first); `Shell.close()`/context-manager + lazy signal-notifier allocation +
close the `env` child (with an fd-count stress test); centralize identifier policy behind
the existing `unicode_support` API and gate on posix_mode; truth-up
`tests/conformance/differences/README.md` (spectacularly stale) and reconcile README's three
test counts; widen ruff/mypy incrementally (B/UP/SIM families; `disallow_untyped_defs`
package-by-package).

**Elegance-only (zero behavior change):** centralize the 8 copies of the shell-name/
assignment-word regex (`core/assignment_utils.py` is the natural home); finish
`parse_flags` convergence (history/directory_stack/shell_options first); extract formatter
escaping statics to `formatter_quoting.py`; delete the vestigial `DebugASTVisitor` (426
dead lines); rewrite the combinator's `heredoc_processor` as a thin visitor subclass; convert
2–3 showcase combinator productions to genuine combinator composition (teaching payoff);
split `_execute_buffered_command` (258 lines, 8 except clauses — parse/execute/classify);
one glob→regex converter (`glob.py` still uses stdlib fnmatch + a parallel bracket table);
route trap-body internal defects through `report_internal_defect` (strict-errors
consistency); `builtins/registry.py` duplicate-name rejection.

## 7. Gate status (fresh first-party run)

A full `python run_tests.py --parallel` was run at the end of this reappraisal on an
otherwise-idle machine (results: `tmp/test-results-r18-gate.txt`) to give the "gate fails
and hangs" claim a controlled data point. **Result: fully green — 11,536 passed / 867
skipped / 12 xfailed across all three phases (parallel, serial, subshells), exit 0, no
hang.** The parallel phase — where the external reviewer observed 5 failures + 1 error with
`OSError: Too many open files` — completed clean in 61s (10,576 passed); the serial phase —
where the reviewer's run hung on an orphaned `sleep 300` — completed normally. Combined
with the fd-lifecycle stress evidence (§5), the gate-failure narrative is confirmed as
environment/load-specific, not a property of the current tree. The *mechanisms* the review
identified (untimed capture, non-`finally` test cleanup, eager notifier fds) remain real
hardening items — Tier 3.

## 8. Themes

1. **The second-divergent-path pattern remains the #1 defect factory** — eight fresh
   instances this round (duplicate `_apply_attributes`, duplicate `-nt/-ot`, two glob→regex
   converters, three arith collectors, `$(( ))`-vs-`(( ))` error paths, the exec-close path
   missing the stream-swap primitive its two siblings have, PS4 verbatim ×5, analysis modes
   missing the exec path's preprocessing). **And the first counter-evidence:** expansion's
   two-walker design — the one place the second path is *documented as a policy decision
   with a rationale* — held under adversarial probing. The lesson is not "never two paths";
   it is "a second path must be a documented decision, not an accident."
2. **The frontier is now process/fd edges + feature gaps + assurance,** not language
   semantics. The language core (quoting, expansion, arithmetic, patterns, control flow,
   `set -e`, traps-in-scripts, LINENO) survived ~5,600 probes and two fuzzers essentially
   clean; what breaks is bg-job trap plumbing, CLOEXEC corners, termios modes, and tooling
   honesty (conformance runner, differences doc).
3. **Verification pays for itself** — third campaign running: 3 wrong fixes stopped, one
   root cause redirected to the right subsystem, one new defect found by auditing a "this
   works" claim, and a severity promotion driven by two independent verifiers converging.
4. **False-green tests are a recurring hazard:** `history -w/-a` tests pass via an
   exit-persistence artifact; `read -s` tests only exercise the non-tty path; the case-
   charclass gap survived because the only test uses the single-line form. Pin through the
   user-visible channel (pty/CLI), not the convenient one.
5. **External review + internal verification is a strong combination.** The independent
   review found real families internal rounds had under-weighted (resource lifecycle,
   tooling trust); the internal verification kept its two overstatements (deterministic gate
   failure; a stale demo) out of the ledger. Both directions mattered.

## 9. Follow-up ledger updates

- **Strike (fixed, verified):** nameref-to-existing-array `(( r[0]=9 ))` creation-fallthrough
  — now matches bash.
- **Confirmed still open (re-verified):** assoc quoted keys in arithmetic
  (`(( A["x y"]=9 ))`); binary-stdin traceback (now Tier-1 roadmap); `readonly r=;
  ${r:=new}` continues; history `-d`/`fc` absent.
- **New deliberate-divergence candidates (document, don't fix):** same-line alias
  define+use (already in ch17 — auditors should check before flagging); assoc iteration
  order (insertion vs hash) — worth an explicit ch17 row; CRLF stripping inside open quotes
  (add the one-paragraph ch17 note); psh Unicode identifiers (document + gate under posix).
- **New LOWs (unscheduled):** `**`-negative-exponent validation in untaken ternary arms;
  xtrace cmd-sub depth prefix; `declare -p` control-byte quoting; procsub-in-for-list.

---

*Report artifacts: 14 auditor reports (`tmp/probes-r18-*/REPORT.md`), 8 verifier verdicts
(`tmp/probes-r18-verify-*/VERDICT.md`), the independent-review verification
(`tmp/probes-r18-indie/REPORT.md`), master ledger (`tmp/r18_findings_ledger.md`), and all
probe batteries/transcripts alongside each report.*
