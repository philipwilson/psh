# PSH I/O Redirect: Programmer's Guide

> **Note (2026-06-11):** This guide describes the tree as of ~v0.27x, before
> the v0.285 module relocation and subsequent cleanups. In particular it
> references `psh/token_types.py`, which has since moved to `psh/lexer/token_types.py`.
> See the subsystem CLAUDE.md files for current structure.

This guide covers the I/O redirect package in detail: its external API,
internal architecture, and the responsibilities of every source file.  It is
aimed at developers who need to modify redirection behaviour, add new
redirect types, or understand how shell redirections are applied at the
file-descriptor level.

## 1. What the I/O Redirect Package Does

The I/O redirect package converts `Redirect` AST nodes into actual
file-descriptor operations.  It handles:

- **File redirections** -- `< file`, `> file`, `>> file`
- **Here documents** -- `<< DELIM`, `<<- DELIM`
- **Here strings** -- `<<< string`
- **FD duplication** -- `2>&1`, `<& N`
- **FD close** -- `>&-`, `<&-`
- **Process substitution** -- `<(cmd)`, `>(cmd)`
- **noclobber enforcement** -- `set -C` / `set -o noclobber`

The package does **not** parse redirect syntax (that is the parser's job) or
expand arguments (that is the expansion engine's job, though the package does
call into the expansion manager for redirect targets and heredoc content).

## 2. External API

The public interface is defined in `psh/io_redirect/__init__.py`.  The
declared `__all__` contains a single item: `IOManager`.  See
`docs/guides/io_redirect_public_api.md` for full signature documentation.

### 2.1 `IOManager`

```python
from psh.io_redirect import IOManager

io_manager = IOManager(shell)
```

Central orchestrator constructed once by `Shell.__init__()` and stored as
`shell.io_manager`.  All external code accesses redirections through
`IOManager` methods.

The key methods, grouped by use case:

**Temporary redirections** (compound commands, subshells):
- `with_redirections(redirects)` -- context manager for apply/restore.
- `apply_redirections(redirects)` / `restore_redirections(saved_fds)` --
  manual apply/restore when a context manager is not suitable.

**Permanent redirections** (exec builtin):
- `apply_permanent_redirections(redirects)` -- no save/restore.

**Builtin command redirections**:
- `setup_builtin_redirections(command)` -- redirects Python file objects.
- `restore_builtin_redirections(...)` -- restores them.

**Child process redirections**:
- `setup_child_redirections(command)` -- raw FD operations after `fork()`.

**Process substitution**:
- `setup_process_substitutions(command)` -- set up `<(cmd)` / `>(cmd)`.
- `cleanup_process_substitutions()` -- close FDs and wait for children.


## 3. Architecture

### 3.1 Component structure

```
IOManager (orchestrator)
     |
     +-- FileRedirector      file-based redirections, shared helpers
     +-- HeredocHandler       interactive heredoc fallback
     +-- ProcessSubstitutionHandler   <(cmd) and >(cmd)
```

`IOManager` delegates to its sub-handlers.  `FileRedirector` contains the
shared per-type redirect helpers that all dispatch paths use.
`ProcessSubstitutionHandler` manages the fork/pipe lifecycle for process
substitutions.  `HeredocHandler` is a minimal safety net for interactive
heredoc content collection.

### 3.2 Four redirect dispatch paths

Redirections are applied in four different contexts, each with different
requirements:

| Path | Method | FD ops | Python objects | Save/restore | Error handling |
|------|--------|--------|---------------|-------------|---------------|
| **Temporary** | `FileRedirector.apply_redirections()` | `os.open` + `dup2` | Save/restore `state.stdout/stderr/stdin` | Yes (returns saved FDs) | Raise `OSError` |
| **Permanent** | `FileRedirector.apply_permanent_redirections()` | `os.open` + `dup2` | Update `sys.stdout`/`shell.stdout`/`state.stdout` | No | Raise `OSError` |
| **Builtin** | `IOManager.setup_builtin_redirections()` | `os.dup` for stdin FD backup | Redirect `sys.stdin`/`sys.stdout`/`sys.stderr` | Yes (returns backup tuple) | Raise `OSError` |
| **Child** | `IOManager.setup_child_redirections()` | `os.open` + `dup2` | None (post-fork, pre-exec) | No | `os.write(2, ...)` + `os._exit(1)` |

All four paths use shared helpers on `FileRedirector` for the per-type
redirect logic (see section 3.3), but differ in how they manage
save/restore, Python file objects, and error handling.

### 3.3 Shared redirect helpers

`FileRedirector` provides per-type helpers that encapsulate the core FD
operations for each redirect type.  These are used by all four dispatch
paths:

| Helper | Redirect type | What it does |
|--------|--------------|-------------|
| `_redirect_input_from_file(target)` | `<` | `os.open(target, O_RDONLY)` + `dup2` to fd 0. |
| `_redirect_heredoc(redirect)` | `<<`, `<<-` | Create pipe, expand content (unless quoted delimiter), write to pipe, `dup2` read end to fd 0.  Returns content string. |
| `_redirect_herestring(redirect)` | `<<<` | Create pipe, expand target (unless single-quoted), write + `\n`, `dup2` read end to fd 0.  Returns content string. |
| `_redirect_output_to_file(target, redirect, check_noclobber=True)` | `>`, `>>` | Noclobber check (optional), `os.open()` with `O_TRUNC` or `O_APPEND`, `dup2` to target fd.  Returns `target_fd`. |
| `_redirect_dup_fd(redirect)` | `>&`, `<&` | Validate source fd with `fcntl`, then `os.dup2()`.  Handles `target == '-'` as fd close. |
| `_redirect_close_fd(redirect)` | `>&-`, `<&-` | `os.close(redirect.fd)`. |

Two additional helpers handle pre-processing:

| Helper | Purpose |
|--------|---------|
| `_expand_redirect_target(redirect)` | Expand variables (unless single-quoted) and tilde in targets for `<`, `>`, `>>` redirections. |
| `_check_noclobber(target)` | Raise `OSError` if `noclobber` option is set and target exists. |

And one module-level function:

| Function | Purpose |
|----------|---------|
| `_dup2_preserve_target(opened_fd, target_fd)` | `os.dup2()` + `os.close()` wrapper that no-ops when FDs already match. |

### 3.4 Redirect execution flow

For a simple command like `echo hello > file.txt`:

```
Parser produces:  SimpleCommand(args=["echo", "hello"],
                                redirects=[Redirect(type='>', target='file.txt')])
                                 |
                                 v
Executor calls:   io_manager.with_redirections(command.redirects)
                                 |
                                 v
IOManager calls:  file_redirector.apply_redirections(redirects)
                                 |
                                 v
FileRedirector:   1. _expand_redirect_target(redirect)  -> 'file.txt'
                  2. os.dup(1) -> saved_fd               (backup stdout)
                  3. _redirect_output_to_file('file.txt', redirect)
                     -> _check_noclobber('file.txt')
                     -> os.open('file.txt', O_WRONLY|O_CREAT|O_TRUNC)
                     -> _dup2_preserve_target(fd, 1)
                                 |
                                 v
                  [echo builtin writes to fd 1, which now points to file.txt]
                                 |
                                 v
FileRedirector:   restore_redirections([(1, saved_fd)])
                  -> os.dup2(saved_fd, 1)                (restore stdout)
                  -> os.close(saved_fd)
```

### 3.5 Builtin vs external command redirections

The fundamental difference:

- **External commands** run in a child process after `fork()`.  Redirections
  use raw FD operations (`os.open` + `os.dup2`).  There is no need to
  save/restore because the child process exits after execution.

- **Builtin commands** run in the current process.  Redirections must modify
  Python file objects (`sys.stdout`, `sys.stderr`, `sys.stdin`) because
  builtins write through Python I/O.  The original file objects must be
  saved and restored after the builtin completes.

`setup_builtin_redirections()` handles this by:

1. Backing up `sys.stdin`, `sys.stdout`, `sys.stderr` references.
2. For stdin redirections (`<`, `<<`, `<<<`): also backing up fd 0 with
   `os.dup(0)`, because some builtins use `os.read(0, ...)` directly.
3. For stdout/stderr redirections (`>`, `>>`): opening a Python file object
   pointing to the target file and assigning it to `sys.stdout`/`sys.stderr`.
4. For FD duplication (`2>&1`): reassigning Python file objects.

`restore_builtin_redirections()` reverses all of this, closing any
redirected file handles and restoring the originals.

### 3.6 Process substitution

`<(cmd)` and `>(cmd)` create a pipe, fork a child to run `cmd`, and
return a `/dev/fd/N` path that the parent can open like a regular file.

The lifecycle:

1. **`create_process_substitution(cmd_str, direction, shell)`** -- module-level
   function that creates the pipe, forks the child, and returns
   `(parent_fd, fd_path, child_pid)`.

2. **`ProcessSubstitutionHandler`** -- tracks active FDs and PIDs, provides
   `setup_process_substitutions()` for argument-position process subs and
   `handle_redirect_process_sub()` for redirect-target process subs.

3. **Cleanup** -- `cleanup()` closes parent FDs and waits for child PIDs.
   Called automatically by `restore_builtin_redirections()` and explicitly
   by the expansion manager.

### 3.7 noclobber handling

The `noclobber` option (`set -C`) prevents `>` from overwriting existing
files.  The `>>` (append) and `>|` (force) operators are exempt.

Implementation differs by context:

- **Parent process** (apply_redirections, setup_builtin_redirections,
  apply_permanent_redirections): `_check_noclobber(target)` raises
  `OSError`, which propagates to the executor's error handler.

- **Child process** (setup_child_redirections): cannot raise (would crash
  the child without proper error reporting).  Instead writes the error
  message to fd 2 with `os.write()` and calls `os._exit(1)`.

### 3.8 FD validation ordering

A subtle correctness requirement: when saving a file descriptor for later
restoration (`os.dup(redirect.fd)`), the saved copy may be allocated the
same FD number as `redirect.dup_fd`.  If `dup_fd` was previously closed,
`os.dup()` reuses it, making validation pass incorrectly.

The solution in `apply_redirections()`: validate `dup_fd` with
`fcntl.fcntl(dup_fd, F_GETFD)` **before** calling `os.dup(redirect.fd)`.

## 4. Source File Reference

All files are under `psh/io_redirect/`.

### 4.1 Package entry point

#### `__init__.py` (~4 lines)

Imports `IOManager` from `manager.py` and declares `__all__ = ['IOManager']`.
This is the only file external code needs to import from.

### 4.2 Core orchestrator

#### `manager.py` (~235 lines)

The `IOManager` class.  Initialises three sub-handlers (`FileRedirector`,
`HeredocHandler`, `ProcessSubstitutionHandler`).  Provides the public
methods that the executor calls:

- `with_redirections()` -- context manager delegating to `FileRedirector`.
- `apply_redirections()` / `restore_redirections()` -- thin wrappers around
  `FileRedirector` methods.
- `apply_permanent_redirections()` -- delegates to `FileRedirector`.
- `setup_builtin_redirections()` -- redirects Python file objects for
  builtin commands.  Uses `FileRedirector` helpers for FD work and manages
  `sys.stdin`/`sys.stdout`/`sys.stderr` Python objects.
- `restore_builtin_redirections()` -- restores Python file objects, closes
  redirected handles, restores fd 0 if backed up.
- `setup_child_redirections()` -- applies redirections in a child process
  using `FileRedirector` helpers.  Errors write to fd 2 + `os._exit(1)`.
- `setup_process_substitutions()` / `cleanup_process_substitutions()` --
  delegates to `ProcessSubstitutionHandler`.

### 4.3 File redirection engine

#### `file_redirect.py` (~225 lines)

`FileRedirector` class and the `_dup2_preserve_target()` module-level
function.

`FileRedirector` provides:

- **Six per-type redirect helpers** (`_redirect_input_from_file`,
  `_redirect_heredoc`, `_redirect_herestring`, `_redirect_output_to_file`,
  `_redirect_dup_fd`, `_redirect_close_fd`) -- the shared implementation
  for each redirect type, used by all four dispatch paths.

- **Two pre-processing helpers** (`_expand_redirect_target`,
  `_check_noclobber`) -- shared logic extracted from formerly duplicated
  code.

- **Three dispatch methods**:
  - `apply_redirections(redirects)` -- saves FDs, applies redirections via
    helpers, returns saved list.
  - `restore_redirections(saved_fds)` -- restores FDs and Python file
    objects.
  - `apply_permanent_redirections(redirects)` -- applies via helpers,
    updates `sys.stdout`/`sys.stderr`/`sys.stdin` and shell stream
    references.

- **`_handle_process_sub_redirect(target, redirect)`** -- handles
  `<(cmd)` / `>(cmd)` appearing as a redirect target, delegating to
  `create_process_substitution()`.

Instance state:
- `_saved_stdout`, `_saved_stderr`, `_saved_stdin` -- backup slots for
  Python file objects during temporary redirections.  Set in
  `apply_redirections()`, cleared in `restore_redirections()`.

### 4.4 Heredoc handler

#### `heredoc.py` (~40 lines)

`HeredocHandler` class.  A minimal safety net for interactive heredoc
content collection.  Contains a single method:

- `_read_heredoc_content(redirect)` -- reads lines from `input()` until
  the delimiter is found.  Skipped if `redirect.heredoc_content` is already
  populated (which it always is in practice, since the parser pre-populates
  it during the tokenize/parse pipeline).

The three public methods that formerly existed (`collect_heredocs`,
`create_heredoc_file`, `expand_variables_in_heredoc`) were deleted in
v0.179.0 as dead code.

### 4.5 Process substitution

#### `process_sub.py` (~205 lines)

Two components:

**`create_process_substitution(cmd_str, direction, shell)`** -- module-level
function (the single source of truth for all process substitution creation,
consolidated in v0.166.0):

1. Creates a pipe.
2. Forks a child process.
3. Child: applies signal policy, sets up stdio, tokenizes/parses/executes
   the command in a temporary shell, exits.
4. Parent: closes the child's pipe end, returns `(parent_fd, fd_path, pid)`.

**`ProcessSubstitutionHandler`** -- class that provides:

- `setup_process_substitutions(command)` -- scans command arguments for
  `<(cmd)` / `>(cmd)` patterns, creates process substitutions, returns
  `(fds, substituted_args, pids)`.
- `handle_redirect_process_sub(target)` -- creates a process substitution
  for a redirect target, returns `(path, fd_to_close, pid)`.
- `cleanup()` -- closes all tracked FDs and waits for all tracked PIDs.


## 5. Common Tasks

### 5.1 Adding a new redirection type

1. **Token type** -- add a `TokenType` member in `psh/token_types.py` and
   the operator string to `OPERATORS_BY_LENGTH` in `psh/lexer/constants.py`.

2. **Parser** -- handle the new operator in
   `RedirectionParser.parse_redirect()` in
   `psh/parser/recursive_descent/parsers/redirections.py`.

3. **Per-type helper** -- add a `_redirect_new_type()` method on
   `FileRedirector` in `file_redirect.py`.

4. **Dispatch paths** -- call the helper from all four dispatch methods:
   - `FileRedirector.apply_redirections()`
   - `FileRedirector.apply_permanent_redirections()`
   - `IOManager.setup_child_redirections()`
   - `IOManager.setup_builtin_redirections()`

5. **Tests** -- add tests in `tests/unit/io_redirect/` and
   `tests/integration/redirection/`.

### 5.2 Modifying noclobber behaviour

The noclobber check is centralised in `FileRedirector._check_noclobber()`.
To change the behaviour (e.g. supporting `>|` force-overwrite), modify this
method and any child-process inline checks in
`IOManager.setup_child_redirections()`.

### 5.3 Adding a new expansion to redirect targets

Variable and tilde expansion for redirect targets is centralised in
`FileRedirector._expand_redirect_target()`.  To add a new expansion type
(e.g. brace expansion), modify this method.

### 5.4 Debugging redirections

```bash
python -m psh --debug-exec -c "echo hello > /tmp/test.txt 2>&1"
```

Output includes:
```
DEBUG IOManager: setup_builtin_redirections called
DEBUG IOManager: Redirects: [('>', '/tmp/test.txt', None), ('>&', None, 1)]
DEBUG IOManager: Redirected stdout to file '/tmp/test.txt'
```


## 6. Design Rationale

### Why are there four dispatch paths instead of one?

The four paths serve fundamentally different contexts:

- **Temporary** needs FD save/restore.
- **Permanent** (exec) modifies FDs without restoring.
- **Builtin** must redirect Python file objects, not just raw FDs, because
  builtins write through `print()` / `sys.stdout`.
- **Child** runs after `fork()` where errors cannot be raised (must write
  to fd 2 and `_exit`).

While these could theoretically be unified with a mode parameter, the
differences in error handling and Python-object management make a clean
unification difficult without introducing fragile branching.  The current
design uses shared per-type helpers to eliminate the actual redirect logic
duplication, while keeping the dispatch-level differences explicit.

### Why is `_dup2_preserve_target` a module-level function?

It has no `self` reference -- it operates purely on two integer FD
arguments.  Making it module-level avoids the need for a `@staticmethod`
on multiple classes and lets any code in the package call it directly.

### Why does `FileRedirector` own the saved Python file objects?

Before v0.179.0, saved file objects were stored as `shell._saved_stdout`
etc. -- private attributes written onto the Shell instance, creating hidden
coupling.  Moving them to `FileRedirector._saved_stdout` keeps the state
co-located with the code that uses it.

### Why does `HeredocHandler` still exist?

Its only active code path (`_read_heredoc_content`) is a fallback for
interactive heredoc content collection.  In practice, the two-pass
lexer/parser system (`tokenize_with_heredocs` + `parse_with_heredocs`)
always pre-populates `redirect.heredoc_content` before execution reaches
the I/O redirect package.  The handler is kept as a defensive safety net
for edge cases where heredoc content might not be pre-populated.

### Why is `create_process_substitution` a module-level function?

It was consolidated from ~130 lines of duplicated fork/pipe/exec code
across three files (v0.166.0).  As a module-level function, it is callable
from both `ProcessSubstitutionHandler` and `FileRedirector` without
requiring either class to import the other.

### Why does `apply_redirections` validate dup_fd before saving?

This prevents a subtle bug: `os.dup(redirect.fd)` allocates the lowest
available FD number.  If `redirect.dup_fd` was just closed (e.g. by
`exec 3>&-`), `os.dup()` may reuse that FD number for the saved copy,
making validation of `dup_fd` pass incorrectly.  Validating first catches
the "bad file descriptor" error at the right time.


## 7. File Dependency Graph

```
__init__.py
└── manager.py  (IOManager)
    ├── file_redirect.py  (FileRedirector, _dup2_preserve_target)
    │   └── process_sub.py  (create_process_substitution — via lazy import)
    ├── heredoc.py  (HeredocHandler)
    └── process_sub.py  (ProcessSubstitutionHandler, create_process_substitution)

External dependencies (outside the io_redirect package):
- psh/ast_nodes.py       — Redirect, Command, SimpleCommand
- psh/core/state.py      — ShellState (options, stdout/stderr/stdin)
- psh/expansion/manager.py — expand_string_variables(), expand_tilde()
- psh/lexer/             — tokenize() (used by create_process_substitution)
- psh/parser/            — parse() (used by create_process_substitution)
- psh/executor/child_policy.py — apply_child_signal_policy() (process sub)
```

## 8. Integration Points

### With Executor (`psh/executor/`)

- `with_redirections()` is called by `ExecutorVisitor` for compound commands
  (if, while, for, case, brace groups, subshells).
- `setup_builtin_redirections()` / `restore_builtin_redirections()` are
  called by `CommandExecutor` around builtin execution.
- `setup_child_redirections()` is called by `ProcessLauncher` and
  `ExternalExecutionStrategy` after `fork()`.
- `apply_permanent_redirections()` is called by `CommandExecutor` for the
  `exec` builtin.

### With Expansion (`psh/expansion/`)

- `setup_process_substitutions()` is called by `ExpansionManager` before
  command execution to substitute `<(cmd)` / `>(cmd)` arguments with
  `/dev/fd/N` paths.
- Redirect targets are expanded via `expansion_manager.expand_string_variables()`
  and `expansion_manager.expand_tilde()` through the `_expand_redirect_target()`
  helper.
- Heredoc content is expanded via `expansion_manager.expand_string_variables()`
  inside `_redirect_heredoc()` (unless the delimiter was quoted).

### With Shell State (`psh/core/state.py`)

- `noclobber` option checked via `state.options.get('noclobber', False)`.
- `debug-exec` option controls debug logging.
- `state.stdout` / `state.stderr` / `state.stdin` are saved/restored by
  `FileRedirector`.

### With Parser (`psh/parser/`)

- `Redirect` AST nodes are created by `RedirectionParser` with fields:
  `type`, `target`, `fd`, `dup_fd`, `heredoc_content`, `heredoc_quoted`,
  `quote_type`.
- `heredoc_content` and `heredoc_quoted` are populated during parsing
  (either inline or via `parse_with_heredocs()`).
