# Testing Source of Truth

This document defines the canonical test commands for PSH. It is the
authoritative reference; other docs should point here rather than restate
commands.

## The gate is local

GitHub's per-PR test workflow (`tests.yml`) is intentionally **disabled**.
The release gate is therefore **local**: a change is ready to merge when the
full suite, the linter, and the type checker all pass on your machine.

```bash
python run_tests.py --parallel    # full suite (pytest-xdist; ~4x faster)
ruff check psh tests              # lint (production AND test trees)
mypy                              # type check (config + scope in pyproject.toml)
```

A nightly GitHub workflow (`nightly.yml`) re-runs the full suite plus bash
conformance and coverage on Linux as a safety net — but it is a backstop,
not the gate. (The local gate runs on macOS; see root `CLAUDE.md` for the
known platform-divergent code paths the nightly is responsible for.)

## Validation tiers and the CI contract

Four tiers, used at different moments. They are named consistently here, in
`run_tests.py`, and in the README:

| Tier | Command | Scope | When |
| --- | --- | --- | --- |
| **quick** | `python run_tests.py --quick` | Curated smoke subset (unit tree + fast integration areas), parallel, ~20s | Tight local iteration |
| **standard** (the gate) | `python run_tests.py --parallel` | Whole suite in two phases: Phase 1 (xdist, `-m "not serial and not benchmark"`) then Phase 1b (serial-marked tests, no xdist). There is no separate subshell phase — subshell tests are ordinary Phase-1 tests. | Before every merge, locally |
| **benchmark** | `python run_tests.py --benchmarks` | `benchmark`-marked CPU/wall-time microbenchmarks (`tests/performance/`), serial | Explicit runs; intended nightly addition |
| **full** (nightly backstop) | `nightly.yml` | Standard **plus** live bash conformance, coverage, on Linux | Nightly on `main` |

What runs where, stated plainly so the truth surface is honest:

- **Per-PR CI does not run.** GitHub's `tests.yml` is intentionally disabled
  (`state: disabled_manually`). There is no automated per-PR gate; the standard
  tier run on the author's machine **is** the gate.
- **Nightly** (`nightly.yml`) runs the full tier on Linux as a backstop, not a
  precondition for merge. The benchmark tier is *intended* to be added to the
  nightly (`python run_tests.py --benchmarks` as an extra step); until that is
  wired, benchmarks run only when invoked explicitly.
- **Release** uses the same standard tier plus the version/stat sync checks in
  `tests/unit/tooling/` (README statistics, doc pointers, version sync), and
  writes the release attestation (see below).

The quick tier is for signal during development only — it deliberately omits
the serial/subprocess-heavy areas and the benchmark tier, so a green quick
run is **not** sufficient to merge.

### The performance tree and the `benchmark` marker

`tests/performance/` is ordinary collected content (the old global
`--ignore=tests/performance` in `pytest.ini` is gone). Its tests are
classified honestly:

- **Timing microbenchmarks** (millisecond/second thresholds over CPU or wall
  time) carry `benchmark` **and** `serial` markers. Every standard-gate phase
  excludes `benchmark`, so removing the ignore did not import timing
  thresholds into the xdist phase; the `serial` marker additionally keeps them
  out of any manual `pytest -n auto -m "not serial"` run. They run in the
  benchmark tier: `python run_tests.py --benchmarks`.
- **Deterministic invariants** (large-input robustness; no timing) are
  unmarked and run in the standard gate. The primary complexity guarantees
  (state/transition-count guards, e.g.
  `tests/unit/expansion/test_pattern_engine_matcher.py`) also live in the
  standard gate; the timing benchmarks are a coarse backstop, not the
  guarantee.

### Structured phase evidence (manifests)

Every `run_tests.py` phase loads `tools/pytest_phase_manifest.py` (via `-p`)
and writes a JSON manifest (`tmp/phase-manifests/phase-N.json`): collected
node ids in execution order plus counts for
passed/failed/errored/skipped/xfailed/xpassed/deselected. A phase passes only
when pytest exits 0 **and** its manifest is present, parseable, and
internally consistent. **No nonzero pytest exit is ever translated to
success** — the old xdist teardown-race carve-out is gone; if that race fires,
the gate is red and is rerun. The combined summary is computed from manifests
(never re-parsed transcript text) and deliberately excludes `deselected`.

`--shuffle-seed N` deterministically shuffles the collected items of every
phase (including the serial Phase 1b) via the same plugin; three seeded runs
with identical censuses are the campaign's Phase-E exit evidence.

### Release attestation (same-SHA tagging guard)

`python run_tests.py --parallel --write-attestation` — on a fully green run it
also runs `ruff check psh tests` and `mypy`, then writes
`gate_attestation.json` at the repo root (schema, version, gated commit/tree,
platform, per-phase counts, timestamps). Commit that file as the **final**
commit before pushing a release. `.github/workflows/release-tag.yml` runs
`tools/verify_gate_attestation.py` before tagging and fails loudly unless the
attestation exists, names the version being tagged, points at an ancestor
commit, and **nothing but the attestation changed since the gate ran**.

## Canonical commands

### 1) Full suite — THE gate (recommended)

```bash
python run_tests.py --parallel
```

What it does:
- Runs the whole suite under `pytest-xdist`, splitting it into a parallel
  phase (`-m "not serial"`) and a serial phase (`-m serial`, no `-n`) so
  that process/signal/job-control and permanent-fd tests run safely. A bare
  `pytest -n auto` would crash the run — always use the runner (or add
  `-m "not serial"` yourself).
- `python run_tests.py` (no `--parallel`) runs the same multi-phase flow
  serially; `--parallel 8` pins the worker count.

> Redirect output to a file so failures can be inspected without re-running:
> `python run_tests.py --parallel > tmp/test-results.txt 2>&1; tail -15 tmp/test-results.txt`

### 2) Quick tier — fast inner-loop smoke subset

```bash
python run_tests.py --quick    # curated smoke subset, parallel (~20s)
```

Runs the whole `tests/unit/` tree plus the fast, in-process integration areas
(control flow, parameter expansion, arrays, functions, variables, pipelines) in
parallel — about 8,300 tests in ~20s. It omits the serial/subprocess-heavy
areas (redirection, subshells, job control, interactive, scripting) and
explicitly excludes the benchmark tier (`-m "… and not benchmark"`, and
`tests/performance/` is not among its paths). Use it during development for a
faster signal. It is **not** the gate — run the standard `--parallel` suite
before merging.

### 3) Manual focused runs

```bash
python -m pytest tests/                       # all tests, serially
python -m pytest tests/conformance/           # POSIX/bash compatibility
python -m pytest tests/unit/builtins/ -v      # one category
python -m pytest -k "test_name" -xvs          # one test with output
```

Subshell tests pass under normal capture (no `-s` needed since v0.195.0).
Manual parallel runs must exclude serial-marked tests:
`python -m pytest tests/ -n auto -m "not serial"`, then
`python -m pytest tests/ -m serial`.

### 4) Bash behavioral comparison

```bash
python run_tests.py --compare-bash            # re-run golden cases vs real bash
```

Re-runs `tests/behavioral/golden_cases.yaml` against a live bash. Promote a
worthwhile probe into that file rather than leaving it in `tmp/`.

### 5) XPASS audit for stale xfail markers

```bash
python -m pytest tests/ -m xfail -q -rxX
```

Surfaces `XPASS` for markers that should be removed.

## Notes

- If a test touches subshell or FD behavior, prefer `run_tests.py` over raw
  pytest.
- Keep command examples in other docs aligned with this file.
