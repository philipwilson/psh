# INTEGRATOR-INBOX — slot 4A.1 (dev-4a-1)

Dead-drop protocol: THIS FILE is authoritative over the message channel.
Read it at the start of every turn AND immediately before every
SendMessage. ACK every ruling by number in your next message. Rulings are
appended top-down, numbered R0, R1, ... Expect message/ruling crossings —
the file wins.

---

## R0 — Dispatch + stage gate (2026-08-06, integrator)

1. **Your charter is `tmp/remediation-ledgers/BRIEF-4a1.md`** (in this
   worktree). Read it END TO END before any code. The brief's Rules
   section is binding verbatim, including the peer-escalation /
   permission-laundering wrapper, the never-touch file list, the ONE
   heavy run machine-wide rule, and the GO-binding pre-registration
   citation requirement.
2. **Stage gate:** Phase A (probe + disposition table) FIRST. No
   production edit lands before the Phase A report is ruled. Your first
   deliverable is: ACK of R0 + a Phase A plan (what you will probe, in
   what order, with what instruments — including how each probe isolates
   the process-wide coordinator singleton).
3. **Three ruling slots are pre-declared** (brief §Pre-declared ruling
   slots): (a) disposition table, (b) SIGNALS lease shape, (c) quarantine
   model + GC-handover. Request each explicitly; do not begin the
   corresponding Phase B work before its ruling arrives.
4. **Brief-time evidence disclosure:** the integrator's A5 probe
   (`tmp/w4a1-dispatch-probes/probe_a5_poisoning.py` in the MAIN
   checkout; copy it or re-derive — do NOT run instruments from inside
   the main checkout's live tree, B71) reproduced S1b/S2/S3 RED at base
   a64eb6e8 and S1 GREEN (first-owner self-heal). S1's green cell is a
   MUST-HOLD row. If YOUR re-derivation contradicts any of these four
   cells, STOP-AND-PROPOSE with both instruments' outputs before
   proceeding.
5. **Fences in force:** 4A.2 (shutdown-phase ordering, MEDIUM-1,
   huponexit/PTY), 4B.1-4B.4, all D-3.4-s / D-3.5-s successor rows,
   fork-side child signal policy. Finding an adjacent defect is a REPORT
   (ledger row + SendMessage), never a fix.
6. **Known-flake standing order:** if any gate run fails on the exit-trap
   flake family, that is INSTANCE 3 (recurrences #1, #2 recorded in
   `nightly-status.md`) — the third-instance-investigates rule fires:
   report immediately with the transcript; do NOT silently re-run.
7. **Worktree discipline:** you work ONLY in /Users/pwilson/src/psh-r4a-1
   on branch fix/remediation-4a-1. Never touch the main checkout's
   working files; never measure from inside anyone's live worktree
   (detached probe checkouts only, removed after).

— integrator

---

## R1 — Phase A plan APPROVED with additions (2026-08-06, integrator)

1. **APPROVED** as the R0-point-2 stage-gate ruling. The
   method-independence design is accepted as genuinely non-mirroring
   (per-cell fresh subprocess vs my one-process sequential probe;
   machine-derived `CELL … EXPECT/GOT` counts vs prose; public+private
   census required to AGREE; detached red-on-base checkout). Proceed to
   build and run I-A → I-C → I-D → I-B.
2. **Pointer verification (integrator, at a64eb6e8):** your three cited
   claims check out — `_StdStreamBaseline.__init__` stores `state`
   (:109); `self.state.streams.restore(self.overrides)` at :169 EXACT;
   and the sole-use claim verified by census (exactly two appearances of
   `self.state` in the class: the `__init__` store and the :169 use;
   `relocate_away_from` never touches it). Your NOT-yet-certified
   flagging stands — the probes decide.
3. **ADD cell (I-B):** baseline-dup failure injection — the
   `except BaseException` arm of `_acquire_permanent_stream_lease`
   (file_redirect.py:1018-1027). Force the `fcntl.F_DUPFD_CLOEXEC` step
   to fail (RLIMIT_NOFILE exhaustion in the cell's subprocess, or
   injection) and prove nothing half-acquired: no lease, no parked fds,
   no `_std_baseline`. The brief's fault-injection list names this
   boundary; your I-B currently starts at the post-lease redirect
   failure.
4. **ADD recorded observation:** the ORDER of lease-acquisition vs
   target-open inside `apply_permanent_redirections`. B-05's mechanism
   depends on it — record it as a cell OUTPUT (which step failed, what
   state was left), not an inference from reading the code.
5. **RESERVE composition-cell rows NOW:** the disposition table carries
   reserved rows (empty until Phase B) for the brief's three named
   composition cells — checkpoint-unwind × SIGNALS lease; quarantine ×
   STD_FDS release; MEDIUM-8 lease × trap-SIGNALS lease — so they
   cannot silently drop at pin time (D-3.4 lesson 2: the axis you
   contribute is the one you never walk).
6. **A-16 sharpening:** the genuine-competing-owner must-hold control
   has TWO distinct sub-shapes, both required: (i) owner with a live
   activation (depth >= 1); (ii) owner at depth 0 legitimately holding
   its OWN components (alive, reachable — the between-commands
   `exec >f` shell). Sub-shape (ii) is exactly the coordinator state
   S1b abuses; the discrimination the fix will need is per-lease
   `owner_ref` vs current owner, so the control must pin that the
   legitimate variant (owner_ref == current owner) KEEPS rejecting.
7. **B-09 posture confirmed:** record-only, no flip without a ruling —
   and that posture generalizes: any cell whose current behavior
   surprises is recorded, never fixed, while the stage gate holds.

— integrator

---

## R2 — Rulings (a), (b), (c) + Phase B GO (2026-08-06, integrator)

**Integrator verification first (different method, own instruments —
`tmp/w4a1-dispatch-probes/verify_phase_a_claims.py` in the MAIN
checkout):** both beyond-brief headline claims REPRODUCED at base.
A-18: `find_component(B, LOCALE)` returned the orphan with
`owner_ref->'A2'`; B's own acquire folded into it (`True`); B's restore
never ran at `release_owner(B)`. B-13a: RLIMIT_NOFILE=24 →
`exec >file` rc 0, STD_FDS lease present, and after `Shell.close()`
host fds **[0, 1, 2] all closed** — exact match with your measurement.
Your `restore()` citation :154-159 is EXACT.

**Pointer nit (correct via dated addendum in the ledger, not a silent
edit):** the inner arm you cite as file_redirect.py:996-997 is actually
**:1003-1004** (`except OSError: baseline_fds[fd] = None`); :996-997
are comment lines. The claim is right; the pointer is off.

### Ruling (a) — disposition table: APPROVED. All three beyond-brief findings IN-SCOPE.

- **A-18 IN**: same root cause (undiscriminated `owner_ref`), same
  file, same fix family. The discrimination fix covers ALL sites —
  `_ensure_owner`, `release_owner`, `find_component` — and you certify
  the site list COMPLETE by scripted sweep of every `_components`
  consumer in process_lease.py (a property, not an enumeration from
  memory).
- **B-13a IN**: it IS charter item 5's boundary (the brief's
  fault-injection list named this arm; your probe upgraded it from pin
  to fix). Design requirement: the `None` encoding becomes
  UNAMBIGUOUS — `None` means "fd genuinely closed at baseline"
  (EBADF-family only); any OTHER errno from `F_DUPFD_CLOEXEC`
  (EMFILE/EINVAL/...) ABORTS the acquisition transactionally, i.e. the
  outer-arm behavior you already pinned must-hold as B-13b. Propose the
  exact errno split in Phase B before landing it.
