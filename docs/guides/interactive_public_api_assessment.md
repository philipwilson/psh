# Interactive Package — Public API Assessment

**Package**: `psh/interactive/`
**Version**: 0.186.0
**Date**: 2025-02-14
**Lines of code**: ~805 across 8 Python files

## Package Purpose

The `psh.interactive` package provides all interactive shell components:
the REPL loop, command history, tab completion, prompt management, signal
handling, and RC file loading. The `InteractiveManager` orchestrator ties
them together and is the primary entry point used by `Shell`.

## Current `__init__.py` Exports

```python
__all__ = [
    'InteractiveComponent',   # ABC base class
    'InteractiveManager',     # Orchestrator
    'HistoryManager',         # Command history
    'PromptManager',          # PS1/PS2 prompts
    'CompletionManager',      # Tab completion
    'SignalManager',          # Signal handling (SIGCHLD, SIGWINCH, etc.)
    'REPLLoop',               # Read-Eval-Print Loop
]
```

All 7 items are imported at the top of `__init__.py` and listed in `__all__`.

## Tier Classification

### Tier 1 — True Public API (production callers outside the package)

| Symbol | Callers | Access Pattern |
|--------|---------|---------------|
| `InteractiveManager` | `shell.py` (import + construction) | `from .interactive.base import InteractiveManager` |
| `SignalManager` | 7 sites across executor, expansion, I/O | accessed as `shell.interactive_manager.signal_manager` |

**`InteractiveManager`** is the sole import from outside the package. All other
components are accessed transitively through it:
- `shell.interactive_manager.signal_manager` (7 sites)
- `shell.interactive_manager.history_manager` (2 sites: `core.py` exit builtin, `source_processor.py`)
- `shell.interactive_manager.run_interactive_loop()` (2 sites: `__main__.py`)
- `shell.interactive_manager.load_history()` / `.save_history()` (1 site each)

### Tier 2 — Internal Components (used only within the package or via orchestrator)

| Symbol | Used by |
|--------|---------|
| `REPLLoop` | `InteractiveManager.__init__()` only |
| `HistoryManager` | `InteractiveManager.__init__()` only |
| `PromptManager` | `InteractiveManager.__init__()` only |
| `CompletionManager` | `InteractiveManager.__init__()` only |
| `InteractiveComponent` | Base class; subclassed within the package only |

None of these have production callers outside `psh/interactive/`.

### Standalone Functions (not in `__all__`)

| Symbol | Module | Callers |
|--------|--------|---------|
| `load_rc_file()` | `rc_loader.py` | `shell.py` (1 site), test (1 site) |
| `is_safe_rc_file()` | `rc_loader.py` | `load_rc_file()` only |

`load_rc_file` has a production caller in `shell.py` but is not exported
through `__all__` — it is imported directly via `from .interactive.rc_loader
import load_rc_file`.

## External Access Patterns

All external usage goes through `shell.interactive_manager.<component>`:

| Accessor Path | Files Using It |
|---------------|---------------|
| `shell.interactive_manager.signal_manager` | `process_launcher.py`, `strategies.py` (x2), `pipeline.py`, `subshell.py`, `command_sub.py`, `process_sub.py` |
| `shell.interactive_manager.history_manager` | `core.py` (exit builtin), `source_processor.py` |
| `shell.interactive_manager.run_interactive_loop()` | `__main__.py` (x2) |
| `shell.interactive_manager.load_history()` | `shell.py` |

## Issues Found

### Issue 1: Bypass Imports (2 sites)

`shell.py` imports directly from submodules rather than through the package:

```python
# shell.py:14
from .interactive.base import InteractiveManager    # bypass

# shell.py:117
from .interactive.rc_loader import load_rc_file     # bypass
```

These should use package-level imports:
```python
from .interactive import InteractiveManager
from .interactive import load_rc_file  # after adding to __all__
```

### Issue 2: `load_rc_file` Missing From `__all__`

`load_rc_file()` has a production caller in `shell.py` and a test caller in
`test_rc_file.py`, but is not exported through `__init__.py`. This is
inconsistent with the established pattern where all production-called
symbols are available at the package level.

