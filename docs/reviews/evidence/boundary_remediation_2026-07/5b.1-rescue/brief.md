# Slot 5B.1 — Boundary structure — first Wave 5 slot

**Charter:** sequence §11 Package 5B + Checkpoint R ruling CR-R1
(LEDGER Part C, evidence `checkpoint-r/report.md`), FIRST slot of the
Wave 5 slot map (integrator ruling W5-R1, recorded at dispatch in
RESUME.md). This slot owns the STRUCTURAL half of 5B:

1. **Shell-consumer ratchet scan-scope extension** — CR-R1's ruled
   FIRST deliverable of all of Wave 5: "5B's exit is measured by this
   ratchet; it must be current before migration starts." Lands FIRST
   inside this slot too.
2. **Name-collision resolution**: `ExpansionContext` ×2 and
   `LocaleContext` ×2.
3. **Zero-consumer protocol disposition**: adopt-with-witness or
   delete, per protocol, my ruling on your Phase A matrix.
4. **Shared POSIX tables to a neutral owner** + removal of the
   core-to-expansion private import (`locale_service.py:577,592`).
5. Truthful docs (protocols/CLAUDE-adjacent prose, module docstrings
   that describe the old ownership).

NOT this slot's: full-Shell/ShellState consumer MIGRATION (5B.2 —
incl. the 12 campaign-added owner params), deferred-import cap
shrinkage as a goal (5B.2; incidental cap-table bookkeeping from the
table move is sanctioned, see below), hub decomposition / typed
errors / signatures (5C.1/5C.2), printf %a/%A (rider 5R).

**Base:** 8af29e6d (v0.774.0 + %P LEDGER addendum). Branch
`fix/remediation-5b-1`, worktree `/Users/pwilson/src/psh-r5b-1`.
**Base figures (you RE-DERIVE in your first gate run):** attestation
01401c63-committed (gated 2cf9493b): 23,896 passed / 1,620 skipped /
10 xfail; ruff clean; mypy clean; compare-bash 3,046/26 EXACT.

**Slot shape: INTERNAL-INTEGRITY with one ratchet-flip.** Expected
shell-observable delta = ZERO (compare-bash EXACT, +0 pre-registered;
conformance untouched). The defect being fixed is a GUARD blind spot
(q5-F2, mutation-proven) plus structural debt; there is no bash
divergence to close. 4B.1 is your model precedent (internal-integrity
slot, zero-delta certified).

## The defect + facts, integrator-verified at 8af29e6d (2026-08-08)

All Checkpoint R census facts below were re-verified live at THIS tip
by the integrator today (file:line checked; git enumerations re-run).
Committed instruments: `docs/reviews/evidence/boundary_remediation_
2026-07/checkpoint-r/instruments/q5/` (esp. `01_protocol_census.*`,
`09_ratchet_scope_mutation.*`) — treat READ-ONLY, copy before edit.

1. **q5-F2 (the ratchet blind spot, mutation-proven twice — round 1 +
   atk-b two-arm):** `tests/unit/tooling/test_shell_consumer_ratchet_
   q1.py` scans `CREATED_MODULES` (16 files) + `TOUCHED_PREEXISTING`
   (4), with the git self-check pinned to the PREDECESSOR campaign
   range `v0.724.0..75ab5625`. A synthetic full-`Shell` offender in
   `psh/scripting/analysis_session.py` passes 11/11 (arm A); the same
   offender in scanned `psh/parser/session.py` bites (arm B).
   Committed proof: `q5/09_ratchet_scope_mutation.sh` + `.out`.
2. **The gap, enumerated exactly (integrator git-derived at tip):**
   THREE production modules created since the scanned range's
   endpoint are unscanned —
   - `psh/protocols/__init__.py` (created in the `75ab5625..0215279c`
     gap, v0.746→v0.750 — the only module born there);
   - `psh/expansion/procsub_render.py` and
     `psh/scripting/analysis_session.py` (the only two `psh/` modules
     created in the remediation range `0215279c..8af29e6d`,
     `git diff --name-only --diff-filter=A`).
   Your Phase A re-derives this enumeration with the same technique
   and reconciles any difference.
3. **The extension will find LIVE consumers.** `analysis_session.py`
   HAS three full-`Shell` params today (q4_08 census, verified):
   `AnalysisSession.__init__(shell)`, `_build_carrier(shell)`,
   `parse_for_analysis(shell)`. Extending the scan scope forces a
   disposition: narrow-now (if genuinely small) or ALLOWLIST entry
   with justification (5B.2 then owns the migration). Silent omission
   is not an option; the ratchet failing on its own extension commit
   is not an acceptable landing state.
