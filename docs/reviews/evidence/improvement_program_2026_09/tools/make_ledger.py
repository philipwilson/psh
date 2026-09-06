#!/usr/bin/env python3
"""Regenerate the generated blocks of LEDGER.md (Improvement Program 2026-09).

stdlib only.  Run from anywhere:

    python3 docs/reviews/evidence/improvement_program_2026_09/tools/make_ledger.py

Inputs (all relative to the evidence directory this script lives under):
  ../../../improvement_program_2026-09-06.md   the program (slot headings, §12, §15, §16)
  INVENTORY.json                               245 canonical rows C001–C245
  gate_triage.json                             51 red local-gate nodes at 6459f1a6

Ownership is DERIVED from the program text, not typed by hand:
  1. a cid named in a slot heading ``- **N.n Title (cids…)**`` (§7–§13) is owned
     by that slot; a heading clause ``Cxxx itself stays owned by M.m`` moves
     that cid to M.m (only 1.0 → 6.5 uses it);
  2. §15 Park rows own their cids (``Park P-n``); the §15 Excluded row owns
     C114/C163/C208; §12 owns the Checkpoint R coverage scopes (``R``);
  3. Wave 0's sub-slot headings (§6 ``**0.n — …**``) carry no cids, so the
     Wave 0 owned findings are routed by WAVE0_ROUTES with the §6 line cited;
  4. a cid still unowned is looked up in slot BODIES, restricted to the wave
     whose ``### Owned findings`` paragraph lists it (6.2 and 6.3 list their
     dead-code / doc rows in the body, not the heading);
  5. a cid still unowned but listed in a wave's Owned findings is owned at wave
     level (``N (wave charter)``) — only C229 (Wave 5 design input) lands here.
The result is cross-checked against §16 and every disagreement is printed in
Part E; the only expected one is C153 (§16 lists it under Wave 0, the 4.24
heading takes it "only if Wave 0 ruled it still divergent" — ruling R-C153).

The script rewrites only the text between ``<!-- generated:NAME:start -->``
and ``<!-- generated:NAME:end -->`` markers; the hand-written header, Part C
(N-rows) and Part D (rulings) are preserved.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
EVID = os.path.dirname(HERE)
ROOT = os.path.abspath(os.path.join(EVID, '..', '..', '..', '..'))
PROGRAM = os.path.join(ROOT, 'docs', 'reviews', 'improvement_program_2026-09-06.md')
INVENTORY = os.path.join(EVID, 'INVENTORY.json')
TRIAGE = os.path.join(EVID, 'gate_triage.json')
LEDGER = os.path.join(EVID, 'LEDGER.md')

CID = re.compile(r'\bC\d{3}\b')
SLOT_HEADING = re.compile(r'^- \*\*(\d+\.\d+)\s+(.*?)\*\*(.*)$')
WAVE0_HEADING = re.compile(r'^\*\*(0\.\d)\s+—\s+(.*?)\s+\((.*?)\)\.\*\*')
STAYS = re.compile(r'\b(C\d{3}) itself stays owned by (\d+\.\d+)')

# --- Wave 0: the §6 sub-slot headings carry no cids (rule 3 above). ----------
WAVE0_ROUTES = {
    'C242': ('0.3', '§6 "Required work": the gate is red until the 0.3 tree; green gate + schema-2 attestation are the 0.3 exit criteria'),
    'C241': ('0.1', '§6 0.1 item 8: C241 census + `test_oracle_version_comments.py` ratchet (D12)'),
    'C243': ('0.1', '§6 0.1 item 7: r23 row added to the reviews index; `test_every_review_file_is_indexed` green'),
    'C238': ('0.1', '§6 0.1 item 7: stale "latest/active" index lines refreshed (C238)'),
    'C169': ('0.1', '§6 0.1 item 7: confirm `f`, `f1`, `f2` absent at HEAD (ruling R-C169)'),
    'C245': ('0.1', '§6 Owned findings: closed by D8 (pre-handoff smoke); CLAUDE.md line in 0.1 item 7'),
    'C181': ('0.2', '§6 0.2: delete the `command_mode` DONE filter; CHANGELOG discharges the v0.692 deferral (ruling R-C181)'),
    # C153 is taken by the 4.24 heading; ruling R-C153 confirms the transfer.
}

# Wave 0 rows are heterogeneous (docs, hygiene, a ruling, the gate), so each carries
# its own symbol/guard instead of the sub-slot's.
WAVE0_META = {
    'C242': ('the 0.3 tree: `python run_tests.py --parallel --write-attestation` green, unsandboxed; `gate_attestation.json` schema 2 with `oracle.version == "5.3.15(1)-release"`',
             'runner preflight refuses under `BASH_PATH=/bin/bash`; `tools/verify_gate_attestation.py`; three seeded gates recorded in `oracle-baseline.md`'),
    'C241': ('provenance stamps ("verified against bash 5.2") rewritten only in files a slot touches (D12)',
             '`tests/unit/tooling/test_oracle_version_comments.py` ratchet — frozen baseline (Part D census) that only decreases'),
    'C243': ('`docs/reviews/README.md` rows for r23 and the program under "Current appraisal"',
             '`tests/unit/tooling/test_reviews_index.py::test_every_review_file_is_indexed`'),
    'C238': ('`docs/reviews/README.md` Live-references rows (the 2026-07 campaign and the #19/#22 audits demoted to historical wording)',
             '§13 6.3 exit criterion: the reviews index carries no stale "active" claim (re-checked at Wave 6 and Ceremony C)'),
    'C169': ('repo root (`f`, `f1`, `f2`)',
             'ruling R-C169: absent and untracked at `788ffe41`; delete on sight if they reappear'),
    'C245': ('D8 pre-handoff smoke (`run_tests.py --quick`, touched modules, ruff, mypy; four tails pasted in the handoff) + the CLAUDE.md Development Principles line',
             'the integrator rejects a handoff without the four tails (no new CI by user decision)'),
    'C181': ('`psh/builtins/job_control.py:96-98` `command_mode` DONE filter deleted (0.2)',
             '`test_jobs_completed_listing_modes.py` `_listed_once_c_mode` rows against the live oracle; CHANGELOG discharges the v0.692 deferral'),
}

# --- Per-slot owner symbol and guard, transcribed from the slot briefs. -------
# (symbol, guard).  "—" where the program names none.
SLOT_META = {
    '0.1': ('`tests/harness/oracle_policy.py` (`EXPECTED_BASH_MM`, `oracle_at_least`, `oracle_feature`); `run_tests.py#build_attestation` schema 2',
            '`test_bash_oracle_resolution.py::test_resolved_oracle_matches_policy` (red under `BASH_PATH=/bin/bash`); bash-version-literal ratchet; `test_oracle_version_comments.py` (D12); synthetic 5.2 attestation refused'),
    '0.2': ('one-site psh retunes: `psh/builtins/signal_handling.py` (`trap -P`, synopsis), `psh/builtins/shell_options.py#_print_option`, `psh/executor/job_control.py` widths, `psh/builtins/job_control.py` (`command_mode` filter deleted), `psh/builtins/hash_builtin.py`, `psh/executor/function.py`',
            '`test_builtin_help_sync.py` stays green without an allowlist entry; golden rows for every retuned command; live-oracle pins'),
    '0.3': ('`psh/executor/strategies.py#format_exec_failure` (`unset_path`); `psh/__main__.py` STDIN branch (closed fd 0 → 126); declared-divergence pins in `FLIP-PINS.md`',
            'both-sides pins with `min_bash: "5.3"` / `oracle_min("5.3")`; `gate_attestation.json` schema 2 verified by `tools/verify_gate_attestation.py`; three seeded gates → `oracle-baseline.md`'),
    '1.0': ('`tests/unit/core/test_write_authority_matrix.py` (entry points × observations)',
            'the matrix itself: cells owned by later slots ship `xfail(strict=True, reason="C0xx → slot y")`'),
    '1.1': ('`psh/executor/context.py#ExecutionContext.for_pipeline_member` (one-shot `in_pipeline`)',
            'ratchet — `in_pipeline` referenced only in `context.py`/`pipeline.py` (offender); `--debug-exec` shows no exec; golden rows'),
    '1.2': ('`psh/io_redirect/manager.py#_swap_closed_output_streams` installs `_RawFdStream`',
            'pins assert file contents after `1>&- 1>f` / `2>&- 2>f` in compound forms'),
    '1.3': ('the resolved `RedirectPlan`; `psh/io_redirect/manager.py#_builtin_redirect_fd_level` applies it',
            'counter — `planner.plan` runs once per `RedirectOp` (instrumented; mutation re-adds the second call)'),
    '1.4': ('`psh/builtins/navigation.py#resolve_cd_target(operand, mode)`; `ShellState.__init__` PWD/OLDPWD validation (W0-N7)',
            'D3 pins: `pwd -P`, `os.getcwd()`, a file placed after `cd ..`; `case_env` stale-PWD/bogus-OLDPWD rows in three modes'),
    '1.5': ('`psh/core/scope.py#ScopeManager._effective_binding_changed(name)`; `CommandHashTable` sole subscriber',
            'counter test over every write path — one observer call per binding change; `execve` target asserted'),
    '1.6': ('`VariableExpansion.braced` (`psh/visitor/formatter_visitor.py#_needs_brace_disambiguation`, `psh/ast_nodes/words.py` `__str__`)',
            '`tests/unit/visitor/test_executable_roundtrip.py` corpus: `--format` and `eval "$(declare -f f)"` reproduce stdout/rc'),
    '1.7': ('`psh/parser/recursive_descent/parsers/control_structures.py` (`ForLoop.variable` = token value; `session.py#token_lexeme`)',
            'three-mode pins with `--debug-ast`'),
    '1.8': ('`psh/lexer/state_context.py#LexicalState.at_word_start`',
            '`tests/unit/tooling/test_lexer_word_start_authority.py` — AST ratchet on `text[pos-1]`/`prev_char in` under `psh/lexer/recognizers/` (offender) + corpus differential vs the `$(…)` scanner'),
    '1.9': ('`_parse_trailing_redirects` in `psh/parser/combinators/special_commands.py`',
            'matrix — every AST class with `redirects` has a combinator production consuming them (RD↔combinator AST equality); direct-API pins (D6)'),
    '1.10': ('`psh/executor/core.py` per-statement `noexec` check; `command.py#_run_command` sets `$?` from the last substitution',
             'independent three-mode pins; user-guide `17_differences_from_bash.md:25` corrected in the same diff'),
    '1.11': ('`psh/expansion/pattern_words.py#expand_pattern_word` (tilde + quote-aware; `case`, `[[ == ]]`, `${var#pat}`)',
             'pins `~`, `~/x`, `~+`, alternation, quoted control; user-guide rows `:934`/`:941`'),
    '1.12': ('`psh/executor/process_launcher.py#AsyncJobPolicy.apply` (fd 0 origin from the stream bindings)',
             'pins read the actual bytes'),
    '1.13': ('`psh/io_redirect/process_sub.py` (`ExitStack`-owned acquisition; blocking open or diagnostic, never silent `/dev/null`)',
             'fault injection at pipe/flag/FIFO/fork/launch; `/dev/fd` census asserts no leak; 6 s late-open pin; Linux nightly (D11)'),
    '1.14': ('`psh/builtins/numeric.py#legal_number` (+ `legal_octal`, `legal_fd`, `finite_timeout`)',
             'ratchet — no bare `int(`/`float(` on argv-derived operands under `psh/builtins/` outside the owner (offender); user-guide `:990`'),
    '1.15': ('`scope_manager.lookup(name).is_set` in `psh/core/options.py`; `parameter_expansion.py` drops the env union',
             'ratchet forbidding `state.env` reads for set-ness/enumeration in `psh/core/options.py`, `psh/expansion/` (offender); user-guide `:957`'),
    '1.16': ('`ScopeManager.set_variable`/`create_local` (allexport at the write site); `state.py:1047` consumer deleted',
             'conformance across all five spellings; `CLAIM_TESTS` mapped; user-guide `:961`'),
    '1.17': ('`psh/builtins/mapfile_builtin.py` preflight (nameref target resolved, writability/indexed compatibility validated BEFORE reading)',
             'D3 pins: fd position after rejection; untouched assoc contents'),
    '1.18': ('`psh/core/variable_store.py#VariableStore.promote_to_indexed`; `psh/executor/array.py#ArrayBuilder` phases (`IndexedInitializerCursor`, `VarAttributes.UNSET`)',
             '1.0 matrix extended with array cells + ratchet: `VarAttributes.ARRAY` construction outside the store fails (offender); `test_no_derived_variables_writes.py` extended'),
    '1.19': ('`psh/expansion/word_expander.py#_project_star_fields(parts, quoted)`; `DEFAULT_IFS` and `IFS_WHITESPACE` constants',
             "ratchet forbidding `' \\t\\n'` as a class test and `' '.join(` on field lists in `psh/expansion/` and `read_builtin.py` (offender); compare-bash IFS matrix"),
    '2.1': ('`psh/core/trap_manager.py` entry-status record `(saved_exit_code, len(function_stack), source_depth)`; `psh/builtins/core.py` applies it',
            'flipped rows renamed `…uses_entry_status` + boundary rows (subshell/function/`if`/`eval`/ERR/dot) in three modes; user-guide `:968`'),
    '2.2': ('`SpecialBuiltinUsageError(1, suppressible=True)` raised by `ExportBuiltin`, `DeclareBuiltin.run_as(invoked_as=\'readonly\')`, `UnsetBuiltin` (`psh/builtins/environment.py`, `function_support.py`); `special_exit_floor` raise deleted in `psh/scripting/source_processor.py`',
            '`TestPosixSpecialBuiltinExit` rows; `tests/integration/test_posix_special_builtin_exit.py`; golden `posixexit_*` (`min_bash: "5.3"`); matrix doc rows 48/49/51'),
    '2.3': ('`psh/core/internal_errors.py#special_builtin_usage_discard` (`SystemExit(1)` in command_mode, `TopLevelAbort(2, errexit_immune=True)` otherwise)',
            'full probe matrix in the brief; flipped `test_cd_too_many_arguments`, `test_exit_too_many_args_does_not_exit`; W0-N4 golden + `bcontract` pins'),
    '2.4': ('`psh/core/scope.py#ScopeManager.apply_attribute`/`remove_attribute` raise `ReadonlyVariableError` after nameref resolution',
            'flipped `test_declare_i_on_readonly_succeeds` / `test_attrs_only_add_integer_allowed` → `_refused`; conformance rows for the refused and allowed halves'),
    '3.1': ('`psh/utils/escapes.py#decode_ansi_c_escapes` (one digit reader; `unicode_escape_char` with surrogate/range guards)',
            'ratchet forbidding `chr(int(` in `psh/lexer/` and `psh/utils/` outside the owner (offender); cross-entry NUL matrix'),
    '3.2': ('the failing recognizer (backtick-in-subscript extent) fixed; no-progress guard KEPT as an internal-defect raise; `psh/lexer/recognizers/registry.py` carve-out `(RecursionError, PshError, SyntaxError)`',
            'reproducer pinned against 5.3.15; fault-injected pin for the carve-out'),
    '3.3': ('`psh/io_redirect/file_redirect.py#fd_from_text` (int32 range; `(OSError, OverflowError)` caught)',
            'pins `exec 4294967296>f`, `echo x 2147483648>f`'),
    '3.4': ('`psh/lexer/pure_helpers.py#scan_double_paren_arithmetic` (always quote-aware); `#validate_brace_expansion` sole `${` authority; `recognizers/operator.py` `((` only when balanced',
            'ratchet forbidding `find_closing_delimiter(` with `\'{\'` and any second `))`-search loop in `psh/lexer/` (offender); `grep -rc track_quotes psh/lexer` = 0; 1.8 corpus differential extended; user-guide `:931`'),
    '3.5': ('`psh/parser/combinators/special_commands.py` (`special_command` without `.or_else(self.process_substitution)`); `build_statement_list` depth vs the ONE `MAX_NESTING_DEPTH`',
            'direct-API pins under strict-errors'),
    '3.6': ('`psh/interactive/title.py#sanitize_title` at the single OSC write site',
            'PTY pin with a crafted `$PWD` basename; CHANGELOG flags security'),
    '3.7': ('`psh/executor/pipeline.py` (`except BaseException: rollback; raise`; explicit empty-status branch); `psh/scripting/input_sources.py` read error propagates',
            'both pipeline fault-injection probes promoted to tests; `/dev/fd` census asserts no leak'),
    '3.8': ('`psh/builtins/input_reader.py#InputCursor` + the `read` builtin stream selection handle `sys.stdin is None`',
            'pins in `-c` and script modes with fd 0 closed; strict-errors pin: no traceback'),
    '3.9': ('`JobManager` (tty handed to the pipeline pgid once; nested members never re-fork a pgid / `tcsetpgrp`)',
            'PTY pin checking `tcgetpgrp` from inside the grandchild; Linux nightly watch row'),
    '4.1': ('`psh/parser/recursive_descent/parsers/control_structures.py#_parse_word_list_loop(keyword, node_cls)`; `commands.py#_parse_brace_body`',
            'three-mode pins; user-guide `:942` (here or in 4.11)'),
    '4.2': ('`psh/parser/recursive_descent/parsers/arrays.py#_candidate_initializer`; `psh/ast_nodes/command_head.py#CommandHead.of`',
            'ratchet forbidding `.args[0]`/`.words[0]` head inspection in `psh/parser/` and `psh/visitor/` outside `CommandHead` (offender)'),
    '4.3': ('`ShellState.error_location_prefix()` / `Builtin.report_error` (all 18 sites migrated)',
            '`tests/unit/tooling/test_error_prefix_ratchet.py` — AST walk forbids `"psh: "` literals to stderr under executor/expansion/builtins (allowlist frozen to C205; offender)'),
    '4.4': ('`process_line_continuations` → `(joined_text, LineMap)`; `psh/parser/recursive_descent/support/nested_parse.py#parse_nested_command` with the enclosing source',
            'pins BOTH `$LINENO` and the command-not-found line; `psh/parser/CLAUDE.md` coordinate invariant'),
    '4.5': ('`unexpected_token_message` (via `ctx.consume()` default and both combinator sites); one `make_error_context`; `variable_store.py` raises with the pre-resolution name; `RedirectPlan.target_fd` threaded into the OSError',
            'ratchet forbidding `f"…unexpected token…"`/`"Expected "` literals outside helpers (offender); wording/caret parity rows across modes'),
    '4.6': ('`psh/expansion/enhanced_test_evaluator.py` compile diagnostic through `error_location_prefix`, rc 2',
            'conformance pin (`[[ x =~ a{1 ]]` → braces not balanced, rc 2)'),
    '4.7': ('`Builtin.parse_flags` — the only option walker (printf/times/eval/builtin/source migrated; six declaration parsers use `self.error`+`self.usage`)',
            '`test_builtin_help_sync.py` (c): builtins scanning a leading `-` without `parse_flags` on an explicit justified allowlist (the C135 drift-lock; offender); user-guide `:976`'),
    '4.8': ('per builtin: `source` usage + `SpecialBuiltinUsageError(2, suppressible=True)`; `kill -n`; `wait` malformed id; `psh/utils/printf_formatter.py` `_CONVERSIONS` without `%`',
            'conformance status/message rows; user-guide `:976`/`:953`'),
    '4.9': ('`push_temp_env_scope` (eval/source/`.` push a real `is_temp_env` scope); `_remove_export` resolves the nameref first; `SHLVL` seeded in `ShellState.__init__`; `type` under unset PATH',
            'enumeration test (`set`, `export -p`) over the temp-env scope; 1.15 `state.env` ratchet extended to `psh/builtins/environment.py`'),
    '4.10': ('`psh/invocation.py#_parse_cluster` consumed by invocation AND the `set` builtin; `InvocationConfig.argv0: Optional[str]`',
             '`test_invocation_argv_guard.py` extended so `set` cannot grow a second cluster parser (offender); golden rows `-opipefail`, `-oe pipefail`, `-ox`, `set -opipefail`'),
    '4.11': ('`ExecutionResult.assignments_persist` (posix `VAR=v exec`); `control_flow.py` select `if reply == \'\': continue`',
             'conformance pins; user-guide `:942` if landing last'),
    '4.12': ('`psh/executor/job_control.py#job_command_text(node, source)` (AST source extents); `JobManager.create_job` burns no number for foreground commands',
             'flips the Wave 0 signal-death FLIP-PIN to parity (`strsignal.ljust(27) + text`)'),
    '4.13': ('trap dispatcher "handler fired" record → `wait` 128+N; procsub-wait list registered at fork; PIPESTATUS re-stamp removed inside groups; pipeline member runs its own EXIT trap',
             'each 2026-07 LEDGER successor row closes with a pin; 138-vs-158 nightly row; user-guide `:953`'),
    '4.14': ('`fd_from_text` (from 3.3): `{v}` unset → `NAME: ambiguous redirect` rc 1; move form closes the SOURCE in the parent',
             'conformance pins (bash 5.3 confirmed)'),
    '4.15': ('`TokenGroups.WORD_LIKE` (every word-like set derives from it); `[[` operator table imported from the one RD/test-evaluator table; `build_statement_list` stamps `.line`',
             'ratchet forbids local `frozenset({TokenType.WORD, …})` in `psh/parser/combinators/` (offender); committed RD↔combinator corpus parity test; direct-API pins (D6)'),
    '4.16': ('`_render_redirects` helper on DebugASTVisitor; node-anchored `visit_CommandSubstitution`/`visit_ProcessSubstitution`; security command head via 4.2\'s `CommandHead.of`',
             '`test_ast_coverage_matrix.py` parametrized over EVERY analysis visitor'),
    '4.17': ('`psh/parser/visualization/dot_generator.py` (scalar else arm; DOT escaping); `_render_sexp_list` indent threading',
             'renderer pins (escaping, indentation)'),
    '4.18': ('`ShellState.history_base` (monotonic; owner of `!n`, `\\!`, listing numbers); `LOCK_EX` in `write_history`/`append_history`; `_editable` at `_replace_line`; `CTRL_UNDERSCORE` → undo',
             'pins via `history -s`/`-p`/`${PS1@P}` + one PTY leg; user-guide `:983`'),
    '4.19': ('`psh/interactive/tab_completion.py#CompletionContext` (raw span, decoded lookup text, quote mode)',
             'PTY workflow tests (escaped spaces/quotes/`$`/backticks/backslashes, cursor mid-word)'),
    '4.20': ('one canonical action table in `psh/interactive/keybindings.py`; `prompt.py#_get_cwd` (shell `HOME`, component boundary, `PROMPT_DIRTRIM`, octal 1–3 digits)',
             'completeness test — mode-independent actions bound in every table'),
    '4.21': ('the 4B.2 incremental UTF-8 decoder reused by `KeyDecoder`; `line_layout` single width policy',
             'ratchet: no second decoder; PTY pin delivering split 2/3/4-byte sequences'),
    '4.22': ('the `cat <<` classification rule (interactive INCOMPLETE vs non-interactive syntax error)',
             'PTY pin'),
    '4.23': ('user-guide §17 row "no REPL with non-tty stdin (deliberate, `__main__.py:279-290`)"',
             'No-row probe in `test_claims_have_tests.py`'),
    '4.24': ('the command-number increment (`psh/interactive/prompt.py`, `psh/scripting/source_processor.py`): `-c` mode must hold `\\#` at 1 like bash 5.3 (ruling R-C153)',
             '`${PS1@P}` pins in `-c`/script/stdin + a PTY leg'),
    '5.1': ('`psh/lexer/modular_lexer.py#emit_token` builds the frozen `Token` once; literal collector segment accumulation; cursor-indexed `[` lookahead',
            'scaling pins (one long word; 2000 `[`-words on a line); replace-count = 0 per recognizer token; `tools/regen_lexer_corpus.py` diff reviewed in the ledger'),
    '5.2': ('`psh/lexer/heredoc_lexer.py` — skip the re-lex while the failure is `UnclosedQuoteError`',
            '`test_heredoc_scaling.py` extended with a one-logical-command source'),
    '5.3': ('`psh/parser/combinators/commands/pipelines.py` (redundant retry deleted; optional packrat memo keyed `(id(parser), pos)`)',
            'counter pin linear in nesting (≤ 2× per +2 levels); memory pin'),
    '5.4': ('`psh/expansion/operands.py` list accumulation, flushed per protection change',
            'scaling pin'),
    '5.5': ('`VarAttributes.is_*` against raw ints; PEP-562 lazy `psh/__init__.py` (+ `__main__.py` handles `--version`/`--help` before importing `Shell`); `_read_line_block` chunk accumulator; `args` snapshot per handler',
            '`python -c "import psh"` does not import `psh.shell`; `--version` wall ≤ 40% of the Wave 0 baseline; microbench ≥ 1.6× recorded'),
    '5.6': ('`psh/builtins/mapfile_builtin.py` incremental records on the unbounded path',
            'peak-memory pin'),
    '6.1': ('tree-wide ratchets (error-prefix; one-extent-authority census; `TokenGroups.WORD_LIKE` derivation; duplicated literals; `chr(int(`/bare `int(` census); C178 sentence in `psh/parser/CLAUDE.md`',
            'each ratchet run against its offender'),
    '6.2': ('coverage-instrumented deletion sweep (dead code / duplicated rules)',
            'census tests enumerate the surviving allowlisted sites with reasons'),
    '6.3': ('`tests/unit/tooling/test_comment_hygiene.py` (campaign-ID ceiling that only decreases; `tmp/` pointers forbidden); `test_doc_pointers` gains the `#symbol` half',
            'documented-by-design rows stated in `17_differences_from_bash.md` with both-sides pins; `test_doc_snippets.py` green'),
    '6.4': ('named `ShellState.__init__` phases; VariableStore completes its transaction contract or is retitled; legacy config-path census; protocol census',
            'ratchet forbidding new `Shell`/`ShellState`-typed protocol members; no new import cycles; functions ≥ 100 lines ≤ the Wave 0 baseline'),
    '6.5': ('cross-entry-point matrix where the 1.0 matrix did not reach; written D3 audit per closed Wave 1 row',
            'the audit itself (D3 compliance per row)'),
}

# Owner symbol / guard for rows not owned by a numbered slot.
PARK_META = {
    'P-1': ('RESUMABLE-PARSER successor campaign (measured cost target + own verification model)', 'characterization pins become upper-bound tests when it lands'),
    'P-2': ('by design (educational parser); one sentence in `psh/parser/CLAUDE.md` via 6.1', 'C178 is D6'),
    'P-3': ('not a feature-parity sweep; funsub pinned as a declared divergence behind `oracle_feature(\'funsub\')` (0.1); 6.3 verifies the doc rows', '`$(< file)` may be pulled in ONLY by a written ruling after Wave 4'),
    'P-4': ('declared divergence documented at `psh/builtins/core.py:380-390`', '6.3 verifies the both-sides pin'),
    'P-5': ('successor: defined width policy + rendering harness', '—'),
    'P-6': ('platform, not psh', '`oracle_feature(\'x87_long_double\')` classification (0.1)'),
}
R_META = ('Checkpoint R report (`checkpoint-r/`) — explicit coverage scope', 'attack rounds to zero; every ratchet re-run against its offender; Linux nightly green at the checkpoint tree')
EXCLUDED_META = ('§15 Excluded — recorded in `INVENTORY.json` with the verify note; not queued', '—')

# --- Gate-triage nodes → Wave 0 sub-slot, per §6. ------------------------------
# (regex on node_id, slot, owner symbol, guard/closure instrument)
GATE_ROUTES = [
    (r'test_error_prefix_conformance\.py|test_trap_signal_spec_conformance\.py', '0.2',
     '`psh/builtins/signal_handling.py` — synopsis `trap [-Plp] [[action] signal_spec ...]` + `-P` implemented (flags `lpP`)',
     'live-oracle stderr pins (no test edit); `test_builtin_help_sync.py` green WITHOUT an allowlist entry'),
    (r'test_cmdsub_errexit_conformance\.py|test_locale_conformance\.py|test_nocasematch_conformance\.py', '0.2',
     '`psh/builtins/shell_options.py#_print_option` width 15→20 for shopt-table prints (`set -o` / `-o` listings stay 15)',
     'live-oracle pins; `test_shopt.py:79`, `test_shopt_set_o.py`, golden rows `:2378`/`:8910` retuned'),
    (r'test_stdin_startup_robustness\.py', '0.3',
     '`psh/__main__.py` STDIN non-interactive branch: `sys.stdin is None` → `error creating buffered stream: Bad file descriptor`, exit 126',
     '`test_plain_with_closed_fd0` / `test_dash_s_with_closed_fd0` → 126; W0-N1 (`read` with fd 0 closed at start) registered → 3.8'),
    (r'r18t2_builtins_history_write_to_stdout', '0.1',
     'golden row gains `requires_dev_fd: true` (probe-open `/dev/stdout`)',
     'ENV skip (D4): SKIP under a sandbox, never FAIL'),
    (r'test_socket_earlier_bash_126_psh_runs_later', '0.1',
     '`except PermissionError: pytest.skip` around the AF_UNIX bind; docstring "5.2- and 5.3.15-verified"',
     'ENV skip (D4)'),
    (r'test_cap_kill_reaches_a_writer_that_left_the_process_group', '0.1',
     'skip when `ps -eo pid=,ppid=` cannot spawn',
     'ENV skip (D4)'),
    (r'test_variable_projection_reads_conformance\.py|test_command_resolution_r3\.py', '0.3',
     '`psh/executor/strategies.py#format_exec_failure` — `unset_path = not state.scope_manager.lookup(\'PATH\').is_set` (bash 5.3 CHANGES p: NULL PATH ≡ ".")',
     'renamed `…_is_command_not_found` twins + `local PATH=` row; W0-N5 registered → 4.9'),
    (r'test_hash_conformance\.py', '0.2',
     '`psh/builtins/hash_builtin.py:80-83` empty-table short-circuit deleted (bash 5.3 CHANGES calls 5.2 a bug)',
     'conformance row uses `2>/dev/null`; `test_hash_builtin.py::…_silently_succeeds` → `_reports_miss`'),
    (r'test_declare_i_on_readonly_succeeds', '0.3',
     'declared-divergence pin (both sides, `oracle_min("5.3")`) — FLIP-PINS row owned by 2.4',
     'flips in 2.4 (`ScopeManager.apply_attribute` refusal)'),
    (r'test_posix_special_builtin_exit_conformance\.py', '0.3',
     'declared-divergence pins (both sides, `oracle_min("5.3")`) — FLIP-PINS rows owned by 2.2',
     'flip in 2.2 (`SpecialBuiltinUsageError(1, suppressible=True)`; eval/dot boundary transparent)'),
    (r'test_declare_export_read_report_and_continue', '0.3',
     'test split: `declare é`/`read é` stay report-and-continue; `export é=1` half becomes a declared-divergence pin — FLIP-PINS row owned by 2.2',
     'flip in 2.2'),
    (r'test_for_and_function_rejected_by_both', '0.2',
     '`psh/executor/function.py:47-55` posix-mode function-name rejection deleted; `function_support.py` stops pre-validating `-f` operands',
     'split test: keep `for é`; new `test_function_names_unrestricted_in_posix`; user-guide `17_differences_from_bash.md:504-540` narrowed'),
    (r'test_pipeline_signal_death\.py|test_signal_killed_diagnostic\.py', '0.1',
     'S path: `bash.stderr == strsignal(SIGTERM).ljust(27) + \'<job text>\\n\'` with psh\'s bare-form pin kept; docstrings + `psh/executor/job_control.py:626-628` reworded',
     'FLIP-PINS row owned by 4.12 (C065 job text) for the L path'),
    (r'test_bg_actually_resumes_a_job_stopped_behind_the_shells_back', '0.1',
     'skip when `ps -o stat= -p $$` is empty',
     'ENV skip (D4)'),
    (r'test_cd_too_many_arguments|test_exit_too_many_args_does_not_exit', '0.3',
     'declared-divergence pins (both sides, `oracle_min("5.3")`) — FLIP-PINS rows owned by 2.3',
     'flip in 2.3 (`special_builtin_usage_discard` → rc 2 on the next line); W0-N4 golden `bcontract_exit_bad_first_operand_exits_two`'),
    (r'test_exit_trap_status_precedence_conformance\.py', '0.3',
     'declared-divergence pins (4 nodes incl. the must-hold; both sides, `oracle_min("5.3")`) — FLIP-PINS rows owned by 2.1',
     'flip in 2.1 (trap entry status, POSIX interp 1602 / bash 5.3 NEWS uu)'),
    (r'test_bash_compatibility\.py::TestBashJobControl|_done_label_script|_listed_once_script|_listed_once_stdin|test_jobs_n_completion_listed_once_script', '0.2',
     '`psh/executor/job_control.py:279/:280/:683` status column `:<24` → `:<27`',
     'live-oracle pins (no test edit)'),
    (r'_suppressed_c_mode', '0.2',
     '`psh/builtins/job_control.py:96-98` `command_mode` DONE filter deleted (C181 closed); tests renamed `_listed_once_c_mode`',
     'CHANGELOG discharges the v0.692 deferral; module docstring rewritten'),
    (r'test_bad_substitution_conformance\.py', '0.1',
     '`${ }` / `${ :-x}` dropped from BAD_CASES; funsub declared-divergence pin guarded by `oracle_feature(\'funsub\')`',
     'Park P-3 (no flip in this program); FLIP-PINS notes the row'),
    (r'test_divergence_procsub_compound_render_residual', '0.1',
     'PREMISE S-edit: 4th tuple → bash 5.3\'s `\'<(case x in y)\\n        echo n\\n    ;;\\nesac)\'`; trailing-space docstring phrase dropped',
     'pin retuned in place'),
    (r'test_divergence_sq_in_dq_readback_outcome', '0.1',
     'PREMISE: parity pin renamed `test_sq_in_dq_readback_round_trips` (bash 5.3 CHANGES k: subscripts expanded once)',
     'oracle-side closure recorded in FLIP-PINS (no flip)'),
    (r'test_unlexable_subscript_route_audit\[let_arith\]', '0.1',
     'PREMISE S-edit: bash branch → rc 0 / `declare -A a` / `not a valid identifier`',
     'pin retuned in place'),
    (r'test_tilde_expands_in_key', '0.1',
     'ENV: `env={\'HOME\': \'/probe-home\'}` with the D14 comment (Homebrew 5.3.15 bottle resolves `~` from the startup environment)',
     'pin retuned in place (D14)'),
    (r'test_redirect_procsub_suppression_is_a_declared_divergence', '0.1',
     'ENV: write-row poll lengthened 10×0.1 s → 30×0.1 s',
     'pin retuned in place'),
    (r'test_invalid_regex_diagnostic_is_psh_only', '0.1',
     'PREMISE: both-diagnose wording pin (`invalid regular expression` in bash, `invalid regex` in psh, rc 2 both)',
     'W0-N3 (`[[ x =~ a{1 ]]` rc 1 vs 2) registered → 4.6'),
]


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def esc(s):
    return str(s).replace('|', '\\|').replace('\n', ' ')


def short(title, n=96):
    title = re.sub(r'\s+', ' ', title).strip()
    if len(title) <= n:
        return title
    cut = title[:n].rsplit(' ', 1)[0]
    if cut.count('`') % 2:            # never cut inside a code span
        cut = cut[:cut.rindex('`')].rstrip()
    return cut + '…'


def parse_program(text):
    lines = text.splitlines()
    # section index: '## N.' → (start, end)
    sec_starts = [(i, m.group(1)) for i, ln in enumerate(lines)
                  if (m := re.match(r'^## (\d+)\.', ln))]
    sections = {}
    for k, (i, num) in enumerate(sec_starts):
        end = sec_starts[k + 1][0] if k + 1 < len(sec_starts) else len(lines)
        sections[int(num)] = (i, end)

    slots = {}          # id -> dict(title, wave, heading, body, line)
    heading_owner = defaultdict(set)
    stays = {}
    # Waves 1–6 (§7–§11, §13): '- **N.n Title (…)**'
    for i, ln in enumerate(lines):
        m = SLOT_HEADING.match(ln)
        if not m:
            continue
        sid, head, body = m.group(1), m.group(2), m.group(3)
        title = head.split(' (', 1)[0].rstrip('.')
        slots[sid] = dict(title=title, wave=sid.split('.')[0], heading=head, body=body, line=i + 1)
        for cid, target in STAYS.findall(head):
            stays[cid] = target
        for cid in CID.findall(head):
            if cid in stays and stays[cid] != sid:
                continue
            heading_owner[cid].add(sid)
    for cid, target in stays.items():
        heading_owner[cid].add(target)
    # Wave 0 (§6): '**0.n — Title (…).**' followed by a numbered/bulleted list
    s6 = sections[6]
    for i in range(*s6):
        m = WAVE0_HEADING.match(lines[i])
        if m:
            sid = m.group(1)
            # body = lines until the next wave-0 heading or the exit-criteria heading
            j = i + 1
            buf = []
            while j < s6[1] and not WAVE0_HEADING.match(lines[j]) and not lines[j].startswith('### '):
                buf.append(lines[j])
                j += 1
            slots[sid] = dict(title=m.group(2), wave='0', heading=m.group(2), body='\n'.join(buf), line=i + 1)

    # '### Owned findings' paragraph per wave section
    wave_of_section = {6: '0', 7: '1', 8: '2', 9: '3', 10: '4', 11: '5', 13: '6'}
    owned = defaultdict(set)   # cid -> waves
    for sec, wave in wave_of_section.items():
        a, b = sections[sec]
        for i in range(a, b):
            if lines[i].startswith('### Owned findings'):
                j = i + 1
                while j < b and not lines[j].startswith('### '):
                    for cid in CID.findall(lines[j]):
                        owned[cid].add(wave)
                    j += 1
    # §12 (R)
    r_cids = set()
    a, b = sections[12]
    for i in range(a, b):
        r_cids.update(CID.findall(lines[i]))
    # §15 Park table
    park = {}
    a, b = sections[15]
    excluded = set()
    for i in range(a, b):
        m = re.match(r'^\| (P-\d) ([^|]*)\| ([^|]*)\|', lines[i])
        if m:
            for cid in CID.findall(m.group(3)):
                park[cid] = m.group(1)
        m2 = re.match(r'^\| Excluded[^|]*\| ([^|]*)\|', lines[i])
        if m2:
            excluded.update(CID.findall(m2.group(1)))
    # §16 table
    s16 = {}
    a, b = sections[16]
    for i in range(a, b):
        m = re.match(r'^\| ([^|]+?) \| (.*) \|$', lines[i])
        if m and m.group(1).strip() not in ('Wave / slot', '---'):
            for cid in CID.findall(m.group(2)):
                s16[cid] = m.group(1).strip()
    return slots, heading_owner, owned, r_cids, park, excluded, s16


def derive_owner(cid, slots, heading_owner, owned, r_cids, park, excluded):
    """Return (owner, method, note)."""
    hs = heading_owner.get(cid, set())
    if len(hs) == 1:
        sid = next(iter(hs))
        return sid, 'heading', f'§{slot_section(sid)} `{sid}` heading (line {slots[sid]["line"]})'
    if len(hs) > 1:
        return ' / '.join(sorted(hs)), 'CONFLICT', 'named in more than one slot heading'
    if cid in r_cids:
        # §12 wins over §15: C215 is a Checkpoint R coverage scope whose
        # REMAINDER ("beyond Checkpoint R's PTY scope") is parked under P-5.
        extra = f'; also named in §15 {park[cid]} for the remainder' if cid in park else ''
        return 'R', 'checkpoint', '§12 coverage scope' + extra
    if cid in park:
        return f'Park {park[cid]}', 'park', '§15'
    if cid in excluded:
        return 'Excluded', 'excluded', '§15 Excluded row'
    if cid in WAVE0_ROUTES:
        return WAVE0_ROUTES[cid][0], 'wave0', WAVE0_ROUTES[cid][1]
    waves = owned.get(cid, set())
    bodies = [sid for sid, s in slots.items()
              if s['wave'] in waves and cid in CID.findall(s['body'])]
    if len(bodies) == 1:
        return bodies[0], 'body', f'§{slot_section(bodies[0])} `{bodies[0]}` body (line {slots[bodies[0]]["line"]}); wave from its Owned findings'
    if len(bodies) > 1:
        return ' / '.join(sorted(bodies)), 'CONFLICT', 'named in more than one slot body of its wave'
    if len(waves) == 1:
        w = next(iter(waves))
        return f'{w} (wave charter)', 'wave', f'§{ {"0":6,"1":7,"2":8,"3":9,"4":10,"5":11,"6":13}[w] } Owned findings only'
    return 'UNOWNED', 'NONE', 'not found in any heading, body, park, excluded, R or Owned findings'


def slot_section(sid):
    return {'0': 6, '1': 7, '2': 8, '3': 9, '4': 10, '5': 11, '6': 13}[sid.split('.')[0]]


def wave_of_owner(owner):
    if owner.startswith('Park'):
        return 'Park'
    if owner in ('Excluded', 'R'):
        return owner
    return owner.split('.')[0].split(' ')[0]


def meta_for(owner):
    if owner.startswith('Park '):
        return PARK_META.get(owner.split()[1], ('—', '—'))
    if owner == 'Excluded':
        return EXCLUDED_META
    if owner == 'R':
        return R_META
    if owner in SLOT_META:
        return SLOT_META[owner]
    if owner.endswith('(wave charter)'):
        return ('every slot of the wave (design input; no single owner symbol)', 'wave exit criteria (§11: before/after numbers + scaling/counter pin per row)')
    return ('—', '—')


def part_a(rows, slots, heading_owner, owned, r_cids, park, excluded):
    out = ['| id | title | sev / kind | status | owner slot | owner symbol | guard | closure |',
           '|---|---|---|---|---|---|---|---|']
    derived = {}
    for r in sorted(rows, key=lambda r: r['cid']):
        owner, method, note = derive_owner(r['cid'], slots, heading_owner, owned, r_cids, park, excluded)
        derived[r['cid']] = (owner, method, note)
        sym, guard = WAVE0_META.get(r['cid']) or meta_for(owner)
        status = r['status']
        if r['cid'] == 'C153':
            status = 'oracle_changed → still divergent in `-c` (R-C153)'
        elif r['cid'] == 'C181':
            status = 'oracle_changed → closed by 0.2 (R-C181)'
        elif r['cid'] == 'C169':
            status = 'n/a → already gone (R-C169)'
        out.append('| {} | {} | {} {} | {} | {} | {} | {} |  |'.format(
            r['cid'], esc(short(r['title'])), r['severity'], r['kind'], esc(status),
            esc(owner), esc(sym), esc(guard)))
    return '\n'.join(out), derived


def part_b(nodes):
    out = ['| id | node (red at `6459f1a6`) | triage / effort | status | owner slot | owner symbol | guard | closure |',
           '|---|---|---|---|---|---|---|---|']
    routes = Counter()
    for k, n in enumerate(nodes, 1):
        nid = n['node_id']
        hit = None
        for pat, slot, sym, guard in GATE_ROUTES:
            if re.search(pat, nid):
                hit = (slot, sym, guard)
                break
        if hit is None:
            raise SystemExit(f'gate node without a route: {nid}')
        slot, sym, guard = hit
        routes[slot] += 1
        short_node = nid.replace('tests/', '', 1)
        out.append('| G{:02d} | `{}` | {} / {} | RED @6459f1a6 | {} | {} | {} |  |'.format(
            k, esc(short_node), n['category'], n['effort'], slot, esc(sym), esc(guard)))
    return '\n'.join(out), routes


def part_e(derived, s16, slots):
    out = []
    by_wave_derived = defaultdict(set)
    for cid, (owner, _method, _note) in derived.items():
        by_wave_derived[wave_of_owner(owner)].add(cid)
    by_wave_s16 = defaultdict(set)
    for cid, w in s16.items():
        by_wave_s16[w].add(cid)
    out.append('| wave | derived (headings/§12/§15/§6) | §16 map | agree |')
    out.append('|---|---:|---:|---|')
    for w in ['0', '1', '2', '3', '4', '5', 'R', '6', 'Park', 'Excluded']:
        d, s = by_wave_derived.get(w, set()), by_wave_s16.get(w, set())
        out.append(f'| {w} | {len(d)} | {len(s)} | {"yes" if d == s else "NO: " + ", ".join(sorted(d ^ s))} |')
    methods = Counter(m for _, m, _ in derived.values())
    out.append('')
    out.append('Derivation methods: ' + ', '.join(f'{k} = {v}' for k, v in sorted(methods.items())) + '.')
    disagreements = []
    for cid, (owner, _method, note) in sorted(derived.items()):
        w = wave_of_owner(owner)
        if cid not in s16:
            disagreements.append(f'- {cid}: derived `{owner}`, ABSENT from §16')
        elif s16[cid] != w:
            disagreements.append(f'- {cid}: derived `{owner}` ({note}); §16 says `{s16[cid]}`')
    conflicts = [f'- {cid}: {owner} — {note}' for cid, (owner, m, note) in sorted(derived.items()) if m in ('CONFLICT', 'NONE')]
    out.append('')
    out.append(f'Disagreements with §16 ({len(disagreements)}):')
    out.extend(disagreements or ['- none'])
    out.append('')
    out.append(f'Derivation conflicts / unowned ({len(conflicts)}):')
    out.extend(conflicts or ['- none'])
    extra16 = sorted(set(s16) - set(derived))
    out.append('')
    out.append(f'§16 cids not in INVENTORY.json: {extra16 or "none"}; §16 rows: {len(s16)}; inventory rows: {len(derived)}.')
    # non-heading rows, for the record
    out.append('')
    out.append('Rows not derived from a slot heading (method ≠ heading):')
    for cid, (owner, method, note) in sorted(derived.items()):
        if method != 'heading':
            out.append(f'- {cid} → `{owner}` [{method}]: {note}')
    return '\n'.join(out)


def c241_census():
    """Per-file counts of the literal 'bash 5.2' under tests/ and psh/ (C241 baseline)."""
    try:
        res = subprocess.run(['grep', '-rn', 'bash 5\\.2', 'tests/', 'psh/'], cwd=ROOT,
                             capture_output=True, text=True)
    except OSError as e:
        return f'(census unavailable: {e})'
    files = Counter(line.split(':', 1)[0] for line in res.stdout.splitlines() if line)
    head = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    total = sum(files.values())
    multi = {f: n for f, n in files.items() if n > 1}
    single = sorted(f for f, n in files.items() if n == 1)
    out = [f'`grep -rn "bash 5\\.2" tests/ psh/` at `{head}`: **{total} lines in {len(files)} files** '
           f'(the D12 ratchet baseline; only decreases; rewritten only in files a slot touches). '
           f'Files with ≥ 2 lines are tabled; the {len(single)} single-line files follow as a list.', '',
           '| file | lines |', '|---|---:|']
    for f, n in sorted(multi.items(), key=lambda kv: (-kv[1], kv[0])):
        out.append(f'| `{f}` | {n} |')
    out.append('')
    out.append('One line each: ' + ', '.join(f'`{f}`' for f in single) + '.')
    return '\n'.join(out)


def splice(text, name, body):
    start, end = f'<!-- generated:{name}:start -->', f'<!-- generated:{name}:end -->'
    if start not in text or end not in text:
        raise SystemExit(f'LEDGER.md lacks the {name} markers')
    a = text.index(start) + len(start)
    b = text.index(end)
    return text[:a] + '\n' + body + '\n' + text[b:]


def main():
    program = read(PROGRAM)
    rows = json.load(open(INVENTORY, encoding='utf-8'))
    nodes = json.load(open(TRIAGE, encoding='utf-8'))
    slots, heading_owner, owned, r_cids, park, excluded, s16 = parse_program(program)

    a_text, derived = part_a(rows, slots, heading_owner, owned, r_cids, park, excluded)
    b_text, routes = part_b(nodes)
    e_text = part_e(derived, s16, slots)
    census = c241_census()

    text = read(LEDGER)
    text = splice(text, 'part-a', a_text)
    text = splice(text, 'part-b', b_text)
    text = splice(text, 'part-e', e_text)
    text = splice(text, 'c241', census)
    with open(LEDGER, 'w', encoding='utf-8') as f:
        f.write(text)

    bad = [cid for cid, (o, m, n) in derived.items() if m in ('CONFLICT', 'NONE') or o == 'UNOWNED']
    print(f'inventory rows: {len(rows)}; gate nodes: {len(nodes)}; slots parsed: {len(slots)}')
    print('gate routes:', dict(sorted(routes.items())))
    print('unowned/conflict:', bad or 'none')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
