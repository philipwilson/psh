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
| `word_expansion_types.py` | The expansion data model: `WordExpansionPolicy` + named policy instances (`COMMAND_ARGUMENT`, `LOOP_ITEM`, ...), and the field IR `FieldRun` (`Protection`/`Split`), `ExpandedField`, `ExpandedWord` |
| `evaluator.py` | `ExpansionEvaluator` - evaluates expansion AST nodes |
| `param_parser.py` | THE `${...}` content parser (`parse_parameter_expansion()`) — the single grammar shared by WordBuilder (parse time) and `expand_variable` (string contexts); module docstring is the grammar reference |
| `variable.py` | `VariableExpander` - dispatch, special variables, `${!name}` indirection |
| `arrays.py` | `ArrayOpsMixin` - `${arr[i]}`, `${arr[@]}` access (keying via `subscript.py`) |
| `subscript.py` | `SubscriptEvaluator` - THE one array-subscript keying authority (indexed arithmetic vs associative string key, decided by target kind; campaign W2) |
| `operators.py` | `OperatorOpsMixin` - `${VAR:-...}`, `${VAR#...}`, `${VAR/p/r}`, case ops |
| `operands.py` | `OperandOpsMixin` - expands pattern/replacement operands, `glob_escape()` |
| `fields.py` | `FieldExpansionMixin` - `expand_to_fields()` for multi-field `$@`/array results |
| `pattern.py` | `match_shell_pattern()` - the thin full-match facade for `case`/`[[ == ]]`/name filters: `PatternCompiler.compile(pattern).full_match(...)` — plain AND extglob route through the one engine (campaign W3; no regex path) |
| `pattern_engine.py` | THE compiled shell-pattern engine: `PatternCompiler.compile`(raw string)/`compile_protected`(protection runs) → `CompiledPattern` with the FOUR relations (`full_match`/`matching_ends`/`matching_starts`/`span_at`+`matching_spans`); iterative stars + literal chains (two-pointer boolean / forward position-set DP — star count never consumes recursion frames), recursion ONLY for extglob nesting depth; `MatchProfile` (for_pathname, ic). Legacy `compile_pattern`/`reachable_ends`/`fullmatch`/`match_at`/`count_states` kept (see "Pattern matching engine" below) |
| `extglob.py` | Extglob scanning primitives (`_find_matching_paren`, `_split_pattern_list`, `_bracket_end`, `_bracket_match`), locale-aware bracket membership (`_bracket_to_regex`), and thin `extglob_fullmatch`/`extglob_match_at`/`_extglob_consume` that delegate to `pattern_engine`. (`glob_to_regex_body`/`extglob_to_regex`/`_convert_pattern` are production-DEAD after W3 — the regex matching path was retired; kept only as test oracles pending a census deletion) |
| `parameter_expansion.py` | `ParameterExpansionOps` - string ops behind the operators (incl. `PATSUB_MATCH`); the engine, not the `ParameterExpansion` AST node |
| `command_sub.py` | `CommandSubstitutionExecutor` - runs `$(cmd)` and `` `cmd` ``; the engine, not the `CommandSubstitution` AST node |
| `tilde.py` | `TildeExpander` - handles `~` and `~user` |
| `glob.py` | `GlobExpander` - pathname expansion (wildcards) |
| `word_splitter.py` | `WordSplitter` - splits on IFS (`split()`, `split_with_edges()`) |
| `arithmetic/` | Arithmetic package: tokenizer/parser/evaluator (`evaluate_arithmetic()`); decomposed from `arithmetic.py` into `tokens.py`/`tokenizer.py`/`nodes.py`/`parser.py`/`evaluator.py`/`errors.py` |
| `brace_expansion.py` | `BraceExpander` - textual per-word `{a,b}`, `{1..5}` |
| `brace_expansion_words.py` | `WordBraceExpander` - applies `BraceExpander` to a parsed `Word` at the Word stage (`Word` → `List[Word]`, reading the live `braceexpand` option) |
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
        self.command_sub = CommandSubstitutionExecutor(shell)
        self.tilde_expander = TildeExpander(shell)
        self.glob_expander = GlobExpander(shell)
        self.word_splitter = WordSplitter()

        self.word_expander = WordExpander(self)

    def expand_arguments(self, command: SimpleCommand) -> List[str]:
        """Expand all arguments using Word AST nodes."""
        # picks COMMAND_ARGUMENT or DECLARATION_ASSIGNMENT per word, then
        # word_expander.expand_to_word(word, policy) + .materialize(...)