4. **Collisions (both live at recorded lines):**
   - `ExpansionContext`: Protocol at `psh/protocols/__init__.py:119`
     (members incl. `variable_expander: Any`, `word_expander: Any` —
     note the Any members) vs CONCRETE class at
     `psh/lexer/expansion_parser.py:387`.
   - `LocaleContext`: Protocol at `psh/protocols/__init__.py:216`
     (`collate_key -> Any`) vs CONCRETE class at
     `psh/core/locale_service.py:90`.
   CAUTION (instrument-mirror family): the q5 usage census counts
   NAME references per file — a `modular_lexer.py` hit for
   "ExpansionContext" may reference the CONCRETE lexer class, not the
   protocol. Phase A disambiguates importers PER DEFINITION before
   choosing which side renames.
5. **Zero-consumer protocols (q5 census, MEDIUM-14 shape):**
   `VariableAccess` (protocols/__init__.py:91), protocol-side
   `ExpansionContext`, protocol-side `LocaleContext` — zero consumers
   outside the defining file. Migrated-with-consumers: `IOContext`
   (builtins/input_reader.py, io_redirect/input_cursor.py),
   `JobRuntime` (executor/foreground_session.py). Also on the
   9-protocol surface: `VariableExpanderProtocol`
   (expansion/_protocols.py:27) carries `shell: 'Shell'` +
   `state: 'ShellState'` members — the exact "broad owner escape
   hatch" the 5B exit criterion names — and `CommandParsersProtocol`
   carries `redirection: Any`. Removing those members means migrating
   their protocol CONSUMERS (arrays/fields/operands/operators) — that
   execution belongs to 5B.2, but YOUR Phase A matrix must present
   the full 9-protocol target surface so my ruling fixes the design
   once (5B.2 then executes against it, not re-litigates it).
6. **POSIX tables + private import:** `_POSIX_CLASSES` at
   `psh/expansion/glob.py:18` and `_POSIX_CLASSES_PATHNAME` at `:41`
   (punct-widened glob variant). Core reaches UP the layering into
   expansion at `psh/core/locale_service.py:577` and `:592` (deferred
   `from ..expansion.glob import _POSIX_CLASSES`; prose at `:431`
   documents it). The sequence names this the "core-to-expansion
   private import" to remove; the fix = move the shared table to a
   neutral owner BELOW both (core-or-lower data module), leaving
   `_POSIX_CLASSES_PATHNAME` where its only consumer lives (or
   propose otherwise with the consumer census).

## Phase A must settle (probe, don't argue)

