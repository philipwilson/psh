# Visitor Public API Assessment

**As of v0.180.0**

This document assesses the public API surface of the `psh/visitor/`
package, catalogues every exported symbol, maps the caller graph, and
recommends improvements.  Follows the same methodology as the lexer,
parser, expansion, and I/O redirect API assessments.

## 1. Package Overview

| File | Lines | Classes / Functions |
|------|-------|---------------------|
| `__init__.py` | 32 | 14 `__all__` entries (re-exports) |
| `base.py` | 169 | `ASTVisitor[T]`, `ASTTransformer`, `CompositeVisitor` |
| `constants.py` | 98 | 5 data constants (dicts and sets) |
| `debug_ast_visitor.py` | 390 | `DebugASTVisitor` |
| `validator_visitor.py` | 501 | `Severity` (enum), `ValidationIssue`, `ValidatorVisitor` |
| `enhanced_validator_visitor.py` | 668 | `VariableInfo`, `VariableTracker`, `ValidatorConfig`, `EnhancedValidatorVisitor` |
| `formatter_visitor.py` | 494 | `FormatterVisitor` |
| `linter_visitor.py` | 406 | `LintLevel` (enum), `LintIssue`, `LinterConfig`, `LinterVisitor` |
| `metrics_visitor.py` | 584 | `CodeMetrics`, `MetricsVisitor` |
| `security_visitor.py` | 332 | `SecurityIssue`, `SecurityVisitor` |
| **Total** | **3,674** | **20 classes + 5 data constants** |

## 2. Current `__all__`

```python
__all__ = [
    'ASTVisitor',
    'ASTTransformer',
    'FormatterVisitor',
    'ValidatorVisitor',
    'DebugASTVisitor',
    'EnhancedValidatorVisitor',
    'ValidatorConfig',
    'VariableTracker',
    'MetricsVisitor',
    'LinterVisitor',
    'LinterConfig',
    'LintLevel',
    'SecurityVisitor',
    'SecurityIssue',
]
```

14 items exported.  All 14 have matching import statements in
`__init__.py`, so everything listed is actually importable from the
package path.

## 3. Tier Analysis

### Tier 1: Production callers outside `psh/visitor/`

| Export | Production callers | Files |
|--------|-------------------|-------|
| `ASTVisitor` | 7 production files | `executor/core.py` (direct), `executor/{function,pipeline,control_flow,subshell}.py` (TYPE_CHECKING), `parser/validation/{validation_pipeline,semantic_analyzer}.py` (direct) |
| `EnhancedValidatorVisitor` | 2 production files | `shell.py` (lazy), `scripting/source_processor.py` (lazy) |
| `FormatterVisitor` | 1 production file | `shell.py` (lazy) |
| `MetricsVisitor` | 1 production file | `shell.py` (lazy) |
| `SecurityVisitor` | 1 production file | `shell.py` (lazy) |
| `LinterVisitor` | 1 production file | `shell.py` (lazy) |
| `DebugASTVisitor` | 1 production file | `utils/ast_debug.py` (lazy) |

**7 of 14 exports have production callers.**

#### Effective API

The real contract used by production code:

```python
# Base class (subclassed by executor, parser visualization, parser validation)
from psh.visitor import ASTVisitor

# Analysis visitors (used by shell.py --validate/--format/--metrics/--security/--lint)
from psh.visitor import EnhancedValidatorVisitor
from psh.visitor import FormatterVisitor
from psh.visitor import MetricsVisitor
from psh.visitor import SecurityVisitor
from psh.visitor import LinterVisitor

# Debug output (used by utils/ast_debug.py)
from psh.visitor import DebugASTVisitor
```

### Tier 2: Test-only usage

| Export | Test callers | Notes |
|--------|-------------|-------|
| `ValidatorConfig` | 1 (`test_enhanced_validator_comprehensive.py`, via submodule path) | Config for `EnhancedValidatorVisitor` |
| `VariableTracker` | 1 (`test_enhanced_validator_comprehensive.py`, via submodule path) | Tested directly for scope tracking |

**2 of 14 exports have test-only callers.**

Both items are imported by the test file from the submodule path
(`from psh.visitor.enhanced_validator_visitor import ...`), not from the
package path.  The package-level re-export is unused.

### Tier 3: Zero callers outside `psh/visitor/`

