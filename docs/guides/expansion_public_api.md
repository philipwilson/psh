# Expansion Public API Reference

**As of v0.180.0** (post-cleanup)

This document describes the public API of the `psh.expansion` package: the
items declared in `__all__`, their signatures, and guidance on internal
imports that are available but not part of the public contract.

## Public API (`__all__`)

The declared public API consists of one item:

```python
__all__ = ['ExpansionManager']
```

### `ExpansionManager`

```python
from psh.expansion import ExpansionManager

expansion_manager = ExpansionManager(shell)
```

Central orchestrator for all shell expansions.  Constructed once by
`Shell.__init__()` and stored as `shell.expansion_manager`.  All external
access goes through `ExpansionManager` methods -- no other class in the
package is imported by production code outside `psh/expansion/`.

#### Constructor

```python
ExpansionManager(shell: Shell)
```

Creates the manager and initialises five sub-expanders:

- `self.variable_expander` -- `VariableExpander` instance for `$VAR`,
  `${VAR}`, arrays, and parameter expansion operators.
- `self.command_sub` -- `CommandSubstitution` instance for `$(cmd)` and
  `` `cmd` ``.
- `self.tilde_expander` -- `TildeExpander` instance for `~` and `~user`.
- `self.glob_expander` -- `GlobExpander` instance for pathname expansion
  (`*`, `?`, `[...]`).
- `self.word_splitter` -- `WordSplitter` instance for IFS word splitting.

A lazy-loaded `ExpansionEvaluator` is also available via the `evaluator`
property.

#### Argument expansion (primary entry point)

| Method | Signature | Description |
|--------|-----------|-------------|
| `expand_arguments` | `(command: SimpleCommand) -> List[str]` | Expand all arguments using Word AST nodes.  Runs the full POSIX expansion pipeline: tilde, variable, command substitution, arithmetic, word splitting, pathname expansion, and quote removal. |

#### Individual expansion methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `expand_string_variables` | `(text: str) -> str` | Expand variables and arithmetic in a string.  Used for heredoc content, here strings, and double-quoted strings.  Delegates to `VariableExpander.expand_string_variables()`. |
| `expand_variable` | `(var_expr: str) -> str` | Expand a variable expression (e.g. `$VAR`, `${VAR:-default}`).  Delegates to `VariableExpander.expand_variable()`. |
| `expand_tilde` | `(path: str) -> str` | Expand tilde in paths (`~` and `~user`).  Delegates to `TildeExpander.expand()`. |
| `execute_command_substitution` | `(cmd_sub: str) -> str` | Execute `$(cmd)` or `` `cmd` `` and return captured stdout.  Delegates to `CommandSubstitution.execute()`. |
| `execute_arithmetic_expansion` | `(expr: str) -> int` | Execute `$((expr))` and return the integer result.  Pre-expands variables and command substitutions in the expression before evaluation. |

#### Evaluator property

