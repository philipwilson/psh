# Expansion Public API Assessment

> **Note (2026-06-11):** This guide describes the tree as of ~v0.27x, before
> the v0.285 module relocation and subsequent cleanups. In particular it
> references `psh/arithmetic.py`, which has since moved to `psh/expansion/arithmetic.py`.
> See the subsystem CLAUDE.md files for current structure.

**As of v0.179.0**

This document assesses the public API surface of the `psh/expansion/`
package, catalogues every exported symbol, maps the caller graph, and
recommends improvements.  Follows the same methodology as the lexer and
parser API assessments.

## 1. Package Overview

| File | Lines | Classes / Functions |
|------|-------|---------------------|
| `__init__.py` | 0 | Empty -- no `__all__`, no imports |
| `manager.py` | 693 | `ExpansionManager` |
| `variable.py` | 907 | `VariableExpander` |
| `parameter_expansion.py` | 412 | `ParameterExpansion`, `PatternMatcher` |
| `extglob.py` | 260 | 4 public functions + 4 private functions |
| `command_sub.py` | 138 | `CommandSubstitution` |
| `word_splitter.py` | 112 | `WordSplitter` |
| `evaluator.py` | 92 | `ExpansionEvaluator` |
| `glob.py` | 63 | `GlobExpander` |
| `tilde.py` | 54 | `TildeExpander` |
| **Total** | **2,731** | **8 classes + 4 module functions** |

## 2. Current Import Patterns

The `__init__.py` is empty.  All consumers import directly from
submodules:

```python
# Production imports from outside psh/expansion/:
from .expansion.manager import ExpansionManager        # psh/shell.py
from ..expansion.variable import VariableExpander       # psh/builtins/shell_state.py (2x lazy)
from ..expansion.word_splitter import WordSplitter      # psh/executor/control_flow.py
from ..expansion.extglob import contains_extglob, match_extglob  # psh/executor/control_flow.py, test_evaluator.py
from ..expansion.arithmetic import ArithmeticEvaluator  # psh/builtins/function_support.py (BROKEN)
```

**Effective public API**: The single production entry point is
`shell.expansion_manager` (an `ExpansionManager` instance), constructed
in `Shell.__init__()`.  Three modules have direct external callers
beyond this facade: `extglob`, `word_splitter`, and `variable`.

## 3. ExpansionManager Method Caller Map

### Tier 1: Production methods with external callers

| Method | Callers | Files |
|--------|---------|-------|
| `expand_arguments(command)` | 1 call site | `executor/command.py` |
| `expand_string_variables(text)` | 9 call sites | `io_redirect/manager.py`, `io_redirect/file_redirect.py` (via helpers) |
| `expand_variable(var_expr)` | 3 call sites | `executor/command.py`, `executor/control_flow.py`, `builtins/environment.py` |
| `expand_tilde(path)` | 4 call sites | `io_redirect/file_redirect.py`, `builtins/navigation.py`, `executor/command.py` |
| `execute_command_substitution(cmd_sub)` | 1 call site | `executor/command.py` |
| `execute_arithmetic_expansion(expr)` | 2 call sites | `executor/core.py`, `evaluator.py` |

### Tier 2: Internally-used methods (no external callers)

| Method | Role |
|--------|------|
| `_expand_word_ast_arguments(command)` | Main expansion loop, called by `expand_arguments()` |
| `_expand_word(word)` | Per-word expansion with full pipeline |
| `_expand_double_quoted_word(word)` | Double-quoted word expansion |
| `_expand_at_with_affixes(...)` | `"$@"` splitting with prefix/suffix text |
| `_expand_expansion(expansion)` | Delegates to `ExpansionEvaluator` |
| `_split_with_ifs(text, quote_type)` | IFS word splitting wrapper |
| `_glob_words(words)` | Glob expansion wrapper |
| `_word_to_string(word)` | Literal word-to-string (no expansion) |
| `_expansion_to_literal(expansion)` | Expansion back to literal syntax |
| `_process_dquote_escapes(text)` | Static: double-quote escape processing |
| `_process_unquoted_escapes(text)` | Static: unquoted escape processing |
| `_has_process_substitution(command)` | Static: detect `<(cmd)` / `>(cmd)` |
| `_expand_vars_in_arithmetic(expr)` | Pre-expand `$var` for arithmetic |
| `_expand_command_subs_in_arithmetic(expr)` | Pre-expand `$(cmd)` for arithmetic |
| `evaluator` (property) | Lazy-loaded `ExpansionEvaluator` |

## 4. Direct External Callers of Sub-Modules

Three modules have production callers that bypass `ExpansionManager`:

### 4.1 `extglob.py` -- 2 production callers + 1 test caller

| Caller | Functions used |
|--------|---------------|
| `executor/test_evaluator.py` | `contains_extglob`, `match_extglob` |
| `executor/control_flow.py` | `contains_extglob`, `match_extglob` |
| `tests/unit/expansion/test_extglob.py` | `contains_extglob`, `match_extglob`, `expand_extglob`, `extglob_to_regex`, `_find_matching_paren`, `_split_pattern_list` |

