# Reappraisal #19 Campaign Briefs — dev notes for the HIGH/MED clusters

**Date:** 2026-07-11
**Source appraisal:** `ground_up_reappraisal_19_textbook_2026-07-10.md` (v0.687.0 @ `8a622ff8`)
**Roles:** design decisions in this document are fixed (integrator-owned); implementation is
delegated to dev agents; the integrator performs final review, gating ceremony, and release.
**Priority directive (2026-07-11):** *duplicate and dead code removal leads the campaign.* The
phases below are ordered accordingly: **Phase D** (dead-surface deletion) → **Phase T** (twin
convergence, including the HIGHs that are duplication-shaped) → **Phase B** (remaining behavioral
HIGHs) → **Phase P** (docs/meta/polish).

---

## 0. Currency: the appraisal SHA is three releases stale

All `file:line` references in the appraisal and in this document were measured at `8a622ff8`
(v0.687.0). Since then v0.688.0 (locale Stage 4), v0.689.0 (ECHILD reap race, `wait -n`), and
v0.690.0 (**systemic runtime-error location prefix**) have shipped. Files known to have drifted
(from `git diff --stat 8a622ff8..HEAD`):

- `builtins/base.py` (+42: **new `error`/`report_error`/`usage` channel trio** — see T3),
  `builtins/core.py`, `environment.py`, `function_support.py`, `positional.py`,
  `signal_handling.py`, `navigation.py`, `job_control.py`
- `core/state.py` (+99), `core/scope.py` (+16), `core/trap_manager.py` (+6),
  `core/locale_service.py`, `core/internal_errors.py`
- `executor/job_control.py` (+71), `executor/strategies.py` (+34), `executor/command.py`,
  `executor/command_assignments.py`, `executor/array.py`
- `expansion/operators.py`, `expansion/variable.py`, `expansion/command_sub.py`,
  `expansion/arithmetic/evaluator.py`, `expansion/word_expander.py`
- `scripting/source_processor.py`

**Mandatory Step 0 for every brief:** re-locate every cited symbol at current HEAD (grep the symbol
name, not the line number) and **re-verify the finding still holds** — re-run the appraisal's probe
where one exists. If v0.688–0.690 already fixed or moved it, report in the dev ledger and skip; do
not "fix" code that no longer has the defect. The v0.690 prefix sweep is the most likely collision:
any finding about *error message shape* must be re-probed against current output.

## 1. Standing rules for dev agents (non-negotiable)

1. **Scope & ceremony.** Work on a `fix/<topic>` branch. Devs NEVER touch `psh/version.py`,
   `CHANGELOG.md`, `README.md`/`ARCHITECTURE.md` version stamps, never `gh pr merge`, never tag.
   When your gate is green, **release the gate slot** and hand the branch to the integrator.
   One gate machine-wide; the integrator sequences slots. Foreground the gate run (a backgrounded
   `&` launch inherits SIG_IGN and produces ~29 spurious signal-test failures). Gate from a neutral
   detached worktree **and create `tmp/` in it first** (a fresh worktree without `tmp/` silently
   skips writing results).
2. **Evidence.** "Verified" means an archived transcript: probe scripts + outputs committed to the
   branch under `tmp/probes-<topic>/` (or pasted into the dev ledger) **with the SHA they ran at**.
   Differentials and probe batteries must be re-run at the final SHA before slot release — stale
   evidence is an honest false claim and has burned this project twice.
3. **Bash-verification workflow.** Any change that can alter observable behavior gets a
   *pre-registered* probe battery (written BEFORE the fix, cases enumerated in the ledger) comparing
   `bash -c` vs `python -m psh -c` on stdout, stderr, and exit code. Fix until probes match; promote
   keeper probes to `tests/behavioral/golden_cases.yaml`. Pins that pin NEW behavior must be
   **demonstrated red-on-base** (run the new test against the pre-fix tree; record the failure).
   Pins must exercise BOTH branches of a symmetric fix. Never use `run_tests.py --compare-bash`
   in a dev loop (block-buffering stall); use `pytest tests/behavioral --compare-bash`.
4. **Pure refactors** (deduplication with no intended behavior change) get pin-first treatment:
   identify the tests that currently exercise both twin paths; if a path is untested, add a
   characterization test BEFORE converging. Token-stream/AST-shape refactors get a differential
   harness (old vs new over a corpus) with the corpus and SHAs recorded.
5. **Deletion policy (Phase D).** "Referenced only by its own unit tests" = dead: delete test and
   code together. Before deleting, grep `psh/ tests/ docs/` at CURRENT HEAD and walk the dynamic-
   dispatch checklist: `visit_<ClassName>` methods, builtin registry registration, `getattr`/
   `__getattr__` strings, `__init__.py` re-exports, entries in `__all__`, plugin/hook tables,
   `eval`/f-string construction of names. If ANY live production reference exists → do not delete;
   report in the ledger. Phase D permits **zero behavior change** — same bytes on stdout/stderr for
   the whole golden corpus.
6. **Quality bars at slot release:** full local gate green (`python run_tests.py --parallel`),
   `ruff check psh tests` clean, `mypy` clean, goldens green. Golden-file merges use
   `git merge-file --union` ONLY, verified by case count afterward.
7. **Riders.** If you find an adjacent defect, declare it in the ledger and get an integrator
   ruling before folding it in. Undeclared scope creep bounces the whole slot.
8. **Strict-errors.** The suite runs with `PSH_STRICT_ERRORS=1`. A test that deliberately drives an
   internal exception must disable strict-errors on its own shell only.

## 2. Review checklist (what the integrator will verify before merging)

