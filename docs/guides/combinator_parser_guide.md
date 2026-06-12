# Combinator Parser Guide

> **Status: Educational only (project decision 2026-06-12).**  This is not
> the production parser and is outside the production quality bar.  The
> recursive descent parser in `recursive_descent/` handles all shell input
> in normal operation.  There is no plan to converge the two implementations
> or to replace the recursive descent parser.  The combinator parser may lag
> behind on edge-case fixes and new features; its documented gaps are not
> tracked as defects.  The decision may be revisited if dedicated time
> becomes available.

## What This Is

The combinator parser (`psh/parser/combinators/`) is an experimental,
alternative parser implementation that uses functional composition instead
of recursive descent.  It parses the same shell grammar as the main
recursive descent parser but demonstrates a fundamentally different
parsing paradigm.

This is an educational counterpoint: the recursive descent parser uses
mutable state and imperative control flow, while the combinator parser
uses immutable position passing and composable parser functions.

## How to Select It

From inside psh:

```
parser-select combinator
```

Aliases: `pc`, `functional`.

To switch back:

```
parser-select recursive_descent
```

Aliases: `rd`, `recursive`, `default`.

Child shells inherit the active parser from their parent.

## Core Concepts

### Parser\[T\]

A parser is a function `(tokens, position) -> ParseResult[T]`.  It either
succeeds (returning a value and a new position) or fails (returning an
error message).

```python
@dataclass
class ParseResult(Generic[T]):
    success: bool
    value: Optional[T]
    remaining: List[Token]
    position: int
    error: Optional[str]
```

### Combinators

Small functions that build complex parsers from simple ones:

| Combinator | Purpose |
|---|---|
| `token(type)` | Match a single token by type |
| `keyword(kw)` | Match a keyword token |
| `literal(lit)` | Match a token with a specific value |
| `many(p)` | Zero or more |
| `many1(p)` | One or more |
| `optional(p)` | Zero or one |
| `sequence(p1, p2, ...)` | All in order |
| `separated_by(p, sep)` | Items with separator between |
| `between(open, close, p)` | Content between delimiters |
| `try_parse(p)` | Backtracking on failure |
| `lazy(factory)` | Deferred construction for recursion |
| `fail_with(msg)` | Always fail with message |

### Composition

Parsers compose through methods:

```python
# Transform the result
word_parser = token("WORD").map(lambda t: t.value)

# Sequence: parse A then B
assignment = variable.then(equals).then(value)

# Alternative: try A, fall back to B
command = control_structure.or_else(simple_command)
```

### ForwardParser

Handles circular dependencies between grammar rules. Declare first,
define later:

```python
statement = ForwardParser()        # placeholder
command_list = many(statement)     # uses placeholder
statement.set(and_or_list)         # resolve after all parsers exist
```

## Module Structure

```
combinators/
  core.py               - Parser[T], ParseResult, combinator primitives
  tokens.py             - Token matchers (word, keyword, operator, etc.)
  expansions.py         - $var, ${...}, $(...), $(()), Word AST building
  commands.py           - Simple commands, pipelines, and-or lists
  control_structures.py - if, while, for, case, select, functions, groups
  special_commands.py   - (( )), [[ ]], arrays, process substitution
  heredoc_processor.py  - Post-parse heredoc content population
  parser.py             - ParserCombinatorShellParser integration class
```

## Feature Coverage

### Supported

| Feature | Combinator module | RD equivalent |
|---|---|---|
| Simple commands | commands.py | parsers/commands.py |
| Pipelines | commands.py | parsers/commands.py |
| And-or lists (`&&`/`||`) | commands.py | parsers/statements.py |
| If/elif/else/fi | control_structures.py | parsers/control_structures.py |
| While/until loops | control_structures.py | parsers/control_structures.py |
| For loops (traditional) | control_structures.py | parsers/control_structures.py |
| C-style for loops | control_structures.py | parsers/control_structures.py |
| Case/esac | control_structures.py | parsers/control_structures.py |
| Select loops | control_structures.py | parsers/control_structures.py |
| Function definitions | control_structures.py | parsers/functions.py |
| Subshell groups `()` | control_structures.py | parsers/commands.py |
| Brace groups `{}` | control_structures.py | parsers/commands.py |
| Break/continue | control_structures.py | parsers/control_structures.py |
| Arithmetic `(( ))` | special_commands.py | parsers/arithmetic.py |
| Enhanced tests `[[ ]]` | special_commands.py | parsers/tests.py |
| Array operations | special_commands.py | parsers/arrays.py |
| Process substitution | special_commands.py | parsers/commands.py |
| Variable expansion | expansions.py | (handled by lexer) |
| Command substitution | expansions.py | (handled by lexer) |
| Parameter expansion | expansions.py | (handled by lexer) |
| Arithmetic expansion | expansions.py | (handled by lexer) |
| I/O redirections | commands.py | parsers/redirections.py |
| Heredoc post-processing | heredoc_processor.py | support/utils.py |
| Word AST construction | expansions.py | support/word_builder.py |

### Limitations

- Arithmetic and test expressions are collected as strings rather than
  parsed into expression trees (evaluation happens at execution time).
- Complex compound test expressions (`[[ a && b ]]`) use simplified parsing.
- Some array syntax edge cases may not be detected.

## How to Read the Code

**Recommended reading order:**

1. **core.py** -- Start here. Read `ParseResult`, `Parser`, then the
   combinator functions (`token`, `many`, `sequence`, `optional`,
   `or_else`). This is the foundation everything else builds on.

2. **tokens.py** -- Token-level matchers built from `core.token()`.
   Notice how keywords, operators, and delimiters are each just a
   `token(TYPE)` call.

3. **commands.py** -- See how simple commands are built by composing
   token parsers with `many()` and `optional()`.  Then see how
   pipelines chain commands with `separated_by()`.

4. **control_structures.py** -- The largest module. See how `if_statement`
   uses `sequence()` to parse `if COND; then BODY; fi` by composing
   keyword parsers with statement list parsers.

5. **special_commands.py** -- Arithmetic and test expressions.

6. **parser.py** -- The integration class that wires all modules together
   and exposes `parse()`.

## Key Differences from Recursive Descent

| Aspect | Recursive Descent | Combinator |
|---|---|---|
| State | Mutable `ParserContext` | Immutable position passing |
| Control flow | Imperative methods | Functional composition |
| Error handling | Rich `ErrorContext` with suggestions | Simple error strings |
| Backtracking | Limited (manual save/restore) | Full (via `or_else` / `try_parse`) |
| Circular deps | Direct method calls | `ForwardParser` + wiring phase |
| Code style | Classes with methods | Functions returning `Parser[T]` |
| Performance | Single pass, no backtracking overhead | May re-parse on alternatives |
| Debugging | `--debug-ast`, `--debug-tokens` | `explain_parse()` method |

## Running Both Parsers

```bash
# Default: recursive descent
python -m psh -c 'echo hello'

# Switch to combinator inside a session
python -m psh
psh> parser-select combinator
psh> echo hello    # now uses combinator parser
psh> parser-select rd
psh> echo hello    # back to recursive descent
```

## Testing

Parity tests verify both parsers produce equivalent ASTs:

```bash
python -m pytest tests/test_parser_parity_basic.py -v
```

Combinator-specific tests:

```bash
python -m pytest tests/unit/parser/combinators/ -v
```
