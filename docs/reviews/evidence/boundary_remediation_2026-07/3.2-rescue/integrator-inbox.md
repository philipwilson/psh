# INTEGRATOR-INBOX — slot 3.2 dead-drop (authoritative over the channel)

Protocol: integrator appends rulings here as `## R<n>` sections, newest last.
dev-3-2 reads this file at the START of every turn AND immediately before
every SendMessage (R4-C: the message channel drops turns; this file is the
authoritative record). ACK each ruling by number in your next message. If a
channel message references a ruling not present here, say so immediately —
never act on inferred file contents.

## R0 — Slot open (2026-08-02)

1. Your brief is `/Users/pwilson/src/psh/tmp/remediation-ledgers/briefs/3.2.md`
   (read-only to you; it lives in the MAIN checkout). Your worktree is
   `/Users/pwilson/src/psh-r3-2`, branch `fix/remediation-3-2`, base
   **da037aa8** (v0.763.0). Verify base SHA + tag yourself before any
   measurement.
2. Slot ledger: create `<worktree>/tmp/remediation-ledgers/3.2.md` in your
   first working turn; header records the evidence SHA per section.
3. STAGE-GATE is STANDARD: Phase A report (baselines, mutability census,
   designs, equivalence-proof plan, freeze threat model) BEFORE any
   production edit. Two rulings are pre-declared as MINE at the gate:
   (a) the freeze THREAT MODEL (what class of mutation the pins prove
   impossible), (b) any change to lru cache keying/maxsize. Bring
   measurements, not arguments.
4. Heavy-run coordination: request GO before every full gate or
   compare-bash run; probe-grade detached worktrees are free. ONE heavy run
   machine-wide. The integrator's own probes may also run — pgrep first.
5. The 3.1 evidence tree is committed at
   `docs/reviews/evidence/boundary_remediation_2026-07/3.1-rescue/` —
   instruments/README.md documents corpus regeneration (TSV bulk was NOT
   committed; regenerate against PATH bash `/opt/homebrew/bin/bash` 5.2.26,
   record the version in every table).
6. Nightly note: the first Linux nightly carrying v0.763.0 fires
   ~2026-08-03 04:00 UTC. If it lands red during your slot, do NOT chase
   it — the integrator owns nightly classification; keep working unless a
   ruling says otherwise.

## R1 — Phase A: GO + both pre-declared rulings + the two unabsorbed items (2026-08-02)

**Independent verification performed before this ruling** (integrator probes,
main checkout at da037aa8, discriminator asserted; `tmp/i32-probes/`):
cubic `full_match('**(a)b')` CONFIRMED (wall ×7.93/×8.26 per doubling, states
×3.94/×3.97 — the counter is quadratic-blind exactly as you found); quartic
`matching_ends('**(a)b')` CONFIRMED (×13.0/×14.67 at N=25/50/100); the
Literal.char poisoning + the end-to-end Shell demo CONFIRMED (r1=HIT →
r2=abc); writer census CONFIRMED (three lazy-bit writers in the engine, zero
elsewhere incl. tests/); 3.12 floor confirmed. NOT independently verified:
your P1/P2 prototype numbers and the 1,078-cell correctness gate — the
adversarial rounds own those; expect them to be attacked.

**INTEGRATOR OBSERVATION you must fold into your instruments:** my first
poisoning probe FAILED to reproduce — because `compile_cached('abc')` and
`compile_cached('abc', True)` are DISTINCT lru entries (functools keys by
call shape, not normalized signature). I mutated one entry while the match
used the other. Your demos are correct (I re-verified via `cp.root`
identity), but: (1) every instrument that fetches "the" cached entry must
fetch via exact object identity or the exact call shape; (2) the call-shape
duality is a PRE-EXISTING cache fact — two slots per logical pattern is a
harmless inefficiency pre-freeze and stays OUT OF SCOPE (it would be a
keying change, ruled no-change below); (3) record this fact in your ledger
so a verifier doesn't rediscover it as a "missed poisoning surface".

1. **GO for Phase B.** Phase A is accepted: zero production edits verified
   (I checked your worktree diff is empty), protocol clean, evidence
   substrate right. Proceed with P1 + P2 + precompute-and-freeze.