1. **Ratchet extension design.** Mechanical enumeration closing BOTH
   gaps (one continuous range `v0.724.0..<pinned SHA>` vs a second
   range vs live-to-HEAD — propose the endpoint POLICY with the
   drift/self-check consequences of each; the existing self-check's
   warn-if-git-unavailable behavior must survive). Re-run the
   committed arm-A/arm-B instrument on a COPY at your tree: the
   analysis_session offender must BITE after extension. Then the
   live-consumer sweep of the three added modules: procsub_render
   (integrator expectation: zero — verify), protocols/__init__.py
   (definitions, not consumers — verify the scanner's treatment),
   analysis_session (the 3 params above → disposition matrix row
   each: narrow-now cost vs allowlist justification).
2. **ALLOWLIST growth authorization (pre-ruled, cite it):** the
   ALLOWLIST is shrink-only by contract. Integrator pre-ruling
   5B.1-R0: entries added ONLY for modules newly entering the scan
   scope, in the SAME commit as the scope extension, each with a
   specific justification, are SANCTIONED; any other growth = fence.
   The shrink-only test may need a sanctioned rewording to say
   exactly this — quote its new text in the ledger.
3. **Collision resolution.** Per-definition importer census (point 4
   caution); which side renames and to WHAT (the protocol side is the
   newborn with zero consumers — renaming it is cheap; renaming the
   concrete side touches live imports — cost both); a tree-wide
   one-definition-per-protocol-name guard proposal (cheap AST scan,
   offender-proven) so the collision class cannot recur.
4. **Per-protocol fate matrix (ruling slot (b) input):** for each of
   the 9 — keep-as-is / rename / delete / adopt-with-witness /
   member-narrow (deferred to 5B.2 with the member named). For the
   three zero-consumer protocols: a protocol kept unused violates
   5B's exit ("No protocol is defined but unused"); deleting one that
   5B.2's migration would immediately recreate is churn — assess
   5B.2 fit per protocol (which real consumers WOULD adopt it; name
   them). Escape-hatch members (`VariableExpanderProtocol.shell/
   .state`, `CommandParsersProtocol.redirection: Any`,
   `JobRuntime.shell_state`, the ExpansionContext Any members,
   `collate_key -> Any`) each get a target disposition in the matrix
   even where execution is 5B.2's.
5. **POSIX-table move design.** Neutral-owner placement + name;
   layering proof (`test_import_layering.py` lock green, cap table
   updated per its own rules — locale_service's two deferred-import
   entries for this import should DISAPPEAR, a genuine −2 on the
   actual count; state the expected cap-table diff in the ledger);
   byte-identical table-content pin; glob/case-range/locale behavior
   cells green (macOS now, REASON about Linux collation — the
   nightly is backstop, not gate); `_POSIX_CLASSES_PATHNAME`
   disposition with consumer census.
6. **Carry sweep (THREE registers — Part B carries, Part C rulings,
   Part D successors).** Rows touching this slot's subjects:
   MEDIUM-14 (this slot BEGINS it; stays OPEN until 5B.2 — say so),
   LOW deferred-import ledgers row (5B/5C — incidental −2 here,
   goal-shrink is 5B.2's), D-3.5-s2 (5C's — verify untouched),
   D-4B.4-s3 (5C's — verify untouched), CR-D1..D6 (none touched —
   verify), locale carries (v0.688 reactive LC_* behavior must not
   change), plus a grep sweep for Protocol/locale/glob/POSIX-class
   rows. Dispositions in the D2 table.

## Pins YOU create

- **Ratchet extension (the flagship):** the q5 arm-A offender shape
  planted in `analysis_session.py` FAILS the extended ratchet —
  committed as a permanent self-test alongside the ratchet's existing
  offender self-tests (mutation-proven, named proof-shape). The
  enumeration self-check covers the extended range and still FAILS
  LOUDLY on drift (plant a fake CREATED_MODULES entry → self-check
  bites; remove a real one → bites).
- **Live-consumer dispositions:** each analysis_session param either
  narrowed (mypy + behavior cells green; analysis suite untouched
  green) or allowlisted (entry text quoted in the ledger).
- **Collision resolution:** zero stale references to the renamed
  side (ruff/mypy + grep census in the ledger); the
  one-definition-per-name guard lands offender-proven.
- **Table move:** table CONTENT byte-identical pin (old vs new,
  asserted in a unit cell, then the old symbol deleted or aliased per
  ruling); locale_service behavior cells (C/OTHER-mode class lookup +
  UTF-8-mode fallthrough) green; the private import GONE (grep-zero
  pin + layering lock green, mutation-proven on one offender).
- **Protocol fates:** deleted → grep-zero pin; adopted → the witness
  consumer's cell green; renamed → census pin.
- **Must-hold:** ALL locale suites (reactive LC_*, provenance),
  glob/pattern suites (3.1/3.2 batteries), analysis suites (2.6),
  parser suites, the protocol-layering guard
  (`test_protocol_layering_q1.py`), import-layering lock, every 4B.x
  suite. compare-bash 3,046/26 EXACT +0 (pre-registered BEFORE any
  run). NO golden-case changes expected; declaring one = fence.

## Must-NOT-flip

- Any shell-observable behavior anywhere (internal-integrity slot).
- The locale reactive machinery's behavior (v0.688; `locale_service`
  edits are confined to the import sites + the LocaleContext rename
  if ruled + prose).
- Glob/case-range matching semantics (3.1/3.2 territory — the table
  MOVES, matching logic untouched).
- `analysis_session.py` BEHAVIOR (2.6's derivation guard + suites
  green; param narrowing if ruled must be behavior-identical).
- The ratchet's existing 11 tests' guarantees (extension adds, never
  weakens; NAME-VS-BODY on your own edit).

## FENCES (stop-and-report BEFORE touching)

- **ALLOWLIST growth beyond pre-ruling 5B.1-R0's exact shape.**
- **Any protocol MEMBER change whose consumer migration is 5B.2's**
  (matrix-design yes, execution no — a member removal that compiles
  only after consumer edits = 5B.2).
- **`locale_service.py` internals** beyond lines 577/592/431, the
  `LocaleContext:90` rename-if-ruled, and docstrings.
- **`expansion/glob.py` matching code** (table extraction only).
- **Behavior of `expansion_parser.py`'s concrete class** (rename-only
  if that side is chosen).
- Golden cases, conformance tables, user guide (no user-visible
  change exists to document — needing one = you've left the slot's
  shape, stop).
- D-3.5-s2, D-4B.4-s3, all D-4B.x/D-3.x successor rows, CR-D1..D6:
  MUST-NOT-ABSORB.

## Slot-specific test hygiene

