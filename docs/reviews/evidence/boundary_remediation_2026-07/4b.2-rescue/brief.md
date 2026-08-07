# Slot 4B.2 — Input decoding (MEDIUM-2 + A5 rider) — second 4B slot

**Charter:** integrator plan §6 Wave 4 bullet 4B.2 + sequence §9 Package
4B item 2: *"Finalize incremental UTF-8 decoding by feeding remaining
bytes through the existing decoder. Pin character identity and byte
round-trip at every multibyte split."* Plus the A5 RIDER (plan §A5,
found in verification, not in #22): *"`read -t X -N n` ignores `-t`
entirely — `_read_exact` calls `read_limited` with no deadline and
hangs; lowercase `-n` honors `-t`."* Exit criterion (sequence §9):
*"Every split of valid 2-, 3-, and 4-byte UTF-8 input yields the
original character sequence; malformed bytes still round-trip under
surrogateescape."*

**Base:** 21a23a4c (v0.770.0 + 4B.1 addendum). Branch
`fix/remediation-4b-2`, worktree `/Users/pwilson/src/psh-r4b-2`.
**Base figures (you RE-DERIVE in your first gate run):** attestation
0a8be3bb-committed (gated 29c13396): 23,604 passed / 1,618 skipped /
10 xfail; ruff clean; mypy 275 files; compare-bash 3,042/26 EXACT.

**Unlike 4B.1, this slot HAS shell-observable behavior deltas by
design** — both defects are user-visible. Each flip is a DECLARED
toward-bash (or toward-correctness) delta with red-on-base pins;
anything ELSE shell-observable that moves is a STOP.

## The defects, integrator-probed at 21a23a4c

`tmp/w4b2-dispatch-probes/probe_medium2_decoder_seam.py` (run at the
base worktree, discriminator verified; outputs verbatim):

1. **MEDIUM-2 decoder seam** (`psh/builtins/input_reader.py#read_all`,
   the r22 :181-216 region): a timed `read_record` consumes the first
   byte of é (`C3`) into the cursor's incremental decoder (outcome
   TIMEOUT, data `''`); `read_all` then finalizes that decoder with
   EMPTY input (`decode(b'', final=True)` → `\udcc3`) and decodes the
   tail with a FRESH one-shot decode (`\udca9`). Measured:
   `read_all → '\udcc3\udca9\n'`, expected `'é\n'`, CORRUPTED. Byte
   round-trip DOES survive (`b'\xc3\xa9\n'` — the finding says so;
   character identity is the broken half). Fix direction per the
   finding: feed the tail through the EXISTING decoder with
   `final=True` — but see Phase A item 1 for the ordering trap.
2. **A5 rider** (`psh/builtins/read_builtin.py#_read_exact`, the
   v0.750.0 ~:688-731 region — re-locate at base): `read -t 1 -N 3`
   → psh **HUNG (>4s, killed)**; bash 5.2.26 → `rc=142 v=<>` at
   dt=1.0s. Control: psh `read -t 1 -n 3` → `rc=142 v=<>` at ~1.2s —
   the deadline plumbing EXISTS (`_read_with_timeout` / `deadline=`
   params) and `-n` uses it; `_read_exact` calls
   `read_limited(delimiter=None, max_chars=count)` passing NO deadline.

## Integrator recon facts (verify, then lean on)

- `read_all`'s current merge order is: `prefix` (already-decoded chars)
  + `pending` (decoder finalized empty) + `tail` (pushback bytes + fd
  bytes, fresh-decoded). The pushback buffer (`self._pushback`) holds
  RAW BYTES that sit BETWEEN the decoder's pending state and the fd's
  remaining bytes — whether feeding order must be
  decoder-state→pushback→fd or pushback is logically BEFORE the
  decoder's held bytes is a REAL question: probe the pushback
  producers before designing (get this wrong and you fix the split
  seam while introducing a reordering seam).
- `read_all`'s docstring claims "there is no multibyte-boundary
  concern" for the bulk path — FALSE at the cursor seam (this slot's
  subject); doc-sweep target.
- `-n` timeout shape matches bash (`rc=142`, empty var) — that path
  is your must-hold reference AND your plumbing precedent for the
  rider fix.
- The 4B.4 fence: this slot fixes the DECODER SEAM and the rider
  INSIDE the current InputCursor contract. Contract-level questions
  (dup sharing, temporary-redirect isolation — the sequence's 4B.4
  close-or-narrow item) are REPORT rows for 4B.4, never absorbed.

## Phase A must settle (probe, don't argue; bash 5.2.26 oracle)

