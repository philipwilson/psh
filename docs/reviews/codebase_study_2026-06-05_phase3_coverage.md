# PSH Codebase Study (2026-06-05) — Phase 3: Test Coverage & Quality

This report synthesizes Phase 3 findings on PSH's test coverage and test-suite quality. It ranks coverage gaps by runtime criticality, triages skipped/xfailed tests into keep/rotting/stale buckets, reassesses the long-standing subshell `-s` workaround, and identifies conformance claims made in the user guide that have no backing conformance test. A prioritized list of recommended test additions closes the report.

---

## 1. Coverage Gaps Ranked by Runtime Criticality

The overall suite sits at ~67% line coverage, but the headline number is misleading: most of the shortfall comes from developer/debug tooling (Section 1.6), while several genuinely runtime-critical modules are both under-measured (forked children execute outside in-process coverage) and contain real untested holes. The modules below are ordered so that the runtime-relevant, low-coverage modules come first.

### 1.1 Process substitution handler — `io_redirect/process_sub.py` (19%) — HIGH

File: `/Users/pwilson/src/psh/psh/io_redirect/process_sub.py`
Missing lines: 25-88, 109-143, 153-162, 174-187, 193-196, 201-204

This is runtime-critical I/O machinery: fork + pipe + `/dev/fd` path generation + zombie reaping, yet only 19% covered. The gap is **both a measurement artifact and a genuine hole**. Nearly all existing process-substitution tests (`tests/integration/redirection/test_advanced_redirection.py`, `tests/unit/io_redirect/test_fd_operations.py`, `conformance/bash`) spawn psh via `subprocess.run([..., '-m', 'psh', ...])`, so the forked child's execution never counts toward in-process coverage. Worse, the class `TestProcessSubstitution` in `test_advanced_redirection.py` is **mislabeled**: its docstring claims it tests `<()` and `>()`, but its methods only exercise invalid fds and errexit.

Genuinely untested behaviors:
- **Output direction `>(cmd)`** entirely — lines 32-38, 60-61 (parent-writes / child-reads path).
- `handle_redirect_process_sub()` for a proc-sub used as a redirect target like `> >(cat)` — lines 164-187.
- `create_process_substitution()` child-side fork body — lines 44-88 (signal policy, dup2 wiring, tokenize/parse/execute of the inner command, and the exception branch at 77-79 printing `process substitution error`).
- `cleanup()` fd-close and `waitpid` loop — lines 189-205 (zombie prevention).
- The `ValueError` raised for a malformed proc-sub string — line 160/179.

Failure here means FD leaks, zombie children, or silently dropped output — hard-to-debug runtime corruption.

**Recommendations** (use `isolated_shell_with_temp_dir`, NOT subprocess; run under `run_tests.py` since this forks + redirects):
- (a) `tee out.txt > >(cat > captured.txt)` to drive `direction == 'out'`; verify `captured.txt` content.
- (b) `cat <(echo a; echo b)` reading the file and asserting both lines, covering the child execute path and `/dev/fd` path.
- (c) Proc-sub as a redirect target to hit `handle_redirect_process_sub`.
- (d) A test asserting no leaked FDs / no zombies after the command (poll `os.waitpid` or count `/dev/fd` entries) to cover `cleanup()`.
- (e) A malformed-target unit test asserting `ValueError`.
- (f) Rename/fix the mislabeled `TestProcessSubstitution` class.

### 1.2 Shebang handler — `scripting/shebang_handler.py` (14%) — HIGH

File: `/Users/pwilson/src/psh/psh/scripting/shebang_handler.py`
Missing lines: 24-53, 57-87, 91-124. Caller: `/Users/pwilson/src/psh/psh/scripting/script_executor.py:27-28`

Despite many grep hits for "shebang" in tests, **none** call `parse_shebang` / `should_execute_with_shebang` / `execute_with_shebang` / `ShebangHandler` — the matches are incidental `#!/` strings inside test script bodies. This module decides whether psh hands a script off to an external interpreter, a security- and correctness-sensitive dispatch.