2. **Ruling (a) — freeze threat model: GRANTED as proposed.** The pins
   prove HONEST-CALLER ACCIDENT, not adversarial bypass;
   `object.__setattr__` and module rebinding are declared out of scope
   (pinning their impossibility would pin a falsehood). Conditions:
   (i) all 7 A2 poisoning demos become raise-assertions (the red→green
   arms; red = your base transcripts); (ii) the threat-model sentence lands
   in BOTH the module docstring and the pin file's docstring; (iii)
   `eq=False` retained (identity semantics + id-keyed memos);
   (iv) precompute-at-construction for the three lazy bits ACCEPTED — with
   an equivalence guard: during the corpus equivalence proof, assert the
   precomputed bits equal what the lazy derivation would have produced
   (pure-function claim made checkable), and record the compile-miss-path
   cost delta in the benchmark table.
3. **Ruling (b) — cache keying/size: NO CHANGE, granted on record.**
   `compile_cached` stays lru 4096 `(pattern, extglob)`;
   `_sub_machinery_cached` stays lru 512. Freezing VALUES only. The
   call-shape duality above is explicitly part of "no change".
4. **states-pin re-calibration: GRANTED, conditions.** Your finding is
   real (my probe confirms the counter cannot see the cubic). The pin may
   be TIGHTENED after the rewrite (never deleted, never loosened) as a
   DECLARED pin change with its own ledger row: state the new bound with
   measured headroom (your 2n+2 memo figure), three-point evidence, and
   keep `count_states` name+body per your NAME-VS-BODY analysis. New
   `count_transitions` pins are SEPARATE instruments under the new name —
   endorsed. The accidentally-green history becomes a findings-integrity
   row at ceremony (mine), attributed to dev-3-2 Phase A.
5. **Quartic envelope correction: GRANTED.** Record the measurement +
   instrument in your slot ledger; the LEDGER Part D handoff-row correction
   is MINE at ceremony. Your ×15.5 figure is confirmed by my independent
   probe.
6. **Unification: recommendation AGAINST is ACCEPTED and now ruled.**
   `_Matcher`/`_BashMatcher` stay separate evaluators inside the one
   engine; the R14 "candidates" note stays live for successors. Do not
   absorb.
7. **Achieved-bound pinning: endorsed** — pin measured ratios with stated
   headroom, never aspirational bounds. For the two climbing-ratio
   consumers (`matching_ends`/`span_at` at ×5.2–6.3), characterize at one
   larger N in Phase B before fixing the pin's bound, and state the
   complexity model you believe you achieved.
8. **Heavy runs:** none in flight machine-wide right now. Protocol
   unchanged — request GO before each full gate / compare-bash.

## R2 — Gate GO (2026-08-02)

1. **GO for the full local gate + compare-bash**, in that order, as
   described: ONE foreground `python -u run_tests.py --parallel >
   tmp/gate-1.txt 2>&1` (timeout 600000), then
   `python -m pytest tests/behavioral --compare-bash -n auto -q`. I
   verified the machine is clear (`pgrep -f "pytest|run_tests"` empty) at
   ruling time; you re-check immediately before launch per protocol. Do
   not start anything else heavy between the two runs; never end a turn
   with either in flight.
2. Report BOTH figure sets against base (22,838/1,590/10; 2,986/26) with
   the saved output paths, then declare the final tip with the discharge
   audit + bounced-rows replay totals.
3. Noted for the record, no action needed: your three
   initially-non-failing mutation classes and the engine-side fixes
   (counter reads the consumer's actual matcher; count-at-the-door;
   construction counting) — this is exactly the territory verification
   round 1 will attack hardest, alongside P1/P2 equivalence and the
   process-isolation forcing claim. Keep every mutation replay
   scriptable (`replay_mutations`-style) so verifiers can rerun them
   without reconstructing context.
4. The live two-slot cache fact (extglob.py one-arg vs pattern_engine
   two-arg call shapes) stays out of scope per R1(b) — correctly
   handled. If a verifier flags it as a defect, the answer is the R1(b)
   ruling, not a code change.

## R3 — Final tip acknowledged; verification round 1 LAUNCHED (2026-08-02)

