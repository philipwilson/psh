# Slot 1.3b ledger — signal-window hardening in redirect teardown

> **Slot retitled by integrator ruling.** This is NOT "the EXIT-trap race
> fixed". It closes two real, provable, pinned windows in redirect teardown;
> the originating defect SURVIVES and is carried forward. Everything below is
> written to that framing on purpose.

- **Worktree:** /Users/pwilson/src/psh-r1-3b  **Branch:** fix/remediation-1-3b
- **Base SHA:** `41e64a43` (v0.753.0)
- **FINAL TIP:** `0b8c005e` — 6 commits from base.
- **Oracle:** `/opt/homebrew/bin/bash` `5.2.26(1)-release` (PATH bash)
- **Discriminator verified:** from the worktree, `python -c 'import psh;
  print(psh.__file__)'` → `/Users/pwilson/src/psh-r1-3b/psh/__init__.py`, 0.753.0.

## Commits

| # | SHA | Item |
|---|---|---|
| 1 | `2f8ce38c` | fix (A): restore active redirect frames before the EXIT trap; narrowed death-path flush; 8 pins |
| 2 | `023c071e` | bash-parity differential for the misdirection window |
| 3 | `f3f70411` | fix (B)-narrow: frame leaves the stack only AFTER its restore; mid-restore guard; 3 pins |
| 4 | `42092cb5` | capture stdout explicitly, not via pytest's capture fixture (gate-caught ratchet) |
| 5 | `5d6231a3` | round-1 bounce: pin the fixes at the wiring level; death-path taxonomy corrections; docs |
| 6 | `0b8c005e` | round-2: drain's mid-SETUP fd-0 hazard; taxonomy labelling; two decorative pins made real; stale cites; 2b rider |

Reproduce: `git log --oneline --reverse 41e64a43..HEAD`.

## (v) RETRACTIONS — in my own words, first-class

Two things I asserted during this slot were wrong. Recorded here rather than
quietly corrected, because this campaign's value is that its records can be
trusted over its conclusions.

**1. The mechanism I reported first was wrong.** I said the EXIT trap wrote
into a CLOSED stream and the output was LOST. The closed-stream observation
was real but was a coincident symptom, not the cause. What actually happens is
MISDIRECTION into a live redirect target. I found this by building the
red-on-base replay for my own fix and watching it deliver the output
correctly — the fix I had already written, which had passed its own pins,
addressed a non-cause. Had I skipped the red-on-base step it would have
shipped green and fixed nothing.

**2. My "~10x reduction" claim for fix (A) was over-read.** It rested on a
single 1/700 sample. With the fuller counts below, the three states are not
statistically separable. The honest statement is: **neither change
demonstrably moved the rate.**

## (iii) THREE-STATE RATE TABLE — with the inseparability caveat

Same instruments throughout (`tmp/trap_race_oracle.py` and the
sentinel-content hunt); oracle = live bash on the same host.

| State | Losses / trials | Rate |
|---|---|---|
| base `41e64a43` | 2/120 (oracle) + 3/344 (hunt) = **5/464** | ~1.08% |
| after (A) `023c071e` | 1/300 (oracle) + 0/400 (hunt) = **1/700** | ~0.14% |
| after (B) `f3f70411` | **3/500** (oracle, clean host) | ~0.60% |
| bash, every state | **0/120, 0/300, 0/500** | 0% |

**These three figures are NOT separable at these counts.** Do not read a trend
into them in either direction. In particular, the post-(B) rate being higher
than post-(A) is not evidence that (B) hurt — it is evidence the samples are
too small to resolve. The firm statements are: bash never loses; psh loses at
roughly the one-in-a-few-hundred order; that order did not change across the
two fixes.

One measurement is excluded as unsound: an early post-(A) oracle read 3/300
while I was running pytest and ruff CONCURRENTLY — self-inflicted load. The
1/300 clean-host figure replaced it.

