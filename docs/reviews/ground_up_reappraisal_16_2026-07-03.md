# Ground-Up Reappraisal #16 — psh v0.580.0

**Date:** 2026-07-03
**Method:** 13 parallel per-subsystem auditors, each grading Correctness (bash-conformance
of implemented behavior) and Textbook Quality (elegance/clarity). Every claimed divergence
pinned with an actually-run probe against GNU bash 5.2.26 on the same host (~1,400 paired
probes; artifacts under `tmp/appraisal16/`). Unimplemented features excluded by instruction.
**This round doubled as the verification pass for the reappraisal-#15 Tier-1 fix campaign**
(21 releases, v0.560–v0.580): each auditor first re-probed its subsystem's shipped fixes to
confirm they held, then hunted the new frontier.
**Baseline:** 240 Python files, ~58.4K LOC, 10,271 collected tests.

---

## Executive summary

**The campaign worked. Correctness rose across the board and every intended fix held —
with exactly one exception (a regression the campaign itself introduced).**

Of ~30 verified behaviors spanning all 20 shipped clusters (A–L + M), **every single one
held under fresh adversarial re-probing** except **I/O F1** (below). Six subsystems climbed
a full grade; the two worst performers of #15 — the combinator parser (B−→A−) and the
`--format` visitor (C+→B+) — were the biggest movers. No subsystem regressed in grade.

| Subsystem | #15 | #16 | Δ |
|---|---|---|---|
| Lexer | B+/A− | **A−/A−** | ↑ |
| Parser (RD) | B+/A− | **A−/A−** | ↑ |
| Parser (combinator) | B−/B | **A−/A−** | ↑↑ |
| Expansion | B+/A− | **A−/A−** | ↑ |
| Executor | B+/A− | **A−/A−** | ↑ |
| Core/State | B/A− | **B+/A−** | ↑ |
| Builtins | B+/B+ | **A−/A−** | ↑ |
| I/O Redirect | B+/A− | **A−/A−** | ↑ (1 regression) |
| Interactive | B−/B+ | **B+/A−** | ↑↑ |
| Scripting/Entry | B−/B+ | **B+/A−** | ↑ |
| Visitor/Formatter | **C+**/A− | **B+/A−** | ↑↑ |
| Engines (arith/pattern) | B+/A− | **B+/A−** (arith A−/A, pattern B+/A−) | = |
| Cross-cutting | B+/A− | **B+/A−** | = |

**Overall: Correctness B+ → A− (holding at A−); Elegance A− (holding).** The campaign's
three meta-fixes were independently confirmed *genuinely rigorous*: the conformance
meta-test now structurally rejects vacuous evidence, the `ShellState.adopt()` drift-lock
really guards (23 fields, 0 missing), and 0 placeholder tests remain across 440 files.

The new frontier is **narrower and shallower than #15's**. Where #15 found ~35 HIGH, #16
finds **8 HIGH**, and most are either (a) pre-existing items #15 explicitly scoped *out* of
Tier-1, or (b) new edges — not the everyday-idiom breakage that dominated #15. The
recurring "flat-string AST" and "silent misexecution at statement boundaries" families that
drove #15 are **closed**.

---

## Tier 1 — HIGH findings

### The one regression (fix first)

- **H1. I/O F1 — builtin output misrouted when a dup source fd is later reassigned
  (REGRESSION, introduced by v0.576 Cluster C).** `echo hi 1>&2 2>err` writes "hi" *into
  err* instead of the terminal's stderr; `echo hi 3>&1 1>&2 2>&3 3>&-` (the documented
  swap idiom on a bare builtin) sends output to stdout not stderr. `_dup_output_fd_for_children`
  (`psh/io_redirect/manager.py:427-447`) aliases stdout's stream object onto fd 2, then a
  later `2>file` calls `os.dup2(file_fd, 2)` and clobbers the backing out from under the
  alias. Proven a regression: correct at `1582718~1`, broken at the C-cluster commit. The
  C-cluster's own pinning test (`test_swap_order_matters`) uses `echo out 2>&1 1>/dev/null`
  where echo writes only stdout, so it never exercised the failing path. **Silent
  misrouting, no error.** The executor auditor found a sibling symptom (MED): after
  `exec 1>&-`, `echo X 2>g` leaks stdout into g with rc 0 (bash rc 1) — the temp fd from the
  redirect's `open()` isn't closed on the fd1/fd2 path. Fix these together.

