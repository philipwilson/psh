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
| `manager.py` | `ExpansionManager` - orchestrator: owns the sub-expanders, declaration-builtin recognition, public entry points |
| `word_expander.py` | `WordExpander` - THE Word expansion engine (part walkers, IFS split, glob, escapes) |
| `word_expansion_types.py` | The expansion data model: `WordExpansionPolicy` + named policy instances (`COMMAND_ARGUMENT`, `LOOP_ITEM`, ...), `ExpandedSegment`, `_WalkState` |
| `evaluator.py` | `ExpansionEvaluator` - evaluates expansion AST nodes |
| `param_parser.py` | THE `${...}` content parser (`parse_parameter_expansion()`) — the single grammar shared by WordBuilder (parse time) and `expand_variable` (string contexts); module docstring is the grammar reference |
| `variable.py` | `VariableExpander` - dispatch, special variables, `${!name}` indirection |
| `arrays.py` | `ArrayOpsMixin` - `${arr[i]}`, `${arr[@]}`, `_eval_array_index()` |
| `operators.py` | `OperatorOpsMixin` - `${VAR:-...}`, `${VAR#...}`, `${VAR/p/r}`, case ops |
| `operands.py` | `OperandOpsMixin` - expands pattern/replacement operands, `glob_escape()` |
| `fields.py` | `FieldExpansionMixin` - `expand_to_fields()` for multi-field `$@`/array results |
| `pattern.py` | `match_shell_pattern()` - the consumer-facing dispatch facade: extglob → compiled engine, plain glob → regex; `PatternMatcher` still builds the plain-glob→regex |
| `pattern_engine.py` | THE compiled shell-pattern engine: `compile_pattern()` (parse-once AST) + memoized `reachable_ends`/`fullmatch`/`match_at` (see "Pattern matching engine" below) |
| `extglob.py` | Extglob scanning primitives (`_find_matching_paren`, `_split_pattern_list`, `_bracket_end`, `_bracket_match`), the glob→regex converter (`glob_to_regex_body`), and thin `extglob_fullmatch`/`extglob_match_at`/`_extglob_consume` that delegate to `pattern_engine` |
| `parameter_expansion.py` | `ParameterExpansion` - string ops behind the operators (incl. `PATSUB_MATCH`) |
| `command_sub.py` | `CommandSubstitution` - handles `$(cmd)` and `` `cmd` `` |
| `tilde.py` | `TildeExpander` - handles `~` and `~user` |
| `glob.py` | `GlobExpander` - pathname expansion (wildcards) |
| `word_splitter.py` | `WordSplitter` - splits on IFS (`split()`, `split_with_edges()`) |
| `arithmetic/` | Arithmetic package: tokenizer/parser/evaluator (`evaluate_arithmetic()`); decomposed from `arithmetic.py` into `tokens.py`/`tokenizer.py`/`nodes.py`/`parser.py`/`evaluator.py`/`errors.py` |
| `brace_expansion.py` | `BraceExpander` - textual per-word `{a,b}`, `{1..5}` |
| `brace_expansion_tokens.py` | `TokenBraceExpander` - applies `BraceExpander` across the token stream (post-lex) |
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

        self.word_expander = WordExpander(self)

    def expand_arguments(self, command: SimpleCommand) -> List[str]:
        """Expand all arguments using Word AST nodes."""
        # picks COMMAND_ARGUMENT or DECLARATION_ASSIGNMENT per word,
        # then word_expander.expand(word, policy)
```

### 2. Word AST Expansion (Primary Path)

Arguments are expanded using Word AST nodes. Each `Word` contains
`LiteralPart` and `ExpansionPart` nodes with per-part quote context.
`WordExpander.expand(word, policy)` (in `word_expander.py`) walks the
parts and applies expansions based on each part's `quoted` and
`quote_char` fields; the `WordExpansionPolicy` names what the context
permits (axes: `split`, `glob`, `assignment_tilde` — named instances
`COMMAND_ARGUMENT`, `LOOP_ITEM`, `DECLARATION_ASSIGNMENT`,
`ARRAY_INIT_ELEMENT`, `ASSOC_INIT_ELEMENT`):

```python
def expand(self, word: Word, policy: WordExpansionPolicy) -> Union[str, List[str]]:
    # Single-quoted: return literal
    # Double-quoted: expand vars/commands, no splitting/globbing
    # ANSI-C ($'...'): return literal (lexer already processed escapes)
    # Composite/unquoted: _walk_literal_part/_walk_expansion_part per
    # part on a _WalkState, then _finish() splits and globs per policy
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
  literal command word); the engine never guesses from a `=`. Ordinary
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
operand) components straight from the AST (`param_parser.py` fully
classifies every form at parse time — nothing is re-parsed at runtime):

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
1. Brace Expansion      {a,b,c}         → TokenBraceExpander (token stream, post-lex;
                                          gated by the braceexpand option — set -B/+B,
                                          incl. same-stream `set` toggles)
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

