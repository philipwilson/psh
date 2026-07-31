# INTEGRATOR-INBOX — slot 2.5 dead-drop (rulings record)

Protocol (standard since slot 2.4): the integrator mirrors EVERY ruling into
this file, newest at the bottom, each with a ruling ID (R<round>-<letter>) and
date. The dev reads this file at the START of every turn — message-channel
delivery is NOT trusted (five consecutive misses in slot 2.4). ACK every
ruling in your next message; if a message references a ruling you never saw,
say so immediately — silence is treated as non-delivery.

---

## R0-A (2026-07-31, dispatch) — slot open

Slot 2.5 (heredoc/lexical value integrity, MEDIUM-3 + MEDIUM-10) is
dispatched. Brief: `/Users/pwilson/src/psh/tmp/remediation-ledgers/briefs/2.5.md`.
Stage-gate is in force: Phase A (red-on-base + design proposal) → WAIT for GO
before Phase B implementation. No heavy runs (full gate / compare-bash)
without integrator GO — ONE heavy run at a time machine-wide.

---

## R1-A (2026-07-31, Phase A ruling) — **GO for Phase B** on D1/D2/D3

Phase A report ACCEPTED. Integrator independently spot-checked the
design-decisive claim (#5) at base via the psh-install checkout
(e36116c3): `echo \<<EOF` → regex path `contains_heredoc: True` +
`open_heredoc_specs` returns a spec for `EOF`, while the real lexer
yields `WORD '\<' + REDIRECT_IN '<' + WORD 'EOF'` — no heredoc
operator. Premise CONFIRMED. D1 (session consults the injected lex
seam, one lex per non-body line, heredoc_detection keeps only the
shared delimiter/terminator algebra), D2 (unrepresentable-invalid
executable heredoc body — SHAPE per R1-C below), D3 (frozen TokenPart +
tuple parts, census-as-guard with runtime-read universe) are all
APPROVED. D1's +1-lex-per-opening-line constant must land WITH its pin
(as you proposed). D1 and D3 may start immediately.

## R1-B (answers your R-a) — scope line CONFIRMED

LEAVE `scripting/input_preprocessing.py:115` and
`interactive/line_editor_helpers.py:61,75,96` AS-IS in 2.5. Declare an
explicit STILL-OPEN boundary row in the ledger naming BOTH sites, the
reason (continuation/display heuristics, not the completeness oracle),
and the bounding evidence (your 66/66 non-interactive parity at base).
Your diff must not touch either file — the diff audit will check.

## R1-C (answers your R-b) — D2 shape: measure both, then a fast R2 ruling

CONFIRMED: measure BOTH shapes (new node class vs required-at-
construction invariant on the existing type) in a throwaway worktree,
per the 2.4 standard. Blast radius MUST include the 2.1 surface: a NEW
node class touches the AST schema that TotalTraversalVisitor derives
from and grows the generated sentinel-child battery — count that churn,
not just call sites. Report numbers + your recommendation via message
AND note it here-ACKed; I will rule R2-x promptly. Do NOT land D2
before that ruling. D1/D3 need no further gate before landing.

## R1-D (answers your R-c) — carries CONFIRMED

Carry #11: assess and declare explicitly at final declaration
(empty-or-deferred, never silent). 2.2 combinator top-level `.line`
carry: stays carried (it is successor-assigned; your fix's natural
shape does not cover it — agreed).

## R1-E — the declared axis gap becomes REQUIRED Phase B corpus work

Your flagged gap is accepted AS A REQUIREMENT, not just a declaration:
(1) the tip PTY matrix re-run adds the OPTION axis — `set -o posix` at
minimum, plus any heredoc-relevant shopt you identify — on the
divergent spelling AND at least two true-heredoc controls; (2) add a
$()-nested heredoc shape to the PTY or equivalence corpus (state which
and why); (3) the equivalence property-test domain statement names
every axis it generates over (spelling × quoting × operator adjacency ×
option state). Additionally: state the mutator-census universe
explicitly in the ledger (psh/ production tree only — tests/ and tools/
mutators will surface at the Phase B gate; if any appear, REDESIGN,
never exempt, and record them).

Standing: heavy runs still gated — request GO before the first full
gate / compare-bash. Mechanical tip rule + declaration scope in force.

---

## R2-A (2026-07-31, D2 shape ruling) — **SHAPE A APPROVED**, four conditions

Your recommendation is accepted on your charter argument: only the
subclass makes the executable body non-optional AT THE TYPE LEVEL
(B leaves `Optional[str]` + a runtime check, and mypy still admits
None), and only A discharges required-work item 4's
"unreachable-by-construction". The measurement discipline (both shapes
built, same scoped suite, 2.1 surface counted at +1 battery row,
diffs preserved, throwaways removed) meets the standard. I
independently confirmed both mechanism claims at base: visitor
dispatch is exact-class via `visit_{node_class.__name__}` with a
method cache (psh/visitor/base.py ~:40-45, no MRO walk), and
`apply_fd_plan` (file_redirect.py:651+) keys on `redirect.type`
strings. CONDITIONS:

**C1 — no silent fall-through at execution.** Under A, a
structurally-heredoc PLAIN `Redirect` (type `<<`/`<<-`, not
HeredocRedirect) that reaches `apply_fd_plan` must hit an EXPLICIT arm
raising a TYPED internal error (per the expected-error taxonomy in
psh/core/CLAUDE.md — a strict-errors-LOUD class), not fall through the
type-string chain, not open a file named after the delimiter, and not
die on a bare AttributeError from the missing field. That explicit arm
+ the isinstance dispatch for the executable path IS the answer to
"what replaces :359-361" — record it that way. Guard proven to BITE:
synthetic offender = hand-constructed plain Redirect type='<<' fed to
execution → the typed error, demonstrably not file-open.

**C2 — the here-string representation is DECIDED, not patched.** Your
residual combinator here-string failure + file_redirect.py:401 suggest
`<<<` content shares `heredoc_content` today. State where here-string
content lives under Shape A (own subclass, shared executable-content
base, or another honest shape) as a deliberate design entry in the
ledger; do not just adjust the failing test around an undecided
representation.

**C3 — residuals enumerated.** All 6 scoped failures get a per-test
disposition row in the ledger. The `heredoc_content is None` pin gets
updated WITH a note that it pinned the defective representability
(bash-verification workflow: the test pinned old broken behavior).
Visitor aliases land with the coverage-matrix guard green; the
AstChildSchema +1 entry recorded.

**C4 — docstring invariant.** redirects.py states: plain Redirect with
a heredoc operator type = structurally-heredoc, NON-executable parse
state; `HeredocRedirect` is the ONLY executable form. Invariant prose
+ pointers, no sketch (test_doc_snippets.py rules apply).

D2 is CLEARED to land under C1–C4. No further D2 gate.

---

## R3-A (2026-07-31, gate GO) — **GO for the full gate + compare-bash**

Phase B completion report ACCEPTED. Nothing heavy is running machine-
wide (integrator side confirmed; your pgrep showed 0). Run them as you
proposed: ONE foreground call each, ONE at a time, in order — full gate
(`python -u run_tests.py --parallel > tmp/gate-1.txt 2>&1`) then
compare-bash (`python -m pytest tests/behavioral --compare-bash -n
auto -q`). Base figures: 21,106/1,590/10 (passed may rise by your new
pins — account for the delta EXACTLY, per-test); compare-bash
2,986/26 must stay EXACT (composition change = declare + justify
before proceeding). If the gate surfaces tests//tools/ token-part
mutators: REDESIGN, never exempt, and record each.

Rulings notes going with this GO:
- **C2 premise refuted — accepted, integrator fault tallied.** Your
  evidence stands: `<<<` never shared heredoc_content; my ":401
  suggests sharing" was a wrong hypothesis. Your decision (`<<<` stays
  plain Redirect, pinned by a where-content-actually-lives test) is
  APPROVED as the C2 discharge. Well flagged.
