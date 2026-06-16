## Project Overview

Python Shell (psh) is an educational Unix shell implementation designed to teach shell internals through clean, readable Python code.
- Hand-written recursive descent parser for clarity
- Component-based architecture with clear separation of concerns
- Comprehensive test suite 
- POSIX compliance (within reason)
- Visitor pattern for AST operations

## Quick Start Commands

```bash
# Run tests (RECOMMENDED - uses smart test runner)
# IMPORTANT: Always redirect full test output to a file so you can inspect
# failures without re-running the entire suite:
python run_tests.py > tmp/test-results.txt 2>&1; tail -15 tmp/test-results.txt
# If failures are found, grep the saved file instead of re-running:
#   grep FAILED tmp/test-results.txt
#   grep -A 10 "FAILURES" tmp/test-results.txt

python run_tests.py --quick                # Fast tests only
python run_tests.py --parallel             # Parallel mode (pytest-xdist; ~4x faster, ~23s vs ~87s)
python run_tests.py --parallel 8           # Parallel with 8 workers
python run_tests.py --all-nocapture        # Simple mode - run all with -s

# Run tests manually (for specific scenarios)
python -m pytest tests/                    # All tests, serially (subshell tests pass without -s as of v0.195.0)
python -m pytest tests/integration/subshells/      # Subshell tests (no -s needed)
python -m pytest tests/test_foo.py -v     # Specific test file
python -m pytest tests/unit/builtins/ -v  # Specific test category
python -m pytest -k "test_name" -xvs      # Specific test with output

# Manual parallel runs MUST exclude serial-marked tests, or xdist workers crash
# (process/signal/job-control + permanent-fd tests; see "Known Test Issues").
# run_tests.py --parallel handles this split automatically — prefer it.
python -m pytest tests/ -n auto -m "not serial"    # Parallel phase (safe)
python -m pytest tests/ -m serial                  # Serial phase (no -n)

# Run conformance tests (POSIX/bash compatibility)
cd tests/conformance
python run_conformance_tests.py           # Full conformance suite
python run_conformance_tests.py --posix-only    # POSIX compliance only
python run_conformance_tests.py --bash-only     # Bash compatibility only
python run_conformance_tests.py --summary-only  # Just show summary

# Run specific test categories
python -m pytest tests/unit/              # Unit tests (builtins, expansion, lexer, parser)
python -m pytest tests/integration/       # Integration tests (pipelines, control flow)
python -m pytest tests/system/            # System tests (interactive, initialization)
python -m pytest tests/performance/       # Performance benchmarks

# Run psh
python -m psh                              # Interactive shell
python -m psh script.sh                    # Run script
python -m psh -c "echo hello"             # Run command

# Debug options
python -m psh --debug-ast                  # Show AST before execution
python -m psh --debug-tokens              # Show tokenization
python -m psh --debug-expansion           # Trace expansions
python -m psh --debug-exec                 # Debug executor (process groups, signals)
python -m psh --validate script.sh        # Validate without executing
```

## Test Organization

### Main Test Suite (`tests/`)
- **Location**: `/tests/`
- **Organization**:
  - `unit/` - Unit tests (builtins, expansion, lexer, parser)
  - `integration/` - Integration tests (pipelines, control flow, functions)
  - `system/` - System tests (interactive, initialization, scripts)
  - `conformance/` - POSIX/bash compatibility tests
- **Command**: `python -m pytest tests/`


**Interactive testing**

You can switch parsers inside a running psh session:

```bash
python -m psh --parser combinator         # Start with combinator
python -m psh --parser rd                 # Start with recursive descent (default)
```

**Lint**

Production AND test trees must stay ruff-clean (CI runs `ruff check psh tests`
— linting only `psh/` locally will pass here and fail CI). After any change:

```bash
ruff check psh tests
```

**Type checking**

A non-strict mypy config lives in `pyproject.toml` (`[tool.mypy]`); the `files`
list defines the checked scope, which is now the **entire `psh/` source tree**
(238 files as of v0.483.0) with `check_untyped_defs = true` enabled per-package.
Run `mypy` (no arguments) and keep it passing. The **local** release gate and
the nightly run enforce it — per-PR CI (`tests.yml`) is intentionally disabled
(see the release-workflow note below), so a green `mypy` is your responsibility
before merging. New modules are picked up by the package globs automatically;
keep new code mypy-clean rather than loosening the config.

