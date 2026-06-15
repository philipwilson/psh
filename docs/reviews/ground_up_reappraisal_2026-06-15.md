# Ground-Up Reappraisal — 2026-06-15 (textbook-grade audit)

Scope: a full read-only, subsystem-by-subsystem reappraisal of `psh` at
**v0.423.0**, scoring each area against a "textbook-quality" rubric (clarity,
architectural elegance, separation of concerns, consistency, duplication/dead
code, type coverage, module/function size, test quality, conformance risk).
Conducted via 11 parallel reviewers (10 subsystems + 1 cross-cutting) and
synthesized here. Goal: identify the gap between today and a clean, elegant,
"textbook" A+ architecture.

## Overall grade: A−

Functionally healthy and architecturally sound. Verified strengths: clean
layering (lexer imports neither parser nor executor; parser never imports
executor; expansion touches executor only via one documented fork helper),
100% mypy *file* coverage, ~1.3 test-LOC per source-LOC, no god-objects among
the largest files, and **no actual dead modules** (every "unimported"
candidate is reached via `from .x import`).

What keeps it off the A+ shelf is not big design debt — it's an accumulation
of **half-finished campaign migrations, vestigial code scattered across nearly
every subsystem, and one over-grown alternate parser**.

## Scorecard

| Subsystem | Grade | The one thing holding it back |
|---|---|---|
| Lexer | A | 2 dead `Token` methods; 4 duplicated quote-toggle loops ignoring `QuoteState` |
| Parser — recursive descent | A− | Dead two-RPAREN arithmetic branches; stale `array_init.py` comment; sub-parser `self.parser` is `Any` |
| Parser — combinator | B | Grammar doesn't use its own combinators (manual token-slicing); fragile substring error-dispatch; 1.7× the RD parser's size |
| Executor | A | `[[ ]]` back-channels through `shell.execute_enhanced_test_statement`; dead `in_loop`/`in_function` |
| Expansion | A | Two divergent double-quote escape processors; dead alias save/load; 143-line `_apply_operator` |
| Core / State | A− | **ShellState god-object decomposition never started** (129 `self.` attrs); `Variable.copy()` deep-copy contract unfulfilled |
| Builtins | A− | Option-parsing split: ~6 use `parse_flags`, 12 hand-roll loops; `[` reports errors as `test:` |
| I/O Redirect | A | Duplicated process-sub body runner; a few untyped `_builtin_redirect_*` params |
| Visitor + AST | A− | Word-layer migration only ~80% done — `metrics_visitor` + 2 linter helpers still regex rendered strings |
| Interactive / Scripting | A / A | Completion is path-only (no command/var/`$VAR`); 2 vestigial members |
| Cross-cutting health | A− | README LOC/file/test figures stale; `check_untyped_defs` still core-only |

## Key numbers (cross-cutting reviewer, measured)

- Source: **227 .py files, 54,901 LOC**; `shell.py` is 401 lines (genuinely thin).
- Tests: **8,012 collected** across **339 test files / 72,569 LOC** (51 conformance
  files; 244 behavioral golden cases).
- Type coverage: `mypy` clean on the full tree (181 `files` entries expand to
  whole packages = effectively 100% file coverage). `check_untyped_defs=true`
  **only** for `psh.core.*`; global default `false`.
- Skips/xfails: 83 total (57 xfail, 27 skip, 2 skipif) ≈ 1% — no hidden cluster.
- Largest files: `brace_expansion.py` 902, `word_expander.py` 898,
  `combinators/commands.py` 813, `executor/command.py` 790. No god-objects.

## Per-subsystem findings

### Lexer — A
Standout "why" docs tied to bash semantics (`cmdsub_scanner.py:1-16`,
`word_scanners.py:1-48`, `modular_lexer.py:282-296`). All 28 modules mypy-typed.
654 tests.
- **Dead code:** `Token.from_basic_token` (`token_types.py:114-136`) and
  `Token.normalized_value` (`token_types.py:138-155`) — zero references.
- **Duplication:** hand-rolled `in_single/in_double` quote loops recur in
  `pure_helpers.py` (`find_closing_delimiter` :87-130,
  `find_balanced_double_parentheses` :176-234, `validate_brace_expansion`
  :486-503) and `word_scanners.build_assignment_prefix_map` (:568-604), despite
  `QuoteState` (`pure_helpers.py:19-60`) existing for exactly this.
