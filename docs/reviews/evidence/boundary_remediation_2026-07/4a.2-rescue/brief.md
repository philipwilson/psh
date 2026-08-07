# Slot 4A.2 — Shutdown phases (MEDIUM-1) — second Wave-4 slot

**Charter:** integrator plan §6 Wave 4 bullet 2 + sequence §9 Package 4A
item 4: *"Split shutdown into mandatory phases so EXIT-trap `SystemExit`
cannot bypass job disposition, detached reaping, required history policy,
or resource restoration. Specify exit-status precedence."* Exit criterion
(sequence §9): *"PTY tests prove EXIT-trap exits still apply
HUP/reap/history policy and leave no child, handler, terminal state, fd,
or lease behind."*

**Base:** d1e4f1ae (v0.768.0 + record addendum). Branch
`fix/remediation-4a-2`, worktree `/Users/pwilson/src/psh-r4a-2`.
**Base figures (you RE-DERIVE in your first gate run):** attestation
e2e5d3b4 (gated ec995a76): 22,466 + 1,017 = 23,483 passed / 1,618
skipped / 10 xfail; ruff clean; mypy 275; compare-bash 3,042/26 EXACT.

## The defect (MEDIUM-1), integrator-probed at d1e4f1ae

`Shell.shutdown()` (shell.py:486-519) runs: EXIT trap → history (route-
gated) → `_dispose_jobs_at_exit` → `finally: close()`. The trap fires
FIRST inside the `try`, and `execute_exit_trap`
(trap_manager.py:537-567) swallows only `SubstitutionSyntaxAbort` — a
`SystemExit` from the trap's own `exit N` (the exit builtin re-entering
shutdown, which no-ops on the `_shutdown_reason` latch, then raising)
propagates OUT of the try. **Measured (instrumented Shell, subprocess):**
`trap 'exit 7' EXIT; exit 3` → SystemExit(7), `_shutdown_reason` set,
and the recorded step list is **NONE** — job disposition, detached
reaping, AND history save all bypassed; only `close()` ran (finally).
The latch makes the skips PERMANENT, not deferred. The docstring
documents only the history-save skip as intended ("as before"); the
job-disposition/reap bypass is undocumented — the LEDGER row's
"CONFIRMED structurally" fact, now measured live.

**Exit-status precedence ALREADY MATCHES bash** at the `-c` level
(probe battery, both shells, base): `trap 'exit 7' EXIT; exit 3` → 7/7;
`trap ':' EXIT; exit 3` → 3/3; `trap 'exit 7' EXIT` (normal
completion) → 7/7; echo-then-exit → T + 7/7. The precedence half of the
charter is SPECIFY-AND-PIN (document the rule, pin the cells, add the
`$?`-inside-trap and nested/no-exit cells), NOT behavior change. Any
precedence cell that DIVERGES in your wider Phase A battery is a finding
to report, not silently fix ahead of the ruled design.

## Phase A must settle (probe, don't argue; bash 5.2.26 oracle)

1. **The phase-split design**: mandatory phases (trap → history-policy →
   job disposition → reap → close), what CAPTURES the trap's SystemExit
   (hold-then-re-raise after all phases, mirroring the 4A.1 EN-1 shape
   ONE LEVEL UP), where precedence is enforced, and idempotence-latch
   semantics under re-entry (the exit-builtin-inside-trap route is the
   NORMAL route, not an edge).
2. **History policy under trap-exit (ruling slot (b))**: the current
   skip is DOCUMENTED as historical. What does bash do — interactive
   shell, `trap 'exit 7' EXIT`, exit/EOF: is the histfile written?
   PTY-probe it (the interactive gate makes `-c` probes vacuous here).
   If bash saves, the documented skip flips = a DECLARED delta with the
   doc updated; if bash skips, pin the skip as bash-parity.
