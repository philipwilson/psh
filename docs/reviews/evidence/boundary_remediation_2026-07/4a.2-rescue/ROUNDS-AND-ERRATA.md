# Slot 4A.2 — rounds, faults, and errata (integrator-authored ceremony record)

Slot: shutdown phases (MEDIUM-1). Base `d1e4f1ae` (v0.768.0 + addendum) →
final tip `80042767` (eight commits, per-hunk). Shipped as **v0.769.0**.
Dev: dev-4a-2; integrator: main session. Dead-drop R0–R6 (complete copy
in this directory's `integrator-inbox.md`).

## What shipped

- **Shutdown is now mandatory phases** (`psh/shell.py`): the EXIT-trap
  phase's terminal exception (SystemExit is the NORMAL route — the exit
  builtin re-enters shutdown) is HELD; history-policy, job disposition
  and detached reaping all still run; `close()` runs unconditionally in
  the finally; the held exception re-raises with specified precedence
  (close()-raised error > trap SystemExit > phase failure; non-winners
  as `__context__`). Phase ORDER unchanged — it already matched bash's
  own `exit_shell` (trap → history → hangup → exit). At base, a
  trap-exit permanently skipped history, HUP fan-out, and reaping
  (measured: recorded steps NONE vs both on the no-trap control).
- **Declared toward-bash delta 1 (ruling (b))**: history now SAVES under
  a trap-exit on the saving routes — PTY-probed: bash writes the
  histfile under `trap 'exit 7' EXIT` on both exit routes; psh's
  documented "skips the save, as before" had recorded a bash divergence
  as if it were policy. The ROUTE still owns the policy (`main-exit`
  still never saves — pinned must-hold).
- **Declared toward-bash delta 2 (the R4 fix)**: a bare `exit` in an
  EXIT trap now resolves to the TRAP-ENTRY status, matching bash
  (`trap 'cleanup; exit' EXIT; exit 3` now exits 3, not cleanup's
  status). **Wording constraint honored: this is a CLOSED PRE-EXISTING
  divergence found by the adversarial HARNESS in round 1 — the dev's
  own 66-cell battery had certified the cell as parity through two
  non-discriminating rows.** The mechanism narrowing that shaped the
  fix (EXIT-only; non-EXIT traps measurably use current `$?` in BOTH
  shells, so a general saved-status rule would have created a NEW
  divergence) was the dev's. Seam: `TrapManager.exit_trap_entry_status`
  + the bare-exit consult in `builtins/core.py` (scope extended by
  ruling R4 to exactly that seam). 39/39 discriminating battery at tip;
  the two vacuous cells are COMMITTED as labelled `control` rows with a
  docstring explaining how they mislead.
- **Precedence specified in the tree**: a 39-row conformance table
  (`test_exit_trap_status_precedence_conformance.py`) + the EXIT-only
  must-hold — the spec survives the merge instead of living in a tmp
  transcript.
- **Batteries**: unit phase battery 18, PTY battery 4 (huponexit +
  history + anti-vacuity control), ruling-(c) composition cell,
  precedence 40 → **63 committed tests**; M8 10 arms / distinct kill
  sets; 13 files +907/−39.

## Round table

| round | verdict | substance |
|---|---|---|
| Phase A (R1) | accepted first submission | EXECUTED not planned: 66-cell precedence (later shown blind to one rule — see R3), 4-observable bypass red-on-base, ruling probes; **A-8: the exit-trap flake MECHANISM identified** (1.3b redirect-restore residual window — the trap's output found inside the harness's own sentinel file; two published negatives rule out naive timing fixes) |
| Phase B (R2) | double GO | 4 per-hunk commits; gates green EXACT (23,502 / 3,042) |
| Harness round (R3) | **BOUNCE** | **1 blocker / 1 real / 0 false**: frozen A-1 certified "no divergent cell" via two vacuous bare-exit rows; the discriminating composition diverges (psh bare exit in EXIT trap used current `$?`; bash preserves pre-trap status). Pre-existing, unpinned, unreported. Plus a required nit set (committed spec pins, half-asserted SIGHUP cell, PTY anti-vacuity, BaseException branch, stale census comment) |
| Fix round (R4–R5) | proposal ruled first | figure-true/inference-false A-1 correction; 39-cell re-derivation (21 divergent); USR1 narrowing; ten-line fix approved with explicit scope extension; gates green EXACT (23,546 / 3,042) |
| Integrator-direct (R6) | **PASS** | blocker replayed closed (my own four cells); fresh-checkout 58/58 at a no-tmp detached checkout; every required nit verified in tree |

