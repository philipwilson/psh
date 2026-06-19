# PSH Test Suite

> [!IMPORTANT]
> Canonical test commands for contributors live in
> [`docs/testing_source_of_truth.md`](../docs/testing_source_of_truth.md).
> The release gate is **local**: `python run_tests.py --parallel`, plus
> `ruff check psh tests` and `mypy`. (GitHub per-PR CI is disabled.)

This directory contains the active PSH test suite — about 8,400 tests
across 365 `test_*.py` files. The layout below is generated from the real
tree; if you add or rename a top-level area, update this list.

## Directory structure

### `unit/`
Pure unit tests for components in isolation (use the `captured_shell`
fixture). Subdirectories:
`builtins/`, `core/`, `executor/`, `expansion/`, `interactive/`,
`io_redirect/`, `lexer/`, `multiline/`, `parser/`, `scripting/`,
`tooling/`, `utils/`, `visitor/`.

`unit/tooling/` holds the meta-tests that keep the docs honest —
`test_doc_pointers.py` (backticked paths/symbols must resolve),
`test_readme_statistics.py` (README counts stay within 10% of the tree),
`test_version_sync.py`, and `test_examples.py` (the `examples/` scripts
parse and run).

### `integration/`
Component-interaction tests (use `isolated_shell_with_temp_dir` for file
I/O). Subdirectories include:
`aliases/`, `arrays/`, `builtins/`, `command_resolution/`, `control_flow/`,
`functions/`, `interactive/`, `job_control/`, `multiline/`,
`parameter_expansion/`, `parser/`, `parsing/`, `pipeline/`, `redirection/`,
`shell_options/`, `subshells/`, `validation/`, `variables/`.

### `system/`
Full-shell behavior driven via subprocess/PTY: `initialization/`,
`interactive/`.

### `conformance/`
POSIX/bash compatibility, compared against live bash on the same host:
`posix/`, `bash/`, `differences/` (documented intentional differences),
plus `conformance_results/` data. See
`conformance/test_claims_have_tests.py` (every "Full support" user-guide
claim must map to a proving test).

### `behavioral/`
`golden_cases.yaml` — bash-comparison probes re-run by
`python run_tests.py --compare-bash`.

### `parser_differential/`
Parity tests pinning the recursive-descent parser against the educational
parser-combinator implementation.

### `performance/`
`benchmarks/` — speed/scaling checks (CPU-time based, marked `slow`).

### `regression/`
Pinned regressions for specific past bugs.

### `framework/`
Shared test-support code (the conformance framework and helpers), not test
cases itself.

### Top level
`conftest.py` (shared fixtures, suite-wide `strict-errors`, automatic
`serial` marking), plus the parser parity/visualization checks
(`test_parser_*.py`).

## Running tests

See [`docs/testing_source_of_truth.md`](../docs/testing_source_of_truth.md)
for the authoritative command list. The common ones:

```bash
python run_tests.py --parallel        # full suite (the gate)
python run_tests.py --quick           # fast inner-loop subset
python -m pytest tests/unit/          # one category
python -m pytest -k name -xvs         # one test, with output
```

## Writing tests

See [`docs/test_pattern_guide.md`](../docs/test_pattern_guide.md) for
fixtures, output-capture rules, and parallel-safety guidance (permanent-fd
tests must run in a subprocess; process/signal tests are auto-marked
`serial`).
