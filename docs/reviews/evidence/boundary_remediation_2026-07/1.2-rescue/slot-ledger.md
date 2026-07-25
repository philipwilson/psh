# Slot 1.2 ledger — Oracle migration + anti-spawn guard (HIGH-1 second half)

- **Worktree:** /Users/pwilson/src/psh-r1-2  **Branch:** fix/remediation-1-2
- **Base SHA:** `e52957d4` (v0.751.0, tip of slot 1.1 merge — ships
  `OutputLimitExceeded` + `is_comparable`, the API this slot migrates callers TO)
- **Oracle:** `/opt/homebrew/bin/bash` `5.2.26(1)-release` (PATH bash, never /bin/bash)
- **Discriminator verified:** `PYTHONPATH=<wt> python -c import psh` →
  `psh.__file__ = /Users/pwilson/src/psh-r1-2/psh/__init__.py`, version 0.751.0.

## Census (item 1) — committed as tests/harness/oracle_migration_census.md

Enumeration commands + outputs (replayable at base).
**SUPERSEDED figures — read with the round-2/3 corrections below:** the
"107 import sites" and the "183 / 88 / 95" bearing-set line here are the
first-draft measures; round 2 replaced them with the three-measure import table
(108 files / 105 real imports / 102 statements) and the AST bearing-set numbers
(181 / 182 / 96 / 245), and round 3 corrected the PTY claim. The committed
census file is the authority.
- `grep -rlE 'subprocess\.(run|Popen|call|check_output|check_call)|os\.system|os\.popen' tests/ --include='*.py' | wc -l` → **294** modules spawn directly tree-wide.
- `grep -rlE 'shell_oracle' tests/ --include='*.py' | wc -l` → **107** import sites.
- Guard-bearing set (imports shell_oracle OR under conformance): **183** modules;
  **88** have no direct spawn; **95** are migration targets (**243** spawn sites).
