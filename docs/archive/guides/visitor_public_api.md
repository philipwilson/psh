# Visitor Public API Reference

**As of v0.181.0** (post-cleanup)

This document describes the public API of the `psh.visitor` package: the
items declared in `__all__`, their signatures, and guidance on internal
imports that are available but not part of the public contract.

## Public API (`__all__`)

The declared public API consists of nine items:

```python
__all__ = [
    'ASTVisitor',
    'FormatterVisitor',
    'DebugASTVisitor',
    'EnhancedValidatorVisitor',
    'ValidatorConfig',
    'VariableTracker',
    'MetricsVisitor',
    'LinterVisitor',
    'SecurityVisitor',
]
```

### `ASTVisitor`

```python
from psh.visitor import ASTVisitor
```

Abstract generic base class for all AST visitors.  Provides double
dispatch via method name lookup with result caching.

```python
class ASTVisitor(ABC, Generic[T]):
    def visit(self, node: ASTNode) -> T: ...
    def generic_visit(self, node: ASTNode) -> T: ...
```

| Method | Description |
|--------|-------------|
| `visit(node)` | Dispatch to `visit_NodeClassName(node)`.  If no matching method exists, falls back to `generic_visit()`.  Results are cached by node class for performance. |
| `generic_visit(node)` | Called for unhandled node types.  Default implementation raises `NotImplementedError`.  Subclasses typically override this to no-op (`pass`) or to traverse children. |

The type parameter `T` determines the return type of visitor methods:

| Use case | Type | Example |
|----------|------|---------|
| Execution | `int` | `ExecutorVisitor(ASTVisitor[int])` returns exit codes |
| Formatting | `str` | `FormatterVisitor(ASTVisitor[str])` returns formatted code |
| Analysis | `None` | `MetricsVisitor(ASTVisitor[None])` stores results in instance variables |

Subclassed by `ExecutorVisitor` (in `psh/executor/core.py`), the parser
visualization visitors (in `psh/parser/visualization/`), and all
analysis visitors in this package.

### `FormatterVisitor`

```python
from psh.visitor import FormatterVisitor

formatter = FormatterVisitor()
formatted_code = formatter.visit(ast)  # returns str
```

Pretty-prints shell AST back into formatted shell code.  An
`ASTVisitor[str]` -- `visit()` returns the formatted string directly.

### `DebugASTVisitor`

```python
from psh.visitor import DebugASTVisitor

debug = DebugASTVisitor()
tree_str = debug.visit(ast)  # returns str
print(tree_str)
```

Formats AST structure as an indented tree for debugging.  An
`ASTVisitor[str]`.  Used by `psh/utils/ast_debug.py` for the
`--debug-ast` flag.

### `EnhancedValidatorVisitor`

```python
from psh.visitor import EnhancedValidatorVisitor

validator = EnhancedValidatorVisitor()
validator.visit(ast)
print(validator.get_summary())
error_count = sum(1 for i in validator.issues if i.severity.value == 'error')
```

Comprehensive AST validation with semantic checks.  An
`ASTVisitor[None]` that extends `ValidatorVisitor` with:

- Undefined variable detection (with scope tracking via `VariableTracker`)
- Command existence validation
- Quoting analysis
- Dangerous command warnings
- Command typo detection (using `COMMON_TYPOS` from `constants.py`)

| Attribute / Method | Type | Description |
|--------------------|------|-------------|
| `.issues` | `List[ValidationIssue]` | All validation issues found. |
| `get_summary()` | `str` | Formatted summary of all issues (inherited from `ValidatorVisitor`). |
| `get_detailed_summary()` | `str` | Extended summary with additional context. |

Constructor accepts an optional `ValidatorConfig` to control which
checks are enabled:

```python
from psh.visitor import EnhancedValidatorVisitor, ValidatorConfig

config = ValidatorConfig(
    check_undefined_vars=True,
    check_command_existence=True,
    check_quoting=True,
    check_security=True,
)
validator = EnhancedValidatorVisitor(config=config)
```

### `ValidatorConfig`

```python
from psh.visitor import ValidatorConfig
```

Configuration dataclass for `EnhancedValidatorVisitor`.  Controls which
validation checks are enabled.

| Field | Default | Description |
|-------|---------|-------------|
| `check_undefined_vars` | `True` | Warn about undefined variables. |
| `check_command_existence` | `True` | Warn about unknown commands. |
| `check_quoting` | `True` | Warn about unquoted variable expansions. |
| `check_security` | `True` | Warn about dangerous commands. |

### `VariableTracker`

```python
from psh.visitor import VariableTracker
```

