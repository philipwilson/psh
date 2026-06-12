# Builtins Public API Reference

**As of v0.184.0** (post-cleanup)

This document describes the public API of the `psh.builtins` package: the
items declared in `__all__`, their signatures, and guidance on internal
imports that are available but not part of the public contract.

## Public API (`__all__`)

The declared public API consists of five items:

```python
__all__ = ['registry', 'builtin', 'Builtin', 'FunctionReturn', 'PARSERS']
```

### `registry`

```python
from psh.builtins import registry
```

The global `BuiltinRegistry` instance. All builtins register themselves
here at import time via the `@builtin` decorator. The executor uses this
registry to look up commands during execution.

| Method | Returns | Description |
|--------|---------|-------------|
| `registry.get(name)` | `Optional[Builtin]` | Get a builtin by name or alias. Returns `None` if not found. |
| `registry.has(name)` | `bool` | Check if a builtin exists. |
| `registry.all()` | `Dict[str, Builtin]` | Get all registered builtins (including aliases). Returns a copy. |
| `registry.names()` | `List[str]` | Get sorted list of primary builtin names (excluding aliases). |
| `registry.instances()` | `List[Builtin]` | Get all unique builtin instances. |

The registry also supports `in` (`'echo' in registry`) and dict-style
access (`registry['echo']`).

### `builtin`

```python
from psh.builtins import builtin

@builtin
class MyBuiltin(Builtin):
    name = "mycommand"
    def execute(self, args, shell):
        return 0
```

Decorator function that auto-registers a `Builtin` subclass with the
global `registry`. Apply it to any class that inherits from `Builtin` to
make the command available to the shell.

### `Builtin`

```python
from psh.builtins import Builtin
```

Abstract base class for all shell builtins. Subclasses must implement
`name` (property) and `execute()`.

| Member | Type | Description |
|--------|------|-------------|
| `name` | `str` (abstract property) | Primary command name. |
| `aliases` | `List[str]` (property) | Optional command aliases. Default: `[]`. |
| `execute(args, shell)` | `int` (abstract method) | Execute the builtin. `args[0]` is the command name. Returns exit code. |
| `synopsis` | `str` (property) | Brief command syntax. Default: the command name. |
| `description` | `str` (property) | One-line description. Default: class docstring. |
| `help` | `str` (property) | Detailed help text. Default: synopsis + description. |
| `error(message, shell)` | `None` | Print `"{name}: {message}"` to `shell.stderr` and flush. |

### `FunctionReturn`

```python
from psh.builtins import FunctionReturn
```

Exception class used by the `return` builtin to implement function
returns. Caught by the executor's function-call handler to unwind the
call stack.

| Attribute | Type | Description |
|-----------|------|-------------|
| `.exit_code` | `int` | The return value passed to `return N`. |

Typical usage in executor code:

```python
try:
    exit_code = self._execute_function_body(body, shell)
except FunctionReturn as e:
    exit_code = e.exit_code
```

### `PARSERS`

```python
from psh.builtins import PARSERS
```

Dictionary mapping parser implementation names to their aliases. Used by
the `parser-select` builtin and `--parser` CLI argument to select the
active parser at runtime.

```python
PARSERS = {
    'recursive_descent': ['rd', 'recursive', 'default'],
    'combinator': ['pc', 'functional'],
}
```

## Convenience Imports (not in `__all__`)

All 27 builtin modules are imported at the package level to trigger
registration, so any class can be imported from its defining module:

```python
from psh.builtins.test_command import TestBuiltin
from psh.builtins.directory_stack import DirectoryStack
from psh.builtins.kill_command import SIGNAL_NAMES
from psh.builtins.parser_experiment import PARSER_LABELS
```

These are **not** part of the declared public contract. They are internal
implementation details that happen to be importable. New code should
prefer importing the public API items listed above.

### Notable Internal Items

| Import | Canonical path | Description |
|--------|---------------|-------------|
| `BuiltinRegistry` | `psh.builtins.registry` | The registry class. Most code uses the `registry` instance instead. |
| `DirectoryStack` | `psh.builtins.directory_stack` | Helper class for `pushd`/`popd`/`dirs` stack management. |
| `SIGNAL_NAMES` | `psh.builtins.kill_command` | Dict mapping POSIX signal names to `signal` module constants. |
| `PARSER_LABELS` | `psh.builtins.parser_experiment` | Dict mapping parser names to display labels (`'production'`, `'experimental'`). |
| `POSIX_SPECIAL_BUILTINS` | `psh.executor.strategies` | Set of POSIX special builtin names (not in the builtins package, but relevant). |

## API Tiers Summary

| Tier | Scope | How to import | Stability guarantee |
|------|-------|---------------|-------------------|
| **Public** | `registry`, `builtin`, `Builtin`, `FunctionReturn`, `PARSERS` | `from psh.builtins import ...` | Stable. Changes are versioned. |
| **Internal** | All builtin classes, helper classes, module-level constants | `from psh.builtins.<module> import ...` | Internal. May change without notice. |

## Typical Usage

### Check if a command is a builtin

```python
from psh.builtins import registry

if registry.has('echo'):
    builtin = registry.get('echo')
    exit_code = builtin.execute(['echo', 'hello'], shell)
```

### Create a new builtin

```python
from psh.builtins import Builtin, builtin

@builtin
class MyBuiltin(Builtin):
    name = "mycommand"

    def execute(self, args, shell):
        print(f"Hello from {args[0]}", file=shell.stdout)
        return 0
```

### Handle function returns in executor code

```python
from psh.builtins import FunctionReturn

try:
    result = execute_function(body, shell)
except FunctionReturn as e:
    result = e.exit_code
```

### Look up parser implementations

```python
from psh.builtins import PARSERS

for name, aliases in PARSERS.items():
    print(f"{name}: aliases={aliases}")
```

## Related Documents

- `docs/guides/builtins_guide.md` -- Full programmer's guide (architecture,
  file reference, adding builtins)
- `docs/guides/builtins_public_api_assessment.md` -- Analysis that led to
  this cleanup
- `psh/builtins/CLAUDE.md` -- AI assistant working guide for the builtins
  subsystem