Untested behaviors:
- `parse_shebang` reading the first 1024 bytes and the no-shebang / empty-shebang / non-utf8 early returns (lines 24-53).
- `should_execute_with_shebang`'s psh self-detection (interpreter `endswith '/psh'` or `== 'psh'` → `False`, lines 62-65); the `/usr/bin/env` unwrapping (`env psh` → `False` vs `env python` → `True`, lines 67-73); absolute-path exists+executable check (76-78); and the PATH search loop (81-87).
- `execute_with_shebang` building `cmd_args`, the `subprocess.run` invocation, and the three error branches returning 127/126/1 for `FileNotFoundError`/`PermissionError`/`OSError` (lines 96-124).

A regression here could cause psh to mis-route scripts (e.g. run a `#!/usr/bin/env python3` file as shell text) with no test to catch it.

**Recommendation:** Add `tests/unit/scripting/test_shebang_handler.py` writing temp script files in `tmp/` and instantiating `ShebangHandler` with a shell:
- `parse_shebang` returns `(False, ...)` for no shebang / empty / binary; `(True, '/usr/bin/env', ['python3'])` for env form.
- `should_execute_with_shebang`: `False` for `#!/usr/bin/psh`, `False` for `#!/usr/bin/env psh`, `True` for `#!/bin/sh` (or skip if missing), `False` for a non-existent absolute interpreter.
- `execute_with_shebang`: use a real interpreter (`/bin/cat` or `python3`) to assert returncode passthrough; use a bogus absolute interpreter path to assert the 127 branch and the "No such file or directory" message.

### 1.3 Interactive signal manager — `interactive/signal_manager.py` (24%) — HIGH

File: `/Users/pwilson/src/psh/psh/interactive/signal_manager.py`
Missing lines: 33-36, 42-59, 64-91, 98-110, 115-137, 141-147, 157, 167-205, 215, 222, 240-241, 245-257, 279-295

The only test reference to `SignalManager` is in `conftest.py` cleanup (closing notifier pipes); there is no test of its actual behavior. This is core job-control / interactive infrastructure.

Untested runtime paths:
- `setup_signal_handlers` branching to script-mode (38-59) vs interactive-mode (61-93) registration — including which signals get `SIG_IGN` vs custom handlers.
- `_handle_signal_with_trap_check` trap lookup, ignored-trap early return, trap execution, and default re-raise via `SIG_DFL` + `os.kill` (112-137).
- `_handle_sigint` script-mode-terminate vs interactive-print-newline (139-147).
- `process_sigchld_notifications` — the central reaping loop: reentrancy guard, draining notifications, the `waitpid(-1, WNOHANG|WUNTRACED)` loop, job state update, and stopped-foreground-job terminal-control transfer (159-205).
- `reset_child_signals` resetting all 8 signals to default in forked children (279-295) — critical so children don't inherit shell handlers.
- `ensure_foreground` setpgid + tcsetpgrp (243-257).
- `restore_default_handlers` (95-110).

Bugs here cause zombies, lost job notifications, terminal-control loss, or children inheriting the shell's SIGINT handler.

**Recommendation:** Add `tests/unit/interactive/test_signal_manager.py`. Most paths are testable without a TTY by mocking:
- (a) Instantiate `SignalManager` with a script-mode and an interactive-mode shell; assert expected signals were registered with expected dispositions via the signal registry.
- (b) Set a trap via `shell.trap_manager`; assert `_handle_signal_with_trap_check` invokes `execute_trap`, and that an empty trap action is a no-op.
- (c) Drive `process_sigchld_notifications` with a real short-lived background child (`sleep`/`true`); assert the job transitions to DONE and that the reentrancy guard short-circuits when `_in_sigchld_processing` is True.
- (d) Call `reset_child_signals` in a forked child (`os.fork`); assert via `os._exit` code that handlers are `SIG_DFL`.
- (e) Assert `restore_default_handlers` re-registers saved handlers and closes notifiers.
- Run via `run_tests.py` because of the fork/`-s` interaction.

