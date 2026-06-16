# Ground-Up Reappraisal #11 — psh v0.464.0 (2026-06-16)

11 parallel subsystem reviewers (read-only), synthesized here. Baseline: reappraisal
#10 (`ground_up_reappraisal_10_2026-06-15.md`, v0.447, overall **A− trending A**)
followed by the full Tier R12 program (v0.448–464: 6 bug fixes, `check_untyped_defs`
to 12/12 packages, ShellState→`ExecutionState` extraction, six dedup/polish items).

## Overall grade: **A−**, trending A

The *structural ceiling rose*: six subsystems moved up to **A** (Executor, Core/State,
Visitor, Interactive, Cross-cutting — plus Lexer/IO holding at A), the whole codebase is
now mypy body-checked (12/12), the ShellState god-object is decomposed, and dead code /
doc drift are near zero. Every Tier R12 fix verified; no regressions from it.

What keeps the overall at **A−** (not a clean A) is that this round's *deeper functional
audit* — going past the structure into builtin edge semantics — surfaced a **fresh
cluster of ~8 genuine bash-divergence bugs** that earlier passes hadn't probed. The
standout: **Builtins dropped A− → B+** on four real bugs, including a `test -v` that has
never worked. This is the expected yield of repeated adversarial review: each pass digs a
layer deeper and finds more. The architecture is A/A+; correctness is the remaining gap.

## Subsystem scorecard (vs #10)

| Subsystem | #10 | #11 | Movement |
|-----------|----|----|----------|
| Lexer | A | **A** | held; only dead-constant + DRY nits |
| RD parser | A− | **A−** | held; break/continue arg validation still open |
| Combinator parser | A− | **A−** | held; every R11/R12 claim verified, no new defects |
| Executor | A− | **A** | ▲ v0.449 exec-redirect fix verified; 1 cosmetic msg bug |
| Expansion | A− | **A−** | held; a new anchored-patsub bug found; failglob still missing |
| Core/State | A− | **A** | ▲ ExecutionState extraction closes #9 M1; 2 new edge bugs |
| Builtins | A− | **B+** | ▼ deeper audit found 4 genuine bugs (test -v broken, …) |
| I/O Redirect | A | **A** | held; noclobber message word-order |
| Visitor | A− | **A** | ▲ structured Word-analysis bedded in; rm-rf/777 fixes verified |
| Interactive | A− | **A** | ▲ v0.448 history regression fixed + pinned |
| Scripting | A− | **A−** | held; AST-reuse string guard unchanged |
| Cross-cutting | A− | **A** | ▲ check_untyped_defs 12/12; docs/versions in sync |

## HIGH findings — genuine bugs (the R13.A cluster)

1. **Builtins — `test -v VAR` / `[ -v VAR ]` is completely broken.**
   `test_command.py:297-301` — `evaluate_unary` returns the sentinel `2` ("special
   handling needed") for `-v`, but nothing in the test builtin ever implements it (only
   the separate `[[ ]]` path does). `x=5; test -v x; echo $?` → bash `0`, psh `2`;
   `test -v nope` → bash `1`, psh `2`. Fix: implement `-v` by querying `shell.state`.
2. **Builtins — `getopts` leaves `OPTARG` set on a bad option (non-silent mode).**
   `positional.py:162-163` — sets `OPTARG` to the bad char; bash unsets it (psh's own
   help text says so, and the missing-arg branch already unsets correctly).
   `set -- -x; getopts ab o; echo "${OPTARG-UNSET}"` → bash `UNSET`, psh `x`. Fix: unset.
3. **Builtins — `test !` (lone `!`) returns 1; bash returns 0.**
   `test_command.py:81-85` — a single `!` is the one-argument "non-empty string" test in
   POSIX (exit 0), not negation-of-empty. Fix: only negate when `len(args) > 1`.
4. **Expansion — anchored empty-pattern substitution `${x/#/PRE}` / `${x/%/SUF}` no-ops.**
   `operators.py:448-451` — `_substitute` short-circuits `if not pattern: return value`
   for ALL operators, but `/#` and `/%` with an empty pattern match the empty string at
   start/end (bash prepends/appends). `x=hello; echo ${x/#/PRE}` → bash `PREhello`, psh
   `hello`. (`substitute_prefix`/`substitute_suffix` already do the right thing when
   reached.) Fix: gate the early-return to `operator in ('/', '//')`.