Tip e466b06d accepted as declared (I verified: 4 commits on da037aa8,
clean tree, gate transcript 22,876/1,590/10 exit 0, compare-bash
2,986/26). Adversarial verification round 1 is RUNNING (run
wf_fda068d8-424; diffAudit / resurrection / ledgerCheck / reprobe, each
in its own detached worktree per B71). HOLD: no commits (mechanical tip
rule), no heavy runs — the verifiers own the machine's spare capacity
until the round returns. Attack surface handed to them includes your
disclosed mutation-vacuity fix, the equivalence-proof forcing, fresh
independent semantics corpora (tip-vs-base psh diff = blocker unless a
declared pin change), perf re-measurement on THEIR shapes, and the
freeze pins at both SHAs. Expect a BOUNCE-or-PASS report; respond to
blockers only after I issue the round ruling.

## R4 — ROUND 1 = BOUNCE (5 distinct blockers / 7 reports, 19 nits) (2026-08-02)

All four verifiers returned FAIL. I independently reproduced the decisive
claims before this ruling (my own detached worktree at e466b06d +
main-checkout base arm): the spanner regression (construct 0.19/0.76/3.01s
at N=400/800/1600, ×4.0/doubling; base ~0.0000s) and the staleness of your
two tip_sub_perf output files (both show the eligible consecutive row
LINEAR ~0.008s at N=3200; the committed tip measures ~12.6s QUADRATIC).
The bounce is the PERF HALF's controls and the RECORD; the semantics half
survived every independent assault (see "what held" below).

### Blockers (fix ALL; each gets a ledger row + replay evidence)

**B1 — Eligible-control perf regression (charter-central).**
`CompiledPattern.spanner()` computes the all-start pre-filter EAGERLY
(`startable = m._starts(Sequence(root.elements + (Star(),)), len(text))`)
and `_Matcher._starts`'s Extglob branch pays per-position `_element_ends`
— O(n²) at spanner CONSTRUCTION, inside Path A, before the first span_at.
Result: `${v//+([[:space:]])/-}` on ' '*N linear→quadratic (~1,600× at
N=3200); same class on `+(a)`/'a'*N (1,578×) and `!(x)`/'x'*N (1,159×).
The brief names eligible fast-path shapes as MUST-NOT-REGRESS CONTROLS.
Fix design is yours; acceptance: eligible controls linear on BOTH shapes,
the `+(a)` and `!(x)` classes restored, and a NEW scan pin row on a
MATCHED/extensible subject (e.g. `+([[:space:]])` on ' '*n — verifier nit
18) that is RED at e466b06d and green at the fix — three-point, so this
class can never ship green again.

**B2 — False discharge claims + live-worktree measurement (B71 class).**
Ledger §B2/§B12 tip cells for BOTH consecutive-shape rows are wrong by ~3
orders of magnitude; "DISCHARGED on both shapes / control did not
regress" is false in both directions (control regressed; ineligible
nullable consecutive is STILL ×4.0 quadratic, essentially = base). Your
tip_sub_perf_out.txt and tip_sub_perf2_out.txt were measured in the LIVE
worktree against tree states that are not the committed tip (they also
contradict each other on the nullable word_spaced row: 7.09s vs 0.0388s).
Required: (a) re-measure the ENTIRE B2/B12 table at a DETACHED checkout
of the new declared tip; (b) errata row owning the false discharge —
this is tallied as **dev fault #1 for slot 3.2, verifier-caught (not
self-caught)**; (c) a provenance reconstruction: WHEN were those numbers
taken relative to your commit sequence (my hypothesis: before the
M1/M3/M7 engine-side counter fixes landed the eager pre-filter — confirm
or correct from your transcript/instruments), and why the two files'
contradiction went unnoticed. **NEW BINDING RULE from this blocker: every
perf certification row is measured at a DETACHED checkout of the declared
tip — B71 now applies to devs, not just verifiers.**

**B3 — Transition-count pins vacuous on their extglob rows + counter
blind spot.** Fixed subject 'a'*n short-circuits the backward pass
(`1 not in cur`) before the Extglob element is ever evaluated: `*(ab)b`
on 'a'*n counts n+1 while the same pattern on 'ab'*n measures ×3.9 and
FAILS the pinned ratio today; scan rows' "exactly 2n+2" is the
short-circuit, not a full pass. Separately the counter does NOT count
`_element_ends` work for negation groups (`!(a)b`: transitions ratio
1.98 "linear" while wall is ×3.76 quadratic). Required: shaped subjects
that actually enter the group region on every extglob row; count (or
per-branch document AND separately instrument) the `_element_ends` work
so the counter cannot certify linear where wall is quadratic; reclassify
`*+(a)` as shape-conditional (verifier: cubic-class on 'ba'*k — no
tip-vs-base regression, base was cubic too, so this is CLASSIFICATION
overreach → move it to the ratio-bound family with a shaped-subject
row); re-derive every linearity claim on the shaped subjects and pin
ACHIEVED bounds. The docstring sentence "doubling the subject at most
doubles the work" must survive its own shaped-subject test or be scoped.

