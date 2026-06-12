# PSH Expansion: Programmer's Guide

> **Note (2026-06-11):** This guide describes the tree as of ~v0.27x, before
> the v0.285 module relocation and subsequent cleanups. In particular it
> references `psh/arithmetic.py` and `psh/brace_expansion.py`, which have since moved into the `psh/expansion/` package.
> See the subsystem CLAUDE.md files for current structure.

This guide covers the expansion package in detail: its external API, internal
architecture, and the responsibilities of every source file.  It is aimed at
developers who need to modify expansion behaviour, add new expansion types, or
understand how shell arguments are transformed before command execution.

## 1. What the Expansion Package Does

The expansion package transforms shell arguments through the POSIX-defined
expansion pipeline.  It takes the raw Word AST nodes produced by the parser
and produces the final expanded argument list that the executor passes to
commands.

The expansion pipeline, in order:

```
1. Brace expansion      {a,b,c}         (handled by tokenizer, not this package)
2. Tilde expansion      ~, ~user        TildeExpander
3. Variable expansion   $VAR, ${VAR}    VariableExpander
4. Command substitution $(cmd), `cmd`   CommandSubstitution
5. Arithmetic expansion $((expr))       ExpansionManager.execute_arithmetic_expansion()
6. Word splitting       on IFS          WordSplitter
7. Pathname expansion   *, ?, [...]     GlobExpander
8. Quote removal        (automatic)     During processing
```

