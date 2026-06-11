# I/O Redirection Subsystem

This document provides guidance for working with the PSH I/O redirection subsystem.

## Architecture Overview

The I/O subsystem handles all file descriptor redirections including file redirections, heredocs, here strings, and process substitutions.

```
IOManager (orchestrator)
     ↓
┌────┴──────────┐
↓               ↓
File          Process
Redirector    SubHandler
```

(Heredocs and here-strings live inside `FileRedirector` — there is no
separate heredoc handler.)

The package exports only `IOManager` via `__init__.py`.

## Key Files

| File | Purpose |
|------|---------|
| `manager.py` | `IOManager` - central orchestrator for all I/O operations |
| `file_redirect.py` | `FileRedirector` - file-based redirections (`<`, `>`, `>>`, etc.) |
| `process_sub.py` | `ProcessSubstitutionHandler` - process substitution (`<()`, `>()`) |

## Core Patterns

### 1. IOManager Orchestration

All I/O operations go through `IOManager`:

```python
class IOManager:
    def __init__(self, shell):
        self.file_redirector = FileRedirector(shell)
        self.process_sub_handler = ProcessSubstitutionHandler(shell)
```

### 2. Context Manager for Temporary Redirections

```python
@contextmanager
def with_redirections(self, redirects: List[Redirect]):
    """Apply redirections temporarily, then restore."""
    saved_fds = self.apply_redirections(redirects)
    try:
        yield
    finally:
        self.restore_redirections(saved_fds)
```

### 3. File Descriptor Backup/Restore

```python
def apply_redirections(self, redirects) -> List[Tuple[int, int]]:
    """Apply redirections, returning (original_fd, saved_fd) pairs."""
    saved = []
    for redirect in redirects:
        # Backup original fd
        saved_fd = os.dup(redirect.fd)
        saved.append((redirect.fd, saved_fd))
        # Apply new redirection
        ...
    return saved

def restore_redirections(self, saved_fds):
    """Restore original file descriptors."""
    for original_fd, saved_fd in reversed(saved_fds):
        os.dup2(saved_fd, original_fd)
        os.close(saved_fd)
```

## Redirection Types

### Input Redirections

| Syntax | Type | Description |
|--------|------|-------------|
| `< file` | `<` | Read stdin from file |
| `<> file` | `<>` | Open file for read-write (POSIX) |
| `<< DELIM` | `<<` | Here document |
| `<<- DELIM` | `<<-` | Here document (strip tabs) |
| `<<< string` | `<<<` | Here string |

### Output Redirections

| Syntax | Type | Description |
|--------|------|-------------|
| `> file` | `>` | Write stdout to file (truncate) |
| `>> file` | `>>` | Append stdout to file |
| `>| file` | `>|` | Force overwrite, ignore noclobber (POSIX) |
| `&> file` | `&>` | Redirect stdout+stderr to file (bash) |
| `&>> file` | `&>>` | Append stdout+stderr to file (bash) |
| `2> file` | `>` (fd=2) | Write stderr to file |
| `2>> file` | `>>` (fd=2) | Append stderr to file |

### File Descriptor Operations

| Syntax | Type | Description |
|--------|------|-------------|
| `2>&1` | `>&` | Redirect stderr to stdout |
| `>&2` | `>&` | Redirect stdout to stderr |
| `n>&m` | `>&` | Duplicate fd m to fd n |

### Pipe Operations

| Syntax | Type | Description |
|--------|------|-------------|
| `cmd1 \| cmd2` | `\|` | Pipe stdout only |
| `cmd1 \|& cmd2` | `\|&` | Pipe stdout+stderr (bash) |

### Process Substitution

| Syntax | Direction | Description |
|--------|-----------|-------------|
| `<(cmd)` | Input | Command output as input file |
| `>(cmd)` | Output | File that feeds command input |

## Redirection Flow

### For External Commands (Child Process)

```
1. Fork child process
2. In child: setup_child_redirections()
   - Open files with os.open()
   - Redirect with os.dup2()
   - Close original fds
3. Exec external command
4. Parent waits for child
```

### For Builtin Commands — the two redirection universes

Builtins run *in-process* and write through Python stream objects
(`sys.stdout`/`shell.stdout`), which may not be backed by fd 1 at all
(capture buffers in tests); external children inherit real fds. So
`setup_builtin_redirections` dispatches each redirect to the right
universe — the full design rationale is the module docstring of
`manager.py` (read it before touching this code):

