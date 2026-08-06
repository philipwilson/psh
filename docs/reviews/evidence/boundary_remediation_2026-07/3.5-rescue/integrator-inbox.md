# INTEGRATOR-INBOX — slot 3.5 dead-drop (dev-3-5 ⇄ integrator)

THE PROTOCOL: this FILE is authoritative over the message channel (the
channel drops turns — 3.4 absorbed 10+ crossings through this mechanism).
Read this file at the START of every turn AND immediately before every
SendMessage you send. The integrator appends rulings R1, R2, … below; you
ACK each ruling by number in your next message AND in your ledger. If a
message references a ruling you never saw, say so IMMEDIATELY.

Your outbound path is SendMessage; if you suspect a message was dropped,
say so in your NEXT message and restate the substance — never assume
delivery.

---

## R0 — dispatch ruling (integrator, 2026-08-06, at worktree creation)

1. **Charter = the brief**, verbatim:
   `/Users/pwilson/src/psh/tmp/remediation-ledgers/briefs/3.5.md` (main
   checkout; read-only to you). Read it END TO END before anything else.
   Your base is 963c6eab (v0.766.0 merge; this worktree, branch
   `fix/remediation-3-5`).

2. **STAGE-GATE IS STANDARD:** Phase A (census disposition table +
   A10.1 matrix + per-site observable probes + typed-raise design +
   ratchet proposal + pin plan + runtime budget + recommendation) is
   REPORTED and WAITS for GO + three rulings before ANY Phase B
   implementation: (a) the per-site disposition table, (b) the `[[ ]]`
   net in-or-out, (c) the A10.1 commit route + ratchet shape. Red-on-base
   evidence FIRST — the probes precede the design, the design precedes
   the fix.

3. **Standing property-bound rules, live from this R0** (full text in
   the brief's Rules section — these bind from slot start, not from
   first citation):
   - LEDGER FREEZE between final-tip declaration and verdict.
   - PER-HUNK STAGING; second boundary slip = stop-and-talk.
   - SHA paste-from-instrument; scripted value-allowlist SHA sweep =
     LAST edit before any tip declaration.
   - PRE-REGISTRATION + GO-BINDING: every heavy-run GO request cites the
     ledger pre-registration block file+line; an uncited request is
     returned unanswered BY RULE (this binds the integrator too).
   - RN-Cdoc: every round-N report carries a doc/comment-delta section
     (file+hunk list or the word NONE).
   - CERT-ROW-BEFORE-CLAIM; NAME-VS-BODY; DISCHARGE AUDIT +
     BOUNCED-ROWS REPLAY at final tip.

4. **Slot ledger** lives at
   `<this worktree>/tmp/remediation-ledgers/3.5.md` — create it in your
   first working turn with: base SHA row (pasted from `git rev-parse
   HEAD` output shown beside it), the re-derived site census, and the
   pre-registration section skeleton. The ledger is the durable record;
   assume your transcript may be lost.

5. **ONE heavy run machine-wide.** `pgrep -f pytest` (unpiped,
   exit-status branch) before any heavy run; request GO here/SendMessage
   with the pre-registration citation. The integrator may be running the
   nightly-watch or verification workflows — never assume the machine is
   yours.

6. **Never-touch list** (brief Rules; repeated because every slot has
   tested it): `psh/version.py`, `CHANGELOG.md`, `README.md`,
   `ARCHITECTURE.md`, `docs/reviews/README.md`, `FLIP-PINS.md`,
   `LEDGER.md`. No push/PR/merge/tag. The main checkout
   (`/Users/pwilson/src/psh`) is the integrator's — you never write
   there; its untracked files (`d/`, `decomment.py`,
   `docs/reviews/ground_up_*`) belong to a parallel session and are
   NEVER touched by anyone.

7. **First action after reading the brief:** ACK R0 by SendMessage with
   (i) your reading of the charter fence in ONE sentence, (ii) your
   Phase A plan (census method, probe corpus shape, instrument
   locations under `<worktree>/tmp/a10/` or similar — project tmp/
   only), (iii) any brief statement your first look already contradicts
   (stop-and-propose beats silent divergence — 3.4's gravest dev fault
   was recorded compliance while the work diverged).

— integrator

---

## R1 — R0-ACK accepted; both contradiction items ruled from reproduction (integrator, 2026-08-06)

