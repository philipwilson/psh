# PSH Utils: Programmer's Guide

> **Note (2026-06-11):** This guide describes the tree as of ~v0.27x, before
> the v0.285 module relocation and subsequent cleanups. In particular it
> references `psh/token_types.py`, which has since moved to `psh/lexer/token_types.py`.
> See the subsystem CLAUDE.md files for current structure.

This guide covers the utils package in detail: its external API, internal
architecture, and the responsibilities of every source file.  It is aimed at
developers who need to modify utility functions, add new cross-cutting
infrastructure, or understand how the support modules fit into the shell.

## 1. What the Utils Package Does

The utils package provides cross-cutting utility modules that support shell
infrastructure but do not belong to any single subsystem.  The modules cover
signal handling, AST formatting, parser instantiation, heredoc detection,
file-test operations, and debug output.

The package does **not** participate in the main execution pipeline
(lex-parse-expand-execute).  Its modules are called by components in other
packages that need reusable infrastructure.

## 2. External API

The public interface is defined in `psh/utils/__init__.py`.  The declared
`__all__` contains ten items -- every item with production callers outside
the package.  See `docs/guides/utils_public_api.md` for the full reference
including signatures and API tiers.

### 2.1 Signal infrastructure

```python
from psh.utils import SignalNotifier, get_signal_registry
```

- **`SignalNotifier`** -- self-pipe pattern for safe signal notification.
  Signal handlers call `notify(signal_num)` (async-signal-safe); the main
  loop calls `drain_notifications()` to collect pending signals.  Pipe FDs
  are promoted to high numbers (>= 64) to avoid collisions with user
  redirections.

- **`get_signal_registry(create=True)`** -- returns the global
  `SignalRegistry` singleton.  The registry tracks every
  `signal.signal()` call, recording which component made the change, when,
  and optionally the call stack.

### 2.2 Shell formatting

```python
from psh.utils import ShellFormatter
```

Static-method class that reconstructs shell syntax from AST nodes.
`ShellFormatter.format(node)` handles all node types; `.format_function_body(func)`
formats function bodies for `declare -f` output.

### 2.3 Parser factory

```python
from psh.utils import create_parser
```

Factory function that creates a parser respecting `shell._active_parser`
(recursive descent or combinator) and shell debug options.  Returns an
object with a `.parse()` method.

### 2.4 Heredoc detection

```python
from psh.utils import contains_heredoc
```

Heuristic that distinguishes heredoc `<<` from bit-shift `<<` inside
arithmetic expressions.  Used by `source_processor.py` to decide between
normal and heredoc-aware tokenization paths.

### 2.5 Debug output

```python
from psh.utils import print_ast_debug, TokenFormatter
```

- **`print_ast_debug(ast, format, shell)`** -- renders the AST to stderr in
  one of five formats (pretty, tree, compact, dot, sexp).

- **`TokenFormatter.format(tokens)`** -- renders a token list as indexed
  debug output.

### 2.6 File test helpers

```python
from psh.utils import file_newer_than, file_older_than, files_same
```

Implement the `-nt`, `-ot`, and `-ef` test operators for `[[ ]]` and
`test` expressions.  (The `to_int` function for `-eq`/`-ne`/`-lt`/`-le`/
`-gt`/`-ge` was moved to `psh/executor/test_evaluator.py` in v0.184.1.)

### 2.7 Submodule-only imports

The following are importable from their submodules but are not part of the
declared public API:

| Import | Canonical path | Notes |
|--------|---------------|-------|
| `SignalRegistry` | `psh.utils.signal_utils` | Used by `SignalManager`; test-only external usage. |
| `set_signal_registry` | `psh.utils.signal_utils` | Test helper for replacing the global instance. |
| `SignalHandlerRecord` | `psh.utils.signal_utils` | Dataclass internal to `SignalRegistry`. |
| *(removed)* | *`parser_factory.py` moved to `psh.parser` in v0.186.0* |


## 3. Architecture

### 3.1 Package structure

```
psh/utils/
├── __init__.py           # Public API: __all__ (10 items), re-exports
├── signal_utils.py       # SignalNotifier, SignalRegistry, get/set_signal_registry
├── shell_formatter.py    # ShellFormatter (AST → shell syntax)
├── heredoc_detection.py  # contains_heredoc() heuristic
├── ast_debug.py          # print_ast_debug() (AST visualization dispatch)
├── file_tests.py         # file_newer_than, file_older_than, files_same
└── token_formatter.py    # TokenFormatter (token list → debug text)
```

