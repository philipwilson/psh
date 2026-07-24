# Wave 0 baseline legs — summary of record

- **Run:** 2026-07-24, 17:51–18:20 local, sequentially, in a neutral detached
  worktree at **`0215279c`** (v0.750.0, the launch base = origin/main).
  Script + full per-leg outputs: `wave0-legs/` (this directory).
- **Environment:** macOS (Darwin 25.5.0, arm64), Python 3.14, PATH bash
  5.2.26 (homebrew, `/opt/homebrew/bin/bash`), ruff/mypy versions in
  `wave0-legs/context.txt`. Shared interactive host; only light document
  editing ran concurrently.
- **Dual role (integrator plan A11):** these legs are BOTH this campaign's
  Wave 0 regression baseline AND the predecessor Boundary Integrity
  Campaign's pending criterion-7 exit legs, discharged here (see the
  2026-07-24 addendum in `../../boundary_campaign_close_2026-07.md`).

## Results

| Leg | Command | Result |
|---|---|---|
| ruff | `ruff check psh tests tools` | clean |
| mypy | `python -m mypy` (config: pyproject, files=psh) | clean, 274 source files |
| gate seed 101 | `python -u run_tests.py --parallel --shuffle-seed 101` | **20,315 passed / 1,590 skipped / 10 xfailed** — all phases PASSED |
| gate seed 202 | same, `--shuffle-seed 202` | **20,315 / 1,590 / 10** — identical census |
| gate seed 303 | same, `--shuffle-seed 303` | **20,315 / 1,590 / 10** — identical census |
| conformance | `python -m pytest tests/conformance -q` | 2,654 passed / 1 skipped / 8 xfailed (538 s) |
| compare-bash | `python -m pytest tests/behavioral --compare-bash -n auto -q` | 2,986 passed / 24 skipped — EXACT (40 s) |
| benchmarks | `python -u run_tests.py --benchmarks` | all phases PASSED (timing-threshold tier; full transcript in `wave0-legs/benchmarks.txt`) |

Three seeds, identical phase censuses — the sequence doc §12.2 standard holds
at the base. No flake fired in any leg this run (the MEDIUM-13 race remains in
the tree and is owned by slot 1.3; it did not trigger here).

## Complexity counters (regression baseline for Waves 3/5 and Ceremony C)

From `wave0-legs/complexity.txt` (AST-based, script in `wave0-baseline.sh`):

- production files: **274**; LOC: **77,346**
- functions: **3,080** total; **54** ≥100 lines
  (largest: `ShellState.__init__` 303, `CommandExecutor._run_command` 211,
  `PipelineExecutor._execute_pipeline` 200 — top-10 list in the file)
- incomplete-annotation functions (stated methodology): **510**

## Caveats

- These are macOS numbers. The Linux nightly at this same SHA is RED
  (24 + 54 failures) — see `nightly-status.md`; owned by slot 1.4. The macOS
  gate and the Linux nightly are BOTH part of the campaign's evidence
  baseline; green-on-macOS is not green.
- Reappraisal #22's fresh-gate observations at v0.748.0/v0.749.0 (one race
  flake; one ENOSPC-invalidated run) are consistent with this baseline: with
  disk headroom checked and one run each, all legs passed here.