## Critical Information

### Bash-verification workflow (how behavior fixes are made)

Behavior changes are pinned to bash, not to intuition. Before fixing,
write a probe battery comparing the two shells:

```bash
b=$(bash -c "$cmd" 2>&1); p=$(python -m psh -c "$cmd" 2>&1)
# diff stdout/stderr/exit codes across the relevant cases
```

Fix until the probes match, then turn the probes into tests (conformance
tests for user-guide claims, unit/integration tests otherwise). When an
existing test fails after a fix, READ it first — if it pins old broken
behavior, verify against bash and update the test, not the fix.

Probe scripts that are still worth keeping after the fix don't stay in
`tmp/` — promote them to entries in `tests/behavioral/golden_cases.yaml`,
which the `--compare-bash` phase (`python run_tests.py --compare-bash`,
or `pytest tests/behavioral --compare-bash`) re-runs against a real bash.
That keeps the probe earning its keep as a regression pin instead of
rotting as a scratch file.

### Release workflow (per completed enhancement)

The gate is **local** — GitHub's per-PR `tests.yml` workflow is intentionally
disabled (`gh workflow disable tests.yml`, state `disabled_manually`; re-enable
with `gh workflow enable tests.yml`). The nightly full+bash+coverage run
(`nightly.yml`) stays on as a safety net. `release-tag.yml` auto-creates the
annotated `vX.Y.Z` tag when `psh/version.py` changes on main, so tagging is
automatic — there is **no manual `git tag`** step.

1. Work on a `fix/<topic>` branch.
2. Full suite green LOCALLY: `python run_tests.py --parallel > tmp/test-results-N.txt 2>&1`
   (this is THE gate). Also `ruff check psh tests` and `mypy` clean.
3. Update `psh/version.py` (bump `__version__`) and add a `CHANGELOG.md` entry.
4. Update the version string in **all** of these files (they must always match):
   - `README.md` — the `**Current Version**:` line (also the `**Tests**:` and
     `**Test Coverage**:` counts and Recent Development when they changed)
   - `ARCHITECTURE.md` — the `**Current Version**:` line
5. Commit on the branch, push, open a PR (`gh pr create --head <branch>`),
   then merge immediately (`gh pr merge <n> --merge --delete-branch` — no CI to
   wait on). `release-tag.yml` creates the `vX.Y.Z` tag on the version bump;
   verify with `git fetch --tags`.

### Architecture documentation files and what they contain

These files have version-stamped metadata that must stay in sync:

| File | Contains | Key metadata |
|------|----------|-------------|
| `psh/version.py` | Canonical version | `__version__` |
| `CHANGELOG.md` | Detailed version history | `## VERSION` entries |
| `README.md` | User-facing overview | Version, test count, LOC, file count, recent development |
| `ARCHITECTURE.md` | Architecture guide (incl. Quick Map for orientation) | Version |

For agent orientation: ARCHITECTURE.md's Quick Map → the relevant
subsystem `CLAUDE.md` → `docs/architecture/ast_data_flow.md` for
expansion-context pointers. For the end-to-end narrative (one command
traced through every stage, reproducible via the debug flags) see
`docs/architecture/tour_of_psh_internals.md`. (`ARCHITECTURE.llm` was
retired to `docs/archive/` in v0.311.0.)

### Known Test Issues

0. **`strict-errors` is enabled suite-wide** (`conftest.py` sets
   `PSH_STRICT_ERRORS=1`, covering in-process and subprocess psh). A test that
   triggers a genuine INTERNAL DEFECT (an unexpected Python exception —
   `RuntimeError`/`AttributeError`/`TypeError`/`KeyError`/plain `ValueError`)
   now FAILS LOUDLY instead of silently passing as exit-1. Expected shell
   errors (`PshError`/`OSError`/`SyntaxError`) pass through normally. A test
   that DELIBERATELY drives an internal exception (to exercise the swallow-to-1
   path) must set `strict-errors` off on its shell explicitly. See the
   expected-error taxonomy in `psh/core/CLAUDE.md`.