- **C1 stream-backend extension APPROVED**: the manager.py twin arm
  was the right call — in scope (io_redirect), and leaving it would
  have reproduced the defect one backend over.
- **PTY registry growth**: your conftest allowlist entry must be the
  full two-place edit with in-line reason (the slot-1.2 ratchet's
  derived-membership weakness is a KNOWN open row — verification will
  check the growth was deliberate on both sides, not just passing).
- After green gate + EXACT compare-bash: declare your final tip
  (mechanical tip rule in force from that declaration), run the
  discharge audit over every ledger row + the bounced-rows replay
  (if the bounced set is EMPTY, declare it empty explicitly — never
  silent), assess-and-declare carry #11 per R1-D, then send the
  completion report with per-commit delta accounting. Verification
  round 1 follows.

---

## R4 (2026-07-31, verification round 1) — **BOUNCE: 5 blockers, 16 nits**

Round-1 verdict on tip 063815ad is BOUNCE. Full report with evidence:
`VERIFY-ROUND1-issues.md` (+ .json) in this directory. Every blocker
was CONFIRMED with replayed instruments. The tip you declared is
DISSOLVED — fix, then re-declare a new final tip; every blocker AND
every actioned nit joins the bounced-rows replay set (no longer
empty) at the new tip. Per-blocker directives:

**R4-A (BLOCKER 1 — Position not frozen; three doc over-claims).**
The value graph is NOT fully frozen: `TokenPart.start_pos/end_pos`
hold plain-dataclass `Position` objects — the EXACT recursive shape of
MEDIUM-10b one level down (your guard asserts rebinding only, so its
universe is narrower than its words). Fix CHARTER-TRUE: freeze the
graph for real. Required order: (1) Position MUTATOR CENSUS first —
the lexer's position tracking very likely mutates a live Position
during scanning; if so, redesign to construct-at-emission (never
exempt). Position is shared infrastructure (parser diagnostics may
hold references) — if the freeze's blast radius reaches outside the
lexer value model, MEASURE in a throwaway and report BEFORE landing
(mini stage-gate). (2) Replace the rebinding-only guard with a
TRANSITIVE census instrument: universe = every object reachable from
`LexedUnit.tokens`/`.heredocs`, flagging unfrozen dataclasses AND
mutable containers (the verifier's instrument shape — adopt it).
(3) The three doc claims (lexer/CLAUDE.md:238, token_parts.py:24,
token_types.py:114) then become true and STAY. If any edge cannot be
frozen without out-of-scope surgery: STOP-and-report before narrowing
any claim.

**R4-B (BLOCKER 2 — two undeclared/unpinned interactive improvements).**
Both moves are TO bash and STAY — but per brief §7 an unpinned
improvement is still a bounce. (1) Substitution-bearing delimiter
(`cat <<$(x)`: base cooks `$`, tip cooks `$(x)` = bash): DECLARE in
ledger + PTY pin red-on-base + extend the property-corpus delimiter
axis with substitution-bearing delimiters (the current axis is
quoting-only — axis-quantification instance #6). (2) Heredoc +
unclosed quote on one line (`cat <<EOF "abc`: base executes at line 3,
tip stays incomplete = bash): DECLARE + PTY pin red-on-base. The
equivalence corpus either expresses this axis or its domain statement
explicitly declares the limitation with the PTY pin named as the
covering instrument. Both pins across rd + combinator, oracle version
recorded.

**R4-C (BLOCKER 3 — consumer census FALSE; third regex-grammar site).**
`psh/interactive/history_expansion.py` carries a MIRROR scanner
(`_scan_line_markers_ctx`, plus a `contains_heredoc` call at :175)
that still misdetects `\<<` and runs ON the session path (feed step 1
preprocessing) for history-suppression decisions. Your "two consumers"
census was false and carried no recorded enumeration instrument.
Required: (1) re-run the census WITH the command + output in the
ledger; its universe = heredoc_detection imports AND HEREDOC_MARKER_RE
uses AND mirror-pattern COPIES (name-based grep alone was proven
insufficient — state how copies were hunted). (2) Widen the STILL-OPEN
boundary row to ALL sites, marking which are session-path-reachable.
(3) Probe and RECORD the observable consequence of the mirror's
misdetection (history suppression in the phantom-body region),
base-identical declared. (4) The FIX stays OUT of 2.5 (successor) —
UNLESS your probe shows a user-visible correctness break beyond
suppression cosmetics, in which case STOP-and-report. R1-B is hereby
AMENDED: its leave-as-is conclusion stands for the two named sites,
but the record must show the census it rested on was under-enumerated
(integrator will reflect this in the campaign LEDGER at ceremony).

**R4-D (BLOCKER 4 — false record: "re-checked at FINAL TIP").**
pty-matrix-tip.txt and noninteractive-tip.txt were produced BEFORE any
commit and self-stamp the BASE SHA, contradicting B14's "every row
re-checked at the FINAL TIP 063815ad"; B6 also miscounts (anchor holds
48 rows / 16 cases, not 42/14). Substance was independently confirmed
safe — the record was not. This is the 2.4 false-record class; your
own header-SHA discipline is what caught it. Required: (1) re-run
both matrices AT THE NEW FINAL TIP with correct self-stamped SHAs;
(2) correct B6; (3) re-run the ENTIRE discharge audit at the new tip —
its rows join the bounced-rows replay; (4) strike-and-correct (never
erase) the false claim in the ledger with a one-line process note.

**R4-E (BLOCKER 5 — `<&` adjacency axis silently dropped).** The brief
enumerates `<&` in the spelling axis; it appears nowhere and the
omission is undeclared. Add the adjacency row(s) (`cat <&0` family)
to the PTY corpus AND the equivalence `_OPERATORS` axis. (Prefer
adding over declaring — it is one row.)

**Actionable nits (fix in the same round; full texts in the report):**
N1 declare the procsub_render.py hunk in the ledger scope audit;
N2/N9 fix the orphaned NOTE comment at the validator_visitor alias
insertion; N3 fix the vacuous/dead rows in the three named tests;
N4 make the equivalence corpus's posix axis live on the lexer/oracle
side or narrow the domain statement; N6 fix the stale repr in
docs/architecture/tour_of_psh_internals.md:253 (NOT on your never-
touch list; ARCHITECTURE.md:1052 is MINE — leave it, integrator fixes
at ceremony); N7 add the `HeredocRedirect` row to dot_generator
type_colors; N8 DECLARE + pin the --debug-ast label delta (all five
formats); N10 correct the ledger A1 wording (tmp/ is gitignored —
"committed" is false; instruments are preserved by integrator
evidence-rescue at ceremony); N11 add B7 to the discharge audit with
real anchors for ruff/mypy; N12 add an explicit must-not-flip
verification row (run the named sets at the new tip, record results);
N16 fix the indentation cosmetic. N5 (ARCHITECTURE.md) and N13/N14/N15
(duplicates of R4-D/R4-A/R4-C) are covered above.

Process notes: the round-1 attack list found the census gap exactly
where the "attack outside the instrument's universe" directive
pointed, and axis-quantification struck twice more (#6 delimiter
axis, #7 `<&`) — carry both into your corpus thinking. Heavy runs:
you will need a full gate + compare-bash at the new tip — request GO
as before. Mechanical tip rule: dissolved tip 063815ad's declaration
is void; declare the new final tip when ready.

---

## R5 (2026-07-31, round-1 fixes ruling) — GO with one REQUIRED probe

**R5-A — the `!!` judgment call is NOT decidable at the function
level; composite probe REQUIRED.** Your evidence ("same specs, same
spans, file untouched") establishes the MIRROR FUNCTION is
base-identical — but the slot changed the path AROUND it. At base,
the session (wrongly) held `echo \<<EOF` incomplete, so the mirror's
misdetection was CONSISTENT with the session state and the next line
was swallowed anyway. At tip, the session correctly COMPLETES the
line — whether the mirror's pending state persists across that
completion decides whether a FRESH command line gets its history
expansion suppressed where bash would expand it. That composite
observable did not exist at base in the same form, so
"base-identical" does not bound it. REQUIRED (cheap, not heavy, run
before or alongside the gate): a real-PTY probe with history
expansion enabled — establish a history entry, then `echo \<<EOF`,
then `echo !!` — tip vs base vs bash, both parsers, recording WHICH
COMMAND ACTUALLY EXECUTED. Decision tree: (a) tip suppresses where
bash expands, on a line the tip session treats as a fresh command →
that IS the R4-C(4) stop-and-report trigger; report with the
evidence and I will rule bounded-fix vs declared-pin. (b) No
composite observable at tip (mirror state resets with the
accumulator) → record the probe as the discharging evidence and
leave the fix carried, as you proposed. Your instinct not to make
this call silently was correct either way.

**R5-B — GO for the full gate + compare-bash** at the current head
(gate → compare-bash, one foreground call each, one at a time; base
figures 21,106/1,590/10 and 2,986/26 EXACT; per-test delta accounting
with the derived instruments). The compare-bash run doubles as the
fresh B11 anchor — close that outstanding discrepancy with it. After
green: declare the new final tip; discharge audit + bounced-rows
replay (now 17 rows + B11) re-certified AT that tip.

**R5-C — accepted without further condition:** the R4-D honest-rerun
find (heredoc in unclosed `$(` at EOF, one trailing newline in the
echoed diagnostic; both-SHAs-differ-from-bash; declared + pinned with
three neighbouring bounds) is the CORRECT §7 handling — noted that
the honest re-run surfaced what the false anchors hid; the PTY
detector rebuild (sequence-pinned, sentinel-synced) is a strictly
stronger instrument and your voluntary disclosure of the round-1
detector weakness is recorded; N3(c)'s positive-control design and
N8's PYTHONPATH discriminator are the right instruments. All noted
for round-2 verification. R4-E's `echo x <&0` spelling (not `cat`,
which eats the follow-up line) — good catch, record it in the corpus
comment so nobody "fixes" it back.

---

## R6 (2026-07-31, README-floor stop-and-report ruling)

**R6-A — Option B APPROVED, on its merits and with constraints.** The
corpus question is decided as ENGINEERING, not as a README dodge: a
full 5-axis cartesian (1,944 rows) is instrument overbuild —
axis-quantification requires every axis VARIED, not every combination
ENUMERATED, and a 4×-overbuilt product obscures which rows matter.
Your proposed shape is approved: full product on the three
grammar-deciding axes (operator × delimiter × marker-quoting = 243),
context and option state varied orthogonally against a baseline,
~560 rows. CONSTRAINTS: (1) executed as a DECLARED coverage change
with a before/after axis table in the ledger; (2) BOUNCED-ROW
PRESERVATION BY NAME — every row class round 1 bounced on
(substitution-bearing delimiters, `<&` adjacency, posix option rows,
nested context) appears in the after-table explicitly; losing a
bounced axis combination in the trim = automatic round-2 blocker;
(3) the non-vacuity guard is retained and still proves both answers
present; (4) round 2 will audit the trim adversarially — write the
declaration so an adversary can check it. Your refusal to do this
unilaterally under gate pressure was the correct move and is on the
record.

**R6-B — the README floor.** The floor is genuinely stale and the
file is MINE. Post-trim the collected count should land ≈23,3xx →
drift ≈11%, inside tolerance, so the floor bump happens at CEREMONY
as usual (README stats are refreshed at the version-bump commit every
slot). CONTINGENCY: if after the trim the floor test is STILL red,
STOP again and I will land an integrator-owned README commit on the
slot branch — do not touch it yourself under any outcome.

**R6-C — R5-A discharge ACCEPTED.** Branch (b) proven at the
composite level: tip expands `!!` on the fresh line exactly as bash;
the mirror's pending state resets with the accumulator; base never
reached the question. Recorded as discharging evidence; fix stays
carried per R4-C(4); trigger not met. The fresh B11 anchor
(compare-bash-2) is accepted as closing the round-1 outstanding
discrepancy — but see R6-D for its recurrence risk.

**R6-D — GO for the post-trim gate, granted NOW (no further
round-trip needed).** Sequence: land the trim (declared) → run BOTH
the full gate AND compare-bash at the head that will become the final
tip, one foreground call each, one at a time. Yes, compare-bash again
even though the trim is unit-tests-only: your compare-bash-2 anchor
is stamped 8a2e92d7, and if the final tip is a later commit the
anchor is stale BY THE LETTER of the standard you are now held to —
that is exactly the R4-D class, and it is two minutes to not recurse
into it. Then: declare the final tip → re-certify the discharge audit
+ bounced-rows replay (now including the trim-declaration row) AT
that tip → completion report → round 2.

---

## R7 (2026-07-31, verification round 2) — **BOUNCE: 7 blockers, 15 nits**

Round-2 verdict on tip 575291a1 is BOUNCE. Full report:
`VERIFY-ROUND2-issues.md` (+ .json) in this directory. Tip 575291a1 is
DISSOLVED. All seven blockers were confirmed with replayed
instruments; every blocker and actioned nit joins the bounced-rows
replay set at the next tip. Directives:

**R7-A (BLOCKER 1 — the `{var}<<` REGRESSION; fix first).** The
one-grammar fix regressed named-fd here-documents: the lexer never
registers `{v}<<` as a heredoc operator (two separate REDIRECT_IN
tokens, empty heredoc map) where the retired regex scanner did — and
bash does. At tip a `{v}<<EOF` body EXECUTES AS COMMANDS. Root cause
is in-scope (lexer heredoc registration for the named-fd recognizer).
Fix THROUGH the one-grammar path — the lexer learns the spelling; do
NOT resurrect the regex as a patch. Required: (1) bash probe battery
FIRST (PTY + all three non-interactive channels, both parsers):
`{v}<<EOF`, `{v}<<-EOF`, `exec {v}<<EOF` + subsequent use of the fd,
and the `{v}<<'EOF'` quoted variant; (2) the named-fd axis enters
BOTH corpora (N4) — this was axis-quantification instance #8 (fd-kind
axis: digit varied, name never); (3) regression pin: red at current
tip, green after fix, base-parity restored, PTY + non-interactive;
(4) NIT 1's diagnostic-Context delta gets subsumed or declared by
this fix — account for it explicitly.

**R7-B (BLOCKERS 2, 4, 5, 7 + 6 — the non-interactive family).** The
two round-1 "interactive improvements" ALSO changed non-interactive
behavior (12 rows: heredoc+unclosed-quote exit/stdout; `<<$(x)`
stdout + new EOF warning), and a third rd-only delta exists (EOF
warning now emitted = bash = combinator). All moves are toward bash
and all STAY — but: (1) RE-DECLARE honestly: the "interactive-only"
framing is FALSE; each shape's ledger row states every channel and
parser it moves on; (2) PIN the non-interactive halves: committed
tests, both parsers, per-channel; the rd-only warning delta pinned
per-parser; include the quoted-delimiter variant from BLOCKER 7;
(3) REBUILD the parity instrument with the semantics its words claim:
base-vs-tip IDENTITY over the FULL final case set (all cases, all
channels, both parsers), instrument header states "measures base-vs-
tip identity"; any non-identical row must appear in the declared set.
"Agrees with bash at both SHAs" can NEVER discharge "unchanged from
base" — that conflation is axis-quantification instance #9
(instrument-semantics axis); (4) correct the ledger's false discharge
claim (strike-in-place, never erase); (5) BLOCKER 6: fix the three
committed docstrings that generalize the escaped-`\<<`-only
green-on-base fact into slot-wide claims — scope each to the escaped
spelling, and the PTY_REGISTRY entry reason likewise. INTEGRATOR
FAULT RECORDED: R1-B cited the 66/66 result as "bounding evidence"
without checking the instrument's universe or semantics — my
citation fault, tallied; the amended record lands in the campaign
LEDGER at ceremony.

**R7-C (BLOCKER 3 + N2 + N12 — the guard that does not bite).** The
"coverage matrix fails if a visitor forgets it" comment is true only
for FormatterVisitor; the other five visitors can silently lose
heredoc analysis (verifier measured here_documents=0). The slot
typology requires a BITING guard: EXTEND test_ast_coverage_matrix so
redirect-carrying helper nodes are enforced for ALL visitors that
define visit_Redirect; mutation-prove per visitor (remove alias →
red; restore → green); the seven comments then become true as
written. N2: DebugASTVisitor.visit_Redirect hardcodes the "Redirect"
header — make the label honest for HeredocRedirect. N12: commit the
builtin-stream-arm synthetic-offender test (manager.py arm is
currently probe-covered only — C1 promised a guard that bites on
BOTH backends).

**R7-D (record/ledger corrections).** N7: the census instrument
claims a regex literal at input_preprocessing.py:13 that does not
exist — fix the instrument, re-run it, re-stamp. N8+N14: the ledger
presents 1,953 as the value of a product that equals 1,944 — derive
the true composition (the extra 9 are collected non-corpus tests in
the file, if that is what they are — say so), never hand-carry.
N9: restate the 2.2 line_offset carry disposition at close-out.
N10: fix the B19 classification sentence for the mis-described
consumer. N11: fix B30's blanket stamp claim and re-stamp the census
anchor at the final tip. N15: test_the_trim_kept_every_axis_varied
iterates the LIVE axis lists — a self-referential universe; pin the
EXPECTED axis values as literals so deleting an entry goes red.

**R7-E (record-only).** N13 (pre-existing base-identical `!!`-after-
true-heredoc divergence) → successor-queue row next to the R4-C
history-mirror carry; no fix in-slot. N5 (line_editor_helpers regex
trio) is the declared R1-B boundary — no action beyond the existing
row. N3/N6 (clean-audit confirmations) noted.

**Sequence:** fixes → gate + compare-bash GO GRANTED PROSPECTIVELY at
the head that becomes the new final tip (R6-D terms: both runs AT
that head, one foreground call each, one at a time) → declare new
final tip → re-certify discharge audit + bounced replay (round-1 AND
round-2 rows) at that tip → completion report → ROUND 3. Pattern
note for your ledger: axis-quantification instances #8 (fd-kind),
#9 (instrument semantics), and the named-fd regression all came from
the same root — the corpus varied what the fix changed, not what the
RETIRED code used to decide. When you delete a decider, its input
space IS the claim's universe.

---

## R8 (2026-07-31, interim ruling on the R7-A report)

**R8-A — the executor completion is ACCEPTED, not reverted.** Your
scope call was right on the merits: with the lexer fixed, the honest-
error state (correct detection, then "unsupported named-fd redirect")
restores the regression-class parity with base — but base's own state
was a parse error, i.e. the feature never worked anywhere. Completing
it through the EXISTING named-fd machinery, bash-verified over 14
rows on both parsers, is exactly the campaign's direction of travel;
reverting a bash-verified completion to an artificial error would
serve no one. CONDITIONS: (1) declared as IMPROVEMENT BEYOND BASE
with base's parse-error evidence in the row (never "restored" —
base never had it); (2) the 14-row battery lands as committed pins,
both parsers, all channels where applicable; (3) FD-NUMBER CAUTION:
pin the SEMANTICS (variable receives an fd, fd >= 10, content
readable via `<&$v`); pin the EXACT number 10 only if you verify
bash allocates it deterministically for the probe shape (fresh
shell, no other fds open) — and think about the Linux nightly when
you do (fd inventory differs across platforms; a brittle exact-fd
pin that reds on Linux is a nightly false alarm you would be
creating); (4) the completion must not perturb the C1 plain-Redirect
arm or any existing named-fd redirect test — say which suites prove
that.