### Crash

- **H2. `cmd | [[ ... ]]` raises an internal `AttributeError` (one-line fix; found by 4
  auditors).** `EnhancedTestStatement` (`psh/ast_nodes/tests.py:84`) is the only
  `CompoundCommand` subclass missing the `background: bool = False` field that
  `base.py:44-46` documents as mandatory; `PipelineExecutor` reads
  `node.commands[-1].background` (`pipeline.py:120`), so `true | [[ -n y ]]` crashes with a
  strict-errors internal defect. `[[ ]] | cat` (leader) and `(( )) | …` are fine. Add the
  field. This is on the #15 follow-up ledger (#1); everyday construct, so promoting to HIGH.

### Genuinely new behavior HIGHs

- **H3. `$IFS` reads empty — breaks the ubiquitous `OLD=$IFS; …; IFS=$OLD` save/restore
  idiom.** psh never seeds `IFS` as a real variable (only uses `' \t\n'` as an internal
  lookup fallback: `word_expander.py:350,751`, `state.py:566`), so `$IFS` expands empty and
  `IFS=$OLD` restores IFS to *empty* (= no splitting), silently corrupting all later
  word-splitting. `declare -p IFS` → "not found"; `"${IFS+set}"` → empty. `read`/default
  splitting still work via the fallback; only the *variable* is invisible. Seed
  `IFS=$' \t\n'` at init (unset still falls back). Likely a one-line fix, high blast radius.

- **H4. `${!prefix@}` / `${!prefix*}` silently corrupted → `bad substitution` (through both
  `--format` and `declare -f`).** `ParameterExpansion.__str__` (`psh/ast_nodes/words.py:67-73`)
  renders the prefix-names operator as a *suffix* — `${ab!@}` instead of `${!ab@}` — turning
  a working program into a broken one when formatted or serialized. `${!x}` (indirect) and
  `${!arr[@]}` (keys) render correctly; only the composite prefix+suffix forms break.

- **H5. Arithmetic integer literals ≥ 2⁶³ are not wrapped to signed 64-bit (all sites).**
  Every arithmetic *operation* wraps via `_to_signed64`, but a bare/assigned/compared/
  subscript literal does not (`tokenizer.py:38`, `evaluator.py:73,102,221`).
  `$((9223372036854775808))` → psh keeps the unsigned value where bash gives
  `-9223372036854775808`; `[[ 9223372036854775808 -eq -9223372036854775808 ]]` matches in
  bash, not psh (wrong result). Apply `_to_signed64` at literal ingestion. (#15 foresaw
  "literals may not wrap"; the H-cluster fixed only division.)

- **H6. POSIX classes `punct`/`cntrl`/`graph`/`print` unsupported everywhere + a Python
  `FutureWarning` leaks to stderr in default mode.** `glob.py:16-25` `_POSIX_CLASSES` maps
  only 8 classes; the four omitted ones reach Python `re`/`fnmatch` as literal nested sets →
  wrong match *and* `FutureWarning: Possible nested set` printed to stderr from
  `extglob.py:342`, `pattern.py:51`, `parameter_expansion.py:87`. Spans `[[ ]]`, `case`,
  `${v#pat}`, and pathname globs. The four ranges are expressible; the root is the pattern
  engine's split between stdlib `fnmatch` (plain pathname) and the `extglob.py` converter.

- **H7. Docs stale-negative cluster — ch17/README misclaim working features as
  unsupported.** `docs/user_guide/17_differences_from_bash.md` (lines 596/598/602/604 +
  prose 692–739) and `README.md:333` state that `read -u`, history designators/modifiers
  (`!!`, `!$`, `!!:1`, `:h`/`:t`/`:s`, `^old^new`), `${!prefix*}`, and `${var@K}`/`@k` are
  unsupported — **all probe as working and bash-matching** (some shipped 177 releases ago).
  The v0.580 meta-test only guards *positive* "Full support" rows, so these went undetected.
  Fixing requires flipping the rows + adding conformance tests + `CLAIM_TESTS` mappings (the
  meta-test will then demand them). Consider a complementary check that probes "No"-marked
  rows.

