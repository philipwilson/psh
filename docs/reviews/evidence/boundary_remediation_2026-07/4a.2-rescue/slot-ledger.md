# SLOT LEDGER — 4A.2 (shutdown phases, MEDIUM-1)

Worktree `/Users/pwilson/src/psh-r4a-2`, branch `fix/remediation-4a-2`.
Base tip **d1e4f1ae** (v0.768.0 + record addendum) — pasted from
`git -C /Users/pwilson/src/psh-r4a-2 rev-parse HEAD`.

Oracle bash: `/opt/homebrew/bin/bash`, GNU bash 5.2.26(1)-release
(aarch64-apple-darwin23.2.0). Explicit argv in every probe. Never `/bin/bash`.

---

## Round 1 — Phase A (probe only; NO production edit)

### Instruments (all in `tmp/w4a2-probes/`, transcripts in `.../transcripts/`)

| Instrument | Substrate | Transcript |
|---|---|---|
| `probe_precedence.py` | subprocess, both shells, 3 input modes | `transcripts/precedence.txt` |
| `probe_bypass.py` | in-process Shell per subprocess; OBSERVABLE side effects | `transcripts/bypass.txt` |
| `probe_pty_history.py` | pexpect PTY, both shells | `transcripts/pty_history.txt` |
| `probe_pty_huponexit.py` | pexpect PTY **and** tmux real terminal | `transcripts/pty_huponexit.txt` |
| `probe_sighup_composition.py` | tmux real terminal (J1 construction) | `transcripts/sighup_composition.txt` |
| `probe_terminal.py` | in-process fault injection + subprocess signal cells | `transcripts/terminal.txt` |
| `probe_flake.py` | subprocess repetition, harness-faithful construction | `transcripts/flake.txt` |

**D-3.5 instrument-mirror compliance.** The brief's evidence was produced by an
INSTRUMENTED Shell recording shutdown steps. This slot's primary re-derivation
uses a DIFFERENT substrate — real observable consequences (was the detached
child actually reaped, per `waitpid` from the child's own parent; was the
histfile actually written on disk; did the bg child actually die) — and only
then carries a step-recording cell as a cross-check. Both agree; **no
STOP-AND-PROPOSE is raised against the brief's evidence.**

### A-1 Exit-status precedence — 66/66 cells AGREE with bash

22 cell shapes x 3 input modes (`-c`, script file, piped stdin), stdout and
exit status both compared. `transcripts/precedence.txt`, final line
`TOTAL cells=66 agree=66 disagree=0`.

Covers the brief's named family and more: no-trap; trap-no-exit; `trap 'exit
7'` over `exit 3` and over normal end; echo-then-exit; **bare `exit` inside the
trap** (preserves the pre-trap status: 3 and 1); `$?` at trap entry (3 / 1 / 0);
a command inside the trap that changes `$?` (does NOT change the status);
trap re-arming EXIT (does not re-fire); trap clearing itself; `set -e` x
trap-exit and x trap-no-exit; `exit` inside a FUNCTION called from the trap;
out-of-range (`exit 257` -> 1) and negative (`exit -1` -> 255) inside the trap;
a subshell `(exit 9)` inside the trap (does NOT exit the shell, `$?`=9 visible,
status still 3).

**Disposition: SPECIFY-AND-PIN, zero behavior change.** The brief's four
must-hold cells (7/3/7/7) are inside this set and reproduce. No divergent
precedence cell was found in the wider battery, so there is no finding to
report under the brief's "report, don't silently fix" clause.

The four precedence cells were ALSO re-measured at the PTY (`pty_history.txt`):
interactive `trap 'exit 7' EXIT` exits 7 on both the Ctrl-D and the `exit 3`
route, in BOTH shells. Precedence holds on the interactive route too.

### A-2 The bypass family — RED-ON-BASE, controls green (4 independent observables)

`transcripts/bypass.txt`, all at d1e4f1ae. Each row is a fresh subprocess. The
`no-trap` and `trap-noexit` arms are CONTROLS proving the observable is
reachable (D-3.4 lesson 8 — a careful label on a vacuous probe still misleads).

| observable | no-trap | trap-noexit | **trap-exit7** |
|---|---|---|---|
| detached child reaped (`waitpid` ECHILD) | reaped | reaped | **NOT reaped** |
| histfile written on disk | written+canary | written+canary | **not written** |
| bg job HUP'd (interactive+huponexit) | hupped | hupped | **NOT hupped** |
| recorded steps (cross-check) | history,hangup,reap,close | same | **close ONLY** |

Latch is `exit-builtin` in all three; the trap-exit arm raises `SystemExit(7)`.
The step-recording cross-check reproduces the brief's measurement exactly.

**Permanence (not deferral)** — `transcripts/terminal.txt`, cell `reentry`:
after the trap-exit shutdown, `_shutdown_reason` is latched and a SECOND
`shutdown('main-exit')` (which is exactly what `__main__`'s `finally` does)
returns immediately and runs NOTHING. `steps` is `[]` for the trap-exit arm and
`['reap']` for both controls.

### A-3 Ruling slot (b): history under trap-exit — bash SAVES. The documented skip is a DIVERGENCE.

`transcripts/pty_history.txt` — interactive shell at a real pty, HISTFILE set,
canary command, 2 exit routes x 3 trap dispositions, both shells.

| route | trap | bash histfile | psh histfile |
|---|---|---|---|
| Ctrl-D (repl-eof) | no-trap | canary | canary |
| Ctrl-D | trap-noexit | canary | canary |
| **Ctrl-D** | **trap-exit7** | **canary (status 7)** | **absent (status 7)** |
| `exit 3` (exit-builtin) | no-trap | canary | canary |
| `exit 3` | trap-noexit | canary | canary |
| **`exit 3`** | **trap-exit7** | **canary (status 7)** | **absent (status 7)** |

bash writes the histfile on BOTH routes even when the EXIT trap runs `exit 7`.
This matches bash's `exit_shell()` order (run the exit trap, then
`maybe_save_shell_history`, then the exit-time hangup) — the same phase ORDER
psh's `shutdown()` already has; only psh's bypass differs.

