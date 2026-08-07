# Slot 4B.3 — Rounds, Faults, and Errata (integrator record)

Slot: history state machine — MEDIUM-7 (both cursor legs + `-s` policy),
carry #32 (`-a`/`-c`/`-n` counter model), carry #25 rider (clustered
flags). Base `bd13b303` (v0.771.0) → final tip `4f079c14` (10 commits).
Shipped at v0.772.0. Dead-drop: `integrator-inbox.md` (R0–R12 /
D1–D13, md5 chain intact both directions throughout; ACK-the-highest-R
structural rule from R6). Frozen slot ledger: `slot-ledger.md`
(freeze-chain: c05102c0 → dd99a730 → 75bb0495 → fd2a7193, each move
quoting its predecessor from R11 on).

## Round chronology

| Round | Event |
|---|---|
| R0/D1 | Dispatch; dev found MY carry sweep incomplete (rows 25, 10) and a wrong CV3 pin pointer — errata E1/E2, rider ruled IN (R1) |
| D2/R2 | Phase A: bash counter model. My verification CONFIRMED 5 rows, BOUNCED 2: R2-F1 (the `-a` model idealized — could not discriminate marker vs tail-count), R2-F2 (psh read paths swallow pending typed entries). Partial GO |
| D3/R3 | A1′ re-derivation: bash's `-a` = POSITIONAL TAIL WINDOW (executable model, all 9 pre-stated cells + my adversarial MIX cell). bash's own model loses AND leaks → O3 ruled in (explicit pending set; 5 binding invariants) |
| D4/R4 | O3 landed, `_file_synced_len` RETIRED. My probe found b5 (default-file `-w`→`-a`), a fifth deviation face living only in a counter-pin — declaration required |
| D5–D8, R5–R7 | Pins (case history ~40-55 → 84 → 90 → 104 → 106 cells, all labelled), gates: 23,817/1,620/10 EXACT, compare-bash 3,046/26 EXACT |
| VERIFY 1 (R8) | Workflow harness: **BOUNCE, 4 blockers + 15 RNs, all real** (I reproduced BL-1/2/3 independently before issuing) |
| D9–D12, R9–R12 | Fix round: all 4 BL + 15 RN with pins; gates re-run EXACT (23,833); my integrator-direct re-verify PASS + one finding (b4 mirror face) |
| D13 | Mirror face pinned WITH the offset-not-suppression control; tip 4f079c14 |

## Verify round 1 blockers (all fixed, commit 8bb139ee)

- **BL-1** REGRESSION (base correct): pending view resolved by TEXT —
  a `-d`'d entry resurrected into $HISTFILE as a duplicate; the pin
  naming the property was hollow (NAME-VS-BODY inside the dev's own
  suite). Fixed: owed flag per POSITION; genuine pins incl. the
  counter-direction twin cell and the leak face.
- **BL-2** false bash claim: "two of `-anrw`: rc 1, no message" —
  bash prints `cannot use more than one of -anrw`; tip was silent.
  Fixed with channel-asserting pins.
- **BL-3** clusters ran every action; bash runs AT MOST ONE, with
  OPERAND-SENSITIVE `-c` suppression (found in the fix round:
  `-cw` suppresses, `-cw FILE` runs). Root cause: a `-cw` instrument
  on a named EMPTY file could not discriminate — instrument-mirror
  family, third occurrence.
- **BL-4** b4's "both-sides pinned" was claim-true but CELL-missing —
  silently-dropped commitment (4B.2 lesson 10).

## Fault register (F-1..F-9, gap-free; all self-disclosed except F-5)

| # | Fault | Owner |
|---|---|---|
| F-1 | read-counter instrument delta arithmetic invalid under trim (VOIDed + rebuilt w/ control) | dev |
| F-2 | rc probe captured the marker echo's status (exposed by the known-rc-2 row) | dev |
| F-3 | heavy-territory run (798s) without pgrep/token | dev |
| F-4 | D5 appended + doorbelled without reading R4 | dev |
| F-5 | D6 repeated F-4 with R5 unread (found by integrator from the file order + `ps`; the dev could not have self-disclosed it) | dev |
| F-6 | BL-2 probe filtered stderr then took `[:2]` — job-control warnings crowded out bash's real diagnostic | dev |
| F-7 | action-model probe inferred "delete fired" from an absence a clear also produces (VOIDed + rebuilt) | dev |
| F-8 | the a7 `-cw` named-empty-file confound behind BL-3's false model | dev |
| F-9 | F-3 repeated: 8,415-test sweep, no pgrep/token (disclosed unprompted; its data reused honestly as §3.7 pre-run evidence) | dev |

Integrator faults, recorded with the same standard: E1 (dispatch carry
sweep missed LEDGER rows 25 and 10 — row 25 names this slot), E2
(brief's must-not-flip pointer named a file with zero history rows),
R2's five-vs-six risk paid forward from 4B.1, and the R10 note that I
could not mechanically verify a freeze-move claim until I began
snapshotting frozen ledgers (closed: snapshot rule + the dev's
freeze-chain proposal, both now standing).

## Structural rules born in this slot

1. **ACK-the-highest-R** (R6): every D-entry opens by ACKing the
   highest R-number found by re-reading the file in the same turn —
   a skipped read becomes structurally visible.
2. **Freeze-chain** (R11, dev-proposed): every freeze declaration
   quotes the previous freeze md5.
3. **Integrator snapshots every frozen ledger** at freeze time (R10).
4. **`--collect-only` count first** for any pytest argument that is
   not a file or node ID (F-9 countermeasure).
5. **Instruments are files from the start** — inline-heredoc probes
   are an evidence-integrity defect even when their readings are
   correct (D7's six regenerated transcripts, tip-reading caveat
   declared).

## Reading caveats

- Six regenerated transcripts in `instruments/` (named in D7) read at
  the FIXED tip; their base-state claims rest on the D4/D6 quotations
  plus the integrator's independent reproductions (both archived).
- `verify-round-1-verdict.json` is the round-1 workflow report
  verbatim; its BL-3 model ("at most one action") was REFINED by the
  fix round's operand-sensitivity discovery — read D9/R9 with it.
- Integrator instruments live under `instruments/integrator/`
  (dispatch probe, per-round verification probes, the bounce
  confirmations, the operand attack, and the 75bb0495 ledger
  snapshot that made D13's only-declared-sections-changed claim
  mechanically checkable).
