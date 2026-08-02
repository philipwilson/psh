# INTEGRATOR INBOX — slot 3.1 (dev-3-1)

Rulings and messages from the integrator land here, numbered R0, R1, R2, …
This file is AUTHORITATIVE over the message channel (the channel drops
turns — memory: agent-message dead-drop). Protocol:

- Read this file at the START of every turn, before anything else, AND
  again immediately BEFORE every SendMessage you send (R4-C).
- ACK each new ruling by number in your next SendMessage.
- If a SendMessage from me references a ruling number you cannot see here,
  say so immediately — do not guess at its content.
- Your durable record is the slot ledger
  (`tmp/remediation-ledgers/3.1.md` in your worktree). Write it as you go;
  assume your transcript can be lost at any time.

---

## R0 — slot open (2026-08-01)

Brief: `tmp/remediation-ledgers/briefs/3.1.md` (in your worktree; identical
copy held by the integrator). Base = origin/main 29456fdc (v0.762.0),
branch `fix/remediation-3-1` checked out in `/Users/pwilson/src/psh-r3-1`.

Standing reminders, non-negotiable:
- STAGE-GATE: Phase A report BEFORE any implementation. WAIT for my GO and
  the KNOWN_DIVERGENCES ruling.
- A9: semantics only. No all-start rewrite, no cache freeze, no perf work —
  that is slot 3.2. Declare any incidental complexity change.
- Oracle = PATH bash `/opt/homebrew/bin/bash` 5.2.26. Never `/bin/bash`.
- ONE heavy run machine-wide; request GO before every full gate or
  compare-bash run; `pgrep -f pytest` first.
- Never touch `psh/version.py`, `CHANGELOG.md`, `README.md`,
  `ARCHITECTURE.md`, `docs/reviews/README.md`, `FLIP-PINS.md`, `LEDGER.md`.
  Never push/PR/merge/tag.
- Red-on-base is DEMONSTRATED red: run the pin at base, record the
  transcript in the ledger, then green at tip.

---

## R1 — Phase A verdict: GO (2026-08-02)

