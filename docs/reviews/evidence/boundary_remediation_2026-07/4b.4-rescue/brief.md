# Slot 4B.4 — InputCursor contract close-or-narrow — final 4B slot

**Charter:** integrator plan §6 Wave 4 bullet 4B.4 + sequence §9 Package
4B item 3: *"Complete the cursor ownership model for dup-related
descriptors and temporary redirect frames, or narrow the contract
explicitly before work begins and leave the campaign open for the
omitted behavior."* Plus the accumulated holdings: **D-4B.2-s1**
(timeout-partial assignment disposition + its user-guide doc-absence —
"4B.4 moves doc and code together", adjacency
`17_differences_from_bash.md:596-598`), **P1** (vestigial `_pushback`,
producerless per the 4B.2 census), and the I1 registry's two
deliberate-loss cases, revalidated at THIS base. Wave 4's LAST slot —
Checkpoint R follows.

**Base:** e3924ed3 (v0.772.0 + 4B.3 addendum). Branch
`fix/remediation-4b-4`, worktree `/Users/pwilson/src/psh-r4b-4`.
**Base figures (you RE-DERIVE in your first gate run):** attestation
a239c1ce-committed (gated edcf1ab6): 23,835 passed / 1,620 skipped /
10 xfail; ruff clean; mypy clean; compare-bash 3,046/26 EXACT.

**This slot's shape is a RULING SLOT with defect legs.** The
close-or-narrow decision is EXPLICITLY sanctioned by the charter — a
narrowing with declared, registered open behavior is a legitimate
outcome. What is NOT legitimate: leaving the two probed corruption
faces below both unfixed AND undeclared, or ruling the s1 disposition
and the contract width as if they were independent. They are ONE
coupled decision (see The Coupling below).

## The defects, integrator-probed at e3924ed3

