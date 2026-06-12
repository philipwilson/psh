# Utils Public API Assessment

**As of v0.182.0**

This document assesses the utils package's public API contract -- what is
exported vs what is actually used -- and recommends cleanup actions.
Follows the same methodology as the lexer, parser, expansion, I/O redirect,
visitor, and executor API assessments.

## 1. Package Overview

| File | Lines | Classes / Functions |
|------|-------|---------------------|
| `__init__.py` | 0 | Empty; no `__all__`, no imports |
| `signal_utils.py` | 581 | `SignalNotifier`, `SignalHandlerRecord` (dataclass), `SignalRegistry`; `block_signals()`, `restore_default_signals()`, `get_signal_registry()`, `set_signal_registry()` |
| `shell_formatter.py` | 292 | `ShellFormatter` (static methods) |
| `ast_debug.py` | 82 | `print_ast_debug()` |
| `heredoc_detection.py` | 59 | `contains_heredoc()` |
| `file_tests.py` | 41 | `to_int()`, `file_newer_than()`, `file_older_than()`, `files_same()` |
| `parser_factory.py` | 35 | `create_parser()`, `ParserWrapper` (inner class) |
| `token_formatter.py` | 17 | `TokenFormatter` (static method) |
| **Total** | **~1,107** | **5 classes + 10 functions** |

## 2. Current State

The `__init__.py` is empty.  There is no `__all__`, no re-exports, no
docstring.  Every caller imports directly from submodules using paths
like `from ..utils.signal_utils import SignalNotifier`.  The package is
effectively a namespace directory, not a curated API.

There is no `CLAUDE.md` for this subsystem.

## 3. Caller Analysis

### Items with production callers outside `psh/utils/`

| Item | Module | Production callers | Files |
|------|--------|--------------------|-------|
| `SignalNotifier` | `signal_utils` | 1 | `interactive/signal_manager.py` |
| `get_signal_registry` | `signal_utils` | 2 | `interactive/signal_manager.py`, `builtins/debug_control.py` |
| `contains_heredoc` | `heredoc_detection` | 1 | `scripting/source_processor.py` |
| `create_parser` | `parser_factory` | 1 | `scripting/source_processor.py` |
| `print_ast_debug` | `ast_debug` | 1 | `scripting/source_processor.py` |
| `TokenFormatter` | `token_formatter` | 1 | `scripting/source_processor.py` |
| `ShellFormatter` | `shell_formatter` | 1 | `builtins/function_support.py` |
| `to_int` | `file_tests` | 6 (all in 1 file) | `executor/test_evaluator.py` |
| `file_newer_than` | `file_tests` | 1 | `executor/test_evaluator.py` |
| `file_older_than` | `file_tests` | 1 | `executor/test_evaluator.py` |
| `files_same` | `file_tests` | 1 | `executor/test_evaluator.py` |

**11 items have production callers** across 5 files.

### Items with test-only callers

| Item | Module | Test callers | Files |
|------|--------|--------------|-------|
| `SignalRegistry` | `signal_utils` | 1 | `tests/unit/utils/test_signal_registry.py` |
| `set_signal_registry` | `signal_utils` | 1 | `tests/unit/utils/test_signal_registry.py` |

### Items with zero callers outside `psh/utils/`

| Item | Module | Notes |
|------|--------|-------|
| `block_signals` | `signal_utils` | Context manager for signal blocking. Zero production or test callers. Referenced only in old archived docs. |
| `restore_default_signals` | `signal_utils` | Context manager for restoring default signal handlers. Zero callers. Referenced only in old archived docs. |
| `SignalHandlerRecord` | `signal_utils` | Dataclass used internally by `SignalRegistry`. Zero external callers. |

**3 items have zero callers.**

## 4. Architectural Observations

### 4.1 The package is a "misc" grab-bag

The seven modules have no cohesive theme.  They fall into distinct
categories:

| Category | Modules | Natural home |
|----------|---------|--------------|
| **Signal infrastructure** | `signal_utils.py` | `psh/interactive/` (only callers are signal_manager and debug_control) |
| **Parsing support** | `parser_factory.py`, `heredoc_detection.py` | `psh/scripting/` (only caller is source_processor) |
| **Debug/formatting** | `ast_debug.py`, `token_formatter.py` | `psh/scripting/` (only caller is source_processor) |
| **Shell formatting** | `shell_formatter.py` | `psh/builtins/` (only caller is function_support) |
| **File test helpers** | `file_tests.py` | `psh/executor/` (only caller is test_evaluator) |

Each module has exactly 1-2 production callers, all in a single
package.  This makes `psh/utils/` a "nowhere else to put it" directory
rather than a coherent subsystem.

### 4.2 `signal_utils.py` is the largest file (53% of the package)

At 581 lines, `signal_utils.py` contains three distinct components:

1. **`SignalNotifier`** (170 lines) -- self-pipe pattern for signal-safe
   notification.  Used by `signal_manager.py`.
2. **`SignalRegistry` + `SignalHandlerRecord`** (290 lines) -- debugging
   tool for tracking signal handler changes.  Used by
   `signal_manager.py` and `debug_control.py`.
3. **`block_signals` + `restore_default_signals`** (75 lines) -- context
   managers for signal masking.  Zero callers.

The `SignalNotifier` is tightly coupled to the interactive subsystem.
The `SignalRegistry` is a debugging/introspection tool.

### 4.3 `file_tests.py` is tightly coupled to `test_evaluator.py`