- Ledger shows Step-0 currency check per finding; pre-registered battery predates the fix commits.
- Probe transcripts exist, carry SHAs, and were re-run at the final SHA.
- Red-on-base demonstrations for every new behavior pin.
- Phase-D slots: `git diff` contains only deletions/doc-repointing; golden corpus byte-identical.
- No `version.py`/`CHANGELOG`/stat-file touches; no golden merges except blob-union.
- Grep-audit: for every "converge on X" brief, the retired twin has zero remaining callers and the
  claim-bearing docstring was updated to be TRUE (a docstring claiming a chokepoint that isn't is
  the #1 clarity failure this appraisal found).
- New/updated CLAUDE.md text contains **no code sketches** — invariant prose + `file.py#symbol`
  pointers only (see P2).

---

# Phase D — Dead-surface deletion sweep (~90 items, 6 slots)

Mechanical, high-volume, zero-behavior-change. Each batch is one dev slot, one branch, one gate.
Inventories below are exhaustive per the appraisal; every item was grep-verified dead by an auditor
AND re-verified by an adversarial verifier at `8a622ff8` — but rule 5's re-grep at HEAD is still
mandatory (three releases have landed). Items marked **[fix-not-delete]** are excluded from D and
handled in the referenced brief.

## D1 — Lexer + RD parser

**Lexer** (`psh/lexer/`):
- `heredoc_lexer.py:32` `normalize_heredoc_delimiter` (dead twin of `_delimiter_from_source`);
  repoint the cross-reference in `utils/heredoc_detection.py:46` at the live symbol (or at the T4
  helper if T4 has landed first).
- `token_stream.py:62-161` `collect_until_balanced`, `collect_until`, `save_position`,
  `restore_position`, `remaining_tokens`; also delete the misleading "quote tracking" comments
  around the per-token `in_quotes` recomputation (:95-98). Keep `peek/advance/pos/`
  `collect_arithmetic_expression` — the module's real job.
- `position.py:98` `LexerError` + its dead 25-line `_format_error` renderer. **Decision: delete**
  (do not resurrect by routing `UnclosedQuoteError` through it). Prune from `__all__`
  (`lexer/__init__.py:152`) and fix the two production docstrings that cite it.
- `position.py:160-174` `create_interactive_config`/`create_batch_config` (both return `cls()`);
  update `tests/regression/test_lexer_deprecation.py`. Rewrite the `LexerConfig` docstring to its
  three real fields; fix the module docstring's phantom "recovery capabilities" (:5).
- `position.py:158` `case_sensitive` knob (never set False anywhere) + the dead lowercase branch in
  `unicode_support.py:102-103` + the flag threading in `expansion_parser.py:284-290`. Keep NFC
  normalization.
- `keyword_defs.py:69` `matches_any_keyword`; `keyword_defs.py:74` `KeywordGuard` (production-
  unused). **Decision: delete both** and rewrite `docs/keyword_helper_cookbook.md` (which currently
  recommends them) around the helpers production code actually uses.
- `keyword_normalizer.py:201-202` unreachable FI/DONE/ESAC branch + never-read
  `_current_command_position` parameter of `_next_command_position`.
- `heredoc_collector.py:156` dead accessor tail on HeredocCollector/HeredocLexer.
- `heredoc_lexer.py:323` module-level `tokenize_with_heredocs` shadow twin that skips `_post_lex`.
  **Verify-first:** the live entry is the package-level export; confirm which one
  `source_processor`/`command_accumulator` import. If the module-level one has zero production
  imports → delete; if it has any → this is T4/T6 territory, report instead.
- `quote_parser.py:87` never-read `position_tracker` parameter (drop at all three
  `modular_lexer.py` call sites :439/:482/:514) + fix the false "Line/col will be filled by
  tracker" comment at :205. Same pattern: `expansion_parser.py:407` `ExpansionContext.
  position_tracker` (never read).
- `recognizers/registry.py:10` unused logger + test-only container-protocol dunders.
- `modular_lexer.py:172` dead-defensive isinstance juggling / unreachable position-setter rebuild.
- `pure_helpers.py:596-650` `is_inside_expansion` + its only feeder `find_balanced_parentheses`
  (:134-152) + `tests/unit/lexer/test_pure_helpers.py` coverage of both. The live same-named
  function is `utils/heredoc_detection.py:185` — after deletion, a grep for the name must land only
  there. (Flagged independently by three scopes; has outlived two prior review flags.)
- Stale-docstring repairs riding along (text-only): `recognizers/operator_debris.py:29` and
  `modular_lexer.py:22/:244` "priority order" relics; `recognizers/comment.py:21` third relic.

**RD parser** (`psh/parser/`):
- `recursive_descent/helpers.py`: `ErrorSeverity` enum, `ErrorContext.severity` (:155),
  write-only `context_tokens` (:156) + its assignment at `context.py:299`, unused
  `CONTROL_KEYWORDS` group (:111), never-populated `ErrorContext.expected` + the dead first branch
  of `summary()` (:169-175), and the unused `expected` kwarg in `combinators/diagnostics.py:9`.
  Keep `context_before/after` (read by `format_error` and tests). Also delete the no-invariant
  historical migration comments (:137).
- `recursive_descent/parsers/arrays.py:182` `_candidate_split_element` (unreachable from the live
  lexer AND misparses when hand-fed) + write-only `inline_tail` field (:98) + the stale comment at
  :201; update the module docstring's "live token shapes" list.
- `recursive_descent/support/word_builder.py:173` dead `isinstance(VariableExpansion)` branch +
  false comment (point it at `_variable_name_to_expansion` :189-199 instead).
- `recursive_descent/parsers/arithmetic.py:53` vestigial `terminator` parameter + lying Optional
  return annotation. Same-file LOW: `statements.py:20` `Optional[Statement]` that never returns
  None; fix annotations.
- `recursive_descent/parser.py:59` write-only `self.config` alias + the `ctx=` parameter that
  silently discards six arguments.
- `recursive_descent/parsers/functions.py:53` vestigial multi-token function-name plumbing with the
  self-contradicting docstring. (**Coordinate with B3**, which rewrites this file's dispatch —
  if B3 is scheduled in the same wave, fold this into B3 instead.)
- Import prunes: `psh/parser/__init__.py:10` (three unused names),
  `recursive_descent/__init__.py:7` (`ContextBaseParser`, `TokenGroups`),
  `recursive_descent/support/__init__.py:6` (phantom `context_snapshots.py` doc; add
  `nested_parse.py`).

**Gate note:** D1 touches lexer/parser only; the differential-corpus tests and full gate are the
safety net. Zero golden changes expected.

## D2 — Combinator parser + visualization

- `combinators/tokens.py:45-46, 162-171, 220-221` **ghost token parsers**: `AND_IF`, `OR_IF`,
  `EQUALS`, `GLOB`, `ASSIGNMENT`, `HEREDOC_DELIMITER` — names absent from `TokenType`, can never
  match. Where a ghost is *wired* into an `or_else` chain (the and-or grammar), delete the dead arm
  and leave the live arms; run the combinator differential corpus (`tests/parser_differential/`)
  before/after to prove no acceptance change. Then add the H17 guard: `token(name)` validates
  `name in TokenType.__members__` at construction and raises — this converts future ghosts into
  import-time failures. Also delete the three `WHITESPACE` checks (`combinators/parser.py:149`) —
  a seventh ghost name.
- `combinators/control_structures/__init__.py:86-111` 14 dead keyword parsers +
  `statement_terminator` + `do_separator`/`then_separator`, and their twin dead implementations in
  `tokens.py:192-200`, plus the `_parse_do_separator`/`_parse_then_separator` helper pair
  (:167-189) that exists only to feed them.
- `combinators/tokens.py:204-252` static factories, `:254-309` test-only predicates
  (`is_terminator`/`is_keyword`/`is_expansion`), `:323-383` module-level convenience functions.
  Point `tests/unit/parser/combinators/test_tokens.py` at the instance attributes or delete the
  now-redundant tests.
- `combinators/expansions.py:62-80` duplicate `format_token_value` (live one is in `utils`),
  `:144-193` `create_expansion_parser`/`create_word_parser` (zero callers), `:195-209`
  `is_expansion_token`; re-source the `or_else` expansion chain (:41-60) from one place.
- `combinators/parser.py:299-312` `configure()` (guaranteed no-op that rebuilds the grammar twice)
  — delete. `parse_partial`/`can_parse` (:241-297): **keep, but docstring-mark as test-facing**
  (they have test users).
- `combinators/core.py` **shelfware algebra — decision: DELETE** `between`, `literal`, `lazy`,
  `try_parse`, `separated_by`, `with_error_context`, `ForwardParser`, and `sequence`/`skip`/`.map`
  if their only remaining feeders were the dead separators. The live algebra is
  `token/keyword/many/many1/optional/fail_with/or_else`. Rewrite
  `docs/guides/combinator_parser_guide.md` to describe the actual closure style — it currently
  claims pipelines use `separated_by()` (they never have; `pipelines.py:104-143` is a manual loop).
  This is H18; the guide fix is part of this slot, not P-phase.
- `combinators/commands/__init__.py:15` ~15 unused imports (hidden by the blanket `__init__` F401
  ignore — remove them anyway).
- Visualization: `dot_generator.py:32` write-only `node_ids`; `ascii_tree.py:231` `skip_fields`
  guards for `arg_types`/`quote_types` (removed from the AST in v0.120);
  `sexp_renderer.py:294/:307` `render_ast_sexp`/`render_compact_sexp` (zero callers);
  `visualization/__init__.py:7` export-surface prune. **[fix-not-delete]** the `show_positions`
  no-op, static `render()`, and DOT field drift → B4.
- `combinators/special_commands.py:73` private `ExpansionParsers` instead of the shared wired
  instance — one-line rewire, rides here.

## D3 — Core + executor + expansion + arithmetic

**Core:**
- `option_registry.py:222-241` five dead typed accessors (`errexit`…`interactive`) + the FALSE
  "hottest internal reads" comment. Also update
  `tests/unit/core/test_option_registry.py:236/:239`, whose only reads of these accessors are
  self-referential.
- `scope.py:925` `has_variable` (dead and semantically hazardous); `scope.py:21`
  `VariableScope.parent` (vestigial, misleads about resolution — delete field + fix docstring).
- `state.py:948` vestigial `name = opt` alias from the removed hashcmds table.
- `functions.py:72` vacuous readonly-preserve in `define_function`.
- Text-only riders: the five stale `adopt()` docstring references (`command_hash.py:13`,
  `history_state.py:29`, `execution_state.py:8`, `trap_manager.py:233/:282`, comments in
  `state.py`) → rename to `clone_for_child`. (Mechanical; P2 covers the CLAUDE.md half.)

**Executor:**
- `pipeline.py:48-52` `PipelineContext.job_manager` constructor param (no method reads it; fix
  `tests/unit/executor/test_pipeline_rolling_fds.py:27`) + write-only `self.job` attribute
  (assigned :321/:329, never read).
- `executor/__init__.py:23` ~10 imported names neither exported nor consumed.
- `job_control.py:160` `Process.stopped`/`.completed` back-compat properties — one test-only
  consumer; delete both + fix the test. (**Drift warning:** job_control.py changed in v0.689 —
  re-locate.)
- `command.py:999` `_handle_exec_builtin`'s verbatim-duplicated OSError block — fold to one.

**Expansion:**
- `brace_expansion.py:636` `_contains_expandable_dollar` (dead method).
- `extglob.py:229` `match_extglob` + its package export (production-dead).
- `fields.py:57` dead `is not None` check; `tilde.py:84` `pwd` module-shadowing local rename.
- Stale docstring rider: `arrays.py:89` "_expand_array_subscript can return None" (it can't).

**Arithmetic:**
- `arithmetic/__init__.py:69` backward-compat re-exports with zero external users; while there, fix
  the drifted public node export list (:25 — array inc/dec nodes missing).
- `evaluator.py:192` redundant local import of `ShellArithmeticError`; hoist the nine function-local
  imports (:70) to module scope (no cycles force them — verify with a quick import check).
- `evaluator.py:93` the `"'_' * 2"` mystery exclusion: **probe first** (`__x=5; echo $((__x))` and
  friends vs bash); behavior converges via the fallback per the auditor, so **delete the exclusion**
  if probes confirm equivalence; otherwise write the real reason as a comment. Record probes.

## D4 — Builtins + io_redirect + interactive + scripting

**Builtins:**
- `declaration_engine.py:52-54, 79-80` `PrintMode` + `DeclarationRequest.array_kind`/`print_mode`
  (never constructed); `function_support.py:289` `_original_args` parameter + stale comment at :76.
- `registry.py:64` dead dunders with misleading dict-like contract.
- `shell_options.py:29` `SHOPT_OPTIONS` vestigial identity dict.
- `navigation.py:82` dead tilde branch behind always-false `hasattr(shell, '_expand_tilde')`.
- `disown.py:111-113` phantom `job.no_hup` write. **Decision:** delete the write; keep accepting
  `-h` for compatibility; rewrite its help text to say "accepted for compatibility; psh does not
  send SIGHUP on exit" and add a line to `docs/missing_features.md` (huponexit is out of scope).
- `io.py:103` leftover debug scaffolding in echo's write path; `io.py:15` double alias layer for
  echo escape processing; `print_builtin.py:230` no-op trailing `continue`s.
- `base.py:217`-area no-op `if consumed_value: continue` in `parse_flags` — **re-verify at HEAD**
  (v0.690 edited this function); delete only if still a no-op.
- Mock-defensive guards in production code (`navigation.py:28-30/125-126/164-165`,
  `directory_stack.py:318/476`, `print_builtin.py:104-106`, `signal_handling.py:81-84`): delete the
  guards; where a unit test then fails, fix the test to use a real shell fixture (per project
  guidance). This is deletion-adjacent and included here; if any guard turns out load-bearing for a
  real (non-mock) path, report instead.

**io_redirect:**
- `fd_remap.py:81` `protected` parameter (no production caller); `file_redirect.py:475` dead
  `check_noclobber` parameter chain; `file_redirect.py:158` dead `redirect=None` default.
- Text-only riders: `process_sub.py:18` 3-tuple/4-tuple docstring; `file_redirect.py:77`
  `dup_fd_valid` cross-module claim; `ast_nodes/redirects.py:35` here-string comment.

**Interactive:**
- `history_expansion.py:638-646` `is_history_expansion_char`, `get_history_list`,
  `get_history_item`; `tab_completion.py:73` `_find_word_start` compat alias;
  `history_manager.py:209` `get_history()`; `repl_loop.py:24` dead `prompt_manager` wiring;
  `history_manager.py:324` `delete_entry`'s discarded `removed` + lint-silencer.
- `prompt_manager.py` `set_prompt` — **defer to T14** (which wires the getters); do not delete here.

**Scripting:**
- `input_sources.py:93` `FileInput.loaded` + twin lockstep counters; `:182` display-label sentinel
  keying read granularity (replace with an explicit boolean attribute — tiny, behavior-neutral).
- `command_accumulator.py:298` `_need_more` wrapper — verifier ADJUSTED this; re-read the addendum
  in `tmp/appraisal-r19-reports/scripting-entry.md` before deleting.
- `base.py:9` `ScriptComponent` ABC (zero abstract methods): drop the ABC base. **Facade decision:**
  widen `ScriptManager` to the real API (`execute_as_main`, `validate_script_file`) and route the 7
  bypassing call sites through it (`script_executor.py:18/:52`, `visitor_modes.py:115`,
  `__main__.py:438/:505`, `source_command.py:69/:99`) so the facade earns its keep. If that proves
  invasive mid-slot, the fallback ruling is: delete the facade instead — but ask first.

## D5 — Visitor + ast_nodes + utils

**Visitor (write-only state + dead promises):**
- `validator_visitor.py`: `in_loop` (±'d at 10 sites, never read), `in_function`, `variable_names`;
  fix the docstring promising a break/continue-outside-loop check that cannot work (D2-era parse
  makes them SimpleCommands). **Decision: delete the fields and the docstring claim** — implementing
  the check is T10's call if it wants it.
- `security_visitor.py:58-59` `in_function`/`function_stack`; `linter_visitor.py:119-121`
  `_in_function`/`_in_subshell`; `metrics_visitor.py:151` `in_command_substitution` +
  `CodeMetrics.total_lines`/`total_variables`/`total_arrays` (to_dict computes from sets).
- `enhanced_validator_visitor.py:191` no-op overrides + dead parameter.
- `security_visitor.py:29` `SecurityIssue` hand-rolled → dataclass (consistency rider);
  in-method imports for shared helpers (:283) hoisted.
- `psh/visitor/__init__.py:23` `__all__` omits `ValidatorVisitor` — fix the export surface.

**ast_nodes:**
- `arrays.py:59-92` three dead derived properties (`element_quote_types`, `value_type`,
  `value_quote_type`) whose docstrings name consumers that no longer exist; keep `element_types`
  (live at `validator_visitor.py:453`). Update the stale table in
  `tests/unit/visitor/test_legacy_field_isolation.py:20-23` — the isolation lock *forbids* readers,
  it doesn't require these properties to exist.
- `commands.py:98` `StatementList.and_or_lists` (production-dead, one test) — delete + test.
- `words.py:171` `_expansion_literal_text`'s self-described unreachable broken branch;
  `words.py:396` `if False:` import guard → `TYPE_CHECKING` (flagged by two scopes);
  `__init__.py:28` vestigial typing re-exports; `__init__.py:166` two underscore-named helpers
  pinned in `__all__`.

**utils:**
- `signal_utils.py:303` `SIGNAL_NAMES` 9-entry hand map — **this one is a behavior fix** (SIGUSR1
  renders as `Signal-30`): replace the four `.get(sig, f'Signal-{sig}')` sites (:354/:436/:455/:513)
  with `signal_number_to_name(...)`; pin with a `signals`-builtin output test. Included in D5
  because the diff is deletion-shaped; pre-register the tiny probe (bash `trap -l`-adjacent
  rendering is psh-specific here, so pin psh's own output, red-on-base).
- `signal_utils.py:425+` registry report/validate apparatus: trim to what the `signals` builtin
  (`debug_control.py:283`) consumes — current-handler table (+ optional history). Delete
  `get_all_handlers`/`get_history`/`enable`/`disable`/`clear` (used only by the registry's own unit
  tests) and `validate()`'s pathologizing heuristics, with their tests.
- `ast_debug.py:69` duplicate default arm + silent unknown-format acceptance (raise instead —
  verify no caller depends on the silence).
- `token_formatter.py` **[fix-not-delete]** → P4 (import-hygiene move to lexer).

## D6 — Test infrastructure + repo root

- Root `conftest.py`: delete the shadowed `shell` fixture (:80-119, wait-based teardown — the
  retired policy), `_reap_children` twin (:67), `except (OSError, Exception)` (:99), and the
  `visitor_xfail` hook machinery (:10-64, zero marker users). Keep `pytest_configure`'s env pins
  (PYTHONPATH, PSH_STRICT_ERRORS, LC_ALL) — they are load-bearing.
- `tests/conftest.py:240-269` `MockStdout`/`MockStderr` (identical twins, zero users); `:365-397`
  `isolated_subprocess_env` (+ bare except); `--strict-isolation` and `--run-slow` options (never
  read); `pytest_configure_node_id_parts` (:401, not a real hook); `flaky` and `isolated` markers
  (never applied / write-only) — and reconcile marker registration to ONE source of truth
  (pytest.ini vs conftest; pick pytest.ini).
- `tests/conformance/conformance_framework.py:402-475` `is_posix_required` +
  `get_posix_test_commands`; `:362-398` `save_results`/`get_results_summary`; `:278-284`
  `_is_bash_specific` + `assert_bash_specific` (keys on constructs psh fully supports; zero real
  callers).
- `tests/framework/pty_test_framework.py` — **decision: prune, don't port.** Delete the dead
  members (`validate_line_editing_sequence` :381, cursor/screen helpers :321-348, vestigial
  `initial=` param :207, five bare excepts). Porting the default-skipped legacy tests onto the
  smoke-suite harness is explicitly NOT in scope (separate task if ever).
- `run_tests.py` subshell `-s` Phase 2 (:613-623) + `--subshells-only`/`--no-subshells` flags + the
  lying "need capture disabled" docstring claim (:5-6): fold subshell tests into Phase 1.
  **Verification requirement:** run the full parallel gate twice (before/after) and diff pass
  counts; also run `tests/integration/subshells/` standalone under xdist to prove the premise
  really is obsolete on this machine.
- Repo root junk file `test_` (6 bytes, tracked) — `git rm`. `MANIFEST.in:3` two nonexistent file
  references — prune.
- Riders (text-only): `tests/README.md:61` framework/ description;
  `tests/TEST_FRAMEWORK_IMPROVEMENTS.md:136` bare `pytest -n auto` recommendation;
  stale compare-bash banner is T12's (computed at runtime), skip here.

---

# Phase T — Twin convergence (the duplication clusters)

Ordering within T follows risk-adjusted value: behavioral twins that have ALREADY drifted first.

## T1 — Core mutation authority (H7 + H8 + H9) — `psh/core/`

**Files:** `scope.py`, `variable_store.py`, `assignment_utils.py`, `trap_manager.py`, `state.py`.
All five drifted in v0.688–0.690 — Step 0 applies with force.

1. **H7 (behavior, do first):** `create_local` readonly bypass. Guard BOTH redeclare paths
   (`scope.py:647-651` value path, `:653-661` attrs-only path — relocate at HEAD) with
   `existing_local.is_readonly` → raise `ReadonlyVariableError`. Pre-registered battery (bash
   5.2 oracle): `f(){ local -r x=1; local x=2; }`, `local x` (attrs-only redeclare on readonly),
   `local -r x=1; local -r x=2`, `declare x=2` inside the function, `local x+=y`, unset attempt,
   and the non-error control (`local -r x=1` then plain reads). Pin exact stderr (note v0.690:
   expect the location prefix — probe bash for its exact shape first: bash emits
   `bash: line N: local: x: readonly variable` in scripts), rc, and that the function CONTINUES
   (bash: local returns 1, execution proceeds). Also confirm the `readonly`-special-builtin posix
   exit matrix (v0.673) is not implicated (`local` is not a special builtin). Goldens + unit pins;
   red-on-base required. Then make `variable_store.py:3-9`'s "cannot be bypassed" claim true.
2. **H8:** ONE `+=` engine. **Design:** `VariableStore.append` becomes the sole computation+commit
   path. Extract nothing new: instead, `assignment_utils.resolve_append_assignment` is reduced to a
   thin adapter that calls `store.append` (or deleted outright if its three caller families —
   `executor/command_assignments.py` two sites, `builtins/shell_state.py:370` — can call the store
   directly with the same inputs; prefer deletion). The store docstring's ALL-appends claim then
   becomes true. Characterization-first: enumerate the append matrix as tests BEFORE converging —
   scalar `+=`, integer-attr `+=` (arithmetic), array element-0 append via scalar `+=` on an array
   variable, `-l/-u` case-fold interaction, nameref target, temp-env prefix `VAR+=x cmd`
   (v0.679 semantics — run the tempenv test battery), local-scope append. The verifier established
   the `copy()` vs `deepcopy` divergence is currently unobservable — the characterization matrix
   must include the case that WOULD distinguish them (nested container in a Variable value) so the
   converged engine's choice is pinned deliberately.
3. **H9:** one inherited-traps rule. **Design:** add
   `TrapManager.compute_inherited_traps(options) -> dict[str, str]` implementing the correct set —
   ERR exempt under `errtrace` AND DEBUG (and RETURN, if/when supported) exempt under `functrace` —
   and call it from BOTH `state.clone_for_child` (`state.py:497-506`) and
   `trap_manager.enter_subshell_trap_environment` (:288-296). Battery: DEBUG trap + `set -T` in
   `( )`, `{ ...; } &`, `$( )`, `<( )` children; ERR trap + `set -E` same four; each also WITHOUT
   the option (traps must NOT inherit). Both branches of the symmetric fix pinned (rule 3). Fix the
   docstring that falsely claims the sets already agree.

## T2 — Declaration family: `local` converges on `declare` (H5) — solo slot

**Files:** `builtins/shell_state.py`, `builtins/function_support.py`, `builtins/declaration_engine.py`.
This is the largest single brief; do not pair it with anything touching builtins.

**Design.** `declaration_engine.py` grows the shared pipeline (it already owns scalar commit):
- `ATTRIBUTE_FLAGS: dict[str, str]` — one flag→Variable-attribute table (lift declare's
  `_OPTION_ATTRIBUTES`, `function_support.py:247-257`); `-l`/`-u` mutual-cancellation handled here.
- `build_array_init(request) -> IndexedArray | AssociativeArray` — single home for
  `_build_indexed_array`/`_build_assoc_array` (currently verbatim at `shell_state.py:418-431` AND
  `function_support.py:612-626`). It must keep using the shared `parser/array_flat_text.py` keys —
  the v0.687 escape-key fix — do not fork that logic; run its tests.
- `copy_before_append(existing, ...)` — the C2/P1.2 copy-then-build `+=` logic (one home; both
  copies carry the same campaign comment today). Coordinate with T1.2: if T1's store-append
  convergence lands first, this helper may collapse into `VariableStore.append` — integrator will
  sequence T1 before T2 and rule on the seam.
- `local` (`LocalBuiltin.execute_in_context`, 158 lines) shrinks to: parse flags (see T3),
  `create_local` scope calls, then delegate everything else to the engine. `local -n` adopts
  declare's nameref target-shape validation — **behavior change**: pre-register a nameref battery
  (`local -n r=valid`, `=arr[0]`, `=1bad`, `=a b`, self-reference) against bash and pin messages/rc.
- Keep each builtin's teaching docstrings; the engine docstring drops its "Phase 4 deferred" note
  and documents the now-real consolidation scope.

**Probe/pin protocol.** Pre-register a declare/local matrix battery (attributes × init forms ×
append × scoping): `-i -l -u -a -A -r -x -n`, `+x` forms, `declare -a a=(...)` with escaped keys,
`local -a` inside functions, `local` shadowing with attribute changes, `declare -p` round-trips.
The existing declare/local suites are dense — run
`pytest tests/unit/builtins tests/integration -k "declare or local or readonly or typeset"` early
and often. Red-on-base only for the nameref validation change; the rest is characterization-pinned
refactor.

## T3 — Builtins option-parse + PWD + banner + PATH-walk twins (H6 + MEDs)

**T3a — `parse_flags` migration (H6).** v0.690 gave `base.py` the blessed error channels
(`error` → prefixed `name: -x: invalid option`; `usage` → unprefixed usage line; rc 2). **Design:**
extend `parse_flags` minimally — (a) a `value_flags` spec it already has, plus (b) an optional
per-builtin validator hook `check(ch, value) -> Optional[str]` for range/shape errors, (c) a
`special_usage=True` mode that raises `SpecialBuiltinUsageError` instead of printing (for
POSIX-special builtins per the v0.673 matrix), (d) an ordered-events variant
`parse_flags_ordered()` returning `[(flag, value), ...]` for builtins where option ORDER matters.
Migrate: `read` (`_parse_options` :432), `mapfile` (:74-121), `wait` (:294-311), `trap` (:93-117 —
mind the v0.684 "lp" cluster semantics and v0.690's F1 set-path fix; trap's ordered/positional
rules are why the ordered variant exists), `ulimit` (:71-97), `cd` (:36-48). Keep `print`/`kill`/
`dirs` hand-rolled WITH a one-line justification comment each (kill's `-SIGNAME`, printf's `--`,
dirs' `+N/-N` are genuinely non-getopt). **Message standardization battery (pre-registered):** for
each migrated builtin, probe bash for `-Z` (invalid), missing option-value, `--` handling, and pin
psh's shape = parse_flags' channelized form. Expect existing tests pinning the OLD divergent
messages — update them only after the bash probe confirms the new shape is closer to bash (record
the probe beside each test change). **Coordination flag:** memory shows queued wave tasks (#26/#27
from the errprefix wave) may touch builtin usage surfaces — integrator will sequence; check the
tracker before starting.

**T3b — PWD/OLDPWD + cwd-read + `_print_stack` + lazy-init twins.** Extract cd's readonly-aware
updater (the only copy with the fix, `navigation.py:155-171`) as
`builtins/navigation.py#update_pwd_vars(shell, new_logical, old_logical)`; `cd`, `pushd`, `popd`
call it; delete the verbatim twins (`directory_stack.py:308-319`, `:466-477`, which swallow
AttributeError/TypeError). One `_ensure_stack` (currently triplicated :156/:364/:520); one
`_print_stack` (:321/:479); route pushd's directory branch through its own `_chdir_or_error`.
Unify the cwd READ side: probe bash for whether `dirs`/`pushd` display tracks the logical `PWD`
variable (it does — `PWD=/tmp dirs` probe) and converge on the PWD variable with env fallback.
Battery: readonly PWD/OLDPWD then cd/pushd/popd (bash: cd succeeds, update silently fails —
re-probe exact behavior + v0.690 prefix), `cd -`, CDPATH, `pushd` into a failing dir, symlinked
logical paths. Riders: `dirs` double-validation LOW, fg/bg resume-ritual LOW if trivially adjacent.

**T3c — `type`/`command -V` banner.** One `render_candidate_banner(candidate) -> str` (suggest:
in `type_builtin.py`, imported by `command_builtin.py`) replacing the near-verbatim twins
(`type_builtin.py:100-113`, `command_builtin.py:105-120`). Update both modules' "cannot drift"
docstrings to mention the shared renderer. Characterization pins: alias/keyword/function/builtin/
hashed/path outputs for both builtins (bash-probe `type` and `command -V` — their wording differs
between the two builtins in bash! The renderer needs a `style` parameter if probes confirm).

**T3d — `source`'s third PATH walk.** Add `mode: int = os.X_OK` parameter to
`CommandResolver.search_path`; `source_command.py:_find_source_file` delegates with `mode=os.R_OK`.
Fix the empty-component divergence: probe bash `PATH=':/dir' source f` (empty component = cwd) and
pin. Comment at the resolver why source needs R_OK (the previously-undocumented blocker). Update
the builtins CLAUDE.md "every PATH scan uses search_path" sentence to be true again (P2 rider).

## T4 — Lexer/heredoc twin family (+ H2 behavior fix)

**Files:** `lexer/modular_lexer.py`, `lexer/heredoc_lexer.py`, `lexer/cmdsub_scanner.py`,
`utils/heredoc_detection.py`. High regression risk; the golden corpus + lexer differential corpus
are the net. One dev owns the whole family to avoid conflicts (D1 must land first or be same-dev).

1. **Delimiter-unquote rule (drifted twin — behavior).** One
   `unquote_heredoc_delimiter(raw: str) -> tuple[str, bool]` in `utils/heredoc_detection.py`
   beside `heredoc_terminator_matches`; adopters: `heredoc_lexer._delimiter_from_source` (:211),
   `cmdsub_scanner._read_heredoc_delimiter` (:124), `heredoc_detection.heredoc_delimiter_word`
   (:40). The verifier PROVED drift (bash sides against the lexer copy) — get the verifier's probe
   from `tmp/appraisal-r19-reports/lexer.md` addendum, extend it into the pre-registered battery:
   delimiters `EOF`, `'EOF'`, `"EOF"`, `E"O"F`, `E\OF`, `$EOF`, `EO F` (quoted space), backslash-
   only, mixed-quote; each × (expansion-suppression check, terminator-match check, inside-`$()`
   check). Pin as goldens; red-on-base for the drifted cases.
2. **H2 — quote-aware heredoc detection (behavior).** `contains_heredoc`'s naive quote-blind
   `((`/`))` index-pairing (`heredoc_detection.py:389-424`) AND the accurate path share the defect
   (verifier: `scan_line_heredoc_markers` fails the same demo). **Design:** compute `_quote_flags`
   once per line (also closes the runs-twice LOW at :297) and feed it into
   `_scan_arith_or_cmdsub` so quoted `((`/`(`/backtick can never open a region; reduce the
   `contains_heredoc` fast path to `'<<' in line`. Battery: the appraisal demo
   (`echo '((' ; cat <<EOF ... echo '))'`), heredoc after quoted `$((`, `<<` inside single/double
   quotes (must NOT open), `<<-`, two heredocs one line, heredoc inside `$( )` (the cmdsub path),
   quoted terminator lines. Every case three-way: bash / psh-before / psh-after.
3. **Quote-lexing triplication (pure refactor).** `_lex_quoted(prefix_len, rules_key, quote_type)`
   helper in `modular_lexer.py`; `_handle_quote`/`_handle_locale_string`/`_handle_ansi_c_quote`
   become two-line wrappers; delete the thrice-repeated dead `if not rules` guard. Token-stream
   differential over the corpus (old vs new lexer output byte-identical).
4. Rider (clarity MED, pure): split `KeywordNormalizer.normalize`'s heredoc-skip FSM into a helper
   pre-pass and group the one-shot flags into a small state object — ONLY if the token-differential
   corpus is already wired from item 3; otherwise defer to a later slot. CLAUDE.md fusion-stage
   diagram fix rides with P2.

## T5 — io_redirect chokepoint adoption + fd-behavior trio (H1 rides here)

**Files:** `io_redirect/manager.py`, `file_redirect.py`, `process_sub.py`, `planner.py`.

1. **H1 — procsub node-carry (behavior).** Extend `RedirectPlan` with
   `procsub_node: Optional[ProcessSubstitution] = None`, populated where `_word_is_process_sub`
   (`file_redirect.py:103`) is true; `resolve_procsub_resource` consumes the node and NEVER sniffs
   strings. The string-sniff branch (`process_sub.py:302`) and the legacy expansion fallback
   (:152-155) are deleted — a redirect whose Word is not a procsub is a filename, full stop.
   Battery (bash-pinned): `cat < '<(echo x)'` (ENOENT, rc 1 — mind v0.690 prefix shape),
   `cat < <(echo hi)`, `echo hi > >(cat)` (+wait for output), `x='<(echo hi)'; cat < $x`
   (bash: ambiguous redirect — probe), `x='$y'; y=secret; cat < <(echo $x)` (no double
   expansion), procsub under `--parser combinator`, nested `<(cat <(echo a))`. Red-on-base for the
   two live bugs.
2. **Error-shape chokepoint.** `setup_child_redirections`' three message shapes (`manager.py:869`,
   `:847/:853`) → all route through `format_redirect_error`. **v0.690 interplay:** re-probe FIRST —
   the prefix sweep may have altered these sites; the invariant to converge on is
   `format_redirect_error`'s documented one-shape (+ the location prefix where bash has one).
   Probe bash for child-redirect failures (`ls > /root/x` in a pipeline member) and pin.
