# Slot 1.4 — Linux nightly recovery (Wave 1, AM-1; carry #17 J1 family)

- **Agent:** dev-1-4. **Worktree:** `/Users/pwilson/src/psh-r1-4`.
- **Branch:** `fix/remediation-1-4`, base `21d6c5b4` (v0.754.0 merge, all of Wave 1).
- **Started:** 2026-07-25.

## Environments (record in EVERY probe row)

| | local gate host | Linux container (my inner loop) | GitHub runner (authority) |
|---|---|---|---|
| OS | macOS 26.5.2 | ubuntu 24.04 | ubuntu-latest |
| arch | arm64 | **arm64** (differs from runner) | x86_64 |
| python | 3.14.2 | 3.12.3 | 3.12.13 |
| PATH bash | `/opt/homebrew/bin/bash` **5.2.26** | `/bin/bash` **5.2.21** | **5.2.21** |
| extra bash | — | `/opt/bash5226/bin/bash` **5.2.26** built from source (see below) | — |
| `/bin/sh` | bash | **dash** | **dash** |
| `RLIMIT_CORE` soft | **0** | unlimited | unlimited |

Container specifics: `docker run -d --name psh-linux -v /Users/pwilson/src/psh-r1-4:/work -w /work ubuntu:24.04 sleep infinity`,
then `apt-get install python3 python3-pip python3-venv locales build-essential wget`,
repo copied to `/repo` (writable, `.git` removed) and `pip install -e ".[dev]"` into `/venv`.
bash 5.2.26 built from `ftp.gnu.org/gnu/bash/bash-5.2.tar.gz` + official patches 001–026,
`./configure --prefix=/opt/bash5226`. Its purpose is to isolate **bash version** from **OS**
when a row could be either. The container approximates but does NOT replace the
workflow_dispatch proof (arch differs; no runner `~/.bashrc`).

## Runs

| run ID | head | what | conclusion |
|---|---|---|---|
| 30143337081 | `491b0e30` = v0.752.0 | latest SCHEDULED (2026-07-25 04:03 UTC). **Census source.** Predates v0.753.0/v0.754.0. | FAILURE |
| 30154694015 | `21d6c5b4` = my base | my `workflow_dispatch` BASELINE at base tip, dispatched before any change — the honest post-Wave-1 picture (verifies class (i) instead of assuming) | (in flight) |

Logs saved: `tmp/nightly-census/30143337081-failed.log` (raw), `parallel-30143337081.txt`,
`conformance-30143337081.txt` (prefix-stripped), `failed-names-30143337081.txt`.

## Census of run 30143337081

- Job **Full Parallel Suite + Bash Golden Comparison**: phase 1 parallel **16 failed / 19,436 passed**;
  phase 1b serial **10 failed / 883 passed**; phase 2 golden **1,481 passed, 24 skipped** clean.
  Combined manifest: 21,800 passed, **26 failed**, 1,640 skipped, 10 xfailed.
- Job **Full Conformance Suite**: **54 failed** (names in `failed-names-30143337081.txt`).

### Conformance job (54)

| # | family | rows | class | evidence |
|---|---|---|---|---|
| C1 | `test_syntax_template_timing_conformance.py` `-file` channel (20 accept + 24 reject) | 44 | **(i)** | `FileNotFoundError: [Errno 2] ... '/home/runner/work/psh/psh/tmp/tmpXXXX.sh'` — the repo-`tmp/` trap. Fix already in my base (v0.753.0, slot 1.3): module now uses a `tmp_path_factory` `_SCRIPT_DIR` fixture. Verify in 30154694015. |
| C2 | `test_nested_substitution_timing_conformance.py` script-file rows | 2 | **(i)** | same `FileNotFoundError`; same `_SCRIPT_DIR` fixture present at base. |
| C3 | `test_history_outcomes_i4.py` | 6 | **(iv)** | see P1 |
| C4 | `test_subscript_keying_conformance.py::TestCompositeQuoting::test_tilde_expands_in_key` | 1 | **(iii)** | see P2 |
| C5 | `test_locale_conformance.py::TestInheritedCtypeProvenance::test_terminal_app_utf8_row` | 1 | **(v)** | see P3 |

C3/C4/C5 are the SAME tests that also fail inside the parallel job (conformance tests are
collected there too), so the two jobs' failure sets overlap — they are not distinct defects.

### Parallel job (26) — see per-item sections below

## Findings

### P1 — history outcomes (6 rows) — class (iv), test env assumption

`test_history_outcomes_i4.py::test_history_outcome_matches_bash[bang_string, identical_expand,
normal_expand, print_only_recorded_not_executed, set_minus_H_reenables, word_star]`

CI excerpt (normal_expand): psh records `1 echo one / 2 echo one / 3 history`; bash records
`1 echo one / 2 history` — bash drops the duplicate.

Probe, container, case `["echo one","!!","history"]`, fresh HISTFILE per run:

```
bash 5.2.21 (distro = runner):      1 echo one / 2 echo one / 3 history
bash 5.2.26 (built, same OS):       1 echo one / 2 echo one / 3 history
psh (python 3.12.3):                1 echo one / 2 echo one / 3 history
```

All three AGREE → not a bash-version effect and not a psh defect. Discriminator found:
`/etc/skel/.bashrc:13: HISTCONTROL=ignoreboth` (Ubuntu default, hence `/home/runner/.bashrc`
on the runner). `ignoreboth` includes `ignoredups`, which suppresses the second identical entry.
Re-probe with `HOME` pointed at a dir holding that skel `.bashrc`:

```
bash -i          → 1 echo one / 2 history          <-- reproduces CI exactly
bash --norc -i   → 1 echo one / 2 echo one / 3 history
psh  --norc -i   → 1 echo one / 2 echo one / 3 history
```

Root cause: `hermetic_shell_env()` strips `LC_*`/`LANG`/`DISPLAY`/`PWD` but NOT `HOME`, so the
`-i` bash oracle reads the HOST's `~/.bashrc`. The local macOS gate's `$HOME/.bashrc` does not
set `HISTCONTROL`, so the row is green there and red on CI — the comparison is contaminated by
host startup files, in the one module that runs shells interactively.

**Fix:** pass `--norc` to BOTH shells in that module's `_run` (psh supports `--norc`; verified
above that it equalizes them). Only this module uses `["-i"]` (`grep -rn '\["-i"\]' tests/` →
one hit), so the change is contained.

### P2 — assoc-subscript tilde — class (iii), bash version, PROVEN

`test_subscript_keying_conformance.py::TestCompositeQuoting::test_tilde_expands_in_key`
Case: `HOME=/probe-home; declare -A a; a[~]=v; echo "${!a[@]}"`

| shell | OS | result |
|---|---|---|
| bash 5.2.21 | Linux | `~` |
| bash 5.2.26 (built, SAME Linux, same arch/libc) | Linux | `/probe-home` |
| bash 5.2.26 (homebrew) | macOS | `/probe-home` |
| psh | both | `/probe-home` |

Same-OS flip between 5.2.21 and 5.2.26 proves it is the **bash version**, not the platform.
psh matches current bash (5.2.26). Fix = version-gate the row, naming the change (tilde
expansion inside an associative-array subscript was added between bash 5.2.21 and 5.2.26).

### P3 — locale over-warning — class (v), PRODUCTION, STOP-and-report sent

`test_locale_conformance.py::TestInheritedCtypeProvenance::test_terminal_app_utf8_row`

CI: psh emits `psh: warning: setlocale: LC_CTYPE: cannot change locale (UTF-8)`, bash emits
nothing. The row's env is `LC_ALL=C, LC_CTYPE=UTF-8`; `UTF-8` is a macOS locale alias that does
not exist on glibc, so `unset LC_ALL` makes an INVALID ctype effective only on Linux.

Not a Linux artifact — re-probed with `xx_BOGUS.UTF-8` (invalid on BOTH platforms) via
`tmp/locale-warn-matrix.sh`:

| case | bash 5.2.26 macOS | bash 5.2.21 Linux | bash 5.2.26 Linux | psh (both) |
|---|---|---|---|---|
| A `unset LC_ALL` exposes bogus LC_CTYPE | silent | silent | silent | **WARNS** |
| B assign bogus `LC_ALL` | warns 1 line (LC_ALL) | same | same | warns **2 lines** (LC_COLLATE+LC_CTYPE) |
| C assign bogus `LC_CTYPE` | warns | warns | warns | warns (match) |
| D startup bogus `LC_ALL` | warns 1 line | same | same | warns 2 lines |
| E startup bogus `LC_CTYPE` | silent | silent | silent | silent (match) |
| F `LC_ALL=` empties, exposes bogus | silent | silent | silent | **WARNS** |
| G temp-env prefix bogus | warns | warns | warns | warns (match) |

bash's rule: warn only when the variable BEING ASSIGNED fails setlocale (at startup, only for
`LC_ALL`); a locale that becomes effective REACTIVELY (higher-precedence var unset/emptied) is
applied silently. psh warns on every re-application → diverges in A and F, and in warn SHAPE in
B/D. Stable across both bash versions and both OSes.

Code: `psh/core/locale_service.py` — `reinit()` (~L226) re-applies with `warn=True`
unconditionally; `ensure_applied()` (~L189) warns per failing category via `_try_setlocale`
(~L354).

