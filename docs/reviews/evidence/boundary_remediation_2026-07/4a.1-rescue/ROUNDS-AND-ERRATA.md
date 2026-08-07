# Slot 4A.1 — rounds, faults, and errata (integrator-authored ceremony record)

Slot: activation/component transaction (HIGH-8 A5-amplified + MEDIUM-8 +
LOW STD_FDS retention). Base `a64eb6e8` (v0.767.0) → final tip `57eb29ce`
(ten commits, per-hunk). Shipped as **v0.768.0**. Dev: dev-4a-1;
integrator: main session. Dead-drop rulings R0–R13 (this directory's
`integrator-inbox.md` is the complete authoritative copy).

## What shipped

- **The activation/component transaction completed** (`psh/core/
  process_lease.py`): component-depth checkpoint at BOTH grant windows,
  newly acquired components unwound LIFO BEFORE owner-metadata rollback;
  per-lease `owner_ref` discrimination at every `_components` consumer
  (`_ensure_owner`, `release_owner`, `find_component` — the third found
  in Phase A as A-18); orphan sweep; restore failures COLLECTED,
  quarantined leases retained and observable, one aggregate
  `LeaseRestoreError` (LeaseError-derived, strict-errors-LOUD; never an
  ExceptionGroup); public surface grew exactly `is_clean`,
  `quarantine_report`, `clear_quarantine`. The singular
  `ComponentLease.release()` path delegates to the same machinery (EN-2).
- **MEDIUM-8 closed**: managed mode-setup signal dispositions restore
  exactly (7 script / 10 interactive leaked at base → all RESTORED).
  Final design per R9: a distinct `ComponentKind.MANAGED_SIGNALS` lease
  acquired ONLY when the shell already owns the process (mode setup
  never transfers ownership — the BL-2 lesson), plus an UNCONDITIONAL
  drain in `Shell.close()` (the leaseless-embedder guarantee), ordered
  so a raising release still completes the whole teardown (EN-1).
