# Correctness Program 2026-09 — Integrator's Campaign Plan (reappraisal #23 ∪ fresh appraisal 2026-09-06)

- **Date:** 2026-09-06
- **Status:** PLANNED, NOT LAUNCHED. Nothing executes without an explicit user go.
- **Launch base:** `origin/main` @ `6459f1a6` (v0.779.0).
- **Oracle (USER DECISION, binding):** `/opt/homebrew/bin/bash` = GNU bash **5.3.15(1)-release**. Never `/bin/bash` (3.2). Bash 5.2 is no longer on the host and is never consulted again; anything "verified against 5.2" is a historical coordinate.
- **Findings source:** the 245-row canonical inventory (C001–C245) re-verified at HEAD vs 5.3.15 on 2026-09-06, folding `docs/reviews/ground_up_reappraisal_23_correctness_textbook_2026-08-09.md` (r23, verified 2026-08-09 vs 5.2.26) and `docs/reviews/fresh_appraisal_2026-09-06.md` (16 findings, all reproduced). Plus the 51-node GATE TRIAGE of the red gate.
- **Governing documents (authority order):** (1) this plan; (2) `boundary_remediation_integrator_plan_2026-07-21.md` §3 roles, §5 verification standard, §7 ceremony — ADOPTED by reference; (3) `boundary_remediation_campaign_sequence_2026-07-21.md` §3 standing rules 1–10 and wave format — ADOPTED by reference; (4) `.claude/skills/psh-release/SKILL.md` and `CLAUDE.md` "Release workflow" — no manual `git tag`, `gate_attestation.json` is the FINAL commit, the local gate IS the gate.

---

## 1. Decision

Yes: fold the two appraisals into ONE program. Execute it as a **harm-ordered slot campaign** on the merge train the previous two campaigns proved (one dev per slot in an isolated worktree, adversarial verification to zero, local gate, attestation, release). Ordering inside the program is by **user-visible harm**, not by subsystem or by reviewer severity:

1. **Wave 0** — the gate is red and the oracle moved: restore a green, version-identified gate first (nothing else can be verified until then).
2. **Wave 1** — silent data loss and wrong-target defects (wrong directory, wrong executable, dropped pipeline commands, wrong redirect target, changed serialized semantics, silently-wrong values/fields, safety options that silently do not fire).
3. **Wave 2** — crashes and internal defects (Python exceptions reaching the user, stream-corrupting mis-lexes, fault-path leaks, tty-control loss, one security sink).
4. **Wave 3** — conformance (loud divergences: parse rejections of valid input, wrong status codes, wrong messages, missing options, interactive gaps; includes the bash-5.3 semantics adoption that Wave 0 pinned as declared divergences).
5. **Wave 4** — measured performance costs only.
6. **Wave 5** — design/textbook (themes, dead code, doc drift, design generalizations).
7. **Ceremony C** — close at one final tree.

Within a wave, slots are small, independent, and each ships as its own release. The integrator may combine adjacent trivial slots at dispatch time but never merges two distinct harm classes into one diff.

## 2. Campaign outcome

The program succeeds when:

1. The local gate is green and its attestation names the oracle (`bash 5.3.15`) — and a future oracle change fails ONE named test, not 44 unrelated ones.
2. Every inventory row with status `live` (defect or perf) and both `oracle_changed` rows are either closed by a wave slot or explicitly parked in §9 with a reason. No `fixed`/`not_reproducible` row is queued.
3. Every fix is pinned red-on-base against bash 5.3.15 (or by fault injection / PTY / counter where bash comparison is inappropriate), and every probe still worth keeping is a `golden_cases.yaml` row or a conformance test — not a `tmp/` file.
4. Every user-guide compatibility claim touched is corrected in the same slot (the claims meta-test polices over-claiming only; under-claiming rows are fixed by hand).
5. A clean checkout of the final commit contains the plan, ledger, flip-pin registry, oracle policy, benchmark deltas, and a close report whose headline agrees with its tables.

