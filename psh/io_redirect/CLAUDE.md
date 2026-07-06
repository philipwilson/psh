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
   ↓
RedirectPlanner (shared planning phase)
```

(Heredocs and here-strings live inside `FileRedirector` — there is no
separate heredoc handler.)

The package exports `IOManager` and the `remap_fds` collision-safe
descriptor-remapping utility (`fd_remap.py`) via `__init__.py`. `remap_fds`
installs a set of source→destination fd remaps for a forked child safely even
when descriptors 0/1/2 begin closed (it promotes endpoints out of the way and
resolves remapping cycles); it is shared by the pipeline executor and command
substitution (and, per the audit, process substitution) so no fork site
reinvents the unsafe `dup2` + blanket-close recipe.

## Key Files

| File | Purpose |
|------|---------|
| `manager.py` | `IOManager` - central orchestrator for all I/O operations |
| `file_redirect.py` | `FileRedirector` - file-based redirections (`<`, `>`, `>>`, etc.) |
| `process_sub.py` | `ProcessSubstitutionHandler` + `ProcessSubstitutionResource` - process substitution (`<()`, `>()`) |
| `planner.py` | `RedirectPlanner`/`RedirectPlan` - the shared resolve→expand→procsub planning phase used by every dispatch site |

## Core Patterns

### 1. IOManager Orchestration

All I/O operations go through `IOManager`:

```python
class IOManager:
    def __init__(self, shell):
        self.file_redirector = FileRedirector(shell)
        self.process_sub_handler = ProcessSubstitutionHandler(shell)
```

### 1a. Shared Planning Phase (`RedirectPlanner` / `RedirectPlan`)

Every dispatch site (`apply_redirections`, `apply_permanent_redirections`,
`setup_builtin_redirections`, `setup_child_redirections`) begins the SAME
way: resolve a dynamic fd-dup, expand the target, and create any
process-substitution resource. That common work lives once in
`planner.py`:

```python
plan = self.planner.plan(redirect)        # FileRedirector.planner
redirect, target = plan.redirect, plan.target
applied = False
try:
    ...                                   # backend applies the redirect
    applied = True
finally:
    plan.close_procsub(applied=applied)   # release procsub parent fd