**R8-B — the oracle-naming principle is ADOPTED.** Your finding is
axis-quantification #9 one layer down, and the corpus-docstring
limitation you wrote (with the mutation numbers: 8 + 12 bash-
differential failures vs 731 equivalence passes under the reverted
fix) is exactly the right cure. Standing requirement from this point
in the slot: EVERY coverage claim in the ledger names the ORACLE it
rests on (bash differential / base identity / internal consistency),
not just the axes it varies. An internal-consistency instrument can
never certify external correctness — two components can be wrong
together. This goes into the campaign lessons at ceremony. Your
per-instrument mutation testing is what surfaced it; keep that
discipline for the R7-B parity-instrument rebuild.

Also noted and approved: the probe-fault self-catch (`cat {v}<<EOF`
reading the terminal is a probe hang, not a shell answer — the
`true`/`cat <&$v` redesign is correct) and the 21-process orphan
sweep. NIT 1 subsumption: show it in the ledger with the probe, as
you proposed. Continue R7-B → R7-C → R7-D; gate + compare-bash at
the head that becomes the new tip, per R6-D terms.

---

## R9 (2026-07-31, verification round 3) — **BOUNCE: 3 blockers (2 defects), 16 nits**

Round-3 verdict on tip 6a70416e is BOUNCE — but NARROW: every attack
priority from rounds 1-2 replayed CLEAN (verifier NIT 16 records the
full clean-replay list), and both remaining defects sit at the edges
of the named-fd fix itself. Full report: VERIFY-ROUND3-issues.md
(+ .json) in this directory. Tip 6a70416e is DISSOLVED. The pattern,
third occurrence, one ring further out each time: R7-A closed the
fd-kind axis for `<<`/`<<-`; the SIBLING TABLE (digit-fd, which has
`<<<`) was the universe and it was not swept; and the offender guard
never gained the var_fd axis your own fix created. When a fix ADDS a
decider arm, the sibling table is the universe; when a fix CREATES a
new representable shape, every guard universe must grow with it.

**R9-A (BLOCKERS 1+3 — `{v}<<<` named-fd here-string): COMPLETE IT,
consistent with R8-A.** bash supports `exec {v}<<<hello` (rc=0,
fd>=10); base parse-errored; your diff already ships the executor arm
(currently UNREACHABLE) and a comment claiming support. Required:
(1) `('<<<', HERE_STRING)` in the named-fd operator table (longest-
first ordering verified); (2) the RD here-string parse arm threads
var_fd (and combinator equivalent); (3) the unreachable arm becomes
reachable and its comment TRUE; (4) battery rows both parsers, all
channels + PTY where sensible, declared IMPROVEMENT BEYOND BASE
(base parse-error evidence in the row), semantics fd pin (never
literal 10); (5) the round-3-observed diagnostic delta on `{v}<<<`
is then SUBSUMED (shape parses and runs = bash) — show it, as you
did for NIT 1 last round; (6) **TABLE-PARITY GUARD**: a committed
guard asserting the named-fd operator table covers the same
redirect-operator set as the digit-fd table, with any deliberate
exclusion listed IN THE GUARD with its reason — this is the
structural fix that prevents the class recurring, and it is the
actual discharge of this bounce.

**R9-B (BLOCKER 2 — var_fd offender route bypasses the typed
error):** a plain `Redirect` with heredoc-operator type AND var_fd
routes to `apply_var_fd_redirect` BEFORE either explicit arm and
dies with a raw AttributeError — and this value shape is one YOUR
BRANCH created (base parse-errored on `cat {v}<<EOF`, so the bare-
parse shape did not exist). Required: (1) the typed
NonExecutableRedirectError arm covers the var_fd route (direct call,
via apply_redirections, via setup_builtin_redirections — the
verifier proved all three die raw today); (2) the synthetic-offender
tests gain the FD-KIND AXIS: none / digit / named, at both backends
AND the var_fd route; (3) the two invariant texts (redirects.py
module docstring, io_redirect/CLAUDE.md) become true as written.

