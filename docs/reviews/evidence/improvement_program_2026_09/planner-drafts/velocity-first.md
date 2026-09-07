# Velocity Program 2026-09 — folding reappraisal #23 and the fresh appraisal into one improvement program

- **Date:** 2026-09-06
- **Status:** PLAN OF RECORD, NOT LAUNCHED. Nothing executes without an explicit user go.
- **Base:** `origin/main` @ `6459f1a6` (v0.779.0). Gate attestation on record: `72a2da8d` (gated 2026-08-09, bash 5.2.26).
- **Findings sources (both at v0.779.0):** `docs/reviews/ground_up_reappraisal_23_correctness_textbook_2026-08-09.md` (UNTRACKED) and `docs/reviews/fresh_appraisal_2026-09-06.md` (UNTRACKED, evidence in `docs/reviews/evidence/fresh_appraisal_2026_09_06/`). The canonical merged inventory is the 245-row C-register (C001–C245) re-verified today at HEAD against bash 5.3.15; the 51-row GATE TRIAGE is the second input. Both become the evidence tree's first files at Wave 0.
- **Governing documents, in authority order:** (1) this plan; (2) `boundary_remediation_integrator_plan_2026-07-21.md` §3 roles / §5 verification / §7 ceremony / §8 risks — ADOPTED by reference, amended only by the deltas in §3 below; (3) `boundary_remediation_campaign_sequence_2026-07-21.md` §3 standing rules 1–10 and the wave format (Owned findings / Architecture target / Required work / Exit criteria) — ADOPTED; (4) `.claude/skills/psh-release/SKILL.md` (local gate, attestation FINAL commit, no manual tag).
- **Lens:** velocity and verifiability. Green local gate first (one release), green Linux nightly next (same release), then a merge train of small slots — each ≤ ~2 dev-days, each verifiable by ONE verifier in ONE bounce, each shipping as its own attested release (integrator may pair two S slots in one release).

---

## 1. Decision

Run ONE sequential program, not two (one per report). The two appraisals cite the same code at the same version and the C-register already merges them; a second ledger would only create cross-references. The program is ordered by *unblocking value per day*: first restore the two observation channels (local gate, Linux nightly) because every later closure claim is meaningless while they are red; then close the silent-data-loss and lexer P0 clusters (highest user impact, smallest diffs); then the conformance/systemic/builtin/visitor/interactive/perf families as independent slots; then the record-only textbook cleanup. Large projects that do not fit a 2-day slot are PARKED in §17 with a reason, not smuggled in.

The oracle is **GNU bash 5.3.15 at `/opt/homebrew/bin/bash`** (user decision). bash 5.2 is history: rows verified against it are provenance stamps, not claims. Integrator plan amendment A12 ("PATH bash 5.2") is superseded by §3 delta D1.

## 2. Program outcome

The program succeeds when:

1. `python run_tests.py --parallel` is green at the launch tree with an attestation whose `oracle` field records bash 5.3.15, and the attestation writer REFUSES to attest against any other major.minor (Wave 0).
2. The scheduled Linux nightly is green against the SAME oracle version, and platform-divergent rows are classified as platform (skip with a probed reason), never left red (Wave 0).
3. Every C-register row with status `live` or `oracle_changed` has exactly one owning wave in §5 and is closed by a shipped slot, or sits in the Parked register (§17) with a stated reason and a successor name. `fixed` / `not_reproducible` rows are NOT queued (C114, C163, C208); `n/a` design/doc/theme rows are inputs to the slots that cite them or land in Wave 11.
4. Every slot ships with: a red-on-base pin (replayed at base), a bash-5.3.15 differential (conformance or golden) where bash is the contract, a guard where the finding was systemic, user-guide correction where a claim was wrong, and one verifier report with 0 open blockers.
5. A clean checkout of the final tree contains the plan, the ledger (`docs/reviews/evidence/velocity_2026-09/LEDGER.md`), the flip-pin inventory, per-slot evidence, and a close report whose headline agrees with its tables.

Out of scope by design: feature parity sweeps (funsub `${ cmd; }`, coproc, BASH_SOURCE), the resumable parser, the Unicode width model, the combinator parser's constant-factor cost. Each is parked in §17.

## 3. Standing rules — DELTAS ONLY from the prior campaign

Everything in the integrator plan §3 (roles, never-touch list, detached gate worktree, ruff+mypy before merge, project `tmp/`, BLOB-UNION golden merges, ≥10 GB disk, discriminator in probe harnesses, PTY leg for interactive facts) and the sequence doc §3 rules 1–10 stays in force. Deltas:

- **D1 — Oracle.** Differential contract = "bash 5.3.15, `/opt/homebrew/bin/bash` locally; the nightly builds the SAME 5.3.15 from source and points `BASH_PATH` at it". Never `/bin/bash` (3.2). Never `bash` on PATH. `resolve_bash().version` is the single source of the oracle version; the attestation records it; `tests/harness/oracle_policy.py::EXPECTED_BASH_MM = "5.3"` is the declared expectation, enforced by the attestation writer and a conftest session header. A row that must differ by oracle version is classified with a probed predicate on the ORACLE (`oracle_feature(...)`), never with a hard-coded version string in test code.
- **D2 — Slot size cap.** A slot is ≤ ~2 dev-days of work and touches one subsystem family unless the fix is one mechanism across files. If a dev's honest estimate exceeds 2 days, the brief is split before dispatch, not after.
- **D3 — One verifier, one bounce.** Per slot: ONE adversarial verifier, fresh context, who (a) replays every red-on-base claim at base, (b) constructs ≥ 5 novel rows outside the dev's declared audit scope (mode axis: `-c` / file / stdin; parser axis where the parser is touched; option axis where an option is touched), (c) runs every new guard against a synthetic offender, (d) re-runs the slot's differentials at the FINAL slot SHA. A slot that bounces ONCE is fixed by the same dev and re-verified once. A slot that bounces TWICE is SPLIT by the integrator into smaller slots — never a third verification round on the same brief. (The prior campaign's 5→10→2→0 rounds are what this program is optimizing away.)
- **D4 — Pre-merge smoke (C245).** Before handing off, the dev runs `python run_tests.py --quick`, the touched test modules, `ruff check psh tests tools`, and `mypy`, and pastes the four tails into the handoff. The full gate remains the integrator's ceremony step; per-PR CI stays disabled.
- **D5 — Test-shape rule (C244).** Each slot's pins assert the ACTUAL effect (cwd via `pwd -P`/`os.getcwd()`, executable actually dispatched, bytes actually consumed, exit status of the NEXT command), not only the return code or the restored string. Formatter/serializer slots add execution-equivalence pins (`declare -f` → `eval` round-trip runs identically).
- **D6 — Provenance stamps.** "Verified against bash 5.2" in an existing docstring is a provenance stamp; it is updated ONLY when the slot touches that file. No tree-wide rewrite of the 453 test-side and 146 psh-side mentions (C241) — instead conformance failure messages print the oracle version so drift shows in the first red diff.
- **D7 — Ownership by cid.** Every ledger row, brief, pin docstring, and CHANGELOG line names the C-id(s) it closes. `grep -rn "C0[0-9][0-9]\b"` over tests must find every closed row's pin.
- **D8 — Nightly is a wave-close criterion.** No wave closes until the first scheduled nightly after its last merge is green (carried from Ceremony C rule 2; now a hard gate, not a watch).
- **D9 — Deferred registrations.** New defects discovered during a slot (the fresh appraisal's "side findings", this triage's incidental bugs) are registered in the ledger with a cid `N0xx` and an owning slot on the day they are found; they never ride an unrelated slot's diff.

## 4. Status and dependency order

| Order | Wave | Releases (est.) | Depends on |
|---:|---|---:|---|
| 0 | Oracle baseline, green gate, green nightly | 1 (v0.780.0) | none |
| 1 | bash 5.3 semantics (flip the Wave 0 version pins) | 3 | Wave 0 |
| 2 | Silent data loss + security rider | 3 | Wave 0 (independent of 1) |
| 3 | Lexer P0 cluster | 6 | Wave 0 |
| 4 | Recursive-descent parser conformance | 3 | Wave 3 (3.1/3.2 change tokens the parser pins depend on) |
| 5 | Systemic guards + core invariants | 5 | Wave 0 |
| 6 | Builtins, arrays, executor and invocation conformance | 6 | Wave 5 (5.2 `legal_number` precedes 6.4/6.3) |
| 7 | Analysis visitors, formatter, combinator tooling | 3 | Wave 0 |
| 8 | Interactive | 3 | Wave 0 |
| 9 | Demonstrated performance costs | 3 | Waves 3, 5 (touch the same lexer/expansion sites) |
| 10 | Process/IO lifetime and registered successors | 3 | Wave 2 |
| 11 | Textbook cleanup (record-only, no behavior) | 2 | all fix waves (comments follow code) |
| C | Close ceremony | 0 | Wave 11 |

Waves 1, 2, 3, 5, 7, 8 are mutually independent after Wave 0 and may interleave on the merge train (the integrator picks by verifier availability); the table's order is the recommended one. Within a wave, slots touch disjoint files and may be developed in parallel worktrees; they merge in any order. No slot depends on an unshipped slot: the only cross-slot dependencies are the wave edges above plus the in-wave notes (5.2 → 6.3/6.4; 3.1 → 3.x none; 6.2 → 6.3 for `mapfile` preflight).

Release numbering: Wave 0 = v0.780.0; each subsequent slot bumps the minor patch (v0.781.0, …). ~41 releases total at one per slot.

---

## 5. Ownership map (every `live` / `oracle_changed` row → exactly one wave.slot)

| Wave.slot | Owned C-ids |
|---|---|
| 0.1 | C242, C241, C243, C238, C245 (rule D4), C244 (rule D5) |
| 0.2 | gate FORMAT rows (trap synopsis+`-P`, shopt width, jobs width, hash -d, procsub render param, signal-death S-path) |
| 0.3 | gate SEMANTIC/PREMISE rows converted to version pins or fixed when ≤ 1 file; C153, C181 (re-derive vs 5.3.15) |
| 0.4 | nightly: 5.3.15 source build + `BASH_PATH`, printf `%a` platform predicate, 4 ENV skip guards |
| 1.1 | POSIX special-builtin exit family (export/readonly/unset exits; eval/dot boundary; posix function names; identifier rows) |
| 1.2 | trap entry-status top-level rule; usage-error `$?`=2 family (`cd`/`exit`/`shift`/`return`/`break`/`continue`); `exit abc` continue |
| 1.3 | readonly attribute refusal; closed-fd-0 startup 126; empty-PATH wording; `read <&-` internal defect (N-row) |
| 2.1 | C001, C022, C038 |
| 2.2 | C031, C032 |
| 2.3 | C020, C021, C056, C060 |
| 3.1 | C002, C003 |
| 3.2 | C004, C011, C164 |
| 3.3 | C005, C006, C170, C080 |
| 3.4 | C007, C047 (theme C221) |
| 3.5 | C008, C013 (doc qualification), C191, C100 (fold) |
| 3.6 | C009, C046, C014 |
| 4.1 | C010, C017, C052, C166 |
| 4.2 | C015, C016, C018, C110 (fold) |
| 4.3 | C051, C111, C039 |
| 5.1 | C066, C069, C130, C139 (fold) (theme C219) |
| 5.2 | C030, C098, C141 (fold) (theme C220) |
| 5.3 | C026, C023, C024, C025, C068 |
| 5.4 | C027, C028, C044, C071, C072 |
| 5.5 | C070, C063, C195 |
| 6.1 | C043, C225, C074 |
| 6.2 | C093, C094, C095, C096, C136, C226 (as the cross-entry-point matrix), C194 |
| 6.3 | C090, C240 |
| 6.4 | C029, C076, C134, C077, C078, C075, C089, C200, C135 (fold) |
| 6.5 | C064, C065, C067, C124, C126, C127, C041, C042, C040 |
| 6.6 | C086, C197, C198, C157, C158, C161, C092 |
| 7.1 | C033, C231, C083, C085, C145 |
| 7.2 | C084, C144, C147, C099, C211, C209, C210 (fold) |
| 7.3 | C116, C117, C122, C177, C118, C061, C062, C057, C058, C059, C019 |
| 8.1 | C034, C151, C155, C156 |
| 8.2 | C035 |
| 8.3 | C036, C212, C037, C213, C152, C097 (decode half; width half parked as P3), C214 (declare) |
| 9.1 | C050, C048, C103 |
| 9.2 | C012, C128 |
| 9.3 | C073, C088, C239 (theme C229) |
| 10.1 | C081, C082, C091 |
| 10.2 | C180, C182, C183, C184, C185, C206, C207 |
| 10.3 | C190 |
| 11.1 | C087, C133, C188, C108, C109, C112, C115, C123, C106, C135, C154, C168, C179, C224, C228, C143, C049, C232 |
| 11.2 | C120, C186, C174, C165 (doc rows re-affirmed), C227 (bounded: C131 phase extraction), C230, C236 (census + ratchet only) |
| P (parked) | C171, C172, C097 width half, C013 byte model, funsub `${ cmd; }`, C196, C233, C237, C233 |
| not queued | C114, C163 (not_reproducible), C208 (fixed); n/a design rows C045, C053, C054, C055, C101, C102, C104, C105, C107, C113, C119, C121, C125, C129, C132, C137, C138, C140, C142, C146, C148, C149, C150, C159, C160, C162, C173, C176, C201, C202, C216, C217 — folded into the Wave 11 cleanup slots at the integrator's discretion, none is a closure obligation |

---

## 6. Wave 0 — Oracle baseline, green local gate, green Linux nightly

**One release (v0.780.0)** composed of four sub-slots on one integration branch `fix/oracle-5.3-baseline`; sub-slots are verified by targeted module runs (`pytest <family files> -q`) because the gate cannot be green until all four land; the full gate runs once at the integration tip.

### Owned findings
C242 (gate red: 52 failures at 6459f1a6), C241 (oracle comments target 5.2), C243 (reviews index test fails on untracked r23 report), C238 (stale "latest/active" index claims), C245 (no pre-merge smoke), C244 (test-shape limits), C153 (`\#` prompt number — oracle_changed), C181 (`-c` + `set -m` notice — oracle_changed); all 51 GATE TRIAGE rows; the Linux nightly's 7 red `printf %a` rows (red every night since the 5R rider; runs 33586284596 … 34008477403, bash 5.2.21 on x86-64).

### Architecture target
One oracle identity, recorded where drift is detected: `resolve_bash()` → `BashOracle(path, version)` is the single producer; the attestation, the conftest session header, and every conformance failure message are consumers. Version-sensitive behavior is expressed as a probed predicate on the oracle, platform-sensitive behavior as a probed predicate on the oracle's host, never as a version literal in a test. The nightly runs the same oracle version as the local gate.

### Required work

**0.1 — Oracle identity + evidence bootstrap (S/M, 1 day)**
- `tests/harness/oracle_policy.py` (new): `EXPECTED_BASH_MM = "5.3"`, `oracle_feature(name)` probe cache (e.g. `x87_long_double` = `printf '%a\n' 1` prints `0x8p-3`; `funsub` = `${ :; }` parses).
- `tests/harness/shell_oracle.py#resolve_bash`: unchanged ladder; export `oracle_version()`; `tests/conftest.py` prints one session header line `oracle: <path> <version>`; `tests/conformance/conformance_framework.py#assert_identical_behavior` failure text gains `oracle=<version>`.
- `run_tests.py#build_attestation`: schema 1→2, add `"oracle": {"path", "version"}`; `_run_attestation_checks` REFUSES to write when `major.minor != EXPECTED_BASH_MM` (loud message naming D1). `tools/verify_gate_attestation.py` REQUIRED_KEYS += `oracle`, ATTESTATION_SCHEMA = 2; `tests/unit/tooling/test_gate_attestation.py` updated + a synthetic-offender test (attestation with version 5.2.26 → refused).
- `tests/unit/tooling/test_bash_oracle_resolution.py`: add the rule that no test file contains a bash version literal used as a predicate (`"5.2"`/`"5.3"` inside `if`/`skipif`) — offender test included.
- Evidence tree `docs/reviews/evidence/velocity_2026-09/`: `LEDGER.md` (245 C-rows + 51 gate rows + N-rows, one owner each), `FLIP-PINS.md`, `wave-manifest.json` (same shape as the 2026-07 manifest), `gate-triage-2026-09-06.md` (the 51-row triage verbatim), `nightly-status.md`.
- Commit the two untracked reports + the fresh-appraisal evidence dir; add index rows in `docs/reviews/README.md` (current appraisal = the fresh appraisal; r23 row; this plan row; the 2026-07 close report demoted to "historical"); `test_every_review_file_is_indexed` green.
- CLAUDE.md "Development Principles" gains one line each for D4 and D5 (smoke + actual-effect assertions).

**0.2 — FORMAT retunes, psh side (M, 1.5 days)** — bash 5.3 changed presentation only; psh follows.
- `psh/builtins/signal_handling.py:24` synopsis → `trap [-Plp] [[action] signal_spec ...]`; implement `-P` (flags `lpP`; `-P` with no operand → `trap: -P requires at least one signal name` rc 2; `-p`+`-P` → `cannot specify both -p and -P` rc 2; prints the bare action per operand; help text gains a `-P` line) so `test_builtin_help_sync.py::test_no_unspec_flag_advertised` stays green without an allowlist entry. Update pins `tests/unit/builtins/test_trap_flags.py:73`, `tests/unit/builtins/test_error_location_prefix.py:39`; user-guide `04_builtin_commands.md:1107` listing. Closes the 4 `trap` gate rows.
- `psh/builtins/shell_options.py#_print_option`: width 15→20 for shopt-table prints (queries and bare `shopt`/`-s`/`-u` listings), 15 kept for `-o` listings; `set -o` (`environment.py:568`) untouched. Pins: `test_shopt.py:79`, `test_shopt_set_o.py:23,29,191,207,213,249`; golden rows at `golden_cases.yaml:2378` and `:8910`. Closes 5 shopt rows.
- `psh/executor/job_control.py:279/280/683` status field 24→27. Closes 6 jobs-width rows (+ the 2 `-c` listing rows once 0.3 removes the filter).
- `psh/builtins/hash_builtin.py:80-83` delete the empty-table short-circuit (bash 5.3 CHANGES ggggg calls 5.2 a bug); test row uses `2>/dev/null`; invert `test_hash_builtin.py::test_dash_d_on_empty_table_silently_succeeds` → `…_reports_miss`.
- `test_subscript_keying_conformance.py::test_divergence_procsub_compound_render_residual[case]` expected string → bash 5.3's layout (S).
- Signal-death announcement rows (5 tests in `test_pipeline_signal_death.py`, `test_signal_killed_diagnostic.py`): S-path — assert bash's `strsignal(SIGTERM).ljust(27) + <job text>` shape on the bash side, keep psh's bare-form pin, reword docstrings + `psh/executor/job_control.py:626-628`. Register the L-path (bash-faithful job text) as N-row owned by 10.2 alongside C065 (the same `<subshell>` placeholder).

**0.3 — SEMANTIC/PREMISE retunes (M, 2 days)** — the rule: fix psh in Wave 0 only when the change is one site and the verifier can see it in one module; otherwise pin the 5.3 behavior BOTH-SIDES as a version-classified divergence and hand the fix to Wave 1.
- Fixed here (one site each): `psh/builtins/job_control.py:96-98` delete the `command_mode` filter (+ comment :85-95; module docstring of `test_jobs_completed_listing_modes.py`; rename the two `_suppressed_c_mode` tests; CHANGELOG note that the 5.2 `-c` eager reap no longer exists); `psh/executor/strategies.py:148` `empty_path` → `unset_path = not state.scope_manager.lookup('PATH').is_set` (+ `format_exec_failure` kwarg/docstring; rename `test_explicit_empty_path_is_no_such_file` → `…_is_command_not_found`; `test_command_resolution_r3.py` pin flip); `psh/executor/function.py:47-55` delete the posix-mode function-name rejection + stop pre-validating `-f` operands in `function_support.py` (bash 5.3 CHANGES p) with the `test_identifier_policy_conformance.py` split (`for`/`select` still rejected; new `test_function_names_unrestricted_in_posix`); `test_bad_substitution_conformance.py` drop `${ }` and `${ :-x}` from BAD_CASES + both-sides funsub pin (psh rc 1 vs bash rc 0) guarded by `oracle_feature('funsub')`; `test_divergence_sq_in_dq_readback_outcome` → parity pin; `test_unlexable_subscript_route_audit[let_arith]` bash assertions updated; `test_invalid_regex_diagnostic_is_psh_only` → both-diagnose pin.
- Pinned both-sides for Wave 1 (FLIP-PINS "must-flip" rows, each named `test_v53_*`): export/readonly bad-identifier exits + `unset` readonly exit + eval/dot boundary suppression (`test_posix_special_builtin_exit_conformance.py`, integration twins, golden `posixexit_*` rows) → 1.1; trap entry-status (`test_exit_trap_status_precedence_conformance.py` 4 rows) and `cd`/`exit` usage `$?`=2 (`test_exit_cd_options_conformance.py` 2 rows) → 1.2; `declare -i` on readonly (`test_export_env_sync_conformance.py`) and closed-fd-0 126 (`test_stdin_startup_robustness.py`) → 1.3. `test_identifier_policy…::test_declare_export_read_report_and_continue` splits its `export é=1` iteration into the 1.1 pin.
- C153: re-derive `\#` against 5.3.15 via `${PS1@P}` and a PTY leg; outcome recorded in the ledger as closed-by-oracle or a fresh both-sides pin handed to 8.3. C181: re-derive `-c` + `set -m` boundary notice (bash 5.3 shows no notice — probed in the jobs triage); update `psh/builtins/job_control.py:86-99` prose; close or pin.

**0.4 — Linux nightly (M, 1 day)**
- `.github/workflows/nightly.yml` (both jobs): build bash 5.3 + patches 001–015 from `ftp.gnu.org` into `~/bash-5.3.15` (actions/cache keyed `bash-5.3.15-${{ runner.os }}-${{ runner.arch }}`), export `BASH_PATH=~/bash-5.3.15/bin/bash`, and a step that FAILS if `$BASH_PATH -c 'echo $BASH_VERSION'` is not `5.3.15*`; the "Show bash version" step also prints `printf '%a\n' 1` and `$MACHTYPE` so the platform predicate is visible in every log.
- Platform classification of the 7 red rows in `tests/conformance/bash/test_printf_float_format_conformance.py` (observed on the nightly: bash `0xc.8fp-2` vs psh `0x1.92p+1` for `%.2a` 3.14 — x86-64 glibc formats bash's `long double` with an explicit-integer-bit leading digit): `pytest.mark.skipif(oracle_feature('x87_long_double'), reason=...)` on the 7 tests, docstring corrected ("libc-STABLE" was false for x86-64 long double), LEDGER row for the 5R rider updated. No psh change (psh's double-based `%a` is bash-on-macOS/arm64-faithful).
- ENV skip guards (S each, skip not expectation change): `test_socket_earlier_bash_126_psh_runs_later` wraps `s.bind` in `except PermissionError: pytest.skip`; `test_cap_kill_reaches_a_writer…` and `test_bg_actually_resumes…` skip when `ps -o stat= -p <own pid>` returns empty; golden `r18t2_builtins_history_write_to_stdout` gains `requires_dev_fd: true` honored by `test_golden_behavior.py` (probe-open `/dev/stdout`); `TestCompositeQuoting::test_tilde_expands_in_key` supplies `HOME` via `env=` (Homebrew's installed-readline `~` resolves from the startup env — recorded in the row comment; psh NOT changed).
- `test_redirect_procsub_suppression_is_a_declared_divergence`: bounded poll 10×0.1 s → 30×0.1 s (the only mechanism consistent with the one-off gate failure; no expectation change).

### Exit criteria
- `python run_tests.py --parallel --write-attestation` green at the integration tip; `gate_attestation.json` schema 2 with `oracle.version == "5.3.15(1)-release"`; `tools/verify_gate_attestation.py` passes; a synthetic 5.2 attestation is refused (test).
- `python -m pytest tests/conformance -q` and `python -m pytest tests/behavioral --compare-bash -n auto -q` green locally; counts recorded in `wave0-legs-summary.md`.
- First scheduled nightly after merge: both jobs green with `BASH_VERSION 5.3.15` in the log and the 7 `%a` rows SKIPPED with the x87 reason.
- `FLIP-PINS.md` lists every Wave 0 version pin with its Wave 1 owner; LEDGER has no TBD owner among the 245 + 51 rows.
- C153/C181 have a ruling line each.
- Estimated: 4 sub-slots, ~5.5 dev-days, 1 release.

---

## 7. Wave 1 — bash 5.3 semantics (flip the Wave 0 version pins)

### Owned findings
The Wave 0 `test_v53_*` pins (no C-ids; gate rows): POSIX special-builtin exit family, trap entry-status rule, usage-error `$?`=2 family, readonly attribute refusal, closed-fd-0 126, plus N-rows registered by the triage: `read x <&-` internal defect (`input_reader.py:429` `NoneType.fileno`), `exit abc` continues in 5.3 (golden `bcontract_exit_bad_first_operand_exits_two` now wrong), `readonly -f é`/`export -f é` rc 0 in posix, `unset -f` readonly-function wording.

### Architecture target
psh's POSIX-mode exit policy and trap exit-status policy state the bash 5.3 rule in ONE place each (`psh/core/internal_errors.py#special_builtin_usage_*`, `psh/core/trap_manager.py`), documented by invariant prose, not by "probe-verified 5.2" sketches.

### Required work
- **1.1 POSIX special-builtin exit family (M, 2 days).** `ExportBuiltin` bad-identifier branch (`environment.py` ~152-156) → print first diagnostic, `raise SpecialBuiltinUsageError(1, suppressible=True)` when invoked as the special builtin (not via `command`/`builtin`; `-f` operands exempt); `DeclareBuiltin.run_as(invoked_as='readonly', special=True)` both `not a valid identifier` sites likewise (declare/typeset unchanged); `UnsetBuiltin` readonly-variable/element/function branches record and raise after the loop (first failure stops; wording `cannot unset: readonly function`); delete the `special_exit_floor` raise for eval/dot nested runs in `psh/scripting/source_processor.py` (~233-240) so an OUTER guard suppresses across `eval`/`.` (probe the trap-action nested run before deciding its floor; bash keeps exit 2 there). Flip: conformance rows to `TestPosixSpecialBuiltinExit`, integration `SURVIVING_ROWS`→`EXITING_ROWS`, golden `posixexit_export_badid_survives`/`posixexit_unset_readonly_survives`/`posixexit_no_suppress_across_eval`, matrix doc rows 48/49/51 + the eval-boundary sentence, docstrings in `exceptions.py`/`internal_errors.py`/`context.py`; identifier-policy `export é=1` row; user-guide §17 identifier prose (`export é=1`/`readonly é=1` exit in posix, bash 5.3).
- **1.2 Trap entry status + usage `$?`=2 (M, 2 days).** `trap_manager.py:449-451` record `(saved_exit_code, len(function_stack), source_depth)` for EXIT, signal and ERR traps; `builtins/core.py:39-41` apply when EXIT or when depths equal the recorded entry (bash 5.3 NEWS uu / POSIX interp 1602: top level of the action incl. `if`/`{ }`/loops/`eval`; NOT inside a function body or sourced file called from the action; DEBUG keeps current `$?`). Pins: the 4 rows renamed `…uses_entry_status`, plus the boundary rows listed in the triage (subshell rc 5, function body rc 1, `if` rc 0, `eval` rc 0, ERR rc 1, dot rc 1) in all three modes. `special_builtin_usage_discard`: `SystemExit(1)` in command_mode, `TopLevelAbort(2, errexit_immune=True)` otherwise, so `cd a b`/`exit 1 2 3`/`shift 1 2`/`return`/`break`/`continue` leave `$?`=2 on the next line while `-c` still exits 1; `navigation.py:103` rc 1→2; `exit abc` → rc 2 and CONTINUE (golden row + `bcontract` pins updated). Prose: `psh/core/CLAUDE.md:744-757`, `trap_manager.py:94-99`, `core.py:31-37,56-61`.
- **1.3 Readonly attributes, closed fd 0, `read` on closed stdin (M, 1.5 days).** `ScopeManager.apply_attribute`/`remove_attribute` (`scope.py:1290/1363`): raise `ReadonlyVariableError` when target is readonly and the changed set intersects `INTEGER|LOWERCASE|UPPERCASE|ARRAY|ASSOC_ARRAY|NAMEREF` (EXPORT/TRACE/READONLY still allowed; `local` renders `local: x: readonly variable`); flip `test_local_builtin.py::test_attrs_only_add_integer_allowed` → `_refused`; conformance rows (`declare -i R 2>/dev/null; …; declare -p R` rc 1, and the allowed `-x` half). `psh/__main__.py` STDIN branch: `sys.stdin is None` → `psh: error creating buffered stream: Bad file descriptor` exit 126 (only the no-`-c`/no-script path); `test_stdin_startup_robustness.py` two tests → 126; `read` builtin: `input_reader.py:429` guard `sys.stdin is None` → `read: 0: read error: Bad file descriptor` rc 1 (strict-errors pin: no traceback).

### Exit criteria
- All `test_v53_*` pins flipped to parity pins (FLIP-PINS rows struck through with the release number); zero remaining `test_v53_` names in tests.
- Conformance, compare-bash, gate green; nightly green (D8).
- Verifier's novel rows include the mode axis for every trap/usage cell and the `command`/`builtin` wrapper axis for 1.1.
- 3 slots, ~5.5 dev-days, 3 releases.

---

## 8. Wave 2 — Silent data loss (theme C222) + security rider

### Owned findings
C001 (function/eval/source body as pipeline member drops commands — P0), C022 (backgrounded command inside pipeline gets `/dev/null` stdin), C038 (OSC-0 title escape injection — SECURITY), C031 (fd ≥ 3 redirect targets expanded twice for builtins), C032 (`1>&-` then reopen → EBADF), C020 (combinator drops trailing redirect on `[[ ]]`/`(( ))`), C021 (bare procsub at command position → non-Command node), C056 (`time -p !`), C060 (`[[ -ef/-nt/-ot ]]` rejected by combinator).

### Architecture target
A pipeline-membership fact is consumed exactly once, at the member's own dispatch; a redirect plan is planned once and applied once; the combinator's special-command productions consume trailing redirects like every other compound. A single sanitizer owns the terminal-title write.

### Required work
- **2.1 Executor (M, 1.5 days).** `psh/executor/strategies.py:605` make `context.in_pipeline` one-shot at pipeline-member dispatch (clear on entry to `_function_frame` (`function.py:196`), eval and source frames — mirror `control_flow.py:91-92`/`subshell.py:82-83`); delete the false "nothing left to do" comment (C179 member). `AsyncJobPolicy.apply` (`process_launcher.py:81`) gets a third input — whether frame fd 0 is still the shell's original stdin — and suppresses the `/dev/null` redirect when fd 0 came from a pipe or enclosing compound redirect. `psh/interactive/title.py:21` sanitize via `str.translate` (drop `c < 0x20`, `0x7f`, `\x9b`) at the single write site; PTY pin with an injected `$PWD` basename. Pins: red-on-base rows for C001 in `-c`/file/stdin × function/eval/source × pipefail; C022 four shapes; golden rows promoted from the verification probes.
- **2.2 I/O (M, 2 days).** `manager.py:955 _builtin_redirect_fd_level` receives the already-resolved plan (`_clear_user_fds_from_parking` + `saved_fds_for_plan` + `apply_fd_plan`) instead of rebuilding a `RedirectProgram`; add a plan-once guard (a counter on `RedirectOp` asserted in a unit test with a synthetic double-plan offender). `manager.py:518 _swap_closed_output_streams` installs `_RawFdStream` (swap_output_stream_reopenable) instead of `_ClosedStream`; rewrite the falsified docstring premise. Pins: cmdsub-count file, procsub fork count, noclobber target; brace/function/if/while × fd 1/2 close-then-reopen.
- **2.3 Combinator small fixes (S/M, 1 day).** `special_commands.py:161-165, 245-249` consume `many(redirection)` after `))`/`]]`; remove `.or_else(process_substitution)` from `special_command` (:109-113); `pipelines.py:68-91` treat WORD `!` after `-p` as negation; `:277-278` add `-ef -nt -ot` and split the diagnostic. Pins via the direct combinator API AND `--parser combinator -c` (C178 framing rule: direct API for combinator claims).

### Exit criteria
- The r23 P0-1 repro prints all three lines in every mode; `pipefail` rc = 1; C001/C022 golden rows green under `--compare-bash`.
- Verifier's title-injection PTY probe shows no raw ESC in the OSC payload.
- Plan-once guard offender fails; no `RedirectProgram` re-plan in `_builtin_redirect_fd_level` (grep guard).
- Combinator: the 6 C020 shapes + the infinite-loop shape terminate identically to bash; `ProcessSubstitution` never reaches `core.py:634`.
- 3 slots, ~4.5 dev-days, 3 releases.

---

## 9. Wave 3 — Lexer P0 cluster

### Owned findings
C002/C003 (`((` without matching `))`; depth clamp), C004 (`is_comment_start` preceding-char model), C011 (`!` delimiter set), C164 (bare `]]` rc 127 vs 2), C005/C006 (fd-prefix mid-word; `>&` backtrack), C170 (fd > INT_MAX taken as fd), C080 (fd ≥ 2^31 OverflowError in io guards), C007 (`$((…))` quote-blind extent), C047 (two `${…}` extent scanners disagree — theme C221), C008 (`$'\uD800'` chr() crash), C013 (byte-model doc qualification), C191 (NUL retained in `$'…'` and read/mapfile), C100 (escape-decoder duplication, fold), C009 (function-header `)` in `$(…)` drops command position), C046 (no-progress RuntimeError CLI-reachable), C014 (heredoc spec ids positional — latent).

### Architecture target
The lexer has ONE model for each decision the `$( )` scanner already gets right: word-start-only comment/fd-prefix recognition, balanced-`))` lookahead before `DOUBLE_LPAREN`, quote-aware `$((` extent, `validate_brace_expansion` as the sole `${` extent authority, and the guarded `unicode_escape_char` as the sole codepoint producer. A mis-lex can never poison the rest of the stream.

### Required work
- **3.1 (M, 1.5 days)** `recognizers/operator.py:451-476` apply `find_balanced_double_parentheses` lookahead before accepting `((`; emit a single `LPAREN` on failure. `advance_lexical_state`: clamp `arithmetic_depth` to 0 on NEWLINE/SEMICOLON and reset the `fuse_words` counter (C003). Pins: `((cmd); cmd)` in all modes; tokenize-level cascade pin (space terminates words after a mis-lex); extend `tests/unit/lexer/test_arith_cmdsub_disambiguation.py` to the bare `((` form.
- **3.2 (S/M, 1 day)** `recognizers/comment.py:26` drop `{`, add `)`; consult only at word start (`literal.py:310` when `value == ""`). `operator.py:104` delimiter set → `'|&;()<>'`. Bare `]]` outside `[[` → parse error rc 2 (parser-side keyword check; C164 is lexer-classified but the decision point is the RD command-start rule — dev locates and records). Pins both directions incl. inside `$( )`.
- **3.3 (M, 1.5 days)** `operator.py:438` gate fd-prefix (digit/`{`) recognition on previous char blank/metachar; delete the `:129-131` backtracking branch; reject a digit run > INT_MAX as an fd (re-lex as word) (C170); `file_redirect.py:823/328` catch `(OSError, OverflowError)` (C080). Pins: `"a"2>f`, `${v}2>f`, backtick-2, `{v}` named form; `a2>&1` split; `echo x 2147483648>f` word.
- **3.4 (M, 1.5 days)** pass `quote_aware=True` at the four `scan_double_paren_arithmetic` call sites then delete the parameter (`expansion_parser.py:164`, `cmdsub_scanner.py:82`, `pure_helpers.py:540`, `word_scanners.py:93`); fix the `pure_helpers.py:152-154` docstring; `word_scanners.py:102` `skip_expansion_region` `${` branch → `validate_brace_expansion` (C047). Guard: a tooling test that `find_closing_delimiter` has no `${` caller. Pins vary the mode axis (the `"("` variant's shape depends on mode).
- **3.5 (S/M, 1 day)** `pure_helpers.py:380/414/435` route `\x`/`\u`/`\U` through `psh/utils/escapes.py#unicode_escape_char`, one `_read_digits` helper (C100 fold); strict-errors pin for `$'\ud800'`. NUL: drop NUL on the `$'…'` decode face and on the read/mapfile face (extend the 4B.2 handling) with the three-face pin from the C191 verification (bash 1/0/2). C013: qualify `docs/user_guide/08_quoting_and_escaping.md:267` (`\NNN`/`\xHH` match bash for values ≤ 0x7F; above, psh yields the codepoint per §17's character model) — byte model itself parked (P4).
- **3.6 (M, 1.5 days)** `cmdsub_scanner.py:570` set `command_position = True` on the depth>0 close paren; extend `test_cmdsub_case_conformance.py`. C046: make the no-progress guard unreachable for the ledger reproducer (`a["x`echo "]"`"]=v`) by fixing the backtick-in-subscript extent, and convert the guard's raise into a typed `LexerError` (PshError family) so strict-errors classifies it as a user error; amend the false "ZERO inputs" comment. C014: record the `<<` operator token offset on the heredoc spec and match by offset (`heredoc_lexer.py:325-331`); pin the latent shift with an unacceptable-delimiter row.

### Exit criteria
- The seven r23 lexer P0 repros match bash 5.3.15 in `-c`, file and stdin; the 2.3-carry "LEXER NO-PROGRESS CRASH (PRIORITY)" ledger row closes with a pin (a typed error, never a traceback).
- `grep -rn find_closing_delimiter psh/lexer` shows no `${` consumer (guard test).
- Lexer corpus (`tools/regen_lexer_corpus.py`) regenerated once at wave end; diff reviewed in the ledger.
- 6 slots, ~8 dev-days, 6 releases.

---

## 10. Wave 4 — Recursive-descent parser conformance

### Owned findings
C010 (alias → for/select loop variable corrupted — P0), C017 (newline after `for`/`select` accepted), C052 (`for ( (`/unbalanced C-style header accepted), C166 (`a=(1 2)x` → bash scalar literal), C015 (`{ list; }` body for `for`/`select`), C016 (`name=(...)` as an argument to any command), C018 (`a[0]=(1 2)` parse-time reject → runtime error), C110 (brace-body helper fold), C051 (nested `$(…)` parse-error coordinates), C111 (two diagnostic vocabularies), C039 (`$LINENO`/diagnostics wrong inside continuation-joined commands).

### Architecture target
Semantic fields come from tokens, never from source slices; the body rule for word-list loops is the same helper the C-style loop uses; error coordinates are absolute in the ORIGINAL source for nested substitutions and for continuation-joined lines.

### Required work
- **4.1 (M, 1.5 days)** `control_structures.py:220` store the token's own value as `ForLoop.variable` (lexeme only for the diagnostic); delete `skip_newlines()` at `:153` and `:475`; require `peek(1).adjacent_to_previous` on the second `LPAREN` at `:159-167` and a balance check on the close; `a=(1 2)x` → the lexer/parser treat the word as a scalar assignment when the initializer is not followed by a word boundary (bash 5.3 assigns `"(1 2)x"`). Pins: alias → `for`/`select` in three modes (`--debug-ast` shows the right name), newline rows for `for`/`select` (bash rc 2) with `if`/`while` controls.
- **4.2 (M, 1.5 days)** extract `_parse_brace_body()` (from `control_structures.py:311-329` + `commands.py:635-662`, C110) and use it in `parse_for_statement`/`parse_select_statement` when `LBRACE` follows; gate `_check_array_initialization` (`commands.py:182`) on the head word set {declare, typeset, local, export, readonly, alias, eval, let} (re-probed rc 2 on 5.3.15 for the rest); `arrays.py:172` consume `a[0]=(…)` as an `ArrayInitialization` with subscript and let the executor emit `cannot assign list to array member` rc 1. Conformance rows for all three plus `builtin declare a=(1)` (bash rc 2 — the triage's extra divergence).
- **4.3 (M, 2 days)** `parse_nested_command` carries a column offset (or the enclosing source + absolute start) so `ErrorContext` resolves the real source line (`word_builder.py:96-103`, `nested_parse.py:74`, `helpers.py:174-189`); `process_line_continuations` (`source_processor.py:583-585`) returns a joined-line→physical-line map applied by `_parse_command` so `$LINENO` and diagnostics inside a continued command are right (pin BOTH the `$LINENO` value and the command-not-found line — they differ in bash); route `consume()`'s default message through `unexpected_token_message` where the offending token is informative, keep "Expected X" where the missing token is; build the Context line from a filtered list (no doubled space). Update `psh/parser/CLAUDE.md`'s coordinate invariant.

### Exit criteria
- The five r23 P1-parser repros and P0-8 match bash in three modes; parser-differential suite (`tests/parser_differential/`) still agrees between RD and combinator on the campaign corpus.
- `$LINENO` inside a 3-line continued command equals bash's in file and stdin modes.
- 3 slots, ~5 dev-days, 3 releases.

---

## 11. Wave 5 — Systemic guards (themes C219/C220) + core invariants

### Owned findings
C066 (15 executor diagnostics bypass `error_location_prefix()`), C069 (3 expansion diagnostics), C130 (readonly diag names target not reference), C139 (test -v diag inlines the prefix), C030 (`int()` semantics in 8 builtins), C098 (`read -t inf` OverflowError), C141 (`_evaluate_binary` fold), C026 (IFS whitespace hardcoded 3×), C023 (unquoted `$*` join-then-split), C024 (`"${!x}"` with x=@), C025 (`\}` in DQ operand), C068 (`"${!arr[*]}"` joins with space), C027 (`set -u` env fallback), C028 (`set -a` misses declaration builtins), C044 (function return leaves local PATH in the command hash), C071 (`export -n` through nameref), C072 (`${!prefix*}` lists opaque env entries), C070 (temp-env over eval/source invisible to enumeration), C063 (POSIX `VAR=v exec` persistence inert), C195 (SHLVL never set).

### Architecture target
One producer per systemic rule with a ratchet that forbids the drifted spelling: `state.error_location_prefix()` for every diagnostic under `psh/executor/` and `psh/expansion/`; one `legal_number()` (base 10, sign, surrounding whitespace only; base-8 variant for umask); one `IFS_WHITESPACE` constant; `set -u`/`set -a` decided at the read/write authority (`scope_manager.lookup` / `ScopeManager.set_variable`), not in a builtin.

### Required work
- **5.1 (M, 1.5 days)** replace the 18 literal `"psh: "` prefixes (sites listed in C066/C069) with `state.error_location_prefix()`; `variable_store.py:214-217` raise with the pre-resolution name; `test_command.py:59-61` → `self.report_error`. Ratchet `tests/unit/tooling/test_error_prefix_ratchet.py`: AST scan of `psh/executor/` and `psh/expansion/` for stderr writes starting with a literal `psh: ` — allowlist empty, synthetic offender test. Script-mode conformance rows for the 5 probed diagnostics.
- **5.2 (M, 1.5 days)** `psh/builtins/numeric.py::legal_number()` (+ `legal_octal()` for umask) routed from `test_command.py:435`, `positional.py:33`, `core.py:51`, `function_support.py:1012`, `system_builtins.py:50`, `limits.py:237`, `read_builtin.py:528/545/553/562`, `mapfile_builtin.py:193/204/216`; `read -t` validates finite floats and `-u` representable fds at option parsing (C098); operator table + one try/except in `_evaluate_binary` (C141). Ratchet: no bare `int(` on an argv-derived operand in `psh/builtins/` (AST scan, allowlist = the helper). Pins: underscore digits rejected, `0o` rejected, `umask 0_77` no longer applied, `read -t inf` typed error rc 2.
- **5.3 (M, 1.5 days)** `IFS_WHITESPACE = ' \t\n\v\f\r'` in `psh/expansion/word_splitter.py` consumed by `read_builtin.py:359-360` and `word_expander.py:580`; `word_expander.py:882-904` return the element list for unquoted `*`/`[*]`; `fields.py:57-63` `target == '@'` branch; `operands.py:466` add `}` to the escapable set; `arrays.py:102/105` `_ifs_star_separator().join`. Pins vary IFS (`""`, `:`, `x`) and quoting per row (campaign lesson: vary IFS AND subscript shape).
- **5.4 (M, 2 days)** `options.py:78-80` → `if not state.scope_manager.lookup(var_name).is_set`; allexport moved into `ScopeManager.set_variable`/`create_local` (or DeclarationEngine OR-ing `VarAttributes.EXPORT`) covering `local`/`declare`/`typeset`/`readonly`/`declare -i`; `scope.py:331 pop_scope` invokes the same PATH-cache invalidation as assignment/unset (`_notify_path_changed`) — pin actual dispatch after return, nested scopes, early return, failing body; `_remove_export` resolves the nameref first; `parameter_expansion.py:480` drop the env union. Correct the two over-claiming "Full support" rows (`17_differences_from_bash.md:957` set -u, `:961` allexport) — keep "Full support" only if the extended conformance cells (shadowed export; five assignment spellings) pass; `CLAIM_TESTS` markers updated.
- **5.5 (M, 2 days)** eval/source/`.` adopt the temp-env layer as an `is_temp_env` scope (`push_temp_env_scope`), correct `scope.py:113-120` and `core/CLAUDE.md` prose; `VAR=v exec` under posix routes through `ExecutionResult.assignments_persist`, delete the inert loop `command.py:1102-1109`; set `SHLVL` at startup (inherit+1, bash rule; scrub-env pin). Guard: enumeration test (`set`, `export -p`) over the temp-env scope.

### Exit criteria
- Ratchets 5.1 and 5.2 fail on synthetic offenders and pass on the tree; `grep -rn '"psh: ' psh/executor psh/expansion` = 0 stderr sites.
- All 8 builtins reject `1_0`; `umask`/`ulimit` never apply a mis-parsed value (pin reads back the mask).
- `set -u` and `set -a` conformance cells green for every spelling in the triage; the user-guide rows are truthful.
- 5 slots, ~8.5 dev-days, 5 releases.

---

## 12. Wave 6 — Builtins, arrays, executor and invocation conformance

### Owned findings
C043 (logical `cd` enters a different directory than it reports — P1), C225 (empty CDPATH component prints destination), C074 (empty HOME/OLDPWD treated as unset); C093 (arith scalar→array promotion discards value), C094 (explicit index high-water mark), C095 (integer-array attribute phase), C096 (assoc initializer empty keys/mixed forms), C136 (`declare -p` prints `=()` for never-assigned array), C226 (design D1: one owner per mutation rule), C194 (array alias write-ban gap); C090 (`mapfile` consumes input before rejecting destination), C240 (mapfile unbounded read); C029 (printf option parsing), C076 (seven builtins reject no invalid option), C134 (six hand-rolled parsers reversed message, no usage line), C077 (`kill -n`), C078 (`wait` 127 vs 1), C075 (`source` without filename rc/usage/posix exit), C089 (`%` after flag prints literal), C200 (usage strings), C135 (builtins CLAUDE.md inventory + guard); C064 (`select` empty line), C065 (compound bg job placeholder text), C067 (`wait` interrupted by trap → 128+N), C124 (`( cmd ) | cat` signal notice), C126 (pipeline rollback except too narrow), C127 (`all_statuses[-1]` unguarded), C041 (bare cmdsub doesn't set `$?`), C042 (tilde in case patterns), C040 (`set -n` inert in `-c`); C086 (invocation `-o` cluster), C197 (`set -opipefail`), C198 (`set -o` table), C157 (bare `+`), C158 (`argv0` sentinel), C161 (unsupported bash options undocumented), C092 (script read error → EOF).

### Architecture target
Navigation derives the chdir operand from the logical destination it reports; every array/scalar transition has one owner in `VariableStore`/`array.py` exercised by one cross-entry-point matrix (assignment, arithmetic, declare/local, nameref, read/mapfile, scope exit); option parsing goes through `parse_flags` or the two base helpers that produce bash's exact invalid-option shape; the `set -n`/noexec decision is per statement.

### Required work
- **6.1 cd (M, 1.5 days)** `navigation.py:168/175`: chdir to the logical destination in `-L` mode (physical `-P` path preserved); echo only when a NON-empty CDPATH component resolved; `is None` tests at `:113-117`/`:126-129`. Pins assert `pwd -P` AND file placement (rule D5), across relative/absolute `..`, symlinks, CDPATH, empty HOME/OLDPWD.
- **6.2 arrays/variable store (M, 2 days)** `variable_store.py:225` one scalar→indexed rule (value preserved at index 0, attributes kept, nameref-targeted); `array.py:172` separate initial append cursor from initializer cursor, resolve negative indices first; `array.py:93/99/165` model expansion → attribute → commit as phases (keep the `a=(old); a=(new "${a[0]}")` control); `array.py:179` choose the initializer form once, validate keys before mutation with bash 5.3's partial-state behavior; `declare -a/-A` bare cells marked `UNSET` so `declare_format.py:74` fires. The C226 matrix test (`tests/unit/core/test_mutation_matrix.py`) covers values, flags, effective lookup, env, dispatch. C194: add the alias-mutation guard to the write-ban test or record it as closed-by-readonly-guard with the reason in `core/CLAUDE.md:162-164`.
- **6.3 mapfile/read (M, 1 day)** `mapfile_builtin.py:125/223` resolve the nameref destination, validate writability and indexed compatibility BEFORE reading; centralize the type-transition rule from 6.2; process records incrementally on the unbounded path (C240) with a peak-memory pin. Pins: descriptor position and pre-existing contents after rejection.
- **6.4 option parsing (M, 2 days)** `io.py:143-161` → `parse_flags(value_flags='v')`; `times`/`eval`/`builtin`/`source` → `parse_flags` with empty spec; `pushd`/`popd`/`dirs` emit `invalid number` rc 2; six declaration-family parsers call `self.error(f"-{flag}: invalid option")` + `self.usage(...)`; `kill -n`; `wait` malformed id → rc 1 with bash's text; `source` no filename → usage + `SpecialBuiltinUsageError(2, suppressible=True)`; remove `%` from `_CONVERSIONS` (`printf_formatter.py:150-154`) and delete the false comment; align usage strings listed in `tmp/program-2026-09/batch26/c200_raw.json` (cd, read, trap, ulimit, exec, mapfile); builtins CLAUDE.md inventory corrected + guard: every `psh/builtins/*.py` scanning a leading `-` without `parse_flags` is on an explicit allowlist (C135). Conformance rows per builtin (bash 5.3 prints a usage line after `invalid option` — the pins match 5.3's shape).
- **6.5 executor misc (M, 2 days)** `control_flow.py:650-676` `if reply == '': continue`; job text from AST source extents for subshell/brace/SubshellGroup (`subshell.py:209/307/346`, `pipeline.py:495-502`) — this also delivers the L-path job text registered at 0.2 for the signal-death announce (`report_signal_death_at` prints `message.ljust(27) + job_text`; flip the Wave 0 S-pins to parity in this slot); `job_control.py:1060-1065` return 128+signum after a fired handler; signal-death-notice suppression as a property of the forked-subshell subtree (C124); `pipeline.py:344` `except BaseException: …; raise`; `:439` empty-list branch (both fault-injection pins from the verification harness promoted to tests); `$?` from the last cmdsub when a simple command expands to zero words (C041); tilde expansion on case pattern words (C042); noexec consulted per statement (`source_processor.py:523` → executor dispatch) (C040).
- **6.6 invocation/toplevel (M, 1.5 days)** `invocation.py:231-248` `-o` takes the next argv element and keeps scanning; `set -o<attached>` follows bash (list table, then cluster) (C197); `set -o` table: add the five missing names as recognized options (`interactive-comments`, `keyword`, `onecmd`, `physical` implemented where trivial, `privileged` accepted no-op) or declare each in §17 with a "No" row probe — the dev probes and rules per name in the brief; bare `+` admitted; `argv0: Optional[str]`; `--verbose` alias + HELP_TEXT "Not supported" block + user-guide row for login/restricted; `LazyFileInput._read_line_block` propagates read errors through the scripting error boundary (fault-injection pin: before input, after complete command, partial buffered command).

### Exit criteria
- fresh F01/F04/F07–F10 observations (`observations.jsonl`) re-run → 0 mismatches for those cases.
- `test_builtin_help_sync.py` and the new C135 guard green; each builtin's `--badopt` sweep matches bash 5.3's first line and usage line.
- Signal-death pins are parity pins (FLIP-PINS rows struck); `jobs` shows `( sleep 30 ) &` like bash.
- 6 slots, ~10 dev-days, 6 releases.

---

## 13. Wave 7 — Analysis visitors, formatter, combinator tooling

### Owned findings
C033 (formatter drops `${v}` braces before brace expansion — `declare -f`→`eval` semantics change), C231 (structural vs executable round-trip contracts), C083 (DebugASTVisitor drops redirects on 10 node classes), C085 (validator `>&1` advisory inverted), C145 (validator pops context before redirects), C084 (metrics substitution counting word-anchored), C144 (backtick counted twice), C147 (ARITHMETIC_INJECTION misses `$(( ))`), C099 (security loses command behind assignment prefixes/wrappers), C211 (quoted variable labelled unquoted), C209 (`SimpleCommand.args` recomputed 17×/visit), C210 (coverage matrix gaps); C116 (DOT drops scalar fields), C117 (DOT labels HTML-escaped), C122 (sexp indentation), C177 (sexp quotes unescaped), C118 (combinator error path leaks token index), C061 (f-string syntax messages), C062 (combinator stamps no `.line`), C057 (four word-like token sets drifted), C058 (over-acceptance family), C059 (no nesting-depth guard), C019 (exponential retry in `parse_element`).

### Architecture target
The formatter is semantics-preserving under an execution-equivalence contract (structural equality is NOT sufficient); every analysis visitor is node-anchored and driven by the framework sweep; the combinator derives all word-like sets from `TokenGroups.WORD_LIKE`, stamps statement lines, and bounds nesting.

### Required work
- **7.1 (M, 1.5 days)** `formatter_visitor.py:120 _needs_brace_disambiguation` → `return part.expansion.braced` (the spelling is recorded); execution-equivalence test module `tests/unit/visitor/test_format_execution_equivalence.py` (format → run vs source → run over a corpus incl. adjacent brace expansions and `declare -f` round-trips) as the C231 contract; `_render_redirects` helper called from the 10 DebugASTVisitor handlers + `DebugASTVisitor` added to `REDIRECT_SOURCES` in `test_ast_coverage_matrix.py`; delete the inverted `>&1` check; move `_visit_redirects` above `_pop_context` in the ten validator handlers.
- **7.2 (M, 1.5 days)** `visit_CommandSubstitution`/`visit_ProcessSubstitution` node handlers in MetricsVisitor, delete `_analyze_string_features`; `visit_ArithmeticExpansion` in SecurityVisitor; shared structural command-head analysis (skip assignment prefixes, known wrappers `command`/`builtin`/`eval`/`exec`/`env`/`nice`/`time`, explicit dynamic-head result) using the typed Word quoting helpers (fixes C211 too); snapshot `args` once per handler; extend the coverage matrix parametrization to all analysis visitors (C210).
- **7.3 (M, 2 days)** `dot_generator.py:116-156` terminal else arm; DOT escaping; thread indent through `_render_sexp_list`; escape string atoms; `combinators/parser.py:229-241` drop the token index, render `expected`; `structures.py:363-366/404-407` use `unexpected_token_message`; stamp `.line` in `parse_statement_list` (fixes `$LINENO` under `--parser combinator`, C062; `show_positions` no longer a silent no-op); derive the four sets from `TokenGroups.WORD_LIKE` (C057); `many1(separators)` between statements + emptiness checks (C058, verified via the direct API); depth counter vs `MAX_NESTING_DEPTH` in `build_statement_list` (C059); delete the `pipelines.py:166-173` fallback (C019) with a timing pin (≤ 2.3× per +2 nesting levels).

### Exit criteria
- fresh F03/F14/F16 observations → 0 mismatches; `declare -f f; eval "$(declare -f f)"` runs identically for the corpus.
- Combinator `$LINENO` inside compound bodies equals RD's on the differential corpus; the r23 exponential-backtracking script parses in < 1 s at n=12.
- 3 slots, ~5 dev-days, 3 releases.

---

## 14. Wave 8 — Interactive

### Owned findings
C034 (history numbers are list positions), C151 (Meta-</Ctrl-R accept skip cmdhist join), C155 (emacs undo unreachable; undo stack survives reads), C156 (`history -a/-w` unlocked; docstring over-claims); C035 (tab completion cannot round-trip its own escaping); C036 (vi Ctrl-D), C212 (vi-insert Ctrl-R), C037 (`\w` reads process HOME / prefix match), C213 (PROMPT_DIRTRIM), C152 (prompt octal 1–2 digits at end), C097 decode half (incremental UTF-8 decoder across reads; `errors='surrogateescape'`), C214 (`psh -i` with piped stdin — declare in the user guide), C153 result from Wave 0 if still divergent.

### Architecture target
A monotonic `history_base`; completion context = raw replacement span + decoded lookup text + quote mode; one incremental decoder owned by `KeyDecoder` whose pending state survives editor/paste handoffs; prompt `\w` reads the shell variable HOME with a component-boundary match.

### Required work
- **8.1 history (M, 1.5 days)** `history_base` on ShellState never decremented; `!n` → `history[n-history_base]`; `\!` renders `history_base+len`; listing numbered from the base; `_editable` applied at the `_replace_line` boundary; bind `CTRL_UNDERSCORE` → undo, clear both stacks in `reset()`; `LOCK_EX` in `write_history`/`append_history` (single `os.write` for append) or scope the docstring. Pins via `history -s`/`-p`/`${PS1@P}` (no PTY needed) + one PTY leg for undo.
- **8.2 completion (M, 2 days)** `find_word_start` treats backslash-preceded delimiters as in-word; unescape before filesystem lookup; escape only the appended basename; represent quote mode; PTY tests for escaped spaces, quotes, `$`, backticks, backslashes, cursor-in-middle (the fresh F11 list).
- **8.3 keys/prompt/decoder (M, 2 days)** `ViKeyBindings` insert+normal `CTRL_D: 'delete_char'`, insert `CTRL_R`; `prompt.py:317-323` `state.get_variable('HOME')` + `rstrip('/') + '/'` boundary; PROMPT_DIRTRIM per bash 5.3 (no trim when the value is ≤ 0 or non-numeric — probe first); octal 1–3 digits; `key_decoder.py:285-289` `codecs.getincrementaldecoder('utf-8')(errors='surrogateescape')` persisted across reads and paste handoff — PTY pin delivering a split 2-byte sequence across two reads (the C097 PTY probe promoted). Width half PARKED (P3). C214: user-guide §17 row "`-i` with non-tty stdin: no REPL (documented)" + a No-row probe.

### Exit criteria
- `!n` after `history -d`/HISTSIZE trim resolves like bash; PTY completion of `some\ file` twice yields the same line as readline.
- The C097 PTY probe shows the correct character for every split point of a 2/3/4-byte sequence.
- 3 slots, ~5.5 dev-days, 3 releases.

---

## 15. Wave 9 — Demonstrated performance costs (theme C229)

### Owned findings
C050 (quadratic literal collection at `literal.py:190`), C048 (identifier-prefixed unmatched `[` whole-line lookahead copy), C103 (`dataclasses.replace` per token), C012 (heredoc discovery re-lexes the pending command per line — O(N²)), C128 (value-operand builder quadratic), C073 (half of every variable write in `enum.Flag` arithmetic), C088 (eager `from .shell import Shell` — 70% of `--version` startup), C239 (`LazyFileInput._read_line_block` rescans the tail).

### Architecture target
Fix measured costs only, each with a scaling pin (per-doubling ratio ≤ 2.3×) and a benchmark-tier delta vs the Wave 0 baseline. The resumable parser (C171) is NOT in scope — 9.2 uses the cheap variant.

### Required work
- **9.1 lexer hot path (M, 2 days)** segment accumulation + single join in the literal collector, tracking last-char/tilde-prefix/assignment state separately; cursor indexing and a line-end bound for the `[` lookahead; recognizers return `(type, value, start, end, extras)` and `emit_token` builds the frozen Token once. Scaling pins: long single word, 2000 `[`-words on one line, 1500-line synthetic script token count/replace count.
- **9.2 heredoc + operands (M, 1.5 days)** `heredoc_lexer.py:207-222`: on `UnclosedQuoteError` accumulate without re-lexing until the quote closes; otherwise retry from the last successful partial-lex `LexicalState` + cursor feeding only the new line (if the seed-state variant exceeds the slot, ship the UnclosedQuote variant and register the rest as a P1 successor row — say so in the brief); extend `test_heredoc_scaling.py` with a one-logical-command source. `operands.py:162-169` list accumulation, flush per protection change.
- **9.3 core/startup/input (S/M, 1.5 days)** eleven `is_*` properties against raw ints; PEP-562 lazy `psh/__init__.py`, `__main__.py` moves the Shell import below `--version`/`--help`; chunk accumulator scanning only new bytes in `_read_line_block` (after 6.6 fixed its error path). Pins: `--version` wall time budget (generous, host-neutral: < 40% of full-import time), microbench for the write path recorded in the ledger (not a test).

### Exit criteria
- `python run_tests.py --benchmarks` delta vs Wave 0 recorded; every touched path shows ≤ 2.3× per doubling in its scaling pin; token count and outputs unchanged on the lexer corpus.
- 3 slots, ~5 dev-days, 3 releases.

---

## 16. Wave 10 — Process/IO lifetime and registered successors

### Owned findings
C081 (`>(cmd)` FIFO on every platform; docs call it macOS-only), C082 (`>(cmd)` 5 s SIGALRM → `/dev/null`, exit 0, data lost), C091 (procsub acquisition leaks on fork failure); C180 (nested `( )` in a foreground pipeline member hands the tty to its grandchild — PTY-confirmed), C182 (bare `wait` ignores procsub children), C183 (PIPESTATUS collapses in brace groups), C184 (pipeline member never runs its own EXIT trap), C185 (`times`/`%P` residue), C206 (`exec {v}>&-` with v unset silently succeeds), C207 (`n<&m-` per-command move leaves source open); C190 (`$(< file)`).

### Architecture target
Process substitution branches on platform (pipe + `/dev/fd/N` on Linux, FIFO on Darwin) with ownership transferred only on success and no silent give-up; terminal control is decided once per foreground job at the launcher; bare `wait` covers the last process substitution as in bash 5.x; PIPESTATUS and EXIT-trap bookkeeping belong to the member/group that produced them.

### Required work
- **10.1 procsub (M, 2 days)** `process_sub.py:32-34` platform branch; replace the 5 s alarm with a blocking open (or non-zero exit + diagnostic); `try/finally`/`ExitStack` ownership at `:62/:144` with fault injection at pipe/flag/FIFO/fork; correct root `CLAUDE.md` Known Test Issues item 5 and `io_redirect/CLAUDE.md`. Linux path verified on the nightly (D8) — the brief states the Linux expectation (`/dev/fd/63`).
- **10.2 job/pipeline bookkeeping (M, 2 days)** JobManager: a nested subshell inside a foreground pipeline member must not re-fork into its own pgid/tcsetpgrp (PTY pin from `verify/batch24/ptyprobe3.py`); bare `wait` waits the last procsub child (register the child in a procsub-wait list at fork; `psh/expansion/command_sub.py`/`process_sub.py` fork directly by design — the list, not job status, is the mechanism); `executor/pipeline.py` single-command path stops re-stamping `state.pipestatus` for the enclosing group; pipeline members run their own EXIT trap; `times` residue (`builtins/system_builtins`) uses the CR-R2 measure; `file_redirect.py:659-668` unset/non-numeric `{v}` → `NAME: ambiguous redirect` rc 1; per-command move form closes the SOURCE permanently in the parent (bash 5.3 confirmed). Each is a LEDGER successor row from 2026-07 closing with a pin.
- **10.3 `$(< file)` (S, 0.5 day)** in `command_sub.py`: body matching `^\s*<\s*(\S+)\s*$` (after the RD parse confirms a lone input redirect with no command) → read the file (bash: no cmdsub fork; rc 1 + `No such file` diagnostic on failure); backtick spelling too; update `06_expansions.md:254`.

### Exit criteria
- The 2026-07 LEDGER successor rows named above are struck with release numbers; C180 PTY probe shows the pipeline pgid holding the tty throughout.
- Nightly green with the Linux procsub path (`/dev/fd/N` for `>(cmd)`).
- 3 slots, ~4.5 dev-days, 3 releases.

---

## 17. Wave 11 — Textbook cleanup (record-only), then Close

### Owned findings
C087 (ten `tmp/` evidence citations + ~96 campaign IDs), C133 (psh/core indexed by codename), C188 (expansion docstrings as changelogs), C108/C109/C112/C115/C123/C106 (false or truncated comments/docs), C135 (builtins CLAUDE.md inventory — landed in 6.4, re-checked), C154 (interactive CLAUDE.md REPL sketch not drift-locked), C168 (CRLF divergence undocumented), C179/C224/C228 (comment-drift themes), C143 (manager.py docstring mass), C049/C232 (state the `((…))`-interior and command-position/quote-state ownership invariants in `lexer/CLAUDE.md` with `file.py#symbol` pointers); C120, C186, C174, C165, C214 re-affirmed as declared divergences with user-guide rows and No/Partial probes; C227 bounded to `ShellState.__init__` phase extraction (C131) and `_run_command` phase naming with no behavior change; C230 (retire duplicate legacy configuration paths — census first, delete only zero-consumer paths); C236 (protocol narrowing — census + ratchet only, no migration).

### Required work
- **11.1 (M, 2 days)** promote still-live `tmp/` probes cited in code to `golden_cases.yaml` rows and cite the case name; delete dead pointers; ≤ 1 campaign ID per file (state the invariant); fix the listed false comments; drift-lock or replace the REPL sketch via `test_doc_snippets.py`; user-guide CRLF note; `test_doc_pointers` gains the symbol-half check (the 2.3 successor "`#symbol` DOC-GUARD GAP").
- **11.2 (M, 2 days)** the bounded refactors above, each guarded by the existing suites only (no new behavior pins are possible for a no-behavior change; the verifier's job is diff-audit + the full gate).

### Exit criteria
- `grep -rn "tmp/" psh/` finds no evidence citations; every subsystem CLAUDE.md passes `test_doc_snippets.py`; `docs/reviews/README.md` has no stale "active" claim.
- 2 slots, ~4 dev-days, 2 releases.

### Close ceremony (C)
Sequence doc §12 with the A6 compare-bash form (`python -m pytest tests/behavioral --compare-bash -n auto -q`), the Wave 0 oracle recorded in the close report, three seeded gates, benchmark delta vs Wave 0, every ratchet run against its offender, nightly green at the final tree, close report + LEDGER + FLIP-PINS committed, reviews index updated, campaign memory written.

---

## 18. Parked register (separately budgeted projects — NOT in this program)

| Id | Item | Why parked | Successor |
|---|---|---|---|
| P1 | C171 resumable lexer/parser (ParseSession O(k²)); C172 nested-cmdsub super-linearity | Ruled campaign-scale twice (I3 Option B; 2026-07 ruling R1). Needs a measured cost target and its own verification model; cannot fit 2-day slots. 9.2 ships the cheap heredoc variant only. | RESUMABLE-PARSER campaign |
| P2 | funsub `${ cmd; }` / `${| cmd; }` (bash 5.3 NEWS s) | New lexer+parser+expansion feature (L). Wave 0 pins `${ }` as a both-sides divergence behind `oracle_feature('funsub')`. | feature campaign |
| P3 | C097 width half — display-column model (wcwidth/grapheme policy in `line_layout.py`), C215 real-terminal rendering | Requires a defined width policy and a PTY rendering harness; the decode half ships in 8.3. | Unicode width project |
| P4 | C013 byte-model escapes (`$'\xff'` codepoint vs byte; LEDGER carry #19) | Changes psh's documented character model; 3.5 qualifies the doc instead. | design ruling first |
| P5 | C165 coproc; C196 BASH_SOURCE | Missing features, documented as such (`missing_features.md`, §17 rows re-affirmed in 11.2). | feature campaign |
| P6 | C233 two grammar implementations; C237 typed `or_else` union; C120 combinator constant factor | By design (educational combinator); documented in 11.2. | none |
| P7 | 0.4 platform rows: psh emulating x87 `long double` `%a` output | Platform, not psh; classified by predicate. | none |

Parked items appear in the LEDGER with these ids so the close report cannot count them as closed.

## 19. Risk register (deltas from the integrator plan §8, which stays in force)

| Risk | Mitigation |
|---|---|
| Wave 0 becomes a big-bang release (4 sub-slots, one gate) | Sub-slots are file-disjoint and verified by module runs; the integration branch is rebased daily; if 0.3's psh changes stall, DOWNGRADE them to version pins (the 1.x path) — the gate goes green either way. |
| Nightly source-build of bash 5.3.15 fails or is slow | Cached prefix; fallback step installs from the cached tarball; a version-assert step fails loudly rather than silently testing 5.2.21. Contingency: run the nightly conformance job on `macos-latest` with Homebrew bash as an interim (documented deviation). |
| Homebrew bumps bash to 5.3.16+/5.4 mid-program | The attestation writer refuses on major.minor drift and records the patch level; a patch-level bump is allowed but logged; a minor bump is a Wave 0-style re-baseline slot before any further release. |
| Slots bounce repeatedly (the prior campaign's 5–10 round slots) | D3: two bounces → split. Briefs carry a "verification axes" section so the dev pins what the verifier will attack. |
| bash 5.3 semantics chosen in Wave 1 turn out partially wrong (no bash source fetched for the trap rule — 30+ probes only) | 1.2's boundary rows are pinned as observed; the brief states "probe-derived, not source-derived"; if a later nightly/user report contradicts, the row flips with a ruling, not a silent edit. |
| Parallel-session uncommitted files (`docs/reviews/README.md` modified; two untracked reports) | Wave 0 commits them as its first task with the user's go; nothing else touches `docs/reviews/README.md` until then. |
| gh account (`philipwilsonTHG` read-only on psh) | Launch checklist: `gh auth switch --user philipwilson` before any PR/merge. |
| Lexer corpus regeneration hides a regression | Corpus diffs reviewed in the ledger at wave end; 9.1 must show identical token streams on the corpus. |
| Interactive/PTY facts ruled from python-pty only | Carried rule: tmux/PTY leg with independent probe construction for 2.1 (title), 8.x, 10.2. |
| Disk (114 GB free now) / ENOSPC on the gate | Carried: ≥ 10 GB check in the ceremony script; scratch under project `tmp/`. |

## 20. Launch checklist (all require the explicit user go)

1. User go received for Wave 0.
2. `gh auth status` shows `philipwilson` active (`gh auth switch --user philipwilson`).
3. `/opt/homebrew/bin/bash -c 'echo $BASH_VERSION'` = `5.3.15(1)-release`; `/bin/bash` never on the oracle ladder (existing ratchet green).
4. Untracked reports + evidence dir + modified `docs/reviews/README.md` committed (Wave 0 task 0.1 first commit), index test green.
5. Evidence tree created with LEDGER (296 rows: 245 C + 51 gate), FLIP-PINS, wave-manifest, nightly-status; no TBD owner.
6. Integration branch `fix/oracle-5.3-baseline` cut from `origin/main` @ `6459f1a6`; four sub-slot briefs written with verification axes; verifier harness preamble points at THIS plan.
7. Wave 0 exit: attestation schema 2 with oracle 5.3.15, gate green, nightly green, v0.780.0 tagged by `release-tag.yml` (no manual tag).
8. First Wave 1/2/3 briefs written; merge-train order chosen by verifier availability.

Until item 1, this document is a plan of record only.