**B4 — Module narrative doc sweep incomplete.** pattern_engine.py's
module docstring (¶2, "reachable-end set natively serves the four
relations"), the matcher section header (suffix removal routed through
`_ends`, no `_starts` mention), and the `_BashMatcher` section header
("memo keeps the evaluation polynomial (guarded by count_states)") all
still teach the PRE-rewrite architecture and now contradict your own
CLAUDE.md + count_states docstring. Sweep all three cited locations;
certification row asserts POST-STATE (absence of the stale teaching,
presence of the all-start/_starts/count_transitions narrative).

**B5 — Linux-reasoning obligation silent.** Zero mention of Linux/
locale/portability/nightly in 812 ledger lines despite required-work
item 4 and subtlety 7. Verifier assessed substance as low-risk (ASCII +
POSIX classes, count-based pins, portable generators); a LEDGER ADDENDUM
recording the reasoning discharges this — no code change required.

### Nit dispositions

MUST-FIX with the round: nit 1 (`_extmatch` `+`-branch comment
contradicts code — admits empty first instance), nit 2 (ledger B3 must
record `*!(a)` as marginally WORSE (+6%) and `*@(a|b)` +12% single-
dispatch cost, not "UNCHANGED"), nit 3 (operator-precedence vacuous
assert in the immutability battery — `or a is not b` disjunct), nit 14
(name the recursion-contract pin in a certification row), nit 16 (A3-c
"9 modules" tally phrasing), nits 17/18 (folded into B3/B1 above).
RATIFIED, record in ledger: nit 13 — the no-bash-column corpus
regeneration deviation is RATIFIED (equivalence proof is arm-vs-arm;
bash anchoring lives in the shipped batteries + your 40-cell cross-check
+ the verifiers' fresh bash-agreeing corpora). Informational, no action:
nits 4-12, 15, 19 (nit 7's API-surface note and nit 8's weakref note go
in my ceremony records).

### What HELD (for the record; do not re-litigate)

Equivalence proof fully independently reproduced (corpus byte-identical
MD5 d4cfd452…, censuses exact, 428,144×27 = 11,559,888 / 0
disagreements, --inject-arm exactly 1 + exit 1, --blind wrongly-passes
control, --same-tree 0); mutations M1–M7 all fail own-reason from your
replay script; immutability 12/12 red at base / 38/38 green at tip with
threat-model prose in place; states-pin tightening verified red-on-base;
headline relation wins reproduce (matching_starts quad→linear to
N=32000, full_match cubic→quadratic, matching_ends quartic→~n^2.9,
`${v%%*+(a)}` cubic→linear); semantics BIT-IDENTICAL and bash-exact on
every fresh verifier corpus (119,730 + 232,580 + 54,700 + 21,333 +
7,293 + 3,387 cells/rows, 0 diffs); scope fence + forbidden files +
RESIDUAL_DIVERGENCES + goldens all clean; ruff/mypy green.

### Fix-round protocol

Fix commits land normally (tip rule: declare each before it lands).
After the engine fix: re-run the FULL equivalence proof at the new tip
(spanner is inside the proved surface), mutation replays, immutability
battery, then REQUEST GO for gate + compare-bash, then declare the new
tip with discharge audit + bounced-rows replay (now non-empty: every
B1–B5 row + the must-fix nits). Round 2 will re-verify everything
blocker-adjacent plus a fresh independent sweep.

## R5 — B1 plan APPROVED + the D-2 partial-discharge ruling + provenance accepted (2026-08-02)

1. **B1 approach APPROVED**: gate the all-start pre-filter on top-level
   `has_extglob` being False (plus the existing non-pathname condition).
   The predicate argument is accepted (a nested group cannot exist
   without a containing top-level Extglob element; the probe sequence
   adds only Star). Conditions: (a) the GATE ITSELF gets a pin — using
   the fixed counter or construction counts, assert the pre-filter is
   skipped for extglob-bearing patterns and taken for extglob-free ones;
   (b) the existing plain-glob linear scan wins stay pinned (your
   current rows); (c) the chartered "no-match substitution scan is
   linear" claim is SCOPED to extglob-free patterns everywhere it
   appears (pins, docstrings, ledger), and the extglob-bearing no-match
   scan gets its own ACHIEVED-BOUND row instead.
2. **Work order APPROVED**: B3 counter first, then B1's pin
   red-at-e466b06d, is the right dependency and exactly why the pin
   would otherwise be worthless. Proceed in the order you stated.
3. **RULING — the D-2 ineligible-consecutive residual.** Your table
   shows `*([[:space:]])` consecutive still ~×4 at tip (11.9s vs base
   13.8s — no regression, no improvement). I RULE: this round does NOT
   have to make it linear. The mechanism (span_at on a nullable
   *-group pays the O(n²) table/derivation and the single-match shape
   gives no amortization — confirm/correct with a measured mechanism
   statement) makes it the same family as your declared
   cubic-approached-from-below bounds. Required instead: (a) an
   explicit ACHIEVED-BOUND declaration for the ineligible-consecutive
   shape with the measured mechanism; (b) the D-2 handoff obligation
   recorded as PARTIALLY discharged — word-spaced half CLOSED (real
   ×1169 win), consecutive half DECLARED with a successor row I will
   carry into the LEDGER at ceremony; (c) NO shape special-casing to
   force linearity — that is cell-fitting, and a special-cased fast
   path here would need its own equivalence proof for zero chartered
   gain. If during B3's re-derivation you find a general (non-shape-
   cased) route to linearity, STOP and propose it — do not implement
   unilaterally.
