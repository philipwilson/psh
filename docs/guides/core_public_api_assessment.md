# Core Public API Assessment

**Package**: `psh/core/`
**Version assessed**: v0.184.1
**Files**: 8 Python modules, ~1,590 lines total

## 1. Current `__init__.py` State

```python
"""Core PSH modules for state management and variable handling."""

from .exceptions import LoopBreak, LoopContinue, ReadonlyVariableError, UnboundVariableError
from .scope_enhanced import EnhancedScopeManager, VariableScope
from .state import ShellState
from .variables import AssociativeArray, IndexedArray, VarAttributes, Variable

# from .options import ShellOptions  # Not yet implemented

__all__ = [
    # Exceptions
    'LoopBreak',
    'LoopContinue',
    'UnboundVariableError',
    'ReadonlyVariableError',
    # Variables
    'Variable',
    'VarAttributes',
    'IndexedArray',
    'AssociativeArray',
    # Scope management
    'EnhancedScopeManager',
    'VariableScope',
    # State and options
    'ShellState',
    # 'ShellOptions',  # Not yet implemented
]
```

**Issues**:

1. `ExpansionError` is defined in `exceptions.py` but not imported or
   listed in `__all__`.
2. `OptionHandler`, `TrapManager`, and `assignment_utils` functions are
   not imported or listed in `__all__`.
3. Stale commented-out reference to `ShellOptions` (never implemented).
4. No module-level docstring listing submodules (inconsistent with other
   packages post-cleanup).

## 2. Module Inventory

### `exceptions.py` (~30 lines)

| Symbol | Type | In `__all__` | External callers |
|--------|------|:---:|---|
| `LoopBreak` | Exception | Yes | executor (core, function, control_flow, command), scripting |
| `LoopContinue` | Exception | Yes | executor (core, function, control_flow, command), scripting |
| `UnboundVariableError` | Exception | Yes | expansion (manager, variable), executor (function) |
| `ReadonlyVariableError` | Exception | Yes | executor (command, control_flow), builtins (environment, function_support) |
| `ExpansionError` | Exception | **No** | expansion (manager, variable), executor (command) |

### `variables.py` (~240 lines)

| Symbol | Type | In `__all__` | External callers |
|--------|------|:---:|---|
| `VarAttributes` | Flag enum | Yes | builtins (environment, function_support, read_builtin, shell_state), expansion (variable), executor (array) |
| `Variable` | Dataclass | Yes | builtins (function_support) |
| `IndexedArray` | Class | Yes | builtins (environment, function_support, read_builtin, shell_state), expansion (variable), executor (array, test_evaluator) |
| `AssociativeArray` | Class | Yes | builtins (environment, function_support, shell_state), expansion (variable), executor (array, test_evaluator) |

### `scope_enhanced.py` (~467 lines)

| Symbol | Type | In `__all__` | External callers |
|--------|------|:---:|---|
| `EnhancedScopeManager` | Class | Yes | state.py (internal) |
| `VariableScope` | Class | Yes | No direct external callers found |

### `state.py` (~370 lines)

| Symbol | Type | In `__all__` | External callers |
|--------|------|:---:|---|
| `ShellState` | Class | Yes | shell.py, executor (process_launcher TYPE_CHECKING) |

### `options.py` (~132 lines)

| Symbol | Type | In `__all__` | External callers |
|--------|------|:---:|---|
| `OptionHandler` | Class (static methods) | **No** | expansion (variable) -- 2 lazy imports |

### `assignment_utils.py` (~88 lines)

| Symbol | Type | In `__all__` | External callers |
|--------|------|:---:|---|
| `is_valid_assignment` | Function | **No** | executor (command) |
| `extract_assignments` | Function | **No** | executor (command) |
| `is_exported` | Function | **No** | executor (command) |

### `trap_manager.py` (~239 lines)

| Symbol | Type | In `__all__` | External callers |
|--------|------|:---:|---|
| `TrapManager` | Class | **No** | shell.py (lazy), builtins (signal_handling, lazy) |

## 3. Bypass Import Analysis

**44 bypass imports** across 16 files import from `psh.core.<submodule>`
instead of `psh.core`.

### By submodule

| Submodule | Bypass count | Files |
|-----------|:---:|---|
| `exceptions` | 14 | 9 files |
| `variables` | 23 | 8 files |
| `assignment_utils` | 1 | 1 file |
| `options` | 2 | 1 file |
| `state` | 2 | 2 files |
| `trap_manager` | 2 | 2 files |
| `scope_enhanced` | 0 | -- |

### Top offenders

