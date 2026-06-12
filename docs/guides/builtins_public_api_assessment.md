# Builtins Public API Assessment

**As of v0.183.0**

This document assesses the builtins package's public API contract -- what
is exported vs what is actually used -- and recommends cleanup actions.
Follows the same methodology as the lexer, parser, expansion, I/O
redirect, visitor, executor, and utils API assessments.

## 1. Package Overview

| File | Lines | Classes / Functions |
|------|-------|---------------------|
| `__init__.py` | 35 | Re-exports `registry`, `builtin`, `Builtin`; imports 25 modules |
| `base.py` | 58 | `Builtin` (ABC) |
| `registry.py` | 63 | `BuiltinRegistry`, `builtin()` decorator, `registry` singleton |
| `aliases.py` | ~140 | `AliasBuiltin`, `UnaliasBuiltin` |
| `command_builtin.py` | ~200 | `CommandBuiltin` |
| `core.py` | ~230 | `ExitBuiltin`, `ColonBuiltin`, `TrueBuiltin`, `FalseBuiltin`, `ExecBuiltin` |
| `debug_control.py` | ~290 | `DebugASTBuiltin`, `DebugBuiltin`, `SignalsBuiltin` |
| `directory_stack.py` | ~440 | `DirectoryStack` (helper), `PushdBuiltin`, `PopdBuiltin`, `DirsBuiltin` |
| `disown.py` | ~170 | `DisownBuiltin` |
| `environment.py` | ~570 | `EnvBuiltin`, `ExportBuiltin`, `SetBuiltin`, `UnsetBuiltin` |
| `eval_command.py` | ~40 | `EvalBuiltin` |
| `function_support.py` | ~825 | `FunctionReturn` (exception), `DeclareBuiltin`, `TypesetBuiltin`, `ReadonlyBuiltin`, `ReturnBuiltin` |
| `help_command.py` | ~60 | `HelpBuiltin` |
| `io.py` | ~780 | `EchoBuiltin`, `PrintfBuiltin`, `PwdBuiltin` |
| `job_control.py` | ~230 | `JobsBuiltin`, `FgBuiltin`, `BgBuiltin`, `WaitBuiltin` |
| `kill_command.py` | ~300 | `KillBuiltin` + module-level signal dicts |
| `navigation.py` | ~180 | `CdBuiltin` |
| `parse_tree.py` | ~200 | `ParseTreeBuiltin`, `ShowASTBuiltin`, `ASTDotBuiltin` |
| `parser_control.py` | ~290 | `ParserConfigBuiltin`, `ParserModeBuiltin` |
| `parser_experiment.py` | 67 | `PARSERS` (dict), `PARSER_LABELS` (dict), `ParserSelectBuiltin` |
| `positional.py` | ~170 | `ShiftBuiltin`, `GetoptsBuiltin` |
| `read_builtin.py` | ~300 | `ReadBuiltin` |
| `shell_options.py` | ~130 | `ShoptBuiltin` |
| `shell_state.py` | ~130 | `HistoryBuiltin`, `VersionBuiltin`, `LocalBuiltin` |
| `signal_handling.py` | ~260 | `TrapBuiltin` |
| `source_command.py` | ~130 | `SourceBuiltin`, `DotBuiltin` |
| `test_command.py` | ~430 | `TestBuiltin`, `BracketBuiltin` |
| `type_builtin.py` | ~120 | `TypeBuiltin` |
| **Total** | **~6,870** | **~50 builtin classes + 3 infrastructure items** |

## 2. Current State

`__init__.py` declares:

```python
__all__ = ['registry', 'builtin', 'Builtin']
```

It also imports all 25 builtin modules (as bare `from . import ...`
statements) to trigger `@builtin` decorator registration at import time.

The `__all__` is minimal and clean, but it does not include two items
that have production callers outside the package: `FunctionReturn` and
`PARSERS`.

## 3. Caller Analysis