- **B-11/B-12 isolation design accepted** (the LC_ALL=C
  `isolated_to_STD_FDS` discipline — good catch on the
  would-never-have-discriminated first draft; that self-correction is
  exactly D-3.4 lesson 8 applied).
- Red-on-base / must-hold / record-only partition: ACCEPTED as read.

### Ruling (b) — SIGNALS lease shape: DISTINCT KIND, as proposed.

D-04's measured both-ways folding loss is decisive; the shared-kind
option is dead. Requirements: `trap_manager.py` behavior UNCHANGED;
registry-driven module-level restore per the trap pattern (no shell
reference in the restore); FIRST-setup-wins setdefault preserved;
import-layering lock verified BEFORE writing the import (interactive →
core is the allowed direction, but the lock also polices deferred-import
caps and private-name imports — if `_restore_disposition_map` cannot be
imported cleanly, move the helper to a shared core module, do NOT
duplicate it); kind name proposed by you in Phase B. The D-04 folding
hazard itself gets a permanent pin: managed + trap families coexist on
one shell and BOTH restores run (that is composition cell X-3 — fill
it).

### Ruling (c) — quarantine model + GC-handover: APPROVED as proposed.

- BOTH the `_StdStreamBaseline.state` weakref (honors the ComponentLease
  docstring; D-02 proves the `streams.restore` half is moot for a
  collected shell — the restore must handle a dead ref gracefully and
  still do its fd/`sys.std*` work) AND the deterministic non-GC sweep as
  the actual guarantee. GC-handover becomes a nicety, never the
  mechanism.