3. **Open-flags table.** `REDIRECT_OPEN_FLAGS: dict[str, int]` (type → flags) consumed by both
   `apply_var_fd_redirect` (:331-343) and the `_redirect_*` family; noclobber goes through
   `check_noclobber` at all three raise sites (one message string). Battery: `set -C` × (`>`, `>|`,
   `>>`, `<>`, `{fd}>`) × (existing, dangling-symlink, device).
4. **fd-behavior trio (each probed + pinned):** `note_stdin` high-slot dup mirroring `_save_fd_high`
   (`exec 0<&-; read x < f` must read the file, not EBADF); `output_close_fd` accepting `<&-`
   spelling with direction-based default fd (`echo hi 1<&-` error-only — no leaked 'hi';
   `{ echo a; } 1<&-`; `2<&-`); builtin stdin double-open → `os.fdopen(os.dup(0), 'r',
   errors='surrogateescape')` (one file description; verifier notes it's latent today — pin the
   offset-sharing property with a `{ read a; read b; } < f` style test so it stays fixed).
   The one-offset dup+fdopen recipe then exists ONCE (also closes the twin-recipe LOW at :703).

## T6 — Scripting lex→parse convergence (H11) + error-rendering + strict-errors

**Files:** `scripting/command_accumulator.py`, `scripting/source_processor.py`,
`scripting/visitor_modes.py` (+ `__main__.py` touchpoints). `source_processor` drifted in v0.690.