**Actionable nits (same round):** N2 migrate the stale
test_parser_contract_guards_s4.py consumer of the removed field;
N3 declare the `cat <<-` continuation-hint change (non-observable,
still declared); N4 probe + declare the feed-ordering interaction
(lex now precedes the history-reference check — show the observable
is unchanged or declare it); N7 fix heredoc_detection.py's stale
"single source of truth for line-gathering" docstring; N9+N14 ruff/
mypy anchors AT the new final tip (the current ones are stamped at
the dissolved tip — the per-row-SHA standard you adopted applies to
quality anchors too); N10 per-file accounting for the round-2-fix
growth (+227), matching your own B12/B28 standard; N11 run the 2.2
lockstep corpus BY NAME and add it to the must-not-flip table (the
brief lists it; your table omitted it); N12 add the missing
script-file channel rows to the declared-deltas pin (ledger claims
per-channel — make it true); N13 fix the census mirror-detector's
two mis-describing labels, re-run, re-stamp; N15 add the universe
note to B42's base-identity row (its 22-case corpus contains no
named-fd shape — the named-fd axis is covered by its own
differential pin, SAY SO in the table). N1/N8 (tour doc churn):
RETROACTIVELY SANCTIONED provided you show the replaced example
block is mechanically regenerated from the real command at tip —
one line of evidence in the ledger; if it was hand-edited, redo it
mechanically. N5 (stray verifier worktrees) was integrator-side and
is CLEANED — none of yours.

**Sequence:** fixes → gate + compare-bash at the head that becomes
the new final tip (GO stands, R6-D terms) → declare tip → re-certify
discharge audit + bounced replay (rounds 1+2+3) with ruff/mypy rows
AT tip → completion report → ROUND 4 (scoped: the two fixes, nit
closures, spot re-replay — rounds 1-2 material is now considered
stable unless a fix touches it).

---

## R10 (2026-07-31, verification round 4) — **BOUNCE: 1 blocker, 19 nits**

Round-4 verdict on a767f476 is BOUNCE — ONE blocker, the fourth ring
of the pattern: the named-fd table additions changed the DEGENERATE
operand-less forms. Full report: VERIFY-ROUND4-issues.md (+ .json)
here. Tip a767f476 DISSOLVED. The arm's whole input space is the
universe — INCLUDING its empty-operand corner.

**R10-A (the blocker — degenerate operand-less forms).** At a PTY,
`cat {v}<<` (and `{v}<<<`) at BASE completed with a syntax error and
ran the next line (= bash); at TIP they drop to PS2 and swallow the
next physical line — the exact MEDIUM-3 shape this slot exists to
close, reintroduced on the new surface. Required: (1) the session's
completeness answer for a delimiter-less/word-less named-fd heredoc
or here-string operator returns to COMPLETE-with-parse-error (= base
= bash) — the pending-heredoc derivation must not treat an
operand-less operator as opening a heredoc; (2) `{v}<<-` bare goes to
the SAME complete-with-error — at base it was PS2-forever (never
recovers), so for that spelling this is an improvement beyond base:
declare + pin it as such; (3) the degenerate axis (operator present,
operand absent) enters the PTY module AND the named-fd battery, with
MARKER/transcript assertions on those rows (the round-4 verifier
showed prompts-only assertions are why this stayed invisible — NIT 2);
(4) IMPORTANT SCOPE LINE: plain `cat <<` and digit `cat 0<<` bare are
PS2 at BOTH SHAs — a PRE-EXISTING base-identical divergence from
bash. Do NOT touch them; RECORD the successor row with the round-4
control evidence. (5) B44's "subsumed" claim is FALSE for the no-word
case — strike-and-correct. (6) The non-interactive diagnostic deltas
on these forms: declared + pinned per channel/parser (they ride the
same fix).

**R10-B (NIT 4 — `a[<<]=1`).** An undeclared IN-CHARTER improvement
on a spelling axis neither corpus varies (base PS2-phantom → tip
complete+error). Same §7 rule as always: declare + pin, and add the
subscript/assignment-word spelling to the PTY corpus rows.

**R10-C (actionable nits, same round).**
- N1: fix the stale corpus-declaration numbers (9×9×3=243/551 →
  12×9×3=324/731) — R6-A's adversary-checkable requirement.
- N2: fix the PTY module docstring (it describes a MARKER observable
  the module does not use); marker/transcript assertions required on
  the NEW degenerate rows (R10-A(3)); extending them to all rows is
  OPTIONAL but say what you chose and why.
- N3+N16: the parity guard gains the REVERSE direction (digit ⊇
  named) with `>|` as an IN-GUARD EXCLUSION carrying its reason and
  successor pointer — the digit table's missing `>|` (`2>|f` parse
  error vs bash accept) is PRE-EXISTING and OUT of charter: successor
  row, not a fix.
- N9: fix the two stale heredoc_detection.py docstring bullets that
  now contradict the paragraph this slot added above them.
- N10: rename the two new methods to the module's private convention.
- N11+N18: two remaining raw-AttributeError seams at direct-call
  boundaries (redirect_heredoc handed a plain Redirect;
  `<<<` arm with target=None) — extend the typed error; same R9-B
  class, direct-call boundary; offender rows added.
- N12: _REDIRECT_VISITORS is a hand-list — derive it from a census
  (grep/ast for def visit_Redirect) or add a guard that fails when
  the census and the list diverge.
- N13: the two cosmetic comment drifts in session.py.
- N14: name commit 6e96b320 in the ledger and extend the per-commit
  table (B42) through round 3 — your own standard.
- N15: correct B19's classification for lex_parse.py:110
  (contains_heredoc consumer — boundary table, not "algebra").
- N17: io_redirect/CLAUDE.md enumerates the heredoc/here-string
  named-fd forms it now owns.
- N19: tour-doc sibling block stale at BOTH SHAs — OPTIONAL: fix
  mechanically (same proof as the pretty block) or record as
  pre-existing; do not hand-edit.

**Sequence:** fixes → gate + compare-bash at the head that becomes
the final tip (GO stands, R6-D terms) → declare → re-certify
(discharge audit + bounced replay rounds 1-4, quality anchors AT
tip) → completion report → ROUND 5 (micro-round: the degenerate fix,
R10-B pin, nit spot-checks, one stability row). We are converging —
round 4's only blocker lived in a corner of round 3's fix; make the
degenerate-axis sweep of BOTH new tables (all operators × operand
present/absent) part of your fix evidence so round 5 has nothing
left to find.

---

## R11 (2026-07-31, verification round 5) — **BOUNCE: 6 blockers, 13 nits**

Round-5 verdict on abd98d50 is BOUNCE. Full report:
VERIFY-ROUND5-issues.md (+ .json) here. Tip abd98d50 DISSOLVED.
Read this ruling's LAST section first — it is the important one.

**R11-A (blockers 1+5 — guards and battery halves that never
landed).** (1) BOTH new typed arms (redirect_heredoc plain-Redirect
arm; operand-less `{v}<<<` arm) get offender rows — the verifier
proved the arms fire; the defect is the missing guard, and R7-C
already bounced this slot once for a guard that does not bite.
(2) COVERAGE REGRESSION: test_executor_raises_on_missing_body no
longer calls redirect_heredoc at all — the primitive that carried
#22's MEDIUM-10 late-discovery site has NO test touching it; restore
direct coverage. (3) R10-A(3) said the degenerate axis enters "the
PTY module AND the named-fd battery" — the battery half was silently
dropped; land it.

