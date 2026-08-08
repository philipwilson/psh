# Checkpoint R — Whole-tree boundary reappraisal (sequence §10)

- **Date:** 2026-08-08. **Integrator:** campaign integrator (this report's
  rulings are the integrator's; all measurement is agent-attributed below).
- **Tree appraised:** `ae871a16` = v0.773.0 = main = origin/main (Waves 0–4
  complete, v0.751.0–v0.773.0, 22 slots).
- **Format:** predecessor closing-verification precedent — independent scopes,
  composed probes, attack rounds to zero. Round 1 = six independent scoped
  verifiers (Q1–Q5 + QR-queue), each in its own detached worktree at
  `ae871a16`, import-discriminator asserted, oracle `/opt/homebrew/bin/bash`
  5.2.26. Round 2 = three adversarial attack scopes (cross-composition,
  verify-the-verifiers, coverage-gap closure) against the round-1 result.
- **Charter:** `checkpoint-r/charter.md` (dispatch copy, md5
  `a08a9c1df086b1c128b8bce6772f1d57`). Round-1 digest: `checkpoint-r/`
  (mechanically generated from the workflow journal, md5 `b0bb7dd7…`).
- **Verification-only:** no implementation, no committed-file edits by any
  agent; synthetic offenders lived only in agent worktrees and were reverted.

## Verdict

**CLEAN BILL, CERTIFIED UNDER ATTACK — attack rounds to zero.** Round 1 (six
independent scopes): ZERO BLOCKERs, ZERO REQUIRED-NITs, 23 NOTEs. Round 2
(three adversarial scopes, explicitly chartered to refute round 1): ZERO
BLOCKERs, ZERO REQUIRED-NITs, 7 NOTEs — every attack scope states the clean
bill SURVIVED. No LEDGER closure claim was contradicted anywhere in either
round; every declared deviation touched behaves as declared; zero false
findings in either direction. Per the pre-registered convergence rule
(RESUME.md, at round-2 dispatch): a round-2 attack returning zero new
BLOCKER/REQUIRED-NIT findings satisfies attack-rounds-to-zero. The seven
round-2 NOTEs are three PRE-EXISTING unregistered divergences (each
base-provenance-graded at `0215279c` — psh byte-identical base/tip, so
register additions, not campaign regressions; Part D rows below), two
instrument-portability notes, and two gap-closures that came back clean.

§10 exit criteria: (1) this report records confirmed closures, new blockers
(none), and the updated Wave 5 scope — MET; (2) no unresolved correctness or
evidence-trust blocker is deferred into textbook cleanup — MET (CR-R6, with
the audit's by-elimination evidence); (3) Wave 5 begins from the freshly
verified census below, superseding the v0.749.0 counts — MET (and the census
numbers were independently REPRODUCED EXACTLY by round 2's atk-b).

## The five questions (§10), answered

**1. Do all original #22 HIGH and user-visible MEDIUM discriminators now
pass?** YES — 23/23 rows CONFIRMED (Q1): every CLOSED Part A row's
discriminator re-executed at `ae871a16` reproduces its closure claim; declared
deviations behave as declared (10/10 b-family cells; s1 timeout mapping
rc 142 observed live). HIGH-10 is PARTIAL only in that its Ceremony-C
self-contained-close leg is future BY PLAN. The still-OPEN rows (MEDIUM-14/15/
16, LOW printf %a, LOW deferred-import ledgers) reproduce their base facts —
they are Wave 5's, not regressions. `gate_attestation.json` reconciles
(version 0.773.0; gated commit `cc476e91` an ancestor; 22,775+1,117 passed).
Wording note (q1-F2): H4b/H9a/H9b cells match bash on rc and behavior;
diagnostic WORDING differs per psh's standing multi-line parse-error format —
prefix/wording-normalized in conformance pins, stated here so the cells are
not misread as regressions.

**2. Did any adapter, raw-string fallback, visitor override, subprocess
helper, or service-locator path recreate a deleted boundary?** NO (Q2) — nine
boundary groups swept two ways (guards run + independent grep census): 201
guard tests green across 12 modules; TEN synthetic offenders planted, ten
bites, zero GUARD-DOES-NOT-BITE; zero raw spawns beyond frozen allowlists;
`_ParserWrapper`/`support/utils.py` gone; no `<<` regex outside the sanctioned
survivor; `arg_types`/`_file_synced_len`/`_pushback` zero live hits;
`with_redirections` dead as declared; `as_scalar` only at ruled consumers;
`_materialize_env_name` sole env materializer. Residue (NOTEs q2-F1..F3):
one documented-limit spawn shape in `test_lazy_script_source_i2.py` (honest
limit, not a bypass); two retirements are dead-by-sweep with no reintroduction
ratchet (`arg_types`, `_file_synced_len` — structural retirements); one
psh-only PTY module records its own oracle-exemption only in its docstring.

**3. Are the new representations transitively immutable and
authority-timed?** YES (Q3) — all charter representations HOLD under fresh
outside-the-suite attack: frozen lexical graph rejects depth-3 writes;
pattern nodes/CompiledPattern reject writes reached through a live Shell;
VariableLookup rejects set/del on all three surfaces with shared singletons;
OperandValue raises on every str-coercion route; the OpenDescription lifecycle
rule holds shell-observably (14 dup/temp-frame cells == bash except the
DECLARED move-form); history pending set satisfies all five O3 invariants with
mutation-proven drift-loudness; HeredocRedirect body unconstructible absent;
AnalysisSession derivation guard bidirectional. Authority timing: exactly ONE
`resolve_command` on dispatch (ratchet + five offender arms); seed-at-COMMIT
(D-3.4-s4 behaves exactly as declared); one shared `iter_command_units`;
refuse-before-evaluate proven with the RHS-marker-file cell. One flagship
guard mutation-proven to bite (unfreezing Position fails the 2.5 census 10/78,
clean revert). NOTE q3-F1: the committed 4B.4 three-way instrument hardcodes
two retired worktree paths — its REGRESSION axis is no longer re-runnable from
the record; successors write fresh divergence-axis equivalents and cite the
committed transcripts for base.

**4. Did the work introduce new dependency cycles, deferred-import caps,
broad owner parameters, complexity cliffs, process leaks, or flaky tests?**
NO on five of six axes; YES, quantified, on complexity (Q4):
- Cycles: 0 package-level runtime cycles (independent AST walker, tip + both
  bases); r19 layering lock green and mutation-proven on two offenders; all
  six campaign-created modules obey it.
- Deferred imports: FELL 183→179 (cap sum 206→200); one new cap entry with a
  declared cycle-break; 21 cap-slack is a hygiene note (q4-F3).
- Owner params: 12 new full-`Shell`/`ShellState` params in wave-touched
  modules vs 2 removed (q4-F2/q5-F6) — the existing convention continued;
  folds into 5B's consumer-migration scope.
- Complexity: census reproduces the 54 baseline EXACTLY at v0.749.0; tip = 60
  fns ≥100 lines. `_run_command` +52 (→263), `apply_var_fd_redirect` +55
  (→107); 12 already-large functions grew; campaign created/grew five hub
  files (+939 pattern_engine, +282 operands, +282 file_redirect, +231
  command_assignments, +201 io_redirect/manager). ABSORBED into 5C (below).
- Process leaks: procsub reap, writer cleanup, shutdown parity, lease orphan
  sweep all clean (incl. a fresh visible-mechanism probe). One divergence —
  finished bg job stays zombie past command boundaries until exit, bash reaps
  promptly — is PRE-EXISTING (byte-identical at v0.749.0/v0.750.0/tip) and
  previously UNREGISTERED (q4-F4); registered by this checkpoint (Part D row
  below).
- Flaky tests (recorded evidence): SIX consecutive green scheduled Linux
  nightlies (08-03..08-08); every recent red classified in
  `nightly-status.md`; Wave-4 suites passed their FIRST Linux exposure;
  exit-trap sentinels green on Linux + 20/20 bounded local iterations;
  recurrence tally stands at 2. TIMING FACT: v0.773.0 merged after the 08-08
  nightly — its first scheduled Linux run is pending (integrator watch).

**5. Is Wave 5 still the right architecture backlog?** YES for 5B verbatim;
YES for 5C with re-scoped numbers (Q5). See the amendment below. Fresh census
replaces the v0.749.0 counts per the §10 exit criterion.

## Wave 5 re-scope amendment (Checkpoint R ruling CR-R1)

Baseline for Wave 5 = the Checkpoint R census at `ae871a16` (instruments in
`checkpoint-r/`), superseding all v0.749.0 counts:

**5B — KEEP ENTIRE, backlog 100% intact** (nothing in §11's 5B text was done
by waves 1-4): both name collisions live (`ExpansionContext` ×2,
`LocaleContext` ×2); core-to-expansion private import live
(`locale_service.py:577,592`); `_POSIX_CLASSES` still owned by
`expansion/glob.py` with the back-import; `VariableAccess`/`ExpansionContext`/
`LocaleContext` protocols have ZERO consumers; 9 Protocol classes (2 migrated
/ 3 defined-unused per the MEDIUM-14 shape); full-Shell consumer surface GREW
251→255 Shell + 14→19 ShellState params. Three reshapes:
1. **FIRST deliverable of 5B** (ruling): extend the Q1 shell-consumer
   ratchet's scan scope to the remediation-campaign-created modules — the
   scope is frozen at the predecessor set and a synthetic full-Shell offender
   in `analysis_session.py` passes it 11/11 (q5-F2, mutation-proven). 5B's
   exit is measured by this ratchet; it must be current before migration
   starts.
2. The 12 campaign-added owner params (enumerated in q4/q5 instruments) are
   IN 5B's migration set — mostly narrow status helpers, none protocol-shaped.
3. 5B's "caps materially shrink" criterion now measures from 179 actual / 200
   cap (q4), and includes trimming the 21 cap-slack.

**5C — KEEP with re-scoped numbers**: hubs = 60 fns ≥100 lines (54 at base;
the six campaign-touched growers explicitly in scope — `_run_command`,
`apply_var_fd_redirect`, `pattern_engine`, `operands`, `file_redirect`,
`command_assignments`/`io_redirect/manager`); §11's named-transaction list
still matches the actual hub census. MEDIUM-12 residue precisely enumerated
(q5-F7): 7 BROAD_MASKING ledger entries + 24 terminal except-Exception
handlers (0 bare); NOTE — `let_builtin.py`'s catch is ALREADY a typed
`(ValueError, ArithmeticError)` pair at tip; the LEDGER's "broad catch"
wording for it is corrected by this report. Incomplete signatures: 648
(Method A) / 488 (Method B) at tip — GREW 625→648 during the campaign; the
two campaign-created modules sit outside the `disallow_untyped_defs` ratchet
with 4 incomplete private defs (q5-F3) — bringing them in is part of 5C.
Explicit absorbs: D-3.5-s2 and D-4B.4-s3 (dead `with_redirections` API) into
5C; MEDIUM-12's subscript + expansion/arith halves DROPPED-AS-DONE (carved by
2.3/3.5, censuses reconcile).

**Riders:** LOW printf %a/%A stays the declared Wave-5 rider (reproduces
byte-exactly as recorded, q5-F5).

## Checkpoint-R-queued rows — dispositions (rulings CR-R2..CR-R7)

- **CR-R2 — TIMEFORMAT %P: QUICK RIDER APPROVED** (QR recommendation
  accepted). Mechanism confirmed live at tip: `os.times()` 10ms quantum feeds
  `(U+S)/R` in `executor/core.py#_format_timeformat`; psh printed `P=0.00` in
  60/60 `time true` runs vs bash 1.62–3.53 in 10/10 (the zero face of the same
  quantization; the absurd face is load-dependent, 0/60 idle). Blast radius:
  one file + un-blinding the deliberately magnitude-blind test. Runs as a
  standalone micro-slot on user GO (not inside this checkpoint —
  verification-only).
- **CR-R3 — EXIT-trap output misdirection: characterization STANDS; stays
  successor queue** with the non-perturbing-observation ENTRY REQUIREMENT
  intact. 0 events in 200 validity-controlled foreground runs (consistent with
  recorded long-run rates); both un-quarantined sentinels green locally
  (10/10) and on Linux; recurrence tally 2; both post-1.4 recurrences were
  sibling rows already classified. Re-eval owed at the successor, not Wave 5.
- **CR-R4 — Benchmark tier baselines: OWED BASELINES NOW EXIST** — harvested
  from 3 consecutive nightly artifacts (10ms rows measure 11.3–12.6ms on the
  shared runner; the 2ms row 3.0–3.4ms; stable spread across 2 head SHAs);
  visibility conditions verified at `ae871a16`. Discharge at CEREMONY C:
  retune the three constants to runner-measured envelopes and re-gate them.
  (The 08-08 nightly's three misses behaved exactly as the declared class,
  q4-F5.)
- **CR-R5 — D-4A.2-s1 (exit-trap flake mechanism): premise UNCHANGED by
  4B.4** (zero signal/trap/job files changed v0.769.0..tip; the io_redirect
  diff is cursor bookkeeping inside the existing frame lifecycle). Stays with
  the successor row.
- **CR-R6 — No-defer audit: PASS.** No Part B RE-CARRIED or Part D
  successor row is an unresolved correctness or evidence-trust blocker
  deferred into Wave 5 textbook cleanup (qr-F4, by-elimination, with the
  5C-routed rows spot-verified as deadness-argued cleanup). The 2.3-carry
  LEXER NO-PROGRESS CRASH (CLI-reachable raw RuntimeError; bash keys `x]`)
  re-reproduces exactly as recorded and is RE-AFFIRMED PRIORITY at the head
  of the r18-lexer successor campaign queue — named owner, not general queue.
- **CR-R7 — new Part D row (from q4-F4):** finished background job remains a
  zombie past subsequent command boundaries until shell exit where bash reaps
  promptly — PRE-EXISTING (identical at v0.749.0/v0.750.0/`ae871a16`),
  previously in NO register; now recorded as a characterized divergence on
  the successor queue (general async reaper family, carries #12/#16).

Also: HIGH-10's only open leg is Ceremony C's self-contained close — carried
there (q1 recommendation).

## Round 2 — the attack, and what it added

**Attack-A (cross-composition):** 11 composition families, ~84 cells, every
cell exercising two or more closed slots' machinery in one shell command,
two-sided vs bash — decoder×procsub/forks 8/8, prefix-staging×field-IR 9/9
(refuse-before-evaluate marker ABSENT both shells), patterns×fields 9/9,
fatal-substitution×traps×exec 8/8, analysis×heredocs (exec/-n/--validate
parity per contract), rd-vs-combinator-vs-bash three-way + security
byte-identical across parsers, failed-exec×cursor lifecycle, typed-errors×
errexit×traps 7/7, RANDOM×forks. The historical regression habitat
(composition cells) produced ZERO contradictions of any closure. Three
pre-existing unregistered divergences surfaced (Part D rows CR-D2..CR-D4).
The declared combinator arrays.py carry diverges EXACTLY at its pin's
spellings.

**Attack-B (verify-the-verifiers):** 14 round-1 headline cells reproduced
from the committed instruments — byte-identical (path-normalized) or
count-exact in every case, including both census bases re-derived at
`0215279c` (54 fns; 625/466 signatures; walker counts exact). All six scope
discriminators verified genuine (transcripts + probe sources assert both
facts). NAME-VS-BODY on six cited guards: all genuinely assert their named
property. Three synthetic offenders re-planted with DELIBERATELY VARIED
shapes (different visitor, tuple-form broad except, third producer in a
different file): all three guards went red naming the offender, green after
revert. The %P zero-face independently reproduced 20/20. Classification
honesty audit: 14 line-precise citations resolve; every round-1
FAILED/PARTIAL verdict honestly evidenced; no NOTE understated; q5-F2's
ratchet-blind-spot independently re-proven two-arm. Verdict: could not
refute the clean bill anywhere it attacked.

**Attack-C (coverage-gap closure):** every round-1 `not_checked` gap closed
GREEN — MEDIUM-7's committed battery 161/161 (collect-only counts first);
4B.2 face 72 cells + 4B.4 contract/registry/M8 57 tests = green; all four
PTY legs run one-module-at-a-time foreground with no hangs (heredoc PTY
70/70, shutdown-phases 4/4, shutdown-route 2/2, read-exact tty 3/3); HIGH-2
sentinel battery 78/78; MEDIUM-13's companion 1→0 claim HOLDS under a fresh
AST instrument (0 state-guarded asserts tree-wide over 828 test files);
HIGH-1's frozen census reconciles (95 modules / 243 spawn sites, per-dir
split exact, spot-checks clean). The question-coverage audit found the ONE
face no round-1 scope examined — resurrection of slot-internal deleted
deciders outside Q2's nine groups (`visit_word_substitution_bodies`,
`_substitute_scan`, `_seq_nullable`, `OperandResult` internals,
`_file_synced_len`, the utils facade) — and closed it CLEAN: zero
resurrections (atk-c-F3). q4-F4 verified genuinely unregistered and its
register row drafted (adopted as CR-D1).

## Findings register

Round 1: 23 NOTEs, 0 BLOCKERs, 0 REQUIRED-NITs (q1-F1/F2, q2-F1..F3, q3-F1,
q4-F1..F5, q5-F1..F8, qr-F1..F4). Round 2: 7 NOTEs, 0 BLOCKERs, 0
REQUIRED-NITs (atk-a-F1..F3, atk-b-F1, atk-c-F1..F3). Full text in the two
digests; the load-bearing ones are woven into the sections above and the
Part D rows below.

## New Part D register rows adopted by this checkpoint (CR-D1..CR-D6)

- **CR-D1** (q4-F4/atk-c-F1, attach to Part B carry #12): bg-job reap-timing
  divergence — a finished background job's process remains Z/defunct past
  subsequent command boundaries until shell exit; bash (async SIGCHLD reap)
  shows none by the next boundary. PRE-EXISTING (byte-identical
  v0.749.0/v0.750.0/tip); observable only via ps; no fd leak; bounded by
  jobs-table size. Mechanism = the absent general async reaper already
  RE-CARRIED as carry #12 (H19 residual, routed with #16). Repro:
  `checkpoint-r/instruments/q4/q4_14_procleak_followup.py` +
  `atk-c/p08_bgjob_zombie.sh`. Unpinned (no committed test flips on it);
  pin owed by the successor owner.
- **CR-D2** (atk-a-F1): psh runs the EXIT trap after a failed `exec PROG`
  where bash 5.2.26 exits without running it (rc 127 parity; trap-fire
  divergence; controls prove exec-specificity). PRE-EXISTING at `0215279c`.
  Successor queue (shutdown/exec family, 4A.2-adjacent). Unpinned;
  characterization transcript `atk-a/a08b_execfail_trap`.
- **CR-D3** (atk-a-F2): fork-taxonomy RANDOM inconsistency — subshell and
  cmdsub forks reseed (bash-mechanism parity) but PIPELINE-MEMBER forks
  continue the parent's seeded sequence deterministically where bash
  reseeds. PRE-EXISTING at `0215279c`. Successor queue (with the D-3.4
  dynamic-specials family). Unpinned; transcript `atk-a/a10b`.
- **CR-D4** (atk-a-F3): `history -w` to fd-path targets (`/dev/fd/N`,
  `/dev/stdout`, `HISTFILE=/dev/fd/N`) succeeds rc 0 and writes in psh where
  bash 5.2.26 fails rc 1 silently writing nothing; named-file and
  `/dev/stdin` read routes are parity. PRE-EXISTING; distinct from the
  declared b1–b5 family. Successor queue (history file-op family, 4B.3
  successor territory). Unpinned; transcript `atk-a/a01`.
- **CR-D5** (q3-F1 + atk-b-F1, instrument portability): (a) the committed
  `4b.4-rescue/instruments/instr12_three_way.py` hardcodes two retired
  worktree paths — its REGRESSION axis is not re-runnable from the record;
  successors write fresh divergence-axis equivalents citing the committed
  transcripts for base. (b) `checkpoint-r/instruments/q3/p05` requires a
  pre-existing `<worktree>/tmp` (fails LOUD, not silent, in a fresh
  worktree; byte-identical after mkdir). Standing note for successor
  re-verifications: instrument portability is part of the record.
- **CR-D6** (q2-F2 + atk-c-F3): the dead-by-sweep retirement class — retired
  authorities with no reintroduction ratchet (`arg_types`/`quote_types`,
  `_file_synced_len`, and the slot-internal deciders enumerated in
  atk-c-F3) — verified zero resurrections at `ae871a16` by two independent
  sweeps. Structural retirements; record-only (a resurrection requires
  rewriting the mechanism; no cheap guard adds value beyond the sweeps now
  on record).

## Method & instruments

Round 1: workflow `wf_f7c52bc5-09d`, 6 agents, ~21 min, 428 tool uses; every
scope in its own detached worktree at `ae871a16` (all removed cleanly),
import discriminator asserted before measurement (two scopes' discriminator
probes each independently CAUGHT the editable-install-imports-MAIN hazard and
applied the banked PYTHONPATH+cwd correction), oracle bash 5.2.26 recorded
per scope. Instruments + transcripts: `checkpoint-r/instruments/{q1,q2,q3,q4,
q5,qr}/`. Committed version-pinned wave-0 probes were never edited (fresh
0.773.0-pinned equivalents written per the D-4B.3-note hazard). Two round-1
agents self-caught and corrected instrument errors in-transcript (q4 lease
probe v1, q4 P4 capture cell v1; errata noted in their dirs — the two-version
record is deliberate).
Round 2: workflow `wf_de92254a-f5c`, 3 agents, ~24 min, 170 tool uses; same
worktree/discriminator/oracle discipline (atk-a and atk-b additionally held
second detached worktrees at `0215279c` for base-provenance grading — the
reason all three fresh divergences could be graded PRE-EXISTING rather than
left ambiguous). Round-1 instruments were treated read-only (copies taken;
the single path edit per copy recorded). Two attack agents self-recorded
their own instrument defects with corrected v2 designs in-transcript (atk-a:
rundir-path normalization + the bash-5.1+-reseeds instrument-mirror flaw;
atk-c: one stray no-op line that never touched a measured cell) — consistent
with the campaign's instrument-discipline standard.

## Convergence statement

Round 1 found zero blocker-class defects. Round 2, chartered adversarially
against round 1 across three cutting planes (composition, evidence audit,
coverage closure), found zero blocker-class defects and independently
reproduced round 1's key evidence. Attack rounds reached zero; the
checkpoint CLOSES with the clean bill certified, the Wave 5 amendment
(CR-R1) in force, and the dispositions CR-R2..CR-R7 + register rows
CR-D1..CR-D6 recorded in the LEDGER.