Tracks variable definitions and usage across scopes.  Maintains a stack
of scope dictionaries.  Used internally by `EnhancedValidatorVisitor`
but exported for tests that need to verify scope tracking directly.

| Method | Description |
|--------|-------------|
| `define_variable(name, info)` | Register a variable in the current scope. |
| `is_defined(name)` | Check if a variable is defined in any scope. |
| `push_scope()` | Enter a new scope (function body). |
| `pop_scope()` | Leave the current scope. |

### `MetricsVisitor`

```python
from psh.visitor import MetricsVisitor

metrics = MetricsVisitor()
metrics.visit(ast)
print(metrics.get_summary())
report = metrics.get_report()  # dict
```

Collects code metrics and complexity statistics from the AST.  An
`ASTVisitor[None]`.

| Attribute / Method | Type | Description |
|--------------------|------|-------------|
| `.metrics` | `CodeMetrics` | Raw metrics container. |
| `get_summary()` | `str` | Human-readable metrics summary. |
| `get_report()` | `dict` | Machine-readable metrics dict. |
| `get_metrics()` | `CodeMetrics` | The `CodeMetrics` instance. |

Metrics collected include: command counts and frequency, control
structure usage, cyclomatic complexity, nesting depth, pipeline length,
variable and function names, and advanced feature usage (command
substitutions, process substitutions, here documents, arithmetic
evaluations).

### `LinterVisitor`

```python
from psh.visitor import LinterVisitor

linter = LinterVisitor()
linter.visit(ast)
print(linter.get_summary())
issues = linter.issues
```

Style and best-practice checking.  An `ASTVisitor[None]`.

| Attribute / Method | Type | Description |
|--------------------|------|-------------|
| `.issues` | `List[LintIssue]` | All lint issues found. |
| `get_summary()` | `str` | Formatted issue summary. |
| `get_issues()` | `List[LintIssue]` | Same as `.issues`. |

Constructor accepts an optional `LinterConfig` (importable from
`psh.visitor.linter_visitor`).

### `SecurityVisitor`

```python
from psh.visitor import SecurityVisitor

security = SecurityVisitor()
security.visit(ast)
print(security.get_summary())
issues = security.issues
```

Security vulnerability detection.  An `ASTVisitor[None]`.

| Attribute / Method | Type | Description |
|--------------------|------|-------------|
| `.issues` | `List[SecurityIssue]` | All security issues found. |
| `get_summary()` | `str` | Formatted security report. |
| `get_report()` | `dict` | Machine-readable report dict. |

Detects: command injection risks, unsafe `eval` usage,
world-writable file permissions, unquoted variables in dangerous
contexts, and sensitive command usage.

## Convenience Imports (not in `__all__`)

The following items are importable from `psh.visitor` for convenience but
are **not** part of the declared public contract.  They are internal
implementation details whose signatures may change without notice.

Existing code that imports these will continue to work; the imports are
kept specifically to avoid churn.  New code should prefer the submodule
import paths listed below.

### Visitor Classes

| Import | Canonical path | Description |
|--------|---------------|-------------|
| `ValidatorVisitor` | `psh.visitor.validator_visitor` | Base validation visitor.  Only used as the parent class of `EnhancedValidatorVisitor`.  No external code instantiates it directly. |

### Configuration and Data Types

| Import | Canonical path | Description |
|--------|---------------|-------------|
| `LinterConfig` | `psh.visitor.linter_visitor` | Configuration dataclass for `LinterVisitor`.  Controls check enablement. |
| `LintLevel` | `psh.visitor.linter_visitor` | Enum: `ERROR`, `WARNING`, `INFO`, `STYLE`. |
| `SecurityIssue` | `psh.visitor.security_visitor` | Issue dataclass for `SecurityVisitor`.  Fields: `severity`, `issue_type`, `message`, `node`. |

## Submodule-Only Imports

These classes are not importable from `psh.visitor` -- import them from
their defining modules:

```python
from psh.visitor.validator_visitor import Severity, ValidationIssue
from psh.visitor.linter_visitor import LintIssue
from psh.visitor.metrics_visitor import CodeMetrics
from psh.visitor.constants import SHELL_BUILTINS, DANGEROUS_COMMANDS, SENSITIVE_COMMANDS, COMMON_COMMANDS, COMMON_TYPOS
```