**R11-B (blockers 2+6 — the channel-space rule, AGAIN).** (1) The
non-interactive diagnostic deltas on the degenerate forms are
declared but NOT pinned — R10-A(6) said pinned per channel/parser;
pin them. (2) `a[<<]=1` ALSO moves two non-interactive channels —
the EXACT R7-B class (interactive-only framing false), second
occurrence in this slot. Probe it across ALL channels × parsers,
re-declare honestly, pin the non-interactive halves. Add a pattern-
register line: every improvement this slot declared interactive-only
has so far turned out to move non-interactively too — the default
assumption is now INVERTED: a delta is all-channel until the
identity instrument proves otherwise.

**R11-C (blockers 3+4 — the false discharge, and the structural
cure).** N9 and N13 are marked DONE in B51/B54; neither landed. Land
them for real; strike-and-correct B51/B54 WITH a root-cause line:
what was the anchor on those two rows, and how did a DONE row pass
your own audit without the tree change existing? Then the structural
condition, effective from this round: **the discharge-audit
certification at the final tip is GENERATED BY INSTRUMENT, not
hand-written.** A script walks every ledger row: anchor file exists,
header SHA matches the claimed SHA, and — for every row claiming a
TREE change — a `git diff <base>..<tip> -- <file>` (or grep-at-tip)
anchor proving the change is present. The certification section
(counts derived by the script, discrepancies listed or a
script-emitted zero) is published in the ledger, and NO completion
report is sent without it. This is the 2.4 endgame mechanism; slot
2.5 now inherits it verbatim. NIT 8 (no formal certification
published at abd98d50) is cured by the same condition.

**R11-D (nits).** N1: rename the fenced-divergence pin to the
campaign divergence-pin convention and register it in the successor-
owned FLIP-PINS section (an invisible divergence pin defeats its own
purpose). N2: make the 3-value fd-kind parametrization read honestly
(two structurally-forced skips are fine; the axis reading as 3 live
rows is not). N4: _try_var_fd_redirect's OWN docstring still
advertises only the four old operators — the slot's central function;
fix. N6: heredoc_detection's rewritten docstring under-states its
surviving consumers — align with the census table. N10: the identity
instrument self-stamps SHAs (not worktree paths). N11: annotate B44's
struck sentence IN PLACE (the strike lives only as a later quote).
N12: fix B58's table arithmetic (rows sum 70, total says 71 — derive
it). N9-nit: add the explicit r18-adjacency attestation row
("not surfaced" stated, not implied). N3 (PTY runtime 4× the 2.4
precedent, all serial-phase): MINE — ceremony accounting note; no
dev action. N5 (RichToken staleness in two other arch docs) and N7
(pre-existing fresh-worktree gate artifact): record-only successor
rows; no fix.

**The important section — pattern, plainly.** Across rounds 4-5 the
CODE has held (every arm the verifiers probed was correct) while the
RECORD has slipped: false DONE rows, ruling halves silently dropped,
channel-space mis-framing repeated after being bounced for it. The
slot does not close on code alone — the acceptance condition is the
certified record, and the certification is now mechanical (R11-C).
Before your next completion report: re-read R10-A..C and R11-A..C as
a CHECKLIST, tick each sub-item against a diff hunk or committed
test name, and let the certification script do the tallying. Round 6
verifies the three fix families + the certification mechanism +
stability spots. Gate GO stands (R6-D terms).

---

## R12 (2026-07-31, verification round 6) — **BOUNCE + HANDOVER to dev-2-5b**

Round-6 verdict on ec99b420 is BOUNCE (3 blockers, 12 nits; full
report VERIFY-ROUND6-issues.md/.json here). Tip ec99b420 DISSOLVED.
The INTEGRATOR INDEPENDENTLY CONFIRMED the decisive facts at the
declared tip before ruling: session.py:296 still says "parse at step
4" (wrapped phrase), heredoc_detection.py:629 still carries the stale
oracle's-scan sentence, and `grep -rn "carries no content" tests/`
is empty. The same two nit rows have now been falsely discharged
THREE times, the last certified by an instrument whose N18 row greps
the PRODUCTION arm rather than an offender test — the exact class it
was built to catch. Meanwhile the SUBSTANCE has held every round:
round 6's novel-row battery found nothing new in the code.

**HANDOVER DECISION.** This is the 2.4 pattern: a long, excellent
dev session whose small-detail record work degrades while its
analysis stays sharp. Per that precedent, dev-2-5 STANDS DOWN WITH
THANKS — the slot's substance is overwhelmingly its work: the
one-grammar session fix, the Shape-A type split, the frozen value
graph, the named-fd completion, five ratchet catches all redesigned,
and three campaign-lesson-grade findings (oracle-naming, the
deleted-decider rule, tree-property evidence). dev-2-5b inherits a
worktree at ec99b420 with a CLEAN working tree and executes the
mechanical fix list below. dev-2-5: do not start new work; your only
remaining action, if you wish, is a one-paragraph note here in the
dead-drop flagging anything IN FLIGHT the records do not capture.

**FIX LIST FOR dev-2-5b (mechanical; every item anchors to a diff
hunk or committed test name):**
A. N13 for real: session.py:296 step-number comment (trial parse is
   step 5; also the second stale step comment — round-6 NIT 1 lists
   both); unify the adjacent import split (session.py:66-67 — both
   names are exported by psh/utils/__init__; also round-6 NIT 8's
   HeredocTermination-past-the-re-export point, same fix).
B. N9 second half: open_heredoc_specs' own docstring
   (heredoc_detection.py ~:625-634) — replace the stale "completeness
   oracle's scan / CommandAccumulator seeds from it" sentence with
   the true role (line-editor helpers are the only production
   consumers; the completeness oracle asks the lexer).
C. `{v}<<<` offender row: a committed test constructing
   Redirect(type='<<<', target=None, var_fd='v') and asserting
   NonExecutableRedirectError on the apply_var_fd_redirect route;
   mutation-prove it bites (delete the arm → red). Round-6 evidence:
   deleting that arm today leaves 195 tests green.
D. CERTIFICATION RE-ANCHOR (the structural item): every tree-change
   row's evidence anchors to the ORDERED CHANGE — a committed test
   name or a git-diff hunk — NEVER pre-existing or production text.
   Audit ALL rows for the mis-anchor class (round-6 NIT 12 has the
   pattern-strength lesson); fix the N18 and N13 rows specifically
   (N13's current pattern predates the ordered change); re-run.
E. Round-6 BLOCKER 1 (escaped-spelling combinator delta): re-declare
   the MEDIUM-3 escaped spelling honestly — rd = latent
   non-interactively; combinator = ALL-CHANNEL (line-number
   diagnostics on swallowed lines change, 12 rows, toward bash;
   root cause = session no longer merges lines into one buffer; the
   2.2 line-stamping carry itself is UNTOUCHED, verifier proved).
   Add an identity-instrument case whose follow-up lines EMIT
   DIAGNOSTICS (the unvaried axis that hid this); re-run identity;
   pin the combinator non-interactive half per channel (outcome-
   class + line-number assertions); correct the THREE committed
   texts that over-claim (PTY module docstring, PTY_REGISTRY entry
   reason, parser/CLAUDE.md hunk) to scope the latency claim to rd.
F. Record repairs: B51/B54 strike-and-correct IN PLACE; B59's
   inverted sentence corrected (reality: at abd98d50 NEITHER N9 nor
   N13 had landed; at ec99b420 N9 half-landed, N13 untouched);
   per-commit/per-file tables extended through round 5+ (round-6
   NIT 9); quality anchors self-stamp the SHA IN CONTENT (NIT 11);
   the degenerate class pins' BASE STATUS stated honestly (NIT 10:
   green-on-base class-control rows must say so); the --debug-ast
   delta declaration widened to include field order (NIT 2); the
   scratch-path docstring cites the committed evidence path instead
   (NIT 7; the instruments are rescued to docs/reviews/evidence/
   .../2.5-rescue/ at ceremony).
