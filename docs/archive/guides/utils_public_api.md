# Utils Public API Reference

**As of v0.184.1**

This document describes the public API of the `psh.utils` package: the
items declared in `__all__`, their signatures, and guidance on internal
imports that are available but not part of the public contract.

## Public API (`__all__`)

The declared public API consists of ten items:

```python
__all__ = [
    'SignalNotifier',
    'get_signal_registry',
    'ShellFormatter',
    'create_parser',
    'contains_heredoc',
    'print_ast_debug',
    'TokenFormatter',
    'file_newer_than',
    'file_older_than',
    'files_same',
]
```

### `SignalNotifier`

```python
from psh.utils import SignalNotifier

notifier = SignalNotifier()
```

Self-pipe pattern for safe signal notification.  Signal handlers write a
byte to an internal pipe; the main loop reads from it.  This moves all
complex work out of signal handler context, ensuring async-signal-safety.

The pipe file descriptors are automatically promoted to high-numbered FDs
(>= 64) to avoid collisions with user-facing redirections like
`exec 3>file`.

| Method | Returns | Description |
|--------|---------|-------------|
| `notify(signal_num)` | `None` | Write signal number to pipe.  Async-signal-safe (only calls `os.write`).  Called from signal handlers. |
| `drain_notifications()` | `List[int]` | Read all pending signal numbers from pipe.  Called from the main loop. |
| `get_fd()` | `int` | Read file descriptor for `select()`/`poll()` integration. |
| `close()` | `None` | Close pipe resources.  Also called automatically by `__del__`. |

Production caller: `psh/interactive/signal_manager.py`.

### `get_signal_registry()`

```python
from psh.utils import get_signal_registry

registry = get_signal_registry(create=True)
```

Get the global `SignalRegistry` singleton instance.

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `create` | `True` | If `True`, create the registry if it doesn't exist yet. |

Returns a `SignalRegistry` instance, or `None` if `create=False` and no
registry has been created.

Production callers: `psh/interactive/signal_manager.py`,
`psh/builtins/debug_control.py`.

### `ShellFormatter`

```python
from psh.utils import ShellFormatter

text = ShellFormatter.format(ast_node, indent_level=0)
body = ShellFormatter.format_function_body(func)
```

Static-method class that reconstructs shell syntax from AST nodes.
Handles all control structures (`if`, `while`, `for`, `case`, `select`,
`until`), pipelines, and-or lists, simple commands, function definitions,
and redirections.

| Method | Returns | Description |
|--------|---------|-------------|
| `format(node, indent_level=0)` | `str` | Format any AST node as shell syntax. |
| `format_function_body(func)` | `str` | Format a function body with `{ ... }` braces for display by `declare -f`. |

Production caller: `psh/builtins/function_support.py`.

### `create_parser()`

```python
from psh.utils import create_parser

parser = create_parser(tokens, shell, source_text=None)
ast = parser.parse()
```

Factory function that creates a configured parser instance, selecting
between the recursive descent parser and the combinator parser based on
`shell._active_parser`.  Applies shell debug options
(`debug-parser`) to the parser configuration.

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `tokens` | -- | List of tokens from `psh.lexer.tokenize()`. |
| `shell` | -- | Shell instance for reading options and active parser selection. |
| `source_text` | `None` | Original source text for error messages. |

Returns a `Parser` instance (recursive descent) or a `ParserWrapper`
(combinator) -- both expose a `.parse()` method.

Production caller: `psh/scripting/source_processor.py`.

### `contains_heredoc()`

```python
from psh.utils import contains_heredoc

if contains_heredoc(command_string):
    # Use heredoc-aware tokenization and parsing
    ...
```

Heuristic that distinguishes heredoc `<<` operators from `<<` bit-shift
operators inside arithmetic expressions.  Scans for `<<` and checks
whether all occurrences fall inside `(( ... ))` boundaries.

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `command_string` | -- | The shell command text to analyse. |

Returns `True` if the command likely contains a heredoc, `False` if all
`<<` occurrences are inside arithmetic expressions.

Production caller: `psh/scripting/source_processor.py`.

### `print_ast_debug()`

```python
from psh.utils import print_ast_debug

print_ast_debug(ast, ast_format, shell)
```

Print AST debug output to stderr in one of several formats.  Reads the
format from `ast_format` (command-line flag), the `PSH_AST_FORMAT` shell
variable, or defaults to `'tree'`.

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `ast` | -- | The AST node to display. |
| `ast_format` | -- | Format string: `'pretty'`, `'tree'`, `'compact'`, `'dot'`, `'sexp'`, or `None` for default. |
| `shell` | -- | Shell instance for reading `PSH_AST_FORMAT` variable and active parser name. |

Supported formats:

| Format | Renderer | Output |
|--------|----------|--------|
| `pretty` | `ASTPrettyPrinter` | Indented human-readable text. |
| `tree` | `AsciiTreeRenderer` | Box-drawing tree for terminals. |
| `compact` | `CompactAsciiTreeRenderer` | Dense box-drawing tree. |
| `dot` | `ASTDotGenerator` | Graphviz DOT format. |
| `sexp` | `SExpressionRenderer` | S-expression (Lisp-style). |

Production caller: `psh/scripting/source_processor.py`.

### `TokenFormatter`

```python
from psh.utils import TokenFormatter

output = TokenFormatter.format(tokens)
```