1. **One pipeline helper.** New `psh/scripting/lex_parse.py` exposing
   `lex_and_parse(text, shell, *, source_name, base_line=1, expand_aliases, lexer_options=None)
   -> Program` — does exactly: contains_heredoc? `tokenize_with_heredocs` : `tokenize`; alias
   expansion per flag; dispatch to `shell.active_parser` (RD or combinator); returns AST or raises
   (ParseError/UnclosedQuoteError pass through untouched — callers interpret). Adopters:
   `_trial_parse` (keeps its NeedMore interpretation of the raised errors), `_parse_command`,
   `_parse_for_analysis`. **Behavior deltas to pre-register:** `--parser combinator --validate`
   now actually uses the combinator (probe before/after; pin), and analysis modes now receive
   `lexer_options` (probe a case that differs, e.g. one requiring the options the execution path
   passes). 
2. **Syntax-error rendering.** One `_location(input_source, start_line) -> str` helper; route the
   UnclosedQuoteError clause (:364-365) through `_report_syntax_error`; merge or explicitly
   differentiate `visitor_modes.py`'s second renderer. Re-probe ALL shapes at HEAD first (v0.690
   touched this file); bash-pin the script-file, `-c`, and stdin variants.
3. **Strict-errors in analysis modes.** Delete `visitor_modes.py:90`'s
   `except (ValueError, TypeError)` swallow; mirror the execution boundary: expected shell errors
   render normally, internal defects route through `report_internal_defect` (re-raise under
   strict). Add a unit test: a visitor that raises TypeError under `--lint` must FAIL LOUDLY with
   strict-errors on (red-on-base) and report as an internal defect with it off.
