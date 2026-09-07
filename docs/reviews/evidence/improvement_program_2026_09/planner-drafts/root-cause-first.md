# Root-Cause Consolidation Program — reappraisal #23 + fresh appraisal 2026-09-06

- **Date:** 2026-09-06
- **Status:** PLANNED, NOT LAUNCHED. Nothing executes without an explicit user go.
- **Launch base:** `origin/main` @ `6459f1a6` (v0.779.0).
- **Oracle (USER DECISION, binding):** GNU bash **5.3.15** at `/opt/homebrew/bin/bash`. Never `/bin/bash` (3.2). Reappraisal #23 was verified against 5.2.26; every 5.2-pinned expectation is re-derived against 5.3.15 in Wave 0 before anything else lands.
- **Findings sources:** `docs/reviews/ground_up_reappraisal_23_correctness_textbook_2026-08-09.md` (UNCOMMITTED — Wave 0 commits and indexes it) and `docs/reviews/fresh_appraisal_2026-09-06.md`, folded into the 245-row canonical inventory (C001–C245) re-verified at HEAD on 2026-09-06 — ALL correctness rows re-reproduced; the fresh appraisal's red gate is oracle drift (bash 5.2.26 → 5.3.15 on 2026-08-18), not psh regression.
- **Governing documents, authority order:** (1) this program; (2) `boundary_remediation_integrator_plan_2026-07-21.md` §3 roles / §5 per-slot verification standard / §7 release ceremony — ADOPTED BY REFERENCE; (3) `boundary_remediation_campaign_sequence_2026-07-21.md` §3 standing rules 1–10 — ADOPTED BY REFERENCE except as amended in the "Standing rules (deltas)" section; (4) `.claude/skills/psh-release/SKILL.md` and `CLAUDE.md` (local gate; attestation is the FINAL commit; no manual tag).

---

## 1. Decision

Run a **root-cause consolidation campaign**: cluster the 245 rows by the *mechanism* that produces them and close each cluster with **one rule in one named owner plus one guard that forbids re-duplication**. A slot that fixes a symptom without landing the owner and the guard is a bounce, not a partial close.

This is the fresh appraisal's Design §1 made operational: the live defects (scalar→array promotion in three builders, four drifted `WORD_LIKE` sets, three IFS-whitespace literals, eighteen bypassed error-prefix sites, two `${…}` extent scanners, five hand-rolled option walkers, eight `int()` leaks, three "am I at word start" predicates) are not local bugs; they are independently re-implemented semantic rules that drifted. The remedy per cluster is: **rule → one owner (`file.py#symbol`) → every consumer migrated → superseded copies deleted → executable guard with a synthetic offender**.

Not in scope: bash feature parity for absent features (`coproc`, `$(<f)`, `${ cmd; }` funsub, `BASH_SOURCE`), cosmetic rewrites, and the resumable lexer/parser (successor campaign, see Park register).

## 2. Campaign outcome

The campaign succeeds when:

1. The local gate is green against bash 5.3.15 with the oracle version recorded in `gate_attestation.json`, and a drift guard fails loudly when the resolved oracle differs from the attested baseline (Wave 0).
2. Every `live` / `oracle_changed` defect and perf row in the canonical inventory is closed by a wave, or sits in the Park register with a written ruling and successor owner (Wave 0 ruling; no post-launch deferrals).
3. Every closed cluster has: one owner symbol holding the rule, a consumer census with the superseded copies deleted, and a guard (ratchet / drift-lock / structural invariant) that was run against a synthetic offender in the shipping slot.
4. Externally observable behavior is differential-pinned to bash 5.3.15 on macOS and to the same version on the Linux nightly (§ Wave 0, oracle pin); version-sensitive rows are classified, not silently assumed.
5. A clean checkout of the final commit contains the ledger, the cluster→owner→guard map, probe evidence, benchmark deltas, and a close report whose headline agrees with its tables.
6. Nothing labelled `partial`, `carried`, `watch`, `TBD` counts as closed.

## 3. Standing rules (deltas only — sequence-doc rules 1–10 and integrator plan A1–A12 stay in force by reference)

- **SR-1 Oracle.** Replaces A12: the differential contract is "bash **5.3.15**, exact version recorded per host in `gate_attestation.json` (`oracle.version`) and printed in the pytest session header". Any host whose resolved oracle differs from the attested baseline fails `tests/unit/tooling/test_bash_oracle_resolution.py::test_resolved_oracle_matches_attested_baseline` with a triage instruction. Retuning to a new bash is a Wave-0-shaped slot, never an in-slot edit.
- **SR-2 Root-cause slot shape.** Every slot brief names (a) the owner `file.py#symbol` that holds the rule, (b) the consumers to migrate, (c) the copies to delete, (d) the guard and its synthetic offender. Verifiers reject a slot whose diff leaves a second implementation of the rule alive.
- **SR-3 Mode-varied pins.** Every behavioral pin is exercised in `-c`, script-file and stdin modes (lesson C007/C040: failure shape differs by input mode). Interactive facts get a PTY leg; combinator facts are verified through the direct combinator API (C178: under `--parser combinator` the RD trial parse hides over-acceptance).
- **SR-4 Version-sensitive rows.** A row whose expectation depends on the bash version carries a classifier — `bash_min: "5.3"` in `tests/behavioral/golden_cases.yaml` (runner skips with reason on an older oracle) or `@requires_bash("5.3")` in conformance — and the module docstring names the CHANGES entry. Exactly the Wave 0 retuned rows are classified; nothing else.
- **SR-5 Never reassign `HOME` in-script before expanding `~` in a conformance row** — the Homebrew 5.3.15 bottle links installed readline and resolves `~` from the startup environment (oracle-binary artifact, not psh semantics). Supply `HOME` via `env=`.
- **SR-6 Gate runs unsandboxed** (seatbelt denies `ps`, AF_UNIX bind, `/dev/stdout` by path). Sandbox-sensitive tests carry a skip-with-reason guard so a sandboxed run reports SKIP, never FAIL.
- **SR-7 compare-bash invocation** is A6's pytest form only: `python -m pytest tests/behavioral --compare-bash -n auto -q`.
- **SR-8 Comments** state the invariant and the reproducing command; campaign IDs ≤1 per file (CLAUDE.md no-sketch rule applied to source comments; C087/C133/C188/C224). Drift-lock any irreplaceable sketch in `test_doc_snippets.py`.

## 4. Status and dependency order

| Order | Wave | Charter | Depends on | Slots (est.) |
|---:|---|---|---|---:|
| 0 | Oracle baseline + evidence bootstrap | Green gate on 5.3.15; oracle recorded; ledger; rulings; park register | — | 4 (2–3 releases) |
| 1 | Lexer word-boundary and extent authority | One word-start predicate, one `((`/`${` extent authority, one escape decoder | 0 | 4 |
| 2 | Parser grammar parity | One brace-body/loop rule, one array-initializer rule, one command-head analysis, one diagnostic vocabulary, RD↔combinator corpus parity | 1 | 5 |
| 3 | Variable-write authority | One scalar→array promotion rule, one lookup truth, one allexport decision, one PATH-cache invalidation policy | 2 | 3 |
| 4 | Executor frame and redirect ownership | One-shot pipeline-member flag, plan-once redirects, procsub lifetime, job text, one error-prefix route | 3 | 5 |
| 5 | Builtin contracts | One option walker, one `legal_number`, one usage shape, one cd destination rule | 4 | 3 |
| 6 | Expansion field semantics | One field-vector for `*`/`[*]`/`!x`, one `IFS_WHITESPACE`, one pattern-word expander | 5 | 2 |
| 7 | Surfaces: scripting/invocation (7A), interactive (7B), analysis visitors (7C) | One line map, one option grammar, one completion context, one keybinding table, executable round-trip contract | 6 | 7 |
| R | Whole-tree checkpoint | Attack rounds to zero; re-scope Wave 8 | 7 | report |
| 8 | Textbook and measured perf | D2 coordinators, D3 comment history, D4 demonstrated costs | R | 3 |
| C | Closure ceremony | One final tree; all discriminators + guards + flip-pins re-run | 8 | — |

Wave N+1 does not merge until Wave N's exit criteria hold. Within a wave, slots ride the merge train one at a time (integrator plan §3 roles: dev in isolated worktree, adversarial verifiers, integrator owns version/changelog/ceremony).

---

## Wave 0 — Oracle baseline (bash 5.3.15) and evidence bootstrap