```

### 2. Word AST Expansion (Primary Path)

Arguments are expanded using Word AST nodes. Each `Word` contains
`LiteralPart` and `ExpansionPart` nodes with per-part quote context. The field
engine is two methods in `word_expander.py`:

- `WordExpander.expand_to_word(word, policy)` walks the parts (per-part `quoted`
  / `quote_char`) and builds an `ExpandedWord` — zero or more explicit
  `ExpandedField`s, each an ordered run of homogeneous-protection `FieldRun`s.
  A multi-field `$@`/`[@]` SPLICES through the same algebra (no shortcut): the
  first field attaches to the open field, the middle fields commit, the last
  becomes the new open field, so `"$@"$x` lands the fragment in the right field
  and still splits (`#20 H5`). Field splitting runs here for split policies.
- `WordExpander.materialize(expanded_word, policy)` is the SOLE terminal
  boundary that turns the field IR back into `argv` strings: it pathname-expands
  a field only when an ACTIVE run carries a live glob/extglob metacharacter,
  compiling the pattern from the runs so a PROTECTED (quoted/escaped)
  metacharacter stays literal beside an active one (`#20 H6`), else joins.

The `WordExpansionPolicy` names what the context permits (axes: `split`, `glob`,
`assignment_tilde` — named instances `COMMAND_ARGUMENT`, `LOOP_ITEM`,
`DECLARATION_ASSIGNMENT`, `ARRAY_INIT_ELEMENT`, `ASSOC_INIT_ELEMENT`,
`CASE_SUBJECT`). The three funnels in `manager.py` (`expand_arguments`,
`expand_word_to_fields`, `expand_word_as_subject`) are the only callers of the
pair — the grep-verified chokepoint guarded by
`tests/unit/expansion/test_field_ir_guards.py`.

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
`VariableExpander`. For `ParameterExpansion` nodes it resolves straight from
the pre-parsed AST components — `param_parser.py` fully classifies every form
at parse time, so **a ParameterExpansion is never re-parsed at runtime**: an
operator form goes to `expand_parameter_direct(op, name, operand)`, and a plain
(operator-less) form to `_resolve_plain_parameter(name)` (the same name-only
resolution `expand_variable`'s braced path uses — no second `${...}` parse, no
double bad-substitution check). `ArithmeticExpansion` likewise resolves from
the raw expression text via `arithmetic_expansion_value(expr)` (no `$(( ))`
wrap/unwrap round-trip):

```python
class ExpansionEvaluator:
    def evaluate(self, expansion: Expansion) -> str:
        # VariableExpansion → expand_variable("$name")  (string entry point)
        # ParameterExpansion → expand_parameter_direct(op, name, operand)  [operator]
        #                    | _resolve_plain_parameter(name)              [plain]
        # CommandSubstitution → command_sub.execute("$(cmd)")
        # ArithmeticExpansion → arithmetic_expansion_value(expr)
```

## Expansion Order (POSIX)

The `expand_arguments()` method processes expansions in this order:

```
1. Brace Expansion      {a,b,c}         → WordBraceExpander (Word stage, per command,
                                          gated by the LIVE braceexpand option — set -B/+B;
                                          Word → List[Word] before variable expansion)
2. Tilde Expansion      ~, ~user        → TildeExpander
3. Variable Expansion   $VAR, ${VAR}    → VariableExpander
4. Command Substitution $(cmd), `cmd`   → CommandSubstitutionExecutor
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

### Array and $@ Expansion (the field-splicing algebra)

Multi-field expansions (`$@`, `${arr[@]}`, parameter ops applied to them),
quoted OR unquoted, route through ONE algebra in `word_expander.py`:

- `_field_expansion_fields(part)` returns the list of fields a part expands
  to (`"$@"`, `"${arr[@]}"`, and parameter ops applied to them — the latter
  via `FieldExpansionMixin.expand_to_fields()` in `fields.py`), or `None`
  for ordinary single-field parts (including `$*`/`${a[*]}`, which are scalar).
- `_FieldBuilder.splice(fields)` distributes those fields with the splicing
  algebra: the first field attaches to the open field, the middle fields commit
  as their own fields, and the last field becomes the new open field — so an
  affix or an adjacent unquoted fragment continues the right field (`"x$@y"`
  with `(a, b)` → `xa`, `by`; empty `$@` between affixes → one field). There is
  no `$@` shortcut: no walker returns `str | list[str]` and no join happens
  before field splitting and pathname generation (`#20 H5`).