5. **RD parser — `break`/`continue` arguments unvalidated** (carried from #10).
   `control_structures.py:487-492` — only a digit WORD is consumed as the level; `break
   foo`, `break 0`, `break 1 2`, `break -1` are silently accepted (exit 0) where bash
   errors (numeric-argument / out-of-range / too-many-args). Fix: consume the single
   argument as a Word and validate numeric/range at the builtin.

## MED findings

- **Builtins — `declare -p` on an empty array prints `=()`** (carried #10);
  `declare_format.py:51,56` — bash prints the name with no value (`declare -A m`). Fix:
  omit `=()` when the array is empty.
- **Builtins — `read` of a partial last line at EOF returns 0; bash returns 1.**
  `read_builtin.py:563` — knowingly pinned as a "quirk" but still a real divergence
  affecting scripts that branch on `read`'s status; `_read_chars` already returns an
  `'eof'` status that `_read_normal` discards.
- **Core — `declare -ul`/`-lu` keeps BOTH case flags** (case-fold then wrong).
  `variables.py:509` + `scope.py:357` — bash treats `-u`/`-l` as mutually exclusive and
  cancels both. `declare -ul y; y=HELLO; echo $y` → bash `HELLO`, psh `hello`. Fix: clear
  the opposite case flag on set; treat both-set as no-op.
- **Core — readonly array *element* write bypasses the readonly gate.**
  `expansion/arrays.py:138-153` — `a=(1 2); readonly a; a[0]=X` succeeds (bash errors);
  the element setter mutates `var.value` directly instead of going through
  `set_variable`. (`a+=(4)` is correctly rejected.) Fix: check `var.is_readonly` first.
- **Expansion — `failglob` unimplemented** (carried #10); `shopt -s failglob` errors
  "invalid shell option name". Fix: register it; abort with "no match" (status 1) when a
  metacharacter pattern matches nothing.
- **I/O Redirect — noclobber error message word order.** `file_redirect.py:83` (+ two
  mirrors) emits `cannot overwrite existing file: NAME`; bash uses the `NAME: message`
  shape psh uses everywhere else. Fix: `f"{target}: cannot overwrite existing file"`.

## LOW findings (polish)

- **Executor — `exec` errno-less OSError prints `psh: exec: None`** (`command.py:782,799`)
  — noclobber/bad-fd/ambiguous-redirect on `exec CMD >…` loses the real message; mirror
  the sibling `_execute_builtin_with_redirections` (`print(psh: {e})` when `errno is None`).
- **Cross-cutting — the "12/12" is package-glob-level; 11 in-scope files lack the
  override** (most notably `psh/shell.py`, plus `parser/config.py`, `parser/__init__.py`,
  `parser/visualization/*`, `__main__.py`). A probe adding overrides returned zero errors
  — a free closure of the rollout. Fix: add `psh.shell` + collapse the parser globs to
  `psh.parser.*` + `psh.parser.visualization.*`.
- **Dead/dup**: lexer `VARIABLE_START_CHARS`/`VARIABLE_CHARS` dead (`constants.py:6`);
  `KEYWORDS` vs `KEYWORD_TYPE_MAP` two hand-lists (add a sync meta-test); RD dead
  `create_with_config`/`from_context`/`base_context.previous()`; RD arithmetic
  `stop_at_double_rparen` duplicated; visitor `enhanced_validator` perm/operator lists
  still duplicate `constants.py` (#10 LOW); scripting AST-reuse string-equality guard
  (`source_processor.py:182`) + `repl_loop` bare-`except` bypassing the error taxonomy.
- **Misc divergence**: out-of-range negative array READ — psh silent, bash warns to
  stderr (value empty in both); `type` builtin lone TODO.

## Proposed Tier R13 roadmap

- **R13.A — the bug cluster** (highest value). Builtins first (it's the B+):
  `test -v`, `getopts` OPTARG, `test !`, `declare -p` empty array; then Expansion
  anchored patsub; RD break/continue validation; Core `declare -ul` + readonly-array
  element; Executor/IO message fixes. Each: bash-probe + conformance/regression test.
- **R13.B — small features**: `failglob` (Expansion), and decide on `read`-EOF-status
  (un-pin the quirk to match bash) and the negative-array-read warning.
- **R13.C — finish typing & dead-code polish**: add the 11-file `check_untyped_defs`
  overrides (incl. `shell.py`); remove the dead lexer constants / RD methods; the
  KEYWORDS sync meta-test; visitor constants dedup; RD arithmetic helper dedup.

Recommended order: **R13.A (bugs) → R13.B → R13.C.** The architecture and hygiene are at
A/A+; closing this freshly-found correctness cluster — especially Builtins back to A — is
what earns the clean overall **A**.
