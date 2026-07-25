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
| `traversal.py` | `walk_ast_edges()`/`walk_ast()` — the SOLE schema-declared structural enumeration (reads `AstChildSchema`); `TotalTraversalVisitor` — the analysis-visitor base whose framework-owned sweep guarantees every declared child edge is visited; `iter_child_nodes()` is a thin alias, `visit_children()` a callback helper |
| `analysis_helpers.py` | Shared redirect-traversal mixin for analysis visitors |
| `word_analysis.py` | Structured Word-AST inspection (variable references, word classification) used by the validator/linter/security visitors instead of regexing rendered strings |
| `constants.py` | Shared data: `SHELL_BUILTINS`, `DANGEROUS_COMMANDS`, `COMMON_TYPOS`, etc. |
| `debug_ast_visitor.py` | Debug/pretty-print AST structure |
| `validator_visitor.py` | Basic AST validation |
| `enhanced_validator_visitor.py` | Extended validation with semantic checks |
| `formatter_visitor.py` | Format/pretty-print shell code; also `format_function_definition()`, the single chokepoint behind `declare -f` / `type` / `command -V` / `export -f` (output must re-parse to the same program) |
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

For a new ANALYSIS visitor (whole-tree issue/metric collection), subclass
`TotalTraversalVisitor` (`traversal.py#TotalTraversalVisitor`) and add
`visit_X` handlers ONLY where a node needs per-node analysis — descent is the
framework's job, so a handler that just analyzes and returns still gets its
whole subtree traversed. Do not override `visit()` (the battery guard rejects
it), do not add a descending `generic_visit`, and register any deliberate
subtree skip in `PRUNED_EDGES` rather than by leaving an edge undispatched.
`SecurityVisitor` (`security_visitor.py`) is the reference example: pure
analysis handlers, explicit dispatch only where issue ORDER matters, zero
pruned edges. Classify the new visitor in the battery's roster (it fails
loudly until you do). Run it as `visitor.visit(ast)`; collect results from
instance state (`.issues`, `.metrics`, ...).

For a RENDERING/EVALUATION visitor (formatter, executor, debug printers),
subclass plain `ASTVisitor[T]` — traversal is the computation itself there —
and add the explicit per-node methods the coverage matrix requires.

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

4. Declare its child-bearing fields in `AstChildSchema`
   (`traversal.py#AstChildSchema`) — the drift-lock
   (`tests/unit/tooling/test_ast_child_schema_guard.py`) fails until the
   declaration matches the node's annotations, and the analysis visitors
   traverse the new node's children through it automatically.

5. Update tests — `tests/unit/visitor/test_ast_coverage_matrix.py` will
   fail until the new node is supported: it introspects every concrete
   `ASTNode` dataclass and requires the formatter to have an explicit
   `visit_X` for all of them, the executor/validators to cover every
   executable node, and (if the node carries a `redirects` field) a
   source-snippet entry proving the security/formatter/metrics visitors
   handle its redirects. The sentinel battery
   (`tests/unit/visitor/test_traversal_totality_battery.py`) generates
   reach tests for the new node's edges from the schema with no edit.

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

### Recursive Traversal (framework-owned for analysis visitors)

