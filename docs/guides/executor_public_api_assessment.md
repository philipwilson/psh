# Executor Public API Assessment

> **Note (2026-06-11):** This guide describes the tree as of ~v0.27x, before
> the v0.285 module relocation and subsequent cleanups. In particular it
> references `psh/arithmetic.py`, which has since moved to `psh/expansion/arithmetic.py`.
> See the subsystem CLAUDE.md files for current structure.

**As of v0.181.0** (implemented in v0.182.0)

This document assesses the executor package's public API contract -- what is
exported vs what is actually used -- and recommends cleanup actions.
Follows the same methodology as the lexer, parser, expansion, I/O redirect,
and visitor API assessments.

## 1. Package Overview

| File | Lines | Classes / Functions |
|------|-------|---------------------|
| `__init__.py` | 51 | 13 `__all__` entries (re-exports) |
| `core.py` | 319 | `ExecutorVisitor` |
| `command.py` | 611 | `CommandExecutor` |
| `pipeline.py` | 502 | `PipelineContext`, `PipelineExecutor` |
| `control_flow.py` | 649 | `ControlFlowExecutor` |
| `strategies.py` | 424 | `ExecutionStrategy` (ABC), `SpecialBuiltinExecutionStrategy`, `BuiltinExecutionStrategy`, `FunctionExecutionStrategy`, `AliasExecutionStrategy`, `ExternalExecutionStrategy`; `POSIX_SPECIAL_BUILTINS` constant |
| `process_launcher.py` | 343 | `ProcessRole` (enum), `ProcessConfig` (dataclass), `ProcessLauncher` |
| `function.py` | 137 | `FunctionOperationExecutor` |
| `subshell.py` | 311 | `SubshellExecutor` |
| `array.py` | 277 | `ArrayOperationExecutor` |
| `context.py` | 189 | `ExecutionContext` (dataclass) |
| `child_policy.py` | 45 | `apply_child_signal_policy()` function |
| `test_evaluator.py` | 199 | `TestExpressionEvaluator` |
| **Total** | **~4,057** | **14 classes + 1 function + 1 constant** |

## 2. Current `__all__`

```python
__all__ = [
    'ExecutorVisitor',
    'ExecutionContext',
    'PipelineContext',
    'PipelineExecutor',
    'CommandExecutor',
    'ControlFlowExecutor',
    'ArrayOperationExecutor',
    'FunctionOperationExecutor',
    'SubshellExecutor',
    'ExecutionStrategy',
    'BuiltinExecutionStrategy',
    'FunctionExecutionStrategy',
    'ExternalExecutionStrategy'
]
```

13 items exported.  All 13 have matching import statements in
`__init__.py`, so everything listed is actually importable from the
package path.

## 3. Tier Analysis

### Tier 1: Production callers outside `psh/executor/`

| Export | Production callers | Files |
|--------|-------------------|-------|
| `ExecutorVisitor` | 2 sites in 1 file | `shell.py` (`execute_command_list`, `execute_toplevel`) |
| `ExecutionContext` | 1 site in 1 file | `builtins/command_builtin.py` (bypass: `from ..executor.context import`) |
| `ExternalExecutionStrategy` | 1 site in 1 file | `builtins/command_builtin.py` (bypass: `from ..executor.strategies import`) |

**3 of 13 exports have production callers.**

#### Effective API

The real contract used by production code is just three items:

```python
# Main entry point (used by shell.py)
from psh.executor import ExecutorVisitor

# Used by command_builtin.py (currently via bypass imports)
from psh.executor import ExecutionContext
from psh.executor import ExternalExecutionStrategy
```

Note: `ExecutionContext` and `ExternalExecutionStrategy` are imported via
submodule paths (`from ..executor.context import ExecutionContext`,
`from ..executor.strategies import ExternalExecutionStrategy`) rather than
from the package.  The package-level re-exports exist but are unused.