`tmp/w4b4-dispatch-probes/probe_cursor_contract_v2.py` (MAIN checkout,
discriminator asserted; od -c outputs verbatim; strand = lone é lead
byte `\xc3` into `read -t 1 -N 2` — bash ASSIGNS the partial at
timeout (D-4B.2-s1), psh HOLDS it on fd 0's cursor):

1. **Leg A — TEMP-FRAME CONTAMINATION (data corruption):** after the
   strand, `read x < FILE` (FILE = `FILELINE\n`):
   - bash: `v=\303 | x=FILELINE`
   - psh: `v= | x=\303FILELINE` — the stranded stdin byte PREPENDED
     to a read from a DIFFERENT FILE. `cursor_for_fd(0)` finds the
     stdin description's cursor while fd 0 is temporarily the file;
     the pending decoder byte meets the file's bytes.
2. **Leg B — DUP LOSS (silent byte loss):** after the strand,
   `exec 3<&0`, phase-2 feed `\xa9Z\n`, `read -t 1 -u 3 y`, then
   `read -t 1 -N 1 w` on fd 0:
   - bash: `v=\303 | y=\251Z | w=` — every byte delivered.
   - psh: `v= | y=\251Z | w=` — **`\xc3` is never delivered
     anywhere**: not v (held), not y (fd 3 got a FRESH cursor; the
     surplus lives on fd 0's), not w (the pending lead can never
     complete — its continuation went to fd 3's cursor).
3. **P1 recon at this base:** `_pushback` has 0 references outside
   `input_reader.py`, 7 inside — the producerless finding stands;
   re-census the INTERNAL producers (does any live path append?)
   before ruling removal.

## The Coupling (the design insight this slot turns on)

Both corruption faces require STRANDED USERSPACE STATE on a cursor —
and the census of stranding routes (4B.2: TIMEOUT and ERROR only,
post-seam-fix) says the dominant route is exactly the behavior
D-4B.2-s1 DEFERRED: psh holding timeout partials that bash assigns.

- If s1 is ruled TOWARD BASH (assign stranded partials at `-t`
  timeout), the cursor carries (almost) no state the kernel offset
  doesn't, the I1 docstring's "the kernel offset is the complete
  shared state" argument becomes TRUE for the timeout route, and
  NARROWING the contract (documented, pinned, registered) becomes
  defensible — IF the ERROR route and the `-N`-split-malformed
  surplus route (the `_decoded` queue) are also shown bounded or
  handled.
- If s1 is ruled KEEP-PSH, the contract gaps corrupt (leg A) and lose
  (leg B) real data, and close-or-narrow collapses toward CLOSE
  (temp-frame hooks + dup aliasing on the registry's own additive
  design: `OpenDescription` aliasing on dup, frame-scoped keying on
  temp redirects).
Phase A must present this as one decision matrix: s1 disposition ×
per-surface contract choice × residual stranding routes, each cell
probed. The s1 I1-style pins were BUILT to flip loudly when this slot
rules — a flip there is the DESIGNED outcome, not a violation; the
FLIP-PINS registration moves with the ruling at ceremony.

## Integrator recon facts (verify, then lean on)

- The registry (`psh/io_redirect/input_cursor.py`): fd →
  `OpenDescription` → cursor; SCOPED realization ruled 2026-07-19 —
  same-fd persistence only. Its docstring DEFERS dup-sharing +
  temp-frame isolation as "purely ADDITIVE" (bind_dup/temp-frame
  hooks over the same maps) and argues the extra fidelity "exceeds
  the oracle" — an argument my leg A/B probes now measure as FALSE in
  composition with s1's hold. That docstring is a doc-sweep target
  whichever way the ruling goes.
- Existing lifecycle hooks: `exec` rebind =
  `executor/command.py#_rebind_input_cursors_after_exec` (permanent
  redirects drop the old description); fork = `clone_for_child`
  installs a fresh registry (children inherit no userspace buffer —
  I1, must-hold). Temp redirects and dups have NO hooks — that is
  the gap, and the additive design anticipated exactly these two.
- The two deliberate-loss cases are "documented in the I1 ledger with
  discriminating bash probes" — FIND that ledger text, cite it, and
  re-derive its probes at this base (they may predate the 4B.2 seam
  fix and the rider's partial-assignment work).
- `builtins/CLAUDE.md` and `io_redirect/CLAUDE.md` both describe the
  SCOPED contract — doc-sweep targets.
- The user guide's char-model prose (`17_differences_from_bash.md`
  :596-598 region) is where s1's doc lands (the D-4B.2-s1 row's
  absence-travels clause discharges HERE, doc and code together).

## Phase A must settle (probe, don't argue; bash 5.2.26 oracle)

1. **Stranding-route census at THIS base.** Every route that leaves
   userspace state on a cursor: `-t` TIMEOUT mid-multibyte (proven),
   ERROR route (4B.2 census — re-derive), `-N` split of a MALFORMED
   sequence leaving `_decoded` surplus (the I1 original motivation —
   re-derive; note it survives s1-toward-bash!), `_pushback`
   internal producers (P1 census — if truly producerless, its
   removal is a slot deliverable). For each route: can it reach a
   temp-frame read or a dup read? Matrix: STRANDING ROUTE × CONTRACT
   SURFACE, each cell probed or proven-unreachable.
2. **The s1 bash table, completed.** D-4B.2-s1 pinned the value-only
   divergence; complete the matrix for the RULING: timeout-partial
   assignment across `-N`/`-n`/plain × pipe/tty × complete-vs-partial
   chars × what bash assigns (raw surrogate? the partial bytes?) —
   the 4B.2 NEW-1 evidence is the starting point, cite and extend.
3. **The decision matrix** (ruling slot (a) = GO gate): s1 disposition
   (toward-bash / keep-psh / keep-psh-narrowed) × per-surface
   (temp-frame: close/narrow; dup: close/narrow) × residual routes,
   with the leg-A/leg-B corruption faces resolved in EVERY proposed
   cell — no cell may leave corruption both unfixed and undeclared.
   Your recommendation with costs; my ruling picks.
4. **Close designs sketched honestly.** If close: temp-frame =
   frame-scoped keying (the builtin redirect frame already exists —
   `manager.py` BuiltinRedirectFrame) or registry hook at
   setup/restore; dup = `OpenDescription` aliasing at the dup sites
   (which sites? census: `exec n<&m` permanent, per-command `n<&m`
   fd-level, `{v}<&n` named). If narrow: the EXACT declared behavior,
   its pins (corruption faces become CHARACTERIZATION cells with the
   bash side pinned), the user-guide text, and the registered open
   row for Checkpoint R.
5. **Carry sweep (standing checklist item).** LEDGER rows touching
   this slot's name/subject: D-4B.2-s1 (discharges here), D-4B.2-s2/
   s3 (adjacent, MUST-NOT-ABSORB — state disposition), P1 (in
   charter), D-4B.3-s1/s2 (not this slot's — verify), carry #21
   (input-layer adjacency — verify untouched), plus a grep sweep for
   `InputCursor`/`input_cursors`/`OpenDescription` rows. Dispositions
   in the D2 table.

## Pins YOU create

Per the ruling's shape — but these are fixed regardless:
red-on-base: legs A and B end-to-end (two-phase feed cells use the
timing-hygiene floor; stimulus scripts get validity controls — 4B.2
lesson 1). If CLOSE: the corruption faces flip red→green; composition
cells (strand × temp-frame × nested frames; strand × dup × dup-again;
strand × exec-rebind interplay; fork × stranded-parent must-hold). If
NARROW: both faces as both-sides characterization cells + the
declared-behavior pins + user-guide conformance mapping if any claim
lands in the compatibility table (CLAIM_TESTS meta-test). s1: whichever
disposition, the I1-style pins get their DESIGNED flip or an explicit
re-affirmation, and the FLIP-PINS registration follows. P1: removal
lands with an M8-style guard that a reintroduction is caught, or a
documented retention reason. Must-hold: same-fd persistence (I1 —
the `read -N` malformed-split surplus surviving across invocations),
fork-fresh-registry, exec-rebind drop, EVERYTHING 4B.2 shipped (seam
suites, rider suites — the s1 pins excepted per above), all 4B.3
suites, mapfile semantics. M8: per the landed design, kill reasons
distinct, loud diagnostics, fresh-checkout certification (tmp/
ABSENT), PYTHONDONTWRITEBYTECODE=1.

## Must-NOT-flip

- Everything 4B.2 shipped EXCEPT the designed s1 flip: decoder-seam
  suites, rider rc suites, carry-#21 characterization cells.
- All 4B.3 history suites (untouched subject).
- I1 same-fd persistence, fork-reset, exec-rebind (`test_` files for
  the registry — READ THEM FIRST, NAME-VS-BODY).
- The never-over-read contract (bulk-drain regression = the historical
  mapfile bug).
- compare-bash: EXACT-or-pre-registered; expected +0 unless a golden
  case is declared (2 nodes per case, pre-registered BEFORE any run).

## FENCES (stop-and-report BEFORE touching)

- **The 4B.2 decoder seam internals** (`read_all` merge, the
  incremental-decoder invariant): the contract work COMPOSES with the
  seam, never rewrites it. A design needing seam changes =
  stop-and-propose with the census row.
- **`scripting/input_sources.py` / LazyFileInput** (I2): read for the
  census; editing = stop-and-propose.
- **The redirect machinery itself** (`file_redirect.py` frames,
  planner, R1 program): hooks may be ADDED at the frame boundaries if
  CLOSE is ruled; changing restore ordering/semantics = fence
  (slot 1.3b invariants live there).
- **R1 here-input `OpenDescription` adoption** (the input_cursor.py
  docstring's "later fixup slot"): OUT of this slot unless the ruling
  explicitly pulls it in — default = successor note.
- D-4B.2-s2/s3, D-4B.3-s1/s2, all D-3.x / D-4A.x successor rows:
  MUST-NOT-ABSORB.

## Slot-specific test hygiene

- Two-phase feed cells: writer threads with bounded joins; deadlines
  ≥1s; hang detection ≥4×; serial marker where siblings could starve
  the clock; subprocess isolation for fd/pipe cells; every stimulus
  script carries a validity control proving the stimulus itself
  arrived (4B.2 lesson 1).
- In-process registry cells close every fd they open (xdist workers).
- Fresh-checkout leg standing: no reliance on repo tmp/ existing;
  scratch via mktemp under the test's own tmp.
- PTY only if a tty-arm cell is forced by the s1 table; conftest
  interactive gate with inline justification (4B.2 precedent) +
  `assert_tree_under_test`.

## Pre-declared ruling slots

- **(a)** the Phase A decision matrix (stranding routes × surfaces ×
  s1 disposition, with costs) = GO gate for Phase B.
- **(b)** the close-or-narrow ruling itself, per surface — MINE, on
  your matrix; includes the s1 disposition and the FLIP-PINS/user-
  guide consequences.
- **(c)** anything pulling toward the fenced seams (decoder internals,
  redirect restore semantics, R1 adoption, script reader) =
  stop-and-propose with the census row.

## Rules

The FULL binding rule set is `docs/reviews/evidence/
boundary_remediation_2026-07/4a.1-rescue/brief.md` §Rules — binding
verbatim (never-touch list, dead-drop + ACK + md5 chain, mechanical
tip rule, ledger freeze + freeze-md5-in-declaration, per-hunk staging,
SHA paste-from-instrument, pre-registration + GO-binding citation,
RN-Cdoc, CERT-ROW-BEFORE-CLAIM, NAME-VS-BODY — your named siblings:
the registry/reader suites (`tests/unit/io_redirect/`,
`tests/unit/builtins/` read/mapfile/input_reader suites, the 4B.2 pin
files), READ THEM FIRST — instrument discipline, the 13 D-3.4 lessons
+ D-3.5 + 3.x sets, axis quantification, discharge audit, gate rules
(ONE heavy run machine-wide, unpiped pgrep first, foreground, never
shell-`&`, NEVER `run_tests.py --compare-bash` — use `python -m
pytest tests/behavioral --compare-bash -n auto -q`), oracle rules
(PATH bash `/opt/homebrew/bin/bash` 5.2.26, explicit argv, never
/bin/bash), project tmp/ only, peer-escalation/permission-laundering
wrapper). PLUS the D-4A.1 additions + 4A.2 lessons + the **11 banked
4B.1 lessons** + the **11 banked 4B.2 lessons** (enumerated in
`briefs/4b.3.md` §Rules — binding here by reference). PLUS the **4B.3
structural rules and lessons, ALL binding**: (1) ACK-the-highest-R —
every dead-drop entry opens by ACKing the highest R-entry found by
re-reading the file IN THE SAME TURN; (2) freeze-chain — every freeze
declaration quotes the PREVIOUS freeze md5; (3) the integrator
snapshots every frozen ledger (I hold copies; only-declared-sections-
changed claims are diffed); (4) `--collect-only` count FIRST for any
pytest argument that is not a file or node ID; (5) instruments are
FILES from the start — no inline-heredoc probes, transcripts
regenerated by committed scripts; (6) the instrument-mirror family —
a cell consistent with two hypotheses is evidence for neither; make
each candidate mechanism's execution VISIBLE (three occurrences in
4B.3 — assume your first probe composition has this flaw and design
against it); (7) a deviation face living in one probe is one probe
away from silence — every declared face gets its cell; (8)
NAME-VS-BODY applies to YOUR OWN suite; (9) identity over lists is
POSITIONAL, text never identifies an entry; (10) the PROOF-SHAPE of
every claim is NAMED (revert-proven / mutation-proven / by-elimination
/ characterization). New axes for this slot: **STRANDING ROUTE ×
CONTRACT SURFACE** (timeout / error / malformed-split / pushback ×
same-fd / temp-frame / dup / exec-rebind / fork) and **S1 DISPOSITION
× SURFACE RULING** (toward-bash / keep-psh × close / narrow per
surface).

Done = Phase A census + decision matrix + ruling (b) applied — either
the corruption faces flip red→green under CLOSE or they are
characterized both-sides under NARROW with the registered open row —
+ s1 discharged (code and user-guide doc together; I1-pins flipped or
re-affirmed per ruling; FLIP-PINS updated at ceremony) + P1 resolved
(removal + guard, or documented retention) + registry/CLAUDE.md
docstrings truthful + composition cells + M8 + must-not-flip green +
compare-bash at the pre-registered figure + green gate + ruff + mypy
+ discharge audit + complete ledger → completion report with declared
final tip + frozen ledger (chain rule) + instrument manifest
(self-excluding, command-generated).
