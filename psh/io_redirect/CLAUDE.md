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
| `planner.py` | `RedirectPlanner`/`RedirectPlan` - the shared resolve→expand→procsub planning phase; `plan_program` classifies a command's redirects into one ordered `RedirectProgram` |
| `redirect_program.py` | `RedirectProgram`/`RedirectOp`/`RedirectOpKind` - the typed, source-ordered redirect operation sequence and its one immediate applicator `apply_in_order` (campaign R1) |
| `input_cursor.py` | `OpenDescription` (owned open-file-description identity) + `InputCursorRegistry` (per-shell `ShellState.input_cursors`, campaign I1). `read`/`mapfile` borrow a persistent `InputCursor` (the reader in `builtins/input_reader.py`) keyed by description so a `read -N` count-boundary surplus survives across invocations. `exec 0<file` rebinds → new cursor (hook: `command.py#_rebind_input_cursors_after_exec`). SCOPED: dup-cross-fd sharing + temp-frame isolation are the deferred additive FULL fidelity; `OpenDescription` is the type R1 here-input can adopt |

## Core Patterns

### 1. IOManager Orchestration

All I/O operations go through `IOManager`:

```python
class IOManager:
    def __init__(self, shell):
        self.file_redirector = FileRedirector(shell)
        self.process_sub_handler = ProcessSubstitutionHandler(shell)
```

### 1a. One ordered `RedirectProgram`, one applicator (campaign R1)

Every dispatch site (`_apply_redirections`, `apply_permanent_redirections`,
`setup_builtin_redirections`, `setup_child_redirections`) builds ONE typed,
source-ordered program — `planner.plan_program(redirects)` — and walks it with
`RedirectProgram.apply_in_order(apply_one)`, the single semantic applicator
that applies each operation IMMEDIATELY, left-to-right. `apply_one` is the
mechanical adapter (fd universe vs Python-stream universe); the ORDER and the
per-redirect `RedirectOpKind` (OPEN_FILE / DUP_FD / CLOSE_FD / HERE_INPUT /
COMBINED / VAR_FD) are computed once, in the program. There is no
representation for a *deferred* operation — a close is applied in place, so a
later `n>&m` that dups an already-closed fd fails with bash's "Bad file
descriptor" (#20 H4; the freed-low-fd concern the old deferral guarded is
covered by relocation — `_open_output_off_low_fds`). Guards:
`tests/unit/tooling/test_redirect_program_guard_r1.py` (every site walks
`apply_in_order`; `plan_program` is the sole producer) and
`tests/unit/io_redirect/test_redirect_program_r1.py` (applicator immediacy).

### 1b. Per-redirect resolution (`RedirectPlanner` / `RedirectPlan`)

At each operation's turn the adapter resolves ONE redirect with
`planner.plan(redirect)`: resolve a dynamic fd-dup, then decide
procsub-or-filename STRUCTURALLY from the Word AST (`redirect_procsub_node`) —
a whole-word `<(cmd)`/`>(cmd)` is resolved to a resource from its node
(`resolve_procsub_resource(node)`), everything else is a filename expanded via
`expand_redirect_target`. Nothing re-sniffs the expanded string (#20 C1;
guard: the C1 tests above). Resolution stays per-operation so a substitution
fork and a file open keep bash's source-order side effects:

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

`RedirectPlan` carries `(redirect, target, procsub, procsub_node)` plus:
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

**`n>&n` self-dup leniency (bash rule, probe-verified):** a dup whose source
and target fd coincide POST-RESOLUTION (`3>&3`, `3<&3`, `3>&3-`, and
`3>&$x` with x=3) is an unconditional success no-op — no validation, no
syscall, no fd change, even when fd n is closed or never opened. The one
predicate is `redirect_program.is_self_dup`; every dup path consults it
(`_validate_dup_source`, `_redirect_dup_fd`, `saved_fds_for_plan`, the
builtin stream half in `_builtin_redirect_dup` — which still installs the
closed-stream sentinel when a CLOSED fd 1/2 is self-dup'd, so the builtin's
own write fails like bash — and the `exec` stream rebind). Pinned by
`tests/integration/redirection/test_self_dup_leniency_r1.py`. An INVALID dup
source's diagnostic names the SOURCE fd for the static spelling but the
TARGET fd for the dynamic spelling (`_bad_dup_source_error`, bash-pinned).