### 1.4 Subshell executor & process launcher — `executor/subshell.py` (41%), `executor/process_launcher.py` (32%) — MEDIUM

Files: `/Users/pwilson/src/psh/psh/executor/subshell.py` (missing 85, 111-181, 194, 206, 219-249, 279-311); `/Users/pwilson/src/psh/psh/executor/process_launcher.py` (missing 118-120, 146-248, 269-283, 307-343)

`ProcessLauncher` is documented as the single source of truth for **all** forked process creation (pipelines, externals, background builtins, subshells, brace groups); `subshell.py` runs `( )` groups. Both are runtime-critical but show 32% and 41%. As with process_sub, much of the real exercise happens via subprocess-based subshell tests (which must run under `-s`), so forked child bodies — signal policy, pgid/job-control setup, I/O wiring, child exit paths — are not counted in-process, and several branches (foreground vs background, pipeline leader vs member, error/exit paths) are likely genuinely untested.

**Recommendation:** Add in-process tests (run via `run_tests.py` / `-s`) exercising:
- A subshell that sets a variable, proving isolation from the parent scope.
- A subshell with output redirection verified by reading the file.
- A background subshell verifying `$!` and job registration.
- A pipeline whose members are subshells, to drive `PIPELINE_LEADER` / `PIPELINE_MEMBER` `ProcessConfig` roles.
- A subshell exiting non-zero, to confirm exit-code propagation.

### 1.5 Heredoc & redirection orchestration — `io_redirect/heredoc.py` (26%), `io_redirect/manager.py` (46%) — MEDIUM

Files: `/Users/pwilson/src/psh/psh/io_redirect/heredoc.py` (missing 18-40); `/Users/pwilson/src/psh/psh/io_redirect/manager.py` (missing 63-123, 136-152, 162-163, 197-261)

Heredoc and the `IOManager` apply/restore orchestration are core to almost every redirected command. `manager.py` at 46% leaves large contiguous blocks (197-261) unmeasured — the apply/restore dispatch and per-type helper routing. Many heredoc tests pass, yet `heredoc.py` shows 26%, suggesting `HeredocHandler` methods (18-40) are bypassed by the `FileRedirector` path or only hit in subprocess tests. Lower priority than the top three because functionality is heavily exercised end-to-end and stable, but the low line coverage hides which branch (quoted vs unquoted delimiter, `<<-` tab stripping, FD restore on error) is actually verified.

**Recommendation:** Add targeted in-process tests asserting file **content** (not just exit codes — several existing heredoc tests in `test_advanced_redirection.py` only assert `result == 0` with a comment that output verification would need shell output capture). Cover: unquoted heredoc with variable expansion; quoted-delimiter no-expansion; `<<-` tab stripping; here-string `<<<`; and an error path (redirect to an unwritable target) to confirm FDs are restored. Strengthening these existing weak assertions will incidentally raise `manager.py`/`heredoc.py` coverage.

### 1.6 Auxiliary / tooling / debug modules — LOW (deprioritize)

These modules drag the overall 67% down but are **not** on the runtime hot path:

- `psh/__main__.py` (0%) — known artifact, exercised only via subprocess, never imported in-process.
- Visitor tooling: `metrics_visitor.py` (14%), `security_visitor.py` (18%), `debug_ast_visitor.py` (17%), `formatter_visitor.py` (37%), `linter_visitor.py` (42%).
- Utils: `ast_debug.py` (5%), `shell_formatter.py` (23%), `token_formatter.py` (36%).
- Parser visualization: `sexp_renderer.py` (0%), `ast_formatter.py` (35%).
- Debug/introspection builtins: `help_command.py` (16%), `debug_control.py` (19%), `parser_control.py` (16%), `parse_tree.py` (28%), `parser_experiment.py` (38%).

These are developer/debug tooling invoked by `--debug-*` flags or analysis builtins, not by normal command execution. Spending test budget here yields little runtime-safety value.