An ANALYSIS visitor (one that walks the whole tree collecting issues/metrics)
subclasses `TotalTraversalVisitor` (`traversal.py#TotalTraversalVisitor`) and
never needs a generic descent of its own: after each node's handler runs, the
framework sweeps every declared child edge the handler did not itself
dispatch. A handler may still dispatch children explicitly to control ORDER
and surrounding context (the validator's context stack, the metrics visitor's
nesting depth, the enhanced validator's scope push/pop) — but omitting an
edge, or returning early, no longer skips a subtree: the sweep visits it.
Whole-program logic that must run exactly once (the linter's end-of-program
checks) is scoped with `TotalTraversalVisitor.at_traversal_root`, since
nested `Program` nodes (substitution bodies) are traversed too.

Invariants (enforced by
`tests/unit/visitor/test_traversal_totality_battery.py`):

1. A production analysis visitor never overrides `visit()` — the totality
   guarantee lives there.
2. Deliberate pruning is DECLARED on the class (`PRUNED_EDGES`), never an
   accidental omission; production analysis visitors declare none.
3. For every concrete node type, every declared child edge, and every
   production analysis visitor, a generated sentinel test proves the child
   in that position is reached.

### Structural enumeration is schema-declared (`walk_ast_edges` / `AstChildSchema`)

`walk_ast_edges(node)` (`traversal.py#walk_ast_edges`; child-only view
`traversal.py#walk_ast`) is the ONE structural enumeration: the framework
sweep, `iter_child_nodes`, and `visit_children` all route through it, so no
visitor hand-rolls a second generic child enumerator. It reads
`AstChildSchema` (`traversal.py#AstChildSchema`), which DECLARES each concrete
node's structural child fields and their container shape (`ChildShape.NODE` /
`NODE_LIST` / `NODE_TUPLE_LIST` / `TEMPLATE_SUBS`). Declaring the shape is
what makes the enumeration total over the tuple-in-list case
(`IfConditional.elif_parts`) that a plain "is-it-an-ASTNode?" reflection walk
silently skipped, and over the S3 syntax templates: a template carrier field
(`ParameterExpansion.word_template`, `ArithmeticExpansion.arith_template`,
the subscript specs, the C-style-for clause templates) is declared
`TEMPLATE_SUBS`, and the walk yields the read-time-parsed substitution nodes
the template holds (`subs[*].expansion`) — the executable `$()` inside
`${x:-...}`, `$((...))`, and `a[...]` regions. (Reappraisal #22 HIGH-2
overturned the earlier never-descend-into-templates exception; the templates
themselves stay non-`ASTNode` value carriers.) The schema is drift-locked
against reflection over the node annotations by
`tests/unit/tooling/test_ast_child_schema_guard.py` (a new or removed
child-bearing field, a new template carrier, or a wrong shape fails there),
and the visualization walker `parser/visualization/node_fields.py` is guarded
to agree with it.

Opaque executable regions that are NOT node edges are flagged, not skipped:
`security_visitor.py#SecurityVisitor.visit_CommandSubstitution` reports an
unparsed backtick body, and
`security_visitor.py#SecurityVisitor.visit_Redirect` reports an unquoted
here-document body embedding a substitution — the security mode never makes a
clean claim over code it could not analyze.

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

Every production visitor is classified by how it achieves totality, and the
classification itself is guarded (an unclassified new `ASTVisitor` subclass
fails `tests/unit/visitor/test_traversal_totality_battery.py`):

| Visitor | Totality mechanism | Enforcement |
|---------|--------------------|-------------|
| `ValidatorVisitor` / `EnhancedValidatorVisitor` / `SecurityVisitor` / `MetricsVisitor` / `LinterVisitor` | `TotalTraversalVisitor` framework sweep — every declared child edge visited regardless of handler behavior | generated sentinel battery (every node type x child edge x visitor) |
| `FormatterVisitor` | traversal IS the rendering; explicit `visit_X` for **every** concrete node class | coverage matrix + reparse round-trips (`test_ast_coverage_matrix.py`) |
| `ExecutorVisitor` | traversal IS evaluation (branch-dependent by semantics — it must NOT visit both if-branches) | explicit `visit_X` for every executable node (matrix); named exemption from the sweep |
| `DebugASTVisitor` | debug rendering; explicit handlers + best-effort field dump | named exemption (not an analysis mode) |
| `ASTPrettyPrinter` / `ASTDotGenerator` (visualization) | `node_fields` walk | `node_fields` drift-locked to agree with the schema |

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
2. **`break`/`continue` have no AST nodes** (since the D2 de-keywording):
   they parse as ordinary `SimpleCommand`s backed by builtins, so their
   redirects attach and apply like any command's (`break >f` — bash). The
   matrix's `REDIRECT_EXEMPT` set is currently empty.

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

1. **Hand-owning descent in an analysis visitor**: subclass
   `TotalTraversalVisitor` and let the sweep own coverage; a hand-rolled
   `generic_visit` descent or a "remember to visit every field" handler is
   the bug class this framework removed.

2. **Forgetting generic_visit in a rendering visitor**: `ASTVisitor`'s
   default raises `NotImplementedError` — define the fallback you want.

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
