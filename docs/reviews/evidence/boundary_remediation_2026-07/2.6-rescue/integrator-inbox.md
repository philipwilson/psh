# INTEGRATOR-INBOX — slot 2.6 dead-drop (poll at the START of every turn)

Protocol: the integrator writes rulings here AND sends them by message;
the message channel drops turns (proven in 1.4/2.4/2.5) — THIS FILE is
authoritative. ACK every ruling by number in your next message. If a
message referencess a ruling not in this file, say so immediately.
Append-only; never edit or delete integrator entries.

---

## R0 — STANDING RULINGS AT SLOT START (2026-08-01)

**R0-1 (stage-gate, STANDARD):** Phase A (red-on-base + censuses +
both-oracle table + design proposal + composition census) is a REPORT.
WAIT for explicit GO + the mode-composition RULING before any production
edit. Design decisions with real alternatives: trial in a throwaway
worktree first — evidence, not argument.

**R0-2 (R-AWAIT + 600s form):** never end a turn with a heavy run in
flight. Runs under ~10 min = ONE foreground Bash call (timeout 600000),
e.g. `python -u run_tests.py --parallel > tmp/gate-N.txt 2>&1`. Longer
runs: declare BEFORE launching and await in-turn with a bounded poll.
`pgrep -f pytest` before every heavy run; a timed-out foreground call has
been MOVED TO BACKGROUND, not stopped — sweep before relaunching.

**R0-3 (machine-wide serialization):** ONE heavy run at a time on this
machine. REQUEST INTEGRATOR GO by message before every full gate and
every compare-bash run. Probe-grade detached base worktrees are not
heavy — use freely, remove after, discriminator + neutral cwd always.

**R0-4 (composition ruling pending):** MEDIUM-9(b) compose-vs-reject is
ruled at the Phase A gate, on your census. Integrator leaning: REJECT at
invocation parsing (usage error 2, message naming the flags). Do not
implement either branch before the ruling lands here.

**R0-5 (certification):** your final-tip certification instrument follows
the 2.5 end-state from birth: rows anchor to ORDERED CHANGES (committed
test names / diff hunks, never production prose), since-SHA both ends,
POST-STATE predicates (would this row pass if the ordered change were
absent but my edit present? — it must not), reads commit content via
`git show` at tip, self_check rejects malformed rows, and every mutation
class fails for its OWN reason. Break the instrument on purpose and
confirm it notices — before you cite it.

---
(integrator entries below this line, newest last)

## R1 — PHASE A ACCEPTED; GO FOR PHASE B + ALL RULINGS (2026-08-01)

Integrator tree-verification performed BEFORE this ruling (own instruments,
neutral cwd + discriminator at 42f75591): F7 reproduced with independently
written bytes (rd --format corrupts the post-heredoc loop header; combinator
clean; psh executes correctly = bash); both-oracle extglob table reproduced
exactly (bash EXEC 0 / bash -n 2 / psh exec 0 / psh --validate 2; bash
5.2.26 confirmed); test_parse_invocation.py:358 pair confirmed
(ordered-retention + dedupe); parse_with_inputs fresh-parser-per-call
confirmed at psh/parser/__init__.py:110-123. Nothing below is a relayed
claim.

**R1-A (Q1, discharges R0-4): REJECT at invocation parsing.**
Two or more DISTINCT analysis modes → usage error, exit 2, stderr message
naming ALL offending flags, raised in parse_invocation so it precedes Shell
construction. Same-flag duplicates KEEP deduping silently
(test_analysis_mode_deduplicated survives; test_analysis_modes_ordered is a
DECLARED FLIP, replaced by a rejection pin covering: each 2-permutation
class, a 3-way, the 5-way, and duplicate+distinct). Downstream: make the
silent-drop state UNREPRESENTABLE (shell.py's five booleans become one
honest single-mode representation — exact shape yours within that pattern).

**R1-B (Q2): ADOPT per-unit line diagnostics.** Declared + pinned per
channel × parser; syntax-error status stays 2. The _report_syntax_error
docstring rationale ("the whole content was parsed at once") becomes FALSE
prose — sweep it tree-wide; certification rows assert the POST-STATE.

**R1-C (Q3): ACCEPT R3's declared residual.** No widened-state retry —
your rejection rationale (analysis must not accept broken scripts) is
adopted verbatim. eval-string/source-file opacity: declared + pinned +
documented in the user guide's psh-specific rows (your census confirmed no
conformance-claims mapping is triggered; keep it that way — no bash
"Full support" wording).