### Tier 2: Test-only usage

No items in `__all__` are imported by test files.  The single test import
from the executor package is `apply_child_signal_policy` from
`child_policy.py`, which is not in `__all__`.

### Tier 3: Zero callers outside `psh/executor/`

| Export | Notes |
|--------|-------|
| `PipelineContext` | Used only internally by `pipeline.py` and `core.py`. |
| `PipelineExecutor` | Used only internally by `core.py`. |
| `CommandExecutor` | Used only internally by `core.py`. |
| `ControlFlowExecutor` | Used only internally by `core.py`. |
| `ArrayOperationExecutor` | Used only internally by `core.py`. |
| `FunctionOperationExecutor` | Used only internally by `core.py`. |
| `SubshellExecutor` | Used only internally by `core.py`. |
| `ExecutionStrategy` | Used only internally by `strategies.py` and `command.py`. |
| `BuiltinExecutionStrategy` | Used only internally by `command.py`. |
| `FunctionExecutionStrategy` | Used only internally by `command.py`. |

**10 of 13 exports have zero callers outside the package.**

All ten are specialised executors that are constructed and used
exclusively by `ExecutorVisitor` in `core.py`.  External code accesses
execution through the `ExecutorVisitor` facade; the sub-executors are
implementation details.

## 4. Items Not in `__all__` That Have External Callers

### `apply_child_signal_policy` (from `child_policy.py`)

Used by 3 external files (2 production, 1 test):

| File | Import path |
|------|-------------|
| `psh/expansion/command_sub.py` | `from psh.executor.child_policy import apply_child_signal_policy` |
| `psh/io_redirect/process_sub.py` | `from psh.executor.child_policy import apply_child_signal_policy` |
| `tests/unit/executor/test_child_policy.py` | `from psh.executor.child_policy import apply_child_signal_policy` |

This function is the single source of truth for child process signal
setup, documented in the executor CLAUDE.md as being used by all 5 fork
paths.  Three of those fork paths are inside the executor package
(`process_launcher.py`), while two are in external packages
(`expansion/command_sub.py`, `io_redirect/process_sub.py`).

### `TestExpressionEvaluator` (from `test_evaluator.py`)

Used by 1 external file:

| File | Import path |
|------|-------------|
| `psh/shell.py` | `from .executor.test_evaluator import TestExpressionEvaluator` |

The `shell.py` method `execute_enhanced_test_statement()` constructs a
`TestExpressionEvaluator` directly.  This is the only way `[[ ]]` test
expressions are evaluated.

## 5. Bypass Imports

Four production files import from executor submodules instead of from
the package:

| File | Import | Exported in `__all__`? |
|------|--------|----------------------|
| `builtins/command_builtin.py` | `from ..executor.context import ExecutionContext` | Yes |
| `builtins/command_builtin.py` | `from ..executor.strategies import ExternalExecutionStrategy` | Yes |
| `shell.py` | `from .executor.test_evaluator import TestExpressionEvaluator` | No |
| `expansion/command_sub.py` | `from psh.executor.child_policy import apply_child_signal_policy` | No |
| `io_redirect/process_sub.py` | `from psh.executor.child_policy import apply_child_signal_policy` | No |

The `command_builtin.py` imports bypass the package for items that *are*
in `__all__`.  The other three bypass the package for items that are
*not* in `__all__` (and therefore must use the submodule path).

## 6. `__init__.py` Docstring Issues

The module docstring (lines 8-18) references two modules that do not
exist:

```
- arithmetic: Arithmetic evaluation execution
- utils: Shared utilities and helpers
```

There is no `arithmetic.py` or `utils.py` in the executor package.
Arithmetic evaluation is handled by `psh/arithmetic.py` (outside the
executor) and invoked from `core.py` and `control_flow.py`.  There is
no separate `utils` module.

## 7. Strategy Pattern Analysis

The executor uses a strategy pattern for command execution with five
strategy classes:

| Strategy | In `__all__`? | External callers |
|----------|--------------|-----------------|
| `ExecutionStrategy` (ABC) | Yes | 0 |
| `SpecialBuiltinExecutionStrategy` | No | 0 |
| `BuiltinExecutionStrategy` | Yes | 0 |
| `FunctionExecutionStrategy` | Yes | 0 |
| `AliasExecutionStrategy` | No | 0 |
| `ExternalExecutionStrategy` | Yes | 1 (`command_builtin.py`) |

Only `ExternalExecutionStrategy` has an external caller.  The other
four strategies (and the ABC) are used exclusively within the package.
`SpecialBuiltinExecutionStrategy` and `AliasExecutionStrategy` are not
in `__all__` and are internal-only -- correctly so.

The inclusion of `ExecutionStrategy`, `BuiltinExecutionStrategy`, and
`FunctionExecutionStrategy` in `__all__` appears aspirational: they were
exported for potential future use by external code that might want to
plug into the strategy chain, but no such code exists.

## 8. Architectural Observations

### 8.1 Clean facade pattern

`ExecutorVisitor` is an effective facade.  All external code creates an
`ExecutorVisitor` and calls `visit(ast)`.  The specialised executors
(`CommandExecutor`, `PipelineExecutor`, `ControlFlowExecutor`,
`FunctionOperationExecutor`, `ArrayOperationExecutor`,
`SubshellExecutor`) are implementation details hidden behind the
facade.  This is good design, and the `__all__` should reflect it.

### 8.2 `ProcessLauncher` is correctly internal

`ProcessLauncher`, `ProcessConfig`, and `ProcessRole` are used by
`strategies.py`, `pipeline.py`, and `subshell.py` -- all within the
executor package.  No external code imports them.  This is proper
encapsulation.

### 8.3 `apply_child_signal_policy` crosses package boundaries

This function is architecturally interesting: it's the single source of
truth for child signal setup, used by all 5 fork paths in the codebase.
Three of those paths are in the executor package, but two are in
`expansion/` and `io_redirect/`.  Currently it lives in the executor
package and is imported via submodule path by the external callers.

Two options:

1. **Add to executor `__all__`** -- simplest change, acknowledges the
   cross-package contract.
2. **Move to `psh/core/`** -- the function doesn't depend on executor
   internals (it takes a signal manager and state object).  Moving it
   to `psh/core/` would make the cross-package dependency cleaner,
   since `psh/core/` is already a dependency of all packages.

Option 1 is simpler and sufficient.  Option 2 is architecturally
cleaner but a larger change with no functional benefit.

### 8.4 `TestExpressionEvaluator` is executor-adjacent

`TestExpressionEvaluator` is only used by `shell.py`.  It evaluates
`[[ ]]` expressions and calls into `psh/builtins/test_command.py` and
`psh/utils/file_tests.py`.  It doesn't depend on `ExecutorVisitor` or
any other executor class -- it's a leaf evaluator that happens to live
in the executor package.  It could equally live in `psh/builtins/` or
`psh/utils/`.

### 8.5 `ExecutionContext` usage is minimal

`ExecutionContext` is a dataclass with 10 fields and 7 factory methods.
It's used extensively *within* the executor package (passed between
executors), but externally only `command_builtin.py` creates one.  The
external caller constructs it with defaults (`ExecutionContext()`) and
uses it only to satisfy the `ExternalExecutionStrategy.execute()`
signature.

### 8.6 `POSIX_SPECIAL_BUILTINS` is purely internal

The set constant `POSIX_SPECIAL_BUILTINS` in `strategies.py` is used
only within that file.  It is not in `__all__` and has zero external
callers.  Correctly internal.

## 9. Recommendations

### R1. Trim `__all__` from 13 to 3 items

Remove all items with zero external callers.  The executor's effective
public API is three items:

