# I/O Redirect Public API Assessment

**As of v0.178.0** (all recommendations implemented in v0.179.0)

This document assesses the public API surface of the `psh/io_redirect/`
package, catalogues every exported symbol, maps the caller graph, and
recommends improvements.

## 1. Package Overview

| File | Lines | Classes / Functions |
|------|-------|---------------------|
| `__init__.py` | 0 | Empty — no `__all__`, no imports |
| `manager.py` | 441 | `IOManager` |
| `file_redirect.py` | 341 | `FileRedirector` |
| `heredoc.py` | 129 | `HeredocHandler` |
| `process_sub.py` | 205 | `ProcessSubstitutionHandler`, `create_process_substitution()` |
| **Total** | **1,116** | **4 classes + 1 module function** |

## 2. Current Import Patterns

The `__init__.py` is empty. All consumers import directly from submodules:

```python
# The only production import (in psh/shell.py):
from .io_redirect.manager import IOManager

# TYPE_CHECKING only (in psh/executor/process_launcher.py):
from ..io_redirect.manager import IOManager
```

No test files import from `psh.io_redirect` at all — all testing goes
through `shell.io_manager`.

**Effective public API**: The single entry point is `shell.io_manager`
(an `IOManager` instance), constructed in `Shell.__init__()`. All
external access goes through `IOManager` methods.

## 3. IOManager Method Caller Map

### Tier 1: Production methods with external callers

| Method | Callers | Files |
|--------|---------|-------|
| `with_redirections(redirects)` | 10 call sites | `executor/command.py`, `executor/control_flow.py`, `executor/core.py`, `executor/subshell.py` |
| `apply_redirections(redirects)` | 4 call sites | `shell.py`, `executor/subshell.py` |
| `restore_redirections(saved_fds)` | 4 call sites | `shell.py`, `executor/subshell.py` |
| `setup_builtin_redirections(command)` | 1 call site | `executor/command.py` |
| `restore_builtin_redirections(...)` | 1 call site | `executor/command.py` |
| `setup_child_redirections(command)` | 3 call sites | `executor/process_launcher.py`, `executor/strategies.py` |
| `apply_permanent_redirections(redirects)` | 1 call site | `executor/command.py` |
| `setup_process_substitutions(command)` | 1 call site | `expansion/manager.py` |
| `cleanup_process_substitutions()` | 0 external | Only called inside `restore_builtin_redirections()` |

### Tier 2: Zero external callers (dead public methods on IOManager)

| Method | Lines | Notes |
|--------|-------|-------|
| `collect_heredocs(node)` | 2 | Delegates to `HeredocHandler`. Zero callers anywhere in production or tests. |
| `handle_heredoc(delimiter, content, strip_tabs)` | 30 | Creates temp files. Zero callers anywhere. |
| `cleanup_temp_files()` | 9 | Cleans up `_temp_files` list. Zero callers. `_temp_files` is only populated by `handle_heredoc()` which also has zero callers. |
| `is_valid_fd(fd)` | 9 | Zero callers anywhere in production or tests. |
| `_is_heredoc_delimiter_quoted(delimiter)` | 5 | Private. Zero callers. |

### Tier 3: Zero external callers (dead methods on sub-handlers)

| Class | Method | Notes |
|-------|--------|-------|
| `HeredocHandler` | `collect_heredocs(node)` | Only called by `IOManager.collect_heredocs()`, which itself has zero callers. |
| `HeredocHandler` | `create_heredoc_file(content, strip_tabs)` | Zero callers anywhere. |
| `HeredocHandler` | `expand_variables_in_heredoc(content, delimiter)` | Zero callers anywhere. Expansion is done inline in `manager.py` and `file_redirect.py` instead. |

## 4. Code Duplication Analysis

The package has significant internal duplication. The same redirection
logic is implemented in three parallel code paths:

### 4.1 Three-way duplication of the full redirect dispatch

Each redirection type (`<`, `>`, `>>`, `<<`, `<<-`, `<<<`, `>&`, `<&`,
`>&-`, `<&-`) is handled in **three** separate methods:

| Code path | Method | Lines | Used by |
|-----------|--------|-------|---------|
| **FD-level temporary** | `FileRedirector.apply_redirections()` | 120 | `with_redirections()` context manager, subshell setup |
| **FD-level child** | `IOManager.setup_child_redirections()` | 122 | Child process after fork |
| **Python-object builtin** | `IOManager.setup_builtin_redirections()` | 142 | Builtin commands |

Additionally, `FileRedirector.apply_permanent_redirections()` (152 lines)
is a fourth copy for `exec` builtin redirections.

