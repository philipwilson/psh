# Expansion Subsystem

This document provides guidance for working with the PSH expansion subsystem.

## Architecture Overview

The expansion subsystem transforms shell input through multiple stages before command execution. It implements POSIX-compliant expansion ordering with bash extensions.

```
Input Arguments → ExpansionManager → Expanded Arguments
                        ↓
    ┌──────────┬────────┼────────┬──────────┬──────────┐
    ↓          ↓        ↓        ↓          ↓          ↓
  Tilde    Variable  Command  Arithmetic  Word    Pathname
 Expander  Expander    Sub      Eval    Splitter  (Glob)
```

## Key Files

| File | Purpose |
|------|---------|
| `manager.py` | `ExpansionManager` - orchestrates all expansions in correct order |
| `evaluator.py` | `ExpansionEvaluator` - evaluates expansion AST nodes |
| `variable.py` | `VariableExpander` - dispatch, special variables, `${!name}` indirection |
| `arrays.py` | `ArrayOpsMixin` - `${arr[i]}`, `${arr[@]}`, `_eval_array_index()` |
| `operators.py` | `OperatorOpsMixin` - `${VAR:-...}`, `${VAR#...}`, `${VAR/p/r}`, case ops |
| `operands.py` | `OperandOpsMixin` - expands pattern/replacement operands, `glob_escape()` |
| `fields.py` | `FieldExpansionMixin` - `expand_to_fields()` for multi-field `$@`/array results |
| `pattern.py` | `PatternMatcher` - THE canonical shell-pattern→regex converter/matcher |
| `extglob.py` | Extended glob (`@(...)`, `!(...)`) pattern conversion and matching |
| `parameter_expansion.py` | `ParameterExpansion` - string ops behind the operators (incl. `PATSUB_MATCH`) |
| `command_sub.py` | `CommandSubstitution` - handles `$(cmd)` and `` `cmd` `` |
| `tilde.py` | `TildeExpander` - handles `~` and `~user` |
| `glob.py` | `GlobExpander` - pathname expansion (wildcards) |
| `word_splitter.py` | `WordSplitter` - splits on IFS (`split()`, `split_with_edges()`) |
| `arithmetic.py` | Arithmetic tokenizer/parser/evaluator (`evaluate_arithmetic()`) |
| `brace_expansion.py` | `BraceExpander`, `TokenBraceExpander` - `{a,b}`, `{1..5}` |
| `aliases.py` | `AliasManager` - alias storage and expansion |

`VariableExpander` was decomposed in v0.279: it is now a thin facade,
`class VariableExpander(ArrayOpsMixin, OperatorOpsMixin, OperandOpsMixin,
FieldExpansionMixin, ...)`, with the mixins in `arrays.py`, `operators.py`,
`operands.py`, and `fields.py`. `arithmetic.py`, `brace_expansion.py`, and
`aliases.py` moved into this package from the top-level `psh/` in v0.285.

## Core Patterns

### 1. ExpansionManager Orchestration

All expansions go through `ExpansionManager`:

```python
class ExpansionManager:
    def __init__(self, shell):
        self.variable_expander = VariableExpander(shell)
        self.command_sub = CommandSubstitution(shell)
        self.tilde_expander = TildeExpander(shell)
        self.glob_expander = GlobExpander(shell)
        self.word_splitter = WordSplitter()

    def expand_arguments(self, command: SimpleCommand) -> List[str]:
        """Expand all arguments using Word AST nodes."""
        return self._expand_word_ast_arguments(command)
```

### 2. Word AST Expansion (Primary Path)

Arguments are expanded using Word AST nodes. Each `Word` contains
`LiteralPart` and `ExpansionPart` nodes with per-part quote context.
The `_expand_word()` method walks the parts and applies expansions
based on each part's `quoted` and `quote_char` fields:

```python
def _expand_word(self, word: Word) -> Union[str, List[str]]:
    # Single-quoted: return literal
    # Double-quoted: expand vars/commands, no splitting/globbing
    # ANSI-C ($'...'): return literal (lexer already processed escapes)
    # Composite/unquoted: per-part expansion with splitting/globbing
```

Key behaviors controlled by Word AST structure:
- **Glob suppression**: Quoted `LiteralPart`/`ExpansionPart` nodes suppress globbing
- **Word splitting**: Only triggered when there are unquoted expansion results
- **Tilde expansion**: Only on first unquoted literal, not after escape processing
- **Escape processing**: `_process_unquoted_escapes()` handles `\$`, `\\`, `\~`, `\*` etc.
- **Declaration-builtin assignments**: an assignment-shaped argument
  (`NAME=...`/`NAME+=...`, unquoted literal prefix, valid identifier — see
  `assignment_word_prefix()`) of a declaration builtin (`DECLARATION_BUILTINS`:
  alias, declare, typeset, export, local, readonly) skips word splitting AND
  pathname expansion. The CALLER decides (`expand_arguments()` checks the
  literal command word); `_expand_word()` never guesses from a `=`. Ordinary
  commands split such arguments (`printf '%s' foo=$x` splits — bash). True
  command-prefix assignments are stripped by the executor before expansion.