### 3.2 Caller graph

Each module has a small, well-defined set of callers:

```
signal_utils.py
    └─ interactive/signal_manager.py  (SignalNotifier, get_signal_registry)
    └─ builtins/debug_control.py      (get_signal_registry)

shell_formatter.py
    └─ builtins/function_support.py   (ShellFormatter)

heredoc_detection.py
    └─ scripting/source_processor.py  (contains_heredoc)

ast_debug.py
    └─ scripting/source_processor.py  (print_ast_debug)

token_formatter.py
    └─ scripting/source_processor.py  (TokenFormatter)

file_tests.py
    └─ executor/test_evaluator.py     (file_newer_than,
                                       file_older_than, files_same)
```

### 3.3 Design rationale

The seven modules have no cohesive theme -- they are genuinely cross-cutting
utilities that do not depend on the internal state of their caller packages.
Keeping them in a shared `utils/` directory avoids coupling them to any single
subsystem and follows the common Python convention for miscellaneous
infrastructure.

Each module was extracted from a larger file during the shell.py decomposition
(v0.165.0) or existed as standalone utility code from early development.  They
are intentionally kept small and focused.


## 4. Source File Reference

All paths are relative to `psh/utils/`.  Line counts are approximate (as of
v0.183.0).

### 4.1 Package entry point

#### `__init__.py` (~35 lines)

Docstring listing all submodules, import statements for the 10 public
items, and `__all__` declaration.  This is the only file external code
needs to import from.

### 4.2 Signal infrastructure

#### `signal_utils.py` (~475 lines)

Three components:

1. **`SignalNotifier`** (~125 lines) -- the self-pipe pattern.  Creates a
   pipe on construction, promotes FDs to high numbers via `fcntl.F_DUPFD`,
   and provides `notify()` (async-signal-safe write) and
   `drain_notifications()` (main-loop read).  The write end is set
   non-blocking to prevent signal handler blocking.

2. **`SignalRegistry` + `SignalHandlerRecord`** (~330 lines) -- a debugging
   and introspection tool.  `SignalRegistry.register(sig, handler, component)`
   wraps `signal.signal()` and records a timestamped `SignalHandlerRecord`.
   Provides `get_handler()`, `get_all_handlers()`, `get_history()`,
   `validate()` (detects excessive or rapid handler changes), and
   `report()` (human-readable summary).

3. **Module-level functions** (~20 lines) -- `get_signal_registry(create)`
   and `set_signal_registry(registry)` manage the global singleton.

Key implementation details:

- **FD promotion**: `_promote_internal_fd()` uses `fcntl.F_DUPFD_CLOEXEC`
  (with fallback to `F_DUPFD` + explicit `FD_CLOEXEC`) to relocate pipe
  FDs to >= 64, preventing collision with user scripts that manipulate low
  FDs.
- **Signal names**: `SignalRegistry.SIGNAL_NAMES` maps 9 common signal
  numbers to human-readable names for reports.
- **Stack capture**: optional `capture_stack=True` on `SignalRegistry`
  construction records `traceback.format_stack()` on every registration
  (expensive; off by default).

### 4.3 Shell formatting

#### `shell_formatter.py` (~293 lines)

`ShellFormatter` is a static-method class with a single recursive entry
point, `format(node, indent_level)`, that dispatches on AST node type.
It handles:

- `TopLevel`, `FunctionDef`, `CommandList`, `AndOrList`, `Pipeline`
- `SimpleCommand` -- reconstructs arguments with quote preservation using
  `Word.effective_quote_char`, and appends redirections and `&`.
- `WhileLoop`, `UntilLoop`, `ForLoop`, `CStyleForLoop`
- `IfConditional` (with optional `else` clause)
- `CaseConditional` -- delegates individual case items to
  `_format_case_item()`.
- `SelectLoop`, `ArithmeticEvaluation`, `BreakStatement`,
  `ContinueStatement`
- Fallback for compound commands with a `.body` attribute.

Private helpers:

| Method | Purpose |
|--------|---------|
| `_format_redirect(redirect)` | Format one redirection (FD, operator, target). |
| `_format_case_item(item, indent)` | Format one `case` clause with patterns and terminator. |
| `format_function_body(func)` | Format function body with `{ ... }` braces. |

### 4.4 Heredoc detection

#### `heredoc_detection.py` (~59 lines)

`contains_heredoc(command_string)` performs a lightweight heuristic scan:

1. Quick exit if `<<` is not in the string.
2. If `((` is present, find all `((`/`))` boundaries and all `<<`
   positions.  If every `<<` falls inside an arithmetic boundary, return
   `False`.
3. Otherwise return `True`.

This avoids expensive heredoc tokenization for commands that only use `<<`
as bit-shift inside `(( ... ))`.

### 4.6 AST debug output

#### `ast_debug.py` (~82 lines)

`print_ast_debug(ast, ast_format, shell)` dispatches to one of five
renderers from `psh.parser.visualization`:

| Format | Renderer | Module |
|--------|----------|--------|
| `pretty` | `ASTPrettyPrinter` | `ast_formatter.py` |
| `tree` | `AsciiTreeRenderer` | `ascii_tree.py` |
| `compact` | `CompactAsciiTreeRenderer` | `ascii_tree.py` |
| `dot` | `ASTDotGenerator` | `dot_generator.py` |
| `sexp` | `SExpressionRenderer` | `sexp_renderer.py` |

All imports are lazy (inside the function body) to avoid circular
dependencies and reduce startup cost.  On failure, falls back to
`DebugASTVisitor` from `psh.visitor`.

### 4.7 File test helpers

#### `file_tests.py` (~30 lines)

Three standalone functions implementing shell file-comparison test operators:

| Function | Test operator | Behaviour |
|----------|--------------|-----------|
| `file_newer_than(f1, f2)` | `-nt` | Compare `st_mtime`; `False` if either file missing. |
| `file_older_than(f1, f2)` | `-ot` | Compare `st_mtime`; `False` if either file missing. |
| `files_same(f1, f2)` | `-ef` | Compare `st_dev` and `st_ino`; `False` if either file missing. |

All three are called exclusively from `psh/executor/test_evaluator.py`.
(`to_int` was moved to `test_evaluator.py` in v0.184.1.)

### 4.8 Token debug formatting

#### `token_formatter.py` (~17 lines)

`TokenFormatter.format(tokens)` iterates a token list and returns a
multi-line string with each token's index, type name, and value:

```
  [  0] WORD                 'echo'
  [  1] WORD                 'hello'
  [  2] EOF                  ''
```


## 5. How the Shell Uses Utils

### 5.1 Signal handling flow

```
Shell startup
    │
    ▼
SignalManager.__init__()
    ├─ SignalNotifier()                      ← creates self-pipe
    └─ get_signal_registry(create=True)      ← creates global registry
         │
         ▼
    SignalManager.setup_signal_handlers()
         └─ registry.register(sig, handler, component)
                                             ← tracks every handler change
         │
         ▼
    REPL loop
         └─ signal_manager.process_sigchld_notifications()
              └─ notifier.drain_notifications()
                                             ← reads pending signals
```

### 5.2 Command execution flow (parser factory + heredoc detection)

```
source_processor._execute_buffered_command(command)
    │
    ├─ contains_heredoc(command)?
    │   ├─ Yes → tokenize_with_heredocs() + parse_with_heredocs()
    │   └─ No  → tokenize() + create_parser(tokens, shell).parse()
    │
    ├─ debug_tokens? → TokenFormatter.format(tokens)
    ├─ debug_ast?    → print_ast_debug(ast, format, shell)
    │
    └─ execute AST
```

### 5.3 Function display flow (shell formatter)

```
DeclareBuiltin._print_function_definition(name, func, stdout)
    └─ ShellFormatter.format_function_body(func)
         └─ ShellFormatter.format(stmt, indent_level)
              └─ recursive dispatch on AST node type
```

### 5.4 Test expression evaluation flow (file tests)

```
TestExpressionEvaluator._evaluate_binary()
    ├─ op == '-eq' → to_int(left) == to_int(right)   (to_int is local)
    ├─ op == '-nt' → file_newer_than(left, right)     (from psh.utils)
    ├─ op == '-ot' → file_older_than(left, right)     (from psh.utils)
    └─ op == '-ef' → files_same(left, right)          (from psh.utils)
```