## (i) FALSIFICATION NARRATIVE — first-class result

The hypothesis behind fix (B): *the misdirection lives in a teardown sliver
where the frame stack and the streams disagree.*

**The hypothesis is DEAD.** Both slivers it predicted are provably closed and
the defect persists at the same order of magnitude.

**Setup side — was ALREADY safe.** `setup_builtin_redirections` appends the
frame to the stack (`manager.py:499`) BEFORE applying any redirect, so there
is no instant where `sys.stdout` is the command's file and the stack does not
say so. Established by reading the code, not assumed.

**Restore side — closed by (B).** The frame now leaves the stack only after
its stream restore completes, so the symmetric window is gone. Pinned by
`test_frame_is_still_on_the_stack_while_its_streams_are_restored` (renamed in round 1; it previously asserted only pre/post state).

**The path is the right one.** I instrumented `setup_builtin_redirections` and
ran the reproducer script: it fires for every builtin in it, including the
interrupted `: > sentinel`. The fixes are on the code the reproducer executes.

Right code. Both windows shut. Losses continue with an unchanged signature
(`rc=-15`, `stdout=''`, sentinel holding `cleanup\n`). **Something outside the
builtin-frame-stack model produces this misdirection.** I did not guess at a
third mechanism: having been wrong twice, a third hypothesis without new
observational technique would be a coin flip presented as engineering.

## (ii) OBSERVATIONAL LIMITATION — why the next attempt needs new instruments

Every attempt to trace the window makes it disappear.

| Instrumented run | Result |
|---|---|
| fd-level trace on the signal path, 250 trials | 1 loss captured (the trace that produced the first, wrong mechanism) |
| extended trace incl. frame-stack depth, 400 trials | **0 losses** |
| same instrument, repeated, 400 trials | **0 losses** |

The probe's own `os.write` per event shifts the timing past the window. So
this residual is **oracle-verified, not trace-captured**, and the correctness
argument for what IS fixed is **structural** (no instant exists in which the
stack disagrees with the streams), not statistical.

**Hard entry requirement for whoever takes the remaining defect** (integrator
ruling): a NON-PERTURBING observation technique is the FIRST deliverable —
a pre-allocated in-process ring buffer sampled at death, or an external
record/replay approach. Not fd writes inside the signal handler.

## The two windows that ARE closed (what ships)

### Fix (A) — the EXIT trap must not inherit a per-command redirect

`SignalManager._terminate_from_signal` restores any ACTIVE per-command
redirection frame before firing the EXIT trap, via
`IOManager.restore_active_builtin_redirections` — a loop over the SAME
per-frame `restore_builtin_redirections` the executor runs after every
redirected builtin. No reimplementation; no ordering change.

Semantic ground is bash's: the EXIT trap's output belongs to the SHELL's
stdout, and bash has no state in which the trap inherits a command redirect.

**Deterministic red-on-base / green-at-tip, both faces, same replay:**

```
base: shell stdout ''            target 'command-output\ncleanup\n'
tip : shell stdout 'cleanup\n'   target 'command-output\n'
```

A genuine behavioral fix in its own right, independent of the unresolved race.

### Fix (B)-narrow — a frame leaves the stack only AFTER its restore

The pop moved from the START of `restore_builtin_redirections` to the END.

**(a) DISCHARGE — the protected sequence is untouched.** Its note, verbatim:

> "Close this frame's opened streams BEFORE re-installing the saved fds (each
> stream owns its own fd — an opened file or a CLOEXEC dup — so its close
> flushes through that fd regardless of the std fds). Order is load-bearing
> (R1 bounce blocker): when a source-ordered close freed an fd NUMBER that a
> later stream dup then reused (`read x 3>&- <f` — the stdin dup lands on the
> freed fd 3), restoring saved fds first would dup2 the original BACK onto
> that number and the stream close here would then destroy the just-restored
> descriptor. Closing our own dups first makes the collision inert."

