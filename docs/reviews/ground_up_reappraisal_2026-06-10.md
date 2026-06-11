# psh Ground-Up Reappraisal — 2026-06-10 (v0.274.0)

> **⚡ STATUS (2026-06-11, as of v0.287.0) — PROGRAM COMPLETE.**
> All three tiers of §5 shipped across 13 releases:
> **Tier A** v0.275.0–v0.278.0 (packaging truth, behavior bugs, test-tree
> cleanup, meta-docs); **Tier B** v0.279.0–v0.284.0, GitHub PRs #10–#15
> (variable.py decomposed, one pattern engine, PshError root, lexer made
> linear, the fork→exec signal-loss race found and fixed, vi-mode arrows,
> builtins consistency); **Tier C** v0.285.0–v0.287.0, PRs #16–#18
> (module relocation + scope rename, parser pruning + CLAUDE.md
> refreshes, mypy in CI + interactive unit tests). Findings below are
> preserved as written at v0.274.0; several review claims were disproven
> during implementation and are documented in the corresponding
> CHANGELOG entries (lexer map-threading, ErrorContext.suggestions,
> getopts parser, env builtin). Suite at close: 4,310 passed / 4,625
> collected; mypy and ruff enforced in CI.

A fresh, post-campaign assessment of the whole project, conducted immediately after
the architecture/feature review campaign closed (37 releases, v0.238.0–v0.274.0,
see `architecture_feature_review_2026-06-09.md`). That campaign was about
**correctness**; this reappraisal asks a different question: **is the code
textbook quality?** — psh's stated purpose is teaching shell internals through
clean, readable Python. Eight parallel reviews covered every major subsystem,
the test suite, the meta-documentation, and whole-tree health signals.

## Executive summary

**Overall grade: B+.** The project is in the best shape of its life on
correctness and architecture — ProcessLauncher, child_policy, line_layout,
word_splitter, and the conformance claims meta-test are genuinely exemplary
teaching artifacts. But the campaign optimized for *behavior*, and the bill for
that is visible: a few files grew into grab-bags (`expansion/variable.py` at
1,644 lines is the worst), duplicated logic accumulated (six copies of
array-element resolution, four pattern-matching engines, ~5× job-registration
boilerplate), and the meta-docs drifted badly (ARCHITECTURE.md/.llm describe
removed subsystems; README claims `trap` is unimplemented; root CLAUDE.md says
v0.237.0).

**One outright broken claim**: packaging says `requires-python = ">=3.8"` but
the tree won't import below 3.12 (PEP 701 f-string in
`visitor/debug_ast_visitor.py:131`, runtime PEP 585 generics in four files).

**Per-area verdicts:**

| Area | Grade | One-line judgment |
|------|-------|-------------------|
| Parser (recursive descent) | A− | Textbook delegation; marred by dead error-recovery scaffolding |
| Executor / process mgmt | B+ | ProcessLauncher/child_policy/pipeline are exemplary; job-registration boilerplate ×5 |
| Core / state | B+ | Clean state container; `scope_enhanced.py` name is a smell (no plain `scope.py` exists) |
| I/O redirect | B+ | `file_redirect.py` is textbook; `manager.py`'s dual stream/fd universe is the hard part |
| Interactive / line editor | B+ | New line_layout split is exemplary; dead DSR machinery, vi-mode arrow bug |
| Test suite | B+ | Excellent conftest/runner/claims-meta-test; legacy trees and `/tmp` paths drag it down |
| Lexer | B− | Learnable pipeline; `literal.py` re-derives state by string archaeology, dead config flags |
| Expansion | B− | Small modules exemplary; `variable.py` is a 1,644-line grab-bag with 3 `${...}` parsers |
| Builtins | B− | Registration clean; option parsing and error channels wildly inconsistent (incl. a real `read` bug) |
| Parser (combinator) | B− | Honest about experimental status, but drifted behind v0.266–267 fixes and isn't combinator-y where it counts |
| Meta-docs (CLAUDE.md, ARCHITECTURE.*, README) | C | Substantial sections describe code that no longer exists |

---

## 1. Subsystem findings

### 1.1 Lexer — B−

