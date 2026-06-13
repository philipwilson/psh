# Redirection / IO Architecture Review

Date: 2026-06-13

Scope: `psh/io_redirect/`, with integration checks in `psh/executor/command.py`, `psh/executor/strategies.py`, `psh/executor/pipeline.py`, and `psh/executor/process_launcher.py` where those subsystems decide how redirections are applied.

## Verification

Focused executor/redirection run:

```sh
python -m pytest tests/unit/executor tests/unit/io_redirect tests/integration/redirection tests/integration/pipeline tests/integration/subshells tests/integration/job_control tests/integration/command_resolution/test_hash_execution.py tests/regression/test_visitor_executor_review_fixes.py -q
```

Result:

```text
2 failed, 531 passed, 1 skipped in 24.88s
```

Failures:

```text
FAILED tests/unit/io_redirect/test_fd_operations.py::TestDynamicDupTarget::test_dup_stdout_to_arithmetic_fd
FAILED tests/integration/redirection/test_process_sub_cleanup.py::TestProcessSubOutputCorrectness::test_write_side_substitution_tee
```

The first failure reproduced directly:

```sh
python -m psh -c 'exec 3>/dev/stdout; echo hi >&$((1+2)); exec 3>&-'
```

Output:

```text
psh: /dev/stdout: Operation not permitted
psh: 3: Bad file descriptor
```

The second failure also reproduced directly:

```sh
python -m psh -c 'echo data | tee >(cat > /tmp/psh_psub_codex_check.txt) >/dev/null'
```

Output:

```text
tee: /dev/fd/4: Operation not permitted
```

This environment is macOS with Python 3.14.2. The failures point at portability and ownership issues around `/dev/fd` paths, not at the general redirection test suite being broken.

## Executive Verdict

Redirection/IO is one of the hardest parts of a Python shell because PSH has to support two I/O worlds at once:

- external commands and forked children write through kernel file descriptors;
- in-process builtins often write through Python stream objects, which may be `StringIO` under tests or embedding.

The current code understands that distinction and documents it unusually well. The `BuiltinRedirectFrame` design is a real improvement: builtin redirection setup is transactional, nestable, and restores exactly the frame it changed.

It is not textbook quality yet. The remaining complexity is structural: redirect dispatch is duplicated across multiple paths, stream/fd ownership is implicit in several private helpers, process substitution relies on `/dev/fd/N` paths that are not portable enough, and some `exec` permanent-redirect paths appear to leave Python stdin streams stale.

Quality rating by area:

| Area | Rating | Direction | Short version |
| --- | --- | --- | --- |
| Conceptual model | Good | Improved | The two-universe model is right and documented. |
| Builtin redirection frames | Good | Improved | Transactional and nestable, with careful restore behavior. |
| File descriptor redirection | Adequate to good | Stable | Correct helpers, but duplicated dispatch and private coupling. |
| Permanent `exec` redirection | Adequate | Improving | Output rebinding is strong; stdin rebinding looks incomplete. |
| Process substitution | Adequate | Risky | Scoped cleanup is good; `/dev/fd` write-side portability is failing. |
| Error handling | Adequate | Stable | Parent vs child behavior is separated, but child dispatch duplicates policy. |
| Test coverage | Strong | Improving | Many important regressions covered; current focused run found two real failures. |

## What Is Strong

### 1. The two-universe model is correct

`IOManager` explicitly distinguishes fd-level redirection from Python stream swapping (`psh/io_redirect/manager.py:3`). Builtins need stream redirection when they run in-process; external commands need fd-level redirection after fork. This is the central architectural truth for a Python shell.

The command dispatcher uses that distinction when deciding how to run builtins, functions, external commands, and pipeline members (`psh/executor/command.py:392`).

### 2. Builtin redirection frames are the right abstraction

`BuiltinRedirectFrame` records the pre-redirection stream snapshot, fd-level saves, and exactly the file objects opened by one setup invocation (`psh/io_redirect/manager.py:102`). `setup_builtin_redirections()` returns a frame, and `restore_builtin_redirections()` consumes that frame (`psh/io_redirect/manager.py:173`, `psh/io_redirect/manager.py:354`).

This is a significant quality point. Nested `eval`, `source`, and trap handlers make manager-level global save lists unsafe; frames are the correct fix.

### 3. Restore logic is order-aware and conservative