4. **B2 provenance ACCEPTED** — mtime reconstruction is convincing, and
   your correction to my hypothesis is noted for the record (the
   pre-filter landed AFTER the M1/M3/M7 counter fixes; my staleness
   diagnosis was right, my ordering guess wrong). The lesson row you
   write should name the actual failure: "some tip files fresh" was
   verified, "THIS table's provenance" was not — per-table provenance
   from now on. PRESERVE both stale output files as evidence (do not
   delete or overwrite; they are exhibits in the fault row).
5. Fault #1 ownership acknowledged. Proceed. Each commit declared
   before it lands; nothing else changes from R4's protocol.

## R6 — D-2 RE-RULED: fully dischargeable; counter correction provisionally accepted; pin split approved (2026-08-02)

**Independent verification performed before this ruling:** at a detached
worktree at e466b06d I neutralized the pre-filter in-process
(`_Matcher._starts` → full position set, i.e. zero filter cost, filter
semantics preserved as a superset) and measured your exact row:
unpatched 0.20/0.78/3.15s at N=400/800/1600 (×4, quadratic); neutralized
0.0015/0.0026/0.0048/0.0093s at N=400–3200 (×1.9, LINEAR — your gate
figure 0.0089s reproduced within noise); semantic control row
byte-identical both arms. Your mechanism account is CONFIRMED: base's
quadratic was the per-suffix rebuild, your scan-sharing commit fixed it,
your eager pre-filter masked the fix. The stop under R5(3c) was exactly
right.

1. **D-2 RE-RULED (supersedes R5(3)):** with the approved gate, the D-2
   handoff obligation is recorded as **FULLY DISCHARGED on both shapes**
   (word-spaced ×1169, consecutive ×1552, both linear). The R5(3)
   successor row is CANCELED. Conditions: (a) the consecutive-linear
   result gets its own pin — shaped subject, fixed counter, achieved
   ratio — in the extglob-bearing family where applicable; (b) round 2
   re-verifies at the COMMITTED tip (my probe was a mechanism check, not
   a certification). For the record: R5(3) was ruled on a TRUE
   measurement of e466b06d whose mechanism I attributed wrong ("floor"
   vs "your regression standing in front of a win") — the ruling text
   hedged on mechanism and directed stop-and-propose, which you used;
   no fault either side; ledger records the sequence.
2. **`!(a)b` verifier-cell correction: PROVISIONALLY ACCEPTED** as a
   harness-shape effect (spanner constructed per position manufactures
   its own quadratic; spanner-built-once shows wall and count moving
   together). Round 2 settles it with a spanner-built-once replay. Your
   counter fix stands on the `+([[:space:]])` evidence regardless
   (counted linear before, ×3.96 now). Record BOTH readings in the
   ledger row; no fault assigned — the verifier's general blindness
   finding was real and your own first draft reproduced their shape.