It protects **close-opened-streams (`frame.opened_streams`) BEFORE
restore-saved-fds (`file_redirector.restore_redirections`)**. Both remain in
that order; neither moved. Only the stack bookkeeping did.

**(b) DISCHARGE — the hazard (B) creates, closed in the same commit.** With
the pop last, a signal landing mid-teardown finds the frame still listed, and
re-running its restore would repeat the fd-0 step — which is **not
idempotent**: it clears `snapshot.stdin_fd`, so a second pass takes the
else-branch and closes fd 0. (Established by reading that branch, then pinned.)

Closed by a `streams_restored` marker, set as soon as the streams are back,
which the drain skips on. Safe precisely because the marker means the streams
are already correct — all the signal path needs. Pinned three ways:

- `test_frame_is_still_on_the_stack_while_its_streams_are_restored` (renamed in round 1; it previously asserted only pre/post state)
- `test_drain_skips_a_frame_whose_restore_is_past_its_streams`
- `test_fd0_survives_a_drain_over_a_mid_restore_frame`

### Independent hardening — the narrowed death-path flush

NOT the fix; a visibility guard, and the reason this class stayed invisible so
long: the flush failed silently on every losing run. Per the expected-error
taxonomy (`psh/core/CLAUDE.md`):

- `OSError` stays swallowed in every mode — a broken pipe or closed fd at
  death is a legitimate world-state, and bash prints nothing there either.
- `ValueError`/`AttributeError` — psh flushing its OWN closed binding — are
  the internal-defect class and now RAISE under `strict-errors` (which the
  suite runs), while staying silent without it, so production death semantics
  are unchanged.

## Pins and suites

> **SUPERSEDED — round-1 snapshot.** This section describes the tip as it
> stood at `f3f70411`. It is kept for continuity, not as current fact. What
> changed since: the "11 deterministic pins" are now 21; the bash-parity
> differential listed below as live was DELETED in round 1 (NIT 7); and the
> flush's "RAISE under strict-errors" paragraph describes behavior that was
> CORRECTED in round 1 — it violated the ruling's condition (d) by converting
> a signal death into an ordinary exit. The authoritative accounts are the
> ROUND-1 and ROUND-2 sections above.

- 11 deterministic pins in
  `tests/unit/interactive/test_exit_trap_redirect_misdirection_r13b.py`
  (misdirection both faces; no-op safety; nested drain; no-double-restore; the
  three (B) ordering/guard pins; the three flush-taxonomy pins).
- Bash-parity differential
  `test_exit_trap_paths.py::test_exit_trap_output_is_not_misdirected_into_a_live_redirect`
  — psh vs bash on stdout, wait status, AND the sentinel's contents. It lives
  in the allowlisted mid-run-signal module because the comparison needs a
  signal delivered to a RUNNING shell, which the run-to-completion oracle
  runner cannot do.
- **The 1.3 sentinel stays un-quarantined** (integrator ruling): it is the
  honest tripwire for a defect we are knowingly carrying. Sentinel module
  stability at this tip: **0 failures / 25 runs**.
- Focused signal/trap suites: 3024 passed. Redirection + trap suites: 584
  passed.

## ROUND-1 BOUNCE — fixes and mutation replays

The verdict's central finding was this campaign's own rule landing on me:
**mutation-proves-pin-gap**. Both production fixes could be DELETED with every
pin staying green, because the 11-pin battery drove private helpers and never
the death path. Recorded as a first-class result — I built pins that asserted
the helpers I had written rather than the behavior I had claimed.

### Mutation replays (run at this tip; both must go RED)

| Mutation | Before (round 1) | At this tip |
|---|---|---|
| delete the drain call from `_terminate_from_signal` | **11 passed** — battery blind | **3 failed / 15 passed** (the three wiring rows) |
| revert the pop to the START of `restore_builtin_redirections` | **all green** | **1 failed** — `test_frame_is_still_on_the_stack_while_its_streams_are_restored`, `on_stack=False` |