**Recommendation for ruling (b): FLIP the documented skip; declared delta.**
`shell.py#Shell.shutdown`'s docstring claim that a trap-raised `SystemExit`
"skips the save, as before" documents a bash divergence as if it were policy.
The skip is not a bash-parity fact; it is the bypass. `_HISTORY_SAVING_SHUTDOWNS`
route gating for NON-trap exits is untouched (must-not-flip) — the trap merely
stops CANCELLING the route's own policy.

### A-4 huponexit x trap-exit (the charter's named PTY cell) — RED-ON-BASE, construction-robust

`transcripts/pty_huponexit.txt`. bash arm spawns `--login -i` (bash gates the
exit-time HUP on interactive+login); psh arm is interactive+huponexit (J1
ruling 1 login-narrowing). Run in BOTH pexpect and tmux because J1 recorded
pexpect is not always faithful for job-control signal behavior.

| shell | trap | pexpect | tmux |
|---|---|---|---|
| bash | no-trap | HUP'd | HUP'd |
| psh | no-trap | HUP'd | HUP'd |
| bash | trap-noexit | HUP'd | HUP'd |
| psh | trap-noexit | HUP'd | HUP'd |
| **bash** | **trap-exit7** | **HUP'd** | **HUP'd** |
| **psh** | **trap-exit7** | **survived** | **survived** |

Both constructions agree on every row — no construction disagreement to report.
*Instrument caveat:* the exit status column reads `None` in this probe (it is
sampled before `close(force=True)` settles); the marker file is the observable
this cell asserts, and status is covered by A-1/`pty_history.txt` instead.

### A-5 Composition: trap-exit x the RECEIVED-SIGHUP route — RED-ON-BASE

`transcripts/sighup_composition.txt`, tmux real terminal (the J1 construction),
SIGHUP delivered to the shell's pane pid.

| shell | trap | job survived | histfile |
|---|---|---|---|
| bash | no-trap | no (fanned out) | written |
| psh | no-trap | no (fanned out) | written |
| bash | trap-noexit | no | written |
| psh | trap-noexit | no | written |
| **bash** | **trap-exit7** | **no (fanned out)** | **written** |
| **psh** | **trap-exit7** | **YES — no fan-out** | **absent** |

`signal_manager.py:327-332` wraps `shutdown('signal-hup')` in
`except BaseException: pass`, so the trap's `SystemExit` is absorbed THERE and
the signal death still wins (correct, 1.3b) — but the bypass already happened
INSIDE `shutdown()`, so the unconditional `hangup_all_jobs` fan-out and the
history save are both lost. This route needs no change of its own: it is fixed
by the phase split one level down.

### A-6 Ruling slot (c): the signal-death path — recommend NOT IN SCOPE

`transcripts/terminal.txt` section D — non-interactive script + SIGTERM, psh vs
bash, 4 dispositions:

| cell | bash | psh | verdict |
|---|---|---|---|
| no-trap | `''`, -15 | `''`, -15 | OK |
| trap-noexit | `'T\n'`, -15 | `'T\n'`, -15 | OK |
| trap-exit7 | `'T\n'`, -15 | `'T\n'`, -15 | OK |
| trap-exit7 + bg job | `'T\n'`, -15 | `'T\n'`, -15 | OK |

`_terminate_from_signal` matches bash on every cell. Its phases are
interactive-gated ones that do not apply to a non-interactive shell (bash's own
history save and `hangup_all_jobs` are gated on interactive/login), and the
process dies by signal immediately after, so process-global restoration is moot.

**Recommendation for ruling (c): the phase model does NOT extend to
`_terminate_from_signal`; 1.3b invariants stay untouched.** The interactive
SIGHUP route (A-5) reaches the phases through `shutdown()` and is covered
without touching 1.3b. Add the four cells above as MUST-HOLD pins.

### A-7 Terminal-signal precedence inside shutdown() (composition, must be specified)

`transcripts/terminal.txt` cell `close_raises` — `close()` injected to raise
`LeaseRestoreError` after completing:

| trap | escapes shutdown() | `__context__` |
|---|---|---|
| no-trap | `LeaseRestoreError` | none |
| trap-noexit | `LeaseRestoreError` | none |
| **trap-exit7** | **`LeaseRestoreError`** | **`SystemExit(7)`** |

Today the `finally: self.close()` shape means a close() failure REPLACES a
pending trap-exit `SystemExit`, which survives as `__context__`. That is the
right precedence — `LeaseRestoreError` is the loud internal-defect family and
must not be silenced by an exit status — and it is this slot's
**must-not-flip baseline**: the phase split must preserve it while now holding
the `SystemExit` across the *earlier* phases too.

### A-8 REPORT ROW (INSTANCE 3): the `TestExitTrapOnFatalSignal` flake — mechanism identified

Standing order R0.6 / brief S:test-hygiene. **No gate flake has occurred in
this slot yet** (no gate has been run); this is the Phase A investigation the
brief invited, run directly against the recorded loss.

Recorded loss (`/Users/pwilson/src/psh/tmp/flake-watch-3-5/gate-attest.txt`
line 608): `test_matches_bash_for_sigterm` —
`assert ('', -15) == ('EXIT-TRAP-FIRED\n', -15)`. psh's trap OUTPUT was lost;
the trap itself fired and the signal death was correct.

**Reproduced at base tip d1e4f1ae** with a harness-faithful construction
(`_inject_ready` verbatim, 10 ms existence poll, signal on first sighting):
**2 losses in 750 runs** across two independent batteries (1/250 and 1/500,
`transcripts/flake.txt` records the 500-run battery: `LOSS #1 at iter 397:
out='' rc=-15 ready_body='EXIT-TRAP-FIRED\n'`).

**Deciding observable — in BOTH losses the EXIT trap's output was found inside
the harness's own sentinel file**, i.e. the redirect target of
`: > "$ready"`. So at trap time a per-command redirection was still in effect:
this is the slot-1.3b redirect-restore window in a RESIDUAL form, not a
shutdown-phase-ordering defect. The harness aims squarely at it: `_inject_ready`
rewrites the script to `: > "$ready"; sleep 0.5`, and the sentinel file is
CREATED BY THE REDIRECTION SETUP — so "file exists" fires while stdout is
redirected into it.

