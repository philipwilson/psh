# Test-Suite Performance Appraisal — 2026-07-07

Scope: **runtime of the test suite / release gate**, and concrete, measured
optimization options. This is a companion to
`tests_documentation_appraisal_2026-07-06.md` (which covers correctness/honesty
of the oracle layer). That appraisal's runtime-adjacent findings — C3 (the
default pytest gate excludes `tests/performance`; `run_tests.py --quick`
deselects almost nothing so it is not meaningfully quick) and C4 (runner
cleanup) — are taken as given here and revisited only through a runtime lens.

Measured on: main @ v0.662.0, host = 16 physical cores (16 logical), 128 GB RAM,
Python 3.14.2, pytest 9.0.2, pytest-xdist 3.8.0. All numbers below are either
mined from real gate transcripts (`tmp/last-test-run.txt`, `tmp/merged-gate.txt`,
`tmp/expnp1a-verify-gate.txt`, and their `*-comparebash.txt` siblings) or
measured directly with the probes listed in the Appendix. Nothing here is
estimated where a measurement was possible.

---

## Executive summary

The suite is **subprocess-bound, and its wall-clock is dominated by the one
phase that cannot use `-n auto`.** Two usual suspects — per-test fixture
construction and collection — were measured and are *not* bottlenecks
(`Shell()` costs 0.36 ms; collecting all 14,860 items costs 2.15 s). The cost
lives almost entirely in spawning `python -m psh` (and, in the compare-bash
phase, `bash`) subprocesses, of which there are thousands.

Measured single-tenant breakdown of the documented release gate
(`python run_tests.py --parallel`):

| Phase | Tests | Wall-clock (measured) | % of gate | Parallelism |
|---|---:|---:|---:|---|
| Phase 1 — regular (`-n auto`, `-m "not serial"`) | ~11,900 | **59–75 s** | ~24% | 16 xdist workers |
| Phase 1b — **serial** (`-m serial`, no xdist) | ~1,014 | **210–241 s** | **~73%** | **none (1 process)** |
| Phase 2 — subshells (`-s`) | 77 | 5.5–6.2 s | ~2% | serial |
| **Default gate total** | ~13,000 | **~283–298 s (≈5 min)** | 100% | |
| Phase 3 — `--compare-bash` (opt-in) | ~2,025 | **220–229 s** | (+75%) | none (1 process) |
| **Gate + compare-bash** | | **~505–525 s (≈8.5 min)** | | |

**The single biggest time sink is Phase 1b, the serial phase: ~73% of the
default gate wall-clock while holding only ~7% of the tests.** It runs
single-threaded because its tests manipulate the runner's file descriptors or
deliver signals, both of which corrupt xdist workers. When `--compare-bash` is
enabled it adds a co-equal ~220 s that re-spawns work Phase 1 already ran.

### On the "~19 min / ~1150 s" figure — resolved: it was a stale baseline, never a real measurement of this gate

**The gate was never ~19 min on this machine.** The three release-ceremony gates
actually run this session — all `python run_tests.py --parallel`, each captured
as a harness background task with a recorded start/end — clock in at ~290 s:

| Release | Wall-clock window | Duration |
|---|---|---:|
| v0.661.0 | 20:46:40 → 20:51:33 | 4 m 53 s (293 s) |
| v0.662.0 | 23:05:55 → 23:10:44 | 4 m 49 s (289 s) |
| v0.663.0 | 23:44:41 → 23:49:31 | 4 m 50 s (290 s) |

These match my measured **283–298 s** exactly. Notably, they ran *during*
moderately-active multi-agent waves and were still ~290 s — so even contention
did not push this gate anywhere near 19 min. The command was confirmed
`python run_tests.py --parallel`, observed directly in the process table during
the v0.663.0 release (pid 62898:
`... && python run_tests.py --parallel > tmp/gate-release-0663.txt`) — *not*
serial mode, *not* `--coverage`, and *not* `--compare-bash` (that phase is
measured separately at 2,189 / 223 s, matching my ~220–229 s).

The "~19 min / 1149 s" figure was therefore a **stale prior-session baseline,
carried forward through a context compaction and never re-measured**; its
original command is unverifiable and was not worth ~20 min of machine time to
chase. The serial-mode and hidden-coverage hypotheses are both refuted.

**The headline: the gate was not slow — the perceived slowness was an unexamined
assumption.** The per-phase attribution and optimization targets below stand
unchanged (they make the ~290 s faster still). Heavy machine contention *can*
inflate any wall-clock and remains worth avoiding — do not run a 16-worker gate
alongside other heavy work on a 16-core box — but it was not the cause here.

---

## Where the time actually goes

### Fixture and collection cost are NOT the problem (measured, ruled out)