```

`RedirectPlan` carries `(redirect, target, procsub)` plus:
- `target_fd` — the single source of truth for "which fd does this
  redirect act on" (replaces the per-branch `redirect.fd if … else 0/1`
  classification).
- `close_procsub(applied=)` — delegates to the resource; closes the
  substitution's parent fd UNLESS a successful `dup2` made that fd number
  the redirect's own target. The `finally` placement is load-bearing: it
  guarantees the parent fd is released even when a *later* redirect in the
  same command raises (the pre-v0.375 unconditional close after the
  if/elif chain leaked on that path). Used by the external/permanent paths.
- `hand_procsub_to_scope(handler)` — the *other* fate of a procsub parent
  fd: instead of closing it after the redirect, hand it to the enclosing
  `process_sub_scope()` for deferred close. Used by the in-process builtin
  redirect path, where the builtin reads `/dev/fd/N` and the read end must
  outlive the single redirect.

A redirect-target substitution's parent fd has exactly these two fates, and
**both are owned by `RedirectPlan`/`ProcessSubstitutionResource`** — a
dispatch site never pokes `handler.active_fds` itself.

`ProcessSubstitutionResource` (in `process_sub.py`) owns one substitution's
`(path, parent_fd, pid, cleanup_path)`; `resolve_procsub_resource()` builds
it and `register_with(handler)` hands pid/cleanup-path to the enclosing
`process_sub_scope()`. `close_parent_fd_for_redirect()` and
`hand_off_to_scope()` are the close-vs-transfer primitives the plan delegates
to (the latter is the single place that appends to `active_fds`, shared by
word-expansion substitutions and the builtin path).

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

`guarded_redirections` is the redirect-error chokepoint for the in-process
COMPOUND commands (brace group, `if`/`for`/`while`/`until`/`case`, `[[ ]]`,
`(( ))`). It wraps `with_redirections` but turns a redirect SETUP failure
into bash's `psh: TARGET: STRERROR` diagnostic and yields `False` (so the
caller skips the body and returns 1 — `|| fallback` runs, `set -e` still
aborts). The one message shape is `format_redirect_error()`, shared by the
simple-command, subshell and function-call redirect-failure sites too, so
they no longer diverge (appraisal #15 C3). Only the setup is guarded — a
body exception is not misreported as a redirect error.

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
| `>`, `>>`, `>|`, `&>` to fd 1/2 | BOTH (stream swap for the builtin's own writes, dup2 of fd 1/2 sharing the file's description for children it spawns — `eval`/`source`/`command` running an external) | `_builtin_redirect_output_file`, `_builtin_redirect_combined` (fd half via `_dup_output_fd_for_children`) |
| `2>&1`, `1>&2` | BOTH (`sys.stderr = sys.stdout` for the builtin, dup2 of fd 2/1 for children) | `_builtin_redirect_dup` |
| `<`, `<>`, heredoc, here-string | BOTH (stream for the builtin, dup2 of fd 0 for children it spawns) | `_builtin_redirect_stdin` |
| `1>&m`, `2>&m` (m >= 3), e.g. `echo x >&3` | BOTH (dup2 for children, stream onto a dup of m's description for the builtin — sys.stdout may be a swapped file object not backed by fd 1) | `_builtin_redirect_dup` |
| dups of fd >= 3 (`3>&1`), `>&-` | fd level | `_builtin_redirect_fd_level` |

The fd-level half is per-command (dup saved on the frame, restored when the
command finishes); only `exec` rewrites fds permanently. This is why
`command ls > /dev/null`, `eval "cmd | cmd" > f`, and `source f 2>/dev/null`
now redirect the children the builtin spawns, not just the builtin's own
Python-stream writes (appraisal #15 C1).

```
1. frame = setup_builtin_redirections()
   - Returns a BuiltinRedirectFrame owning everything this invocation
     changed: a _BuiltinStreamSnapshot of the pre-redirect streams
     (first-touch-wins) and a dup of fd 0, the (fd, saved_fd) pairs from
     fd-level redirects (frame.saved_fds), and the files setup opened
     (frame.opened_streams)
   - Transactional: a failure part-way through rolls back THIS frame only