```python
__all__ = [
    'ExecutorVisitor',
    'ExecutionContext',
    'ExternalExecutionStrategy',
]
```

**Keep the import statements** for the removed items so they remain
importable from `psh.executor` for any code that might reference them.

**Remove from `__all__`:**
- `PipelineContext` -- zero external callers; internal to pipeline
  execution
- `PipelineExecutor` -- zero external callers; used only by
  `ExecutorVisitor`
- `CommandExecutor` -- zero external callers; used only by
  `ExecutorVisitor`
- `ControlFlowExecutor` -- zero external callers; used only by
  `ExecutorVisitor`
- `ArrayOperationExecutor` -- zero external callers; used only by
  `ExecutorVisitor`
- `FunctionOperationExecutor` -- zero external callers; used only by
  `ExecutorVisitor`
- `SubshellExecutor` -- zero external callers; used only by
  `ExecutorVisitor`
- `ExecutionStrategy` -- zero external callers; ABC for internal
  strategy pattern
- `BuiltinExecutionStrategy` -- zero external callers; internal
  strategy
- `FunctionExecutionStrategy` -- zero external callers; internal
  strategy

**Rationale:** Removing from `__all__` does not break any code -- items
remain importable via their module paths and as convenience imports.
The current `__all__` exports 13 items but only 3 are imported by
external code, giving a misleading impression of the package's API
surface.

### R2. Add `apply_child_signal_policy` and `TestExpressionEvaluator`

Add the two items that have external production callers but are
currently not in `__all__`:

```python
from .child_policy import apply_child_signal_policy
from .test_evaluator import TestExpressionEvaluator
```

And add to `__all__`:

```python
__all__ = [
    'ExecutorVisitor',
    'ExecutionContext',
    'ExternalExecutionStrategy',
    'apply_child_signal_policy',
    'TestExpressionEvaluator',
]
```

This acknowledges the actual cross-package contracts.  External callers
can then import from the package path instead of reaching into
submodules.

### R3. Fix bypass imports

Update the 2 production files that bypass the package for items that
*are* in `__all__`:

```python
# builtins/command_builtin.py -- currently:
from ..executor.context import ExecutionContext
from ..executor.strategies import ExternalExecutionStrategy
# Preferred:
from ..executor import ExecutionContext, ExternalExecutionStrategy
```

After R2, also update the files that bypass for newly-exported items:

```python
# shell.py -- currently:
from .executor.test_evaluator import TestExpressionEvaluator
# Preferred:
from .executor import TestExpressionEvaluator

# expansion/command_sub.py -- currently:
from psh.executor.child_policy import apply_child_signal_policy
# Preferred:
from psh.executor import apply_child_signal_policy

# io_redirect/process_sub.py -- currently:
from psh.executor.child_policy import apply_child_signal_policy
# Preferred:
from psh.executor import apply_child_signal_policy
```

### R4. Fix `__init__.py` docstring

Remove references to non-existent modules (`arithmetic`, `utils`).
Add references to modules actually in the package (`child_policy`,
`test_evaluator`):

```python
"""
PSH Executor Package

This package implements the execution engine for PSH using a modular
visitor pattern architecture. It transforms AST nodes into executed
commands with proper process management, I/O handling, and job control.

The package is organized into focused modules:
- core: Main ExecutorVisitor coordinating execution
- command: Simple command execution (builtins, functions, externals)
- pipeline: Pipeline execution and process management
- control_flow: Control structures (if, while, for, case, select)
- function: Function execution and scope management
- array: Array initialization and element operations
- subshell: Subshell and brace group execution
- context: Execution context and state management
- strategies: Execution strategies (builtin, function, alias, external)
- process_launcher: Unified process creation with job control
- child_policy: Child process signal setup
- test_evaluator: [[ ]] test expression evaluation
"""
```

### R5. Update executor CLAUDE.md

The CLAUDE.md Key Files table is accurate.  No changes needed beyond
verifying it stays in sync with any R1-R4 changes.