**Strengths.** The five-stage `tokenize()` pipeline (`lexer/__init__.py:33`) and
the 30-line main loop (`modular_lexer.py:260`) read beautifully;
`command_position.py` and the quote-rule tables are textbook; remediation-era
comments (O(n) array map, heredoc single-pass, fail-loud registry) explain *why*.

**Issues, ranked:**
1. **`literal.py` (814 lines) is the biggest obstacle in the subsystem.** ~10
   helpers reconstruct parse state by re-scanning the accumulated value string
   — `_is_inside_array_assignment` (literal.py:545) is O(n²) per word and
   *duplicates* the lexer-level O(n) `_build_array_assignment_map`
   (modular_lexer.py:372). Fix: pass the precomputed map into the recognizer
   and delete the string-archaeology helpers; the file shrinks naturally.
2. **Never-used config flags inflate both big files.** `posix_mode` is never
   True; `strict` selects between two identical configs (position.py:104-118);
   the 8-branch "is this quote disabled?" ladder appears twice in literal.py
   and once in operator.py, all for test-only configurations. Delete or
   collapse to one helper.
3. **Duplicated logic:** comment-start logic in three places with *diverging*
   operator sets (literal.py:335, comment.py:51, pure_helpers.py:431); backtick
   parsing verbatim in quote_parser.py:242 and expansion_parser.py:226;
   `_parse_fd_duplication` (operator.py:97) is two near-identical 45-line halves;
   process_sub.py:67-90 re-implements `QuoteState` inline.
4. **Dead code to delete:** `parse_simple_quoted_string`, `get_operator_type`,
   `_is_identifier`, `is_comment_start`, unused `WORD_TERMINATORS*` constants
   (shadowed by a different live set in literal.py:19), `create_expansion_parser`,
   the test-only registry surface (`default_registry`, `unregister`, `get_stats`).
5. **Fragile heuristics worth fixing or commenting:** PARAM_EXPANSION
   classified by substring scan (modular_lexer.py:449); keyword matching is
   case-insensitive though bash keywords are not (keyword_normalizer.py:38);
   `heredoc_already_collected` assigned in one branch, read on a later loop
   iteration (NameError trap); unmatched chars silently dropped
   (modular_lexer.py:284).

### 1.2 Parser — A− (recursive descent) / B− (combinator)

**Strengths.** The rd `Parser` (362 lines) delegates to 8 sub-parsers, all
under 500 lines, uniform contract — a student can trace
`parse → statement → and_or → pipeline → command` directly. Both parsers share
`ast_nodes.py` and `WordBuilder` (so `${!name}` indirection is at parity by
construction). `ParseError.at_eof` is a structural incomplete-input signal
rather than string matching.

**Issues, ranked:**
1. **The combinator control structures aren't combinators.**
   `_build_if_statement` (combinators/conditionals.py:47) is 192 lines of
   manual token slicing with hand-rolled nesting counters; same for case (165
   lines), array-element assignment (178 lines), and the loop builders. The
   educational claim ("functional composition vs imperative state") is
   undermined exactly where it matters. Either rewrite with the actual
   primitives or document why slicing was necessary.