## Final register (wording constraints honored)

**One bounce, one real blocker, the dev's** — the "zero blockers"
phrasing applies ONLY to the behavioral core of the original
phase-split delta, which took no findings across both rounds. 5 dev
self-corrections recorded in place (the `git status` wording; the M8-g
kill-set duplicate dropped-and-replaced; the M8-h both-halves
unspellability; the parametrized-id counting artifact; the truncated
red-on-base transcript re-captured). 0 false findings in any direction.
2 process notes, both handled: the freeze-md5-omitted declaration
(rule adopted: md5 IN the declaration) and nothing else.

**MEDIUM-1 exit-criterion widths, stated exactly:** the HUP and history
legs are PTY-proven (pexpect AND tmux agreeing); **the reap leg is
UNIT-proven, not PTY-proven** — a shutdown-path detached reap is
structurally unobservable end-to-end (nothing runs after it; an
unreaped child reparents to init, so both worlds end zombie-free), and
the opportunistic-reap call site would be a DIFFERENT observation. The
lease leg: ownership release under trap-exit is DIRECTLY measured; what
close() restores downstream is 4A.1's pinned surface (composition, at
that narrower width only).

## Lessons bank (D-4A.2-lessons)

1. A battery cannot license "no divergence exists" over a rule it is
   structurally blind to — the FIGURE can be true while the INFERENCE
   is false; vacuous cells certified a real divergence in the slot's
   own charter family (lesson-8 shape, recommitted as labelled
   control rows so the trap is visible to the next reader).
2. State claim BOUNDARIES before the verdict, not after findings (the
   reap-observability discriminator, the lease-width upgrade, the
   identical-object boundary — all pre-registered while the harness
   ran); and pre-register where the record could FLATTER you (the
   dev's three ceremony wording constraints, all honored above).
3. A mutation that cannot be spelled as one half (each half defended by
   the other) is recorded as a both-halves arm WITH the reason — not
   as an unpinned arm, not silently.
4. Kill-counts are artifacts before they are numbers (the
   parametrized-id regex collapse); fix the instrument, report neither
   wrong-looking number.
5. An instrument-caught truncation (`tail` on a red-on-base transcript)
   is re-captured in full — a split asserted is not a split shown.
6. The flake-mechanism investigation pattern: reproduce at recorded
   density, find the deciding observable (WHERE the lost output went),
   publish the negatives that rule out cheap fixes, fence what you
   cannot touch (A-8 → successor row D-4A.2-s1).

## Successor rows

- **D-4A.2-s1**: exit-trap flake mechanism (A-8) — 1.3b
  redirect-restore residual window; the sentinel-inside-redirect
  construction amplifies it; 2/750 reproduction density; negatives
  published (busy-poll, randomized delay); owner: a 1.3b-adjacent slot
  or Checkpoint R.
- **D-4A.2-s2**: `_run_shutdown_phases` holds ANY BaseException; the
  KeyboardInterrupt branch is pinned, but the policy question (should a
  KeyboardInterrupt during shutdown really complete all phases?) is
  recorded as deliberate-and-open.

## Regeneration notes

Dev instruments + transcripts under `instruments/dev/` (pre/post pairs
for all four observable batteries, `bare-exit.txt`/`nonexit-trap.txt`,
the three red-on-base splits at their respective pre-fix tips,
`m8-mutations.txt`, `flake.txt` with the A-8 density runs); the
integrator dispatch probe at `instruments/probe_medium1_bypass.py`.
Harness round: `remediation-branch-verify.js`, run `wf_f0521f37-f89`.
Gate transcripts remain in the dev worktree's tmp/ per convention
(figures durable in ledger, inbox, attestation, PR body).