| Export | Notes |
|--------|-------|
| `ASTTransformer` | Imported and re-exported but never imported by any file outside the visitor package. No subclasses exist anywhere in the codebase. |
| `ValidatorVisitor` | Exported but only used as a base class by `EnhancedValidatorVisitor` (internal to the package). No external code imports it. |
| `LinterConfig` | Configuration dataclass for `LinterVisitor`. Never constructed or imported outside the package. |
| `LintLevel` | Enum for linter severity levels. Never imported outside the package. |
| `SecurityIssue` | Issue dataclass for `SecurityVisitor`. Never imported outside the package. |

**5 of 14 exports have zero callers.**

## 4. Bypass Imports

Seven production files import `ASTVisitor` from `psh.visitor.base`
instead of from `psh.visitor`:

| File | Import |
|------|--------|
| `psh/executor/core.py` | `from psh.visitor.base import ASTVisitor` |
| `psh/executor/function.py` | `from psh.visitor.base import ASTVisitor` (TYPE_CHECKING) |
| `psh/executor/pipeline.py` | `from psh.visitor.base import ASTVisitor` (TYPE_CHECKING) |
| `psh/executor/control_flow.py` | `from psh.visitor.base import ASTVisitor` (TYPE_CHECKING) |
| `psh/executor/subshell.py` | `from psh.visitor.base import ASTVisitor` (TYPE_CHECKING) |
| `psh/parser/visualization/ast_formatter.py` | `from ...visitor.base import ASTVisitor` |
| `psh/parser/visualization/dot_generator.py` | `from ...visitor.base import ASTVisitor` |

Two files use the package-level import:

| File | Import |
|------|--------|
| `psh/parser/validation/validation_pipeline.py` | `from ...visitor import ASTVisitor` |
| `psh/parser/validation/semantic_analyzer.py` | `from ...visitor import ASTVisitor` |

The dominant pattern (7 of 9 sites) bypasses the package and imports
from the submodule.  This makes `ASTVisitor` the most-imported item in
the package, yet most callers don't go through `__init__.py`.

## 5. Items Not in `__all__` That Have External Callers

### `CompositeVisitor`

Defined in `base.py`, imported in `__init__.py` but **not** included
in `__all__`.  However, `CompositeVisitor` also has **zero callers**
anywhere in the codebase (production or tests).  It appears only in
documentation files and archived design notes.

### `Severity` (from `validator_visitor.py`)

Not in `__all__`.  Has **1 test caller**
(`test_enhanced_validator_comprehensive.py`) that imports it from the
submodule path.  Used internally by `EnhancedValidatorVisitor` through
inheritance from `ValidatorVisitor`.

### `VariableInfo` (from `enhanced_validator_visitor.py`)

Not in `__all__`.  Has **1 test caller**
(`test_enhanced_validator_comprehensive.py`) that imports it from the
submodule path.

### `ValidationIssue` (from `validator_visitor.py`)

Not in `__all__`.  Has **zero external callers**.  Used internally by
`ValidatorVisitor` and `EnhancedValidatorVisitor`.

### `CodeMetrics` (from `metrics_visitor.py`)

Not in `__all__`.  Has **zero external callers**.  Accessed indirectly
via `MetricsVisitor.get_metrics()` and `MetricsVisitor.get_summary()`.

### `LintIssue` (from `linter_visitor.py`)

Not in `__all__`.  Has **zero external callers**.  Accessed indirectly
via `LinterVisitor.get_issues()` and `LinterVisitor.get_summary()`.

## 6. `get_summary()` Method Consistency

All analysis visitors are used through the same pattern in `shell.py`:

```python
visitor = SomeVisitor()
visitor.visit(ast)
print(visitor.get_summary())
```

All five analysis visitors (`EnhancedValidatorVisitor`, `FormatterVisitor`,
`MetricsVisitor`, `SecurityVisitor`, `LinterVisitor`) support this
pattern, but the method names are inconsistent:

| Visitor | Summary method | Result access |
|---------|---------------|---------------|
| `EnhancedValidatorVisitor` | `get_summary()` (inherited) + `get_detailed_summary()` | `.issues` |
| `FormatterVisitor` | `visit()` returns formatted string directly | Return value of `visit()` |
| `MetricsVisitor` | `get_summary()` + `get_report()` + `get_metrics()` | `.metrics` |
| `SecurityVisitor` | `get_summary()` + `get_report()` | `.issues` |
| `LinterVisitor` | `get_summary()` + `get_issues()` | `.issues` |
| `ValidatorVisitor` | `get_summary()` | `.issues` |