2. **Combinator drift (confirmed empirically):** function-def trailing
   redirects are applied at *definition* time instead of per-call
   (structures.py:173 builds `FunctionDef` without `redirects`); quoted case
   patterns wrongly keep glob chars active (conditionals.py:290 builds
   `CasePattern` without `word=`). Both regressions postdate the rd fixes of
   v0.266–0.267. `docs/guides/combinator_parser_remaining_failures.md` ("0
   remaining failures as of v0.171.0") is stale.
3. **Dead error-recovery machinery in rd:** `ErrorContext.suggestions` /
   `error_code` / `related_errors` never populated; `ParsingMode.EDUCATIONAL`,
   `permissive()`, `parse_with_error_collection` / `MultiErrorParseResult`
   (parser.py:187-272) have no production caller. Prune or wire up.
4. **Vestigial AST metadata contradicts the Word-AST story:** parallel string
   lists survive in `ArrayInitialization.element_types/element_quote_types`,
   `ForLoop/SelectLoop.item_quote_types`, `BinaryTestExpression.*_quote_type`,
   `ArrayElementAssignment.value_type` — the removed `arg_types` pattern by
   another name. Stale comment at ast_nodes.py:415-416 references dual
   Statement/Command types removed long ago.
5. **Error-message inconsistency** (`"Syntax error: unclosed…"` vs
   `"syntax error near unexpected token"` vs bare `"Expected command"`); 25
   lines of backslash-parity lexing leaked into
   `parse_pipeline_component` (commands.py:348-372).

### 1.3 Executor & process management — B+

**Strengths.** ProcessLauncher is effectively the single source of truth (only
3 production `os.fork()` sites; the two outliers in command_sub/process_sub
immediately apply `child_policy`). Terminal ownership is centralized
(`terminal_pgid_if_owned()`, all `tcsetpgrp` funneled through three named
methods, TCSANOW/reclaim-first rationale documented in place). The visitor
core is a clean dispatch table. `process_launcher.py`, `child_policy.py`, and
`pipeline.py` are among the best shell-internals teaching code anywhere.

**Issues, ranked:**
1. **Background-job registration boilerplate duplicated ~5×**
   (strategies.py:188, :268, :448; subshell.py:244, :288; pipeline.py:221) —
   and the `[N] pid` notice goes to **stdout** in strategies.py but **stderr**
   (bash-correct) in pipeline.py and subshell.py. Extract
   `JobManager.launch_background()`; fixes the inconsistency and teaches the
   pattern once.
2. **Oversized functions:** `CommandExecutor.execute` 191 lines (command.py:64,
   mixing assignment phasing, `\cmd` bypass rewriting, and a 50-line exception
   policy); `_execute_pipeline_with_forking` 157 lines;
   `ExternalExecutionStrategy.execute` 124 lines containing two unrelated
   programs (in-pipeline inline exec vs fork-and-wait).
3. **One pytest sniff survived the campaign:** `expansion/command_sub.py:63`
   gates stdin protection on `PYTEST_CURRENT_TEST`. Replace with a capability
   check, as was done for terminal ownership.
4. **Dead code:** `process_metrics` hooks guarded by `hasattr` for an object
   never created (job_control.py:321, :334); unused `ProcessLauncher` imports
   ×3; `_execute_pipeline` → `_execute_pipeline_with_forking` pointless
   indirection; "will be implemented in Phase 7" docstring (function.py:27).
5. **Opaque plan codenames** ("H3", "H4", "H5", "C1") in 15+ comments reference
   an improvement plan no reader can see. Replace with self-contained prose.
6. **Smells:** `command_executor._visitor = self` backchannel (core.py:83);
   `job.state.name == 'DONE'` string comparison (subshell.py:192); error output
   alternating between `sys.stderr` / `self.state.stderr` / `shell.stderr`.

### 1.4 Expansion — B−

**Strengths.** `word_splitter.py` (122 lines, POSIX 2.6.5 spelled out),
`tilde.py`, `glob.py`, and the ParameterExpansion operator methods are
exemplary. The new helpers (`_split_part_fields`, `split_with_edges`,
`_expand_at_with_affixes`, `_expand_pattern_operand`) are well documented with
bash citations; the PATSUB_MATCH and `_UNSET` sentinels are documented at
definition and use — teachable, not hacks. Essentially no dead code.

**Issues, ranked:**
1. **`variable.py` (1,644 lines) is a grab-bag needing decomposition.** It
   mixes seven concerns. Concrete split keeping `VariableExpander` as facade:
   `arrays.py` (~450 lines: subscript/slice/length/element get-set),
   `operators.py` (~350: `_apply_operator`, transforms, `_substitute`),
   `operands.py` (~250: pattern/replacement operand mini-lexers),
   `fields.py` (~180: `expand_to_fields`, `_slice_fields`).
2. **Array-element resolution copy-pasted six times** (variable.py:106, :233,
   :330, :365, :514, :709 — the same eval-index-with-ArithmeticError→0 dance,
   plus 10 repeated local arithmetic imports). One
   `_resolve_array_element(name)` helper removes ~150 lines and a real student
   trap (which copy is canonical?).
3. **Three places parse `${...}`** (lexer/Word-AST path;
   `parse_expansion`'s 147-line scan for the string path; `_parse_trailing_op`
   re-parsing operators baked into parameter text), and slice-operand parsing
   is tripled. The dual string/AST entry points (`expand_variable` vs
   `expand_parameter_direct`) mean a student can't tell which path runs.
4. **Four hand-rolled `$`-construct scanners overlap**
   (`expand_string_variables`, `_expand_one_dollar`,
   `_expand_vars_in_arithmetic`, `_expand_command_subs_in_arithmetic`).
   `_expand_one_dollar` is the cleanest; rebase the others on it.
5. **Functions >100 lines:** `ArithTokenizer.tokenize` ~217 (table-drive it),
   `_expand_word` ~164, `parse_expansion` ~147, `expand_parameter_direct` ~144,
   `CommandSubstitution.execute` ~136, `_apply_operator` ~126 (dispatch table).

### 1.5 Core / builtins / io_redirect — B+ / B− / B+

**Core.** `scope_enhanced.py` / `EnhancedScopeManager` is enhanced relative to
nothing — no legacy `scope.py` exists; rename to `scope.py` / `ScopeManager`.
The `_evaluate_integer` MinimalShell fallback (scope_enhanced.py:361-386) is
opaque near-dead code. The stdio live-tracking properties (state.py:179-215)
say "for test compatibility" but are actually how redirections rebind streams —
initialize `_custom_* = None` in `__init__` and document the design. Layering
violation: scope manager calls *up* into `shell.expansion_manager` for
subscripted nameref targets (scope_enhanced.py:179).

**Builtins.** `parse_flags` (base.py:84) is a clean shared helper used by only
4 of 33 files; everything else hand-rolls. **Real bug found:** `read`'s
combined-option branch ends with `break` (read_builtin.py:323), so
`read -rs -p foo x` treats `-p foo` as variable names; a nested
`raise ValueError` inside its own handler discards messages (:332-337). ~27 raw
`print(..., file=...)` calls bypass the forked-child-aware `self.error()` /
`write_line()`; type_builtin.py repeats a `hasattr` stdout dance 12 times. The
`env` builtin does executor work (spawns a child Shell, rebinds process fds —
environment.py:56-77); `unset` re-implements subscript parsing
(environment.py:552-591). `set` help advertises nonexistent
`enhanced-parser` options (environment.py:461-466).

**io_redirect.** `file_redirect.py` is genuinely textbook (transactional
apply, reverse-order restore, deadlock rationale, the new fd-aware `<` is
clean). The hard part is `setup_builtin_redirections` (manager.py:57, 120
lines): a dual universe of Python stream-swapping for fds 1/2 plus dup2 for
fd≥3. Also: triple-open in `apply_permanent_redirections` (file_redirect.py:322,
:350, :361 — use `os.fdopen` on the already-redirected fd); `IOManager` calls
underscore-private FileRedirector methods as a cross-class contract; hidden
`_saved_fds_list` accumulator state.

### 1.6 Interactive / line editor — B+

**Strengths.** `line_layout.py` (73 lines, pure functions, unit-tested) is
exemplary — exactly the pure-math/terminal-I/O split promised. Every mutating
edit funnels through `_redraw`; movement through `_move_cursor_to`; the
docstrings explain why the old backspace arithmetic was wrong. REPL flow is
legible; signal setup is documented at the entry points; shell.py is still a
thin orchestrator (333 lines).

**Issues, ranked:**
1. **Dead resize state + wasted terminal round-trips:** `_prompt_draw_row` is
   written (line_editor.py:207, :209, :932) but never read; the DSR
   `_query_cursor_row()` queries (and the `_drain_stale_cpr` complexity they
   necessitate) feed only this dead variable. Deleting it is a big legibility
   win.
2. **Vi-mode arrow keys are broken:** CSI parsing lives only in the emacs
   branch (line_editor.py:290-294); in vi insert mode, Up-arrow becomes
   ESC→normal-mode, unbound `[`, then `A`→append-at-end — corrupting state.
   Hoist escape-sequence consumption above the mode split. psh now has three
   ANSI-aware parsers; centralize.
3. **History writing is split and works by accident:** both
   `LineEditor.read_line` (:265) and `source_processor.py:294` add to history,
   masked by the dedup check; multiline commands land twice (physical lines +
   joined). The `import readline` mirror in history_manager.py is vestigial.
4. **Oversized functions:** `__main__.main` ~279 lines (six near-identical
   `--debug-*=` blocks + inline help — extract `parse_args()`/`print_help()`);
   `_update_context_stack` 172 lines (wants a table).
5. **Misplacement:** `TerminalManager` (raw-mode handling) lives in
   `tab_completion.py`; `read_builtin.py:617-626` hand-rolls the same termios
   dance instead of reusing it.

---

## 2. Testing framework health — B+

**Key metrics:** 4,499 tests / 217 files, collection 0.53s clean. 54
skip/skipif/xfail hits (11 skip / 5 skipif / 37 xfail). 249 serial tests,
auto-marking paths match `run_tests.py`'s split exactly. 23 `time.sleep` in 5
files (all PTY/job-control — acceptable). 22 fixed-`/tmp` paths in 7 files.
Zero commented-out tests. Category split: unit 2,418 / integration 1,048 /
conformance 311 / system 110 / regression 104 / performance 9.

**Strengths.** `tests/conftest.py` is exemplary (every non-obvious decision
documented with rationale; `_restore_os_environ` kills a pollution class). The
parallel-safety design is coherent end-to-end. The claims meta-test is robust.
The behavioral golden suite pins `LC_ALL=C` correctly.

**Issues, ranked:**
1. **Legacy/duplicate trees at the repo root:** `conformance_tests/` (123
   tracked files — a *second* golden-file conformance system with its own
   runner, plus tracked debug junk: `bash_output.txt`, `psh_output.txt`,
   `temp_test.sh`); `contract_tests_draft/`; empty `test_invalid/`. CLAUDE.md's
   principle even says "a test in conformance_tests" while the meta-test
   checks `tests/conformance/`. Fold useful goldens in, delete the rest, fix
   the wording.
2. **Dead diverged duplicate framework:** `tests/framework/conformance.py`
   duplicates (and has diverged from) `tests/conformance/conformance_framework.py`
   with zero importers. Empty dirs: `tests/fixtures/`, `tests/helpers/`,
   `tests/resources/`, `tests/unit/interactive/`. Delete.
3. **Fixed `/tmp` paths in unit tests** (worst: `test_env_builtin.py` writes
   `/tmp/env_output.txt` etc.) — xdist collision risk and a violation of the
   project's own rule. Switch to `tmp_path` / isolated fixtures.
4. **Conformance framework doesn't pin locale:** `run_in_shell` copies full
   `os.environ`; sort order and messages can drift by machine. Pin `LC_ALL=C`
   as the behavioral suite does.
5. **Stale skip reasons** ("History functionality not implemented yet" ×4 —
   it is implemented); `isolated_shell_with_temp_dir` docstring still warns
   about the `-s` issue fixed in v0.195.0; two overlapping autouse env
   fixtures.
6. **Coverage gap:** `line_editor.py` (1,089 LOC), `tab_completion.py`,
   `keybindings.py`, `prompt.py` are thin — most interactive tests are opt-in;
   `tests/unit/interactive/` is empty. Buffer ops and completion candidate
   generation are unit-testable without a PTY.
7. Minor: `run_tests.py` Phase 3 hardcodes two test node IDs (will silently
   break on rename); 26 unit files spawn subprocesses where in-process
   `Shell()` would do.

---

## 3. Meta-documentation fitness — C

### Root CLAUDE.md — needs update (smallest job)
- `**Version**: 0.237.0` — 37 releases stale, violating its own sync rule.
- The v0.195.0 subshell `-s` note appears twice and merits one sentence now.
- "NEW in v0.103.0" on ProcessLauncher is 171 releases old.
- **Missing:** the claims meta-test (a contributor adding a "Full support" row
  will hit a failing test with no warning); the exact path
  `tests/conformance/` (the ambiguous "conformance_tests" wording matches the
  legacy dir); the bash-probe verification workflow; the branch/merge/tag
  release convention.
- Everything else verified accurate (commands, flags, Word AST table).

### ARCHITECTURE.md (1,185 lines) — needs rewrite or aggressive pruning
- Describes **removed subsystems**: §3.8 AST validation / `SemanticAnalyzer` /
  `psh/parser/validation/` (doesn't exist); `support/factory.py` /
  ParserFactory (removed v0.256.0); ParserContext profiler (removed).
- Wrong: brace expansion located at `expansion/brace_expansion.py` (actual:
  `psh/brace_expansion.py`); "~93% POSIX" contradicts README's "~98%";
  "3,400+ tests" (actual 4,499); Known Limitations lists two fixed issues.
- ~80 lines of v0.103/0.104 release archaeology (C1/C2/H3–H5) belong in
  CHANGELOG.

### ARCHITECTURE.llm (386 lines) — needs component-map rewrite
- The recipes/invariants format is genuinely LLM-useful and worth keeping, but
  the file map lists ~10 removed files (`pipeline/builder.py`, six purged
  lexer modules, `parser/validation/` ×4, `io_redirect/heredoc.py`,
  `executor/test_evaluator.py`); Known Limitations still claims the subshell
  `-s` issue; testing conventions point at a tests layout that hasn't existed
  for a long time and at the legacy `conformance_tests/`.

### README.md — needs update
- **Flatly wrong:** "Signal Handling: `trap` builtin not yet implemented"
  (TrapBuiltin exists; the same README's own Recent Development lists trap
  work). Broken link to nonexistent `TODO.md`. Built-ins list omits dozens
  (trap, printf, shopt, umask, mapfile, exec, wait, kill, …) — a v0.30-era
  snapshot. LOC/file counts off and basis unstated. "Recent Development" is
  ~80 bullets — a second changelog.
- Test stats verified accurate.

### docs/ tree
- Healthy: `docs/user_guide/` (18 chapters + appendices), `docs/reviews/`.
- Stale top-level docs worth archiving: `FEATURES_TODO.md`,
  `ARCHITECTURE_ROADMAP.md` (2025-07), `posix_conformance_analysis_v0.61.0.md`,
  `implementation_status.md`, `BUGS_FOUND.md` (2026-02, superseded by the
  campaign), one-off plan/summary files (`H3_investigation.md`,
  `PHASE_C_SUMMARY.md`, …). Nothing distinguishes current reference from
  completed plans in `docs/architecture/`.

---

## 4. Cross-cutting findings

1. **Packaging is broken below Python 3.12** (see executive summary).
   Simplest fix: bump `requires-python` to `>=3.12`, drop stale classifiers,
   retarget ruff from `py38`. Alternative: fix the PEP 701 f-string + add
   `from __future__ import annotations` to 4 files + CI matrix.
2. **Top-level module sprawl:** 23 orphan modules (7,229 LOC, 15% of the tree)
   sit beside 12 well-formed packages. Logical homes: line_editor/line_layout/
   tab_completion/prompt/keybindings/multiline_handler/history_expansion →
   `interactive/`; arithmetic/brace_expansion/aliases → `expansion/`;
   token_types/token_stream/token_transformer → `lexer/`; functions.py →
   `core/`; job_control.py → `interactive/` or `executor/`. Only shell.py,
   __main__.py, ast_nodes.py, version.py belong at top level. ~10 moves with
   import shims would make the layout match the documented architecture.
3. **Four parallel pattern-matching engines** —
   `PatternMatcher.shell_pattern_to_regex` (most complete), extglob's
   `_convert_pattern`, control_flow's fnmatch trio (which *also* lazily imports
   PatternMatcher — two engines in one file), and
   enhanced_test_evaluator's `_pattern_match`. A classic source of
   case/`[[ == ]]`/`${var#pat}` divergence bugs. Consolidate on PatternMatcher
   in a shared module.
4. **Duplicated escape/quote utilities:** `_shell_quote` ×2; echo/printf-style
   escape processing ~6× including twice *within* `builtins/io.py`. One
   `psh/utils/escapes.py` is a free win.
5. **Exceptions scattered across 7 modules with no common root:**
   `FunctionReturn` lives in `builtins/function_support.py` away from its
   control-flow siblings; ShellArithmeticError, BraceExpansionError,
   LexerError, ParseError, PrintOptionError each live in their own module;
   there is no `PshError` base, so "catch any psh error" is impossible.
6. **shell.py is a circular-import hub:** 53 deferred `from ..shell import
   Shell` sites; 362 function-local imports total (variable.py alone has 40).
   Many could be TYPE_CHECKING imports or depend on ShellState/protocols.
7. **Lint/typing half-installed:** 87% of functions have type hints (excellent)
   but nothing checks them (no mypy/pyright config); ruff selects only
   F401/F811/F841/I/W yet the tree carries 37 violations (36 auto-fixable);
   CLAUDE.md scopes linting to the combinator package only.
8. **Positive:** state access is consistent (zero direct `state.variables[...]`
   dict accesses outside the scope implementation); only 3 honest TODOs and no
   FIXME/XXX/HACK markers; no `_v2`/`old_` vestigial code.

---

## 5. Recommended program of work

Ordered by leverage; sized in likely releases.

**Tier A — correctness and honesty (do first, ~3–4 releases)**
1. Fix the Python-version claim (decide: `>=3.12` or restore 3.8 compat) and
   run `ruff check psh/ --fix` (clears 36/37 violations). Widen ruff scope in
   CI/CLAUDE.md.
2. Fix the two newly found behavior bugs: `read` cluster-option `break`
   (read_builtin.py:323) and the stdout-vs-stderr background-job notice
   inconsistency. Remove the surviving pytest sniff (command_sub.py:63).
   Decide the combinator's fate for the two drifted features (fix or document
   as known divergence + update the stale "0 failures" guide).
