# Slot 2.6 — verification rounds index + integrator errata (rescued at ceremony, 2026-08-01)

Slot: MEDIUM-9 analysis session (Wave 2 closer). Base 42f75591 (v0.761.0
code) → final tip **d89679de** (17 commits). SEVEN adversarial rounds,
TWO devs (dev-2-6 rounds 1–5; handover per the R13-D standing agreement;
dev-2-6b rounds 5-fix–7). **19 verifier-found defects + 1 integrator-chain
falsification = every finding real, 0 false.** Rulings R0–R23 in
`integrator-inbox.md`; the full narrative in `slot-ledger.md` (rescued
AS-IS — see errata below).

## Rounds

| round | workflow | verdict | headline |
|---|---|---|---|
| 1 | wf_f5b524f3-f39 | BOUNCE 4 blockers | heredoc bodies re-lexed as command text (regression); expand_aliases dropped from PARSE_RELEVANT_OPTIONS w/ false census docstring; interactive-leg record absent; 6 directive spellings missed |
| 2 | wf_3cda029c-51d | BOUNCE 2 distinct | alias absorption lost the command-position guard (regression); user-guide three-limits contradicted the per-option rule |
| 3 | wf_14547757-ee7 | BOUNCE 1 blocker | quote-blind backslash normalizer (`'sh\opt'` recognized as shopt) — 3rd same-class fault; R11 ordered the CLASS closed (string-surgery guard) |
| 4 | wf_9804286d-a6b | BOUNCE 4 distinct | 1 code (cluster rule single-word only) + 3 FALSE DISCHARGES (N1/N12/N13) → R13-C cert-row-before-claim |
| 5 | wf_8ffbd0eb-2ba | BOUNCE 6 distinct | blind rename de-collected slot 2.1's B8 pin; over-aggregation past first operand; E7/E9 half/undelivered; HANDOVER FIRED (2nd record-degradation round) |
| 5-fix | — | — | dev-2-6b: R15-B A–I + R15-C + R16 in 7 commits; `collected` cert kind born; 9-row arrangement widening (declared) |
| 6 | wf_e2806fa6-37f | BOUNCE 1 blocker | verbatim twin of the false whole-file-parse sentence in a conformance docstring; R15 work all HELD |
| 7 | wf_0a64b0a6-9ef | **PASS** | 0 blockers, 13 ceremony-class nits; R21-C suppression teaching confirmed on 13 novel cells |

## R23 nit dispositions (integrator)

1. `test_noexec_state_blindness_conformance.py` is **green-on-base BY
   DESIGN** — a claim-proving CONTROL ROW: it pins a *shared blind spot*
   (psh -n and bash -n agree in state-blindness), proving a user-guide
   bash-agreement claim; there is no state in which it could be red at
   base. (dev-2-6b's own note, adopted: it should have been labelled a
   control when added, rather than left for a verifier to classify.)
   The slot's red-on-base accounting is NOT short.
2. FLIP-PINS cross-ref for the deliberate `--validate`-vs-`bash -n`
   divergence: done in ceremony Commit A.
3. The brief's "byte-identical before/after" parity clause holds for the
   corpus MINUS the declared F7 post-heredoc-corruption class (whose
   changes are corrections, each pinned).
4. Analysis stderr gained a `file:N:` line component (= execution's
   renderer, strict improvement, pinned red-on-base): CHANGELOG line.
5. The 02_getting_started help-block hunk is drift-repair guarded by
   `test_help_transcript_matches_guide.py`; the program's `--help` delta
   is exactly one line.
6. `test_analysis_modes_ordered` deletion = the declared flip, correct.
7. `_MODE_RUNNERS` set-equality guard: successor row (LEDGER Part D).
8. Silent no-op `*_only` post-construction assignment: successor row.

## Errata in `slot-ledger.md` (rescued as-is; the record's imperfections are part of the record)

- The R21-F SUPERSEDED pointer says "Final check at 9d3a0e25" where the
  current table is titled "Final check at d89679de" (one round stale).
- R8-C census C2 cites `psh/shell.py:142`; at the final tip the write
  site is `:147` (count claim replays true; guard-enforced since R16).
- R8-C census C3's result column records the filtered reading of its
  grep (conclusion replays true at tip).
- Bounced rows B20–B26 are enumerated only inside `replay.py`, not in
  the round-5/6 addendum prose (totals derive from the instrument per
  the counts-derived rule; 625/625 independently reproduced in round 7).

## Named lessons this slot added to the campaign register

- "A claim that is its own only evidence is the purest form of this
  fault." (dev-2-6, round 4)
- "Intent narrated as implementation." (dev-2-6 stand-down, naming the
  false-discharge class)
- "A count without its instrument basis is not yet a fact; a guard
  without its universe is not yet a guard." (R10-A / dev-2-6 round 5)
- "When execution moves and the mirror does not, they part company by
  construction" — agreement-form assertions over fixed-status ones.
  (dev-2-6b)
- "The five measured cells are facts; the chain between them was not" —
  the R21-C falsification of the integrator's own unmeasured precedence
  interpolation (integrator fault tallied). (dev-2-6b / R22-A)
- The `collected` certification row kind: a suite post-state needs a
  suite-reading instrument — commit-content rows were structurally blind
  to test de-collection. (dev-2-6b)