Out of scope: bash feature parity for things psh documents as unsupported (§9), cosmetic refactors without a measured payoff, and the resumable-parser project (successor campaign per the prior campaign's ruling R1).

## 3. Standing rules — deltas only

Sequence-doc rules 1–10 and integrator-plan §3/§5/§7 apply unchanged. Deltas:

- **D1 (replaces A12).** The differential contract is "bash **5.3.15**, resolved by `tests/harness/shell_oracle.py#resolve_bash`, version recorded in the attestation and policed by `tests/harness/oracle_policy.py`". A slot brief, docstring, or test comment that cites "bash 5.2" is a bounce unless it is explicitly a historical note.
- **D2 (from C244).** A pin must assert the **actual target**: the cwd/`pwd -P`/file placed (cd), the executable actually dispatched (PATH), the bytes actually written to the fd (redirects), the input actually consumed (mapfile/read), the behavior of the re-parsed serialization (`declare -f`/`--format`). A test that checks only the reported value, the return code, or AST equality does not close a Wave 1 row.
- **D3 (from the ENV triage).** The gate runs OUTSIDE any filesystem/process sandbox; the four ENV tests gain honest skips (`pytest.skip` on a probed precondition) so a sandboxed run reports skips, not psh failures.
- **D4.** Every psh behavior change that follows a bash 5.3 change cites the `CHANGES` item (`/opt/homebrew/Cellar/bash/5.3.15/share/doc/bash/CHANGES`) in the test docstring; when no `CHANGES` item exists, the docstring says "empirical, 5.3.15".
- **D5.** Probe invocations use `env -u PWD -u OLDPWD` from a fresh `mktemp -d` (psh trusts an inherited stale `$PWD`); the harness does this — direct `subprocess` in oracle-bearing modules stays banned by `test_no_direct_spawn_in_oracle_modules.py`.
- **D6.** Each slot brief names its harm class (silent-loss / crash / conformance / perf / textbook) and the verifier attacks that class first: a Wave 1 verifier must construct a "did the data go to the wrong place" row the dev's suite does not contain.
- **D7.** Version-sensitive rows carry `min_bash: "5.3"` (golden) or `@pytest.mark.oracle_min("5.3")` (pytest) so an oracle below the policy version SKIPS them with a count rather than failing them (transition safety for the Linux nightly).

## 4. Status and dependency order

| Order | Wave | Slots (est.) | Depends on |
|---:|---|---:|---|
| 0 | Oracle identity and green gate | 3 | none |
| 1 | Silent data loss and wrong-target | 19 | Wave 0 |
| 2 | Crashes, internal defects, stream corruption, security | 9 | Wave 0 (may interleave with late Wave 1 slots at integrator discretion) |
| 3 | Conformance (incl. bash-5.3 adoption flip-pins) | ~30 | Wave 2 |
| 4 | Measured performance | 6 | Wave 3 |
| 5 | Design and textbook | ~8 | Wave 4 |
| C | Ceremony | 1 | Wave 5 |

Wave N+1 does not merge until Wave N's exit criteria hold. Estimated total: ~75 releases (v0.780.0 →).

---

## 5. Wave 0 — Oracle identity and green gate

### Owned findings
- C242 Local gate red at 6459f1a6 (52 failed; oracle drift, not psh regressions)
- C241 Oracle comments in tests target 5.2 while the oracle is 5.3.15
- C243 docs/reviews index test fails on the untracked r23 report
- C238 Documentation indexes carry stale "latest/active" claims
- C169 Untracked junk files `f`, `f1`, `f2` in repo root
- C153 `\#` command number (oracle_changed) — re-derive against 5.3.15
- C181 `-c` + `set -m` job notice (oracle_changed) — re-derive; closed by 0.2 (the notice no longer exists on 5.3; `jobs` in `-c` now lists the finished job once)
- All 51 GATE TRIAGE nodes (retunes below)

### Architecture target
One oracle identity: `resolve_bash()` already records `BashOracle.version`; make it a policed fact. The attestation testifies to WHICH bash the gate compared against. Version-sensitive expectations are marked, not hidden.

### Required work

**0.1 — Oracle identity, ENV hardening, PREMISE/FORMAT retunes (1 release, docs+tests+harness only, no psh behavior).**
1. `tests/harness/oracle_policy.py`: `EXPECTED_ORACLE_MINOR = (5, 3)`; `tests/unit/tooling/test_bash_oracle_resolution.py::test_resolved_oracle_matches_policy` fails with the message `oracle drift: resolved bash X, policy 5.3` — the ONE test that goes red next time.
2. `run_tests.py#build_attestation`: schema 1→2, new `"oracle": {"path", "version"}` (from `resolve_bash()`); `tools/verify_gate_attestation.py` REQUIRED_KEYS gains `oracle`; `tests/unit/tooling/test_gate_attestation.py` pins both; the phase banner prints the oracle line.
3. Nightly oracle: `.github/workflows/nightly.yml` builds bash 5.3.15 from the GNU tarball (cached by version key) and exports `BASH_PATH` — the nightly compares against the SAME oracle as the gate (pin, not classify). D7 markers remain as the transition safety so an unpinned run skips the version-sensitive rows; the `oracle_policy` test makes any mismatch a single named failure.
4. `min_bash` key honored in `tests/behavioral/test_golden_behavior.py` (skip when oracle < key); `oracle_min` marker in `tests/conftest.py`.
5. ENV hardening (skips, not expectation changes): `test_bg_actually_resumes_a_job_stopped_behind_the_shells_back` (skip when `ps -o stat= -p $$` is empty); `test_socket_earlier_bash_126_psh_runs_later` (`except PermissionError: pytest.skip`); `test_cap_kill_reaches_a_writer_that_left_the_process_group` (skip when `ps -eo pid=,ppid=` cannot spawn); golden `r18t2_builtins_history_write_to_stdout` (`requires_dev_fd: true`, skipped when a probe open of `/dev/stdout` fails); `test_redirect_procsub_suppression_is_a_declared_divergence` lengthen the write-row poll to 30×0.1 s.
6. PREMISE/FORMAT S-edits exactly per triage: `test_divergence_procsub_compound_render_residual` case tuple → `'<(case x in y)\n        echo n\n    ;;\nesac)'`; `test_divergence_sq_in_dq_readback_outcome` → parity pin (rename `test_sq_in_dq_readback_round_trips`; record oracle-side flip in FLIP-PINS.md:47); `test_unlexable_subscript_route_audit[let_arith]` bash branch → rc 0 / `declare -A a` / `not a valid identifier`; `TestCompositeQuoting::test_tilde_expands_in_key` → `env={'HOME': '/probe-home'}` with the installed-readline comment (do NOT copy this into psh); `test_invalid_regex_diagnostic_is_psh_only` → both-diagnose wording pin; `test_bad_substitution_conformance` drop `${ }`/`${ :-x}` from BAD_CASES + declared-divergence pin for funsub (bash `echo ${ echo fs; }` → `fs`, psh rc 1) with `min_bash: "5.3"`; the five signal-death FORMAT tests (`test_pipeline_signal_death.py` ×3, `test_signal_killed_diagnostic.py` ×2) → S path: `bash.stderr == strsignal(SIGTERM).ljust(27) + '<job text>\n'` with psh's bare-form pin kept, docstrings + `psh/executor/job_control.py:626-628` reworded; `test_socket_earlier…` docstring "5.2-verified" → "5.2- and 5.3.15-verified".
7. Docs: commit r23, the fresh appraisal + its evidence dir, and THIS plan; index all three in `docs/reviews/README.md` (coordinate the one-row conflict with the parallel session's uncommitted README edit — never overwrite it); refresh stale "latest/active" lines (C238); remove `f`, `f1`, `f2` after confirming origin (C169).
8. C241 census: `grep -rn "bash 5\.2" tests/ psh/` → per-file list in the ledger; rewrite only the ones touched by triage now, the rest as a ratchet (`tests/unit/tooling/test_oracle_version_comments.py` forbids NEW "bash 5.2" mentions).
9. Re-derive C153 (`\#`) under a real PTY against 5.3.15 (bash `CHANGES` 5.3-alpha item rrrrrr) and C181; write the rulings in the ledger. C153 transfers to slot 3.9 ONLY if still divergent.
10. Evidence tree: `docs/reviews/evidence/program_2026_09/` with `LEDGER.md` (245 rows → owner/wave/disposition), `FLIP-PINS.md`, `wave-manifest.json`, `oracle-baseline.md` (gate numbers at 6459f1a6 vs 5.3.15).

**0.2 — Presentation retunes to bash 5.3 (1 release; verified psh one-liners).**
- `psh/builtins/signal_handling.py:24` synopsis → `trap [-Plp] [[action] signal_spec ...]` + implement `-P` (flags `lpP`; `-P` no operand → `trap: -P requires at least one signal name` rc 2; `-pP` → `cannot specify both -p and -P` rc 2; prints bare action per operand; help OPTIONS gains `-P`); update `tests/unit/builtins/test_trap_flags.py:73`, `tests/unit/builtins/test_error_location_prefix.py:39`, `docs/user_guide/04_builtin_commands.md:1107`; `test_builtin_help_sync.py` stays green because `-P` is real. Closes 4 nodes.
- `psh/builtins/shell_options.py#_print_option` width 15→20 for shopt-table prints, 15 only for `-o` bare listings; `set -o` untouched; pins: `test_shopt.py:79`, `test_shopt_set_o.py:23,29,191,207,213,249`, `golden_cases.yaml:2378,8910`. Closes 5 nodes.
- `psh/executor/job_control.py:279/:280/:683` `:<24` → `:<27`. Closes 7 width nodes.
- `psh/builtins/job_control.py:96-98` delete the `command_mode` DONE filter; rewrite comment :85-95; rename the two `_suppressed_c_mode` tests to `_listed_once_c_mode`; CHANGELOG note that the v0.692 "-c+monitor boundary notice" deferral is discharged (C181 closed).
- `psh/builtins/hash_builtin.py:80-83` delete the empty-table short-circuit (CHANGES ggggg); conformance row uses `2>/dev/null`; invert `test_hash_builtin.py::test_dash_d_on_empty_table_silently_succeeds` → `_reports_miss`.

**0.3 — Status retunes + declared-divergence pins (1 release).**
- Usage-error status: `psh/core/internal_errors.py#special_builtin_usage_discard` → `SystemExit(1)` in command_mode, `TopLevelAbort(2, errexit_immune=True)` otherwise; `psh/builtins/navigation.py:103` `return 2`; retune `test_cd_too_many_arguments` (`rc=2`), `test_exit_too_many_args_does_not_exit` (`after=2`), core.py:59-60 comment; `-c` pins (golden `bcontract_exit_too_many_discards`, `test_bcontract_argument_policy.py:78/105`) stay. NEW row TRIAGE-N4: golden `bcontract_exit_bad_first_operand_exits_two` is wrong vs 5.3 (`exit abc; echo rc=$?` → `rc=2`, continues) — retune with the same helper.
- PATH wording: `psh/executor/strategies.py:148` `empty_path` → `unset_path = not state.scope_manager.lookup('PATH').is_set`; rename kwarg + rewrite `format_exec_failure` docstring (CHANGES 5.3-alpha p.); rename the conformance and r3 unit tests per triage; add `local PATH=` row.
- Closed fd 0: `psh/__main__.py` STDIN branch — `sys.stdin is None` → `psh: error creating buffered stream: Bad file descriptor`, exit 126; tests `test_plain_with_closed_fd0`/`test_dash_s_with_closed_fd0` → 126. Sibling crash `read x <&-` (AttributeError at `input_reader.py:429`) is TRIAGE-N1 → Wave 2 slot 2.7.
- DECLARED-DIVERGENCE pins (each a FLIP-PINS row owned by Wave 3 slot 3.1, all `min_bash: "5.3"`): trap entry-status (4 nodes in `test_exit_trap_status_precedence_conformance.py`, incl. the must-hold), posix special-builtin exits (`export 1bad=x`, `readonly 1bad=x`, `unset r` readonly, `eval 'set -q' || …` boundary, `export é=1` unicode), posix function names (`function é`, `9x()`, `export -f é`), `declare -i` on readonly (+ `test_local_builtin.py::test_attrs_only_add_integer_allowed`). Each pin asserts BOTH sides' current output so it is red the moment either side moves.
- Golden rows for every retuned command; module docstrings "Verified against bash 5.2" → 5.3.15 (D1).

### Exit criteria
- `python run_tests.py --parallel` green, unsandboxed, at the 0.3 tree; `gate_attestation.json` schema 2 carries `oracle.version == "5.3.15(1)-release"`; `python -m pytest tests/conformance -q` and `python -m pytest tests/behavioral --compare-bash -n auto -q` green.
- `test_resolved_oracle_matches_policy` demonstrated red with `BASH_PATH=/bin/bash` (mutation check on the guard).
- Nightly: first scheduled run at the 0.3 SHA shows the built 5.3.15 in "Show bash version" and the same phase censuses as the local gate (D7 skip count = 0 when pinned).
- Ledger has 245 rows, no TBD; FLIP-PINS lists every 0.3 divergence pin with its Wave 3 owner; C153/C181 rulings written.
- Size: 3 releases (S, S, M).

---

## 6. Wave 1 — Silent data loss and wrong-target

### Owned findings
- C001 Function/eval/source body as pipeline member drops every command after the first external command
- C032 `1>&-` closing fd 1/2 defeats a LATER reopen in the same redirect list (EBADF, silent loss)
- C031 Redirect targets for fd ≥ 3 expanded twice for in-process builtins
- C043 Logical `cd` can enter a different directory from the one it reports
- C225 `cd` through the empty CDPATH component wrongly prints the destination
- C044 Returning from a function leaves executable resolution using its local PATH
- C033 Formatter drops `${v}` braces before a brace expansion (`declare -f` → eval round-trip changes semantics)
- C010 for/select loop variable corrupted when the header comes from an alias
- C004 `is_comment_start`: `echo a{#b` truncated / `(cmd)#c` rejected
- C005 fd-prefix redirect recognized mid-word (digit/`{` after quote/expansion stolen as IO_NUMBER)
- C006 `>&` branch backtracks INTO the previous token (`a2>&1`)
- C020 Trailing redirect on `[[ ]]`/`(( ))` silently split into a second statement (combinator)
- C040 `set -n` inert in `-c` mode
- C041 A bare command substitution does not set `$?`
- C042 Tilde not expanded in case patterns → wrong branch silently
- C022 Backgrounded command inside pipeline/redirected compound gets `/dev/null` stdin
- C082 `>(cmd)` child gives up after 5 s, opens `/dev/null`, exits 0 having processed NO data
- C030 Python `int()` semantics leak into 8 builtins; umask/ulimit silently apply wrong values
- C098 `read -t inf` / huge `-u` escape as OverflowError (same helper, co-located)
- C027 `set -u` consults `state.env` (exported shadow silently passes)
- C028 `set -a` misses all four declaration builtins (child silently does not see the variable)
- C090 mapfile consumes input before rejecting its destination; corrupts array attributes
- C093 Arithmetic promotion scalar→array discards the scalar value
- C094 Explicit array indices set a high-water mark for subsequent elements
- C095 Integer-array initialization applies attributes at the wrong phase
- C096 Associative initializers accept invalid empty keys and mixed forms
- C023 Unquoted `$*`/`${a[*]}` join-then-split diverges under empty IFS
- C024 `"${!x}"` where x names `@` collapses positionals to one field
- C025 `\}` not unescaped in DQ operand; escaped text stored by `:=`
- C026 IFS whitespace hardcoded as `' \t\n'` (missing `\v\f\r`), duplicated ×3
- Design inputs: C222 (ordering/re-entry theme), C226 (write-site invariants), C231 (executable round-trip contract), C179 (executor comment drift — falls out of 1.1)

### Architecture target
A fact that decides WHERE data goes (cwd, executable, fd, loop variable, branch, serialized text, field boundaries) is decided once, by its owner, at the right time, and every consumer reads that decision. Pins assert the actual target (D2).

### Required work (one slot = one release unless noted)
- **1.1 Pipeline-member flag** — `psh/executor/strategies.py:605` exec branch fires only for the member's OWN dispatch: make `context.in_pipeline` one-shot at `pipeline.py` member launch (consumed by the first `SimpleCommand` strategy), so `_function_frame` (`function.py:196`), eval and source frames never inherit it; delete the "nothing left to do" comment (C179). Pins: function/eval/source bodies as pipeline members in `-c`/script/stdin, `pipefail` rc, `--debug-exec` shows no exec; golden rows.
- **1.2 Close-then-reopen** — `psh/io_redirect/manager.py:518#_swap_closed_output_streams` installs `_RawFdStream` (`swap_output_stream_reopenable`) instead of `_ClosedStream`; rewrite the docstring premise. Pins: `{ … } 1>&- 1>f`, `2>&- 2>f`, function/if/while forms, fd 1 and 2, file contents asserted.
- **1.3 Plan once** — `manager.py:955#_builtin_redirect_fd_level` applies the already-resolved plan (`_clear_user_fds_from_parking` + `saved_fds_for_plan` + `apply_fd_plan`); a counter guard asserts `planner.plan` runs once per `RedirectOp` (mutation check: re-add the second plan call, guard goes red). Pins: cmdsub-in-target counter file, procsub fork count, noclobber target identity.
- **1.4 Logical cd** — `psh/builtins/navigation.py:168-175`: `os.chdir` operand derived from the logical destination in `-L` mode, physical path only under `-P`; CDPATH echo only for non-empty components (C225). Pins assert `pwd -P`, `os.getcwd()`, and a file written after `cd ..` (D2), across relative/absolute `..`, symlinks, CDPATH.
- **1.5 PATH cache on scope exit** — `psh/core/scope.py:331#pop_scope` invokes the same `_notify_path_changed` policy (`:156`) as assignment/unset when the effective PATH binding changes; pins dispatch the actual probe executable after `local PATH`, nested scopes, early `return`, failing bodies, temp-env.
- **1.6 Executable round-trip** — `psh/visitor/formatter_visitor.py:120#_needs_brace_disambiguation` returns `part.expansion.braced` (source spelling wins); `psh/ast_nodes/words.py:143` `__str__` honors `braced`; new `tests/unit/visitor/test_executable_roundtrip.py`: for a corpus, `psh --format` output and `eval "$(declare -f f)"` produce identical stdout to the original (C231 contract stated in `psh/visitor/CLAUDE.md`).
- **1.7 Alias loop variable** — `control_structures.py:220` stores the token's own `value` as `ForLoop.variable` (source slice only for the diagnostic); same for select; pins in all three modes.
- **1.8 Lexer wrong-target trio** — `comment.py:26` at-word-start model (drop `{`, add `)`, consult only when `value == ""`); `operator.py:438` gate fd-prefix on previous char blank/metachar; delete `operator.py:129-131` backtracking. Pins: `echo a{#b`, `(cmd)#c`, `"x"2>f`, `${v}2>f`, `` `c`2>f``, `{v}>f` mid-word, `a2>&1` (file contents asserted, D2).
- **1.9 Combinator trailing redirects** — `special_commands.py:161-165/:245-249` consume `many(redirection)` after `))`/`]]` (both nodes have `redirects`); pins via the direct combinator API AND `--parser combinator -c` (C178 framing), incl. the `while (( i-- )) >/dev/null` termination row.
- **1.10 noexec + bare-cmdsub status** — `source_processor.py:523` re-checks `noexec` per statement dispatch; `$?` becomes the last cmdsub's status when a simple command expands to zero words (executor `command.py` empty-argv path). Two independent pins/rows; may ship as two releases.
- **1.11 Tilde in case patterns** — pattern-word expansion applies tilde (as `[[ ]]` already does); pins `~`, `~/x`, `~+`, alternation, quoted control.
- **1.12 Async stdin** — `process_launcher.py:81#AsyncJobPolicy.apply` takes "fd 0 is the shell's original stdin" and suppresses the `/dev/null` redirect when fd 0 came from a pipe or enclosing compound redirect; pins read actual bytes.
- **1.13 procsub write-side** — `process_sub.py:147-167`: blocking open or non-zero exit; never substitute `/dev/null` silently; pins: 6 s late open processes all lines. (C081 platform branch stays Wave 3.)
- **1.14 legal_number** — one `psh/builtins/_numbers.py#legal_number` (base-10, sign, surrounding whitespace only; int64 range) + octal twin for umask; route `test_command.py:435`, `positional.py:33`, `core.py:51`, `function_support.py:1012`, `system_builtins.py:50`, `limits.py:237`, `read_builtin.py:528/545/553/562` (finite timeout, representable fd → C098), `mapfile_builtin.py:193/204/216`; static guard: no bare `int(` on user operands under `psh/builtins/` (allowlist with synthetic offender). Pins assert the applied umask/ulimit value.
- **1.15 `set -u` authority** — `options.py:78-80` asks `scope_manager.lookup(name).is_set`; conformance cell with a shadowed export; correct `17_differences_from_bash.md:957`.
- **1.16 allexport** — decision moves into `ScopeManager.set_variable`/`create_local` (or `DeclarationEngine` ORs EXPORT when `allexport`, not a dynamic special, not an array); conformance across all five spellings; correct `17_differences_from_bash.md:961`.
- **1.17 mapfile preflight** — resolve nameref target, validate writability and indexed compatibility BEFORE reading (`mapfile_builtin.py:125/:223`); one attribute-transition owner so `-aA` cannot be produced; pins assert the fd position after rejection and the untouched assoc contents (D2).
- **1.18 Array write invariants** — `variable_store.py:225` scalar→indexed rule preserving the scalar; `executor/array.py:172` initial-append cursor separate from explicit-index cursor (negative indices resolved first); `:93/:99/:165` phases expansion → attribute → commit with shared integer-append; `:179` initializer form chosen once, keys validated before mutation. C226 matrix test (assignment / arithmetic / declare / local / nameref / read / mapfile / scope exit × value, flags, lookup, env, dispatch). May split into two releases (promotion+HWM; integer+assoc).
- **1.19 Expansion field integrity** — `word_expander.py:882-904` unquoted `*`/`[*]` returns the element list (join only when quoted); `fields.py:57-63` `target == '@'` → positional list; `operands.py:466` escapable set gains `}`; `IFS_WHITESPACE = ' \t\n\v\f\r'` constant consumed by `word_splitter.py:47`, `read_builtin.py:359`, `word_expander.py:580` (guard: no other literal). Rows vary IFS (`""`, `:`, `x`) and mode.

### Exit criteria
- Every Wave 1 row's discriminator (from the inventory verify notes) passes against 5.3.15 in `-c`, script and stdin modes; each slot's pins were shown RED on the slot base (replayed by the verifier).
- D2 holds: each slot has at least one pin asserting the actual target, and the verifier produced at least one novel wrong-place row per slot.
- Guards shipped with synthetic offenders: plan-once counter (1.3), `int(` ratchet (1.14), IFS literal ratchet (1.19), executable round-trip corpus (1.6).
- Gate, ruff, mypy, conformance, compare-bash green at the wave's final tree; user-guide rows corrected in 1.15/1.16.
- Size: 19 slots, mostly S/M; 1.18 and 1.3 are M+.

---

## 7. Wave 2 — Crashes, internal defects, stream corruption, security

### Owned findings
- C008 `$'\uD800'` → UnicodeEncodeError (internal defect under strict-errors)
- C046 Lexer no-progress RuntimeError CLI-reachable; guard comment asserts a false "ZERO inputs" census
- C080 fd prefix ≥ 2^31 escapes as OverflowError
- C170 Lexer accepts an fd prefix > INT_MAX as a redirect
- C002 `((` lexed as DOUBLE_LPAREN without checking for a matching `))`
- C003 Cascade hardening: unbalanced DOUBLE_LPAREN leaves `arithmetic_depth > 0` for the rest of the stream
- C007 `$((…))` extent scan is quote-blind
- C009 `)` closing a function header inside `$(…)` drops command position
- C021 Bare process substitution at command position yields a non-Command node ("Unimplemented node type")
- C059 Combinator: deeply nested input raises RecursionError instead of ParseError
- C038 Terminal title writes `$PWD`/command text into OSC 0 unsanitized (escape injection — SECURITY)
- C091 Process-substitution acquisition leaks resources when fork fails
- C126 Pipeline rollback except-clause too narrow (sync pipes leak)
- C127 `all_statuses[-1]` unguarded against empty-list state
- C092 Script-file read error silently converted to EOF
- TRIAGE-N1 `read x <&-` raises AttributeError/ValueError (`input_reader.py:429/:124`); bash: `read: 0: read error: Bad file descriptor`, rc 1
- C180 Nested `( )` in a foreground pipeline member hands the tty to its own grandchild (PTY-confirmed)
- Design inputs: C221 (extent-scanner theme), C102 (registry converts every recognizer exception to RuntimeError — fix the carve-out here since it is the crash boundary)

### Architecture target
No Python exception reaches the user; every lexer extent decision goes through one quote-aware authority; fault paths own what they acquire; terminal ownership follows the job, not the frame.

### Required work
- **2.1** `pure_helpers.py:380/:414/:435` route `\x`/`\u`/`\U` through `psh/utils/escapes.py:53#unicode_escape_char`; delete the duplicate; pins for surrogates, > 0x10FFFF, locale-independence.
- **2.2** Lexer no-progress: reproduce the registered ledger input (`boundary_remediation_2026-07/LEDGER.md` Part D 2.3 carry), fix the recognizer that fails to advance, replace the `modular_lexer.py:264-271` comment with the invariant + pointer; widen `registry.py:78-85` carve-out to `(RecursionError, PshError, SyntaxError)` (C102) with a fault-injected pin.
- **2.3** fd > INT_MAX: lexer re-lexes the digit run as a word when > INT_MAX; `file_redirect.py:823/:328` catch `(OSError, OverflowError)`; pins `echo x 2147483648>f` and `exec 4294967296>f`.
- **2.4** Extent scanners (three releases): (a) `operator.py:451-476` apply the `))` lookahead before accepting `((`, emit LPAREN on failure; `advance_lexical_state` clamps `arithmetic_depth` to 0 on NEWLINE/SEMICOLON and resets the fuse counter (C003) — tokenize-level pin that the suffix after a deliberate mis-lex is intact; (b) `scan_double_paren_arithmetic` quote-aware at all four call sites, parameter deleted, `pure_helpers.py:152-154` docstring fixed — pins vary mode (rc 2 vs `m[(]: command not found`); (c) `cmdsub_scanner.py:570` `command_position = True` on depth>0 header close; extend `test_cmdsub_case_conformance.py`.
- **2.5** Combinator: remove `.or_else(self.process_substitution)` from `special_command` (C021); depth counter in `build_statement_list` vs `MAX_NESTING_DEPTH` (C059); pins via direct API and `--parser combinator`, under strict-errors.
- **2.6** OSC-0 sanitization at `title.py:21` (`str.translate` stripping `< 0x20`, `0x7f`, `0x9b`); optional `shopt`-style gate; PTY pin with a crafted `$PWD` basename. Flag to user as security-relevant in the CHANGELOG.
- **2.7** Fault-path integrity: `process_sub.py:62/:144` own each resource via `ExitStack` transferring on success; `pipeline.py:344` `except BaseException: rollback; raise`; `:439` explicit empty branch; `input_sources.py:545` read error propagates through the scripting error boundary (rc ≠ 0, message); `input_reader.py:429` handles `sys.stdin is None` → `read: 0: read error: Bad file descriptor` rc 1 (TRIAGE-N1). Fault-injection tests (monkeypatched `pipe`/`mkfifo`/`fork`/`launch`/`read`) assert no fd leak (`/dev/fd` census) and no orphan.
- **2.8** Terminal control: `JobManager` gives the tty to the pipeline's pgid once; nested subshell members neither re-fork into a new pgid nor call `tcsetpgrp`; PTY pin (`tmux` or pty leg per §3) checking `tcgetpgrp` from inside the grandchild; reason about Linux (nightly watch row).

### Exit criteria
- Under `PSH_STRICT_ERRORS=1`, the full crash corpus of this wave (every repro from the inventory + TRIAGE-N1) exits with a shell error, never a traceback; a `tests/system/test_no_internal_defects_corpus.py` runs the corpus.
- Extent-scanner rows agree with 5.3.15 in all three modes; tokenize-level suffix-intact pin (C003) green; `find_closing_delimiter`/`scan_double_paren_arithmetic` callers censused in the ledger.
- Fault-injection legs leave no fd/child behind (counted); PTY leg for 2.8 recorded with SHA.
- Size: 9 slots (2.4 = 3 releases), S/M.

---

## 8. Wave 3 — Conformance

### Owned findings
- **3.1 bash-5.3 adoption (flip Wave 0.3 pins):** trap entry-status (POSIX interp 1602, `trap_manager.py:449-451` records `(status, function depth, source depth)`; `builtins/core.py:39-41` applies at trap top level for EXIT/signal/ERR; DEBUG keeps current `$?`; prose in `psh/core/CLAUDE.md:744-757`); posix special-builtin exits (`environment.py` ExportBuiltin ~:152 and UnsetBuiltin ~:665/709/730/775, `function_support.py` readonly sites ~:373/:516 raise `SpecialBuiltinUsageError(1, suppressible=True)` after the FIRST bad operand, function operands exempt; `source_processor.py:233-240` stop raising `special_exit_floor` for eval/dot; probe trap-action nesting first; lockstep: `tests/integration/test_posix_special_builtin_exit.py` rows, golden `posixexit_*`, matrix doc rows 48/49/51, `exceptions.py`/`internal_errors.py` docstrings); posix function names (delete `function.py:47-55` posix rejection; `-f` operands skip identifier policy; user-guide `17_differences_from_bash.md:504-540` "Note on for/function error flow" narrowed to for/select; locate the R21-A certification row by test before editing prose); `declare -i` on readonly (`scope.py:1290/:1363` raise `ReadonlyVariableError` when the changed set ∩ `INTEGER|LOWERCASE|UPPERCASE|ARRAY|ASSOC_ARRAY|NAMEREF`; `local:` wording; CHANGES llllll). 4 releases.
- **3.2 RD parser acceptance:** C015 (+C110 `_parse_brace_body` shared helper), C016 (hard-coded head list re-probed on 5.3.15: declare/typeset/local/export/readonly/alias/eval/let accept; others rc 2, incl. `builtin declare a=(1)`), C017, C018 (parse then runtime `cannot assign list to array member`), C052, C166 (`a=(1 2)x` → literal scalar), C164 (bare `]]` → syntax error rc 2), C011 (`![`), C047 (`skip_expansion_region` `${` branch → `validate_brace_expansion`), C014 (heredoc spec matched by operator offset; unit pin with an unacceptable delimiter token).
- **3.3 Diagnostics:** C066 + C069 + C219 — route 18 sites through `state.error_location_prefix()`, ratchet test forbidding literal `"psh: "` stderr writes under `psh/executor/` and `psh/expansion/` (synthetic offender); C039 per-line physical map from `process_line_continuations` (pin `$LINENO` AND the command-not-found line — they disagree in bash); C051 nested cmdsub error coordinates; C111 route consume() through `unexpected_token_message`, fix doubled space; C130 nameref readonly diagnostic names the reference; C079 dup2 target fd in the message.
- **3.4 Builtins:** C029+C076 `parse_flags` for printf/times/eval/builtin/source, `invalid number` rc 2 for pushd/popd/dirs; C134 six hand-rolled parsers use `self.error`+`self.usage`; C200 usage strings aligned to 5.3.15 `help` text (cd, read, trap, ulimit, exec, mapfile + the 14 flagged) incl. `unset: f: cannot unset: readonly function`; C074 `is None` tests in cd; C075 source/. usage rc 2 + posix exit; C077 `kill -n`; C078 wait rc 1 + message; C089 remove `%` from `_CONVERSIONS`; C136 UNSET marker on bare `declare -a/-A`; C063 `VAR=v exec` persistence via `ExecutionResult`, delete `command.py:1102-1109`; C064 select empty line; `declare -c` acceptance (triage note). C135 doc inventory + allowlist guard ships with the printf slot.
- **3.5 Core/state/invocation:** C070 temp-env over eval/source as a real scope; C071 nameref-resolved `export -n` (+ sweep of `get_variable_object` pre-checks); C072 drop env union at `parameter_expansion.py:480`; C195 SHLVL; C197 `set -o<attached>` cluster semantics; C198 add `interactive-comments`/`keyword`/`onecmd`/`physical`/`privileged` rows (or document each), history default; C086+C157+C158+C161 invocation (`-o` takes next argv, bare `+`, `argv0: Optional[str]`, `--verbose` alias + "Not supported" HELP block + user-guide row); C013 either emit `chr(0xDC00+b)` for ≥ 0x80 or qualify `08_quoting_and_escaping.md:267` and cross-reference §17 (decide by probe battery; the doc correction is mandatory either way); C191 drop NUL in `$'…'` decode (read/mapfile face re-verified after 4B.2).
- **3.6 Executor/io:** C065 job text from AST source extents (also fixes the `<subshell>` triage note and is the prerequisite for any future signal-death parity); TRIAGE-N2 foreground external commands must not consume job numbers (`JobManager.create_job` next_id policy); C067 `wait` returns 128+N after a trap handler fired; C124 signal-death notice suppression per subtree; C182 bare `wait` reaches procsub children; C183 PIPESTATUS in brace groups; C184 pipeline member runs its own EXIT trap; C185 `times` CPU residue; C206 `{v}>&-` with v unset → `ambiguous redirect` rc 1; C207 move-form closes the source fd permanently in the parent; C081 platform branch in `process_sub.py:32-34` (FIFO Darwin-only) + `CLAUDE.md` wording — verified on the Linux nightly (D7 marker if needed).
- **3.7 Combinator:** C056 `time -p !`; C057 derive the four token sets from `TokenGroups.WORD_LIKE`; C058 separators/emptiness checks (verified via direct API); C060 `-ef/-nt/-ot`; C061 `unexpected_token_message`; C062 stamp `.line`; C118 render `expected`, drop token index.
- **3.8 Analysis/visualization tools:** C083 `_render_redirects` in `DebugASTVisitor` + coverage-matrix entry (C210 guard extended to every analysis visitor); C084+C144 node-anchored substitution counts; C085 delete the inverted `>&1` check; C099+C211 structural command-head analysis with typed quoting helpers; C145 redirect traversal before `_pop_context`; C147 `visit_ArithmeticExpansion`; C116/C117 dot scalar fields + DOT escaping; C122/C177 s-expression indent + quoting. TRIAGE-N3 (`[[ x =~ a{1 ]]` psh rc 1 silent vs bash rc 2 diagnostic) lands with the regex diagnostic reshaping (`enhanced_test_evaluator.py:195`).
- **3.9 Interactive:** C034 `history_base`; C035 completion context (raw span / decoded lookup / quote mode) with real PTY tests; C036+C212 vi CTRL_D/CTRL_R; C037+C213 `\w` on component boundary + PROMPT_DIRTRIM; C097 incremental UTF-8 decoder retained across reads + column-aware layout (`wcwidth` policy); C151 `_editable` at the `_replace_line` boundary; C152 1–3 octal digits; C155 CTRL_UNDERSCORE undo, clear stacks in `reset()`; C156 LOCK_EX in `write_history`/`append_history`; C174 `cat <<` classification (interactive INCOMPLETE vs bash syntax error — rule and pin via PTY); C153 only if Wave 0 ruled it still divergent.
- **3.10 Expansion residue:** C068 `_ifs_star_separator()` on the `[*]` arm.

### Architecture target
Every loud divergence from 5.3.15 is either closed with a live-oracle pin or declared in `17_differences_from_bash.md` with a both-sides pin. Diagnostics carry one location prefix. The combinator is verified through its own API (C178).

### Exit criteria
- All Wave 0.3 FLIP-PINS flipped to equality pins in 3.1; FLIP-PINS.md shows zero open rows owned by Wave 3.
- Diagnostic-prefix ratchet green with offender; `--parser combinator` corpus (`tests/conformance` subset + Wave 2/3 rows) agrees with RD on acceptance for every row in 3.2/3.7.
- Interactive rows have a PTY leg with SHA in the transcript; C081 has a Linux nightly result row.
- Conformance suite, compare-bash, gate, ruff, mypy green; every user-guide row named above corrected; `test_claims_have_tests.py` green.
- Size: ~30 slots (3.1 = 4, 3.2 = 4, 3.3 = 3, 3.4 = 5, 3.5 = 4, 3.6 = 5, 3.7 = 2, 3.8 = 2, 3.9 = 5, 3.10 = 1), S/M.

---

## 9. Wave 4 — Measured performance

### Owned findings
- C012 Heredoc-discovery loop re-lexes the pending command per line (O(N²))
- C019 Combinator ~4^n backtracking from one redundant pipeline-element retry
- C048 Identifier-prefixed unmatched `[` whole-line lookahead + `text[pos:]` copy (O(n²))
- C050 Long unquoted literal collection quadratic (`literal.py:190`)
- C128 Value-operand builder quadratic in operand length
- C073 Half of every variable write spent in `enum.Flag` arithmetic
- C088 Eager `from .shell import Shell` in `psh/__init__.py` (79% of `--version` startup)
- C103 Every recognizer token rebuilt with `dataclasses.replace`
- C209 `SimpleCommand.args` recomputed per access
- C239 `LazyFileInput._read_line_block` rescans the tail of a long line
- C240 mapfile unbounded read holds whole input then splits
- Design input: C229 (target demonstrated costs only)

### Architecture target
Each fix targets a measured cost with a counter or scaling pin (≤ ~2.3× per doubling), never an indiscriminate rewrite. Resumable parsing (C171) stays OUT (§10).

### Required work
- **4.1** Lexer: C012 retry from the pending command's seed `LexicalState` (or skip re-lex on `UnclosedQuoteError`), extend `test_heredoc_scaling.py` with a one-logical-command variant; C048 cursor indexing + line-end bound; C050 segment accumulation; C103 recognizers return `(type, value, start, end, extras)` and `emit_token` constructs once — frozen-token invariant preserved. Deterministic operation counters + `--benchmarks` delta vs the Wave 0 baseline.
- **4.2** Combinator: delete `pipelines.py:166-173` fallback; optional packrat memo keyed `(id(parser), pos)`; scaling pin on nested control structures.
- **4.3** Expansion: C128 list accumulation with flush per protection change (scaling pin).
- **4.4** Core: C073 `is_*` properties on raw ints; microbench pin (write path ≥ 1.6× faster than baseline).
- **4.5** Startup/input: C088 PEP-562 lazy `psh/__init__.py` + `__main__.py` import order (guard: `python -c "import psh"` does not import `psh.shell`); C239 chunk accumulator scanning only new bytes; C209 snapshot `args` per handler.
- **4.6** C240 incremental mapfile records (after 1.17).

### Exit criteria
- Every row has a before/after number in `evidence/program_2026_09/benchmarks.md` and a scaling or counter pin that fails on the old code (mutation-checked by reverting the fix locally).
- `--version` wall ≤ 40% of baseline; heredoc/literal/bracket scaling ≤ 2.3× per doubling; combinator nested-depth curve linear-ish (≤ 2× per +2 levels).
- Gate/ruff/mypy green; no behavior change (compare-bash identical to Wave 3 tree).
- Size: 6 slots, S/M.

---

## 10. Wave 5 — Design and textbook

### Owned findings
Themes and design inputs: C219–C224 (themes; their instances closed in Waves 1–3, this wave adds the missing guards), C226–C237 (fresh-appraisal design items), C244 (test-suite limits → D2 already in force; this wave adds the cross-entry-point matrix where Wave 1 did not), C194 (array alias-mutation write-ban gap, documented Phase-4 P1 — close by routing `executor/array.py` mutations through `VariableStore`), C178 (framing: combinator verified by direct API — document in `psh/parser/CLAUDE.md`), C179.
Dead code / duplication: C045, C049, C053+C173 (coverage-confirm then delete both fd-dup WORD paths), C054, C055, C100, C101, C104, C105, C107, C110 (if not consumed by 3.2), C113, C119, C121, C125, C129, C137, C138, C139, C140, C141, C142, C148, C149, C150, C162, C176, C216.
Docs/comments: C087 (promote live tmp/ probes to golden rows, delete dead pointers, ≤1 campaign ID per file), C106, C108, C109, C112, C115, C123, C131 (named `__init__` phases), C132 (finish Phase 4 or retitle), C133, C143, C146, C154 (REPL sketch → invariant prose or drift-lock), C159, C160, C167/C189/C193/C215 (coverage notes → ledger rows for the nightly/PTY legs), C168 (CRLF divergence into the user guide), C175/C199/C203/C204/C205/C218 (documented by-design — verify the doc still states them), C187/C192 (Linux-oracle rows on the nightly), C188, C201, C202, C217, C230, C236, C237.

### Architecture target
The subsystem-CLAUDE.md rule applied to source comments: state the invariant, point at the code, drift-lock what must be a sketch. Write-site invariants (C226) enforced in one owner per transition. Analysis visitors covered by one coverage matrix (C210).

### Required work
- **5.1** Guards for the themes: `error_location_prefix` ratchet tree-wide (extends 3.3); one-extent-authority census test for `${`/`$((` scanners; `TokenGroups.WORD_LIKE` derivation guard; duplicated-literal ratchet (IFS, stdin-source predicate).
- **5.2** Dead-code deletions (coverage-instrumented suite run first for C053/C173/C107).
- **5.3** Comment/doc hygiene (C087, C133, C188, C217 + the listed one-liners); `test_doc_snippets.py` registry entries where a sketch survives.
- **5.4** Structural: C131, C132/C226 (VariableStore as the transaction boundary; `local` routed through it; C194 closed), C227 phase extraction only where cleanup obligations simplify, C236 protocol narrowing, C237 typed `or_else`.
- **5.5** Coverage-matrix extension to all analysis visitors (C210) and the C244 cross-entry-point matrix.

### Exit criteria
- Ratchets green with offenders; census tests enumerate the surviving allowlisted sites with reasons.
- Complexity counters (functions ≥ 100 lines) ≤ Wave 0 baseline; no new import cycles.
- Every documented-by-design row (C175, C199, C203–C205, C218, C168) is stated in `17_differences_from_bash.md` and each has a both-sides pin.
- Size: ~8 slots.

---

## 11. Ceremony C
Per integrator-plan §7 and sequence-doc §12 with amendment A6 (`python -m pytest tests/behavioral --compare-bash -n auto -q`, never `run_tests.py --compare-bash`): three seeded gates with identical censuses at ONE final tree; every inventory discriminator, flip-pin, guard offender, PTY and fault leg re-run with SHAs; benchmark and counter deltas vs the Wave 0 baseline explained; close report; ledgers and essential probes in the committed tree; attestation the FINAL commit; nightly at the final SHA green with the pinned 5.3.15.

---

## 12. Parked / deferred (explicit, with reason)
- **C171** ParseSession O(k²) — RESUMABLE-PARSER successor campaign (prior ruling R1); measured cost is interactive-only; not this program.
- **C172** nested cmdsub re-parse mildly super-linear — capped at `MAX_SUBSTITUTION_NESTING=100`, documented.
- **C120** combinator constant factor + double parse — by design (educational parser); one sentence in `psh/parser/CLAUDE.md` via 5.3.
- **`${ cmd; }` / `${| cmd; }` function substitution** (bash 5.3 NEWS s; surfaced by the `${ }` triage node) — L feature work; Wave 0.1 pins it as a declared divergence with `min_bash: "5.3"`; a successor feature slot may adopt it.
- **C165** coproc — documented unsupported.
- **C190** `$(< file)` — documented unsupported (`06_expansions.md:254`); candidate for a later feature slot, not a defect.
- **C196** BASH_SOURCE — documented missing (`docs/missing_features.md` §1); C199 identity variables by design.
- **C186** `%Q` lenient TIMEFORMAT — declared divergence, documented at `core.py:380-390`.
- **C214** `psh -i` with piped stdin — deliberate, documented at `__main__.py:279-290`.
- **C245** pre-merge smoke check — USER DECISION: per-PR CI disabled, the local gate is the gate (`run_tests.py --quick` already exists as the smoke).
- **Signal-death exact parity with bash 5.3's job-table printer** — L (needs bash-faithful job text, prerequisite C065 in 3.6); Wave 0.1 declares the format divergence.
- **Not queued (status):** C114, C163 (not reproducible), C208 (fixed — harness race, closed).

## 13. Risk register

| Risk | Mitigation |
|---|---|
| Oracle drifts again (Homebrew upgrade mid-campaign) | `oracle_policy` test is the single red signal; brew pin `bash` for the program's duration; attestation records the version; nightly builds the pinned tarball. |
| Nightly runs 5.2.21 until pinned → 44 confusing reds | 0.1 lands the source-built 5.3.15 + D7 markers in the same release; nightly result checked at every wave close (AM-1 lesson). |
| Wave 1 scope creep (19 slots) | Each slot is one harm; integrator may re-order but never merges two harms; verifier D6 focus. |
| 1.3/1.18/1.19 blast radius (redirect planner, array writes, field splitting) | Probe matrix precedes design (A8 pattern); compare-bash + conformance in each exit; the C226 matrix ships before consumers migrate. |
| Bash-5.3 adoption pins (0.3) rot while waiting for 3.1 | Both-sides pins fail the moment either side moves; FLIP-PINS owner column; integrator may pull 3.1 forward after Wave 1 if a user complaint lands. |
| Sandboxed gate produces phantom ENV failures | D3; the four skips report as skips; gate launcher checks `sandbox-exec` absence and disk ≥ 10 GB. |
| Interactive/PTY facts (2.8, 3.9) mis-ruled by python-pty-only probes | Realistic-terminal leg (tmux) per prior §3; probe-construction independence. |
| macOS-only gate misses Linux paths (C081, C067 signal numbers, locale) | Nightly rows in the ledger; D7 markers; reason about Linux in briefs touching signals/procsub/locale. |
| Parallel session's uncommitted README/index edit collides with 0.1 | Never-touch list carried; index row coordinated at launch (one-row conflict known). |
| Editable-install imports MAIN in probe harnesses | Discriminator (`psh.__file__` under the tree under test) in every harness. |

## 14. Launch checklist (all require explicit user go)
1. User go received; oracle decision (5.3.15) confirmed in writing (done — this plan records it).
2. `brew pin bash`; `/opt/homebrew/bin/bash --version` = 5.3.15 recorded in `oracle-baseline.md`.
3. Disk ≥ 10 GB; no sandbox in the gate launcher's process tree; `gh auth status` shows `philipwilson` active.
4. Evidence tree created; ledger has 245 rows with owner/wave/disposition and no TBD; FLIP-PINS seeded with the Wave 0.3 rows.
5. Verification harness preamble points at THIS plan (stale-preamble lesson).
6. 0.1 dev brief written; worktree cut from `6459f1a6`; the parallel session's uncommitted files listed in the never-touch list.
7. After 0.3 merges: nightly result at the 0.3 SHA reviewed before Wave 1's first brief is dispatched.