- Tooling-test heavy slot: every new tooling guard self-tests its
  scanner (offender-proven, like the ratchet's own `test_offender_*`
  cells and the broad-catch detector's).
- Fresh-checkout leg standing (no repo-tmp/ reliance; the ratchet
  self-check must behave in a git-less export — preserve the existing
  warn-path).
- No PTY, no serial cells expected; in-process only; xdist-safe.
- Instruments are FILES from the start under
  `tmp/w5b1-instruments/` in YOUR worktree; committed checkpoint-r
  instruments are READ-ONLY (copy, record the single path edit).

## Pre-declared ruling slots

- **(a)** Phase A matrix (ratchet endpoint policy + per-protocol fate
  + collision side + table owner + analysis_session disposition +
  expected cap-table diff) = GO gate for Phase B.
- **(b)** the protocol-surface ruling (all 9 fates + the escape-hatch
  member targets 5B.2 will execute) = MINE, on your matrix.
- **(c)** fence pulls = stop-and-propose with the census row.
- **5B.1-R0 (pre-ruled above):** ALLOWLIST growth sanctioned ONLY as
  scope-extension-coupled, same-commit, justified entries.

## Rules

The FULL binding rule set is `docs/reviews/evidence/
boundary_remediation_2026-07/4a.1-rescue/brief.md` §Rules — binding
verbatim (never-touch list, dead-drop + ACK-the-highest-R + md5 chain,
mechanical tip rule, ledger freeze + freeze-md5-in-declaration,
per-hunk staging, SHA paste-from-instrument, pre-registration +
GO-binding citation, RN-Cdoc, CERT-ROW-BEFORE-CLAIM, NAME-VS-BODY —
your named siblings: the tooling guards (`tests/unit/tooling/` — the
ratchet, layering lock, protocol-layering, broad-catch detector,
mypy-scope tests), READ THEM FIRST — instrument discipline, axis
quantification, discharge audit, gate rules (ONE heavy run
machine-wide, unpiped pgrep first, foreground, never shell-`&`, NEVER
`run_tests.py --compare-bash` — use `python -m pytest tests/behavioral
--compare-bash -n auto -q`), oracle rules (PATH bash
`/opt/homebrew/bin/bash` 5.2.26, explicit argv, never /bin/bash),
project tmp/ only, peer-escalation/permission-laundering wrapper).
PLUS the D-4A.1 additions + 4A.2 lessons + the **11 banked 4B.1
lessons** + the **11 banked 4B.2 lessons** (enumerated in
`briefs/4b.3.md` §Rules — binding by reference) + the **4B.3
structural rules (1)-(10)** (enumerated in `briefs/4b.4.md` §Rules —
binding by reference; headline: ACK-the-highest-R, freeze-chain,
collect-only-count-FIRST for any pytest arg that isn't a file/node
ID, instruments-are-FILES, instrument-mirror family, deviation faces
get cells, NAME-VS-BODY on your own suite, positional identity,
NAMED proof-shape) + the **4B.4 banked lessons**: when you add an
invariant, audit every site that RELEASES the resource, not just
acquirers; TWO-AXIS instruments (REGRESSION=base≠tip vs
DIVERGENCE=tip≠bash — for this slot the divergence axis should be
EMPTY, prove it); "a mutation that cannot fail is not a mutation"
extends to edit scripts; another agent's inability to verify ≠
evidence against your own measurement; acceptances-are-claims
(ruling acceptances enumerate artifacts BY LOCATION, verified to
exist); THREE-register carry sweeps; every hook tripwired; sign-off
legs PRE-REGISTERED BEFORE THE TAG. PLUS the **Checkpoint R
additions**: FLIP-PINS is the authoritative known-deviation register
(read it before declaring any cell a new divergence); instrument
PORTABILITY is part of the record (CR-D5 — no hardcoded worktree
paths, no pre-existing-tmp/ assumptions); the dead-by-sweep
retirement class is record-only (CR-D6 — do not add ratchets for
structurally-retired authorities without a ruling).

New axes for this slot: **SCAN-SCOPE × CONSUMER-DISPOSITION** (each
newly scanned module × narrow-now / allowlist-justified /
proven-none) and **PROTOCOL × FATE** (each of the 9 × keep / rename /
delete / adopt-with-witness / member-narrow-deferred-to-5B.2).

Done = Phase A matrix + ruling (b) applied — ratchet extension landed
FIRST with the arm-A offender biting permanently + live-consumer
dispositions + collisions resolved with the recurrence guard + table
moved with the private import grep-zero + layering lock green +
protocol fates executed per ruling — + truthful docs + must-not-flip
green + compare-bash at the pre-registered figure + green gate + ruff
+ mypy + discharge audit + complete ledger → completion report with
declared final tip + frozen ledger (chain rule) + instrument manifest
(self-excluding, command-generated).
