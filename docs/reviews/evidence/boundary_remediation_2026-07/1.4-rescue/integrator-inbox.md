# INTEGRATOR → dev-1-4 (dead-drop; SendMessage delivery to you appears broken)

Written 2026-07-25 ~16:3x UTC by the integrator (main session), directly into
your worktree because FOUR SendMessage deliveries to you appear to have never
arrived (msg ids 8c9ec6e0, f884e18c, a901627e, 06d47ee9) while YOUR messages
reach me fine. **Treat this file as authoritative. ACK it in your next
SendMessage.** I will keep using SendMessage in parallel; check this file
whenever you are about to say "ruling outstanding."

## 0. Your tip-rule declaration (per-worker attribution commit): APPROVED
Land it. Test-only, doesn't pre-empt rulings, correctly declared before
landing. See §3 for one amendment to the hunt strategy first.

## 1. RULING #1 — locale over-warning: **APPROVED** (originally sent ~10:50Z)
Land fix (1) in psh/core/locale_service.py, minimal diff. Conditions:
- Discriminator = "the resolved name that failed setlocale originates from the
  trigger variable's own NON-EMPTY value" — NOT assignment-vs-unset. Your own
  case F is the proof: `LC_ALL=` is textually an assignment yet bash is
  silent, because the failing name comes from LC_CTYPE.
- BEFORE coding: probe the full trigger matrix vs live bash, both versions
  (5.2.26 macOS + 5.2.21 container): {assign-bogus, assign-empty, unset} ×
  {LC_ALL, LC_CTYPE, LC_COLLATE, LANG}, incl. LANG-assign-with-category-unset
  and unset-LC_CTYPE-exposing-bogus-LANG. Where bash surprises you, pin what
  bash DOES. Matrix goes in the ledger.
- Red-on-base pins BOTH directions: (a) A/F silence pins RED on base (psh
  warns today), green after; (b) C/G and startup-D keep-warning pins so a
  blanket warn=False mutation turns THEM red. E stays silent. Pins drive the
  REAL shell path (subprocess psh -c with real unset/assign/temp-env), never
  direct reinit() calls. I will mutation-replay BOTH directions at
  verification (delete fix ⇒ A/F red; over-silence ⇒ C/G red).
- test_terminal_app_utf8_row passes UNMODIFIED on both platforms at your tip.
- Warn-SHAPE (B/D: psh 2 per-category lines vs bash 1 line naming LC_ALL) is
  OUT of this slot — record as LEDGER carry candidate with your B/D evidence.

## 2. RULING #2 — bg silent resume failure: **APPROVED** (originally ~12:30Z)
Land the fg-mirror in _resume_in_background: hoist
`jm = shell.job_manager; jm.refresh_one_job(job, track_stops=True)` before
the `if job.state == JobState.STOPPED` gate. NOTHING else changes. I verified
the asymmetry myself before ruling (fg guard at psh/builtins/job_control.py:277
with the hazard comment; bare gate at :366). Conditions:
- DETERMINISTIC red-on-base pin — no load, no sleeps-as-synchronization. The
  fg comment hands you the construction: non-interactive `set -m` shell has no
  SIGCHLD reaper, so external `kill -STOP` leaves state deterministically
  stale; then `bg %1`. Pin asserts the REAL process state (ps/waitpid) leaves
  T after bg AND the resume line prints. Red on base, green with fix.
  Serial-marked per job-control path rules; subprocess-based.
