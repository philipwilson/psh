# INTEGRATOR-INBOX — durable rulings dead-drop for slot 2.4 (poll this file)

## ADDENDUM 6 (2026-07-31) — ROUND 9 VERDICT: BOUNCE, ONE BLOCKER — RULINGS R10-A..F — CURRENT

Evidence: VERIFY-ROUND9-issues.md (+ -full.txt). Tip 71e83c35 DISSOLVED.
The fifth axis instance — and your own command_sub.py comment was the
witness. ACK by letter.

**R10-A — FIX: complete the pre-sever rule at the CMDSUB creator.** Under
`shopt -s inherit_errexit` (and `set -o posix`), a cmdsub child DOES
inherit errexit — the exception your own command_sub.py comment documents
(`reset_errexit=not (opts.get('inherit_errexit') or opts.get('posix'))`)
— so the depth IS observable there, and the severed member's cmdsub child
loses the pre-sever suppression: `set -e; shopt -s inherit_errexit;
{ true | echo "x=$(false; echo A)"; } || …` → bash/base x=A, tip x=
(empty), both parsers, all channels. Regression vs base+bash (arrived
with the severing machinery at r8, unpinned). Fix = pass the SAME
errexit_suppress_override at command_sub.py's run_child_shell call;
verify the BACKTICK spelling rides the same creator; pins red-on-71e83c35
for both option spellings (inherit_errexit AND posix), plus a
severed-member × inherit_errexit × cmdsub-inside-eval'd-text composition
row. The procsub side under inherit_errexit is already green at your tip
(verifier C4) — pin it if not already.

