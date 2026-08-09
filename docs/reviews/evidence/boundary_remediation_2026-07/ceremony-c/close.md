# Ceremony C — Boundary Remediation Campaign close (2026-08-09)

This is the campaign's **self-contained close record** (the final leg of
HIGH-10, whose subject is exactly this class of artifact: closure records
must be committed, reproducible from the tree, and honest about what
remains open). It also formally closes the **transferred boundary-campaign
obligations**: the boundary campaign (v0.725.0–v0.750.0) was closed as an
implementation milestone on 2026-07-24 with its criterion-7 exit legs
discharged as this campaign's Wave 0 baseline and its 35-row carry
register dispositioned into this LEDGER's Part B; its closure was
transferred to this ceremony, and completes here.

Everything cited below is committed in this repository at the SHA of the
commit introducing this file (base `dff4a3bb`, v0.779.0). No claim in
this record depends on `tmp/`, on a dead-drop, or on any uncommitted
state. Where a figure was measured for this record, the instrument or
transcript is committed beside it.

## 1. Campaign shape and releases

Reappraisal #22 (audited at v0.749.0, verified at v0.750.0) produced the
30-row Part A register. Remediation ran:

- **Wave 0** (baseline + governing docs) through **Wave 4** — v0.751.0
  to v0.773.0, PRs #500s–#528/#529.
