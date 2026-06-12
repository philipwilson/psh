# Interactive Public API Reference

**As of v0.187.0** (post-cleanup)

This document describes the public API of the `psh.interactive` package: the
items declared in `__all__`, their signatures, and guidance on internal
imports that are available but not part of the public contract.

## Public API (`__all__`)

The declared public API consists of two items:

```python
__all__ = [
    'InteractiveManager',
    'load_rc_file',
]
```

### `InteractiveManager`

```python
from psh.interactive import InteractiveManager

manager = InteractiveManager(shell)
```

The central orchestrator for all interactive shell components.  Created by
`Shell.__init__()` and stored as `shell.interactive_manager`.  On
construction it instantiates and wires together the five interactive
components (`HistoryManager`, `PromptManager`, `CompletionManager`,
`SignalManager`, `REPLLoop`), sets up cross-component dependencies, and
conditionally initialises signal handlers and foreground process-group
ownership.

| Parameter | Type | Meaning |
|-----------|------|---------|
| `shell` | `Shell` | The shell instance that owns this manager. |

Signal setup is skipped in two situations (to avoid interfering with
tests or child processes):

- When running under pytest (unless `PSH_TEST_SIGNALS=1`).
- When the `PSH_IN_FORKED_CHILD=1` environment variable is set.

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `shell` | `Shell` | Back-reference to the owning shell. |
| `state` | `ShellState` | Shortcut to `shell.state`. |
| `history_manager` | `HistoryManager` | Command history component. |
| `prompt_manager` | `PromptManager` | Prompt expansion component. |
| `completion_manager` | `CompletionManager` | Tab completion component. |
| `signal_manager` | `SignalManager` | Signal handling component. |
| `repl_loop` | `REPLLoop` | The main read-eval-print loop. |

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `run_interactive_loop()` | `None` | Delegates to `repl_loop.run()`.  This is the main entry point for the interactive shell session. |
| `setup_readline()` | `None` | Delegates to `completion_manager.setup_readline()`.  Configures readline tab-completion bindings. |
| `load_history()` | `None` | Delegates to `history_manager.load_from_file()`.  Loads history from `~/.psh_history`. |
| `save_history()` | `None` | Delegates to `history_manager.save_to_file()`.  Saves history to `~/.psh_history`. |

### `load_rc_file()`

```python
from psh.interactive import load_rc_file

load_rc_file(shell)
```

Loads the shell's RC file (`~/.pshrc` by default, or `shell.rcfile` if
set).  Called during `Shell.__init__()` for interactive, non-`--norc`
sessions.

| Parameter | Type | Meaning |
|-----------|------|---------|
| `shell` | `Shell` | The shell instance to source the RC file into. |

Behaviour:

1. Determines the RC file path (`shell.rcfile` or `~/.pshrc`).
2. Checks the file exists and is readable.
3. Checks permissions via `is_safe_rc_file()` -- skips with a warning if
   the file is world-writable or owned by a different user.
4. Sources the file using `shell.script_manager.execute_from_source()`.
5. Prints a warning (but does not abort) if an error occurs during loading.

## Convenience Imports (not in `__all__`)

The following items are importable from `psh.interactive` for convenience
but are **not** part of the declared public contract.  They are internal
implementation details whose signatures may change without notice.

Existing code that imports these will continue to work; the imports are
kept specifically to avoid churn.  New code should prefer the submodule
import paths listed below.

### Base Classes

| Import | Canonical path | Description |
|--------|---------------|-------------|
| `InteractiveComponent` | `psh.interactive.base` | ABC base class for all interactive components.  Provides `shell`, `state`, `job_manager` attributes. |

### Component Classes

| Import | Canonical path | Description |
|--------|---------------|-------------|
| `REPLLoop` | `psh.interactive.repl_loop` | Main read-eval-print loop.  Callers use `run()`. |
| `SignalManager` | `psh.interactive.signal_manager` | Signal handling, SIGCHLD/SIGWINCH self-pipe pattern.  Callers use `setup_signal_handlers()`, `process_sigchld_notifications()`, `ensure_foreground()`. |
| `HistoryManager` | `psh.interactive.history_manager` | Command history management.  Callers use `add_to_history()`, `load_from_file()`, `save_to_file()`. |
| `CompletionManager` | `psh.interactive.completion_manager` | Tab completion via readline.  Callers use `setup_readline()`, `get_completions()`. |
| `PromptManager` | `psh.interactive.prompt_manager` | PS1/PS2 prompt expansion.  Callers use `get_primary_prompt()`, `get_continuation_prompt()`. |

### RC File Utilities

| Import | Canonical path | Description |
|--------|---------------|-------------|
| `is_safe_rc_file` | `psh.interactive.rc_loader` | Permission check for RC files.  Returns `False` if the file is world-writable or not owned by the current user or root. |

## API Tiers Summary

| Tier | Scope | How to import | Stability guarantee |
|------|-------|---------------|-------------------|
| **Public** | `InteractiveManager`, `load_rc_file` | `from psh.interactive import ...` | Stable.  Changes are versioned. |
| **Convenience** | `InteractiveComponent`, `REPLLoop`, `SignalManager`, `HistoryManager`, `CompletionManager`, `PromptManager`, `is_safe_rc_file` | `from psh.interactive import ...` (works) or `from psh.interactive.<module> import ...` (preferred) | Available but not guaranteed.  Prefer submodule paths. |

## Typical Usage

### Access the interactive manager from the shell

```python
# The interactive manager is always available on the shell object
shell.interactive_manager.run_interactive_loop()

# Access sub-components through the manager
shell.interactive_manager.signal_manager.process_sigchld_notifications()
shell.interactive_manager.history_manager.add_to_history("echo hello")
```

### Load RC file at startup

```python
from psh.interactive import load_rc_file

if not shell.norc:
    load_rc_file(shell)
```

### Check RC file safety

```python
from psh.interactive import is_safe_rc_file

if is_safe_rc_file("/path/to/.pshrc"):
    # File has safe permissions, OK to source
    pass
```

## Related Documents

- `docs/guides/interactive_guide.md` -- Full programmer's guide
  (architecture, file reference, design rationale)
- `docs/guides/interactive_public_api_assessment.md` -- Analysis that led
  to this cleanup
- `psh/interactive/CLAUDE.md` -- AI assistant working guide for the
  interactive subsystem