**Total**: ~536 lines of redirection dispatch across 4 methods, handling
the same set of redirect types with near-identical logic.

### 4.2 Duplicated target expansion preamble

The following 8-line block (expand variables, expand tilde) appears
**6 times** across `manager.py` and `file_redirect.py`:

```python
target = redirect.target
if target and redirect.type in ('<', '>', '>>'):
    if hasattr(redirect, 'quote_type') and redirect.quote_type == "'":
        pass
    else:
        target = self.shell.expansion_manager.expand_string_variables(target)
    if target.startswith('~'):
        target = self.shell.expansion_manager.expand_tilde(target)
```

### 4.3 Duplicated `_dup2_preserve_target` static method

Defined identically on both `IOManager` and `FileRedirector`. The
`IOManager` copy is used by `setup_builtin_redirections()` and
`setup_child_redirections()`. The `FileRedirector` copy is used by
`apply_redirections()` and `apply_permanent_redirections()`.

### 4.4 Duplicated noclobber check

The noclobber check (`self.state.options.get('noclobber', False) and
os.path.exists(target)`) appears **5 times** across `manager.py` (3)
and `file_redirect.py` (2).

### 4.5 Duplicated process substitution redirect handling

Process substitution as a redirect target (`<(cmd)` / `>(cmd)` in
target position) is handled in three places:
- `IOManager.setup_builtin_redirections()` (lines 96–104)
- `IOManager.setup_child_redirections()` (lines 268–273)
- `FileRedirector._handle_process_sub_redirect()` (lines 330–340)

### 4.6 Duplicated heredoc/here-string pipe creation

The heredoc pipe pattern (create pipe, write content, close write end,
dup2 read end to stdin) appears **6 times**: twice in
`IOManager.setup_builtin_redirections()`, twice in
`IOManager.setup_child_redirections()`, and twice in
`FileRedirector.apply_redirections()`.

## 5. Architectural Observations

### 5.1 The delegation pattern is inconsistent

`IOManager` delegates `apply_redirections` and `restore_redirections` to
`FileRedirector`, but implements `setup_builtin_redirections` and
`setup_child_redirections` directly — duplicating all the redirect-type
dispatch logic that `FileRedirector` also contains.

### 5.2 `HeredocHandler` is largely vestigial

`HeredocHandler.collect_heredocs()` walks the AST to collect heredoc
content interactively. This predates the two-pass lexer/parser heredoc
system (`tokenize_with_heredocs` + `parse_with_heredocs`), which now
populates `redirect.heredoc_content` before execution. The handler's
three public methods all have zero callers.

The only `HeredocHandler` code path that actually executes is the
fallback `_read_heredoc_content()` for interactive mode, but even that
is gated behind `if redirect.heredoc_content is not None: return` and
never triggered in practice.

### 5.3 `_saved_fds_list` is created ad-hoc

In `setup_builtin_redirections()`, `self._saved_fds_list` is created
via `hasattr` checks rather than being initialized in `__init__()`.
This is fragile — the attribute only exists if certain redirect types
were processed.

### 5.4 `FileRedirector` stores state on `Shell` directly

`FileRedirector.apply_redirections()` saves Python file objects as
`self.shell._saved_stdout` / `_saved_stderr` / `_saved_stdin` — writing
private attributes onto the Shell instance. This creates hidden coupling.

### 5.5 Module-level function in `process_sub.py`

`create_process_substitution()` is a module-level function rather than
a method, which is appropriate since it's used by both
`ProcessSubstitutionHandler` and `FileRedirector`. This was a deliberate
consolidation (v0.166.0) and is the cleanest part of the package.

## 6. Recommendations

### R1. Populate `__init__.py` with a minimal public API

```python
from .manager import IOManager

__all__ = ['IOManager']
```

`IOManager` is the only class imported externally. Declaring it in
`__init__.py` makes the API explicit and lets `shell.py` use:
```python
from .io_redirect import IOManager
```

### R2. Delete dead IOManager methods (5 methods, ~55 lines)

| Method | Lines | Reason |
|--------|-------|--------|
| `collect_heredocs()` | 2 | Zero callers. Heredocs are now populated by the parser. |
| `handle_heredoc()` | 30 | Zero callers. Dead code. |
| `cleanup_temp_files()` | 9 | Zero callers. Only used by `handle_heredoc()`. |
| `is_valid_fd()` | 9 | Zero callers. |
| `_is_heredoc_delimiter_quoted()` | 5 | Zero callers. |

Also delete the `_temp_files` list from `__init__()` (only used by
`handle_heredoc`).

### R3. Delete dead HeredocHandler methods (3 methods, ~42 lines)