**STOP-and-report #1 sent to integrator.** Proposed: thread the cause into `reinit` so
reactive (unset/empty-driven) re-application applies with `warn=False`; assignments and
startup-LC_ALL keep warning. Fallback offered: platform-gate the row on the `UTF-8` locale name
not resolving. AWAITING RULING — no `psh/` edit until then.

### P4 — core dumps: RLIMIT_CORE platform split — class (ii), ONE cause, THREE red rows

macOS `RLIMIT_CORE` soft default = **0**; Linux = **unlimited**. Measured `python3 -c
"import resource;print(resource.getrlimit(resource.RLIMIT_CORE))"` → macOS `(0, 2**63-1)`,
container `(-1, -1)`.

Consequences on Linux only:

1. `test_pipeline_signal_death.py::TestPipelineLastMemberSignalDeath::test_non_sigterm_names_the_signal`
   and `test_signal_killed_diagnostic.py::TestAbnormalTerminationDiagnostic::test_diagnostic_names_the_signal`
   assert `psh.stderr.strip() == signal.strsignal(SIGSEGV)` but get
   `'Segmentation fault (core dumped)'`. psh is **correct** here — it appends the suffix from
   `os.WCOREDUMP` (`psh/executor/job_control.py:39,73`) exactly as bash does. The TESTS are
   macOS-centric.
2. `test_boundary_j1_lifecycle.py::test_fg_subshell_sigquit_prints_quit` TIMED OUT at 12s.
   Mechanism: it SIGQUITs a forked **CPython** subshell; I measured that core at
   **20,180,992 bytes** in the container (`ulimit -c unlimited` → `/tmp/core`). The two SEGV
   rows above only dump a tiny `dash`, which is why they complete and merely show the suffix.
   On the runner the dump is slower still (hosted runners route `core_pattern` through
   apport), blowing the 12s budget. In my container (`core_pattern=core`, local disk) the same
   command finishes in **0.106s**, so the container does NOT reproduce the timeout — the
   size/route difference is the point, and the fix removes the dump entirely.

Probe, container, `ulimit -c 0`:
```
psh -c '( kill -s QUIT $BASHPID ); echo after=$?'  → stderr "Quit",              after=131
psh -c '( kill -s SEGV $BASHPID ); echo after=$?'  → stderr "Segmentation fault", after=139
```
i.e. with cores off, stderr is exactly `strsignal(sig)` on Linux, matching macOS.

**Fix:** lower the soft `RLIMIT_CORE` to 0 for the pytest process in `tests/conftest.py`, so
every child (psh, bash, dash) inherits it. This NEUTRALIZES the platform difference rather than
widening acceptance, and stops CI writing 20 MB cores into the workspace.

Safety checks done before choosing this:
- `grep -rn "core dumped|WCOREDUMP|RLIMIT_CORE" tests/ psh/` → the only test asserting the
  suffix is `test_job_notice_channel.py:167::test_core_dumped_suffix`, which builds a
  **synthetic** wait status (`_signaled_status(SIGQUIT, core=True)`), so the formatting path
  keeps its coverage regardless of the real limit.
- `tests/conformance/bash/test_ulimit_conformance.py` reads/sets `ulimit -c`. Only the SOFT
  limit is lowered; the HARD limit is untouched, so `ulimit -c unlimited` still raises back,
  and psh and bash are compared as children inheriting the SAME limit → identical either way.

## Classification tally (run 30143337081)

Deduplicated across the two jobs. Conformance rows that also ran inside the parallel job are
counted once.

- (i) already fixed by Wave 1, pending baseline verification: **46** (C1 44 + C2 2)
- (ii) Linux platform behavior: P4 (3 rows) + others below
- (iii) bash-oracle version: P2 (1 row)
- (iv) test defect / env assumption: P1 (6 rows) + others below
- (v) psh production defect on Linux: P3 (1 row) — ruling pending

Remaining parallel-job rows still being root-caused are listed in the working set below.

---

# Part 2 — baseline verification, fixes, and the core-dump correction

## Baseline run 30154694015 (workflow_dispatch at base tip `21d6c5b4`) — CONCLUSION: failure

This is the honest post-Wave-1 picture and it VERIFIES class (i) rather than assuming it.

- **Conformance job: 54 -> 8 failures.** All 46 `-file`-channel `FileNotFoundError` rows are
  GONE. Wave 1's v0.753.0 repo-`tmp/` fix genuinely cleared them. Remaining 8 = 6 history +
  1 locale + 1 tilde.
- **Parallel job:** 24 of the 26 scheduled-run rows recur, plus 3 NEW ones; 2 scheduled rows
  did not recur (flaky).

Failure-set diff (`comm` over the FAILURES headers of both runs):

| | rows |
|---|---|
| in BOTH runs | 24 |
| only in scheduled 30143337081 | `test_argument_less_builtin_has_no_trailing_space_script`, `TestBackgroundScopesWholeList...` |
| only in baseline 30154694015 | `test_subprocess_runs_this_worktrees_psh`, `TestProcessSubRepeatedUse.test_no_zombie_accumulation_across_loop`, `TestPtyJobControl.test_bg_resumes_stopped_job_to_running` |

Union = **29 distinct parallel-job rows**. Every one is dispositioned below.

## P5 — `bg` fails to resume a stopped job (class (v), PRODUCTION, STOP-and-report #2)

`TestPtyJobControl.test_bg_resumes_stopped_job_to_running`, red in 30154694015.

`bg %1` prints its line and returns 0 while the job stays stopped — and the REAL process
state confirms it, so this is not a stale display:

```
psh jobs says: Stopped
REAL process state: ['  41837 T    sleep 42']
```

Load-dependent, which is why the macOS gate never saw it. Container, 8 timeout-bounded
spinners, 2 cores:

| shell | sample immediately | sample +1.0s |
|---|---|---|
| psh | 0/5 Running | 0/5 Running |
| bash 5.2.21, same harness/load | 5/5 Running | 5/5 Running |

The 1.0s settle rules out a sampling race: the state never flips. pytest row failed **9/10**
under load, **0/5** without. Probes: `tmp/pty-bg-probe2.py`, `tmp/pty-bg-probe.py`.

ROOT CAUSE — `psh/builtins/job_control.py::_resume_in_background` gates on a state it never
refreshes: `if job.state == JobState.STOPPED:`. If the stop notification has not been
processed, state is still RUNNING, the branch is skipped, and **SIGCONT is never sent**.
`FgBuiltin` already guards exactly this with `jm.refresh_one_job(job, track_stops=True)` and a
comment saying so in as many words; `bg` never got it.

CANDIDATE FIX (validated in the container's THROWAWAY copy, never in the worktree, no `psh/`
change staged): add the same refresh. Under identical load: probe **5/5 Running**, pytest row
**0/6 failures**. Did NOT reproduce on macOS at 10 spinners — consistent with a race window
macOS timing closes. AWAITING RULING.

## P6 — the RLIMIT_CORE premise was WRONG, and how it was caught

Verification run **30157713743** (tip `1abe5a64`, all test-side fixes) showed the two SEGV
rows STILL failing on `(core dumped)`. The conftest reset had not worked on the runner.

Cause: **when `/proc/sys/kernel/core_pattern` names a PIPE, the kernel ignores `RLIMIT_CORE`
and dumps anyway** (it forces the limit to infinity for piped dumps). Hosted runners use a
piped pattern (apport / systemd-coredump). Proven directly — one kernel, privileged
container, ONLY the pattern changed, soft limit 0 in both:

```
core_pattern = core       -> WCOREDUMP = False
core_pattern = |/bin/cat  -> WCOREDUMP = True
```

CORRECTION: whether a core is dumped is a HOST property no test can assume away. psh appending
`" (core dumped)"` on WCOREDUMP is CORRECT and matches bash. `tests/harness/core_dump_env.py`
encodes the kernel's rule (piped -> always; else the soft limit decides) and the two rows build
their expected text from it — an EXACT pin under both patterns, not a widened one.

Verified in the container under BOTH patterns, including the piped shape that was red on the
runner: **47 passed** each time.

The conftest reset STAYS (it still prevents ~20 MB cores where the pattern is a file) but its
comment no longer overclaims. SIGQUIT row's budget 12s -> 60s: the dump cannot be suppressed on
a runner, and the budget is a hang-catcher.

## P7 — runner disk exhaustion (nightly.yml)

Run 30157713743 died with **~26 ENOSPC on `/tmp`**, taking ~29 otherwise-healthy rows with it
(the `test_dash_var_*`, `test_trap_p_*`, `test_closing_stdout_*` names are ENOSPC victims, not
defects). The logs could not say what consumed the space. Cores are the one mechanism PROVEN to
exist here but are NOT proven to be the whole cause, so nightly.yml gets (a) a plain-file
core_pattern, which restores RLIMIT_CORE's authority so nothing is dumped, and (b) disk +
inode reporting either side of the suite plus the largest `/tmp` entries, so the next ENOSPC
arrives with evidence. The suite does not depend on (a) — the rows ask the host.

## Local macOS gate — host ENOSPC, classified per run (NEVER reflex-retried)

The host disk collapses periodically (documented brief gotcha). Every gate attempt was
classified by message text before any retry:

| attempt | result | classification |
|---|---|---|
| gate-1 | 1 failed | REAL: `test_no_direct_spawn_in_oracle_bearing_modules` — my `resolve_bash` import pulled 3 modules into the oracle-bearing set while their helpers used raw subprocess. FIXED by routing them through the typed runner (the ALLOWLIST is growth-refusing and was NOT grown). |
| gate-2 | 4 failed, 3 errors | ENVIRONMENTAL face (a): all 7 in ONE module, each `[Errno 28]` on temp-dir creation. Isolated re-run on a healthy disk: **9/9 passed**. |
| gate-3 | 5 failed, 2 errors | ENVIRONMENTAL: DIFFERENT module set, all `[Errno 28]`. |
| gate-4 | 5 failed, 5 errors | ENVIRONMENTAL: different set again; includes face (b) "could not create numbered dir ... after 10 tries". |
| gate-5 | 8 failed | ENVIRONMENTAL: job_control signal modules, 8/8 ENOSPC. Isolated re-run: **53/53 passed** (also re-verifies the RLIMIT_CORE change). |

Phase 1 (parallel) PASSED in gate-3, gate-4 and gate-5. Serial phase run alone:
`pytest tests/ -m serial` -> **910 passed, 0 failed, 0 ENOSPC** (`tmp/serial-1.txt`).
The volume shows 138 GB free and 1.4e9 free inodes between collapses; TMPDIR holds only
1.6 GB, so the consumer is external. Shared temp dirs were NOT cleared — other sessions are
live on this host.

## Commit map (branch `fix/remediation-1-4`)

| commit | what |
|---|---|
| `17c8f9f9` | test-side platform-honesty pass (13 rows) |
| `1abe5a64` | route 3 newly oracle-bearing fd modules through the typed runner |
| `603de516` | ask the host whether to expect `(core dumped)`; SIGQUIT budget |
| `8c390de3` | nightly.yml: normalise core dumping, report disk |

## Runs

| run | tip | purpose | conclusion |
|---|---|---|---|
| 30143337081 | 491b0e30 (v0.752.0) | latest SCHEDULED; census source | failure |
| 30154694015 | 21d6c5b4 | BASELINE at base tip | failure (8 conformance, 27 parallel) |
| 30157713743 | 1abe5a64 | verification #1 | failure — conformance 54->1; parallel wrecked by runner ENOSPC; exposed the piped-core_pattern fact |
| 30158789660 | 8c390de3 | verification #2 | (in flight) |

## Wave-close checklist note for the integrator

The first SCHEDULED nightly after this merges (03:00 UTC) MUST be checked green — a
workflow_dispatch on a branch is not the same event and does not prove the schedule works.
`gh run list --workflow=nightly.yml --limit 3`. This is the standing rule nightly-status.md
already records; it exists because the backstop went dark for 23 nights unnoticed.

## GREEN LOCAL GATE at `8c390de3`

`python -u run_tests.py --parallel > tmp/gate-6.txt` (attempt 6, foregrounded, never
shell-`&`):

```
Combined across 2 phase(s) (from phase manifests): 20408 passed, 1589 skipped, 10 xfailed
✅ All test phases PASSED          EXIT=0
```

ENOSPC marker count in that transcript: **0**. `ruff check psh tests tools` -> All checks
passed. `mypy` -> Success: no issues found in 274 source files.

---

# Part 3 — verification rounds and the runner-storage investigation

## Verification run 30157713743 (tip `1abe5a64`)

Conformance **54 -> 1**. Parallel job wrecked by **26 ENOSPC on /tmp** — the `test_dash_var_*`,
`test_trap_p_*` and `test_closing_stdout_*` names in that run are ENOSPC victims, not defects.
This run is also what exposed the piped-`core_pattern` fact (P6): the SEGV rows still showed
`(core dumped)` despite the RLIMIT_CORE reset.

## Verification run 30158789660 (tip `8c390de3`)