1. **Seam census + ordering.** Where can a partial multibyte sit when
   a drain happens? Proven: timed-read timeout mid-sequence →
   `read_all`. Enumerate the rest: `read_limited`/`read_record` after
   a prior TIMEOUT left decoder state (does the NEXT timed read resume
   correctly? — probe; if yes, pin as must-hold), pushback interaction
   (census the pushback producers: what pushes back, can decoder state
   and pushback coexist, what is the correct BYTE ORDER at the merge),
   `read_all` callers census (mapfile no-count, others), EOF-with-
   pending-decoder-state, and the fd/stream duality (`_stream` path
   never has the seam — verify and state). Design lands only after
   the census.
2. **The split matrix.** Every split point × every seam route: 2-byte
   (é C3 A9: 1 split), 3-byte (€ E2 82 AC: 2 splits), 4-byte (🙂 or
   any F0-lead: 3 splits), × the seam routes from item 1. Assert BOTH
   halves of the exit criterion per cell: character identity AND byte
   round-trip. Malformed-byte matrix alongside: lone lead byte,
   orphan continuation, truncated-at-EOF sequence — all round-trip
   under surrogateescape (must-hold: the surrogateescape POLICY is
   settled; you are fixing the seam, not the policy).
3. **Rider semantics table (ruling slot (b)).** Bash-probe the full
   `-N × -t` matrix BEFORE implementing: timeout with zero bytes
   (measured: rc=142, var empty), timeout with PARTIAL input arrived
   (does bash assign the partial? rc?), `-t 0` (poll) with `-N`
   data-ready vs not, `-N` satisfied exactly at deadline, EOF before
   count vs timeout before count (distinct rc?), TTY vs pipe if
   observable, and `-t` composed with `-N 0`. Encode bash's table;
   any cell where following bash contradicts the existing `-n`
   plumbing's shape is a STOP-AND-PROPOSE, not an improvisation.
4. **End-to-end legs.** The LEDGER row names the FIFO + `read -t`
   repro — at least one end-to-end shell-level red-on-base cell per
   defect (FIFO/pipe timing cells run subprocess; see hygiene).
5. **Perf sanity (proportionate).** The seam fix touches `read_all`'s
   drain merge — a byte-path change on the bulk drain. State the
   expected cost shape (should be ~zero: same decoder, same bytes);
   if any measured figure is cited, PREMISE-BEFORE-FIGURE (4B.1
   lesson 5) and instrument it. No heavy benchmark battery required
   unless Phase A finds a hot path.

## Pins YOU create

