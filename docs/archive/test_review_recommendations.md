# Test Suite Review & Recommendations

**Date**: 2026-02-06
**Version**: 0.113.0

## Current State

| Metric | Value | Change from 0.112.0 |
|--------|-------|---------------------|
| Total Tests | 3,021 | +88 |
| Passed | 2,803 | +88 |
| Failed | 0 | — |
| Skipped | 173 | — |
| XFail | 36 | -4 |
| XPass | 0 | -2 |
| POSIX Compliance | 98.4% | — |
| Bash Compatibility | 91.8% | — |

The test suite is in good shape -- zero real failures, well-organized structure, and clear categorization of expected issues. All original recommendations 1-8 have been implemented. Subsequent fixes addressed SIGTTOU signal issues, nested subshell parsing, and full extglob implementation.

---

## Completed Recommendations (v0.107.0)

### ~~1. Reclassify `echo $$` conformance result~~ DONE

`echo $$` reclassified from `psh_bug` to `documented_difference` with ID `PROCESS_ID_DIFFERENCE`. Different PIDs is expected behavior since PSH and bash are separate processes.

### ~~2. Fix glob expansion on variable results~~ DONE

`PATTERN="*.txt"; echo $PATTERN` now correctly glob-expands after variable expansion per POSIX. Removed `VARIABLE` from the glob exclusion list in `_process_single_word()`. The `test_glob_with_variable` xfail has been removed.

### ~~3. Fix partial quoting in glob patterns~~ DONE

`echo "test"*.txt` now correctly expands the unquoted `*` while preserving the quoted `test` literal. Implemented using `\x00` markers to distinguish quoted vs unquoted glob characters in composite tokens, with proper handling for `${...}` expansion syntax so array subscripts are not affected. The `test_partial_quoting` xfail has been removed.

### ~~4. Move I/O-capture xfails to `-s` test phase~~ DONE

3 C-style for loop I/O redirection tests moved from xfail to Phase 3 of `run_tests.py` (run with `-s`). The alias test (`test_alias_with_arguments`) was left as xfail since it's a real non-interactive mode limitation, not an I/O capture issue.

### ~~5. Implement `shopt` builtin~~ DONE

Created `psh/builtins/shell_options.py` with full `shopt` implementation:
- Flags: `-s` (set), `-u` (unset), `-p` (print reusable), `-q` (query silently)
- Options: `dotglob`, `nullglob`, `extglob`, `nocaseglob`, `globstar`
- Added `nullglob` support in glob expansion (no-match returns empty instead of literal)
- 16 tests in `tests/unit/builtins/test_shopt.py`

### ~~6. Add regression tests~~ DONE

Created `tests/regression/test_bug_fixes_4f4d854.py` with 12 tests covering:
- Command substitution trailing newline stripping
- IFS word splitting (whitespace vs non-whitespace delimiters)
- dotglob option behavior
- Comment recognition after `)` and `}` tokens

---

## Completed Recommendations (v0.108.0)

### ~~7. Fix Remaining Conformance Bugs (4 bugs)~~ DONE

All 4 `psh_bug` conformance items resolved:

- **`echo \$(echo test)`** -- Reclassified as `documented_difference` (ID: `ERROR_MESSAGE_FORMAT`). Both shells reject with exit code 2; only the error message format differs.
- **`sleep 1 & jobs`** -- Fixed job format string in `psh/job_control.py` to match bash: wider state field (24 chars), ` &` suffix for background jobs. Also fixed background job `+` marker by calling `register_background_job()` in `psh/executor/strategies.py` so `current_job` is properly set.
- **`history`** -- Fixed in `psh/shell.py` to only load history for interactive shells. Bash doesn't load persistent history in non-interactive mode (`bash -c 'history'` outputs nothing).
- **`pushd /tmp`** -- Fixed in `psh/builtins/directory_stack.py` to initialize the stack with the current directory before pushing the new one. `pushd /tmp` from `~` now produces stack `[/tmp, ~]` matching bash. Remaining output difference (different CWD paths) classified as `documented_difference` (ID: `PUSHD_CWD_DIFFERENCE`) since it's a test environment artifact.

---

## Completed Recommendations (v0.110.0)

### ~~8. Fix the Intermittent Race Condition~~ DONE

Fixed `_wait_for_all` in `psh/builtins/job_control.py` to collect exit statuses from already-completed jobs before waiting for running ones. Previously, if a background job (e.g. `false &`) completed and was reaped before `wait` was called, its exit status was lost because the `while` loop only iterated over non-DONE jobs. Now DONE jobs are checked first for their stored exit status, then removed. Verified stable over 20 consecutive runs.

---