1. **Subshell Tests**: the full suite passes under normal pytest capture —
   the `-s` flag has not been needed since v0.195.0 (forked children do
   fd-level I/O; see `tests/integration/subshells/README.md` for history).

2. **Pytest Collection Best Practices**:
   - Don't name source files starting with `test_`
   - Don't name classes starting with `Test` unless they're actual test classes

3. **Parallel runs and the `serial` marker** (see `docs/reviews/parallel_test_safety_2026-06-06.md`):
   - The suite runs safely under `pytest-xdist`, but some tests **cannot** run
     concurrently and are auto-marked `serial` by `tests/conftest.py`:
     - **Permanent/process-level fd redirection** run *in-process* (e.g. `exec >file`,
       `exec 3>&1`) rewrites the worker's own fds — under xdist those carry the
       execnet channel, so the whole parallel session aborts with
       `INTERNALERROR> OSError: cannot send (already closed?)`. **Write these tests
       in a subprocess instead** (see Testing guidelines below); they don't need
       the marker if isolated.
     - **Process/signal/job-control** tests (`job_control`, `test_disown`,
       `test_signal_builtins`, `test_pty`, `integration/redirection`) send signals /
       wait on processes and must not run alongside siblings.
   - `run_tests.py --parallel` runs `-m "not serial"` under xdist, then `-m serial`
     without `-n`. A **bare** `pytest -n auto` will crash — always add `-m "not serial"`.
   - Mark a new xdist-unsafe test with `@pytest.mark.serial` (or place it under one
     of the path prefixes above, which conftest marks automatically).

4. **Background-job tests don't need to clean up their own jobs**:
   - The `shell`-family fixtures' teardown (`_cleanup_shell`) **SIGKILLs** any
     still-running background jobs and reaps them. Tests may freely start
     `sleep 30 &` without an explicit `kill`. (Teardown used to *wait* for these
     jobs, which made the serial phase ~12× slower — fixed 2026-06-06.)

5. **The local gate runs on macOS; only the nightly runs on Linux.** Conformance
   tests compare psh against *live bash on the same host*, so any behavior that
   differs by platform is exercised on macOS-vs-bash locally and on Linux-vs-bash
   only in the nightly. Linux-specific code paths therefore are NOT covered by the
   local gate. Known platform-divergent spots: real-time signals (`SIGRTMIN+n`,
   absent on macOS — the v0.472 `kill -l` bug surfaced only on the Linux nightly),
   the macOS-only `/dev/fd` FIFO fallback in `process_sub.py`, glob/case-range
   locale collation, and signal-name aliases (`SIGCHLD`/`SIGCLD`). When touching
   signals, process substitution, or fd/locale behavior, reason about Linux too —
   the nightly is the backstop, not the gate.

## Architecture Quick Reference

### Subsystem Documentation

Each major subsystem has its own CLAUDE.md with detailed guidance:

| Subsystem | Location | Purpose |
|-----------|----------|---------|
| **Lexer** | `psh/lexer/CLAUDE.md` | Tokenization, recognizers, quote/expansion parsing |
| **Parser** | `psh/parser/CLAUDE.md` | Recursive descent parsing, AST construction |
| **Executor** | `psh/executor/CLAUDE.md` | Command execution, process management, control flow |
| **Expansion** | `psh/expansion/CLAUDE.md` | Variable, command, tilde, glob expansion |
| **Core/State** | `psh/core/CLAUDE.md` | Shell state, variables, scopes, options |
| **Builtins** | `psh/builtins/CLAUDE.md` | Built-in commands, registration, adding new builtins |
| **I/O Redirect** | `psh/io_redirect/CLAUDE.md` | Redirections, heredocs, process substitution |
| **Visitor** | `psh/visitor/CLAUDE.md` | AST visitor pattern, traversal, transformation |
| **Interactive** | `psh/interactive/CLAUDE.md` | REPL, job control, history, completion |

These provide focused documentation for working within each subsystem.

### Key Files
- `psh/shell.py` - Main orchestrator (thin wiring; no execution logic)
- `psh/parser/` - Recursive descent parser package
- `psh/lexer/` - Modular tokenizer package with recognizer architecture
- `psh/executor/` - Execution engine with visitor pattern
- `psh/core/state.py` - Central state management
- `psh/expansion/manager.py` - Orchestrates all expansions