`FormatterVisitor` is the outlier -- `shell.py` uses its return value
from `visit()` rather than calling `get_summary()`.  This is correct
since it's a `str`-returning visitor, but it's a different pattern from
the others.

## 7. CLAUDE.md Issues

### Incorrect return types in table

`psh/visitor/CLAUDE.md` contains this table:

```
| DebugASTVisitor | Print AST structure | None |
| ValidatorVisitor | Validate syntax | List[Error] |
| EnhancedValidatorVisitor | Semantic validation | List[Error] |
| MetricsVisitor | Complexity analysis | Metrics |
```

These return types are wrong:
- `DebugASTVisitor` returns `str`, not `None`.
- `ValidatorVisitor` returns `None` (issues accessed via `.issues`), not
  `List[Error]`.
- `EnhancedValidatorVisitor` returns `None`, not `List[Error]`.
- `MetricsVisitor` returns `None` (metrics accessed via `.metrics`), not
  `Metrics`.

### Missing `constants.py` from Key Files table

The `constants.py` file provides `DANGEROUS_COMMANDS`, `SENSITIVE_COMMANDS`,
`SHELL_BUILTINS`, `COMMON_COMMANDS`, and `COMMON_TYPOS`, used by
`enhanced_validator_visitor.py`, `linter_visitor.py`, and
`security_visitor.py`.  It is not listed in the Key Files table.

## 8. Architectural Observations

### 8.1 Clean pattern implementation

The visitor package implements the visitor pattern well.  `ASTVisitor[T]`
with its method cache provides efficient double dispatch.  The generic
type parameter allows visitors to return different types (`int` for
executor, `str` for formatter, `None` for analysis).

### 8.2 `ASTTransformer` is unused

`ASTTransformer` exists as a node-modifying visitor but has **zero
subclasses** anywhere in the codebase.  It was presumably created for
planned AST transformation passes (optimisation, desugaring) that were
never implemented.

### 8.3 `CompositeVisitor` is unused

`CompositeVisitor` exists for running multiple visitors in a single pass
but is **never instantiated** anywhere.  It appears only in documentation.

### 8.4 Duplicate constant sets

`MetricsVisitor` defines its own `BASH_BUILTINS` class variable (~40
items) instead of using `SHELL_BUILTINS` from `constants.py` (~50
items).  The two sets overlap substantially but are not identical.

### 8.5 Dual severity enums

`validator_visitor.py` defines `Severity` (ERROR, WARNING, INFO) and
`linter_visitor.py` defines `LintLevel` (ERROR, WARNING, INFO, STYLE).
These overlap — `LintLevel` is a superset of `Severity` with the
addition of STYLE.  External code (tests) imports `Severity` from the
submodule path.

### 8.6 `ValidatorVisitor` vs `EnhancedValidatorVisitor`

`ValidatorVisitor` is the base; `EnhancedValidatorVisitor` extends it
with semantic checks (undefined variables, command existence, quoting,
security).  No external code uses `ValidatorVisitor` directly — it is
always `EnhancedValidatorVisitor` that is instantiated.  The base class
serves only as an internal abstraction.

### 8.7 `SecurityVisitor` and `EnhancedValidatorVisitor` overlap

Both check for dangerous commands, both reference `DANGEROUS_COMMANDS`
from `constants.py`, and both flag security issues.
`EnhancedValidatorVisitor` has `check_security` in its config that
enables security analysis similar to what `SecurityVisitor` does.  They
are used independently (different `--` flags in `shell.py`), so the
overlap is intentional.

## 9. Recommendations

### R1. Trim `__all__` to items with external callers

Remove Tier 3 items that have zero callers outside the package:

**Remove from `__all__`:**
- `ASTTransformer` — zero subclasses, zero imports outside the package
- `ValidatorVisitor` — only used as internal base class for
  `EnhancedValidatorVisitor`
- `LinterConfig` — zero external constructions
- `LintLevel` — zero external imports
- `SecurityIssue` — zero external imports

