# Slot 5C.2 — sign-off record (v0.778.0, 2026-08-09)

Six dev-pre-registered legs (dead-drop D18), executed by dev-5c-2 at a
throwaway checkout of tag `v0.778.0` → merge `89df893c`, reported in D19
and accepted in R22. **6/6 PASS, zero blockers, nothing withheld.**

## Legs

| leg | claim | result |
|---|---|---|
| L1 | tag's psh/ + tests/ byte-identical to the dev-gated content | PASS — tag vs final branch tip differs in exactly `psh/version.py` and the LEDGER (the two integrator-owned ceremony files); zero drift in dev-authored files |
| L2 | import discriminator + version at a detached checkout (editable install imports MAIN — a version check that silently read MAIN would certify the wrong tree) | PASS — resolves under the tag checkout at 0.778.0 |
| L3 | both standing guards BITE at the tag, not merely pass | PASS — widened R4 RED naming `ast_data_flow.md` on re-seeded rot; resurrection ratchet RED naming `foreground_pgid` on a seeded reference; controls green; trees restored byte-identical |
| L4 | (against integrator ceremony) every LEDGER/CHANGELOG/README figure reproduces from the tagged tree or committed evidence, never from dead-drop prose | PASS — fn 3,236 · hubs 55 · ledger 51+1+3 · sig 632/477 · ≥100-exec 3 base / 2 tip · `__init__` 95 · README 276/818/25,673, all re-derived; **MEDIUM-15's closure carries the CANONICAL 57/3/95, not the superseded A9 58/2/94** (the dev's pre-declared hardest-watched cell — those figures appear in the dev's own early entries and were the likeliest wrong-source copy) |
| L5 | no production or test edit rode in on a ceremony commit | PASS — ceremony diffs are the two integrator-owned files + attestation |
| L6 | (against integrator ceremony) fault register matches the R18 allocation; a register that quietly reassigned the integrator's poller to the dev would be a BLOCKER ("a generous register is still an inaccurate one") | PASS — `D-5C.2-record` states the allocation verbatim |

Bonus checks, dev-initiated: `D-5C.2-s1` EXISTS (the widened guard's
exemption comment promises the row — a guard comment is a claim and was
verified); attestation `cb5f2ceb` in tag ancestry; tags gap-free.

**Pre-registered refusals, none quietly executed:** the Linux nightly
(integrator watch — this slot touched fd/job-control/signal-adjacent
code and the local gate is macOS-only); `release-tag.yml` firing (not
dev-controllable; the tag-points-at-merge fact was verified instead); a
conformance figure (no baseline was ever established — the sourceable
evidence is L5's zero-diff); benchmarks (Ceremony C / CR-R4).

## The 25,673 / 24,026 reconciliation (D19, record-worthy)

README's 25,673 (collection) and the gate's 24,026+1,620+10 = 25,656
(execution) differ by exactly the **17 benchmark tests** the gate
deselects (`-m "not benchmark"`), measured not assumed:
25,673 − 17 = 25,656. Two correct figures with different denominators,
reconciled so no future reader trips over an apparent discrepancy.

## Ceremony chronology (R20–R21)

Ceremony commits xxiii `fc4b4de7` (LEDGER) + xxiv `2e2526cf` (bump; the
README stats rewritten ONLY from `tools/gen_test_stats.py`, with
`test_readme_statistics` + `test_version_sync` green BEFORE the commit —
the direct countermeasure to 5C.1's attempt-1 red). Attestation gate at
detached `psh-gate-5c2`: **GREEN FIRST ATTEMPT, 24,026 / 1,620 / 10
EXACT per pre-registration**; attestation FINAL `cb5f2ceb`; PR #540 →
origin/main `89df893c`; tag `v0.778.0` minted FIRST-TRY (4th
consecutive), run 31334194322.

## Dead-drop integrity

The complete dead-drop is committed WHOLE as
`INTEGRATOR-INBOX-final.md`, final md5
`6a0188624ffd68af6803b523690c3624` (205,237 bytes; R0–R22 / D1–D19
incl. D2.1). No mid-slot inbox snapshot was ever committed, so no
prefix proof is owed; the integrity mechanism is the IN-FILE md5 chain
(every entry records the file md5 before its own append,
compute-then-author), verifiable end-to-end, plus the self-guarding
append mechanic ratified at R3 after fault #1 — which subsequently
caught three real crossings.

## Final fault register (allocation per R18; detail in `ledger.md` Part 4)

- **Dev:** D1 stale-ACK chain fault (#1, mechanically fixed by the
  self-guarding append); the E-series brief errata were dev FINDINGS
  not faults; missing-term pre-registration arithmetic (shared);
  moved-key enumeration missing the mutation-anchor category
  (self-caught, fence pulled); three self-caught instrument faults
  (A/B shared-fixture, grep-vs-collect-only, unannotated helpers with
  mypy green); the 200-vs-121 commit-message read-off; two gate-wait
  stalls (the second a REPEAT-OF-A-BANKED-LESSON); the benign
  over-claim of the integrator's poller.
- **Integrator:** truncated-grep brief erratum (E3, READ-IT-OFF #7);
  approving the contradictory act order (R4 vs R2, dev-caught);
  accepting the E4 doc census without per-file docs/ disposition
  (half of the verify-round blocker); constraining already-dispatched
  work (R16 timing); the orphaned 5C.1-era poller surviving the
  compaction boundary + its MISATTRIBUTION to the dev; three probe
  near-misses (wrong-tree collect-only, nonexistent seeding anchor,
  ALLOWLIST regex counting a comment) — each caught by its own
  assertion before contaminating a conclusion.
- **ZERO false findings in any direction** across the 4-agent workflow
  round, the fix round, the integrator-direct re-verify, and the
  sign-off.