4. Riders: `__main__.py` `-c`-branch stale comment + redundant writes (:417-421 — appraisal-
   verified false); location-ternary dedup (:223/:364/:616-617/:626).

## T7 — Executor: child-exit taxonomy (H10) + subshell body + RHS walker

1. **H10.** `child_policy.map_child_exception(exc: BaseException) -> int` — one taxonomy:
   TopLevelAbort→its code; FunctionReturn→its code; LoopBreak/LoopContinue→its status;
   `SystemExit(None)`→**0** (Python semantics; the launcher's 1 is the wrong copy);
   `SystemExit(n)`→n; KeyboardInterrupt stays a launcher-local arm (130). Five adopters:
   `process_launcher.py:280-314`, `child_policy.py:185-193`, `:326-345`, `subshell.py:167-173`,
   `pipeline.py:252-265` (delete the redundant catch if the launcher's suffices). Add a grep-based
   meta-test (`tests/unit/tooling/`) asserting the exception-tuple pattern appears only in
   `child_policy.py` — same shape as the existing write-ban guards. Direct unit tests on the
   helper; probe any observable `SystemExit(None)` path (builtin calling `sys.exit()` in a
   pipeline child) if one exists — else the unit pin suffices.
2. **Subshell child body.** Factor `child_policy.run_child_body(shell, node, *, in_substitution,
   drop_traps, loop_seed, ...)` shared by `run_child_shell` (:295-363) and
   `subshell.py execute_fn` (:121-190). The verifier's addendum lists MORE deltas than the
   auditor's three flags — read `tmp/appraisal-r19-reports/executor.md` addendum and parameterize
   exactly what it enumerates. Pure refactor: subshell/procsub/cmdsub test batteries + goldens.
3. **`enhanced_test_evaluator` RHS walker.** One per-part walker parameterized by escape fn
   (glob_escape vs re.escape) + tilde flag; one `_expand_dquote_literal` helper for the
   thrice-pasted recipe (:98-100/:230-233/:266-269). Characterization: `[[ x == pat ]]` and
   `[[ x =~ re ]]` quoting matrices already have dense tests — run them; add any missing
   dquote-part case BEFORE converging.
4. Riders: diagnostic-stream consistency (`state.stderr` at `core.py:577`, `:204`,
   `control_flow.py` select PS3/menu sites — probe `select` output routing under redirect vs bash
   first: bash writes PS3+menu to stderr); `strategies.py` dummy-SimpleCommand idiom ×4 → one
   helper; C-style-for arithmetic-error mapping ×3 → one local helper (coordinate with the
   arithmetic-chokepoint item in #17's ledger if it's still queued).

## T8 — Expansion twins + evaluator round-trips

1. **Substitution scan loops.** One scan loop parameterized by `match_at(pos) -> Optional[int]`
   replacing `_substitute_all_empty_aware`/`_substitute_all_matcher`/`_substitute_all_negation`
   (`parameter_expansion.py:246-336`). The clones already differ on zero-width stepping
   (`pos<n` vs `pos<=n`) — pre-register an empty-match battery against bash
   (`${x//?()/y}` extglob empties, `${x//\*/y}` on empty string, anchored empties `${x/#/pre}`,
   `${x/%/post}`) and pin WHICH semantics is correct before merging the loops.
2. **Subscript splitting.** `split_subscript(name) -> Optional[tuple[str, str]]` in
   `expansion/arrays.py`; adopt at the ~9 hand-rolled sites (`variable.py` ×4, `arrays.py` ×4,
   `operators.py` ×2 — re-grep at HEAD; param_parser's own two sites STAY, it's the parser).
   Pure refactor + existing array suites.
3. **`expand_array_to_list`.** Replace with a component-taking helper used by `fields.py:45/:60/:69`
   (delete the string re-construction + re-parse). Pure refactor.
4. **Evaluator round-trips.** Resolve operator-less `ParameterExpansion` directly from AST
   components (`evaluator.py:115` — kill `str(expansion)[2:-1]` → re-parse; same for the arithmetic
   wrap/unwrap LOW at :120). Then the CLAUDE.md "nothing is re-parsed" claim becomes true — verify
   and update the sentence either way.
5. **Behavior (verifier-added, probe first):** `get_variable`'s re-$-expansion of stored values
   (`arithmetic/evaluator.py:104`, `:129` — `expand=True` default). Bash: `y=5; x='$y'; echo $((x))`
   errors (`$y: syntax error: operand expected`); psh prints 5. **Decision: align with bash and the
   package's own never-rescan invariant** — pass `expand=False`, run a full arithmetic regression
   battery (name-chains `a=b b=c c=3; echo $((a))` must still work — that's ARITH-VALUE recursion,
   not $-expansion), pin goldens red-on-base. If the battery surfaces legitimate uses of the
   rescan, STOP and escalate to the integrator instead of shipping a divergence.
6. Riders: case-mod per-char reconversion (compile the predicate once per operator application;
   `lru_cache` on `_bracket_to_regex`) — efficiency, clarity-neutral; standalone-`$@` branch into
   the segment IR only if tests fully cover it (else defer).

## T9 — Arithmetic: tokenizer table + LValue reification

1. **Maximal-munch operator table.** Replace the 218-line elif ladder (`tokenizer.py:197-414`)
   with 3-char → 2-char → 1-char dict lookup; `++`/`--` keep the bespoke `_pair_is_incdec` path
   (its bash-pinned comment survives verbatim). **Differential harness required:** corpus of
   expressions (pull every arithmetic string from the test suite + goldens) → token streams
   byte-identical old vs new; archive the run.
2. **LValue.** New `LValue(name: str, subscript: Optional[ArithNode])` in `nodes.py`; ONE
   `AssignmentNode(lvalue, op, rhs)` and ONE `IncDecNode(lvalue, op, prefix: bool)` replace the six
   scalar/array twin classes; evaluator gains `_read_lvalue`/`_write_lvalue` (readonly enforcement
   — already present per the H1-of-#17 fix — moves to exactly one place); the three parser forks
   collapse. The arithmetic AST is engine-internal (verify: grep the six class names outside the
   package — expect only `__init__` exports and possibly debug tools). Full arith battery +
   goldens; the ordering-invariant comments (read-LHS-before-RHS) move onto the single methods.
3. Riders (from the verifier): fix the two falsifiable narratives — scope the RecursionError
   docstring (`parser.py:29-32`) to what the guard actually guards, and convert evaluator
   RecursionError at the `evaluate()` boundary into the standard "expression too deeply nested"
   ShellArithmeticError (clean error, documented divergence from bash's 25k-term tolerance;
   add to the deferred ledger rather than chasing iterative evaluation).

## T10 — Visitor analysis layer: twins + the seven advisories (H13/H14 + MEDs)

**Decision (the fork):** the analysis visitors STAY — they are teaching artifacts — but they get
the execution path's discipline: every advisory needs a positive AND a negative test, and a
false-positive ratchet corpus.

1. Fix the seven verified wrong advisories (each: red-on-base test → fix):
   - validator useless-cat twin: DELETE the copy (`validator_visitor.py:163` + `_in_pipeline`
     dead-default cleanup); linter owns the check (`linter_visitor.py:311`).
   - linter bare-assignment→undefined-function (`linter_visitor.py:211`): guard `used_functions`
     tracking with `_is_assignment` like line 244 does.
   - linter `set -eu` cluster miss (:407): detect `e` in a flag cluster; delete the no-op `-u` arm.
   - enhanced-validator quoted-`"$@"` false positive (:506): drop the advisory from the
     string-fallback path; the structural path (`_has_unquoted_at` :468) is the one implementation.
   - security ARITHMETIC_INJECTION noise (`security_visitor.py:221`): flag only embedded
     `$(`/backtick/`${...[...]}` shapes.
   - validator cd-arity flag counting (`validator_visitor.py:149`): count non-option operands.
   - metrics procsub always-0 (`metrics_visitor.py:479-481`): count ProcessSubstitution parts in
     `_analyze_word_features`; delete the dead `visit_ProcessSubstitution`.
2. Twin consolidation: one `is_assignment(arg)` built on the canonical `SHELL_NAME`
   (place in `visitor/constants.py` or `word_analysis.py`) used by all three visitors; ONE
   predefined-variables set in `constants.py` feeding both the linter suppression list and
   `VariableTracker.special_vars`; one unquoted-operand-in-test routine (in `word_analysis.py`,
   severity-parameterized) for linter + enhanced validator; `DANGEROUS_COMMANDS` consolidated (or
   the "union of all three" comment corrected — prefer consolidation with per-visitor severity).
3. **Harness:** new `tests/unit/visitor/test_analysis_advisories.py` — (a) a clean-corpus ratchet:
   N idiomatic scripts (reuse golden inputs) through `--validate/--lint/--security/--metrics`
   asserting ZERO advisories, (b) one positive case per advisory. This is the drift-lock that
   keeps the sidecar honest; wire it into the normal gate (it's plain pytest).
4. Rider: `security_visitor` noclobber-advisory LOW, `--validate` exit codes LOW if adjacent.

## T11 — ANSI-C encoder unification (cross-package)

Move `formatter_quoting.ansi_c_encode` (probe-verified authority: octal + `\E`) into
`utils/escapes.py` as THE `$'...'` encoder; `quote_at_q` (:188) and `quote_printf_q` (:148)
delegate. **Note for the dev:** escapes.py's famous "do NOT deduplicate" header covers the five
*decoder* dialects — the ENCODERS are a different family; add one sentence to the header making
that boundary explicit so the next reader doesn't misapply it. Battery (bash 5.2): `${v@Q}`,
`printf %q`, `declare -p`, `set` listing over a value matrix: `\x01`, `\x1b`, `\x7f`, high bytes
(`\xff` via surrogateescape), embedded `'`, newline, tab, plain ASCII. Bash renders ONE shape
across all four surfaces; psh currently renders three — red-on-base goldens for the divergent
cases. Formatter idempotence corpus must stay green.

## T12 — Test-infra twins

1. Shared AST "asserting test" analyzer: extract `tests/conformance/_assert_analysis.py` from
   `test_claims_have_tests.py:205-241`; both guards import it (delete the verbatim copy in
   `test_conformance_probes_assert.py:49` and its "mirrors so the two agree" apology).
2. Bash-oracle policy: `test_golden_behavior._run_bash` imports `find_bash()` from the conformance
   framework (BASH_PATH → Homebrew → PATH); record which oracle ran in the run header the way
   `run_conformance_tests.py` does. (26 golden cases need bash-4+; stock macOS `/bin/bash` 3.2
   currently breaks the gate on PATH-bash machines.)
3. Fixture convergence, ratchet-style: `shell_with_temp_dir` becomes a thin alias of
   `isolated_shell_with_temp_dir` ONLY if their semantic diff (reused vs fresh Shell, PWD-var vs
   os.environ) proves inert for current users — sample 20 users first; if inert, alias + ratchet
   meta-test capping non-isolated usage at current count; if not inert, document the real
   difference in both docstrings and ratchet anyway. Same ratchet pattern for capsys files
   (cap at current 81, direction down).
4. `tests/conformance/conftest.py` (3 lines: sys.path setup) + strip the 83 boilerplate headers
   (scripted edit; verify collection count unchanged before/after).
5. compare-bash banner: compute counts from `golden_cases.yaml` at runtime (kill the frozen
   "1,119" text — actual is 1,318/23 as of v0.690 and moving).
6. Riders: `pytest.ini` `addopts -v` removal — **verify `run_tests.py`'s parsers first** (it reads
   summary lines; `-v` affects per-test lines only, but prove it: run the full runner once without
   `-v` and diff the classify inputs); ~23 hand-rolled `sys.path.insert` headers outside
   conformance; `test_keyword_comparisons.py` is B5 (behavioral guard fix, not a twin).

## T13 — Interactive PS1/PS2 twin + prompt costs

One prompt-getter path: `MultiLineInputHandler._get_prompt` calls
`prompt_manager.get_primary_prompt()/get_continuation_prompt()`; the getters switch from
`state.variables` materialization to `state.get_variable` (kills the per-prompt full-dict build AND
the env-fallback divergence); delete `set_prompt` (zero callers) or wire it — **decision: delete**.
`title.py:27/:34` likewise moves to `get_variable('PWD', '')`. `PromptExpander._expand_escape`
becomes escape→thunk dispatch (evaluate only the selected expansion). `CompletionEngine.
get_completions` drops the vestigial `text` param and returns `(word_start, completions)`; the
three `find_word_start` recomputations per Tab collapse to one. Riders: `_get_key_action`
polymorphism LOW; two-`expand_prompt` naming LOW. Characterization: PTY smoke suite + prompt unit
tests; no bash oracle needed except PS1 escape outputs already pinned.

---

# Phase B — Remaining HIGHs (not duplication-shaped)

## B1 — Newline-unsafe glob-regex fast path (H3)

`extglob._convert_pattern` wraps its output in `(?s:...)`; every `'$'` end-anchor in
`parameter_expansion.py` (:163/:182/:377 — grep for more) becomes `\Z`. Sweep the file for OTHER
uncompiled/per-iteration regex in the suffix helpers while there (LOW confirmed at :163). Battery:
`case $'a\nb' in *)`/`a?b)`/`a*b)`, `[[ $'a\nb' == a?b ]]`, `${x%b}` on `$'ab\n'`, `${x//?/-}`,
`${x#pat}`, extglob `@(a|b)` with newline subjects — all three-way (bash/psh-before/psh-after),
red-on-base goldens. Then run the full golden corpus: the DOTALL change must not alter any
non-newline case.

## B2 — Token leak in ArrayElementAssignment (H4)

`ast_nodes/arrays.py:75`: `index: Union[str, List[Token]]` → `str`. Both parser emit sites
(`recursive_descent/parsers/arrays.py:301`, `combinators/arrays.py:239`) pass the subscript string
directly; `executor/array.py:253-264` deletes the unwrap loop + the stringly-typed dead
VARIABLE branch; grep for other consumers (formatter, parse-tree renderers, tests constructing the
node). mypy enforces the rest. Pure refactor: array assignment suites + goldens; add one AST-shape
unit test asserting `index` is `str` for both parsers.

## B3 — Function bodies through the compound chokepoint (H12)

`functions.parse_compound_command` routes through `_parse_compound_component` (unwrap to the AST
shape function bodies expect); delete `parse_control_structure` (its if/elif exists only for this
caller) and the hand-rolled brace parse (:134-146). Depth now accumulates in function bodies —
that is the point. Battery: `f() { ...; }`, `f() (...)`, `f() [[ ... ]]` (the v0.592 fix — must
survive), `f() if/for/while/case`, body redirects (`f() { ...; } > log`), deep-but-legal nesting
(64 levels parse fine), and a red-on-base pin that ~1,200 nested function bodies now raise the
standard MAX_NESTING_DEPTH ParseError (not RecursionError). Full parser suite + differential
corpus. D1's `functions.py` deletions fold in here if same wave.

## B4 — Visualization repairs (H15 + H16 + renderer dedup)

One shared `node_fields(node)` helper (the `__dataclass_fields__` walk `ast_formatter.py` already
models) used by ascii_tree, sexp_renderer, AND dot_generator (killing the ~80-line reflection twins
and H15's phantom-field reads in one move; per-node visit methods survive only for labels/colors).
`render()` becomes a `@classmethod` using `cls(**kwargs)` (H16) — pin
`CompactAsciiTreeRenderer.render != AsciiTreeRenderer.render` on a nested AST. `show_positions`
reads `node.line` (it's a no-op in three of four renderers today) or is removed — **decision: read
`node.line`**, matching ast_formatter. Fix the sexp `non-&& → '||'` silent mapping and the DOT
`visit_AndOrList` pipe-label LOW while in there. Tests: a renderer-output characterization corpus
(one nontrivial script → all four renderers, golden files) so future AST changes break loudly —
this is the drift-lock the package never had.

## B5 — Born-vacuous keyword guard (H21)

Single-escape the regexes in `tests/unit/tooling/test_keyword_comparisons.py`; delete the dead
`.py.archived` allowlist entry; add the standard self-test (synthetic offender source must be
flagged — the guard-the-guard idiom every sibling has). Expect the fixed guard to FIRE on real
offenders — triage each hit: fix the offender if it's a genuine raw keyword comparison, extend the
allowlist with justification if deliberate. Budget for a handful of real finds.

## B6 — `expand_history` decomposition (H22)

Rewrite as one forward scan tracking `in_squote/in_dquote/bracket_depth/brace_depth/arith_depth`
alongside the existing quote tracking; each `!` candidate consults current state — no backward
rescans, no `while/else`. Split scanner (finds candidates) from the existing `_resolve_*` resolvers.
**Byte-compatibility protocol:** before touching anything, build a characterization corpus — every
history-expansion test input in the suite plus the appraisal's nesting cases (`${!x}`-lookalikes,
`$((!x))`, `[!a]`, quoted `!`, `!!`/`!n`/`!?str?`/modifiers) — capture current outputs, then assert
identical after. Bash parity is already pinned by existing tests; this is a pure refactor with a
safety corpus.

---

# Phase P — Docs, meta, polish

## P1 — Contract-docstring truth sweep (H19)

Mode-aware persistence wording at all seven sites: `command_assignments.py:19` (point 3),
`command.py:91/:114/:376-378/:544-545/:725-727`, plus `executor/CLAUDE.md` (:24 designation,
:61-69 strategy order → bash-default order + `_resolve_command`'s POSIX reorder, :123-124 rule,
:344 `last_exit_status`→`last_exit_code`). Doc-only; verify each sentence against the code it
describes at HEAD (files drifted in v0.690).

## P2 — CLAUDE.md sync ×8 + the no-sketch rule

Rewrite the drifted sections per the appraisal's per-file lists (lexer fusion stage + two missing
module rows; parser CONTROL_KEYWORDS/error-collection/dispatch example + missing table rows;
core env-write snippets + options-dict + missing Key Files rows; builtins write() snippet (both
scopes found it) + category-table fixes + parse_flags mandate wording after T3; io_redirect backup
+ heredoc sketches + primary-path/var-fd documentation; interactive self-pipe laziness +
notification marker + jobspec API section (resolve_job_spec, %?str, typed results) + reaping
sketch WCONTINUED; executor covered by P1). **Rule going forward (add to root CLAUDE.md):**
subsystem CLAUDE.mds carry invariant prose and `file.py#symbol` pointers, never implementation
sketches — the appraisal showed every embedded sketch drifts into teaching fixed bugs. Where a
sketch is irreplaceable, add a drift-lock: a tooling test asserting the quoted lines appear
verbatim in the source file (small helper + registry in `tests/unit/tooling/test_doc_snippets.py`).

## P3 — ARCHITECTURE.md rewrite (H20)

Sections 2.6 (COMPOSITE tokens → current frozen-token/fusion story), 3.12 (derived
`SimpleCommand.args`), 4.4 (ProcessLauncher, not raw fork), 1.3 + pipeline diagram (brace expansion
at the Word stage, v0.678); delete or regenerate the "Current Architecture Capabilities" tail
(ParserConfig/error-recovery claims its own body contradicts; retired `LexerContext` name); sync
the test count from the README stats block. Integrator reviews this one line-by-line — it is the
front door.

## P4 — Import hygiene + layering lock

1. `builtins↔executor` cycle: move the shared job vocabulary (`JobState`, jobspec result types)
   to `psh/core/job_state.py`; `executor/job_control.py` and both builtins import from core.
   (v0.689 touched these files — re-map first.)
2. `core→utils→lexer→core` cycle: move `TokenFormatter` (18 lines, one caller) into `psh/lexer/`;
   `psh/utils` becomes psh-import-free (assert it).
3. Engine renames for the data-vs-behavior collisions: `expansion/command_sub.CommandSubstitution`
   → `CommandSubstitutionExecutor`; `expansion/parameter_expansion.ParameterExpansion` →
   `ParameterExpansionOps` (or similar — integrator will confirm names before the slot); AST node
   names keep the plain terms. Internal-only rename; fix all imports; no aliases left behind.
4. Lazy-import hoist: hotspot files first (`executor/strategies.py` ×20,
   `enhanced_test_evaluator.py` ×20, `expansion/operators.py` ×15, `executor/command.py` ×14);
   hoist everything a trial import proves cycle-free; the genuinely forced ones get a
   `# cycle-break: <path>` comment.
5. **The lock:** new `tests/unit/tooling/test_import_layering.py` — AST-builds the module-level
   import graph and asserts (a) zero package-level runtime cycles (allowlist starts empty after 1
   and 2), (b) `psh/utils` and `psh/core` leaf-ness rules, (c) optionally a cap on function-level
   intra-psh imports per file (ratchet at post-hoist counts). This converts the layering from
   folklore to a guard.

## P5 — Help/usage oracle (the T5-theme closer)

After T3's `parse_flags` migration, each migrated builtin's flag spec is declarative. New meta-test
`tests/unit/tooling/test_builtin_help_sync.py`: for every registered builtin exposing a spec,
assert (a) every spec'd flag letter appears in its `help`/synopsis text, (b) every `-x` the help
advertises is in the spec (allowlist for prose mentions). Fix the known drift NOW regardless of
spec coverage: unset (-v/-n), declare/local synopses (-n), read (-u), pwd/cd (-L/-P), wait
(-n/-p), exec (-a/-c/-l), shopt (list from SHOPT registry), trap `help_text`→`help` rename, the
two `-h`-prints-`__doc__` surfaces (`parse_tree.py:54`, `debug_control.py:266` → `self.help`),
debug builtin `_OPTION_MAP` derived from the option registry's DEBUG category (+ delete the
phantom 'parser' row), `help` version fallback (drop the hardcoded '0.54.0'; use `psh.version`),
`__main__.py` HELP_TEXT (-o/+o, +x, -B/+B), and rewrite-or-delete `explain_parse` (decision:
shrink to a short, derived-from-wired-modules summary; delete the advantages blurb).

## P6 — Strict-errors border repairs (remainder)

- Arithmetic cant-happen branches (`evaluator.py:220/:290/:304/:342/:423`): raise
  `RuntimeError("internal: ...")` (strict re-raises RuntimeError) instead of `ValueError`; KEEP the
  ValueError catches — the verifier proved plain ValueError is user-reachable (huge-int parse), so
  the original "narrow the catch" prescription is WRONG. Add one test per direction (user-reachable
  ValueError → clean shell error; injected internal RuntimeError → strict re-raise).
- `read`'s `ValueError` + `setattr('rc')` dialect → a small typed `ReadError(PshError)` carrying
  rc; align mapfile's sibling dialect to the same class.
- `UnclosedQuoteError` rooting: audit catch sites first; preferred end-state
  `class UnclosedQuoteError(PshError)`; if the audit shows load-bearing `except SyntaxError`
  coupling, dual-inherit `(PshError, SyntaxError)` and document why. Update `exceptions.py`'s
  "everything roots at PshError" claim to be true either way.
- Update `internal_errors.py`'s guard-count docstring (undercounts its delegates).

## P7 — Efficiency residue (single slot, all measured-before/after)

`CommandAccumulator.feed`: cache the preprocessed prefix (continuation-joined text) so each new
line preprocesses incrementally; keep the whole-buffer re-parse (correctness first) but document
the per-logical-command quadratic bound in the docstring; add a 500-line-function timing
sanity check to `tests/performance/` (not the gate). RD parser: precompute the two frozenset
unions as named `TokenGroups` members; module-level frozenset for the unclosed-expansion check.
Lexer: hoist the per-token `sorted()` → `_LENGTHS = (3, 2, 1)`. `KeyDecoder`: `collections.deque`
for the pending-bytes queue. `set -x` for-loop header: render once per loop, not per iteration
(`control_flow.py:333`) — verify xtrace output unchanged. Undo-stack growth cap (edit_buffer):
bound at N snapshots with a comment.

## P8 — Monolith blind-spot reads (M16)

`ScopeManager.set_variable` (171 lines, `core/scope.py:441`) and `execute_function_call`
(167 lines, `executor/function.py:90` — zero findings across all lists, which is itself the flag):
one dev reads each end-to-end and files either (a) a decomposition proposal with named seams, or
(b) a written "cohesive as-is" verdict with the invariants it protects. No code change without the
integrator approving the proposal. Rider: the four hand-rolled enumeration walks
(`scope.py:854/:875/:909/:969`) converge on one `iter_effective_variables()` generator with
call-site filters — this IS approved (twin-class); include the OPTION_REFLECTION_SPECIALS
injection question in the design (only `all_variables_with_attributes` injects them today — probe
`declare -p` vs `set` vs `export -p` listings against bash to decide per-surface).
`state.variables` property: fix the four production readers (T13 covers two; `rc_loader` comment
already warns) to `get_variable`, then docstring the property as SNAPSHOT semantics (tests use it
widely — do not delete this wave).

---

# Wave sequencing proposal (2 slots/wave, existing cadence)

| Wave | Slot A | Slot B | Notes |
|------|--------|--------|-------|
| 1 | D1 (lexer+parser dead) | D3 (core/exec/expn dead) | disjoint trees |
| 2 | D2 (combinator dead) | D4 (builtins/io/inter/script dead) | disjoint |
| 3 | D5 (visitor/ast/utils dead) | D6 (tests+root dead) | disjoint |
| 4 | T1 (core twins, behavior) | T4 (lexer/heredoc family) | T4 is the riskiest — early |
| 5 | T2 (declare/local) — solo | — | largest brief |
| 6 | T3 (builtins options/PWD/PATH) | T5 (io_redirect + H1) | |
| 7 | T6 (scripting pipeline) | T7 (executor taxonomy) | |
| 8 | T8 (expansion twins) | T9 (arithmetic) | |
| 9 | T10 (visitor advisories) | T12 (tests twins) | |
| 10 | T11 (ANSI-C) + T13 (interactive) | B1 + B2 | small pairs |
| 11 | B3 (parser guard) | B4 (visualization) + B5 (guard fix) | |
| 12 | B6 (expand_history) | P4 (imports + lock) | |
| 13 | P1+P2+P3 (docs) | P5 (help oracle) | |
| 14 | P6 (strict-errors) | P7 (efficiency) + P8 (reads) | |

Integrator inter-leaves with the existing queued tasks (#22/#24/#26/#27) per the standing
wave directive; T3 in particular must be sequenced against the errprefix-wave follow-ups.

# Per-brief ledger template (devs copy this)

```
BRIEF: <id>  BRANCH: fix/<topic>  BASE SHA: <sha>
Step 0 currency: <finding-by-finding: HOLDS / MOVED to <file:line> / ALREADY FIXED by <sha>>
Pre-registered battery: <cases enumerated BEFORE fix commits; bash version; script path>
Red-on-base demos: <test id → failure output at base SHA>
Fix commits: <shas>
Battery re-run at FINAL SHA: <sha, result>
Gate: <counts> | ruff: clean | mypy: clean | goldens: <n>/<n>
Riders declared: <list + integrator ruling>
Slot released: <timestamp>
```