**Keep the import statements** in `__init__.py` so any existing code
that happens to use them continues to work.  Only the `__all__`
declaration changes.

**New `__all__`:**

```python
__all__ = [
    # Base class (subclassed by executor, parser visualization/validation)
    'ASTVisitor',
    # Analysis visitors (used by shell.py visitor modes)
    'EnhancedValidatorVisitor',
    'ValidatorConfig',
    'VariableTracker',
    'FormatterVisitor',
    'MetricsVisitor',
    'LinterVisitor',
    'SecurityVisitor',
    # Debug output (used by utils/ast_debug.py)
    'DebugASTVisitor',
]
```

9 items (down from 14).

**Rationale:** Removing items with zero callers from `__all__` reduces
the apparent API surface without breaking any code.  Items remain
importable via their submodule paths.

### R2. Demote Tier 2 exports

`ValidatorConfig` and `VariableTracker` have only test callers, and
those tests import from the submodule path, not the package path.  They
could be removed from `__all__` (but kept importable).

This is a judgement call.  `ValidatorConfig` is a constructor argument
for `EnhancedValidatorVisitor`, so keeping it in `__all__` signals that
it's part of the public interface for configuring the validator.
`VariableTracker` is more of an internal implementation detail.

**If demoting both:**

```python
__all__ = [
    'ASTVisitor',
    'EnhancedValidatorVisitor',
    'FormatterVisitor',
    'MetricsVisitor',
    'LinterVisitor',
    'SecurityVisitor',
    'DebugASTVisitor',
]
```

7 items.

### R3. Fix bypass imports

Seven production files import `ASTVisitor` from `psh.visitor.base`
instead of from `psh.visitor`.  Update them to use the package-level
import:

```python
# Currently (7 files):
from psh.visitor.base import ASTVisitor
from ...visitor.base import ASTVisitor

# Preferred:
from psh.visitor import ASTVisitor
from ...visitor import ASTVisitor
```

This makes the import pattern consistent with the two parser validation
files that already use the package-level import.

### R4. Update CLAUDE.md

Fix the return type table (section 7 above):

| Visitor | Purpose | Return Type |
|---------|---------|-------------|
| `ExecutorVisitor` | Execute AST | `int` (exit code) |
| `DebugASTVisitor` | Format AST structure | `str` |
| `ValidatorVisitor` | Validate AST | `None` (issues in `.issues`) |
| `EnhancedValidatorVisitor` | Semantic validation | `None` (issues in `.issues`) |
| `FormatterVisitor` | Format code | `str` |
| `LinterVisitor` | Style checking | `None` (issues in `.issues`) |
| `MetricsVisitor` | Complexity analysis | `None` (metrics in `.metrics`) |
| `SecurityVisitor` | Security analysis | `None` (issues in `.issues`) |

Add `constants.py` to the Key Files table.

### R5. Deduplicate `BASH_BUILTINS` in `MetricsVisitor`

`MetricsVisitor` defines its own `BASH_BUILTINS` set (~40 items) as a
class variable.  Replace it with `SHELL_BUILTINS` from `constants.py`
(~50 items), which is already used by `EnhancedValidatorVisitor` and
`LinterVisitor`:

```python
# Currently in metrics_visitor.py:
class MetricsVisitor(ASTVisitor[None]):
    BASH_BUILTINS = {'echo', 'cd', 'pwd', ...}  # ~40 items

# Replace with:
from .constants import SHELL_BUILTINS
class MetricsVisitor(ASTVisitor[None]):
    # Use SHELL_BUILTINS from constants.py instead of duplicating
```

This eliminates a second source of truth for the builtins list and
ensures `MetricsVisitor` recognises the same set of builtins as the
other visitors.

### R6. (Optional) Remove unused `ASTTransformer` and `CompositeVisitor`

`ASTTransformer` has zero subclasses and `CompositeVisitor` has zero
call sites in the entire codebase.  Both could be deleted from
`base.py` if there are no plans to use them.

This is a stronger action than R1 (which just removes them from
`__all__`).  The classes are small (~70 lines combined) and educational,
so keeping them is defensible.  But they inflate the base module and may
mislead contributors into thinking they are actively used.

## 10. Priority Order