1. Add the operator to the grammar in `param_parser.py` (scan tables +
   module-docstring grammar reference)

2. Implement the application in `operators.py` (`_apply_operator`, and
   `_apply_op_per_element` if it has per-element array semantics), with
   string helpers in `parameter_expansion.py`

3. Add tests for the new operator (including a `test_param_parser.py`
   grammar case; extend the frozen corpus only with bash-verified rows)

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

Multi-field expansions inside quotes go through two helpers in
`word_expander.py`:

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

### Pattern matching engine (`pattern_engine.py`)

One compiled representation matches shell patterns for **all five** consumers —
`case`, `[[ string == pattern ]]`, `${var#/%/##/%%}` removal, `${var/}`
substitution, and pathname extglob components — so glob/extglob semantics cannot
drift between them.

- **Parse once.** `compile_pattern(pattern)` builds a small AST (`Sequence` of
  `Literal` / `AnyChar` / `Star` / `Bracket` / `Extglob`). `compile_cached`
  memoizes it for hot loops. Parsing reuses `extglob.py`'s scanning primitives,
  so bracket/escape/nesting handling matches the rest of the shell.
- **Match with memoization.** `reachable_ends(root, s)` returns every index `k`
  where the pattern fully matches `s[:k]`, evaluating each `(node, position)`
  state at most once. That single reachable-end set serves every consumer:
  full match (`len(s) in ends`), prefix/suffix removal (`min`/`max` and a
  start-index scan), leftmost-longest substitution (`match_at` = `max` ends of
  `s[pos:]`), and pathname-component matching (`for_pathname=True`).
- **Why it exists.** It replaced two backends that were each exponential on a
  different adversarial input (expansion appraisal finding #6): the Python-`re`
  path blew up on ambiguous repetition (`*(a|aa)c`), and the former recursive
  backtracking matcher (`_match_from`, now deleted) blew up on sequential
  optional fan-out (`?(a)…!(z)`). Memoization makes both `O(nodes·positions)`.
- **Policies stay outside the matcher.** `for_pathname` and `nocasematch`
  (`ic`) are match-time arguments; bracket membership and case folding delegate
  to the shared, locale-aware `extglob._bracket_match` / `_eq`, so v0.655 POSIX
  `[:class:]` semantics are preserved exactly. dotglob/globstar/nullglob/
  failglob/symlink handling live in the pathname walker (`glob.py`), not here.
- **Not routed through it:** the plain-glob pathname fast path (`glob.glob` /
  `_compile_component`'s glob→regex conversion). That is a *converter*, not the
  matcher, and is linear — kept on stdlib/regex by design and byte-verified
  against the old `fnmatch` path.

Complexity is guarded deterministically by `count_states()` (see
`tests/unit/expansion/test_pattern_engine_matcher.py`), which also property-tests
`reachable_ends` equality against the former matcher over ~24k random cases.

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
def _split_with_ifs(self, text: Optional[str]) -> List[str]:
    # Only ever called on already-unquoted field text; quoted segments are
    # kept intact by the segment walk before they reach here.
    if text is None:
        return []
    ifs = self.state.get_variable('IFS', ' \t\n')
    return self.word_splitter.split(text, ifs)
```

Splitting a composite word is segment-aware. The walk builds a list of
`ExpandedSegment`s (`text`, `quoted`, `splittable`, `glob_eligible`); the
field-splitting pass `_field_split_pass(segments)` in `word_expander.py`
splits ONLY the segments that came from unquoted expansions
(`segment.splittable`), using `WordSplitter.split_with_edges()` (which also
reports whether the text had leading/trailing IFS) so quoted text joins
correctly onto adjacent fields (`a"$x"b`). `_finish()` runs three explicit
passes over the segment list: field-split → glob (`_glob_pass`) → join.

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

### With Arithmetic (`psh/expansion/arithmetic/`)

- `execute_arithmetic_expansion()` calls `evaluate_arithmetic()`
- `evaluate_arithmetic()` expands $-constructs itself (one verbatim pass
  via `expand_string_variables()` → `_expand_one_dollar`); substituted
  values are NOT rescanned, and bare names are resolved by the evaluator
