# Slot 5B.1 — sign-off and close record (post-merge addendum)

- **Dev sign-off (D10): PASS.** Committed rescue tree at `a8c5de8f`
  verified BYTE-EXACT against the dev's worktree originals by
  md5-of-bytes (`git show` vs disk): 42 files; 40/40 applicable
  identical; MANIFEST.md5 41/41 entries recompute, self-excluding
  confirmed; 0 missing / 0 extra / 0 mismatches. Anchors: `ledger.md`
  = freeze-2 `876a2d86ec2f6baa5a2a3afccc576f6b` exactly as declared at
  D9; `brief.md` = `c958a7a95737f35c5c1cdbc8649cb3ce` = the value R0
  quoted at dispatch (charter unaltered end-to-end). Final-tip
  ancestry (`dc843423` ∈ `a8c5de8f`) independently confirmed. The one
  difference (the in-flight inbox) was PROVEN an exact prefix
  (committed copy = the file through R5), not waved through.
  Instrument: `instruments/20_signoff_byte_verify.sh` + transcript.
- **Tag chronology:** the tagger REFUSED v0.775.0 at `a8c5de8f` —
  correctly: gated `1cddebb5` ≠ merged tree by
  `.github/workflows/release-tag.yml` (the PR #532 recovery-trigger
  commit landed on main mid-slot). Re-attested at the merged tree
  itself (identical 23,921/1,620/10; attestation-only PR #534, merge
  `47f921fb`); tag **v0.775.0 minted via workflow_dispatch** run
  31276767882 at `47f921fb`, verified in-workflow.
- **Fault register:** integrator 2 — (R7) mid-slot main advance not
  merged into the release branch before the attestation gate (the tag
  refusal); (R5/R6) wake-up nudge not sent after posting R-entries,
  compounding the session's THREE channel-drop instances (R3, R5, R6
  — the dead-drop file caught all three). Dev 1 — the §B5
  pre-registration phantom term (gate-caught, accounted forward from
  phase manifests, independently reproduced). Zero false findings in
  either direction.
- **Ceremony lessons (banked, standing):** (1) merge mid-slot main
  advances into the release branch BEFORE the attestation gate, or
  defer non-slot merges while a slot is between gate and merge;
  (2) every dead-drop R-entry gets an explicit channel wake-up — the
  nudge rule is both-directions standing.
- **Final inbox:** `INTEGRATOR-INBOX-final.md` (through R8, the
  closing entry; md5 `d43f2b24452725d51d7e5d4c2bd6b5c1`).