### Owned findings
- C242 Local gate red at 6459f1a6 (52 failures = oracle drift + ENV) · C241 oracle comments target 5.2 · C243 docs/reviews index test fails on untracked r23 report · C238 stale "latest/active" index claims · C169 junk files `f`, `f1`, `f2` · C181 `-c` + `set -m` job notice (oracle_changed: bash 5.3 dropped the -c eager reap) · C245 no fast pre-merge smoke check · C224 (theme) index/doc hygiene entry point.
- The 51-node GATE TRIAGE (FORMAT/SEMANTIC/PREMISE/ENV), retuned per its proposals.
- Rulings on every Park-register row (§ Park register) — the A7 lesson: rule before implementation begins.

### Architecture target
One recorded oracle identity flows from `tests/harness/shell_oracle.py#resolve_bash()` (already records the version) into the pytest session header, `run_tests.py#build_attestation` (`oracle: {path, version}`), `tools/verify_gate_attestation.py`, and the nightly. Version drift is a test failure, not a discovery three weeks later.

### Required work
**0.1 Evidence + index + housekeeping (docs-only release or first commit of 0.2).**
- Commit `ground_up_reappraisal_23_…md`, this program, and the canonical inventory as `docs/reviews/evidence/rootcause_2026-09/INVENTORY.json` (245 rows, status column frozen at 2026-09-06). Create `LEDGER.md` (cid → wave → owner symbol → guard → status), `FLIP-PINS.md`, `wave-manifest.json` (same shape as `evidence/boundary_remediation_2026-07/wave-manifest.json`). Index rows in `docs/reviews/README.md` (coordinate with the parallel session's uncommitted README edit; one-row conflict). Fix stale "active/latest" claims (C238).
- Delete `f`, `f1`, `f2` after confirming they are probe debris (C169).
- Import the 2026-09-06 re-verification transcripts from `tmp/program-2026-09/` into `evidence/rootcause_2026-09/wave0-base-probes/` (durable home) — no re-derivation.

**0.2 Oracle plumbing (psh tooling change; release).**
- `run_tests.py#build_attestation`: add `oracle: {"path": ..., "version": "5.3.15(1)-release"}` from `resolve_bash()`; `tools/verify_gate_attestation.py` requires the field; `tests/unit/tooling/test_gate_attestation.py` pins the shape.
- `tests/harness/shell_oracle.py`: add `ORACLE_BASELINE = "5.3.15"` (single constant) and `oracle_at_least("5.3")`; `tests/conftest.py` prints `oracle: <path> <version>` in the session header; `run_tests.py` echoes it in the phase banner.
- Drift guard: `tests/unit/tooling/test_bash_oracle_resolution.py::test_resolved_oracle_matches_attested_baseline` — fails when `resolve_bash().version` ≠ `ORACLE_BASELINE` with the message "oracle drift — run the Wave-0-shaped retune, do not edit pins in place". Mutation check: monkeypatched version string trips it.
- Version classifiers (SR-4): `bash_min:` key in `golden_cases.yaml` honored by `tests/behavioral/test_golden_behavior.py` (skip with reason when the resolved oracle is older); `@pytest.mark.requires_bash("5.3")` in `tests/conformance/conformance_framework.py`. Applied to exactly the rows retuned in 0.3/0.4.
- **Nightly oracle (Linux, was 5.2.21 system bash): PIN.** `.github/workflows/nightly.yml` builds bash 5.3.15 from the GNU tarball (cache keyed on version + patch level) and exports `BASH_PATH` so both channels run the SAME oracle; the "Show bash version" step asserts 5.3.15. Classification (SR-4) is the secondary defence so a future host with an older bash reports SKIP with reason rather than a red family. `docs/testing_source_of_truth.md` records both.
- Smoke check (C245): `run_tests.py --smoke` (≤60 s: tooling guards + one conformance module + golden subset) documented in CLAUDE.md as the pre-commit convention; per-PR CI stays disabled by decision.

**0.3 Semantic retunes A — trap/exit/posix special-builtin family (psh follows bash 5.3; release).**
- `psh/builtins/signal_handling.py#TrapBuiltin.synopsis` → `trap [-Plp] [[action] signal_spec ...]`; implement `-P` (flags `lpP`; `-P` no operand → "requires at least one signal name" rc 2; `-p`+`-P` → "cannot specify both" rc 2; `-Pl` listing wins; prints bare action per operand). Update `tests/unit/builtins/test_trap_flags.py:73`, `test_error_location_prefix.py:39`, user guide `04_builtin_commands.md:1107`; `test_builtin_help_sync.py` must stay green WITHOUT an allowlist entry.
- `psh/core/internal_errors.py#special_builtin_usage_discard`: `-c` → `SystemExit(1)` (unchanged), script/stdin → next-line `$?=2` (`TopLevelAbort(2, errexit_immune=True)`); serves exit/shift/return/break/continue. `psh/builtins/navigation.py:103` cd too-many-args → rc 2. Retune `test_exit_cd_options_conformance.py` (rc=1→2 rows), docstrings, `core.py:59` comment. Re-probe `exit abc; echo rc=$?` on 5.3 (continues, rc=2) and retune golden `bcontract_exit_bad_first_operand_exits_two` with `bash_min: "5.3"`.
- Trap entry status (POSIX interp 1602, bash 5.3 NEWS uu): `psh/core/trap_manager.py` records `(saved_exit_code, len(function_stack), source_depth)` for EXIT, signal and ERR traps; `psh/builtins/core.py` exit applies it at trap top level (relative depth) — DEBUG keeps current `$?`, EXIT stays unconditional. Rename `test_bare_exit_in_a_signal_trap_still_uses_current_status` → `…_uses_entry_status`; CELLS row `disc-signal-trap-uses-current-status` → `…-entry-status`; add the six boundary rows from the triage (function body → current `$?` rc 1; `eval`/`if`/`{ }` → entry; ERR → rc 1; sourced file → rc 1). Rewrite `psh/core/CLAUDE.md:744-757`.
- POSIX special-builtin identifier exits (bash 5.3 CHANGES jj/nnnnn/bbbbbb): `psh/builtins/environment.py` ExportBuiltin and UnsetBuiltin, `function_support.py` readonly path raise `SpecialBuiltinUsageError(1, suppressible=True)` at the FIRST bad operand when invoked as the special builtin (not via `command`/`builtin`, not `-f` operands). Remove the eval/dot `special_exit_floor` raise in `psh/scripting/source_processor.py` so an outer guard suppresses across `eval`/`.` (probe the trap-action nested run first). Posix function names unrestricted (`psh/executor/function.py` posix `is_valid_name` rejection deleted; `export -f é`/`readonly -f é` succeed). Move the three `…_survives` conformance rows to `TestPosixSpecialBuiltinExit`, flip `tests/integration/test_posix_special_builtin_exit.py` SURVIVING→EXITING rows, golden `posixexit_*` rows (`bash_min: "5.3"`), matrix doc rows 48/49/51, split `test_identifier_policy_conformance.py` loops, user guide §17 identifier prose (function-name sentence narrowed to variables).

**0.4 Semantic retunes B — jobs/PATH/hash/attributes/format/ENV (release).**
- `psh/executor/job_control.py:279/280/683` status field width 24→27; delete the `command_mode` DONE filter at `psh/builtins/job_control.py:96-98` (bash 5.3 CHANGES d./bbbb — closes C181); rename the two `…suppressed_c_mode` tests; CHANGELOG note.
- Signal-death diagnostics: S path now — pins assert `bash.stderr == strsignal(SIGTERM).ljust(27) + <job text>` and psh's bare form as a DECLARED divergence with a `FLIP-PINS.md` row that Wave 4 slot 4.4 (C065 job text) flips to parity. Reword `job_control.py:626-628`.
- PATH truth (bash 5.3 CHANGES p.): `psh/executor/strategies.py#report_exec_failure` uses `state.scope_manager.lookup('PATH').is_set` (`unset_path`), not emptiness; rewrite `format_exec_failure` docstring; rename the two tests; add the `local PATH=` row.
- `psh/builtins/hash_builtin.py:80-83` delete the empty-table short-circuit (CHANGES ggggg); invert `test_dash_d_on_empty_table_silently_succeeds`.
- `psh/core/scope.py#ScopeManager.apply_attribute/remove_attribute`: refuse INTEGER/LOWERCASE/UPPERCASE/ARRAY/ASSOC_ARRAY/NAMEREF changes on a readonly target (`ReadonlyVariableError`; CHANGES llllll); EXPORT/TRACE/READONLY still allowed; `local -i x` on readonly local → rc 1. Invert `test_attrs_only_add_integer_allowed`. (Wave 3 slot 3.1 consolidates this into the attribute-transition rule.)
- `psh/builtins/shell_options.py#_print_option` width 15→20 for shopt-table prints, 15 only for `-o` listings; `set -o` untouched; retune `test_shopt.py:79`, `test_shopt_set_o.py` (six sites), golden rows 2378/8910.
- Closed fd 0: `psh/__main__.py` STDIN branch — `sys.stdin is None` → `psh: error creating buffered stream: Bad file descriptor`, exit 126; retune both `TestClosedFd0Startup` tests.
- `test_bad_substitution_conformance.py`: drop `${ }` / `${ :-x}` from BAD_CASES; add the funsub declared-divergence pin (Park P-6). `test_subscript_keying_conformance.py`: `case` render tuple, `test_divergence_sq_in_dq_readback_outcome` → parity pin (bash 5.3 expand-once; record in `FLIP-PINS.md:47`), `let_arith` row expectation, tilde row via `env={'HOME': '/probe-home'}` (SR-5). `test_invalid_regex_diagnostic_is_psh_only` → both diagnose, wording differs (LEDGER D-3.5-s5).
- ENV guards (SR-6): `pytest.skip` when `ps -o stat=` returns nothing (`test_bg_actually_resumes…`), when AF_UNIX bind raises `PermissionError` (`test_socket_earlier…`), when `ps -eo pid=,ppid=` cannot spawn (`test_cap_kill_reaches…`); golden `r18t2_builtins_history_write_to_stdout` gains `requires_dev_fd: true`.
- Register the Wave-0-discovered rows in the ledger with owners: **W0-N1** `read` with closed fd 0 → `AttributeError` at `psh/builtins/input_reader.py:429` (→ Wave 5 slot 5.1); **W0-N2** foreground external command consumes a job number (`JobManager.create_job`; → Wave 4 slot 4.4); **W0-N3** `[[ x =~ a{1 ]]` psh silent rc 1 vs bash "braces not balanced" rc 2 (→ Wave 6 slot 6.2); **W0-N4** `unset -f` readonly-function wording (→ 5.1); **W0-N5** `unset PATH; type cmd` prints `./cmd` vs absolute (→ Wave 3 slot 3.3); **W0-N6** `declare -c` rejected as invalid option (→ 5.1 rider).
- Three seeded standard gates at the Wave 0 final tree (identical phase censuses), `python -m pytest tests/conformance -q`, compare-bash (SR-7), `run_tests.py --benchmarks`, ruff, mypy, complexity counters — the regression baseline for every later wave.

### Exit criteria
- Gate green (0 failed) against 5.3.15; `gate_attestation.json` carries `oracle.version = 5.3.15…`; drift guard trips under a mutated version string.
- Nightly run at the Wave 0 tree shows `bash --version` = 5.3.15 and is green (or its residual is a written Linux-watch ledger row).
- Every canonical row has a ledger disposition (wave / park / excluded: C114, C163 not_reproducible; C208 fixed); no TBD.
- Every retuned row cites its bash 5.3 CHANGES/NEWS entry or a probe transcript and carries SR-4 classification.

---

## Wave 1 — Lexer word-boundary and extent authority

### Owned findings
- **1.1 word-start authority:** C004 `is_comment_start` keyed on preceding char · C005 fd-prefix mid-word · C006 `>&` backtracks into previous token · C011 `!` delimiter set includes `{}[]` · C170 fd digit run > INT_MAX taken as fd · C164 bare `]]` lexed as a word · C046 no-progress `RuntimeError` CLI-reachable (registered carry).
- **1.2 extent authority:** C002 `((` without `))` lookahead · C003 arithmetic_depth cascade hardening · C007 `$((` scan quote-blind · C047 two `${…}` scanners disagree · C009 cmdsub `)` header drops command position · C014 heredoc spec ids matched positionally (latent) · C221 (theme).
- **1.3 escape decoder:** C008 `\u`/`\U` unguarded `chr()` · C013 octal/hex byte model + user guide §8.4 over-claim · C191 NUL retained in `$'…'` (+ read/mapfile face) · C100 three duplicated digit loops · C220 (theme, lexer face).
- **1.4 lexer perf and dead weight:** C050 quadratic literal collection · C048 unmatched-`[` O(n²) lookahead · C103 per-token `dataclasses.replace` · C012 heredoc re-lex O(N²) (cheap variant only; full fix = Park P-1) · C045 dead `WordShapeTracker` props · C104 `WORD_TERMINATORS` vs override · C105 dead config · C102 registry exception widening · C101 duplicated bracket matcher · C106 lexer CLAUDE.md drift · C049 `((…))` interior invariant (doc) · C168 CRLF divergence doc · C232 (design).

### Architecture target
The main lexer and the `$(…)` scanner share one model of "where am I": `psh/lexer/state_context.py#LexicalState.at_word_start` (true iff the current collect value is empty and the previous char is blank/newline/metachar) and `psh/lexer/command_position.py`'s single transition function. Extent decisions for `((…))` and `${…}` have exactly one authority each. ANSI-C escapes decode through one function in `psh/utils/escapes.py`.

### Required work
- **1.1** Owner `LexicalState.at_word_start`. Consumers: `recognizers/comment.py#is_comment_start` (drop `_COMMENT_PRECEDING_OPS`; `#` is a comment iff at word start — `(cmd)#c` accepted, `a{#b` kept), `recognizers/operator.py` fd-prefix recognition (`isdigit()`/`{` only at word start; delete the :129-131 backtracking branch; digit run must fit int32 else it is word text — C170), the `!` veto (delimiter set = bash metacharacters `|&;()<>` + whitespace). `]]`/`}` at command position emit the reserved-word token so the parser reports bash's syntax error rc 2 (C164). C046: reproduce the registered no-progress input, root-cause it in the same recognizer family, convert the guard to a typed `LexerError`, and delete the false "ZERO inputs reach this point" census comment. Guard: tooling test `tests/unit/tooling/test_lexer_word_start_authority.py` — AST walk forbids any `text[pos-1]`/`prev_char in` predicate in `psh/lexer/recognizers/` outside the owner (synthetic offender file under `oracle_spawn_fixtures/`-style fixtures) + a differential property test: for a corpus, `#`/fd-prefix/`!` decisions of the main lexer equal the cmdsub scanner's.
- **1.2** Owner `psh/lexer/pure_helpers.py#scan_double_paren_arithmetic` (always quote-aware; `quote_aware` parameter DELETED; docstring at :152-154 corrected) and `#validate_brace_expansion` as sole `${` extent authority (`word_scanners.py#skip_expansion_region` delegates; `find_closing_delimiter` no longer callable with `{`). `recognizers/operator.py` accepts `((` only when the same lookahead finds `))`, else emits `LPAREN`. `state_context.py#advance_lexical_state` clamps `arithmetic_depth` to 0 on NEWLINE/SEMICOLON and resets the fuse counter (C003). `cmdsub_scanner.py:570` calls the shared command-position transition (C009); heredoc specs carry the operator token offset and match by offset (C014). Guard: ratchet forbidding `find_closing_delimiter(` with `'{'` and any second `))`-search loop in `psh/lexer/`; the corpus differential from 1.1 extended with `$(…)`-bodies-vs-top-level command-position equality; mode-varied pins for every C002/C007 repro; extend `tests/conformance/bash/test_cmdsub_case_conformance.py`.
- **1.3** Owner `psh/utils/escapes.py#decode_ansi_c_escapes` (one digit-reader helper; `\u`/`\U`/`\x` through `unicode_escape_char`); `pure_helpers.handle_ansi_c_escape` becomes a call to it (or is deleted). Byte-model RULING (recorded in Wave 0 ledger, default): `\NNN`/`\xHH` ≥ 0x80 emit the surrogateescape byte `chr(0xDC00+b)` so `$'\303\251'` prints bytes identical to bash; if the verifier's byte round-trip matrix (`${#x}`, `printf %s | od`, `[[ == ]]`) shows the character model cannot carry it, the fallback is a qualified user-guide §8.4 note + §17 row — either way §8.4's unqualified "matching bash" is corrected. NUL rule (one statement, two decode boundaries): "a NUL never enters a variable value" — dropped in `decode_ansi_c_escapes` and at `psh/builtins/input_reader.py`'s byte→str boundary (read/mapfile face, 4B.2 residual); probe command substitution too. Guard: ratchet forbidding `chr(int(` in `psh/lexer/` and `psh/utils/` outside the owner; cross-entry NUL matrix (`$'\0'`, `read`, `mapfile`, `$(printf '\0')`).
- **1.4** `recognizers/literal.py:190` accumulate segments, join once (shape facts tracked separately); `word_scanners.py:446` cursor indexing + line-end bound; recognizers return lightweight tuples and `modular_lexer.py#emit_token` builds the frozen `Token` once; `heredoc_lexer.py:207-222` skip re-lex while the failure is `UnclosedQuoteError` (accumulate until the quote closes) — the retry-from-seed-state variant is Park P-1. Delete `WordShape`, `in_assignment_value`, `concat_safe` + four feeding fields; rename `WORD_TERMINATORS` → `WORD_START_REJECTS`; delete `allows_newlines`, `QUOTE_RULES['`']`, `SourceMap.line_starts`; `registry.py:78-85` carve-out widened to `(RecursionError, PshError, SyntaxError)`. Guards: scaling pins ≤2.3×/doubling for one long word, one line of n unmatched `[`, and a one-logical-command heredoc source in `test_heredoc_scaling.py`; per-token `replace()` count assertion (0 per recognizer token); benchmark delta vs Wave 0 baseline.

### Exit criteria
- Every C002/C004/C005/C006/C007/C009/C011/C047/C164/C170 repro matches bash 5.3.15 in all three modes; C046's input yields a typed error, rc 2.
- `grep -c "quote_aware" psh/lexer` = 0; exactly one `${` extent authority and one `((` lookahead remain (guard offender red, tree green).
- `$'\ud800'` no longer raises; byte-model ruling pinned both ways; user guide §8.4/§17 corrected.
- Perf pins hold; lexing benchmark ≥ baseline.

---

## Wave 2 — Parser grammar parity (RD + combinator)

### Owned findings
- **2.1 RD word-list loops and headers:** C015 `{ }` body for `for`/`select` · C017 newline before loop variable · C052 `for ( (` adjacency · C010 alias-corrupted loop variable · C054 duplicated for/select tail · C110 duplicated brace-body rule · C107 dead `!` branch.
- **2.2 array-initializer recognition + command-head analysis:** C016 `name=(…)` accepted for any head · C018 `a[0]=(1 2)` rejected at parse time · C166 `a=(1 2)x` · C053/C173 dead WORD-shaped fd-dup path (both parsers).
- **2.3 diagnostics and coordinates:** C111 two vocabularies · C061 combinator f-string messages · C118 combinator error path leaks token index · C055 three `ParseError` routes · C051 nested-cmdsub coordinate mix · C062 combinator stamps no `.line` · C059 no depth guard in combinator · C108/C109/C112/C113/C115 doc/defensive-access riders.
- **2.4 combinator parity:** C019 exponential retry · C020 trailing redirects on `[[ ]]`/`(( ))` dropped · C021 bare procsub at command position · C056 `time -p !` · C057 four drifted `WORD_LIKE` sets · C058 over-acceptance family · C060 `[[` operator whitelist · C121 parsers built inside closures · C119/C123 inert algebra/guide drift · C178 framing (→ SR-3) · C233 (design: keep both, retain differential).
- **2.5 debug renderers:** C116 dot drops scalars · C117 DOT escaping · C122 sexp indentation · C177 sexp quotes · C176 dead branch.

### Architecture target
Grammar rules exist once: `_parse_brace_body`, `_parse_word_list_loop(keyword, node_cls)`, `ArrayParser._candidate_initializer` (the only place that decides "this `(` opens an initializer"), `psh/ast_nodes/command_head.py#CommandHead.of(node)` (the only static "what command is this" analysis — reused by Wave 7C's visitors), `recursive_descent/helpers.py#unexpected_token_message` (the only bash-style message builder), one `MAX_NESTING_DEPTH`, one `TokenGroups.WORD_LIKE`. RD and combinator agree on a committed corpus.

### Required work
- **2.1** Owner `parsers/control_structures.py#_parse_word_list_loop` (mirrors `_parse_loop_structure`); body via `commands.py#_parse_brace_body` (shared with `parse_brace_group` and C-style for); no `skip_newlines()` between keyword and name; second `LPAREN` must be `adjacent_to_previous` and the close must balance. `ForLoop.variable` = token `.value` (source slice only for the caret; `session.py#token_lexeme` verifies slice==token). Pins: `for x in 1 2; { echo $x; }`, `select` twin, alias-headed `for`, `for\nx`, `for ( (…` in all three modes.
- **2.2** Owner `parsers/arrays.py#_candidate_initializer`: initializer iff `name=`/`name[sub]=`/`+=` head, adjacent `(`, balanced `)`, and the `)` is followed by a word terminator — otherwise the whole thing is a literal scalar word (C166); `a[0]=(…)` parses to `ArrayInitialization(subscript=…)` and the executor emits "cannot assign list to array member" rc 1 (C018). `commands.py#_check_array_initialization` consults `CommandHead.of(command)` and the frozen head list re-probed on 5.3.15 (`declare typeset local export readonly alias eval let`); others get bash's rc 2 syntax error (C016). Delete `parse_fd_dup_word`/`_is_fd_duplication` and the combinator twin after a counter-instrumented suite run. Guard: ratchet forbidding `.args[0]`/`.words[0]` head inspection in `psh/parser/` and `psh/visitor/` outside `CommandHead` (offender test).
- **2.3** `ctx.consume()` default message and both combinator sites route through `unexpected_token_message`; one `make_error_context` on the context class; Context line joined from a filtered list (no doubled space). `support/nested_parse.py#parse_nested_command` receives the enclosing source + absolute body start so nested errors report file (line, column) and the real source line; `psh/parser/CLAUDE.md` invariant stays true. Combinator `build_statement_list` stamps `.line` and checks `MAX_NESTING_DEPTH` (imported, not re-declared). Guard: ratchet forbidding `f"…unexpected token…"`/`"Expected "` literals outside helpers; parse-error wording/caret parity rows for the closed set in C111 across modes.
- **2.4** Delete `pipelines.py:170-173` fallback; packrat memo keyed `(id(parser), pos)` with a counter pin (linear in nesting). Combinator compound productions consume trailing redirects through one `_parse_trailing_redirects` (C020) — guard: every AST class with a `redirects` field has a combinator production that consumes them (matrix test, RD↔combinator AST equality). Remove procsub from `special_command`; `time -p` re-runs keyword normalization; all word-like sets derive from `TokenGroups.WORD_LIKE` (ratchet forbids local `frozenset({TokenType.WORD, …})` in `psh/parser/combinators/`); `many1(separators)`, emptiness checks, `[[` operator table imported from the one table the RD/test evaluator uses (C060); memoize terminator-keyed parsers (C121); `.then/.map` either adopted at three productions or deleted with the guide corrected (C119/C123). Per SR-3 all combinator pins go through the direct API; add a committed RD↔combinator corpus (golden commands) parity test.
- **2.5** `dot_generator.py` terminal else arm for scalars; DOT escaping (`\\`, `\"`) not `html.escape`; `sexp_renderer.py` thread indent and escape string atoms; delete the dead `elif`.

### Exit criteria
- All Wave 2 repro rows match bash 5.3.15 in all modes (RD) and via the direct API (combinator); RD/combinator AST-equal on the corpus.
- One brace-body rule, one loop-tail rule, one initializer rule, one head analysis, one message builder, one `WORD_LIKE` (each guard's offender red).
- Combinator nesting cost linear (counter pin); no `RecursionError` escapes below `MAX_NESTING_DEPTH`.

---

## Wave 3 — Variable-write authority (core)

### Owned findings
- **3.1 conversion and attribute transitions:** C093 arithmetic promotion discards scalar · C094 explicit index high-water mark · C095 integer-array attribute phase · C096 assoc initializer empty keys/mixed forms · C090 mapfile consumes input before rejecting destination / attribute corruption · C136 `declare -p` prints `=()` for never-assigned array · C073 half of every write in `enum.Flag` arithmetic · C194 array alias-mutation write-ban gap · C226 (design D1) · C132 VariableStore façade (as far as this wave's rule requires).
- **3.2 lookup truth:** C027 `set -u` consults `state.env` · C072 `${!prefix*}` env union lists opaque entries · C070 temp-env over eval/source invisible to enumeration · C071 `export -n` through nameref no-op · C130 readonly diagnostic names target not reference · C195 `SHLVL` never set · W0-N5 `type` under unset PATH.
- **3.3 allexport and PATH-cache invalidation:** C028 `set -a` misses declaration builtins · C044 function return leaves resolution on the local PATH.

### Architecture target
Every value transition has one owner in `psh/core/variable_store.py`/`psh/core/scope.py`; callers (executor array builders, arithmetic, declare/local, mapfile, read -a, nameref writes, scope exit) invoke the rule, never re-derive it. Lookup truth is `ScopeManager.lookup()` — nothing consults `state.env` for set-ness. "Effective binding of PATH changed" is one event fired from every path that changes it.

### Required work
- **3.1** Owner `VariableStore.promote_to_indexed(name)` (scalar→array: existing value becomes element 0 — preserving set/unset distinction, empty value, attributes, nameref target) used by `set_element` (arithmetic), `psh/executor/array.py` builders, `declare -a`, `mapfile`, `read -a`. `psh/executor/array.py#ArrayBuilder` restructured into named phases: expand → validate keys (assoc: no empty key, one initializer form, bash 5.3 order/partial-state per probe) → commit through the store with an `IndexedInitializerCursor` (append start separate from explicit-index cursor; negatives resolved first; integer attribute applied at commit via the same integer-assignment rule scalars use). Attribute transitions (incl. Wave 0's readonly refusal) live in `ScopeManager.apply_attribute`; mapfile resolves the nameref destination and validates writability/indexed compatibility BEFORE reading (fd position and prior contents asserted). Bare `declare -a/-A` cell carries `VarAttributes.UNSET` until first assignment so `declare -p` omits `=()`. `VarAttributes.is_*` rewritten against raw ints (public API unchanged; microbench pinned ≥1.6× write-path speedup). Guard: the D1 **cross-entry-point matrix** (`tests/unit/core/test_write_authority_matrix.py`: ordinary assignment × arithmetic × declare/local × nameref × read/mapfile × scope exit → asserts value, flags, effective lookup, `os.environ` of a child, executable dispatch) + extend `test_no_derived_variables_writes.py` so `VarAttributes.ARRAY` construction outside the store fails (offender).
- **3.2** `psh/core/options.py#check_unset_variable` asks `lookup(var).is_set`; `parameter_expansion.py:480` drops the env union; eval/source/`.` push a real `is_temp_env` scope (`push_temp_env_scope`), `scope.py:113-120` + `core/CLAUDE.md` "exactly like bash" corrected; `_remove_export` resolves the nameref first (sweep the ~30 `get_variable_object` pre-checks and route each through the store); `set_element`/`unset_element` raise with the pre-resolution name; `SHLVL` seeded/incremented in `ShellState.__init__` identity phase. Guard: ratchet forbidding `state.env` reads in `psh/core/options.py`, `psh/expansion/`, `psh/builtins/environment.py` for set-ness (offender); conformance rows for `set -u` shadowed export, `${!p*}` with `env 'bad-name=x'`, `FOO=1 eval 'set'`, nameref `export -n`.
- **3.3** Owner `ScopeManager.set_variable`/`create_local` OR in `EXPORT` when `options['allexport']` (not dynamic specials, not arrays) — the declaration builtins inherit it because they write through the store; delete the `state.py:1047` sole consumer. Owner for PATH: `ScopeManager._effective_binding_changed(name)` (rename of `_notify_path_changed`) fired from set/unset/`local`/`pop_scope`/temp-env push+pop whenever the EFFECTIVE binding of PATH changes; `CommandHashTable` is the single subscriber. Guard: fault-injection counter test — every write path that can change PATH's effective binding (incl. early `return`, failing body, `local PATH` then pop, temp env) fires exactly one observer call and the next dispatch resolves through the restored PATH (actual `execve` target asserted, not the string). Conformance: allexport across all five spellings (user guide §17 rows 957/961 corrected from over-claiming "Full support" — map the proving tests in `CLAIM_TESTS`).

### Exit criteria
- Matrix test green; each of C093–C096/C090/C136 pinned by an execution-visible assertion (values, `declare -p`, fd position).
- `grep -n "state.env" psh/core/options.py psh/expansion/parameter_expansion.py` = 0 for set-ness.
- C044 probe: `f(){ local PATH=/x; }; f; ls` dispatches `/bin/ls`; observer counter = 1 per binding change.
- User guide §17 `set -u` / `set -a` rows carry proving conformance tests.

---

## Wave 4 — Executor frame and redirect ownership (silent-data-loss family T4)

### Owned findings
- **4.1 frame flags and statuses:** C001 function/eval/source as pipeline member drops commands (P0) · C040 `set -n` inert mid-`-c` · C041 bare cmdsub does not set `$?` · C063 posix `VAR=v exec` persistence · C064 `select` empty line · C183 PIPESTATUS collapse in brace groups · C184 pipeline member EXIT trap · C179/C125 executor comment drift + dead `setpgid`.
- **4.2 redirect ownership:** C031 fd≥3 targets expanded twice (plan-once) · C032 `1>&-` then reopen EBADF · C079 dup2 error name · C080 fd ≥ 2³¹ `OverflowError` · C206 `exec {v}>&-` with v unset · C207 `n<&m-` move-form lifetime · C142 context-manager rider.
- **4.3 process-substitution lifetime:** C081 `>(cmd)` FIFO on every platform · C082 5 s SIGALRM give-up · C091 fork-fail resource leak · C182 bare `wait` misses procsub children · C192 Linux oracle for locale (nightly watch) · C081 doc facets.
- **4.4 jobs and signals:** C022 async `/dev/null` stdin inside pipeline/redirected compound · C065 compound jobs recorded as placeholder text · C067 `wait` EINTR → 128+N · C124 signal-death notice in subshell subtree · C126/C127 pipeline rollback/empty-status · C180 nested `( )` in fg pipeline takes the tty · W0-N2 job number consumed by foreground command · the Wave 0 signal-death FLIP-PIN (bash 5.3 padded job text).
- **4.5 error-prefix route:** C066 fifteen executor sites · C069 three expansion sites · C219 (theme) · C139 `test -v` hand-inlined prefix · C205 `environment:` FUNCNEST prefix (by-design, kept and pinned).

### Architecture target
`in_pipeline` is consumed exactly once, at the pipeline member's own dispatch (`ExecutionContext.for_pipeline_member()`), so no inherited frame can observe it. Redirect plans are resolved once per `RedirectOp` and applied; stream halves follow fd numbers. Every acquired procsub resource has an owner from acquisition to release. Job command text is derived from source extents. Every non-interactive diagnostic in `psh/executor`, `psh/expansion`, `psh/builtins` goes through `ShellState.error_location_prefix()` / `Builtin.report_error`.

### Required work
- **4.1** Owner `psh/executor/context.py#ExecutionContext.for_pipeline_member` — one-shot: `pipeline.py` consumes the flag when launching the member and hands the body a context with `in_pipeline=False`; `strategies.py:605` exec-branch reads the one-shot token, not the inherited flag; delete the save/restore copies in `function.py`, `control_flow.py:91-92`, `subshell.py:82-83`. Guard: ratchet — `in_pipeline` referenced only in `context.py`, `pipeline.py` (offender). `noexec` checked per statement in `psh/executor/core.py#ExecutorVisitor` dispatch (source_processor keeps the per-unit fast path). Empty-words command: `command.py#_run_command` sets `$?` from the expansion result's `last_substitution_status`. exec-without-command routes assignments via `ExecutionResult.assignments_persist`; inert loop at `command.py:1102-1109` deleted. `select` `if reply == '': continue`. PIPESTATUS re-stamp removed from the single-command path inside groups; pipeline member runs its own EXIT trap (LEDGER successor rows discharged). Pins mode-varied; compare-bash rows for `f | cat` with 3 commands, `eval`/`source` twins, pipefail rc.
- **4.2** `manager.py#_builtin_redirect_fd_level` applies the already-resolved plan (`_clear_user_fds_from_parking` + `saved_fds_for_plan` + `apply_fd_plan`); guard: `planner.plan` call-count = 1 per `RedirectOp` (instrumented test) + cmdsub-side-effect counter rows. `_swap_closed_output_streams` installs `_RawFdStream` (fd-number-following) — docstring premise rewritten. One `psh/io_redirect/file_redirect.py#fd_from_text` (int32 range; `{v}` with unset/non-numeric v → "ambiguous redirect" rc 1; catches `OverflowError` as defence behind Wave 1's lexer rule). `RedirectPlan.target_fd` threaded into the OSError so bash's fd number is printed. Move-form closes the source permanently in the parent for per-command frames (C207). `builtin_redirections` as `@contextmanager`. Pins: brace/function/if/while × fd1/fd2 close-then-reopen; noclobber different-file row; `ulimit -n 64` dup2 rows.
- **4.3** `process_sub.py`: platform branch (FIFO only on Darwin; pipe + `/dev/fd/N` elsewhere — nightly verifies on Linux); replace the 5 s alarm with a blocking open or a non-zero exit (never silently `/dev/null`); every resource owned by an `ExitStack` from acquisition, transferred on success (fault injection at pipe/flag/FIFO/fork/setup). Bare `wait` reaps procsub children. Root `CLAUDE.md` item 5 wording and `io_redirect/CLAUDE.md` corrected.
- **4.4** `AsyncJobPolicy.apply` gains "is fd 0 the shell's original stdin" from the stream bindings and suppresses the POSIX `/dev/null` when fd 0 came from a pipe/compound redirect. Owner `psh/executor/job_control.py#job_command_text(node, source)` from AST source extents (as `set -x` headers already do) — used by `jobs`, `%?str`, and `report_signal_death_at` (flips the Wave 0 FLIP-PIN to bash 5.3 parity: `strsignal.ljust(27) + text`, `( … )` for subshells). Trap dispatcher records "handler fired" → `wait` returns 128+N on the next EINTR (macOS 158 / Linux 138 — nightly row). Signal-death suppression is a property of the forked-subshell subtree. `except BaseException` rollback + explicit empty-status branch in `pipeline.py`. `JobManager` does not hand terminal control to a nested subshell's own pgid (PTY-verified per §3 realistic-terminal rule). `JobManager.create_job` does not burn a job number for foreground commands.
- **4.5** Owner `ShellState.error_location_prefix()` / `Builtin.report_error`. Migrate all 18 sites + `test_command.py:59-61`. Guard: `tests/unit/tooling/test_error_prefix_ratchet.py` — AST walk forbids `"psh: "` string literals written to stderr in `psh/executor/`, `psh/expansion/`, `psh/builtins/` (allowlist frozen to the deliberate `environment:` FUNCNEST prefix, C205); synthetic offender. Conformance rows for the five probed diagnostics in script mode (prefix byte-identical to bash).

### Exit criteria
- C001: `f(){ echo a; /bin/echo b; echo c; }; f | cat` prints a b c in all modes and via eval/source; pipefail rc correct.
- `planner.plan` count = 1 per op under the instrumented test; C032 rows byte-identical to bash for fd 1 and fd 2.
- Fault injection at every procsub acquisition point leaks no fd/FIFO/child.
- `jobs` shows `( sleep 30 ) &` text; signal-death parity pin flipped; error-prefix ratchet offender red, tree green with allowlist = {FUNCNEST}.

---

## Wave 5 — Builtin contracts

### Owned findings
- **5.1 one option walker, one number parser, one usage shape:** C030 `int()` leaks in 8 builtins (umask/ulimit apply wrong values) · C098 `read -t inf` / huge `-u` `OverflowError` · C029 printf hand-rolled options · C076 seven builtins reject no invalid options · C134 six declaration-family parsers print the message backwards / drop usage · C135 builtins CLAUDE.md inventory + promised drift-lock · C200 usage strings differ from bash · C141 `_evaluate_binary` six-fold try/except (where `_to_int64` lands) · C089 printf `%` conversion after flag/width · C075 `source` no filename rc 2 · C077 `kill -n` · C078 `wait` bad id rc 1 · W0-N1 `read` with closed fd 0 · W0-N4 `unset -f` readonly wording · W0-N6 `declare -c` · C201/C202/C203 riders (`_declare_bare_name` decomposition, stringly-typed option dicts, documented divergences stay documented) · C234 (design).
- **5.2 cd destination rule:** C043 logical cd enters a different directory than it reports (P1) · C225 empty CDPATH component echoes destination · C074 empty `HOME`/`OLDPWD` treated as unset.
- **5.3 input streams:** C240 mapfile unbounded read · C140 duplicated stdin-source predicate · C137/C138 registry/`write_line` riders.

### Architecture target
`Builtin.parse_flags`/`parse_flags_ordered` is the only option walker (the declaration family's `+x` grammar and `set -o` are expressed as explicit ordered-flag forms of it, or listed on a frozen justified allowlist); `psh/builtins/numeric.py#legal_number` (base-10, sign, surrounding whitespace only, int64) and `legal_octal` are the only numeric operand parsers; `Builtin.usage()` renders bash's exact `name: usage: synopsis` shape from `synopsis`. `cd` computes one logical destination and derives the chdir operand from it.

### Required work
- **5.1** Owner `psh/builtins/numeric.py#legal_number` (+ `legal_fd`, `finite_timeout`) — routes: `test_command.py#_to_int64` (via the operator table), `positional.py:33`, `core.py:51`, `function_support.py:1012`, `system_builtins.py:50`, `limits.py:237` (base 8 for umask via `legal_octal`), `read_builtin.py` `-n/-N/-t/-u` (preflight rejects non-finite and unrepresentable fds; closed fd 0 → bash's `read: 0: read error: Bad file descriptor` rc 1 through the `InputCursor` boundary, not an `AttributeError`), `mapfile_builtin.py:193/204/216`. printf/times/eval/builtin/source → `parse_flags` (`-v` as `value_flags='v'`); pushd/popd/dirs emit `invalid number` rc 2; the six declaration-family parsers call `self.error(f"-{flag}: invalid option")` + `self.usage(...)`; `printf_formatter.py` removes `%` from `_CONVERSIONS` (bash message + status via `_FatalError`), false comment deleted; `source_command.py` usage + `SpecialBuiltinUsageError(2, suppressible=True)`; `kill -n`; `wait` `ValueError` arm → bash text rc 1; `unset -f` wording; `declare -c` accepted or explicitly declared. Usage strings aligned to bash 5.3 `help` first lines for the C200 sweep. Guards: extend `test_builtin_help_sync.py` with (c) "every builtin that scans `args` for a leading `-` without `parse_flags` is on an explicit justified allowlist" (the C135 drift-lock; offender); ratchet forbidding bare `int(`/`float(` on operands in `psh/builtins/` outside `numeric.py` (offender); conformance rows per builtin for `_`-digits, `0o`, `inf`, huge fd, `-X` invalid option (usage line byte-identical).
- **5.2** Owner `psh/builtins/navigation.py#resolve_cd_target(operand, mode)` returning `(logical_pwd, chdir_operand, via_cdpath_component)`: `-L` chdir's the logical path (never the physically-resolved one); `-P` keeps the physical path; print only when a NON-EMPTY CDPATH component resolved; `HOME`/`OLDPWD` tested `is None`, empty falls to the empty-operand no-op. Guard: tests assert file placement + `os.getcwd()` + `pwd -P` (not just `$PWD`) across relative/absolute `..`, symlinks, CDPATH; user guide `cd` rows checked.
- **5.3** mapfile processes records incrementally after 3.1's preflight; `input_reader.py#make_reader`'s stdin-source predicate exported and consumed by `ReadBuiltin`; `registry.get(...)`, `self.write_line`.

### Exit criteria
- All C030/C098 rows: umask/ulimit refuse (`invalid octal number`/`invalid number`), values unchanged; no Python exception under strict-errors.
- `test_builtin_help_sync.py` (c) allowlist ≤ the frozen justified set; help transcripts match bash 5.3 for the C200 sweep.
- C043: logical `cd` places files where `pwd` says, across the symlink matrix, in all modes.

---

## Wave 6 — Expansion field semantics

### Owned findings
- **6.1 field vectors and IFS:** C023 unquoted `$*`/`${a[*]}` join-then-split · C024 `"${!x}"` with `x=@` collapses · C068 `"${!arr[*]}"` joins with literal space · C026 IFS whitespace hard-coded thrice.
- **6.2 operands and pattern words:** C025 `\}` in DQ operand (+ `:=` store) · C042 tilde not expanded in `case` patterns · W0-N3 `[[ =~ ]]` regex compile diagnostics (bash 5.3 diagnoses `a{1`) · C128 quadratic value-operand builder · C129 arithmetic subscript re-render/re-parse rider · C188 changelog docstrings rider.

### Architecture target
`*`/`[*]`/indirect-`@` produce the element list unquoted and one `_ifs_star_separator()`-joined field quoted — from one projection point. `psh/expansion/word_splitter.py#IFS_WHITESPACE = ' \t\n\v\f\r'` is the only spelling. Pattern words (`case`, `[[ ==`, glob) go through one `expand_pattern_word` that applies tilde expansion identically.

### Required work
- **6.1** Owner `word_expander.py#_project_star_fields(parts, quoted)` (return list when unquoted; join with `_ifs_star_separator()` when quoted) used by `$*`, `${a[*]}`, `${!a[*]}` (arrays.py:88-108 — "historical behavior" sentence deleted), `${!prefix*}`; `fields.py:57` returns positionals for `target == '@'`. `IFS_WHITESPACE` consumed by `word_splitter`, `read_builtin.py:359`, `word_expander.py:580`. Guard: ratchet forbidding the literal `' \t\n'` and `' '.join(` on field lists in `psh/expansion/` and `psh/builtins/read_builtin.py` (offender); compare-bash matrix IFS ∈ {'', ':', 'x', default} × {`$*`, `${a[*]}`, `${!a[*]}`, `"${!x}"`} × quoted/unquoted.
- **6.2** `operands.py:466` escapable set gains `}`; owner `psh/expansion/pattern_words.py#expand_pattern_word` (tilde + quote-aware) used by `case` (control_flow), `[[`, `${var#pat}`; `enhanced_test_evaluator.py:195` reshapes the regex-compile diagnostic to bash's frame with `error_location_prefix` and returns rc 2 for unbalanced braces (W0-N3; reason text mapped best-effort); `operands.py:162` list accumulation (scaling pin ≤2.3×/doubling); `evaluator.py:69-72` calls `_resolve_plain_parameter`. Guard: conformance rows for `case ~/x`, `~+`, alternation; `${u:="\}"}` in `-c` and heredoc.

### Exit criteria
- Full IFS × form × quoting matrix identical to bash 5.3.15; one `IFS_WHITESPACE`, one star-join point (offenders red).
- `[[ x =~ a{1 ]]` rc 2 with diagnostic; case tilde rows match.

---

## Wave 7 — Surfaces

### 7A Scripting and invocation (2 slots)
**Owned:** C039 `$LINENO`/diagnostic line inside continuation-joined command · C092 read error → EOF · C239 `_read_line_block` rescans tail · C086 invocation `-o` reads cluster remainder · C157 bare `+` · C161 unsupported bash options undocumented / `--verbose` · C197 `set -opipefail` · C198 `set -o` table divergences · C158 `argv0` sentinel · C088 eager `psh/__init__` import · riders C159 annotate `input_source`, C160/C162 utils facade + dead `has_unclosed_heredoc`, C216 no-op deferred imports, C230 legacy config paths.
**Target/owners:** `psh/scripting/source_processor.py#process_line_continuations` returns `(joined_text, LineMap)` consumed by `_parse_command` (pin both `$LINENO` and the command-not-found line — they disagree in bash); `LazyFileInput._read_line_block` chunk accumulator scanning only new bytes and propagating read errors through the scripting error boundary (fault injection before input / after complete command / mid-partial; exit status pinned); ONE option-cluster grammar `psh/invocation.py#_parse_cluster` consumed by both invocation and the `set` builtin (`-o` always takes the next argv element and keeps scanning; bare `+` no-op; `--verbose` alias; unsupported `-l/-r/-D/--login/--noprofile/--noediting/--restricted` listed in `HELP_TEXT` + user guide row); `set -o` table gains bash's rows where meaningful and documents `strict-errors`/`history` deltas in §17 (C198 by-design half stays documented); `InvocationConfig.argv0: Optional[str]`; PEP-562 lazy `psh/__init__` + `--version` before `Shell` import (startup benchmark pin). Guard: golden rows `-opipefail`, `-oe pipefail`, `-ox`, `set -opipefail`; `test_invocation_argv_guard.py` extended so `set` cannot grow a second cluster parser (offender).

### 7B Interactive (3 slots; C038 first — security-relevant)
**Owned:** C038 OSC-0 title injection · C034 history numbers vs `history_base` · C035 + C097 completion cannot round-trip its escaping; bytes/codepoints/columns conflated · C036/C212/C155 vi Ctrl-D/Ctrl-R unbound, emacs undo unreachable, undo stack survives reads · C037/C213/C152 `\w` home boundary, `PROMPT_DIRTRIM`, prompt octal 1–2 digits · C151 Meta-</Ctrl-R skip cmdhist join · C156 `history -a/-w` unlocked · C153 `\#` (oracle_changed — re-derive vs 5.3 CHANGES rrrrrr, then fix) · C154 REPL sketch drift-lock · riders C214 (documented deliberate — user guide row), C215 (→ Checkpoint R PTY leg).
**Target/owners:** `psh/interactive/title.py#sanitize_title` at the single OSC write site (control chars, 0x7f, 0x9b stripped; optional shell option gate); `ShellState.history_base` monotonic (owner of `!n`, `\!`, `history` numbering); `psh/interactive/tab_completion.py#CompletionContext` (raw replacement span, decoded lookup text, quote mode) — encode the selected name for the context; `KeyDecoder` reuses the campaign-4B.2 incremental UTF-8 decoder owner (no second decoder — ratchet), `line_layout` counts display columns via one width policy; one canonical action table in `keybindings.py` with a completeness test "mode-independent actions (eof, reverse-search, undo) bound in every table"; `prompt.py#_get_cwd` reads shell `HOME`, matches on a component boundary, applies `PROMPT_DIRTRIM` (bash 5.3 does not trim when … — per probe), octal 1–3 digits; `_editable` applied once at `_replace_line`; `LOCK_EX` in `write_history`/`append_history` (single `os.write`); `\#` per the re-derived 5.3 rule. Every fact PTY-verified (realistic-terminal leg). Guard: PTY workflow tests (escaped spaces/quotes/`$`/backticks/backslashes, cursor mid-word); `test_doc_snippets.py` registry entry for the REPL fragment.

### 7C Analysis visitors (2 slots)
**Owned:** C033 formatter drops `${v}` before brace expansion (declare -f → eval round-trip) · C231 no executable round-trip contract · C099/C211 security visitor loses the command behind prefixes/wrappers; quoted variable labelled unquoted · C083 DebugASTVisitor drops redirects on 10 classes · C210 coverage matrix covers three visitors only · C084/C144 word-anchored substitution counting · C085 inverted `>&1` advisory · C145 validator pops context before redirects · C147 arithmetic injection only for `(( ))` · C209 `SimpleCommand.args` recomputed · riders C146 location claims, C148/C149/C150 dead code, C235 (design).
**Target/owners:** `VariableExpansion.braced` is the formatter's authority (`_needs_brace_disambiguation` reads it); an **execution-equivalence contract**: `tests/unit/visitor/test_executable_round_trip.py` runs a corpus through `--format` and `declare -f`→`eval` and asserts identical stdout/rc (structural equality is insufficient — C231). Command-head reads go through Wave 2's `CommandHead.of` (security visitor skips prefixes, accounts conservatively for `command`/`builtin`/`eval`, represents dynamic heads explicitly; clean result described as "no findings from the implemented rules"); quote state from the typed `Word` helpers. Substitution counting node-anchored (`visit_CommandSubstitution`/`visit_ProcessSubstitution`; `_analyze_string_features` deleted); `_render_redirects` helper on all ten handlers; coverage matrix parametrized over EVERY analysis visitor incl. DebugASTVisitor; delete the inverted advisory; `_visit_redirects` before `_pop_context`; `visit_ArithmeticExpansion` injection shape; `args` snapshot per handler. Guard: coverage-matrix extension + the head ratchet from 2.2 + the round-trip corpus.

### Exit criteria (Wave 7)
- `$LINENO` and diagnostic lines match bash inside continuation-joined commands in all modes; read-fault injection yields bash's exit status.
- One option-cluster grammar (offender red); invocation golden rows match.
- Title bytes contain no control characters; completion PTY workflow round-trips; every keybinding completeness row green; `\#` matches 5.3 on a PTY.
- Round-trip corpus equal for `--format` and `declare -f`; the four #22 security probes AND `X=1 eval …`/`command eval …` report findings; DebugASTVisitor in the coverage matrix.

---

## Checkpoint R — Whole-tree checkpoint

Bespoke multi-scope adversarial workflow (integrator plan §5 standard: independent scopes, composed probes, attack rounds to zero). Questions: (1) do all Wave 0–7 discriminators pass at one tree? (2) did any wave resurrect a deleted duplicate (each ratchet run against its offender)? (3) are the new owners the only implementation (census)? (4) new cycles/complexity cliffs/leaks/flakes? (5) is Wave 8 still the right scope? Also discharges the reviewers' coverage notes as R scopes: C167 (Linux ctype/PTY continuation seam/posix identifiers), C189 (pattern_engine/prompt/aliases), C193 (process_lease/locale/trap/terminal/stream bindings), C215 (SIGWINCH/completion listing/Ctrl-R painting on a real terminal), C192 (locale on the Linux nightly). Output: report + Wave 8 re-scope amendment.

---

## Wave 8 — Textbook and measured perf (design D2/D3/D4)

**Owned:** C227 simplify coordinators (`_run_command` 263 lines, `ShellState.__init__` 323, `scope.set_variable` 172, `file_redirect.py`) · C131 named startup phases · C228/C087/C133/C188/C217/C143 comment history vs algorithm (evidence pointers into gitignored `tmp/`, campaign IDs, changelog docstrings, prose density) · C229 (D4 — already discharged narrowly in 1.4/5.3/7A; this wave records deltas) · C244 (test-suite limits — carried as the standing pattern: actual-target/side-effect/fault assertions, applied in every wave; audited here) · C232/C223/C224 (themes) · C132 finish or retitle the VariableStore façade · C230 legacy config retirement.
**Required work:** extract named phases only where inputs/outputs/cleanup become simpler; replace transaction-flag bundles with one small ownership object; promote still-live `tmp/` probes to `golden_cases.yaml` and cite case names; ≤1 campaign ID per file (SR-8 ratchet: `tests/unit/tooling/test_comment_hygiene.py` counting campaign-ID tokens per file against a frozen ceiling that only decreases; pointers into `tmp/` forbidden); move long rationale to subsystem CLAUDE.md/design notes; complexity counters vs the Wave 0 baseline explained.
**Exit:** hub line counts and campaign-ID counts below the ratchet ceilings; no `tmp/` pointers in `psh/`; a new reader can explain `_run_command`'s phases and cleanup from the code (verifier narrative test).

---

## Ceremony C — Closure

Sequence-doc §12 with SR-7's compare-bash form: at ONE final tree run three seeded standard gates (identical censuses), `ruff check psh tests tools`, `mypy`, `python -m pytest tests/conformance -q`, compare-bash, `run_tests.py --benchmarks`; re-run every inventory discriminator, every FLIP-PIN (all flipped to parity or declared with both-sides pins), every guard against its offender; nightly green at the final tree on bash 5.3.15; ledger/INVENTORY/FLIP-PINS/evidence committed; close report headline agrees with its tables; attestation is the FINAL commit; no manual tag.

---

## Park register (ruled at Wave 0; each row has a successor owner — not counted as closed)

| Park | Rows | Ruling |
|---|---|---|
| P-1 RESUMABLE-PARSER successor campaign | C171 ParseSession O(k²) (registered carry), C172 nested cmdsub super-linear (capped, documented), C012 full retry-from-seed variant (cheap `UnclosedQuoteError` skip ships in 1.4) | Separately budgeted with a measured cost target (fresh appraisal D4); characterization pins become upper-bound tests when it lands. |
| P-2 Combinator constant factor + double parse | C120 | By design (educational parser); one sentence in `psh/parser/CLAUDE.md`. C178 becomes SR-3. |
| P-3 Missing bash features | C165 `coproc`, C190 `$(< file)`, C196 `BASH_SOURCE`, C199 identity variables (by-design), funsub `${ cmd; }`/`${\|cmd;}` (bash 5.3, L) | Documented gaps in user guide §17 / `missing_features.md`; Wave 0 adds both-sides declared-divergence pins for funsub and `$(<f)` so a future implementation flips them. |
| P-4 Documented deliberate divergences | C175 aliases in scripts (escape hatch verified), C185 `%P`/`times` residue, C186 `%Q` lenient, C187 CR-D1 async reaper, C203 (ulimit -p, `declare -A` order, printf %a subnormal, mapfile -C), C204 `declare -f` pretty-print, C205 `environment:` prefix, C214 `-i` with piped stdin, C218 richer parse-error format, C174 `cat <<` interactive INCOMPLETE (registered successor) | Stay documented; each has (or gets in Wave 0) a both-sides pin so drift is visible. C205 is pinned by the 4.5 ratchet allowlist. |
| P-5 Architecture successors (5B lineage) | C236 leaky protocols, C237 typed `or_else` union, C233 two parsers (keep) | Successor to the boundary campaign's 5B; not correctness. |
| Excluded | C114, C163 (not reproducible on 5.3.15), C208 (fixed: test-harness race) | Not queued; recorded in INVENTORY with the verify note. |

---

## Finding ownership map (live / oracle_changed rows — exactly one owner each)

| Wave | Owned cids |
|---|---|
| 0 | C169, C181, C238, C241, C242, C243, C245 (+ 51 gate-triage nodes; W0-N1..N6 registered and routed) |
| 1 | C002, C003, C004, C005, C006, C007, C008, C009, C011, C012 (cheap variant), C013, C014, C045, C046, C047, C048, C049, C050, C100, C101, C102, C103, C104, C105, C106, C164, C168, C170, C191, C221 |
| 2 | C010, C015, C016, C017, C018, C019, C020, C021, C051, C052, C053, C054, C055, C056, C057, C058, C059, C060, C061, C062, C107, C108, C109, C110, C111, C112, C113, C115, C116, C117, C118, C119, C121, C122, C123, C166, C173, C176, C177, C178 |
| 3 | C027, C028, C044, C070, C071, C072, C073, C090, C093, C094, C095, C096, C130, C132, C136, C194, C195, C226 |
| 4 | C001, C022, C031, C032, C040, C041, C063, C064, C065, C066, C067, C069, C079, C080, C081, C082, C091, C124, C125, C126, C127, C139, C142, C179, C180, C182, C183, C184, C206, C207, C219, C222 |
| 5 | C029, C030, C043, C074, C075, C076, C077, C078, C089, C098, C134, C135, C137, C138, C140, C141, C200, C201, C202, C225, C240 |
| 6 | C023, C024, C025, C026, C042, C068, C128, C129, C188 |
| 7A | C039, C086, C088, C092, C157, C158, C159, C160, C161, C162, C197, C198, C216, C230, C239 |
| 7B | C034, C035, C036, C037, C038, C097, C151, C152, C153, C154, C155, C156, C212, C213 |
| 7C | C033, C083, C084, C085, C099, C144, C145, C146, C147, C148, C149, C150, C209, C210, C211, C231, C235 |
| R | C167, C189, C192, C193, C215 (coverage scopes) |
| 8 | C087, C131, C133, C143, C217, C223, C224, C227, C228, C229, C232, C234, C244 |
| Park | C120, C165, C171, C172, C174, C175, C185, C186, C187, C190, C196, C199, C203, C204, C205, C214, C218, C233, C236, C237 |
| Excluded | C114, C163, C208 |

Themes C219–C224 and designs C226–C235 are cross-cutting inputs whose members are owned by the waves above (theme row listed under the wave that ships its guard).

## Risk register

| Risk | Mitigation |
|---|---|
| bash 5.3 semantics not yet fully mapped (trap top-level boundary, special-builtin exits, `${ }` funsub grammar, `exit abc` continue) | Wave 0 probes precede design (A8 lesson); every retune cites CHANGES/NEWS or a transcript; funsub parked with declared-divergence pins, not half-implemented. |
| Nightly bash build (source tarball) slow/flaky | Cache keyed on version; assert `bash --version` = 5.3.15 before the suite; SR-4 classifiers are the secondary defence. |
| Byte-model ruling (C013) ripples into `${#x}`, `[[ == ]]`, printf | Slot 1.3 ships the round-trip matrix first; fallback = documented divergence, decided by evidence in-slot. |
| `in_pipeline` one-shot breaks the exec-optimization of the last pipeline member / `lastpipe` | 4.1 pins `shopt -s lastpipe`, builtin-last, function-last, `exec`-branch rows in all modes; verifier attacks outside the dev's scope. |
| PATH observer semantics (effective-binding change) over-fires or misses temp-env pops | 3.3 counter test enumerates every write path; dispatch asserted by `execve` target. |
| Job-text unparser (C065) scope creep (bash's `make_command_string` layout) | Source-extent text first; parity pins limited to the shapes bash 5.3 prints (`( … )`, `> /dev/null` spacing); exotic layouts declared. |
| Combinator packrat memo memory | Counter + memory pin on the nesting corpus; memo cleared per parse. |
| Homebrew bash readline-linked `~` artifact | SR-5; Wave 0 grep confirms only one module reassigns HOME in-script. |
| Sandbox/ENV false reds | SR-6 skip guards; gate unsandboxed; disk ≥10 GB headroom; seeded triplicate gates at Wave 0 and C. |
| Parallel session's uncommitted files (`docs/reviews/README.md` modified; r23 report untracked) | Wave 0.1 commits the r23 report and coordinates the one-row README conflict before any production slot. |
| Verifier drift (stale harness preamble) | Campaign-local copy of the verify harness with the preamble pointing at THIS program; reviewed at each wave boundary. |
| Linux-only paths (procsub `/dev/fd`, signal 138 vs 158, locale) not covered by the macOS gate | Nightly watch rows in the ledger; 4.3/4.4 reason about Linux at design time. |

## Launch checklist (all require explicit user go)

1. User go received; oracle ruling (5.3.15) acknowledged in the ledger header.
2. `gh auth status` → `philipwilson` active; ≥10 GB disk free; no sandbox around the gate shell.
3. Wave 0.1 committed (r23 report + program + INVENTORY.json + ledger skeleton; README index reconciled with the parallel session).
4. Wave 0.2 oracle plumbing green locally; nightly.yml bash pin run manually once (`workflow_dispatch`) and observed green with `bash --version` = 5.3.15.
5. Wave 0.3/0.4 retunes released; three seeded gates + conformance + compare-bash + benchmarks recorded as the baseline; `gate_attestation.json` carries `oracle.version`.
6. Park register rulings written; every INVENTORY row has an owner; FLIP-PINS inventory complete (signal-death text, funsub, `$(<f)`, sq-in-dq closure noted).
7. Verify harness copied and re-pointed; first Wave 1 brief (1.1 word-start authority) written with owner/consumers/deletions/guard per SR-2; worktree cut from the Wave 0 final tree.