- `Shell()` construction: **0.36 ms/instance**; `Shell.close()`: ~0 ms
  (`tmp/measure_shell_cost.py`, N=200). Even if every one of the 14,176 items
  built its own shell, that is **5.1 s total** across the whole suite. The
  function-scoped `shell`/`captured_shell`/`isolated_shell_with_temp_dir`
  fixtures are cheap; moving them to module/session scope would save a
  negligible amount and cost real isolation. **Do not chase fixture scope.**
- Full-suite collection (`--collect-only -q`): **2.15 s** for 14,860 items. Not
  a bottleneck; no collection speedup is worth pursuing.

### The subprocess tax (this IS the problem)

| Operation | Measured cold cost |
|---|---:|
| `python -m psh -c :` (interpreter + full psh import) | **~85 ms** |
| bare `python -c pass` (interpreter only) | ~20 ms |
| `bash -c :` | ~5 ms |
| in-process unit test (avg, `captured_shell`) | **~2.3 ms** |
| subprocess golden test (avg, spawns psh) | **~146 ms** |

An in-process test is roughly **60× cheaper** than the same behavior exercised
through a `python -m psh` subprocess. Static scan of `tests/`:

- **413** `subprocess.run(` sites, **16** `Popen(`, **384** `sys.executable`
  references. Many are parametrized, so the runtime spawn *count* is far higher
  than the site count — e.g. the single parametrized `test_golden` spawns
  **~1,106** psh processes in Phase 1, and the golden suite runs **twice** in a
  full gate (psh-only in Phase 1, then psh+bash in the compare-bash phase).

Because psh import is ~65 ms of the ~85 ms cold start (bare Python is ~20 ms),
**every subprocess test pays a fixed ~85 ms tax before doing any work.** This is
why the serial and compare-bash phases, which are serial *and* subprocess-heavy,
dominate.

---

## Hot files and tests (ranked, measured)

### Phase 1b serial phase — 217.9 s clean run (1014 passed, 2 xfailed, 0 failed)

(The 29 "failures" visible in `tmp/last-test-run.txt` are the known
`&`-launch SIGINT gotcha, not real; a foreground solo run is all-green.)

Aggregate wall-clock by file (from `--durations`, top contributors):

| File | ~Aggregate | Why slow |
|---|---:|---|
| `integration/job_control/test_exit_trap_paths.py` | **~57 s** | Each test runs a script containing `sleep 3` and signals it after `delay=1.0`; the orphaned `sleep 3` child holds the stdout pipe so `communicate()` blocks ~3 s; comparison tests run **psh and bash** → ~6 s each. 4 tests measure **6.2 s**, ~11 measure **3.1 s**. |
| `system/interactive/test_pty_smoke.py` | **~40–45 s** | 82 pexpect PTY tests; each spawns a real PTY psh and drives it interactively (0.5–4.2 s each). Inherently serial. |
| `integration/redirection/test_process_sub_cleanup.py` | ~12–15 s | Forks, creates FIFOs, waits to reap children (5.4 s top test). |
| `integration/job_control/test_bg_child_trap_discipline.py` | ~6–10 s | bg subshell signal-disposition tests, ~2 s each. |
| `integration/redirection/test_process_sub_embedded.py` | ~5 s | process-sub path forms (5.1 s top test). |

The only tests exceeding **5 s** in the entire suite are here: four
`test_exit_trap_paths` tests at ~6.2 s and two `test_process_sub_cleanup`/
`_embedded` tests at ~5.1–5.4 s. Everything else is < 2.4 s.

**Serial-bucket composition** (`-m serial` = 1,016 items, ~7% of suite):

| Category | Items | Can it ever parallelize? |
|---|---:|---|
| `integration/*` (mostly `redirection/` ~350 + `job_control/` ~250) | 733 | redirection: **partly** (see below); job_control: no (signals) |
| `conformance/*` (trap-signal + builtin-state) | 113 | no (delivers signals) |
| `unit/*` (`test_signal_builtins` 43, `test_disown` 22, …) | 87 | no (signals) |
| `system/*` (`test_pty_smoke` 82) | 83 | no (PTY, terminal-driven) |

### Phase 1 subprocess hot tests (parallel, so amortized — lower priority)

Slowest individual calls (2.0–2.4 s): conformance tests that spawn several
bash+psh pairs — `test_regex_posix_classes` (~1.4 s ×4), `test_locale_conformance`
POSIX-class membership (~0.5 s ×many), `test_test_file_operators_conformance`
(2.37 s), and golden `read -t` timeout cases (~1.1 s ×3, real timers). These are
distributed across 16 workers so they cost little wall-clock; they matter only if
Phase 1 becomes the critical path after the serial phase shrinks.

### Compare-bash phase — 220–229 s, ~2,025 cases