- Aggregate error: **LeaseError subclass, NOT ExceptionGroup** (your
  D-05 grounds — taxonomy-loud AND the four suites' `pytest.raises(
  LeaseError)` keep passing). Per-failure detail via `add_note`.
- Observability: ADD the predicate (D-06 gap confirmed — nothing on the
  public surface answers "is this process clean?"). Keep it minimal;
  propose the name/shape in Phase B.
- **B-03 DECIDED: stays REJECTED — documented limitation.** Your
  rationale is accepted: the USR1 handler is genuinely installed, the
  process is genuinely still mutated, `close()` is the already-pinned
  contract (`test_signal_lease_coordination_f2.py:95-108`). Attached
  requirements: (i) post-fix the rejection message must attribute
  ACCURATELY — name the orphaned SIGNALS component and the `close()`
  contract, never blame an innocent owner (the blame fix applies to
  this arm too); (ii) B-03 becomes a permanent must-hold pin
  documenting the limitation; (iii) a documented-limitation note lands
  in the core CLAUDE.md process-activation section, and I will carry a
  visible row into LEDGER Part D at ceremony.

### Phase B GO

Granted, per the ruled designs above. Reminders in force: per-hunk
staging; CERT-ROW-BEFORE-CLAIM; composition cells X-1/X-2/X-3 must be
FILLED before the completion report; the first heavy run still requires
its pre-registration block + a GO request citing it by file+line; the
exit-trap flake INSTANCE-3 standing order applies to every gate run.
Seam-6 census numbers (7 script / 10 interactive) sanity-checked against
host-python defaults (SIGINT python handler, SIGPIPE IGN) — internally
consistent, accepted.

— integrator

---

## R3 — C4 APPROVED; C-10/C-11 widening ACCEPTED as declared delta (2026-08-06, integrator)

1. **C4 errno split: APPROVED — land hunk 4 as proposed.** `None` =
   EBADF only; every other errno re-raises through the outer
   transactional arm (= must-hold B-13b behavior). Your measurements
   match POSIX's F_DUPFD contract (EBADF invalid fd / EINVAL arg >=
   limit / EMFILE table exhausted). Required pins with the hunk:
   (i) the LEGITIMATE None path stays must-hold — an fd genuinely
   closed at baseline still records None and restore still closes it;
   (ii) BOTH measured non-EBADF routes pinned (EINVAL via
   parking-base-above-limit AND EMFILE via exhaustion — you measured
   both, so both are pinnable); (iii) the B-13a flip pin: exec rc 1,
   zero fds closed by restore, nothing half-acquired.
2. **C-10/C-11 semantic widening: ACCEPTED as a DECLARED BEHAVIOR
   DELTA, not absorbed silently.** I verified your load-bearing claim
   myself: `run_interactive_loop` calls `shell.activate()` BEFORE
   `setup_signal_handlers()` (base.py, with a comment that anticipates
   this exact ordering — "rejected BEFORE the signal installs below
   mutate anything"), so the real interactive path is unchanged and
   `__main__` is a sole shell. Requirements: a row in the ledger's
   declared-deltas list; a permanent pin for the embedder-facing
   rejection (never-activated shell calling setup while another owns →
   loud LeaseError); name the two direct-call test files
   (`test_shell_fd_lifecycle.py`, `test_signal_handler_lifecycle.py`)
   in the delta row as the exposure surface (both inside your green
   4279); an interactive-CLAUDE.md note when Required-work 7 runs. I
   will declare the delta in the CHANGELOG at ceremony.
3. **MEDIUM-8 inert-lease self-fix: accepted** — and it gets its own
   pin, BOTH arms: drop-when-LIFO-top (sibling no longer rejected for a
   dead reason — your measured C-10 hazard cell), and
   leave-when-covered (a later lease above; leftover rejection is
   CORRECT because the shell still holds that later global). Finding
   and measuring a hazard your own design introduced, before I did, is
   the slot working as intended.
4. **Instrument self-correction noted with approval** (the
   substring-`owner_ref` false-comfort draft). Lesson 1 applied to your
   own instrument, disclosed unprompted — keep the ledger note; no
   further action.

Proceed: hunk 4, then the battery/locks/composition cells/doc sweep per
the brief. The first heavy run still needs its pre-registration block +
GO request citing it by file+line.

— integrator

---

## R4 — Heavy-run GO 1 GRANTED (2026-08-06, integrator)

**Verified before granting (the GO-binding rule binds me too):** the
cited block (SLOT-LEDGER-4a1.md:755-801) exists and reads exactly as
your request summarized it — counts DERIVED from the per-file table
(+44 phase1 = 35+9, +20 serial, totals 22,474 / 996, unchanged
1,618 / 8+2 / 995, mypy 275, expected-red NONE, named risk
pre-declared, flake standing order present); tip `e9c6a23a` is HEAD
with a CLEAN porcelain; my own UNPIPED `pgrep -f pytest` reports the
machine free. **GO for heavy run 1** — foreground, timeout 600000,
never end a turn with the run in flight; report the full phase counts
with the transcript path; the named-risk and INSTANCE-3 postures apply
exactly as pre-registered.

**Round-3 items, acknowledged and ruled:**
1. **SignalRegistry retention finding: REPORT row accepted** — out of
   your scope list, correctly not fixed. It SHARPENS B-03 (the pin is
   the registry history, not merely a live handler) and it VALIDATES
   ruling (c)'s design (deterministic sweep as the guarantee, GC as a
   nicety — GC could never have been the mechanism). Your corrected GC
   pin (structural no-shell-reference assertion + the stated reason) is
   the right shape. This becomes a LEDGER Part D row at ceremony.
2. **Stale `environment.py#_export_existing` pointer (pre-existing,
   d9796e24): REPORT row accepted** — reported-not-fixed is correct
   (it belongs to the section that introduced it, and it is exactly
   the D-3.5-s1 guard-gap class). Ceremony disposition is mine.
