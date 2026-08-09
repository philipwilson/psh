# Slot 5C.1 — Typed errors + boundary signatures — third Wave 5 slot

**Charter:** sequence §11 Package 5C (first half) + Checkpoint R ruling
CR-R1 (LEDGER Part C) + Wave 5 slot map W5-R1: "**5C.1** typed errors +
boundary signatures (7 BROAD_MASKING + 24 terminal handlers; D-3.5-s2;
campaign-created modules into disallow_untyped_defs; 648/488 census)".
This slot owns the REST of MEDIUM-12 (the row CLOSES with this slot if
its exit is met — subscript + expansion/arith halves already carved by
2.3/3.5, DROPPED-AS-DONE per CR-R1) plus the boundary-seam first half
of MEDIUM-16 (row stays OPEN; 5C.1 lands the seam set + ratchet
currency; per-package depth is post-campaign). Deliverables:

1. **The 7 BROAD_MASKING ledger entries**
   (`tests/unit/tooling/test_broad_valueerror_catch_q2.py`, the
   shrink-only Q2 ledger — READ ITS HEADER FIRST, it defines the
   contract). The seven keys at base:
   - `psh/builtins/directory_stack.py` popd VE net (the sibling
     `_popd_no_cd` is the codebase's own correct narrow form — the
     ledger reason says so)
   - `psh/builtins/directory_stack.py` dirs -N VE net
   - `psh/builtins/disown.py` VE net around int(spec) + job lookups
   - `psh/builtins/parse_tree.py` debug-builtin VE/TE/AE pipeline net
   - `psh/builtins/read_builtin.py` whole-record-engine VE net (no
     int()/documented-VE source in the body per the reason text)
   - `psh/parser/combinators/parser.py` can_parse AE/IE/TE/ParseError
     net (reason text itself says "explicitly outside the production
     quality bar (parser/CLAUDE.md) — flagged, low priority" —
     justified-keep with corrected reason is a LEGITIMATE disposition
     here; ruling slot (b) decides)
   - `psh/utils/ast_debug.py` formatter-selection VE/TE/AE
     compound-statement masker
   Per-entry disposition: NARROW (tighten the try body to the
   documented-signal expression and/or type the error at the raise
   site — the 2.3/3.5 model) or JUSTIFIED-KEEP with corrected reason.
   The ledger genuinely SHRINKS for every narrowed entry (the Q2
   stale-entry test forces it — 3.5 precedent). Exit: every entry
   dispositioned by ruling; pre-register the final BROAD_MASKING count.
2. **The 24 terminal except-Exception handlers** (0 bare; Checkpoint R
   census q5-F7, instrument
   `checkpoint-r/instruments/q5/06_broad_except_ast.py` — re-run at
   base, reconcile). The 24 at CR tip:
   `core/locale_service.py:488,502`; `core/process_lease.py:565`;
   `core/trap_manager.py:480`; `executor/child_policy.py:366,374,452,582`;
   `executor/command.py:290`; `executor/function.py:188`;
   `executor/process_launcher.py:374`; `executor/strategies.py:270`;
   `interactive/prompt.py:135`; `interactive/rc_loader.py:48`;
   `interactive/repl_loop.py:145`; `io_redirect/file_redirect.py:212,913,1327`;
   `io_redirect/manager.py:673`; `lexer/recognizers/registry.py:78`;
   `scripting/analysis_session.py:487`; `scripting/source_processor.py:545`;
   `scripting/visitor_modes.py:90`; `utils/signal_utils.py:258`.
   Per-handler disposition: TERMINAL-BY-DESIGN with a SPECIFIC reason
   (fork boundary — a child must never propagate past the fork, the
   os._exit discipline; REPL survival; defect-reporter
   must-not-itself-raise; signal-context) or NARROW. Deliver a
   SELF-MAINTAINING classification mechanism (a ledger test in the Q2
   shape: every terminal handler classified, stale entries forced out,
   new unclassified handlers loud) — propose the mechanism in Phase A,
   ruling slot (c) fixes it. Strict-errors interplay is a must-not-flip
   (below).