| File | Bypass imports |
|------|:---:|
| `psh/expansion/variable.py` | 16 (all lazy) |
| `psh/builtins/shell_state.py` | 5 (all lazy) |
| `psh/builtins/environment.py` | 4 (3 lazy, 1 top-level) |
| `psh/builtins/function_support.py` | 3 (1 lazy, 2 top-level) |
| `psh/executor/command.py` | 3 (2 lazy, 1 top-level) |

**Note**: Many bypasses in `expansion/variable.py` and builtins are
**lazy imports** (inside function/method bodies).  Lazy imports are
typically used to avoid circular dependencies.  Changing the import path
from `..core.exceptions` to `..core` still works for lazy imports and
is the preferred convention.

## 4. CLAUDE.md Documentation Issues

The subsystem CLAUDE.md at `psh/core/CLAUDE.md` has these errors:

1. **Stale file reference**: Lists `scope.py` with description
   "`VariableScope`, `ScopeManager` - basic scope management".  This
   file does not exist; `VariableScope` is in `scope_enhanced.py` and
   there is no `ScopeManager` class.

## 5. Recommendations

### R1: Add `ExpansionError` to `__all__` (Priority: High)

`ExpansionError` has 4 external callers across 3 files (expansion
manager, expansion variable, executor command).  It is a core exception
that belongs alongside `LoopBreak`, `LoopContinue`,
`UnboundVariableError`, and `ReadonlyVariableError`.

**Changes**:

`psh/core/__init__.py` -- add import and `__all__` entry:
```python
from .exceptions import (
    ExpansionError, LoopBreak, LoopContinue,
    ReadonlyVariableError, UnboundVariableError,
)
```

Add `'ExpansionError'` to `__all__`.

Fix 4 bypass imports:
- `psh/expansion/manager.py:5` (top-level)
- `psh/expansion/variable.py:88` (lazy)
- `psh/expansion/variable.py:558` (lazy)
- `psh/executor/command.py:186` (lazy)

### R2: Add `ExpansionError` + fix remaining `exceptions` bypasses (Priority: Medium)

The remaining 10 bypass imports of symbols that **are** already in
`__all__` (`LoopBreak`, `LoopContinue`, `UnboundVariableError`,
`ReadonlyVariableError`) should also be updated to use the package
import path.

Top-level imports to fix (5):
- `psh/executor/core.py:43`
- `psh/executor/function.py:11`
- `psh/executor/control_flow.py:21`
- `psh/builtins/environment.py:9`
- `psh/builtins/function_support.py:6`

Lazy imports to fix (5):
- `psh/executor/command.py:186` (same line as R1)
- `psh/executor/command.py:349`
- `psh/expansion/manager.py:498`
- `psh/expansion/variable.py:100`
- `psh/expansion/variable.py:355`
- `psh/scripting/source_processor.py:357`

### R3: Add `OptionHandler` to `__all__` (Priority: Medium)

`OptionHandler` has 2 lazy-import callers in `expansion/variable.py`.
It provides shell option behaviour that is logically part of the core
contract.

**Changes**:

`psh/core/__init__.py` -- add import:
```python
from .options import OptionHandler
```

Add `'OptionHandler'` to `__all__`.

Fix 2 bypass imports:
- `psh/expansion/variable.py:101` (lazy)
- `psh/expansion/variable.py:356` (lazy)

### R4: Add `TrapManager` to `__all__` (Priority: Medium)

`TrapManager` has 2 callers: `shell.py` (lazy) and
`builtins/signal_handling.py` (lazy).  It manages a core shell
responsibility (signal traps).

**Changes**:

`psh/core/__init__.py` -- add import:
```python
from .trap_manager import TrapManager
```

Add `'TrapManager'` to `__all__`.

Fix 2 bypass imports:
- `psh/shell.py:92` (lazy)
- `psh/builtins/signal_handling.py:74` (lazy)

### R5: Add `assignment_utils` functions to `__all__` (Priority: Medium)

Three functions (`is_valid_assignment`, `extract_assignments`,
`is_exported`) have 1 top-level caller (`executor/command.py`).  They
are pure utilities with no internal dependencies and logically belong
in the core public API.

**Changes**:

`psh/core/__init__.py` -- add imports:
```python
from .assignment_utils import extract_assignments, is_exported, is_valid_assignment
```

Add all three to `__all__`.

Fix 1 bypass import:
- `psh/executor/command.py:14` (top-level)

### R6: Fix remaining `variables` bypass imports (Priority: Medium)