`ProcessSubstitutionResource` (in `process_sub.py`) owns one substitution's
`(path, parent_fd, pid, cleanup_path)`; `resolve_procsub_resource(node)` builds
it from the `ProcessSubstitution` AST node (its raw `source`/`direction`, so the
body is expanded once — by the child), and `register_with(handler)` hands
pid/cleanup-path to the enclosing
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
into bash's `<$0>: line N: TARGET: STRERROR` diagnostic and yields `False`
(so the caller skips the body and returns 1 — `|| fallback` runs, `set -e`
still aborts). The one message shape is `format_redirect_error(error, target,
location=state.error_location_prefix())`, shared by the simple-command,
subshell and function-call redirect-failure sites too, so they no longer
diverge (appraisal #15 C3). The `location` prefix is the single source of
truth every runtime diagnostic uses, so a redirect error carries bash's
`line N:` exactly like a builtin write error (campaign R1, "diagnostic source
computed once"). Only the setup is guarded — a body exception is not
misreported as a redirect error.

### 3. File Descriptor Backup/Restore

`apply_redirections` (`file_redirect.py#FileRedirector.apply_redirections`)
backs up each affected original fd before applying the new one, returning
`(original_fd, saved_fd | None)` pairs that `restore_redirections` unwinds in
reverse.

The backup does NOT use `os.dup` — every backup goes to a HIGH fd (>= 10)
via `_save_fd_high` (`fcntl.fcntl(fd, F_DUPFD, 10)`). A plain `os.dup` takes
the LOWEST free slot, which after `exec 1>&-`/`2>&-` is fd 1/2 — a slot a
stale `sys.stdout`/`sys.stderr` wrapper still names, so a builtin's write
would land in the backup instead of failing EBADF like bash, and the freed
low slot could not be reclaimed by the redirect's own `open()`. `bash` keeps
its saved descriptors above fd 10 for the same reason. `_save_fd_high`
returns None when the fd is not currently open; `restore_redirections` then
just closes the fd rather than dup2-restoring it (see
`file_redirect.py#FileRedirector._save_fd_high` and its docstring for the
full rationale).

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
   - Restore the snapshot's original stream objects
   - Close exactly the files setup opened (never whatever happens to be
     in sys.stdout — after `cmd 2>&1` that IS the shell's real stdout).
     Streams close BEFORE the fd-level restore — each stream owns its own
     fd, and a source-ordered close can free an fd NUMBER that a later
     internal dup reused; restoring first would let the stream close
     destroy the just-restored descriptor (R1 bounce blocker)
   - Restore that frame's fd-level saves
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
description** via `_rebind_output_stream` → `dup_sharing_stream(fd, 'w',
buffering=1)`. Never re-`open()` the target
independently: a second open has its own offset (and re-truncates in 'w'
mode), so builtin writes and external children would overwrite each other.
`os.dup()` shares the description (offset and O_APPEND), giving both
universes one file position; line buffering makes builtin output interleave
with externals like bash's unbuffered writes.

Process ownership (campaign F2): the first permanent redirect that touches
the standard descriptors acquires the coordinator's `STD_FDS` component
lease (`_acquire_permanent_stream_lease` — baseline = `F_DUPFD_CLOEXEC`
dups of 0/1/2 parked at fd >= 63 plus the stream snapshot). Redirects stay
permanent inside the active shell; the baseline restores when the owning
shell deactivates (`Shell.close()`/`shutdown()`), so an EMBEDDED shell
hands the host its fds/streams back, and a successful `exec` of a new
image never inherits the backups (CLOEXEC — bash-pinned by
`tests/integration/redirection/test_std_fd_lease_f2.py`). A list of only
named-fd redirects (`exec {v}>file`) takes no lease, keeping bash's
first-free->=10 allocation numbering.

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
| `redirect_input_from_file(target, redirect)` | `<` — open + dup2 to the redirect's fd (`redirect.fd`, default 0) so explicit fds like `5<file` reach the named fd, not stdin |
| `redirect_readwrite(target, redirect)` | `<>` — open O_RDWR + dup2; returns target_fd |
| `redirect_heredoc(redirect)` | `<<`/`<<-` — expand + unlinked temp file + dup2; returns content |
| `redirect_herestring(redirect)` | `<<<` — expand + unlinked temp file + dup2; returns content |
| `redirect_procsub_node(redirect)` | Return the `ProcessSubstitution` node when the target is a whole-word `<(cmd)`/`>(cmd)` (structural, from the Word AST), else None; called by the planner to decide procsub-vs-filename without sniffing the expanded string |
| `expand_redirect_target(redirect)` | Full field expansion (+ bash's ambiguous-redirect rule) for a NON-procsub filename target `<`/`>`/`>>`/`<>`/`>|`/`&>`/`&>>` (called by the planner and `apply_var_fd_redirect`) |
| `resolve_dynamic_dup(redirect)` | Resolve a dynamic fd-dup target (`>&$fd`, `2>&$((n+1))`); called by the planner |
| `noclobber_blocks(target)` | Predicate: noclobber set AND target is an existing regular file or dangling symlink (shared by all dispatchers; response differs: raise vs `os._exit`) |
| `check_noclobber(target)` | Raises OSError if `noclobber_blocks(target)`; the ONE noclobber-refusal message (all three raise sites route here) |
| `dup_fd_valid(dup_fd)` | Predicate: `dup_fd` is an open fd (for `>&`/`<&` validation) |
| `dup_sharing_stream(fd, mode, *, buffering=-1)` | The ONE dup+fdopen recipe: a text stream sharing `fd`'s open file description (one offset). OUTPUT (`'w'`, `buffering=1`) for the `exec` rebind and a builtin `n>&m` dup; INPUT (`'r'`/`'r+'`) for a builtin `<`/`<>` stdin |
| `procsub_handler` (property) | The shell's `ProcessSubstitutionHandler`; the planner resolves procsub targets through it |

**Private (internal to `file_redirect.py`):**

| Helper | Used For |
|--------|----------|
| `_redirect_output_to_file(target, redirect)` | `>`/`>>` — open + dup2; returns target_fd |
| `_redirect_clobber(target, redirect)` | `>|` — open O_TRUNC (ignore noclobber); returns target_fd |
| `_redirect_combined(target, redirect)` | `&>`/`&>>` — open + dup2(fd,1) + dup2(1,2) |
| `_redirect_dup_fd(redirect)` | `>&`/`<&` — validate + dup2 or close |
| `_redirect_close_fd(redirect)` | `>&-`/`<&-` — close fd |
| `_rebind_output_stream(fd)` | `exec >file` — point sys.stdout/stderr at a `dup_sharing_stream` of the redirected fd |

Also: `_dup2_preserve_target(opened_fd, target_fd)` is a module-level
function (not a method) that wraps `os.dup2()` + `os.close()` safely.

### Adding a New Redirection Type

1. Add a per-type helper on `FileRedirector` in `file_redirect.py`

2. Wire the new operator into `classify_redirect` (redirect_program.py) so it
   maps to the right `RedirectOpKind`, then handle that kind in each dispatch
   site's `apply_one` (`_apply_redirections`, `apply_permanent_redirections`,
   `setup_child_redirections`, `setup_builtin_redirections` — each walks
   `plan_program(...).apply_in_order(apply_one)`). Inside `apply_one` resolve
   with `self.planner.plan(redirect)` and read
   `plan.redirect`/`plan.target`/`plan.target_fd` rather than
   re-resolving/expanding, and rely on `try/finally: plan.close_procsub(
   applied=…)` for process-substitution fd cleanup.

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

Both deliver content via `_content_to_fd(content, target_fd)`
(`file_redirect.py#FileRedirector._content_to_fd`), which materializes the
body in an **anonymous (unlinked) temp file, deliberately NOT a pipe** — a
pipe would deadlock for a body larger than the kernel pipe buffer (~64KB)
because the whole body is written before any reader exists (bash uses a temp
file for the same reason). `target_fd` is the redirect's fd (default 0/stdin),
so an explicit fd prefix — `5<<EOF`, `5<<<word` — materializes the body on fd 5.

Two things the naive `os.dup2(tmp.fileno(), target_fd); tmp.close()` recipe
gets wrong, and which the real method handles: the body is written with
`errors='surrogateescape'` so non-UTF-8 bytes reach the reader unchanged
(bash byte transparency); and the temp fd is `os.dup`'d to a DISTINCT fd
BEFORE the temp object is closed and moved onto `target_fd` (via
`_dup2_preserve_target`), so a case where the temp file happens to land ON
`target_fd` (`cat 3<<EOF <&3`) can never close the very fd holding the body.

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

For a NON-procsub filename target (`<`, `>`, `>>`, `<>`, `>|`, `&>`, `&>>`),
this runs the parsed Word through the full command-argument pipeline
(variable/command/arithmetic expansion, IFS splitting of unquoted expansions,
globbing, and an embedded `pre<(cmd)post` procsub) and enforces bash's
"ambiguous redirect" rule: the result must be EXACTLY one field, or NOTHING is
opened (`psh: <word>: ambiguous redirect`, errno None). A WHOLE-WORD process
substitution never reaches here — the planner detects it structurally
(`redirect_procsub_node`) and resolves it from its AST node, so the body is
expanded exactly once, by the substitution's own child.

### Named file descriptors (`{var}>file`)

`{varname}>file` (and `{varname}<file`, `{varname}>&N`, `{varname}>&-`)
allocates a FRESH fd >= 10, performs the redirect onto it, and stores the
number in the shell variable `varname` — bash's named-fd form.
`apply_var_fd_redirect`
(`file_redirect.py#FileRedirector.apply_var_fd_redirect`) owns the form; it is
reached from all FOUR redirect-application paths:

- `manager.py:501` — `IOManager.setup_builtin_redirections` (in-process builtin);
- `manager.py:895` — `IOManager.setup_child_redirections` (forked child);
- `file_redirect.py:554` — `FileRedirector._apply_redirections` (fd-level
  save/restore window, via `IOManager.apply_redirections` / `with_redirections`);
- `file_redirect.py:699` — `FileRedirector.apply_permanent_redirections` (`exec`).

It owns all the redirect shapes of the form:

- **open** (`{v}>f`/`{v}<f`/`{v}>>f`) — open the file, then `fcntl(F_DUPFD, 10)`;
- **duplicate** (`{v}>&N`, incl. dynamic `{v}>&$x`) — dup the source high;
- **close** (`{v}>&-`/`{v}<&-`) — close the fd named by the variable (the
  variable keeps its value).

Unlike a normal per-command redirect, a named-fd allocation is PERMANENT
(parent-side, outside any save/restore window): the user closes it explicitly
with `{v}>&-`.

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

- Filename targets expanded via `expand_word_to_fields` in COMMAND_ARGUMENT
  context (full field expansion + the ambiguous-redirect rule); process-sub
  targets never reach expansion — the planner carries the AST node directly
- Heredoc content expanded based on delimiter quoting

### With Shell State (`psh/core/state.py`)

- `noclobber` option checked for `>` redirections
- Debug options control output

### With Parser (`psh/parser/`)

- `Redirect` AST nodes created with type, target, fd, heredoc_content
- `heredoc_quoted` attribute indicates if delimiter was quoted