- **Checkpoint R** (whole-tree reappraisal at v0.773.0, evidence-only
  PR #529): clean bill certified under attack — 2 rounds, 0 blockers,
  0 false findings, 23/23 discriminators, 0 boundary resurrections.
- **%P rider** (CR-R2) — v0.774.0, PRs #530/#531.
- **Wave 5** — 5B.1 v0.775.0 (PRs #533–535), 5B.2 v0.776.0 (#536/#537),
  5C.1 v0.777.0 (#538/#539), 5C.2 v0.778.0 (#540/#541).
- **5R rider** (printf %a/%A) — v0.779.0, PR #542.

29 releases, v0.751.0 → v0.779.0, tags verified **gap-free** (29 tags in
the range, counted at this ceremony; v0.766.0/v0.767.0 minted via the
attestation-verified `workflow_dispatch` recovery, PR #532 — never a
manual tag). Every release gated by the local attestation flow
(`gate_attestation.json` as final commit, verified by `release-tag.yml`
before tagging).

## 2. Register sweep — Part A (30 findings)

Counted from the committed LEDGER at this ceremony:

- **29 CLOSED** — all 10 HIGH (HIGH-10 closes with this record: Wave 0
  delivered the A4 corrections + governing docs + evidence tree, Wave 1
  the durable oracle evidence, and this ceremony the self-contained
  close), 15 of 16 MEDIUM, all 4 LOW. The LOW deferred-import/Q2
  debt-ledgers row closes **by criterion** at this ceremony: its exit
  criterion was "caps materially shrink" — delivered as 66 entries /
  cap 177 == actual 177 / slack 0, locked by
  `test_every_cap_equals_its_modules_actual_count`, with the measured
  115-statement hoist remainder recorded in-row as a measurement with
  the missing step named (comment-aware move tooling) for the next
  owner (registered as D-CC-s1).
- **1 OPEN BY DESIGN** — MEDIUM-16 (boundary signatures): the seam half
  landed v0.777.0 (80 seams; census 648→632 Method A / 488→477 Method
  B, beating the ruled floor); the per-package depth half is
  post-campaign work, route stated in-row. Residue: 568 non-seam
  incomplete defs.

## 3. Register sweep — Part B (35 predecessor carries)

Every row carries a terminal disposition: **10 CLOSED** (#1, #2 — closed
before the campaign; #4, #7 with-scope, #8, #17, #22, #25, #28, #32),
**5 sanctioned/NOTE terminal states** (#15, #20, #26, #30, #34), and
**20 RE-CARRIED** into the successor register with pins intact.

Two rows stamped at this ceremony:

- **#28 (nested-subscript assignment extractor)** — was "ATTACHED to
  slot 2.3: close or re-carry with evidence" and never stamped after
  2.3 shipped. Stamped **CLOSED-BY-2.3** here on fresh evidence: 3/3
  nested-subscript assignment probes SAME vs bash 5.2.26 at `dff4a3bb`
  (`a[b[0]]=5`, `a[b[c[0]]]=7`, `a[$((b[0]+1))]=9` — outputs and rcs
  identical; cells recorded in the LEDGER row).
- **#17 (J1 Linux-nightly watch)** — closed v0.755.0; the standing rule
  it produced ("first scheduled nightly post-merge must be verified
  green") remains in force post-campaign and is restated in §6.

## 4. Register sweep — Part C (rulings) and CR-R4 discharge

All Wave 0, Checkpoint R, Wave 5, and per-slot rulings are discharged by
landed work or explicitly transferred: CR-R2 shipped (v0.774.0), CR-R6
PASS, CR-R7 became CR-D1, CR-R3 (exit-trap characterization) and CR-R5
(D-4A.2-s1) remain successor-queue transfers with their entry
requirements intact. The last open ruling obligation, **CR-R4, is
discharged by this ceremony**:

The three benchmark thresholds that were dev-machine-tuned and failed on
the shared runner (made step-level non-gating at slot 1.4, with the
workflow comment + always-uploaded artifact as the visibility
conditions) are retuned to **runner-measured envelopes** harvested from
3 consecutive nightly artifacts (runs 31237400812 / 31145981907 /
31070163425; harvest transcript committed at
`../checkpoint-r/instruments/qr/p07_benchmark_baselines.transcript.txt`):

| Row (`test_parsing_performance.py`) | old | runner measured (3 nightlies) | new | derivation |
|---|---|---|---|---|
| `test_simple_command_performance` `time_100` | 10ms | 11.30 / 12.48 / 11.43 ms | 25ms | ~2× runner median |
| `test_complex_structure_performance` `nested_time` | 10ms | 11.14 / 12.59 / 11.44 ms | 25ms | ~2× runner median |
| `test_tokenization_scaling` size-100 | 2ms | 3.05 / 3.38 / 3.10 ms | 7ms | ~2× runner median (QR-3 recommendation) |
| `time_1000` | 100ms | never reached (behind failing assert) | 250ms | pinned linear-scaling ratio × time_100 |
| `pipeline_time`, `case_time` | 10ms | never reached | 25ms | same workload class, same test |
| tokenization size-1000 / size-10000 | 20 / 200ms | never reached | 70 / 700ms | pinned linear-scaling ratio |

Rows that **passed** on the runner across all 3 nightlies keep their
measured-adequate constants untouched. `continue-on-error` is dropped
from the nightly's benchmark step — **the tier gates again** — and the
transcript artifact upload stays, so any future miss arrives with its
measurement attached. Verified locally post-retune: 16 passed / 1
xfailed (`benchmark-tier-local-post-retune.txt`, committed beside this
file). Carry 1.4's owed "measured runner baselines" are thereby
delivered and the carry row is stamped DISCHARGED.

## 5. Register sweep — Part D (successors and records)

162 substantive rows (169 table rows less headers), each carrying a
terminal route — verified by sweep at this ceremony (route classes:
CLOSED/DISCHARGED in a named slot, successor queue, divergence register,
standing lesson, record). The LEDGER is the authoritative successor
register; the headline post-campaign queue:

- **r18-lexer successor queue** — with the CLI-reachable lexer
  NO-PROGRESS CRASH re-affirmed PRIORITY at its head (CR-R6), named
  owner.
- **RESUMABLE-PARSER successor campaign** (H15 / carry #16 / the O(k²)
  ParseSession element ruled out of MEDIUM-15 with 5A).
- **General async reaper family** (carries #12/#16 + CR-D1
  characterization).
- **MEDIUM-16 per-package depth** (568 non-seam incomplete defs).
- **Divergence register** — CR-D2..D6, D-5C.2-d1/d2, D-5R-d1 and
  siblings: each both-sides-characterized, most both-sides-pinned.
- Per-slot `s`-rows (D-3.4-s1..s8 through D-5R-s1), each pointed.

## 6. Watches and standing rules at close

Stated honestly as open observations, each with an owner (the
post-campaign maintainer session), none blocking this close:

1. **Next nightly (~2026-08-10 03:30Z)** — first Linux exposure for
   v0.777.0/v0.778.0/v0.779.0 (5C.2 touched fd/job-control-adjacent
   code; 5R's conformance rows were built libc-stable by design), and
   the **first gating benchmark-tier run** under the CR-R4 retune.
   Contingency if the tier misses despite ~2× headroom: single-step
   rollback (restore `continue-on-error: true`) or widen from the fresh
   artifact measurement — either is a one-line change, and the
   transcript artifact carries the data.
2. **Standing rule from carry #17**: first scheduled nightly after any
   merge is verified green as part of the wave-close/session checklist.
3. The 08-09 nightly (at `4c333a78`, v0.776.0) was verified **green**
   during this ceremony — the most recent completed Linux signal at
   close.

## 7. Hygiene

Stale remote `fix/remediation-*` branches from prior slots' merge
wrinkle (11 enumerated at this ceremony: 1-1, 1-2, 1-3, 1-3b, 3-4, 3-5,
5b-1, 5b-2, 5b-2-addendum, reviews-index, wave0) — each verified fully
merged into `origin/main` before deletion; deletions executed at this
ceremony and recorded in the ceremony section of the LEDGER.

## 8. Close statement

With CR-R4 discharged, HIGH-10's final leg delivered by this record, and
every register row terminally dispositioned or explicitly routed, the
**Boundary Remediation Campaign is CLOSED**, and with it the transferred
closure of the boundary campaign completes. Post-campaign work proceeds
from the successor register (Part D) and the divergence register, not
from this campaign's queue — which is empty.