## Additional Fixes (v0.111.0 - v0.112.0)

### ~~9. Fix SIGTTOU in Subshell Pipelines~~ DONE (v0.111.0)

Fixed subshell child processes getting killed by SIGTTOU (signal 22, exit code 150) when running pipelines with a controlling terminal. Root cause: `reset_child_signals()` set SIGTTOU to SIG_DFL for all forked children, but subshell children act as mini-shells that may call `tcsetpgrp()` and need SIGTTOU ignored.

- Added `signal.signal(SIGTTOU, SIG_IGN)` in subshell `execute_fn` (`psh/executor/subshell.py`)
- Made pipeline `_wait_for_foreground_pipeline()` skip `restore_shell_foreground()` when terminal control was never transferred
- Added test isolation cleanup (`_reap_children`, `_cleanup_shell`) to conftest.py files

### ~~10. Fix Nested Subshell Parsing and Process Substitution SIGTTOU~~ DONE (v0.112.0)

Fixed nested subshell syntax `(echo "outer"; (echo "inner"))` failing with parse error. Root cause: the lexer greedily matched `))` as `DOUBLE_RPAREN` (arithmetic close) instead of two separate `RPAREN` tokens.

- Added context check in `psh/lexer/recognizers/operator.py`: `))` is only `DOUBLE_RPAREN` when `arithmetic_depth > 0`
- Removed xfail from `test_nested_subshells` (now passes)
- Guarded `restore_shell_foreground()` in `ExternalExecutionStrategy` with `original_pgid is not None`, preventing SIGTTOU when tests are piped through tee
- Added SIGTTOU `SIG_IGN` in process substitution child fork (`psh/io_redirect/process_sub.py`)

---

## Completed Recommendations (v0.113.0)

### ~~11. Implement `extglob` Extended Globbing~~ DONE

Full implementation of bash-compatible extended globbing with five pattern operators:

| Operator | Meaning |
|----------|---------|
| `?(pat\|pat)` | Zero or one occurrence |
| `*(pat\|pat)` | Zero or more occurrences |
| `+(pat\|pat)` | One or more occurrences |
| `@(pat\|pat)` | Exactly one occurrence |
| `!(pat\|pat)` | Anything except pattern |

Patterns support nesting (e.g., `+(a|*(b|c))`) and pipe-separated alternatives. Enable with `shopt -s extglob` (must be set on a previous line, matching bash tokenization behavior).

**Four integration points**, all working:
1. **Pathname expansion** -- `echo @(a|b).txt` matches files via `expand_extglob()` in `psh/expansion/glob.py`
2. **Parameter expansion** -- `${var//@(a|b)/X}` via `extglob_to_regex()` in `PatternMatcher`
3. **Case statements** -- `case $x in @(yes|no)) ...` via `_match_case_pattern()` in `psh/executor/control_flow.py`
4. **Conditional expressions** -- `[[ $x == @(yes|no) ]]` via `_pattern_match()` in `psh/shell.py`

**Implementation details:**
- Core engine: `psh/expansion/extglob.py` with recursive extglob-to-regex converter
- Negation `!(pat)` uses match-and-invert for standalone patterns, negative lookahead for inline
- Lexer: extglob patterns tokenized as single WORD tokens when enabled; `+` and `!` followed by `(` no longer treated as word terminators
- Shell options threaded through `tokenize()` and `tokenize_with_heredocs()` for dynamic extglob awareness
- Fixed `StringInput` `-c` mode to split on newlines so `shopt` on line N affects tokenization of line N+1
- 88 new tests: 55 unit (pattern engine), 13 lexer (tokenization), 20 integration (all 4 contexts)

### ~~12. Remove XPass Markers~~ DONE

Removed xfail markers from two tests that now pass:
- `test_simple_command_after_nested_structure` in `test_nested_structures_io_conservative.py`
- `test_variable_assignment_after_nesting` in `test_nested_structures_io_conservative.py`

Updated conformance test markers:
- `test_extended_globbing` -- removed xfail, now uses `check_behavior()` with multi-line extglob commands
- `test_shopt_options` -- removed xfail, now uses `assert_identical_behavior()` for shopt commands

---

## Remaining Recommendations

### 1. Reclassify Conformance Test Errors

9 conformance results are `test_error` but most are actually known missing features (exec FDs, error expansion). They should be reclassified as `documented_difference` with appropriate notes, which would give a more accurate picture of actual compliance.

### 2. Fill Performance Test Gaps

- `tests/performance/memory/` and `tests/performance/stress/` are empty directories
- Consider adding memory and stress tests for expansion, parsing, and process creation

### 3. Interactive Test Strategy