## 6. Common Tasks

### 6.1 Adding a new utility function

1. Choose the appropriate module based on the function's domain, or create
   a new module if it doesn't fit any existing category.
2. Implement the function in the module file.
3. If the function will have production callers outside `psh/utils/`, add
   it to `__init__.py`: import statement and `__all__` entry.
4. Add tests in `tests/unit/utils/`.

### 6.2 Adding a new AST debug format

1. Create a renderer class in `psh/parser/visualization/`.
2. Add a new `elif format_type == 'myformat':` branch in
   `ast_debug.py:print_ast_debug()`.
3. Update the format table in `docs/guides/utils_public_api.md`.
4. Add the format name to the valid list in
   `psh/builtins/debug_control.py:DebugASTBuiltin`.

### 6.3 Adding a new file test operator

1. Add the implementation function to `file_tests.py`.
2. Add the function to `__init__.py` imports and `__all__`.
3. Add a branch in `psh/executor/test_evaluator.py` for the new operator.
4. Add tests.

### 6.4 Debugging signal handling

```bash
# Show signal handler state
python -m psh -c "signals"

# Show full history and stack traces
python -m psh -c "signals -v"
```

Programmatically:

```python
from psh.utils import get_signal_registry

registry = get_signal_registry(create=False)
if registry:
    print(registry.report(verbose=True))
    issues = registry.validate()
    if issues:
        for issue in issues:
            print(f"Warning: {issue}")
```


## 7. Design Rationale

### Why a `utils/` package instead of inlining into callers?

Each module is genuinely utility-grade -- it does not depend on the internal
state of its caller package.  Keeping utilities in a shared location avoids
tight coupling and makes them available if additional callers emerge as the
shell evolves.

### Why not move each module to its sole caller's package?

This was considered and rejected.  Moving seven files would be significant
churn for no functional benefit.  The modules are intentionally stateless
(or use a global singleton) and don't import from their caller packages,
so there is no circular-dependency pressure to relocate them.

### Why is `signal_utils.py` the largest file?

At ~475 lines, `signal_utils.py` contains two distinct components
(`SignalNotifier` and `SignalRegistry`) that share a signal-handling theme.
Splitting into separate files was considered but rejected because the file
is cohesive and the module boundaries within it are clear.

### Why are file test functions separate from `test_evaluator.py`?

The file-comparison functions (`file_newer_than`, `file_older_than`,
`files_same`) are pure utilities (no shell state dependency) and could
potentially be reused by other components.  Keeping them separate follows
the same pattern as the other utils modules.  The `to_int` helper was
moved to `test_evaluator.py` in v0.184.1 because it was the sole caller
and was importing it 6 times via lazy imports.

### Why are most imports in `ast_debug.py` lazy?

The five AST renderers live in `psh.parser.visualization`, which imports
from `psh.visitor`.  Eagerly importing them in `ast_debug.py` would
create import-time circular dependencies and slow startup for commands
that don't use AST debugging.  Lazy imports (inside the function body)
defer the cost to first use.


## 8. File Dependency Graph

```
__init__.py
├── signal_utils.py          (no psh-internal imports)
├── shell_formatter.py
│   └── psh/ast_nodes.py     (AST node types for isinstance dispatch)
├── heredoc_detection.py     (no psh-internal imports)
├── ast_debug.py
│   ├── psh/parser/visualization  (5 renderers, all lazy imports)
│   └── psh/visitor               (DebugASTVisitor, lazy fallback)
├── file_tests.py            (no psh-internal imports; only stdlib os)
└── token_formatter.py
    └── psh/token_types.py   (Token class for isinstance check)

External callers:
├── psh/interactive/signal_manager.py  → SignalNotifier, get_signal_registry
├── psh/builtins/debug_control.py      → get_signal_registry
├── psh/builtins/function_support.py   → ShellFormatter
├── psh/scripting/source_processor.py  → contains_heredoc, create_parser,
│                                        print_ast_debug, TokenFormatter
└── psh/executor/test_evaluator.py     → file_newer_than,
                                         file_older_than, files_same
```