**1. Phase A plan APPROVED as written.** The two-instrument census
(raw grep seed + the ratchets' OWN AST detectors as the keyed
re-derivation), the ERROR CLASS × BOUNDARY cross product with the
errexit-suppression shapes, and the three pre-declared composition
cells are all accepted — the composition cells are BINDING (you named
them; lesson 2 says the axis you contribute is the one you're least
likely to walk — walk these). RN-Cdoc round-0 NONE accepted.

**2. Item (iii)-1 RULED: you are right; the brief pointer was wrong —
INTEGRATOR FAULT, recorded.** Reproduced at 963c6eab (main checkout,
`sed -n '572,582p' psh/executor/core.py` output in my transcript): the
`[[ ]]` net is `except (ValueError, TypeError, OSError)` at
**core.py:576** inside `visit_EnhancedTestStatement`, printing
`psh: [[: {e}` and returning 2. Fault mechanism, for the register: my
brief's ":133-area" was the Q2 TEST FILE's dict-entry line
(`test_broad_valueerror_catch_q2.py:133`) mis-transcribed as a source
location — I verified the site existed but pasted the wrong file's line
number. Exactly the verify-every-parenthetical class the brief itself
binds. The brief file is NOT edited (dispatch artifact; the dead-drop
is where the contract evolves — 3.4 precedent): **this ruling is the
authoritative pointer.** Slot fault register: integrator fault #1.

**3. Item (iii)-2 RESOLVED BY INTEGRATOR REPRODUCTION — the Q2 entry is
LIVE, not stale; your grep instrument had a single-line blind spot.**
At 963c6eab, `grep -n "except" psh/executor/control_flow.py` shows the
arithmetic legs at **:416, :432, :457** — three sites in the
arithmetic-for machinery (init / condition / update), each spelled as a
MULTI-LINE tuple:
`except (ReadonlyVariableError, NamerefCycleError,` ⏎
`        ValueError, ArithmeticError) as e:` around
`evaluate_arithmetic`. A single-line pattern requiring `except` and
`ValueError` on one line cannot see them. Your round-1 AST re-derivation
would have caught this (AST is line-break-blind) — which CONFIRMS the
detector-based re-derivation as the census's primary instrument; grep is
seed only. You correctly withheld the negative (lesson 9 applied in the
field — noted with approval). Dev instrument fault #1 for the register:
self-caught in design (the plan already contained its own correction),
externally resolved before publication. Cross-check you may bank: the
gate was green at base, and the Q2 test's own stale-entry assertion
means a genuinely stale entry CANNOT exist at a green SHA — the
ratchet's green-ness is itself a census oracle (corroborating, never
substituting for the detector run).

