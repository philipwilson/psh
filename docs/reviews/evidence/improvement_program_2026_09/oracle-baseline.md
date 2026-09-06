# Oracle baseline — the regression baseline for every later wave

Filled ONCE at the Wave 0.3 tree (program §6 0.3, last bullet; §11 and §14 compare
against it). Every section below is **PENDING (filled at the 0.3 tree)** until the
integrator runs the legs on the final Wave 0 commit, unsandboxed (D4), with the oracle
resolved to `/opt/homebrew/bin/bash` 5.3.15 and `psh.__file__` under the gated tree
(D15). Record the SHA once and reuse it in every section; a later re-baseline (oracle
patch bump, D1) appends a dated section rather than overwriting.

- **Tree:** PENDING (filled at the 0.3 tree) — `git rev-parse HEAD` of the gated commit
  (the commit BEFORE the `gate_attestation.json` FINAL commit).
- **Oracle:** PENDING — `oracle: <path> <version>` as printed by the `run_tests.py`
  preflight and the pytest session header (expected `/opt/homebrew/bin/bash
  5.3.15(1)-release`).
- **Host:** PENDING — macOS version, `uname -m`, Python version, `brew pin bash` state,
  free disk ≥ 10 GB, no `sandbox-exec` around the gate shell.

## 1. Three seeded standard gates (identical phase censuses required)

`python run_tests.py --parallel` ×3 with distinct seeds; the third run is the
`--write-attestation` run. Record per run: seed, phase 1 (parallel) census, phase 1b
(serial) census, golden phase census, wall time, exit code.

| run | seed | phase 1 (parallel) | phase 1b (serial) | golden | wall | exit |
|---|---|---|---|---|---|---|
| 1 | PENDING (filled at the 0.3 tree) | | | | | |
| 2 | PENDING | | | | | |
| 3 (`--write-attestation`) | PENDING | | | | | |

Attestation: PENDING — `gate_attestation.json` schema 2, `oracle.{path,version}`,
`gated_commit`, verified by `tools/verify_gate_attestation.py`; the synthetic 5.2.26
attestation refused (test name + output); the runner preflight shown refusing under
`BASH_PATH=/bin/bash` (transcript path).

## 2. Conformance

`python -m pytest tests/conformance -q` — PENDING (filled at the 0.3 tree): passed /
failed / skipped / xfailed, wall time, and the D5 version-skip count (expected 0 on this
host).

## 3. compare-bash

`python -m pytest tests/behavioral --compare-bash -n auto -q` (D15 form; never through
`run_tests.py --compare-bash`) — PENDING (filled at the 0.3 tree): rows compared, EXACT
count, psh-only rows, `min_bash`-skipped rows (expected 0), `requires_dev_fd` skips
(expected 0 unsandboxed), wall time.

## 4. Benchmarks

`python run_tests.py --benchmarks` — PENDING (filled at the 0.3 tree): the runner's
per-benchmark measurements and the CR-R4 envelope verdicts, plus the specific numbers
Wave 5 exit criteria cite (§11): `--version` wall time, a variable-write microbench
figure, the lexer-corpus token-stream digest (`tools/regen_lexer_corpus.py`), and peak
RSS of the mapfile unbounded read.

## 5. ruff

`ruff check psh tests tools` — PENDING (filled at the 0.3 tree): the "All checks
passed!" tail (or the exact finding list, which must be empty for a release).

## 6. mypy

`mypy` (no arguments; `pyproject.toml` scope) — PENDING (filled at the 0.3 tree): the
"Success: no issues found in N source files" tail with N.

## 7. Complexity counters (Wave 6 exit criteria, §13)

PENDING (filled at the 0.3 tree):

| counter | command | value |
|---|---|---|
| functions ≥ 100 lines under `psh/` | PENDING (script named here) | PENDING |
| import cycles under `psh/` | PENDING (script named here) | PENDING |
| `grep -rn "tmp/" psh/` evidence citations | `grep -rn "tmp/" psh/ \| wc -l` | PENDING |
| campaign-ID tokens per file (6.3 ceiling seed) | PENDING | PENDING |
| `grep -rc track_quotes psh/lexer` (3.4 target = 0) | `grep -rc track_quotes psh/lexer` | PENDING (9 hits on the launch base per §9) |
| `grep -rn "bash 5\.2" tests/ psh/` (C241 ratchet seed) | see LEDGER Part D census | 645 lines / 416 files at `788ffe41` (re-count at the 0.3 tree) |

## 8. Nightly at the 0.3 tree

Cross-reference `nightly-status.md`: the `workflow_dispatch` run id, both job verdicts,
`BASH_VERSION 5.3.15` in the log, the 7 `%a` rows SKIPPED with the x87 reason, and the
EXPLAINED platform delta between the Linux census and section 1. PENDING (filled at
the 0.3 tree).