| Class / Constant | Module | Description |
|------------------|--------|-------------|
| `Severity` | `validator_visitor` | Enum: `ERROR`, `WARNING`, `INFO`.  Used by `ValidationIssue`. |
| `ValidationIssue` | `validator_visitor` | Dataclass: `severity`, `message`, `node_type`, `location`. |
| `LintIssue` | `linter_visitor` | Dataclass: `level`, `message`, `line`, `column`, `suggestion`. |
| `CodeMetrics` | `metrics_visitor` | Container for all metrics data.  Accessed via `MetricsVisitor.get_metrics()`. |
| `VariableInfo` | `enhanced_validator_visitor` | Dataclass for variable metadata in `VariableTracker`. |
| `SHELL_BUILTINS` | `constants` | Set of shell builtin command names.  Used by `MetricsVisitor`, `EnhancedValidatorVisitor`, and `LinterVisitor`. |
| `DANGEROUS_COMMANDS` | `constants` | Dict mapping dangerous commands to risk descriptions. |
| `SENSITIVE_COMMANDS` | `constants` | Dict mapping sensitive commands to descriptions. |
| `COMMON_COMMANDS` | `constants` | Set of common external command names. |
| `COMMON_TYPOS` | `constants` | Dict mapping common command typos to corrections. |

## Deleted in v0.181.0

The following classes were removed from `base.py` (not just demoted).
They had zero subclasses and zero call sites in the entire codebase:

| Item | Was in | Notes |
|------|--------|-------|
| `ASTTransformer` | `psh.visitor.base` | Modifying visitor that returns transformed nodes.  Zero subclasses anywhere.  ~69 lines. |
| `CompositeVisitor` | `psh.visitor.base` | Runs multiple visitors in sequence.  Zero instantiations anywhere.  ~34 lines. |

## API Tiers Summary

| Tier | Scope | How to import | Stability guarantee |
|------|-------|---------------|-------------------|
| **Public** | `ASTVisitor`, `FormatterVisitor`, `DebugASTVisitor`, `EnhancedValidatorVisitor`, `ValidatorConfig`, `VariableTracker`, `MetricsVisitor`, `LinterVisitor`, `SecurityVisitor` | `from psh.visitor import ...` | Stable.  Changes are versioned. |
| **Convenience** | `ValidatorVisitor`, `LinterConfig`, `LintLevel`, `SecurityIssue` | `from psh.visitor import ...` (works) or `from psh.visitor.<module> import ...` (preferred) | Available but not guaranteed.  Prefer submodule paths. |
| **Internal** | `Severity`, `ValidationIssue`, `LintIssue`, `CodeMetrics`, `VariableInfo`, constants | `from psh.visitor.<module> import ...` | Internal.  May change without notice. |

## Typical Usage

### Validate a script

```python
from psh.lexer import tokenize
from psh.parser import parse
from psh.visitor import EnhancedValidatorVisitor

tokens = tokenize("echo $undefined_var")
ast = parse(tokens)

validator = EnhancedValidatorVisitor()
validator.visit(ast)
print(validator.get_summary())
```

### Format a script

```python
from psh.lexer import tokenize
from psh.parser import parse
from psh.visitor import FormatterVisitor

tokens = tokenize("if true;then echo yes;fi")
ast = parse(tokens)

formatter = FormatterVisitor()
formatted = formatter.visit(ast)
print(formatted)
```

### Collect metrics

```python
from psh.lexer import tokenize
from psh.parser import parse
from psh.visitor import MetricsVisitor

tokens = tokenize("for i in 1 2 3; do echo $i; done")
ast = parse(tokens)

metrics = MetricsVisitor()
metrics.visit(ast)
print(metrics.get_summary())
report = metrics.get_report()  # dict for programmatic use
```

### Security analysis

```python
from psh.lexer import tokenize
from psh.parser import parse
from psh.visitor import SecurityVisitor

tokens = tokenize("eval $user_input")
ast = parse(tokens)

security = SecurityVisitor()
security.visit(ast)
for issue in security.issues:
    print(issue)
```

### Write a custom visitor

```python
from psh.visitor import ASTVisitor
from psh.ast_nodes import SimpleCommand, Pipeline

class CommandCounter(ASTVisitor[None]):
    def __init__(self):
        super().__init__()
        self.count = 0

    def generic_visit(self, node) -> None:
        pass  # ignore unhandled nodes

    def visit_SimpleCommand(self, node: SimpleCommand) -> None:
        self.count += 1

    def visit_Pipeline(self, node: Pipeline) -> None:
        for cmd in node.commands:
            self.visit(cmd)
```

## Related Documents

- `docs/guides/visitor_guide.md` -- Full programmer's guide (architecture,
  file reference, design rationale)
- `docs/guides/visitor_public_api_assessment.md` -- Analysis that led to
  this cleanup
- `psh/visitor/CLAUDE.md` -- AI assistant working guide for the visitor
  subsystem