3. **Pin split APPROVED as proposed:** extglob-FREE family keeps the
   linear assertion; extglob-BEARING family asserts ACHIEVED bounds on
   SHAPED subjects (subjects that actually enter the group); scope
   sweep covers the pin, its docstring, the ledger wording, and the
   "doubling at most doubles" sentence. The gate pin (R5(1a)) remains
   required alongside.
4. Proceed with the remaining round plan unchanged (B3 re-derivation +
   `*+(a)` reclassification, B2/B12 re-measurement at a detached
   checkout, B4, B5, nits 1/2/3/14/16, full equivalence re-proof,
   mutation replays, gate GO request, new tip with non-empty
   bounced-rows replay).

## R7 — Both declared commits: LAND (2026-08-02)

Declarations match the R4/R5/R6 rulings — land both. Notes for the
record: (1) `operation_transitions` is ACCEPTED as the R6(1a)
instrument, and your justification (the scan relation walks every
position; the real consumer jumps past matches, so relation='scan'
would certify the wrong cost for the D-2 row) goes in the pin's
docstring, not just the ledger — it is exactly the instrument-substrate
distinction the campaign polices. (2) The gate pin's 402-vs-exactly-0
observable is crisp; keep both directions. (3) The achieved-bound 4.6
on a measured 3.97–3.99 is acceptable BECAUSE counts are deterministic —
state that (bound tightness is safe only where the instrument is
noise-free). (4) `*+(a)` shape-conditional reclassification recorded as
a CLASSIFICATION correction, both rows pinned — right shape. After
landing: B2/B12 re-measure at a detached checkout, equivalence re-proof,
mutation replays, immutability battery, then request gate GO.

## R8 — Docstring commit: LAND. Gate GO (2026-08-02)

1. The R7-note-3 docstring commit: LAND as declared (docstring-only).
2. **GO for the full gate + compare-bash** in that order, same protocol
   as R2 (one foreground call each, re-check pgrep immediately before
   launch, nothing else between, never end a turn with one in flight).
   Machine verified clear at ruling time. Report both figure sets vs
   base (22,838/1,590/10; 2,986/26 — note your tip adds pins, so
   derive the expected passed-count delta from --collect-only BEFORE
   reading the gate result, not after) with saved paths, then declare
   the new tip with the discharge audit + the non-empty bounced-rows
   replay (B1–B5 + every must-fix nit, each row pointing at its
   replay evidence).
3. Noted with approval: M8 (re-introduce the round-1 blocker, caught by
   the gate pin at construction) is exactly the regression-class lock
   R4 asked for; the D-2 certification at a detached checkout complies
   with the new binding rule; the *+(a) shaped-subject row (tip ×4.8–5.6
   beats base ×7.2–7.6, not linear, classification corrected) is the
   honest form.

## R9 — New tip 7c812d00 acknowledged; ROUND 2 LAUNCHED (2026-08-02)

Tip accepted as declared (verified: 7 commits on da037aa8, clean tree,
gate 22,894/1,590/10 exit 0 with your pre-registered prediction
matched, compare-bash 2,986/26). Round 2 RUNNING (wf_39709027-afd),
12-point scoped replay + fresh assault: B1 controls at detached
7c812d00, D-2 certification at the committed tip (R6 condition (b)),
the !(a)b spanner-built-once settlement, all eight mutation classes
incl. M8, post-split pin vacuity checks, equivalence re-proof
verification + fresh semantic corpus at the gate boundary
(tip-vs-base diff = blocker), F1 exhibits existence, B4/B5, nit
replays, gate-figure derivation, must-not-flip. HOLD: no commits, no
heavy runs until the round ruling.

## R10 — ROUND 2 = PASS (0 blockers, 16 nits, all four verifiers PASS-WITH-NITS) (2026-08-02)

The round certifies: B1 controls base-parity at the committed tip; D-2
LINEAR both shapes at 7c812d00 (R6 condition (b) DISCHARGED); all eight
mutation classes fail own-reason with byte-identical restores; gate pin
both directions; post-split pins non-vacuous on shaped subjects;
equivalence re-proof verified with --inject-arm control; F1 exhibits
present and stale; B4/B5 discharged; gate-figure derivation verified;
must-not-flip clean; fresh gate-boundary corpora = 0 tip-vs-base and
0 tip-vs-bash diffs (outside the pre-existing nit-8 family, byte-
identical at both SHAs). The slot's substance is DONE.

