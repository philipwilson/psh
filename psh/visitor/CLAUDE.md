# Visitor Subsystem

This document provides guidance for working with the PSH visitor pattern implementation.

## Architecture Overview

The visitor subsystem implements the visitor pattern for AST traversal and transformation. It provides a clean separation between AST structure and operations performed on it.

```
AST → ASTVisitor.visit(node) → visit_NodeType(node) → Result
                ↓
        Double dispatch via
        method name lookup
```

## Key Files

| File | Purpose |
|------|---------|
| `base.py` | `ASTVisitor[T]` base class |
| `traversal.py` | `iter_child_nodes()` / `visit_children()` - shared dataclass-field child walk used by the analysis visitors' `generic_visit` |
| `analysis_helpers.py` | Shared redirect-traversal mixin for analysis visitors |
| `word_analysis.py` | Structured Word-AST inspection (variable references, word classification) used by the validator/linter/security visitors instead of regexing rendered strings |
| `constants.py` | Shared data: `SHELL_BUILTINS`, `DANGEROUS_COMMANDS`, `COMMON_TYPOS`, etc. |
| `debug_ast_visitor.py` | Debug/pretty-print AST structure |
| `validator_visitor.py` | Basic AST validation |
| `enhanced_validator_visitor.py` | Extended validation with semantic checks |
| `formatter_visitor.py` | Format/pretty-print shell code |
| `linter_visitor.py` | Style and best practice checking |
| `metrics_visitor.py` | Code complexity and metrics analysis |
| `security_visitor.py` | Security vulnerability detection |

## Core Patterns

### 1. ASTVisitor Base Class (Generic)

```python
class ASTVisitor(ABC, Generic[T]):
    """Read-only visitor with double dispatch."""

    def __init__(self):
        # Cache for method lookups
        self._method_cache = {}

    def visit(self, node: ASTNode) -> T:
        """Dispatch to visit_NodeType method."""
        node_class = node.__class__
        if node_class not in self._method_cache:
            method_name = f'visit_{node_class.__name__}'
            self._method_cache[node_class] = getattr(
                self, method_name, self.generic_visit
            )
        return self._method_cache[node_class](node)

    def generic_visit(self, node: ASTNode) -> T:
        """Called for unhandled node types."""
        raise NotImplementedError(
            f"No visit_{node.__class__.__name__} method"
        )
```

## The ExecutorVisitor

The main executor in `psh/executor/core.py` is an `ASTVisitor[int]` that returns exit codes:

```python
class ExecutorVisitor(ASTVisitor[int]):
    """Executes AST nodes and returns exit codes."""

    def visit_SimpleCommand(self, node: SimpleCommand) -> int:
        # Execute command
        return exit_code

    def visit_Pipeline(self, node: Pipeline) -> int:
        # Execute pipeline
        return exit_code

    def visit_IfConditional(self, node: IfConditional) -> int:
        # Execute if statement
        return exit_code
```

## Creating a New Visitor

### Step 1: Define Your Visitor Class

```python
# psh/visitor/my_visitor.py
from typing import List
from .base import ASTVisitor
from ..ast_nodes import SimpleCommand, Pipeline, IfConditional

class MyAnalysisVisitor(ASTVisitor[None]):
    """Analyze shell AST for specific patterns."""

    def __init__(self):
        super().__init__()
        self.findings = []

    def generic_visit(self, node) -> None:
        """Default: do nothing for unhandled nodes."""
        pass

    def visit_SimpleCommand(self, node: SimpleCommand) -> None:
        # Analyze command
        if node.args and node.args[0] == 'rm':
            self.findings.append("rm command found")

    def visit_Pipeline(self, node: Pipeline) -> None:
        # Recursively visit pipeline components
        for cmd in node.commands:
            self.visit(cmd)

    def visit_IfConditional(self, node: IfConditional) -> None:
        # Visit condition and branches (each is a StatementList)
        self.visit(node.condition)
        self.visit(node.then_part)
        for elif_cond, elif_body in node.elif_parts:
            self.visit(elif_cond)
            self.visit(elif_body)
        if node.else_part:
            self.visit(node.else_part)
```

### Step 2: Add Visitor Methods for Each Node Type

Common AST node types to handle:

```python
# Control structures
def visit_IfConditional(self, node) -> T: ...
def visit_WhileLoop(self, node) -> T: ...
def visit_ForLoop(self, node) -> T: ...
def visit_CaseConditional(self, node) -> T: ...

# Commands
def visit_SimpleCommand(self, node) -> T: ...
def visit_Pipeline(self, node) -> T: ...
def visit_StatementList(self, node) -> T: ...  # NB: `CommandList` is an
                                               # alias for StatementList in
                                               # psh/ast_nodes/commands.py; dispatch uses
                                               # the real class name
def visit_AndOrList(self, node) -> T: ...

# Functions
def visit_FunctionDef(self, node) -> T: ...

# Groups
def visit_SubshellGroup(self, node) -> T: ...
def visit_BraceGroup(self, node) -> T: ...
```

### Step 3: Use Your Visitor

```python
from psh.visitor.my_visitor import MyAnalysisVisitor

# Parse code
ast = parser.parse()

# Run analysis
visitor = MyAnalysisVisitor()
visitor.visit(ast)

# Get results
print(visitor.findings)
```

## Adding Support for a New AST Node

When adding a new AST node type:

1. Define the node in the `psh/ast_nodes/` package