- **Assignment-value tilde**: assignment-shaped words (any command's
  arguments and for/select items, NOT array initializers) expand unquoted
  tilde prefixes after the first `=` and after each `:`
  (`_expand_assignment_value_tildes()`)

### 3. ExpansionEvaluator

`ExpansionEvaluator` evaluates expansion AST nodes by delegating to
`VariableExpander`.  For `ParameterExpansion` nodes it calls
`expand_parameter_direct()` with the pre-parsed (operator, var_name,
operand) components, avoiding the string round-trip through
`parse_expansion()`:

```python
class ExpansionEvaluator:
    def evaluate(self, expansion: Expansion) -> str:
        # VariableExpansion → expand_variable("$name")
        # ParameterExpansion → expand_parameter_direct(op, name, operand)
        # CommandSubstitution → command_sub.execute("$(cmd)")
        # ArithmeticExpansion → execute_arithmetic_expansion("$((expr))")
```

## Expansion Order (POSIX)

The `expand_arguments()` method processes expansions in this order:

```
1. Brace Expansion      {a,b,c}         → TokenBraceExpander (token stream, post-lex)
2. Tilde Expansion      ~, ~user        → TildeExpander
3. Variable Expansion   $VAR, ${VAR}    → VariableExpander
4. Command Substitution $(cmd), `cmd`   → CommandSubstitution
5. Arithmetic Expansion $((expr))       → execute_arithmetic_expansion()
6. Word Splitting       on IFS          → WordSplitter
7. Pathname Expansion   *, ?, [...]     → GlobExpander
8. Quote Removal        remove quotes   → During processing
```

## Variable Expansion Details

The `VariableExpander` handles:

```python
# Simple variables
$VAR, ${VAR}

# Special variables
$?, $$, $!, $#, $@, $*, $0-$9

# Parameter expansion operators
${VAR:-default}   # Use default if unset/null
${VAR:=default}   # Assign default if unset/null
${VAR:+value}     # Use value if set
${VAR:?error}     # Error if unset/null
${#VAR}           # String length
${VAR%pattern}    # Remove shortest suffix
${VAR%%pattern}   # Remove longest suffix
${VAR#pattern}    # Remove shortest prefix
${VAR##pattern}   # Remove longest prefix
${VAR/pat/repl}   # Replace first match
${VAR//pat/repl}  # Replace all matches

# Array expansions
${arr[0]}, ${arr[@]}, ${arr[*]}, ${#arr[@]}
```

## Common Tasks

### Adding a New Expansion Type

1. Create an expander class with `__init__(self, shell)` and a domain method:
```python
# In new_expander.py
class NewExpander:
    def __init__(self, shell):
        self.shell = shell

    def expand(self, value: str) -> str:
        # Implement expansion logic
        return expanded_value
```

2. Add to `ExpansionManager.__init__()`:
```python
self.new_expander = NewExpander(shell)
```

3. Integrate into `expand_arguments()` at correct position in order

4. Add tests in `tests/unit/expansion/`

### Adding a Parameter Expansion Operator

1. Edit `parameter_expansion.py`

2. Add operator to the parsing logic

3. Implement the operation in the appropriate method

4. Add tests for the new operator

## Key Implementation Details

### Quote Handling

Different quote types affect expansion:

| Quote Type | Variable Expansion | Command Sub | Glob | Word Split |
|------------|-------------------|-------------|------|------------|
| Unquoted   | Yes               | Yes         | Yes  | Yes        |
| `"double"` | Yes               | Yes         | No   | No         |
| `'single'` | No                | No          | No   | No         |
| `$'ansi'`  | Escape sequences  | No          | No   | No         |

### Array and $@ Expansion in Quotes

Multi-field expansions inside quotes go through two helpers in `manager.py`:

- `_field_expansion_fields(part)` returns the list of fields a part expands
  to (`"$@"`, `"${arr[@]}"`, and parameter ops applied to them — the latter
  via `FieldExpansionMixin.expand_to_fields()` in `fields.py`), or `None`
  for ordinary single-field parts.
- `_expand_at_with_affixes(...)` splices those fields into the word,
  distributing prefix/suffix text onto the first/last field:

```python
# "x$@y" with params (a, b) → ["xa", "by"]
# "$@" with no params → nothing
```

### Pattern and Replacement Operand Expansion