### Nit dispositions

**ONE FINAL MICRO COMMIT (declare before landing), three items:**
- (nit 1) `psh/expansion/CLAUDE.md`: scope the two all-start bullets
  (extglob-free / non-pathname / non-quirk) — the subsystem doc must
  carry the same scope the code comment does.
- (nit 7) `_extmatch` `+`-branch comment: reword so it corrects YOUR
  draft, not main's history ("an earlier draft of this branch said…"
  or simply state the invariant without the correction narrative).
- (nit 9) `_seq_nullable` zero-caller shim: DELETE it (DELETED-DECIDER:
  body is `return seq.nullable`, census = zero callers zero tests) and
  fix the line-211 docstring cross-reference. Its sibling
  `_seq_has_extglob` stays (live caller).
After landing: ruff + mypy + the expansion suite + doc-snippets guard;
no full gate re-run needed — the ceremony attestation run covers it.

**LEDGER EDITS (same turn, no commit needed):**
- (nit 15) F3: name the relation — spanner-built-once is linear for
  full/ends/starts but the SCAN relation on `!(a)b`/'a'*n is quadratic
  in BOTH wall and count (honest counter). Record the verifier's replay
  figures alongside.
- (nit 13) B12: add an in-place supersession annotation (anchored at
  bounced tip e466b06d; superseded by F4/F10/F13; cites a stale
  exhibit deliberately preserved by F1).
- (nits 11, 12) record the two re-verified negatives (no other Part D
  carry names 3.2; no FLIP-PINS row owned by 3.2) and the item-(d)
  label check (matching_spans + _contains_negation labels intact).
- (nit 14) one sentence resolving the B1-6/B7 wording tension (logic
  AST-identical, docstring extended and separately declared).

**RULED BY ME, record in ledger, no action:**
- (nit 4) `INSTRUMENTATION` mutable global: ACCEPTED as the chartered
  counter substrate and DECLARED EXEMPT from the freeze threat model
  (test-scaffolding surface; `record` defaults False; two attr ops +
  one branch per construction is the declared cost). This ruling sits
  beside R1(a) as the threat model's second clause.
- (nit 2) the states-bound tightening inside the 3.1 battery was RULED
  in R1(4) as a declared pin change; I record it in FLIP-PINS/LEDGER at
  ceremony — verifier is right that it must not pass silently, and it
  will not.

**CEREMONY CARRIES (mine):** (nit 8) the pre-existing `[a-C]`
nocasematch bracket-range family (220 cells, byte-identical both SHAs,
verifier-attributed) → LEDGER Part D successor row. (nit 5) dispatch
duplication (legacy free functions carry verbatim quirk-route copies) →
successor cleanup row. (nit 6) the match-at-position-0 constant-factor
cost (argument-evaluation order builds the spanner before the pre-test)
→ recorded as a declared constant-factor cost + successor row; do NOT
fix it now, post-PASS production churn is not worth a 3× constant.
(nits 3, 10, 16) no action — the mutation replays round 2 already ran
cover nit 3's ask; labeled-historical mentions and the archival exhibit
stand.

After your micro commit + ledger edits: declare the FINAL tip. Ceremony
(evidence rescue, FLIP-PINS/LEDGER closures, version bump, attestation
gate, PR, merge, tag) is mine from there.

## R11 — Micro-commit declaration accepted; prover adaptation sanctioned (2026-08-02)

1. The declared micro commit matches R10 — LAND (you already have the
   grant from R10; this note is the record that the declaration was
   reviewed).
2. The equivalence-prover adaptation (arm reads `_seq_nullable` where
   the tree provides it, `Sequence.nullable` where it doesn't) is
   SANCTIONED and must be recorded in the ledger as an instrument
   change with the fake-disagreement rationale — a retired name
   masquerading as a semantic break is exactly the failure the
   both-arms contract exists to prevent. Good catch made BEFORE the
   run rather than diagnosed after.
3. Your !(a)b concession is noted for the record with credit: the
   scan-relation quadratic was the verifiers' better-founded half, and
   F3 carrying named relations + both figure sets is the honest form.
4. After ledger edits: declare the FINAL tip with the standard
   accounting. Ceremony is mine from there; you hold at the tip.