Two negative results, published because the cells arrived (lesson 9):
* busy-polling (µs detection instead of 10 ms) gave 0/100 — it does not amplify;
* a random 0–12 ms post-detection delay gave 0/300 — the window is NOT simply
  "shortly after the sentinel appears", so a naive harness sleep would not
  close it.

This is a real psh-vs-bash divergence (the v0.753.0 record has bash 0/120), so
it is not purely a test-construction defect. **It is OUT OF THIS SLOT'S SCOPE**
(1.3b's surface + `psh/io_redirect/manager.py` frame lifecycle, both fenced).
Raised as a report row for a successor row / ruling, not touched.

### A-9 REPORT ROW: doc drift in the J1 PTY suite

`tests/system/interactive/test_pty_huponexit_j1.py:10-13` states the file is
"Opt-in (marked ``interactive``; not in the run-by-default PTY allowlist)" and
"Run with ``--run-interactive``". It IS in the run-by-default allowlist —
`tests/conftest.py:574`, `or "test_pty_huponexit_j1" in str(item.fspath)`.
The docstring is stale. Adjacent to this slot's PTY work; reporting, not fixing,
pending disposition.

---

### A-10 Planned pin shapes VERIFIED red-on-base (Phase-B pre-registration input)

D-3.4 lesson 7 — a test that passes before its fix proves nothing, and the
prover must force on the REAL path. Every planned assertion was run AT BASE
before being written as a pin. `probe_pinshape.py`,
`transcripts/pinshape.txt`, tip d1e4f1ae:

| pin | predicted | measured |
|---|---|---|
| P1 hup under trap-exit (interactive+huponexit) | RED | **RED** |
| P2 `signal-hup` fan-out under trap-exit | RED | **RED** |
| P3 history under trap-exit | RED | **RED** |
| P4 detached reap under trap-exit | RED | **RED** |
| M1 `close()` always runs | GREEN | GREEN |
| M2 trap status still escapes as `SystemExit(7)` | GREEN | GREEN |
| M3 `close()` `LeaseRestoreError` outranks held SystemExit (as `__context__`) | GREEN | GREEN |
| M4 second `shutdown()` is a latch no-op | GREEN | GREEN |
| M5 no-trap control still HUPs (P1's non-vacuity control) | GREEN | GREEN |

`TOTAL pins=9 red=4 green=5 mispredicted=0`.

The deterministic cells reuse the pin shape ALREADY in the tree
(`tests/unit/executor/test_boundary_j1_job_lifecycle.py#_make_job` +
patched `os.killpg`, per `test_shutdown_signal_hup_reason_fans_out`): a
SYNTHETIC job and no real signal, so they are xdist-safe and run in the
ordinary gate rather than behind `--run-interactive`. NAME-VS-BODY sweep of
existing siblings: `tests/unit/core/test_shutdown_f2.py` already pins
idempotence / first-reason-wins / at-most-once / trap-exit status override;
`test_shutdown_census_f2.py` pins the call-site allowlist (my design adds no
call site); `test_pty_shutdown_route_f2.py` + `test_pty_huponexit_j1.py` are
the PTY precedents I follow. **Red-on-base counts here are re-derived at the
declared tip before any claim, never carried (D-4A.1).**

## Pre-declared ruling requests (Phase A)

* **(a)** disposition table above + the phase-split design in the Phase A
  report → GO gate for Phase B.
* **(b)** history-under-trap-exit: recommend FLIP (bash-divergence, declared
  delta, docstring corrected). Evidence A-3.
* **(c)** signal-death-path applicability: recommend OUT (1.3b untouched;
  four must-hold pins added). Evidence A-6.

## RN-Cdoc — round 1

Doc/comment deltas since last round: **NONE.** No production, test, or doc file
has been modified in this worktree. `git status --porcelain` at d1e4f1ae is
EMPTY (the probe material lives under the gitignored `tmp/`).

---

## Round 2 — Phase B (ruled design landed)

R1 ACK: rulings (a) APPROVED-as-proposed, (b) FLIP approved as a declared
toward-bash delta, (c) OUT OF SCOPE, A-8 = REPORT + successor row D-4A.2-s1,
A-9 folded into Phase B. Dead-drop re-read and md5-verified
(`cb3a632f0d7b71255ba87e94595cfb11`, R0+R1 present).

### Ordered changes (per-hunk staged, four commits off d1e4f1ae)

| SHA | change |
|---|---|
| 06dba0f8 | production: `Shell.shutdown` phase split + docstring correction |
| 90ac3c2a | pins: unit battery, PTY battery, ruling-(c) must-hold, conftest allowlist |
| f3338b38 | docs: `psh/core/CLAUDE.md` shutdown-phase invariants |
| d18cbe8f | A-9: stale allowlist claim in the J1 PTY docstring |

SHAs pasted from `git log --oneline d1e4f1ae..HEAD`. `git status --porcelain`
EMPTY after the four commits (no stray file).

### Certification rows (post-state, each with its instrument)

| claim | instrument | result |
|---|---|---|
| the 4 bypass observables flip | `probe_bypass.py` → `transcripts/bypass-postfix.txt` | reap/history/hangup all TRUE under trap-exit; steps `history,hangup,reap,close` |
| PTY history reaches bash parity | `probe_pty_history.py` → `transcripts/pty_history-postfix.txt` | 6/6 OK (was 4 OK / 2 DIFF) |
| huponexit × trap-exit reaches parity | `probe_pty_huponexit.py` → `transcripts/pty_huponexit-postfix.txt` | psh HUPs in BOTH constructions, matching bash on all 6 rows |
| received-SIGHUP × trap-exit reaches parity | `probe_sighup_composition.py` → `transcripts/sighup_composition-postfix.txt` | psh fans out AND saves history; all 6 rows match bash |
| unit pins RED at base, GREEN at tip | detached probe checkout at d1e4f1ae → `transcripts/redonbase-unit.txt` | **measured split: 7 failed / 8 passed at base**; 15/15 pass at tip |
| PTY pins RED at base, GREEN at tip | same checkout → `transcripts/redonbase-pty.txt` | **measured split: 2 failed / 1 passed at base**; 3/3 pass at tip |
| every load-bearing arm is independently pinned | `mutate_m8.py` → `transcripts/m8-mutations.txt` | 7 mutations, each kills a NON-EMPTY and DISTINCT set; harness exits 0 |
| doc pointers resolve | `verify_doc_pointers.py` → `transcripts/doc-pointers.txt` | `checked=9 failures=0` |
| lint | `ruff check psh tests tools` | `All checks passed!` |
| types | `mypy` | `Success: no issues found in 275 source files` |

Red-on-base was re-derived AT d1e4f1ae in a throwaway detached worktree with
this branch's test files copied in — never carried from Phase A, and never
measured inside the live worktree (B71). Both probe worktrees removed
(`git worktree list` shows only the three long-lived ones).

M8 note, published because the cell arrived: the first M8-g ("let the trap veto
history again") killed EXACTLY M8-a's set and was DROPPED rather than kept as a
padding row — the phase functions take only `reason` and cannot observe the
held signal, so that mutation can only be spelled "history never runs", which
M8-a already covers. It was replaced by the arm that is genuinely separate —
dropping the ROUTE gate — which kills exactly
`test_history_route_gating_is_unchanged_for_non_trap_exits` and nothing else.

### PRE-REGISTRATION — heavy run 1 (full gate)

Command: `python -u run_tests.py --parallel > tmp/gate-1.txt 2>&1` (foreground,
never shell-`&`), at tip d18cbe8f.

Base figures (brief §Base, attestation e2e5d3b4 gated ec995a76):
phase1 22,466 + serial 1,017 = **23,483 passed**, 1,618 skipped, 10 xfail.

Expected deltas — new tests only, no existing test changes phase or outcome:

* `tests/unit/core/test_shutdown_phases_4a2.py` — **+15 passed, PARALLEL
  phase** (`tests/unit/core/` carries no serial path marker).
* `tests/system/interactive/test_pty_shutdown_phases_4a2.py` — **+3 passed,
  SERIAL phase** (auto-marked by the `test_pty` path marker) and NOT skipped
  (conftest allowlist entry added in 90ac3c2a).
* `tests/integration/job_control/test_exit_trap_paths.py` — **+1 passed,
  SERIAL phase** (`job_control` path marker).

Predicted totals: **phase1 22,481 + serial 1,021 = 23,502 passed**, 1,618
skipped (unchanged), 10 xfail (unchanged).

Named expected-red pins at this tip: **NONE.** Every pin this slot adds is
green at d18cbe8f; the red-on-base evidence lives in the two detached-checkout
transcripts above.

Expected failures: **NONE.** Predicted `ruff` clean and `mypy` 275 files (both
already measured green at this tip).

Flake watch: `TestExitTrapOnFatalSignal` is in the serial phase and lives in
this slot's subject area. Per R1.4 a firing there is reported citing **A-8** as
the prior cause hypothesis (1.3b redirect-restore residual window amplified by
the harness's own `: > "$ready"` sentinel) rather than re-investigated, and
never silently re-run.

### PRE-REGISTRATION — heavy run 2 (compare-bash)

Command: `python -m pytest tests/behavioral --compare-bash -n auto -q`
(NEVER `run_tests.py --compare-bash`). Base: 3,042 / 26 EXACT.
Expected: **3,042 / 26 EXACT, unchanged** — this slot adds no behavioral
golden case, and exit-status precedence is unchanged (66/66 agreement
re-measured in Phase A and unaffected by the split, which re-raises the
identical `SystemExit` object).

### RN-Cdoc — round 2

Doc/comment deltas since round 1:

* `psh/shell.py` — `Shell.shutdown` docstring rewritten (the "skips the save,
  as before" claim removed as a documented divergence per ruling (b)); new
  docstrings on `_run_shutdown_phases`, `_shutdown_fire_exit_trap`,
  `_shutdown_save_history`, `_shutdown_dispose_jobs`. Commit 06dba0f8.
* `psh/core/CLAUDE.md` — new "Shutdown phases: the EXIT trap gets no veto"
  section. Commit f3338b38.
* `tests/conftest.py` — allowlist comment for the 4A.2 PTY file. Commit 90ac3c2a.
* `tests/system/interactive/test_pty_huponexit_j1.py` — A-9 correction. Commit d18cbe8f.
* New test-file module docstrings in the two new pin files. Commit 90ac3c2a.

### Must-not-flip: fence-post suites re-run at tip d18cbe8f (targeted, pre-gate)

Run BEFORE requesting the heavy-run GO, so a guard-rail break would cost a
targeted run rather than a gate cycle. Not heavy runs (single-file/dir
selections; `pgrep -f pytest` unpiped and clear before each).

| suite set | result |
|---|---|
| `test_shutdown_f2.py` + `test_shutdown_census_f2.py` + `test_boundary_j1_job_lifecycle.py` + `test_substitution_abort_guards.py` + all of `tests/unit/tooling/` | **635 passed** |
| 4A.1's four lease suites + `test_activation_transaction_4a1.py` + `test_managed_signal_lease_4a1.py` + `test_failed_exec_lease_4a1.py` + `test_std_fd_lease_f2.py` + all of `tests/system/interactive/` | **291 passed, 16 skipped, 2 xfailed** |

926 passed across every fence post named in the brief: the census allowlist is
untouched (the phase split adds no `execute_exit_trap` / `save_to_file` call
site), 4A.1's close()-ordering and quarantine pins are green, the J1 dispose
pins are green, 2.4's abort guards are green, and the whole PTY tier — the
existing files plus this slot's new one — is green.

Incidental verification while locating a fence post: `psh/core/CLAUDE.md:682`'s
4A.1 pointer `test_managed_signal_lease_4a1.py#test_dropped_shell_holding_a_trap_lease_still_rejects_the_next`
RESOLVES — the file is `tests/unit/interactive/` (a bare filename, not
path-qualified, unlike this slot's own test pointers). Not a defect; recorded
so the near-miss is not re-investigated later.

---

## Round 3 — heavy runs (R2 GO, cited ledger :334 and :363)

R2 ACK: GO for both heavy runs; M8-g drop-and-replace accepted as disclosed;
ruling (c) one-cell narrowing accepted and the restatement offer declined;
ruling (b) route-owns-policy must-hold accepted. Dead-drop md5 at read time
`19b459164b076f56f561b9a4e655c7a0`, R0+R1+R2 present.

### Heavy run 1 — full gate at tip d18cbe8f

`python -u run_tests.py --parallel > tmp/gate-1.txt 2>&1`, foreground; exceeded
the 600 s tool timeout and was MOVED TO BACKGROUND by the harness (never
stopped, never shell-`&`), then awaited in-turn with a bounded poll. Transcript
`tmp/gate-1.txt` (full copy also at `tmp/last-test-run.txt`).

| figure | pre-registered (:334) | measured | verdict |
|---|---|---|---|
| phase 1 (parallel) passed | 22,481 | **22,481** | exact |
| phase 1b (serial) passed | 1,021 | **1,021** | exact |
| combined passed | 23,502 | **23,502** | exact |
| skipped | 1,618 unchanged | **1,618** | exact |
| xfailed | 10 unchanged | **10** | exact |
| failures / errors | none | **0** (`grep -c "FAILED\|ERROR"` = 0) | exact |

`✅ All test phases PASSED`. Every pre-registered number landed on its
prediction; no unpredicted movement anywhere in the suite.

Phase PLACEMENT verified independently of the counts rather than inferred from
them (D-3.5: a derived relation gets its own instrument) — `--collect-only`
with the marker expressions the runner uses:
`test_shutdown_phases_4a2.py` → 15 collected under `-m "not serial"`, 0 under
`-m serial`; `test_pty_shutdown_phases_4a2.py` → 3 collected under `-m serial`.
So the +15/+3/+1 split is measured, not assumed, and the new PTY file provably
RAN (it appears in the phase-1b transcript) rather than being silently skipped.

**Flake posture: the exit-trap family did NOT fire.** Zero failures in the
serial phase, which is where `TestExitTrapOnFatalSignal` runs. A-8 stands as
the recorded prior for any future recurrence; nothing to report and nothing
re-run.

### Heavy run 2 — compare-bash at tip d18cbe8f

`python -u -m pytest tests/behavioral --compare-bash -n auto -q`
(NEVER `run_tests.py --compare-bash`). Transcript `tmp/compare-bash-1.txt`.

**3,042 passed, 26 skipped, 0 failed** — identical to the base figure
(3,042 / 26) and to the pre-registration at :363.

Precision on the word EXACT, since the run prints no such banner: in this
harness a divergence is a hard assertion, not a warning —
`tests/behavioral/test_golden_behavior.py` asserts `psh_stdout == bash_stdout`
and `psh_exit == bash_exit` per case (only stderr-PRESENCE disagreement is a
non-gating warning). 3,042 passed with 0 failed therefore means zero stdout or
exit-status divergence across the corpus. That is the EXACT floor, held.

## Discharge audit (counts DERIVED by script, never hand-tallied)

Instrument: the AST/diff counter run at tip d18cbe8f (output in this round's
transcript set). New pins: **unit 15 + PTY 3 + ruling-(c) 1 = 19**.
Tree delta `git diff --stat d1e4f1ae..HEAD`: 7 files, 586 insertions,
32 deletions.

| charter clause | discharged by | evidence |
|---|---|---|
| EXIT-trap `SystemExit` cannot bypass **job disposition** | `_run_shutdown_phases` holds the signal | P1 + P2 unit pins (red at base), PTY huponexit pin, `pty_huponexit-postfix.txt` + `sighup_composition-postfix.txt` both-construction parity |
| ... cannot bypass **detached reaping** | same | P4 unit pin (red at base), `bypass-postfix.txt` reap row |
| ... cannot bypass **required history policy** | phase 2 + ruling (b) flip | P3 unit pin, PTY history pin, `pty_history-postfix.txt` 6/6 OK |
| ... cannot bypass **resource restoration** | phases always reach `close()` | M1 pin plus `test_close_still_runs_and_releases_ownership_under_a_trap_that_exits` (coordinator ownership RELEASED under trap-exit, measured) |
| **exit-status precedence specified** | docstring + `core/CLAUDE.md` + pins | 66/66 agreement table (`precedence.txt`), M2/M3 pins, M8-e lock |
| PTY-verified incl. huponexit (exit criterion) | `test_pty_shutdown_phases_4a2.py` | 2 red-at-base + 1 must-hold, run BY DEFAULT in the gate |

**Honest scope note on the exit criterion.** "PTY tests prove ... reap" is
discharged at the UNIT level, not the PTY level, and deliberately: a detached
reap is observable only to the reaping process's own parent, so a PTY cell
cannot see it (the shell under test is the pty's child, and its children are
reparented on death). The PTY battery discharges the HUP and history halves,
which ARE terminal-observable; the reap half is pinned by P4 against the real
`reap_detached` via its ECHILD arm. Stated rather than glossed so the criterion
is not recorded as more PTY-proven than it is.

Likewise "leave no ... lease behind" is discharged as a COMPOSITION, not a new
PTY measurement: this slot pins that the phases always reach `close()` and that
ownership is released under trap-exit; what `close()` then restores (locale,
managed and trap-leased dispositions, std fds) is 4A.1's settled surface and
stays pinned by its own suites, all of which were re-run green here.

## Bounced-rows replay

**No row was bounced in this slot.** Phase A was accepted at first submission
(R1) and Phase B GO granted at first request (R2); no ruling was reversed and
no claim retracted. Two self-corrections are recorded above rather than hidden:
the round-1 `git status` wording (fixed before the Phase A report went out) and
the M8-g mutation that duplicated M8-a's kill set (dropped and replaced, and
the replacement closed a genuinely unlocked must-hold). Both were caught by my
own instruments, not by a verifier bounce.

## Must-not-flip: final state

Every guard rail in the brief was re-run green at d18cbe8f — 926 tests in the
targeted pre-gate pass (fence-post table above) and again inside the full gate:
the four precedence cells (inside 66/66), 2.4's teardown swallow, 4A.1's entire
close() contract and lease suites, 1.3b's signal-death invariants (untouched
per ruling (c), plus a new must-hold cell), `_HISTORY_SAVING_SHUTDOWNS` route
gating for non-trap exits (locked by M8-g), exit-trap at-most-once, and the
unconditional `hangup_all_jobs` fan-out on received SIGHUP.

## FINAL TIP: d18cbe8f — LEDGER FROZEN

Four commits off d1e4f1ae: 06dba0f8, 90ac3c2a, f3338b38, d18cbe8f.
`git status --porcelain` EMPTY. No commit after this declaration; any
correction is a SendMessage plus a dated addendum after the verdict.

---

# ADDENDUM 1 — 2026-08-07, post-R3-verdict (freeze lifted by R3)

R3 ACK: **VERDICT BOUNCE, 1 blocker / 1 REAL / 0 false.** I accept the blocker
without qualification. This addendum discharges required item 1 (correct A-1);
the disposition proposal for the divergence itself is required item 2 and went
to the integrator as a STOP-AND-PROPOSE before any implementation.

## A-1 CORRECTED — the bare-exit cells were VACUOUS

**What A-1 said** (frozen text, §A-1): that the battery covered "bare `exit`
inside the trap (preserves the pre-trap status: 3 and 1)" and that "No
divergent precedence cell was found in the wider battery, so there is no
finding to report."

**What was actually true.** The two bare-exit cells were
`trap 'exit' EXIT; exit 3` → 3/3 and `trap 'exit' EXIT; false` → 1/1. In
BOTH, nothing inside the trap body changes `$?` before the bare `exit`, so
"uses the pre-trap status" and "uses the current `$?`" predict the SAME
answer. **The cells could not have failed for the reason their row gave.**
That is D-3.4 lesson 8 exactly — a careful label on a vacuous probe still
misleads — and I cited that lesson as governing while committing it, inside my
own charter's named family, in a row whose parenthetical ("preserves the
pre-trap status") asserted the very semantics the cell could not test.

**Precisely which claim was false.** The figure `66/66 agree` is factually
true as measured — all 66 rows did agree, and the harness re-measured them.
What was false is the INFERENCE drawn from it: "no divergent precedence cell
exists, so there is nothing to report." A battery cannot license that
conclusion over a rule it is structurally blind to. The number stands; the
conclusion does not, and it is withdrawn.

**The divergence the vacuous cells hid** (re-derived by me at tip d18cbe8f
with a NEW discriminating battery, `probe_bare_exit.py` →
`transcripts/bare-exit.txt`; 13 shapes × 3 input modes = 39 rows):

**`TOTAL rows=39 agree=18 disagree=21`, and all 21 disagreements are in
DISCRIMINATING cells** (cells whose trap body changes `$?` before the bare
`exit`). Every divergence reproduces identically in `-c`, script-file AND
piped-stdin mode.

| cell | bash 5.2.26 | psh |
|---|---|---|
| `trap 'false; exit' EXIT; exit 3` | 3 | **1** |
| `trap 'true; exit' EXIT; exit 3` | 3 | **0** |
| `trap 'false; exit' EXIT` (normal end) | 0 | **1** |
| `trap 'true; exit' EXIT; false` | 1 | **0** |
| `trap '(exit 9); exit' EXIT; exit 3` | 3 | **9** |
| `trap 'false; echo q=$?; exit' EXIT; exit 3` | q=1, 3 | q=1, **0** |
| `f() { false; exit; }; trap f EXIT; exit 3` | 3 | **1** |

Controls that AGREE, retained so the divergent rows cannot be over-read:
the two original vacuous shapes (3/3 and 1/1), `trap 'false' EXIT; exit 3`
→ 3/3 (the trap body's status alone does NOT leak — psh already gets this
right), and the explicit-operand guard `trap 'false; exit 7' EXIT; exit 3`
→ 7/7.

**The rule, stated exactly.** In bash the EXIT trap's body cannot change the
shell's exit status EXCEPT through an explicit `exit N`; a BARE `exit` in the
body means "unspecified", so the status stays the value in effect when the
trap was entered. psh resolves a bare `exit` from the CURRENT `$?` instead, so
the last command of the trap body silently becomes the shell's status. Note
the `echo q=$?` row: `$?` READ inside the trap is the current value in BOTH
shells (q=1 both) — the divergence is confined to what a bare `exit`
RESOLVES to, not to `$?` itself.

**Scope of the rule — NEW, beyond the harness's four cells.** The saved-status
rule is EXIT-trap-SPECIFIC. For non-EXIT traps bash and psh AGREE and both use
the current `$?` (`probe_nonexit_trap.sh` → `transcripts/nonexit-trap.txt`,
4 cells; the explicit `trap 'echo entry=$?; false; exit' USR1` row shows
entry=0 yet status 1 in BOTH). Any fix must therefore NOT be a general
"saved status for all traps" mechanism.

**Provenance.** The divergence is PRE-EXISTING (identical at base d1e4f1ae;
this branch changed no behavior here) and pinned nowhere in the tree. It is a
record-and-coverage failure of mine, not a regression I introduced.

## Why my own instruments did not catch it

The axis I contributed — "bare `exit` inside the trap" — is the one I did not
walk, which is D-3.4 lesson 2 verbatim. My AXIS-QUANTIFICATION list carried
spelling, channel, mode, quoting and a dozen more, and I varied input mode
exhaustively (3 modes × 22 shapes) while leaving the axis that actually
mattered — **what the trap BODY does before the bare exit** — at a single
value: nothing. Breadth on the axes I had listed disguised a hole on the axis
the cell was about. The corrected battery composes the body, and the cells are
now labelled DISC / control in the instrument itself so a future reader can
see at a glance which rows can discriminate and which cannot.

**Correction to the round-1 record:** A-1's sentence "no divergent precedence
cell was found ... there is no finding to report" is WITHDRAWN. The finding
exists, is now measured at 21 divergent rows, and its disposition is the
integrator's ruling.

---

## Round 4 — R4 fix round (bare `exit` in an EXIT trap)

R4 ACK: option (i) FIX-IN-SLOT approved; **SCOPE EXTENDED to exactly
`psh/core/trap_manager.py` and `psh/builtins/core.py`, for exactly the
bare-exit-in-EXIT-trap seam** — recorded here as required. Nothing else in
those two files was touched beyond that seam and one stale route comment in
`builtins/core.py` (declared in its commit message). Dead-drop md5 at read
time `192212d0f640d2f58c80d3262ffc9ea3`, R0–R4.

### Ordered changes (per-hunk, four commits off d18cbe8f)

| SHA | change |
|---|---|
| 07521ea1 | seam: `TrapManager.exit_trap_entry_status` + `ExitBuiltin` consumes it |
| 146f0728 | `close()` restored to UNCONDITIONAL + guarded note render |
| 09dc3454 | pins: committed precedence table, unit cells, PTY control, census comment |
| 80042767 | docs: exit-STATUS rule in core/CLAUDE.md; route comments at four phases |

SHAs pasted from `git log --oneline d18cbe8f..HEAD`; porcelain EMPTY after.

### The fix

`execute_trap` already took `saved_exit_code` at trap entry and discarded it
for EXIT. It is now exposed as `TrapManager.exit_trap_entry_status` and
consumed **solely** by `ExitBuiltin.execute` for a BARE `exit`. Explicit
`exit N` is untouched. **EXIT-ONLY**: the value is CLEARED for non-EXIT traps
and saved/restored across nesting, so a signal trap nested inside an EXIT
action still takes the signal rule.

### Certification rows

| claim | instrument | result |
|---|---|---|
| the divergence closes | `probe_bare_exit.py` | **39/39 agree, 0 disagree** (was 18/21) |
| non-EXIT traps unchanged | `probe_nonexit_trap.sh` → `transcripts/nonexit-trap.txt` | 4/4 agree, incl. the `entry=0`/rc=1 discriminator |
| red-on-base at the PRE-FIX tip d18cbe8f | detached worktree → `transcripts/redonbase-r4.txt` | **measured split: 22 failed / 40 passed** = 21 precedence rows + 1 close-bookkeeping cell; PTY 0 (its cells were already green — correctly not red for THIS fix) |
| spec now survives the merge | committed conformance file | 13 shapes × 3 modes = **39 rows** + 1 dedicated must-hold = 40 tests |
| every arm independently locked | `mutate_m8.py` → `transcripts/m8-mutations.txt` | **10 mutations, each kills a NON-EMPTY DISTINCT set**; harness exits 0 |
| seam localization | same | M8-i kills **21** precedence rows, M8-j kills **4**, both with **0** collateral in the phase battery |
| doc pointers | `verify_doc_pointers.py` → `transcripts/doc-pointers.txt` | `checked=12 failures=0`, re-stamped at the COMMITTED tip |
| lint / types | `ruff check psh tests tools` / `mypy` | clean / 275 files |
| fence posts | targeted runs at this tip | `tests/unit/core` 804; `tests/integration/job_control` 392; tooling+system/interactive+pins 855+96 |

Two instrument self-corrections, published because the cells arrived:

* **M8-h could not be spelled as one half.** Reverting only the `close()`
  finally kills nothing, because the guarded note render (added in the same
  commit) stops the escape — and reverting only the note kills nothing for the
  mirror reason. A one-half mutation would have read as an UNPINNED arm when
  the arm is in fact doubly defended. M8-h therefore reverts BOTH halves, and
  the harness comment says why.
* **The seam kill-counts were an artifact before they were a number.** The
  harness's `^FAILED [^:]+::(\w+)` stops at the `[` of a parametrized id, so
  21 failing rows collapsed to ONE name and M8-i first read "kills 1". Fixed
  to capture the full node id; the counts above are post-fix.

### Nit dispositions (all 13, each classified)

| # | nit | disposition |
|---|---|---|
| 1 | precedence spec only in untracked tmp | **FIXED** — committed conformance table (39 rows) |
| 2 | signal-hup × history half-cell | **FIXED** — `test_signal_hup_route_saves_history_under_a_trap_that_exits` |
| 3 | PTY huponexit lacks in-file anti-vacuity control | **FIXED** — `test_without_huponexit_the_job_survives_a_trap_that_exits` |
| 4 | non-SystemExit BaseException unpinned | **FIXED** — KeyboardInterrupt driven through the trap phase |
| 5 | stale census history-allowlist comment | **FIXED** |
| 6 | red-on-base not stated as a measured split | **FIXED** — docstring now states the 7/8 split |
| 7 | conftest PTY allowlist grows to a 6th file | **DECLINED (not mine to sanction)** — R2 already resolved it as declared-and-justified; recorded here so the trail is closed |
| 8 | `_shutdown_fire_exit_trap` ignores `reason` | **DECLINED** — the uniform `(reason)` phase signature is deliberate: the loop dispatches all three phases identically, and a special-cased signature would make the phase list heterogeneous to save one parameter. Stated rather than silently kept |
| 9 | `close()` no longer unconditional | **FIXED** (not accepted as pathological) — phase loop under the `close()` finally + guarded note; M8-h locks it |
| 10 | route-side comments describe two phases | **FIXED** — `builtins/core.py`, `repl_loop.py`, `interactive/CLAUDE.md` |
| 11 | MEDIUM-1 row's reap leg is unit- not PTY-level | **ACKNOWLEDGED, integrator-owned** — my Round-3 honest scope note stands; reconciliation of the row wording is a ceremony action |
| 12 | `close()` skipped via unrenderable `__str__` | **FIXED** — same commit as #9 |
| 13 | `doc-pointers.txt` stamped with the base SHA | **FIXED** — re-run and re-stamped at committed tip 80042767 |

An incidental find while fixing #1: the new file initially tripped
`test_bash_oracle_resolution.py::test_no_bash_oracle_outside_resolver` on a
literal `"bash"` used as a MODE SELECTOR argument. The guard cannot tell that
from a hard-coded oracle binary, and it is right not to try — fixed by passing
the runner CALLABLE instead of a shell-name string, not by seeking an
exemption.

### PRE-REGISTRATION — heavy run 3 (full gate) at tip 80042767

Command: `python -u run_tests.py --parallel > tmp/gate-2.txt 2>&1`, foreground.

Baseline = the round-3 gate at d18cbe8f: phase1 22,481 + serial 1,021 =
23,502 passed, 1,618 skipped, 10 xfail.

Expected deltas (placement verified by `--collect-only` with the runner's own
marker expressions, not inferred):

* `tests/conformance/bash/test_exit_trap_status_precedence_conformance.py` —
  **+40 passed, PARALLEL** (40 collected under `-m "not serial"`, 0 under
  `-m serial`).
* `tests/unit/core/test_shutdown_phases_4a2.py` — 15 → **18, PARALLEL**
  (+3: signal-hup history, BaseException hold, close-bookkeeping).
* `tests/system/interactive/test_pty_shutdown_phases_4a2.py` — 3 → **4,
  SERIAL** (+1 anti-vacuity control).

Predicted totals: **phase1 22,524 + serial 1,022 = 23,546 passed**, 1,618
skipped (unchanged), 10 xfail (unchanged). Expected-red pins at this tip:
**NONE**. Expected failures: **NONE**. ruff clean, mypy 275 (both already
green here).

Flake watch: unchanged — a firing of `TestExitTrapOnFatalSignal` is reported
citing **A-8** as the prior, not re-investigated.

### PRE-REGISTRATION — heavy run 4 (compare-bash) at tip 80042767

Command: `python -m pytest tests/behavioral --compare-bash -n auto -q`.
Base 3,042 / 26. Expected **3,042 / 26 unchanged**: no golden case is added,
and although this round IS a behavior change, it moves psh TOWARD bash — the
corpus was green before with psh diverging, so every case that passed still
passes. A movement here would mean a golden case had pinned the divergent
direction, which the harness's grep says does not exist; if one moves, that is
a finding and I stop.

### RN-Cdoc — round 4

* `psh/core/trap_manager.py` — `exit_trap_entry_status` docstring + the
  set/restore comment in `execute_trap` (07521ea1).
* `psh/builtins/core.py` — bare-exit comment rewritten; route comment now
  names four phases (07521ea1).
* `psh/shell.py` — `shutdown` unconditional-close comment; guarded-note
  comment (146f0728).
* `psh/core/CLAUDE.md` — new exit-STATUS paragraph, kept separate from the
  exception-precedence one (80042767).
* `psh/interactive/repl_loop.py`, `psh/interactive/CLAUDE.md` — route comments
  at four phases (80042767).
* `tests/unit/tooling/test_shutdown_census_f2.py` — allowlist comment (09dc3454).
* New module docstring in the conformance file; module docstring of the unit
  battery restated as the measured split (09dc3454).

### Heavy run 3 — full gate at tip 80042767 (R5 GO, cited :705)

`python -u run_tests.py --parallel > tmp/gate-2.txt 2>&1`, foreground; exceeded
the 600 s tool timeout and was MOVED TO BACKGROUND by the harness, then awaited
in-turn with a bounded poll. Transcript `tmp/gate-2.txt`.

| figure | pre-registered (:705) | measured |
|---|---|---|
| phase 1 (parallel) | 22,524 | **22,524** |
| phase 1b (serial) | 1,022 | **1,022** |
| combined passed | 23,546 | **23,546** |
| skipped | 1,618 | **1,618** |
| xfailed | 10 | **10** |
| failures / errors | none | **0** |

`✅ All test phases PASSED`. Exit-trap flake family did NOT fire (0 failures in
the serial phase, where it runs); A-8 remains the recorded prior.

### Heavy run 4 — compare-bash at tip 80042767 (cited :731)

`python -u -m pytest tests/behavioral --compare-bash -n auto -q`.
Transcript `tmp/compare-bash-2.txt`. **3,042 passed / 26 skipped / 0 failed** —
unchanged from base, as pre-registered. The stop-and-report escape hatch was
not needed: no golden case had pinned the divergent direction, so the
toward-bash change moved nothing. A divergence would have been a hard
assertion here, not a warning (`test_golden_behavior.py` asserts stdout and
exit status per case), so 0 failed IS the EXACT floor.

## Discharge audit — FINAL (counts derived by script at the declared tip)

Pins by `--collect-only` (authoritative, not hand-tallied): unit phase battery
**18**, PTY battery **4**, precedence spec **40** (13 shapes × 3 modes + 1
dedicated must-hold), plus the ruling-(c) cell in `test_exit_trap_paths.py`
= **63 committed tests** for this slot. Whole-slot delta vs campaign base
d1e4f1ae: **13 files changed, 907 insertions, 39 deletions**.

Charter clauses, all discharged (evidence unchanged from Round 3 except where
this round moved it):

| clause | evidence |
|---|---|
| no bypass of job disposition | P1/P2 unit + PTY huponexit + both-construction parity |
| no bypass of detached reaping | P4 unit (real `reap_detached` ECHILD arm) |
| no bypass of required history policy | P3 + PTY history + signal-hup half + ruling (b) |
| no bypass of resource restoration | `close()` UNCONDITIONAL (restored this round), ownership-release cell, M8-e/M8-h |
| **exit-status precedence SPECIFIED** | **committed 39-row conformance table + the EXIT-only must-hold** — this round replaced a tmp transcript and a FALSE conclusion with a ratcheted spec |
| PTY-verified incl. huponexit | PTY battery, run by default, now with its own anti-vacuity control |

The Round-3 honest scope notes stand unchanged: the reap leg is discharged at
UNIT level because a detached reap is not terminal-observable, and "no lease
behind" is a composition of this slot's `close()` guarantee with 4A.1's pinned
restores. R3's harness endorsed both readings.

## Bounced-rows replay — FINAL

**One bounce, one row: R3's blocker.** Replayed at the declared tip:

* The four integrator cells now AGREE with bash (integrator re-ran them at a
  detached checkout of 80042767 and confirmed 3/3, 3/3, 0/0, and the
  localizing `q=$?` cell 3/3).
* My own wider battery: **39/39 agree** (was 18 agree / 21 disagree).
* The false claim is corrected in Addendum 1, with the
  figure-true/inference-false distinction stated explicitly, and the two
  vacuous cells are now COMMITTED as labelled `control-` rows so the shape
  that misled cannot quietly recur.
* Coverage remedy landed alongside: the spec is in the tree, not in tmp.

Prior rounds: no other row was bounced. Self-corrections caught by my own
instruments rather than by a verifier — the round-1 `git status` wording, the
M8-g kill-set duplicate, the M8-h one-half unspellability, the parametrized-id
counting artifact, and the truncated red-on-base transcript — are recorded in
place rather than folded away.

## FINAL TIP: 80042767 — LEDGER FROZEN

Eight commits off d1e4f1ae: 06dba0f8, 90ac3c2a, f3338b38, d18cbe8f (round 2)
and 07521ea1, 146f0728, 09dc3454, 80042767 (round 4). `git status --porcelain`
EMPTY. No commit follows this declaration; any correction is a SendMessage plus
a dated addendum after the verdict.