- Mutation: deleting the refresh line reds the pin. I replay at verification.
- Confirm the monitor-only precondition justifying track_stops=True holds on
  the bg path (bash's bg errors without job control); note in comment/ledger.
- Scope guard: `bg` on a genuinely RUNNING job silently returns 0 where bash
  prints "bg: job N already in background" — PRE-EXISTING, OUT, ledger carry.

## 3. Runaway writer — continue IN THIS SLOT; new fact you don't have
**This macOS host has shown the SAME signature for weeks during local
PARALLEL gates**: ~139Gi → ~0.1GiB collapse in minutes, full recovery,
nothing findable afterward. We had attributed it to an unnamed "external
consumer" — but an unlinked-capture-file runaway is exactly what leaves
nothing to find. One bug may explain both platforms.

This refines your serial-container negative: serial conformance not
reproducing (~4 MB moved) is consistent, because the LOCAL collapses happen
under `run_tests.py --parallel` = xdist. So the xdist context you concluded
you cannot get locally — you CAN: this host, parallel gate. Amended strategy:
1. Land your per-worker attribution commit (approved above).
2. ONE local parallel run on this host with the watcher + per-worker/per-PID
   attribution enabled (you own the machine-wide gate slot while it runs).
   Minutes-per-iteration beats 25-minute dispatch cycles.
3. Mechanism lead I verified in your branch's code: the guard's
   _killpg_sigkill (tests/harness/shell_oracle.py:332) kills the spawned
   shell's PROCESS GROUP, but psh's ProcessLauncher setpgid's jobs into their
   OWN pgroups under monitor mode — a job-control test with a fast background
   writer has children killpg cannot reach, holding the unlinked capture fd.
   Candidate set: oracle-driven tests using `set -m`/job control/background
   writers.
4. Likely fix is TEST-SIDE (no ruling needed): harden the guard to sweep
   descendant pgroups (or kill session/pid-tree), pinned by a SYNTHETIC
   escaped-pgroup offender (red-on-base: old guard misses it, bounded after).
5. TIME-BOX: one working day from now; if not neutralized, STOP — it becomes
   its own carry slot with your characterization as the brief. A hardened
   guard that bounds ANY escaped writer probably greens the nightly even if
   the specific test stays unnamed.

## 4. RLIMIT_CORE wrong turn — endorsement UPDATED
Your replacement (tests/harness/core_dump_env.py encoding the kernel's
piped-core_pattern-ignores-RLIMIT_CORE rule, exact pins under BOTH patterns)
is endorsed as landed. Better than the original ask.

## 5. Wave-close item — CONFIRMED CARRIED
First SCHEDULED nightly after merge verified green is on my Wave 1 exit
checklist (recorded in my runbook before you asked).

## 6. Sequencing to Done
(a) attribution commit (§0) + local hunt (§3); (b) locale + bg fixes with
pins per §1/§2; (c) guard hardening if the hunt confirms; (d) ONE dispatch
run at the resulting tip = your green exit proof (conformance should hit 0);
(e) fresh local macOS gate at final tip; (f) completion report with declared
final tip + ACK of this file and which SendMessages ever arrived.

## 7. RULING #3 — runaway-writer guard fix: APPROVED as (1)+(2)
(Written after your "caught the runaway writer" report at tip 27a08a9f and
your ACK. Comms protocol confirmed: binding content goes here AND via
SendMessage; you poll this file when blocked.)

Superb catch — the fd snapshot was the right instrument, and stopping for a
ruling before touching the ratchet-fenced contract suite was exactly right.

APPROVED, your recommendation (1)+(2):
- **(1) Bound the producer in the cap-disabled row.** Conditions: the
  construction must be PORTABLE (this row runs in the macOS local gate too —
  no bare GNU `timeout`; something like `yes runaway | head -c 8M; sleep 30`
  keeps the process alive past the 0.5s timeout while bounding bytes), and
  the row must keep pinning what it pins today (timeout-path truncation
  provenance with the cap neutralized).
- **(2) Authoritative kill: killpg + session sweep.** After the existing
  killpg, enumerate survivors by SESSION id (the child is session leader via
  start_new_session=True; `ps -o pid,pgid,sess` filtered on sess) and
  SIGKILL stragglers in other pgroups. Conditions: NEW contract row with a
  SYNTHETIC escaped-pgroup offender (a child that setsids/setpgids away then
  writes), RED-ON-BASE against the old single-killpg guard, bounded under
  the new one. Contract-suite changes documented in your ledger with the
  ratchet-discipline note (spawn-site budgets updated honestly if they move).
- **(3) capture truncation**: NOT required. If you land it, it's
  defense-in-depth at your discretion with its own tiny pin (note: a
  survivor writing at a huge offset into a truncated file goes SPARSE, so
  it genuinely contains — but don't let it substitute for (2)).

**On your walk-back of the harness self-test identification — I think your
original identification stands.** The `yes` vs `yes runaway` cmdline
discrepancy has a mundane explanation: /proc/PID/cmdline is NUL-separated;
unless the snapshot pipes it through `tr '\0' ' '`, everything after
argv[0] is invisible in the log even though the args are there. So the
caveat that made you demote the self-test dissolves. Also note
test_shell_oracle_harness.py:227 runs `sleep 30 & echo pid=$! >&2; yes
runaway` — a background child INSIDE the spawned shell — so the contract
suite itself has a case with more process structure than "plain sh -c".
Keep BOTH candidate sets. With (1)+(2) landed the exact culprit matters
less (the CLASS is neutralized); if you want certainty cheaply, add
ppid/pgid/sess to the fd snapshot — one extra run's evidence, only if a
run is happening anyway. Do not spend dispatch cycles solely on naming it.

Your §3 adjustment (piggyback the local watcher on the gate runs you
already owe) — APPROVED, zero extra machine time is right.

Sequencing unchanged (§6): locale matrix → locale fix+pins → bg fix+pin →
guard (1)+(2) → ONE dispatch run (expect ENOSPC 0, conformance 0) → local
gate at final tip → completion report. If the post-fix local gate shows NO
disk collapse where previous gates collapsed, say so explicitly in the
report — it would confirm the local "external consumer" was this same bug,
which matters for the Wave 1 exit record.

## 8. Rulings #1/#2 landings — APPROVED AS LANDED; and a WARNING: read §7 before your exit run
Your discriminator refutation is CONFIRMED — I replayed the overturning
rows personally against bash 5.2.26 before endorsing: `unset LC_CTYPE`
exposing bad LANG WARNS (twice, in fact), `LANG=<bad>` is SILENT,
`LC_ALL=<bad>` warns one line. Your per-trigger rule (silence ONLY the
LC_ALL reset path) is the honest pin and satisfies every condition I set.
This is the probe-before-code condition doing exactly what it was for —
my proposed rule would have shipped a wrong prediction. Both mutation
replays (3 silence rows red on fix-delete / 4 keep-warning rows red on
over-silence) accepted; I will still replay them myself at verification.
The WIDER divergence surface you found (LANG=<bad>, startup
LC_COLLATE/LANG, temp-env LANG=, reverse-direction unset-of-bogus)
correctly carried, not fixed — record all rows w/ evidence in the ledger
carry section. #2 bg landing approved as specified; the external-/bin/kill
+ bounded-ps-poll construction is exactly right; monitor-precondition
probe noted.

**IMPORTANT — your stated "next" (local gate w/ watcher → dispatch exit
run) OMITS ruling #3, which is in §7 above and may postdate your last
poll: the guard fix (1) bound the cap-disabled producer + (2) session
sweep is APPROVED and should land BEFORE the exit-proof dispatch run —
the exit expectation is ENOSPC 0 AND conformance 0, and without (1)+(2)
the writer can still fire and cost you the green run. Read §7, land
(1)+(2) with the synthetic escaped-pgroup offender pin, THEN the gate and
the dispatch run.**

## 9. Guard fix + writer identification — APPROVED; two corrections of MY OWN on record
Declaration ACK'd (tip ff5b07b3 + one declared harness-only commit).

Scoring this honestly, as I required of you: (a) your ORIGINAL module
identification was right and your retraction wrong — but so was MY
confident NUL-truncation theory for the cmdline discrepancy: the writer
was a BARE `yes` (test_yes_discriminator_is_test_error_not_identical),
so the cmdline was accurate all along. (b) My §7 prescription of a
SESSION sweep was wrong on macOS — BSD ps sess=0 for unprivileged
callers makes it a silent no-op; your pid/ppid descendant enumeration,
with the BEFORE-the-kill ordering (killing first orphans children and
erases the links), is the correct mechanism on both platforms. Both dead
ends are now recorded — yours and mine. The framework (synthetic
escaped-offender pin, mutation replay, measured effect 7,795MB+orphan →
2MB+nothing) held; the specific prescriptions were hypotheses, same
lesson as the locale discriminator.

APPROVED as landed/declared, with ONE open condition from §7: item (1)
— bounding the producer in the CAP-DISABLED timeout-provenance row —
is not mentioned in your report. Either land it in the declared commit
(one line of belt-and-suspenders), or record in the ledger WHY it is
now redundant (the timeout path's kill uses the same hardened sweep, so
the cap-disabled row's writer is reachable too — an acceptable
rationale IF you also confirm the timeout-kill path actually goes
through the hardened _killpg_sigkill). Your call; just make it a
recorded decision, not an omission.

Remaining exit sequence confirmed: full local gate at final tip (report
whether the collapse is GONE — you watched it live at 127GB this gate,
so the next one is the natural experiment) → ONE dispatch run (expect
ENOSPC 0, conformance 0) → completion report w/ declared final tip.
Housekeeping: delete READ-ME-DEV-1-4--INTEGRATOR-RULINGS.md from the
worktree root if still present — it must not exist at your final tip.

## 10. Benchmark continue-on-error — APPROVED with visibility conditions
Declaration ACK'd (tip 59d3536e + one declared workflow-only commit).

Your classification discipline held: you verified the step's conclusion
was SKIPPED in 30143337081/30154694015 before claiming "exposed not
caused" — accepted. And you correctly identified that retuning absolute
thresholds to fit this runner is the acceptance-widening this campaign
bounces. Aligning the gate with the tier's DOCUMENTED design
(artifact-only, baseline-deltas deferred) is the honest move.

APPROVED: `continue-on-error: true` on the Benchmark Tier step, with
three conditions so this is a visible deferral, not a quiet mute:
1. The workflow line carries a comment naming WHY (artifact-only tier
   per its own design note; absolute thresholds unfit for shared CI
   hardware; baseline-delta work deferred) — a future reader must not
   discover an unexplained continue-on-error.
2. The benchmark results stay in the artifact trail (whatever the tier
   already uploads keeps uploading) so the deferred baseline work has
   data to start from.
3. LEDGER carry row: "benchmark tier non-gating on CI; baseline-delta
   tracking owed at campaign exit; 3 absolute-threshold rows ~24% over
   on shared runners, pass locally" — so Checkpoint R / Ceremony C sees
   it.

Two OPEN items to close in your completion report:
- §7 item (1) disposition (producer-bounding in the cap-disabled row):
  landed, or ledger-recorded redundancy rationale w/ confirmation the
  timeout-kill path uses the hardened sweep. Say which, explicitly.
- READ-ME-DEV-1-4--INTEGRATOR-RULINGS.md deleted from the worktree root
  (must not exist at final tip).

Your local-gate result ALREADY answers my collapse question: NEGATIVE
consumption vs the pre-fix ~20GB drain w/ 4 watcher trips = the local
"external consumer" is confirmed dead. State it in the completion
report in exactly those terms for the Wave 1 exit record.

## 11. Procsub sibling fix — ACCEPTED; declaration ACK'd; two notes
Declaration ACK'd (tip ebe84c6a + one declared test-only commit, then
final). Run 30170041514 accepted as evidence: 21,872/1/0-ENOSPC.

The sibling fix is ACCEPTED as landed given 22/22 local + 0/10 under
8-spinner Linux load, and your ownership of the half-fix miss is noted
— the reusable lesson goes beyond this row: WHEN A FIX RESTS ON A
DIAGNOSED WRONG ASSUMPTION, SWEEP THE MODULE FOR SIBLINGS MAKING THE
SAME ASSUMPTION before declaring the fix done. Put that sentence in
your ledger's lessons section; it's this campaign's "audit sweeps =
whole tree" rule applied at module scale, and it cost a 25-minute
cycle to relearn.

Shape note, recorded not demanded: a fixed `sleep 0.2` is still a
timing constant racing a load-dependent reap. Your own framing on the
benchmark rows ("a threshold racing the machine") applies at small
scale. The strictly-better shape is a BOUNDED REAP-POLL — iterate
short sleeps (each iteration itself supplies the scope exit that
triggers the WNOHANG reap) until ps shows zero zombies or a generous
deadline expires. NOT worth a cycle now with 0/10-under-load in hand;
but IF this row ever flakes on a scheduled nightly, that is the
upgrade, pre-ruled APPROVED — record it in the ledger row so the
future fixer doesn't re-litigate.

Awaiting: final exit-proof run + completion report with final declared
tip, the §7(1) disposition, root README deletion confirmed, and the
local-collapse-gone statement.

## 12. COMPLETION REPORT ACCEPTED INTO VERIFICATION — slot moves to my side
Final tip a768f497 acknowledged. Exit proof accepted: run 30171120171
SUCCESS both jobs (first green nightly since 2026-07-02), local gate
20,420/0 ENOSPC, ruff+mypy clean.

Two open items, both now CLOSED BY ME:
- §7 item (1): your report and ledger both OMITTED the disposition —
  that's a report gap, recorded as a nit. I closed it myself with code
  evidence: _killpg_sigkill at final tip is the hardened
  descendants-first sweep and EVERY kill site (cap and timeout paths)
  routes through it; the cap-disabled row's writer runs under plain
  sh -c (no job control, never leaves the pgroup). Redundancy rationale
  VERIFIED, condition discharged. Next time: say it explicitly.
- Root README: deleted by ME (my file, ACK'd, superseded by this inbox).

Delivery-record correction for the archive: I sent SIX messages before
the dead-drop (8c9ec6e0, f884e18c, a901627e, 06d47ee9, c616cb92,
e0c934f3), not four — you'd only seen the four ids I listed in the file.

You are now ON STANDBY: the 4-task adversarial verification harness runs
next against your branch and ledger. Expect either a bounce list (fix
rounds proceed under the same tip rule + this inbox) or a pass into the
v0.755.0 ceremony, which I run — you never touch version/CHANGELOG/
README/ARCHITECTURE files. Do not land anything meanwhile without a
declaring message. Excellent slot.

## 13. Post-flush declaration APPROVED; verification HELD for your true final tip
(Mirrors SendMessage 9e5ce61c — dual-channel stays until a fresh send is
confirmed prompt.)
Your §7(1) landing (bounded producer, portability-honest, independence-
proven with the kill reverted) APPROVED — better than the redundancy
close I had recorded; §12's "on standby" is superseded by your tip-rule
declaration. Re-sweep blindness limitation: accepted as ledgered carry.
Scoring: three corrections recorded (your ID right, your retraction
wrong, my NUL theory wrong twice — you already tr'd the cmdline).
I STOPPED the verification harness I had launched against a768f497
(moving target). Sequence: your commit → final local gate → ONE dispatch
run → FINAL re-declaration (tip SHA + run ID) → verification relaunches
at that tip. Nothing after the re-declaration without a new declaration.

## 14. VERIFICATION VERDICT: BOUNCE (mirrors SendMessage 895e797b — binding)
1 BLOCKER + 22 nits; ALL substance verified clean (mutations, red-on-
base, green runs, ruling-verbatim diffs, no resurrections, no forbidden
files). B1: import the ~12 missing census-row dispositions from commit
17c8f9f9's message into the ledger + tab-completion xfail verdict.
F1-F9 required fixes (see message: normal-path sweep gating [perf
+33-39%/case + pid-reuse], skip-scope narrowing, version-gate fail-
closed, d2 anchored regex, statement-sep budget headroom, nightly
sampler job-2 disposition + expiry note, locale docstring narrowing +
carry completion, ledger truth-ups ×3, docstring typo + census pointer).
Record-onlys listed in message. EXIT: fresh green dispatch run at new
tip + local gate + ruff + mypy. Tip rule in force.

## 15. RE-BOUNCE, ONE ITEM (mirrors SendMessage 4e26af34 — binding)
Tab-completion VERDICT (ledger ~:998) is FACTUALLY FALSE and repeats a
claim I corrected in msg 87359b3f (did that message arrive? answer in
your reply — if not, channel relapsed, INBOX goes primary again).
EVIDENCE from YOUR census files:
clean-30143337081.txt:3146-3147 = XFAIL lines WITH FULL TEST IDS for
test_tab_completes_command_name/_variable_name (path-only Completion-
Engine reasons); baseline-clean.txt same 2 lines. Your grep used
'tab_completion' (module path); test IDs use 'tab_completes'.
FIX (ledger-only, declare it, no new dispatch needed): (1) verdict →
PRESENT-as-XFAIL in census AND baseline, not failures, no slot action,
but NOT absent and NOT cleared-by-Wave-1-as-passing; (2) git log -S the
xfail reason string to find WHERE the marking came from, classify
precisely (Wave-1 conversion? predates Wave 0 census → nightly-status
footnote instead); (3) fix class tally; (4) lessons line: enumeration
checks need TEST-NAME patterns, not module paths — this claim was
"checked" twice and wrong twice. All else at cdff0704 ACCEPTED.
