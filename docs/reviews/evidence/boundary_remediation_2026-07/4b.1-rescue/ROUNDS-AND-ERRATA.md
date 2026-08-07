# Slot 4B.1 (immutable variable reads, MEDIUM-5) — rounds, register, errata

Companion to `slot-ledger.md` (frozen md5 `d70c4b79a8e1c5632cf5188c9f2e9514`,
1,059 lines) and `integrator-inbox.md` (through R5, md5
`6464c680bc627930de1e83115059aa62`). Base 4f2facaf (v0.769.0); final tip
`2f08bd7a1b251066d68126cc5ad086ef2a1a664c` (7 commits: 4 slot + 3 fix-round).
Shipped as v0.770.0.

## Round narrative

- **R0/D1** — dispatch; dev ACK + Phase A plan written before execution
  (9 instruments, census by AST as a deliberately different method from the
  integrator's grep, benchmark methodology pinned before measuring).
- **D2/R1** — Phase A EXECUTED: MEDIUM-5 reproduced 4/4 (incl. the dev's
  nameref fourth leg); census: ONE production `lookup()` caller
  (`operators.py:207`, `.is_set` only), ZERO `.binding` readers; the module
  docstring's perf premise ("lookup() sits on the shell's hottest read
  path") MEASURABLY FALSE at base (P5: 0 constructions on realistic
  workloads and at startup — integrator-reproduced, plus an
  integrator-closed gap: colon operators never reach `_param_is_set`, so
  the zeros are not a workload artifact); its "roughly triples" COST claim
  CONFIRMED for the routes it describes. Rulings: (a) design D — read-only
  properties over private `__slots__` at a measured 1.000x, PRESENT_UNSET
  0.956x (stops allocating); (b) `binding` OMITTED (exit criterion's
  binding leg later recorded as MET BY ELIMINATION); (c) frozen shared
  singletons + honest-caller threat model.
- **D3/R2** — binding pre-registration (58 cells, 33 red / 25 green as a
  per-class measured split); GO citing it by file+line+md5. R2 scope
  extension: the stale `VariableLookup` half of a precedent citation in
  `executor/command_resolution.py` dropped (2 doc lines, isolated commit)
  — found by the DEV as a stop-and-propose, ruled in by the integrator.
- **D4/R3** — Phase B landed. TWO SELF-REPORTED DEVIATIONS whose errors
  CANCELLED in the headline total (TestCompositionCells 4/0 vs registered
  3/1; TestRepresentationSemantics 3/3 vs 4/2) — reported by the dev
  against its own clean-looking numbers; and the M8-5 vacuous-cell
  self-catch (the equality pin compared a singleton to itself). Gate GO.
- **D5** — gate green: 23,604 passed (+58 exactly, cross-derived via the
  serial phase's deselected count moving 24,167→24,225), compare-bash
  3,042/26 EXACT, ruff/mypy clean.
- **R4 (harness round: 4 verifiers) — BOUNCE, 1 blocker + 13 raw nits.**
- **R4-a** — the dev DISPUTED the RN-2 five-cell list; integrator
  MEASUREMENT sided with the dev (six cells; see errata).
- **R4-b** — F3 declared (dev's self-caught ruff fault); unpiped-checks
  rule ADOPTED campaign-wide.
- **D6/R5** — fix round complete (F1/F2/F3); integrator-direct re-verify
  PASS at the integrator's own detached checkout.

## Final register

- **1 blocker (real): BL-1** — found by the HARNESS resurrection verifier:
  the module docstring of `tests/unit/core/test_variable_lookup.py` still
  taught the deleted `(…, binding)` signature at line 3 while
  self-contradicting the paragraph the dev rewrote at lines 7-8. Root
  cause (dev's own analysis, banked as a lesson): the propagation grep
  searched `\.binding\b` — one syntactic form — instead of the field NAME.
- **5 required nits (real):** RN-1 threat-model clause was a CLOSED
  enumeration with live routes outside it (`__init__` re-invocation —
  integrator-reproduced end-to-end — and `delattr`; found independently by
  two verifiers) → ruling (c-1) OPEN CLASS; RN-2 six unlabelled
  green-on-base carried-successor cells; RN-3 M8 SHA anchor (instrument
  honestly recorded DIRTY c1c7b69a; ledger said tip); RN-4 unnamed
  tip-suite checkout; RN-5 the §1.3 macro wall-time arm never discharged.
- **Dev faults (2, both self-caught):** the M8-5 vacuous equality cell
  (caught by the dev's own M8 run BEFORE the gate); the F2 ruff-red commit
  (piped exit status — mechanism recorded, rule adopted).
- **Integrator/harness faults (2, both recorded):** R4's RN-2 list said
  FIVE cells on the verifier's parenthetical; the dev's flag was upheld by
  integrator measurement (the sixth cell is green in per-cell isolation;
  the verifier's red came from class-level batching — itself a second
  demonstration that red-on-base is well-defined only per-cell). And the
  integrator's first M8 replay ran the driver without its companion plugin
  at the wrong depth — the instrument's own CONTROL refused to certify
  both times, exactly as designed.
- **0 false findings in both rounds.** 58 committed pin cells (32
  defect-evidencing red + 1 incidental-red labelled control + 25 declared
  green-at-base); M8 5/5 with kill counts 37/1/10/1/2 identical across
  FOUR independent runs (dev pre-fix, dev post-fix at a named clean
  checkout, harness verifier, integrator re-verify).

## Attribution constraints honored

- BL-1 belongs to the harness verifier, not the dev's sweep — and not the
  integrator's R1/R2 reviews either, which also missed it.
- The RN-2 six-cell correction belongs to the DEV (flag) + integrator
  (measurement); the original five-cell ruling was the integrator
  repeating the verifier's parenthetical without measuring.
- The perf-premise falsification (P5) is the dev's design work,
  integrator-verified; the colon-operator gap that makes W3's zero a fact
  about the code is the integrator's addition.
- The unpiped-checks rule extension was PROPOSED BY THE DEV out of its own
  fault report.

## What this slot deliberately did NOT claim

- Per-commit ruff cleanliness (F2 is a known ruff-red intermediate; the
  invariant is TIP-clean).
- Any closure of deliberate-circumvention routes (the (c-1) OPEN CLASS is
  demonstrated, not guarded; no available representation closes the whole
  class — §8.6).
- Any shell-observable behavior change (compare-bash 3,042/26 EXACT both
  ends; internal-integrity slot).