**R1-D (F7): CO-LAND APPROVED as a declared improvement.** Requirements:
own red-on-base pin (rd), combinator control (clean at BOTH SHAs),
execution control (unchanged, = bash), and the fencing statement in the row
(NOT r18: no crash, no unterminated construct — state it, don't imply it).

**R1-E (F2 third surface): ADOPTED.** `-n` stays pinned to bash's
state-blind `-n`; `--validate` becomes state-aware. Pin the two-surface
split on ONE script (same input: psh -n rc 2 = bash -n rc 2;
--validate rc 0 at tip). Docstrings + user guide state the boundary.
The LEDGER 2.4-row cross-reference is MINE at ceremony — leave it.

**R1-F (F5): rule R3 ADOPTED** (monotone enables + function bodies).
The DISABLE direction (`shopt -u extglob` then literal `+(`/`@(`) must
appear explicitly in the pinned corpus with its permissive outcome declared.

**R1-G (F4): alias overlay threads across units.** The 6 currently-green
alias rows land as DECLARED REGRESSION GUARDS (base-green pins declared as
such — never presented as red-on-base evidence).

**R1-H (F8): SHAPE M ADOPTED.** One parse per unit, statements merged into
one Program, each visitor runs once.

**R1-I (S-A vs S-B): STREAMLINED stage-gate** (2.4 R7-A precedent —
earned by the quality of this report): pre-register the decision criteria
in your ledger BEFORE running the trial, run it in the throwaway worktree,
record decision + evidence in the ledger BEFORE the implementing commit
lands. No round-trip wait required.

**R1-J (--format posix mis-render): declared improvement, own red-on-base
pin** (`set -o posix` + `$äö` reprint preserving meaning). --format threads
OPTION state only, never alias state — the #19 T6 ruling survives verbatim.

**R1-K:** heavy runs remain per-request GO (R0-3). GO NOW GRANTED for your
FIRST full gate when Phase B reaches it — announce start/finish by message;
subsequent gates still ask first. compare-bash: pytest form only, ask first.

GO FOR PHASE B.

## R2 — GATE-1 ANNOUNCEMENT ACKED; PIN-SHAPE RULING (2026-08-01)

**R2-A (combinator line pin): YOUR SHAPE APPROVED.** "Analysis reports a
syntax error at the same location execution does, per parser" + literal
line-3 for rd is the stronger-and-true claim; the combinator's top-level
line-1 stamping is the PRE-EXISTING 2.2 carry (LEDGER Part D), correctly
not absorbed — parser internals are outside your scope. Two requirements:
(1) the pin's docstring CITES the carry row by its ledger name verbatim, so
whoever closes the carry finds this pin from the row and vice versa;
(2) if the pin asserts the combinator's literal line 1 anywhere, that
assertion is LABELLED a carry tripwire expected to flip when the carry
closes — declared, never silent.

**R2-B:** mypy 274→275 via the directory glob with zero config change is
the designed behavior (test_mypy_scope.py guards it) — record the delta in
the ledger as you have; no action.

R1-I discharge shape (criteria pre-registered → trial → decision recorded
before implementing commit, worktree removed) is exactly as ordered.
Awaiting gate-1 result.

## R3 — GATE-2 GREEN ACKED; compare-bash GO; R2 POINTER (2026-08-01)

**R3-A: gate story ACCEPTED.** Reporting the red first run rather than only
the green one is exactly the record discipline this campaign runs on. The
resolution class — hoist everything, defer NOTHING, caps ratchet DOWN
(source_processor 6→5, visitor_modes 9→7), zero allowlist entries — is the
preferred one, and the type(shell) carrier is a clean answer to the
layering inversion (record the embedder-subclass side benefit in the
ledger row; it is a behavior claim and needs its one-line test or an
explicit untested-note).

**R3-B: compare-bash GO GRANTED** — `python -m pytest tests/behavioral
--compare-bash -n auto -q`, one foreground call, announce finish. Expect
EXACT 2,986/26. A composition move = blocker + stop, as you committed.

**R3-C (R2 pointer):** your R1-B section re-asks a question ALREADY RULED —
R2-A in this file (written while your gate ran; expected crossing).
Summary: your shape APPROVED, with TWO requirements — (1) pin docstring
cites the 2.2 carry row by verbatim ledger name; (2) any literal
combinator line-1 assertion is labelled a carry tripwire expected to flip
at carry-close. CONFIRM both are implemented (or implement them now,
before the certification instrument freezes rows) and ACK R2 + R3 by
letter in your next message.

**R3-D (command_accumulator cap 2 vs actual 0): TAKE IT IN-SLOT.** You are
already editing adjacent rows of the same cap table; a free ratchet-down
is what the ratchet exists for. One line, declared in the ledger.

## R4 — R1-I DISCHARGED BY INTEGRATOR READ; FINAL GATE GO (2026-08-01)

**R4-A: R1-I DISCHARGED — by my read, as you correctly framed it.** Evidence:
(1) ledger ordering (pre-registered criteria + fixed decision rule precede
the trial result; trial result precedes the Phase B commit table);
(2) temporal corroboration OUTSIDE your control: your gate-1 START message
in my transcript already reported the trial complete with identical content
BEFORE the implementing commits were gated. Your refusal to write a
certification row for your own process ordering — "an instrument certifying
it would be certifying its own author" — is the correct form and goes in
the ceremony lessons register.

**R4-B: FINAL GATE GO at 94e038c6** — one foreground call, announce finish,
then declare the final tip with per-commit delta accounting. Your six-minute
no-caveat instinct is the campaign standard; correct request.

**R4-C: poll-before-SEND adopted as a standing rule** (your cure, verbatim:
re-poll the dead-drop immediately before sending, not only at turn start).
It joins the briefs for every subsequent slot. Fault honestly owned, no
tally — the protocol gap was real and the cure is yours.

**R4-D (preview, not a gate item):** on green + your final declaration, I
launch adversarial verification round 1. Expect verifiers directed FIRST at
your self-flagged weakest claims — bring the ledger's flag list current
before declaring.

## R5 — SELF-ATTACK ACCEPTED; GATE GO AT 62f2bd45 (2026-08-01)

**R5-A: GATE GO at 62f2bd45.** Your recommendation over your alternative is
correct and endorsed: 62f2bd45 deletes production code, so it is NOT
mechanical-tip material — declaring at 94e038c6 would ship a tip whose gate
predates a production delta. The serialization budget exists to be spent on
exactly this. One foreground call, announce finish, then declare.

**R5-B: both self-attack findings ACCEPTED as the system working.**
(1) unit_texts deletion — the zero-reference class, found by you before a
verifier found it; record it in the ledger as a self-found blocker (it
joins the bounced-rows replay set). (2) The safety-property pin: correctly
framed as evidence over a stated domain, not proof. Expect round-1
verifiers to attack that domain first — your own top-ranked weakest claim,
which is where I will point them.

**R5-C (_absorb_aliases private coupling):** your scope discipline was
right (expansion/ is STOP-and-report). The coupling is accepted for this
slot AND gets a SUCCESSOR ROW: AliasManager grows a public
analysis-overlay seam in a future expansion-owning slot; your ledger row
states the coupling, the reason, and the successor. If round 1 finds the
private method's contract too weak even for this use, that is a bounce,
not a successor.

**R5-D:** double-visit negative (0 duplicates across 5 nesting shapes)
noted — verifiers will be told it was pre-checked so they attack the
CORPUS, not re-run the claim.

On green: declare final tip with per-commit delta accounting (six commits
expected: 832dc663, 062ee8e9, 58972a1e, 94e038c6, 62f2bd45 + none further
without declaration). Verification round 1 launches on your declaration.

## R5-CORRECTION (2026-08-01)

R5's closing line says "six commits expected" then lists five SHAs — the
count was a miscount, the LIST is authoritative: FIVE commits (832dc663,
062ee8e9, 58972a1e, 94e038c6, 62f2bd45), none further without declaration.
First correction was sent message-only, which is the B80 anti-pattern this
file exists to prevent — integrator fault, tallied (2.6 tally: 1).

## R6 — LATTICE WIDENING ACCEPTED; PROMOTION DEFERRED; LEDGER FREEZE RULE (2026-08-01)

**R6-A: the widening is ACCEPTED as evidence** (62 → 7,496 generated →
29,984 subset-lattice cells, 0 counterexamples; inverted-direction
mutation proof 2,892 hits; self-found one-option-at-a-time axis gap,
closed over the lattice). Finding the axis-quantification failure in your
OWN instrument and closing it unprompted is the campaign lesson operating
at full depth. The honest residual (contexts ≠ grammar) is correctly the
only remaining attack surface.

**R6-B: PROMOTION DEFERRED — tree stays frozen.** Round 1 launched BEFORE
your message (wf_f5b524f3-f39, running now against 62f2bd45); your own
decision logic resolves the question: verifiers can run
hunt_invented_error.py themselves. Disposition by verdict:
- BOUNCE → promotion is PRE-APPROVED to ride the fix round.
- PASS → promotion is APPROVED as a post-PASS declared commit in ceremony
  prep (mechanical-tip declaration + scoped re-gate on my GO) — the
  in-tree domain statement is worth one gate.
Either way you do not touch the tree until the verdict and my word.

**R6-C (new standing rule, stale-snapshot class):** while a verification
round is IN FLIGHT, the ledger is frozen the same as the tree — post-
declaration evidence goes in a DATED ADDENDUM section, never an in-place
rewrite of an existing entry (a verifier that read entry #1 before your
rewrite and re-reads after sees a moved target). Your rewrite this once
strengthens the claim and is marked as post-declaration — accepted, no
fault, rule applies from now.

## R7 — ADDENDUM SANCTIONED; BOUNDARY CONFIRMED (2026-08-01)

**R7-A: the addendum was the CORRECT action, not a freeze violation.**
R6-C's boundary is confirmed exactly as you read it: in-place edits are
forbidden during a round; DATED ADDENDA are the sanctioned form — and an
addendum that discloses a pre-rule rewrite, preserves the superseded text
VERBATIM for the verifiers to diff, and explicitly declines to upgrade the
claim's epistemic category as the number grew, is the model instance.
"The number got larger; the epistemic category did not" goes in the
ceremony lessons register.

**R7-B: the instrument inventory with self-flagged attack points is
noted** — score_rules.py's hand-modelled FACTS table (the one human
transcription in the evidence chain) and census_state.py's
fourth-input attack are precisely the pointers a verifier should receive
from the author rather than find. No further action from either of us
until the round-1 verdict.

## R8 — ROUND 1 VERDICT: BOUNCE (4 blockers, 21 nits). TIP 62f2bd45 DISSOLVED. FIX ORDERS (2026-08-01)