- **H8. Interactive editing: multi-line paste silently merges commands; Ctrl-R refinement
  recalls the wrong entry.** (Pre-existing #15 interactive MEDs, elevated because they cause
  *wrong command execution*; interactive editing beyond K1/K2 was never in Tier-1 scope.)
  LF/`\n`/Ctrl-J is unbound (`keybindings.py:103` binds only `\r`) and dropped, so pasting
  `echo one⏎echo two` runs `echo oneecho two`. And `HistorySearch._perform`
  (`history_nav.py:213-227`) always searches strictly *before* the current position, so
  extending the Ctrl-R pattern abandons a still-matching current entry and lands on an older
  one (shown as `(failed-...)`). Both are localized fixes.

---

## Tier 2 — MED findings (by subsystem)

**Lexer:** `>&word` (non-numeric target, csh-style redirect-both) rejected at parse time;
trailing `\c` in a `$'...'` string over-consumes the closing quote.

**RD parser:** `time <lone-compound>` drops all timing (`_bare_top_level_compound` guards
`negated` but not its sibling `timed` — one-line fix); `! ! cmd` double-negation rejected;
`f() [[ ... ]]` and `for x do` rejected (lexer command-position not context-fed by the
parser — the parser handling is wired but never receives the token; same class as the
`((cmd);cmd)` ledger item); consecutive `;` accepted where bash syntax-errors.

**Combinator:** `{var}>fd` named-fd silently dropped (reads `fd`, never `var_fd`) → clobbers
the shell's own stdout; `[[ ]]` boolean-compound/grouping fallback returns a
plausible-but-wrong exit status instead of cleanly rejecting (documented boundary, bad
failure mode); the imperative token-slicing in `(( ))`/`[[ ]]` is the core FP-teaching
weakness.

**Expansion:** colon operators (`:-`/`:=`/`:?`/`:+`) on `${a[@]}`/`${@}`/`${a[*]}` test
element-count not joined-nullness; `nocasematch` not threaded into `${v/pat/}` patsub;
`@A`/`@a` on a single array element don't strip the subscript; glob results C-locale-sorted
not `LC_COLLATE`; `${1:=default}` on an unset positional silently succeeds (bash errors).

**Executor:** no abnormal-termination diagnostic (`Terminated`/`Segmentation fault`) for
signal-killed foreground externals; nonexistent slash-path says "command not found" vs
bash "No such file or directory"; the `exec 1>&-`-then-builtin fd leak (sibling of H1).

**Core/State:** `declare -g NAME=val` writes an existing local instead of forcing global;
`eval "$(set +o)"` broken (`set +o` dumps non-set/shopt/internal options); readonly-assign
error double-wrapped through the declaration-builtin path; `local -` unimplemented (options
leak past return); `set -o` lists `emacs`/`vi` twice with contradictory values; `trap ''`
ignore not inherited across exec by externals.

**Builtins:** `[[ -o opt ]]`/`[ -o opt ]` shell-option test unsupported (parser recognizes
`-o`, evaluator rejects); `exec -a NAME`/`-c`/`-l` unsupported; `pushd -n`/`popd -n`
unsupported; `unset -vf` not rejected; `[ -R ]`/`[[ -R ]]` nameref test unsupported (`[[`
form is a parse error); `type` ignores the hash table; `printf "%()T"` empty format;
`umask -S MODE` sets silently; `set -o` listing omits several option names.

**I/O:** fd-move `[n]>&m-`/`[n]<&m-` silently mis-parsed (arg-leak on simple commands, parse
error in compounds); `exec` with multiple redirects doesn't roll back on partial failure;
`>&word` combined-redirect rejected.

**Scripting:** `$0` overwritten inside a sourced file; LINENO drifts by N per preceding
line-continuation (+ corrupts error line numbers; root = quadruple continuation processing);
`set --` in a no-arg `source` doesn't persist; `source` searches cwd before PATH; script
files translate CR→LF (even in quotes); POSIX short options `-s`/`-e`/`-x`/`-u`/… rejected.