**Recommendation:** Explicitly exclude or accept these in the coverage target so they don't mask runtime gaps. Optionally add a handful of cheap smoke tests later (one `--debug-ast` invocation, one help builtin call, one formatter round-trip; an in-process `runpy` test of `__main__` to recover its 0% if the entry-point logic is worth guarding) — but do not prioritize them ahead of process_sub, shebang_handler, and signal_manager.

---

## 2. Skip / xfail Triage

Buckets: **KEEP** (genuine, durable environment constraint), **ROTTING** (feature works now or the skip is hiding real coverage — un-skip/relabel), **STALE/WRONG** (test premise or label is inaccurate — fix or delete).

### 2.1 ROTTING — un-skip / relabel

| Issue | File:line | Verdict | Notes |
|-------|-----------|---------|-------|
| History xfails mislabeled "not implemented" | `tests/integration/interactive/test_history.py:84,102,119,136,160,175,192,266,365,396` | ROTTING (HIGH) | history **is** implemented (`type history` → builtin; entries recorded). xfail persists only because the helper drives psh over a non-TTY pipe — a harness limit, not a feature gap. Double-gated: whole dir is `interactive`-marked and skipped unless `--run-interactive` (`conftest.py:424`), so they report as plain skips. **Fix:** rewrite assertions to run via `shell.run_command(...)` against `captured_shell` and drop xfail, or convert to pexpect/PTY tests tagged "requires PTY". Drop the false reason. |
| Tab-completion xfails mislabeled "not implemented" | `tests/integration/interactive/test_completion.py:70,92` | ROTTING (MED) | Completion exists; failure is from piping `'ec\t'` into a non-TTY subprocess. Same `--run-interactive` double-gate. **Fix:** relabel to a PTY/raw-terminal reason and move to pexpect, or delete if redundant. |
| Background-subshell skip is stale | `tests/integration/subshells/test_subshell_implementation.py:287` | ROTTING (HIGH) | `(sleep 0.1; echo done) & wait; echo after` prints `done` then `after`, exit 0 — exactly what the skipped test checks. **Fix:** remove `@pytest.mark.skip`, run under `run_tests.py` (`-s`). |
| Heredoc-in-function xfail is stale | `tests/integration/functions/test_function_advanced.py:116` | ROTTING (HIGH) | `show_doc() { cat << EOF ... EOF }` works with `$1` expansion. xfail will now XPASS. **Fix:** remove `@pytest.mark.xfail`; also remove the internal `pytest.skip` fallback at line 123. |
| ANSI-C here-string skip | `tests/unit/lexer/test_ansi_c_quoting.py:214` | ROTTING (LOW) | Real forked-fd/capsys limitation for `cat <<< $'line1\nline2'`, but it sits as a permanently-skipped unit test (zero coverage). **Fix:** move to an integration test under `tests/integration` running with `-s` via `run_tests.py` (or assert on a file redirection), then un-skip. |

### 2.2 STALE / WRONG — fix premise or label, then un-xfail or delete