3. Meta-docs sweep: root CLAUDE.md (version, claims meta-test, conformance
   path, prune duplicate notes), README (trap claim, builtins list, TODO.md
   link, move Recent Development to CHANGELOG), ARCHITECTURE.md/.llm (delete
   removed-subsystem sections, fix the file maps, drop release archaeology).
4. Test-tree cleanup: delete/fold the legacy `conformance_tests/`,
   `contract_tests_draft/`, `tests/framework/conformance.py`, empty dirs;
   fix `/tmp` paths; pin `LC_ALL=C` in the conformance framework; sweep stale
   skip reasons.

**Tier B — structural decomposition (the "textbook quality" work, ~4–6 releases)**
5. Split `expansion/variable.py` into arrays/operators/operands/fields with a
   facade; extract `_resolve_array_element`; unify the four `$`-scanners.
6. Consolidate pattern matching on PatternMatcher; create `utils/escapes.py`;
   centralize exceptions under a `PshError` root (move FunctionReturn).
7. Lexer cleanup: kill literal.py's string-archaeology helpers (feed it the
   O(n) map), delete dead config flags and dead functions, dedupe backtick/
   comment-start logic.
8. Executor: extract `JobManager.launch_background()`; split
   `CommandExecutor.execute`; delete process_metrics and codename comments.
9. Interactive: delete `_prompt_draw_row`/DSR machinery; centralize escape
   parsing (fixes vi arrows); single history writer; extract `parse_args` from
   `__main__`.
10. Builtins: adopt `parse_flags` across the tree; route all errors through
    `self.error()`/`write_line()`; move env's process work to the executor.

**Tier C — layout and infrastructure (~2–3 releases)**
11. Move the 23 top-level orphan modules into their packages (with shims);
    rename `scope_enhanced.py` → `scope.py`.
12. Add minimal mypy config (non-strict, core/ + ast_nodes.py first); add
    in-process unit tests for line-editor buffer ops and completion.
13. Prune dead rd error-recovery scaffolding and vestigial AST quote-type
    fields; archive stale top-level docs into `docs/archive/`.

**Subsystem CLAUDE.md refresh** should ride along with whichever tier touches
each subsystem — every one of the eight reviewed files has specific stale
claims (catalogued in sections 1–2 above); the executor and io_redirect ones
misstate flagship APIs, which for a teaching codebase is the costliest kind of
error.