### Issue 3: Oversized `__all__` — 5 Items Have Zero External Callers

Five of the seven `__all__` entries (`InteractiveComponent`, `REPLLoop`,
`HistoryManager`, `PromptManager`, `CompletionManager`) are never imported
from outside the package. They are internal implementation details of the
orchestrator. Exporting them inflates the public API surface.

Following the pattern established in executor (v0.182.0) and visitor
(v0.181.0) cleanups, these should be demoted to convenience imports
(available for ad-hoc/test use) but removed from `__all__`.

### Issue 4: Dead `shell.signal_manager` Access (2 sites)

Two files access `shell.signal_manager` directly (not via
`interactive_manager`):

```python
# repl_loop.py:50-51
if hasattr(self.shell, 'signal_manager'):
    self.shell.signal_manager.process_sigchld_notifications()

# multiline_handler.py:36-38
if hasattr(self.shell, 'signal_manager') and self.shell.signal_manager:
    sigwinch_fd = self.shell.signal_manager.get_sigwinch_fd()
    sigwinch_drain = self.shell.signal_manager.drain_sigwinch_notifications
```

`Shell` has no `signal_manager` attribute. Its `__getattr__` delegates to
`ShellState`, which also lacks `signal_manager`. The `hasattr()` checks
therefore always return `False`, making these code paths dead.

The correct path is `shell.interactive_manager.signal_manager`, which is
what all 7 external callers in the executor/expansion/I/O packages use.

### Issue 5: Missing Module Docstring in `__init__.py`

Other recently-cleaned packages (`core`, `executor`, `expansion`) include a
module-level docstring listing the package's modules and their purposes. The
interactive `__init__.py` has only `"""Interactive shell components."""` —
a one-liner that doesn't describe the module structure.

### Issue 6: `InteractiveComponent.execute()` Signature Variance

The ABC defines `execute(self, *args, **kwargs)`, but subclass signatures
diverge:
- `REPLLoop.execute()` — no parameters
- `HistoryManager.execute(command=None, action="add")` — keyword parameters
- `CompletionManager.execute(text, line, cursor_pos)` — positional parameters
- `PromptManager.execute(prompt_type="PS1")` — keyword parameter
- `SignalManager.execute(*args, **kwargs)` — passthrough

The `*args, **kwargs` signature provides no type safety or documentation
value. In practice, `execute()` is never called polymorphically — each
component is invoked by name-specific methods (`run()`, `add_to_history()`,
`get_completions()`, etc.). The ABC method is vestigial.

### Issue 7: CLAUDE.md Contains Stale/Inaccurate Code Examples

The `CLAUDE.md` contains pseudocode-style examples (e.g., `self.run_loop.run()`
showing `input(prompt)` + `self.shell.execute(line)`) that don't match
the actual implementation. The real `repl_loop.py` uses
`MultiLineInputHandler.read_command()` and `self.shell.run_command()`.
Similarly, the SignalManager section shows a simplified self-pipe implementation
that diverges from the actual `SignalNotifier`-based implementation. While
the CLAUDE.md is educational, the code examples should match reality.

## Recommended `__all__` (Trimmed)

```python
__all__ = [
    'InteractiveManager',  # Orchestrator — sole external import
    'load_rc_file',        # RC file loading — has production caller
]
```

The 5 component classes (`InteractiveComponent`, `REPLLoop`,
`HistoryManager`, `PromptManager`, `CompletionManager`, `SignalManager`)
would remain as convenience imports in `__init__.py` — importable but not
part of the contracted API.

**Note on `SignalManager`**: Although `SignalManager` has 7 external call
sites, it is never imported directly — it is always accessed as
`shell.interactive_manager.signal_manager`. This is the same pattern as
`PipelineExecutor` and `CommandExecutor` in the executor package, which
were demoted from `__all__` in v0.182.0.

## Recommended Changes Summary