| Issue | File:line | Verdict | Notes |
|-------|-----------|---------|-------|
| Function-as-background-job xfail reason vague | `tests/integration/functions/test_function_advanced.py:171` | STALE label (MED) | The limitation is real and deliberate (`bg_func &` → "functions cannot be run in background"), so expecting failure is correct, but "PSH may not support…" is hedged and diverges from bash (bash backgrounds functions fine). **Fix:** decide product intent — implement bash-compatible background functions and make it pass, OR keep the restriction and assert the explicit error message + exit code (not xfail). Replace the hedged reason. |
| Command-not-found-in-subshell xfail tests a flawed assertion | `tests/integration/subshells/test_subshell_implementation.py:578` | WRONG premise (MED) | Test asserts non-zero exit for `(echo before; nonexistent_command; echo after)`, but the last command (`echo after`) succeeds, so `$? = 0` is correct POSIX/bash behavior. psh already propagates 127 when the failing command is last. **Fix:** assert per-command 127 (capture status right after the missing command, or make it last); remove xfail, or delete. |
| Deeply-nested-parentheses xfail tests invalid syntax | `tests/performance/benchmarks/test_parsing_performance.py:161` (input at 162) | OBSOLETE (MED) | `echo ( ( ( ... ) )` is a syntax error in bash too; psh emits a clean parse error (no crash). The case is not meaningful. **Fix:** delete the deep_parens portion (or replace with valid deep nesting like `$(( ((((1)))) ))`); drop the xfail; the heredoc/long-line portions stand alone. |
| Advanced-arithmetic skip mislabeled "parameter expansion" | `tests/unit/expansion/test_arithmetic_integration_advanced_todo.py:12` (stray note at 68) | STALE label (LOW), real gap | The actual gap is arithmetic inside `${var:offset:length}` (`${str:1+1}` → "invalid offset"); the file also confusingly mentions "parser combinator" and "Process substitution not implemented yet". **Fix:** implement arithmetic in substring offset/length and un-skip, OR relabel precisely to "arithmetic in `${var:offset:length}` not supported" and split out the unrelated proc-sub note. Avoid the catch-all "parameter expansion not implemented" (false for most param expansion). |

### 2.3 KEEP — genuine environment constraints (tighten reasons only)

| Issue | File:line | Verdict | Notes |
|-------|-----------|---------|-------|
| PTY/pexpect line-editing & job-control block (~12 markers) | `tests/system/interactive/test_pty_job_control.py:46,74,93,147,211`; `test_line_editing.py:42`; `test_basic_interactive.py:187` | KEEP (LOW) | Genuinely env-bound: raw escape sequences, arrow keys, Ctrl-C, SIGTSTP under pexpect PTY. **Caveat:** `test_basic_interactive.py:187` reason "Line editing may not be fully supported yet" is mislabeled — line editing IS supported interactively; the real issue is pexpect/PTY flakiness. **Action:** keep skipped/xfailed; normalize reasons to "flaky/unsupported under pexpect PTY". |
| `skipif` gates for missing tools | `test_pty_*.py:40` (pexpect), `test_interactive_features.py:36`, `test_print_vs_zsh.py:16` (zsh) | KEEP (LOW) | Correct as-is; no change. |

---

## 3. Subshell `-s` Workaround Assessment

**Conclusion: the global `-s` requirement is obsolete.** Only the `read` builtin's stdin detection genuinely breaks under pytest capture; stdout-redirection subshell tests already pass under normal capture.

### 3.1 Measured reality contradicts the README

Running the full subshell suite **without** `-s` under default pytest capture (`python -m pytest tests/integration/subshells/`) yields **47 passed, 1 skipped, 1 xfailed, exactly 1 FAILED**. The single failure is `TestSubshellRedirection::test_input_redirection` (`tests/integration/subshells/test_subshell_implementation.py:249`), which reads redirected stdin via the `read` builtin. Every stdout-redirection subshell test passes.

The README's central claim (`tests/integration/subshells/README.md:31-38` — "Many tests fail with empty output files due to pytest capture interference" for stdout redirection) is **STALE**. Stdout redirection works because `echo`/`printf`/`pwd` in forked children write via `os.write(1)` after the redirection is applied with `os.dup2` to the real fd 1 (`psh/builtins/io.py:178-184`); pytest's `sys.stdout` replacement is irrelevant at the fd level. The one remaining failure is structural and fixable, not an inherent pytest limitation.

### 3.2 Root cause — `read` consults `sys.stdin` instead of the real fd

File: `/Users/pwilson/src/psh/psh/builtins/read_builtin.py:379-409`

`_read_normal()` decides between `os.read(fd)` and `sys.stdin.readline()` by calling `sys.stdin.fileno()` at line 381. Under pytest capture `sys.stdin` is pytest's `DontReadFromInput`, whose `fileno()` raises `io.UnsupportedOperation`, so `has_real_fileno=False` (line 384) → `use_sys_stdin=True` (line 387) → the code calls `sys.stdin.readline()` (line 406), triggering pytest's "reading from stdin while output is captured! Consider using -s".