| Priority | Recommendation | Risk | Impact |
|----------|---------------|------|--------|
| 1 | R1. Trim `__all__` | None | API hygiene — removes 5 items with zero callers |
| 2 | R4. Update CLAUDE.md | None | Documentation accuracy |
| 3 | R5. Deduplicate `BASH_BUILTINS` | Low | Eliminates duplicate constant |
| 4 | R3. Fix bypass imports | None | Import consistency |
| 5 | R2. Demote Tier 2 exports | None | Optional further trimming |
| 6 | R6. Remove unused classes | Low | Optional dead code removal |

R1-R5 are safe, low-risk changes.  R6 is optional and depends on whether
the educational value of `ASTTransformer` and `CompositeVisitor` is
worth keeping.

## 11. Files Modified (if all recommendations implemented)

| File | Changes |
|------|---------|
| `psh/visitor/__init__.py` | Trim `__all__` from 14 to 9 (or 7) items (R1, R2) |
| `psh/visitor/CLAUDE.md` | Fix return type table, add `constants.py` (R4) |
| `psh/visitor/metrics_visitor.py` | Replace `BASH_BUILTINS` with import from `constants.py` (R5) |
| `psh/visitor/base.py` | (Optional) Delete `ASTTransformer`, `CompositeVisitor` (R6) |
| `psh/executor/core.py` | Change `from psh.visitor.base import` to `from psh.visitor import` (R3) |
| `psh/executor/function.py` | Same (R3) |
| `psh/executor/pipeline.py` | Same (R3) |
| `psh/executor/control_flow.py` | Same (R3) |
| `psh/executor/subshell.py` | Same (R3) |
| `psh/parser/visualization/ast_formatter.py` | Same (R3) |
| `psh/parser/visualization/dot_generator.py` | Same (R3) |

## 12. Verification

```bash
# Verify public API imports work
python -c "from psh.visitor import ASTVisitor, EnhancedValidatorVisitor, FormatterVisitor, MetricsVisitor, SecurityVisitor, LinterVisitor, DebugASTVisitor; print('OK')"

# Verify demoted items still importable (if R2 applied)
python -c "from psh.visitor import ValidatorConfig, VariableTracker; print('OK')"

# Verify Tier 3 items importable from submodules
python -c "from psh.visitor.base import ASTTransformer; print('OK')"
python -c "from psh.visitor.validator_visitor import ValidatorVisitor; print('OK')"
python -c "from psh.visitor.linter_visitor import LinterConfig, LintLevel; print('OK')"
python -c "from psh.visitor.security_visitor import SecurityIssue; print('OK')"

# Run visitor-related tests
python -m pytest tests/integration/validation/ -q --tb=short
python -m pytest tests/regression/test_codex_review_findings.py -q --tb=short
python -m pytest tests/regression/test_visitor_executor_review_fixes.py -q --tb=short

# Run full suite
python run_tests.py > tmp/test-results.txt 2>&1; tail -15 tmp/test-results.txt
grep FAILED tmp/test-results.txt

# Lint
ruff check psh/visitor/
```

## Implementation Status

All six recommendations were implemented in v0.181.0:

| Rec | Status | Notes |
|-----|--------|-------|
| R1 | Done | `__all__` trimmed from 14 to 9 items |
| R2 | Kept | `ValidatorConfig` and `VariableTracker` retained in `__all__` |
| R3 | Done | 7 bypass imports fixed |
| R4 | Done | CLAUDE.md return type table corrected, `constants.py` added |
| R5 | Done | `BASH_BUILTINS` replaced with `SHELL_BUILTINS` from `constants.py` |
| R6 | Done | `ASTTransformer` and `CompositeVisitor` deleted from `base.py` |

See `docs/guides/visitor_public_api.md` for the post-cleanup API reference.

## Related Documents

- `docs/guides/visitor_public_api.md` -- Post-cleanup API reference
- `docs/guides/visitor_guide.md` -- Full programmer's guide
- `psh/visitor/CLAUDE.md` -- AI assistant working guide
- `docs/archive/guides/visitor_executor_implementation_review_2026-02-09.md` --
  Detailed implementation review of the visitor/executor subsystem
- `docs/archive/guides/codex_visitor_executor_review.md` -- Codex review of
  visitor executor
- `ARCHITECTURE.md` -- System-wide architecture reference (the former ARCHITECTURE.llm is archived)