| Redirect | Universe | Helper |
|----------|----------|--------|
| `>`, `>>`, `>|`, `&>` to fd 1/2 | stream swap | `_builtin_redirect_output_file`, `_builtin_redirect_combined` |
| `2>&1`, `1>&2` | stream swap (`sys.stderr = sys.stdout`) | `_builtin_redirect_dup` |
| `<`, `<>`, heredoc, here-string | BOTH (stream for the builtin, dup2 of fd 0 for children it spawns) | `_builtin_redirect_stdin` |
| fd >= 3, other `n>&m`, `>&-` | fd level | `_builtin_redirect_fd_level` |

```
1. setup_builtin_redirections()
   - _BuiltinStreamSnapshot records pre-redirect streams (first-touch-wins)
     and a dup of fd 0; opened files accumulate in _opened_streams
   - Transactional: a failure part-way through rolls everything back
2. Execute builtin
3. restore_builtin_redirections()
   - Restore fd-level saves (_saved_fds_list) first
   - Restore the snapshot's original stream objects
   - Close exactly the files setup opened (never whatever happens to be
     in sys.stdout — after `cmd 2>&1` that IS the shell's real stdout)
   - dup2 the saved fd 0 back
```

### For `exec` (Permanent Redirections)

`apply_permanent_redirections` (FileRedirector) does the fd-level redirect
first, then rebinds the Python-level stream onto the **same open file
description** via `_rebind_output_stream` → `_stream_sharing_fd`
(`os.fdopen(os.dup(fd), 'w', buffering=1)`). Never re-`open()` the target
independently: a second open has its own offset (and re-truncates in 'w'
mode), so builtin writes and external children would overwrite each other.
`os.dup()` shares the description (offset and O_APPEND), giving both
universes one file position; line buffering makes builtin output interleave
with externals like bash's unbuffered writes.

## Common Tasks

### Per-Type Redirect Helpers

`FileRedirector` provides shared helpers used by all redirect dispatch
methods (`apply_redirections`, `apply_permanent_redirections`,
`setup_child_redirections`, `setup_builtin_redirections`):

| Helper | Used For |
|--------|----------|
| `_redirect_input_from_file(target)` | `<` — open + dup2 to stdin |
| `_redirect_readwrite(target, redirect)` | `<>` — open O_RDWR + dup2; returns target_fd |
| `_redirect_heredoc(redirect)` | `<<`/`<<-` — expand + unlinked temp file + dup2; returns content |
| `_redirect_herestring(redirect)` | `<<<` — expand + unlinked temp file + dup2; returns content |
| `_redirect_output_to_file(target, redirect)` | `>`/`>>` — open + dup2; returns target_fd |
| `_redirect_clobber(target, redirect)` | `>|` — open O_TRUNC (ignore noclobber); returns target_fd |
| `_redirect_combined(target, redirect)` | `&>`/`&>>` — open + dup2(fd,1) + dup2(1,2) |
| `_redirect_dup_fd(redirect)` | `>&`/`<&` — validate + dup2 or close |
| `_redirect_close_fd(redirect)` | `>&-`/`<&-` — close fd |
| `_expand_redirect_target(redirect)` | Variable + tilde expansion for `<`/`>`/`>>`/`<>`/`>|`/`&>`/`&>>` |
| `_noclobber_blocks(target)` | Predicate: noclobber set AND target is an existing regular file or dangling symlink (shared by all dispatchers; response differs: raise vs `os._exit`) |
| `_stream_sharing_fd(fd)` / `_rebind_output_stream(fd)` | `exec >file` — Python stream sharing the redirected fd's open file description |
| `_check_noclobber(target)` | Raises OSError if `_noclobber_blocks(target)` |
| `_dup_fd_valid(dup_fd)` | Predicate: `dup_fd` is an open fd (for `>&`/`<&` validation) |

Also: `_dup2_preserve_target(opened_fd, target_fd)` is a module-level
function (not a method) that wraps `os.dup2()` + `os.close()` safely.

### Adding a New Redirection Type

1. Add a per-type helper on `FileRedirector` in `file_redirect.py`

2. Call the helper from `apply_redirections`, `apply_permanent_redirections`,
   `setup_child_redirections`, and `setup_builtin_redirections`

3. Add tests in `tests/unit/io_redirect/` or `tests/integration/redirection/`

### Handling noclobber Option

Use the `_check_noclobber` helper on `FileRedirector`:
```python
self._check_noclobber(target)  # Raises OSError if _noclobber_blocks(target)
```

The bash rule (probe-verified): noclobber blocks `>` only when the target
is an existing **regular** file (directly or through a symlink) or a
dangling symlink. Non-regular targets — `/dev/null`, devices, FIFOs — are
always writable, because opening them for write destroys nothing. `>|` and
`>>` are never blocked.

Exception: child-process noclobber in `setup_child_redirections` uses
`os.write(2, ...)` + `os._exit(1)` instead of raising.