Independent spot-check by the integrator BEFORE this ruling: 12-cell battery
(H7a/b/c, M1 `*!(a)` vs "", M2 `@(*!(a))` enclosure flip, M3/M4 `*?(a)`
group-skip, L1 `!("a")` quoted-alt, K1 q4_sub1, K2 `${v/%!(a)/Z}`, R1
`${v##*!(a)}`, G1 glob fixture) run against PATH bash 5.2.26 --norc and base
psh at 29456fdc (integrator checkout = base SHA, discriminator = repo root):
**12/12 agree with your report**, both oracles' readings and every claimed
psh divergence. Also verified: extglob-off honored identically inside `[[`
by BOTH shells (off_neg=0/off_at=0 both) — your "not a divergence axis for
[[" conclusion stands; `test_new_fullmatch_agrees_with_regex_converter_on_nonneg`
exists at tests/unit/expansion/test_pattern_engine_matcher.py:139.

The 65,625-cell / 0-mismatch model claim is ACCEPTED FOR PHASE B on the
strength of the spot check; expect round-1 verifiers to re-run your corpus
generator and model against live bash independently — the ledger must make
that replayable (exact generator invocation + corpus version + one-command
repro).

**PHASE B: GO**, under R2–R4 below. Design accepted as proposed in A10:
compile-time flag (wildcard-run∘group adjacency + per-node enclosed bit);
non-flagged patterns byte-for-byte on today's paths; flagged patterns get
the additive iterative evaluator of the MEASURED model. A9 declaration
accepted: per-k evaluation cost for flagged patterns MEASURED and recorded
in Phase B; no cache/mutability changes; matching_starts quadratic untouched
(your 3.2 baseline numbers go in the ledger). Battery runtime budget <20s
accepted — measure and report at tip. State-count guard: deterministic, and
its failure mode must name the pattern (not just a number).

## R2 — KNOWN_DIVERGENCES ruling: CLOSE ALL FOUR (2026-08-02)

Implement the measured consumer-layer semantics (i)–(iii), respecting (iv)
as measured, at the parameter_expansion.py seam. Conditions, all binding:

(a) Each mechanism lands with its OWN corpus-pinned cells, red-on-base where
    psh diverges today (my K2 probe is one: base aZ → tip a; your ledger
    pins the full set).
(b) The `_neg` special-case deletion runs the DELETED-DECIDER RULE: census
    its input space, prove the replacement re-decides every case
    (sibling-table + created-shape checks included).
(c) The KNOWN_DIVERGENCES set EMPTIES and
    `test_known_divergences_are_still_divergent` retires WITH it. The four
    keys join the equality lock. The retirement is a certified post-state
    row, and the replacing equality rows are proven COLLECTED (the 2.6
    `collected` kind — a commit-content row is blind to de-collection).
(d) The comment block teaching "not derivable from the match extent"
    (test file lines ~93–102) is swept; a post-state row asserts the stale
    rationale is ABSENT tree-wide and the new mechanism teaching is present.
(e) The newly measured same-family empty-subject cells join the battery;
    the battery's residual structure is EMPTY of these keys at tip.

FLIP-PINS row closure is MINE at ceremony — you report, you do not edit
FLIP-PINS.md.

## R3 — Declared item 1 (regex-oracle agreement narrowing): APPROVED (2026-08-02)

Conditions:
(a) The narrowing predicate IS the compile-time flag — the same decider,
    imported and queried; never a re-derived textual twin (NAME-VS-BODY).
(b) The test docstring states WHY (the regex model cannot express bash's
    star∘group composition) and names the bash-corpus battery as the
    covering oracle for the excluded shapes.
(c) A cert row records the excluded-cell COUNT derived from the producing
    script (never hand-tallied) and asserts coverage transfer: every
    excluded shape class appears in the battery.
(d) The Q3-permanent regex oracle itself is UNTOUCHED — treat as
    must-not-flip.

## R4 — Declared item 2 (lexer quoted-chars-in-extglob-group): SUCCESSOR, no scope extension (2026-08-02)

Correct stop-and-report — thank you for not touching it. Ruling rationale:
lexer extglob tokenization sits in the 2.3 lexer word-extent successor
neighborhood (r18 family); lexer changes carry their own blast radius and
this slot's diff stays engine-pure per A9 discipline. Requirements:

(a) Carry `!("a")`, `!("*")`, `${v/*!("a")/Z}` (and any family you found) in
    the battery's successor-visible residual structure, pinned in the
    DIVERGENT direction (a fix is a visible flip). Where compile_protected
    is CORRECT engine-level (as you verified in-process), add engine-level
    agreement rows so the record localizes the defect to the lexer seam.
(b) Ledger section with the token dump; at ceremony I add the LEDGER
    successor row + FLIP-PINS successor entry.
(c) If the lexer defect contaminates any end-to-end battery row you need
    green, route that row engine-level and record the reason — NEVER weaken
    a row to make it pass.

Standing R0 reminders unchanged: heavy runs need per-run GO; ONE machine-wide.

---

## R5 — Heavy-run GO: gate then compare-bash, sequential (2026-08-02)

`pgrep -f pytest` verified CLEAR on the integrator side; no other heavy run
machine-wide. GO for BOTH runs, sequential, each as ONE foreground call:

1. `python -u run_tests.py --parallel > tmp/gate-1.txt 2>&1` (timeout
   600000). Report full figures vs base 22,820 / 1,590 / 10 — growth from
   your new tests EXPECTED; report the delta and reconcile it against your
   ledger's new-test count (derived, not hand-tallied).
2. `python -m pytest tests/behavioral --compare-bash -n auto -q` — base
   composition 2,986 / 26. Composition changes only if declared+pinned;
   if you added no golden/behavioral rows, expect EXACT.

Never end a turn with a run in flight; a timed-out call is MOVED TO
BACKGROUND, not stopped — poll to completion before reporting.

Three declared items NOTED, accepted for now, and flagged for round-1
verifier scrutiny (no action needed unless the gate disagrees):
(a) af236478 recursion-contract pin made limit-relative + the 40k
    activation fact — the verify round will replay the pin's red/green
    on both sides and check the pin still binds a CONTRACT, not just
    "whatever the limit is".
(b) The user-guide `[[` extglob correction — the claims meta-test runs in
    the gate; if it demands a CLAIM_TESTS mapping for your new example,
    add the mapped conformance row rather than weakening the text.
(c) The two flipped characterization rows in
    test_substitution_scan_unified.py — sanctioned under R2(a) given
    their docstrings pinned OLD-psh-behavior-as-characterization; the
    verify round will read those docstrings at base and confirm the
    sanction reading.

After both runs green: declare final tip (MECHANICAL TIP RULE in force
from that moment) and send the completion report with per-commit delta
accounting. I then launch verification round 1.

---

## R6 — Gate rerun GO; run 2 follows on green (2026-08-02)

pgrep verified clear my side. GO for the gate RERUN as one foreground call.
On green, proceed DIRECTLY to run 2 (compare-bash) under the R5 sequence —
no fresh grant needed between them this time; the pair is granted as one
sequence again.

The B7 false-red diagnosis is ACCEPTED as presented: the stale
assertion-rewrite cache mechanism (byte-length-neutral mutation + revert in
the same mtime second → mtime+size .pyc validation serves the mutated
compile) is a real and known pitfall, and your isolation steps (serial
repro, byte-identical fresh-file pass, git diff clean, cache removal cures)
are the right instrument chain. Expect the rerun to show 22,832 passed /
1,590 / 10 if the false red was the only delta — reconcile whatever appears.

The harness lesson is BANKED campaign-wide (I will carry it into the
mutation-protocol briefs): after reverting a same-length mutation, drop the
target's __pycache__ entries — same-second same-size reverts are invisible
to mtime+size validation. Add it to your ledger's lessons section if not
already there.

Round-1 verifier note (for the record, not for you to act on): the M5
mutation cycle itself must re-run its mutations with cache hygiene to
confirm all mutation classes still fail for their own reasons post-fix.

---

## R7 — ROUND 1 VERDICT: BOUNCE — 3 blockers, 14 nits (2026-08-02)

Task verdicts: diffAudit FAIL; resurrection / ledgerCheck / reprobe all
PASS-WITH-NITS (your R5-flagged items — recursion-pin classification,
flipped-row sanction readings, mutation replay w/ cache hygiene — all
verified clean). The bounce is diffAudit's: it built its own independent
corpora (61,600 cells/consumer alphabet {a,b} + 43,065 disjoint {a,c})
and found the blind spot. I REPLAYED the decisive cells myself at
bash/base/tip before this ruling — all confirmed:

**B-1 (BLOCKER): behavior REGRESSION, base-correct → tip-wrong, all five
consumers.** `_BashMatcher`'s end-of-subject negation shortcut
(pattern_engine.py:782-785: `if (t2 is Extglob and op=='!' and n == se):
return not enclosed` — "# rest ignored") fires and IGNORES every
remaining pattern element; bash does not. My replay: `[[ aa == *a*!(a)?a ]]`
bash 1 / base 1 / TIP 0; `${v/*a*!(a)?a/Z}` on aa: bash aa / base aa /
TIP Z. Verifier census: ~1,034 base-OK→tip-WRONG cells in [[, 1,062 in
substitution, + glob/case/removal. ROOT CAUSE: your corpus `_PRE`
context list ["","*","?","a","*a","a*","**","*?"] never generates
star-literal-star (`*a*`) contexts, and post-negation continuations
after such contexts — the model was never measured there, so your
battery is green while wrong.

**B-2 (BLOCKER): the chartered class is NOT closed and the headline
claim is falsified.** `*<literal>*!(...)` still diverges at tip exactly
as at base: my replay `[[ aa == *a*!(a) ]]` bash 1 / base 0 / TIP 0;
`${v##*a*!(a)}` on aa: bash a / base "" / TIP "". Verifier: 53
cells/consumer over 26 patterns base==tip≠bash; removal consumer
1,473/61,600 ≠ bash at tip (down from 8,228 — improved, not closed).
Meanwhile ledger/docstrings/battery assert "0 mismatches" as if
universal. Claims must be SCOPED to the corpus that backs them —
honest-claim discipline.

**B-3 (BLOCKER): A9 complexity declaration FALSE as written; undeclared
asymptotic regression.** Ledger B5 says non-flagged paths are
byte-identical — true of the ENGINE, false of the SLOT: the consumer
wrapper (`_sub_machinery`/`_any_match`) wraps every unanchored
substitution in `*...*`, which makes ANY extglob-headed pattern
quirk-flagged, running the O(n²) _BashMatcher per operation and cubic
under O(n) matches. My replay: `${v//+([[:space:]])/-}` end-to-end at
1,200 chars: base 0.47s / TIP 2.76s (verifier: ×4 per doubling vs base
×2; 12.5ms → 18,370ms in-process at n=1600). Mitigation recorded: tip
still beats live bash on the idiom (bash is itself cubic). The fault is
the DECLARATION, and A9 exists precisely for this.

### Required fixes (Phase C; mechanical tip rule — declare every commit)

B-1/B-2 share one root: the model is UNMEASURED in star-literal-star and
post-negation-continuation contexts.
1. WIDEN the corpus grammar: PRE contexts must include `*<lit>*`,
   multi-run shapes, and richer literal spacing; POST contexts must
   include continuations after the negation group (`?a`, literals,
   groups). Keep it deterministic + derived.
2. RE-DERIVE the rule in those contexts against live bash AND re-read
   the sm_loop.c source for the TRUE conditioning of the end-of-subject
   negation shortcut (it is conditioned on more than `not enclosed` —
   bring the mechanism, not a patch that fits the cells).
3. Fix `_BashMatcher`; re-verify 0 mismatches on the WIDENED corpus
   union; the PERMANENT battery grammar gains the widened contexts (the
   instrument must cover its own former blind spot).
4. SCOPE every "exact/0 mismatches" claim (docstrings, CLAUDE.md,
   ledger) to the corpus it covers, and reconcile the 65,625 vs 64,575
   count contradiction (N4/N12) with DERIVED counts everywhere.
5. Round 2 will attack with FRESH independent corpora again (different
   alphabets/contexts) — assume the grammar question is adversarial.

B-3:
6. Correct ledger B5 with a measurement table (yours or the verifier's,
   attributed); the A9 declaration states the consumer-layer flagging
   consequence plainly.
7. Wrapper memoization (nit N3) PERMITTED — semantics-neutral, measure
   the gain. A broader fast-path is permitted ONLY if corpus-proven
   equivalent on its eligible class; otherwise declare and hand off.
8. Add an explicit 3.2-handoff row: restoring linear substitution
   scanning under the bash-mechanics semantics is a NAMED 3.2 exit
   criterion (with your measured baselines).

### Nit dispositions (14)
- FIX IN-SLOT: N1 matching_spans production-dead (census + docstring +
  CLAUDE.md; my ruling: labelled test-only relation oracle per the
  extglob_to_regex PERMANENT-ORACLE precedent, or delete with census —
  bring a recommendation); N2/N5 _contains_negation same treatment; N3
  wrapper memo; N8 user-guide 17_differences_from_bash.md:59-60 stale
  "supported once extglob..." sentence (make the two guide pages agree);
  N9 CLAUDE.md:284 span_at/matching_spans stale teaching; N13 ADD the
  case-consumer lexer-family rows (`case a in !("a"))` bash N / psh M,
  pre-existing) to RESIDUAL_DIVERGENCES divergent-direction; N14 stale
  CLAUDE.md recursion sentence (limit-relative now); N4/N12 count
  reconciliation (with B-2 item 4).
- LEDGER ERRATA ROW: N10 (C6 recorded grep spelling vs recorded output
  mutually inconsistent — record the actual spelling run).
- LEDGER NOTE: N7 (battery not collectable at base by design — name the
  Phase A harness as the red-on-base instrument; three-point
  replayability lives there).
- RATIFIED BY ME: N11 (the star-run/group recursion dimension — declared
  in your completion report, limit-relative pin verified; ratification
  contingent on N14).
- MINE AT CEREMONY: N6 (FLIP-PINS names the retired test's OLD name —
  rename recorded when I close the row).

Gate + compare-bash re-run after fixes under a fresh GO. Your battery,
gate, and my 12-cell spot check all shared the blind spot — the
independent-corpus rule exists for exactly this; no shame in the bounce,
the record is what matters. Fix well.

---

## R8 — Commits 7+8 APPROVED to land as declared; sequence GO pre-granted (2026-08-02)

Both declared commits are APPROVED exactly as scoped in your declaration.
Any mid-landing growth (a file added, a hunk beyond the declared scope)
stops and re-declares per DECLARATION SCOPE. Notes, binding:

1. The glibc star-jump mechanism account (leftmost-commit of inter-star
   segments; committed entry position feeds the negation special and the
   ?(/*( branches) is accepted as the R7-item-2 "mechanism, not
   cell-fitting" answer — WITH the expectation that round 2 verifiers
   will hunt fresh contexts again (third alphabet, longer subjects,
   segment shapes your grammar-v2 still lacks). The union figure
   0/437,811 is noted; keep the one-command replay current.
2. N3 memo condition ADDED: the lru(512) wrapper cache is a NEW cache of
   CompiledPattern objects. MEDIUM-6 (writable cached pattern ASTs) is
   3.2's charter — your 3.2 handoff row must NAME this cache as one of
   the caches 3.2's freeze must cover. No other cache/mutability change.
3. C-3 disclosure acknowledged and CREDITED — the wipe/recovery account
   with two script bugs found and the hardened cp-based replay is
   exactly what full disclosure looks like. It becomes a round-2
   verifier target (recovery completeness + the hardened script's
   restore actually restores); your idempotence-check instruments must
   be runnable by them from a detached worktree.
4. N1 KEEP recommendation ACCEPTED: matching_spans = labelled permanent
   test-pinned relation oracle (extglob_to_regex precedent).
5. SEQUENCE GO PRE-GRANTED: after both commits land and your local
   post-state checks pass, run the R6-form sequence (gate as one
   foreground call, then compare-bash) WITHOUT a further round-trip,
   PRECONDITION: pgrep -f pytest clear at start (record the check).
   Report both figures with the delta DERIVED and reconciled (battery
   12→15 and any other test-count changes named).

After the green sequence: declare the new final tip; round 2 launches on
my side.

---

## R9 — Round 2 RUNNING; hold tip b49b8e9c (2026-08-02)

Crossings fully resolved: your sequence results + tip declaration
(d578e70c) were received and acted on — round 2 launched BEFORE your
latest crossing-resolution message arrived (wf_278fd24b-a62, 4 agents,
own detached worktrees; scope: three-point anchor replays, fresh
third-alphabet corpus beyond grammar-v2, star-jump implementation audit,
B-3 discharge re-measure, recovery completeness incl. your hardened
replay script, all 14 nit discharges, diff scope). Your C-10 self-log of
the R4-C slip is noted and closes the matter. N3/N1 confirmations
accepted. HOLD b49b8e9c: no commits of any kind without a declared
message first; write any wait-time observations into the ledger, not the
tree.

---

## R10 — ROUND 2 VERDICT: BOUNCE — 2 blockers, 15 nits — WITH AN INTEGRATOR FAULT TALLIED (2026-08-02)

Verdicts: diffAudit FAIL; resurrection/ledgerCheck/reprobe PASS-WITH-NITS.
The GOOD news first, on the record: your star-jump fix survived a massive
independent assault — the verifier's own disjoint grammars (714,714 `[[`
cells, 725,625 flag-boundary, 336,000 removal+substitution, 27,125 case,
1,350 real-fixture pathname, 12,750 nocasematch, 5,600 extglob-off,
28,000 len-5/6 subjects, 7,500 `&`-template, 112 UTF-8, plus a 60,000-
iteration fuzz with 0 internal exceptions) found ZERO mismatches outside
one class. The bounce is narrow. I replayed both blockers before ruling.

**B2-1 (BLOCKER): the wrap-guard docstring states a FALSE bash mechanism,
and the class it mis-states is unmeasured and unpinned.** Your docstring
(parameter_expansion.py:177-183) claims "an escaped `\*` tail still gets
the append". Bash's outer guard is a RAW-CHAR test on both ends: when the
pattern head is a raw `*`, bash builds NO wrapper at all, so the pre-test
is unwrapped and the substitution is suppressed. My replay: `v='a*b';
"${v/*\*/Z}"` → bash a*b / base Zb / TIP Zb (pre-existing divergence, not
a regression; control `"${v/\*/Z}"` → aZb everywhere). Verifier probe: 45
of 1,520 escaped-metachar cells still divergent at tip (13 fixed, 0
regressions), pattern shapes `*...\*` family. Your corpora contain NO
backslash anywhere — the named nuance has zero coverage. Same fault class
as round-1 B-2: a claim not scoped to the corpus that backs it.
REQUIRED: (1) measure bash's REAL guard from subst.c (raw-char both-ends
test — mechanism, not my sketch, and not cell-fitting); (2) implement it
— the 45 cells are IN CHARTER (substitution consumer mechanics, your R2
work); survivors, if any, go to RESIDUAL_DIVERGENCES divergent-direction
with measured reasons; (3) the battery grammar gains a BACKSLASH/
escaped-metachar axis — in substitution AND `[[`/case/removal contexts
(the axis, not just the failing cells); (4) fixed cells get red-on-base
pins; (5) the docstring states the measured rule.

**B2-2 (BLOCKER): the B-3 mitigation sentence is FALSE for the shape it
names — and the false generalization is MINE.** Ledger C-4 carries
"(R7, attributed): tip still beats live bash on the idiom (bash itself is
cubic there)". My replay on N=1,600 CONSECUTIVE spaces:
bash 0.011s (FLAT — verifier: flat to N=12,800) / base 0.46s / tip 3.44s
(~×3.6 per doubling). The mitigation holds only for the word-spaced
many-matches shape ('x '-repeated — which is what MY R7 probe measured;
bash 37.9s there). I generalized a shape-specific measurement to "the
idiom"; you carried it attributed, as you should. **INTEGRATOR FAULT
TALLIED (3.1 fault #1, R21-C class: the cells were measured, the chain
between them was not — subject SHAPE is an axis).** The record stays
honest in both directions.
REQUIRED: (1) ledger ERRATA row replacing the sentence with a
shape-scoped table (both shapes × bash/base/tip, attributed, noting the
fault is the integrator's); (2) B-3's declaration-only discharge is
RE-OPENED at the measured magnitude (~28× base at N=3,200 on a common
idiom, bash flat). Path A (PREFERRED, permitted under R7-item-7):
an eligibility-gated fast-path — if the linear DP path and _BashMatcher
agree on every corpus-union cell whose groups are ALL non-nullable and
non-negation (predicate DERIVED from compiled-pattern node properties,
never textual), dispatch eligible patterns to the DP path. Bring the
equivalence measurement over the full union restricted to eligible
cells (0 disagreements required) + an eligibility-boundary battery test.
`+([[:space:]])` is eligible → the common idiom returns to linear,
in-slot, without an algorithm rewrite. Path B (if equivalence FAILS,
measured): perf-envelope pin + the 3.2 handoff row ESCALATED (linear
substitution restoration = named 3.2 MUST; I will note the temporary
regression at ceremony). Measure first; the choice follows the evidence.
(3) Fold in verifier NIT-9 properly (the DELETED-DECIDER rule): `_neg`
decided "contains !() at any depth"; your `end_eligible` decides
head-shape — CENSUS the disagreement space of the two deciders against
bash and record which decider bash agrees with, everywhere measured.

### Nit dispositions (15)
- FIX IN-SLOT: N1 (B2b is green at ALL FOUR points — label it a CONTROL
  row and fix the "all fixed by the star-jump port" docstring sentence
  that sweeps it in); N2+N6+N14 (complete the matching_spans sweep:
  module docstring four-relations sentence + CLAUDE.md line 34 must
  agree with the labels the diff itself added); N3 (derived, SCOPED
  counts everywhere — `_seq_bash_quirk` docstring still cites bare
  65,625); N7 (test_substitution_scan_unified.py filename names the
  deleted mechanism — rename WITH collected-proof per the 2.6
  blind-rename lesson, or justify keeping); N8 (Extglob.enclosed is an
  unguarded semantic seam for hand-built ASTs — minimal invariant guard
  or pinned constructor contract; also name it in the 3.2 handoff row,
  it is exactly what 3.2's freeze must respect).
- LEDGER ROWS: N10 (record the H7-unpinned-at-base re-verification —
  the verifier's grep, attributed); N11 (write the Linux reasoning down
  — portable alphabets, docstring-only extglob.py, oracle-drift arms,
  locale rows — it was done, never recorded); N12 (your NEXT final-tip
  declaration carries the formal discharge-audit + bounced-rows-replay
  TOTALS the binding rules require).
- NOTED, no action: N4 (clean negatives on record), N13 (your C-10
  self-log — counted), N15 (commit-message wording — messages are
  immutable post-land; ledger is precise and that suffices).
- MINE AT CEREMONY: N5 (FLIP-PINS + plan doc name the deleted constant
  and retired test — closure records the renames).

Round 3 will be NARROW: the escaped-metachar class three-point, the
wrap-guard mechanism vs subst.c, the fast-path equivalence (if Path A),
the sweep-completeness greps, and the totals. Declare commits before
landing; sequence GO pre-granted on the R8 pattern (pgrep-clear
precondition, figures derived+reconciled, new tip declared).

---

## R11 — Commits 9+10 APPROVED as declared (2026-08-02)

Both commits approved to land exactly as declared; growth re-declares.
Notes, binding:

1. B2-1: the string-built wrapper + paren-pun account must be TAUGHT
   where it lives (docstring states the measured raw-char rule incl.
   the pun; round 3 checks teaching-vs-code against subst.c). The
   corpus4 7th cell (`${v/%(a)/Z}` on "(a)") and your two
   corrected-to-measured control expectations are exactly the right
   record — keep both visible in the ledger.
2. B2-2: the VOID-proof disclosure is CREDITED — an equivalence proof
   whose forcing was laundered by the lru cache, caught because M6 did
   NOT fire, is the mutation-discipline working as designed. M6 joins
   the permanent replay classes (prover-proving). Round 3 re-runs the
   equivalence proof and VERIFIES THE FORCING (cache-clear present and
   effective — a proof that cannot fail is not a proof).
3. Checkout-slip #2 acknowledged; the hardened posture is now BINDING
   for the remainder of the slot: NO git checkout of tracked files in
   a tree holding uncommitted work, for any reason, manual checks
   included — restores go through your cp/patch instruments only. Two
   slips in one slot is a pattern, not bad luck; the third is a
   stop-and-talk signal per the R13-D precedent, set by me this time.
4. Perf numbers (consec 12.8s→0.007s, wordsp 17.5s→0.013s at N=3200)
   are BETTER than base absolutes — state the measurement basis
   (in-process vs end-to-end, startup included or not) in the D-2
   table so the comparison is apples-to-apples; round 3 re-measures.
5. Sequence remains pre-granted (pgrep precondition recorded); expected
   22,838/1,590/10 — reconcile whatever appears; compare-bash EXACT.
   Tip declaration carries the N12 formal totals (discharge audit over
   every ledger row + every bounced row replayed, both totals).

On tip declaration: round 3 launches, NARROW as promised (escaped-axis
three-point, wrap-guard vs subst.c teaching-vs-code, equivalence-proof
forcing, perf basis, sweep greps, totals, recovery-completeness #2).

---

## R12 — Session-limit stall: verified state + resume point (2026-08-02)

Your session hit its usage limit (~03:08 UTC; reset 4:10am London). I
verified the stall state from my side so you can resume without
re-deriving it:
- Both R11-approved commits LANDED as declared: a55651e0 (commit 9,
  B2-1 raw-char guard + Path-A fast path) and 43df27ac (commit 10, N7
  rename). Branch tip = 43df27ac; your worktree is CLEAN.
- NO heavy run was in flight (pgrep clear) — nothing orphaned.
- Not yet done: the pre-granted sequence (gate + compare-bash) and the
  tip declaration with the N12 formal totals.

RESUME POINT: run the sequence (pgrep precondition recorded), report
figures (expected 22,838/1,590/10, reconcile whatever appears;
compare-bash EXACT), then declare the round-3 final tip WITH the
discharge-audit + bounced-rows-replay totals. Round 3 launches on that
declaration.

---

## R13 — Provenance accepted; round 3 running; HOLD (2026-08-02)

(Landed AFTER the channel message that cited it — my slip, flagged by
you correctly per protocol: a ruling number without a file entry is
exactly the drift the dead-drop exists to prevent. Integrator procedural
note logged; content below is identical to the channel text, nothing
new.)

1. Provenance correction ACCEPTED with my own verification: tip
   43df27ac committed 2026-08-02 03:56:48+01:00; tmp/gate-4.txt 04:05
   and tmp/compare-bash-3.txt 04:06 (both post-commit, clean tree);
   pgrep precondition recorded pre-run. NO re-run required — R5/R6
   crossing posture applies. My R12 "not yet done: the sequence" was
   wrong; your evidence corrected it.
2. FIGURES ACCEPTED: gate 22,838/1,590/10 (derived chain
   22,820+12+3+3); compare-bash 2,986/26 EXACT. D-8 formal totals
   noted; fault register noted (integrator 1 / dev 4, all dev faults
   self-caught).
3. ROUND 3 RUNNING against 43df27ac (wf_1b19aad6-f56): escaped-axis
   three-point + fresh escaped rows beyond corpus4; wrap-guard
   teaching-vs-code vs live bash; fast-path forcing verified by
   BREAKING the prover + M6 own-reason; shape-scoped perf re-measure
   both shapes; deleted-decider quadrant re-derivation;
   sweep-completeness greps; recovery-completeness #2 via your patch
   instrument (byte-exact apply check); perimeter + full anchor
   re-check + 10 spot rows from round-2's grammars.
4. HOLD 43df27ac: no commits without a prior declared message; cp/patch
   restore posture binding. If clean → straight to ceremony.

---

## R14 — ROUND 3 VERDICT: PASS, 0 BLOCKERS, 14 NITS — acceptance path (2026-08-02)

All four tasks PASS-WITH-NITS. The fix survived: escaped-axis three-point
clean, teaching-vs-code clean, prover forcing verified real BY BREAKING
IT, perf re-measured in-range both shapes, deleted-decider quadrants
re-derived, recovery byte-exact via your patch instrument, perimeter +
anchors hold, 10 round-2 grammar spot rows green.

TWO CONFIRMATIONS THE VERIFIERS ASKED OF ME (both confirmed, no action):
(a) Scope/A9 coverage of the consumer layer + lru(512) + fast_ok
    dispatch: CONFIRMED covered by the ruling chain — R2 ordered the
    consumer-layer implementation at that seam; R7-item-7 permitted the
    memo; R10 ordered Path A with the equivalence proof; R8/R11 named
    the cache in the 3.2 handoff. The ceremony LEDGER row will state
    this explicitly (deliberate, ruled, evidence-anchored).
(b) "No second matcher" vs the literal _BashMatcher class: CONFIRMED
    covered by R1's accepted A10 design — the prohibition targets
    PER-CONSUMER forks; _BashMatcher is a per-pattern-class evaluator
    inside the one engine, all consumers via the same compiled object.
    Ceremony row states it; 3.2 handoff notes the evaluators as
    unification candidates.

FINAL CLEANUP — ONE declared commit (11), then one gate sequence, then
ceremony. Commit 11 contents (all small, all verifier-anchored):
1. guide-17 line ~71: scope the blanket "extglob must be enabled before
   the line is parsed" sentence to globbing/case (the verifier verified
   your new 59-62 claim correct with 90 cells; the two paragraphs must
   agree).
2. extglob.py:255: mark `parameter_expansion._neg` RETIRED in the
   docstring (branch's only surviving deleted-symbol reference).
3. Battery hygiene: (a) the `test_fast_path_eligibility_boundary`
   Shell()/run_command permanently raises the process recursion limit
   to 40k with no teardown, and `test_bash_matcher_recursion_contract`
   READS the limit — invisible order coupling in your own new battery;
   snapshot/restore the limit around the offending test (or isolate).
   (b) Per-row labels: B1 = THREE-POINT regression pin (green base,
   red 7bec085c, green tip — say so), subc_jump/case_jump2 labelled
   control or three-point per their true history; no row rides the
   blanket sentence. (c) regex-oracle docstring gains the DERIVED
   narrowing counts (6000 → 1687 neg-excl → 689 non-extglob → 267
   quirk-excl → 3357 kept).
4. NEW residual row: the operand-extent divergence the verifier found —
   unquoted `/` inside an extglob group in `${v/pat/repl}`: bash
   terminates the pattern at the first `/`, psh balances parens
   (`v=''; "${v/*!(/)/Z}"` → bash `)/Z` / psh ``; PRE-EXISTING at base,
   3/3,888 cells). Pin it divergent-direction in RESIDUAL_DIVERGENCES
   (operand-extent family, sibling of the R4 lexer-seam rows); I add
   the FLIP-PINS successor entry at ceremony.
LEDGER errata/additions (no commit): A4 "55-cell" → the DERIVED 40
(corpus1.py prints 40; counts-derived rule); "union 437,811" wording →
row SUM 437,811 / distinct union 427,586 (+558 backslash = 428,144,
reconciles exactly); matching_starts A9 wording → "per-start-position
evaluation SHAPE preserved; routing hunk (8713f7e0) required for
suffix-removal consumers, verified rounds 1-2"; 3.2 handoff table gains
the verifier's FULL_MATCH baselines (`**(a)b` on 'a'*N: base ~x4/doubling,
tip ~x8/doubling, 85x at N=400 — script-visible, flagged as a 3.2
opener priority) + matching_ends `*!(a)` 17x@N=200, attributed.
Instrument cleanups (no commit): replay_mutations.sh header five→six
(M1-M6); corpus5_equiv.py:65 dead assignment + stray comment dropped.
NOT yours: golden_cases.yaml:10218 stale comment (must-not-flip file —
I land the comment-only fix at ceremony, declared in the ceremony
record).

SEQUENCE PRE-GRANTED for after commit 11 lands (pgrep precondition
recorded; expect 22,838±0 unless the battery labels change collection —
derive and reconcile; compare-bash EXACT). Then declare the CEREMONY
TIP with updated totals and I take it from there: evidence rescue,
version v0.763.0, CHANGELOG/README/ARCHITECTURE, FLIP-PINS + LEDGER
closures (incl. the rename records), nightly-status update, attestation
gate, PR, merge, tag verify, smoke.

---

## R15 — Commit 11 APPROVED as declared (2026-08-02)

Approved exactly as declared; growth re-declares. Two touches noted with
credit: the A4 discrepancy resolved as STATE-DEPENDENT with the formula
recorded (40 stride + min(15, divergent) — 55 at base, 40 clean; better
than either bare number), and the narrowing chain RE-DERIVED before
pinning. opx_slash as a DATA row (no collection delta) accepted —
expected gate figure 22,838/1,590/10 EXACT; any surprise reconciles.
Sequence pre-granted per R14. After green: declare the CEREMONY TIP with
updated D-8 totals (rounds 1-3 bounced-rows replay included). I take it
from there.