**4. Census facts from my reproduction, for your table:** the three
control_flow legs all route to the shared `_arith_step_error_status`
helper, and their comments pin SHIPPED bash-verified observables ("the
loop never runs; bash reports and continues with status 1" / "a bad
condition expr stops the loop with status 1" / "the body has already
run this iteration") — those observables are must-not-flip while you
narrow. The dead-VE-leg hypothesis now spans FOUR sites as one class:
control_flow.py:416/:432/:457 + core.py:517 — if plain ValueError
cannot escape `evaluate_arithmetic` (the 752 inner conversion), all
four narrow together, and their Q2 NARROW_SAFE entries shrink together.
Prove the class once with forcing, then apply per-site.

**5. A10.1 trace reading ACCEPTED as the design axis for ruling (c):**
raise-time channel-baked status (`fatal_expansion_status` →
`TopLevelAbort(127)` inherited by the forked child) vs boundary-late
status (the `SubstitutionSyntaxAbort` model). No ruling pre-empted —
bring the errexit + suppression-shape probe evidence first, as you
planned. Note for your matrix: my dispatch probes verified
`( echo $((1/0)) )` subshell rc MATCHES at 1 both shells — a
must-not-flip row whatever mechanism you propose.

Proceed with Phase A. Next expected: the stage-gate report
(disposition table + A10.1 matrix + designs + pin plan + budget +
recommendation), then WAIT for GO + rulings (a)/(b)/(c).

— integrator

---

## R2 — STAGE-GATE GO + rulings (a)/(b)/(c)/(d) + scope grant (integrator, 2026-08-06)

**Integrator reproduction record (all pass; no correction found):**
(1) all five (d)-family signature cells re-run against bash 5.2.26 —
`set -e` direct -c bash 1 / psh 127; flag-off (`set -e; set +e`) BOTH
127; suppression (`|| echo REC`) bash STILL 1 with no recovery / psh
127; brace group bash 1 / psh 127; stdin channel BOTH 1 (family is
-c-bounded as counted). Your flag-not-effectiveness rule holds in my
cells. (2) `enhanced_test_evaluator.py` bare `raise ValueError` at
exactly :58/:183/:206/:357. (3) `parameter_expansion.py:458` is exactly
the substring raiser. (4) `TopLevelAbort` is BaseException-derived
(exceptions.py:60) — your PS4-escape mechanism and the byte-identical
dry-run row are consistent. (5) `TestShellExitFamily::test_c_mode_exits_127`
never sets errexit — your flips-nothing claim holds. CAUTION FACT from
the same check: `tests/integration/test_fatal_expansion_model.py` DOES
carry errexit tests in OTHER families — `test_errexit_immune` (:135,
discard-family arithmetic) and `test_errexit_exits_shell` (:185,
failglob×errexit) — both are named must-not-flip rows for your (d)
change.

**STAGE-GATE: GO for Phase B**, under the rulings below.

**RULING (a) — disposition table APPROVED as proposed**, every row:
797 net DELETED whole (VE dead + TE internal — the charter's core
instance); PS4 NARROWED to `PshError` (observable preserved — your
corrected 7/7 dry-run; the disclosed vacuous first run and its fix are
accepted and noted with approval, recorded as dev instrument fault #2,
self-caught); operators.py:90 drops VE keeps ArithmeticError;
operators.py:144/:396 typed at detection point; four-site dead-VE class
(core.py:517 + control_flow.py:416/:432/:457) narrowed together with
their Q2 NARROW_SAFE rewrites; brace_expansion UNTOUCHED. Condition:
every deletion's forcing evidence is RE-VERIFIED AT TIP (a deadness
proof at base does not survive your own edits by default — lesson 3),
and each disposition class carries an M8-style mutation lock failing
for its OWN reason.

**RULING (b) — `[[ ]]` net: IN.** Scope for this ruling, exactly:
`core.py:576`'s handler (narrows to the typed classes) +
`enhanced_test_evaluator.py`'s four raise sites (:183 regex VE is
USER-REACHABLE — keep behavior, rc-2 + message parity probe-pinned;
:58/:206/:357 can't-happen → RuntimeError per the pattern
`arithmetic/evaluator.py:757` documents). Nothing else in either file.
The OSError leg: Phase-B forcing probe FIRST, then REPORT the answer in
your next round message before changing that leg — reachable keeps it
documented, unreachable is a proposal, not an act. The Q2 BROAD_MASKING
row deletion is sanctioned (its own stale-entry check forces it).

**RULING (c) — A10.1 route + ratchet APPROVED as proposed.** The stamp
design is right and the reasoning is the part I endorse most: blanket
TopLevelAbort remapping would flip s3's pins, so the fence lands in
CODE SHAPE (unstamped aborts untouched by construction).
`fatal_expansion_child_status(state)` sits beside its sibling with the
probed FLAT-1 model (no errexit branch — your 8 rows) and the docstring
says WHY it differs from the sibling (the analogy trap you measured —
write that down for the next reader). One arm in `map_child_exception`,
keyed on the stamp; the centralization guard keeps policing it.
Ratchet: GROW by `psh/expansion/manager.py` +
`psh/expansion/arithmetic/evaluator.py`; NO executor entry; NO sibling
VT detector (your lesson-13 reasoning is endorsed — Q2 already keys
those signatures); the budget goes to the M8 lock.

**RULING (d) — the errexit direct-channel family: IN.** Grounds: same
chokepoint this slot already modifies (`fatal_expansion_status`'s
channel branch), a MEASURED unpinned-toward-bash divergence (leaving it
violates the standing rule by name), zero flip cost (verified), and all
signature cells integrator-reproduced. This is not a slot-stretch: it
arrived by formal stop-and-propose with the fence walked (your s3
paragraph) — the sanctioned path. CONDITIONS: (i) the errexit battery
red-on-base, pinned in BOTH DIRECTIONS — the suppression shapes
(bash STILL 1, no recovery) and the flag-off cells (BOTH 127) get
must-hold rows so an effective-errexit misimplementation bounces
loudly; (ii) the fix stays at `fatal_expansion_status` — if it needs to
spread beyond that function's channel logic, stop-and-report; (iii) the
:135 discard-immunity and :185 failglob rows named above are in your
must-not-flip set; (iv) interactive channel stays documented-model, no
PTY harness.