Entirely serial psh+bash subprocess startup. Each case spawns psh (~85 ms) +
bash (~5 ms); at ~100 ms/case × ~2,025 ≈ ~205 s, i.e. **the phase is ~90%
process-startup, ~0% real computation.** It also **duplicates** Phase 1: the
`test_golden` cases already ran (psh-only) in Phase 1, and the compare-bash phase
re-runs them *and* their `test_golden_bash_comparison` twins.

---

## Optimization opportunities

Ranked by (estimated wall-clock saved on the default gate) ÷ (effort × risk).
"Safe" = no coverage or clarity loss. "Trade-off" = buys speed at some cost the
project (an educational shell) may not want to pay.

| # | Opportunity | Est. saving | Effort | Risk | What could break / cost |
|---|---|---:|---|---|---|
| **1** | **Shrink `test_exit_trap_paths.py` waits**: `sleep 3`→`sleep 0.5`, `delay=1.0`→`~0.3`, and/or close the pipe so the orphaned sleep doesn't hold `communicate()`. | **~40–50 s** (serial phase 218→~170 s) | S (1 file) | **Med** | Signal must still land while the shell is in `sleep`; too-short delays race and flake. Needs re-validation and possibly `communicate(timeout=)` tightening. High value/effort. |
| **2** | **Split the serial bucket into a parallelizable sub-pool.** Only in-process-fd and signal tests truly can't use xdist. 23/28 `redirection/` files **already spawn subprocesses** (fd-safe) yet the whole dir is blanket-marked serial by path prefix. Mark serial per-test (only the genuinely in-process-fd forking tests) and let the rest join Phase 1. | **~40–70 s** (moves ~150–300 tests from serial into 16-way parallel) | M | Med | Re-introduces the exact flakiness the blanket rule suppressed ("each file passes alone, the dir flakes") if the audit misclassifies one test. Must re-run under xdist repeatedly to confirm. |
| **3** | **De-duplicate the golden suite in the compare-bash phase.** `test_golden` (psh-only) already runs in Phase 1; the compare-bash phase re-runs it. Run only `test_golden_bash_comparison` there (`-k comparison`), or drive both psh and bash from one parametrized test in Phase 1. | **~80–100 s** on the `--compare-bash` gate | S–M | Low | Loses nothing: Phase 1 already asserts psh output; the comparison test is the only new work. Straightforward. |
| **4** | **Parallelize the compare-bash phase.** It is pure independent subprocess spawns with no shared fd/signal state → xdist-safe. Run it `-n auto`. | **~180–200 s** on the `--compare-bash` gate (229→~30–50 s) | S | Low | Each case is isolated (`LC_ALL=C`, own subprocess); no reason it can't parallelize. Biggest single win *when compare-bash is in the gate*. |
| **5** | **A genuine `--quick` smoke tier.** Today `--quick` only adds `-m "not slow"` and `slow` is nearly unused, so it ≈ full run. Define a real tier: unit + a thin integration/conformance smoke, in-process only, `-m "not serial"`, no subshell/compare-bash. Target < 30 s. | Dev-loop only (not gate) | S–M | Low | Must curate the smoke set so it stays meaningful; risk is a smoke tier that misses regressions → false confidence. Pair with a `smoke` marker. Aligns with doc-appraisal C3. |
| **6** | **Reduce compare-bash re-runs**: the phase re-verifies psh-vs-bash on every gate though the golden cases rarely change. Sample (e.g. run the full set nightly, a fixed 25% subset per local gate) or content-hash the yaml to skip when unchanged. | ~150–200 s on `--compare-bash` gate | M | Med | Sampling weakens the per-commit guarantee; only acceptable if the nightly runs the full set. #4 (parallelize) is lower-risk and preferred. |
| **7** | **Cache psh import** for subprocess tests via a persistent `python -m psh` server / `-X importtime` pruning, or reduce psh import cost. ~65 ms of the ~85 ms start is import. | broad but small each | L | Med | A test server changes process semantics (the thing many of these tests verify); import pruning risks lazy-import bugs. Poor value vs. #1–#4. |
| **8** | **Tune xdist workers.** `-n auto` = 16 on this box; Phase 1 is 59–75 s and already core-saturated, so more workers won't help and `-n` is *not* the lever. The lever is that Phase 1b uses `-n 1`. | ~0 | — | — | Confirms the serial phase, not worker count, is the constraint. |

### What must NOT be converted (subprocess-by-design — cite CLAUDE.md)

Per CLAUDE.md "Parallel-safety rules" and "Known Test Issues", these are
subprocess/serial **by necessity** and converting them to in-process would
either corrupt the xdist worker channel or lose the coverage they exist for:

