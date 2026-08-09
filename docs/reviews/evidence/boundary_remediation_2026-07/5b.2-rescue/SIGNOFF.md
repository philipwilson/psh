# Slot 5B.2 — sign-off record (post-merge addendum, 2026-08-09)

## Sign-off: NINE legs, 9/9 PASS (dev-5b-2, D8, at tag v0.776.0 = `4c333a78`)

Legs pre-registered in D6 BEFORE any tag existed (standing shape), amended in
D7 (leg 2 → prefix-extension form, mechanic dry-run before registration), run
from a throwaway detached worktree at the tag with the import discriminator
asserted first, removed after.

| Leg | Result |
|---|---|
| 1 discriminator | PASS — psh under test proven to be the tag's tree |
| 2 artifact byte-exactness + prefix proof | PASS — MANIFEST 45/45 recomputed, 0 mismatches; `ledger.md` = freeze-2 `327a9bf270ce082878ef79ea823b0efc`; `brief.md` = `e65a0a90089803361ca78e49797b55ad` (the R0 dispatch value — charter unaltered end-to-end); committed inbox snapshot `d7770fadb516e34f0384f32d0ff4f1e7` verified at its DECLARED point (through R4) AND the live file's first 54,066 bytes hash exactly to it, suffix = precisely D6/D7/R5 — nothing rewritten behind the snapshot |
| 3 source-vs-evidence equivalence | PASS — 20 instruments + 22 transcripts byte-identical to what was actually run |
| 4 per-commit scope + never-touch attribution | PASS — 21 files across the dev's five commits, ZERO never-touch files in each; never-touch changes confined to the integrator's `d79c37b5` (LEDGER) and `d8166242` (bump) |
| 5 pin liveness at fresh checkout, `tmp/` ABSENT | PASS — instruments 14 (4/4) and 21 (3/3) replayed from the COMMITTED copies, both restoring byte-identically |
| 6 must-hold recomputed, not adopted | PASS — caps 66 entries / cap 177 == actual 177 / slack 0; ALLOWLIST 9 over 24 scanned modules; `__all__` = exactly four protocols; grep-zero 0 in psh/ + exactly one test file; compare-bash 3,046/26 EXACT |
| 7 falsification (pins lose their mechanism → red) | PASS — headline arm: a seeded `VariableAccess` reference makes the grep-zero pin FAIL, and neutering only the pin's scan body with the same seed present makes it PASS — the pin is load-bearing, not decorative |
| 8 attestation figures independently summed | PASS — 23,941 / 1,620 / 10, 0 failed, 0 errored, agreeing with BOTH pre-registrations (dev D5, integrator R4), reached separately |
| 9 zero flakes | PASS — every leg once; no re-runs |

**Disclosures under the zero-flakes clause (dev, self-reported in D8):**
1. A near-false-finding caught INSIDE leg 8 before reporting: an initial parse
   filtered for top-level `passed`/`skipped` keys where the attestation schema
   nests them under `counts`, summing zeroes and printing a disagreement. The
   schema was checked before reporting; the corrected sum agrees exactly. Never
   left the dev's turn → recorded here as a disclosure, not a fault-register
   row (the register records what reached an artifact or a report).
2. `tmp/` existed at sign-off teardown: verified ABSENT for leg 5 (the leg that
   needs it); created afterwards by leg 6's pytest runs. Stated so no future
   reader reconstructs the sequence wrongly.

## Tag chronology

1. Attestation gate at detached `psh-gate-5b2` @ `d8166242` (tmp/ created
   first, version verified): **23,941 / 1,620 / 10 EXACT** per both
   independent pre-registrations; ruff + mypy in-gate; attestation written
   (gated_commit `d8166242`, version 0.776.0).
2. Attestation committed FINAL `f6bd54f5` → PR **#536** → merged, origin/main
   `4c333a78`.
3. **Tag v0.776.0 minted FIRST-TRY on the push event**: annotated tag object
   `7f33d4c2` → `4c333a78`, 2026-08-08 23:24:34Z, release-tag run 31283897810
   SUCCESS with in-workflow attestation verification. The 5B.1 ancestry lesson
   was applied as a CHECK (origin/main verified unmoved before the gate), so
   gated tree == merged tree and no re-attestation was needed.

## Fault register, final (gap-free; see frozen ledger §B18 + §B20.1)

- **Dev: 12** — D-0 (instrument-01 alias blindness), D-1 (reach-vs-usage
  census gap), D-2 (subsumed detector grammar), D-3a/b/c (the caps
  static-predicate chain), D-3 (add-import-vs-move-import verification), D-4
  (cold-bytecode timing artifact), D-5 (unobserved mypy-clean), D-6 (stranded
  cycle-break comments — the only fault to reach the working tree; reverted
  before any commit), D-7 (watcher self-match deadlock, integrator-diagnosed),
  D-8 (unanchored instrument seeding, caught by its own reason-asserting arm).
- **Integrator: 2** — I-1 (subscript-ALLOWLIST shrink pre-registration,
  reasoned-to not measured; withdrawn in R1), I-2 (stale-inbox crossing nudge,
  composed against the post-R2 md5 while D3 was in flight).
- **Zero false findings in either direction** across the 4-agent adversarial
  round, the integrator-direct re-verify, and the nine-leg sign-off (the
  verify round's one BLOCKER and one REQUIRED-NIT were both reproduced against
  the tree by the integrator before ruling; the dev verified each against the
  tree before fixing).

## Final dead-drop

`INTEGRATOR-INBOX-final.md` (alongside this file) is the complete R0–R6 /
D1–D8 record; final md5 `2415e9d167a13a084f53e41264435ad7` (declared in R6).
The `INTEGRATOR-INBOX.md` committed in the rescue tree at the release merge is
its exact 54,066-byte prefix (through R4), proven by leg 2.