2. Add visit method to `ExecutorVisitor`:
```python
def visit_MyNewNode(self, node: MyNewNode) -> int:
    # Execute the new node type
    return exit_code
```

3. Add to other relevant visitors (validator, formatter, etc.)

4. Update tests — `tests/unit/visitor/test_ast_coverage_matrix.py` will
   fail until the new node is supported: it introspects every concrete
   `ASTNode` dataclass and requires the formatter to have an explicit
   `visit_X` for all of them, the executor/validators to cover every
   executable node, and (if the node carries a `redirects` field) a
   source-snippet entry proving the security/formatter/metrics visitors
   handle its redirects.

## Key Implementation Details

### Method Caching

Visitor uses a cache for method lookups to improve performance:

```python
def visit(self, node):
    node_class = node.__class__
    if node_class not in self._method_cache:
        method_name = f'visit_{node_class.__name__}'
        self._method_cache[node_class] = getattr(
            self, method_name, self.generic_visit
        )
    return self._method_cache[node_class](node)
```

### Recursive Traversal

For visitors that need to traverse the entire tree, implement recursive visiting:

```python
def visit_StatementList(self, node) -> None:
    for stmt in node.statements:
        self.visit(stmt)

def visit_Pipeline(self, node) -> None:
    for cmd in node.commands:
        self.visit(cmd)
```

For a generic descend-into-children default, reuse the shared walk in
`traversal.py` instead of hand-rolling one:

```python
from .traversal import visit_children

def generic_visit(self, node) -> None:
    visit_children(self, node)   # visits every ASTNode child field
```

### Collecting Results

For analysis visitors, store results in instance variables:

```python
class CountingVisitor(ASTVisitor[None]):
    def __init__(self):
        super().__init__()
        self.command_count = 0
        self.pipeline_count = 0

    def visit_SimpleCommand(self, node) -> None:
        self.command_count += 1

    def visit_Pipeline(self, node) -> None:
        self.pipeline_count += 1
        for cmd in node.commands:
            self.visit(cmd)
```

## Totality Over the AST (enforced)

Every visitor must handle every real AST node, but each uses a different
mechanism for unhandled types — the coverage matrix test
(`tests/unit/visitor/test_ast_coverage_matrix.py`) enforces the mechanism
each visitor actually relies on:

| Visitor | `generic_visit` behavior | Requirement |
|---------|--------------------------|-------------|
| `FormatterVisitor` | emits `# Unknown node: X` (defensive fallback only) | explicit `visit_X` for **every** concrete node class |
| `ExecutorVisitor` | raises `NotImplementedError` | explicit `visit_X` for every executable node |
| `ValidatorVisitor` / `EnhancedValidatorVisitor` | non-traversing `pass` | explicit `visit_X` for every executable node (else its subtree is silently skipped) |
| `SecurityVisitor` / `MetricsVisitor` / `LinterVisitor` | `visit_children` (shared traversal) | unhandled nodes are still fully traversed |
| `DebugASTVisitor` | best-effort field dump | fallback acceptable; major nodes have explicit methods |

Two rules that came out of the 2026-06 coverage audit (fixed in the same
change that added the matrix test):

1. **Explicit handlers must not lose `redirects`.** Compound commands
   (loops, conditionals, groups, function defs, `[[ ]]`, `(( ))`) carry a
   `redirects` list just like `SimpleCommand`. A visitor with an explicit
   `visit_WhileLoop` that only visits condition/body silently skips
   `while ...; done >/etc/passwd`. The security, validator, and metrics
   visitors share one `_visit_redirects(node)` helper —
   `RedirectTraversalMixin` in `analysis_helpers.py` (each visitor mixes it
   in; `EnhancedValidatorVisitor` inherits it via `ValidatorVisitor`) — that
   every such handler calls; the matrix test verifies all redirect carriers
   behaviorally (parse real source, assert the issue/output/count).
2. **`BreakStatement`/`ContinueStatement` redirects are unreachable from
   source** (`break >f` parses as two statements); their `redirects`
   fields exist only to satisfy the `Command` interface and are exempt in
   the matrix, with a pinning test.

## Available Visitors

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

## Testing

```bash
# Run visitor tests
python -m pytest tests/unit/visitor/ -v

# Test specific visitor files
python -m pytest tests/unit/visitor/test_analysis_visitors.py -v
python -m pytest tests/unit/visitor/test_formatter_visitor.py -v
python -m pytest tests/unit/visitor/test_ast_coverage_matrix.py -v  # totality matrix

# Debug AST output
python -m psh --debug-ast -c "if true; then echo yes; fi"
```

## Common Pitfalls

1. **Forgetting generic_visit**: Define how to handle unmatched nodes.

2. **Not Visiting Children**: For tree traversal, explicitly visit child nodes.

3. **Method Name Typos**: Visitor method must be exactly `visit_NodeClassName`.

4. **Generic Type**: Use appropriate return type (`ASTVisitor[int]` for executors).

5. **Cache Invalidation**: If you modify the visitor dynamically, clear `_method_cache`.

## Integration Points

### With Parser (`psh/parser/`)

- Parser produces AST nodes
- Visitor traverses the resulting tree

### With Executor (`psh/executor/`)

- `ExecutorVisitor` is the main execution engine
- Delegates to specialized executors for different node types

### With AST Nodes (`psh/ast_nodes/`)

- All AST node classes defined there
- Visitor methods named after node class names