### Items with production callers outside `psh/builtins/`

| Item | Module | Production callers | Files |
|------|--------|--------------------|-------|
| `registry` | `registry` | 2 | `shell.py`, `executor/pipeline.py` |
| `builtin` | `registry` | 0 external | Only used within the package (decorator) |
| `Builtin` | `base` | 0 external | Only used within the package (base class) |
| `FunctionReturn` | `function_support` | 5 | `executor/core.py`, `executor/command.py`, `executor/function.py`, `executor/strategies.py` (x2) |
| `PARSERS` | `parser_experiment` | 1 | `__main__.py` |
| `TestBuiltin` | `test_command` | 1 | `executor/test_evaluator.py` |

### Import patterns

**Package-level imports (correct):**
- `psh/shell.py:10`: `from .builtins import registry as builtin_registry`

**Submodule imports (bypass):**
- `psh/executor/core.py:42`: `from ..builtins.function_support import FunctionReturn`
- `psh/executor/function.py:10`: `from ..builtins.function_support import FunctionReturn`
- `psh/executor/command.py:185`: `from ..builtins.function_support import FunctionReturn` (lazy)
- `psh/executor/strategies.py:77`: `from ..builtins.function_support import FunctionReturn` (lazy)
- `psh/executor/strategies.py:134`: `from ..builtins.function_support import FunctionReturn` (lazy)
- `psh/executor/pipeline.py:331`: `from ..builtins.registry import registry` (lazy)
- `psh/executor/test_evaluator.py:144`: `from ..builtins.test_command import TestBuiltin` (lazy)
- `psh/__main__.py:154`: `from .builtins.parser_experiment import PARSERS` (lazy)

### Items with test-only callers

No test files import directly from `psh.builtins`.  All test code
interacts with builtins through `captured_shell.run_command()`.

### Items with zero callers outside `psh/builtins/`

| Item | Module | Notes |
|------|--------|-------|
| `Builtin` | `base` | Base class; only subclassed within the package |
| `builtin` | `registry` | Decorator; only applied within the package |
| `DirectoryStack` | `directory_stack` | Helper class; only used by pushd/popd/dirs builtins |
| `PARSER_LABELS` | `parser_experiment` | Only used within `ParserSelectBuiltin.execute()` |
| All ~50 builtin classes | Various | Accessed through `registry.get()`, never imported directly (except `TestBuiltin`) |

## 4. Architectural Observations

### 4.1 The package is well-designed

Unlike the `utils/` grab-bag, the builtins package has a clear,
cohesive architecture:

- **Infrastructure** (3 files): `base.py`, `registry.py`, `__init__.py`
- **Builtin commands** (25 files): Each file groups related commands

The `@builtin` decorator + auto-import pattern in `__init__.py` is
clean and self-documenting.  Adding a new builtin requires only creating
a file, applying the decorator, and importing it in `__init__.py`.

### 4.2 `FunctionReturn` is misplaced

`FunctionReturn` is an exception class for control flow.  It is defined
in `function_support.py` alongside `DeclareBuiltin`, `ReturnBuiltin`,
etc.  However, its 5 production callers are all in `psh/executor/` --
it is a control-flow mechanism shared between builtins and the executor.

Three of the five executor imports are lazy (inside `except` blocks)
with comments about avoiding circular imports.  This suggests the class
was placed in builtins for pragmatic reasons (it's raised by
`ReturnBuiltin`) rather than because it logically belongs there.

Peer exceptions `LoopBreak` and `LoopContinue` live in
`psh/core/exceptions.py`, which is the canonical location for
cross-cutting control-flow exceptions.

### 4.3 `PARSERS` is a module-level data structure exported from a builtin

`parser_experiment.py` defines `PARSERS` as a module-level dict mapping
parser names to their aliases.  It is used both within the file (by
`ParserSelectBuiltin`) and externally by `__main__.py` for `--parser`
CLI argument matching.  This couples CLI argument parsing to a builtin
module, which is unusual.