Red-on-base: the split matrix (char-identity cells red where the seam
corrupts; round-trip cells that ALREADY pass at base are labelled
must-hold controls, not defect evidence — 4B.1 lesson: state the
measured split per class); the rider family (bounded-time subprocess
cells: psh matches bash's timeout rc/assignment per the ruled table);
end-to-end FIFO cells. Must-hold: `-n`/`-t` timeout shape (rc=142
cell), surrogateescape malformed-byte matrix, `read_all` EOF/exhaust
semantics, mapfile behavior, next-timed-read-resumes (if item-1 probe
shows it correct at base). M8 locks: seam-fix arms (empty-finalize
reintroduced; fresh-decoder reintroduced; merge-order scrambled) and
rider arms (deadline dropped again) — each with must-stay-green
discrimination rows. Composition cells: split × timeout × THEN more
input arrives; split × EOF; rider × multibyte (a `-N` count landing
mid-multibyte under `-t` — count is in CHARS, the decoder must not
hand back a partial char at deadline); pushback × pending-decoder
(per the item-1 ordering ruling).

## Must-NOT-flip

- `read -n` / `-t` composed behavior (rc=142 cell measured at base).
- surrogateescape policy for genuinely malformed bytes (exit
  criterion's second half — the malformed matrix is must-hold).
- `read_all` reads-to-EOF contract and its callers' semantics.
- InputCursor fork/clone rule (children inherit no userspace buffer —
  campaign I1; `clone_for_child` resets `input_cursors`).
- Everything 4B.1 just shipped (lookup suites) and all 4A surfaces.
- compare-bash: only the DECLARED delta cells may move; the count
  stays EXACT-or-explained-by-declared-flips, pre-registered.

## FENCES (stop-and-report BEFORE touching)

- **4B.4's subject**: InputCursor CONTRACT questions (cross-fd dup
  sharing, temporary-redirect isolation, contract width). Fixing the
  seam inside the contract = this slot; changing the contract =
  report row for 4B.4.
- **4B.3's subject**: history state machine — untouched.
- `scripting/input_sources.py` / the script reader: READ for the
  census; editing = stop-and-propose (the lazy stdin-as-script
  machinery has its own settled invariants, v0.666).
- `psh/builtins/mapfile_builtin.py` semantics beyond what the
  read_all fix transparently improves — behavior deltas there must be
  declared cells, not side effects.
- D-4A.*-s and D-4B.1-s successor rows and all D-3.x: MUST-NOT-ABSORB.

## Slot-specific test hygiene

- **Timing cells are flake risks.** Every deadline cell uses generous
  margins (timeouts ≥1s, hang-detection ≥4x the deadline), subprocess
  isolation for anything driving real fds/FIFOs, and `@pytest.mark.
  serial` where parallel siblings could starve the clock. A flaky
  timing cell that needs a re-run is a REPORT, never a silent re-run.
- FIFO/pipe cells: create fifos inside the test's own tmp scratch
  (fresh-checkout leg is standing; no fixed names in shared cwd).
- In-process InputCursor cells must close their fds (no fd leaks into
  xdist workers) — pair every `os.pipe()` with closes in finally.
- The hang-reproduction cell at BASE would hang the suite — the
  red-on-base derivation for the rider uses the subprocess-timeout
  harness shape from the dispatch probe (bounded kill), never a bare
  in-process call.

## Pre-declared ruling slots

- **(a)** Phase A table: seam census + ordering design + split-matrix
  plan (GO gate for Phase B).
- **(b)** Rider semantics: the bash-derived `-N × -t` table (timeout
  rc, partial-assignment policy, `-t 0`, EOF-vs-timeout) — encode
  exactly what bash does; divergences framed as declared deltas.
- **(c)** Anything the seam census pulls toward the 4B.4 contract or
  the script-reader fence — stop-and-propose with the census row.

## Rules

The FULL binding rule set is `docs/reviews/evidence/
boundary_remediation_2026-07/4a.1-rescue/brief.md` §Rules — binding
verbatim (never-touch list, dead-drop + ACK + md5 chain, mechanical
tip rule, ledger freeze + freeze-md5-in-declaration, per-hunk staging,
SHA paste-from-instrument, pre-registration + GO-binding citation,
RN-Cdoc, CERT-ROW-BEFORE-CLAIM, NAME-VS-BODY — your named siblings:
`tests/unit/builtins/` read/mapfile suites and any input_reader unit
suite: READ THEM FIRST — instrument discipline, the 13 D-3.4 lessons +
D-3.5 + 3.x sets, axis quantification, discharge audit, gate rules
(ONE heavy run machine-wide, unpiped pgrep, foreground, never
shell-`&`, NEVER `run_tests.py --compare-bash`), oracle rules (PATH
bash `/opt/homebrew/bin/bash` 5.2.26, explicit argv, never /bin/bash),
project tmp/ only, peer-escalation/permission-laundering wrapper).
PLUS the D-4A.1 additions (red-on-base re-derived at declared tip;
"all X except Y" as measured splits; test-created scratch dirs; no
glob-deletes outside own mktemp scratch). PLUS the 4A.2 lessons
(labelled controls for non-discriminating cells;
claim-boundaries-before-verdict; treat your own headline parity cells
as hostile). PLUS the **11 banked 4B.1 lessons, all binding here**:
(1) UNPIPED rule covers EVERY exit-status-bearing check — ruff, mypy,
pytest subsets — run unpiped or branch on the command's own exit
status, never pipe a gating check through a filter; (2) a doc sweep
for a removed/renamed symbol searches the NAME, not one syntactic
form; (3) red-on-base is well-defined ONLY per-cell (isolate
interpreters; batched collateral is not a count); (4) threat-model /
boundary declarations are OPEN CLASSES, demonstrated not enumerated
(if this slot declares any out-of-scope boundary, demonstrate each
named route); (5) a perf ruling's PREMISE is measured before its
figure is honored; (6) opposite-sign registration errors can cancel —
per-class splits are the integrity check; (7) manifests EXCLUDE
THEMSELVES; instrument/manifest handoff is BY EXPLICIT DECLARATION
(final + md5) before any copy; (8) M8 drivers diagnose a missing
companion plugin LOUDLY (build yours that way from the start);
(9) the ARTIFACT-VERIFICATION release leg is STANDING — at ceremony
the slot's defect legs re-run at a detached checkout of the TAG;
(10) the sign-off protocol is DEFINED BY YOU when we get there —
never inherited undefined; (11) CERT-ROW-BEFORE-CLAIM applies to
INTEGRATOR rows too — challenge any unbacked claim you find in mine.
New axes for this slot: **SPLIT POINT × SEAM ROUTE** (byte position
within 2/3/4-byte sequences × timed-read / pushback / bulk-drain /
exact-read routes) and **OPTION COMPOSITION × TIME OUTCOME**
(`-N`/`-n`/`-t`/`-t 0` × data-arrives / partial / timeout / EOF).

Done = Phase A table + rulings + seam fix landed with the split
matrix flipped red→green (char identity AND round-trip per cell) +
rider landed per the ruled bash table with bounded-time pins + M8 +
composition cells + must-not-flip green + declared-delta
pre-registration honored (compare-bash movement = exactly the
declared cells) + doc sweep (`read_all` docstring's false "no
multibyte-boundary concern" claim rewritten; `io_redirect/CLAUDE.md` /
`builtins/CLAUDE.md` pointers verified) + green gate + ruff + mypy +
discharge audit + complete ledger → completion report with declared
final tip + frozen ledger.