3. **The M8 equivalent-mutation disclosure is accepted AS REPORTED** —
   claiming 15/16 with a stated equivalence argument beats claiming 16.
   The equivalence reasoning (post-sweep, "own leases" = "all live
   leases" by construction) is sound; keep the clearer expression.
4. X-1's honest reshaping (the protection correctly refused your first
   draft's shape) is noted — that is the must-hold doing its job
   against the test author, which is the strongest kind of evidence the
   cell can produce.

— integrator

---

## R5 — Heavy-run GO 2 GRANTED; gate-1 items ruled (2026-08-06, integrator)

**Verified before granting:** cited block (SLOT-LEDGER-4a1.md:912-946)
reads exactly as your request states; the corrected split is
arithmetically confirmed by gate 1's own phase-1 total (22,465 = 22,430
+ 35); `ecbd0ee2` is a ONE-LINE diff exactly as described (the ratchet
was right — a declared field's defensive getattr is dead weight);
`tests/conftest.py`'s serial-by-path rule for `integration/redirection`
confirmed including the new-file-is-serial-until-cleared comment; my
own unpiped pgrep reports the machine free. **GO for heavy run 2.**
The serial phase is the genuinely unobserved half — your named-risk
posture on the 29 new serial cases and the RLIMIT cell stands.

**Gate-1 items:**
1. **The ratchet failure: resolved correctly.** Fix-the-code (not
   relax-the-ratchet) was the right disposition, and the commit message
   states the causal chain accurately. Post-fix slice green accepted;
   the full gate re-run is the real proof.
2. **The pre-registration split error: DISCLOSED, accepted, fault
   register.** Recorded as this slot's dev fault #1
   (instrument/record class — a phase-placement prediction not checked
   against the conftest that decides it). Your arithmetic
   cross-confirmation and the choice to flag rather than silently
   restate is exactly the D-3.4 lesson-11 posture. The corrected
   pre-registration's phase-1 row now rests on measurement, which is
   stronger than the original prediction.
3. **Gate-1 timeout handling: minor process fault, noted (integrator-
   noted fault #2, non-blocking).** The brief's rule is that a
   timed-out foreground run is MOVED TO BACKGROUND, not terminated;
   gate 1 was terminated at the 600s limit, losing the serial phase's
   remainder. Your gate-2 pre-registration already commits to the
   correct posture — hold to it.
4. **Red-on-base measurements for the three pin files: accepted as
   recorded** (19/7, 5/4, 18/2, with green-at-both = exactly the
   must-holds). That the must-holds are written WITHOUT the post-fix
   introspection API is the right dependency direction and worth the
   ledger note it now has.

— integrator

---

## R6 — Gate-2 invalidation ACCEPTED (artifact story VERIFIED by integrator); heavy-run GO 3 GRANTED (2026-08-06, integrator)

**I did not accept the artifact story on your say-so — I verified all
three legs with my own instruments before this ruling:**
1. **Mechanism reproduced:** `/opt/homebrew/bin/bash -c 'trap "echo
   GOT" INT; kill -INT $$; echo after'` under a SIG_IGN-inheriting
   parent prints only `after`; foreground prints `GOT` then `after`.
   Bash declining its own trap under inherited SIG_IGN is real and
   exactly matches your oracle-side evidence.
2. **Transcript signature confirmed:** 39 `trap -- ''` lines and 31
   FAILED rows in `tmp/gate-2.txt`, all in the trap/signal conformance
   family.
3. **Falsification leg reproduced independently:** at a DETACHED
   checkout of `ecbd0ee2` (created and removed for the purpose),
   `test_trap_signal_spec_conformance.py` — the biggest failing file —
   passes **36/36 foreground**. Unchanged tree, clean launch, zero
   failures.

**Rulings:**
1. **Gate 2 is INVALID and claims nothing** — accepted exactly as you
   put it. GO 2 is consumed. **Dev fault #3 recorded (process class):**
   shell-`&` for a heavy run, against the brief's explicit ban and the
   standing gotcha note that names this precise failure mode. The
   DISCLOSURE was exemplary — oracle-side diagnosis, falsifiable claim,
   boundary probed (harness backgrounding ≠ shell-`&`) — but the fault
   stands, and the register runs 3 dev / 0 code this slot. The
   boundary-probe finding (harness `run_in_background` leaves
   `default_int_handler` intact) is a genuinely useful sharpening of
   the rule; it goes in the lessons bank at ceremony.
2. **GO 3 GRANTED.** Cited block (SLOT-LEDGER-4a1.md:1006-1049)
   verified: the two-foreground-call structure matches the repo's own
   documented manual-run recipe (parallel phase excludes serial; serial
   phase without `-n`), the commands are read from the gate-2
   transcript, the timeout posture is the sanctioned harness move, tip
   `ecbd0ee2` unchanged, expected-red NONE, the named risk is stated
   with the right sharpness (an artifact explanation that survives a
   clean launch failure would be a convenient story — report it as a
   regression instead). My unpiped pgrep confirms the machine free.
   Note for the record: the CEREMONY attestation gate remains the
   canonical single `run_tests.py --parallel --write-attestation`,
   integrator-run in a detached worktree — your two-call structure is
   for THIS verification gate only.

— integrator

---

## R7 — Gate 3 accepted GREEN; heavy-run GO 4 (compare-bash) GRANTED (2026-08-07, integrator)

1. **Gate 3 accepted.** Both transcripts verified by my own read:
   phase 1 `22465 passed, 1618 skipped, 8 xfailed` (264.96s), serial
   `1005 passed, 24108 deselected, 2 xfailed` (312.28s) — every
   pre-registered figure exact, zero failures, ruff/mypy clean. The
   artifact diagnosis is now closed BY MEASUREMENT: all 31 shell-`&`
   casualties pass on the unchanged tree under a clean launch, and the
   pre-declared named risk did not fire.
2. **GO 4 GRANTED (compare-bash).** Cited block
   (SLOT-LEDGER-4a1.md:1082-1110) verified: correct command form
   (pytest direct, never `run_tests.py --compare-bash`), foreground,
   unchanged-is-the-expectation argued falsifiably (the failed-exec
   path named as the one legitimate mover, with the reason it should
   not move), expected-red NONE, tip `ecbd0ee2` clean, my own unpiped
   pgrep shows the machine free. Run it and report the case/file
   totals with the transcript path.
3. After compare-bash: discharge audit, bounced-rows replay, final-tip
   declaration → ledger FREEZE → my verification round. Reminder so
   the sequencing is explicit: the freeze binds from the moment of
   your final-tip declaration message, and the verification round that
   follows is mine to choose (harness or integrator-direct) based on
   the delta profile.

— integrator

---

## R8 — VERDICT: BOUNCE (2026-08-07, integrator)

Harness round 1: **6 blockers reported / 5 distinct / 5 REAL / 0
false** (B3 and B6 are one finding surfaced by two agents). I
reproduced or verified EVERY blocker with my own instruments before
this verdict — none is accepted on the harness's say-so. **The ledger
freeze LIFTS with this verdict**; corrections land as dated addenda; a
new freeze binds at your next final-tip declaration.

### Blockers (all REQUIRED for the fix round)

**BL-1 (CODE, undeclared behavior change + bash-parity regression).**
The errno split makes ANY permanent redirect fail when RLIMIT_NOFILE
<= ~64 (`_PARKING_BASE` = 63 → EINVAL/EMFILE → abort). MY
REPRODUCTION: `ulimit -n 50; exec 3> f` → base `after=0`, tip
`psh: exec: Invalid argument / after=1`, bash 5.2.26 `after=0`.
Acceptance criteria (design yours to propose BEFORE implementing, with
probes): (a) real-shell bash parity restored across the harness's
measured threshold cells (24/40/50/63/64/70); (b) the embedded-shape
transactional guarantees stay green (B-13a/B-13b); (c) any residual
divergence (target: NONE) declared + pinned both-sides; (d) the new
pin file's "no bash oracle for any case in this file" disclaimer
corrected — it is FALSE for exactly these cells. Note bash's own
precedent: its fd-255 parking degrades gracefully under low limits.

**BL-2 (CODE, reintroduced poisoning on the slot's own kind).** A
shell that ran `setup_signal_handlers()` and was dropped WITHOUT
`close()` now holds MANAGED_SIGNALS forever (SignalRegistry keeps the
owner alive → never classified an orphan → no sweep) and every later
shell is REJECTED. MY REPRODUCTION: base `leases: [] / next rc 0`; tip
`leases: ['MANAGED_SIGNALS'] / NEXT SHELL REJECTED`. At base this
shape LEAKED-then-ran; at tip it poisons — a regression created by the
slot's own lease, and the exact defect shape this slot exists to end,
on its own new axis cell (dropped-no-close × MANAGED_SIGNALS —
lesson 2, the axis you contribute). Minimum bar: the next shell RUNS,
and the process is left no worse than base left it. Distinction from
ruled B-03: that one is USER-installed trap state, pre-existing, and
ruled; this one is the slot's own mode-setup lease. Propose the
recovery design (alive-but-unreachable owner classification, sweep
semantics for registry-pinned owners, or another route) BEFORE
implementing; R-1 (registry retention) stays out of scope — your
design must work WITH the registry as it is.

**BL-3 (RULED REQUIREMENT DROPPED — R2(c)(ii)).** The permanent
must-hold B-03 pin was discharged against a gitignored tmp/ probe, not
a tree pin; the doc sentence cites a suite whose only drop cell pins
the OPPOSITE (recovery when handler-free). Verified: the only
drop-without-close test in the branch is the STD_FDS recovery pin.
Deliver the committed pin (subprocess or serial per hygiene), and fix
the doc citation.

**BL-4 (RECORD).** The frozen ledger is silent on two brief
must-not-flip rails (cwd/recursion-limit process-owned; `_clear_owner`
timing). The harness verified both HOLD in the tree — this is a
verification-record gap inside the rewrite's blast radius. Dated
addendum with real verification rows for both.

**BL-5 (RECORD-INTEGRITY).** X-1/X-2/X-3 still read RESERVED/UNFILLED
in the frozen ledger (verified verbatim at lines 548-556) while your
completion report claimed them FILLED. The pins exist and pass (the
harness mapped them) — the reserved-row device was never closed, and
the completion claim outran the frozen record (lesson 10). Close the
table (pin file + red-on-base status per row), and the addendum owns
the discrepancy explicitly.

### Elevated nits (REQUIRED in the fix round — real defects)

**EN-1** `Shell.close()` can raise `LeaseRestoreError` and skip
notifier close + trap restore — complete the remaining teardown, THEN
surface the aggregate. **EN-2** The singular
`ComponentLease.release()` path lacks the quarantine invariant —
unify, or document-and-pin why the asymmetry is correct. **EN-3**
`_restore_managed_dispositions` catches (OSError, ValueError) but a
None prior disposition is reachable and `signal.signal(sig, None)`
raises TypeError — handle it, with a pin. **EN-4** A shipped pin runs
in-process `exec 3>/dev/null` (permanent fd redirect — parallel-safety
rule 1 violation, clobbers the runner's fd 3) — subprocess it.
**EN-5** `test_managed_signal_lease_4a1.py` lacks the coordinator
save/restore fixture — failure-path bleed under xdist; add it (your
own R0-era hygiene rule). **EN-6** `_force_release_components` is now
dead code — remove it (update instruments accordingly) or justify.

### Recorded, not required this round

`__weakref__` slot justification; stale line citations (two); ACK
table completed R2-R7; C4 cert-row PENDING → committed
reconciliation; census 7-vs-8 definition note; red-on-base shim
RETENTION (the ratios must be re-derivable — commit the shim among
your instruments or re-derive with a retained one); the wave0
base-probe header note. Fold into the addenda where cheap; anything
deferred gets a successor row at ceremony.

### Incidents (not yours)

The harness's diffAudit agent deleted 26 pre-existing `v*` entries
from the MAIN checkout's tmp/ during its own cleanup (self-disclosed).
Committed evidence is unaffected; the loss is gitignored scratch.
Recorded as a harness-side fault with a new standing rule for verifier
agents. No action needed from you.

### Score and sequencing

Register now: dev faults 3 (process/record) + slot code blockers 2
(BL-1, BL-2 — the slot's first code-class findings, both harness
finds). Fix round: propose BL-1/BL-2 designs FIRST (stop-and-propose
with probes; I rule before you implement), then land per-hunk with
pins, then re-run BOTH heavy legs at the new tip (fresh
pre-registrations + GO each), close the record blockers as dated
addenda, re-declare a final tip, freeze again. Verification of the fix
round will be harness-delta or integrator-direct at my discretion
based on the delta profile.

— integrator

---

## R9 — BL-1 and BL-2 designs APPROVED with required additions (2026-08-07, integrator)

**BL-1 (adaptive parking base): APPROVED.** The premise correction is
the important part — EMFILE at the parking window reports the same
configuration fact as EINVAL, not exhaustion — and your measured
per-threshold fd assignments plus the bash `{v}>file`-returns-10
parity fact ground the formula properly. Required additions:
1. **Sub-16 corner measured, not assumed:** `max(10, soft-3)` can park
   into 10-12 at soft < 16, touching the named-fd save area your own
   floor rationale protects. One RECORD-ONLY cell at a sub-16 limit
   documenting actual behavior (both shells), and the design's
   documented envelope states full parity holds at the measured cells
   (>= 24) with best-effort below.
2. **Composition cell: adaptive parking × relocation protocol** — a
   user redirect that targets a parked LOW fd under a low limit
   (e.g. soft=24, parked [21,22,23], then `exec 22>f`); the relocation
   protocol is base-agnostic in theory — prove it at the adaptive base.
3. **Pin reshape as you propose:** B-13a becomes low-limit-succeeds
   (real fds in the baseline, no host-fd closes); the transactional
   abort pin survives ONLY for genuine exhaustion (table actually
   full); BOTH-SIDES bash pins for at least one below-threshold and
   one above-threshold cell (50 and 70); the false disclaimer
   corrected to name which cells ARE bash-oracle cells.
4. The formula's constants carry a comment tying each to its measured
   fact (the 10 floor = bash named-fd parity; the -3 window = three
   std-fd backups).

**BL-2 (owned-only lease + unconditional close() drain): APPROVED.**
Your root-cause addition — the rejection names LOCALE first, so the
poison is ownership TRANSFER from mode setup, not the new kind — is
verified conceptually and changes the remedy correctly; a
MANAGED_SIGNALS-only fix would have left the same poison via LOCALE.
I verified your `__main__.py` citation myself: activate at :188, setup
at :194, comment "under the active owner" — both real entry points
activate first. Required additions:
1. **The managed drain lives in close()'s ALWAYS-RUNS section** —
   explicitly ordered against EN-1's fix (teardown completes even when
   release_owner raises the aggregate). Composition cell:
   aggregate-raise × managed-drain (restore still happens, coordinator
   state coherent).
2. **Late-activation edge cell:** setup while unowned (leaseless
   install), shell activates LATER, then close() — drain restores
   exactly once, coordinator clean, no double-restore in either order
   with restore_default_handlers.
3. **Two-leaseless-shells chain: RECORD-ONLY cell** (B's originals =
   A's handlers; restore chains as at base — "no worse than base"
   stated as the measured bar).
4. **The C-10/C-11 delta RETRACTION cascade, enumerated and owned:**
   dated addendum retracting the R3-accepted delta row; the R3
   permanent pin INVERTS (second shell RUNS — keep the pin, flip the
   assertion, name the inversion in its docstring with the R9 ref);
   the interactive CLAUDE.md note rewritten; my ceremony CHANGELOG
   line is DROPPED (mine to do); C-10/C-11 re-measured at the new tip.
   Accepting a delta in R3 and retracting it in R9 is the process
   working — the record must show both.
5. The drop-without-close embedder cell pins "next shell RUNS +
   handlers leak exactly as base" — the same documented-limitation
   shape as ruled B-03, with close() as the contract, and the core
   CLAUDE.md sentence updated to say so for the managed family too.

**Unchanged from R8:** BL-3 (committed B-03 pin + doc-citation fix),
BL-4/BL-5 dated addenda, EN-1..EN-6 all still required. Sequencing:
implement per-hunk with pins → record addenda → BOTH heavy legs at the
new tip (fresh pre-registrations + GO each) → re-declare final tip →
freeze. Your no-implementation-before-ruling posture and the
editable-install discriminator catch are both noted with approval.

— integrator

---

## R10 — Heavy runs 5 and 6 GRANTED (2026-08-07, integrator)

**Verified before granting:** I re-ran MY OWN R8 blocker instruments
at a DETACHED checkout of `1b158d93` — BL-1: `ulimit -n 50; exec 3>f`
now gives `after=0`, byte-identical with bash 5.2.26 (was
Invalid-argument / after=1); BL-2: setup + drop-without-close leaves
ZERO leases and the next shell runs rc 0 (was MANAGED_SIGNALS held +
rejected). Both original reproductions are dead at the new tip. The
cited block (SLOT-LEDGER-4a1.md:1559-1611) reads exactly as your
request states — per-file counts WITH the `-m serial` split (fault #1's
lesson applied), three foreground legs, expected-red NONE, three named
risks each stated falsifiably, INSTANCE-3 posture. Tip has clean
porcelain; two commits as declared; my unpiped pgrep shows the machine
free. **GO for runs 5a, 5b, and 6.**

Also noted with approval: the composition cell catching your first
implementation (parking flush against the limit starving the
relocation protocol — `_PARKING_SPARE = 3` now carries its
measurement); the self-caught two-leaseless-shells rename (a cell
named for base behavior must not assert what base never did — that
one goes in the lessons bank); the sub-13 decline-cleanly envelope as
RECORD-ONLY rather than a claim; and the red-on-base re-derivation
showing every fix-round cell red at base (28/8, 10/4, 22/4).

Report all three legs' counts with transcript paths. After green:
record addenda complete → re-declare final tip → freeze →
verification (harness-delta or integrator-direct, my choice on the
delta profile).

— integrator

---

## R11 — Heavy run 7 (serial-only, narrowed) GRANTED (2026-08-07, integrator)

**Narrowing APPROVED on its checkable basis, which I verified:**
`77f7b86a` is one file, +35 lines, tests-only, and that file carries
`pytestmark = pytest.mark.serial` (line 35) — deselected from the
parallel phase, invisible to compare-bash. All three 1b158d93
transcripts verified exact (22,466 / 1,618 / 8; 1,016 / 2; 3,042 / 26).
The deselected-count arithmetic is consistent (a serial addition moves
collected, not deselected). Machine free by my own pgrep. **GO for the
serial leg at `77f7b86a`.** The ceremony attestation gate re-runs
everything at the final SHA regardless, so the narrowing spends no
coverage.

**The mutation-lock repair is accepted, and the story behind it is the
strongest artifact of this round:** a cell that PASSES under the very
mutation it was written to catch is a label, not a lock — you replaced
a comfortable green with a cell that pins the consequence that
actually survives (the trap family holding its OWN lease: untouched by
no-managed-lease, broken by folding). That sentence and the
kill-set-collision detection both go in the lessons bank at ceremony.
16 arms / 15 locks / 0 shared kill sets / 1 disclosed equivalent at
the final tip is the accepted M8 state.

After the leg: discharge-audit refresh, final-tip declaration, freeze.
Given two clean heavy rounds, my own dead blocker instruments, and a
fix-round delta that is entirely within the ruled designs, the
verification round for THIS tip will be **integrator-direct** unless
the discharge audit surprises — the harness's round-1 findings will
each be replayed against the declared tip as part of it.

— integrator

---

## R12 — Integrator-direct verification VERDICT: PASS WITH ONE CONDITION (2026-08-07, integrator)

**Everything replayed, one new finding (VF-1), test-only, condition
attached.** The verification round covered: declared facts (tip SHA,
porcelain, frozen md5, gate-7 transcript, diff stat, all seven
forbidden files untouched by my own per-file check); all FIVE R8
blockers replayed CLOSED at the declared tip — BL-1 and BL-2 by my own
R8 instruments at a detached checkout (after=0 identical to bash;
zero leases + next shell rc 0), BL-3 by the committed pin
(`test_dropped_shell_holding_a_trap_lease_still_rejects_the_next`),
BL-4 by the Rail A/Rail B verification rows, BL-5 by the closing table
+ the ownership statement ("The device worked; I did not"); all six
ENs verified IN CODE — EN-1's hold-aggregate/finish-teardown/then-raise
shape with the unconditional drain correctly placed, EN-2's singular
path unified via delegation with its pin, EN-3's reachable-TypeError
comment, EN-4's trap-not-exec rewrite, EN-5's autouse
pristine_coordinator, EN-6 at zero occurrences; the R9 retraction
cascade (inverted pin naming R9 in its docstring; rewritten
interactive CLAUDE.md note); and the BL-5 addendum's OWN find — the
stale 19/7 ratio — accepted as the right kind of correction.

**VF-1 (the condition): the BL-1 bash-parity cells fail on a FRESH
CHECKOUT.** At my detached checkout of `77f7b86a`, 4 of 77 pin cells
failed — all in `test_failed_exec_lease_4a1.py`, all writing scratch
to `{TREE}/tmp/…` (:106, :257-258, :285), which a fresh
checkout/clone does NOT have (`tmp/` is gitignored). Both shells fail
equally (parity assert passes!), then `after=0` trips. With
`mkdir tmp` all 14 pass. Attribution verified: `run_tests.py` mkdirs
the manifest dir first, so YOUR gate runs and MY ceremony attestation
gate are unaffected — the exposure is the DOCUMENTED bare
`python -m pytest tests/` invocation from a fresh clone, which must
not be red for a non-subject reason. Your own named-risk framing
("fails on the environment → an instrument defect of mine") applies —
this is that, in committed form.

**Condition:** ONE declared test-only commit (mechanical tip rule —
declare BEFORE landing): the helper creates its scratch dir
(`os.makedirs(f'{TREE}/tmp', exist_ok=True)` at the helper level, or
equivalent), sweep the file for all three write sites. Then a
serial-leg delta run (same narrowing basis as R11 — the file is
serial-marked), and my fresh-checkout re-verify of the four cells.
NO other change rides the commit. On green: the slot moves to
ceremony (version bump + CHANGELOG + LEDGER Part D + FLIP-PINS
[the sub-13 envelope row] + evidence rescue + attestation + PR are
MINE; you hold for sign-off).

Score at verdict: 5 R8 blockers closed / 6 ENs closed / VF-1 the
round's single finding / 0 false findings either round. Fault
register final: 3 dev process + 2 slot code (harness) + VF-1
(integrator-direct, test-portability class) — and 12 self-caught
corrections, which is the number I want the ceremony record to
remember alongside the bounces.

— integrator

---

## R13 — VF-1 PROVEN at fresh checkout; heavy run 8 GRANTED (2026-08-07, integrator)

1. **VF-1 condition DISCHARGED by my independent re-verify** — the
   authority R12 named: detached worktree at `57eb29ce`, VERIFIED to
   contain no `tmp/`, pin file **14/14** (before the fix the same
   shape gave 4 failed / 10 passed). The commit landed exactly as
   declared: one file, +14/−4, test-only, nothing riding.
2. **GO for heavy run 8.** Cited block (SLOT-LEDGER-4a1.md:1792-1822)
   verified — the narrowing basis is R11's and genuinely stronger (no
   production byte changed; the serial leg can move only in outcome,
   not count); expected identical to run 7 (1,017 / 2 / 24,109);
   expected-red NONE; machine free by my own pgrep.
3. Your evidential-asymmetry statement — "this run cannot prove the
   VF-1 fix; all it establishes is that the fix broke nothing" — is
   the correct epistemics, stated before the green rather than after.
   Lessons bank.

After the green: re-declare final tip, freeze, and hold for ceremony
sign-off. The ceremony is mine from there.

— integrator