This is wrong: in a subshell the `< input.txt` redirection was applied with `os.dup2(file_fd, 0)` on the **real** fd 0 in the forked child, so `os.read(0)` would correctly read the file. The decision keys off `sys.stdin` (a Python-level object pytest swaps) instead of the fd argument (0, a real OS file). Notably, `read` has **zero** forked-child awareness (no `_in_forked_child` references), unlike `echo`/`printf`/`pwd`, which all branch on `shell.state._in_forked_child` to use raw `os.read`/`os.write`. Verified correct outside pytest:
```
python -m psh -c '(while read line; do echo "Read: $line"; done) < in.txt > out.txt'
```
produces correct output.

**Recommendation:** In `_read_normal` (and the parallel logic at ~489-509 and ~591), when the target fd is a real, valid OS file descriptor, prefer `os.read(fd)` over `sys.stdin`. Concretely: before consulting `sys.stdin.fileno()`, attempt `os.fstat(fd)`; if it succeeds, set `use_sys_stdin=False` and read via `os.read(fd)`. Simpler and consistent with `echo`/`printf`: make `read` forked-child-aware — if `shell.state._in_forked_child` is True, always use `os.read(fd)`. Thread an `is_forked_child` flag (or fd-validity check) into `_read_normal`/`_read_special`/`_read_with_timeout`. This mirrors the existing pattern at `psh/builtins/io.py:178-184`.

### 3.3 Documentation cleanup after the fix

File: `tests/integration/subshells/README.md:81-90`

After fixing `read`'s fd detection, the only scenario where `-s` could still matter is a test reading from a genuinely interactive/inherited stdin (not a file/pipe redirection) inside a forked child — and no such subshell test exists (the suite only redirects stdin from files). The README's "Future Improvements" section proposes heavyweight solutions (custom pytest plugin, subprocess rewrite) that are unnecessary given the narrow root cause.