### Pattern and Replacement Operand Expansion

Operands of pattern operators (`${VAR#pat}`, `${VAR/pat/repl}`, case ops)
are expanded in `operands.py` before matching: variables/quotes inside the
operand are processed, and text that must stay literal is escaped with
`glob_escape()` so it cannot act as a glob. Replacement operands become a
list of literal strings interleaved with the `PATSUB_MATCH` sentinel
(defined in `parameter_expansion.py`), which stands for the matched text —
this is how a literal `&` in a patsub replacement works.

### Pattern matching engine (`pattern_engine.py`) — the ONE iterative relation

One compiled representation matches shell patterns for **every** consumer —
`case`, `[[ == ]]`, `${var#/%/##/%%}` removal, `${var/}` substitution, case
modification, pathname components, and name filters (`HISTIGNORE`, `print -m`,
`help`) — so glob/extglob semantics cannot drift between them (campaign W3,
#20 H7). There is no parallel regex matching path.

- **Compile once, two entries.** `PatternCompiler.compile(pattern)` (a raw
  string; `\` = escape — name filters) and `PatternCompiler.compile_protected(
  parts)` (per-character `(text, protected)` runs, consumed DIRECTLY via the one
  canonical encoder `runs_to_pattern_string`) both build a `CompiledPattern`
  wrapping a small AST (`Sequence` of `Literal`/`AnyChar`/`Star`/`Bracket`/
  `Extglob`). `compile_cached` memoizes. Parsing reuses `extglob.py`'s scanning
  primitives.
- **The four relations** on `CompiledPattern` are exactly what consumers need:
  `full_match(text)` (case/`[[`/name filter/one pathname entry/one case-mod
  char), `matching_ends(text, start)` (prefix removal — `#`=min, `##`=max),
  `matching_starts(text, end)` (suffix removal — `%`=max start, `%%`=min start),
  and `span_at(text, pos)` / `matching_spans(text)` (leftmost-longest
  substitution). `parameter_expansion.py` calls these directly — no operator
  builds a regex or does its own anchoring.
- **Stars and literal chains are ITERATIVE; recursion only for extglob
  nesting.** The boolean full match for extglob-free sequences (every plain
  glob) is the classic two-pointer backtrack — zero recursion, one backtrack
  point per star — and the reachable-end set is a forward position-set DP that
  processes each element once (a `Star` becomes an interval union). Star and
  literal COUNT therefore never consume recursion frames (a 50,000-star
  pattern matches at any recursion limit — #20 H7-b + the W3 bounce ruling),
  and the DP is its own memoization, so adversarial repetition (`*a*a…*b`,
  `*(a|aa)c`) stays `O(nodes·positions)`, never exponential (#20 H7-c). The
  ONLY recursion is into extglob alternatives — bounded by extglob NESTING
  depth, a compile-time structural property; at the bound psh raises
  `RecursionError` as an expected shell error (probed: bash 5.2 SEGFAULTS at
  depth 30k where psh fails cleanly — pinned in `test_pattern_relations.py` +
  the nightly benchmark tier).
- **Policies stay outside the matcher** as a typed `MatchProfile`
  (`for_pathname`, `ic`); bracket membership and case folding delegate to the
  shared, locale-aware `extglob._bracket_match`/`_eq`, so POSIX `[:class:]`
  semantics are preserved exactly. dotglob/globstar/nullglob/failglob/symlink
  and slash-component/leading-dot policy layer OVER the engine in `glob.py`,
  never inside the matcher.
- **Protection is consumed directly** (`compile_protected`): a PROTECTED
  (quoted/escaped) character is a literal char / bracket member wherever it
  lands — so a quoted class-special char inside an ACTIVE bracket stays a
  literal member (`[a"-"c]` = `{a,-,c}`, not the range `a-c`; #20 H7 carry-2).
  This retired both former interim encodings (`_pattern_from_runs`
  bracket-escaping and `operands.glob_escape`'s incomplete set).

Complexity is guarded deterministically by `count_states()` (see
`tests/unit/expansion/test_pattern_engine_matcher.py` and
`test_pattern_relations.py`); behavior is locked against live bash in
`test_pattern_engine_differential.py`.

### Indirection: `${!name}`

`variable.py` implements `${!name}` via `_expand_indirect()` /
`_resolve_indirect_target()`: the value of `name` (or a nameref's target)
names the parameter actually expanded. `${!name<op>...}` resolves the
indirection first, then applies the operator. `${!prefix*}`/`${!arr[@]}`
forms are dispatched separately (name listing / array keys).

### Array Subscript Keying — ONE authority

`SubscriptEvaluator` (`subscript.py`, on `shell.expansion_manager.subscript`)
is the single interpreter for array subscripts (campaign W2; r21's signature
finding was six inconsistent implementations). The invariant is
**target kind BEFORE interpretation**: the caller resolves the DECLARED
variable's kind (undeclared defaults to indexed; quoting never infers
associative), then calls `associative_key()` (one word/quote expansion under
assignment-value semantics — composite quoting, `$'...'` decode, no
split/glob, bare names literal) or `indexed_index()` (expand, then lazily
arithmetic-evaluate — `${arr[i+1]}`; failures are fatal arithmetic errors).
Read/write/is-set/unset/`test -v`/arithmetic/initializer all route here
(BOTH arms — `test -v`'s indexed arm included, bounce-fix 2026-07-19) —
the caller sets are pinned by
`tests/unit/tooling/test_subscript_authority_guard.py`. `evaluate(raw, kind,
use)` is the use-aware dispatch: `SubscriptUse.TEST_V`/`UNSET` return `None`
for an (expanded-)empty indexed subscript (bash: silently-unset `-v`, no-op
`unset`), while read/write address index 0. In ARITHMETIC context the
subscript is a verbatim `SUBSCRIPT` token (`arithmetic/
tokenizer.py#_read_subscript`) and the assoc rule runs with
`expand_dollar=False` (the arith pre-pass already substituted `$`-constructs;
bash never rescans). `_eval_array_index()` remains as a thin adapter.

### IFS Word Splitting and per-character protection

The field IR carries two facts per run through splitting and globbing:
`FieldRun.protection` (`ACTIVE`/`PROTECTED`) and `FieldRun.split`
(`NEVER`/`IFS_ELIGIBLE`). `WordExpander._field_split` splits each committed
field (a `$@` boundary) independently: only `IFS_ELIGIBLE` runs (unquoted
expansion text) produce field boundaries, `NEVER` runs edge-join, and an
all-eligible field that splits to nothing elides (`$unset` alone → zero fields).
It uses `WordSplitter.split_with_edges()` so leading/trailing IFS is reported
and quoted text joins correctly onto adjacent fields (`a"$x"b`). Split pieces
inherit the run's protection, so materialization still sees it.

Pathname generation is per-character: `WordExpander._pattern_from_runs` compiles
one pattern from a field's runs through the ONE canonical protection encoder
(`pattern_engine.runs_to_pattern_string`): ACTIVE run text passes raw (its
metacharacters act), a PROTECTED run's glob-significant characters are
`\`-escaped so they are literal wherever they land — top level OR inside an
active bracket (`"*"*` → `\**`; `[a"-"c]` → `[a\-c]` = `{a,-,c}`; `#20 H6`+
carry-2). `glob.GlobExpander.expand` matches the result through the same engine
(`\` = escape; `glob.py#_component_matcher`), and an ACTIVE value backslash is
doubled by the encoder so it stays literal — one protection semantics shared
with the `${...}` operand path. `_unquoted_literal_runs` splits an unquoted
literal into protection runs during escape processing (`a\*b*` → ACTIVE `a`,
PROTECTED `*`, ACTIVE `b*`).

### Command Substitution

```python
class CommandSubstitutionExecutor:
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