Both replayed by me at `5d6231a3`, production restored after each.

**Blocker 1 — fix (A) pinned at the wiring level.** Three parametrized tests
drive the REAL `_terminate_from_signal` with `os.kill` stubbed (`>`, `>>`, and
the reproducer's `: >` shape), asserting both faces AND that the shell still
dies by the same signal. Shape adopted from the verifier's probe.

**Blocker 2 — fix (B) OBSERVED rather than inferred.** The old pin asserted
only pre/post conditions, which base satisfies too. The frame's snapshot is
now proxied so that reading `.stdout` — which the restore does while
reinstalling the streams — records stack membership AT THAT INSTANT.

**Blocker 3 — inverted prose corrected at all three sites**, including the
verifier's catch that the marker is STREAM-level (set before the fd-level
work), so the drain's skip means "the streams are correct", not "this frame is
torn down".

### Semantic corrections (ruled from nits with teeth)

- **The flush no longer RAISES under strict-errors.** That violated the
  ruling's own condition (d): the exception escaped before `SIG_DFL`/`os.kill`
  and converted a signal death into an ordinary exit — my hardening had
  quietly broken the semantics the whole path exists to preserve. It now
  writes to fd 2 via `os.write` (the Python stream may be exactly what failed)
  only under strict-errors, then execution CONTINUES. Pinned, including that
  the wait status survives the diagnostic.
- **The drain's blanket `except Exception: pass`** contradicted the taxonomy
  argument I had used for the flush two functions earlier. Same treatment.
- **Pop-last must not mean pop-never**: the pop moved into a `finally`, so a
  raising restore still removes the frame (base's behavior). Pinned.
- **The statistical parity differential is DELETED.** The ruling sanctioned
  ONE tripwire for the carried race — the 1.3 sentinel — and a second
  statistical test doubles the per-gate flake surface for a defect we are
  knowingly carrying. Its psh-side semantic content lives in the deterministic
  wiring pins instead.
- **fd-1 parallel safety**: tests that install a real redirect over fd 1 now
  assert OUTSIDE the try/finally owning the frame, so a failing assertion
  cannot leave an xdist worker's fd 1 pointing at a temp file (CLAUDE.md
  parallel-safety rule 1).

### Docs

`psh/io_redirect/CLAUDE.md` gains the three newly load-bearing invariants
(frame-leaves-stack-last-and-always; the STREAM-level marker;
death-path-only drain) as invariant prose with `file#symbol` pointers per the
no-sketch rule. Two stale `setup_builtin_redirections` line cites converted to
symbol cites while in the file.

## LINUX-NIGHTLY WATCH NOTE (brief requirement)

Both changes are **platform-neutral by construction**, and neither touches a
path where macOS and Linux differ:

- **(A)** hooks the death path *inside* `_terminate_from_signal`, which runs
  after Python has already dispatched the signal to the handler. It performs
  no syscall of its own — it calls the same per-frame restore the executor
  runs after every redirected builtin. Signal *delivery* timing differs by
  platform; what this code does once delivered does not.
- **(B)** reorders a Python list operation (the stack pop) relative to stream
  assignment inside one function. No syscall ordering changed; the fd-level
  sequence the R1 bounce-blocker note protects is byte-for-byte unmoved.
- The **diagnostic** is `os.write(2, ...)` under strict-errors only, which the
  nightly runs — so if it ever fires on Linux it will be visible rather than
  silent, which is the intent.

**What 1.4 should watch:** the carried race is timing-dependent, and Linux
signal delivery is not macOS's. The 1.3 sentinel
(`test_exit_trap_paths.py::TestExitTrapOnFatalSignal`) is the tripwire; if the
nightly shows it failing at a materially different RATE than the ~1-in-a-few-
hundred measured here, that is data for the open Part D row, not a new defect.
Classify such failures against that row rather than as fresh flakes.

