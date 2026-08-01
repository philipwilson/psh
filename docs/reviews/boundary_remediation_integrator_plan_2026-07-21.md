# Boundary Remediation Campaign — Integrator's Operating Plan

- **Date:** 2026-07-21
- **Status:** PLANNED, NOT LAUNCHED. The predecessor campaign is paused per user
  directive; nothing in this plan executes without an explicit user go.
- **Author:** campaign integrator (the session that ran the Boundary Integrity
  Campaign v0.725.0–v0.750.0 and verified reappraisal #22).
- **Launch base:** `origin/main` @ `0215279c` (v0.750.0) — NOT the sequence
  doc's v0.749.0 planning baseline.
- **Governing documents, in authority order for execution:**
  1. This plan (operating authority; where it amends the sequence doc, this
     plan wins).
  2. [`boundary_remediation_campaign_sequence_2026-07-21.md`](boundary_remediation_campaign_sequence_2026-07-21.md)
     — the wave structure, standing rules 1–10, exit criteria, and finding
     ownership map are ADOPTED by reference except as amended in §2.
  3. [`ground_up_reappraisal_22_correctness_textbook_2026-07-20.md`](ground_up_reappraisal_22_correctness_textbook_2026-07-20.md)
     — the findings source. Every claim in it that this integrator tested
     (~30, spanning every HIGH, MEDIUMs 1–7/9–16, and LOW residue) reproduced
     at `0215279c`: **all confirmed, zero refuted**. Findings are DISJOINT
     from the v0.750.0 CV fixes; none is overtaken.
  4. The predecessor's close report
     [`boundary_campaign_close_2026-07.md`](boundary_campaign_close_2026-07.md)
     — its 35-row carry register is a live input to Wave 0 (§4.2).

Verification evidence for the base results already exists: probe battery and
fault-injection scripts in `tmp/r22-review-probes/` (19 files, incl.
`r22-probes.sh`, `inject_claim_a*.py`, `inject_claim_b.py`, `claim_[abc]*.py`),
produced 2026-07-21 against a clean detached worktree at `0215279c` with the
PATH bash 5.2.26 oracle. Wave 0 imports these as its base-result evidence
instead of re-deriving them.

---

## 1. What this campaign is

Close every reappraisal #22 HIGH and MEDIUM finding (or explicitly de-scope it
at Wave 0, before implementation), wave by wave, with the discipline the
predecessor campaign proved: one slot at a time on a merge train, each slot
implemented by a dev agent in an isolated worktree, adversarially verified by
agents who did not implement it, gated locally, attested, released, and
recorded in a ledger that a clean checkout can reproduce.

The campaign thesis is unchanged from #20/#22: the live defects are
authority-timing, traversal-totality, and lifetime-ownership failures at
subsystem boundaries — not local algorithm bugs. The remedy is the triad,
per boundary: lossless typed representation + sole authority at the correct
time + executable anti-bypass guard, with every consumer migrated and the
superseded path deleted in the same slot.

## 2. Binding amendments to the sequence doc

These were established by the integrator's review of 2026-07-21 and are
rulings, not suggestions.

**A1 — Base.** The implementation base is `0215279c` (v0.750.0) or newer
main. All v0.749.0 line references in #22 are historical coordinates
(sequence-doc rule 1 already requires re-location; several already drifted).

**A2 — One registry.** Wave 0 merges the sequence doc's §13 finding map with
the predecessor close report's 35-row carry register into ONE live ledger.
Every carry row gets a disposition in this campaign (closed-here / de-scoped /
explicitly re-carried-with-reason). Known overlaps: carry #4 = HIGH-6
(operand-`$@` flatten), carry #22 = HIGH-9 (substitution-origin rc-127 +
frame-abort family), carry #3 = the empty-arith-subscript row (see A3),
carry #12/#16 = J1/H15 residuals feeding Waves 4/5.

**A3 — Flip-pin inventory.** The repository contains divergence-PIN tests that
will go RED when their fix lands. Wave 0 inventories them; each owning slot
flips its pins to equality pins IN THE SAME SLOT and closes the ledger row.
Known members (grow the list at Wave 0 by grepping `test_divergence_` and
`KNOWN_DIVERGENCES`):
- `tests/conformance/bash/test_subscript_keying_conformance.py::test_divergence_operand_at_flattens`
  (4 params) → Wave 3 slot 3.3.
