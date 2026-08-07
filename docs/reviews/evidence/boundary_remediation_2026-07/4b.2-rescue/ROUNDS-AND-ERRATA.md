# Slot 4B.2 (input decoding, MEDIUM-2 + A5 rider) — rounds, register, errata

Companion to `slot-ledger.md` (re-frozen md5
`7bb798ba3e96f4ec1ffd20a38ea60794`, 638 lines) and `integrator-inbox.md`
(through R9). Base 21a23a4c (v0.770.0 + 4B.1 addendum); final tip
`bcd5fd36` (9 commits: 5 declared Phase B + 1 declared ratchet fixup +
3 declared fix-round). Shipped as v0.771.0.

## Round narrative

- **R0/D1** — dispatch; two provisional recon findings flagged before
  instrumenting (P1 `_pushback` producerless; P2 byte/char cursors never
  shared), both later CONFIRMED dynamically. R1 confirmed the P1
  treatment (vacuity is a fact about today's producers; the pin is a
  contract for tomorrow's).
- **D2/R2** — Phase A EXECUTED: 36-cell split matrix (6 red, all in the
  one drain route; 0/36 round-trip failures — the exit criterion's
  second half was a control, not a flip); 32-cell bash rider A/B matrix
  (8 DIFFER); census: exactly TWO routes strand pending decoder bytes
  (TIMEOUT, ERROR). THREE new facts: **NEW-1** (bash ASSIGNS a stranded
  partial at `-t` timeout; psh holds it — rc identical, value-only;
  integrator-reproduced; DEFERRED to 4B.4 as D-4B.2-s1 with I1-style
  divergence pins), **NEW-2** (bash counts POST-escape chars for `-N`,
  psh raw — later measured to reach the EXIT STATUS; D-4B.2-s2),
  **NEW-3** (printf renders >0x7F escapes as characters; report row).
  Plus the dev's CERT-ROW challenge to the INTEGRATOR'S brief claim
  (C.3: "-N hangs" sharpened to "blocks until EOF; unbounded only
  without EOF") — accepted as a brief erratum, and the integrator's own
  verification instrument earned an honesty note (its timing column
  measured the harness's own sleep). Dev disclosed instrument defect
  i5 (shell-under-test generated the stimulus) — retracted output kept
  WITH its retraction note in `instruments/dev/`.
- **D3/R3** — the dev's sweep found TWO LEDGER CARRIES naming this slot
  that the integrator's brief failed to transclude (#21 ATTACHED with a
  re-rule obligation; #33 optional) — INTEGRATOR BRIEF ERRATUM; the
  carry sweep is now a standing dispatch-checklist item. Carry #21
  re-ruled RE-CARRY on a fresh 24-cell split (1 both / 9 UTF-8 / 6 C /
  8 neither — the hybrid is psh's own documented model; closing would
  adopt one libc's quirks) with a characterization pin added where the
  carry had none and a no-silent-change proof (base-vs-tip diff EMPTY).
  Carry #33 declined with reason. Pre-registration: 89 nodes / 19 red,
  golden promotion 2 cases.
- **D4/R4** — Phase B landed. DEV-1 (the NEW-2 cell mis-classified in
  BOTH halves of the dev's own pre-registration — the truth was
  STRONGER: the divergence reaches rc); DEV-2 (two cells re-shaped to
  by-construction determinism). Banked: stimulus-validity controls;
  `PYTHONDONTWRITEBYTECODE=1` REQUIRED for mutation-lock drivers
  (stale same-size .pyc silently disarms an arm).
- **D5-interim/R5** — gate STOP-AND-REPORT: the only failure was the
  pin file's own arm tag `"bash"` tripping the anti-oracle ratchet —
  which is RIGHT to be unable to tell a tag from a hardcoded path;
  renamed, never allowlisted. **F-1** (fix landed without prior
  declaration — replay DECLINED on principle: a reconstructed
  compliant-looking record is worse than the honest violation);
  **F-2** (single-node run while the serial phase was live).
- **D6/R6** — gate at 41447315 EXACT on every axis. **DEV-3**: the
  compare-bash delta was registered +2 where +4 was correct — ruled
  JOINTLY OWNED: the integrator's R3 confirmation had MORE evidence in
  hand than the dev's registration (the two-node mechanism was
  integrator-verified, including the skip condition). Corrected figure
  3,046/26, proven by the deselection control returning base exactly.
  **F-3** (shell-`&` launch — the recorded 4A.1 cautionary tale
  recurring under re-run urgency; killed, output discarded, machine
  verified, relaunched foreground).
- **R7 (harness round: 4 verifiers) — BOUNCE, 3 distinct blockers +
  8 required nits, ALL real, 0 false.** BL-1 (three verifiers
  independently + integrator reproduction): the M8 driver mkdtemp'd
  into the repo's untracked `tmp/` — all six arms ERROR on any fresh
  checkout while the anchor half stays green, MASKED by the canonical
  gate creating `tmp/` first. BL-2: the s1 divergence cited a
  user-guide line that documents the char MODEL, not the divergence
  (documented nowhere — the absence itself now travels with s1).
  BL-3: the TTY leg's binding probe-or-declare commitment discharged
  by NEITHER, while the fix changed the tty arm. The round also
  produced two NOVEL confirming rows (exec-fd rider composition;
  4-byte split at position 1 through `mapfile -t`) and two verifier
  self-disclosures (a compare-bash overlap; an editable-install
  near-miss caught by discriminator).
- **D8/D9/R8** — fix round (3 declared commits): BL-1 fixed AND
  certified in the mandated environment; BL-2's citations reworded (a
  FOURTH site found by the dev); BL-3 discharged with 3 PTY pins —
  after **F-4**, the probe that failed in the WORST direction:
  `pexpect` inherited cwd, `python -m` puts child CWD ahead of
  PYTHONPATH, so the "base" probe imported the FIXED tree and reported
  the base as already bash-matching. Self-caught BEFORE any dispatch
  carried the conclusion; hardened with resolve-and-assert
  (`assert_tree_under_test`); the re-measure showed the base tty arm
  genuinely HUNG — the blocker's premise STRENGTHENED by the fault's
  correction. Integrator-direct re-verify PASS at a fresh detached
  checkout (M8 7/7 with no tmp/; 108 nodes; PTY 3/3).
- **D10 + erratum/R9** — sign-off protocol defined (six legs,
  discriminator-first, with a falsification leg reverting the
  production hunks to prove the defect legs can still fail). **F-5:
  two md5 values in the handoff declaration were FABRICATED** —
  typed as plausible hex instead of computed. Self-caught and
  corrected (computed, command-generated) BEFORE anything was copied.
  Named in the record for what it is: the only fault of the slot that
  attacked the trust model rather than the measurement — and the
  reason it is a fault row rather than a slot-integrity incident is
  that the disclosure discipline held at exactly that point. All four
  corrected values were independently recomputed by the integrator
  before any copy, and every copy into this tree was verified against
  them.

## Final register

- 2 verification rounds: harness BOUNCE (3 blockers + 8 required
  nits, all real, 0 false) → integrator-direct PASS.
- Dev self-report register: **3 deviations (DEV-1/2/3) + 5 faults
  (F-1..F-5) + 5 disclosed instrument defects** — every one disclosed
  before a verdict could catch it. DEV-3 is JOINTLY owned
  (integrator's confirmation-without-reconciliation), C.3 and the
  untranscluded carries are INTEGRATOR brief errata.
- 92 committed pin/lock/characterization nodes (22 red-at-base defect
  cells incl. 3 PTY; labelled controls and psh-CONTRACT divergence
  pins for the declared residue) + 2 promoted golden cases
  (compare-bash 3,042 → 3,046/26, count increase, zero flips, proven
  by deselection control).
- Perf: **no measurable cost expected; not measured** (the fix
  replaces two decoder passes with one on the same bytes).

## Banked lessons (this slot's additions)

1. An A/B probe must not let either side under test generate the
   stimulus (i5).
2. A harness that sleeps before collecting measures its own sleep —
   timing columns state their collection design (integrator's C.3
   instrument).
3. Stimulus scripts get a validity control before their A/B verdicts
   count (`is_comparable` proves the harness ran, not that the script
   meant what you meant).
4. `PYTHONDONTWRITEBYTECODE=1` is REQUIRED for mutation-lock drivers;
   M8 drivers diagnose every precondition loudly — including their
   own scratch parent (BL-1).
5. A test-local tag string can trip a static ratchet that cannot
   distinguish it from the real thing: rename the string, never
   allowlist the file; state the constraint in-file.
6. The search path is a request; the resolved `__file__` is the fact
   — every A/B probe resolves and asserts the module path it measures
   (F-4).
7. A value that is cheap to compute is the one most likely to be
   typed from memory: any hash, count, or SHA in a handoff or
   certification is generated by the command that records it, and the
   RECEIVER recomputes on receipt (F-5).
8. Reconcile every sourced number against every figure it bears on,
   not just the one you fetched it for (DEV-3, jointly earned).

## What this slot deliberately did NOT claim

- bash parity for the timeout-partial ASSIGNMENT disposition (D-4B.2-s1,
  deferred to 4B.4 with the divergence pinned to flip loudly), the `-N`
  count model (D-4B.2-s2, rc-reaching), or `read -s -N` echo at a TTY
  (D-4B.2-s3, pre-existing).
- Any perf figure ("no measurable cost expected; not measured").
- Closure of carry #21 (RE-CARRIED: the hybrid is psh's documented
  model; both-sides characterization pins added).
