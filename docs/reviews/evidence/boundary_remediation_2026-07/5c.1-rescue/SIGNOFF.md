# Slot 5C.1 — Sign-off record (D12, accepted R12, 2026-08-09)

Eight legs, pre-registered in D11 BEFORE the tag (4B.4 standing
shape), executed by dev-5c-1 at a throwaway detached worktree at tag
`v0.777.0` (annotated `58a4c4c7` → merge `6591dcb4`), import
discriminator asserted, both pgreps unpiped-empty before L5/L6,
worktree torn down after. **Result: 8/8 PASS.**

| Leg | Expectation (falsifiable) | Result |
|---|---|---|
| L1 | tag resolves; its tree reads `__version__ = "0.777.0"` | PASS (`6591dcb4`) |
| L2 | `3fe48475` is an ancestor of the tag; all 11 slot commits reachable | PASS 11/11 |
| L3 | the seven slot figures reproduce: Q2 BROAD_MASKING 1 / NARROW_SAFE 13; terminal handlers 24/0; MIGRATED_MODULES 20; `__all__` 5; consumer-ratchet ALLOWLIST 8; caps 66/177/177/0; `self.shell` reach 0 | PASS all |
| L4 | census at the tag: Method A 633 / Method B 478; 3,251 defs; 80 seams | PASS |
| L5 | the four slot-touched suites collect 41 and pass 41 | PASS 41/41 |
| L6 | compare-bash 3,046 / 26 EXACT | PASS |
| L7 | ARCHITECTURE.md names `ExpansionHost` at :98 and in invariant 9; consumer count reads 8 | PASS — **with one finding against the integrator's ceremony text (below)** |
| L8 | none of the dev's eleven commits touched a never-touch file; every never-touch edit in the release is the integrator's | PASS |

Attestation independently summed by the dev: 23,985 / 1,620 / 10 at
gated `67261b29` — matches gate-2 at `3fe48475` exactly; L5/L6
REPRODUCE the two most slot-specific components at the tagged tree
rather than reading them across (noted in R12 as the model for
future sign-offs).

## The L7 finding (dev, against the integrator's work — accepted R12)

D11 declared L7 as "a leg against your work, not mine … a sign-off
that only checks the signer's own work isn't a sign-off." It did
what it was built for: invariant 9's new sentence read "the
full-`Shell` consumer set — 8 **modules** as of v0.777.0", but the
ratchet's unit is the `(module, symbol)` CONSUMER — 8 entries across
4 distinct modules (child_policy ×3, command_resolution ×1,
analysis_session ×3, program_source ×1; integrator re-derived by AST
at the tag). A unit error inside the sentence written to fix
staleness — the same class as the drift this slot polices. Fixed in
this addendum: "8 full-`Shell` consumers across 4 modules".

## Tag chronology

Attestation attempt 1 at bump `33c50a85`: **RED** —
`test_readme_loc_and_file_counts` (23,984/1/1,620/10; the count
pre-registration of 23,985 was RIGHT — one content failure).
INTEGRATOR FAULT: the guard-pinned README LOC line was reformatted
("(816 test files)" where the regex pins "(N Python files)", whose
denominator is all tests/*.py = 835) — a NAME-VS-BODY miss on the
integrator's own edit; the guard names its canonical tool. Fixed
FROM `tools/gen_test_stats.py`; bump AMENDED → `67261b29` (nothing
yet pushed; one bump commit on the branch). Attempt 2 GREEN:
23,985/1,620/10 EXACT; attestation FINAL `058b8441`. origin/main
verified unmoved (`d0956bed`) pre-push; PR #538 → `6591dcb4`; tag
minted FIRST-TRY (run 31317343627), in-workflow attestation
verification green — third consecutive first-try tag under the
ancestry discipline.

## Final fault register (both roles, gap-free; ZERO false findings any direction)

**Dev (8 pre-gate self-caught, zero gate exposure):** 7 instrument
defects (normalizer under-strip; param-only usage census blind to
stored fields + one phantom member from a first-pass grep; seam
census 643-vs-648 recursion blind spot; the near-false-fence — an
except-CLAUSE-line probe answering a branch-level question, caught
by two-method verification pre-report; truncated-dump ledger keys;
two more recorded in ledger §B) + 1 production-side false invariant
(commit vii's non-runtime_checkable ExpansionHost, self-caught,
fixed by commit ix pre-gate) + half of firing #5 (the frozen-ledger
"19 transcripts" prose).

**Integrator (4):** two chain-line defects in the dead-drop (R5.1
placeholder; R6.1 PREDICTED md5 — a paste-from-instrument
violation), the co-owned manifest two-figure note (ruling: the
command-generated manifest is authoritative), and the attempt-1
README reformat (GATE-caught, zero merge exposure).

**Verify round (record layer, charged jointly):** 3 blockers — two
dangling `self.shell` docstrings contradicting the slot's own
headline pin; one TRUE-BUT-UNPINNED claim (ast_debug byte-identity,
verified by the round itself, fixed by committing the pin) — plus 10
required nits, all fixed in 2 commits and re-verified.

**The READ-IT-OFF family: SIX firings across both roles** (dev:
NARROW_SAFE 14, truncated-dump keys, +22/+29 gate drafts;
integrator: two chain-line defects, the README reformat; shared:
the manifest prose figure) — caught by three distinct review
mechanisms and one committed guard, never by the mistake not being
made. The countermeasure, banked in D-5C.1-lessons: COMPUTE THEN
AUTHOR — paste from executed instrument output, two commands, never
one.

Final dead-drop: `INTEGRATOR-INBOX-final.md`, md5
`aaf9c403e82d8bb70854a92d6c6f4802` (112,851 bytes; the committed
release-tree snapshot `INTEGRATOR-INBOX.md`, 98,486 bytes /
`d383b78a…`, is an exact prefix — VERIFIED MECHANICALLY at addendum
time: `head -c 98486` of the final file hashes to the snapshot's
md5, and the suffix contains precisely four entries, D11 / R11 /
D12 / R12).