| # | Change | Impact |
|---|--------|--------|
| 1 | Fix 2 bypass imports in `shell.py` | Consistent with project convention |
| 2 | Add `load_rc_file` to `__init__.py` imports and `__all__` | Eliminates bypass import |
| 3 | Trim `__all__` from 7 → 2 items | Matches established pattern |
| 4 | Fix dead `shell.signal_manager` → `shell.interactive_manager.signal_manager` in `repl_loop.py` and `multiline_handler.py` | Fixes 2 dead code paths |
| 5 | Add descriptive module docstring to `__init__.py` | Consistency with other packages |
| 6 | Consider removing vestigial `execute()` from `InteractiveComponent` ABC | Simplification (optional, lower priority) |
| 7 | Update CLAUDE.md code examples to match actual implementation | Documentation accuracy |

## Dependencies (Outbound)

The package imports from these sibling packages:

| Import | Used by | Purpose |
|--------|---------|---------|
| `psh.job_control.JobState` | `signal_manager.py` | Job state enum for SIGCHLD processing |
| `psh.utils.SignalNotifier` | `signal_manager.py` | Self-pipe pattern for signal safety |
| `psh.utils.get_signal_registry` | `signal_manager.py` | Global signal registration |
| `psh.line_editor.LineEditor` | `repl_loop.py` | Readline-based line editing |
| `psh.multiline_handler.MultiLineInputHandler` | `repl_loop.py` | Multi-line command input |
| `psh.prompt.PromptExpander` | `prompt_manager.py` | Prompt escape expansion |
| `psh.tab_completion.CompletionEngine` | `completion_manager.py` | Completion logic |
| `psh.input_sources.FileInput` | `rc_loader.py` | File input for RC sourcing |

All outbound dependencies use package-level imports (no bypass issues on
the outbound side).

## Dependencies (Inbound)

External modules that reach into the interactive package:

| Module | Reaches Into | Via |
|--------|-------------|-----|
| `psh/shell.py` | `InteractiveManager`, `load_rc_file` | Direct submodule import (bypass) |
| `psh/executor/process_launcher.py` | `signal_manager` | `shell.interactive_manager.signal_manager` |
| `psh/executor/strategies.py` | `signal_manager` | `shell.interactive_manager.signal_manager` |
| `psh/executor/pipeline.py` | `signal_manager` | `shell.interactive_manager.signal_manager` |
| `psh/executor/subshell.py` | `signal_manager` | `shell.interactive_manager.signal_manager` |
| `psh/expansion/command_sub.py` | `signal_manager` | `shell.interactive_manager.signal_manager` |
| `psh/io_redirect/process_sub.py` | `signal_manager` | `shell.interactive_manager.signal_manager` |
| `psh/builtins/core.py` | `history_manager` | `shell.interactive_manager.history_manager` |
| `psh/scripting/source_processor.py` | `history_manager` | `shell.interactive_manager.history_manager` |
| `psh/__main__.py` | `run_interactive_loop()` | `shell.interactive_manager` |

The heavy coupling of `signal_manager` through 7 executor/expansion/I/O
sites is the most architecturally significant dependency. These callers
need `reset_child_signals()` for forked child processes, which is
fundamentally a process lifecycle concern rather than an interactive
concern. This coupling is discussed further below.

## Architectural Observation: SignalManager Placement

`SignalManager` serves two distinct roles:

1. **Interactive signal handling**: SIGINT behavior, SIGWINCH terminal
   resize, SIGCHLD job notification — genuinely interactive concerns.

2. **Child process signal reset**: `reset_child_signals()` is called by
   every fork path (`process_launcher.py`, `command_sub.py`,
   `process_sub.py`, etc.) regardless of whether the shell is interactive.

Role 2 forces the executor, expansion, and I/O packages to reach through
`interactive_manager` to get at signal infrastructure that has nothing to
do with interactivity. The `child_policy.py` module already partially
addresses this by wrapping the call in `apply_child_signal_policy()`, but
the underlying `signal_manager` object still lives inside the interactive
package.

A future refactoring could extract `reset_child_signals()` (and its signal
list) into a standalone utility in `psh/utils/` or `psh/executor/`, removing
the architectural coupling. This is a non-trivial change and is noted here
for consideration rather than as an immediate recommendation.