- `position` setter backward-reset branch (`modular_lexer.py:104-113`) is
  effectively unreachable (all 7 assignments are forward) — drop or assert.

### Parser — recursive descent — A−
Exemplary "why" comments (`commands.py:419-456`, `context.py:39-50`). Structured
error signaling via `ParseError.at_eof`/`unclosed_expansion`. Full mypy
coverage; 612 unit + 198 differential tests.
- **Stale doc:** `commands.py:266` still cites "the legacy fallback path
  (`array_init.py`)" — that module was deleted in v0.349.
- **Dead branch:** two-RPAREN arithmetic fallbacks
  (`arithmetic.py:28-33, 53-59, 111-118, 131-133`) can't fire — `operator.py:385-389`
  emits `DOUBLE_RPAREN` as one token in arithmetic context.
- **Duplication:** `_parse_array_initialization` in both `arrays.py:280` and
  `commands.py:246`.
- **Type gap:** all 8 sub-parsers' `def __init__(self, main_parser)` lack a
  `'Parser'` annotation → `self.parser` is `Any` everywhere.
- `build_word_from_string` (`word_builder.py:267-277`) carries a TODO and is
  unreferenced by RD code.

### Parser — combinator — B
`core.py` is genuinely textbook (`Parser`/`ParseResult`/`many`/`sequence`,
mypy-clean, lines 18-485). 374 tests incl. 3 differential parity suites.
- **Central irony:** the grammar barely uses its own combinators — if/while/case
  parse bodies via manual `while pos < len(tokens)` slicing with hand-tracked
  `nesting_level` (`conditionals.py:142-167, 238-250`; `loops.py:78-88`).
- **Fragile error dispatch:** `is_missing_nested_terminator` matches substrings
  like `"expected 'fi' to close"` (`diagnostics.py:36-39`), and `structures.py:147-156`
  reimplements the same dispatch independently. Any reword silently breaks it.
  → carry a structured `terminator`/`construct` field on `ParseError`.
- **Dead code:** `between`, `fail_with`, `with_error_context`, `try_parse`,
  `literal`, `lazy` defined/exported/tested but unused by the grammar;
  vestigial `ParseResult.remaining` (`core.py:31`, set in `map` :78, never read).
- `then()` returns `first_result.position` on 2nd-parser failure (`core.py:102`)
  vs `sequence()` resetting to `pos` (`core.py:232`) — inconsistent backtracking.

### Executor — A
`child_policy.py` is the standout teaching artifact (`fork_with_signal_window`
:38, `apply_child_signal_policy` :72; every fork site provably routes through
them). R8.3 typed data flow is real (`CommandResolution`/`ExecutionResult`
`command.py:74,:96`). Full mypy coverage; clean error taxonomy.
- `visit_EnhancedTestStatement` (`core.py:342`) bounces through
  `shell.execute_enhanced_test_statement` (`shell.py:355`) — the one node that
  breaks the uniform "delegate to a sub-executor" seam.
- **Dead code:** `ExecutionContext.in_loop()`/`in_function()`
  (`context.py:71,:75`) — zero callers; `execute_subshell`'s `visitor` param
  (`subshell.py:42`) unused.
- **Type increment ready:** add a `psh.executor.*` `check_untyped_defs=true`
  override — the package is fully annotated.
- Minor: `SpecialBuiltinExecutionStrategy._execute_in_background`
  (`strategies.py:184`) instantiates a throwaway `BuiltinExecutionStrategy()`.

### Expansion — A
`WordExpansionPolicy` table (`word_expander.py:49-118`) is the standout
pedagogical device (3 named axes, each row bash-probe-dated). Clean
orchestrator/engine split. 100% mypy; 1545 tests.
- **Dead code:** `AliasManager.save_to_file`/`load_from_file`
  (`aliases.py:296-315`) — zero callers.
- **Vestigial param:** `WordExpander._split_with_ifs`'s `quote_type`
  (`word_expander.py:867`) always `None`.
- **Duplication:** `word_expander.process_dquote_escapes` (:802) and
  `variable.py._process_double_quote_escape` (:478) implement overlapping
  `\$ \\ \" \`` rules with subtly different intent (latter has PS1 nuance) —
  behavior matches bash today but is a latent consistency trap.