Operands of pattern operators (`${VAR#pat}`, `${VAR/pat/repl}`, case ops)
are expanded in `operands.py` before matching: variables/quotes inside the
operand are processed, and text that must stay literal is escaped with
`glob_escape()` so it cannot act as a glob. Replacement operands become a
list of literal strings interleaved with the `PATSUB_MATCH` sentinel
(defined in `parameter_expansion.py`), which stands for the matched text —
this is how a literal `&` in a patsub replacement works.

### Indirection: `${!name}`

`variable.py` implements `${!name}` via `_expand_indirect()` /
`_resolve_indirect_target()`: the value of `name` (or a nameref's target)
names the parameter actually expanded. `${!name<op>...}` resolves the
indirection first, then applies the operator. `${!prefix*}`/`${!arr[@]}`
forms are dispatched separately (name listing / array keys).

### Array Subscript Arithmetic

`ArrayOpsMixin._eval_array_index()` (`arrays.py`) evaluates indexed-array
subscripts as full arithmetic expressions (`${arr[i+1]}`), so subscript
errors surface as arithmetic errors.

### IFS Word Splitting

```python
def _split_with_ifs(self, text: Optional[str], quote_type: Optional[str]) -> List[str]:
    if quote_type is not None:
        return [text]  # Quoted - no splitting

    ifs = self.state.get_variable('IFS', ' \t\n')
    return self.word_splitter.split(text, ifs)
```

Splitting a composite word is part-aware: `_split_part_fields(parts,
splittable_idx)` in `manager.py` splits ONLY the parts that came from
unquoted expansions, using `WordSplitter.split_with_edges()` (which also
reports whether the text had leading/trailing IFS) so quoted text joins
correctly onto adjacent fields (`a"$x"b`).

### Command Substitution

```python
class CommandSubstitution:
    def execute(self, cmd_sub: str) -> str:
        # Extract command from $(...) or `...`
        # Create subprocess to execute
        # Capture and return stdout
        # Strip trailing newlines (POSIX behavior)
```

## Testing

```bash
# Run expansion unit tests
python -m pytest tests/unit/expansion/ -v

# Test specific expansion type
python -m pytest tests/unit/expansion/test_variable_expansion_simple.py -v

# Debug expansion
python -m psh --debug-expansion -c "echo $HOME"
python -m psh --debug-expansion-detail -c 'echo "${arr[@]}"'
```

## Common Pitfalls

1. **Expansion Order Matters**: Variables must be expanded before command substitution results are word-split.

2. **Quote Preservation**: Track quote types carefully - they affect which expansions occur.

3. **Empty Expansions**: An unset variable in `"$var"` produces empty string, but unquoted `$var` produces nothing (no argument).

4. **Array vs Scalar**: `${arr[@]}` expands to multiple words, `${arr[*]}` joins with first IFS character.

5. **Nested Expansions**: Command substitution can contain variable expansions: `$(echo $HOME)`

6. **IFS Edge Cases**: Empty IFS means no word splitting; unset IFS uses default `" \t\n"`.

7. **Assignment Word Splitting**: Only declaration-builtin arguments
   (`declare foo=$x`) suppress word splitting of assignment-shaped words;
   ordinary command arguments (`printf '%s' foo=$x`) split like bash.

## Debug Options

```bash
python -m psh --debug-expansion        # Show pre/post expansion
python -m psh --debug-expansion-detail # Trace each expansion step
```

Output example:
```
[EXPANSION] Expanding Word AST command: ['echo', '$HOME', '*.txt']
[EXPANSION] Word AST Result: ['echo', '/Users/user', 'a.txt', 'b.txt']
```

## Integration Points

### With Shell State (`psh/core/state.py`)

- Variables: `shell.state.get_variable()`, `shell.state.set_variable()`
- Special variables: `shell.state.get_special_variable()`
- Positional params: `shell.state.positional_params`
- Options: `shell.state.options.get('noglob')`, etc.

### With Executor (`psh/executor/`)

- Called from `CommandExecutor` before command execution
- Process substitutions set up via `IOManager`

### With Parser (`psh/parser/`)

- Parser always builds Word AST nodes (`command.words`) with per-part quote context
- `words` is the SOLE argument metadata representation — the legacy
  `arg_types`/`quote_types` lists were removed in v0.120
- `ExpansionEvaluator` evaluates Word AST expansion nodes
- `WordBuilder` (in `parser/recursive_descent/support/`) constructs Word nodes from tokens

### With Arithmetic (`psh/expansion/arithmetic.py`)

- `execute_arithmetic_expansion()` calls `evaluate_arithmetic()`
- `evaluate_arithmetic()` expands $-constructs itself (one verbatim pass
  via `expand_string_variables()` → `_expand_one_dollar`); substituted
  values are NOT rescanned, and bare names are resolved by the evaluator