3. **D-3.5-s2** — `psh/builtins/let_builtin.py` `except (ValueError,
   ArithmeticError)` around `evaluate_arithmetic(expr, shell,
   arith_source_quotes=False)`. NOTE (Checkpoint R corrected the
   LEDGER's wording): this catch is ALREADY the typed pair — the
   residue is the 3.5 DEADNESS question: which of the two legs can
   actually fire? 3.5 forcing-proved the VE leg dead at its sites and
   the deadness argument TRANSFERS (named in expansion/CLAUDE.md
   §error-typing as the residual). Force both legs empirically
   (probe battery: what escapes evaluate_arithmetic on syntax error /
   division by zero / bad subscript / non-numeric?); narrow to the
   real contract or pin justified. Bash-verify any `let` diagnostic
   cell you touch.
4. **Boundary signatures — D-5B.2-s2 retirement steps** (LEDGER Part D
   row, binding):
   a. **Type `evaluate_arithmetic`'s signature**
      (`psh/expansion/arithmetic/evaluator.py:677` — the `shell` param
      is UNANNOTATED; it is one of the 3 whole-Shell forwards that
      justified keeping `VariableExpanderProtocol.shell`). Typing it
      is the named retirement step. What type? That is a Phase A
      design question — the measured usage of `shell` INSIDE
      evaluate_arithmetic (and everything it forwards to) decides;
      D-5B.2-s1's lesson binds: design from MEASURED usage census,
      never a guess. If the honest answer today is `'Shell'`
      annotated, that is still a signature-census win (Method A
      counts missing annotations) — but measure first; a narrower
      protocol may genuinely fit.
   b. **Type `PromptExpander`** (`psh/interactive/prompt.py:13` — the
      third whole-Shell forward) — same treatment.
   c. **The manager-surface protocol for the NINE-hop family** (8 hops
      in the four pinned mixin files + the ninth PRE-EXISTING in
      concrete `VariableExpander`, `psh/expansion/variable.py:182`).
      Measured hop usage (D-5B.2-s2, committed 5b.2-rescue cells):
      `.subscript` ×4+1, `.command_sub` ×2,
      `.execute_arithmetic_expansion` ×1, `.tilde_expander` ×1 — ZERO
      overlap with `ExpansionRuntime`'s members (measured, don't
      re-derive from memory — re-measure at base). Design the protocol
      against exactly this usage (name, members, location = ruling
      slot (e)); adopting it retires the manager hops' untyped reach.
      5B.2 lesson 2 binds: typing verifies only with a consumer in the
      checked set — every new protocol member needs a
      mypy-load-bearing witness (mutation bites).