The package does **not** parse shell syntax (that is the parser's job) or
execute commands (that is the executor's job).  It also does not handle brace
expansion, which runs as a pre-tokenisation step in `psh/brace_expansion.py`.

## 2. External API

The public interface is defined in `psh/expansion/__init__.py`.  The declared
`__all__` contains a single item: `ExpansionManager`.  See
`docs/guides/expansion_public_api.md` for full signature documentation and API
tiers.

### 2.1 `ExpansionManager`

```python
from psh.expansion import ExpansionManager

expansion_manager = ExpansionManager(shell)
```

Central orchestrator constructed once by `Shell.__init__()` and stored as
`shell.expansion_manager`.  All external code accesses expansions through
`ExpansionManager` methods.

The key methods:

| Method | Returns | Description |
|--------|---------|-------------|
| `expand_arguments(command)` | `List[str]` | Main entry point: run the full expansion pipeline on a command's Word AST arguments. |
| `expand_string_variables(text)` | `str` | Expand `$VAR`, `$(cmd)`, `$((expr))` inline in a string. |
| `expand_variable(var_expr)` | `str` | Expand a single variable expression. |
| `expand_tilde(path)` | `str` | Tilde expansion. |
| `execute_command_substitution(cmd_sub)` | `str` | Execute command substitution. |
| `execute_arithmetic_expansion(expr)` | `int` | Execute arithmetic expansion. |

### 2.2 Convenience imports

`contains_extglob` and `match_extglob` are importable from `psh.expansion`
but are not in `__all__`.  They are stateless utility functions for extended
glob pattern detection and matching.

### 2.3 How external code uses the expansion package

External code never constructs expander instances directly.  Instead:

```python
# The single production import (in shell.py):
from psh.expansion import ExpansionManager
self.expansion_manager = ExpansionManager(self)

# All other code uses the instance:
args = shell.expansion_manager.expand_arguments(command)
value = shell.expansion_manager.expand_string_variables(text)
```


## 3. Architecture

### 3.1 Component structure

```
ExpansionManager (orchestrator)
     |
     +-- VariableExpander          $VAR, ${VAR}, arrays, special vars
     |   +-- ParameterExpansion    ${VAR:-default}, ${VAR//pat/repl}, etc.
     |       +-- PatternMatcher    Shell glob -> Python regex conversion
     +-- CommandSubstitution       $(cmd), `cmd`
     +-- TildeExpander             ~, ~user
     +-- GlobExpander              *, ?, [...]
     +-- WordSplitter              IFS word splitting
     +-- ExpansionEvaluator        AST node -> string (lazy-loaded)
```

`ExpansionManager` is a clean facade.  External code accesses it through
`shell.expansion_manager` and the six public methods listed above cover all
use cases.

### 3.2 The expansion pipeline

For a simple command like `echo "$HOME" *.txt`:

```
Word AST from parser:
  [Word("echo"), Word('"$HOME"', quoted), Word("*.txt")]
         |
         v
ExpansionManager.expand_arguments(command)
         |
         v
_expand_word_ast_arguments() -- iterate over command.words
         |
         +--> Word "echo"    -- unquoted literal
         |    -> ["echo"]
         |
         +--> Word '"$HOME"' -- double-quoted with VariableExpansion
         |    -> _expand_double_quoted_word()
         |       -> ExpansionEvaluator.evaluate(VariableExpansion("HOME"))
         |       -> VariableExpander.expand_variable("$HOME")
         |       -> "/Users/user"
         |    -> ["/Users/user"]    (no word splitting, no globbing -- quoted)
         |
         +--> Word "*.txt"   -- unquoted literal with glob chars
              -> ["*.txt"]
              -> _glob_words(["*.txt"])
              -> GlobExpander.expand("*.txt")
              -> ["a.txt", "b.txt"]

Final result: ["echo", "/Users/user", "a.txt", "b.txt"]
```

### 3.3 Word AST expansion

The `_expand_word()` method is the core dispatch point.  It handles each word
based on its quoting context:

```python
def _expand_word(self, word: Word) -> Union[str, List[str]]:
    # Single-quoted word: return literal value
    # Double-quoted word: expand vars/commands, no splitting/globbing
    # ANSI-C ($'...'): return literal (lexer already processed escapes)
    # Composite/unquoted: per-part expansion with splitting/globbing
```

Key behaviours controlled by Word AST structure:

- **Glob suppression** -- quoted parts suppress pathname expansion.
- **Word splitting** -- only triggered when there are unquoted expansion
  results.
- **Tilde expansion** -- only on the first unquoted literal, not after
  escape processing.
- **Escape processing** -- `_process_unquoted_escapes()` handles `\$`, `\\`,
  `\~`, `\*`, etc.
- **Assignment detection** -- words containing `=` with a valid variable name
  suppress word splitting.

### 3.4 `ExpansionEvaluator` -- bridging AST to strings

`ExpansionEvaluator` converts expansion AST nodes back into the string
representations that `VariableExpander` expects, then delegates:

| AST Node | Evaluator method | Delegation target |
|----------|-----------------|-------------------|
| `VariableExpansion` | `_evaluate_variable()` | `VariableExpander.expand_variable("$name")` |
| `ParameterExpansion` | `_evaluate_parameter()` | `VariableExpander.expand_parameter_direct(op, name, operand)` |
| `CommandSubstitution` | `_evaluate_command_sub()` | `CommandSubstitution.execute("$(cmd)")` |
| `ArithmeticExpansion` | `_evaluate_arithmetic()` | `ExpansionManager.execute_arithmetic_expansion("$((expr))")` |

For `ParameterExpansion`, the evaluator uses `expand_parameter_direct()`
which receives pre-parsed components (operator, variable name, operand)
directly from the AST, avoiding the string round-trip through
`parse_expansion()`.

### 3.5 Variable expansion

`VariableExpander` is the largest module (~907 lines) and handles:

```
Simple variables:    $var, ${var}
Special variables:   $?, $$, $!, $#, $@, $*, $0-$9, $-
Array subscripts:    ${arr[0]}, ${arr[@]}, ${arr[*]}
Array indices:       ${!arr[@]}, ${!arr[*]}
Array slicing:       ${arr[@]:start:length}
Array/string length: ${#var}, ${#arr[@]}, ${#arr[index]}
```

For parameter expansion operators (`${var:-default}`, `${var//pat/repl}`,
etc.), `VariableExpander` delegates to `ParameterExpansion`, which contains
all operator implementations.

### 3.6 Parameter expansion operators

`ParameterExpansion` implements all POSIX and bash parameter expansion
operators:

| Operator | Method | Description |
|----------|--------|-------------|
| `${var:-default}` | (in `VariableExpander._apply_operator`) | Use default if unset/null. |
| `${var:=default}` | (in `VariableExpander._apply_operator`) | Assign default if unset/null. |
| `${var:+value}` | (in `VariableExpander._apply_operator`) | Use value if set. |
| `${var:?error}` | (in `VariableExpander._apply_operator`) | Error if unset/null. |
| `${#var}` | `get_length()` | String/array length. |
| `${var#pattern}` | `remove_shortest_prefix()` | Remove shortest prefix match. |
| `${var##pattern}` | `remove_longest_prefix()` | Remove longest prefix match. |
| `${var%pattern}` | `remove_shortest_suffix()` | Remove shortest suffix match. |
| `${var%%pattern}` | `remove_longest_suffix()` | Remove longest suffix match. |
| `${var/pat/repl}` | `substitute_first()` | Replace first match. |
| `${var//pat/repl}` | `substitute_all()` | Replace all matches. |
| `${var/#pat/repl}` | `substitute_prefix()` | Replace prefix match. |
| `${var/%pat/repl}` | `substitute_suffix()` | Replace suffix match. |
| `${var:offset:length}` | `extract_substring()` | Substring extraction. |
| `${!var*}`, `${!var@}` | `match_variable_names()` | Variable name matching. |
| `${var^pat}` | `uppercase_first()` | Uppercase first matching char. |
| `${var^^pat}` | `uppercase_all()` | Uppercase all matching chars. |
| `${var,pat}` | `lowercase_first()` | Lowercase first matching char. |
| `${var,,pat}` | `lowercase_all()` | Lowercase all matching chars. |

Pattern matching in these operators uses `PatternMatcher.shell_pattern_to_regex()`
to convert shell glob patterns (including extglob when enabled) to Python
regular expressions.

### 3.7 Command substitution

`CommandSubstitution.execute()` handles `$(cmd)` and `` `cmd` ``:

1. Create a pipe for capturing output.
2. Reset SIGCHLD to default to prevent job control interference.
3. Fork a child process.
4. Child: create a new `Shell` instance with `parent_shell=self.shell`,
   apply child signal policy, redirect stdout to the write end of the pipe,
   execute the command, exit.
5. Parent: read stdout from the read end, wait for child, strip trailing
   newlines (POSIX behaviour), set `last_exit_code`.

### 3.8 IFS word splitting

`WordSplitter.split()` implements POSIX 2.6.5 IFS splitting:

- IFS whitespace characters (space, tab, newline) are trimmed from
  start/end and consecutive occurrences collapse into one delimiter.
- Non-whitespace IFS characters always produce a field boundary,
  preserving empty fields.
- Backslash-escaped characters are preserved (not treated as delimiters).
- `ifs=None` (unset) uses default `' \t\n'`.
- `ifs=''` (empty string) means no splitting.

`WordSplitter` is stateless -- it has no `shell` reference and no
`__init__` parameters.

### 3.9 Pathname expansion (globbing)

`GlobExpander.expand()` uses Python's `glob.glob()` for standard patterns.
When the `extglob` shell option is enabled, it delegates to
`_expand_extglob()` which uses the `extglob` module's `expand_extglob()`
function.

Respects the `dotglob` option for hidden files (passed as
`include_hidden` to `glob.glob()`).

### 3.10 Extended glob patterns

The `extglob.py` module provides stateless utility functions (no class, no
shell reference) for bash-compatible extended glob patterns:

```
?(pattern|alt)   Zero or one occurrence
*(pattern|alt)   Zero or more occurrences
+(pattern|alt)   One or more occurrences
@(pattern|alt)   Exactly one occurrence
!(pattern|alt)   Anything except the pattern
```

Implementation converts extglob patterns to Python regular expressions via
`extglob_to_regex()`, supporting nesting and pipe-separated alternatives.


## 4. Quote Handling

Different quote types affect which expansions are performed:

| Quote Type | Variable | Command Sub | Glob | Word Split |
|------------|----------|-------------|------|------------|
| Unquoted | Yes | Yes | Yes | Yes |
| `"double"` | Yes | Yes | No | No |
| `'single'` | No | No | No | No |
| `$'ansi'` | Escape sequences only | No | No | No |

### `"$@"` expansion

When `"$@"` appears inside double quotes, the expansion manager distributes
prefix and suffix text across positional parameters:

```bash
# "$@" with params (a, b) -> "a" "b"
# "x$@y" with params (a, b) -> "xa" "by"
# "$@" with no params -> nothing (removed entirely)
```

This is handled in `_expand_double_quoted_word()` and
`_expand_at_with_affixes()`.

### `"${arr[@]}"` expansion

Array expansion in double quotes follows the same splitting rules as `"$@"`:
each array element becomes a separate word.  `"${arr[*]}"` joins elements
with the first character of IFS.


## 5. Source File Reference

All files are under `psh/expansion/`.  Line counts are approximate.

### 5.1 Package entry point

#### `__init__.py` (~7 lines)

Imports `ExpansionManager` from `manager.py` and declares
`__all__ = ['ExpansionManager']`.  Also imports `contains_extglob` and
`match_extglob` as convenience imports (not in `__all__`).

### 5.2 Core orchestrator

#### `manager.py` (~693 lines)

The `ExpansionManager` class.  Initialises five sub-expanders and provides
the public methods that the executor and other subsystems call.

Key responsibilities:

- **`expand_arguments(command)`** -- main entry point, delegates to
  `_expand_word_ast_arguments()`.
- **`_expand_word_ast_arguments(command)`** -- iterates over `command.words`,
  dispatching each word to `_expand_word()`.
- **`_expand_word(word)`** -- per-word expansion with full quoting awareness.
  Routes to `_expand_double_quoted_word()` for double-quoted words or handles
  composite/unquoted words part-by-part.
- **`_expand_double_quoted_word(word)`** -- handles `"$@"` splitting,
  variable expansion, command substitution, and escape processing inside
  double quotes.
- **`_expand_at_with_affixes(prefix, suffix, quoted_params)`** -- distributes
  prefix/suffix text across `$@` elements.
- **`_glob_words(words)`** -- applies `GlobExpander` to each word, respecting
  `noglob` and `nullglob` options.
- **`_expand_expansion(expansion)`** -- delegates AST expansion nodes to
  `ExpansionEvaluator.evaluate()`.
- **`_split_with_ifs(text, quote_type)`** -- IFS splitting wrapper that
  skips splitting for quoted text.
- **`expand_string_variables(text)`** / **`expand_variable(var_expr)`** /
  **`expand_tilde(path)`** -- thin wrappers delegating to sub-expanders.
- **`execute_command_substitution(cmd_sub)`** -- delegates to
  `CommandSubstitution.execute()`.
- **`execute_arithmetic_expansion(expr)`** -- strips `$((...))` wrapper,
  pre-expands `$var` and `$(cmd)` in the expression, then calls
  `evaluate_arithmetic()` from `psh/arithmetic.py`.
- **Static helpers**: `_process_dquote_escapes()`, `_process_unquoted_escapes()`,
  `_has_process_substitution()`, `_word_to_string()`, `_expansion_to_literal()`.

### 5.3 Variable expansion

#### `variable.py` (~907 lines)

`VariableExpander` -- the largest file in the package.  Handles:

- **Simple variables**: `$var`, `${var}`.
- **Special variables**: `$?`, `$$`, `$!`, `$#`, `$@`, `$*`, `$0`-`$9`, `$-`.
- **Brace-enclosed syntax**: `${var}`, parameter expansion operators.
- **Array operations**: subscript access, `@`/`*` expansion, slicing,
  indices/keys, length.
- **String variable expansion**: `expand_string_variables()` for inline
  `$var`, `$(cmd)`, `$((expr))` in strings.
- **Direct parameter expansion**: `expand_parameter_direct()` for
  pre-parsed operator/name/operand triples (used by `ExpansionEvaluator`).

Private methods handle the internal dispatch:

- `_expand_special_variable()` -- routes to the correct special variable.
- `_get_var_or_positional()` -- resolves a name to its value (variable or
  positional parameter), with array subscript support.
- `_set_var_or_array_element()` -- sets a variable or array element (used
  by `:=` operator).
- `_apply_operator()` -- applies default/assign/error/alternate operators.
- `_expand_tilde_in_operand()` -- tilde expansion in operator operands.
- `_split_pattern_replacement()` -- splits `pattern/replacement` on
  unescaped `/`.
- Array-specific: `_expand_array_length()`, `_expand_array_indices()`,
  `_expand_array_slice()`, `_expand_array_subscript()`.

### 5.4 Parameter expansion

#### `parameter_expansion.py` (~412 lines)

Two classes:

**`ParameterExpansion`** -- implements all parameter expansion operators.
Groups of methods:

- **Parsing**: `parse_expansion(expr)` -- extracts operator, variable name,
  and operand from `${...}` content.
- **Pattern removal**: `remove_shortest_prefix()`, `remove_longest_prefix()`,
  `remove_shortest_suffix()`, `remove_longest_suffix()`.
- **Pattern substitution**: `substitute_first()`, `substitute_all()`,
  `substitute_prefix()`, `substitute_suffix()`.
- **Substring**: `extract_substring()`.
- **Length**: `get_length()`.
- **Name matching**: `match_variable_names()`.
- **Case modification**: `uppercase_first()`, `uppercase_all()`,
  `lowercase_first()`, `lowercase_all()`.

**`PatternMatcher`** -- converts shell glob patterns to Python regexes.
Single method: `shell_pattern_to_regex(pattern, anchored, from_start,
extglob_enabled)`.

### 5.5 Command substitution

#### `command_sub.py` (~138 lines)

`CommandSubstitution` class.  Single public method: `execute(cmd_sub)`.

Creates a pipe, forks a child, executes the command in a new `Shell`
instance, captures stdout, strips trailing newlines, and sets the exit code.
Uses `apply_child_signal_policy()` for proper signal setup in the child.
Protects stdin in interactive mode (redirects from `/dev/null`).

### 5.6 Extended glob

#### `extglob.py` (~260 lines)

Module-level functions (no class):

- `contains_extglob(pattern)` -- detect extglob operators.
- `match_extglob(pattern, string, full_match=True)` -- match string against
  pattern.
- `extglob_to_regex(pattern, anchored, from_start, for_pathname)` -- convert
  to Python regex.
- `expand_extglob(pattern, directory, dotglob)` -- expand against filesystem.

Private helpers: `_find_matching_paren()`, `_split_pattern_list()`,
`_convert_pattern()`, `_is_standalone_negation()`.

### 5.7 Evaluator

#### `evaluator.py` (~92 lines)

`ExpansionEvaluator` class.  Bridges expansion AST nodes to the string-based
expansion API by dispatching on node type and delegating to
`VariableExpander` or `ExpansionManager`.  Lazy-loaded via the
`ExpansionManager.evaluator` property.

### 5.8 Glob expansion

#### `glob.py` (~63 lines)

`GlobExpander` class.  Single public method: `expand(pattern)`.
Uses Python's `glob.glob()` for standard patterns and delegates to
`extglob.expand_extglob()` when extglob patterns are detected.

### 5.9 Tilde expansion

#### `tilde.py` (~54 lines)

`TildeExpander` class.  Single public method: `expand(path)`.
Expands `~` to `$HOME` (fallback: `pwd.getpwuid()`), `~/path` to
`$HOME/path`, and `~username` to the user's home directory via
`pwd.getpwnam()`.

### 5.10 Word splitting

#### `word_splitter.py` (~112 lines)

`WordSplitter` class.  Single public method: `split(text, ifs)`.
Stateless (no constructor parameters).  Implements POSIX 2.6.5 IFS
splitting rules with proper handling of whitespace vs non-whitespace IFS
characters, empty fields, and backslash escapes.


## 6. Common Tasks

### 6.1 Adding a new expansion type

1. Create an expander class with `__init__(self, shell)` and a domain method:

   ```python
   # In psh/expansion/new_expander.py
   class NewExpander:
       def __init__(self, shell):
           self.shell = shell
           self.state = shell.state

       def expand(self, value: str) -> str:
           # Implement expansion logic
           return expanded_value
   ```

2. Add to `ExpansionManager.__init__()`:
   ```python
   self.new_expander = NewExpander(shell)
   ```

3. Integrate into `_expand_word()` or `_expand_word_ast_arguments()` at the
   correct position in the POSIX expansion order.

4. Add a public method on `ExpansionManager` if external code needs direct
   access.

5. Add tests in `tests/unit/expansion/`.

### 6.2 Adding a parameter expansion operator

1. Add operator parsing in `ParameterExpansion.parse_expansion()`.

2. Add the operation method on `ParameterExpansion` (e.g.
   `new_operation(value, pattern)`).

3. Wire it into `VariableExpander._apply_operator()` or the appropriate
   dispatch point.

4. Add tests.

### 6.3 Adding a new special variable

1. Add handling in `VariableExpander._expand_special_variable()`.

2. Add tests in `tests/unit/expansion/`.

### 6.4 Modifying word splitting behaviour

The word splitting rules are centralised in `WordSplitter.split()`.  The
method is stateless -- it receives `text` and `ifs` as arguments, so
changes only need to be made in one place.

### 6.5 Debugging expansion

```bash
# Show pre/post expansion
python -m psh --debug-expansion -c "echo $HOME *.txt"

# Trace each expansion step
python -m psh --debug-expansion-detail -c 'echo "${arr[@]}"'
```

Output example:
```
[EXPANSION] Expanding Word AST command: ['echo', '$HOME', '*.txt']
[EXPANSION] Word AST Result: ['echo', '/Users/user', 'a.txt', 'b.txt']
```

Programmatically:

```python
from psh.expansion.word_splitter import WordSplitter

# Test IFS splitting in isolation
splitter = WordSplitter()
result = splitter.split("a::b", ":")
# result = ['a', '', 'b']
```


## 7. Design Rationale

### Why a central `ExpansionManager` instead of direct expander access?

Expansion order matters.  Variables must be expanded before word splitting,
which must happen before pathname expansion.  Centralising the orchestration
in `ExpansionManager` ensures the correct order is always applied and
prevents callers from accidentally running expansions out of sequence.

### Why does `ExpansionEvaluator` reconstruct strings from AST nodes?

The parser builds typed AST nodes (`VariableExpansion`, `ParameterExpansion`,
etc.) for each expansion in a word.  The expansion engine, however, was
originally built around string-based APIs (`expand_variable("$HOME")`).
Rather than duplicate all expansion logic in a separate AST-aware code path,
`ExpansionEvaluator` bridges the gap by converting AST nodes back to their
string forms and delegating.  For `ParameterExpansion`, the evaluator
partially avoids this round-trip by using `expand_parameter_direct()`.

### Why is `WordSplitter` stateless?

IFS word splitting is a pure function: given text and an IFS value, the
output is deterministic.  Making `WordSplitter` stateless (no `shell`
reference) means it can be instantiated anywhere without side effects and
tested in isolation.

### Why are `extglob` functions module-level instead of on a class?

Extended glob operations (`contains_extglob`, `match_extglob`, etc.) are
stateless -- they don't need shell state.  Module-level functions avoid the
overhead and ceremony of a class for what are essentially pure utility
functions.

### Why is `variable.py` so large (907 lines)?

Variable expansion in shell is inherently complex.  It covers simple
variables, special parameters, arrays (indexed and associative), array
slicing, parameter expansion operators, inline string expansion, and
interactions between all of these.  The module is cohesive -- all these
operations share the same internal helpers (`_get_var_or_positional`,
`_expand_special_variable`, etc.).  A potential future split could extract
array expansion logic, but the current single-module structure keeps related
code together.

### Why does command substitution fork a new Shell?

Command substitution creates a subshell environment where changes to
variables, directory, traps, etc. do not affect the parent.  Forking a
child process and creating a new `Shell` with `parent_shell=self.shell`
provides proper isolation while inheriting the parent's state.


## 8. File Dependency Graph

```
__init__.py
└── manager.py  (ExpansionManager)
    ├── variable.py  (VariableExpander)
    │   └── parameter_expansion.py  (ParameterExpansion, PatternMatcher)
    │       └── extglob.py  (contains_extglob, extglob_to_regex)
    ├── command_sub.py  (CommandSubstitution)
    ├── tilde.py  (TildeExpander)
    ├── glob.py  (GlobExpander)
    │   └── extglob.py  (contains_extglob, expand_extglob)
    ├── word_splitter.py  (WordSplitter)
    └── evaluator.py  (ExpansionEvaluator — lazy-loaded)

External dependencies (outside the expansion package):
- psh/ast_nodes.py       — Word, SimpleCommand, expansion node types
- psh/core/state.py      — ShellState (variables, options, positional params)
- psh/core/exceptions.py — ExpansionError
- psh/arithmetic.py      — evaluate_arithmetic() (for $((expr)))
- psh/shell.py           — Shell (for command substitution child)
- psh/executor/child_policy.py — apply_child_signal_policy() (command sub)
```


## 9. Integration Points

### With Executor (`psh/executor/`)

- `expand_arguments(command)` is called by `CommandExecutor` before command
  execution.
- `expand_variable()` is called by `ControlFlowExecutor` for `for` loop
  variable evaluation and by `CommandExecutor` for assignment expansion.
- `expand_tilde()` is called by `CommandExecutor` for unquoted tilde in
  assignments.

### With I/O Redirect (`psh/io_redirect/`)

- `expand_string_variables()` is called by `FileRedirector` for redirect
  targets (via `_expand_redirect_target()`) and heredoc content expansion.
- `expand_tilde()` is called by `FileRedirector` for redirect target paths.

### With Shell State (`psh/core/state.py`)

- Variables: `shell.state.get_variable()`, `shell.state.set_variable()`.
- Special variables: `shell.state.get_special_variable()`.
- Positional params: `shell.state.positional_params`.
- Options: `shell.state.options` (`noglob`, `nullglob`, `extglob`, `dotglob`,
  `nounset`, `noclobber`).

### With Arithmetic (`psh/arithmetic.py`)

- `execute_arithmetic_expansion()` calls `evaluate_arithmetic()` from
  `psh/arithmetic.py` after pre-expanding variables and command
  substitutions in the expression.

### With Parser (`psh/parser/`)

- Parser always builds Word AST nodes (`command.words`) with per-part quote
  context (`LiteralPart`, `ExpansionPart`).
- `ExpansionEvaluator` evaluates expansion AST nodes produced by the parser.
- `ParameterExpansion` nodes carry pre-parsed operator, parameter, and word
  fields, allowing `expand_parameter_direct()` to skip string reparsing.