Verdicts: diffAudit FAIL, ledgerCheck FAIL, reprobe FAIL, resurrection
PASS-WITH-NITS. I independently replayed B-1, B-2, B-4 at the tip with my
own probe files before this ruling (incl. B-1's THIRD face: the bare
`psh: file:` prefix with no line number — the error bypasses your own
per-unit diagnostics). All four blockers are REAL. Round-1 scorecard:
4/4, 0 false. Full verifier output: integrator transcript; the four
finding bodies are reproduced in the fix orders below.

**R8-A (B-1, the regression — fix first).** _absorb_aliases runs the
PLAIN tokenize over each unit's raw text: heredoc BODIES are lexed as
command text. Apostrophe in a body = false rc 2 on 4/5 modes, every
channel, both parsers (REGRESSION, base rc 0); alias text inside a body
is absorbed into carrier state; the UnclosedQuoteError escapes the
AnalysisSyntaxError envelope (no per-unit line prefix). This violates the
brief's must-NOT-flip one-heredoc-grammar clause — the absorption pass
reinvented a body-blind second lex. ORDER: the alias-absorption pass
consumes the SAME heredoc-aware token stream the real parse produces
(reuse, never a second raw-text tokenize); THREE pins, one per face:
(1) apostrophe/quote-bearing heredoc bodies analyze rc 0 (red at
62f2bd45 — a regression pin, state its red-at-dissolved-tip status
explicitly); (2) alias/unalias text inside a heredoc body is DATA, never
absorbed; (3) every per-unit lex/parse error routes through the envelope
and carries the `file:N:` prefix. CORPUS: heredoc bodies gain
quote-bearing content across <<, <<-, quoted delimiters, two-heredoc,
body-in-function shapes (your suite's bodies were abc/body/x — the
observability-axis gap that let the gate pass).