## Key Implementation Details

### Heredoc Processing

```python
# Quoted delimiter: no expansion
<<'EOF'     # heredoc_quoted = True
<<"EOF"     # heredoc_quoted = True

# Unquoted delimiter: expand variables
<<EOF       # heredoc_quoted = False

# In handler:
if not heredoc_quoted:
    content = shell.expansion_manager.expand_string_variables(content)
```

### Heredoc / Here String Delivery

Both deliver content to stdin via `_stdin_from_content()`, which uses an
**anonymous (unlinked) temp file, deliberately NOT a pipe**:

```python
# A pipe would deadlock for content larger than the kernel pipe buffer
# (~64KB) because the whole body is written before any reader exists.
# Bash uses a temp file for heredocs for the same reason.
tmp = tempfile.TemporaryFile()
tmp.write(content.encode())
tmp.seek(0)
os.dup2(tmp.fileno(), 0)
tmp.close()  # fd 0 keeps the underlying file open
```

### Process Substitution

```python
# <(cmd) creates:
# 1. Pipe
# 2. Fork child to run cmd
# 3. Return /dev/fd/N path

read_fd, write_fd = os.pipe()
pid = os.fork()
if pid == 0:  # Child
    os.close(read_fd)
    os.dup2(write_fd, 1)  # stdout to pipe
    # Execute command
    os._exit(exit_code)
else:  # Parent
    os.close(write_fd)
    return f"/dev/fd/{read_fd}"
```

### Variable Expansion in Targets

Use the `_expand_redirect_target` helper on `FileRedirector`:
```python
target = self._expand_redirect_target(redirect)
# or from IOManager:
target = self.file_redirector._expand_redirect_target(redirect)
```

This expands variables (unless single-quoted) and tilde for all
file-target redirect types: `<`, `>`, `>>`, `<>`, `>|`, and the combined
forms `&>`/`&>>` (see the `redirect.type`/`redirect.combined` guard at the
top of `_expand_redirect_target` in `file_redirect.py`).

## Testing

```bash
# Run I/O unit tests
python -m pytest tests/unit/io_redirect/ -v

# Run redirection integration tests
python -m pytest tests/integration/redirection/ -v

# Debug redirections
python -m psh --debug-exec -c "echo hello > /tmp/test.txt"
```

## Common Pitfalls

1. **File Descriptor Leaks**: Always close duplicated fds after use.

2. **Backup Order**: Backup fds before any redirections; restore in reverse order.

3. **Builtin vs External**: Builtins use Python file objects; external commands use raw fds.

4. **Heredoc Expansion**: Remember: quoted delimiter = no expansion.

5. **Pipe Cleanup**: Close unused pipe ends in both parent and child.

6. **noclobber Check**: Must check before opening file, not after.

7. **Process Substitution Ownership**: Substitutions are owned by an
   enclosing `process_sub_scope()` (zombie/fd leak fixed in v0.288). The
   scope records marks into `active_fds`/`active_pids` on entry; on exit it
   closes the parent-side fds registered inside it and reaps finished
   children with `WNOHANG` (still-running children are parked in
   `pending_pids` and re-polled at later scope exits). Scopes nest, so a
   command inside a redirected loop body cleans up only its own
   substitutions. Do NOT clean up in `restore_builtin_redirections` — a
   builtin inside a function called with a `<(...)` argument must not close
   the caller's still-needed fd.

## Debug Options

```bash
python -m psh --debug-exec -c "echo hello > output.txt"
```

Output example (IOManager lines appear only for builtins — external
commands redirect after fork, in the child):
```
DEBUG IOManager: setup_builtin_redirections called
DEBUG IOManager: Redirects: [('>', 'output.txt', None)]
DEBUG IOManager: redirected stdout to 'output.txt' (mode 'w'); sys.stdout is now <_io.TextIOWrapper name='output.txt' mode='w' encoding='UTF-8'>
```

## Integration Points

### With Executor (`psh/executor/`)

- Called during command execution for all redirections
- `ProcessLauncher` calls `setup_child_redirections()` after fork
- Builtins use `setup_builtin_redirections()` / `restore_builtin_redirections()`

### With Expansion (`psh/expansion/`)

- Redirect targets expanded via `expansion_manager.expand_string_variables()`
- Tilde expanded via `expansion_manager.expand_tilde()`
- Heredoc content expanded based on delimiter quoting

### With Shell State (`psh/core/state.py`)

- `noclobber` option checked for `>` redirections
- Debug options control output

### With Parser (`psh/parser/`)

- `Redirect` AST nodes created with type, target, fd, heredoc_content
- `heredoc_quoted` attribute indicates if delimiter was quoted