**Visitor:** validator false "undefined variable" on `printf -v`/`mapfile`/`getopts`;
`echo a & echo b` non-idempotent formatting (blank-line join).

**Engines:** negative shift counts rejected by a guard sitting in front of the `& 63`
masking that would already give bash's answer (NEW); `${v/#pat/repl}` broken for
non-negation extglob (the `/%` suffix path already solved it — sibling divergence);
extglob not expanded in non-final path components; base-N literal with out-of-range digit
stops instead of erroring.

**Cross-cutting:** `set -o interactive` corrupts `$-` (spurious `i`); mypy gate hole — two
packages enumerate files individually so a campaign-added file (`loop_control.py`) escaped
the type gate, and CLAUDE.md's "auto-pickup" claim is false; `expand_aliases` is
accept-and-ignore (aliases expand non-interactively); 47 `tests/integration/interactive/`
tests never run in the gate; `HISTFILESIZE` ignored; `HISTSIZE<0` not unlimited.

---

## Tier 3 — Elegance / dead code (persisting from #15, no behavior change)

`WordShapeTracker.concat_safe` (lexer, dead — flagged #15, un-removed); `DebugASTVisitor`
(14KB fallback-only, duplicates `parser/visualization/`); `PromptManager` getter methods
(dead); `file_redirect.py` `apply_fd_plan(check_noclobber=…)` dead knob +
`_redirect_clobber` near-duplicate; expansion's triplicated colon-operator logic and ×71
`isinstance(var.value, …)` idiom; a dangling `_heredoc_trailer` docstring in the formatter;
the combinator's imperative `(( ))`/`[[ ]]` slicing.

---

## Recurring themes

1. **The campaign's structural fixes were durable and the defect *families* it targeted are
   closed.** The flat-string-AST family (case subject / `[[ ]]` unary / here-string) and the
   statement-boundary misexecution family were the engines of #15; both are gone. What
   remains are *isolated* edges, not systemic patterns.
2. **The #1 remaining systemic gap is lexer command-position not being parser-context-fed**
   (`f() [[`, `for x do`, `((cmd);cmd)`) — bash's parser feeds position back to its
   tokenizer; psh's doesn't. One architectural fix would close a cluster.
3. **"Honored on path A, dropped on path B" still produces the occasional bug** — but far
   fewer than #15: `declare -g` (local vs global), colon-ops (scalar vs array), patsub
   nocasematch (vs case/`[[`), `${v/#}` extglob (vs `/%`), the fd1/fd2 builtin swap. A shared
   helper closes each.
4. **The one regression (H1) slipped through because its pinning test didn't exercise the
   failing sub-path.** Verifier probes should vary *which fd the command actually writes to*,
   not just the redirect syntax. The verification-pass round caught it — as intended.
5. **Docs truthfulness now lags behind the code** (H7): 21 releases fixed features faster
   than the compatibility tables were updated, and the meta-test only guards positive claims.

---

## Recommended next tier (ordered)

1. **H1** I/O builtin fd-misrouting regression + its `exec 1>&-` sibling (fix together;
   strengthen the pin to vary the written-to fd).
2. **H2** `EnhancedTestStatement.background` one-liner (crash on `cmd | [[ ]]`).
3. **H3** seed `$IFS` as a real variable.
4. **H4** `ParameterExpansion.__str__` prefix-operator rendering.
5. **H5/H6** arithmetic literal 64-bit wrap; POSIX bracket classes + FutureWarning leak
   (converge the pattern-engine split).
6. **H7** docs stale-negative truth-up (+ a "No"-row probe in the meta-test) — cheap, high
   user-facing value.
7. **H8** LF/Ctrl-J bind + Ctrl-R inclusive re-search.
8. The MED cluster, batched by subsystem (the parser command-position fix is the highest-
   leverage — closes `f() [[`, `for x do`, `((cmd);cmd)` at once).
9. Elegance sweep for the persisting dead code.

Nothing here rises to the systemic severity of #15's opening frontier. The codebase is in
materially better shape: **A− correctness, A− elegance, no subsystem below B+.**