Fd restoration reverses the saved list so repeated redirects of the same fd restore the original (`psh/io_redirect/file_redirect.py:291`). Builtin stream restoration restores saved stream objects before closing files opened by the frame (`psh/io_redirect/manager.py:379`). That avoids closing the shell's real stdout/stderr by mistake after stream duplication.

### 4. Heredocs and here-strings use temp-file stdin, not pipes

`_stdin_from_content()` uses a temporary file and then dup2s it onto fd 0 (`psh/io_redirect/file_redirect.py:88`). This avoids deadlocks for large heredocs, and the integration tests include a large heredoc case.

### 5. Noclobber and dynamic fd duplication have named helpers

`_noclobber_blocks()` centralizes the regular-file/dangling-symlink rule (`psh/io_redirect/file_redirect.py:30`). `_resolved()` centralizes dynamic fd duplication targets such as `>&$fd` and `>&$((n+1))` (`psh/io_redirect/file_redirect.py:133`).

These are the right kind of small semantic helpers.

### 6. Process substitutions have scoped ownership

`ProcessSubstitutionHandler.scope()` records active fd/pid marks and cleans up only substitutions created inside that scope (`psh/io_redirect/process_sub.py:164`). That nesting model is important for cases like functions consuming process-substitution arguments.

## Current Test Failures

### Failure 1: dynamic dup to `/dev/stdout` fails on this platform

Test:

```text
tests/unit/io_redirect/test_fd_operations.py:95
```

Command:

```sh
exec 3>/dev/stdout; echo hi >&$((1+2)); exec 3>&-
```

Observed:

```text
psh: /dev/stdout: Operation not permitted
psh: 3: Bad file descriptor
```

This appears to be a platform/filesystem behavior difference for opening `/dev/stdout` from this process context. The dynamic arithmetic fd resolution itself is not necessarily the failing piece; the setup `exec 3>/dev/stdout` fails before `echo hi >&3` can work.

Recommended change:

- Make the test avoid `/dev/stdout`; use a temporary file or a pipe-backed helper so it tests dynamic fd duplication, not `/dev/stdout` writability.
- Separately add a platform-characterization test for `/dev/stdout`, `/dev/fd/1`, and `/proc/self/fd/1` behavior where available.
- Consider an internal fd-path resolver that prefers direct fd duplication over reopening `/dev/stdout` when the target denotes an already-open descriptor.

### Failure 2: write-side process substitution fails through `/dev/fd/N`

Test:

```text
tests/integration/redirection/test_process_sub_cleanup.py:202
```

Command:

```sh
echo data | tee >(cat > file) >/dev/null
```

Observed:

```text
tee: /dev/fd/4: Operation not permitted
```

`create_process_substitution()` creates a pipe and returns `/dev/fd/{parent_fd}` (`psh/io_redirect/process_sub.py:11`, `psh/io_redirect/process_sub.py:80`). For `>(cmd)`, the parent side is the write end of the pipe (`psh/io_redirect/process_sub.py:30`). On this environment, external `tee` cannot open that `/dev/fd/N` path for writing.

Recommended change:

- Add a portability layer for process-substitution fd paths.
- On platforms where reopening `/dev/fd/N` write ends is not permitted, consider using named FIFOs for `>(...)` or pass inherited fds in a way the external command can use without reopening an incompatible fd path.
- Add platform probes at startup or test setup for:
  - read-side `/dev/fd/N` process substitution;
  - write-side `/dev/fd/N` process substitution;
  - reopening pipe read/write ends through `/dev/fd`.

## Remaining Uglies

### Ugly 1: redirect dispatch is duplicated across parent fd, permanent fd, builtin stream, and child fd paths

The same redirect type matrix is implemented in several places:

- builtin stream/fd hybrid path: `IOManager.setup_builtin_redirections()` (`psh/io_redirect/manager.py:173`);
- forked child path: `IOManager.setup_child_redirections()` (`psh/io_redirect/manager.py:410`);
- temporary parent fd path: `FileRedirector._apply_redirections()` (`psh/io_redirect/file_redirect.py:235`);
- permanent `exec` path: `FileRedirector.apply_permanent_redirections()` (`psh/io_redirect/file_redirect.py:343`).

Each branch has slightly different error behavior and ownership rules, which is expected. But the dispatch matrix itself is duplicated. Adding a redirect form or fixing a semantic edge now requires auditing four implementations.

Recommended change:

1. Introduce a `RedirectPlan` per redirect:
   - resolved redirect
   - expanded target
   - target fd
   - operation kind
   - process-substitution parent fd, if any