3. **huponexit × trap-exit (the charter's named PTY cell)**: interactive
   + `huponexit` + background job + `trap 'exit 7' EXIT` → bash HUPs
   the job? And the received-SIGHUP route composed with an EXIT trap
   that exits. PTY probes — A5's MEDIUM-3 lesson holds: interactive-only
   behavior gets PTY pins; a `-c` pin green-on-base violates sequence
   rule 3.
4. **Reap-under-trap-exit**: disowned child + trap-exit — is the child
   reaped? Observable via process-table probes in a subprocess harness.
5. **Signal-death path interaction (ruling slot (c))**:
   `_terminate_from_signal` (1.3b-pinned invariants: redirect restore →
   EXIT trap → flush → restore-default + re-raise) — does the phase
   model apply there, and does its EXIT-trap fire honor the same
   no-bypass guarantees? Changing 1.3b invariants = STOP-AND-PROPOSE.
6. **Exit-status precedence spec**: the full cell family — `$?` at trap
   entry, `exit` with no operand inside the trap (bash: preserves the
   pre-trap status), nested traps, trap during `-c` vs script vs
   interactive, `set -e` interaction. Specify as a table, pin the
   agreeing cells, report divergent ones.

## Pins YOU create

Red-on-base: the bypass family — trap-exit runs job disposition (PTY,
huponexit cell), reap (subprocess process-table cell), history (per
ruling (b)), with the step-recording instrumented cells as unit-level
complements. Must-hold: the four measured precedence cells + the
substitution-abort swallow (2.4's teardown policy) + `close()` always
runs + the 4A.1 suites stay green (their close()-ordering pins are YOUR
fence posts). M8 locks for the phase-ordering arms (each phase's skip =
its own kill reason). Composition cells (lesson 3): trap-exit ×
LeaseRestoreError-from-close (both terminal signals held — which wins,
specify); trap-exit × signal-hup route; trap-exit × history-policy ×
interactive.

## Must-NOT-flip

- The four precedence cells measured above (7/3/7/7 both shells).
- 2.4's teardown swallow (`SubstitutionSyntaxAbort` reported-and-
  swallowed at execute_exit_trap; O3 mid-script abort untouched).
- 4A.1's ENTIRE close() contract: EN-1 hold-aggregate/finish-teardown/
  then-raise, the unconditional managed drain, quarantine semantics,
  the lease suites — ALL settled and pinned. **4A.2 orders phases ABOVE
  close(); it never reaches inside it.**
- 1.3b signal-death invariants (redirect restore before trap; frame
  drain semantics) unless ruled in via slot (c).
- `_HISTORY_SAVING_SHUTDOWNS` route set for NON-trap exits.
- Exit-trap at-most-once; `hangup_all_jobs` unconditional fan-out on
  received SIGHUP; non-interactive SIGHUP just dies.

## FENCES (stop-and-report BEFORE touching)

- `psh/core/process_lease.py`, `Shell.close()` internals,
  `signal_manager.restore_managed_dispositions` — 4A.1's settled
  surface. Reading yes; editing = stop-and-propose.
- 4B.3 (history state machine): this slot decides WHEN save runs, never
  HOW history works.
- D-4A.1-s rows (esp. s1 SignalRegistry retention, s6-reframed
  quarantine policy) and all D-3.x successors: MUST-NOT-ABSORB.
- Fork-side child teardowns (the two forked-child exit-trap sites named
  in trap_manager's docstring): report-only unless ruled.

## Slot-specific test hygiene

- **The exit-trap flake family lives IN this slot's code**
  (`TestExitTrapOnFatalSignal`; recurrences #1/#2 in
  `nightly-status.md`, prior transcript `tmp/flake-watch-3-5/
  gate-attest.txt`). If any gate run flakes there, that is INSTANCE 3 —
  the third-instance-investigates rule fires and YOU own the
  investigation, armed with this slot's phase understanding. Report
  with transcript; no silent re-run. Conversely: if your Phase A
  explains the flake mechanism, that is a REPORT row (and a gift).
- PTY tests: follow `tests/integration/` PTY precedents; serial by
  path/marker per conftest; every scratch dir CREATED BY THE TEST
  (D-4A.1 lesson 3 / VF-1); fresh-checkout portability is now a
  standing verification leg — assume your suite WILL be run at a
  checkout with no `tmp/`.
- In-process shutdown tests: a Shell whose shutdown you drive must not
  kill the test runner (SystemExit captured), must leave the
  coordinator proven clean (4A.1's fixtures are your precedent), and
  job-control cells go subprocess/serial per the parallel-safety rules.

## Pre-declared ruling slots

- **(a)** Phase A disposition table + phase-split design (GO gate for
  Phase B).
- **(b)** History-under-trap-exit policy (bash-probe-decided; declared
  delta if it flips the documented skip).
- **(c)** Signal-death-path applicability (1.3b interaction).

## Rules

The FULL binding rule set is `docs/reviews/evidence/
boundary_remediation_2026-07/4a.1-rescue/brief.md` §Rules (in THIS
worktree at that path) — binding verbatim: never-touch list, dead-drop +
ACK, mechanical tip rule, ledger freeze, per-hunk staging, SHA
paste-from-instrument, pre-registration + GO-binding citation, RN-Cdoc,
CERT-ROW-BEFORE-CLAIM, NAME-VS-BODY (the shutdown-census tooling test in
tests/unit/tooling/ and the 2.4 teardown pins are YOUR named siblings —
read them first), instrument discipline, the 13 D-3.4 lessons + D-3.5
instrument-mirror + 3.x sets, axis quantification (add: EXIT ROUTE ×
TRAP DISPOSITION — reason exit-builtin/-c-end/script-end/repl-eof/
signal-hup/signal-fatal × no-trap/trap-no-exit/trap-exit-N/trap-abort),
discharge audit + bounced-rows replay, gate rules (ONE heavy run
machine-wide, unpiped pgrep, foreground, NEVER shell-`&` — 4A.1 dev
fault #3 is your cautionary tale; NEVER `run_tests.py --compare-bash`),
oracle rules (PATH bash 5.2.26, never /bin/bash, explicit argv), project
tmp/ only, peer-escalation/permission-laundering wrapper. PLUS the
D-4A.1 additions now binding: red-on-base counts re-derived at the
declared tip, never carried; "all X except Y" claims stated as measured
splits; scratch dirs created by tests; verifier/probe cleanup never
glob-deletes outside its own mktemp scratch.

Done = Phase A table + three rulings + phase-split landed with the
bypass family flipped red→green + precedence specified-and-pinned + PTY
battery (huponexit + history cells) + M8 + composition cells +
must-not-flip green + doc sweep (shell.py docstring, core/CLAUDE.md
shutdown prose — pointers verified) + green gate + compare-bash EXACT +
ruff + mypy + discharge audit + complete ledger → completion report
with declared final tip + frozen ledger.