## 10. Priority Order

| Priority | Recommendation | Risk | Impact |
|----------|---------------|------|--------|
| 1 | R1. Trim `__all__` from 13 to 3 | None | API hygiene -- removes 10 items with zero external callers |
| 2 | R4. Fix docstring | None | Documentation accuracy |
| 3 | R2. Add 2 items to `__all__` | None | Acknowledges existing cross-package contracts |
| 4 | R3. Fix bypass imports | None | Import consistency |

All four are safe, zero-risk changes.

## 11. New `__all__` (after R1 + R2)

```python
__all__ = [
    # Main entry point (facade for all execution)
    'ExecutorVisitor',
    # Execution context (used by command_builtin.py)
    'ExecutionContext',
    # External command strategy (used by command_builtin.py)
    'ExternalExecutionStrategy',
    # Child process signal policy (used by expansion, io_redirect)
    'apply_child_signal_policy',
    # Test expression evaluator (used by shell.py)
    'TestExpressionEvaluator',
]
```

5 items (down from 13).  All 5 have production callers outside the
package.

## 12. Files Modified (if all recommendations implemented)

| File | Changes |
|------|---------|
| `psh/executor/__init__.py` | Trim `__all__` from 13 to 5; add 2 new imports; fix docstring (R1, R2, R4) |
| `psh/builtins/command_builtin.py` | Fix 2 bypass imports (R3) |
| `psh/shell.py` | Fix 1 bypass import (R3) |
| `psh/expansion/command_sub.py` | Fix 1 bypass import (R3) |
| `psh/io_redirect/process_sub.py` | Fix 1 bypass import (R3) |

## 13. Verification

```bash
# Verify public API imports work
python -c "from psh.executor import ExecutorVisitor, ExecutionContext, ExternalExecutionStrategy, apply_child_signal_policy, TestExpressionEvaluator; print('OK')"

# Verify demoted items still importable
python -c "from psh.executor import PipelineContext, PipelineExecutor, CommandExecutor, ControlFlowExecutor; print('OK')"
python -c "from psh.executor import ArrayOperationExecutor, FunctionOperationExecutor, SubshellExecutor; print('OK')"
python -c "from psh.executor import ExecutionStrategy, BuiltinExecutionStrategy, FunctionExecutionStrategy; print('OK')"

# Verify internal items importable from submodules
python -c "from psh.executor.process_launcher import ProcessLauncher, ProcessConfig, ProcessRole; print('OK')"
python -c "from psh.executor.strategies import SpecialBuiltinExecutionStrategy, AliasExecutionStrategy; print('OK')"

# Run executor tests
python -m pytest tests/unit/executor/ -q --tb=short
python -m pytest tests/integration/ -q --tb=short

# Run full suite
python run_tests.py > tmp/test-results.txt 2>&1; tail -15 tmp/test-results.txt
grep FAILED tmp/test-results.txt

# Lint
ruff check psh/executor/ psh/builtins/command_builtin.py psh/shell.py psh/expansion/command_sub.py psh/io_redirect/process_sub.py
```

## Related Documents

- `psh/executor/CLAUDE.md` -- AI assistant working guide
- `docs/guides/visitor_public_api_assessment.md` -- Same analysis for
  the visitor package (implemented in v0.181.0)
- `docs/guides/expansion_public_api_assessment.md` -- Same analysis for
  the expansion package (implemented in v0.180.0)
- `docs/guides/io_redirect_public_api_assessment.md` -- Same analysis
  for the I/O redirect package (implemented in v0.179.0)
- `docs/guides/parser_public_api_assessment.md` -- Same analysis for
  the parser package (implemented in v0.178.0)
- `docs/guides/lexer_public_api_assessment.md` -- Same analysis for the
  lexer package (implemented in v0.177.0)
- `ARCHITECTURE.llm` -- System-wide architecture reference
