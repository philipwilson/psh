# Slot 4B.4 — Rounds, Faults, and Errata (integrator record)

Slot: InputCursor contract close-or-narrow — sequence §9 Package 4B
item 3, D-4B.2-s1 discharge, P1 `_pushback` removal, W0-R2
supersession. Base `e3924ed3` (v0.772.0) → final tip `05d416e5`
(17 commits). Shipped at v0.773.0 — the release that CLOSES Wave 4.
Dead-drop: `integrator-inbox.md` (R0–R10 / D1–D9, ACK-the-highest-R
structural rule in the header from R0). Frozen slot ledger:
`slot-ledger.md` (freeze chain: 3449eefb → lifted at R6 → 65669a80,
chain rule observed; integrator snapshots held and diffed at each
move).

## Round chronology

| Round | Event |
|---|---|
| R0/D1 | Dispatch (both corruption faces probed at base: temp-frame contamination, dup byte loss). Dev's STOP-AND-PROPOSE: the un-cited Wave-0 ruling W0-R2 → **R1 SUPERSEDED it on premise-falsification** (well-formed-input routes postdating it); integrator erratum E1-4b4 (sweep missed Part C rulings — three-register sweep rule born) |
| D2/R2 | Phase A: THE COUPLING measured both directions — s1-toward-bash closes the faces but costs ≥22 must-not-flip 4B.2 nodes and MEDIUM-2's reachability (ruling-(c) STOP); CLOSE fixes everything at zero pin cost. **Ruled ROW 4**: CLOSE both surfaces, s1 permanent + documented. P1 remove-with-guard. Symmetric face (file surplus leaking OUT) found by dev, integrator-verified with a different composition |
| D3–D5, R3–R5 | Phase B (8 commits): lifecycle + scoping + hooks + P1 removal + pins. Gate-1 MISMATCH (2 static-ratchet failures — instrument conventions carried into a pin suite) → STOP-and-report, fixed by complying never allowlisting, leg-B pin came out STRONGER (concatenation property). Gate-2 + compare-bash EXACT |
| VERIFY 1 (R6) | Workflow harness: **BOUNCE, 7 blockers + 17 RNs** — headline: TWO NEW REGRESSIONS introduced by the branch's own fix (BL-1 `pop_frame` alias-blind cursor destruction; BL-2 named-fd mis-scoping reorder — the dev's own named weakness measured real), the nonexistent s1 table (BL-4, naming the INTEGRATOR's acceptance too — fault I-2), the un-re-affirmed s1 pins (BL-3), dropped chained-dup cell (BL-5), undeclared compound-dup census gap (BL-7) |
| D7–D9, R7–R10 | Fix round (5 + 2 commits): ONE lifecycle rule ("a description outlives any ONE of the fds naming it") fixing BL-1/BL-6 AND the pre-existing N9; apply-time scoping; compound aliasing; the REAL 18-cell s1 table incl. the tty arm (finding: bash ALSO holds at a terminal with plain `read -t`) with the user-guide text narrowed to it; s1 pins re-affirmed with the why in their failure messages. Gate-3 + compare-bash EXACT. Integrator-direct re-verify: **PASS** (6/6 bounce rows, M8 19/19 fresh-checkout, all faces == bash, NAME-VS-BODY clean) |

## Fault register (dev F-1..F-4; integrator I-2 + E1-4b4)

| # | Fault | Note |
|---|---|---|
| F-1 | a mypy delta REASONED instead of measured (impossible mechanism), self-caught pre-GO | |
| F-2 | one-axis repro instrument hid a regression inside a both-ends-diverge row (the move form) | born the TWO-AXIS rule: REGRESSION=base≠tip vs DIVERGENCE=tip≠bash — different questions, different owners |
| F-3 | an edit ASSUMED not asserted — the one `str.replace()` without `assert count==1` silently no-op'd and was reported as a discharge; plus the sharper miss: deferring to another agent's inability-to-verify over first-hand evidence | "a mutation that cannot fail is not a mutation" extends to edit scripts; make citations RESOLVABLE, never delete a measured claim |
| F-4 | three directory-argument runs without collect-only counts; retrospective counts labelled LATE MEASUREMENT, two residues (55, 17) chased to skips | "reading the pass line tells you what ran; it cannot tell you what didn't" |
| — | **ONE HABIT, dev-named**: a figure reasoned (F-1), an edit assumed (F-3), a rule applied where risk was EXPECTED rather than where it is WRITTEN (F-4), an axis chosen for the expected question (F-2) | adopted verbatim; the countermeasure is always the rule as written |
| I-2 | the integrator ACCEPTED "census, s1 table, matrix" at ruling (a) — with no s1 table in existence | acceptances are claims; ruling-(a) acceptances now enumerate artifacts BY LOCATION, each verified to exist |
| E1-4b4 | the dispatch brief failed to cite standing ruling W0-R2 | carry sweeps enumerate THREE registers: Part B carries, Part C rulings, Part D successors |

Instrument defects ID-1..ID-3 + two s1-table instrument defects: all
self-disclosed pre-reliance, VOIDed-and-rebuilt, in the slot ledger.
ID-3's lesson is structural: an emulation whose hook never fires
produces silence that reads as a negative result — every hook gets a
tripwire.

## The slot's headline lesson (dev-named, Part D)

Round 1 closed the REPORTED gap without asking what the new aliasing
invariant did to the code that DESTROYS cursors — re-opening the
slot's own defect class through a different door, invisible to a
96-node suite because every cell consumed its surplus before the pop.
**When you add an invariant, audit every site that releases the
resource it governs, not just the sites that acquire it.**

## Reading caveats

- Phase A evidence is INJECTION-EMULATION (plugin/sitecustomize);
  audit rows 8-9 supersede row 7 — the final claim set rests on the
  LANDED code (instr09/instr12 base-vs-tip pairs), re-derived by the
  integrator at R7/R10 and by the verify round.
- `I1-deliberate-loss-registry-excerpt.md` is the committed copy of
  the I1 campaign ledger's registry section, placed here so the
  suites' "row (d)" citations resolve in-tree (RN-4).
- The declared NOT-closed residue: I1 row (d) (builtin→external
  stranded lookahead) and the move-form (`3<&0-`) fd-lifetime
  divergence — both pinned both-sides, neither absorbed.

## Post-merge sign-off (D-4B.4-a1, 2026-08-08)

dev-4b-4 SEVEN-LEG SIGN-OFF **PASS at TAG v0.773.0** (919935d8, tag
SHA recomputed by the dev; protocol PRE-REGISTERED in D10 before the
tag existed, failure semantics stated up front). Legs: discriminator
(parent+child), per-cell defect legs 13 MATCH / 1 declared-residue
(the move form, pre-registered) + 12/12 original faces, must-hold
152/152, no-silent-change (zero undeclared paths; version.py's last
toucher = the integrator's ceremony commit), M8 19/19 with tmp/
ASSERTED absent, falsification (each production hunk reverted alone →
its cells fail), artifact verification (attestation reconciled
against the dev's own gate: 22,775 + 1,117 = 23,892; manifest exact
vs D9). Zero flakes stated. **Leg 7 found ITS OWN defect**: five
manifest entries named gitignored tmp/ paths a tag-only reader cannot
resolve — the RN-4 shape one level over, caught by the leg written to
catch exactly this. RULED: the five transcripts are committed beside
the instruments in this addendum (hash-verified), so every manifest
line resolves in-tree. Final inbox snapshot md5
`6c96d0147d3a9fb52637787fedcbddf7` (through R11; boundary held).