2. Execute builtin
3. restore_builtin_redirections(frame)
   - Restore that frame's fd-level saves first
   - Restore the snapshot's original stream objects
   - Close exactly the files setup opened (never whatever happens to be
     in sys.stdout — after `cmd 2>&1` that IS the shell's real stdout)
   - dup2 the saved fd 0 back
```

**Frames nest.** `eval "echo one >&3" 3>&1`, `source file 3>&1`, and trap
handlers all run further redirected builtins while an outer frame is
active, so this state is per-invocation, never manager-level (manager-level
lists conflated nested invocations before v0.302: the inner restore
drained the outer's fd saves). Frames are restored innermost-first (LIFO),
guaranteed by the paired try/finally in
`_execute_builtin_with_redirections`; the manager keeps a frame stack only
to keep that invariant observable. See
`tests/integration/redirection/test_builtin_redirect_nesting.py` for the
bash-pinned nesting battery.

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
`setup_child_redirections`, `setup_builtin_redirections`).

**Public vs private surface (v0.350+):** the helpers reused *outside*
`file_redirect.py` — by the builtin stream backend in `manager.py` and by
`planner.py` — are a deliberate **public** surface (no leading underscore);
they are the shared redirect primitives, not implementation details.
Helpers used only within `file_redirect.py` stay private.

**Public (shared) primitives:**

| Helper | Used For |
|--------|----------|
| `redirect_input_from_file(target, redirect=None)` | `<` — open + dup2 to the redirect's fd (default 0). Pass `redirect` so explicit fds like `5<file` reach the named fd, not stdin |
| `redirect_readwrite(target, redirect)` | `<>` — open O_RDWR + dup2; returns target_fd |
| `redirect_heredoc(redirect)` | `<<`/`<<-` — expand + unlinked temp file + dup2; returns content |
| `redirect_herestring(redirect)` | `<<<` — expand + unlinked temp file + dup2; returns content |
| `expand_redirect_target(redirect)` | Variable + tilde expansion for `<`/`>`/`>>`/`<>`/`>|`/`&>`/`&>>` (called by the planner) |
| `resolve_dynamic_dup(redirect)` | Resolve a dynamic fd-dup target (`>&$fd`, `2>&$((n+1))`); called by the planner |
| `noclobber_blocks(target)` | Predicate: noclobber set AND target is an existing regular file or dangling symlink (shared by all dispatchers; response differs: raise vs `os._exit`) |
| `check_noclobber(target)` | Raises OSError if `noclobber_blocks(target)` |
| `dup_fd_valid(dup_fd)` | Predicate: `dup_fd` is an open fd (for `>&`/`<&` validation) |
| `procsub_handler` (property) | The shell's `ProcessSubstitutionHandler`; the planner resolves procsub targets through it |

**Private (internal to `file_redirect.py`):**

| Helper | Used For |
|--------|----------|
| `_redirect_output_to_file(target, redirect)` | `>`/`>>` — open + dup2; returns target_fd |
| `_redirect_clobber(target, redirect)` | `>|` — open O_TRUNC (ignore noclobber); returns target_fd |
| `_redirect_combined(target, redirect)` | `&>`/`&>>` — open + dup2(fd,1) + dup2(1,2) |
| `_redirect_dup_fd(redirect)` | `>&`/`<&` — validate + dup2 or close |
| `_redirect_close_fd(redirect)` | `>&-`/`<&-` — close fd |
| `_stream_sharing_fd(fd)` / `_rebind_output_stream(fd)` | `exec >file` — Python stream sharing the redirected fd's open file description |

Also: `_dup2_preserve_target(opened_fd, target_fd)` is a module-level
function (not a method) that wraps `os.dup2()` + `os.close()` safely.

### Adding a New Redirection Type

1. Add a per-type helper on `FileRedirector` in `file_redirect.py`

2. Call the helper from `apply_redirections`, `apply_permanent_redirections`,
   `setup_child_redirections`, and `setup_builtin_redirections`. Each of these
   first calls `self.planner.plan(redirect)` (see "Shared Planning Phase"),
   so read `plan.redirect`/`plan.target`/`plan.target_fd` rather than
   re-resolving/expanding, and rely on the dispatch site's `try/finally:
   plan.close_procsub(applied=…)` for process-substitution fd cleanup.

3. Add tests in `tests/unit/io_redirect/` or `tests/integration/redirection/`

### Handling noclobber Option

Use the `check_noclobber` helper on `FileRedirector`:
```python
self.check_noclobber(target)  # Raises OSError if noclobber_blocks(target)
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

Both deliver content via `_content_to_fd(content, target_fd)`, which uses an
**anonymous (unlinked) temp file, deliberately NOT a pipe**. `target_fd` is
the redirect's fd (default 0/stdin), so an explicit fd prefix — `5<<EOF`,
`5<<<word` — materializes the body on fd 5 instead, matching bash:

```python
# A pipe would deadlock for content larger than the kernel pipe buffer
# (~64KB) because the whole body is written before any reader exists.
# Bash uses a temp file for heredocs for the same reason.
tmp = tempfile.TemporaryFile()
tmp.write(content.encode())
tmp.seek(0)
os.dup2(tmp.fileno(), target_fd)  # target_fd = redirect.fd or 0
tmp.close()  # target_fd keeps the underlying file open
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

(Sketch only. The real implementation forks via
`fork_with_signal_window()` and runs the whole child branch through the
shared runner `run_child_shell()` — both in `executor/child_policy.py` —
with the dup2 plumbing above passed as its `io_setup` hook.)

### Variable Expansion in Targets

Use the `expand_redirect_target` helper on `FileRedirector`:
```python
target = self.expand_redirect_target(redirect)
# or from IOManager:
target = self.file_redirector.expand_redirect_target(redirect)
```

This expands variables (unless single-quoted) and tilde for all
file-target redirect types: `<`, `>`, `>>`, `<>`, `>|`, and the combined
forms `&>`/`&>>` (see the `redirect.type`/`redirect.combined` guard at the
top of `expand_redirect_target` in `file_redirect.py`).

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