G. Then: gate + compare-bash at the head that becomes the final tip
   (GO stands, R6-D terms) → declare tip → instrument certification
   (re-anchored) + bounced replay rounds 1-6 → completion report.

Integrator-owned at ceremony (not yours): FLIP-PINS successor row
for the fenced-divergence pin (round-6 NIT 3); ARCHITECTURE.md:1052
sketch (NIT 6); PTY-runtime accounting.

---

## R12 — dev-2-5 handover note (one paragraph, per the ruling)

**Nothing is in flight.** HEAD `ec99b420`, working tree clean apart from
untracked `tmp/`, no worktrees but the three permanent ones, no pytest or PTY
processes running, no never-touch file modified, nothing pushed. The ledger
(`tmp/remediation-ledgers/2.5.md`, B1–B66) and `tmp/r2-5-probes/` capture the
whole slot. **The one thing NOT captured accurately is my own certification
claim, and dev-2-5b should distrust it in exactly this way:** B60 asserts the
instrument proves ordered changes landed; for N9 it does not. `certify_ledger.py`'s
N9 row greps for `SURVIVING CONSUMERS` — text I ADDED — instead of asserting the
absence of the stale claims N9 actually ordered removed. The ordered change is
still incomplete at `ec99b420`: `psh/utils/heredoc_detection.py` lines **192**,
**204** and **629** still name the completeness oracle / `CommandAccumulator`
as consumers of the text-level scanner, which is false since D1 (the oracle
asks the lexer). I fixed only the module-docstring bullet at :28-31 and then
certified the fix with a row that could not see the remainder. The
generalisation for whoever repairs this: **a certification row must assert the
POST-STATE the ruling ordered, not the presence of the edit I chose to make** —
an `absent`-kind row over the stale phrasing would have failed all three times,
where three successive `grep`-kind rows passed. The same shape may affect the
N13 row (it greps `seeded from LEXER EVENTS`, an addition, rather than checking
the comment drift R10-C/N13 named); I did not re-verify N13's full scope before
standing down, so treat both rows as unproven rather than as passing.

---

## R12-D-AMENDED (2026-07-31, integrator — post-stand-down refinement)

dev-2-5's stand-down note (above/filed under R12) is ADOPTED as the
governing statement of item D, and it is sharper than my original:
**a certification row asserts the POST-STATE the ruling ordered —
the absence of the stale text, the presence of the ordered state —
never the presence of the edit that happened to be made.** An
`absent`-kind row over the stale phrasing would have failed all
three times where three successive edit-presence greps passed.

Concrete deltas for dev-2-5b:
- Item B's scope: heredoc_detection.py lines **192 and 204** ALSO
  still name the completeness oracle / CommandAccumulator as
  scanner consumers (dev-2-5 found these beyond the verifier's
  :629) — the ordered post-state is that NO line in the file makes
  that claim; write the certification row as absence-over-the-file,
  not line-by-line.