- Conformance job: **1 failure** — the locale row only (ruling #1 pending). 2,661 passed.
- Parallel phase 1: clean. **Serial phase 1b: 893 passed, 0 failed** — the ENTIRE J1 signal
  family is green, carry #17's watch targets included.
- Golden phase: 13 failures, **all ENOSPC on /tmp**.
- The disk step I added CONFIRMED the runner's pattern was
  `|/usr/lib/systemd/systemd-coredump …` — a PIPE, exactly as P6 predicted — and that my
  `sysctl` step changed it to `core`.

## The ENOSPC investigation (NOT written off as ambient)

ENOSPC per run: 30143337081 **0**, 30154694015 **0**, 30157713743 **26**, 30158789660 **8**,
30159482125 **2**. It appears only in dispatch runs at MY tips, so it was investigated as
possibly self-inflicted rather than dismissed.

What the instrumentation established:

| observation | conclusion |
|---|---|
| `df` before AND after: **88G avail, 18.5M inodes free**, `/tmp` = 3 MB | the volume is not full at rest; a before/after pair cannot see the fault |
| during-suite `/tmp` entry count peaked at **102** | **kills the ext4 directory-exhaustion hypothesis** the sampler was built to test |
| oracle `DEFAULT_BYTE_CAP` = 8 MB, enforced by polling every `_POLL_INTERVAL` = 50 ms | a runaway writer can exceed the cap substantially between polls — a transient-spike mechanism that WOULD fully recover, matching the readings. Not proven. |

HONEST STATUS: **unexplained**. It is transient, varies 0-26 per run, leaves no trace at rest,
and the one hypothesis I could test (directory exhaustion) is disproven. I did not "fix" it,
because I could not name it. The instrumentation stays so the next occurrence arrives with a
free-space time series.

Own-goal recorded: the first sampler (`3fb896fa`) used `df -i --output=iavail`, which coreutils
rejects (mutually exclusive), so every space reading was lost and only the entry count survived.
Fixed in `b911692f` and verified against a real coreutils `df` BEFORE committing the second time.

## Run 30160449984 (tip `b911692f`) — HUNG, cancelled

The suite step ran past the job's 60-minute timeout. Prime suspect: the unbounded `while :`
sampler, which also broke the brief's own rule that background loops be timeout-bounded — a
background loop on a runner can outlive its step and confuse job teardown. Bounded in
`da851594` (setsid + `timeout 3300` + stdin `/dev/null` + both output fds to a file, so it
holds none of the step's pipes). A diagnostic must never be able to wedge what it diagnoses.

## Commit map (updated)

| commit | what |
|---|---|
| `17c8f9f9` | test-side platform-honesty pass (13 rows) |
| `1abe5a64` | 3 newly oracle-bearing fd modules -> typed runner |
| `603de516` | ask the host about `(core dumped)`; SIGQUIT budget 12s->60s |
| `8c390de3` | nightly.yml: normalise core dumping, report disk |
| `3fb896fa` | nightly.yml: during-suite sampler (df invocation was broken) |
| `b911692f` | fix the sampler's df invocation |
| `da851594` | hard-bound the sampler |

---

# Part 4 — the runaway-writer finding, and final state

## What the 5s sampler proved (run 30162519629)

```
15:11:17 avail_kb=24376616 ifree=18491476 tmp_entries=51
15:11:22 avail_kb=22352440 ifree=18491476 tmp_entries=51    (-2.02 GB in 5s)
15:11:28 avail_kb=20303116 ifree=18491476 tmp_entries=51
   …  monotonic, ~400 MB/s …
15:12:18 avail_kb=  420596 ifree=18491428 tmp_entries=52
15:12:23 avail_kb=       0 ifree=18491431 tmp_entries=51    <-- FULL
   …  later …
15:19:54 avail_kb=92180316 ifree=18490740 tmp_entries=99    <-- fully recovered
```

Reading: **~400 MB/s sustained, 24 GB in 66 s, then full recovery.** `ifree` FLAT and
`tmp_entries` FLAT throughout. So it is BYTES from ONE runaway WRITER — not inode exhaustion,
not directory exhaustion (already disproven), not accumulation. The flat entry count plus the
clean recovery point at a file that is **already unlinked**: its space returns when the last fd
closes, which is exactly why `df` before/after always looked healthy and why `du /tmp`
afterwards found nothing. The drain begins within ~40 s of Phase 1 starting.

## Attribution attempt (run 30163515174, PSH_DISK_WATCH=1)

Top consumers were ~20 tests at **140-224 MB each**, not one test at many GB:

```
223.8 MB  test_reappraisal7_ambiguous_redirect_conformance.py::test_single_glob_match_is_fine
222.5 MB  test_trap_signal_spec_conformance.py::TestTrapPosixNumericForms::test_single_name_operand_resets
220.2 MB  test_trap_signal_spec_conformance.py::TestTrapSignalSpecConformance::test_sig_prefixed_other_signals
…
```

That is the CONFOUND, not the answer: with 4 xdist workers a runaway in worker A is charged to
whatever short test happens to span the window in worker B, and ~400 MB/s x a ~0.4 s test is
~160 MB — which is precisely the band observed. Every top consumer is under
`tests/conformance/bash/`, which is suggestive but weak (they share a directory).

**HONEST STATUS: characterised, NOT identified.** Nailing it needs per-WORKER attribution
(serial run with the watcher, or a watcher that records the worker id), which is the natural
next step and is left as a carry rather than guessed at.

Mechanism worth checking first: the oracle's runaway guard is `byte_cap` = 8 MB polled every
`_POLL_INTERVAL` = 50 ms (`shell_oracle.py`), and it kills via `_killpg_sigkill`. At 400 MB/s a
writer moves ~20 MB per poll, so the CAP trips promptly — unless the writer has escaped the
process group (its own setsid / a psh subshell in a new group), in which case killpg misses it
and it keeps writing to the unlinked capture file. That matches every observation.

## Final state at tip `6a1eab8e`

| gate | result |
|---|---|
| local macOS gate | **GREEN** — `EXIT=0`, 20,408 passed, 1,589 skipped, 10 xfailed, **0 ENOSPC** (`tmp/gate-7.txt`) |
| `ruff check psh tests tools` | All checks passed |
| `mypy` | Success: no issues found in 274 source files |

Nightly at that tip (run 30163515174): conformance job **1 failure** (the locale row, blocked on
ruling #1); parallel job 14 failed / 4 errored, **all ENOSPC-driven** except that same locale
row. Golden phase and the whole J1 signal family are green.

## Journey of the numbers (Linux)

| run | tip | conformance | parallel |
|---|---|---|---|
| 30143337081 (scheduled) | v0.752.0 | 54 failed | 26 failed |
| 30154694015 (baseline) | 21d6c5b4 | **8** | 27 |
| 30157713743 | 1abe5a64 | **1** | ENOSPC-wrecked |
| 30158789660 | 8c390de3 | **1** | phase1 clean, serial **893/0**, golden ENOSPC |
| 30159482125 | 3fb896fa | **1** | 7 (ENOSPC victims) |
| 30162519629 | da851594 | **1** | ENOSPC-wrecked |
| 30163515174 | 6a1eab8e | **1** | ENOSPC-wrecked |

## Carries for the integrator

1. **Ruling #1 — locale over-warning** (psh/core/locale_service.py). Evidence + proposed fix in
   Part 1 P3. Blocks the LAST conformance failure.
2. **Ruling #2 — `bg` fails to resume** (psh/builtins/job_control.py). Evidence + validated
   candidate fix in Part 2 P5. A user-visible correctness bug live on main.
3. **Runaway writer** — characterised above; needs per-worker attribution. This, not psh
   behaviour, is now the dominant cause of nightly redness.
4. **`test_argument_less_builtin_has_no_trailing_space_script`** — one unexplained
   StopIteration in 30143337081, never recurred; now reports the listing on failure.

## Wave-close checklist note (REPEATED — this is the durable one)

The first **SCHEDULED** nightly after merge (03:00 UTC) must be verified green:
`gh run list --workflow=nightly.yml --limit 3`. A workflow_dispatch on a branch is a different
event and does not prove the schedule works. This is the standing rule nightly-status.md records;
it exists because the backstop went dark for 23 nights unnoticed.

## >>> INTEGRATOR NOTE (written directly into your ledger — comms workaround) <<<
Your SendMessages reach me; MINE DO NOT REACH YOU (5 undelivered). Both
rulings were APPROVED hours ago. Full verbatim rulings + conditions +
runaway-writer decision are in TWO places in this worktree:
  - ./READ-ME-DEV-1-4--INTEGRATOR-RULINGS.md   (worktree root — untracked,
    visible in git status; delete it after reading, it must not be committed)
  - ./tmp/remediation-ledgers/INTEGRATOR-INBOX.md  (same content)
Headlines: #1 locale APPROVED w/ trigger-matrix + both-direction pins;
#2 bg fg-mirror APPROVED w/ deterministic stop-pin; writer hunt CONTINUES
in-slot (local parallel gate on THIS host reproduces the drain — details in
the file); your fd-snapshot commit is APPROVED. ACK via SendMessage after
reading. — integrator

---

# Part 5 — the runaway writer, CAUGHT

## The instrument

Per-test attribution was a dead end and I proved it rather than assuming it: run 30165110328
charged **25,481 MB** to `test_readme_statistics.py::test_readme_loc_and_file_counts` on gw0;
run alone in the container that test consumes **22 MB**. It spawns a nested full
`pytest --collect-only`, so under coverage it runs for roughly the ~64 s the drain lasts and
absorbs it. The earlier 140-224 MB band was the same artifact.

So the sampler was changed to catch the FILE: below 40 GB free, snapshot the largest open
descriptors from `/proc/PID/fd` (pid, target, cmdline), max 3 trips. `/proc` is the only place
the file can be seen, because it is already unlinked. Verified against a deliberately unlinked
200 MB file first: reports `target=/tmp/big (deleted)` with owner pid and cmdline.

## The catch (run 30166172359)

```
=== TRIP 1: avail_kb=38931156 ===   53985173504 bytes  pid=21511  target=/tmp/psh-oracle-ffk8xib2/.oracle-stdout (deleted)
=== TRIP 2: avail_kb=36466868 ===   56420745216 bytes  pid=21511  (same fd)
=== TRIP 3: avail_kb=34107980 ===   58842398720 bytes  pid=21511  (same fd)
```

**A `yes` process, pid 21511, writing 54 -> 59 GB (~480 MB/s, matching the measured ~400 MB/s)
into an ALREADY-UNLINKED `.oracle-stdout` inside a `psh-oracle-*` temp dir.**

(The two 2 TB `memfd:doublemapper` entries are the runner's own .NET processes, pids 2085/2105 —
noise. NOTE a flaw in my own output: `sort -rn` separated each fd's size line from its cmdline
line, so the three cmdlines print as a block; pairing is by PID and unambiguous — the low pids
are the runner, the high pid is the writer.)

This explains EVERY earlier observation at once: the file is unlinked, so its space returns when
the fd finally closes (`df` healthy before and after), `du /tmp` finds nothing afterwards, the
`/tmp` entry count stays flat, and free space recovers on its own.

## Where the `yes` comes from

No product test runs `yes`. The only `yes` invocations in the tree are the oracle harness's OWN
contract tests, `tests/unit/tooling/test_shell_oracle_harness.py`:

- `test_output_cap_is_structural_not_advisory` — `run_shell_case([SH,"-c","yes runaway"],
  timeout=30, byte_cap=64*1024)`; relies on the cap kill.
- `test_output_cap_kills_whole_process_group` — same, plus a backgrounded grandchild.
- **`test_timeout_threads_truncation_provenance`** — the dangerous one. It **monkeypatches
  `os.path.getsize` to return 0 for `.oracle-stdout`/`.oracle-stderr`**, deliberately disabling
  the watchdog's cap kill so the case reaches the TIMEOUT path instead, then runs
  `yes runaway` with `timeout=0.5`. With the cap neutralised, the ONLY thing that stops that
  `yes` is the timeout's `_killpg_sigkill`. If that kill misses or races, nothing else will ever
  stop it — and the temp dir is removed on the way out, leaving exactly the unlinked
  `.oracle-stdout` fd observed.

Honest caveat: the captured cmdline printed as `yes` where these cases spell `yes runaway`. I
could not reconcile that from the log alone (my `cut -c1-200` should not have truncated it), so
the *specific* case is inferred from "these are the only `yes` invocations in the suite", not
proven. The mechanism — a `yes` surviving its guard and filling an unlinked `.oracle-stdout` —
IS proven.

Why a kill can miss: `_killpg_sigkill(proc.pid)` targets the spawned shell's process group, and
`run_shell_case` sets `start_new_session=True`. A job-control shell places pipeline members in
their OWN process groups, so a member is not necessarily in the group being killed.

## Recommendation (NOT actioned — integrator's call)

This is the oracle harness's own contract-test suite, recently reworked by slots 1.1/1.2 and
guarded by growth-refusing ratchets, so I have not touched it. Options, cheapest first:

1. Give the cap-disabled row a bounded producer (`yes runaway | head -c 100M`, or
   `timeout 5 yes runaway`) so no configuration of the harness can leave an unbounded writer.
2. Make the kill authoritative: kill by SESSION (the child is a session leader via
   `start_new_session=True`) and re-sweep, rather than by the single process group.
3. Have `run_shell_case` truncate/unlink its capture files before removing the temp dir, so a
   survivor's writes cannot consume space.

This — not psh behaviour — is now the dominant cause of nightly redness.

---

# Part 6 — rulings executed, and the runaway writer FIXED

Integrator rulings arrived via a **dead-drop file** (`READ-ME-DEV-1-4--INTEGRATOR-RULINGS.md`)
after four SendMessages to me were lost. **I received ZERO of them**; my sends reached the
integrator fine, so the break was one-directional.

## Ruling #1 — locale over-warning: the proposed discriminator was REFUTED

Required: probe the full trigger matrix first, and "pin what bash DOES" where bash surprises.
It surprised. `tmp/locale-trigger-matrix.sh`, 18 rows, live bash 5.2.26 (macOS) and 5.2.21
(container) — **identical on both**:

| trigger | bash |
|---|---|
| `LC_ALL=<bad>` | warns |
| `LC_ALL=` (empty) / `unset LC_ALL` | **SILENT** |
| `LC_CTYPE=<bad>` / `LC_COLLATE=<bad>` | warns |
| `LC_CTYPE=` empty, or `unset LC_CTYPE`, exposing bad LANG | **warns** |
| `LANG=<bad>` (any form) | **SILENT** |
| startup `LC_ALL=<bad>` | warns |
| startup `LC_CTYPE` / `LC_COLLATE` / `LANG` bad | SILENT |

The proposed rule was "the failing name originates from the trigger variable's own non-empty
value". **`unset LC_CTYPE` exposing a bad LANG warns** — the failing name comes from LANG, not
the trigger — so that rule predicts silence where bash warns. bash's actual rule is per-trigger
and matches its source shape: LC_ALL assignment is a direct setlocale it reports; emptying or
unsetting LC_ALL takes the RESET path which re-applies every category silently; LC_CTYPE and
LC_COLLATE changes always re-apply their own category with warning; LANG never warns.

LANDED: minimal diff, silence only the LC_ALL reset path. All ruling conditions met —
`test_terminal_app_utf8_row` passes UNMODIFIED (locale conformance **78 passed macOS, 78 passed
Linux**; the container first needed `locale-gen en_US.UTF-8`, without which bash itself warns —
a container artifact).

Mutation replay, both directions (`test_locale_warn_trigger_conformance.py`, 9 rows):
`warn=True` ⇒ **3 silence rows red**; `warn=False` ⇒ **4 keep-warning rows red**; restored ⇒ 9 passed.

CARRY (wider than the ruling assumed, evidence above): psh still diverges on `LANG=<bad>`,
startup `LC_COLLATE`/`LANG`, the `LANG=` temp-env prefix (psh warns, bash silent), and in the
OPPOSITE direction on `unset` of an already-bogus LC_CTYPE (bash warns naming an empty locale,
psh silent) — plus the B/D warn-shape the ruling scoped out.

## Ruling #2 — bg silent resume failure: LANDED as specified

fg-mirror only. Monitor-only precondition **probe-confirmed**: bash and psh both print
`bg: no job control` and exit 1 without it.

Pin `test_bg_resume_refreshes_state.py` is DETERMINISTIC — no load, no sleep-as-sync: the stop
is delivered by an EXTERNAL `/bin/kill` (so the shell cannot have seen it via its own builtin)
and the script BLOCKS on `ps` until the child really is `T`. Mutation: deleting the refresh
gives `bg_rc=0`, no resume line, `after_bg=STILL-STOPPED`. The PTY row that originally caught
this went **9/10 failing under load → 0/8**.

CARRY: `bg` on a genuinely RUNNING job silently returns 0 where bash prints
"bg: job N already in background" (pre-existing, ruling scoped it out).

## The runaway writer — CAUGHT AND FIXED

The integrator's fact — this macOS host shows the same signature under `--parallel` — collapsed
the loop from 25 minutes to 6 seconds. `lsof +L1` (unlinked files still held open) during a
local gate:

```
yes  35808  1w  REG  110331544050  0  .../psh-oracle-4zymx1zf/.oracle-stdout   <- link count 0
```

reaching **127 GB** before dying. Same bug on both platforms.

**Specific case:** `test_shell_oracle_harness.py::test_yes_discriminator_is_test_error_not_identical`,
which calls `compare_behavior("yes")` — a **bare** `yes`. That also resolves the `yes`-vs-`yes
runaway` cmdline discrepancy I had flagged as unreconciled: it was bare all along, so my
original suspicion of that module was right and my later retraction was wrong. Isolated by
running the module (7.8 GB, one live `yes` at PPID 1) then bisecting to that row.

**Mechanism, measured:**

```
psh   pid 40915  pgid 40910
yes   pid 40919  pgid 40919    <- its own group; killpg(40910) never reaches it
```

`run_shell_case` uses `start_new_session=True`, so `_killpg_sigkill` kills the leader's group —
but psh's job control has already `setpgid`'d the command into its own. Cap trips, shell dies,
writer lives on orphaned, still holding a capture file the harness has by then UNLINKED. Hence:
drain at hundreds of MB/s, `du` finds nothing, `df` healthy either side, space returns on death.

**FIX** (test-side): enumerate descendants by pid/ppid **BEFORE** killing — ordering is
load-bearing, since killing the leader orphans children and erases the links — then SIGKILL
survivors.

**Dead end worth recording:** sweeping by SESSION is the tidier idea (a child only leaves a
session via its own `setsid`) and it silently DOES NOTHING on macOS — BSD `ps` reports `sess=0`
for an unprivileged caller. pid/ppid is identical on both platforms.

Effect on that module: **7,795 MB and a live `yes` → 2 MB and nothing**. New synthetic pin
`test_cap_kill_reaches_a_writer_that_left_the_process_group` drives a writer into its own group
under `set -m`; reverting to killpg-only reds it.

The site-count ratchet then fired on the new `ps` spawn — working as designed — and was resolved
by the deliberate two-place budget change it asks for, with the justification recorded.

## Final gates

| | result |
|---|---|
| local macOS gate, tip `59d3536e` | **GREEN** — EXIT=0, **20,420 passed**, 1,589 skipped, 10 xfailed, **0 ENOSPC**, **0 leaked processes**, disk delta NEGATIVE (nothing consumed) |
| previous gate (pre-fix, same host) | drained to ~20 GB free, 4 watcher trips, ENOSPC present |
| `ruff check psh tests tools` | All checks passed |
| `mypy` | 274 files, clean |

## Commit map (final)

| commit | what |
|---|---|
| `17c8f9f9` | test-side platform honesty (13 rows) |
| `1abe5a64` | 3 fd modules → typed runner |
| `603de516` | host decides `(core dumped)`; SIGQUIT budget |
| `8c390de3` | nightly: core_pattern + disk report |
| `3fb896fa` `b911692f` `da851594` | disk sampler (added, df fixed, bounded) |
| `6a1eab8e` `27a08a9f` | per-test then per-worker/open-fd attribution |
| `79d0a11c` | **fix: LC_ALL reset path is silent** (ruling #1) |
| `ff5b07b3` | **fix: bg refreshes state before SIGCONT** (ruling #2) |
| `164d34fa` | **fix(harness): kill reaches escaped process groups** |
| `59d3536e` | budget the new `ps` spawn site |

---

# Part 7 — EXIT PROOF: the Linux nightly is GREEN

## Run 30171120171 at tip `a768f497` — conclusion **SUCCESS**

https://github.com/philipwilson/psh/actions/runs/30171120171

| job | conclusion |
|---|---|
| Full Conformance Suite | **success** |
| Full Parallel Suite + Bash Golden Comparison | **success** |

Phase totals: phase 1 **19,497 passed**; phase 1b serial **895 passed**; golden **1,481 passed**.
Combined **21,873 passed, 0 failed**, 1,641 skipped, 10 xfailed. Conformance job 2,662 passed.
The extended RD-vs-combinator fuzz (40,000 iterations) passed. The benchmark tier reports 3
timing failures and is non-gating by design (see below).

**ENOSPC: ZERO.** (`grep` finds two literal matches in the log — both are my own workflow
COMMENT text echoed in the step listing, not errors.) Lowest free space sampled during the whole
run: **91,264,520 kB**, against **0** in the pre-fix runs. The drain is gone.

## The last two failures, and how they were dispositioned

**Benchmark tier (3 rows).** Newly EXPOSED, not newly caused: verified that the step's
conclusion is `skipped` in runs 30143337081 and 30154694015, because every nightly since
2026-07-02 died at the suite step and never reached it. The first run to get there found three
ABSOLUTE wall-clock thresholds tuned on a dev machine — `0.012370 < 0.01`, `0.012388 < 0.01`,
and a 2 ms tokenisation budget — ~24% over on shared CI hardware, all three passing locally.
The step already declares itself "artifact-only, no baseline deltas", so it was gating by
accident; `continue-on-error: true` aligns the gating with the tier's stated design. Retuning
the constants against measured runner baselines is the deferred work those numbers want —
picking values that fit today's runner would just move the flake.

**`TestProcessSubReaping::test_no_zombie_accumulation_across_commands`.** My own miss: I fixed
the sibling loop row in this module and did not check whether its neighbour made the same
assumption. It did. Same cause (sampling `ps` races psh's by-design WNOHANG reaping at scope
exits), same fix (settle first). Verified 22/22 locally and **0/10 under an 8-spinner load on
Linux**, the condition that produced it.

## Final gate evidence at tip `a768f497`

| | result |
|---|---|
| Linux nightly (dispatch 30171120171) | **GREEN — both jobs success** |
| local macOS gate | **GREEN** — EXIT=0, 20,420 passed, 1,589 skipped, 10 xfailed, 0 ENOSPC |
| `ruff check psh tests tools` | All checks passed |
| `mypy` | 274 files, clean |

## Journey (Linux), start to finish

| run | tip | conformance | parallel job |
|---|---|---|---|
| 30143337081 (scheduled, census) | v0.752.0 | **54 failed** | 26 failed |
| 30154694015 (baseline at my base) | 21d6c5b4 | 8 failed | 27 failed |
| 30157713743 | 1abe5a64 | 1 failed | ENOSPC-wrecked |
| 30158789660 | 8c390de3 | 1 failed | serial phase clean; golden ENOSPC |
| 30162519629 / 30163515174 / 30166172359 | … | 1 failed | ENOSPC (writer hunt) |
| 30168712840 | 59d3536e | **SUCCESS** | 3 benchmark rows only |
| 30170041514 | ebe84c6a | **SUCCESS** | 1 failed (procsub sibling) |
| **30171120171** | **a768f497** | **SUCCESS** | **SUCCESS** |

## Carries

1. **Locale**: psh still diverges from bash on `LANG=<bad>` (bash silent), startup
   `LC_COLLATE`/`LANG`, the `LANG=` temp-env prefix, and — opposite direction — `unset` of an
   already-bogus LC_CTYPE (bash warns naming an empty locale, psh silent); plus the B/D
   warn-shape (psh emits one line per category, bash one naming LC_ALL). Evidence: Part 6 matrix.
2. **`bg` on a genuinely RUNNING job** silently returns 0 where bash prints
   "bg: job N already in background" (pre-existing; ruling scoped it out).
3. **Benchmark thresholds** want measured runner baselines rather than dev-machine constants.
4. **`test_argument_less_builtin_has_no_trailing_space_script`** — one unexplained StopIteration
   in 30143337081, never recurred; now reports the listing on failure.

## Wave-close checklist (the durable one)

The first **SCHEDULED** nightly after merge (03:00 UTC) must be verified green:
`gh run list --workflow=nightly.yml --limit 3`. A branch `workflow_dispatch` is a DIFFERENT
event and does not prove the schedule works. Confirmed by the integrator as already on the Wave 1
exit checklist.

---

# Part 8 — closing the integrator's open conditions

## §7(1) — bound the producer in the cap-disabled row: **LANDED** (not claimed redundant)

`test_timeout_threads_truncation_provenance` monkeypatches the watchdog's size poll to 0, so it
is the ONE place in the suite where nothing limits a writer's bytes — the exact shape that filled
an unlinked capture file at device speed.

I confirmed the redundancy argument WOULD have held: the timeout path calls the same hardened
`_killpg_sigkill` (`shell_oracle.py:549,554`). I landed the bound anyway, because a row that
switches off its own safety net should not depend on the kill being correct.

Construction per the ruling's portability condition (no GNU `timeout`; this row runs in the macOS
gate): `yes runaway | head -c 8388608; sleep 30`. `head -c` exits after 8 MiB; `sleep` keeps the
shell alive past the 0.5s deadline, so the TIMEOUT path and the truncated partial capture the row
exists to pin both survive (8 MiB >> the 16 KiB readback cap).

PROOF the bound is independent of the kill — kill hardening deliberately reverted, row re-run:
**disk delta 0 MB, 0 leaked processes** (with an unbounded producer and a broken kill this is the
row that ran away). Module total after landing: 38 passed, **8 MB** consumed, 0 leaks.

## Honest limitation found while closing §7(1)

The timeout path calls `_killpg_sigkill` TWICE (`:549` then `:554`, the second after
`proc.wait()`), and the second call was designed as a re-sweep for stragglers that forked during
the first kill. My descendant enumeration walks pid/ppid from `proc.pid` — but by the second call
the shell is dead and its children are reparented to init, so **the second sweep can no longer
see them**. The FIRST call does the real work (it enumerates before killing), which is why the
measured result is 0 leaks. Recorded rather than papered over; the §7(1) bound covers the
residual for the one row that disables its cap.

## §7 ratchet discipline (contract-suite changes)

The site-count ratchet fired on the new `ps` spawn in `_killpg_sigkill` and was resolved by the
deliberate two-place change it demands: `_EXPECTED_SPAWN_SITES["harness/shell_oracle.py"]` 2 → 3,
with the justification recorded inline (cannot route through the runner — it IS the cleanup that
makes the runner's kill authoritative, so doing so would be circular; fixed argv, never a shell;
reads only a pid/ppid table, so it cannot manufacture a false IDENTICAL). NAMED_ALLOWLIST and the
intentionally-empty PSH_ONLY_REGISTRY were NOT grown.

## §10 — benchmark tier CARRY (owed baseline work, for Checkpoint R / Ceremony C)

`continue-on-error: true` on the Benchmark Tier step. Conditions met: the workflow line carries a
comment naming why (artifact-only tier by its own design note; absolute wall-clock thresholds
unfit for shared CI; baseline-delta tracking deferred), and the transcript stays in the artifact
trail (`Upload Benchmark Transcript`, `if: always()`, verified).

**CARRY:** three thresholds are dev-machine constants — `test_simple_command_performance` and
`test_complex_structure_performance` at `0.0124 < 0.01`, and `test_tokenization_scaling` at a 2 ms
budget — ~24% over on shared CI hardware, all passing locally. They want MEASURED runner
baselines. Retuning them to fit today's runner would just move the flake, which is the widening
this campaign exists to bounce.

## §11 — reusable lesson, banked

**When a fix rests on a diagnosed wrong assumption, sweep the module for SIBLINGS making the same
assumption BEFORE declaring done.** I fixed `TestProcessSubRepeatedUse::…_across_loop`, did not
check its neighbour, and `TestProcessSubReaping::…_across_commands` cost a full 25-minute cycle
to rediscover — after I had already written the diagnosis that predicted it.

**PRE-RULED UPGRADE (approved, not owed now):** if either procsub row ever flakes on a scheduled
nightly, replace the fixed `sleep 0.2` with a bounded reap-poll — short sleeps iterated, each
supplying the scope exit that triggers the WNOHANG reap, until zero zombies or a generous
deadline. A fixed constant is still a timing number racing a load-dependent reap, which is the
same criticism I levelled at the benchmark thresholds.

## Local "external consumer" — CONFIRMED DEAD (Wave 1 exit record)

The macOS gate host's long-standing unexplained collapses (~139Gi → ~0.1GiB in minutes, full
recovery, nothing findable) were **this same bug**, not an external consumer:

| gate run | disk behaviour |
|---|---|
| pre-fix (`gate-9`, tip `ff5b07b3`) | drained to **~20 GB free**, 4 watcher trips, one `yes` observed live at **127 GB** on an unlinked `.oracle-stdout` |
| post-fix (`gate-10`, tip `164d34fa`) | **0 watcher trips, 0 ENOSPC**, whole-gate consumption **negative** (nothing consumed) |
| post-fix (`gate-12`/`gate-13`) | green, 0 ENOSPC |

The signature is gone on both platforms from one test-side fix.

---

# Part 9 — FINAL EXIT PROOF at tip `d3783922`

## Run 30172534890 — conclusion **SUCCESS** (second consecutive green)

https://github.com/philipwilson/psh/actions/runs/30172534890

| job | conclusion |
|---|---|
| Full Conformance Suite | **success** — 2,671 passed, 2 skipped, 8 xfailed |
| Full Parallel Suite + Bash Golden Comparison | **success** — 21,873 passed, 0 failed |

Golden phase 1,481 passed. Benchmark tier reports 3 timing rows and is non-gating by design.
**Real ENOSPC: ZERO** (the two `grep` matches are my own workflow COMMENT text in the echoed step
listing — they carry the `[36;1m` ANSI prefix). Lowest free space sampled during the run:
**91,260,268 kB**, against **0** pre-fix.

Two consecutive green dispatch runs: **30171120171** (`a768f497`) and **30172534890**
(`d3783922`).

## Final gate evidence at tip `d3783922`

| | result |
|---|---|
| Linux nightly (dispatch 30172534890) | **GREEN — both jobs success** |
| local macOS gate (`tmp/gate-14.txt`) | **GREEN** — EXIT=0, **20,420 passed**, 1,589 skipped, 10 xfailed |
| local gate ENOSPC / watcher trips / leaked procs | **0 / 0 / 0** |
| local gate whole-run disk consumption | **87 MB** (pre-fix: drained to ~20 GB free) |
| `ruff check psh tests tools` | All checks passed |
| `mypy` | 274 files, clean |

## Housekeeping

`READ-ME-DEV-1-4--INTEGRATOR-RULINGS.md` deleted from the worktree root; never committed
(`git status` clean apart from this ledger and the probe scripts, all under `tmp/`).

## Commit map — 17 commits on `fix/remediation-1-4`

| commit | what |
|---|---|
| `17c8f9f9` | test-side platform honesty (13 rows) |
| `1abe5a64` | 3 fd modules → typed runner |
| `603de516` | host decides `(core dumped)`; SIGQUIT budget |
| `8c390de3` `3fb896fa` `b911692f` `da851594` | nightly diagnostics: core_pattern, sampler, df fix, bounding |
| `6a1eab8e` `27a08a9f` | per-test → per-worker → open-fd attribution |
| `79d0a11c` | **fix: LC_ALL reset path is silent** (ruling #1) |
| `ff5b07b3` | **fix: bg refreshes state before SIGCONT** (ruling #2) |
| `164d34fa` | **fix(harness): kill reaches escaped process groups** (ruling #3(2)) |
| `59d3536e` | spawn-site budget for the new `ps` call |
| `ebe84c6a` | benchmark tier non-gating (§10) |
| `a768f497` | procsub sibling settle |
| `d3783922` | **bound the cap-disabled producer** (ruling #3(1)) |

---

# Part 10 — B1: the per-row classification table (verification blocker)

Part 2 asserted all 29 parallel-job rows were dispositioned but recorded the reasoning for only
about half; the rest lived solely in commit `17c8f9f9`'s message. The brief requires
classifications recorded IN THE LEDGER. Full table, one row per failure, union of census run
**30143337081** and baseline **30154694015**.

## Rows failing in BOTH runs (24)

| # | row | class | root cause | disposition |
|---|---|---|---|---|
| 1 | `test_child_sees_closed_fd_and_shell_survives` | (ii) | `/bin/sh` is dash on Linux; a bad-fd redirect exits **2**, not 1 | child = resolved bash oracle |
| 2 | `test_d2_closed_stdout_upstream_keeps_write_end` | (ii) | GNU cat says `standard output`, BSD says `stdout` | anchored one-line regex accepting both nouns |
| 3 | `test_exec_image_does_not_inherit_script_fd` | (ii) | dash rejects multi-digit fds ("Bad fd number") and ABORTS, so `echo AFTER` never ran | child = resolved bash oracle |
| 4 | `test_fg_subshell_sigquit_prints_quit` | (ii) | SIGQUIT of a forked **CPython** subshell dumps ~20 MB; runner pipes core_pattern through apport, which the kernel does not rate-limit by RLIMIT_CORE | budget 12s → 60s (hang-catcher, not a timing pin) |
| 5 | `test_golden[redirect_eval_external_stderr_suppressed]` | (ii) | GNU `ls` exits **2** on a missing operand, BSD exits 1 | golden case uses `cat` (1 on both) |
| 6 | `test_golden[subshell_trap_modification_drops_inherited_keeps_ignored]` | (ii) | `trap` lists in signal-NUMBER order; SIGUSR2 is 31 on macOS, 12 on Linux — either side of SIGTERM's 15 | golden case uses SIGHUP (1 everywhere) |
| 7-12 | `test_history_outcome_matches_bash` ×6 (`bang_string`, `identical_expand`, `normal_expand`, `print_only_recorded_not_executed`, `set_minus_H_reenables`, `word_star`) | (iv) | the ONLY interactively-run oracle read the host's `~/.bashrc`; Ubuntu's default sets `HISTCONTROL=ignoreboth`, whose `ignoredups` drops the second identical entry. `hermetic_shell_env()` strips `LC_*`/`LANG`/`DISPLAY`/`PWD` but keeps `HOME` | `--norc` on BOTH shells |
| 13 | `test_protocol_member_sets_are_frozen` | (iv) | `typing.get_protocol_members` is 3.13+; `requires-python` is >=3.12 and CI runs 3.12, so the freeze died with `AttributeError` instead of guarding | fall back to `typing._get_protocol_attrs` (same sets, verified) |
| 14 | `test_self_dup_closed_stays_closed_for_child` | (ii) | as #1 (dash exit 2) | child = resolved bash oracle |
| 15 | `TestAbnormalTerminationDiagnostic.test_diagnostic_names_the_signal` | (ii) | Linux dumps core (RLIMIT_CORE unlimited), so psh CORRECTLY appends `" (core dumped)"` from `WCOREDUMP`, like bash | expectation built from the kernel's own rule (`core_dump_env.py`) |
| 16 | `TestCompositeQuoting.test_tilde_expands_in_key` | **(iii)** | tilde-in-assoc-subscript arrived in **bash 5.2.24**; runner bash is 5.2.21. Bisected on ONE Linux box: 5.2.22 `~`, 5.2.23 `~`, 5.2.24 `/probe-home`, 5.2.25 `/probe-home` | version gate naming the change; fails CLOSED |
| 17 | `TestCwdReadConvergence.test_pushd_swap_after_plain_cd_uses_real_cwd` | (ii) | `/private` is macOS-only | third directory is `/usr` |
| 18 | `TestExitTrapOnFatalSignal.test_stdin_mode_fires_exit_trap` | (iv) | `communicate()` flushes `proc.stdin` whenever set; flushing an already-closed pipe raises `ValueError` on **3.12** but not on newer CPython | drop the handle (`proc.stdin = None`) after closing |
| 19 | `TestInheritedCtypeProvenance.test_terminal_app_utf8_row` | **(v)** | psh warned on bash's SILENT LC_ALL reset path | **ruling #1 production fix** (`79d0a11c`); row passes UNMODIFIED both platforms |
| 20-21 | `TestInheritedTrapNotFired.test_parent_trap_reset[brace]`, `[subshell]` | (ii) | SIGUSR1 is 30 on macOS, **10** on Linux; the row hard-coded exit 158 | compute `128 + int(signal.SIGUSR1)` |
| 22 | `TestNamedFdStillWorks.test_named_output_fd_child_inherits` | (ii) | `{v}` allocates fd 10; dash rejects multi-digit fds at parse time | child = resolved bash oracle (sibling row keeps `sh`: fd 3 is POSIX-portable) |
| 23 | `TestPipelineLastMemberSignalDeath.test_non_sigterm_names_the_signal` | (ii) | as #15 | as #15 |
| 24 | `TestTrapListingInheritance.test_first_modification_drops_inherited_but_not_ignored` | (ii) | as #6 (signal-number ordering) | expected lines ordered from the LIVE signal numbers |

## Rows failing ONLY in the census run 30143337081 (2)

| # | row | class | disposition |
|---|---|---|---|
| 25 | `test_argument_less_builtin_has_no_trailing_space_script` | (iv) | **UNEXPLAINED.** One bare `StopIteration`, never recurred (absent from baseline and all later runs); psh matches bash locally. Now reports the whole listing on failure so a recurrence arrives with evidence. Carried. |
| 26 | `TestBackgroundScopesWholeList.test_andor_list_of_groups_backgrounds_whole_list` | (iv) | budget raced interpreter startup (failed at 0.301s vs 0.300s). Sleep 1.0s, budget **0.6s** — deliberately different numbers, so the budget is not racing the sleep it measures |

## Rows failing ONLY in the baseline run 30154694015 (3)

| # | row | class | disposition |
|---|---|---|---|
| 27 | `test_subprocess_runs_this_worktrees_psh` | (iv) | the negative leg cannot discriminate when the editable install targets the tree under test — exactly CI's shape. Skip the NEGATIVE LEG ONLY; the positive leg still runs everywhere |
| 28 | `TestProcessSubRepeatedUse.test_no_zombie_accumulation_across_loop` | (iv) | sampled `ps` the instant the loop ended, racing psh's by-design WNOHANG reap at scope exits (bash never blocks on a substitution child either) | settle before probing |
| 29 | `TestPtyJobControl.test_bg_resumes_stopped_job_to_running` | **(v)** | `bg` gated on an unrefreshed state, so SIGCONT was never sent | **ruling #2 production fix** (`ff5b07b3`) |

## Surfaced later (1)

| # | row | class | disposition |
|---|---|---|---|
| 30 | `TestProcessSubReaping.test_no_zombie_accumulation_across_commands` | (iv) | sibling of #28 making the identical assumption; only reachable once earlier failures stopped masking it | settle before probing (`a768f497`) |

## PTY tab-completion rows — VERDICT (CORRECTED; my first verdict was WRONG)

**Correct verdict:** pre-existing **XFAIL** rows — a documented psh limitation (path-only
completion) — present as XFAIL in the census run, the baseline run, AND both green runs. They are
NOT failures, they were NOT cleared by Wave 1, and this slot took NO action on them.

Evidence, from my own census files:

```
XFAIL tests/system/interactive/test_pty_smoke.py::TestPtyPortedLegacy::test_tab_completes_command_name
  - psh tab completion is path-only (CompletionEngine completes filenames; bash also
    completes command names from PATH/builtins)
XFAIL tests/system/interactive/test_pty_smoke.py::TestPtyPortedLegacy::test_tab_completes_variable_name
  - psh tab completion is path-only (CompletionEngine completes filenames; bash also
    completes $VAR variable names)
```

Present in all four logs (`clean-30143337081.txt`, `baseline-clean.txt`, `v11-clean.txt`,
`v13-clean.txt`), 2 rows each. The markers are `@pytest.mark.xfail(strict=True, ...)` at
`test_pty_smoke.py:834` and `:842` — **strict**, so an unexpected PASS would FAIL the suite. That
matters: this is an ACTIVE pin on a known gap, not a quarantine, which is why no action is owed.

### What I originally wrote, and why it was wrong

I claimed: *"class (i), cleared by Wave 1, absent from every run I censused — the only
`tab_completion` strings are coverage lines"*, and I presented it as **"checked rather than
assumed"**.

The check itself was broken. I grepped **`tab_completion`** — the MODULE PATH
(`psh/interactive/tab_completion.py`, which appears only in coverage tables). The TEST NAMES are
**`tab_completes`**. Every hit I saw was a coverage row, so I concluded absence and reported that
absence as a verified fact.

### LESSON — a "checked" claim whose CHECK was wrong

This is a near-miss of precisely the class this campaign exists to hunt, and it is worse than an
unchecked claim, because saying "checked rather than assumed" *borrowed credibility* the evidence
did not support. An auditor reading it had every reason to stop there.

Rules taken from it:

1. **Enumeration/absence claims must grep the TEST NAMES, not the module path** — and ideally
   both, since the two differ by exactly the kind of near-miss (`tab_completion` vs
   `tab_completes`) that a human eye slides over.
2. **A null result deserves more scepticism than a positive one.** Finding nothing is the
   expected output of a broken pattern; a positive hit at least proves the pattern matches
   something. Before reporting absence, confirm the pattern matches a KNOWN-present instance.
3. **Never label a claim "checked" without stating what the check WAS.** Had I written "grep for
   `tab_completion` finds only coverage lines", the wrong pattern would have been visible on the
   face of the claim and caught in review instead of by the verifier.

Caught by the integrator's verifier, not by me. Recorded in full because the near-miss is more
instructive than the fact.

## Class tally (deduplicated, whole slot)

- **(i)** cleared by Wave 1, verified by measurement: **46 conformance rows**. (The PTY
  tab-completion family was wrongly counted here in the first draft — it is not class (i) and not
  a failure at all: two pre-existing `strict=True` XFAIL rows for a documented path-only
  completion limitation, unchanged by this slot. See the corrected verdict above.)
- **(ii)** Linux platform behaviour: 13 rows (#1-6, 14, 15, 17, 20-24)
- **(iii)** bash-oracle version: 1 row (#16)
- **(iv)** test/environment defect: 13 rows (#7-13, 18, 25-28, 30)
- **(v)** psh production defect: 2 rows (#19, #29) — both ruled on, both fixed, both
  mutation-verified

# Part 11 — F8 truth-ups

**(a) Commit-map arithmetic.** Parts 6 and 9 said "17 commits" while listing 16 SHAs. The missing
one is **`9ec9ab1c`** (per-worker disk attribution). `git log --oneline 21d6c5b4..HEAD | wc -l`
= 17 at that point; the final branch is 18 with the fix-round commit.

**(b) Part 5 undercounted the `yes` sites.** It said "the only `yes` invocations in the tree" and
listed **3**; there are **5** real spawning sites, all in
`tests/unit/tooling/test_shell_oracle_harness.py`:

1. `test_timeout_threads_truncation_provenance` — the cap-DISABLED row (now bounded)
2. `test_output_cap_is_structural_not_advisory` — `yes runaway`
3. `test_output_cap_kills_whole_process_group` — `sleep 30 & …; yes runaway`
4. **`test_output_limit_records_termination_provenance` — `yes runaway >&2`** (the stderr-breach
   row Part 5 omitted entirely)
5. `test_yes_discriminator_is_test_error_not_identical` — `compare_behavior("yes")`, **the actual
   leaker**

(A sixth, `test_two_output_limit_runs_never_classify_identical`, constructs a synthetic
`OutputLimitExceeded` and spawns nothing.) The omission did not change the conclusion — #5 is the
leaker and was identified by bisection, not by enumeration — but the enumeration was presented as
exhaustive and was not.

**(c) FLIP-PINS: the 1.2-loudness interaction question, ruled out explicitly.** The brief asked
whether `test_history_outcomes_i4.py` rows on Linux interact with slot 1.2's loudness change. They
do **not**, and the `--norc` fix is what settles it: the six failures were bash recording ONE
entry where psh recorded TWO, caused entirely by the host `~/.bashrc`'s
`HISTCONTROL=ignoreboth`. Proof it is not a loudness effect: with `HOME` pointed at a directory
holding Ubuntu's skel `.bashrc`, bash 5.2.21 reproduces the CI output exactly, and with `--norc`
bash 5.2.21, bash 5.2.26 and psh all produce the SAME three entries. No psh diagnostic or
loudness path is involved on either side of the comparison — the divergence was entirely in what
bash recorded.

# Part 12 — carries, restated complete after the fix round

**CARRY 1 — locale: the divergences this slot did NOT fix.** Ruling #1 scoped the change to the
LC_ALL reset path, so everything below is still live. Evidence is the Part 6 trigger matrix
(bash 5.2.26 macOS and 5.2.21 Linux, identical row for row). psh vs bash, all with a locale name
invalid on both platforms:

| trigger | bash | psh | direction |
|---|---|---|---|
| `LANG=<bad>` (assignment) | silent | **warns** | psh noisier |
| `LANG=<bad>` with categories unset | silent | **warns** | psh noisier |
| `LANG=<bad>` as a temp-env prefix | silent | **warns** | psh noisier |
| startup `LC_COLLATE=<bad>` | silent | **warns** | psh noisier |
| startup `LANG=<bad>` | silent | **warns** | psh noisier |
| `unset LC_CTYPE` whose own value was bogus | **warns** (names an empty locale, `()`) | silent | psh QUIETER |
| `LC_ALL=<bad>` / startup `LC_ALL=<bad>` | 1 line naming LC_ALL | **2 lines**, one per category | shape |

Six behavioural rows plus the warn-SHAPE row. Note the last behavioural row runs the OTHER way —
psh is too quiet there — so a future fix cannot be a blanket silencing pass. The
`test_locale_warn_trigger_conformance.py` docstring now scopes its "the discriminator is the
TRIGGER" claim to the LC_ALL/LC_CTYPE/LC_COLLATE columns actually probed, and points here.

**CARRY 2 — `bg` on a genuinely RUNNING job** silently returns 0 where bash prints
`bg: job N already in background`. Pre-existing; ruling #2 scoped it out.

**CARRY 3 — benchmark thresholds** want MEASURED runner baselines, not dev-machine constants:
`test_simple_command_performance` and `test_complex_structure_performance` (`0.0124 < 0.01`) and
`test_tokenization_scaling` (2 ms budget) — ~24% over on shared CI, all passing locally. The tier
is `continue-on-error` so this is reporting-only debt, but it is debt. For Checkpoint R /
Ceremony C.

**CARRY 4 — nightly instrumentation EXPIRY.** The core_pattern normalisation, disk sampler,
open-fd snapshots and `PSH_DISK_WATCH` are relapse watch for the escaped-writer bug, not
permanent furniture. Removal criterion, now recorded in the workflow itself: once several
consecutive SCHEDULED nightlies are green with zero ENOSPC and no sampler trip, delete the block.
Nothing in it is load-bearing — the fix is pinned by
`test_cap_kill_reaches_a_writer_that_left_the_process_group`.

**CARRY 5 — second-sweep blindness.** `_killpg_sigkill`'s descendant enumeration is now OPT-IN and
passed only at the two breach sites that kill a LIVE leader. The post-`wait` re-sweeps and the
normal-completion sweep deliberately do NOT enumerate: after the leader is reaped its children are
reparented to init, so the pid/ppid walk returns nothing anyway, and running it there would also
cost a `ps` per case and widen the pid-reuse blast radius. A straggler that forks into the session
*during* the first kill is therefore still only covered by the group kill.

**CARRY 6 — `test_argument_less_builtin_has_no_trailing_space_script`**: one unexplained
`StopIteration` in run 30143337081, never reproduced. Now reports the listing on failure.

**CARRY 7 — bg PTY manifestation unpinned** (integrator-sanctioned): the deterministic pin uses
the `set -m` + external-`kill` construction from ruling #2; the original load-dependent PTY
manifestation stays covered only by the pre-existing `test_pty_smoke` row.

**LESSON 1 (banked).** When a fix rests on a diagnosed wrong assumption, sweep the module for
SIBLINGS making the same assumption BEFORE declaring done — I fixed one procsub row, skipped its
neighbour, and the neighbour cost a full 25-minute cycle to rediscover after I had already written
the diagnosis that predicted it.

**LESSON 2 (banked) — a "checked" claim whose CHECK was wrong.** My PTY tab-completion verdict
was reported as "checked rather than assumed" and was false: I grepped the MODULE PATH
(`tab_completion`) where the TEST NAMES read `tab_completes`, saw only coverage lines, and
declared absence. The rows were there all along as `strict=True` XFAILs. Three rules, in Part 10:
grep test NAMES not module paths (ideally both); treat a NULL result with more scepticism than a
positive one, since finding nothing is exactly what a broken pattern produces; and never label a
claim "checked" without stating what the check WAS — naming the pattern would have exposed it on
the face of the claim. This is the campaign's own target class committed by its own dev, and the
verifier caught it, not me.

**PRE-RULED UPGRADE (approved, not owed now).** If either procsub row ever flakes on a scheduled
nightly, replace the fixed `sleep 0.2` with a bounded reap-poll: short sleeps iterated, each
supplying the scope exit that triggers the WNOHANG reap, until zero zombies or a generous
deadline. A fixed constant is still a timing number racing a load-dependent reap — the same
criticism this ledger levels at the benchmark thresholds.

---

# Part 13 — fix round: exit proof at tip `cdff0704`

## Run 30175067149 — conclusion **SUCCESS** (third consecutive green)

https://github.com/philipwilson/psh/actions/runs/30175067149

| job | conclusion |
|---|---|
| Full Conformance Suite | **success** — 2,671 passed |
| Full Parallel Suite + Bash Golden Comparison | **success** — 21,873 passed, 0 failed |

Golden phase 1,481 passed. **Real ENOSPC: 0.** Benchmark tier reports 3 rows, non-gating by
design (carry 3).

## F1 measured effect (the verification catch)

`_killpg_sigkill` gained `sweep_descendants` (default False), passed ONLY at the two breach sites
that kill a live leader:

| site | leader state | enumerates? |
|---|---|---|
| cap breach | LIVE | yes |
| timeout, first kill | LIVE | yes |
| timeout re-sweep (post-`wait`) | reaped | no |
| cap re-sweep (post-`wait`) | reaped | no |
| normal completion | reaped | no |

40 warm oracle cases: **58.5 ms/case** (verifier measured base 62 ms, swept 82-86 ms) — the
+33-39% regression is gone. Escaped-writer pin green, and still reds under mutation (drop
`sweep_descendants=True` from the cap site).

Three defects in one, all real: a provable no-op where the leader is already reaped (children
reparented to init, so the pid/ppid walk returns nothing), a per-case `ps` spawn multiplied
suite-wide, and a pid-reuse hazard — a recycled pid's tree would have been SIGKILLed. The last is
the one that mattered most and that I had underweighted.

## F6(a) verified in the run

The conformance job now reports the sampler it starts. From this run's log: 88 G free after,
**no open-fd snapshots** (no trips), and the ten lowest samples flat at ~91,361,880 kB with 40
`/tmp` entries. Previously that data was collected and discarded.

## Local gate at `cdff0704`

`EXIT=0`, **20,420 passed**, 1,589 skipped, 10 xfailed, **0 ENOSPC**, 0 leaked processes, 77 MB
whole-gate disk consumption (`tmp/gate-15.txt`). `ruff` clean; `mypy` clean (274 files).
Every touched module re-run together: **281 passed**.

## Green-run history

| run | tip | conformance | parallel |
|---|---|---|---|
| 30171120171 | `a768f497` | success | success |
| 30172534890 | `d3783922` | success | success |
| **30175067149** | **`cdff0704`** | **success** | **success** |