### 4.4 `TestBuiltin` is instantiated directly by the executor

`executor/test_evaluator.py:144-149` creates a new `TestBuiltin()`
instance on every `[[ ]]` unary-test evaluation to reuse its
`_evaluate_unary()` method.  This:

1. Creates a new object on every call (allocates + initialises).
2. Accesses a private method (`_evaluate_unary`) -- a coupling smell.
3. Bypasses the registry entirely (the builtin is also registered
   under `"test"` and `"["`).

The underlying issue is that unary file-test logic is duplicated: it
lives in `TestBuiltin._evaluate_unary()` but is needed by both the
`test`/`[` builtin and the `[[ ]]` executor.  The logic should be
extracted to a shared location.

### 4.5 `name` property inconsistency

The `Builtin` base class declares `name` as an `@property @abstractmethod`.
Two patterns are used by subclasses:

| Pattern | Count | Example |
|---------|-------|---------|
| `@property def name(self): return "foo"` | ~43 builtins | Most builtins |
| `name = "foo"` (class variable) | 10 builtins | `debug_control.py`, `eval_command.py`, `parse_tree.py`, `parser_control.py`, `parser_experiment.py` |

Both patterns work in Python (a class variable satisfies an abstract
property), but the inconsistency makes the codebase harder to scan.
The class-variable pattern is more concise and arguably preferable.

### 4.6 CLAUDE.md has documentation errors

The builtins `CLAUDE.md` has two incorrect file-to-command mappings:

| CLAUDE.md says | Actual location |
|----------------|-----------------|
| `io.py`: `echo`, `printf`, `true`, `false`, `:` | `io.py` has `echo`, `printf`, `pwd` |
| `navigation.py`: `cd`, `pwd` | `navigation.py` has only `cd` |
| `core.py`: `exit`, `exec` | `core.py` has `exit`, `exec`, `:`, `true`, `false` |

`PwdBuiltin` is in `io.py` but CLAUDE.md places it in `navigation.py`.
`true`, `false`, `:` are in `core.py` but CLAUDE.md places them in
`io.py`.

### 4.7 `caller` builtin is documented but not implemented

`psh/visitor/constants.py` lists `'caller'` in the `SHELL_BUILTINS`
set, and `psh/builtins/CLAUDE.md` lists `caller` as a command in
`function_support.py`.  However, no `CallerBuiltin` class exists
anywhere in the codebase.  This is either a planned feature or
documentation debt.

### 4.8 `pipeline.py` bypasses the package-level `registry` import

`executor/pipeline.py:331` imports `registry` from the submodule path
(`from ..builtins.registry import registry`) instead of from the package
(`from ..builtins import registry`).  The package-level re-export exists
and is used correctly by `shell.py`.

## 5. Recommendations

### R1. Add `FunctionReturn` to `__all__` and fix bypass imports

`FunctionReturn` has 5 production callers in the executor package.  It
should be part of the builtins public API.

**`psh/builtins/__init__.py`** -- add import and `__all__` entry:

```python
from .base import Builtin
from .function_support import FunctionReturn
from .registry import builtin, registry

__all__ = ['registry', 'builtin', 'Builtin', 'FunctionReturn']
```

Then fix the 5 bypass imports in executor files:

| File | Current | Preferred |
|------|---------|-----------|
| `executor/core.py:42` | `from ..builtins.function_support import FunctionReturn` | `from ..builtins import FunctionReturn` |
| `executor/function.py:10` | `from ..builtins.function_support import FunctionReturn` | `from ..builtins import FunctionReturn` |
| `executor/command.py:185` | `from ..builtins.function_support import FunctionReturn` | `from ..builtins import FunctionReturn` |
| `executor/strategies.py:77` | `from ..builtins.function_support import FunctionReturn` | `from ..builtins import FunctionReturn` |
| `executor/strategies.py:134` | `from ..builtins.function_support import FunctionReturn` | `from ..builtins import FunctionReturn` |

