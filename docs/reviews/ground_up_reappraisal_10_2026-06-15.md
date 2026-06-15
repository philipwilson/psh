# Ground-Up Reappraisal #10 — psh v0.447.0 (2026-06-15)

Run via 11 parallel subsystem reviewers (read-only), synthesized here. Baseline:
reappraisal #9 (`ground_up_reappraisal_9_2026-06-15.md`, v0.437.0, overall **A−
trending A**) followed by v0.438–447: R10.A bug fixes, the full Tier R11
combinator-parser elevation (P1–P4), and the v0.447 history-concurrency fix.

## Overall grade: **A−**, trending A — the floor rose

The headline change: **the combinator parser, the lone B in #9, is now A−**, so
**no subsystem grades below A− for the first time**. Tier R11 delivered real,
verifiable architecture: a discriminated `ParseSuccess`/`ParseFailure` union with
farthest-error `or_else`, zero token-slicing (one recursion engine for every body
and condition header), grammar built once via recursion slots, and a modular
`commands/` package — all behind a 168-case differential parity suite.

What keeps the overall at A− is a **crop of genuine edge-case behavior bugs** the
reviewers surfaced across several subsystems (including two previously-A ones,
which slip to A−), plus the still-stalled `check_untyped_defs` rollout and the
untouched ShellState god-object. One of the bugs is a **regression in the v0.447
history fix itself** — the adversarial review earned its keep.

## Subsystem scorecard (vs #9)

| Subsystem | #9 | #10 | Movement |
|-----------|----|----|----------|
| Lexer | A | **A** | held; mypy-clean, bash-faithful |
| RD parser | A− | **A−** | held; `((`/`[[`-before-`then`/`do` divergence found |
| Combinator parser | **B** | **A−** | ▲ R11 lift: union+cut, no slicing, build-once, modular |
| Executor | A | **A−** | ▼ exec-with-command ignores redirections |
| Expansion | A− | **A−** | held; `$'...'` in operands + `${var@E}` gaps found |
| Core/State | A− | **A−** | held; sparse-array negative index + `$!`-in-subshell bugs |
| Builtins | A− | **A−** | held; H2 fix confirmed; `_declare_variables` still 195 lines |
| I/O Redirect | A | **A** | held; #9 M7 partially resolved |
| Visitor | A− | **A−** | held; M6 dead helpers + `rm -rf` heuristic still open |
| Interactive | A | **A−** | ▼ v0.447 history `_file_synced_len` stale-after-trim data loss |
| Scripting | A− | **A−** | held; 3 #9 findings still open |
| Cross-cutting | A− | **A−** | held; check_untyped_defs stalled at 3/12 packages |

## HIGH findings — genuine behavior bugs (the R12.A bug cluster)

1. **Interactive — v0.447 history regression (silent data loss).**
   `history_manager.py:102` — `_file_synced_len` is an ABSOLUTE index into
   `state.history`, but `add_to_history` trims the list from the FRONT when it
   exceeds `max_history_size` (default 1000), shifting every index. After a trim,
   `save_to_file`'s `history[self._file_synced_len:]` skips real new entries and
   re-includes already-saved ones. Repro: load 3 (synced=3), max=4, add n1/n2/n3 →
   list trims to `[old3,n1,n2,n3]`, slice `[3:]` = `[n3]` only → **n1,n2 lost**.
   Triggers in any session exceeding `max_history_size` before save. **Fix:** track
   the sync point so a front-trim decrements it by the number of entries dropped
   (or recompute new-entry count and clamp). This is mine to fix first.
2. **Executor — `exec CMD args redirects` ignores redirections.**
   `command.py:752-790` (`_handle_exec_builtin`) — the with-command branch never
   applies `node.redirects` (the no-command branch correctly does). Repro:
   `exec printf "out\n" >file` writes to the terminal, file stays empty (bash:
   file gets "out"); `exec /no/such 2>/dev/null` prints the error to un-redirected
   stderr (bash: silent). Both exit 127, so exit-code-only probes missed it.
   **Fix:** apply `node.redirects` permanently before the exec'd command runs.
3. **RD parser / Lexer — `(( ))`/`[[ ]]` directly before `then`/`do` fails.**
   `lexer/command_position.py:62` — `DOUBLE_RPAREN`/`DOUBLE_RBRACKET` are missing
   from `RESET_TO_COMMAND_POSITION`, so the keyword normalizer never returns to
   command position after `))`/`]]`. `if ((1)) then echo yes; fi`,
   `while ((i<2)) do …`, `for ((;;)) do …`, `if [[ 1 = 1 ]] then … fi` all fail
   (bash accepts all). **Fix:** add the two token types to that frozenset.
4. **Combinator — no newline-skip after `|`/`&&`/`||`.**
   `commands/pipelines.py:72,127` (and the duplicate module-level fns in
   `commands/__init__.py:209,278`) — a pipeline/and-or continued across a newline
   (`echo a |\ncat`, `echo a &&\necho b`) is rejected (bash + rd accept). Not a
   documented-shallow area — a true parity divergence. **Fix:** skip NEWLINE tokens
   after the operator before parsing the RHS.
5. **Expansion — ANSI-C `$'...'` not processed in `${...}` operands; `${var@E}` incomplete.**
   `operands.py:169-268` — `$'\t'` inside any parameter-expansion operand
   (`${x/$'\t'/X}`, `${x:-$'\t'}`, `${x#$'\t'}`) is taken literally (bash decodes
   it). And `operators.py:376-405` (`_ansi_c_expand` for `${var@E}`) is a third,
   incomplete ANSI-C decoder missing `\NNN`/`\cX`/`\uHHHH`/`\UHHHHHHHH`. **Fix:**
   route both through the canonical `lexer/pure_helpers.handle_ansi_c_escape`
   (deletes a duplicate decoder too).
