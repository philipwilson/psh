# PSH Codebase Study (2026-06-05) — Phase 2: Architecture & Code Quality

> **Resolution status (triage fixes through v0.215.0; reviewed against v0.227.0,
> updated 2026-06-06).** The entire prioritized high/medium triage list
> (Section 3) has been resolved, along with every §1.3 duplication item. Mapping
> of finding → fix:
>
> | Finding | Status | Version |
> |---|---|---|
> | Test-only pipeline path (`eval_test_mode`) — #1 | removed | v0.208.0 |
> | Bare `print()` bypasses `shell.stdout` — #2 | all 47 calls routed via `shell.stdout` | v0.207.0 |
> | Recognizer registry swallows defects — #3 | raises with context (+ test) | v0.160-era safety pass |
> | Redundant `except` defaults index 0 — #4 | narrowed to `ArithmeticError` | v0.196.0 + v0.214.0 |
> | Broad except relabels control-flow — #5 | inner catch narrowed | v0.196-era safety pass |
> | ShellFormatter broken node output — #6 | subshell/brace/`[[ ]]` formatted (both formatters) | v0.209.0 |
> | Vestigial readline completion — #7 | `CompletionManager` removed | v0.211.0 |
> | Parser-side validation dormant — #8 | subsystem removed | v0.197.0 |
> | Dual parameter-expansion engines — #9 | one `_apply_operator` | v0.196.0 |
> | Array/quote disambiguation ×3 — #10 | shared `QuoteState` | v0.198.0 |
> | Heredoc detection diverged — #11 | unified in `utils/heredoc_detection` (+ `<<-` fix) | v0.202.0 |
> | Redirect-type dispatch ×4 — #12 | shared predicates | v0.198.0 |
> | Broad `except Exception` in executor — #13 | narrowed + `--debug-exec` tracebacks | v0.215.0 |
> | OptionHandler dead / executor reimplements — #16 | dead methods removed | v0.213.0 |
> | ExecutionContext dead factories/fields — #17 | trimmed 189→60 lines | v0.212.0 |
> | Visitor `generic_visit` ×3 + overlapping checks — #19 | shared `traversal` + `analysis_helpers` | v0.205.0 |
>
> Also fixed beyond the table: glob→regex conversion unified (v0.203.0);
> command-position classification unified (v0.204.0); analysis-visitor latent
> bugs — `until` loops, brace-group crash (v0.206.0); command-substitution
> output flush (v0.210.0).
>
> **Triage table complete.** The five items that were still open at v0.221.0 —
> the §1.1 private-API-leak items (#14 `_in_forked_child`, #15 executor↔expansion
> privates, #20 combinator→RD WordBuilder privates, #21 builtins calling
> siblings' privates) and the oversized `setup_builtin_redirections` (#18) — were
> resolved in v0.223.0–v0.227.0 by promoting the shared operations to public API
> (`ShellState.in_forked_child`, `ExpansionManager.expand_expansion` /
> `process_dquote_escapes` / `set_var_or_array_element`,
> `WordBuilder.has_decomposable_parts` / `token_part_to_word_part`,
> `TestBuiltin.evaluate_test`/`evaluate_unary`, `ParserConfigBuiltin.set_mode`,
> `PrintfBuiltin.process_format_string_posix`) and extracting a shared
> builtin-output-file helper.
>
> **Still open** (lower priority, not in the prioritized triage table): §1.5
> oversized `line_editor.py` (~1300L); and the 2026-02-17 carry-overs noted in
> Section 4 (`source_text` plumbing, string-matching parse heuristics, docs
> drift, combinator CI lane). The §1.1/§1.2/§1.3/§1.4 themes still list smaller
> Low-severity instances beyond the triaged top-21. Line numbers in Sections 1–2
> predate the v0.216.0–v0.227.0 work and may be off by a few lines.
>
> **Work since v0.215.0 (v0.216.0–v0.221.0) is feature additions, not triage
> items** — none of the still-open findings were resolved by it: brace expansion
> of expansion items + arithmetic fd-dup targets (0.216.0), `${var@OP}` transforms
> (0.217.0), `mapfile`/`readarray` (0.218.0), `let` (0.219.0), and namerefs +
> `${!var}` indirect expansion (0.220.0 scalar, 0.221.0 array-element). One new
> coupling was introduced and then removed in the same pass: namerefs Phase 2
> initially had `scope_enhanced.py` reach into a private
> `VariableExpander._set_var_or_array_element`; that helper was promoted to the
> public `ExpansionManager.set_var_or_array_element()` (so §1.1/§1.7 gained no new
> instance).

This report synthesizes per-subsystem audits of the PSH codebase into (1) cross-cutting
themes that aggregate findings of the same kind across subsystems, (2) per-subsystem health
summaries and findings, and (3) a prioritized triage table of the top findings. It also
cross-references the still-open items from the 2026-02-17 review so the overlap between
previously-known and newly-surfaced issues is visible.

Subsystems audited: `psh/builtins/`, `psh/core/`, `psh/executor/`, `psh/expansion/`,
`psh/interactive/`, `psh/io_redirect/`, `psh/lexer/`, `psh/parser/`, `psh/scripting/`,
`psh/utils/`, `psh/visitor/`.

---

## 1. Cross-Cutting Themes

These themes aggregate findings of the same KIND across subsystems. A finding can appear in
more than one theme only where it genuinely spans kinds; otherwise it is filed under its
dominant kind.

### 1.1 Private-API Leakage (callers reach into `_underscore` members / internal data structures)

This is the most pervasive coupling problem in the codebase: many components reach into a
sibling component's underscore-prefixed methods or internal storage, so the depended-upon
component cannot be refactored without silent breakage, and the real public contract is
obscured.

- Builtins call sibling builtins' private methods:
  - `psh/builtins/test_command.py:411-412` — `TestBuiltin()._evaluate_test`
  - `psh/builtins/parser_control.py:278-279` — `ParserConfigBuiltin()._set_mode`
  - `psh/builtins/print_builtin.py:92-93` — `PrintfBuiltin()._process_format_string_posix`
- Builtins / executor reach into core array internals:
  - `psh/builtins/function_support.py:320-323` — `IndexedArray._elements.items()`
  - `psh/executor/array.py:54` — `array._elements.keys()`
  - `psh/executor/test_evaluator.py:195,199` — `var_obj.value._elements`
- Executor reaches into ExpansionManager private methods:
  - `psh/executor/command.py:441` — `expansion_manager._process_dquote_escapes()`
  - `psh/executor/command.py:450` — `expansion_manager._expand_expansion()`
  - (manager-side definitions: `psh/expansion/manager.py:355-377`, `496-508`)
- Executor instantiates a builtin and calls its private evaluator:
  - `psh/executor/test_evaluator.py:156` — `TestBuiltin()._evaluate_unary()`
- `_in_forked_child` private state field read across builtins/expansion via defensive
  `hasattr`/`getattr`:
  - definition `psh/core/state.py:123`; reads at `psh/builtins/io.py:178,336,755`,
    `psh/builtins/print_builtin.py:235`, `psh/builtins/function_support.py:389`,
    `psh/builtins/environment.py:146,212,448`; write at `psh/expansion/command_sub.py:78`
- Interactive SignalManager reaches into TrapManager internals:
  - `psh/interactive/signal_manager.py:117,121-122` — `trap_manager.state.trap_handlers`
- rc_loader mutates `shell.variables` dict directly instead of via state accessors:
  - `psh/interactive/rc_loader.py:28,36`
- Combinator parser reaches into recursive-descent WordBuilder privates (contradicting the
  documented "independent parser" boundary):
  - `psh/parser/combinators/expansions.py:138-139` — `WordBuilder._has_decomposable_parts`,
    `_token_part_to_word_part`
- Lexer reaches across an object boundary into a private factory:
  - `psh/lexer/quote_parser.py:336,341,343,345` — `self.parser._create_literal_part(...)`
- scripting reaches into a private Shell attribute and deep object chains:
  - `psh/scripting/source_processor.py:307` — `shell._active_parser`
  - `psh/scripting/source_processor.py:347` — `shell.interactive_manager.history_manager.add_to_history`

Common remedy: promote the genuinely-shared operations to public API (drop the underscore, add
narrow accessors such as `IndexedArray.items()`/`next_index()`, `TrapManager.get_handler()`,
`ExpansionManager.expand_assignment_value()`, `Shell.add_history()`/`active_parser`), and make
`in_forked_child` a real first-class state attribute.

### 1.2 Broad / Silent Exception Handling (`except Exception` and over-broad catches)

Numerous hot or central paths wrap large bodies in `except Exception` (or redundant
`except (X, Exception)`) and downgrade genuine defects (KeyError, AttributeError, logic bugs)
into benign-looking shell errors, exit code 1, or "treat as default" fallbacks. This directly
undermines the project's "transparent failure / clarity over performance" educational mission.

- `psh/executor/command.py:183-206` — whole `execute()` body wrapped; bugs become `psh: {e}`
  return 1 **(carried over from 2026-02-17 review — STILL OPEN)**
- `psh/scripting/source_processor.py:381-386` (and inner `:360-369`) — relabels control-flow
  and real defects as "unexpected error" **(carried over from 2026-02-17 — STILL OPEN)**
- `psh/expansion/variable.py:140,300,515` — redundant `except (ArithmeticError, Exception)`
  silently defaults `index = 0`
- `psh/expansion/command_sub.py:41-90` — forked child wraps all setup in bare except → `os._exit(1)`
- `psh/lexer/recognizers/registry.py:88-90` — recognizer registry swallows recognizer bugs,
  DEBUG-logs, and continues (silent mis-tokenization)
- `psh/executor/strategies.py:75-83,132-139`; `psh/executor/array.py:80-83`
  (`except (ValueError, Exception)` is redundant); `psh/executor/function.py:113-115`
- `psh/core/trap_manager.py:164-166` — swallows all trap-command errors
- `psh/interactive/repl_loop.py:90-92` — catch-all discards traceback (also hardcodes
  `errno == 5` instead of `errno.EIO`)
- `psh/builtins/print_builtin.py:101-104`; `psh/builtins/core.py:51` — `except AttributeError`
  history fallback hides defects
- `psh/interactive/rc_loader.py:38-40` — broad catch around `execute_from_source`
- `psh/parser/validation/validation_pipeline.py:86-100` — rule crashes downgraded to warnings
  (dead in production per theme 1.4)
- `psh/utils/signal_utils.py:136-142` (`__del__`); `psh/utils/ast_debug.py:74-80` — silent
  format downgrade (drop AttributeError)
- `psh/parser/combinators/expansions.py:230` — `except Exception: return False` in command-sub
  validation

Note: `psh/builtins/` is a positive outlier — zero broad/bare excepts in the whole package.

Common remedy: narrow to the specific expected exceptions; let unexpected ones propagate (or
print a traceback gated on `debug-exec`); keep deliberate broad catches only where justified
(REPL survival, `__del__`, async-signal-safety) and document why.

### 1.3 Duplication / Divergent Reimplementations of the Same Logic

The most damaging clarity hazard repeated across subsystems: the same conceptual operation is
implemented multiple times, with the copies having already DIVERGED in behavior, so a reader
cannot tell which is authoritative and a fix to one silently leaves the others wrong.

- **Two parallel expansion engines** (AST path vs string-parsing path) duplicate parameter
  expansion: `psh/expansion/variable.py:20-108,442-634,657-774`; `psh/expansion/evaluator.py:71-92`
  — `${VAR:-default}` and `${VAR:?}` semantics live in two places.
- **Heredoc-detection diverged** between script and interactive paths:
  `psh/scripting/source_processor.py:388-430,502-567` vs `psh/multiline_handler.py:240-320`
  (different arithmetic/expansion exclusion rules).
- **Array-assignment / quote disambiguation** reimplemented in three lexer modules with
  independent quote scanners: `psh/lexer/modular_lexer.py:354-419`;
  `psh/lexer/recognizers/literal.py:437-624,728-823`; `psh/lexer/pure_helpers.py:58-216`.
- **Redirect-type dispatch** written out four times:
  `psh/io_redirect/manager.py:57-154,195-261`; `psh/io_redirect/file_redirect.py:136-193,210-277`.
  Plus the noclobber predicate inlined in five places (`file_redirect.py:30-33,121-122`,
  `manager.py:91-92,210-211,226-227`).
- **OptionHandler logic reimplemented in executor**: `psh/core/options.py:92-107` (`print_xtrace`)
  duplicated at `psh/executor/command.py:455-460`; errexit at `psh/executor/core.py:112-151`;
  pipefail at `psh/executor/pipeline.py:287-288,402-403`.
- **Command-position tracking computed twice**: `psh/lexer/modular_lexer.py:201-266` and
  `psh/lexer/keyword_normalizer.py:24-110`.
- **Glob→regex conversion duplicated**: `psh/expansion/parameter_expansion.py:341-412` vs
  `psh/expansion/extglob.py:111-187` (diverge on leading `]` in classes).
- **History-expansion regex literal duplicated four times**:
  `psh/scripting/source_processor.py:114,345`; `psh/multiline_handler.py:118`;
  `psh/line_editor.py:263`.
- **Three divergent `generic_visit` traversal strategies**: `psh/visitor/base.py:47-62`;
  `psh/visitor/metrics_visitor.py:563-573`; `psh/visitor/security_visitor.py:320-332`;
  `psh/visitor/linter_visitor.py:394-406`.
- **Overlapping analysis checks** (undefined-var, quoting, dangerous-command) reimplemented
  three times: `psh/visitor/enhanced_validator_visitor.py:403-477,618-659`;
  `psh/visitor/linter_visitor.py:348-392`; `psh/visitor/security_visitor.py:68-152`.
- **Directory-stack helpers duplicated** (with a third divergent variant):
  `psh/builtins/directory_stack.py:224-229,358-363,478-490`.
- **Enable/disable feature maps duplicated**: `psh/builtins/parser_control.py:155-189` vs `191-225`.
- **Executor wrapper duplication / re-instantiation**: `psh/executor/command.py:294-300,378-380`
  (pass-through wrappers); `psh/executor/command.py:560-566` and `psh/executor/strategies.py:204-218`
  (re-instantiate executors that core already caches).
- **Terminal-control teardown copied** between `psh/executor/pipeline.py:303-311` and
  `psh/executor/strategies.py:414-422`.
- **MinimalShell arithmetic wiring duplicated**: `psh/core/scope_enhanced.py:277-319`.

### 1.4 Dead Code / Dormant Subsystems

Large amounts of unused or never-triggered machinery mislead readers into thinking features
exist or paths run when they do not.

> **Resolution (v0.197.0–v0.232.0).** Removed: parser-side validation subsystem
> (#8, v0.197.0); readline completion/history (#7, v0.211.0); ExecutionContext
> dead factories/fields (#17, v0.212.0); OptionHandler dead methods (#16,
> v0.213.0); HeredocHandler + `IOManager._saved_fds` (v0.228.0);
> `ShellState._original_signal_handlers`, `SignalManager._interactive_mode` /
> `get_sigchld_fd`, the unreachable `CommandList` branch (v0.229.0); the scripting
> `ScriptComponent.execute` abstraction + four forwarders + unused
> `expansion_manager` (v0.230.0); the never-enabled validator
> arithmetic-suppression toggle/config + the `_is_piped_to_shell` curl|sh stub
> (v0.231.0); and the unused `QuoteParsingContext.parse_quote_at_position` /
> `get_quote_rules` (v0.232.0).
>
> **Verified NOT removable (kept):** the near-dead string-based array helpers were
> already consolidated by the dual-engine work (v0.196.0) and are now live; the
> `SignalRegistry` diagnostic API, the `ParserProfiler`, and the speculative
> `LexerConfig` knobs are exercised by dedicated tests / tested `create_*_config`
> presets, so they are tested-but-dormant rather than cruft; `LexerErrorHandler`
> has a package-API existence test; the ParserContext heredoc trackers are
> actively used by the RD parser (a §1.3 dedup concern, not dead code).
> `SecurityIssue.node` was kept as a plausible result-object field.

- **Parser-side validation subsystem (~1311 LOC) dormant**, duplicating the visitor validators
  production actually uses: `psh/parser/validation/` (all files);
  `psh/parser/recursive_descent/parser.py:176-221`; `psh/parser/config.py:55-57`.
- **Readline completion/history path fully vestigial** (LineEditor bypasses it):
  `psh/interactive/completion_manager.py:18-77,79-141`; `psh/interactive/history_manager.py:17,31,57`.
- **HeredocHandler class never called**: `psh/io_redirect/heredoc.py:8-40` (+ `manager.py:9,25`).
- **ExecutionContext dead factories/fields**: `psh/executor/context.py:64-81,101-189` and
  fields `in_subshell:29`, `suppress_function_lookup:41`, `exec_mode:42`, `background_job:38`.
- **OptionHandler dead methods**: `psh/core/options.py:14-47,109-132` (zero callers).
- **Redundant ParserContext heredoc tracking + profiler**:
  `psh/parser/recursive_descent/context.py:19-27,30-134,417-452`; `parser.py:238-255,344-364`.
- **Lexer dead config/error machinery**: `psh/lexer/position.py:299-343` (LexerErrorHandler),
  `146-172` (~15 unused LexerConfig knobs); `psh/lexer/quote_parser.py:318-353,370-372`;
  six test-only `pure_helpers` functions (`pure_helpers.py:13-55,387-422,476-498,501-532,578-602,639-693`).
- **Scripting scaffolding**: abstract `execute()` never invoked
  (`psh/scripting/base.py:17-20` + four subclass forwarders); `base.expansion_manager`
  (`base.py:15`) unused.
- **Visitor dead state/stubs**: `psh/visitor/enhanced_validator_visitor.py:172-173,413-414,573-574`
  (context toggles never set True); `psh/visitor/security_visitor.py:141-147,272-276`
  (`_is_piped_to_shell` permanent stub); `SecurityIssue.node` never read (`security_visitor.py:30-40`).
- **SignalRegistry diagnostic API dead in production**: `psh/utils/signal_utils.py:270-307,435-446,471-478`.
- **Core dead fields**: `psh/core/state.py:147-149` (`_original_signal_handlers`).
- **Unreachable executor branches**: `psh/executor/core.py:308-315` (CommandList special-case);
  `psh/interactive/signal_manager.py:17,207-215`; `psh/interactive/base.py:16`.
- **Dead I/O attribute**: `psh/io_redirect/manager.py:29` (`_saved_fds`).
- **Near-dead string-based array helpers**: `psh/expansion/variable.py:776-815,817-884`.

### 1.5 Oversized / Mixed-Altitude Modules

Several modules conflate multiple teachable concerns. (The audits explicitly flagged a few
large modules as "do NOT split" — `psh/interactive/signal_manager.py` and the core
ParserContext token/state model — because the cohesion is genuine.)

- `psh/lexer/recognizers/literal.py:1-911` — word collection + glob + extglob + array
  assignment + inline ANSI-C quotes + concatenation heuristics.
- `psh/builtins/function_support.py:1-822` — declare/typeset engine + readonly + return +
  FunctionReturn; file name no longer matches contents.
- `psh/builtins/io.py:1-778` — echo + pwd + a ~480-line printf engine.
- `psh/expansion/manager.py:88-693` — orchestration mixed with `$@`-affix scanner and two
  arithmetic pre-expansion scanners (duplicating `variable.py`).
- `psh/scripting/source_processor.py:1-568` — read loop + completeness detection (fragile
  string-match table) + heredoc scanners + the tokenize→execute pipeline.
- `psh/io_redirect/manager.py:57-154` — `setup_builtin_redirections` reimplements per-type
  logic at the Python-object level instead of delegating to FileRedirector.

### 1.6 Output Routing / Stream Ownership

A subsystem-specific but high-impact correctness theme: builtins that write via bare `print()`
bypass `shell.stdout`, silently breaking redirection, pipelines, command substitution, and the
`captured_shell` test fixture.

- `psh/builtins/parser_control.py:81-219` (21 calls); `psh/builtins/debug_control.py:48-288`
  (14 calls, never touches `shell.stdout`); `psh/builtins/job_control.py:41,45,77,151`;
  `psh/builtins/kill_command.py:274,286,288,290`; `psh/builtins/navigation.py:96,111`.
- Related stream-ownership coupling: `psh/io_redirect/file_redirect.py:210-277` mirrors
  std streams across both `state` and `shell` by hand.

### 1.7 Layering Inversions / Upward Coupling

Lower-level components reach back up into the Shell/orchestrator, contradicting the layered
architecture in CLAUDE.md.

- `psh/core/scope_enhanced.py:340-342` — scope manager reaches up through
  `self._shell.state.function_stack` for FUNCNAME.
- `psh/executor/core.py:289-292 → psh/shell.py:161-180` — executor bounces back out to Shell to
  reach a helper that itself lives in the executor (`test_evaluator.py`).
- `psh/io_redirect/process_sub.py:67-79` — forked child re-tokenizes/parses a source string
  instead of reusing the already-parsed AST (Input→Lex→Parse→Execute re-entered mid-execution).

---

## 2. Per-Subsystem Findings

### 2.1 `psh/builtins/` — Health: GOOD

Clean decorator-based registry, minimal Builtin base class, and notably disciplined exception
handling (zero broad/bare excepts in the package). Dominant systemic issue is inconsistent
output routing via bare `print()`; secondary issues are a few private-API leaks, genuine
duplication, and two oversized modules.

| Title | Kind | Sev | Effort | Location |
|---|---|---|---|---|
| Bare `print()` bypasses `shell.stdout` | clarity | High | Medium | parser_control.py:81-219; debug_control.py:48-288; job_control.py:41,45,77,151; kill_command.py:274-290; navigation.py:96,111 |
| Builtins call siblings' private `_underscore` methods | private-api-leak | Medium | Small | test_command.py:411-412; parser_control.py:278-279; print_builtin.py:92-93 |
| Reaches into `IndexedArray._elements` | private-api-leak | Medium | Small | function_support.py:320-323 |
| Duplicated pushd/popd/dirs helpers (3rd divergent) | duplication | Low | Small | directory_stack.py:224-229,358-363,478-490 |
| Near-identical enable/disable feature maps | duplication | Low | Small | parser_control.py:155-189 vs 191-225 |
| `function_support.py` oversized (822L) | oversized-module | Low | Medium | function_support.py:1-822 |
| `io.py` bundles echo+pwd+printf (778L) | oversized-module | Low | Medium | io.py:1-778 |
| parser-config output untestable via captured_shell | clarity | Low | Small | parser_control.py:79-225 |

### 2.2 `psh/core/` — Health: GOOD (with concrete clarity/correctness traps)

Small, well-documented, mostly cohesive. Biggest issues: two disjoint special-variable systems
with an upward back-reference, dead/duplicated OptionHandler logic, the `_in_forked_child`
private leak, and a misleading no-op `pass` in `remove_attribute`.

| Title | Kind | Sev | Effort | Location |
|---|---|---|---|---|
| Two disjoint special-variable systems + scope→state back-coupling | coupling | Medium | Medium | state.py:283-303; scope_enhanced.py:84-103,326-347 |
| OptionHandler largely dead; executor reimplements it | dead-code | Medium | Small | options.py:14-47,92-107,109-132 |
| `_in_forked_child` private leak via hasattr/getattr | private-api-leak | Medium | Medium | state.py:123; io.py:178,336,755; environment.py:146,212,448; command_sub.py:78 |
| `remove_attribute(EXPORT)` misleading no-op `pass` | broad-exception | Medium | Small | scope_enhanced.py:463-467 |
| Bare `except Exception` swallows trap-command errors | broad-exception | Low | Small | trap_manager.py:164-166 |
| `_evaluate_integer` MinimalShell fallback duplication | duplication | Low | Medium | scope_enhanced.py:277-319 |
| Redundant pass-through assignment wrappers | duplication | Low | Small | command.py:294-300,378-380 |
| Dead `_original_signal_handlers` field | dead-code | Low | Small | state.py:147-149 |
| `options` dict conflates 4 categories of flags | clarity | Low | Medium | state.py:47-93 |
| stdout/stdin/stderr `hasattr` on maybe-present attrs | clarity | Low | Small | state.py:167-203 |

### 2.3 `psh/executor/` — Health: GOOD architecture, several clarity erosions

Well-structured visitor/strategy/launcher design; ProcessLauncher centralization is a real
strength. Issues: a large test-only pipeline path embedded in production, private-API reaches,
ExecutionContext dead code, broad excepts in hot paths, and duplicated teardown.

| Title | Kind | Sev | Effort | Location |
|---|---|---|---|---|
| Test-only pipeline path embedded in production | coupling | High | Medium | pipeline.py:106-111,320-479; state.py:155 (eval_test_mode) |
| Callers reach into other components' privates | private-api-leak | Medium | Medium | command.py:441,450; test_evaluator.py:156,195,199; array.py:54 |
| ExecutionContext dead factories/fields | dead-code | Medium | Small | context.py:64-81,101-189 + fields :29,38,41,42 |
| Broad `except Exception` in hot paths | broad-exception | Medium | Medium | command.py:183-206; strategies.py:75-83,132-139; array.py:80-83; function.py:113-115 |
| Foreground teardown duplicated | duplication | Low | Small | pipeline.py:303-311 vs strategies.py:414-422 |
| EnhancedTest bounces out to Shell | coupling | Low | Small | core.py:289-292 → shell.py:161-180 |
| `generic_visit` CommandList branch unreachable | dead-code | Low | Small | core.py:308-315 |
| Per-call re-instantiation of cached executors | duplication | Low | Small | command.py:560-566; strategies.py:204-218 |

### 2.4 `psh/expansion/` — Health: REASONABLE, dominated by dual engines

Single-responsibility expander classes coordinated by ExpansionManager, but two parallel
expansion engines (AST path vs string-parsing) split canonical operator/array/nounset logic.

| Title | Kind | Sev | Effort | Location |
|---|---|---|---|---|
| Two parallel expansion engines duplicate param logic | duplication | High | Large | variable.py:20-108,442-634,657-774; evaluator.py:71-92 |
| Redundant `except (ArithmeticError, Exception)` | broad-exception | High | Small | variable.py:140,300,515 |
| Command-sub child bare `except` → exit 1 | broad-exception | Medium | Small | command_sub.py:41-90 |
| Executor reaches into manager privates | private-api-leak | Medium | Small | command.py:441,450; manager.py:355-377,496-508 |
| `expand_string_variables` intricate escape handling | clarity | Medium | Medium | variable.py:740-774 |
| String-based array helpers near-dead | dead-code | Low | Medium | variable.py:776-815,817-884 |
| `manager.py` mixed altitude (oversized) | oversized-module | Low | Medium | manager.py:88-233,269-353,575-693 |
| Glob→regex duplicated with extglob | duplication | Low | Medium | parameter_expansion.py:341-412; extglob.py:111-187 |

### 2.5 `psh/interactive/` — Health: GOOD, but a fully-dead readline layer

Each component has a single clear responsibility. Dominant problem: the readline-based
completion/history path is silently superseded by the custom LineEditor, so it is dead and
teaches the wrong mechanism.

| Title | Kind | Sev | Effort | Location |
|---|---|---|---|---|
| Readline completion fully vestigial | dead-code | High | Medium | completion_manager.py:18-77; line_editor.py:1034; multiline_handler.py:45 |
| Dead `complete_*` helpers | dead-code | Medium | Small | completion_manager.py:79-141 |
| HistoryManager mutates readline history nothing reads | dead-code | Medium | Small | history_manager.py:17,31,57 |
| SignalManager reaches into trap_manager privates | private-api-leak | Medium | Small | signal_manager.py:117,121-122 |
| Builtins history fallback hides defects | broad-exception | Medium | Small | print_builtin.py:101-104; core.py:51 |
| REPL catch-all masks executor defects | broad-exception | Medium | Small | repl_loop.py:90-92 |
| rc_loader mutates `shell.variables` + broad catch | private-api-leak | Low | Small | rc_loader.py:28,36,38-40 |
| Dead `_interactive_mode` / base.multi_line_handler | dead-code | Low | Small | signal_manager.py:17; base.py:16 |
| `get_sigchld_fd` unused public API | dead-code | Low | Small | signal_manager.py:207-215 |
| CLAUDE.md doc drift | clarity | Low | Medium | interactive/CLAUDE.md:114-146,261-289 |
| signal_manager.py size OK — do NOT split | oversized-module | Low | Small | signal_manager.py:1-296 |

### 2.6 `psh/io_redirect/` — Health: GOOD boundaries, duplicated internals

Clean package boundary (exports only IOManager; narrow exceptions). Internal weaknesses:
four-times-duplicated redirect dispatch, an oversized builtin-redirection method with a fragile
fd-dup special-case, and dead code (HeredocHandler, `_saved_fds`).

| Title | Kind | Sev | Effort | Location |
|---|---|---|---|---|
| Redirect-type dispatch duplicated 4x | duplication | High | Large | manager.py:57-154,195-261; file_redirect.py:136-193,210-277 |
| `setup_builtin_redirections` oversized, reimplements logic | oversized-module | Medium | Medium | manager.py:57-154 |
| Builtin `>&` only handles 2>&1 / 1>&2 | clarity | Medium | Medium | manager.py:139-152 |
| noclobber duplicated 5x / 3 error conventions | duplication | Medium | Small | file_redirect.py:30-33,121-122; manager.py:91-92,210-211,226-227 |
| HeredocHandler dead | dead-code | Medium | Small | heredoc.py:8-40; manager.py:9,25 |
| Dead `_saved_fds` attribute | dead-code | Low | Small | manager.py:29 |
| process_sub re-tokenizes instead of reusing AST | clarity | Low | Medium | process_sub.py:67-79 |
| `apply_permanent_redirections` couples to shell.std* | coupling | Low | Medium | file_redirect.py:210-277 |

### 2.7 `psh/lexer/` — Health: GOOD pattern, accumulated cruft

Clean modular-recognizer pattern. Main issues: array/quote disambiguation duplicated across
three modules, a broad except in the recognizer registry, an oversized literal recognizer, and
substantial dead/speculative config and helpers.

| Title | Kind | Sev | Effort | Location |
|---|---|---|---|---|
| Recognizer registry swallows recognizer defects | broad-exception | High | Small | recognizers/registry.py:88-90 |
| Array/quote disambiguation duplicated 3x | duplication | High | Large | modular_lexer.py:354-419; literal.py:437-624,728-823; pure_helpers.py:58-216 |
| LiteralRecognizer oversized (~900L) | oversized-module | Medium | Medium | recognizers/literal.py:1-911 |
| Dead LexerErrorHandler | dead-code | Medium | Small | position.py:299-343 |
| ~15 unused LexerConfig knobs | dead-code | Medium | Small | position.py:146-172 |
| Command-position tracked twice | duplication | Medium | Medium | modular_lexer.py:201-266; keyword_normalizer.py:24-110 |
| Test-only pure_helpers functions | dead-code | Low | Small | pure_helpers.py:13-55,387-422,476-498,501-532,578-602,639-693 |
| Dead QuoteParsingContext methods | dead-code | Low | Small | quote_parser.py:318-353,370-372 |
| Private `_create_literal_part` reached across boundary | private-api-leak | Low | Small | quote_parser.py:336,341,343,345 |
| `position` setter O(n) rebuild on backward move | clarity | Low | Small | modular_lexer.py:95-104 |

### 2.8 `psh/parser/` — Health: GOOD structure, dormant machinery

Clean delegating recursive-descent parser plus a deliberately parallel combinator parser.
Main issues: a dormant parser-side validation subsystem (~1311 LOC), redundant heredoc
tracking, a never-enabled profiler, and the combinator parser's real dependence on RD internals
(contradicting its "independent" documentation).

| Title | Kind | Sev | Effort | Location |
|---|---|---|---|---|
| Parser-side validation dormant, duplicates visitor validators | dead-code | High | Medium | parser/validation/ (all); recursive_descent/parser.py:176-221; config.py:55-57 |
| Redundant ParserContext heredoc tracking | dead-code | Medium | Medium | recursive_descent/context.py:19-27,161,417-452; parser.py:344-364 |
| Combinator parser reaches into RD WordBuilder privates | private-api-leak | Medium | Small | combinators/expansions.py:138-139,151,182; commands.py:332 |
| Fragile substring/string-match error & validation logic | clarity | Low | Small | context.py:280-289; combinators/expansions.py:206-232 |
| Broad except downgrades rule crashes to warnings | broad-exception | Low | Small | validation/validation_pipeline.py:86-100 |
| Profiler wired but never enabled | dead-code | Low | Small | context.py:30-134,137-194; parser.py:238-255; config.py:54 |
| context.py mixed responsibilities (extract profiler only) | oversized-module | Low | Small | recursive_descent/context.py:1-529 |

### 2.9 `psh/scripting/` — Health: GOOD facade, concerns concentrated in source_processor

Thin ScriptManager facade over four focused components. Nearly all health concern is in
`source_processor.py` (the de-facto central command loop): diverged heredoc scanners, broad
excepts mislabeling control flow, a 4x-duplicated regex, and heavy lazy-import / shell reach-in.

| Title | Kind | Sev | Effort | Location |
|---|---|---|---|---|
| Heredoc detection duplicated/diverged with multiline_handler | duplication | High | Medium | source_processor.py:388-430,502-567; multiline_handler.py:240-320 |
| Broad except relabels control-flow as "unexpected error" | broad-exception | High | Small | source_processor.py:381-386,360-369 |
| Abstract `execute()` dead across all components | dead-code | Medium | Small | base.py:17-20 + 4 forwarders |
| `base.expansion_manager` unused | dead-code | Low | Small | base.py:15 |
| History regex duplicated 4x | duplication | Medium | Small | source_processor.py:114,345; multiline_handler.py:118; line_editor.py:263 |
| Reaches into subsystem internals via hasattr chains | coupling | Medium | Medium | source_processor.py:82-84,273-275,347,307 |
| source_processor.py oversized, mixed concerns | oversized-module | Medium | Medium | source_processor.py:1-568 |
| Inconsistent shell-state access style | clarity | Low | Small | source_processor.py:260 |
| Repeated lazy imports in hot paths | clarity | Low | Small | source_processor.py:78,113,133,… |

### 2.10 `psh/utils/` — Health: GOOD, one user-visible defect

Small healthy grab-bag with clean public surfaces. Main issue: ShellFormatter is incomplete and
emits broken "# Unknown node type" output for real AST nodes (user-visible via `declare -f`).

| Title | Kind | Sev | Effort | Location |
|---|---|---|---|---|
| ShellFormatter broken output for several node types | clarity | High | Medium | shell_formatter.py:227-236 |
| SignalRegistry diagnostic API dead in production | dead-code | Low | Small | signal_utils.py:270-307,435-446,471-478 |
| heredoc_detection ignores quoting/string context | clarity | Medium | Medium | heredoc_detection.py:4-59 |
| Broad/silent except in signal cleanup | broad-exception | Low | Small | signal_utils.py:136-142,84-91,125-134 |
| ast_debug silently downgrades on format failure | broad-exception | Low | Small | ast_debug.py:74-80 |
| ShellFormatter drops array_assignments / heuristic re-quote | clarity | Low | Medium | shell_formatter.py:73-104 |

### 2.11 `psh/visitor/` — Health: REASONABLE, internal analysis-visitor duplication

Clean generic ASTVisitor base; healthy coupling to the rest of psh. Main problems are internal:
overlapping check logic across enhanced-validator/linter/security, three divergent traversal
idioms, dead toggles/stubs, and small correctness bugs.

| Title | Kind | Sev | Effort | Location |
|---|---|---|---|---|
| Three divergent `generic_visit` traversal strategies | duplication | Medium | Medium | base.py:47-62; metrics_visitor.py:563-573; security_visitor.py:320-332; linter_visitor.py:394-406 |
| Overlapping checks duplicated across 3 visitors | duplication | Medium | Large | enhanced_validator_visitor.py:403-477,618-659; linter_visitor.py:348-392; security_visitor.py:68-152 |
| Dead context toggles disable arithmetic suppression | dead-code | Medium | Small | enhanced_validator_visitor.py:172-173,413-414,573-574 |
| `_is_piped_to_shell` permanent stub (curl\|sh dead) | dead-code | Low | Small | security_visitor.py:141-147,272-276 |
| `SecurityIssue.node` never read | dead-code | Low | Small | security_visitor.py:30-40,278-318 |
| Operator-precedence bug in `_check_set_command` | other | Low | Small | linter_visitor.py:329-336 |
| `__all__` omits exported public names | clarity | Low | Small | __init__.py:10-27 |
| `Dict[str, any]` typo | clarity | Low | Small | security_visitor.py:278 |
| Inconsistent Issue models across visitors | clarity | Low | Medium | validator_visitor.py:42-56; linter_visitor.py:17-41; security_visitor.py:30-41 |
| Per-call `import re`/`dataclasses` | clarity | Low | Small | metrics_visitor.py:455,468; linter_visitor.py:244,310,396 |

---

## 3. Prioritized Triage (Top ~20 Findings)

Severity x Effort. Items also flagged in the 2026-02-17 review are cross-referenced in Section 4.

Status legend: ✅ resolved (version) · ⬜ open.

| # | Status | Finding | Subsystem | Kind | Sev | Effort |
|---|---|---|---|---|---|---|
| 1 | ✅ v0.208.0 | Test-only pipeline path embedded in production | executor | coupling | High | Medium |
| 2 | ✅ v0.207.0 | Bare `print()` bypasses `shell.stdout` | builtins | clarity | High | Medium |
| 3 | ✅ safety-pass | Recognizer registry swallows recognizer defects | lexer | broad-exception | High | Small |
| 4 | ✅ v0.214.0 | Redundant `except` defaults array index to 0 | expansion | broad-exception | High | Small |
| 5 | ✅ safety-pass | Broad except relabels control-flow as "unexpected error" | scripting | broad-exception | High | Small |
| 6 | ✅ v0.209.0 | ShellFormatter broken output for real node types | utils | clarity | High | Medium |
| 7 | ✅ v0.211.0 | Readline completion fully vestigial | interactive | dead-code | High | Medium |
| 8 | ✅ v0.197.0 | Parser-side validation dormant | parser | dead-code | High | Medium |
| 9 | ✅ v0.196.0 | Two parallel expansion engines duplicate param logic | expansion | duplication | High | Large |
| 10 | ✅ v0.198.0 | Array/quote disambiguation duplicated 3x | lexer | duplication | High | Large |
| 11 | ✅ v0.202.0 | Heredoc detection duplicated/diverged | scripting | duplication | High | Medium |
| 12 | ✅ v0.198.0 | Redirect-type dispatch duplicated 4x | io_redirect | duplication | High | Large |
| 13 | ✅ v0.215.0 | Broad `except Exception` in executor hot paths | executor | broad-exception | Medium | Medium |
| 14 | ✅ v0.223.0 | `_in_forked_child` private leak via hasattr/getattr | core | private-api-leak | Medium | Medium |
| 15 | ✅ v0.224.0 | Executor reaches into ExpansionManager privates | expansion/executor | private-api-leak | Medium | Small |
| 16 | ✅ v0.213.0 | OptionHandler largely dead; executor reimplements policy | core | dead-code | Medium | Small |
| 17 | ✅ v0.212.0 | ExecutionContext dead factories/fields (~half the module) | executor | dead-code | Medium | Small |
| 18 | ✅ v0.225.0 | `setup_builtin_redirections` oversized + fragile `>&` special-case | io_redirect | oversized/clarity | Medium | Medium |
| 19 | ✅ v0.205.0 | Three divergent visitor `generic_visit` + overlapping checks | visitor | duplication | Medium | Medium–Large |
| 20 | ✅ v0.226.0 | Combinator parser reaches into RD WordBuilder privates | parser | private-api-leak | Medium | Small |
| 21 | ✅ v0.227.0 | Builtins call siblings' private methods | builtins | private-api-leak | Medium | Small |

**Resolved: 21 of 21** — the entire prioritized triage table is now closed. The
final five (private-API-leak items #14/#15/#20/#21 and the oversized
`setup_builtin_redirections` #18) landed in v0.223.0–v0.227.0. Original
`Location`/`Carry-over` columns are preserved per-finding in Sections 1–2 (their
line numbers predate the v0.216.0–v0.227.0 work and may be slightly off).

---

## 4. Cross-Reference: Open Items from the 2026-02-17 Review

The 2026-02-17 review flagged five specific items. Their status against this Phase 2 audit:

| 2026-02-17 item | Status | Where it appears in this audit | Overlap vs new |
|---|---|---|---|
| `source_text` plumbing bug — `parser/__init__.py:88` | NOT re-observed in Phase 2 audit data | Not surfaced by any subsystem auditor. Likely still open; not independently re-verified here. | Carry-over (unconfirmed) |
| IOManager private FileRedirector calls | OVERLAPS / SUPERSEDED | The io_redirect audit found the package boundary is now clean (no external private reaches), but the *internal* coupling persists as the 4x redirect-dispatch duplication (Triage #12, `manager.py:57-154` etc.) and the builtin path reimplementing FileRedirector logic. | Carry-over, reframed |
| Broad `except Exception` at `executor/command.py:183` | STILL OPEN — confirmed | Triage #13; theme 1.2. Same line range (`command.py:183-206`). | Carry-over, confirmed |
| Broad `except Exception` at `scripting/source_processor.py:381` | STILL OPEN — confirmed | Triage #5; theme 1.2. Same line (`source_processor.py:381-386`), now with added detail that it also swallows re-raised control-flow exceptions. | Carry-over, confirmed |
| Oversized `line_editor.py` (1302L) | NOT re-audited as a standalone subsystem | `line_editor.py` was referenced by the interactive and scripting audits (it is the authoritative input/completion path, `line_editor.py:1034,263,21,136-214`) but was not given its own oversized-module finding in Phase 2. Still presumed open. | Carry-over (not re-scoped) |

New findings dominate this audit: of the ~75 findings synthesized, only the two `except Exception`
sites (executor/command.py:183, scripting/source_processor.py:381) are direct confirmations of
prior open items; the IOManager item is reframed as internal duplication rather than a boundary
leak. The `source_text` plumbing bug and the `line_editor.py` size were outside the explicit
subsystem scopes audited here and should be re-verified directly.

---

## 5. Recommended Sequencing

1. **Quick high-value safety fixes (High sev / Small effort):** lexer registry broad except
   (#3), expansion redundant excepts (#4), scripting control-flow mislabel (#5). These restore
   transparent failures with minimal risk.
2. **User-visible correctness:** ShellFormatter node coverage (#6), builtin `print()` routing
   (#2).
3. **Remove dormant machinery (clarity wins, low risk):** parser validation subsystem (#8),
   readline path (#7), ExecutionContext dead code (#17), OptionHandler dead methods (#16).
4. **De-duplicate divergent reimplementations (highest clarity payoff, larger effort):** dual
   expansion engines (#9), lexer array/quote scanners (#10), heredoc detection (#11), redirect
   dispatch (#12), visitor analysis logic (#19).
5. **Tighten public APIs:** promote the leaked `_underscore` operations and add narrow
   accessors (#14, #15, #20, #21) — best done alongside the de-duplication work in step 4.