- **LOW closed**: a failing `exec` releases the STD_FDS state it itself
  acquired (newly-acquired-only discrimination); the baseline-dup arm's
  `None` encoding is EBADF-only; a merely-low RLIMIT_NOFILE parks
  ADAPTIVELY (`min(_PARKING_BASE, max(_PARKING_FLOOR, soft −
  _PARKING_SLOTS − _PARKING_SPARE))` = `soft−6`; see the dated addendum —
  the ceremony draft misquoted the pre-spare proposal) instead of failing the user's exec — bash parity
  restored at every measured threshold (24/40/50/63/64/70/256); genuine
  exhaustion still aborts transactionally. The B-13a family (a failed
  dup silently recorded as "closed at baseline", then `close()` closing
  the HOST's fds 0/1/2) is dead, pinned.
- **GC-handover fixed where fixable and demoted where not**:
  `_StdStreamBaseline` holds state weakly (D-01/D-02 measured: PINS
  True→False, USES 2→0); the deterministic sweep — not GC — is the
  guarantee (the SignalRegistry pins any handler-installing shell
  forever, R-1).
- **Batteries**: `tests/unit/core/test_activation_transaction_4a1.py`
  (36), `tests/integration/redirection/test_failed_exec_lease_4a1.py`
  (14, incl. the slot's only bash-oracle cells), `tests/unit/
  interactive/test_managed_signal_lease_4a1.py` (27, serial). 77 pins;
  red-on-base split, re-derived at the declared tip: 57 red / 20 green
  (see the dated addendum for the three green-at-base reasons); M8 mutation locks 16
  arms / 15 locked / 0 shared kill sets / 1 disclosed equivalent;
  composition cells X-1/X-2/X-3 filled (X-1 caught the dev's first BL-1
  implementation before it shipped).

## Round table

| round | verdict | findings |
|---|---|---|
| Phase A (R1) | plan approved | 61 cells, 0 broken; 3 beyond-brief finds (A-18, B-13a, B-11/12 pair) — all 3 ruled IN, 2 verified by integrator reproduction before ruling |
| Phase B (R2–R7) | rulings + 4 heavy-run GOs | gate-1 ratchet catch (fixed-code); gate-2 INVALIDATED (shell-`&` launch, dev fault #3 — artifact story verified 3-leg by integrator); gates 3+4 green exact |
| Harness round 1 (R8) | **BOUNCE** | 6 reported / 5 distinct / **5 real / 0 false**; CODE: BL-1 (bash-parity regression under low ulimit), BL-2 (poisoning reintroduced on the slot's own kind); RECORD: BL-3 (ruled pin discharged against a tmp probe), BL-4 (two rails absent from ledger), BL-5 (X table unclosed vs "FILLED" claim); 6 nits elevated to required |
| Fix round (R9–R11) | designs ruled first | adaptive parking + owned-only lease/unconditional drain; R3's declared delta RETRACTED (the widening caused BL-2); mutation-lock kill-set collision found and repaired ("a cell that passes under the very mutation it was written to catch is a label, not a lock") |
| Integrator-direct (R12) | **PASS with one condition** | all 5 blockers + 6 ENs replayed closed; **VF-1**: the bash-oracle cells failed at a FRESH checkout (`{TREE}/tmp` assumed; both shells fail equally so the parity assert PASSES and the success assert trips) — 4/77 cells, test-portability class |
| Condition (R13) | discharged | one declared test-only commit; proof = integrator's fresh-checkout re-verify (14/14 with no `tmp/`); serial delta green identical |

## Final fault register

**3 dev process/record faults** (pre-registration phase-split not checked
against the conftest that decides it; gate-1 timeout terminated instead
of backgrounded; gate-2 launched with shell-`&` against the ban — the
standing SIGINT=SIG_IGN gotcha, oracle-side corruption, self-diagnosed
falsifiably). **2 slot code blockers** (BL-1, BL-2 — both consequences
of the slot's own fixes, both found ONLY by the adversarial harness).
**1 test-portability finding** (VF-1 — found ONLY by the integrator's
fresh-checkout replay). **12 self-caught dev corrections** (the ones
that would otherwise have produced false greens: the B-11 isolation, the
substring-`owner_ref` census, the GC pin blaming the wrong pinner, the
stale 19/7 ratio, the base-behavior cell asserting what base never did,
the label-not-lock mutation cell, among others). **0 false findings
across both verification rounds.**

## Lessons bank (D-4A.1-lessons; the slot's yield)

1. **The three review layers caught DISJOINT defect classes** (dev's
   closing observation, integrator-endorsed): the dev's 64 probe cells +
   16 mutation arms + 77 pins found every failure INSIDE the design
   frame; the adversarial harness found the two fixes that were correct
   in their own terms but regressed behavior OUTSIDE the frame (bash
   parity under low ulimit; poisoning on the just-invented kind); the
   fresh-checkout replay found the one thing both sides' instruments
   were structurally blind to, because every instrument ran in a tree
   where the dev had already `mkdir`'d the dependency by hand. Each
   layer's blind spot was the next layer's finding.
2. **A mutation lock that passes under the very mutation it was written
   to catch is a label, not a lock** — and only a kill-set-collision
   check makes that visible; two arms sharing an identical kill set
   means a ruled design decision is no longer independently pinned.
3. **A parity cell that reports parity on a broken environment, then
   fails for an unrelated reason, is worse than one that errors** — the
   failure reads as a product defect when it is a missing directory.
   Scratch dependencies must be created by the test, not inherited from
   the tree's history.
4. **An axis you contribute is the one you never walk, part two**: BL-2
   sat at dropped-no-close × MANAGED_SIGNALS — a cell of the very
   lifecycle-×-kind axis this slot registered.
5. **Errno families are claims about causes, not just codes**: EMFILE at
   a too-high parking base reports the same configuration fact as
   EINVAL, not exhaustion; aborting on both was a wrong theory of the
   error wearing a correct-looking guard.
6. **Harness backgrounding ≠ shell-`&`** (measured): harness
   `run_in_background` leaves `default_int_handler` intact; `nohup … &`
   inherits SIG_IGN and corrupts the bash ORACLE side of conformance
   runs — 31 spurious fails wearing psh's name.
7. **State the limits of a green before it arrives**: the dev's
   pre-registration for the final delta run declared "this run cannot
   prove the VF-1 fix" and named the fresh-checkout replay as the
   authority — the evidential asymmetry stated before the green, not
   explained after.
8. **Retracting an accepted delta is the process working**: R3 accepted
   the setup-takes-ownership widening; R9 retracted it when BL-2 showed
   the widening WAS the defect; the record shows both, and the pin
   inverted with its docstring naming the inversion.

## Successor rows (registered in LEDGER Part D)

- **D-4A.1-s1**: `SignalRegistry` retains every registration forever
  (`psh/utils/signal_utils.py` `_history`) — any shell that ever
  installed handlers stays process-reachable regardless of leases;
  sharpens B-03; out of 4A.1 scope by ruling.
- **D-4A.1-s2**: B-03 documented limitation (drop-without-close with a
  live USER trap stays rejected; `close()` is the contract) — permanent
  pin `test_dropped_shell_holding_a_trap_lease_still_rejects_the_next`.
- **D-4A.1-s3**: managed-family drop-without-close leaks handlers
  exactly as base did (next shell RUNS; "no worse than base" measured
  bar) — recoverable only if s1 is ever fixed.
- **D-4A.1-s4**: sub-13 RLIMIT envelope — bash succeeds at soft ≤ 12
  where psh declines cleanly (nothing half-acquired); RECORD-ONLY pin,
  FLIP-PINS row.
- **D-4A.1-s5**: `environment.py#_export_existing` stale pointer
  (pre-existing, d9796e24) — FIXED at this ceremony; the R7-rule
  successor (D-3.5-s1) remains the structural guard to build.
- **D-4A.1-s6**: dead-owner-arm restore failures during `_ensure_owner`
  sweep quarantine correctly but the new-owner grant then proceeds —
  interaction documented, deeper policy (refuse vs proceed) left open.

## Regeneration notes

Instruments live under `instruments/dev/` (the dev's Phase A/B/fix
matrices, the retained red-on-base shim `red_on_base.py`, the mutation
harness with its saved-copy restore protocol, the doc-pointer verifier)
and `instruments/integrator-dispatch/` (the dispatch-time A5 poisoning
probe and the Phase-A claim verifications). Every `out-*.txt` transcript
names its tree; red-on-base ratios are re-derivable via the shim, which
is applied to a BASE COPY only. The harness round was
`remediation-branch-verify.js` (main checkout
`tmp/remediation-ledgers/`), run `wf_b9991176-826`; its full report is
summarized in `slot-ledger.md`'s R8 section and the verdict is
`integrator-inbox.md` R8. Heavy-run transcripts (`gate-*.txt`) remain in
the dev worktree's `tmp/` per the transcript-disposition convention
(figures quadruply durable: ledger, inbox, attestation, PR body).

## Incident (harness-side, not the dev's)

The round-1 diffAudit agent deleted 26 pre-existing `v*` scratch entries
from the MAIN checkout's `tmp/` during its own cleanup (self-disclosed;
committed evidence unaffected; `tmp/v13b` confirmed lost). Standing rule
adopted: **verifier agents never glob-delete outside their own mktemp
scratch.**

## Dated addendum (2026-08-07, post-sign-off — D-4A.1-a1)

dev-4a-1's sign-off verification found three record inaccuracies in this
ceremony document and the LEDGER, each measured and integrator-verified
before this addendum landed:

1. **The adaptive-parking formula was misquoted** as the original
   `soft − 3` proposal; the shipped code is
   `min(_PARKING_BASE, max(_PARKING_FLOOR, soft − _PARKING_SLOTS −
   _PARKING_SPARE))` = `soft − 6` (verified at 9e2c3c0c,
   file_redirect.py:119-120). The misquoted version is exactly the one
   the relocation composition cell proved insufficient — the record was
   citing the defect the cell caught.
2. **D-4A.1-s6's premise was wrong**: a new owner's grant does NOT
   proceed over quarantined state — it is REFUSED on every attempt
   (LeaseRestoreError, then the quarantine LeaseError), reproduced by
   both sides. The successor row is reframed to the genuinely open
   question (is refuse-forever absent `clear_quarantine` the right
   embedder contract?).
3. **The red-on-base shape claim was overstated**: measured split at
   the shipped files is 57 red / 20 green (activation 28/8,
   failed-exec 7/7, managed-signal 22/5), and green-at-base has three
   distinct reasons — must-holds by design; documented-limitation pins;
   and regression pins against MID-SLOT defects, where base was green
   by accident (the three bash-parity cells: base "passed" parity via
   the corrupt-baseline silent success).

Banked from this addendum: **red-on-base counts are re-derived at the
declared tip, never carried forward** (this slot produced two
independent stale-ratio instances), and "all red except X" is a shape
claim that must be stated as a measured split.