- Per-module/per-site classification via `tmp/gen_census.py` (AST walk resolving
  each module's bash-path variable).
- `os.system`/`os.popen`: 0 in scope. PTY/os.fork/pexpect: 0 in scope
  (interactive rows drive via stdin pipe + TERM=dumb — runner-serves).

Class counts (targets): BASH-DIFFERENTIAL 93, PSH-ONLY-SITE 2. Allowlist
candidates: **1** (`harness/shell_oracle.py`, owns the runner's one real Popen).
`test_read_malformed_bytes_i1.py` ruled RUNNER-CAPABLE (surrogateescape byte
round-trip). `test_std_fd_lease_f2.py` python-c fd-harness: decided at migration.

Migration batches (by dir): conformance 36, integration 35, system 12, unit 12.

## Item 3 — 9 isinstance(Completed) consumers → is_comparable (named in census).

## Plan / batches

- [x] Commit 1: census file + ledger (no behavior change).
- [x] Commit 2 (`d5d86808`): shell_oracle helpers (run_psh/run_bash) + item-6 natural-exit
      truncation pin + item-7 Timeout provenance + harness tests.
- [x] Commits 3..N (`675bba35`, `beb0b9e5`, `29f8d791`): migration batches (conformance/bash, integration, unit,
      system); per-batch focused tests green.
- [x] Guard commit (`3b36d21c`, items 3+5 in `c6d8263a`): anti-spawn AST guard + synthetic offender; rework the
      resolution ratchet (item 5); consumer unification (item 3).
- [x] Final: full parallel gate + ruff + mypy; ledger complete; report to main.

## Migration progress

- Commit `0fef6967` census; `d5d86808` harness helpers + pins.
- Commit (batch 1) 6 conformance modules (nounset/set/trap/syntax): 93 focused
  tests green. Pattern-setter.
- Commit `beb0b9e5` (batch 2) 62 mechanical modules via 3 parallel subagents
  under tmp/MIGRATION-SPEC.md (strict: no assertion changes; stop-and-report on
  any residual failure). Each module's focused test verified green individually;
  ruff clean; all 62 carry an is_comparable assert on every migrated spawn.
- Remaining: 27 tricky modules (bytes / script-file / interactive / fd-harness /
  multi-helper), migrated by the slot dev directly.

## Per-file assertion-delta justifications

NO test assertion or expected value was changed in ANY module. Equivalent
non-mechanical adaptations (all behavior-preserving), recorded:
- **skipif repoints**: modules with `skipif(BASH is None, ...)` (dead guard —
  resolve_bash() raises rather than returning None) repointed to a
  `_ORACLE = try_resolve_bash()` sentinel. Same semantics, plus now actually
  skips when no bash (previously would have errored at import).
- **name collisions**: modules defining local helpers literally named
  run_psh/run_bash import the harness versions aliased and keep the local
  wrappers' names/signatures. Behavior unchanged.
- **var-argv dispatch helpers** split into psh (run_psh) + bash (run_bash) paths.
- **byte comparisons** recover exact bytes via
  `.stdout.encode('utf-8','surrogateescape')` (lossless round-trip).
- **test_recursion_depth.py**: original `env.pop('PSH_STRICT_ERRORS')`; hermetic
  base can't delete a key, so set `PSH_STRICT_ERRORS=''` — psh reads empty as OFF
  (state.py:433: `.lower() in ('1','true',...)`), equivalent to absent.
- **test_process_sub_embedded._os_supports_affixed_write_side**: capability
  PROBE (not a comparison) that degraded to `return False` on failure; preserved
  as `if not is_comparable(probe): return False` (skips dependent test, as before).
- **test_command_resolution_r3.py**: kept `BASH = _ORACLE.path` — still used by
  `_norm_prefix()` to scrub the bash path from diagnostic output, not only to spawn.

## Allowlist entries (for the anti-spawn guard) — part (a) NAMED

**CURRENT STATE (after the round-2 shrink): 4 entries — 1, 2, 3, 4 below.
Entry 5 (`test_stdin_script_lazy_read.py`) was REMOVED in round 2** once
`stdin_mode='pipe'` satisfied its own recorded removal condition; it is kept
below, struck through, as the shrink record. Part (b) `PSH_ONLY_REGISTRY` is
**empty** (the bearing set's spawner subset is 95/95 differential); part (c)
`PTY_REGISTRY` holds **1** entry (round 3). Membership of each is pinned
literally (`_EXPECTED_NAMED_ALLOWLIST`, `_EXPECTED_PSH_ONLY_REGISTRY`,
`_EXPECTED_PTY_REGISTRY`).

1. `harness/shell_oracle.py` — owns the runner's single real subprocess.Popen
   (+ the `_bash_version` probe). Owner: slot 1.1. Removal: never (it IS the
   runner). NOT a migration target (see arithmetic below).
2. `integration/job_control/test_exit_trap_paths.py` — DIFFERENTIAL mid-run-signal
   harness: `_spawn_and_signal` (psh side), its bash-side caller passing
   `[BASH, str(path)]`, and the stdin-mode Popen in `TestExitTrapStdin`; each
   waits on a readiness
   sentinel then delivers `os.kill(proc.pid, sig)` to compare the EXIT trap on a
   fatal signal. The run-to-completion runner cannot signal a running child.
   Owner: slot 1.2. Removal: run_shell_case gains a mid-run-signal hook, or a
   PTY/pexpect harness. (Its run-to-completion differential helpers ARE migrated.)
3. `system/test_script_input_sources.py` — concurrent FIFO writer: a bash writer
   Popen (the two fifo-writer sites) must run CONCURRENTLY with the blocking psh fifo reader (a
   fifo open blocks until both ends are open), so the blocking runner would
   deadlock. The psh reader side IS migrated. Owner: slot 1.2. Removal: a
   non-blocking writer helper or a concurrent-writer runner mode.
4. `system/test_stdin_startup_robustness.py` — needs `preexec_fn=os.close(0)`
   (close-fd0 cases) or a live file object on stdin (the raw branch of `_run`); neither is
   expressible through the runner. All raw-byte-stdin cases DO route through the
   runner. Owner: slot 1.2. Removal: runner gains close-fd0 / file-object stdin.
5. ~~`system/test_stdin_script_lazy_read.py`~~ — **REMOVED in round 2 (shrink).**
   It pinned the PIPE (non-seekable) vs seekable-FILE stdin distinction (7
   sites) and was allowlisted because the runner could only offer a seekable
   file. `stdin_mode='pipe'` met that exact removal condition, so all 7 sites
   are now runner-routed and the entry left BOTH the allowlist and the frozen
   membership pin. Distinction verified to survive: bash `mapfile` via pipe
   drains → rc 0; via seekable file → `count=0`, rc 127; `os.fstat(0)` shows
   `S_ISFIFO` vs `S_ISREG`.

### Outcome arithmetic (corrected, round-1 item 3)

**Current (after the round-2 shrink):** 95 migration targets =
**92 MIGRATED + 3 ALLOWLISTED targets** (entries 2-4). `shell_oracle.py` is an
ALLOWLIST entry but was NEVER a migration target (it is the runner), so
allowlist entries (4) ≠ allowlisted targets (3).
History: round 1 corrected the original "90 migrated + 5 allowlisted" (which
conflated entries with targets) to 91 + 4; the round-2 shrink then moved
`test_stdin_script_lazy_read` from allowlisted to migrated, giving 92 + 3.

## FLIP-PINS 1.2 audit (round-1 blocker 2) — documented-difference surface

Obligation (FLIP-PINS.md must-NOT-flip table): "Slot 1.2 audits these three
during oracle migration: each either maps to a ledger row or gets one."
Audited: the `tests/conformance/differences/` framework + all 3
`assert_documented_difference` users. Probed live vs bash 5.2.26 at this tip.

**Live users (3) — behavior probed, then mapped:**

| Call site | ID | Probed behavior (psh vs bash) | Ledger mapping |
|---|---|---|---|
| `posix_compliance.py:562` | `PROCESS_ID_DIFFERENCE` (`echo $$`) | both rc 0, numeric pids `14085` vs `14087` — differ only because they ARE different processes | TAUTOLOGICAL, no psh defect, no fix owed → **must-NOT-flip**; the loose pin is covered by NEW row F1 below |
| `posix_compliance.py:362` | `ERROR_MESSAGE_FORMAT` (`echo \$(echo test)`) | both rc 2, both stdout empty, both "syntax error near unexpected token `('" — only message FORMAT differs (psh adds caret/context block) | maps to the EXISTING re-carried **wording family**, Part B rows #6 (exec wording), #10 (history -p wording), #24 (126 wording). Same class: cosmetic wording, equal rc. **RE-CARRIED**, no new row for the behavior |
| `user_guide_notes:262` | `ALIAS_EXPANSION_NONINTERACTIVE` | psh rc 0 `ALIAS_EXPANDED`; bash rc 127 `ll: command not found` | DELIBERATE psh divergence, user-guide ch17.3/ch04 + catalog category `deliberate_divergences` → **must-NOT-flip**; recommend NEW row F2 to record it explicitly so no later slot "fixes" it silently |

**NEW rows proposed for the integrator to add to the campaign LEDGER:**

- **F1 — documented-difference matching is BEHAVIOR-BLIND (evidence-trust,
  HIGH-1 family).** `conformance_framework._is_documented_difference` is
  `command in catalog['documented']` — a COMMAND-KEY match that never looks at
  the observed behavior. PROVEN at this tip: feeding a nonsense psh result
  (`stdout='banana'`) for `echo $$` still classifies `DOCUMENTED_DIFFERENCE`. So
  every `assert_documented_difference` row green-lights ANY future divergence on
  that command, including a genuine regression — a test that cannot fail for the
  right reason, exactly the HIGH-1 defect shape. Closure: catalog entries carry
  the expected psh/bash observable (or a predicate) and the framework asserts the
  OBSERVED divergence matches the DOCUMENTED one. (Not fixed in 1.2: the brief
  scopes this slot to the audit + row naming; fixing it changes conformance
  semantics and wants its own slot.)
- **F2 — catalog is partly DEAD inventory.** 4 of the 7 documented entries are
  referenced by ZERO tests: `HELP_BUILTIN`, `PUSHD_BEHAVIOR`,
  `PUSHD_CWD_DIFFERENCE`, `POPD_BEHAVIOR` (verified by grep per ID). They are
  inventory, not closures — the same "ratchets are inventories, not closures"
  finding as the LOW debt-ledger row. Worse, `PUSHD_CWD_DIFFERENCE`'s recorded
  justification is a HARNESS artifact ("PSH and bash run from different working
  directories in the conformance test environment"), i.e. it documents a harness
  artifact AS a shell difference. Closure: delete the dead entries or give each a
  proving test; re-justify or drop `PUSHD_CWD_DIFFERENCE`. F2 also carries the
  explicit record of the sanctioned `ALIAS_EXPANSION_NONINTERACTIVE` divergence.

## Evidence — brief item 3 (consumer unification on is_comparable)

Commit `c6d8263a`. Enumeration, replayable:
`grep -rn 'isinstance([a-z_]*, *Completed)' tests/ --include='*.py'` now returns
ONLY the TYPE assertions in `test_shell_oracle_harness.py` (deliberate) and the
`is_comparable` definition itself at `shell_oracle.py#is_comparable` (currently :224 — cite the SYMBOL; the line moves) — zero isinstance
gates left in consumers. The 9 converted sites: `pipeline_closed_fds:88`,
`long_pipeline_fd_limit:44`, `process_sub_closed_fds:54`+`:72`,
`invocation_matrix:42`, `startup_order:34`+`:43`, `source_service_matrix:46`,
`nul_channel_matrix:77`. Focused suites after conversion: **197 passed**.

## Evidence — brief item 5 (superseded blessing reworked)

Commit `c6d8263a`, `tests/unit/tooling/test_bash_oracle_resolution.py`.
COORDS: the superseded blessing was `test_guard_accepts_resolver_usage` at
base `e52957d4:228`; its replacements at this tip are
`test_resolution_ratchet_accepts_runner_usage` (:240) and
`test_resolution_ratchet_is_orthogonal_to_the_anti_spawn_guard` (:261). The
accepted-use fixture blessing a DIRECT `subprocess.run([resolve_bash().path,…])`
is gone; the blessing is now `run_bash([...])`. A new test pins the division of
labour (`test_resolution_ratchet_is_orthogonal_to_the_anti_spawn_guard`): the old
pattern still passes THIS ratchet (resolution is correct) while the anti-spawn
guard rejects it (it is a direct spawn) — it imports the guard's
`find_direct_spawns` and asserts the flag. Module docstring updated. Replayed:
`pytest tests/unit/tooling/test_bash_oracle_resolution.py -q` → **15 passed**.

## Pin replay states (base = e52957d4 / v0.751.0; CURRENT TIP recorded in the
## ROUND-2 section below — this section's states were first taken at c6d8263a
## and re-replayed at each later tip)

- **Anti-spawn guard synthetic offender (red-on-base by construction):** the
  guard file `test_no_direct_spawn_in_oracle_modules.py` DOES NOT EXIST at base
  (`git cat-file -e e52957d4:...` → absent), so on base any offender passes
  undetected. At tip the guard is non-vacuous — MUTATION PROOF replayed: with
  `test_exit_trap_paths.py` de-allowlisted, the guard flags
  the two `subprocess.Popen` sites in `test_exit_trap_paths.py`
  (`_spawn_and_signal` and the `TestExitTrapStdin` stdin-mode spawn — cited by
  SYMBOL because the line numbers have since moved). Restored after.
- **Item 6 natural-exit-past-cap pin:** GREEN at base AND tip — it fills
  coverage debt (the run_shell_case:446 branch shipped in 1.1 but was only hit
  by a poll-timing race); deterministic now via getsize-neutralisation. Not a
  regression flip.
- **Item 7 Timeout provenance:** tests the NEW `stdout/stderr_truncated` fields;
  would AttributeError at base (Timeout had no such fields) → genuinely new.
- **HIGH-1 discriminators** (`test_yes_discriminator...`, identical-timeouts,
  two-output-limit) are slot 1.1's pins, unchanged and green.

## ROUND-1 BOUNCE FIXES (commit history + replayed states)

**Commit currency:** the round-1 report was sent at tip `c6d8263a`; the
integrator ruling was then applied in **`f445ce4e`** (declared post-report
commit: census differential/psh-only primary table + two-part allowlist).
Round-1 verification judged `f445ce4e`. This round's fixes land in the commit
below; **no undeclared post-report commits.**

| # | Fix | Replayed state |
|---|---|---|
| 1 | **Growth-refusal made MECHANICAL**: `_EXPECTED_NAMED_ALLOWLIST` / `_EXPECTED_PSH_ONLY_REGISTRY` frozen sets + `test_allowlist_membership_is_frozen`, plus a third offender face (`test_growth_face_a_bogus_allowlist_entry_is_refused`). | RED-then-GREEN replayed: the verifier's exact attack (bogus entry `conformance/bash/test_nounset_operators_conformance.py` added to ALLOWLIST) now raises `NAMED_ALLOWLIST membership changed…`; before the pin it passed silently. |
| 2 | **FLIP-PINS audit** (above): 3 live users mapped, 4 dead entries + framework blindness written up as proposed rows F1/F2. | Framework blindness PROVEN by probe (nonsense `stdout='banana'` for `echo $$` → `DOCUMENTED_DIFFERENCE`). |
| 3 | **Ledger/census truth-ups**: all 5 allowlist entries listed; arithmetic corrected to 91 migrated + 4 allowlisted targets; census (b) split into 108 files / 105 real AST imports / 102 import statements (base-SHA recount, "107" superseded); MODULE-vs-SITE wording reconciled; commit currency recorded. | Counts re-derived AT BASE `e52957d4` via `git grep`/AST (post-migration counts differ because the migration ADDED imports — the census is a frozen base snapshot). |
| 4a | **Fixture-dir skip is now EXACT-PATH** (`unit/tooling/oracle_spawn_fixtures`), not name-based; policed by `test_only_the_exact_fixture_path_is_skipped`. | ATTACK REPLAYED: offender planted at `tests/conformance/oracle_spawn_fixtures/sneaky.py` — previously undetected, now FLAGGED (`…/sneaky.py:3: subprocess.run`); planted file removed after. |
| 4b | **Honest limits gain aliased-import blindness** (`import subprocess as sp`), alongside bare-name/getattr/string forms. | Claim VERIFIED before documenting: 0 aliased/bare-name subprocess-or-os imports in the bearing set. |
| 5 | **Migration fidelity — `POSIXLY_CORRECT`**: base's `_BASE_ENV` filtered it out; `hermetic_shell_env` does not, and a case env can only ADD keys (and bash treats a PRESENT-but-empty `POSIXLY_CORRECT` as posix ON, so `=''` is NOT equivalent). `test_posix_invocation.py` now builds its env via `hermetic_shell_env()` + explicit `pop('POSIXLY_CORRECT')`. | RED replayed at the previous tip: `POSIXLY_CORRECT=1 pytest tests/system/test_posix_invocation.py` → **5 failed, 5 passed**. GREEN after the fix: **10 passed** both with and without `POSIXLY_CORRECT=1` in the ambient env. |

## ROUND-2 BOUNCE FIXES (tip recorded at the end of this section)

| # | Fix | Replayed state |
|---|---|---|
| 1 | **BLOCKER — migration changed a test SUBJECT.** The runner fed stdin from a seekable REGULAR FILE, so `/dev/stdin` stopped being a pipe. Took the RULING's **preferred remedy**: added a typed `stdin_mode` to the runner (`'file'` default unchanged, `'pipe'` = real FIFO via `os.pipe()` + daemon writer, EPIPE-safe), and routed the affected rows through it. | (a) Runner pin added: `test_stdin_mode_pipe_gives_a_real_non_seekable_pipe` asserts `FD0=PIPE` under pipe mode vs `FD0=REGFILE` under the default, plus EOF-with-no-data, never-reads, and bad-value pins. (b) Non-sniffed branch re-exercised: probe through `run_psh` gives `FD0=PIPE`, hitting the `S_ISREG` early return in `script_validator.py#is_binary_file:62`. |
| 1b | **Swept the whole hazard class, not just the 2 reported rows.** Enumerated every migrated module whose fd-0 kind changed pipe(base)→file(tip): **25 modules**. Restored base's fd-0 kind at **23 call sites across 24 modules**; the 25th (`test_script_fd_ownership_i2.py`) correctly needed no change — all 7 of its callers omit stdin, so base was `input=None` (inherited), never a pipe. | Re-enumeration after the sweep: **0 modules** remain pipe(base)→file(tip) without an explicit `stdin_mode`. All focused suites green (23-site group: 456 passed; 16-site group: 280 passed). |
| 1c | **Allowlist SHRANK** (designed direction): `stdin_mode='pipe'` satisfied `test_stdin_script_lazy_read.py`'s own recorded removal condition, so it was migrated OFF the allowlist (all 7 sites now runner-routed) and removed from BOTH the allowlist and the frozen membership pin. | 31 passed. Distinction verified to SURVIVE: `mapfile_drains` — bash via PIPE drains → `rc=0 stdout=b''`; via SEEKABLE FILE reads from EOF → `rc=127 stdout=b'count=0\n'`; independent `os.fstat(0)` probe confirms `S_ISFIFO` vs `S_ISREG`. |
| 2 | **BLOCKER — census not reproducible.** (a) The recorded `git grep` used a glob that misses `tests/conftest.py` (replayed 107, stated 108); switched to the `-- tests/` pathspec form. (b) The bearing-set headline used the SUPERSEDED textual-mention measure and a TIP-time count labelled as base. Restated with the guard's OWN AST predicates at base, and committed the replay script as `tests/harness/census_replay.py`. | Both replay EXACTLY as recorded: `git grep -l 'shell_oracle' e52957d4 -- tests/ \| wc -l` → **108**; import-statement form → **102**; `python tests/harness/census_replay.py <base>/tests` → **181 / 182 / 96 / 245**, and containment is exact (95 targets = 96 spawners − `shell_oracle.py`; 243 sites = 245 − its 2). Guard docstring + module comment corrected: the scanned bearing set is **182**; "95/95 differential" describes the **SPAWNER SUBSET**. |
| 3 | **RULING — oracle-absence loudness restored.** 11 modules (85 tests) had been converted from module-scope `resolve_bash()` to `try_resolve_bash()` + live `skipif`, so a missing oracle SILENTLY SKIPPED. Restored loud module-scope `resolve_bash()` and deleted every dead `skipif`/`pytestmark` guard. | RED/GREEN replayed with the resolver ladder stubbed out (no BASH_PATH / no Homebrew / no PATH bash): at the PREVIOUS tip the module imported fine → "would SILENTLY SKIP"; at this tip it raises **`BashOracleUnavailable` at import** = loud. 394 tests green with the oracle present. |
| 4a | Guard: `test_fixture_dir_is_excluded_from_the_scan` used substring matching (would "pass" while an impostor went unscanned); tightened to the exact `_FIXTURE_REL` path. | 22 guard tests pass; the impostor attack stays flagged by `test_only_the_exact_fixture_path_is_skipped`. |
| 4b | `test_posix_invocation.py` prose referencing the deleted `_BASE_ENV` reworded as historical. | — |
| 4c | `test_stdin_startup_robustness.py::_run` gained an explicit note that TWO env regimes live in it (hermetic runner branch vs ambient direct branch) so a locale-sensitive row is not added blind. | — |
| 4d | Ledger: stale `tip = c6d8263a` header corrected; real evidence sections added for brief items 3 and 5 (above). | — |
| 4e | Accepted-monkeypatch SCOPE comments added to both getsize-neutralising tests, stating exactly what is disabled (only the watchdog's mid-flight kill) and that child/capture/classification are real. | — |
| NIT | Stale "pipe stdin" prose: after fix 1b the flagged docstrings in `test_history_outcomes_i4`, `test_history_p_interactive`, `test_redirect_failure_paths`, `test_read_malformed_bytes_i1`, `test_read_mapfile_streaming` are ACCURATE AGAIN (their fd 0 really is a pipe once more), so they stand as written. | Verified per module by the sweep agents. |

**Allowlist after round 2: 4 entries** (`shell_oracle.py` + `test_exit_trap_paths`
+ `test_script_input_sources` + `test_stdin_startup_robustness`);
`PSH_ONLY_REGISTRY` still empty. Residual direct spawners in the guard scope:
exactly those 4, verified by running the guard's own scan.

## ROUND-3 BOUNCE FIXES

| # | Fix | Replayed evidence |
|---|---|---|
| A | **BLOCKER — the sweep missed one module and my completeness claim was FALSE.** `test_exit_trap_paths.py::_run` passed `stdin_data` with the DEFAULT file mode; its data-bearing caller `test_fires_from_piped_stdin` was a PIPE row at base. Fixed with the conditional pattern (`stdin_mode='pipe' if stdin is not None else 'file'`). **Root cause of my false negative, stated honestly:** the round-2 verification scan tested for the substring `stdin_mode` ANYWHERE in the module — and this module contains it as a TEST NAME (`test_stdin_mode_fires_exit_trap`, :347), so the module was skipped. A module-level substring check cannot answer a per-CALL-SITE question. | New CALL-SITE-AWARE audit committed as `tests/harness/stdin_kind_audit.py`. Re-run at tip: **13 sites in 9 modules**, every one legitimate — 8 modules ALREADY used the runner at base (file mode was always their behavior; checked per module against `git show e52957d4:`), and the 9th (`test_script_fd_ownership_i2`) passes no stdin data at all (all 7 `_cmp` callers omit it). Remaining fidelity regressions: **0** — independently reproducing the verifier's "this was the only miss" rather than asserting it. FD-0 kind now: data-bearing → `FD0=PIPE`, no-stdin → default. Module: 36 passed. |
| B(a) | **BLOCKER — a PTY bash-differential escaped the census; the covering claim was FALSE.** Added the missing enumeration (`pty_audit()` in `tests/harness/census_replay.py`: AST scan for `pexpect.*` / `pty.*` / `os.fork\|forkpty\|posix_spawn*\|exec*` over the bearing set) and classified `test_multiline_immediate_error_i3.py` as **PTY-INFRA**. | Replayed AT BASE: exactly **2 sites in 1 module** (`:78`, `:92` `pexpect.spawn`), proving it is the SOLE instance. The census's "PTY/pexpect: zero in scope" line is replaced by a CORRECTION paragraph that names the claim false and carries the command + output. |
| B(b) | **Guard PTY face.** New detector `find_non_subprocess_spawns` + a SEPARATE `PTY_REGISTRY` (owner + reason + removal), its own frozen membership pin, its own hygiene test, and a disjointness test against the subprocess lists. Deliberately NOT a `NAMED_ALLOWLIST` entry — the verifier's trap: `test_allowlist_entries_still_spawn` keys on `find_direct_spawns`, which can never see a pexpect spawn, so a PTY module parked there would break that hygiene test or force it to be loosened into meaninglessness. | Synthetic PTY offender `oracle_spawn_fixtures/pty_offender_module.py` + `test_pty_face_fires_on_synthetic_pty_offender_fixture`, which ALSO asserts `find_direct_spawns(src) == []` — pinning the exact blind spot the face closes. Guard suite: **28 passed**. |
| B(c) | **Honest-limits truth-up.** Docstring now describes TWO faces, names the non-subprocess family, and states why PTY is beyond the runner. Added `getoutput`/`getstatusoutput` to `_SUBPROCESS_SPAWNS` (spawn-capable; zero uses today). Fixed the **ImportFrom-alias hole**: `_imports_shell_oracle` now also checks ImportFrom ALIAS names, so `from tests.harness import shell_oracle` reads as bearing — previously it did not, i.e. a module could leave the guard by changing import style. | Guard green with the widened predicates; base bearing-set counts UNCHANGED (181/182/96/245), so the alias fix introduces no false positives. |
| B(d) | Census + ledger claims corrected. The module's `try_resolve_bash()` + in-test `pytest.skip` silent-skip is left AS-IS and recorded as a **1.3 carry** with the other pre-existing silent-skip modules (enumeration below). | — |
| 1 | **Stale `$PWD` (runner-level).** `hermetic_shell_env` copied `os.environ` while cases run in a fresh temp cwd, so the child inherited a STALE `PWD`; bash revalidates, psh trusts it. Fixed by dropping `PWD`/`OLDPWD` from the hermetic base AND setting `PWD` to the real run directory (an explicit case-supplied `PWD` still wins). | RED replayed BEFORE the fix: `echo $PWD` → psh `/Users/pwilson/src/psh-r1-2` vs bash the temp dir — a manufactured divergence. GREEN after: in EACH shell `$PWD == $(pwd)`; pinned to a SHARED cwd both shells print the identical `$PWD`. New pin `test_child_pwd_is_truthful_and_agrees_across_shells` covers all three legs. |
| 2 | **Non-discriminating discriminator.** `test_run_psh_runs_the_worktree_psh` asserted the version string, which the editable install and the worktree share — it passed either way. Now asserts the child's resolved `psh.__file__` lies under the tree under test. | Verified meaningful: child resolves `/Users/pwilson/src/psh-r1-2/psh/__init__.py`, while the main-tree path `/Users/pwilson/src/psh/psh/__init__.py` would FAIL the same assertion. |
| S | **Bundled smalls.** `gen_census.py` promoted to `tests/harness/gen_census.py` (the census cited an uncommitted tool) — and CLEANED while promoting: it carried a hardcoded worktree path, an unused variable, and ran its scan at import; now parameterised with a `__main__` guard (`census_replay.py` got the same treatment). Census isinstance aside corrected to **6 at base / 21 at tip** with its replay command. `_env_override` documents that it carries additions/changes but never REMOVALS (the `POSIXLY_CORRECT` shape). Late imports in `test_heredoc_composite_delimiter` hoisted above the module-level data block. Ledger hygiene: checklist boxes checked with SHAs, `is_comparable` cited by SYMBOL, blessing coords recorded (base `:228` → tip `:240`/`:261`), item-1 census figures annotated SUPERSEDED. | — |

### 1.3 carry — silent skip on a missing bash oracle (evidence for the integrator)

Modules still using `try_resolve_bash()` + a skip when no oracle is present.
PRE-EXISTING: slot 1.2 restored loudness only in the 11 modules it had itself
converted, and deliberately left these.

```
$ grep -rln 'try_resolve_bash' tests/ --include='*.py'
```
→ `system/invocation/test_invocation_matrix.py`,
`system/invocation/test_startup_order.py`,
`system/source_service/test_nul_channel_matrix.py`,
`system/source_service/test_source_service_matrix.py`,
`system/test_posix_invocation.py`, `unit/core/test_tempenv_visibility_ledger.py`,
`unit/executor/test_command_resolution_r3.py`,
`unit/expansion/test_pattern_engine_differential.py`,
plus `system/interactive/test_multiline_immediate_error_i3.py` (in-test
`pytest.skip`). `unit/tooling/test_shell_oracle_harness.py` also references it,
but legitimately — it TESTS the resolver, as do the two harness tools
(`harness/shell_oracle.py`, which DEFINES it, and `harness/gen_census.py`,
which only pattern-matches the name). The 1.2 ruling's rationale applies to
these equally; the replay technique (stub the ladder, import must raise) is
recorded in the round-2 section.

## ROUND-4 NIT-FIX COMMIT (verdict was PASS; these close the round-4 nits)

| # | Fix | Replayed evidence |
|---|---|---|
| 1 | **Module-granular allowlist blindness (the one with teeth).** A verifier appended a brand-new raw `subprocess.run([resolve_bash().path, ...])` differential to an ALLOWLISTED module and the guard suite stayed GREEN — approval was per MODULE, so an approved file could grow fresh HIGH-1 bypasses. Added per-module **`_EXPECTED_SPAWN_SITES`** (and `_EXPECTED_PTY_SITES`), enforced per entry, plus a key-coverage test so no budget is missing or orphaned. | Counts RE-DERIVED, not taken on trust: `shell_oracle.py`=2, `test_exit_trap_paths`=2, `test_script_input_sources`=2, `test_stdin_startup_robustness`=1, PTY module=2 — independently matching the verifier's. **Attack replayed against the REAL file:** appending the offending function took the suite to **2 failed / 33 passed** (the budget test for that module + the growth-face test); file restored → **35 passed**. A source-level replay of the same attack is now a permanent test. |
| 2 | **Discriminator portability.** The pin ran a bare `python` inside the child — on a python3-only host (the Linux nightly) it would print nothing and fail as an empty-path assertion. Now interpolates the parent's `sys.executable`, plus an explicit non-empty check so a failed probe reports itself instead of masquerading as a path mismatch. | Harness suite green; the child still resolves `…/psh-r1-2/psh/__init__.py`. |
| 3 | **Latent helper default.** `test_script_fd_ownership_i2::_cmp` keeps its `stdin=None` parameter; applied the conditional idiom so a future caller passing data gets a PIPE rather than silently a seekable file. No live defect today (all 7 callers omit stdin). | Module green (41 passed with its sibling). |
| 4 | **Replay-tool drift.** `census_replay.py` re-implemented WEAKER copies of the guard's detectors (no ImportFrom-alias branch, no `getoutput`/`getstatusoutput`) while the census billed it as "the guard's OWN predicates". It now IMPORTS `_imports_shell_oracle`, `find_direct_spawns` and `find_non_subprocess_spawns` from the guard. | Base numbers replay UNCHANGED after the swap: **181 / 182 / 96 / 245**. Also caught and fixed a regression my first cut introduced: feeding `ast.unparse(tree)` to the detectors RENUMBERED every site (PTY coords printed `:45`/`:52`), so the tool now passes SOURCE TEXT and the census's recorded `:78`/`:92` replay exactly. |
| 5 | **Spawn-family completeness.** Added `os.spawnl*`/`spawnv*` to `_OS_PROCESS_SPAWNS` (same static shape, trivially detectable, zero uses today). NAMED in honest-limits as deliberately undetected: `multiprocessing.Process` and `asyncio.create_subprocess_exec`/`_shell`, with the instruction to extend the detectors — never allowlist — if a differential ever arrives that way. | Guard green (35 passed). |
| 6 | **Smalls.** Pruned the dead `PSH_ROOT` in `test_variable_projection_reads_conformance.py` (single assignment, zero uses; the then-unused `pathlib` import went with it). OLDPWD widening: the `$PWD` pin gains a fourth leg asserting `cd -` fails IDENTICALLY in both shells (`NO-OLDPWD`), so the drop is PINNED rather than merely noted. Allowlist reason strings + ledger now cite `test_exit_trap_paths`'s sites by SYMBOL (`_spawn_and_signal`, its bash-side caller, the `TestExitTrapStdin` spawn) instead of line numbers — my own round-3 discipline applied to my own text. | Touched suites: **556 passed**. |
| 7 | **Ledger note (no code) — timeout-default exposure.** Re-derived rather than copied: **296 runner call sites across 53 migrated modules** inherit the runner's default 10 s timeout where base was untimed. (The whole-tree figure is 1129 sites / 106 modules, but that includes pre-existing runner users; the migrated-only number is what this slot introduced.) Failure mode is LOUD (`Timeout` → non-comparable → test error), never a false green — but on a loaded host or the Linux nightly these are fresh flake candidates, and the fix for any such flake is a per-case explicit timeout, not a global bump. Queued for 1.3's flake charter. | — |

## Final status

- Items 1-7 done. Migration: 95 targets → **92 fully migrated to the runner**,
  **3 allowlisted targets** (+ the runner itself = 4 allowlist entries; see
  Allowlist above). `test_read_malformed_bytes_i1` and `test_std_fd_lease_f2`
  (both flagged "maybe allowlist") were RULED runner-capable and fully migrated
  (surrogateescape byte round-trip / close_fds fd isolation);
  `test_stdin_script_lazy_read` came OFF the allowlist in round 2 (1c).
- Migration done via 3+2 background subagents on disjoint sets under a strict
  no-assertion-change / stop-on-failure spec (tmp/MIGRATION-SPEC.md), plus the
  5 highest-risk modules by the slot dev. Every migrated module's focused test
  green individually; every migrated spawn carries an is_comparable assert.
- Subagent decision REVIEWED: one introduced a bare-`bash` marker in
  test_lazy_script_source_i2 (tripped the E2 resolver ratchet) — FIXED by the
  slot dev (runner-function dispatch + RSS probe via run_shell_case).
- **Gate (round-4 submission, at FINAL TIP `3e10dab3`):**
  `python run_tests.py --parallel` → **EXIT 0, 20364 passed, 1590 skipped,
  10 xfailed** (`tmp/gate13.txt`, zero ENOSPC hits). **ruff check psh tests
  tools:** clean. **mypy:** clean (274 files).
  (Earlier tips: `5593ffd0` → EXIT 0, 20357 passed, `tmp/gate7.txt`;
  `da106ef7` → EXIT 0, 20355 passed, `tmp/gate5.txt`; `c6d8263a` → EXIT 0,
  20349 passed, `tmp/gate.txt`.)
- **Split-phase corroboration at `3e10dab3`** (run separately while the host was
  unstable, so full coverage never depended on one lucky window):
  phase 1 `-m "not serial" -n auto` → **19471 passed, EXIT 0** (`tmp/phase1.txt`);
  phase 2 `-m serial` → **909 passed, EXIT 0** (`tmp/phase2.txt`).
- Scope audit: NO forbidden files (version/changelog/readme/arch/reviews-index)
  and NO psh/ production changes. 11 commits `0fef6967..3e10dab3`.

### Round-3 gate attempts — every failure classified (host, not branch)

Six combined attempts were needed at `3e10dab3`; the host was cycling ~100 GB of
free space throughout. Every single failure fell into one of two classes, and
each was checked rather than assumed:

| Run | Result | Classification |
|---|---|---|
| `gate8` | 7 failed + 1 error | ALL `[Errno 28] No space left` at `mkdtemp` — including 4 of this slot's OWN new pins, checked individually so they were not waved through as flakes |
| `gate9` | 3 failed | ALL ENOSPC, in `test_stdin_script_lazy_read` (the round-2 shrink module) — checked specifically because a real pipe-mode defect would look similar; the traceback is `mkdtemp`, not a comparison |
| `gate10` | 7 failed | ALL ENOSPC (phase 2) |
| `gate11` | 1 failed, **0 ENOSPC** | `test_pty_huponexit_j1::test_disown_h_exempts_job_from_huponexit` — a REAL failure, therefore investigated: NOT touched by this slot, NOT oracle-bearing (zero `shell_oracle` references, so outside the guard scope entirely), and **5/5 passing on 3 consecutive isolated runs**. J1 signal-family PTY timing flake — the family already carried as #17 / slot 1.4. |
| `gate12` | 3 failed | ALL ENOSPC |
| **`gate13`** | **EXIT 0, 20364 passed, 0 ENOSPC** | the submitted gate |

**Proof the ENOSPC is NOT this branch's footprint:** phase 1 was run standalone
under a 2-second disk sampler — **19471 passed, EXIT 0, low-water 96 GB free**,
no oversized files captured. Free space also read 137 GB immediately after each
failing run. So the runner leaks nothing and the gate does not consume the
volume; an external, intermittent consumer does. (Banked lesson reconfirmed:
ONE gate machine-wide, and check free space first — the plan's ≥10 GB
precondition exists for exactly this.)

### Earlier gate flakes at `5593ffd0` (recorded, NOT slot defects)

The first run at `5593ffd0` (`tmp/gate6.txt`) hit 2 failures; the immediate
re-run (`tmp/gate7.txt`) was fully green. Both are load-sensitive and in modules
this slot NEVER TOUCHED (`git diff --name-only e52957d4..HEAD` lists neither),
and both pass in isolation:

- `tests/integration/test_timeformat.py::test_all_directives` — the assertion
  shape-compares digits→`N`, so a CPU percentage above 1000% under parallel load
  turns `p=N.NN` into `p=NNNN.NN`. This is the ALREADY-QUEUED campaign carry
  "timeformat %P carry #8" (RESUME.md:167), not a new finding.
- `tests/integration/job_control/test_background_jobs.py::TestJobControlWith
  Pipelines::test_complex_pipeline_background` — job-control timing under load;
  candidate for the 1.3 race/hygiene charter.

### Gate-flake investigation (host ENOSPC — NOT a slot defect)

Three intermediate gate attempts failed and were chased to root cause before the
green run; recorded because the campaign has hit this before (#22's second gate
died to host ENOSPC; the plan's ≥10 GB precondition exists for it):

- `tmp/gate2.txt` (14 failures, scattered across migrated AND untouched modules):
  `SpawnFailure: capture readback failed: [Errno 2] No such file …/.oracle-stdout`.
- `tmp/gate3.txt` (8 failures, one module): the SAME condition surfacing as
  `OSError: [Errno 28] No space left on device` at
  `tempfile.mkdtemp('psh-oracle-…')`.
- `tmp/gate4.txt` (1 failure + 1 error): `[Errno 28]` in
  `test_redirect_order_r1.py` at a plain `tempfile.mkdtemp()` — a test that does
  NOT use the oracle runner at all, which is what identifies the condition as
  host-wide rather than harness-caused.

Evidence it is not the migration: (1) ZERO stale `psh-oracle-*` directories
remain on the host (the runner's `TemporaryDirectory` cleanup is sound — no
leak); (2) free space read 134 GB immediately before AND after each failing run,
i.e. a transient external consumer, not monotonic growth; (3) a dedicated serial
phase run with a 3-second disk sampler held a low-water mark of **134 GB free**
with no failures; (4) the final gate on a quiet host (no competing pytest/gate
processes) is GREEN. Banked lesson reconfirmed: **ONE gate machine-wide**, and
check free space first.

## Deviations / STOP-and-report
- none. (Scope note surfaced to integrator at dispatch: guard-bearing migration
  set is 95 modules tree-wide, ~3x the "~30" framing — reconciled as the
  conformance-subset-vs-tree-wide distinction, consistent with A10's "thousands
  of cases"; proceeded per the census-first mechanics.)
