# Phase 2 Plan: Close High-Value Correctness Gaps

Date: 2026-02-09

## Goal

Reduce real shell-semantics risk (not just test noise) while keeping code educational, readable, and pythonic.

## Baseline (as of this plan)

- Canonical suite baseline (from phase-1 analysis): `python run_tests.py --quick` at `2967 passed, 319 skipped, 29 xfailed, 1 xpassed`.
- Targeted probe confirms one stale marker:
  - `tests/integration/parsing/test_quoting_escaping.py::TestQuoteInteractionWithExpansions::test_mixed_quoted_expansions` is `XPASS`.
- Active TODOs in runtime code:
  - `psh/builtins/environment.py:46`
  - `psh/builtins/job_control.py:31`
  - `psh/builtins/function_support.py:492`
  - `psh/builtins/type_builtin.py:90`
  - `psh/parser/recursive_descent/support/word_builder.py:288`

## Priority Order

1. Eliminate stale/ambiguous expectations.
2. Fix correctness that affects script execution semantics.
3. Convert test-infrastructure xfails into reliable coverage.
4. Defer PTY ergonomics and broad feature expansion to later phases.

## Workstream A: Stabilize Expected-Failure Inventory (Quick Win)

- Remove stale xfail marker from:
  - `tests/integration/parsing/test_quoting_escaping.py:430`
- Add a lightweight audit script or documented command to list XPASS quickly during local review.
- Acceptance:
  - `XPASS = 0` on targeted run.

## Workstream B: Implement TODO-Backed Correctness

### B1. `env` command execution mode
- Implement `env [name=value ...] [command [args...]]` in `psh/builtins/environment.py`.
- Respect shell/export model without mutating parent shell state when running a command.
- Add tests in `tests/unit/builtins/test_env_builtin.py` for command-scoped env overrides.

### B2. `jobs -l` behavior
- Implement long format output in `psh/builtins/job_control.py` with stable PID-containing output.
- Tighten tests in `tests/unit/builtins/test_job_control_builtins.py` to verify PID semantics (not just “contains digits”).

### B3. Associative array init parsing
- Replace naive `split()` parser in `psh/builtins/function_support.py` with tokenizer/shlex-based parsing that respects quotes/escapes.
- Add cases with quoted keys/values and spaces.

### B4. Decide low-impact TODOs
- `psh/builtins/type_builtin.py:90`: either implement function body display option or remove TODO with explicit non-goal.
- `psh/parser/recursive_descent/support/word_builder.py:288`: implement expansion parsing or remove dead path if unused.

## Workstream C: Close Highest-Value Semantics Gaps

### C1. Subshell + redirection correctness
- Target tests:
  - `tests/integration/subshells/test_subshell_basics.py:217`
  - `tests/integration/subshells/test_subshell_implementation.py:267`
  - `tests/integration/subshells/test_subshell_implementation.py:578`
- Focus areas: stderr routing, exit-status propagation for command-not-found, multi-redirection ordering.

### C2. Pipeline error propagation
- Target `tests/integration/pipeline/test_pipeline_execution.py:102`.
- Define explicit behavior for failures in middle pipeline stages; verify with and without `pipefail`.

### C3. Function positional-parameter scoping
- Target `tests/unit/executor/test_executor_visitor_functions.py:227`.
- Validate `set` globals are restored after function invocation.

### C4. Alias semantics decision + enforcement
- Target xfails in `tests/integration/aliases/test_alias_expansion.py`.
- Decide and document policy for non-interactive alias expansion, then align parser/expansion/tests.

## Workstream D: Reclassify Infrastructure-Only Xfails

- Convert “capture conflict” xfails to subprocess/`-s` test strategy where behavior is already correct:
  - `tests/integration/functions/test_functions_comprehensive.py:352`
  - `tests/integration/control_flow/test_while_loops.py:94`
  - `tests/integration/subshells/test_subshell_basics.py:235`
- Keep PTY-only limitations explicitly out of phase-2 correctness scope:
  - `tests/system/interactive/test_pty_line_editing.py`
  - `tests/system/interactive/test_pty_job_control.py`

## Exit Criteria

- `python run_tests.py --quick` remains green.
- `XPASS = 0`.
- Net reduction of real-behavior xfails (target: reduce total xfails by at least 8, prioritizing non-PTY and non-performance files).
- Every removed xfail has either:
  - implementation fix + regression test, or
  - explicit documented behavioral decision (if intentionally divergent).

## Execution Checklist

1. Land Workstream A.
2. Land B1+B3 (highest correctness/coverage ratio).
3. Land C1+C2.
4. Land C3+C4.
5. Land B2+B4 cleanup.
6. Reclassify infra-only xfails (Workstream D) and finalize metrics.

## Progress Update (2026-02-09)

### Completed

- Workstream A:
  - Removed stale xfail marker from `tests/integration/parsing/test_quoting_escaping.py::TestQuoteInteractionWithExpansions::test_mixed_quoted_expansions`.
  - Added XPASS-audit command to `docs/testing_source_of_truth.md`:
    - `python -m pytest tests/ -m xfail -q -rxX`
  - Verification snapshot: `35 xfailed, 29 skipped, 0 xpassed`.

- Workstream B1:
  - Implemented `env [name=value ...] [command [args...]]` in `psh/builtins/environment.py`.
  - Added no-command override behavior: `env NAME=value` prints modified environment without mutating parent state.
  - Isolated command execution in a child shell so builtin side effects do not leak.
  - Added fd-alignment for nested external commands so outer redirections (e.g. `env X=1 /usr/bin/env > out`) are honored.
  - Added follow-up option compatibility support:
    - `-i` / `-` (ignore inherited environment),
    - `-u NAME` and `-uNAME` (unset selected variables),
    - `--` option terminator.
  - Hardened child-shell export handling so `-i`/`-u` are preserved even when nested builtins run environment sync.
  - Added regression coverage in `tests/unit/builtins/test_env_builtin.py` for:
    - command-scoped overrides,
    - no-command override printing,
    - non-leaking builtin side effects,
    - command-not-found non-leakage,
    - external-command redirection behavior,
    - `-i` and `-u` behavior and option error paths.
  - Added bash-compatibility coverage in `tests/conformance/bash/test_bash_compatibility.py` for `env -i` and `env -u`.
  - Verification:
    - `python -m pytest -q tests/unit/builtins/test_env_builtin.py` -> `18 passed`
    - `python -m pytest -q tests/conformance/bash/test_bash_compatibility.py::TestBashMiscellaneous::test_env_option_compatibility` -> `1 passed`

- Workstream B3:
  - Replaced naive whitespace split parser in `psh/builtins/function_support.py` for associative array initialization.
  - Added shell-like tokenization via `shlex.split` with fallback for malformed quoting.
  - Added bracket-aware `[key]=value` entry parsing so keys/values with spaces and `=` are handled correctly.
  - Added regression tests in `tests/integration/builtins/test_declare_comprehensive.py` for:
    - quoted keys/values containing spaces,
    - keys and values containing `=` characters.
  - Verification:
    - `python -m pytest -q tests/integration/builtins/test_declare_comprehensive.py -k "associative_array"` -> `4 passed`
    - `python -m pytest -q tests/unit/builtins/test_function_builtins.py -k "declare_associative_array"` -> `1 passed`

### Next Recommended Step

- Continue with **C1: Subshell + redirection correctness**.