2. Use backend objects:
   - `ParentFdBackend`
   - `ChildFdBackend`
   - `BuiltinStreamBackend`
   - `PermanentExecBackend`
3. Keep backend-specific error behavior, but share classification and target expansion.

This would remove most dispatch duplication without flattening the necessary differences.

### Ugly 2: explicit input-fd redirection diverges across paths

The parent fd path handles `N<file` correctly by passing the redirect object into `_redirect_input_from_file()` (`psh/io_redirect/file_redirect.py:248`). The child path drops the explicit fd and calls `_redirect_input_from_file(target)` (`psh/io_redirect/manager.py:432`). The builtin path does the same for `<` (`psh/io_redirect/manager.py:243`).

That means a construct like `cmd 5<file` can behave differently depending on whether the command runs through the parent fd path, the forked-child path, or the builtin stream path. Heredoc and here-string helpers also hard-code fd 0 (`psh/io_redirect/file_redirect.py:104`, `psh/io_redirect/file_redirect.py:112`), so `5<<EOF` / `5<<<x` style redirects need explicit auditing.

Recommended change:

- Fix child and builtin `<` handling to pass the full `redirect`.
- Add a target-fd parameter to heredoc/here-string materialization.
- Add cross-path tests for explicit input fds:
  - external command: `python -c ... 5<file`
  - builtin/function path with `read -u 5` if supported, or a helper that spawns a child while fd 5 is open
  - permanent `exec 5<file`
  - heredoc/here-string with explicit fd.

### Ugly 3: `IOManager` calls `FileRedirector` private methods heavily

`IOManager.setup_builtin_redirections()` calls `_resolved()`, `_expand_redirect_target()`, `_check_noclobber()`, `_redirect_input_from_file()`, `_redirect_readwrite()`, `_redirect_heredoc()`, `_redirect_herestring()`, and `apply_redirections()` (`psh/io_redirect/manager.py:196`, `psh/io_redirect/manager.py:230`, `psh/io_redirect/manager.py:281`, `psh/io_redirect/manager.py:340`).

The coupling is understandable, but it means `FileRedirector` is not really a private implementation behind `IOManager`; it is a semi-public redirect primitive library with underscore names.

Recommended change:

- Rename stable primitives or move them into a `redirect_ops.py` module:
  - `resolve_dynamic_dup()`
  - `expand_redirect_target()`
  - `open_output_redirect()`
  - `apply_input_redirect()`
  - `materialize_heredoc_stdin()`
- Keep `FileRedirector` as one backend, not as the owner of primitives every other backend reaches into.

### Ugly 4: process-substitution ownership is implicit and fragile

For redirect targets, `resolve_procsub_target()` returns `(fd_path, parent_fd)` and the caller must close or transfer the fd correctly (`psh/io_redirect/process_sub.py:125`). Builtin redirection appends the fd to `active_fds` (`psh/io_redirect/manager.py:216`); parent fd paths close it via `_close_procsub_parent_fd()` (`psh/io_redirect/file_redirect.py:418`); child redirection closes it in a `finally` (`psh/io_redirect/manager.py:420`).

That protocol is documented, but it is easy to get wrong because ownership is represented by a raw integer plus comments.

Recommended change:

- Return a small object:
  - `ProcessSubstitutionResource(path, fd, pid, ownership)`
  - methods: `keep_until_scope_exit()`, `close_after_dup(targets)`, `release_to_child()`
- Make scope registration and closing methods explicit rather than appending raw fds to `active_fds` in callers.

### Ugly 5: process-substitution fds can leak on redirect setup failure

In `FileRedirector._apply_redirections()`, a process substitution target is resolved before the redirect branch runs (`psh/io_redirect/file_redirect.py:241`), but `_close_procsub_parent_fd()` is called only after the branch succeeds (`psh/io_redirect/file_redirect.py:285`). `apply_permanent_redirections()` has the same structure (`psh/io_redirect/file_redirect.py:361`, `psh/io_redirect/file_redirect.py:403`).

If opening the target or applying a later redirect fails, normal fd restoration runs, but the just-created process-substitution parent fd may not be closed promptly. The pid is registered for reaping, but the parent fd ownership path is incomplete on failure.

Recommended change:

- Wrap each redirect application after `resolve_procsub_target()` in a per-redirect `try/finally`.
- In the `finally`, close or transfer the process-substitution fd based on an explicit ownership state.
- A `ProcessSubstitutionResource` object would make this much harder to miss.