**Note:** Three of these are lazy imports inside `except` blocks.  They
should remain lazy (keep inside the block) but use the package path.

**Alternative (considered):** Move `FunctionReturn` to
`psh/core/exceptions.py` alongside `LoopBreak` and `LoopContinue`.
This is architecturally cleaner but would require updating 6 import
sites (5 in executor + 1 in `function_support.py` where it's raised).
This is a judgement call; the minimal change is to add it to `__all__`.

### R2. Fix `registry` bypass import in `pipeline.py`

**`psh/executor/pipeline.py:331`**:

```python
# from ..builtins.registry import registry
from ..builtins import registry
```

This is a lazy import inside a method.  Keep it lazy but use the
package path.

### R3. Fix CLAUDE.md documentation errors

**`psh/builtins/CLAUDE.md`** -- correct the file-to-command mapping
table:

| Current | Corrected |
|---------|-----------|
| `io.py`: `echo`, `printf`, `true`, `false`, `:` | `io.py`: `echo`, `printf`, `pwd` |
| `navigation.py`: `cd`, `pwd` | `navigation.py`: `cd` |
| `core.py`: `exit`, `exec` | `core.py`: `exit`, `:`, `true`, `false`, `exec` |

Also remove the `caller` entry from `function_support.py`'s row, or
mark it as not yet implemented.

### R4. Add `PARSERS` to `__all__` (optional)

`PARSERS` is imported by `__main__.py`.  Adding it to `__all__` would
document this dependency:

```python
from .parser_experiment import PARSERS

__all__ = ['registry', 'builtin', 'Builtin', 'FunctionReturn', 'PARSERS']
```

This is a low-priority change.  `__main__.py` uses a lazy import inside
a conditional branch, and `PARSERS` is a simple data structure.  The
import is unlikely to move.

**Alternatively**, the `PARSERS` dict could be kept private and
`__main__.py` could duplicate the 4-line mapping.  But the current
shared-constant approach is reasonable.

## 6. Non-Recommendations (Considered and Rejected)

### Moving `FunctionReturn` to `psh/core/exceptions.py`

While architecturally cleaner (co-locating it with `LoopBreak` and
`LoopContinue`), this would:

1. Move the exception away from `ReturnBuiltin` which raises it.
2. Require updating 6 import sites.
3. Add `FunctionReturn` to `psh/core/` which is otherwise not
   coupled to builtins.

The benefit is small -- the class is trivial (4 lines) and the import
path is not confusing.  Adding it to builtins' `__all__` is sufficient.

### Extracting unary test logic from `TestBuiltin`

`executor/test_evaluator.py` instantiates `TestBuiltin()` to call its
`_evaluate_unary()` method.  Extracting this to a shared module (e.g.
`psh/utils/test_helpers.py` or a module-level function in
`test_command.py`) would:

1. Eliminate the direct `TestBuiltin` class import.
2. Remove the per-call object allocation.
3. Decouple the executor from the builtin implementation.

However, this is a refactoring task, not a public API cleanup.  The
current coupling is functional and the performance impact is negligible.
Recommend deferring to a future refactoring pass.

### Standardising `name` to class variables

Converting all 43 `@property def name` definitions to `name = "foo"`
class variables would be a large churn (43 files) for purely cosmetic
benefit.  Both patterns are valid Python.  The inconsistency is minor
and not worth a dedicated cleanup.

### Moving `PwdBuiltin` from `io.py` to `navigation.py`

While CLAUDE.md documents `pwd` as belonging in `navigation.py`, moving
it would:

1. Change import structure within `__init__.py`.
2. Require updating any tests that reference the module path.
3. Risk breaking the builtin's registration if not done carefully.

The current placement in `io.py` is functional.  The fix should be to
correct the CLAUDE.md documentation to match reality rather than move
the code.

## 7. Priority Order

| Priority | Recommendation | Risk | Impact |
|----------|---------------|------|--------|
| 1 | R1. Add `FunctionReturn` to `__all__` + fix 5 bypass imports | None | Documents cross-package dependency; consistent import paths |
| 2 | R2. Fix `registry` bypass import in `pipeline.py` | None | Import consistency |
| 3 | R3. Fix CLAUDE.md documentation errors | None | Accurate documentation |
| 4 | R4. Add `PARSERS` to `__all__` | None | Documents `__main__.py` dependency |

All four are safe, zero-risk changes.

## 8. New `__all__` (after R1 and R4)

```python
__all__ = ['registry', 'builtin', 'Builtin', 'FunctionReturn', 'PARSERS']
```

5 items.  `registry`, `FunctionReturn`, and `PARSERS` have production
callers outside the package.  `builtin` and `Builtin` are the package's
authoring contract for defining new builtins.

## 9. Items Not in `__all__` (Internal)

After cleanup, the following remain importable from their submodules
but are not part of the package-level API:

| Item | Module | Callers |
|------|--------|---------|
| `TestBuiltin` | `test_command` | 1 (executor/test_evaluator.py) -- accesses private method |
| `DirectoryStack` | `directory_stack` | Internal only (used by pushd/popd/dirs) |
| `PARSER_LABELS` | `parser_experiment` | Internal only |
| All ~50 builtin classes | Various | Accessed through `registry.get()` at runtime |
| `BuiltinRegistry` | `registry` | The class itself is not imported; only the singleton `registry` instance |

## 10. Files Modified (if all recommendations implemented)

| File | Changes |
|------|---------|
| `psh/builtins/__init__.py` | Add `FunctionReturn` import; optionally add `PARSERS` import; update `__all__` |
| `psh/executor/core.py` | Fix `FunctionReturn` bypass import (R1) |
| `psh/executor/function.py` | Fix `FunctionReturn` bypass import (R1) |
| `psh/executor/command.py` | Fix `FunctionReturn` bypass import (R1) |
| `psh/executor/strategies.py` | Fix 2 `FunctionReturn` bypass imports (R1) |
| `psh/executor/pipeline.py` | Fix `registry` bypass import (R2) |
| `psh/builtins/CLAUDE.md` | Fix command-to-file mapping table (R3) |

## 11. Verification

```bash
# Smoke test -- new public API
python -c "from psh.builtins import registry, builtin, Builtin, FunctionReturn; print('OK')"

# Smoke test -- PARSERS (if R4 implemented)
python -c "from psh.builtins import PARSERS; print('OK')"

# Smoke test -- internal items still importable from submodules
python -c "from psh.builtins.test_command import TestBuiltin; print('OK')"
python -c "from psh.builtins.directory_stack import DirectoryStack; print('OK')"

# Run builtin tests
python -m pytest tests/unit/builtins/ -q --tb=short

# Run executor tests (verify FunctionReturn import changes)
python -m pytest tests/integration/ -q --tb=short

# Run full suite
python run_tests.py > tmp/test-results.txt 2>&1; tail -15 tmp/test-results.txt
grep FAILED tmp/test-results.txt

# Lint
ruff check psh/builtins/__init__.py psh/executor/core.py psh/executor/function.py psh/executor/command.py psh/executor/strategies.py psh/executor/pipeline.py
```

## 12. Related Documents

- `psh/builtins/CLAUDE.md` -- Subsystem working guide (has errors; R3)
- `psh/executor/CLAUDE.md` -- Executor subsystem guide
- `docs/guides/executor_public_api.md` -- Executor API reference
  (references `TestExpressionEvaluator`, the sole caller of
  `TestBuiltin`)
- `docs/guides/utils_public_api_assessment.md` -- Previous assessment
  in this series
- `ARCHITECTURE.md` -- System-wide architecture reference (the former ARCHITECTURE.llm is archived)