- `_apply_operator` is 143 lines (`operators.py`); `$*`/`$@` branches in
  `expand_parameter_direct` (`variable.py:208-247`) near-identical.

### Core / State — A−
Superb bash-pinned comments (`scope.py:391-396`, `state.py:54-58`,
`variables.py:128-149`). Exemplary expected-error taxonomy
(`internal_errors.py`). StreamBindings is a model decomposition. Strictest mypy
scope (`check_untyped_defs` for `psh.core.*`).
- **God-object, decomposition unstarted:** `state.py:33-231` sets 129 `self.`
  attributes (history/editor :163-170, terminal :212-214, execution status
  :157-203, traps :228). Proposed `HistoryState`/`OptionState`/`ExecutionStatus`/
  `TerminalState` **do not exist** (grep: none). Extract `TerminalState` +
  `HistoryState` first — both cohesive and nearly self-contained.
- **Dead fields:** `state.history_index` (:166), `state.current_line` (:167) —
  no readers.
- **Latent trap:** `Variable.copy()` (`variables.py:107-113`) shallow-shares
  array objects; safe only because every `adopt()` consumer forks. Deep-copy
  arrays or rename `shallow_copy()` + document the invariant at `state.py:264-268`.
- `get_option_string` (`state.py:445-475`) hard-codes a second option list
  parallel to `__init__` and SetBuiltin — three places to keep in sync.

### Builtins — A−
Exemplary `base.py` (`:67-160` forked-child-aware write/error + getopt-style
`parse_flags`; statelessness contract enforced by test). All 35 builtin files
mypy-typed; no raw stderr prints; strong bash-pinned consistency tests.
- **Inconsistent option-parsing:** ~6 builtins use `self.parse_flags`; 12
  hand-roll `while i < len(args)` loops (`directory_stack.py`,
  `command_builtin.py`, `kill_command.py`, `shell_state.py`, …). Some justified
  (echo `-neE`, read/declare value-flags); `command_builtin`/`directory_stack`/
  `kill_command` could converge.
- **Oversized:** `function_support.py:_declare_variables` is 195 lines (file 724,
  largest in subsystem).
- **bash divergence:** `[` reports errors as `test:` via `self.error`
  (`test_command.py`); bash's `[` emits no command prefix → prefix from `args[0]`.

### I/O Redirect — A
"Two redirection universes" docstring (`manager.py:1-58`) is outstanding
pedagogy. Resource-safety reasoning load-bearing and explained. `RedirectPlanner`/
`RedirectPlan` cleanly factor the R8.2 boundary. mypy-clean; 234 tests.
- **Duplication:** `_execute_process_substitution_body` (`process_sub.py:84-89`)
  is byte-for-byte the inline `_body` (`:60-65`); read-side inlines, write-side
  calls helper.
- `process_sub.py:36-37`: `child_fd`/`child_stdout` two aliases for one fd.
- **Type gap:** `_builtin_redirect_*` signatures (`manager.py:314,357,370,399,437,468`)
  leave `target`/`redirect` untyped while `frame` is typed.
- `manager.py:201-232` `_swap_closed_output_streams` duplicates stream-swap of
  `_builtin_redirect_close` (`:437-466`).

### Visitor + AST — A−
The totality/coverage matrix (`tests/unit/visitor/test_ast_coverage_matrix.py`)
is exemplary — enforces a different `generic_visit` contract per visitor and
behaviorally proves redirect carriers are handled. `word_analysis.py` is a clean
structured layer; AST nodes use derived-not-stored properties well.
- **Migration ~80% done:** `metrics_visitor.py:244,363,412,486-501` still regexes
  rendered `arg` strings (double-counts `$(`/backtick, ignores quoting) — the
  exact anti-pattern `word_analysis.py` exists to replace. `linter_visitor.py:423,452`
  use `arg.startswith('$')` while the same file's `:354` uses the structured
  layer.
- `metrics_visitor.py:515-544` `_count_commands_in_node` hand-walks `n.__dict__`
  instead of reusing `traversal.iter_child_nodes`.
- `debug_ast_visitor.py:134` uses a same-quote-nested f-string (3.12+ only).
- `security_visitor.py:205-223` arithmetic-injection check is a crude heuristic
  (self-flagged).