6. **Core/State — sparse-array negative index + `$!` not inherited by subshells.**
   `variables.py:162-175` — `IndexedArray.get()` resolves negative subscripts by
   indexing the list of SET indices, not bash's one-past-the-top offset (which the
   WRITE path already implements); reads/writes disagree on sparse arrays
   (`a[0]=x; a[5]=y; ${a[-2]}` → psh `x`, bash empty). `state.py:242-278`
   (`adopt`) — `last_bg_pid` isn't copied to subshell children, so `$!` reads empty
   in `( … )` / `$( … )` (bash inherits it). **Fix:** share the negative-index
   mapping with `resolve_write_index`; add `last_bg_pid` to `adopt()`.

## MED findings (structure / consistency / lesser bugs)

- **Cross-cutting — extend `check_untyped_defs`.** Stalled at 3/12 packages
  (core/expansion/executor) since R9.B4. The clearest A−→A lever; next:
  `io_redirect` (mypy already points at `manager.py:124,125,158,161`), then utils,
  visitor, interactive, scripting, lexer (already passes if added), builtins.
- **Core — extract `ExecutionState`** (#9 M1, untouched). ~30 flat execution fields
  on ShellState; the `adopt()` `$!` miss above is a direct symptom of scattering.
  Lift into a sub-object like TerminalState/HistoryState. Plus `options` TypedDict.
- **Combinator — the `committed` cut channel is inert.** `diagnostics.raise_committed_error`
  (exceptions) is the only commitment; a grep for `committed=True` is empty, so the
  `or_else`/`many`/`separated_by`/`then` cut plumbing never fires — the union is
  half-wired (the explicitly-DEFERRED P2 item). Either wire it or document the
  fields as reserved scaffolding so the next reader isn't misled.
- **Combinator — duplicate `parse_pipeline`/`parse_and_or_list`** module-level fns in
  `commands/__init__.py:175-292` reimplement the mixins (and carry the same newline
  bug); only tests use them. Collapse onto the mixins.
- **RD parser — `break`/`continue` arg validation** (`control_structures.py:487`):
  `break foo`/`break 0`/`break 1 2` are silently accepted (bash errors).
- **RD parser — array-init head detection duplicated** (`commands.py:202-294` vs
  `arrays.py:155-186`); the element loop was unified but not the head classifier.
- **Builtins — `_declare_variables` still ~195 lines** (#9 M4); split the
  assignment vs bare-name branches. Also `declare -p` on a bare `declare -A m`
  prints `=()` (bash prints no value).
- **I/O Redirect — #9 M7 residual** (`file_redirect.py:482-494`): post-`plan`
  dispatch still re-classifies by `redirect.type`; collapse to direction-based.
- **Expansion — `failglob` unimplemented** (`shopt -s failglob` errors).
- **Visitor — `rm -rf` security check is substring-based** (`security_visitor.py:134`):
  `rm -r -f /` and `rm -fr /` go unflagged. Inspect flag tokens instead.

## LOW findings (polish — batch)

- **Visitor M6**: 8 unused `word_analysis` helpers (2 with zero refs anywhere) —
  delete or document as intended API. Dead `777` branch (`security_visitor.py:271`).
  `enhanced_validator_visitor` perm/operator lists duplicate `constants.py`.
- **Scripting** (#9, all still open): dead `InteractiveInput` class
  (`input_sources.py:145`); write-only `_last_hint` (`command_accumulator.py`);
  fragile string-equality AST-reuse guard (`source_processor.py:182`).
- **RD parser dead code**: `TokenGroups.COMMAND_LIST_END`, `ErrorSeverity.INFO/WARNING`,
  `word_builder.build_word_from_string` (TODO stub).
- **Docs**: `docs/subsystem_internals.md:527` still lists removed
  `AliasExecutionStrategy` (#9 LOW, unfixed); `core/CLAUDE.md` Key Files table lists
  nonexistent `assignment_utils.py` and omits real files; stale env/allexport code
  samples; `lexer/CLAUDE.md` line-count drift.
- **Lexer**: self-described "FRAGILE" `${...}` VARIABLE-vs-PARAM_EXPANSION substring
  classifier (`modular_lexer.py:411`); O(lines²) heredoc re-lexing.
- **Executor**: `array.py:109` `except (ValueError, Exception)` redundant + over-broad.

## Proposed Tier R12 roadmap

- **R12.A — the bug cluster first** (6 HIGH items). Order by blast radius / mine-first:
  (1) Interactive history regression, (2) executor exec-redirects, (3) lexer
  `((`/`[[`-before-`then`/`do`, (4) combinator newline-continuation, (5) expansion
  `$'...'` operands + `${var@E}`, (6) core sparse-array index + `$!` inheritance.
  Each: bash-probe + regression test.
- **R12.B — typing rollout**: `check_untyped_defs` outward from io_redirect. The
  clearest remaining A−→A lever.
- **R12.C — ShellState `ExecutionState` extraction** (+ options TypedDict, + the
  `adopt()` fix folds in naturally).
- **R12.D — dedup/polish**: combinator committed-channel decision + duplicate
  pipeline fns, RD array-init head dedup, `_declare_variables` split, visitor M6 +
  `rm -rf` heuristic, io_redirect M7 residual, expansion operand dedup, and the
  LOW docs/dead-code batch.

Recommended order: **R12.A (bugs) → R12.B (typing) → R12.C → R12.D.** The combinator
parser is no longer the long pole; the path to a clean overall **A** is the discrete
bug-fix list plus the typing and god-object items that have been deferred twice.
