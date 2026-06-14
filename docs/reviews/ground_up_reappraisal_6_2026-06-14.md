# Ground-Up Reappraisal #6 — Textbook Grade Scorecard

Date: 2026-06-14 (at v0.377.0)

Method: five parallel fresh-read assessments (one per subsystem cluster),
graded against the same strict **textbook** rubric used in #5 — small &
readable, single source of truth, narrow interfaces, abstractions that match
the problem, invariants explicit-and-enforced, behavior proven by tests. Each
agent read the current tree with fresh eyes and was asked to confirm any
suspected behavior bug against real bash before reporting it. This is the first
reappraisal taken *after* a sustained refactor campaign (#5's roadmap shipped
as v0.355–v0.377), so it measures how far the grade actually moved.

## Scorecard

| Cluster | #5 | #6 | Movement |
|---------|----|----|----------|
| Lexer / Parser / AST | B+ | **A−** | ↑ AST package, unified strip helpers, `[[ ]]` Words done, sentinel gone |
| Expansion | A− | **A−** | held (architecture textbook; fresh read found 4 applier-side bugs) |
| Executor / io_redirect | B+ | **A−** | ↑ RedirectionMode, decomposed `_execute_command`, RedirectPlan/planner |
| Core / Builtins | B+ | **B+** | held (core/ textbook; builtins behavior-fidelity gaps in read/declare) |
| Interactive / Scripting / Visitor / Tooling | A− | **A−** | held, on the cusp of A (mypy 10%→38%, redirect-loss fixed) |

**Overall: A− — "production-minded, solidly into textbook territory."** Three
clusters were promoted to A− and two A− clusters held; the campaign clearly
moved the grade up from #5's "B+/A−". mypy scope grew from ~21 to 85 files
(~38% of the tree). The remaining gap to a clean A is now **concentrated in a
list of confirmed, bash-verified bugs** (not architecture) plus finishing the
type-checking coverage. Core/Builtins is the one laggard, held at B+ purely by
bug density in `read`/`declare`.

## Confirmed bugs (bash-verified) — the priority work

### HIGH (independently re-confirmed by the orchestrator)
- **H1 `${var#}` empty-pattern returns the LENGTH.** `v=abc; echo "${v#}"` →
  bash `abc`, psh `3`. Root: `operators.py:236` tests `operator == '#' and not
  operand`, but `not '' == True` so an empty *pattern* hits the *length*
  branch. Fix: test `operand is None`. (Expansion)
- **H2 extglob `!(pat)` negation fails when the subject starts with the
  pattern.** `[[ foobar == !(foo) ]]` → bash `Y`, psh `N`. Root:
  `extglob.py:169` builds a wrong per-char inline-negation regex; affects
  `[[ ]]`, `case`, and all `${var#/%/ //}` removal operators. (Expansion)
- **H3 `read` (non-raw) does C-style escape interpretation.** `printf 'a\tb' |
  read x` → bash `atb` (strip backslash only), psh `a<TAB>b`. Root:
  `read_builtin.py:_process_escapes` converts `\t`/`\n`/`\r`; bash `read`
  without `-r` only strips the backslash + does `\<newline>` continuation.
  (Core/Builtins)