### Component Managers
Each manager handles a specific aspect:
- `ExpansionManager` - Variable, command substitution, globs, etc.
- `IOManager` - Redirections, pipes, heredocs
- `JobManager` - Background jobs, job control
- `ProcessLauncher` - Unified process creation with proper job control (single shared instance on `shell.process_launcher`)
- `FunctionManager` - Shell function definitions
- `AliasManager` - Shell aliases

### Process Execution Architecture
PSH has one fork helper and one child signal policy; job-controlled process
creation additionally goes through ProcessLauncher:
- **fork helper** (`psh/executor/child_policy.py`) - every fork site uses
  `fork_with_signal_window()`, and every child applies
  `apply_child_signal_policy()` immediately after the fork (v0.312)
- **ProcessLauncher** (`psh/executor/process_launcher.py`) - single source of
  truth for *job-controlled* process creation (process groups, terminal
  control, pipeline synchronization)
- **ProcessRole Enum**: SINGLE, PIPELINE_LEADER, PIPELINE_MEMBER
- **ProcessConfig**: Configuration for launch (role, pgid, foreground, sync pipes, I/O setup)
- **Used by**: Pipelines, external commands, builtins (background), subshells, brace groups
- **Substitutions fork directly by design**: command substitution
  (`psh/expansion/command_sub.py`) and process substitution
  (`psh/io_redirect/process_sub.py`) are not jobs — they call the fork helper
  and child signal policy themselves rather than going through ProcessLauncher

### Word AST (SimpleCommand Arguments)
The parser always builds **Word AST nodes** for command arguments. Each
`SimpleCommand.words` list contains `Word` objects with `LiteralPart` and
`ExpansionPart` nodes carrying per-part quote context (`quoted`, `quote_char`).

As of v0.120.0, `words` is the **sole** argument metadata representation.
The legacy `arg_types`/`quote_types` string lists have been removed.
Use Word helper properties for semantic queries:

| Property | Replaces | Purpose |
|----------|----------|---------|
| `word.is_quoted` | `arg_type == 'STRING'` | True if wholly quoted |
| `word.is_unquoted_literal` | `arg_type == 'WORD'` | Plain unquoted word |
| `word.is_variable_expansion` | `arg_type == 'VARIABLE'` | Single `$VAR` expansion |
| `word.has_expansion_parts` | checking for expansion types | Any expansion present |
| `word.has_unquoted_expansion` | unquoted + `$` in arg | Vulnerable to splitting |
| `word.effective_quote_char` | `quote_types[i]` | The quote char (`'`, `"`, `$'`, or None) |

### Execution Flow
```
Input → Line Continuation → Tokenization → Parsing → AST → Expansion → Execution
                                                                         ↓
                                                                   ProcessLauncher
                                                                   (fork + job control)
```

## Development Guidelines

### Testing

**Test Writing Guidelines**

Choose the right fixture based on test type:

1. **Unit Tests** (use `captured_shell`):
   - Testing builtin command output
   - Testing parser/lexer components  
   - Testing expansion logic
   - No file I/O or process spawning

2. **Integration Tests** (use `isolated_shell_with_temp_dir`):
   - Testing I/O redirection
   - Testing pipelines
   - Testing job control
   - Testing subshells
   - File system operations

3. **System Tests** (use `subprocess`):
   - Testing full shell behavior
   - Comparing with bash
   - Testing process lifecycle
   - Interactive features (when possible)

**Output Capture Rules**:
1. NEVER use capsys with shell tests that do I/O redirection
2. ALWAYS use captured_shell for builtin output testing
3. PREFER subprocess.run for external command testing
4. AVOID mixing capture methods in the same test

**Parallel-safety rules** (so tests survive `pytest -n auto`; see
`docs/reviews/parallel_test_safety_2026-06-06.md`):
1. **Permanent fd redirection → subprocess, never in-process.** A test that
   changes the shell's fds *permanently* (`exec >file`, `exec 2>&1`, `exec 3>&1`,
   fd open/close/dup that outlives one command) MUST run psh in a subprocess
   (`subprocess.run([sys.executable, '-m', 'psh', '-c', script], ...)`). In-process,
   it rewrites the test runner's own fds — which under xdist are the worker channel,
   aborting the whole run. Per-command redirections (`echo x > f`, `cmd 2>&1 | …`)
   are fine in-process (psh saves/restores fds around each command).