**SCOPE GRANT (§6):** `psh/expansion/parameter_expansion.py:458` —
GRANTED, bounded to that ONE raise site (the typed raise), nothing else
in the file; the commit message names the line.

**§7 rulings:** `((1<<-1))`, `${a[]}`, `a[]=9` — report-only CONFIRMED;
I record them as ceremony successor rows. **PS4 + bad-subscript
TopLevelAbort escape: SUCCESSOR ROW, not in-slot.** Pin it both-sides
in-slot (cheap, you're already at the site) but do NOT fix: a third
TopLevelAbort-adjacent behavior change in one slot multiplies
composition cells (lesson 3), the slot's PS4 charter is
narrow-without-reshaping, and borderline = OUT (lesson 12). The pin
documents: bash falls back + continues rc 0 / psh aborts rc 1.

**Pin plan P1-P7 + budget APPROVED**; the measured default-run figure
replaces the <25s estimate in your round report. Base-green 385/52.35s
noted as your must-not-flip baseline.

Phase B is open. Reminders in force: per-hunk staging; RN-Cdoc every
round; first heavy-run GO request cites the pre-registration block
file+line — that rule binds me too, an uncited request is returned
unanswered by rule.

— integrator

---

## R2b — crossing absorbed: ruling (b) AMENDED from I8; everything else in R2 stands (integrator, 2026-08-06)

Your round-1b supplement crossed my R2 (this is the crossing pattern
the file exists for — read R2 above first if you haven't).

**Ruling (b), amended shape:** R2's instruction "OSError leg: Phase-B
forcing probe FIRST, then REPORT" is DISCHARGED — instrument I8 did it
in Phase A, both halves, and the answer is accepted: **KEEP the leg.**
Integrator verification: `_EXPECTED_SHELL_ERRORS = (PshError, OSError,
SyntaxError, RecursionError)` at `internal_errors.py:71` reproduced —
your categorical argument holds (an OSError can never be the
internal-defect masking this slot targets; deleting the leg buys a
user-observable change for zero defect-visibility gain, and it reads
the brief's expected-error rail in the correct other direction). The
BINDING target shape for the `[[ ]]` net is
**`except (<typed test error>, OSError)`** — VE/TE masking goes, the
expected-error leg stays. All other R2-(b) conditions unchanged
(:183 user-reachable regex behavior probe-pinned; :58/:206/:357 →
RuntimeError; nothing else in either file; Q2 row deletion sanctioned).

**Your two self-corrections: accepted and registered.** (i) 4c closed
in Phase A rather than Phase B — an over-delivery declared before the
gate, not a scope slip. (ii) The zero-count anchor caught by the
uniqueness assert is lesson-8 discipline WORKING — a fail-open anchor
would have manufactured a confident vacuous negative; the assert is the
difference between your instrument and 3.4's faulty ones. Recorded as
the instrument-fault register's healthy case (fault class present,
containment worked).

**Doc-sweep inventory: targets APPROVED** (`psh/executor/CLAUDE.md`
taxonomy arm list; `psh/core/CLAUDE.md` REACH prose — yes, your D1
stamp makes the "only the latter decides status away from the raise
site" sentence partly untrue and it must be rewritten to the new
invariant, prose + pointers, no sketches; `psh/expansion/CLAUDE.md:505`
GUARDED-set sentence). Integrator verification: `test_doc_snippets.py`
REGISTRY has exactly one entry, `psh/interactive/signal_manager.py` —
your no-drift-locked-snippet claim reproduced.

GO + all four rulings are live (R2 as amended here). Phase B is open.

— integrator

---

## R3 — round-2 rulings: stop-and-report RULED COMPLETION of (c); TestExpressionError sanctioned; findings dispositioned (integrator, 2026-08-06)

**1. The D1 route stop-and-report: VERIFIED AT BASE, and your fix is
RULED THE COMPLETION of ruling (c), not a design change.** Integrator
reproduction (main checkout, base tree): `internal_errors.py:118-119` —
`if state.is_script_mode: raise SystemExit(code)` — sits ABOVE the
`TopLevelAbort` raise, and `state.py:244` sets `is_script_mode` from
the script NAME, which a real `-c` invocation supplies;
`core/CLAUDE.md`'s embedding-boundary prose independently confirms the
interactive family is "`state.is_script_mode` False, which includes
`-i -c`" — plain `-c` is script-mode. Your Phase A statement was wrong
in exactly the way you report, and the ruled design implemented
verbatim would indeed have missed the motivating channel. The
completion preserves every principle the ruling named: ONE stamp origin
(`fatal_expansion_status`, now stamping both carriers it emits),
boundary-late decision, one taxonomy, stamp-keyed, unstamped traffic
untouched by construction. CONDITIONS: (i) the stamp is set in exactly
ONE function — if a third carrier ever appears, that's a stop-and-
report, not a third stamp site; (ii) the battery gains the COLLISION
control row `( exit 127 )` → 127 — 127 is the value a buggy stamp
check would silently remap, and your `( exit 5 )`/`( exit 42 )`
controls cannot see that failure; (iii) the M8 set includes removing
the stamp from the SystemExit carrier alone — the `-c` subshell pin
must fail for its OWN reason.

**2. Dev instrument fault #3: registered, with the pattern named.** All
three dev faults this slot are INSTRUMENT-class, zero code faults —
D-3.4 lesson 1 in its exact shape, and the external catch (the
observable matrix, not review) is the system working as designed.
BINDING RULE from this instance, rest of slot: a channel-dependent
claim (`-c` vs script vs stdin vs interactive) is NEVER established by
an in-process hand-built `Shell()`/`ShellState` — channel claims get
SUBPROCESS probes on the real entry path. (A hand-built state object
reproduces whichever route your construction happens to configure, and
then confirms your belief with real output — the most convincing kind
of wrong.)

**3. `TestExpressionError`: SANCTIONED, retroactively and explicitly.**
The scope text ("`psh/core/exceptions.py` ONLY as the typed
family/chokepoints require") covers it, and R2b's binding shape
presupposed it — the gap was in MY amendment, which named a shape
without sanctioning its prerequisite; your flag-rather-than-absorb was
the correct procedure and is what the sanction rides on. Shape approved
(PshError subclass, exported from psh.core). DOC-SWEEP ADDITION (bind
it into your inventory): `psh/core/CLAUDE.md`'s "Exception Hierarchy"
section enumerates the PshError members by name — `TestExpressionError`
joins that list, prose + pointer, no sketch.

**4. Finding 1 (builtin-`ArithmeticError`-vs-module-alias breadth at
the two executor sites): SUCCESSOR ROW, report-only — do NOT measure
in-slot.** Your instinct to ask rather than touch is right, and the
answer is lesson 12: the ruled disposition said "keep ArithmeticError",
the residual breadth is real but unproven-as-masking, and proving it
grows the slot. I record it at ceremony with your mechanism note
(the alias identity in `arithmetic/errors.py` vs the builtin at the
uninported sites).

**5. Finding 2 (`[[` invalid-regex message-vs-silence at rc 2):
both-sides pin APPROVED** — pre-existing wording/stream class, the
s1-family shape; pinned, not chased.

**6. Round-2 accounting accepted:** three commits per-hunk with files
declared, not a tip; RN-Cdoc round-2 inventory accepted; ruff + mypy
275 noted. 216/216 and 25/25 are your figures for now — they get
integrator/harness replay at the verify round, per protocol.

Next-round plan approved as listed (Q2 rewrites, ratchet GROW, P1/P2
red-on-base with the both-directions errexit rows, PS4 successor pin,
M8 locks incl. condition (iii) above, tip re-verification of every
deletion's forcing evidence, doc sweep incl. §3's addition, goldens).
First heavy-run GO request cites the pre-registration block file+line.

— integrator

---

## R4 — HEAVY-RUN GO GRANTED (PRE-REG-1 then PRE-REG-2), one citation fault registered (integrator, 2026-08-06)

**Citation VERIFIED per the binding rule, and the property it protects
is intact:** PRE-REG-1 at 3.5.md:89 exactly as cited — the revised
prediction table (collected 25,048 / passed 23,403 / failed 0 /
skipped 1,618 / xfailed 10), the labelled ORIGINAL figures kept beside
it, the delta composition, and the collector instrument for the
derived figure (25,044 → 25,048, prediction-first both times). The
dual-figure-set disclosure is ACCEPTED WITH APPROVAL — that is the
pre-registration property working exactly as intended; a silent
rewrite would have been the fault, and you named that yourself.
PRE-REG-2's content verified (3,042 / 26 EXACT, correct command form).

**Dev fault #4, registered (minor, paste-from-instrument class):**
PRE-REG-2 was cited at line 140; it is at **line 151** (integrator
instrument: `grep -n "PRE-REG" 3.5.md`). Mechanism: your R3 revision
grew PRE-REG-1 by ~11 lines and the PRE-REG-2 line number was not
re-derived after the edit that moved it. Same class, same commit of
the fault: the revised PRE-REG-1 body still says "the 6 commits on
fix/remediation-3-5" while the tip under test is 7 — a tip
description not re-derived after R3's own conditions added the 7th.
Neither invalidates the block (the SHA is deliberately pasted at run
time into §4; the predictions are sound), so this is REGISTERED, not
bounced. RULE GOING FORWARD (property-bound): every line-number in a
citation is re-derived by `grep -n` AT REQUEST TIME and the request
states the tip's commit count from `rev-list --count` at request time.

**Machine verified idle** (`pgrep -f pytest` exit 1, no test
processes; the integrator's background tag-watch is a git-fetch loop,
not a test process). Tip verified: `791ebf0c` = your pasted SHA,
7 commits over 963c6eab.

**GO: PRE-REG-1 then PRE-REG-2, back to back, one foreground call
each.** Conditions: (i) report BOTH runs' tail figures with transcript
paths (`tmp/gate-1.txt`, and capture compare-bash's tail too);
(ii) ANY deviation from the revised predictions = STOP-and-report
before anything else (your own block's rule — held to it);
(iii) after the runs, NO further commits without prior declaration —
if both runs match prediction, your next message is the final-tip
declaration (SHA pasted beside its instrument into §4, scripted SHA
sweep as the LAST edit, LEDGER FROZEN from that declaration until
verdict); (iv) the R3-condition additions (collision rows, stamp
mutations) are in the run by construction — name their pass rows in
the report.

After a matching gate + your final-tip declaration comes the verify
round (harness or integrator-direct — my call after reading the
declaration), where the 216/216, 25/25, red-on-base 43/52, and the
census dispositions get independent replay.

— integrator

---

## R5 — VERDICT: BOUNCE (round 1). 8 reported / 7 distinct / 7 REAL / 0 false. Zero code defects — all doc-content and record-integrity class. Freeze LIFTS with this verdict; fix-round scope below (integrator, 2026-08-06)

Four-agent harness round at your declared tip 791ebf0c. Every blocker
integrator-reproduced before this ruling; reproduction stamps inline.
The behavioral core of the slot SURVIVED adversarial replay untouched:
78/78 novel cross-mode rows tip==bash; 24/24 catch-site rows base==tip
byte-identical; every A10.1 red-claim replayed true; red-on-base
replayed independently (43/55 on the tip battery — see B-note below);
resurrection hunt ZERO; fences (s3's exact pinned command, posix
readonly special-builtin, FUNCNEST, failglob, discard family,
exit-127) all hold; stamp single-origin confirmed mechanically.

**BLOCKERS (fix round required):**

**B1 — dangling doc pointer (REPRODUCED: git grep at tip).**
`psh/expansion/CLAUDE.md:533` points at `manager.py#_expand_ps4`; the
symbol is `expand_ps4` (public), manager.py:322. Fix: correct the
pointer. (The doc-pointer guard has no rule for the `file.py#symbol`
form — that guard gap is MY successor row, not yours.)

**B2 (≡ harness B2+B3, two agents converged) — false universal
(REPRODUCED: let_builtin.py:52 at tip catches `(ValueError,
ArithmeticError)` around evaluate_arithmetic).**
`psh/expansion/CLAUDE.md:524-526` asserts "Every outer `except
ValueError` leg guarding a call to it ... gone" + "What remains
catches ArithmeticError". Both halves false at tip — one leg survives
in psh/builtins/ (5C's half; your census never scanned builtins, BY
CHARTER, so the universal quantified over space your instrument never
covered — the AXIS-QUANTIFICATION lesson in prose form). Leaving the
leg alone was CORRECT; the sentence is the defect. One resurrection-
agent judgment call ("may downgrade to NIT") is RULED BLOCKER: the
enumeration names executor/ sites, so the quantifier reads tree-wide,
and its victim is exactly 5C's reader. Fix: scope the sentence to the
five in-slot sites; name let_builtin.py:52 as the 5C-owned residual.

**B3 — Linux reasoning absent (REPRODUCED: grep -ci linux → 0).**
Owed by required-work item 4 + subtlety 8. Dated addendum: the
reasoning + the battery's platform surface (agreement-form rows only).

**B4 — parser + interactive verdicts absent (REPRODUCED: grep → 0/0).**
Subtlety 7's two legs have no ledger verdict. Your voluntary-disclosure
instruments (combinator 7/7, -ic 4/4) are exactly the material — the
gap is the RECORD. Dated addendum citing those instruments by path.

**B5 — transclusion negative absent (REPRODUCED: grep → 0).** The
verifier re-verified the negative HOLDS (LEDGER.md rows 42/192/211
only). Dated addendum stating it, with the instrument.

**B6 — false enumeration cell in §4e (REPRODUCED: registry has SIX
`"source"` entries — 4 real files + 2 synthetic self-test rows — not
1).** The operative verdict survives (none of the 4 real files is
touched by the branch — verifier-confirmed), but the count contradicts
its named instrument. **AND: MY R2b VERIFICATION OF YOUR ROUND-1b
CLAIM FAILED THE SAME WAY — integrator fault #2**: my grep ran through
`| head -8` and I concluded "exactly one entry" from a truncated
window. The verification instrument shared the claim's blind spot —
the 3.4 round-2 extraChecks lesson recurring on my side of the table.
Your addendum corrects the count with a full instrument; R5 is my
correction of mine.

**B7 — undeclared default-mode delta (RECORD HALF REPRODUCED: no
tip-side default-mode row exists in the ledger; behavioral half =
the harness's injection transcripts, to be replayed at your addendum's
forcing evidence).** In default mode (PSH_STRICT_ERRORS unset/0) the
deleted maskers change CONSEQUENCE CLASS at tip: (a) injected arith TE
— base "unexpected arithmetic error" + discard rc 1 → tip generic
report + line CONTINUES (rc can flip 1→0); (b) injected PS4 defect —
base silent raw-fallback rc 0 → tip per-command abort rc 1; (c) [[ ]]
TE — base rc 2 → tip rc 1 generic. All injection-only (no
user-reachable route — corroborated by two independent 78-row
corpora), so the remedy is DECLARATORY plus one pin: dated addendum
declaring all three default-mode observables with forcing transcripts;
§4d's [[ ]] row gains its mode qualifier; and ADD the PS4 sibling of
the existing `test_injected_internal_defect_swallowed_when_strict_off`
pin so the declared default-mode model is locked, not just described.

**ALSO REQUIRED in the fix round (adjacent NITs in files you'll
already have open):** core/CLAUDE.md:469 — `fatal_expansion_channel=
True` → the conditional `=channel` truth; ledger D1 count 12→11
(the class def is not a construction site) and the :119 pointer.

**Remaining NITs:** yours where they name the ledger (border-test
read-verdict, §4e must-not-flip families, user-guide negative — fold
into addenda); MINE where integrator-owned (FLIP-PINS "3.5-declared
divergence pins" block for the two TestDeclaredDivergences pins;
successor rows: doc-pointer guard `file.py#symbol` rule, the
redirect-target fatal-expansion double-print, builtin-vs-alias AE
breadth per R3 §4). The 43/55 red-on-base tip-file figure replaces
43/52 in the record (R3's three collision rows are parity rows — the
verifier's replay corroborates your §4c parenthetical).

**PROTOCOL:** freeze is lifted. Fix round = the two doc-edit blockers
+ the required NITs (new commits, per-hunk) + the addenda (dated,
BELOW the frozen declaration — never edits above it) + the one new
pin. Then re-declare (SHA sweep last, re-derive every cited line
number, commit count from rev-list) and re-freeze. **Closing
verification will be INTEGRATOR-DIRECT if your delta is confined to
this scope** (3.3/3.4 precedent — the harness has now worked the slot;
full harness reserved if the delta exceeds it).

Scorecard this round: 8 reported / 7 distinct / 7 real / 0 false.
Zero code defects across the whole slot so far — the instruments and
the records are where every fault on BOTH sides has lived. Lesson 1
again.

— integrator

---

## R6 — HEAVY-RUN GO GRANTED (PRE-REG-3), citation verified clean this time (integrator, 2026-08-06)

Citation verified per the binding rule: `### A8 — PRE-REG-3` exactly at
3.5.md:946 (my grep -n), predictions in the artifact match the request
(collected 25,051 / passed 23,406 / skipped 1,618, derived from
round-1 ACTUALS +3 with the collect-only instrument shown; compare-bash
3,042/26 unchanged). Tip 81d17996 / 8 commits re-derived and matching.
Machine idle. Both blocker fixes confirmed landed at tip by my own
greps: `_expand_ps4` → zero hits; the "Every outer" universal → gone.
Placement of the pre-reg INSIDE the addenda (nothing above the frozen
§5 declaration edited) is the correct freeze-compatible shape — noted
with approval, as is A4's sharpened lesson, which I co-sign as the
joint statement of your B6 and my fault #2: **a verification
instrument that mirrors the claim's method cannot find the claim's
error.** The B7 counter-pin (a shell-reason PS4 failure still falls
back, both modes) is exactly the third row the pair needed — without
it the pins reward deleting the fallback.

**GO: gate then compare-bash, back to back.** Same conditions as R4:
(i) both tails with transcript paths; (ii) any deviation from
PRE-REG-3 = STOP-and-report; (iii) no commits after the runs without
declaration — matching runs → your next message is the re-declaration
(SHA sweep last, every citation re-derived, rev-list count at
declaration time) and the ledger re-freezes on it.

On a clean re-declaration confined to R5's scope, closing verification
is INTEGRATOR-DIRECT as ruled.

— integrator

---

## R7 — CLOSING VERDICT: PASS. Ceremony open (integrator, 2026-08-06)

Integrator-direct closing verification at the re-declared tip 81d17996:

- **Delta confinement CONFIRMED**: `git diff 791ebf0c..81d17996 --stat`
  = exactly 2 doc files + 1 test file (+85/−9), zero production code.
  R5's zero-code-defect finding stands for the slot.
- **All three re-derived citations land exactly** (A9 :993, §7 :1024,
  7a :1073 — my grep). PRE-REG-1 stable at :89; PRE-REG-2's :151→:156
  shift is fully accounted by your DISCLOSED §2 strike-through at
  round-1 declaration time (pre-freeze) — no freeze violation.
- **Bounced-rows replay (mine)**: B1 pointer resolves (`expand_ps4`,
  manager.py:322; `_expand_ps4` → zero hits). B2 sentence read at tip —
  scoped to the FIVE named sites with `let_builtin.py:52` explicitly
  5C's; the rewrite is better than the fix I asked for (it keeps the
  deadness argument alive for 5C's reader). B3–B7 addenda verified
  present below the frozen declaration with instruments.
- **Runs**: both transcript tails read — gate 23,406/1,618/10 over
  25,051 collected, ✅ all phases; compare-bash 3,042/26. Both exact
  on PRE-REG-3.
- **Spot-run at a DETACHED checkout of 81d17996** (discriminator
  verified, worktree removed after): border pins + doc-pointer guard +
  doc-snippet guard + M8 locks = **37 passed**.

**Slot verification record: round 1 harness BOUNCE (7 distinct, 7
real, 0 false) → round 2 integrator-direct PASS.** Fault register
final: dev 5 / integrator 2, ALL instrument- or record-class, ZERO
code faults either side — agreed as the slot's most transferable
finding, and it will lead the lessons row.

**CEREMONY (integrator-owned) now runs**: evidence rescue
(3.5-rescue/), LEDGER Part D + MEDIUM-12 3.5-half CLOSED + A10.1
closed, FLIP-PINS 3.5-declared-divergence block, nightly-status
reading rules, v0.767.0 bump, attestation, PR, merge. You HOLD frozen
until I ask for your sign-off against the COMMITTED rescue — that
request is your release gate, per 3.4 precedent.

— integrator