- **H4 `source` with no args wipes the caller's positional params.** `set -- A
  B C; source f.sh` (f.sh: `echo "$@"`) → bash `A B C`, psh empty. Root:
  `source_command.py:64` unconditionally assigns `positional_params =
  source_args`; guard with `if len(args) > 2`. (Scripting)

### MEDIUM
- **M1 `declare -i` ignored when combined with `-l`/`-u`.** `declare -il v=5+3;
  declare -p v` → bash `"8"`, psh `"5+3"`. `scope.py:_apply_attributes` uses
  exclusive `if/elif` (integer vs case-fold); bash applies integer then folds.
- **M2 `declare -p` attribute-letter order wrong.** bash canonical `a A i l n r
  t u x`; psh `declare_format.py:_FLAG_CHARS` orders differently (`-xi` vs
  `-ix`). Breaks `declare -p` round-trip.
- **M3 `declare -ia`/`-Aa` doesn't make the var an array** (stores scalar but
  prints `-a`).
- **M4 negative array index rejected on WRITE.** `a=(1 2 3); a[-1]=X` → bash
  ok, psh "index must be non-negative". Reading `${a[-1]}` works; only assign
  (incl. `(( a[-1]=9 ))`, `a[-1]+=`) fails. (`core/variables.py:132` driven by
  the arithmetic/array write path.)
- **M5 `unset -f NONEXISTENT` errors (exit 1); bash succeeds (0).**
  (`environment.py:390`)
- **M6 `test`/`[` lack `<`/`>` string operators** (`[ a \< b ]` → psh error 2;
  bash 0). (`test_command.py`)
- **M7 high numeric/`\xHH` escapes emit codepoints, not bytes.** `printf %s
  $'\377'` → bash 1 byte `ff`, psh 2 bytes `c3bf`. Byte-vs-str model issue in
  `lexer/pure_helpers.py:handle_ansi_c_escape` (also `\x80`, `\200`).
- **M8 ANSI-C `\cX` control escape unsupported** (`$'a\cIb'` → bash `a<TAB>b`,
  psh literal). Same function, missing case.
- **M9 FIFO temp-dir leak from write-side `>(cmd)` inside a pipeline.** `echo x
  | tee >(cat) >/dev/null` orphans a `$TMPDIR/psh-psub-XXXX/` dir per run (the
  pipeline child's `os._exit` skips the `process_sub_scope` cleanup). 78 had
  accumulated locally. (io_redirect)

### LOW
- **L1 `${}`/`${ }`/`${1abc}` not rejected as "bad substitution"** (psh →
  empty/exit 0; bash → error/exit 1).
- **L2 redirect-open failures leak Python `OSError` repr** (`psh: error:
  [Errno 2] ...: 'path'`) instead of bash-style `psh: path: strerror`; exit
  codes correct. Widespread across child + builtin redirect paths.
- **L3 zero-width extglob (`*(...)`/`?(...)`) over-substitutes in `${v//…}`**
  (extra empty match at end-of-string vs bash).
- **L4 `exec 1>&-` then exit → exit 120 + interpreter shutdown leak** (bash
  exits 1 with a write-error). Edge.
- **L5 `declare -F name` prints `declare -f name`** instead of the bare name.
- **L6 `shopt` missing common options** (`nocasematch`, `nocaseglob`,
  `failglob`, `lastpipe`, …); `shopt EXTGLOB` returns 0 not 1.
- **L7 `trap -p SIG` prints the bare name** (`TERM`) not `SIGTERM`.
- **L8 `$-` includes `s` in `-c` mode and uses a non-bash letter order.**
- **L9 ErrorContext "Context:" line is built backwards** and leaks raw
  `TokenType.EOF` reprs (`helpers.py:137`). Cosmetic, user-facing.
- **L10 `!$`/`!^`/`!*`/`:n` history word-designators unimplemented** though the
  user guide shows `!$`; `!!:1` leaves literal `:1` garbage. (Interactive)
- **L11 Metrics visitor counts every `Pipeline` node** (incl. single-command
  wrappers) → "Pipelines: 5" for a pipe-free script. One-liner
  (`len(node.commands) > 1`).

## Top quality issues (cross-cluster, ranked)

1. **Finish mypy coverage** — lexer/ and parser/ are entirely outside scope
   (~16k lines); the expansion mixins (`arrays/fields/operands/operators.py`)
   and the whole `arithmetic/` subpackage are out (self-type plumbing — a
   `VariableExpanderProtocol` unlocks them); `interactive/line_editor.py` and
   `utils/signal_utils.py` each have a handful of real type errors. `core/` is
   in scope but `check_untyped_defs` is off, so method bodies aren't checked.
2. **`builtins/` option-parsing & file size** — ~14 builtins still hand-roll
   flag loops; `function_support.py` (664), `read_builtin.py` (576),
   `directory_stack.py` (521), `environment.py` (483) remain large.
3. **`command.py` `_run_command` (~120 lines)** is still the densest executor
   method despite the #5/T2.1 split.
4. **Residual shared-mutable side channels** — pipeline child repoints
   `visitor.context`; `_decide_redirection_mode` reads `state.in_forked_child`
   rather than the passed context.
5. **Small duplications** — special-var classification in 2 places
   (`word_builder` vs `pure_helpers`); two paren scanners of differing
   fidelity; `operands.py` three near-identical scan loops; repeated
   error-emit triad in expansion.
6. **`_reparent_to_package()` mutates `__module__`** to satisfy a meta-test
   filter — widen the filter instead.
7. **No version-sync meta-test** despite CLAUDE.md mandating the 3 version
   strings match.

## Bottom line

The #5 campaign worked: the architecture is now solidly textbook across four of
five clusters, and the one structural lever left (type-checking the bulk) is
half-done. What separates psh from a clean A is no longer design — it's a
**concrete, bash-verified bug list**, four of them HIGH and all surgically
fixable in localized spots that tests don't pin. Recommended next phase ("Tier
R6"): fix the bugs worst-first (H1–H4, then the MEDIUMs), each with a
bash-probe battery promoted to conformance/golden tests, then resume growing
mypy scope (lexer/parser, then the expansion mixins via a protocol).