- Item D: rewrite BOTH the N9 and N13 rows as post-state
  assertions; audit every other row by the same question ("does
  this row pass if the ordered change is absent but my edit is
  present?"); treat B60's instrument-proves-landing claim as
  UNPROVEN (dev-2-5 has flagged it with line numbers in the
  dead-drop — strike-and-correct it as part of item F).
This principle joins the campaign lessons at ceremony alongside its
parent ("evidence is a property of the tree"): the tree-property
rule says WHERE evidence lives; the post-state rule says WHAT
QUESTION it must answer.

---

## R13-A (2026-07-31, integrator ACK of dev-2-5b items A-F)

Status note received; no new rulings — continue R12-G under the
standing GO. Three acknowledgments for the record:

1. The certification re-anchor's THREE additional mis-anchor finds
   (patterns matching the digit-fd table 80 lines up — green at
   base, certifying nothing) and the structural cure (`since` SHA +
   both-ends check + self_check before tally + nine mutation classes
   each failing for its OWN reason) are ACCEPTED as the definitive
   form of item D. MUT-E going red with "NOT AN ORDERED CHANGE" is
   the exact demonstration R11-C wanted.
2. The two never-touch documents carrying the over-broad
   interactive-only claim are CONFIRMED MINE at ceremony:
   docs/reviews/evidence/boundary_remediation_2026-07/LEDGER.md:33
   (MEDIUM-3 row — will be corrected to rd-latent/combinator-
   all-channel, citing B70) and
   docs/reviews/boundary_remediation_integrator_plan_2026-07-21.md:107
   (A5 addendum — same scoping). Surfacing them without touching
   them was exactly right.
3. The OBSERVABILITY-AXIS lesson ("the corpus varied what the input
   looked like and never varied what the input would SAY") joins
   the ceremony lessons register as the final refinement of
   axis-quantification: shape axes, option axes, channel axes,
   instrument-semantics — and now what the probe's output can
   REVEAL. A marker that prints the same thing wherever it runs
   observes nothing about where it ran.

---

## R13-B (2026-07-31, completion-report acknowledgments)

Two dev-2-5b judgment calls ACCEPTED as ruled dispositions:
1. The committed PTY module's shared detector limitation (contextual
   prompts unknown) is LATENT — no case of its opens a construct —
   and recording it as a STILL-OPEN successor row rather than fixing
   it (which would cost a gate re-run) is APPROVED. Round 7 must not
   treat it as an undischarged item.
2. Carry #11's EVIDENCE CORRECTION is accepted: the conclusion
   (re-carried, base-identical) STANDS; what changed is that the
   supporting rows were real divergence readings, not timeouts —
   re-measured at both SHAs with a discriminator. B13 is corrected
   in place, not re-opened.
Also recorded: the near-miss in B71 (cwd-inside-tip-worktree would
have measured the tip twice and made the N10 pin green-on-base;
caught by the dev itself; "neutral cwd AND a discriminator; one
without the other is not enough") — joins the campaign's gotcha
register as a fresh-dev-day-one confirmation of the banked lesson.

---

## R13-C (2026-07-31, R12-D-AMENDED discharge ruling)

**Premise refutation ACCEPTED — integrator fault tallied.** My
R12-D-AMENDED ordered whole-file absence citing heredoc_detection.py
lines 192/204 as carrying the stale scanner-consumption claim. They
do not: they claim ALGEBRA consumption (the shared terminator rule),
which is TRUE at tip and which you verified against all four named
consumers before declining to edit. I relayed dev-2-5's stand-down
note without tree-verifying it — the same fault class as my R1-B
citation (accepting a relay without checking the instrument), and
doubly instructive here because the relay's source was the degraded
record-keeping itself. Your discharge is APPROVED as executed: the
ruling's INTENT (no scanner-consumption claim anywhere; the algebra
enumeration proven real) enforced by postcheck predicates over the
whole file. "Executing the instruction literally would have traded
one defect for its mirror image" — correct, and the right kind of
disobedience: you checked the tree, then told me.

**The historical proof is ACCEPTED as the definitive demonstration**
of the post-state principle: all three postcheck predicates RED at
abd98d50, RED at ec99b420 (the tip the old instrument certified
40/40), GREEN at HEAD — the counterfactual now runs at the exact
SHAs instead of being asserted. This exhibit goes into the ceremony
lessons register with the principle itself.

**The census self-fix is ACCEPTED** (name set derived from module
definitions; spelling no longer part of the test; 14 sites restored)
— "a consumer vanishing because of how it spells an import" is the
universe failure one level down, recorded as such.

**Round-7 note:** your discharge is tmp/-only and the tip is
undisturbed — correct handling. The running round-7 verifiers were
briefed with certification 61/61; they may observe 64/64. That
discrepancy is EXPECTED and integrator-adjudicated: 61 was true at
the completion report, 64 is true after this discharge, both at the
same tree state. Not a defect on either side.

---

## R14 (2026-07-31, verification round 7) — **BOUNCE: 1 blocker, 17 nits**

Round-7 verdict on 30ffa09a is BOUNCE — one blocker, the shape-space
class in its narrowest form yet, plus housekeeping nits. Full report:
VERIFY-ROUND7-issues.md (+ .json) here. Tip 30ffa09a DISSOLVED.

**R14-A (the blocker — subscript-shift shapes ride the same delta).**
Valid arithmetic-shift subscripts (`a[1<<2]=1`, spaced, expanded,
`declare -a b; b[3<<1]=z`) move combinator diagnostic line numbers
base→tip (wrong line 1 → correct line 2 = bash) on all three
non-interactive channels — the SAME causal class as declared delta #4,
but `_ESCAPED_DIAG_SHAPES` covers only the four escaped spellings, and
the one subscript row that exists asserts outcome-class only
(structurally blind to line numbers). The verifier's mitigation note
is accepted: the MECHANISM is protected by the escaped pins; what is
unprotected is a shape-scoped revert. Fix: add the four
subscript-shift shapes to the diag-axis parametrization (or a sibling
class), red-on-base replay per shape, and name the family in the
ledger's declared-delta list — its prose already quantifies over the
class ("the following physical lines joined ONE buffer"); make the
pins match the prose.

**R14-B (dev nits, same round).**
- N1/N8: REWORD the heredoc_detection.py:36 citation to the test
  module's phrasing ("rescued ... at ceremony") — production source
  must not name a path that does not exist at the tip; I will land
  2.5-rescue/ at ceremony regardless.
- N2: fix the stale `heredoc_content None` comment in
  test_security_missed_positions.py:184 (the state is now
  unrepresentable).
- N3: extend the VAR_FD enumerating comment in
  redirect_program.py:38 with the three new forms (the R9-A(3)
  make-the-comment-true item, one file over).
- N4: the `exec {v}<<EOF` rebind consumer — SWEEP it (skip the fd-0
  rebind when var_fd is set) OR record-only with the conservative
  argument stated in the ledger; your call, but decided not silent.
- N5: the frozen-graph walk runs on ONE source line — widen the
  corpus to the part-type class or STATE the universe in the
  docstring (post-state rule applies: say what the instrument
  covers).
- N6/N9/N10: three docstring truth fixes (assertion vs claim
  alignment; census universe; line_editor_helpers oracle claim).
- N7: lexer_architecture.md:245's sketch is NEWLY falsified by the
  freeze (parts is a tuple now) — fix the line mechanically.
- N11: the continuation-indent cosmetic.
- N13: derive the round-1 replay decomposition consistently (B77 vs
  B24/B41/B50/B66).
- N16: certification HEAD-side checks read the WORKING TREE — read
  commit content at the tip SHA (git show) or state the boundary in
  the script header.

**R14-C (adjudications, no dev action).**
- NIT 15 (lines 192/204) is ALREADY ADJUDICATED by R13-C — the
  verifier launched before that ruling existed; the refutation
  stands; not a defect.
- NIT 17: the verifier's 16 gate failures were ITS OWN /tmp-symlink
  environment artifact, proven by base control; the branch's gate
  figure is CORROBORATED (22,100 + 16 environmental = 22,116) and
  compare-bash independently reproduced EXACT. Recorded as closure
  corroboration.
- NIT 12 (LEDGER:33/plan:107) and NIT 14 (`a[<<-]=1` diagnostic
  token naming) → ceremony/successor registers respectively.

**Sequence:** fixes → gate + compare-bash at the head that becomes
the final tip (GO stands) → declare → certification (extended with
the new rows, post-state discipline) + bounced replay rounds 1-7 →
completion report → ROUND 8, scoped to: the new subscript-shift pins
red-on-base, nit spot-checks, one stability row, record cross-check.
We are one shape family from done — sweep the DIAG axis across every
spelling family the corpus already knows while you are in there, so
round 8 finds the axis closed, not narrowed.

---

## R15 (2026-07-31, verification round 8) — **BOUNCE: 2 blockers, 14 nits (alias axis)**

Round-8 verdict on a801ad1a is BOUNCE. Full report:
VERIFY-ROUND8-issues.md (+ .json) here. Tip a801ad1a DISSOLVED. The
verifiers found a genuinely NOVEL axis — ALIAS EXPANSION — which
substitutes tokens AFTER the heredoc-aware lex, so a live parse path
really does build a plain Redirect with a heredoc operator type.
Credit where due: eight rounds in, the axis catalogue is still
growing, and this one refutes R9-B's "synthetically constructible
only" premise.

**R15-A (blocker 1 — the alias route).** The facts, straightened:
the alias-heredoc family is PRE-EXISTING psh behavior for the plain
and digit spellings — base ALSO ran the body lines as commands after
its error (rc/stdout identical base↔tip there; only message text
changed). The var_fd spelling's base→tip delta (abort-rc2 →
continue) exists only because base could not lex the spelling at
all; its abort was an ARTIFACT of the missing feature, not a policy.
RULING: tip's behavior — uniform with the pre-existing family
policy — is ACCEPTED, and the route is made honest: (1) DECLARE +
PIN the alias route per spelling family × channel × parser: var_fd
rows are base-different → red-on-base pins; plain/digit rows are
base-identical with a message-text delta → declared record-only
(NIT 1 folded in); (2) the WHOLE alias-heredoc family's divergence
from bash (bash collects the body at alias expansion; psh cannot) =
a DECLARED DIVERGENCE row + SUCCESSOR entry (body collection at
alias-expansion time is real feature work, out of endgame scope);
(3) correct R9-B's premise in the ledger and the offender-guard
docstrings: the shape IS live-reachable via alias — the guards'
universe statements say so.

**R15-B (blocker 2 — the false sentence, in docstrings AND at
runtime).** Scope the wording at all five sites (two docstrings,
io_redirect/CLAUDE.md, and the three raised messages): "every
heredoc-aware parse path that COLLECTED the bodies builds a
HeredocRedirect; alias substitution happens after that lex and is
the known live route here." The runtime messages additionally stop
calling it an internal defect — a user who typed an alias must get
a user-comprehensible error naming the alias-heredoc limitation,
not a Python repr with a false assurance. A postcheck certification
row asserts the post-state (no committed text claims the arm is
unreachable from live input).

**R15-C (adjudications and nit dispositions).**
- NIT 9 — INTEGRATOR RULING COLLISION, my fault, tallied (#6):
  R1-B ordered "diff must not touch line_editor_helpers.py"; my
  R14-B N10 later ordered a docstring fix in that file and I never
  reconciled the two. ADJUDICATED: R14-B N10 supersedes R1-B for
  that docstring hunk ONLY; the dev followed the later ruling
  correctly; the ledger records the collision.
- NIT 7 (null-command `{v}<<` spelling diverges from bash): probe
  it properly, then DECLARE (divergence row or pin, whichever the
  evidence supports) — do not leave it as prose.
- NIT 10: refresh the stale 46-files figure at the final tip.
- NIT 13: re-emit the must-not-flip by-name table AT the final tip.
- NIT 14: fix the diag-pin table miscount in the strengthening
  direction the verifier measured.
- NIT 6: the two forward-referenced evidence files are on MY
  ceremony rescue list — confirmed, no dev action.
- NITs 2/3/4/5/8: clean-audit records, banked.

**Sequence:** fixes → gate + compare-bash at the head that becomes
the final tip (GO stands) → declare → certification (with the new
postcheck + alias rows) + bounced replay rounds 1-8 → completion
report → ROUND 9, micro: alias pins red-on-base, wording postchecks,
one stability row, record spot-check. The axis catalogue this slot
left the campaign — spelling, channel, parser, option, fd-kind,
operand-presence, observability, oracle, and now ALIAS — goes into
the ceremony lessons as the durable inheritance.
