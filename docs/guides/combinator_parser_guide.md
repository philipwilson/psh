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

A parser is a function `(tokens, position) -> ParseResult[T]` wrapped in a
`Parser` object.  It either succeeds (returning a value and a new position)
or fails (returning the position where the failure was observed plus an
error message).

```python
@dataclass
class ParseResult(Generic[T]):
    success: bool               # the discriminant
    value: Optional[T]          # the parsed value (on success)
    position: int               # position reached / where the failure was seen
    error: Optional[str]        # message (on failure)
    committed: bool             # cut flag — a committed failure is not retried by or_else
    expected: Tuple[str, ...]   # labels of what would have allowed progress
```

Prefer the `ParseSuccess(value, position)` / `ParseFailure(position, error, ...)`
constructors in new code and branch on `result.success`.

### The live algebra

The grammar is built from a deliberately small set of primitives.  A few are
*functions* that return a `Parser`; the rest are *methods* on `Parser`:

| Primitive | Kind | Purpose |
|---|---|---|
| `token(type)` | function | Match a single token by `TokenType` name |
| `keyword(kw)` | function | Match a keyword token |
| `many(p)` | function | Zero or more |
| `many1(p)` | function | One or more |
| `optional(p)` | function | Zero or one |
| `fail_with(msg)` | function | Always fail with a message (used to seed recursion slots) |
| `p.or_else(q)` | method | Ordered choice with a cut (a *committed* failure is not retried) |
| `p.map(f)` | method | Transform the successful value |
| `p.then(q)` | method | Sequence `p` then `q`, returning a `(a, b)` tuple |

That is the whole toolkit.  There is **no** `sequence`/`separated_by`/`between`/
`lazy`/`try_parse`/`ForwardParser` layer — the shell grammar is context-sensitive
enough that most productions are written as explicit closures (see below), so a
generic applicative/monadic combinator library would only get in the way.  Longer
sequences and separator-delimited lists are hand-rolled `while` loops over
`position` inside a `def parse_x(tokens, pos)` closure wrapped in `Parser(...)`.

### Composition

Parsers compose through the `Parser` methods and through hand-written closures:

```python
# Transform the result
word_parser = token("WORD").map(lambda t: t.value)

# Ordered choice: try A, fall back to B (this is the workhorse)
command = control_structure.or_else(simple_command)

# A production that needs real bookkeeping is a closure over `position`:
def parse_pipeline(tokens, pos):
    result = element.parse(tokens, pos)
    if not result.success:
        return result
    commands = [result.value]
    pos = result.position
    while pos < len(tokens) and tokens[pos].type.name in ('PIPE', 'PIPE_AND'):
        ...  # consume the operator, parse the next element, extend `commands`
    return ParseSuccess(Pipeline(commands), pos)

pipeline = Parser(parse_pipeline)
```

### Recursion via mutable slots

Grammar rules are mutually recursive (a command body contains statements which
contain commands).  Rather than a forward-declaration wrapper, the combinator
parser holds the recursive references in mutable **slots** that the parse
closures read *at parse time*:

```python
# built once, reads self._pipeline_element inside its closure
self.pipeline = self._build_pipeline_parser()
self._pipeline_element = self.simple_command          # placeholder
...
# during the wiring phase, once every module exists:
self.set_command_parser(control_structure
                        .or_else(special_command)
                        .or_else(simple_command))     # fills the slot
```

Because the closure reads the slot when it runs, filling it later takes effect
without rebuilding `pipeline` (see `commands/__init__.py::_initialize_parsers`
and `parser.py::_build_complete_parser`).

## Module Structure

```
combinators/
  core.py               - Parser[T], ParseResult, the live algebra primitives
  tokens.py             - Token matchers (word, keyword, operator, etc.)
  expansions.py         - $var, ${...}, $(...), $(()), Word AST building
  arrays.py             - array assignment / initialization parsing
  commands/             - simple commands, pipelines, and-or lists, statement lists
  control_structures/   - if/case (conditionals.py), loops (loops.py),
                          functions & groups (structures.py)
  special_commands.py   - (( )), [[ ]], process substitution
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
| Heredoc attachment (at construction, id-keyed) | commands/, redirections.py | parsers/redirections.py |
| Word AST construction | expansions.py | support/word_builder.py |

### Limitations

- Arithmetic and test expressions are collected as strings rather than
  parsed into expression trees (evaluation happens at execution time).
- Complex compound test expressions (`[[ a && b ]]`) use simplified parsing.
- Some array syntax edge cases may not be detected.

## How to Read the Code

**Recommended reading order:**

1. **core.py** -- Start here. Read `ParseResult`, `Parser`, then the live
   algebra (`token`, `many`, `many1`, `optional`, `fail_with`, and the
   `Parser.or_else` / `.map` / `.then` methods). This is the whole foundation
   everything else builds on.

2. **tokens.py** -- Token-level matchers built from `core.token()`.
   Notice how keywords, operators, and delimiters are each just a
   `token(TYPE)` call.

3. **commands/** -- See how simple commands are built by composing token
   parsers with `many()` and `optional()`.  Then see how the pipeline parser
   (`commands/pipelines.py`) chains commands with a hand-rolled `while` loop
   over `position` — not a generic separator combinator.

4. **control_structures/** -- The largest area. See how the `if`/`while`/`for`
   parsers are written as `def parse_x(tokens, pos)` closures that consume the
   keyword, parse the condition/body via the shared `build_statement_list`
   engine, and expect the closing keyword — imperative bookkeeping inside a
   composable `Parser`.

5. **special_commands.py** -- Arithmetic and test expressions.

6. **parser.py** -- The integration class that wires all modules together
   (filling the recursion slots) and exposes `parse()`.

## Key Differences from Recursive Descent

| Aspect | Recursive Descent | Combinator |
|---|---|---|
| State | Mutable `ParserContext` | Immutable position passing |
| Control flow | Imperative methods | Functional composition |
| Error handling | Rich `ErrorContext` with suggestions | Simple error strings |
| Backtracking | Limited (manual save/restore) | Ordered choice via `or_else` (position is re-passed, so a failed alternative naturally backtracks) |
| Circular deps | Direct method calls | Mutable recursion slots filled in a wiring phase |
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