23 bypass imports of `VarAttributes`, `Variable`, `IndexedArray`, and
`AssociativeArray` (all already in `__all__`) should use the package
path.

Top-level imports to fix (3):
- `psh/executor/array.py:13`
- `psh/builtins/function_support.py:7`
- `psh/builtins/read_builtin.py:260` -- actually lazy, but verify

Lazy imports to fix (20):
- `psh/expansion/variable.py` -- 12 lazy imports across lines 117,
  167, 195, 273, 380, 412, 436, 477, 848, 873
- `psh/builtins/environment.py` -- 3 lazy imports at lines 53, 126, 526
- `psh/builtins/shell_state.py` -- 5 lazy imports at lines 123, 149,
  179, 183, 284
- `psh/executor/test_evaluator.py:188` -- 1 lazy import

### R7: Fix `state` and `scope_enhanced` bypass imports (Priority: Low)

2 bypass imports of `ShellState`:
- `psh/shell.py:11` (top-level)
- `psh/executor/process_launcher.py:15` (TYPE_CHECKING only)

The `shell.py` import is the primary consumer; fixing it is low-effort.
The TYPE_CHECKING import is acceptable as-is (it has no runtime effect).

### R8: Fix CLAUDE.md documentation errors (Priority: Low)

Remove the stale `scope.py` reference from the Key Files table in
`psh/core/CLAUDE.md`.  Replace with correct information about
`scope_enhanced.py`.

### R9: Clean up stale comments in `__init__.py` (Priority: Low)

Remove the two commented-out `ShellOptions` references:
```python
# from .options import ShellOptions  # Not yet implemented
```
and
```python
    # 'ShellOptions',  # Not yet implemented
```

These have been present since the file was created and `ShellOptions`
was never implemented.  The existing `OptionHandler` serves this role.

### R10: Add module-level docstring to `__init__.py` (Priority: Low)

Add a docstring listing all submodules and their contents, following
the pattern established in the builtins, lexer, parser, executor,
visitor, expansion, io_redirect, and utils packages.

## 6. Proposed `__all__` (post-cleanup)

```python
__all__ = [
    # Exceptions
    'LoopBreak',
    'LoopContinue',
    'UnboundVariableError',
    'ReadonlyVariableError',
    'ExpansionError',
    # Variables
    'Variable',
    'VarAttributes',
    'IndexedArray',
    'AssociativeArray',
    # Scope management
    'EnhancedScopeManager',
    'VariableScope',
    # State
    'ShellState',
    # Options
    'OptionHandler',
    # Traps
    'TrapManager',
    # Assignment utilities
    'is_valid_assignment',
    'extract_assignments',
    'is_exported',
]
```

This grows `__all__` from 11 to 18 items.  All 18 have production
callers.

## 7. Bypass Import Summary

| Recommendation | Bypass imports fixed | Files touched |
|----------------|:---:|:---:|
| R1 (ExpansionError to `__all__`) | 4 | 3 |
| R2 (exceptions bypasses) | 10 | 6 |
| R3 (OptionHandler to `__all__`) | 2 | 1 |
| R4 (TrapManager to `__all__`) | 2 | 2 |
| R5 (assignment_utils to `__all__`) | 1 | 1 |
| R6 (variables bypasses) | 23 | 7 |
| R7 (state/scope bypasses) | 1-2 | 1-2 |
| R8 (CLAUDE.md fix) | 0 | 1 |
| R9 (stale comments) | 0 | 1 |
| R10 (docstring) | 0 | 1 |
| **Total** | **42-44** | **~16** |

## 8. Risk Assessment

All recommendations are low risk:

- **R1-R7**: Changing import paths does not change runtime behaviour.
  Adding items to `__all__` only makes existing symbols importable from
  the package level; it does not break any existing submodule imports.

- **R8-R10**: Documentation and comment cleanup only.

- **Lazy imports**: Many bypass imports are lazy (inside function
  bodies) to avoid circular dependencies.  Changing the path from
  `from ..core.exceptions import X` to `from ..core import X` works
  identically for lazy imports -- the deferred import still avoids
  import-time cycles.

## 9. Implementation Suggestion

All 10 recommendations can be done in a single phase since they are
independent and low risk.  Suggested implementation order:

1. Update `psh/core/__init__.py` (R1, R3-R5, R9-R10) -- add imports,
   update `__all__`, add docstring, remove stale comments.
2. Fix bypass imports (R2, R6-R7) -- update import paths in all 16
   files.
3. Fix CLAUDE.md (R8) -- remove stale `scope.py` reference.
4. Verify: lint, smoke tests, full test suite.