The `extglob` module contains stateless utility functions (no shell
reference needed), making direct import appropriate.  However, the test
file imports two private functions (`_find_matching_paren`,
`_split_pattern_list`).

### 4.2 `word_splitter.py` -- 1 production caller + 2 test callers

| Caller | Class used |
|--------|-----------|
| `executor/control_flow.py` | `WordSplitter` (constructs a new instance) |
| `tests/unit/expansion/test_word_splitter.py` | `WordSplitter` |
| `tests/regression/test_bug_fixes_4f4d854.py` | `WordSplitter` |

`control_flow.py` creates its own `WordSplitter()` instance to split
`for` loop variable lists.  This duplicates the instance already on
`ExpansionManager.word_splitter`.  `WordSplitter` has no `shell`
dependency (it's a pure function object), so direct construction is
semantically fine but creates a second instance.

### 4.3 `variable.py` -- 1 production caller

| Caller | Class used |
|--------|-----------|
| `builtins/shell_state.py` | `VariableExpander` (2 lazy imports, constructs new instances) |

`shell_state.py` creates new `VariableExpander(shell)` instances in
two places.  This is wasteful -- `shell.expansion_manager.variable_expander`
already holds one.

## 5. Broken Import

`psh/builtins/function_support.py` line 534:

```python
from ..expansion.arithmetic import ArithmeticEvaluator
```

This imports from `psh.expansion.arithmetic`, which **does not exist**.
The module was never part of the expansion package -- arithmetic
evaluation lives in `psh/arithmetic.py`.  This import is inside a
`try` block for `declare -i` (integer attribute) processing, so when
it fails with `ImportError`, the fallback at line 540 handles it via
simple `int()` conversion.  The dead import creates a silent
behavioural difference: `declare -i x="1+2"` falls back to `int("1+2")`
which raises `ValueError`, so the value becomes `"0"` rather than the
correct `"3"`.

## 6. CLAUDE.md Issues

`psh/expansion/CLAUDE.md` references `base.py` containing
`ExpansionComponent` (an abstract base class).  This file was deleted
in v0.108.0 as unused.  The CLAUDE.md's "Key Files" table and "Common
Tasks" section still reference it:

```
| `base.py` | `ExpansionComponent` - abstract base class for expanders |
```

```python
from .base import ExpansionComponent

class NewExpander(ExpansionComponent):
```

## 7. Code Duplication Analysis

### 7.1 `VariableExpander` instances created redundantly

`shell_state.py` creates `VariableExpander(shell)` twice via lazy
imports instead of using `shell.expansion_manager.variable_expander`.
This wastes a `ParameterExpansion` + `PatternMatcher` allocation per
call.

### 7.2 `WordSplitter` instances created redundantly

`control_flow.py` creates `WordSplitter()` instead of using
`shell.expansion_manager.word_splitter`.

### 7.3 No significant code duplication within the package

The expansion package has clean internal delegation:
- `ExpansionManager` orchestrates.
- `VariableExpander` handles all `$` expansions, delegating operator
  work to `ParameterExpansion`.
- `ExpansionEvaluator` bridges AST nodes to `VariableExpander`.
- Other modules (`tilde.py`, `glob.py`, `command_sub.py`,
  `word_splitter.py`, `extglob.py`) each have a single clear
  responsibility.

## 8. Architectural Observations

### 8.1 Clean facade pattern

`ExpansionManager` is a well-implemented facade.  External code
accesses it through `shell.expansion_manager` and the six Tier 1
methods cover all use cases.  The few bypass imports (`extglob`,
`word_splitter`, `variable`) are pragmatic rather than problematic.

### 8.2 `extglob.py` is correctly a utility module

Its four public functions are stateless (no `shell` dependency), which
makes direct import from executor modules appropriate.  It does not
need to go through `ExpansionManager`.

### 8.3 `PatternMatcher` is a utility, not a shell component

`PatternMatcher` (in `parameter_expansion.py`) converts shell glob
patterns to Python regexes.  It has no state and no `shell` reference.
It could live anywhere but its current location alongside
`ParameterExpansion` is sensible since that's its primary consumer.

### 8.4 `ExpansionEvaluator` bridges AST to string-based API

`ExpansionEvaluator.evaluate()` converts AST expansion nodes back into
string representations (`$name`, `${param op word}`, `$(cmd)`,
`$((expr))`) and delegates to `VariableExpander` /
`ExpansionManager`.  This is a slight inefficiency (serialise to string,
then re-parse) but avoids duplicating expansion logic.  The
`_evaluate_parameter()` method partially addresses this by calling
`expand_parameter_direct()` instead of round-tripping through
`parse_expansion()`.

### 8.5 `variable.py` is the largest module (907 lines)

It handles simple variables, special variables, arrays, array slicing,
parameter expansion operators (via `ParameterExpansion`), and the
`expand_string_variables()` inline-expansion path.  It is cohesive but
large.  A potential future split (e.g. extracting array expansion logic)
would improve navigability, but is not urgent.

## 9. Recommendations

### R1. Populate `__init__.py` with a minimal public API

```python
"""Shell expansion package."""
from .manager import ExpansionManager

__all__ = ['ExpansionManager']
```

`ExpansionManager` is the only class imported by production code via
the package path (from `shell.py`).  This makes the API explicit and
enables `from .expansion import ExpansionManager`.

### R2. Update `shell.py` import

Change:
```python
from .expansion.manager import ExpansionManager
```
to:
```python
from .expansion import ExpansionManager
```

### R3. Fix the broken import in `function_support.py`

Replace:
```python
from ..expansion.arithmetic import ArithmeticEvaluator
evaluator = ArithmeticEvaluator(shell.state)
result = evaluator.evaluate(str_value)
```
with:
```python
from ..arithmetic import evaluate_arithmetic
result = evaluate_arithmetic(str_value, shell)
```

This fixes the `declare -i` behaviour so that `declare -i x="1+2"`
correctly evaluates to `3` instead of falling back to `0`.

### R4. Eliminate redundant `VariableExpander` construction

In `builtins/shell_state.py`, replace:
```python
from ..expansion.variable import VariableExpander
expander = VariableExpander(shell)
```
with:
```python
expander = shell.expansion_manager.variable_expander
```

This avoids constructing a new `VariableExpander` (and its child
`ParameterExpansion` + `PatternMatcher`) on each call.

### R5. Eliminate redundant `WordSplitter` construction

In `executor/control_flow.py`, replace:
```python
from ..expansion.word_splitter import WordSplitter
splitter = WordSplitter()
```
with:
```python
splitter = shell.expansion_manager.word_splitter
```

`WordSplitter` is stateless, so using the existing instance is safe.

### R6. Update `psh/expansion/CLAUDE.md`

Remove the stale `base.py` / `ExpansionComponent` references:

- Delete the `base.py` row from the "Key Files" table.
- Update the "Adding a New Expansion Type" section to show the actual
  pattern (create a class with `__init__(self, shell)` and a domain
  method, no ABC inheritance needed).

### R7. (Optional) Re-export `extglob` utilities from `__init__.py`

The `extglob` module has 2 production callers outside the package that
import `contains_extglob` and `match_extglob` directly.  These could be
added as convenience imports (not in `__all__`) to make the import
pattern consistent:

```python
# In __init__.py (convenience, not in __all__):
from .extglob import contains_extglob, match_extglob
```

This is optional since the direct submodule imports are clean and the
functions are stateless utilities.

## 10. Priority Order

| Priority | Recommendation | Risk | Impact |
|----------|---------------|------|--------|
| 1 | R3. Fix broken `function_support.py` import | Low | Fixes `declare -i` bug |
| 2 | R1. Populate `__init__.py` | None | API hygiene |
| 3 | R2. Update `shell.py` import | None | Consistency |
| 4 | R4. Eliminate redundant `VariableExpander` | None | Removes wasted allocations |
| 5 | R5. Eliminate redundant `WordSplitter` | None | Removes wasted allocation |
| 6 | R6. Update CLAUDE.md | None | Documentation accuracy |
| 7 | R7. Re-export extglob utilities | None | Optional convenience |

R1-R6 are safe, low-risk changes.  R3 is the highest priority as it
fixes actual incorrect behaviour.

## 11. Files Modified (if all recommendations implemented)

| File | Changes |
|------|---------|
| `psh/expansion/__init__.py` | Add `ExpansionManager` import and `__all__` (R1); optionally add extglob convenience imports (R7) |
| `psh/shell.py` | Update import path (R2) |
| `psh/builtins/function_support.py` | Fix arithmetic import (R3) |
| `psh/builtins/shell_state.py` | Use existing `VariableExpander` instance (R4) |
| `psh/executor/control_flow.py` | Use existing `WordSplitter` instance (R5) |
| `psh/expansion/CLAUDE.md` | Remove `base.py` references (R6) |

## 12. Verification

```bash
# Verify public API import works
python -c "from psh.expansion import ExpansionManager; print('OK')"

# Verify declare -i fix
python -m psh -c 'declare -i x="1+2"; echo $x'  # Should print 3

# Run expansion tests
python -m pytest tests/unit/expansion/ -xvs

# Run builtin tests (covers R3, R4)
python -m pytest tests/unit/builtins/ -q --tb=short

# Run full suite
python run_tests.py > tmp/test-results.txt 2>&1; tail -15 tmp/test-results.txt
grep FAILED tmp/test-results.txt

# Lint
ruff check psh/expansion/ psh/builtins/function_support.py psh/builtins/shell_state.py psh/executor/control_flow.py
```

## Related Documents

- `docs/guides/expansion_public_api.md` -- Post-cleanup API reference
  (created in v0.180.0)
- `docs/guides/expansion_guide.md` -- Full programmer's guide
  (created in v0.180.0)
- `docs/archive/guides/expander_implementation_review_2026-02-09.md` -- Detailed
  implementation review of the expansion subsystem
- `docs/archive/guides/expansion_code_quality_review.md` -- Code quality review
- `psh/expansion/CLAUDE.md` -- AI assistant working guide
- `ARCHITECTURE.llm` -- System-wide architecture reference