### Interactive / Scripting — A / A
Single completeness oracle (`command_accumulator.py:1-29`; both
`source_processor.py:81` and `multiline_handler.py:61` feed `CommandAccumulator.feed()`)
— interactive and script line-gathering provably can't disagree. `shell.py` is
genuinely thin (7 named lifecycle phases). Five-component line-editor
decomposition is reference-grade. All 21 interactive + all scripting files
mypy-typed; 274 tests.
- **Behavioral gap:** `CompletionEngine` does path completion ONLY
  (`tab_completion.py:21-28`) — no command/builtin/variable/`$VAR`/`~user`
  completion. Largest user-facing gap for a teaching shell.
- **Vestigial:** `InteractiveComponent.__init__` sets `self.multi_line_handler = None`
  (`base.py:16`) used only by `REPLLoop`; `LineEditor.save_undo_state()`
  (`line_editor.py:743-745`) dead.
- **Stale doc:** `interactive/CLAUDE.md` "least typed" framing is outdated
  (now 100% typed); its pasted REPL/signal code blocks will drift.
- `StringInput` special-cases `name == "<command>"` (`input_sources.py:115`) —
  a string-equality mode switch; prefer an explicit `single_line` flag.
- `REPLLoop.run` (`repl_loop.py:87-89`) catches bare `Exception` → `psh: {e}`,
  bypassing the `report_internal_defect`/strict-errors taxonomy.

### Cross-cutting health — A−
- **Doc drift:** README claims 51,100 LOC / 222 files / 66,200 test-LOC / 326
  test files / "5,500+ tests"; actual 54,901 / 227 / 72,569 / 339 / 8,012. Five
  stale figures (version string itself is in sync).
- **Dual-parser tax:** combinator parser is 5,882 LOC vs RD's 3,378 (1.7×).
- `check_untyped_defs` still only `psh.core.*` — expansion/executor are ready.
- Two ~900-line expansion files near the readability ceiling.
- 57 xfails worth auditing: which pin known bugs vs document bash divergences?

## The themes separating A− from A+

1. **Vestigial/dead code scattered through nearly every subsystem.** Individually
   trivial, collectively a real blemish for a *teaching* reference. A clean sweep
   touches lexer, RD parser, combinator parser, executor, expansion, core, and
   interactive.
2. **Several campaign migrations are half-done** — ShellState decomposition
   (unstarted), visitor Word-layer (~80%), `check_untyped_defs` (core-only),
   array-init dedup.
3. **The combinator parser is the single biggest quality gap** (B, 1.7× size).
   Needs a strategic decision: invest to elevate, or formally freeze as a
   read-only teaching artifact.
4. **Doc/code drift** in README — worth a meta-test that fails on drift (like
   the version already auto-syncs).
5. **Consistency micro-gaps** — builtins option-parsing, the two escape
   processors, the `[`-vs-`test` prefix, duplicated array-init paths.

## Proposed roadmap to A+ (Tier R9 — locally-gated, mostly zero-behavior)

- **R9.A — Dead-code & vestige sweep** (fast, high signal, near-zero risk):
  remove every theme-#1 item across all subsystems; verify each truly
  unreferenced; full gate per release.
- **R9.B — Finish the migrations** (where the real grade lives):
  ShellState `TerminalState` + `HistoryState` extraction (StreamBindings proves
  the pattern); complete the visitor Word-layer migration; extend
  `check_untyped_defs` to `psh.expansion.*` then `psh.executor.*`; de-dup the
  array-init paths.
- **R9.C — Combinator parser decision + cleanup:** elevate-vs-freeze; either way
  replace substring error-dispatch with a structured `ParseError` field and kill
  the duplication; remove unused primitives + `remaining`; unify `then`/`sequence`
  backtracking.
- **R9.D — Consistency & decomposition polish:** builtins `parse_flags`
  convergence; unify escape processors; `[` error prefix; split the two
  ~900-line expansion files; fix README drift + add a count meta-test; the small
  executor/io_redirect seam fixes (`[[ ]]` in-package evaluator, process-sub body
  runner).

**Recommended start:** R9.A (clears the noise), then R9.B (the unstarted
ShellState decomposition is the biggest single lever).