Static-method class that formats a token list for debug output.  Each
token is rendered as an indexed line with its `TokenType` name and value.

Production caller: `psh/scripting/source_processor.py`.

### `file_newer_than()`

```python
from psh.utils import file_newer_than

result = file_newer_than("/path/to/a", "/path/to/b")
```

Implements the `-nt` test operator.  Returns `True` if `file1` has a
more recent modification time than `file2`.  Returns `False` if either
file does not exist.

Production caller: `psh/executor/test_evaluator.py`.

### `file_older_than()`

```python
from psh.utils import file_older_than

result = file_older_than("/path/to/a", "/path/to/b")
```

Implements the `-ot` test operator.  Returns `True` if `file1` has an
older modification time than `file2`.  Returns `False` if either file
does not exist.

Production caller: `psh/executor/test_evaluator.py`.

### `files_same()`

```python
from psh.utils import files_same

result = files_same("/path/to/a", "/path/to/b")
```

Implements the `-ef` test operator.  Returns `True` if both paths refer
to the same inode on the same device (i.e. hard links or the same file).
Returns `False` if either file does not exist.

Production caller: `psh/executor/test_evaluator.py`.

## Submodule-Only Imports (not in `__all__`)

The following items are importable from their submodules but are **not**
part of the declared public API.  They are internal implementation
details whose signatures may change without notice.

### Signal infrastructure

| Import | Canonical path | Description |
|--------|---------------|-------------|
| `SignalRegistry` | `psh.utils.signal_utils` | Central registry for tracking signal handler changes.  Used by `SignalManager` and the `signals` builtin. |
| `set_signal_registry` | `psh.utils.signal_utils` | Replace the global `SignalRegistry` instance (useful for testing). |
| `SignalHandlerRecord` | `psh.utils.signal_utils` | Dataclass recording a single signal handler registration.  Internal to `SignalRegistry`. |

## Moved in v0.186.0

| Item | Old location | New location | Notes |
|------|-------------|-------------|-------|
| `create_parser` | `psh.utils.parser_factory` | `psh.parser` | Moved to parser package where it belongs.  `parser_factory.py` deleted. |

## Deleted in v0.183.0

The following items were removed entirely (not just demoted).  They had
zero callers in production or test code:

| Item | Was in | Notes |
|------|--------|-------|
| `block_signals(*signals)` | `psh.utils.signal_utils` | Context manager for temporarily blocking signals via `pthread_sigmask`.  Written speculatively; never adopted. |
| `restore_default_signals(*signals)` | `psh.utils.signal_utils` | Context manager for temporarily restoring `SIG_DFL` handlers in child processes.  Superseded by `SignalManager.reset_child_signals()`. |
| `SignalNotifier.has_notifications()` | `psh.utils.signal_utils` | Non-blocking check for pending notifications.  Self-acknowledged hack that consumed pipe data it could not replace.  Use `drain_notifications()` instead. |

## Moved in v0.184.1

| Item | Was in | Moved to | Notes |
|------|--------|----------|-------|
| `to_int(value)` | `psh.utils.file_tests` | `psh.executor.test_evaluator` | Only caller was `test_evaluator.py`, where it was lazily imported 6 times.  Now a module-level function in its sole consumer. |

## API Tiers Summary

| Tier | Scope | How to import | Stability guarantee |
|------|-------|---------------|-------------------|
| **Public** | `SignalNotifier`, `get_signal_registry`, `ShellFormatter`, `create_parser`, `contains_heredoc`, `print_ast_debug`, `TokenFormatter`, `file_newer_than`, `file_older_than`, `files_same` | `from psh.utils import ...` | Stable.  Changes are versioned. |
| **Internal** | `SignalRegistry`, `set_signal_registry`, `SignalHandlerRecord`, `ParserWrapper` | `from psh.utils.<module> import ...` | Internal.  May change without notice. |

## Typical Usage

### Signal notification (self-pipe pattern)

```python
from psh.utils import SignalNotifier

notifier = SignalNotifier()

# In a signal handler (async-signal-safe):
signal.signal(signal.SIGCHLD, lambda s, f: notifier.notify(s))

# In the main loop:
notifications = notifier.drain_notifications()
for sig in notifications:
    handle_child_event(sig)
```

### Create a parser respecting shell options

```python
from psh.lexer import tokenize
from psh.utils import create_parser

tokens = tokenize("for i in 1 2 3; do echo $i; done")
parser = create_parser(tokens, shell, source_text=source)
ast = parser.parse()
```

### Check for heredocs before parsing

```python
from psh.utils import contains_heredoc

if contains_heredoc(command_string):
    tokens, heredoc_map = tokenize_with_heredocs(command_string)
    ast = parse_with_heredocs(tokens, heredoc_map)
else:
    tokens = tokenize(command_string)
    parser = create_parser(tokens, shell)
    ast = parser.parse()
```

### Format a function body for `declare -f` output

```python
from psh.utils import ShellFormatter

func = shell.function_manager.get_function("myfunc")
print(f"myfunc () ", end='')
print(ShellFormatter.format_function_body(func))
```

## Related Documents

- `docs/guides/utils_guide.md` -- Full programmer's guide (architecture,
  file reference, design rationale)
- `docs/guides/utils_public_api_assessment.md` -- Analysis that led to
  this cleanup
- `docs/guides/lexer_public_api.md` -- Companion API reference for the
  lexer package
- `docs/guides/parser_public_api.md` -- Companion API reference for the
  parser package