- `tests/unit/expansion/test_pattern_engine_differential.py` `KNOWN_DIVERGENCES`
  (`q4_sub1/2/3`, `neg7_sub3`) + `test_known_divergences_are_still_divergent`
  → Wave 3 slots 3.1/3.2.
- `tests/conformance/bash/test_nested_substitution_timing_conformance.py::test_divergence_c_mode_exit_code_is_127_in_bash`
  (6 params) → Wave 2 slot 2.4. **DISCHARGED v0.760.0** — flipped to the
  equality pin `test_c_mode_exit_code_is_127_like_bash` (same file, same 6
  params; complete-but-invalid and other-kinds twins added beside it).
- `test_subscript_keying_conformance.py::test_divergence_procsub_*` (timing
  family) and `::test_divergence_empty_arith_subscript_fatality` → Wave 2
  slot 2.3 (fatality row only if 2.3's scope touches it; otherwise re-carry
  explicitly).

**A4 — Correct the record.** The committed close report's carry row #3 states
the empty-arith-subscript divergence BACKWARDS (it says psh warns-and-
continues; the pinned test and live probe show bash warns-and-continues rc 0
while psh aborts the line). Wave 0 ships the one-line correction and adds the
missing procsub-key-identity carry row (HIGH-4a) so the predecessor record is
accurate before this campaign builds on it.