2. **Creating files? Use `isolated_shell_with_temp_dir`** (real `os.chdir` into a
   per-test temp dir). `shell_with_temp_dir` now `os.chdir`s too, but prefer the
   isolated fixture. A test that writes a fixed-name file (`output.txt`) to the
   shared cwd will collide across workers.
3. **Process/signal/job-control tests** are auto-marked `serial` by path (see
   Known Test Issues). Mark any other xdist-unsafe test `@pytest.mark.serial`.

**Example Patterns**:

```python
# Unit test with captured_shell
def test_echo_output(captured_shell):
    result = captured_shell.run_command("echo hello")
    assert result == 0
    assert captured_shell.get_stdout() == "hello\n"
    assert captured_shell.get_stderr() == ""

# Integration test with isolated shell
def test_file_redirection(isolated_shell_with_temp_dir):
    shell = isolated_shell_with_temp_dir
    shell.run_command("echo test > file.txt")
    
    # Read file directly, not through shell output
    import os
    with open(os.path.join(shell.state.variables['PWD'], 'file.txt')) as f:
        assert f.read() == "test\n"

# Conformance test with subprocess
def test_posix_compliance():
    import subprocess
    cmd = "echo $((1 + 1))"
    
    psh = subprocess.run([sys.executable, '-m', 'psh', '-c', cmd], 
                        capture_output=True, text=True)
    bash = subprocess.run(['bash', '-c', cmd], 
                         capture_output=True, text=True)
    
    assert psh.stdout == bash.stdout

# Permanent fd redirection (exec) — MUST be a subprocess, never in-process.
# An in-process `exec >file` would clobber the test runner's own fds.
def test_exec_redirection(temp_dir):
    import os, subprocess, sys
    result = subprocess.run(
        [sys.executable, '-m', 'psh', '-c', 'exec > out.txt; echo hi'],
        cwd=temp_dir, capture_output=True, text=True)
    assert result.returncode == 0
    with open(os.path.join(temp_dir, "out.txt")) as f:
        assert "hi" in f.read()
```

**For conformance tests**:
- Add to `tests/conformance/posix/` or `tests/conformance/bash/`
- Inherit from `ConformanceTest` base class
- Use `assert_identical_behavior()` for exact PSH/bash matching
- Use `assert_documented_difference()` for known differences

**Best Practices**:
- Clear output between tests: `captured_shell.clear_output()`
- Check both stdout and stderr
- Always verify exit codes
- Use appropriate test markers (@pytest.mark.serial, @pytest.mark.isolated)

See `docs/test_pattern_guide.md` for examples and patterns.

### Error Handling
- Use `self.error()` in builtins for consistent error messages
- Return appropriate exit codes (0=success, 1=general error, 2=usage error)
- For control flow, use exceptions (LoopBreak, LoopContinue, FunctionReturn)

## Current Development Status

The canonical version lives in `psh/version.py`; see `CHANGELOG.md` for
detailed history. (Do not record the version number here — it goes stale.)

## Debugging Tips

1. **Import Errors**: Clear `__pycache__` directories if you see module import issues
2. **Test Failures**: Run failing tests individually to check for test pollution
3. **Parser Issues**: Use `--debug-ast` and `--debug-tokens` to see parsing details
4. **Expansion Issues**: Use `--debug-expansion` to trace variable/command expansion

## Important Notes

- Use `tmp/` subdirectory for temporary files, not system `/tmp`
- Educational focus means clarity over performance in implementation choices

## Development Principles
- If we assert that a feature of psh is POSIX or bash conformant in the user's guide (docs/user_guide/*) then we must have a test in `tests/conformance/` which proves it. This is enforced by a meta-test (`tests/conformance/test_claims_have_tests.py`): adding a "Full support" row to the user-guide compatibility table without a mapped conformance test fails the suite — add the proving test, then map it in `CLAIM_TESTS`.