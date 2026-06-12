# I/O Redirect Public API Reference

**As of v0.179.0** (post-cleanup)

This document describes the public API of the `psh.io_redirect` package:
the items declared in `__all__`, their signatures, and guidance on
internal classes that are available but not part of the public contract.

## Public API (`__all__`)

The declared public API consists of one item:

```python
__all__ = ['IOManager']
```

### `IOManager`

```python
from psh.io_redirect import IOManager

io_manager = IOManager(shell)
```

Central orchestrator for all I/O redirection operations.  Constructed
once by `Shell.__init__()` and stored as `shell.io_manager`.  All
external access goes through `IOManager` methods -- no other class in
the package is imported by production code outside `psh/io_redirect/`.

#### Constructor

```python
IOManager(shell: Shell)
```

Creates the manager and initialises three sub-handlers:

- `self.file_redirector` -- `FileRedirector` instance for file-based
  redirections.
- `self.heredoc_handler` -- `HeredocHandler` instance for interactive
  heredoc content collection (safety-net fallback).
- `self.process_sub_handler` -- `ProcessSubstitutionHandler` instance
  for `<(cmd)` and `>(cmd)`.

#### Temporary redirections (compound commands, subshells)

| Method | Signature | Description |
|--------|-----------|-------------|
| `with_redirections` | `(redirects: List[Redirect]) -> ContextManager` | Context manager that applies redirections on entry and restores on exit.  No-ops when `redirects` is empty. |
| `apply_redirections` | `(redirects: List[Redirect]) -> List[Tuple[int, int]]` | Apply redirections at the FD level, returning `(original_fd, saved_fd)` pairs for later restoration.  Delegates to `FileRedirector`. |
| `restore_redirections` | `(saved_fds: List[Tuple[int, int]]) -> None` | Restore file descriptors from a list returned by `apply_redirections`. |

#### Permanent redirections (exec builtin)

| Method | Signature | Description |
|--------|-----------|-------------|
| `apply_permanent_redirections` | `(redirects: List[Redirect]) -> None` | Apply redirections permanently, updating `sys.stdout`/`sys.stderr`/`sys.stdin` and shell stream references.  No save/restore. |

#### Builtin command redirections

| Method | Signature | Description |
|--------|-----------|-------------|
| `setup_builtin_redirections` | `(command: Command) -> Tuple[stdin_backup, stdout_backup, stderr_backup, stdin_fd_backup]` | Redirect Python file objects (`sys.stdin`, `sys.stdout`, `sys.stderr`) for builtin execution.  Returns backup objects for restoration. |
| `restore_builtin_redirections` | `(stdin_backup, stdout_backup, stderr_backup, stdin_fd_backup=None) -> None` | Restore original Python file objects after builtin execution.  Closes redirected file handles and cleans up process substitution resources. |

#### Child process redirections

| Method | Signature | Description |
|--------|-----------|-------------|
| `setup_child_redirections` | `(command: Command) -> None` | Set up redirections in a child process after `fork()`.  Uses raw `os.open()` / `os.dup2()`.  Errors write to fd 2 and call `os._exit(1)` rather than raising. |

#### Process substitution

| Method | Signature | Description |
|--------|-----------|-------------|
| `setup_process_substitutions` | `(command: Command) -> Tuple[List[int], List[str], List[int]]` | Set up `<(cmd)` and `>(cmd)` substitutions for a command.  Returns `(fds, paths, pids)`. |
| `cleanup_process_substitutions` | `() -> None` | Close process substitution file descriptors and wait for child processes. |

## Internal Classes (not in `__all__`)

These classes are not exported by the package but are used internally.
They can be imported from their defining modules for testing or
advanced use, but their signatures may change without notice.

### `FileRedirector`

```python
from psh.io_redirect.file_redirect import FileRedirector
```

Handles file-based I/O redirections at the FD level.  Provides the
shared redirect helpers that all dispatch methods use:

| Helper | Purpose |
|--------|---------|
| `_redirect_input_from_file(target)` | `<` -- open file and dup2 to stdin. |
| `_redirect_heredoc(redirect)` | `<<`/`<<-` -- create pipe, write expanded content, dup2 to stdin.  Returns content string. |
| `_redirect_herestring(redirect)` | `<<<` -- create pipe, write expanded string + newline, dup2 to stdin.  Returns content string. |
| `_redirect_output_to_file(target, redirect, check_noclobber=True)` | `>`/`>>` -- open file and dup2 to target fd.  Returns `target_fd`. |
| `_redirect_dup_fd(redirect)` | `>&`/`<&` -- validate source fd and dup2, or close if target is `-`. |
| `_redirect_close_fd(redirect)` | `>&-`/`<&-` -- close the specified fd. |
| `_expand_redirect_target(redirect)` | Expand variables (unless single-quoted) and tilde for `<`, `>`, `>>` targets. |
| `_check_noclobber(target)` | Raise `OSError` if `noclobber` option is set and target file exists. |