### Ugly 6: permanent stdin redirection does not appear to rebind `sys.stdin`

For permanent output redirects, `_rebind_output_stream()` replaces `sys.stdout`/`sys.stderr`, `shell.stdout`/`shell.stderr`, and state streams with stream objects sharing the redirected fd (`psh/io_redirect/file_redirect.py:328`). That is a strong design.

For permanent input redirects, `apply_permanent_redirections()` dup2s fd 0 and then sets `shell.stdin = sys.stdin` and `state.stdin = sys.stdin` (`psh/io_redirect/file_redirect.py:371`). But `sys.stdin` itself was not reopened onto fd 0 in that branch. Unless some other layer replaces `sys.stdin`, in-process builtins that read from `sys.stdin` may continue using the old Python stream object even though fd 0 changed.

Recommended change:

- Add `_rebind_input_stream()` mirroring output rebinding:
  - close/replace only owned duplicated stream objects;
  - create a text stream from `os.dup(0)`;
  - update `sys.stdin`, `shell.stdin`, and `state.stdin`.
- Add explicit tests for:
  - `exec < file; read x; echo "$x"`
  - `exec 5< file` does not affect stdin;
  - input redirection followed by an external child and then a builtin read.

### Ugly 7: stream redirection opens files separately from fd redirection in some builtin paths

For in-process builtins, output file redirection opens a Python file object and swaps `sys.stdout` or `sys.stderr` (`psh/io_redirect/manager.py:273`). That is appropriate for stream-only builtin output. But for redirects involving `1>&m` or `2>&m`, the code also does fd-level redirection and then creates a stream from `os.dup(redirect.dup_fd)` (`psh/io_redirect/manager.py:323`).

The policy is correct but hard to audit because some builtin redirects affect only streams, some affect only fds, and some affect both. This is exactly why the module docstring is long.

Recommended change:

- Encode the builtin redirect dispatch table as data, not prose:
  - redirect type
  - fd range
  - stream action
  - fd action
  - opened resource owner
- Generate or drive the setup from that table.

That would make the two-universe rules mechanically visible.

### Ugly 8: child redirection error paths duplicate low-level diagnostics

`setup_child_redirections()` writes error messages directly with `os.write()` and exits with `os._exit(1)` for some cases (`psh/io_redirect/manager.py:410`). That is necessary in a child process, but the logic duplicates conditions also present in `FileRedirector`.

Recommended change:

- Raise typed redirect errors from shared classification/open helpers.
- Have child backend translate those typed errors to fd-2 writes and `_exit(1)`.
- Have parent backend translate them to Python exceptions.

This would keep parent/child behavior different without duplicating semantic checks.

### Ugly 9: `/dev/fd` is treated as universal enough for process substitution

`create_process_substitution()` always returns `/dev/fd/{parent_fd}` (`psh/io_redirect/process_sub.py:80`). Current tests show that is not robust for write-side substitutions on this platform. Bash can rely on platform-specific support or use alternative mechanisms; PSH needs an explicit portability strategy.

Recommended change:

- Add a process-substitution transport abstraction:
  - `DevFdTransport`
  - `FifoTransport`
  - possibly `ProcSelfFdTransport` on Linux
- Probe capabilities once.
- Use read-side and write-side probes separately.
- Keep the current `/dev/fd` path as the fast path where supported.

## Suggested Refactor Sequence

1. Fix or quarantine the two failing tests by separating true semantic failures from platform fd-path assumptions.
2. Add a small capability probe for `/dev/fd` read/write reopening.
3. Introduce `ProcessSubstitutionResource` to make fd ownership explicit.
4. Fix explicit input-fd handling across child, builtin, heredoc, and here-string paths.
5. Extract redirect target resolution/classification into a shared `RedirectPlan`.
6. Implement backend-specific application from plans: parent fd, child fd, builtin stream, permanent exec.
7. Add `_rebind_input_stream()` and tests for permanent stdin redirection.
8. Convert the builtin two-universe dispatch table from prose to executable data or at least a table-driven policy function.

## Bottom Line

The redirection subsystem is sophisticated and correctness-oriented. The frame model for builtin redirections and the scoped process-substitution cleanup are strong. It is not textbook quality because too much redirect classification is duplicated, too many ownership rules are implicit, and the process-substitution transport currently assumes `/dev/fd` behavior that failed in the focused run. The next quality jump should be a shared redirect planning layer plus an explicit process-substitution transport/ownership model.