**A5 — Verification addenda (facts #22 does not contain).**
- HIGH-8 is worse than written: the leaked LOCALE/`STD_FDS` component lease
  POISONS later unrelated shells in-process — `ShellState.activate()` raises a
  spurious "competing process owner" `LeaseError`, and `release_owner()`
  early-returns without sweeping the orphan. Wave 4A's fault battery MUST
  include the multi-shell poisoning scenario (shell A fails activation →
  unrelated shell C activates cleanly) and the transfer-rollback variant.
- NEW bug (found during verification, not in #22): `read -t X -N n` ignores
  `-t` entirely — `_read_exact` (`psh/builtins/read_builtin.py`, v0.750.0
  ~:688-731) calls `read_limited` with no deadline and hangs; lowercase `-n`
  honors `-t`. Owned by Wave 4B slot 4B.2 as a rider.
- MEDIUM-3 (`echo \<<EOF` heredoc misdetection) is LATENT in `-c`/script mode
  (the flush path re-lexes correctly) and live ONLY interactively (psh drops
  to PS2 and swallows the next line as phantom body). Its red-on-base pin must
  therefore be a PTY pin; a `-c` pin is green-on-base and violates sequence
  rule 3. [SCOPING CORRECTED at 2.5 close, evidence B70: the latency claim
  holds for the RD parser ONLY — under the COMBINATOR the misdetection also
  moved non-interactive diagnostic line numbers on all three channels, so a
  combinator `-c` diag pin would have been red-on-base. The PTY-pin mandate
  itself was right; its stated reason was rd-scoped.]

**A6 — compare-bash invocation.** The §12 ceremony command
`python run_tests.py --compare-bash` is the invocation that block-buffer
stalled in the varstore campaign and has been on this project's never-run list
since. Use `python -m pytest tests/behavioral --compare-bash -n auto -q`
everywhere, OR make re-verifying the runner path an explicit Wave 1
deliverable before any ceremony depends on it. Until then the pytest form is
the only sanctioned invocation.

**A7 — The 5A ruling happens at Wave 0.** Under the sequence doc's success
criteria 1+6, anything deferred AFTER implementation begins leaves the
campaign permanently unclosable. Package 5A (resumable lexer/parser, = #20
H15) was already ruled campaign-scale once (I3, Option B). Wave 0 makes an
eyes-open in/out ruling on 5A — recommended default: OUT of this campaign's
closure scope, recorded as its own successor campaign, so that MEDIUM-15's
remaining hub-decomposition work (5C) stays closable here. If ruled IN, the
campaign accepts the schedule consequence explicitly.

**A8 — HIGH-3 ordering matrix first.** Before any implementation of slot 3.4,
a bash-vs-psh ordering matrix is probed and pinned: prefix-assignment value
expansion × (arithmetic side effects, `${var:=}` side effects, command-sub
side effects) × (function/builtin/special-builtin/external targets) ×
(POSIX-mode flips, `command_not_found`, redirection errors, temp-env
visibility, assignment persistence after special-builtin). This is the CV
lesson applied: in deep-semantics territory, the probe battery precedes the
design, not the fix.

**A9 — Wave 3 internal sequencing.** Pattern-engine NEGATION/nullable
CORRECTNESS (3.1) lands and is verified before the linear all-start REWRITE +
cache freeze (3.2). Never one combined semantics+algorithm diff in the engine
shared by `[[`, `case`, pathname glob, `${%%}`, and `${//}`.

**A10 — Wave 1 migration mechanics.** The ~30-module oracle migration goes
census-first (one commit that enumerates and freezes the offender list), then
mechanical batches with per-batch green, then the AST guard + allowlist
deletion. Expect a long tail: the runner imposes temp-cwd/timeout/cap policy
on thousands of cases that never had it.

**A11 — Predecessor exit legs fold into Wave 0.** The predecessor campaign's
pending criterion-7 exit legs (3 seeded gates, compare-bash, conformance,
benchmarks at `0215279c`) are the same work as Wave 0's baseline
establishment at the same SHA. Run once, record twice: as this campaign's
Wave 0 baseline AND as the predecessor's milestone-record legs. The
predecessor is then recorded as an implementation milestone per #22's
reclassification, closure transferring to this campaign's Ceremony C.

**A12 — Oracle phrasing.** Differential contract is "PATH bash 5.2, exact
version recorded per host" (macOS local = 5.2.26 homebrew; the Linux nightly's
build differs). Never `/bin/bash`.

## 3. Roles and rules of engagement

Carried unchanged from the predecessor campaign; they are what produced
70/70 real blockers and 0 false findings.

**Integrator (this session):** designs slots, writes briefs, rules on scope
deviations, runs verification, owns the gate/ceremony/release, owns
`psh/version.py`, `CHANGELOG.md`, `README.md`, `ARCHITECTURE.md` version
line, and the reviews index. Only the integrator pushes, PRs, merges.

**Dev agents (one per slot):** implement in an isolated worktree on a
`fix/<topic>` branch. Devs NEVER touch the version/changelog/readme files
above, never push/PR/merge/tag, never run the ceremony. Commit early and
often in the worktree (R2/R3 lost-hunk precedent: idling with uncommitted
work is a bounce). Honest-deviation escape hatch: a dev who believes the
brief is wrong STOPS and reports; it never silently reinterprets.

**Verifier agents (per slot, never the implementer):** adversarial, fresh
context, own probe construction. Standard: sequence-doc rule 10 PLUS the
predecessor's stronger practice — see §5.

**Standing constraints (non-negotiable):**
- NEVER touch the parallel session's uncommitted files in the main checkout:
  `" 1 "`, `b]y`, `bugs.txt`, `d/`, `decomment.py`, `docs/reviews/README.md`
  (modified), and their uncommitted `docs/reviews/*.md` review docs. The
  reviews-index entry for this plan waits until that session commits or the
  user directs the reconcile (one-row conflict, known since v0.749.0).
- Gates run in a fresh DETACHED worktree, foregrounded or
  background-with-watcher (`until ! pgrep` loop), never shell-`&` (SIGINT
  inheritance gotcha). Full output to a file; grep the file.
- `ruff check psh tests tools` and `mypy` (no args) green before any merge.
- Project `tmp/` for scratch, never system `/tmp`.
- Golden-file merges: `git merge-file --union` (BLOB-UNION) only.
- Keep ≥10 GB disk free before launching a gate (#22's second gate died to
  host ENOSPC; that failure mode is now known).
- Probe harnesses embed a discriminator (`psh.version.__version__` +
  `psh.__file__` under the tree-under-test) — the editable-install-imports-
  MAIN trap.
- Interactive/signal facts get a realistic-terminal leg (tmux or PTY probe) —
  python-pty-only constructions produced a false ruling once (J1).

## 4. Wave 0 — concrete task list

Wave 0 is documentation/evidence bootstrap; no production code. Tasks:

1. **Commit the governing set**: the sequence doc, reappraisal #22, this plan
   (plus reappraisals #20-continuation/#21 if the user wants the full lineage
   committed — their files, their call), under their existing `docs/reviews/`
   paths. Coordinate the `docs/reviews/README.md` index rows with the
   parallel session (see §3 constraint).
2. **Create the evidence tree**: `docs/reviews/evidence/boundary_remediation_2026-07/`
   with `LEDGER.md` (the unified registry, A2), `FLIP-PINS.md` (A3),
   `wave-manifest.json` (machine-readable status per sequence-doc §5), and
   copy the base-result probes from `tmp/r22-review-probes/` into
   `evidence/.../wave0-base-probes/` (durable home; A11's legs join them).
3. **Import base results**: record the 2026-07-21 verification (every HIGH +
   MEDIUM discriminator confirmed at `0215279c`, agent transcripts summarized,
   probe filenames) as the Wave 0 "base result" column. No re-derivation.
4. **Run the baseline legs (= predecessor exit legs, A11)** at the launch
   base in a fresh detached worktree, sequentially: standard gate ×3 with
   declared `--shuffle-seed`s (identical phase censuses required),
   `python -m pytest tests/conformance -q`,
   `python -m pytest tests/behavioral --compare-bash -n auto -q`,
   `python run_tests.py --benchmarks`, `ruff`, `mypy`, complexity counters
   (54 fns ≥100 lines is the recorded v0.750.0 figure). Record numbers in the
   evidence tree; these are the regression baseline every wave compares to.
5. **Ship A4** (close-report carry-row correction + missing procsub-identity
   row) as a docs commit.
6. **Rule on 5A** (A7) and on the InputCursor full-contract gaps (4B.4):
   in-scope or explicitly out, in writing, in `LEDGER.md`.
7. **Rebuild the verification harness** for this campaign: adapt
   `tmp/boundary-ledgers/boundary-branch-verify.js` → campaign-local copy
   with its COMMON preamble pointing at THIS plan + the sequence doc
   (predecessor lesson: a stale preamble mis-briefs every verifier).
8. **Predecessor close-out records**: milestone reclassification note +
   final scorecard line (A11), campaign memory updates.

Wave 0 exits when: every ledger row has owner/wave/base-result/intended
closure test and no TBD; baselines recorded; rulings written; harness ready.

## 5. Per-slot verification standard

Sequence-doc rule 10 is the floor. The campaign standard, from what actually
caught things last time:

1. **Adversarial multi-agent verification per slot** (diff-audit /
   resurrection / ledger-check / re-probe roles), fresh contexts, attacking
   OUTSIDE the dev's declared audit scope.
2. **Row novelty**: verifiers must construct probe rows the dev's suite does
   not contain. Green gates plus dozens of pins missed regressions three
   rounds running in the CV slot; fresh rows were the only net that caught
   them. Every regression a verifier finds gets pinned ITSELF.
3. **Re-verify to zero**: a bounced slot re-verifies with FRESH rounds until
   a round returns 0 blockers (CV precedent: 5→10→2→0).
4. **Replay every red claim**: any "this pin was red on base" claim is
   replayed against the base commit before it enters a report (the CV round-2
   lesson: five red-split overclaims caught by replay).
5. **Probe-construction independence** for interactive/signal/PTY facts
   (§3 last bullet).
6. **Mutation checks on guards**: every new static/AST guard is run against a
   synthetic offender IN the slot that ships it, and the offender test stays.
7. Differential rows re-run AT THE FINAL SHA of the slot branch, SHAs logged
   in the transcript.

## 6. Wave and slot map

Waves, dependencies, and owned findings are the sequence doc's §4–§11 with
the A-series amendments. Slot decomposition (each slot = one dev brief, one
verification, normally one release on the merge train; the integrator may
combine small adjacent slots at dispatch time):

**Wave 1 — evidence trust** (target 2 releases)
- 1.1 Typed harness outcomes: `OutputLimitExceeded` (non-`Completed`),
  truncation/termination rejected before comparison; flip the unit pin that
  REQUIRES cap-kill=`Completed`; `yes` discriminator → TEST_ERROR.
- 1.2 Oracle migration (A10): census freeze → batch migration of the ~30
  direct-subprocess differential modules → AST anti-spawn guard with
  synthetic offender → delete the resolution-only blessing.
- 1.3 Test hygiene: MEDIUM-13 deterministic wait via job API; skip-on-failure
  → hard failures (`test_modular_lexer_integration.py`,
  `test_arithmetic_integration.py`, + Wave 0 census of others).

**Wave 2 — syntax identity and analysis totality** (target 4–5 releases)
- 2.1 Traversal totality: framework-owned total child enumeration, generated
  sentinel-child tests over every production visitor; the four #22 security
  probes report findings (HIGH-2).
- 2.2 Parser input contract: one `parse(tokens, inputs)` for RD + combinator,
  context carried through nested/depth-budget paths; parser lifecycle ruling
  (single-use enforced or reusable grammar) (HIGH-5, MEDIUM-11).
- 2.3 Subscript syntax identity: `SubscriptSpec` preserves procsub spelling
  until target-kind authority; read-time rejection parity; raw re-lex +
  broad-catch fallback deleted; quote-aware extent scanner + absolute
  `SourceSpan` on nested substitutions (HIGH-4, MEDIUM-4, MEDIUM-12a).
- 2.4 Substitution-origin frame outcome: `SubstitutionSyntaxError` consumed;
  `-c`/`eval`/`source` abort at the right level with 127; flips the 6-way
  divergence pin + closes carry #22 (HIGH-9).
- 2.5 Heredoc/lexical value integrity: session pending-heredocs from lexer
  events (PTY-pinned per A5); executable `HeredocRedirect` body
  non-optional; frozen token-part graph (MEDIUM-3, MEDIUM-10).
- 2.6 Analysis session: state-aware incremental analysis; compose or reject
  multiple modes at invocation (MEDIUM-9). **DISCHARGED v0.762.0** (reject-at-invocation ruled; 7 verify rounds, 2 devs, evidence `2.6-rescue/`). **WAVE 2 COMPLETE** — 2.1 v0.756.0, 2.2 v0.757.0, 2.3 v0.758.0, 2.4 v0.760.0, 2.5 v0.761.0, 2.6 v0.762.0.

**Wave 3 — expansion semantics and command authority** (target 4 releases)
- 3.1 Pattern correctness: continuation-aware negation + nullable-extglob
  composition, all consumers; generated finite-alphabet differential battery;
  flips the three `[[` rows + re-rules the `KNOWN_DIVERGENCES` empty-subject
  set (HIGH-7 semantics half) (A9: lands first).
- 3.2 Pattern engine integrity/perf: frozen node graph + frozen cache;
  one-pass all-start relation; deterministic transition-count assertions;
  benchmark delta vs Wave 0 baseline (HIGH-7 perf half, MEDIUM-6).
- 3.3 Operand field IR: field vectors through `:-`/`:+`/`:=`/operator
  operands; scalar projection only at named terminal consumers; flips the
  operand-flatten pins + closes carry #4 (HIGH-6).
- 3.4 Resolution authority timing: A8 matrix first, then transactional
  left-to-right prefix expansion → single `ResolvedCommand` from
  authoritative state; static no-second-resolution guard (HIGH-3).
- 3.5 Typed expansion/arithmetic user-errors replacing broad catches
  (MEDIUM-12b; Q2 masker ledger shrinks accordingly).

**Wave 4 — lifetime and state ownership** (target 3–4 releases; 4A before 4B)
- 4A.1 Activation/component transaction: depth checkpoint, restore-all-LIFO,
  aggregate failure surfacing, quarantined ownership; the A5 multi-shell
  poisoning battery; managed signal dispositions under component leases;
  `STD_FDS` release on failed permanent acquisition (HIGH-8, MEDIUM-8, LOW).
- 4A.2 Shutdown phases: EXIT-trap `SystemExit` cannot bypass job disposition/
  reap/history/lease restoration; exit-status precedence specified;
  PTY-verified incl. huponexit (MEDIUM-1).
- 4B.1 Immutable reads: frozen `VariableLookup`, no shared `_MISSING`,
  immutable binding view; readonly/nameref/observer/export coherence pinned
  by mutation attempts (MEDIUM-5).
- 4B.2 Input decoding: one incremental decoder across the cursor/bulk seam,
  every 2/3/4-byte split pinned; `read -N` honors `-t` (A5 rider) (MEDIUM-2).
- 4B.3 History state machine: file cursor independent of memory deletion;
  `history -s` under HISTSIZE; `-r/-n/-d/-s/-a/-w` sequences vs bash
  (MEDIUM-7).
- 4B.4 InputCursor contract per the Wave 0 ruling (close or narrow).

**Checkpoint R** — bespoke multi-scope adversarial workflow over the whole
tree (the predecessor's closing-verification format: independent scopes,
composed probes, attack rounds to zero), answering the sequence doc's five
questions; produces the Wave 5 re-scope amendment.

**Wave 5 — per the Wave 0 ruling (A7)** — 5B capability boundaries (incl.
the `ExpansionContext`/`LocaleContext` naming collisions and the
core↔expansion private-import cycle), 5C cohesion/typed errors/annotations
(boundary seams first), and 5A only if ruled in.

**Ceremony C** — sequence doc §12 with A6's compare-bash form; every #22
discriminator + flip-pin + guard-offender re-run at ONE final tree; three
seeded gates; benchmark + counter deltas vs Wave 0 explained; close report
whose headline agrees with its tables; ledgers and essential probe evidence
IN the committed tree.

## 7. Release ceremony (per slot)

Repo-standard E4 flow, run only by the integrator, per `CLAUDE.md`:
version bump + CHANGELOG + README/ARCHITECTURE version lines → commit →
fresh detached gate worktree → `python -u run_tests.py --parallel
--write-attestation < /dev/null` (background + watcher) → copy attestation →
FINAL commit → `python tools/verify_gate_attestation.py` → push → PR →
merge → targeted single-tag fetch (`git fetch origin
"refs/tags/vX:refs/tags/vX"` — watch the tag, not the fetch rc) → evidence
rescue into the campaign evidence tree → remove worktree/branch. Local
`main` fast-forward only when the parallel session's README reconcile allows.

## 8. Risk register

| Risk | Mitigation |
|---|---|
| 5A sinks closability | A7: Wave 0 in/out ruling; default OUT as successor campaign. |
| HIGH-3 blast radius (every command's side-effect ordering) | A8 matrix precedes design; slot 3.4 isolated; compare-bash + conformance in its exit. |
| Pattern rewrite regressions across 5 consumer contexts | A9 split; generated differential battery; counters + benchmarks vs baseline. |
| Wave 1 migration long tail destabilizes conformance timing | A10 batches; per-batch green; runner policy changes land in 1.1 before migration. |
| Parallel-session file collisions | §3 never-touch list; index edits deferred; launch-time coordination item. |
| Gate flake/ENOSPC/environment | Disk headroom check; seeded-shuffle triplicate at Wave 0 and Ceremony C; flaky finds get fixed-or-pinned in Wave 1's hygiene slot. |
| macOS gate vs Linux nightly divergence (signals/PTY in Waves 2.5/4) | Reason about Linux at design time; nightly watch rows in the ledger; carry-forward of predecessor's Linux-watch obligations. |
| Verifier drift (stale harness preamble) | Wave 0 task 7; harness preamble reviewed at each wave boundary. |

## 9. Launch checklist (all require explicit user go)

1. User go received for launch.
2. Wave 0 tasks 1–8 complete; ledger has no TBD.
3. Baseline legs green and recorded (this also discharges the predecessor's
   pending exit legs, A11).
4. First Wave 1 dev brief written; worktree cut from the launch base.

Until item 1, this document is a plan of record only.

---

## Amendment AM-1 (2026-07-24, at launch)

Wave 1 gains slot **1.4 — Linux nightly recovery**. At launch the `nightly.yml`
backstop was found RED for 23 consecutive nights (since 2026-07-02; last green
`b314064c`), spanning the predecessor campaign's entire final stretch —
current census 24 full-suite + 54 conformance-suite failures at the launch
base, including the J1 signal-family rows predecessor carry #17 (a MUST) was
watching. Evidence trust is Wave 1's charter and the nightly is the Linux
observation channel, so recovery lands there; carry #17 discharges inside 1.4.
Record: `docs/reviews/evidence/boundary_remediation_2026-07/nightly-status.md`;
ruling R3 in the ledger. Wave-close checklist gains "check latest nightly
run result" (this failure mode was the repo's CI-green lesson, re-learned).

Wave 0 rulings recorded in the ledger Part C: **R1** 5A OUT (successor
RESUMABLE-PARSER campaign inherits carries #12/#16/#31 and Part B re-carries);
**R2** InputCursor dup-sharing/temp-redirect isolation de-scoped → 4B.4 is a
contract-narrowing documentation slot; **R4** LOW printf float formatting =
declared Wave 5 rider.