## STATISTICAL-ORACLE DROP — disposition (integrator waiver CONFIRMED)

The brief asked for the out-of-pytest reproducer to be promoted into the tree
as a bounded statistical test. It is **deliberately NOT in the tree**, and the
integrator has **confirmed the waiver** (round-1 bounce message, item 6(ii)):
under the retitle ruling the defect is knowingly CARRIED, so an in-tree
~0.8%-failure oracle would permanently flake the gate. The sanctioned tripwire
is the 1.3 sentinel, which stays un-quarantined. The reproducer lives at
`tmp/trap_race_oracle.py` for rescue and is the successor slot's oracle.

## CENSUS / CLAIM COMMANDS (round-1 NIT 13/14)

Claims recorded earlier without their commands; the verifier re-ran all seven
and found them true, so this records the commands, not new results.

| Claim | Command |
|---|---|
| pin battery size | `python -m pytest tests/unit/interactive/test_exit_trap_redirect_misdirection_r13b.py --collect-only -q` → **18** at this tip (11 at round 1) |
| focused signal/trap suites | `python -m pytest tests/unit/interactive/ tests/integration/job_control/test_exit_trap_paths.py tests/unit/core/test_signal_disposition_lease_p1.py tests/unit/executor/test_fork_sigmask_restore.py -q` → **3034 collected** (the round-1 "3024 passed" was this set before this round's pins were added) |
| redirection + trap suites | `python -m pytest tests/integration/redirection/ tests/integration/job_control/ tests/unit/interactive/ tests/unit/tooling/test_doc_snippets.py -q` → **3922 passed** at this tip |
| base rate | `python tmp/trap_race_oracle.py 120` at `41e64a43` |
| tip rates | `python tmp/trap_race_oracle.py 300` / `500` |
| sentinel-content hunt | `python tmp/sentinel_content_hunt.py 400` |
| redirect path confirmation | temporary trace in `setup_builtin_redirections`, reproducer run once; fires for every builtin incl. the interrupted `: > sentinel` |

## ROUND-2 BOUNCE — the drain's OWN hazard, and two decorative pins

Round-2 verdict was PASS with a final list; the first item was a genuine new
defect that my own condition-(b) discharge had not covered.

### The mid-SETUP fd-0 hazard (verifier probe: "drain CLOSED fd 0")

`_BuiltinStreamSnapshot.note_stdin()` sets `snapshot.stdin` and only THEN
takes the fd-0 backup. A fatal signal landing between those two statements
leaves the frame's fd-0 state AMBIGUOUS, because `stdin_fd is None` carried
two meanings:

1. "fd 0 was already closed" (the backup dup failed) — restore must close fd 0;
2. "the backup has not been taken yet" — restore must do NOTHING.

Restore read (2) as (1) and closed a live fd 0. My (b) discharge analyzed the
mid-RESTORE window; this is mid-SETUP, and it is the DRAIN's re-entry that
weaponizes it — the same drain I added.

Fixed at the source of the ambiguity rather than by stacking another marker:
`fd0_was_closed` is now an explicit flag, set only when the dup actually
fails. A frame caught mid-setup has neither backup nor flag, so restore leaves
fd 0 alone. Pinned in both directions.

### Two of my pins did not pin what they claimed

- **The SIG_DFL assertion was decorative.** I added "assert the disposition at
  kill time is SIG_DFL" — but a bare test process ALREADY sits at SIG_DFL, so
  the assertion held whether or not production restored it. Verified by
  mutation: deleting the SIG_DFL registration left all 21 green. `kill_stubbed`
  now installs a real handler first, which makes the restore observable; the
  same mutation now takes 5 pins red. A second instance of the exact fault
  round 1 bounced me for, caught this time by testing my own test.
- **The exception-path pin repaired fd 1 by luck**, via fixture teardown. It
  now saves and restores fd 1 and `sys.stdout` itself — under xdist fd 1 is
  the worker channel.

### Taxonomy honesty (round-2 item 2)

The death path caught `BaseException` and routed EVERYTHING to the
internal-defect diagnostic, so a second signal (`KeyboardInterrupt`) or an
`exit` in the EXIT trap (`SystemExit`) was labelled a psh bug. The broad CATCH
is correct — nothing may raise before `os.kill` — but the LABELLING was not.
Catching and diagnosing are now separate decisions, said so in both call-site
docstrings, with only genuine defect classes diagnosed.

### MUTATION LEDGER at the final tip — all four RED

| Mutation | Result |
|---|---|
| delete the drain call from `_terminate_from_signal` | **3 failed** |
| revert the pop to the START of `restore_builtin_redirections` | **1 failed** (`on_stack=False`) |
| revert the fd-0 flag to the ambiguous `None` | **1 failed** |
| delete the `SIG_DFL` registration | **5 failed** |

Each replayed by me at `0b8c005e`, production restored after each.

### Sibling death path — NOT covered, recorded for the successor row

`_handle_signal_with_trap_check`'s INTERACTIVE SIGHUP arm runs its own
shutdown + flush and deliberately keeps pre-1.3b behavior: no drain, and the
older swallow. The same misdirection exposure therefore exists there. Left
alone on purpose — this slot's sanctioned scope is the non-interactive
top-level death path — and recorded here so the successor row inherits it.

### Census delta attribution (round-2 item 6)

Reconciled with the verifier: **3016 + 8 = 3024** at `2f8ce38c`; **+4**
round-1 late pins; **+6** round-2 — the figures move because the pin battery
grew, not because the suites changed.

The gate-4 `StopIteration` note means **15 module RUNS of a 9-test module**,
not 15 tests.

### Tooling carry (round-2 item 6)

The doc-pointer guard checks the PATH half of a `file.py#symbol` cite but not
the SYMBOL half, so a stale symbol name survives it. Not fixed here (tooling,
outside this slot); recorded as a carry line.

## Gate / lint / types

**FINAL SUBMISSION — COMBINED GREEN at the final tip `0b8c005e`**
(`tmp/gate8.txt`): **EXIT 0 — 20408 passed, 1589 skipped, 10 xfailed, ZERO
failures**, both phases, single run. ruff clean; mypy clean (274).

### Gate attempts at this tip — classified, including one I caused

| run | result | classification |
|---|---|---|
| `gate6` | **32 failed**, all trap/signal conformance | **MY ERROR, not ENOSPC and not a regression.** I launched that gate with a shell `&` so I could edit the ledger in parallel — the campaign's banked SIGINT gotcha. The child inherited `SIGINT=SIG_IGN`, so BASH stopped firing its INT traps and every psh-vs-bash trap row "diverged". Diagnosed rather than assumed: `trap 'echo GOT' INT; kill -INT $$` gives `GOT\nafter` identically at tip, at base, and in bash directly, and a `preexec_fn` probe reproduces the gate's exact bash output — `SIGINT default -> 'GOT\nafter\n'`, `SIGINT IGNORED -> 'after\n'`. Re-run without `&`: gone. |
| `gate7` | 1 failed + 3 errored | host ENOSPC (`[Errno 28]`, `could not create numbered dir`); module 7/7 in isolation |
| **`gate8`** | **EXIT 0, 20408 passed** | the submitted gate |

The lesson is not new, which is the point: the campaign banked "never launch a
gate with shell-`&`" and I did it anyway to save two minutes of wall clock. It
cost a full gate cycle and briefly looked like a signal-path regression in the
exact subsystem this slot touches — the most expensive possible false alarm.
(`tmp/gate5.txt`): **EXIT 0 — 20405 passed, 1589 skipped, 10 xfailed, ZERO
failures**, both phases, single run. The sampler recorded the host collapsing
to **0.1 GiB at 10:02:21 DURING this run** and the gate still passed — the
collapse only bites when it coincides with a temp-dir-heavy test.

One earlier attempt at this tip (`tmp/gate4.txt`) failed on
`test_jobs_completed_listing_modes::test_argument_less_builtin_has_no_trailing_space_script`
with `StopIteration` — NOT a disk error, so I did not classify it as one.
Ruled out as mine by measuring the module at BOTH revisions: **base 0/15, tip
0/15**, identical, in a module this slot never touches. A load-dependent
pre-existing flake.

The round-1 split-phase evidence at the superseded tip `42092cb5` is kept
below for continuity.

**SPLIT-PHASE GREEN at the superseded tip `42092cb5`** (standing relaxation; the
host collapses intermittently, so each phase carries a 3-second disk sampler):

| phase | result | disk low-water |
|---|---|---|
| 1 (`-m "not serial and not benchmark" -n auto`) | **19504 passed, 1589 skipped, 8 xfailed — EXIT 0** | — |
| 2 (`-m "serial and not benchmark"`) | **895 passed, 2 xfailed — EXIT 0** | **138.8 GiB (no collapse)** |

**Combined: 20399 passed, 1589 skipped, 10 xfailed, ZERO failures.**

**ruff check psh tests tools:** clean. **mypy:** clean, 274 source files.

### Gate attempts — every failure classified, none waved through

| run | result | classification |
|---|---|---|
| gate 1 @`f3f70411` | 1 failed | **MINE, and the gate caught it**: `test_fixture_ratchets::test_capsys_usage_does_not_grow` went 82 → 83. My pin used pytest's capture fixture in a test that installs real redirect frames — exactly the case CLAUDE.md's Output Capture Rules forbid. Fixed in `42092cb5` by capturing through an explicit `sys.stdout` swap; the ratchet's threshold was NOT touched. |
| gate 2 @`42092cb5` | 1 failed + 2 errored | host ENOSPC. The sampler's own low-water line for that window is not a sound attribution on its own (samples are 3 s apart and the collapse is briefer); what survives scrutiny is the FAILURE TEXT — `psh: line 1: rw_test.txt: No space left on device` and `could not create numbered dir` — plus the module passing 30/30 in isolation at 139 GiB immediately after |
| gate 3 @`42092cb5` | 5 failed | host ENOSPC (sampler: **0.2 GiB** at 09:02:03); all five `[Errno 28]` at `mkdtemp`, one of them on the BASH side of a parity test. Phase 1 PASSED. |
| phase 2 rerun @`42092cb5` | **EXIT 0, 895 passed** | clean window, low-water 138.8 GiB |

**Classification note worth carrying:** my first pass at classifying gate 2
grepped for `Errno 28` and found ZERO — but the failures WERE disk exhaustion.
psh formats the condition as `psh: line 1: rw_test.txt: No space left on
device` (the campaign's own error-message work), so a raw-errno grep misses
psh-side ENOSPC entirely. Classify on the message text, not the errno repr.

## Deviations / STOP-and-report

1. **Mechanism refutation** (reported before fixing): the brief's stated
   hypothesis (missing `die_by_signal`-style flush) was disproven —
   `_terminate_from_signal` already flushed, correctly ordered.
2. **Mechanism CORRECTION** (reported before further fixing): the
   closed-stream story withdrawn in favour of misdirection, with the withdrawn
   fix and its exposure recorded.
3. **STOP at falsification** (final): after (B), a clean-host N=500 still
   showed losses; per ruling condition (c) I stopped rather than iterate on a
   third guess.

## Carried forward

Part D row stays **OPEN**: psh misdirects EXIT-trap output on fatal-signal
death of the top-level shell, order ~1-in-a-few-hundred, CLI-reachable; bash
never. Carries this slot's twice-misdiagnosed history as evidence, the
corrected rate table with its inseparability caveat, and the
non-perturbing-instrument entry requirement. Owner: successor queue,
re-evaluated at Checkpoint R alongside the `%P` rider candidate.