All 4 functions in `file_tests.py` are called exclusively from
`executor/test_evaluator.py`.  The functions implement the `-eq`, `-nt`,
`-ot`, `-ef` test operators for `[[ ]]` expressions.  They could live
in `test_evaluator.py` itself or in `psh/builtins/test_command.py`
(which already implements the `[` builtin's unary file tests).

### 4.4 `parser_factory.py` has a single caller

`create_parser()` is called only from `source_processor.py`.  It's 35
lines of straightforward factory logic that reads `shell._active_parser`
to choose between the recursive descent and combinator parsers.

### 4.5 `shell_formatter.py` has a single caller

`ShellFormatter` is used only by `function_support.py` to format
function bodies for the `type` builtin output.  At 292 lines it's a
substantial module for a single call site.

### 4.6 Dead code in `signal_utils.py`

`block_signals()` and `restore_default_signals()` have zero callers in
production or test code.  They appear only in archived documentation
(`docs/archive/EXECUTOR_IMPROVEMENT_RECOMMENDATIONS.md`) as examples.
They are candidates for removal.

### 4.7 `has_notifications()` consumes data it can't put back

`SignalNotifier.has_notifications()` reads a byte from the pipe to
check for pending data, but cannot put it back.  The docstring
acknowledges this ("this is a bit of a hack").  In practice, zero
production callers use this method -- `signal_manager.py` uses
`drain_notifications()` directly.

## 5. Recommendations

### R1. Populate `__init__.py` with `__all__` and imports

Add a proper `__all__` listing the items that have production callers
outside the package, plus a docstring:

```python
"""
PSH Utils Package

Utility modules supporting shell infrastructure:
- signal_utils: Signal handling with self-pipe pattern and registry
- shell_formatter: Reconstruct shell syntax from AST nodes
- parser_factory: Configurable parser instantiation
- heredoc_detection: Distinguish heredocs from bit-shift operators
- ast_debug: AST visualization for debugging
- file_tests: File comparison utilities for test expressions
- token_formatter: Token list formatting for debug output
"""

from .file_tests import file_newer_than, file_older_than, files_same, to_int
from .heredoc_detection import contains_heredoc
from .parser_factory import create_parser
from .shell_formatter import ShellFormatter
from .signal_utils import SignalNotifier, get_signal_registry
from .ast_debug import print_ast_debug
from .token_formatter import TokenFormatter

__all__ = [
    # Signal infrastructure
    'SignalNotifier',
    'get_signal_registry',
    # Shell formatting
    'ShellFormatter',
    # Parsing support
    'create_parser',
    'contains_heredoc',
    # Debug/formatting
    'print_ast_debug',
    'TokenFormatter',
    # File test helpers
    'to_int',
    'file_newer_than',
    'file_older_than',
    'files_same',
]
```

This is 11 items -- every item with production callers.

### R2. Delete dead code from `signal_utils.py`

Remove 2 unused context managers (~75 lines):

- `block_signals()` -- zero callers
- `restore_default_signals()` -- zero callers

These were written speculatively and never adopted.  If needed in the
future they can be reimplemented.

### R3. Delete `has_notifications()` from `SignalNotifier`

This method has zero callers, acknowledges itself as a hack (consumes
pipe data it cannot replace), and provides no value over
`drain_notifications()`.  Remove it (~20 lines).

### R4. Fix bypass imports (after R1)

Once `__init__.py` has the re-exports, update 5 production files to
use package-level imports:

**`psh/interactive/signal_manager.py`** line 7:
```python
# from ..utils.signal_utils import SignalNotifier, get_signal_registry
from ..utils import SignalNotifier, get_signal_registry
```

**`psh/builtins/debug_control.py`** line 278:
```python
# from ..utils.signal_utils import get_signal_registry
from ..utils import get_signal_registry
```

**`psh/builtins/function_support.py`** line 8:
```python
# from ..utils.shell_formatter import ShellFormatter
from ..utils import ShellFormatter
```

**`psh/scripting/source_processor.py`** line 8:
```python
# from ..utils.heredoc_detection import contains_heredoc
from ..utils import contains_heredoc
```

The remaining 3 imports in `source_processor.py` (lines 287, 304, 310)
are lazy imports inside functions.  These should remain as submodule
imports since they are intentionally deferred:

```python
# These are lazy imports -- keep as submodule paths
from ..utils.token_formatter import TokenFormatter   # line 287
from ..utils.parser_factory import create_parser     # line 304
from ..utils.ast_debug import print_ast_debug        # line 310
```

**`psh/executor/test_evaluator.py`** has 9 lazy imports of file_tests
functions (lines 79-103).  These should also remain as submodule imports
since they are intentionally deferred inside method branches:

```python
# These are lazy imports in elif branches -- keep as submodule paths
from ..utils.file_tests import to_int            # lines 79-94
from ..utils.file_tests import file_newer_than   # line 97
from ..utils.file_tests import file_older_than   # line 100
from ..utils.file_tests import files_same        # line 103
```

**Net: 4 bypass imports fixed, 12 lazy imports left as-is.**

## 6. Non-Recommendations (Considered and Rejected)

### Moving modules to their "natural home" packages

Each utils module has callers in exactly one other package, which
suggests relocating them:

| Module | Could move to |
|--------|--------------|
| `signal_utils.py` | `psh/interactive/` |
| `parser_factory.py` | `psh/scripting/` |
| `heredoc_detection.py` | `psh/scripting/` |
| `ast_debug.py` | `psh/scripting/` |
| `token_formatter.py` | `psh/scripting/` |
| `shell_formatter.py` | `psh/builtins/` |
| `file_tests.py` | `psh/executor/` |

**Rejected** because:
1. The modules are genuinely utility-grade -- they don't depend on the
   internal state of their caller packages.
2. Moving 7 files would be a large churn for no functional benefit.
3. Having a `utils/` package for cross-cutting utilities is a common
   and accepted pattern.
4. Some modules (e.g. `signal_utils.py`) could gain callers in other
   packages as the shell evolves.

### Splitting `signal_utils.py` into separate files

`signal_utils.py` could be split into `signal_notifier.py`,
`signal_registry.py`, and `signal_context_managers.py`.

**Rejected** because the file is cohesive (all signal-related
utilities) and the module boundaries within it are clear.  If R2
removes the dead context managers, the file drops to ~500 lines, which
is manageable.

## 7. Priority Order

| Priority | Recommendation | Risk | Impact |
|----------|---------------|------|--------|
| 1 | R1. Populate `__init__.py` | None | API hygiene -- establishes public contract |
| 2 | R2. Delete dead signal context managers | None | Removes 75 lines of unused code |
| 3 | R3. Delete `has_notifications()` | None | Removes 20 lines of self-acknowledged hack |
| 4 | R4. Fix 4 bypass imports | None | Import consistency |

All four are safe, zero-risk changes.

## 8. New `__all__` (after R1)

```python
__all__ = [
    # Signal infrastructure (used by signal_manager, debug_control)
    'SignalNotifier',
    'get_signal_registry',
    # Shell formatting (used by function_support)
    'ShellFormatter',
    # Parsing support (used by source_processor)
    'create_parser',
    'contains_heredoc',
    # Debug/formatting (used by source_processor)
    'print_ast_debug',
    'TokenFormatter',
    # File test helpers (used by test_evaluator)
    'to_int',
    'file_newer_than',
    'file_older_than',
    'files_same',
]
```

11 items.  All 11 have production callers outside the package.

## 9. Items Not in `__all__` (Convenience/Internal)

After R1, the following remain importable from their submodules but
are not part of the package-level API:

| Item | Module | Callers |
|------|--------|---------|
| `SignalRegistry` | `signal_utils` | Test-only (`test_signal_registry.py`) |
| `set_signal_registry` | `signal_utils` | Test-only (`test_signal_registry.py`) |
| `SignalHandlerRecord` | `signal_utils` | Internal to `SignalRegistry` |
| `ParserWrapper` | `parser_factory` | Internal to `create_parser()` |

## 10. Files Modified (if all recommendations implemented)

| File | Changes |
|------|---------|
| `psh/utils/__init__.py` | Populate with `__all__`, imports, docstring (R1) |
| `psh/utils/signal_utils.py` | Delete `block_signals`, `restore_default_signals` (R2); delete `has_notifications` (R3) |
| `psh/interactive/signal_manager.py` | Fix bypass import (R4) |
| `psh/builtins/debug_control.py` | Fix bypass import (R4) |
| `psh/builtins/function_support.py` | Fix bypass import (R4) |
| `psh/scripting/source_processor.py` | Fix 1 bypass import (R4) |

## 11. Verification

```bash
# Smoke test — new public API
python -c "from psh.utils import SignalNotifier, get_signal_registry, ShellFormatter, create_parser, contains_heredoc, print_ast_debug, TokenFormatter, to_int, file_newer_than, file_older_than, files_same; print('OK')"

# Smoke test — internal items still importable from submodules
python -c "from psh.utils.signal_utils import SignalRegistry, set_signal_registry, SignalHandlerRecord; print('OK')"

# Verify dead code removed
python -c "
try:
    from psh.utils.signal_utils import block_signals
    print('FAIL: block_signals still exists')
except ImportError:
    print('OK: block_signals removed')
"

# Run utils tests
python -m pytest tests/unit/utils/ -q --tb=short

# Run full suite
python run_tests.py > tmp/test-results.txt 2>&1; tail -15 tmp/test-results.txt
grep FAILED tmp/test-results.txt

# Lint
ruff check psh/utils/ psh/interactive/signal_manager.py psh/builtins/debug_control.py psh/builtins/function_support.py psh/scripting/source_processor.py
```

## 12. Related Documents

- `psh/executor/CLAUDE.md` -- References `file_tests.py` functions
- `docs/guides/executor_public_api.md` -- `TestExpressionEvaluator`
  (the sole caller of `file_tests`)
- `docs/guides/parser_guide.md` -- References `create_parser()`
- `ARCHITECTURE.md` -- System-wide architecture reference (the former ARCHITECTURE.llm is archived)
