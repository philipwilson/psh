# PSH Visitor: Programmer's Guide

This guide covers the visitor package in detail: its external API, internal
architecture, and the responsibilities of every source file.  It is aimed at
developers who need to add new analysis passes, modify existing visitors, or
understand how AST operations are structured.

## 1. What the Visitor Package Does

The visitor package provides a clean separation between AST structure and
operations performed on it.  Each operation (execution, formatting, validation,
metrics collection, security analysis, linting) is implemented as a separate
visitor class that traverses the AST without modifying the node definitions.

The visitor pattern enables:

- **Multiple independent operations** over the same AST without modifying node
  classes.
- **Type-safe return values** via the generic type parameter (`ASTVisitor[int]`
  for execution, `ASTVisitor[str]` for formatting, `ASTVisitor[None]` for
  analysis).
- **Cached dispatch** for performance -- method lookups are cached per node
  class.

The package does **not** parse shell syntax (that is the parser's job), execute
commands (that is the executor's job), or define AST node types (those live in
`psh/ast_nodes.py`).

## 2. External API

The public interface is defined in `psh/visitor/__init__.py`.  The declared
`__all__` contains nine items.  See `docs/guides/visitor_public_api.md` for
full signature documentation and API tiers.

### 2.1 `ASTVisitor[T]`

```python
from psh.visitor import ASTVisitor
```

Abstract generic base class.  All visitors inherit from this.  Provides
`visit(node)` which dispatches to `visit_NodeClassName(node)` via cached
`getattr()` lookup, and `generic_visit(node)` as a fallback for unhandled
node types.

### 2.2 Analysis Visitors

All analysis visitors follow the same usage pattern:

```python
visitor = SomeVisitor()
visitor.visit(ast)
print(visitor.get_summary())
# Access raw results via visitor.issues / visitor.metrics
```

| Visitor | Purpose | Return Type | Result access |
|---------|---------|-------------|---------------|
| `EnhancedValidatorVisitor` | Semantic validation | `None` | `.issues`, `get_summary()`, `get_detailed_summary()` |
| `FormatterVisitor` | Code formatting | `str` | Return value of `visit()` |
| `MetricsVisitor` | Complexity analysis | `None` | `.metrics`, `get_summary()`, `get_report()` |
| `SecurityVisitor` | Security analysis | `None` | `.issues`, `get_summary()`, `get_report()` |
| `LinterVisitor` | Style checking | `None` | `.issues`, `get_summary()`, `get_issues()` |
| `DebugASTVisitor` | Debug AST display | `str` | Return value of `visit()` |

`FormatterVisitor` and `DebugASTVisitor` are the outliers -- they are
`ASTVisitor[str]` and return strings directly from `visit()`.  The other four
are `ASTVisitor[None]` and store results in instance variables.

### 2.3 Configuration

`EnhancedValidatorVisitor` accepts a `ValidatorConfig` and
`LinterVisitor` accepts a `LinterConfig` to control which checks are
enabled.  Both default to all checks enabled.

### 2.4 Convenience imports (not in `__all__`)

The following are importable from `psh.visitor` but are not part of the
declared public API.  New code should prefer the canonical submodule paths:

- `ValidatorVisitor` (from `psh.visitor.validator_visitor`)
- `LinterConfig`, `LintLevel` (from `psh.visitor.linter_visitor`)
- `SecurityIssue` (from `psh.visitor.security_visitor`)


## 3. Architecture

### 3.1 Dispatch mechanism

```
caller
  │
  ▼
ASTVisitor.visit(node)
  │
  ├─ cache lookup: node.__class__ → method
  │                   (cache miss → getattr(self, "visit_NodeClassName", self.generic_visit))
  │
  ▼
visit_SimpleCommand(node)  ← specific handler
  or
generic_visit(node)        ← fallback
```

The method cache (`self._method_cache`) maps each Python class object to the
bound method that handles it.  This avoids repeated `getattr()` calls after
the first encounter of each node type.

### 3.2 Visitor hierarchy

```
ASTVisitor[T]                         # base.py
├── ExecutorVisitor(ASTVisitor[int])   # psh/executor/core.py (returns exit codes)
├── DebugASTVisitor(ASTVisitor[str])   # debug_ast_visitor.py (returns tree string)
├── FormatterVisitor(ASTVisitor[str])  # formatter_visitor.py (returns formatted code)
├── ValidatorVisitor(ASTVisitor[None]) # validator_visitor.py (collects issues)
│   └── EnhancedValidatorVisitor       # enhanced_validator_visitor.py (extends with semantic checks)
├── MetricsVisitor(ASTVisitor[None])   # metrics_visitor.py (collects metrics)
├── LinterVisitor(ASTVisitor[None])    # linter_visitor.py (collects lint issues)
├── SecurityVisitor(ASTVisitor[None])  # security_visitor.py (collects security issues)
├── ASTPrettyPrinter(ASTVisitor[str])  # psh/parser/visualization/ast_formatter.py
└── ASTDotGenerator(ASTVisitor[str])   # psh/parser/visualization/dot_generator.py
```

The `ExecutorVisitor` and parser visualization visitors live outside this
package but inherit from `ASTVisitor`.

### 3.3 Integration with the shell

`shell.py` uses the analysis visitors via lazy imports in
`_apply_visitor_mode()`.  Each `--validate`, `--format`, `--metrics`,
`--security`, and `--lint` flag triggers the corresponding visitor:

```python
# In shell.py
if self.validate_only:
    from .visitor import EnhancedValidatorVisitor
    validator = EnhancedValidatorVisitor()
    validator.visit(ast)
    print(validator.get_summary())
```

The `ExecutorVisitor` (in `psh/executor/core.py`) is the primary consumer of
`ASTVisitor` during normal execution.  It is not part of this package but
inherits from `ASTVisitor[int]`.

### 3.4 Shared constants

`constants.py` provides data sets shared across multiple visitors:

| Constant | Type | Used by |
|----------|------|---------|
| `SHELL_BUILTINS` | `set` | `MetricsVisitor`, `EnhancedValidatorVisitor`, `LinterVisitor` |
| `DANGEROUS_COMMANDS` | `dict` | `EnhancedValidatorVisitor`, `SecurityVisitor` |
| `SENSITIVE_COMMANDS` | `dict` | `SecurityVisitor` |
| `COMMON_COMMANDS` | `set` | `LinterVisitor` |
| `COMMON_TYPOS` | `dict` | `EnhancedValidatorVisitor` |

This eliminates duplicate constant definitions across visitors.

### 3.5 Validator inheritance

`ValidatorVisitor` is the base validation class.  It performs structural
checks (empty bodies, unreachable code, excessive nesting) and collects
`ValidationIssue` objects in `.issues`.

`EnhancedValidatorVisitor` extends it with semantic checks: undefined
variable detection (via `VariableTracker`), command existence validation,
quoting analysis, dangerous command detection, and typo detection.

No external code instantiates `ValidatorVisitor` directly -- it serves
only as an internal base class for `EnhancedValidatorVisitor`.


## 4. Source File Reference

The files below are all under `psh/visitor/`.  Line counts are approximate.

### 4.1 Package entry point

#### `__init__.py` (~28 lines)

Re-exports the public API and declares `__all__` (9 items).  All external
imports should go through this module.

### 4.2 Base class

#### `base.py` (~63 lines)

Defines `ASTVisitor[T]`, the abstract generic base class.  Contains the
dispatch logic (`visit()`) with method caching, and the default
`generic_visit()` that raises `NotImplementedError`.

### 4.3 Shared data

#### `constants.py` (~98 lines)

Data-only module defining five constants: `DANGEROUS_COMMANDS`,
`SENSITIVE_COMMANDS`, `SHELL_BUILTINS`, `COMMON_COMMANDS`, and
`COMMON_TYPOS`.  Imported by `enhanced_validator_visitor.py`,
`linter_visitor.py`, `security_visitor.py`, and `metrics_visitor.py`.

### 4.4 Debug visitor

#### `debug_ast_visitor.py` (~390 lines)

`DebugASTVisitor(ASTVisitor[str])`.  Formats AST nodes as an indented
tree structure for debugging.  Each `visit_*` method returns a string
fragment; the top-level `visit()` returns the complete tree.

Used by `psh/utils/ast_debug.py` for the `--debug-ast` command-line flag.

### 4.5 Validation visitors

#### `validator_visitor.py` (~501 lines)

Defines `Severity` (enum), `ValidationIssue` (dataclass), and
`ValidatorVisitor(ASTVisitor[None])`.  Performs structural validation:

- Empty loop/function bodies
- Unreachable code after `return`/`exit`/`break`/`continue`
- Excessive nesting depth
- Missing case patterns
- Unused functions (basic detection)

Collects issues in `.issues` and provides `get_summary()`.

#### `enhanced_validator_visitor.py` (~668 lines)

Defines `VariableInfo` (dataclass), `VariableTracker` (scope manager),
`ValidatorConfig` (configuration), and
`EnhancedValidatorVisitor(ValidatorVisitor)`.

Adds semantic checks on top of `ValidatorVisitor`:

- **Undefined variables** -- tracks definitions with `VariableTracker`,
  warns about usage of undefined names.
- **Command existence** -- checks commands against `SHELL_BUILTINS` and
  `COMMON_COMMANDS`.
- **Quoting analysis** -- flags unquoted variable expansions in risky
  contexts.
- **Security checks** -- flags `DANGEROUS_COMMANDS` usage.
- **Typo detection** -- checks commands against `COMMON_TYPOS`.

### 4.6 Formatter visitor

#### `formatter_visitor.py` (~494 lines)

`FormatterVisitor(ASTVisitor[str])`.  Pretty-prints AST back into
formatted shell code.  Handles indentation, keyword spacing, and
operator formatting.

Each `visit_*` method returns a string fragment.  The top-level call
returns the complete formatted script.

### 4.7 Linter visitor

#### `linter_visitor.py` (~406 lines)

Defines `LintLevel` (enum: ERROR, WARNING, INFO, STYLE), `LintIssue`
(dataclass), `LinterConfig` (configuration), and
`LinterVisitor(ASTVisitor[None])`.

Performs style and best-practice checks:

- Useless `cat` usage (`cat file | grep`)
- Command existence validation
- Quoting issues
- Pipeline complexity warnings
- Function naming conventions

### 4.8 Metrics visitor

#### `metrics_visitor.py` (~575 lines)

Defines `CodeMetrics` (data container) and
`MetricsVisitor(ASTVisitor[None])`.

Collects quantitative metrics:

- **Counts**: commands, pipelines, functions, loops, conditionals,
  redirections, variables, arrays.
- **Complexity**: cyclomatic complexity, max nesting depth, max pipeline
  length, max function complexity.
- **Frequency**: command usage frequency, builtin vs external
  classification (using `SHELL_BUILTINS` from `constants.py`).
- **Advanced features**: command substitutions, process substitutions,
  arithmetic evaluations, here documents.
- **Per-function metrics**: complexity and command count per function.

### 4.9 Security visitor

#### `security_visitor.py` (~332 lines)

Defines `SecurityIssue` (class) and `SecurityVisitor(ASTVisitor[None])`.

Detects security vulnerabilities:

- **Command injection** -- unquoted variables passed to dangerous
  commands.
- **Unsafe eval** -- `eval` with variable arguments.
- **File permissions** -- world-writable `chmod` patterns.
- **Sensitive operations** -- usage of `rm -rf`, `dd`, `mkfs`, etc.
- **Unquoted expansions** -- variables in dangerous contexts without
  quoting.


## 5. Common Tasks

### 5.1 Creating a new analysis visitor

1. Create a new file in `psh/visitor/` (e.g. `my_visitor.py`):

   ```python
   from ..ast_nodes import ASTNode, SimpleCommand, Pipeline
   from .base import ASTVisitor

   class MyVisitor(ASTVisitor[None]):
       def __init__(self):
           super().__init__()
           self.findings = []

       def generic_visit(self, node: ASTNode) -> None:
           """Default: ignore unhandled nodes."""
           pass

       def visit_SimpleCommand(self, node: SimpleCommand) -> None:
           if node.args and node.args[0] == 'rm':
               self.findings.append("rm command found")

       def visit_Pipeline(self, node: Pipeline) -> None:
           for cmd in node.commands:
               self.visit(cmd)

       def get_summary(self) -> str:
           if not self.findings:
               return "No issues found."
           return "\n".join(self.findings)
   ```

2. Add import and `__all__` entry in `__init__.py` if the visitor
   should be part of the public API.

3. Add tests in `tests/unit/visitor/` or
   `tests/integration/validation/`.

### 5.2 Adding a visit method for a new AST node

When a new AST node type is added to `psh/ast_nodes.py`, each visitor
that should handle it needs a corresponding `visit_NodeClassName` method:

```python
def visit_MyNewNode(self, node: MyNewNode) -> T:
    # Process the node
    # Visit child nodes if needed
    return result
```

The method name must exactly match `visit_` + the class name.  If no
method is defined, `generic_visit()` is called instead.

### 5.3 Handling recursive traversal

Visitors that need to traverse the entire tree must explicitly visit
child nodes.  `ASTVisitor` does **not** automatically traverse
children -- each `visit_*` method is responsible for visiting any child
nodes it cares about:

```python
def visit_IfConditional(self, node: IfConditional) -> None:
    self.visit(node.condition)
    self.visit(node.then_part)
    for cond, then in node.elif_parts:
        self.visit(cond)
        self.visit(then)
    if node.else_part:
        self.visit(node.else_part)
```

### 5.4 Adding shared constants

If multiple visitors need the same data set, add it to `constants.py`
and import it:

```python
# In constants.py
MY_DATA = {'foo', 'bar', 'baz'}

# In my_visitor.py
from .constants import MY_DATA
```

### 5.5 Debugging visitor dispatch

If a visitor method is not being called, check:

1. The method name matches exactly: `visit_` + `node.__class__.__name__`.
2. The visitor's `__init__()` calls `super().__init__()` to initialise
   the method cache.
3. If the visitor was modified after construction, clear
   `self._method_cache` to force re-lookup.


## 6. Design Rationale

### Why the visitor pattern instead of methods on AST nodes?

Adding methods to AST node dataclasses would couple the AST definition to
every operation (execution, formatting, validation, etc.).  The visitor
pattern keeps AST nodes as pure data containers and lets each operation be
defined independently, tested independently, and modified without touching
node definitions.

### Why a method cache?

The `getattr()` lookup for `visit_NodeClassName` is called once per node
type, not once per node.  The cache maps each Python class to its bound
method, avoiding repeated string construction and attribute lookup.  This
matters for large ASTs with thousands of nodes.

### Why `Generic[T]` instead of a fixed return type?

Different visitors need different return types:

- `ExecutorVisitor` returns `int` (exit codes) because the caller needs to
  know success/failure.
- `FormatterVisitor` returns `str` because each subtree formats to a string
  fragment.
- Analysis visitors return `None` because results are stored in instance
  variables, not passed through the call stack.

The generic type parameter lets the type checker verify that all `visit_*`
methods in a visitor return the same type.

### Why is `ValidatorVisitor` separate from `EnhancedValidatorVisitor`?

`ValidatorVisitor` contains structural checks that are fast and don't require
state (empty bodies, unreachable code).  `EnhancedValidatorVisitor` adds
semantic checks that require a `VariableTracker` and configuration.
Separating them keeps the structural checks lightweight and reusable.

### Why do analysis visitors use `generic_visit` returning `None`?

Analysis visitors override `generic_visit()` to either do nothing (`pass`)
or attempt generic child traversal.  This means unhandled node types are
silently skipped rather than raising `NotImplementedError`.  This is
intentional -- analysis visitors should gracefully handle new node types
added in the future without breaking.

### Why is `constants.py` shared across visitors?

Before the shared constants module, each visitor maintained its own set of
shell builtins, dangerous commands, etc.  This led to subtle inconsistencies
(e.g. `MetricsVisitor` had ~40 builtins, `LinterVisitor` had ~50).
Centralising into `constants.py` eliminates the duplication.


## 7. File Dependency Graph

```
__init__.py
├── base.py
│   └── psh/ast_nodes.py
├── constants.py
├── debug_ast_visitor.py
│   ├── base.py
│   └── psh/ast_nodes.py
├── validator_visitor.py
│   ├── base.py
│   └── psh/ast_nodes.py
├── enhanced_validator_visitor.py
│   ├── validator_visitor.py
│   ├── constants.py
│   └── psh/ast_nodes.py
├── formatter_visitor.py
│   ├── base.py
│   └── psh/ast_nodes.py
├── linter_visitor.py
│   ├── base.py
│   ├── constants.py
│   └── psh/ast_nodes.py
├── metrics_visitor.py
│   ├── base.py
│   ├── constants.py
│   └── psh/ast_nodes.py
└── security_visitor.py
    ├── base.py
    ├── constants.py
    └── psh/ast_nodes.py
```

External consumers (outside the visitor package):

- `psh/executor/core.py` -- `ExecutorVisitor(ASTVisitor[int])` for command
  execution.
- `psh/executor/{function,pipeline,control_flow,subshell}.py` --
  `TYPE_CHECKING` imports of `ASTVisitor`.
- `psh/parser/visualization/ast_formatter.py` --
  `ASTPrettyPrinter(ASTVisitor[str])`.
- `psh/parser/visualization/dot_generator.py` --
  `ASTDotGenerator(ASTVisitor[str])`.
- `psh/parser/validation/{validation_pipeline,semantic_analyzer}.py` --
  direct imports of `ASTVisitor`.
- `psh/shell.py` -- lazy imports of `EnhancedValidatorVisitor`,
  `FormatterVisitor`, `MetricsVisitor`, `SecurityVisitor`, `LinterVisitor`.
- `psh/utils/ast_debug.py` -- lazy import of `DebugASTVisitor`.