**R10-B — scope the $- mechanism claim.** The round-9 universal ('the
depth is not observable there at all') is FALSE off the default-options
axis. Correct the ledger R9-A text and the pin docstring to state the
option-axis exception, citing your own command_sub.py comment. Append
the FIFTH instance to the pattern line (round 9 held the OPTION axis
constant).

**R10-C — external-command-body divergence: SUCCESSOR ROW.** The
verifier's t7 probe: `g(){ /usr/bin/false; echo A; }; set -e;
{ true | g; } || …` → bash A / psh GOT rc=1 at base AND tip
(base-identical; the builtin-false twin matches everywhere). The
co-movement census docstring's '0 pre-existing divergences' gets its
domain scoped (BODIES had no external command). Row text for my
ceremony edit.

**R10-D — the seven green-on-base pins: LEDGER TABLE.** Each self-declares
as control/declared-divergence in its docstring; the campaign rule wants
the declaration IN THE LEDGER. Add one table (pin name → class → why
green-on-base is correct for it → citing this ruling). No pin changes.

**R10-E — done by the integrator:** the brief amendment now carries an
R9/R10 clause (bottom of briefs/2.4.md) naming the process_sub.py
machinery AND the cmdsub-creator completion. Cite it beside your R9-D
citation.

**R10-F — closure:** batteries/audit/bounced-rows gain the new rows;
re-gate + compare-bash (GO PRE-GRANTED, pgrep first); declare. This
family is now closed at every creator the tree contains — if you find
another expansion-time fork creator while implementing, STOP-and-report
rather than extending silently.

## ADDENDUM 5 (2026-07-31) — ROUND 8 VERDICT: BOUNCE, ONE BLOCKER — RULINGS R9-A..E — CURRENT

3 PASS-WITH-NITS-equivalent / 1 FAIL, single blocker. Evidence:
VERIFY-ROUND8-issues.md (+ -full.txt) beside this file. Tip 55edb24f
DISSOLVED. The independent 576-row DISJOINT-space hunt found ZERO other
moved-away rows (430 match / 134 moved-to-bash / 12 = the declared
function-frame family) — this is the last content round. ACK by letter.

**R9-A — FIX the member × argument-procsub regression.** `set -e;
{ true | cat <(false; echo A); } || …` → bash A (procsub child keeps the
SUPPRESSED context), base A (matched), tip END (the severed context
leaks into the member's expansion-time procsub fork). Regression from
base+bash parity = fix, per every precedent this slot set. Mechanism
localized by the verifier: pipeline.py#make_execute_fn :248-251 severs,
then the member child's expansion-time procsub fork inherits the severed
context. The fix: expansion-time substitution children of a severed
member inherit the PRE-SEVER depth (deferred + current). REQUIRED WITH
IT, by instrument: WHY did cmdsub-in-member NOT regress (`{ true | echo
"x=$(false; echo A)"; }` → x=A everywhere per the verifier's control)?
Different seeding path, or masked by the shape? Answer it and cover the
cmdsub/backtick twins in the pin family either way. Streamlined
stage-gate: mechanism proposal in the ledger, sent WITH the landing
declaration.

**R9-B — pin the sibling + scope the docstring.** The member ×
REDIRECT-spelling row moved TOWARD bash undeclared (base A, tip END ==
bash) — pin it beside the fix; and the R8-A pin docstring's 'argument
spelling carries in both' universal gets the member-route statement
(post-R9-A it becomes TRUE at that route — say that it was measured
there this time).

**R9-C — PTY corpus gap: successor row + docstring scope.** The
committed interactive module holds the error-kind axis constant
(direct_complete_but_invalid only). The UNTERMINATED direct spelling at
a real terminal diverges BASE-IDENTICALLY (bash reports and returns to
PS1 with the follow-up runnable; psh swallows into continuation and the
follow-up never runs — no crash, no traceback, brief's bounce condition
not met). Successor row (neighbors S2/r18 continuation family; verifier
transcripts v9/h_pty.py) + scope the module docstring's 'REPL SURVIVES
every row' invariant to its stated corpus with the diverging spelling
named.

**R9-D — done by the integrator, cite it:** the brief now carries a
dated ruling-authority amendment (bottom of briefs/2.4.md) recording the
R4→R8 chain that authorizes the errexit machinery — a round-8 verifier
correctly noted the brief alone did not authorize it. Your ledger's
scope-accounting section should cite the amendment.

**R9-E — closure:** batteries/audit/bounced-rows gain the new rows
(member × both procsub spellings, cmdsub/backtick twins); re-gate +
compare-bash (GO PRE-GRANTED, pgrep first); declare with the audit
composition derived. NIT to fold: the Linux-nightly note should add
that the PTY module's BASH-side values ('1','2') are 5.2.26-measured
and the nightly's bash build differs (plan A12) — a version-dependent
PTY value fails the DEFAULT suite there now; note it for the nightly
reader.

## ADDENDUM 4 (2026-07-31) — ROUND 7 VERDICT: BOUNCE, SINGLE BLOCKER — RULINGS R8-A..D — CURRENT

One blocker, record-only; the rest NITs. Evidence: VERIFY-ROUND7-issues.md
(+ -full.txt). Tip 4ea3df9c DISSOLVED. This is the closing round — the
work is small and none of it is production code. ACK by letter.

**R8-A — the false route universal (the blocker).** Your substitution-route
domain statement is FALSE for REDIRECTION-SPELLED procsub: bash runs a
`< <(…)` / `> >(…)` child with errexit EFFECTIVE in a suppressed context
(does NOT carry the suppression in), while the ARGUMENT spelling
(`cat <(…)`, your c4/c5 corpus) genuinely does carry. psh carries in both
spellings — at base AND tip, both parsers (pre-existing, base-identical,
NOT slot-introduced, no production change required or wanted). Required:
(1) strike-and-correct the ledger's route sentence with the spelling
split stated; (2) BOTH-SIDES PIN the redirect-procsub family (read +
write sides, both channels — the verifier's u3/w1 rows are your
template) + a SUCCESSOR ROW for any future fix (procsub child seeding,
adjacent to this slot's machinery, out of charter now); (3) qualify the
`test_background_fork_severing_matches_bash` docstring sentence
('reaches through a COMPOUND body … and through nothing else' — the
redirect-procsub child body is compound and bash does NOT reach through
it; state the spelling split there too).

**R8-B — R7-B sampling width.** The verifier's 334-shape hunt found 72
moved rows; your pin covers 7; ALL 72 land ON bash and inside the
declared families — so this is width, not concealment. Required: commit
the 72-row hunt enumeration as an instrument file (the verifier's
hunt_errexit.py output is in its evidence — reproduce it yourself under
tmp/r24-probes/ rather than citing theirs), reference it from the pin
docstring as the exhaustive record, and widen the pin sample by ~4 rows
covering the named unpinned shapes (command-prefix, assignment-prefix,
one `{ } &`-family spelling, one while-condition source).

**R8-C — both-parser coverage for the new conformance families.** The
~180 new rows pin RD only (the helpers never pass --parser). Required:
durable both-parser coverage for the NEW families at representative
width — your choice of mechanism (parametrize the helpers for the new
tests, or one both-parser sweep test over representative rows), domain
stated in the docstring. The verifier's 380-obs sweep found zero rd/comb
divergence, so this is a pin-record question, not a bug hunt.

**R8-D — small fixes:** the under-qualified pointer `core.py#
_execute_background_list` → `executor/core.py#_execute_background_list`
(the repo has both a psh/core/ package and psh/executor/core.py — this
ambiguity is exactly why the discipline wants the full path); ledger
note for Linux-nightly awareness of the PTY module's loud-at-import
oracle resolution (KEEP the loudness — bash is always present on the
nightly runner; the note is for the successor reading failures).

Then: batteries/audit/bounced-rows extended with the new rows; re-gate +
compare-bash (GO PRE-GRANTED, same form); declare with corrected audit
count and STILL-OPEN discipline. No production changes are authorized in
this round — if you conclude one is needed, STOP-and-report.

## ADDENDUM 3 (2026-07-31) — ROUND 6 VERDICT: BOUNCE — RULINGS R7-A..E — CURRENT

3 FAIL / 1 PASS-WITH-NITS. Tip d64a3294 DISSOLVED. Full evidence:
VERIFY-ROUND6-issues.md (+ -full.txt) beside this file. The behavior
defects now reduce to ONE rule applied non-uniformly; the record class
recurred again. ACK by letter.

**R7-A — THE UNIFIED SEVERING RULE, applied at every route (mandatory).**
Bash's rule, which your own field docstring quotes: -e-ignoring crosses
into COMPOUND bodies and DIRECTLY-INVOKED function bodies only; a SIMPLE
command severs it. You implemented that for pipeline members. The
verifiers found the two places it also applies: (1) BACKGROUND forks — a
backgrounded BARE SIMPLE command in a suppressing context must sever
(bash/base child=2; your tip 1; the D-matrix shows bg subshell/brace/
function correctly KEEP at 1 — only the bare-simple row is wrong); (2)
the deferral must be ONE-SHOT, bound to the member's own resolved
command: a function reached through a member's eval'd/. text does NOT
get the deferral re-applied (`f(){ eval 'echo $(if)'; }; set -e;
{ true | eval 'f'; }` → bash/base 2, your tip 1 — _function_frame
currently re-applies for ANY function entered anywhere in the member).
ALSO probe the cmdsub/procsub routes for the same bare-simple
distinction and state what bash does. STREAMLINED STAGE-GATE (earned):
write the mechanism proposal (where one-shot consumption happens, why
the direct-call case still re-applies) into the ledger, send it with the
landing declaration in the SAME message — the record must show the
proposal preceding the diff, but no wait-for-GO round-trip this time.

**R7-B — PIN THE TWO TOWARD-BASH CO-MOVEMENTS.** Your R6-B change also
moved ORDINARY errexit (no substitution error involved): (1) failing
commands inside a member's eval'd/sourced text (base ran on; tip fires
= bash); (2) bg subshell in a suppressing context (360090b2's threading;
base fired; tip runs on = bash). Both are DECLARED improvements now:
both-sides pins, and note that your existing controls (posix set -q,
plain-false member) are precisely the shapes that do NOT move — add
rows that DO, beside them.

**R7-C — production fixes:** the false "probe-verified for subshell,
command substitution…" claim in substitution_child_abort_status's
docstring (correct it to what was actually probed, or probe the family
and pin it); the DANGLING file.py#symbol in the one-writer/one-reader
invariant comment for errexit_suppress_deferred (it names a wrong/
moved symbol — fix and note the doc-pointer guard only checks paths);
the WIDENED-SIGNATURE caller left behind for _execute_background_subshell
(update the caller or handle the default explicitly — see resurrection
evidence); the aliased-import guard evasion (from …import X as SSA) —
strengthen OR state the limit in the guard docstring and ledger.

**R7-D — ledger integrity, round-6 crop (strike-and-correct each):**
(1) the R6-F "RED-ON-BASE: 2 of 6 arms fail at 1b271d77 (replayed…)"
claim does not replay — re-run, record what the instrument actually
prints, state the cause; (2) the R6-E(3) absolute is falsified and two
round-5-flagged items survive under it — fix both items and the
absolute; (3) the audit is 55 rows, not "ALL 56 ROWS PASS" — count from
the script, correct the claim; (4) the cumulative "Touched EXACTLY" list
omits the round-6 production files — restate from git diff --name-only;
(5) 360090b2's row must NAME psh/executor/subshell.py. PLUS scope-
accounting rows citing authority for the three edits verifiers flagged
as outside named scope: tests/conftest.py (sanctioned: my PTY
default-run approval), psh/parser/recursive_descent/helpers.py
(sanctioned: the round-4/5 falsified-docstring mandates),
support/nested_parse.py (sanctioned: the R6 pointer-fix mandate) — the
edits were RIGHT; the ledger must cite the ruling so a verifier can see
the authority.

**R7-E — closure:** batteries/bounced-rows/audit gain the new rows
(bg-bare-simple, eval-reached-function, both ordinary-errexit
families); re-gate + compare-bash (GO granted NOW for both, same
foreground form — no separate request needed this round); declare with
the corrected audit count and STILL-OPEN discipline.

Verified-clean carryover you keep: the R6-B core (fresh 59-row verifier
matrix), R6-A bg shapes, teardown, in-child + main-shell families, PTY
module collection, guards on canonical+fixed-evasion shapes, forbidden
files, accounting totals.

## ADDENDUM 2 (2026-07-31, after your d64a3294 landing report) — CURRENT

**GATE GO: GRANTED. The machine slot is yours.** Run exactly as you stated:
`python -u run_tests.py --parallel > tmp/gate-r6.txt 2>&1` foregrounded
with the tip SHA in the header, then `pytest tests/behavioral
--compare-bash -n auto -q`. ONE reminder so a round-1 mistake (mine,
originally) doesn't recur: the golden co-flip is a psh_only row — it
contributes ZERO to compare-bash composition, which should come back
2,986 / 26 UNCHANGED. Report the composition as measured; if it differs
from 2,986/26, that is a finding to explain, not a co-flip effect to
narrate. Your landing report is fully accounted: Q2's fifth kind measured
pre-fix, ruling (c) resolved by scope-check, guard-scope decision
recorded, audit 56/56 with header-SHA anti-staleness, worktrees clean.
After both runs: declare (d64a3294 unless the gate moves it) with the
complete audit + STILL-OPEN table empty-or-deferred, and I launch
verification round 6.

## ADDENDUM (2026-07-31, after your bf2a7d00 status message) — READ THIS FIRST

**R6-B: GO. GO. LAND r6b-READY.patch + the pin NOW.** Fifth transmission.
Every one of your last four messages was composed before my ruling landed —
this file has carried the GO since before your bf2a7d00 message. Poll this
file at the START of every turn from now on.

Also ruled on your bf2a7d00 report:
1. **bf2a7d00 RATIFIED — no conflict.** Your unilateral declare+pin of the
   function-member channel row under the standing rule coincides EXACTLY
   with the ruling I had already issued for it (see (a) below: declare+pin,
   full chain in the docstring, movement told straight). Your procedural
   reasoning (leaving a slot-introduced delta unpinned pending a ruling is
   itself the bounce-shaped choice) is correct and is banked.
2. **/tmp deviation: RECORDED, NO FURTHER ACTION.** Self-reported, transient,
   deleted in the same command, no project artifact. The self-report is the
   conduct the campaign wants; the tally notes it as a minor self-reported
   deviation and moves on.
3. On-GO sequence confirmed as you stated it: land patch + pin → batteries
   SHA-stamped (run_r6_batteries.sh) → discharge audit (its R6-B rows must
   flip to PASS) → remove probe worktrees → THEN request full-gate +
   compare-bash GO (granted promptly on request).


Written 2026-07-31 by the integrator because THREE consecutive GO
transmissions over the message channel missed your working turns. Rulings
here are authoritative; ACK them by number/letter in your next message.

## R6-B: GO — LAND IT. (Third+fourth transmission of this grant.)

The grant was issued after your placement proposal (conditional), again
after your evidence addendum (unconditional — your Q2/Q1 measurements
satisfied the conditions), again after your R6-C/D/E/F status report, and
now after your trial. The trial results (64/64 bounced rows, chain
121/0/5/2 with all 21 regressions → MATCH and nothing else moved, edge
battery flipping only intended rows, teardown byte-identical, 944 + 2,801
green at the trial) are the most de-risked change this slot has seen.
Land exactly the trial patch (context.py field + pipeline.py member
closure + function.py _function_frame restore) plus the pin set you
described (test_pipeline_member_suppression_matches_bash sampling the
family, compound/function members as control pins beside it, red-on-tip
and red-at-base-where-base-was-wrong documented).

The RULE you asked me to ratify is ratified as the recorded invariant:
bash's -e-ignoring reaches a pipeline member only through a COMPOUND
command or a function BODY, never into a simple-command member's own
execution (bash manual sentence, quoted in the field docstring per the
earlier ruling). The one-flag impossibility (r4 satisfied one half, r5/6
the other, neither end both) goes in the ledger as the design rationale.

## Previously crossed rulings (restated so the record is one place)

- (a) Function-member -c row (moved twice: base no-abort → r4 2 → tip 1):
  DECLARE + PIN with the full chain in the docstring; ledger tells the
  movement straight; successor-note for channel-rule unification.
- (b) PIPESTATUS collapse in brace groups: SUCCESSOR-QUEUE row text.
- (c) Member-child EXIT-trap silence: check the round-3 teardown
  declaration's scope; cite it if covered, else successor row. No in-slot
  fix.
- PTY policy edits (registry entry + conftest default-run allowlist):
  BOTH APPROVED — an opt-in pin for a PTY-only fact is an
  accidentally-green pin; keep the module in the gate.
- PTY three-row finding: accepted as declared (discharges R5-F(2)).
- -n pin + --validate declared asymmetry: approved as executed.
- R6-E item (2) as CORPUS GAP (staleness not claimed): approved.
- Anti-spawn guard's derived membership pin (slot 1.2 ratchet defect):
  SUCCESSOR ROW; your entry is the offender demonstration; correct not to
  touch another slot's ratchet mid-round.
- Evidence stays in tmp/r24-probes/; integrator rescues into
  docs/reviews/evidence/2.4-rescue/ at ceremony.

## After R6-B lands

Re-run the batteries at the final tip with SHA-stamped outputs; discharge
audit (expanded form: instrument-output FILE anchors, bounced-rows replay
64/64, SHA-stamped transcripts, STILL-OPEN empty-or-deferred); THEN
request gate GO here or by message. Machine slot will be granted promptly.
Remove the trial worktree either way.