119 tests behind `--run-interactive` and 20 requiring `pexpect`. These cover history, tab completion, line editing, and job control. Current options:
- Install `pexpect` and enable those 20 tests
- Fix PTY-based line editing to unblock the 10 skipped `test_line_editing.py` tests
- Consider running interactive tests in CI with a dedicated phase

---

## Detailed Breakdown

### Skipped Tests (173 total)

| Category | Count | Details |
|----------|-------|---------|
| Interactive (--run-interactive) | 119 | Completion, history, line editing, spawn tests |
| pexpect not installed | 20 | Line editing, history nav, tab completion |
| PTY-based tests | 19 | Job control, line editing via PTY |
| Parser combinator parity | 10 | select, arrays, redirections, heredocs, etc. |
| Advanced arithmetic TODO | 11 | Parameter expansion, brace expansion, nesting |
| Arithmetic integration | 6 | Here docs/strings with arithmetic |
| Other individual skips | 4 | Here doc functions, ANSI-C quoting, composite words, background subshell |
| Line editing | 1 | Cursor movement |

### XFail Tests (36 total)

#### By Classification

| Classification | Count | Description |
|----------------|-------|-------------|
| Test Infrastructure | 1 | Alias expansion in non-interactive mode |
| Missing Features | 1 | exec FDs |
| Design Differences | 3 | Escaped command sub, POSIX variable scoping |
| Other | 31 | Alias expansion, control flow, functions, builtins, parsing |

#### By Subsystem

| Subsystem | Count | Tests |
|-----------|-------|-------|
| Parsing/Expansion | 9 | Character classes, error recovery, mixed quoting, logical ops, brace expansion edge cases |
| Control Flow | 3 | Case fallthrough, heredoc in case, while-read pipes |
| Aliases | 6 | Expansion timing, special chars, subshell inheritance, array syntax, pipe, args |
| Subshells | 4 | Complex redirections, process sub, stderr redirect, command not found |
| Conformance | 2 | Advanced redirection, exec FDs |
| Functions | 4 | Background job, pipeline filter, pipeline chain, many commands |
| Builtins | 3 | Declare nameref, history clear, disown |
| Job Control | 1 | Background job redirection error |
| While Loops | 1 | Command condition with read |
| Performance | 1 | Long brace expansion |
| Pipelines | 1 | Error in middle |
| Parameters | 1 | Scoping |

### Conformance Results (239 total)

| Category | Count | Percentage |
|----------|-------|------------|
| Identical | 222 | 92.9% |
| Documented Difference | 6 | 2.5% |
| PSH Extension | 2 | 0.8% |
| PSH Bug | 0 | 0.0% |
| Test Error | 9 | 3.8% |

#### PSH Bugs (0)

All previously reported bugs have been resolved. See completed recommendations above.

#### Test Errors (9)

1. `unset x; echo ${x:?undefined}` -- Error expansion for unset variables (POSIX)
2. `x=; echo ${x:?empty}` -- Error expansion for empty variables (POSIX)
3-6. Test-level errors for redirection and exec FD operations
7. `exec 3> file.txt` -- Exec with numbered file descriptors (Bash)
8-9. Alias and other test-level errors

#### Documented Differences (6)

1. `VAR=value echo $VAR` -- Command-prefixed variable expansion (PSH is more POSIX-correct)
2. `A=1 B=2 echo $A$B` -- Multi-assignment prefix expansion (PSH is more POSIX-correct)
3. `popd` -- Directory stack behavior
4. `echo $$` -- Process ID differs between PSH and bash (expected)
5. `echo \$(echo test)` -- Both shells reject as syntax error; error message format differs
6. `pushd /tmp` -- Both shells correctly show two-entry stack; CWD differs due to test environment

#### PSH Extensions (2)

1. `alias greet="echo hello"; greet world` -- Alias expansion in non-interactive mode
2. `version` -- PSH-specific command

---

## What's Working Well

- Test organization (unit/integration/system/conformance) is clean and logical
- The `run_tests.py` smart runner properly handles the pytest `-s` issue for subshells and I/O tests
- xfail reasons are specific and actionable
- Conformance framework gives objective compliance metrics
- 97%+ of tests (2,803/3,021 non-skipped) pass
- Regression tests guard against re-introduction of fixed bugs
- SIGTTOU signal handling is robust across subshells, pipelines, and process substitution
- Nested subshell parsing works correctly alongside arithmetic expressions
- Extended globbing (extglob) is fully implemented across all four shell contexts

---

## Summary: Recommended Next Steps

1. Reclassify 9 conformance test errors for more accurate metrics
2. Add performance/stress tests
3. Enable interactive tests with `pexpect`