Also provides:

| Method | Purpose |
|--------|---------|
| `apply_redirections(redirects)` | Apply redirections with save/restore.  Used by `IOManager.with_redirections()`. |
| `restore_redirections(saved_fds)` | Restore saved FDs and Python file objects. |
| `apply_permanent_redirections(redirects)` | Apply redirections permanently (for `exec`). |

### `_dup2_preserve_target`

```python
from psh.io_redirect.file_redirect import _dup2_preserve_target
```

Module-level function.  Wraps `os.dup2(opened_fd, target_fd)` followed
by `os.close(opened_fd)`, but skips both operations when the FDs are
already equal (avoiding an accidental close of the target).

### `HeredocHandler`

```python
from psh.io_redirect.heredoc import HeredocHandler
```

Safety-net fallback for interactive heredoc content collection.  In
practice, the parser pre-populates `redirect.heredoc_content` during
parsing, so the handler's `_read_heredoc_content()` method is rarely
reached.

### `ProcessSubstitutionHandler`

```python
from psh.io_redirect.process_sub import ProcessSubstitutionHandler
```

Manages `<(cmd)` and `>(cmd)` process substitutions.  Tracks active
file descriptors and child PIDs for cleanup.

### `create_process_substitution`

```python
from psh.io_redirect.process_sub import create_process_substitution

parent_fd, fd_path, child_pid = create_process_substitution(
    cmd_str, direction, shell
)
```

Module-level function (not a method) that creates a single process
substitution.  Used by both `ProcessSubstitutionHandler` and
`FileRedirector._handle_process_sub_redirect()`.  This was
consolidated from duplicated fork/pipe/exec code in v0.166.0.

| Parameter | Type | Description |
|-----------|------|-------------|
| `cmd_str` | `str` | The command to execute (without `<()`/`>()` wrapper). |
| `direction` | `str` | `'in'` for `<(cmd)` (parent reads), `'out'` for `>(cmd)` (parent writes). |
| `shell` | `Shell` | The parent shell instance. |

Returns `(parent_fd, fd_path, child_pid)` where `fd_path` is
`/dev/fd/N`.

## Deleted in v0.179.0

The following items were removed entirely as dead code (zero callers):

| Item | Was on | Replacement |
|------|--------|-------------|
| `IOManager.collect_heredocs(node)` | `IOManager` | Heredocs are populated by the parser; no replacement needed. |
| `IOManager.handle_heredoc(delimiter, content, strip_tabs)` | `IOManager` | Dead code.  No replacement. |
| `IOManager.cleanup_temp_files()` | `IOManager` | Only used by `handle_heredoc()`.  No replacement. |
| `IOManager.is_valid_fd(fd)` | `IOManager` | Use `fcntl.fcntl(fd, fcntl.F_GETFD)` directly. |
| `IOManager._is_heredoc_delimiter_quoted(delimiter)` | `IOManager` | Use `redirect.heredoc_quoted` attribute instead. |
| `HeredocHandler.collect_heredocs(node)` | `HeredocHandler` | Dead code.  No replacement. |
| `HeredocHandler.create_heredoc_file(content, strip_tabs)` | `HeredocHandler` | Dead code.  No replacement. |
| `HeredocHandler.expand_variables_in_heredoc(content, delimiter)` | `HeredocHandler` | Expansion is done inline via `_redirect_heredoc()` helper. |

## Typical Usage

### Apply temporary redirections

```python
# Via context manager (preferred)
with shell.io_manager.with_redirections(command.redirects):
    execute_body()

# Manual apply/restore
saved = shell.io_manager.apply_redirections(redirects)
try:
    execute_body()
finally:
    shell.io_manager.restore_redirections(saved)
```

### Redirect builtins

```python
backups = shell.io_manager.setup_builtin_redirections(command)
try:
    result = builtin.execute(args, shell)
finally:
    shell.io_manager.restore_builtin_redirections(*backups)
```

### Redirect in child process

```python
pid = os.fork()
if pid == 0:
    shell.io_manager.setup_child_redirections(command)
    os.execvp(args[0], args)
```

### Permanent redirections (exec)

```python
shell.io_manager.apply_permanent_redirections(redirects)
```

## Related Documents

- `docs/guides/io_redirect_guide.md` -- Full programmer's guide
  (architecture, file reference, design rationale)
- `docs/guides/io_redirect_public_api_assessment.md` -- Analysis that
  led to this cleanup
- `psh/io_redirect/CLAUDE.md` -- AI assistant working guide for the
  I/O redirect subsystem