**Recommendation:** Once the `read` fix lands and `python -m pytest tests/integration/subshells/` is green without `-s`:
- Replace the README's broad "pytest capture interferes with file descriptors in forked children" explanation with the accurate statement that fd-level redirections (stdout via `os.write(1)`, stdin via `os.read(0)`) work fine under capture; the historical `-s` requirement stemmed solely from `read` choosing `sys.stdin` over the real fd.
- Remove the "must run with `-s`" notes in `CLAUDE.md` (Known Test Issues #1) and `psh/executor/CLAUDE.md` (Common Pitfalls #1).

---

## 4. Conformance-Invariant Gaps (Claimed but Untested)

The user guide asserts POSIX/bash compatibility for several features that have **zero** matching tests in `tests/conformance/posix/` or `tests/conformance/bash/`. Per the project's documented principle (a claimed conformant feature must have a conformance test), each is a gap.

| Feature | Claim location | Severity | Untested semantics |
|---------|----------------|----------|--------------------|
| `getopts` "POSIX-compliant" | `docs/user_guide/04_builtin_commands.md:1584` | HIGH | OPTIND, OPTARG, leading-colon silent-error mode, `?` handling. Zero matches for "getopts" in conformance. |
| `=~` regex / ERE in `[[ ]]` | `docs/user_guide/appendix_c_regex_reference.md:110` | HIGH | Anchors, alternation, grouping, character classes, `BASH_REMATCH` capture. No `=~`/`BASH_REMATCH`/`regex`/`ERE` test bodies. |
| `case` `;&` fallthrough & `;;&` continue-match | `docs/user_guide/11_control_structures.md:563` | HIGH | bash-specific terminators with well-defined semantics; zero matches for `;&`/`;;&`/fallthrough/continue-match. |
| `set -x` / xtrace "fully supports" | `docs/user_guide/13_shell_scripts.md:664` | MED | PS4 expansion, `+ ` trace prefix, command echo to stderr. Zero matches. May warrant `assert_documented_difference` if format differs. |
| `wait` builtin "POSIX-compliant" | `docs/user_guide/appendix_b_example_scripts.md:331` | MED | `wait PID`, bare `wait`, exit-status propagation. Zero matches. |
| `trap` "comprehensive signal handling" | `docs/user_guide/README.md:48` | MED | EXIT traps, signal traps, `trap - SIG` reset. Zero matches. |
| Pipeline-component subshell isolation "same as bash" | `docs/user_guide/10_pipelines_and_lists.md:162` | LOW | Variable assigned in a pipeline component must not leak to parent; lastpipe dependence. No test. |

**Recommended conformance tests (POSIX/bash categories):**
- `getopts` loop covering flags, options-with-args, OPTIND/OPTARG state, and silent-error leading-colon mode — `assert_identical_behavior`.
- `[[ str =~ pattern ]]` covering anchors, alternation, grouping with `BASH_REMATCH` extraction, and negation.
- `case` exercising both `;&` and `;;&` — `assert_identical_behavior`.
- `set -x`: capture stderr of a few traced commands; `assert_identical_behavior` if format matches, else `assert_documented_difference`.
- `wait`: launch background jobs, use `wait PID` and bare `wait`, assert exit-status propagation (subshell tests may need `-s` handling).
- `trap`: EXIT trap and a catchable signal (trap then send), assert handler invocation/output; or soften README wording if exact match is impractical.
- Pipeline isolation: `x=1; echo a | while read v; do x=2; done; echo $x` (and a SimpleCommand variant), noting bash default vs lastpipe.

---

## 5. Prioritized List of Recommended Test Additions

Ordered by runtime-safety value per unit of effort.

1. **Fix `read` builtin fd detection** (`read_builtin.py:379-409`) and un-skip `test_subshell_implementation.py:249` — eliminates the entire global `-s` workaround. (Section 3)
2. **In-process process-substitution tests** for `process_sub.py` — cover `>(...)` output direction, proc-sub as redirect target, child execute path, `cleanup()` (no FD leaks / zombies), and the `ValueError` case; fix the mislabeled `TestProcessSubstitution` class. (Section 1.1)
3. **`tests/unit/scripting/test_shebang_handler.py`** — `parse_shebang`, `should_execute_with_shebang` (psh self-detection, env unwrapping, PATH search), and `execute_with_shebang` error branches (127/126/1). (Section 1.2)
4. **`tests/unit/interactive/test_signal_manager.py`** — registration dispositions, trap dispatch, SIGCHLD reaping + reentrancy guard, `reset_child_signals` in a forked child, `restore_default_handlers`. (Section 1.3)
5. **Un-skip / un-xfail the stale tests:** background-subshell (`:287`), heredoc-in-function (`:116`), and rewrite history (`test_history.py`) and completion (`test_completion.py`) assertions to non-interactive `captured_shell` or proper PTY tests. (Sections 2.1)
6. **Conformance tests for HIGH claimed-but-untested features:** `getopts`, `=~`/`BASH_REMATCH`, and `case` `;&`/`;;&`. (Section 4)
7. **In-process subshell/process-launcher tests** — scope isolation, output redirection content, background `$!`/job registration, pipeline-member roles, exit-code propagation. (Section 1.4)
8. **Strengthen heredoc tests to assert content** (not just exit codes) — expansion, quoted no-expansion, `<<-` tab stripping, `<<<`, FD-restore-on-error. (Section 1.5)
9. **Conformance tests for MED features:** `wait`, `trap` (EXIT + signal), `set -x` (identical or documented-difference). (Section 4)
10. **Fix/delete WRONG-premise tests:** command-not-found-in-subshell (`:578`), deeply-nested-parentheses (`test_parsing_performance.py:161`); relabel function-as-background-job (`:171`) and the advanced-arithmetic skip. (Section 2.2)
11. **Pipeline-isolation conformance test** and **optional smoke tests** for debug/tooling modules (`__main__` via runpy, one `--debug-ast`, one help call). (Sections 4, 1.6)