| Property | Type | Description |
|----------|------|-------------|
| `evaluator` | `ExpansionEvaluator` | Lazy-loaded evaluator that converts expansion AST nodes (from the parser's Word AST) into expanded string values.  Bridges the AST representation to the string-based expansion API. |

## Convenience Imports (not in `__all__`)

The following items are importable from `psh.expansion` for convenience but
are **not** part of the declared public contract.  They are stateless
utility functions whose signatures are unlikely to change, but new code
should prefer the submodule import paths listed below.

### Extended Glob Utilities

| Import | Canonical path | Description |
|--------|---------------|-------------|
| `contains_extglob` | `psh.expansion.extglob` | Check if a pattern contains extglob operators (`?(...)`, `*(...)`, `+(...)`, `@(...)`, `!(...)`).  Returns `bool`. |
| `match_extglob` | `psh.expansion.extglob` | Match a string against an extglob pattern.  Returns `bool`. |

These have 2 production callers outside the package (`executor/control_flow.py`,
`executor/test_evaluator.py`) and are stateless (no shell reference needed),
making direct import appropriate.

## Internal Classes (not in `__all__`)

These classes are not exported by the package but are used internally.
They can be imported from their defining modules for testing or advanced
use, but their signatures may change without notice.

### `VariableExpander`

```python
from psh.expansion.variable import VariableExpander
```

Handles all `$`-prefixed variable and parameter expansion.  The largest
class in the package (~907 lines).  Provides:

| Method | Signature | Purpose |
|--------|-----------|---------|
| `expand_variable` | `(var_expr: str) -> str` | Expand `$var`, `${var}`, special variables, arrays. |
| `expand_parameter_direct` | `(operator: str, var_name: str, operand: str) -> str` | Apply a parameter expansion operator from pre-parsed components (avoids string round-trip). |
| `expand_string_variables` | `(text: str) -> str` | Expand `$var`, `$(cmd)`, `$((expr))` inline in a string. |
| `expand_array_index` | `(index_expr: str) -> str` | Expand variables in array subscript expressions. |
| `is_array_expansion` | `(var_expr: str) -> bool` | Check if an expansion produces multiple words (`$@`, `${arr[@]}`). |
| `expand_array_to_list` | `(var_expr: str) -> list` | Expand array to a word list for `${arr[@]}` syntax. |

Contains a `ParameterExpansion` instance (`self.param_expansion`) for
operator handling.

### `ParameterExpansion`

```python
from psh.expansion.parameter_expansion import ParameterExpansion
```

Advanced parameter expansion operations.  Contains a `PatternMatcher`
for converting shell glob patterns to Python regexes.

| Method group | Methods |
|-------------|---------|
| **Parsing** | `parse_expansion(expr) -> (operator, var_name, operand)` |
| **Length** | `get_length(value) -> str` |
| **Prefix/suffix removal** | `remove_shortest_prefix`, `remove_longest_prefix`, `remove_shortest_suffix`, `remove_longest_suffix` |
| **Substitution** | `substitute_first`, `substitute_all`, `substitute_prefix`, `substitute_suffix` |
| **Substring** | `extract_substring(value, offset, length=None) -> str` |
| **Name matching** | `match_variable_names(prefix, quoted=False) -> List[str]` |
| **Case modification** | `uppercase_first`, `uppercase_all`, `lowercase_first`, `lowercase_all` |

### `ExpansionEvaluator`

```python
from psh.expansion.evaluator import ExpansionEvaluator
```

Evaluates expansion AST nodes by dispatching to `VariableExpander` and
`ExpansionManager`.  Handles `VariableExpansion`, `ParameterExpansion`,
`CommandSubstitution`, and `ArithmeticExpansion` node types.

### `CommandSubstitution`

```python
from psh.expansion.command_sub import CommandSubstitution
```

Handles `$(cmd)` and `` `cmd` `` by forking a child process with a new
`Shell` instance, capturing stdout to a pipe, and stripping trailing
newlines per POSIX.

### `TildeExpander`

```python
from psh.expansion.tilde import TildeExpander
```

Expands `~` to `$HOME` (or `pwd.getpwuid()` fallback) and `~username`
to the named user's home directory.  Returns the path unchanged if the
user is not found.

### `GlobExpander`

```python
from psh.expansion.glob import GlobExpander
```

Pathname expansion using Python's `glob.glob()`.  Supports standard
patterns (`*`, `?`, `[...]`), dotglob for hidden files, and extended
glob patterns when `extglob` is enabled.

### `WordSplitter`

```python
from psh.expansion.word_splitter import WordSplitter
```

POSIX-compliant IFS word splitting.  Stateless (no shell reference).

| Behaviour | Detail |
|-----------|--------|
| `ifs=None` (unset) | Uses default `' \t\n'`. |
| `ifs=''` (empty) | No splitting occurs. |
| IFS whitespace | Collapses and trims. |
| Non-whitespace IFS | Always produces field boundary, preserves empty fields. |
| Backslash escapes | Prevent IFS interpretation. |

### Extended Glob Module Functions

```python
from psh.expansion.extglob import contains_extglob, match_extglob
from psh.expansion.extglob import extglob_to_regex, expand_extglob
```

| Function | Signature | Purpose |
|----------|-----------|---------|
| `contains_extglob` | `(pattern: str) -> bool` | Check for extglob operators. |
| `match_extglob` | `(pattern: str, string: str, full_match: bool = True) -> bool` | Match string against extglob pattern. |
| `extglob_to_regex` | `(pattern: str, anchored: bool = True, from_start: bool = True, for_pathname: bool = False) -> str` | Convert extglob to Python regex. |
| `expand_extglob` | `(pattern: str, directory: str = '.', dotglob: bool = False) -> List[str]` | Expand extglob against filesystem. |

### `PatternMatcher`

```python
from psh.expansion.parameter_expansion import PatternMatcher
```

Converts shell glob patterns (including extglob) to Python regular
expressions.  Stateless utility used by `ParameterExpansion`.

## Typical Usage

### Expand command arguments

```python
# Via the shell (normal execution path)
expanded_args = shell.expansion_manager.expand_arguments(command)
```

### Expand variables in a string

```python
# Heredoc content, here strings, double-quoted strings
expanded = shell.expansion_manager.expand_string_variables(text)
```

### Expand a single variable

```python
# (manager-level expand_variable() was removed in v0.312 as dead API;
# use the variable expander directly)
value = shell.expansion_manager.variable_expander.expand_variable("$HOME")
value = shell.expansion_manager.variable_expander.expand_variable("${name:-default}")
```

### Tilde expansion

```python
path = shell.expansion_manager.expand_tilde("~/bin")
```

### Execute command substitution

```python
# (manager-level execute_command_substitution() was removed in v0.312;
# use the command-substitution component directly)
output = shell.expansion_manager.command_sub.execute("$(date)")
```

### Arithmetic expansion

```python
result = shell.expansion_manager.execute_arithmetic_expansion("$((1 + 2))")
# result = 3
```

### Check for extglob patterns

```python
from psh.expansion import contains_extglob, match_extglob

if contains_extglob(pattern):
    if match_extglob(pattern, filename):
        # pattern matches
        pass
```

## API Tiers Summary

| Tier | Scope | How to import | Stability guarantee |
|------|-------|---------------|-------------------|
| **Public** | `ExpansionManager` | `from psh.expansion import ...` | Stable.  Changes are versioned. |
| **Convenience** | `contains_extglob`, `match_extglob` | `from psh.expansion import ...` (works) or `from psh.expansion.extglob import ...` (preferred) | Available but not guaranteed.  Prefer submodule paths. |
| **Internal** | `VariableExpander`, `ParameterExpansion`, `ExpansionEvaluator`, `CommandSubstitution`, `TildeExpander`, `GlobExpander`, `WordSplitter`, `PatternMatcher`, `extglob_to_regex`, `expand_extglob` | `from psh.expansion.<module> import ...` | Internal.  May change without notice. |

## Related Documents

- `docs/guides/expansion_guide.md` -- Full programmer's guide
  (architecture, file reference, design rationale)
- `docs/guides/expansion_public_api_assessment.md` -- Analysis that led
  to this cleanup
- `psh/expansion/CLAUDE.md` -- AI assistant working guide for the
  expansion subsystem