- **Permanent-fd tests** (`exec >file`, `exec 3>&1`, fd open/close/dup that
  outlives one command) — in-process they rewrite the runner's fds, which under
  xdist are the execnet channel. Keep as subprocess.
- **Process/signal/job-control tests** (`job_control`, `test_disown`,
  `test_signal_builtins`, `test_trap_signal_spec_conformance`, `test_pty`) — send
  signals / wait on processes; must stay serial.
- **In-process forked-fd tests** (`test_read_forked_fd`, here-string reads) —
  they *deliberately* exercise the in-process fd path (educational value: proving
  psh saves/restores fds correctly). Do not subprocess them away.

Opportunity #2 respects this: it moves only the *already-subprocess* redirection
tests out of the serial bucket, leaving the genuinely-in-process ones behind.

---

## Phased campaign plan (quick wins first)

**Phase A — safe, high-value (no coverage/clarity loss). Target: default gate
~298→~250 s; compare-bash gate ~525→~250 s.**
1. #4 Parallelize the compare-bash phase (`-n auto`) — biggest single win when
   compare-bash is enabled, lowest risk. (~ -180 s on that gate.)
2. #3 De-duplicate golden in the compare-bash phase (`-k comparison`). (~ -90 s.)
3. #1 Shrink `test_exit_trap_paths.py` waits, with re-validation for signal-race
   robustness. (~ -40 s on the always-run serial phase — compounds every gate.)

**Phase B — medium effort, needs xdist re-validation. Target: serial phase
~170→~110 s.**
4. #2 Convert the serial-bucket path-prefix marker to a per-test marker; move the
   ~23 already-subprocess redirection files into Phase 1. Re-run the parallel
   phase ≥10× to confirm no flakiness returns before landing.

**Phase C — developer experience (not the gate).**
5. #5 Build a real `--quick`/`smoke` tier (< 30 s, in-process) and document it as
   the "quick" gate alongside "standard" (default `--parallel`) and "full"
   (`--parallel --compare-bash`), closing doc-appraisal C3.

**Phase D — orchestration (a real lever, outside the test code).**
6. Keep serializing gate invocations during multi-agent release waves: a
   16-worker gate saturates the 16-core box, so concurrent gates would multiply
   wall-clock. The team already practices a machine-wide gate slot, and the
   measured ceremonies stayed at ~290 s even mid-wave because of it — worth
   preserving. (This is a floor-protection lever, not a speedup: the ~1150 s
   figure that motivated this appraisal turned out to be a stale baseline, not a
   contended run — see the resolution above.)

Expected end state: default gate ~5 min → **~4 min**; compare-bash gate ~8.5 min
→ **~4–4.5 min**; and a genuine < 30 s dev smoke loop. The serial phase remains
the floor (signal/PTY tests have irreducible real-time waits), so ~110–170 s of
serial work is the realistic asymptote without deeper redesign.

---

## Appendix — probes and raw numbers

Host / startup:
```
sysctl hw.ncpu=16 hw.physicalcpu=16 hw.memsize=128GB
python -m psh -c ':'   → real 0.08–0.09 s (×5)
python -c pass         → real 0.02 s
bash -c ':'            → real 0.00 s
```
Fixture / collection:
```
tmp/measure_shell_cost.py → Shell() 0.36 ms, close() ~0 ms (N=200)
pytest --collect-only -q  → real 2.15 s, 14,860 items
```
Phase timings (transcripts + solo probes):
```
Phase 1  (-n auto, not serial): 59.18 / 73.70 / 74.84 s   [3 transcripts]
Phase 1b (-m serial, no xdist): 217.92 s solo (1014 passed, 2 xfailed, 0 failed)
                                210.84 / 227.88 / 241.37 s [3 transcripts]
Phase 2  (subshells -s):        5.56 / 6.02 / 6.20 s
Phase 3  (--compare-bash):      228.73 / 221.70 s  (~2025 passed)
```
Contrast subsets (`-n 6`, this appraisal):
```
system+behavioral+conformance -m "not serial": 2885 passed in 69.68 s; slowest 2.37 s
unit/lexer+parser+expansion (in-process):       4204 passed in  9.62 s; ~2.3 ms/test
tests/behavioral (psh subprocess, no compare):  1106 passed in 26.91 s; ~146 ms/test
```
Static scan (`tests/`): 413 `subprocess.run(`, 16 `Popen(`, 384 `sys.executable`;
redirection dir = 28 files, 23 already spawn subprocess; serial bucket = 1,016
items (integration 733 / conformance 113 / unit 87 / system 83).
```
```
Reproduce the serial-phase profile (run SOLO — no other gate; delivers signals):
  python -m pytest tests/ --ignore=tests/integration/subshells/ -m serial \
    -p no:cacheprovider --durations=40
```