**R8-B (B-2, census→code transcription fault + structurally blind
guard).** Your OWN census found expand_aliases (D1, D2, F3 table);
PARSE_RELEVANT_OPTIONS ships two, under a docstring claiming the
instruments "agreed on exactly these two" — a FALSE sentence about your
own census (B59 class: the claim was true of the census, false of the
code). ORDER: (1) expand_aliases joins PARSE_RELEVANT_OPTIONS; the
session honors shopt -s/-u expand_aliases per execution's MEASURED truth
table — note it is NOT monotone (disable must stop expansion in later
units; your verifier row: exec 127 = bash, analysis must follow). Rule
R3's statement becomes per-option: monotone-enables applies to
extglob/posix; expand_aliases follows its measured semantics under the
same structural/reachability rules. Probe first, declare the table in
the fix report. (2) The false docstring sentence is STRUCK — post-state
certification row (whole-file absence). (3) The derivation guard's
universe must match the claim: derive the option set from the PIPELINE
(runtime trace through lex_and_parse, per the verifier's instrument) or
every package the pipeline traverses — not a two-package list that
excludes the third consumer. (4) The safety corpus re-parametrizes and
STATES the expand_aliases exception explicitly. (5) New certification
row: PARSE_RELEVANT_OPTIONS equals the pipeline-derived set (post-state,
so this class cannot recur silently).

**R8-C (B-3, dropped brief item).** The Interactive-leg bullet's stated
conclusion + census never reached the ledger. ORDER: dated addendum with
YOUR census (command + output + conclusion — re-run your own, do not
copy the verifier's), plus the required-work-5 Linux paragraph (nit) in
the same addendum.

**R8-D (B-4, spelling axis).** Six spellings execute the enable but
analysis misses it (builtin/command/backslash-escaped/assignment-prefixed
heads, clustered -sq, set -e -o extglob) — red at base too: an
undeclared incomplete fix, the MEDIUM-9 signature surviving on the FIRST
axis of the catalogue. ORDER: widen _absorb_transitions per the bounded
shape (normalize head through builtin/command/\-escape/leading
assignments; clustered short flags containing s; every -o pair of a set
command); pin all six red-on-base; keep the eight near-miss controls;
the session docstring's "every option ENABLE found in a parsed unit"
either becomes true over the widened recognizer or is scoped to what is
true. set -e -o extglob keeps its declared psh-superset status.

**R8-E (nit dispositions, itemized):**
1. --help/--version precedence: RESTORE the base short-circuit (help and
   version win over the mode-conflict error, in any argv order), pinned.
   R1-A never authorized that move.
2. R1-D's --metrics face and R1-J's --validate + named-fd faces: PIN
   them; the declared rows state their full measured reach.
3. AnalysisSyntaxError.source_text: DELETE the dead field (dead-state
   rule); combinator caret back-fill = SUCCESSOR row, not this bounce.
4. _MODE_RUNNERS KeyError: keep it (correct internal-defect class under
   strict-errors) + the deleted-decider docstring sentence ("an unknown
   mode name is an internal defect, not a silent no-op").
5. Cap accounting: ledger amendment records all THREE cap changes incl.
   command_accumulator 2→0 (commit message is immutable; the record is
   the cure).
6. Record repairs: replay-set true composition + manifest SHA stated;
   red-on-base counts RE-DERIVED at the new final tip; compare-bash
   re-run at the new tip (required anyway); F6 census command + corrected
   count (108) recorded; B3 bounced-row names 832dc663.
7. Weak-or → conjunctive (rc==0 AND "var: file" in stdout, keep the
   not-in half); delete the always-true `assert cwd`.
8. psh/__main__.py one-line help addition: SANCTIONED NOW (record in the
   ledger's scope accounting citing R8-E-8).
9. Alias-uniformity prose: SCOPE it — the isolation half does not apply
   to the alias axis; base-faithful behavior preserved; successor row is
   the home (verifier concurs per R5-C; not a bounce).
10. Isolation-default polarity: verifier ENDORSED your choice — no
    change; note the endorsement.
11. ARCHITECTURE.md stale analysis-source_text sentence + the archival
    appraisal pointer: MINE at ceremony. Leave both.

**R8-F:** R6-B's bounce arm fires — the 29,984-cell hunt corpus is
PROMOTED to a committed test in this fix round, re-parametrized per
R8-B(4) so the promoted instrument states the expand_aliases exception.

**R8-G (process, for the ledger lessons row):** B-2 could not be caught
by your certification because no row asserted the CONSTANT's
completeness against the census — the new post-state row class (R8-B(5))
closes that. The two corpus gaps (heredoc-body CONTENT, directive
SPELLING) join the axis-catalogue instance list. Your weakest-claims
ranking pointed the verifiers at the right neighborhoods — the two
deepest finds sit exactly where entries #1 and #2 pointed. That is the
flag list working, and it goes in the record as such.

**SEQUENCING:** fix commits → ONE full gate + ONE compare-bash at the
new tip (PRE-GRANTED for this fix round; announce start/finish of each)
→ certification re-anchored + extended (incl. the R8-B(5) row class) →
bounced-rows replay now including these four → declare new final tip
with per-commit accounting → ROUND 2 (scoped: four-blocker replay +
R8-E spot checks + stability rows). Poll-before-send per R4-C. Tip
62f2bd45 is DISSOLVED; the mechanical-tip rule re-arms at your next
declaration.

## R9 — ROUND 2 VERDICT: BOUNCE (2 distinct defects from 3 blocker reports, 17 nits). TIP 053750e5 DISSOLVED (2026-08-01)

Verdicts: diffAudit FAIL, resurrection FAIL, ledgerCheck PASS-WITH-NITS,
reprobe PASS-WITH-NITS. Blockers 2+3 are the SAME defect found
independently by two agents. I replayed BOTH faces of D-1 and read the
doc lines myself before this ruling. Round-2 scorecard: 2/2 distinct
defects real, 0 false. Slot cumulative: 6 verifier-found defects, 0
false.

**R9-A (D-1, REGRESSION introduced by the fix round — fix first).**
_absorb_aliases walks every WORD token for alias/unalias with NO
command-position guard; base's AliasManager.expand_aliases absorbs only
when _is_command_position holds. Face 1 (false red): `alias iff=...` /
`echo unalias -a` / `iff echo X; fi` — executes rc 0 both SHAs, base
validate 0, tip validate 2 (the argument-position unalias wiped the
table). Face 2 (false green): `echo alias iff='...'` / `iff ...` —
executes rc 2 (= bash) both SHAs, base validate 2, tip validate 0.
NAME THE PATTERN, because it is this slot's SECOND instance: R8-A was a
body-blind re-lex of text the pipeline already lexes; this is a
position-blind re-walk of tokens a decider already walks. The
deleted-decider rule binds the WHOLE input space of what you replace —
_is_command_position was part of the decider, and reuse-don't-reinvent
covers the GUARDS in the original walk, not just its tokenizer. ORDER:
absorption applies the SAME command-position discipline as the real
expand path — drive the existing position logic (reuse; if the private
seam blocks full reuse in-slot, match its semantics exactly and state
that in the ledger row). BOTH faces pinned with the three-point
regression shape stated (green at 42f75591, red at 053750e5, green at
new tip). ALIAS-AXIS NEAR-MISS CONTROLS added — the `echo unalias -a` /
`printf '%s' alias` twins of the option-axis controls; R8-D closed this
gap for options and the alias axis never got its copy.

**R9-B (D-2, doc contradicts the branch's own pins).** The user-guide
"three limits" bullets (17_differences_from_bash.md:818-824, written in
062ee8e9) still state ALL-options monotone semantics: "Turning an option
back off does not narrow the analysis" and "accepts slightly more...
rather than reporting errors for scripts that run fine" — both FALSE for
expand_aliases since R8-B, and your own
test_unreached_conditional_disable_is_the_declared_cost pins the
opposite. ORDER: carve expand_aliases out of both bullets; state the
ordered last-wins rule and the declared cost in user-facing words (a
worked example is welcome); the monotone bullets stay for extglob/posix.
The R8-B re-scope reached code docstrings and not the user-facing
declaration — the doc is part of "declared + pinned + doc'd".

**R9-C (nit dispositions):**
1. `set -o` scanner stops at `--` (N2): FIX + pin (`set -- -o extglob`
   is not an option change; probe bash for the row's exec side).
2. `shopt -su extglob` contradictory cluster (N12): probe bash's real
   outcome, make the recognizer match the MEASURED semantics, pin.
3. `sh\opt -s extglob` mid-word backslash (N16): probe; widen the head
   normalizer if the fix is bounded, else SCOPE the documented claim so
   it is true — either way declared, never silent.
4. bash-agreement prose for psh -n (N3/N13): add the conformance pin
   under tests/conformance/ (repo principle: user-guide bash-conformance
   claims are proven there) — the two-surface machinery already exists.
5. _option_changes docstring made true (N1); the two under-counting
   module docstrings corrected (N8).
6. Perf figure (N4, 2.2x on a 4,000-line script): RECORD in the ledger
   with the number + one sentence in the analysis_session docstring.
   No optimization in-slot; successor row if anyone wants one.
7. Record repairs (N9/N10/N11/N15): module-set naming corrected; the
   47/170 red-at-dissolved-tip claim gets a PRESERVED manifest; per-
   commit delta rows for 053750e5 and the new fix commit(s).
8. N17's two boundary resolutions recorded as measured; N5/N6/N7 clean
   results noted, no action.

**R9-D:** certification gains ordered-change rows for R9-A/B/C fixes
(post-state, since = 053750e5); bounced-rows replay grows by the round-2
rows; discharge audit re-run at the new tip.

**SEQUENCING:** fix commits → ONE gate + ONE compare-bash at the new tip
(PRE-GRANTED, announce start/finish) → certification + replay + audit →
declare new final tip with COMPLETE per-commit accounting (incl. the
row N11/N15 flagged) → ROUND 3 (micro: D-1 both faces + near-miss
controls, doc carve-out check, N2/N12/N16 spots, stability rows). Tip
053750e5 is DISSOLVED; mechanical-tip re-arms at your next declaration.
Poll-before-send per R4-C.

## R10 — MANIFEST RULING; ROUND 3 (MICRO) LAUNCHING (2026-08-01)

**R10-A (the 47/170 question): BOTH manifests stand, each on its own
basis — do NOT reconcile to one number.** A red-count is a property of
(module set, SHA), not of the SHA alone; 47/170 is true of the round-1
modules that produced it, 56/182 of today's, and the ImportError is
itself informative (today's tests import names 62f2bd45 lacks — the
suite has moved past the commit it once measured). Your discrepancy
entry with cause is the correct final form; my order is satisfied as
you executed it, not as I worded it. This joins the lessons register:
"a count without its instrument basis is not yet a fact."

**R10-B:** R9-A's fix shape (running the real expand path and keeping
its overlay, so position discipline is INHERITED) is the reuse form the
two bounces were pointing at; your sentence "I reused the NAME of an
existing mechanism and re-derived its BODY" is banked verbatim for the
ceremony lessons row. Near-miss controls asserted against EXECUTION
agreement rather than fixed statuses: correct, and round 3 is told to
attack that form rather than re-litigate it. Perf: recording your own
3.2x and NOTING the verifier's 2.2x without adopting either is the
right form (two hosts, two instruments).

**R10-C:** ROUND 3 (MICRO) launching now at b254ca52: D-1 three-point
replay + novel argument-position rows + structural read of the
absorption path; doc carve-out + guide-holding pins; R9-C spot probes
(set --, -su refusal, backslash normalizer, conformance module content
and reach); records (77/77 + mutation, 170/170, dual-manifest entry,
seven-commit accounting); stability rows. Freeze rules in force.

## R11 — ROUND 3 VERDICT: BOUNCE (1 blocker, 14 nits). TIP b254ca52 DISSOLVED (2026-08-01)

Verdicts: diffAudit FAIL; resurrection/ledgerCheck/reprobe all
PASS-WITH-NITS. I replayed both faces of the blocker with od-verified
bytes before ruling. Round-3 scorecard: 1/1 real, 0 false. Slot
cumulative: 7 verifier-found defects, 0 false — THREE of them the same
fault class.

**R11-A (the blocker — and the CLASS, third instance).** _normalize_head
strips backslashes UNCONDITIONALLY — including backslashes the shell
preserves (inside single quotes, doubled in double quotes). `'sh\opt'`
is not shopt, but the normalizer says it is: the invented
expand_aliases DISABLE produces a false rc 2 on a script that executes
clean; the extglob mirror accepts a script BOTH shells reject. The
docstring's domain claim ("a backslash before an ordinary character is
just quoting") is false when the backslash is itself quoted. This is
the third re-derivation this slot: body-blind lex (R8-A),
position-blind walk (R9-A), quote-blind normalize (now). ORDER, in two
parts:
(1) THE INSTANCE: head normalization consults the LEXER's quote
knowledge — token parts carry per-part quote context (the v0.120
Word/TokenPart invariant); only backslashes the lexer treats as quoting
are stripped, and a head whose quoted parts don't spell the directive
is not the directive. Both faces pinned (false-red expand_aliases face,
false-green extglob mirror, three-point shape); QUOTED-HEAD rows join
the NON_ENABLES controls in BOTH corpora (option AND alias axes);
docstring corrected.
(2) THE CLASS: a census of analysis_session.py for every place it
performs string surgery on token values (strip/replace/slice/compare on
raw text) — each site either consumes a lexer-provided fact or gets a
written justification in the ledger for why the lexer cannot supply it.
After three instances, the fix that ships must make the fourth
IMPOSSIBLE to write without failing a guard — the census becomes a
committed test asserting the sanctioned-sites list, so a new
string-surgery site fails until justified.

**R11-B (nit dispositions):**
1. N1: pin all four additional never-reached-disable shapes (uncalled
   function, while-false, case-miss, ||-RHS) — the corpus matches the
   declared class.
2. N2: combinator detail-line state (unit-relative since the per-unit
   change) DECLARED + pinned with a 2.2-carry cross-reference in the
   tripwire family. No parser internals.
3. N3: alias-heredoc analysis change declared + pinned (permissive
   register; B100 cross-ref; execution unchanged proven in the pin).
4. N4: fix user-guide line 533 — the "parses the entire program before
   executing" premise is false and now contradicts this slot's
   foundation; the paragraph's conclusion stays.
5. N5: mirror the mutual-exclusion help line into both user-guide
   copies.
6. N7+N8: lex_and_parse is KEPT — its role as the whole-file-parse
   ORACLE for the convergence/parity tests is load-bearing and
   legitimately cross-test (not the unit_texts shape, which had no
   external consumer). Its docstring states the oracle role explicitly;
   the FALSE pointer at visitor_modes.py:40 ("each unit goes through
   lex_and_parse") and the stale chokepoint prose are corrected
   (post-state rows).
7. N9: delete the dead 'command_accumulator': 0 cap key (0 ≡ absent by
   the enforcement's own .get default; the regenerator agrees).
8. N12: command-resolution shadowing (function-shadowed shopt absorbed)
   is DECLARED in the accept-more limits enumeration (one doc line) +
   gets a control row asserting the measured behavior; general
   resolution-awareness = successor register.
9. N13: alias-axis normalization asymmetry recorded in the ledger as
   base-faithful preserved limitations under the R8-E-9/R5-C successor
   home; the `command alias` row named in the successor row's text.
10. N14: the guide-holding pin gains the ABSENCE assertion (the old
    unqualified sentence must not reappear) so the committed pin covers
    what only certify.py covers today.
11. N11: one-sentence ledger wording fix (name test_parse_invocation.py
    in the re-derivation set).

**R11-C:** certification rows for every R11 ordered change (post-state,
since = b254ca52); replay grows by the round-3 rows; discharge audit at
the new tip. SEQUENCING: fix commits → ONE gate + ONE compare-bash at
the new tip (PRE-GRANTED, announce start/finish) → records → declare
new final tip with complete accounting → ROUND 4 (NANO: blocker replay
both faces + quoted-head corpora + string-surgery census guard + N-spot
checks + stability). Tip b254ca52 is DISSOLVED; mechanical-tip re-arms
at your next declaration. Poll-before-send per R4-C.

## R12 — FIX ACCEPTED; superseded_by ENDORSED; ROUND 4 (NANO) LAUNCHING (2026-08-01)

**R12-A:** R11-A executed better than ordered: measuring the 11-spelling
head table BEFORE encoding (and thereby refusing my implicitly cruder
"quoted heads are not directives" rule, which would have broken five
working spellings) is the probe-first standard at full depth; the two
measurement-found mirrors (operand ext\glob, flag \-s) and the
expansion-head declared residual are accepted as chartered. The class
guard's stale-entry rejection ("an allowance for deleted code is how a
guard quietly stops guarding") joins the lessons register, as does your
closing formulation: "a guard without its universe is not yet a guard."

**R12-B: certify superseded_by handling ENDORSED as the correct
judgment.** Deleting rows that later rulings replaced would have erased
the ruling chain; asserting the SURVIVING post-state under a SUPERSEDED
heading preserves both the history and the check. Round 4 is told to
verify a superseded row still FAILS when its surviving state is absent.

**R12-C:** ROUND 4 (NANO) launching at 9b78098a: quoted-head both faces
three-point replay + spelling-table sample vs bash + novel quote shapes
+ the two mirrors + expansion-head residual; the string-surgery guard
BROKEN ON PURPOSE (planted site, stale allowance) and its universe
checked; records incl. superseded rows; R11-B spot checks; stability.
Freeze rules in force.

## R13 — ROUND 4 VERDICT: BOUNCE (4 distinct defects from 5 reports, 17 nits). TIP 9b78098a DISSOLVED (2026-08-01)

Verdicts: diffAudit FAIL, reprobe FAIL, resurrection + ledgerCheck
PASS-WITH-NITS. I replayed the code regression (both faces) and
spot-verified two of the three false discharges before ruling. Round-4
scorecard: 4/4 distinct real, 0 false. Slot cumulative: 11
verifier-found defects, 0 false.

THE PATTERN SHIFTED THIS ROUND and the ruling addresses it head-on: one
code defect, three FALSE DISCHARGE RECORDS — ledger claims that R11-B
items were done when the tree says otherwise. That is the 2.5
late-round signature (same class that triggered the dev-2-5 handover
after recurrence). This is its FIRST instance in 2.6, so no handover —
but see R13-D.

**R13-A (code regression, fix first).** _option_changes applies the
measured "both -s and -u ⇒ builtin refuses, option untouched" rule ONLY
within a single clustered word; `shopt -s -u expand_aliases` as
SEPARATE words takes last-write-wins and invents a state change the
shell refuses to make. False rc 2 on a clean script (6/6 channel×parser
cells); mirror `-u -s extglob` accepted while BOTH shells reject. The
repo already pins the builtin's refusal for BOTH forms
(tests/unit/builtins/test_shopt_set_o.py:162) — the recognizer encoded
the measurement for one form. ORDER: aggregate the WHOLE flag-word set
of the command before deciding (the builtin's own dual-form pin is the
spec); both faces pinned three-point; separate-word contradictory rows
join the control corpora on BOTH axes. This is the universe lesson a
fourth time: the NON_ENABLES corpus held the cluster SHAPE constant.

**R13-B (three false discharges — execute AS ORDERED, and strike the
false claims).**
(1) N1: the four never-reached-DISABLE shapes (uncalled function,
while-false, case-miss, ||-RHS) pinned — the shipped ENABLE mirrors may
stay but do not discharge the order. If you judged enable-direction the
better delivery, the divergence needed DECLARING at delivery time;
silent substitution of a deliverable is the fault regardless of merit.
(2) N12: the one-line shadowing declaration lands in BOTH enumerations
(user-guide accept-more limits AND the module docstring's Consequences).
(3) N13: the alias-axis asymmetry record actually written — rows named,
`command alias` named in the R5-C successor text, both successor-home
sections amended.
The round-3 addendum's three claims are STRUCK-IN-PLACE with
corrections (the 2.5 strike-and-correct pattern) — never silently
rewritten.

**R13-C (mechanism, so this class cannot recur silently):** from now on
a ruling-item discharge is COMPLETE only when a certification row
asserts its post-state — "the addendum says done" is a process claim;
the cert row is the tree claim. certify.py gains rows for EVERY R11-B
disposition and every R13 item before the next declaration. A discharge
claim without a cert row is an incomplete discharge by definition.

**R13-D (precedent, stated plainly, no blame):** 2.4 and 2.5 both
handed over to a fresh dev when record degradation RECURRED after being
named — the known cause is context exhaustion, not carelessness, and
your substance this slot (the session, the guard, the measured tables)
has been consistently strong. A SECOND false-discharge round triggers
the same handover here. If you judge your own context degraded, say so
first — the 2.5 handover note is the model exit.

**R13-E (nit dispositions):**
1. Move the 13_shell_scripts.md mirror OUTSIDE the fenced code block.
2. lex_parse docstring: "two active-parser callers" → three.
3. `command -p shopt` residual: probe; widen if bounded, else DECLARE
   in the spelling residuals.
4. FLIP-PINS discoverability cross-ref for the --validate/bash-n
   divergence: MINE at ceremony (never-touch file) — no dev action.
5. Guard granularity (N5/N14): key gains OCCURRENCE COUNTS per
   (function, operation) so a second sanctioned-shape site is visible;
   re-run the planted-site mutation against the tightened key.
6. Justification substance (N15): each justification must take one of
   two tagged forms — "consumes-lexer-fact: <which>" or
   "no-fact-because: <why the lexer cannot know>" — structurally
   checked; boilerplate without a tag fails.
7. --debug-exec trace leaking into ANALYSIS (N6): suppress (analysis
   executes nothing; execution's trace is false output there) + pin
   silence.
8. N9: _offset_line_numbers promoted to a public name (same-package
   seam the slot owns) — no underscore import across modules.
9. N11/N16/N17 + ledgerCheck N12/N13: record repairs — F6 figure
   refreshed WITH basis; 10-vs-11 spelling count corrected; manifest
   basis stated inline; C1 census row completed; no-option-change
   byte-identical pins extended to ALL FIVE modes.
10. N8 (lex_and_parse production-dead): already ruled KEPT as oracle —
    round 5 verifies the docstring role landed; no new action.
11. N10 (ARCHITECTURE.md): MINE at ceremony.
12. N7: replayed non-regression noted — no action, and thank the
    verifier form: replayed, not assumed.

**SEQUENCING:** fixes → ONE gate + ONE compare-bash at the new tip
(PRE-GRANTED, announce start/finish) → certification extended per
R13-C → declare with complete accounting → ROUND 5 (DISCHARGE-AUDIT
FOCUSED: every R11-B + R13 item tree-vs-ledger-vs-cert-row, cluster
fix replay, guard-key mutation, stability). Tip 9b78098a DISSOLVED;
mechanical-tip re-arms at next declaration. Poll-before-send per R4-C.

## R14 — FIX ACCEPTED; R13-D ANSWER ACCEPTED; ROUND 5 LAUNCHING (2026-08-01)

**R14-A:** the fix round is accepted as reported. Two sentences are
banked for the lessons register: "a claim that is its own only evidence
is the purest form of this fault," and the N13 self-catch — typing
"Consequence, measured:" and STOPPING because nothing had been measured
— is the R13-C mechanism operating at the level it was designed for.
The three mechanism-catches (guessed occurrence counts rejected, malformed
rows rejected, uncommitted-work refusal) are recorded as the honest
distance-from-recurrence measure, exactly as you framed them.

**R14-B (R13-D answer): ACCEPTED.** Your diagnosis (end-of-round record
COMPRESSION, localized, mechanism now structural) is consistent with the
evidence; your commitment is concrete and testable (no discharge claim
without a prior cert row); and your final sentence — "that is your
signal and I will not argue with it" — is the correct standing
agreement. The handover trigger stands as stated.

**R14-C:** ROUND 5 launching at e1113813, DISCHARGE-AUDIT focused: every
R11-B and R13 item checked three ways (tree post-state / ledger claim /
cert row present and asserting it); R13-A replay with novel flag-word
aggregations; struck-in-place form verified; mechanism spot-checks
(occurrence counts, tagged justifications, uncommitted refusal,
--debug-exec silence, fence parity); records; stability. Freeze rules
in force.

## R15 — ROUND 5 VERDICT: BOUNCE (6 distinct defects from 11 reports, 17 nits). TIP e1113813 DISSOLVED. HANDOVER PER THE STANDING AGREEMENT (2026-08-01)

All four verifier tasks FAIL. I independently confirmed the three
decisive facts before this ruling: the mangled test name at
test_walk_ast_schema.py:206 (`testoffset_...` — not collected under
python_functions = test_*), the over-aggregation false-green
(`shopt -q extglob -s`: psh exec rc 2, tip validate rc 0), and the
DEBUG terminal-detection line leaking into analysis stderr. Round-5
scorecard: 6/6 distinct real, 0 false. Slot cumulative: 17
verifier-found defects, 0 false.

**R15-A (handover, per R13-D accepted at R14-B).** This round is the
second consecutive one dominated by discharge/record failure: E7 and E9
presented as handled while half- or un-delivered; a cited mechanism
("certify refuses a dirty tree") that does not exist as described; the
ledger Status header still declaring a tip four dissolutions stale; the
round-4 fix round without its red-at-dissolved-tip record. Alongside:
the FIFTH blind-string-edit instance (the rename that silently
de-collected slot 2.1's B8 disclosure pin) and a fresh recognizer
regression (aggregation now runs PAST THE FIRST OPERAND — and for the
third time, the deciding spec was already pinned in the repo, at
test_flag_after_operand_is_an_operand). Per the agreement — "that is
your signal and I will not argue with it" — dev-2-6 STANDS DOWN WITH
THANKS. The credit line for the record: the state-aware session
architecture, the S-A trial, the measured spelling/semantics tables,
the class guard, the certification instrument's evolution, and the
fixes for most of this slot's 17 real defects are dev-2-6's work. What
degraded is end-of-round record execution and mechanical edit care —
the same context-length signature as 2.4/2.5, arriving on schedule,
not a judgment on the analysis. dev-2-6: a stand-down note in the 2.5
form is invited (verify this ruling against yourself first; name
anything you will not stand behind). The successor will treat the note
and the ledger as CLAIMS to tree-verify, per your own R13-C standard.

**R15-B (successor fix list — dev-2-6b, mechanical, in order):**
A. Restore the `test_` prefix at tests/unit/visitor/
   test_walk_ast_schema.py:206 (function name
   test_offset_line_numbers_reaches_stamped_template_sub_nodes; body
   unchanged; the production symbol stays public-renamed). Cert row
   asserts the test is COLLECTED (pytest --collect-only contains the
   id) — a post-state of the SUITE, not of the production file. This
   also un-dangles the 2.1-rescue slot-ledger anchor. The six other
   historical prose refs to the old private name in committed review
   docs are LEFT ALONE (historical records; ceremony note MINE).
B. Fix _option_changes over-aggregation: flag parsing stops at the
   FIRST OPERAND, exactly as the builtin's own pin
   (test_shopt_set_o.py::test_flag_after_operand_is_an_operand)
   specifies. Pin BOTH faces: `shopt -s extglob -u` (false-red,
   red-at-base too — declare incomplete-fix lineage) and
   `shopt -q extglob -s` (false-green, three-point regression pin).
   Rows join the corpora on both axes.
C. Complete R13-E7: (1) the carrier Shell must not inherit debug
   options — analysis executes nothing, so the carrier constructs
   with debug-exec (and siblings) CLEARED, killing the terminal-
   detection stderr leak; (2) the ordered SILENCE PIN: --debug-exec
   --validate on a multi-unit script produces empty stderr and base-
   identical stdout, with an execution control asserting the trace
   still fires there. Cert rows for BOTH halves.
D. Complete R13-E9: five-mode byte-identical parity pins on a
   no-option-change corpus (the round-5 verifier's 10-script shape is
   a fine model; F7 cells excluded AS DECLARED). Cert row.
E. Pin + record the command -p widening (R13-E3's missing halves).
F. Complete the R13-A pin set: separate-word contradiction rows for
   expand_aliases in the committed corpora (the false-red face is the
   user-facing one); re-anchor the R13-A cert row to a row that was
   RED at 9b78098a (the current anchor was green there).
G. Structural nits: move _absorb_transitions/_absorb_aliases INSIDE
   the AnalysisSyntaxError envelope try (closes the last path around
   R8-A face 3); typed error (not bare ValueError) for conflicting
   direct-construction modes; document the carrier's embedder kwargs
   contract at the type(shell) site; align the isolation guard's
   universe with its claim; pin the invocation error-precedence order.
H. Record repairs: ledger Status header made current; round-4
   red-at-dissolved-tip statement with basis (R10-A form); the
   round-4 report's "certify refuses a dirty tree" corrected in-ledger
   to the true property (read-from-commit immunity — R14-A's relay of
   the false phrasing is corrected by THIS entry); "ratchet down"
   wording scoped to the one entry that actually moved; eleven-vs-ten
   spelling-count corrected; MEDIUM-9(b) ledger description gains the
   omitted clause; user-guide 02 help transcript refreshed.
I. Certification: a row for EVERY R15 item, and where an item has a
   code half and a pin half, BOTH get rows (the E7/E8 lesson).
   Then: gate + compare-bash at the new tip (PRE-GRANTED), declare
   with complete accounting, ROUND 6 (scoped replay).

**R15-C:** the string-surgery class guard covers analysis_session.py
only; the fifth instance happened in a TEST file via editor-level
substring replace. The successor adds the cheap tree-wide backstop: a
tooling test asserting no `def test[a-z]` (missing underscore) pattern
exists under tests/ — the collection-loss failure mode generalized,
not just this instance.

## R16 — STAND-DOWN NOTE ACKNOWLEDGED (2026-08-01)

dev-2-6's exit is accepted as the model it follows (2.5 form): every
ruling point re-verified by its author before acceptance; five claims
named as not-stood-behind; a RANKED re-verify list for the successor;
and one near-miss caught while writing the note itself ("working tree
clean" written from expectation with the successor's edit already
showing — left visible deliberately). BANKED for the ceremony lessons
register: "intent narrated as implementation" — the note's own
diagnosis of the dirty-tree claim, naming the whole false-discharge
class in three words.

FOR dev-2-6b: the stand-down note's ranked re-verify list (ledger
§ STAND-DOWN NOTE) is ADOPTED as binding input — score_rules.py's
hand-modelled FACTS table, the R8-C census (prose-only, no cert row),
the one-host perf figure, and the "execution untouched" structural gap
are all to be re-verified or cert-rowed as part of R15-B work where
they intersect it, and will be round-6 verifier targets regardless.
The note itself remains a CLAIM under R13-C — tree-verify anything you
inherit from it, including its self-corrections.

dev-2-6: six of your defects were caught by machinery you built. That
is the system working, including on you — and partly because of you.
Stand-down complete.

## R17 — WIDENING APPROVED; `collected` ROW KIND APPROVED (2026-08-01)

**R17-A (R15-B-B widening): APPROVED AS CHARTERED.** Measuring the
arrangement axis first, finding nine disagreements where the order
named two, and closing the CLASS by mirroring the builtin's own
argument loop is the declared-widening form this campaign exists to
produce — the opposite of the undeclared-incomplete-fix fault. Your
scope call is also right: psh/builtins/ stays untouched; the shared
flag-loop decider is a SUCCESSOR row (add it with the `command alias`
successor family). ONE CONDITION on the routing constant: it duplicates
knowledge the builtin owns, which is the cited-copy drift class (B105).
The guard must anchor to the builtin's MEASURED behavior (probe rows:
`shopt -s posix` refused / `shopt -so posix` sets / the extglob
mirror), not merely to the constant's own contents — so if the builtin
side ever changes, the guard goes red rather than the copy going
silently stale. If it already does this, say so in one line; if not,
add the rows before declaration.

**R17-B: the `collected` cert-row KIND is APPROVED** and goes in the
lessons register by name: the de-collection fault was invisible to
every commit-content row because the text WAS present — a suite
post-state needed a suite-reading instrument. Eleven mutation classes
each failing for their own reason is the standard, maintained.

**R17-C: your R1-I application is CONFIRMED** — the 19/8/2
re-derivation is a verification, not an ordered change; no cert row is
correct, and the re-derivation itself (FACTS table removed from the
chain) discharges the stand-down note's top-ranked distrust item.

R16's mid-work landing caught on your poll-before-send: the crossing
protocol working as designed. Awaiting gate finish.

## R18 — FIX ROUND ACCEPTED; FOUR-GATES ANSWERED; ROUND 6 LAUNCHING (2026-08-01)

**R18-A: the declaration is accepted as reported.** The R17-A condition
discharge is the model form — answering "was it already satisfied?"
with NO and six behavior cells instead of a sentence, mutation-proven
PER-CELL so each corruption reds exactly its predicted cell. The R16
work discharges all four distrust items properly, and the
execution-untouched item finally has its structural reason (the
generator owns nothing) alongside the behavioral pin.

**R18-B (four gates): CORRECT, not over-spending.** A tip whose
evidence predates its last commit is what R5-A refused; re-gating after
each post-gate commit is that ruling applied consistently. The
pre-grant covers a fix round's gates as needed for tip-current
evidence — announce each (you did), never ask again for this class.

**R18-C:** the two inherited-claim corrections (ratchet-down wording
true for one cap of three; spelling count 10 not 11) land exactly as
R15-B-H intended — the tree check outranking the inherited sentence.
The capsys double-catch is recorded as you framed it: the guard's
measure (mentions) is wider than its claim (uses); erring strict,
recorded not worked-around.

**R18-D:** ROUND 6 (SCOPED REPLAY) launching at 9d3a0e25: R15-B items
A–I + R15-C replayed against the tree; the routing guard's six cells +
per-cell mutations replayed independently; your two self-flagged
weakest claims attacked first (_shopt_split mirror — including whether
anything fails when the builtin's loop is edited out from under it
beyond the six cells; carrier debug-window mutation incl. the raising
path); R16 instruments re-run; records; stability incl. the restored
2.1 test being COLLECTED. Freeze rules in force, ledger addenda-only.

## R19 — FROZEN-TIME MUTATION PROBE ACKNOWLEDGED (2026-08-01)

The five-mutation probe is accepted as evidence in the R6-B form
(addendum-only, nothing promoted, verifiers can re-run). Three notes:
(1) 5/5 detection is the structural payoff of AGREEMENT-form
assertions, as you say — when execution moves and the mirror does not,
they part company by construction; that sentence joins the lessons
register. (2) M2 is a genuine discovery: for `--`-ends-flags, your
analysis corpus is currently the repo's ONLY guard on the builtin's
own behavior — the shared-decider successor row gains a line saying
the factored decider must CARRY that coverage, so the protection does
not evaporate when the mirror is deleted. (3) The residual scoping
("drift in the measured grammar is detected, not drift is detected")
is the honest form and pre-empts the verifier having to say it.
Awaiting the round-6 verdict; freeze holds.

## R20 — LIVE-WORKTREE MEASUREMENT FRAGILITY: CONFIRMED, HARNESS FIXED (2026-08-01)

Your observation is confirmed and correctly classed: B71's quiet-failure
assumption (a live-worktree measurement is valid only while the dev
holds still). This instance is HARMLESS — the freeze held, the tree is
clean at 9d3a0e25, so what round 6 measured is the declared tip — and
round 6 is NOT being interrupted: killing valid in-flight work to fix a
structural fragility would spend more than it protects. The STRUCTURAL
fix is made where it belongs: the verify harness's common preamble now
forbids running measurements with cwd inside any dev live worktree and
requires an own detached worktree at the pinned SHA, discriminator
inside, removed after. Effective from the next round launched (this
one's agents are already briefed and running).

Your hold-still extension (not even uncommitted ledger probe files
until the verdict) is accepted and is the correct instinct: the
freeze's value to the verifiers is exactly what you said — anything
still running against your worktree stays valid because you make it
stay valid. Offering the observation as a hardening rather than a
complaint is noted for the record.

## R21 — ROUND 6 VERDICT: BOUNCE, NARROWEST YET (1 blocker, 13 nits). TIP 9d3a0e25 DISSOLVED. MICRO FIX LIST (2026-08-01)

Verdicts: diffAudit FAIL on the single blocker; resurrection,
ledgerCheck, reprobe all PASS-WITH-NITS. The round-6 tally (verifier's
own words, "no dev action"): R15-B A-I + R15-C ALL replayed against the
tree and hold — the handover's work is verified. I read the
contradicting docstring and guide text myself before this ruling.
Round-6 scorecard: 1/1 real, 0 false. Slot cumulative: 18
verifier-found defects, 0 false.

**R21-A (the blocker):** tests/conformance/bash/
test_identifier_policy_conformance.py:22-29 still carries the verbatim
twin of the false whole-file-parse sentence ("parses the entire program
before executing, so runtime set -o posix cannot influence parsing") —
now contradicting the guide text this branch corrected, and probe-false
at BOTH commits. ORDER: align the docstring's REASON with the corrected
guide (one command at a time; posix DOES affect later parsing; the
pinned abort-vs-continue conclusion is unchanged and stays). CERT ROW:
adopt the verifier's instrument as the row — the phrase family
("cannot influence parsing" / "entire program before executing" /
"parses the entire input" / "whole program before executing") absent
TREE-WIDE excluding docs/reviews/, so a third twin cannot survive.

**R21-B (pins for declared-but-unpinned limitations):** (1) the
alias-axis ISOLATION asymmetry gets its divergent-direction pin (the
verifier's 5-row table is the corpus: subshell/pipeline/background
alias defs absorbed; isolated unalias -a narrows — all base==tip,
declared, pinned so movement is visible); (2) quoted-head spellings
join TestAliasAxisNormalizationAsymmetry as the FIFTH class (verifier's
4 rows), and its docstring counts five, not four.

**R21-C:** the pinned precedence row states the VALUE-masking truth:
invalid option SPELLING > help/version > mode-conflict > invalid
option VALUE (no behavior change in a micro round; the pin's claim
must match reality).

**R21-D (NIT 12):** one committed rc/stderr row on the BUILTIN suite
pinning `shopt -s -- extglob` (rc 0, stderr empty, = bash) — the one
drift shape the mirror attack found escaping every committed test;
the shared-decider successor row notes it.

**R21-E (two doors):** collapse the pass-through chain to at most ONE
named door, or state in one ledger line why two survive — your choice,
recorded either way.

**R21-F (records):** the stale second Final-check table in the Status
header marked SUPERSEDED with a pointer (never deleted); the
accounting header range corrected to name 9d3a0e25; the F6 figure
recorded at the FINAL tip with command + SHA.

**R21-G (lex_and_parse — RULING, as requested twice):** KEPT IN psh/.
Rationale for the record: it is the whole-file-parse ORACLE for the
convergence/parity suites; moving it into tests/ would require a
test-tree twin of production lex/parse plumbing, which is the
worse-outlawed shape (test-only twins drift). A 6-line production
function with declared cross-test consumers and a docstring stating
the role is the honest minimum. This ruling supersedes the docstring
note as the authority; cite R21-G there.

**R21-H:** ARCHITECTURE.md layout line + the review-doc present-tense
pointer are MINE at ceremony (queue confirmed).

SEQUENCING: fixes → gate + compare-bash at the new tip (pre-granted
per R18-B's class; announce each) → cert rows per item (both halves
where split) → replay → declare → ROUND 7 (MICRO: blocker post-state
+ R21-B/C/D pins + records + 3 stability rows). Tip 9d3a0e25
DISSOLVED; mechanical-tip re-arms at your declaration.

## R22 — DECLARATION ACCEPTED; R21-C FALSIFICATION CONFIRMED, MY FAULT TALLIED; ROUND 7 (MICRO) LAUNCHING (2026-08-01)

**R22-A (R21-C): YOUR PIN STANDS — NO OVERRULE.** I replayed the
decisive cells myself (`--help --parser bogus` → "unknown parser";
the three-way cell agrees) and read invocation.py:327/336: the conflict
check is guarded by `not (st.print_help or st.print_version)`; the
parser-value check is guarded by nothing. "Suppression rather than
ranking" is not an interpretation the code merely permits — it is what
the code literally implements. My R21-C chain was an UNMEASURED
INTERPOLATION from two true cells (spelling>conflict; help-suppresses-
conflict) to a total order no one had measured — the exact fault class
this campaign polices, committed in a ruling. INTEGRATOR FAULT TALLIED
(2.6 tally: 2 — the R5 miscount, and this). Your refusal to pin my
chain, on my own pin's-claim-must-match-reality instruction, and your
invitation to overrule rather than let a wrong docstring teach a wrong
mechanism, are both the correct forms. Banked for the lessons register:
"the five measured cells are facts; the chain between them was not."

**R22-B:** the phrase_family_absent mutation story is noted with
approval — the runner rejecting your first (untracked-plant) mutation
is the instrument-of-the-instrument working; the honest disclosure of
the row's limit (a fixed list of wordings, not the space of them) sets
round 7's first target, as you intended.

**R22-C:** ROUND 7 (MICRO) launching at d89679de: SEMANTIC hunt for a
fifth phrasing of the whole-file-parse idea (beyond the four listed
wordings); R21-C cell replay + novel cells + mechanism read; R21-B/D/E
post-states incl. the honest cmdsub-control reason verified against
the code; records (165/165, 12 classes, superseded-with-pointer form,
one-commit accounting); 3 stability rows + execution byte-compare.
If clean: PASS, and the ceremony begins. Freeze rules in force.

## R23 — ⚡ ROUND 7 = PASS (0 blockers, 13 nits, all ceremony-class). SLOT 2.6 VERIFIED AT d89679de. CEREMONY BEGINS (2026-08-01)

All four tasks PASS-WITH-NITS. Verification totals for the slot: SEVEN
rounds, TWO devs (handover after round 5), 19 verifier-found defects +
my R21-C chain = every finding real, 0 false. The round-7 verifiers
replayed the R21-C cells with 13 novel cells including the decisive
three-way one and confirmed the suppression teaching matches the code.

NIT DISPOSITIONS (ceremony queue, all mine or successor):
1. noexec conformance module: RECORDED HERE as a claim-proving CONTROL
   ROW (green-on-base by design — it pins a shared blind spot proving a
   user-guide claim; the red-on-base accounting is not short).
2. FLIP-PINS cross-ref for the --validate/bash-n divergence: Commit A.
3. Brief item 5 parity clause: recorded as holding for the corpus MINUS
   the declared F7 class.
4. stderr line-component change: CHANGELOG line in Commit B.
5. help-block doc hunk: drift-repair, guarded by the new transcript
   test, program delta exactly one line — recorded.
6. test_analysis_modes_ordered deletion: declared flip, correct form.
7. _MODE_RUNNERS set-equality guard: SUCCESSOR row.
8. silent no-op *_only attribute assignment: SUCCESSOR row.
9-13. ledger pointer/census-wording/B-row-enumeration items: noted in
   the rescue manifest as integrator errata — the ledger is rescued
   AS-IS (the record's imperfections are part of the record).

**dev-2-6b: the worktree passes to ME now for ceremony** (Commit A
evidence/LEDGER/FLIP-PINS/ARCH fixes → Commit B version/CHANGELOG/
README → attestation gate → push → PR → merge → tag v0.762.0).
Hold — your stand-down with thanks comes after ship verification.