5. **Campaign-created modules into `disallow_untyped_defs` +
   D-5B.1-s2 twin-guard currency**
   (`tests/unit/tooling/test_mypy_untyped_defs_coverage.py`):
   - The guard's git range is STALE at `v0.724.0..75ab5625` (the OLD
     boundary campaign) with its own private
     `_warn_selfcheck_unverified` copy — exactly the q5-F3 mechanism
     and the same scope-staleness class 5B.1 fixed for the consumer
     ratchet. Give it the 5B.1 treatment: currency FIRST (the
     structure that made the consumer ratchet current — post-endpoint
     scanned list + coverage assertion with ancestor-checked loud
     vacuity — is your model; adapt, don't copy blind).
   - The remediation-campaign-created modules join MIGRATED_MODULES +
     pyproject overrides (`disallow_untyped_defs` +
     `disallow_incomplete_defs` both true). Integrator-measured at
     dispatch (`git log --diff-filter=A v0.750.0..d0956bed -- 'psh/*.py'`):
     **THREE** — `psh/expansion/procsub_render.py` (2.3),
     `psh/scripting/analysis_session.py` (2.6a),
     `psh/utils/posix_classes.py` (5B.1). q5-F3 counted TWO with 4
     incomplete private defs at CR tip — posix_classes.py postdates
     that census; RE-DERIVE the set and the incomplete-def count at
     base; complete the defs; overrides land in the same commit as
     the guard growth.
6. **The 648/488 census** (MEDIUM-16 exit measurement): re-run
   `checkpoint-r/instruments/q5/05_sig_census.py` at base, reconcile
   to 648 Method A / 488 Method B (Wave 5 baseline per CR-R1 =
   Checkpoint R census). Phase A proposes the BOUNDARY-SEAM set (the
   cross-package surfaces among the 648 — §11: "boundary seams
   annotated first, then per-package") and a measured reduction
   target; ruling slot (d) fixes the figure. Items 4a/4b/5 all land
   inside this census — count them in the target, sourced per-file
   (5B.1 lesson 3: every pre-registration term needs a SOURCE).
7. Truthful docs (expansion/CLAUDE.md §error-typing residual text,
   any CLAUDE.md/docstring describing the old broad-catch state,
   guard header prose).

NOT this slot's: hub decomposition + dead API (5C.2 — 60-hub census,
D-5B.2-dead `foreground_pgid` write-only, D-4B.4-s3
`with_redirections`; MUST-NOT-ABSORB); printf %a/%A (rider 5R);
deferred-import caps (5B.2's floor 66 entries / 177 cap == 177 actual
/ 0 slack is LOCKED by the cap==actual exactness cell — if a signature
edit would move a deferred import, that's a FENCE, and the 115/62
hoist path is the LOW row's named successor, not yours); re-opening
ANY 5B.2 disposition (the seven §A6 member fates, the 12-param
dispositions, the VariableAccess deletion — all BINDING); the full
648-def sweep (boundary seams + the ruled set only — not a boiled
ocean); D-5B.1-s1 (order-dependence flake — record and route if
tripped, never fix here).

**Base:** d0956bed (v0.776.0 + 5B.2 addendum; local main ==
origin/main; nightly at 4c333a78 GREEN 2026-08-09 = first Linux for
v0.773–776). Branch `fix/remediation-5c-1`, worktree
`/Users/pwilson/src/psh-r5c-1`. **Base figures (you RE-DERIVE in your
first gate run):** attestation f6bd54f5-committed (gated d8166242):
23,941 passed / 1,620 skipped / 10 xfail; ruff clean; mypy clean;
compare-bash 3,046/26 EXACT. Consumer ratchet ALLOWLIST 9 entries;
caps floor 66/177/177/0 (locked, not yours).

**Slot shape: INTERNAL-INTEGRITY with a defect-path caveat.** Expected
shell-observable delta on ALL non-defect paths = ZERO (compare-bash
3,046/26 EXACT +0 pre-registered; conformance untouched). Narrowing a
handler changes ONLY what happens when an internal defect fires — the
strict-errors taxonomy (psh/core/CLAUDE.md) is the frame: a formerly
masked defect surfacing loudly under PSH_STRICT_ERRORS is the POINT,
a user-visible wording/exit change on a valid- or invalid-INPUT path
is a REGRESSION (or a ruling — see fences). Every narrowing carries a
forcing instrument: non-defect path byte-identical (REGRESSION axis
base≠tip EMPTY) + the defect path correctly reclassified (the forced
defect now surfaces as the typed/strict-errors shape). 2.3 and 3.5
are your model precedents — read their LEDGER rows and evidence.

## Phase A must settle (probe, don't argue)

1. **Census reconciliation at base.** Copy (READ-ONLY originals) and
   re-run `06_broad_except_ast.py` and `05_sig_census.py` at
   d0956bed; reconcile to 24/0 and 648/488; enumerate any drift with
   per-file sources. Verify the BROAD_MASKING ledger still has
   exactly the 7 keys (the Q2 suite passing at base is your check).
2. **Per-masker narrow designs (7 rows).** For each: what the try
   SHOULD wrap (the documented-signal expression), which error type at
   which raise site, what the forced-defect path becomes, whether any
   USER-visible diagnostic changes on invalid-input paths (bash-verify
   those cells BOTH sides — popd/dirs/disown/read/let invalid-arg
   diagnostics; enumerate the probe battery). For can_parse: the
   justified-keep case laid out honestly against the narrow case.
3. **Per-handler classification (24 rows).** Classify each with the
   mechanism named (which fork/REPL/reporter/signal context makes it
   terminal) and NARROW candidates argued from what the try body can
   actually raise. Propose the self-maintaining ledger mechanism
   (test name, key shape, stale-forcing, offender arm). The four
   child_policy handlers and process_launcher sit at the fork
   boundary — child-status/exit-trap semantics are 1.3b territory,
   signature-only changes there.
4. **let_builtin forcing battery** (item 3 above): per-leg
   fire/dead verdict with transcripts.
5. **Boundary-seam set + signature designs.** The seam enumeration
   from the census (propose the definition operationally — e.g.
   cross-package callable surfaces — so the set is derivable, not
   curated); evaluate_arithmetic `shell`-usage census (what it and its
   forwards actually reach) → proposed type; PromptExpander same; the
   manager-surface protocol design (members from the measured hop
   usage, name, home, witness plan per 5B.2 lesson 2); proposed
   census reduction target with per-file terms.
6. **Twin-guard currency design.** Endpoint/structure (the 5B.1
   three-list model adapted), MIGRATED_MODULES growth set (re-derived),
   the incomplete-def completion list, whether the private
   `_warn_selfcheck_unverified` copy dedups against the consumer
   ratchet's (propose; small shared helper is fine if BOTH guards'
   self-tests stay independent — don't force it).
7. **Carry sweep (THREE registers — Part B carries, Part C rulings,
   Part D successors).** Rows touching this slot: MEDIUM-12 (this
   slot ENDS it if exit met — say what closure requires), MEDIUM-16
   (partial: say what 5C.1 lands vs leaves), D-5B.1-s2 (THIS slot
   discharges), D-3.5-s2 (THIS slot discharges), D-5B.2-s1 (design
   input — cite it in the protocol design), D-5B.2-s2 (THIS slot
   executes the retirement steps; say whether `.shell` can then
   actually retire or what remains), D-5B.2-dead/D-4B.4-s3 (5C.2's —
   verify untouched), D-5B.1-s1 (flake — know it exists), CR-D1..D6
   (none touched — verify), 1.3b child-status rows, strict-errors
   taxonomy rows. Dispositions in the D2 table.

## Pins YOU create

- **Per narrowed masker:** forcing instrument TWO-AXIS (REGRESSION
  base≠tip on non-defect paths EMPTY; the forced defect reclassified
  as designed); the Q2 ledger entry removed in the SAME commit as its
  narrowing (the stale-entry test forces this — let it); invalid-input
  diagnostic cells bash-verified both sides.
- **Terminal-handler ledger:** offender-proven (a synthetic
  unclassified `except Exception` bites; a stale entry bites; control
  arm — a classified handler passes); every classification reason
  SPECIFIC (the Q2 reason-quality test is your model).
- **Signatures:** every new annotation mypy-LOAD-BEARING (mutation
  witness: a wrong-typed call/member bites — 5B.2 lesson 2; a
  signature nobody checks is unobserved); the new protocol
  offender-proven (re-widening bites a named guard).
- **Twin guard:** currency structure offender-proven (synthetic
  post-endpoint module with incomplete defs bites; ancestor-checked
  vacuity path loud); MIGRATED_MODULES == git-derived set self-check
  still forced; the growth lands with the overrides in one commit.
- **Census:** final Method A/B figures pre-registered from per-file
  terms BEFORE the gate run; the reduction accounted per-file.
- **Must-hold:** strict-errors suites, 2.3/3.5 suites (subscript
  ratchet, typed-expansion locks, Q2 suite), child-status/exit-trap
  suites (1.3b), REPL/interactive suites, trap/signal suites, locale
  suites, analysis-session suites (2.6 guard), consumer ratchet (all
  arms), import-layering lock + caps cell (untouched), mypy-scope
  guard, every 4B.x/5B.x suite. compare-bash 3,046/26 EXACT +0
  (pre-registered BEFORE any run). NO golden-case changes expected;
  needing one = fence.

## Must-NOT-flip

- Any shell-observable behavior on non-defect paths (valid AND
  invalid INPUT are both non-defect: `popd bogus` prints what it
  printed, exit codes identical).
- Strict-errors taxonomy semantics: expected shell errors
  (PshError/OSError/SyntaxError/RecursionError) still pass through;
  internal defects still surface under PSH_STRICT_ERRORS=1; the
  swallow-to-1 path where deliberately exercised by tests.
- Child-status/exit-trap semantics (child_policy/process_launcher
  handlers return the same statuses; a child NEVER propagates past
  the fork — os._exit discipline intact).
- REPL survival (repl_loop's terminal handler keeps the session alive
  on a defect; narrowing there needs the strongest justification).
- The defect-reporter's own must-not-raise property
  (internal_errors — it's in NARROW_SAFE, not yours, but adjacent).
- Reactive LC_* machinery (locale_service handlers are in the 24).
- The Q2 ledger's shrink-only contract and the consumer ratchet's
  guarantees (extension adds, never weakens; NAME-VS-BODY on your own
  edits).
- The caps floor (66/177/177/0) — signature/annotation work must not
  move any deferred import.
- `let` arithmetic semantics incl. the W2/CV1 B1 quote-provenance
  behavior (arith_source_quotes=False stays).

## FENCES (stop-and-report BEFORE touching)

- **Any user-visible diagnostic change on an input path** (a masker
  narrowing that would alter what `popd letters` / `dirs +9` /
  `disown %bogus` / `read` / `let bad` PRINTS or returns) — STOP with
  the bash-verified both-sides cell; wording deltas are a RULING (2.3
  granted builtin translations this way), possibly with conformance
  rows — never improvised.
- **Widening ANY protocol surface**; growing the new manager-surface
  protocol beyond the measured hop usage.
- **ALLOWLIST growth** outside the 5B.1-R0 extended shape (same-commit
  detector/scope-extension-coupled, individually justified).
- **Caps floor changes** / any deferred-import movement.
- **5C.2 surfaces:** hub bodies, `foreground_pgid`,
  `with_redirections` — MUST-NOT-ABSORB.
- **D-5B.1-s1** flake: record (SHA, selection, both-SHA replay), route
  to the row, never fix.
- Golden cases, conformance tables, user guide — EXCEPT via the
  diagnostic-wording ruling route above.
- CR-D1..D6, all other successor rows: MUST-NOT-ABSORB.
- A narrowing whose forcing instrument shows the defect path was
  LOAD-BEARING for real behavior (something non-defect actually
  flowed through the broad catch) — that's a census row + stop, not
  an improvisation (5B.2's (c1)/(c2) fence returns are the model:
  measurement-driven fence pulls got RULED, and one became a better
  design).

## Slot-specific test hygiene

- Tooling-heavy again: every new/extended guard self-tests its
  scanner offender-proven, with control arms for exclusions.
- `PYTHONDONTWRITEBYTECODE=1` in EVERY mutation driver (5B.1 lesson 1).
- RED arms assert failure REASON, not just outcome (5B.1 lesson 2).
- Any `str.replace` in an instrument: ANCHORED, `count=1` (5B.2
  lesson 6 — D-8's seeding bug).
- Pre-registration terms from per-file `--collect-only` counts ONLY.
- collect-only count FIRST for any pytest arg that isn't a file/node
  ID.
- Fresh-checkout leg standing; BOTH guards' git-less warn paths must
  survive your currency work.
- Forced-defect instruments: inject via monkeypatch/seeded-defect in a
  SUBPROCESS or with strict-errors explicitly set per the taxonomy —
  never leave a seeded defect in the tree past its instrument.
- No PTY, no serial cells expected (repl_loop/prompt narrowings that
  need interactive cells: subprocess with `-i` or pexpect under the
  existing serial-marked patterns — flag in Phase A if needed).
- Instruments are FILES from the start under `tmp/w5c1-instruments/`
  in YOUR worktree; committed checkpoint-r + 5b.2-rescue instruments
  are READ-ONLY (copy, record the single path edit).

## Pre-declared ruling slots

- **(a)** Phase A matrix (censuses + 7 masker designs + 24 handler
  classifications + let forcing + seam set + signature designs +
  twin-guard design + carry sweep) = GO gate for Phase B.
- **(b)** per-masker narrow-vs-justified-keep + any diagnostic-wording
  deltas = MINE, on your designs.
- **(c)** terminal-handler mechanism + per-handler classes = MINE.
- **(d)** boundary-seam set + census reduction target (Method A/B
  figures) = MINE, on your enumeration.
- **(e)** manager-surface protocol (name, members, home, witness plan)
  + evaluate_arithmetic/PromptExpander types = MINE, on your usage
  censuses.
- **(f)** fence pulls = stop-and-propose with the census row.
- **5B.1-R0 (pre-ruled, extended shape):** ALLOWLIST additions ONLY as
  same-commit scope-/detector-extension-coupled justified entries.

## Rules

The FULL binding rule set is `docs/reviews/evidence/
boundary_remediation_2026-07/4a.1-rescue/brief.md` §Rules — binding
verbatim (never-touch list — devs never touch version.py / CHANGELOG
/ README / ARCHITECTURE / docs/reviews/README / FLIP-PINS / LEDGER;
never push/PR/tag — dead-drop + ACK-the-highest-R + md5 chain,
mechanical tip rule, ledger freeze + freeze-md5-in-declaration +
freeze-chain, per-hunk staging, SHA paste-from-instrument,
pre-registration + GO-binding citation, RN-Cdoc,
CERT-ROW-BEFORE-CLAIM, NAME-VS-BODY — your named siblings: the
tooling guards (`tests/unit/tooling/` — Q2 ledger, consumer ratchet,
layering lock, protocol-layering, mypy-scope, mypy-untyped-defs
twin, posix-class ownership), READ THEM FIRST — instrument
discipline, axis quantification, discharge audit, gate rules (ONE
heavy run machine-wide, unpiped `pgrep -f pytest` AND `pgrep -f
run_tests` first, foreground, never shell-`&`, NEVER `run_tests.py
--compare-bash` — use `python -m pytest tests/behavioral
--compare-bash -n auto -q`), oracle rules (PATH bash
`/opt/homebrew/bin/bash` 5.2.26, explicit argv, never /bin/bash),
project tmp/ only, peer-escalation/permission-laundering wrapper,
never touch the parallel session's uncommitted files (`d/`,
`decomment.py`, `docs/reviews/ground_up_*` — may already be gone;
absence ≠ license)). PLUS the D-4A.1 additions + 4A.2 lessons + the
11 banked 4B.1 lessons + the 11 banked 4B.2 lessons (`briefs/4b.3.md`
§Rules, by reference) + the 4B.3 structural rules (1)–(10)
(`briefs/4b.4.md` §Rules, by reference) + the 4B.4 banked lessons
(release-site audits, TWO-AXIS instruments, mutations-that-cannot-
fail, acceptances-are-claims, THREE-register carry sweeps, every hook
tripwired, sign-off legs PRE-REGISTERED BEFORE THE TAG) + the
Checkpoint R additions (FLIP-PINS authoritative deviation register;
instrument PORTABILITY; CR-D6 record-only retirement class) + the
FIVE 5B.1 banked lessons (D-5B.1-lessons: PYTHONDONTWRITEBYTECODE;
RED reason-assert; pre-registration SOURCES; mid-slot main advances
merge before the attestation gate — integrator executes, YOU flag any
advance you observe; explicit wake-up nudges BOTH directions every
entry + re-read inbox at START of every turn + ACK-the-highest-R) +
**the SIX 5B.2 banked lessons (LEDGER D-5B.2-lessons, binding
verbatim):**

1. A REACH census is not a USAGE census — measure what consumers call
   ON the reached object.
2. "mypy-clean" on a zero-consumer surface means UNOBSERVED — typing
   changes verify only with a consumer in the checked set (and
   mutable protocol attrs are invariant: read-only properties are the
   correct narrow shape).
3. A detector arm that cannot fire independently of a sibling is not
   a new detector — subsumption is measured (arm-neutered control),
   never assumed.
4. Verify the edit you will make, not a weaker proxy — add-import vs
   move-import differ under partial initialization, and joint
   feasibility composes in NEITHER direction.
5. Foreground what you wait on — a poll must match the state you
   want, never the absence of a process whose name the watcher's own
   command line contains (self-match deadlock).
6. An unanchored `str.replace` in an instrument is a seeding bug
   waiting to happen — anchor and `count=1`.

New axes for this slot: **MASKER × ROUTE** (each of the 7 × narrow /
justified-keep × forcing cell × diagnostic cell) and **HANDLER ×
CLASS** (each of the 24 × terminal-class-with-mechanism / narrowed ×
ledger row) and **SEAM × SIGNATURE** (each ruled seam fn × annotated /
justified × mypy-witness cell).

Done = Phase A matrix + rulings (b)–(e) applied — all 7 maskers
dispositioned per ruling with forcing instruments + the 24 handlers
classified under the ruled self-maintaining mechanism + let legs
forced and dispositioned + evaluate_arithmetic/PromptExpander typed
per ruling + the manager-surface protocol landed witness-proven (or
fence-resolved) + the campaign-created modules under both disallow
flags with the twin guard CURRENT + census at the ruled target with
per-file accounting — + truthful docs + must-not-flip green +
compare-bash at the pre-registered figure + green gate + ruff + mypy
+ discharge audit + complete ledger → completion report with declared
final tip + frozen ledger (chain rule) + instrument manifest
(self-excluding, command-generated).