| Method | Lines | Reason |
|--------|-------|--------|
| `collect_heredocs()` | 41 | Only caller is dead IOManager method. |
| `create_heredoc_file()` | 24 | Zero callers anywhere. |
| `expand_variables_in_heredoc()` | 17 | Zero callers. Expansion is done inline. |

After deletion, `HeredocHandler` would be an empty class with only
`__init__` and `_read_heredoc_content`. Since `_read_heredoc_content`
is also never reached in practice (the parser always pre-populates
heredoc content), `HeredocHandler` itself is a candidate for removal.
However, the interactive fallback path is a reasonable safety net, so
keeping it is defensible.

### R4. Extract shared target-expansion helper

Replace the 6 copies of the target-expansion preamble with a single
method:

```python
def _expand_redirect_target(self, redirect: Redirect) -> str:
    """Expand variables and tilde in a redirect target."""
    target = redirect.target
    if not target or redirect.type not in ('<', '>', '>>'):
        return target
    if not (hasattr(redirect, 'quote_type') and redirect.quote_type == "'"):
        target = self.shell.expansion_manager.expand_string_variables(target)
    if target.startswith('~'):
        target = self.shell.expansion_manager.expand_tilde(target)
    return target
```

### R5. Consolidate `_dup2_preserve_target` to one location

Delete the copy on `IOManager` and have `IOManager` call
`self.file_redirector._dup2_preserve_target()`, or extract it as a
module-level utility function (it has no `self` reference — it's already
`@staticmethod`).

### R6. Extract shared noclobber check

Replace the 5 copies with a helper:

```python
def _check_noclobber(self, target: str):
    """Raise OSError if noclobber is set and target exists."""
    if self.state.options.get('noclobber', False) and os.path.exists(target):
        raise OSError(f"cannot overwrite existing file: {target}")
```

### R7. Initialize `_saved_fds_list` in `__init__`

Replace the `hasattr` pattern in `setup_builtin_redirections()` with
proper initialization:

```python
def __init__(self, shell):
    ...
    self._saved_fds_list = []
```

### R8. Stop storing state on Shell directly

Move `_saved_stdout` / `_saved_stderr` / `_saved_stdin` from
`self.shell._saved_*` to `self._saved_*` on `FileRedirector` itself,
or pass them through the return value like `setup_builtin_redirections`
already does.

### R9. (Future) Reduce the three-way dispatch duplication

The most impactful improvement would be unifying the three redirect
dispatch paths. This is architecturally complex because:
- **FD-level** (child/temporary): Uses `os.open()` / `os.dup2()` on
  raw file descriptors.
- **Python-object** (builtin): Redirects `sys.stdin` / `sys.stdout` /
  `sys.stderr` as Python file objects.
- **Permanent** (exec): Like FD-level but doesn't save/restore.

A possible approach: a single `_apply_single_redirect()` method that
takes a `mode` parameter (`'fd'`, `'python'`, `'permanent'`) and
handles the differences via branching within each redirect type, rather
than duplicating the entire dispatch. This would eliminate ~350 lines
of near-duplicate code.

This is a larger refactor that should be planned separately.

## 7. Priority Order

| Priority | Recommendation | Risk | Lines removed |
|----------|---------------|------|---------------|
| 1 | R1. Populate `__init__.py` | None | 0 (adds ~3) |
| 2 | R2. Delete dead IOManager methods | None | ~55 |
| 3 | R3. Delete dead HeredocHandler methods | None | ~42 |
| 4 | R5. Consolidate `_dup2_preserve_target` | Low | ~8 |
| 5 | R7. Initialize `_saved_fds_list` | Low | ~4 net |
| 6 | R4. Extract target-expansion helper | Low | ~40 net |
| 7 | R6. Extract noclobber helper | Low | ~15 net |
| 8 | R8. Stop storing state on Shell | Medium | ~0 net |
| 9 | R9. Unify redirect dispatch | High | ~350 est. |

R1–R3 are safe, zero-risk deletions. R4–R7 are small refactors. R8 is
a coupling fix. R9 is a significant architectural refactor.

## 8. Files Modified by R1–R8

| File | Changes |
|------|---------|
| `psh/io_redirect/__init__.py` | Add `IOManager` import and `__all__` |
| `psh/io_redirect/manager.py` | Delete 5 methods, add helpers, consolidate static method |
| `psh/io_redirect/heredoc.py` | Delete 3 methods |
| `psh/io_redirect/file_redirect.py` | Use shared helpers, remove `_dup2_preserve_target` copy |
| `psh/shell.py` | Update import path (optional) |
