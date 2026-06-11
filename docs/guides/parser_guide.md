# PSH Parser: Programmer's Guide

> **Note (2026-06-11):** This guide describes the tree as of ~v0.27x, before
> the v0.285 module relocation and subsequent cleanups. In particular it
> describes parser configuration machinery that has since been removed (the `PERMISSIVE`/`EDUCATIONAL` parsing modes, the `COLLECT`/`RECOVER` error-handling modes, and `parse_with_error_collection`).
> See the subsystem CLAUDE.md files for current structure.

This guide covers the parser package in detail: its external API, internal
architecture, and the responsibilities of every source file.  It is aimed at
developers who need to modify the parser, add new syntax, or understand how a
token stream becomes an AST.

## 1. What the Parser Does

The parser converts a flat list of `Token` objects (produced by the lexer)
into an Abstract Syntax Tree (AST).  The AST is a hierarchy of dataclass
nodes defined in `psh/ast_nodes.py` that represents the structure of a shell
command: commands, pipelines, control flow, redirections, function
definitions, and so on.

The parser does **not** expand variables, execute commands, or perform I/O.
Its output is consumed by the executor's visitor, which walks the AST and
carries out the actual work.

## 2. External API

The public interface is defined in `psh/parser/__init__.py`.  The declared
`__all__` contains five items: `parse`, `parse_with_heredocs`, `Parser`,
`ParserConfig`, and `ParseError`.  See `docs/guides/parser_public_api.md`
for full signature documentation and API tiers.

### 2.1 `parse()`

```python
from psh.parser import parse

ast = parse(tokens, config=None)
```

Parse a token list into an AST.  Returns a `TopLevel` node (which may be
simplified to a `CommandList` for single-statement input).

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `tokens` | &mdash; | `List[Token]` from the lexer. |
| `config` | `None` | Optional `ParserConfig`.  When `None`, a default bash-compatible config is used. |

### 2.2 `parse_with_heredocs()`

```python
from psh.parser import parse_with_heredocs

ast = parse_with_heredocs(tokens, heredoc_map)
```

Parse tokens that were produced by `tokenize_with_heredocs()`.  The
`heredoc_map` (a dict mapping delimiter strings to content dicts) is used to
populate `Redirect` nodes with their heredoc bodies.

### 2.3 `ParserConfig`

Configuration dataclass in `psh/parser/config.py` with 14 fields.

Key fields:

| Field | Default | Meaning |
|-------|---------|---------|
| `parsing_mode` | `BASH_COMPAT` | One of `STRICT_POSIX`, `BASH_COMPAT`, `PERMISSIVE`, `EDUCATIONAL`. |
| `error_handling` | `STRICT` | `STRICT` (stop on first error), `COLLECT`, or `RECOVER`. |
| `collect_errors` | `False` | Collect multiple parse errors before reporting. |
| `max_errors` | `10` | Maximum errors to collect. |
| `enable_arithmetic` | `True` | Enable arithmetic expressions. |
| `allow_bash_conditionals` | `True` | Allow `[[ ]]` enhanced tests. |
| `allow_bash_arithmetic` | `True` | Allow `(( ))` arithmetic commands. |
| `enable_validation` | `False` | Run AST validation after parsing. |
| `profile_parsing` | `False` | Collect performance metrics. |

Factory methods: `ParserConfig.strict_posix()`, `.permissive()`.  Use
`.clone(**overrides)` to derive a modified config from an existing one.

### 2.4 `Parser` class

```python
from psh.parser import Parser

parser = Parser(tokens, source_text=None, config=None)
ast = parser.parse()
```

Direct access to the parser for advanced use cases.  Key methods beyond
`parse()`:

| Method | Returns | Description |
|--------|---------|-------------|
| `parse_with_heredocs(heredoc_map)` | AST | Parse and populate heredoc content. |
| `parse_with_error_collection()` | `MultiErrorParseResult` | Parse collecting all errors. |
| `parse_and_validate()` | `(AST, ValidationReport)` | Parse and run AST validation. |
| `create_configured_parser(tokens, **overrides)` | `Parser` | Create child parser with cloned config. |

### 2.5 `ParseError`

```python
from psh.parser import ParseError

try:
    ast = parse(tokens)
except ParseError as e:
    print(e)                    # formatted message
    ctx = e.error_context       # ErrorContext with position, suggestions
```

### 2.6 Runtime parser selection

The `create_parser()` function in `psh/parser/__init__.py` chooses between
the recursive descent parser and the combinator parser at runtime:

```python
from psh.parser import create_parser

parser = create_parser(tokens, active_parser='rd', trace_parsing=False)
ast = parser.parse()
```

The `active_parser` argument selects the implementation (`'rd'` or
`'combinator'`).  Users can switch at runtime via the `parser-select`
builtin.


## 3. The AST

AST nodes are defined in `psh/ast_nodes.py` (~500 lines).  All nodes inherit
from `ASTNode`.

### 3.1 Node hierarchy

```
ASTNode
├── TopLevel                      # Root: list of statements/function defs
├── Statement
│   ├── AndOrList                 # cmd1 && cmd2 || cmd3
│   ├── FunctionDef               # function name() { body }
│   └── UnifiedControlStructure   # (also a CompoundCommand)
│       ├── IfConditional
│       ├── WhileLoop / UntilLoop
│       ├── ForLoop / CStyleForLoop
│       ├── CaseConditional
│       ├── SelectLoop
│       ├── ArithmeticEvaluation  # (( expr ))
│       ├── BreakStatement
│       └── ContinueStatement
├── Command
│   ├── SimpleCommand             # echo hello
│   └── CompoundCommand
│       ├── SubshellGroup         # ( commands )
│       ├── BraceGroup            # { commands; }
│       └── UnifiedControlStructure (shared with Statement above)
├── Pipeline                      # cmd1 | cmd2 | cmd3
├── StatementList / CommandList   # sequence of statements
├── Redirect                      # > file, 2>&1, <<EOF, etc.
├── ProcessSubstitution           # <(cmd) or >(cmd)
├── Word                          # argument with parts
│   ├── LiteralPart               # plain text
│   └── ExpansionPart             # wraps an Expansion node
├── Expansion
│   ├── VariableExpansion         # $VAR
│   ├── ParameterExpansion        # ${VAR:-default}
│   ├── CommandSubstitution       # $(cmd) or `cmd`
│   └── ArithmeticExpansion       # $((expr))
├── TestExpression
│   ├── BinaryTestExpression      # $x -eq 1
│   ├── UnaryTestExpression       # -f file
│   ├── CompoundTestExpression    # expr1 && expr2
│   └── NegatedTestExpression     # ! expr
├── EnhancedTestStatement         # [[ expr ]]
├── CaseItem / CasePattern        # case clause internals
└── ArrayAssignment
    ├── ArrayInitialization       # arr=(a b c)
    └── ArrayElementAssignment    # arr[0]=value
```

### 3.2 The `Word` node

`SimpleCommand.words` is a `List[Word]`.  Each `Word` contains a list of
`WordPart` objects (`LiteralPart` or `ExpansionPart`) with per-part quote
context.  This is the **sole** representation for argument metadata &mdash;
the legacy `arg_types`/`quote_types` fields were removed in v0.120.0.

Useful `Word` properties:

| Property | Purpose |
|----------|---------|
| `is_quoted` | True if wholly quoted (single, double, or ANSI-C). |
| `is_unquoted_literal` | True if plain unquoted word with no expansions. |
| `is_variable_expansion` | True if the word is a single `$VAR` expansion. |
| `has_expansion_parts` | True if any part is an expansion. |
| `has_unquoted_expansion` | True if unquoted expansions exist (vulnerable to splitting). |
| `effective_quote_char` | The dominant quote character, or `None`. |

### 3.3 Unified control structures

Control structures (`IfConditional`, `WhileLoop`, etc.) inherit from both
`Statement` and `CompoundCommand`.  This means they can appear both at the
top level and inside pipelines:

```bash
# As a statement:
while true; do echo loop; done

# Inside a pipeline:
while true; do echo loop; done | head -5
```

Each carries an `execution_context` field (`STATEMENT` or `PIPELINE`) and
optional `redirects` and `background` fields for compound-command usage.


## 4. Architecture

### 4.1 Two parser implementations

PSH has two complete parser implementations that produce identical ASTs:

1. **Recursive descent** (`psh/parser/recursive_descent/`) &mdash; the
   production parser.  Hand-written, imperative, delegation-based.  This is
   what the shell uses by default.

2. **Parser combinator** (`psh/parser/combinators/`) &mdash; a functional
   alternative.  Builds parsers from composable primitives.  Useful for
   education and experimentation.  Selectable at runtime with
   `--parser combinator` or the `parser-select` builtin.

### 4.2 Recursive descent architecture

The main `Parser` class instantiates eight specialised sub-parsers and
delegates to them:

```
Parser  (parser.py — orchestrator)
├── StatementParser      (statements.py)
├── CommandParser        (commands.py)
├── ControlStructureParser (control_structures.py)
├── TestParser           (tests.py)
├── ArithmeticParser     (arithmetic.py)
├── FunctionParser       (functions.py)
├── RedirectionParser    (redirections.py)
└── ArrayParser          (arrays.py)
```

All sub-parsers receive a reference to the main `Parser` and access shared
state through `ParserContext`.

### 4.3 Parsing flow

```
tokens
  │
  ▼
Parser.parse()
  │
  ├─ parse top-level items in a loop:
  │   ├─ FunctionParser.is_function_def()?  → parse_function_def()
  │   └─ otherwise → StatementParser.parse_statement()
  │       └─ parse_and_or_list()
  │           └─ CommandParser.parse_pipeline()
  │               └─ parse_pipeline_component()
  │                   ├─ control keyword? → ControlStructureParser
  │                   ├─ (( ? → ArithmeticParser
  │                   ├─ [[ ? → TestParser
  │                   ├─ ( ? → subshell group
  │                   ├─ { ? → brace group
  │                   └─ otherwise → parse_simple_command()
  │                       ├─ collect args as Word nodes (via WordBuilder)
  │                       ├─ collect redirections (via RedirectionParser)
  │                       └─ detect array assignments (via ArrayParser)
  │
  ▼
TopLevel / CommandList AST
```

### 4.4 `ParserContext`

`ParserContext` (in `context.py`) centralises all mutable parser state:

- **Token stream**: `tokens`, `current` position, `peek()`, `advance()`,
  `match()`.
- **Parsing context flags**: `in_function_body`, `in_arithmetic`,
  `in_test_expr`, `in_case_pattern`, `in_command_substitution`.
- **Depth counters**: `loop_depth`, `function_depth`, `conditional_depth`,
  `nesting_depth`.
- **Scope stack**: tracks nested scopes (`"function"`, `"loop"`,
  `"conditional"`, etc.) for validation.
- **Heredoc tracking**: `register_heredoc()`, `add_heredoc_line()`,
  `close_heredoc()`.
- **Error collection**: list of `ParseError` objects when in
  multi-error mode.
- **Profiling**: optional `ParserProfiler` that records rule timings,
  recursion depth, and backtracking events.

The context manager (`with parser.ctx:`) saves and restores state around a
block &mdash; used when entering nested parsing contexts where flags need
temporary changes.

### 4.5 `WordBuilder`

`WordBuilder` (in `support/word_builder.py`) constructs `Word` AST nodes
from tokens.  It:

- Decomposes STRING tokens into `LiteralPart` and `ExpansionPart` nodes
  using the token's `parts` list.
- Detects parameter-expansion operators in VARIABLE tokens (e.g.
  `${x:-default}`).
- Handles composite words by building multi-part `Word` nodes with per-part
  quote context.

### 4.6 `TokenGroups`

`TokenGroups` (in `helpers.py`) defines frozen sets of related token types
used for fast membership checks:

| Group | Contents |
|-------|----------|
| `WORD_LIKE` | WORD, STRING, VARIABLE, COMMAND_SUB, ARITH_EXPANSION, ... |
| `REDIRECTS` | REDIRECT_IN, REDIRECT_OUT, REDIRECT_APPEND, HEREDOC, ... |
| `CONTROL_KEYWORDS` | IF, WHILE, FOR, CASE, SELECT, ... |
| `STATEMENT_SEPARATORS` | SEMICOLON, NEWLINE |
| `CASE_TERMINATORS` | DOUBLE_SEMICOLON, SEMICOLON_AMP, AMP_SEMICOLON |
| `COMMAND_LIST_END` | FI, DONE, ESAC, ELSE, ELIF, RBRACE, ... |
| `CASE_PATTERN_KEYWORDS` | IF, THEN, ELSE, FI, WHILE, FOR, CASE, ESAC, ... |

### 4.7 Error handling

Three modes, selected via `ParserConfig.error_handling`:

- **STRICT** (default) &mdash; raise `ParseError` on the first error.
- **COLLECT** &mdash; accumulate errors in `ParserContext.errors` and
  continue parsing.
- **RECOVER** &mdash; like COLLECT, but also attempts to skip tokens and
  resume parsing after errors.

`ParseError` wraps an `ErrorContext` that carries the error message, the
offending token, surrounding context tokens, suggestions, an error code,
and source-line display information.

### 4.8 Parser combinator architecture

The combinator parser (`psh/parser/combinators/`) builds parsers from
composable primitives:

```python
# Simplified example
if_statement = (
    keyword("if")
    .then(command_list)       # condition
    .then(keyword("then"))
    .then(command_list)       # body
    .then(keyword("fi"))
    .map(build_if_node)
)
```

Key modules:

| Module | Provides |
|--------|----------|
| `core.py` | `Parser[T]` monad, `ParseResult[T]`, combinators (`many`, `optional`, `sequence`, `choice`, ...) |
| `tokens.py` | Token-level parsers (`keyword()`, `word()`, `operator()`, ...) |
| `commands.py` | Command hierarchy (simple command &rarr; pipeline &rarr; and-or list &rarr; statement list) |
| `special_commands.py` | Arithmetic commands, `[[ ]]` tests, array assignments, process substitution, declaration builtins, control structures |
| `expansions.py` | Expansion node construction |
| `heredoc_processor.py` | Two-pass heredoc content population |
| `parser.py` | `ParserCombinatorShellParser` &mdash; main entry point |

Circular dependencies between commands and control structures are resolved
with `ForwardParser[T]` (a deferred parser definition) and explicit
`set_command_parsers()` wiring.

### 4.9 Validation pipeline

Optional post-parse validation is available through `psh/parser/validation/`:

- **`ValidationPipeline`** &mdash; walks the AST with registered
  `ValidationRule` instances, collecting `Issue` objects with severity
  levels (INFO, WARNING, ERROR, CRITICAL).
- **`SemanticAnalyzer`** &mdash; an `ASTVisitor` that maintains a
  `SymbolTable` and checks for unused variables/functions, undeclared
  variables, and other semantic problems.
- **Concrete rules** include: `NoEmptyBodyRule`, `ValidRedirectRule`,
  `CorrectBreakContinueRule`, `FunctionNameRule`, `ValidArithmeticRule`,
  `ValidTestExpressionRule`, `ValidVariableNameRule`.

Validation is off by default; enable it with
`ParserConfig(enable_validation=True)` or call `parser.parse_and_validate()`.

### 4.10 Visualisation

Four AST renderers live in `psh/parser/visualization/`:

| Renderer | Output |
|----------|--------|
| `ASTPrettyPrinter` | Human-readable indented text. |
| `AsciiTreeRenderer` | Box-drawing tree for terminals. |
| `DotGenerator` | Graphviz DOT format for diagrams. |
| `SExpressionRenderer` | S-expression (Lisp-style) format. |

Usage from the command line:

```bash
python -m psh --debug-ast -c "if true; then echo yes; fi"
```


## 5. Source File Reference

All paths are relative to `psh/parser/`.

### 5.1 Package entry point

#### `__init__.py` (~50 lines)

Defines `parse()` and `parse_with_heredocs()`.  Re-exports the public API
(`Parser`, `ParserConfig`, `ParseError`) and convenience imports
(`ParsingMode`, `ErrorHandlingMode`, `ParserContext`, `ParserProfiler`,
`ErrorContext`, `create_context`).

### 5.2 Configuration

#### `config.py` (~100 lines)

`ParserConfig` dataclass with 14 fields, `ParsingMode` enum (STRICT_POSIX,
BASH_COMPAT, PERMISSIVE, EDUCATIONAL), and `ErrorHandlingMode` enum (STRICT,
COLLECT, RECOVER).  Factory methods `strict_posix()` and `permissive()`
produce preset configurations.

### 5.3 Recursive descent core

#### `recursive_descent/parser.py` (~450 lines)

The main `Parser` class.  Instantiates eight sub-parsers, provides
`parse()`, `parse_with_error_collection()`, `parse_and_validate()`, and
`parse_with_heredocs()`.

#### `recursive_descent/context.py` (~530 lines)

`ParserContext` &mdash; centralised state (token stream, position, parsing
flags, scope stack, heredoc trackers, error list, profiler).  Also defines
`HeredocInfo` and `ParserProfiler`.

#### `recursive_descent/base_context.py` (~160 lines)

`ContextBaseParser` &mdash; the base class for `Parser`.
Delegates token operations to `ParserContext` and provides scope/rule
tracking, error handling, feature checking, and debugging helpers.

#### `recursive_descent/helpers.py` (~175 lines)

`TokenGroups` (predefined token sets), `ErrorContext` (enhanced error info
with suggestions), and `ParseError` (exception class).

### 5.4 Specialised parsers

All in `recursive_descent/parsers/`.

#### `statements.py` (~105 lines)

`StatementParser` &mdash; parses statement lists (`parse_command_list()`,
`parse_command_list_until()`), and-or lists (`parse_and_or_list()`), and
top-level statements (`parse_statement()`).

#### `commands.py` (~545 lines)

`CommandParser` &mdash; parses simple commands, pipelines, and pipeline
components.  Handles argument collection via `WordBuilder`, redirection
detection, file-descriptor duplication, array-assignment detection, and
unclosed-expansion checking.

#### `control_structures.py` (~500 lines)

`ControlStructureParser` &mdash; parses `if`/`elif`/`else`/`fi`,
`while`/`until`/`do`/`done`, `for`/`in`/`do`/`done` (including C-style
`for`), `case`/`esac`, `select`, `break`, and `continue`.  Each structure
has a "neutral" variant that avoids setting execution-context flags (used for
compound commands in pipelines).

#### `tests.py` (~245 lines)

`TestParser` &mdash; parses `[[ ]]` enhanced test expressions with proper
precedence: `||` < `&&` < unary < primary.  Supports string comparisons
(`=`, `==`, `!=`, `<`, `>`), arithmetic comparisons (`-eq`, `-lt`, ...),
file tests (`-f`, `-d`, `-e`, ...), regex matching (`=~`), and negation
(`!`).

#### `arithmetic.py` (~155 lines)

`ArithmeticParser` &mdash; parses `(( expr ))` arithmetic commands.
Collects tokens between the double-paren delimiters into an expression
string.

#### `redirections.py` (~210 lines)

`RedirectionParser` &mdash; parses all redirection operators (`>`, `>>`,
`<`, `2>`, `2>>`, `>&`, `<&`, `<<`, `<<-`, `<<<`), heredoc delimiters, and
file-descriptor duplication.

#### `functions.py` (~95 lines)

`FunctionParser` &mdash; detects and parses function definitions in both
`function name() { body; }` and POSIX `name() { body; }` forms.

#### `arrays.py` (~445 lines)

`ArrayParser` &mdash; detects and parses array assignments:
`arr=(a b c)`, `arr+=(d)`, `arr[0]=value`, `arr[key]+=value`.

### 5.5 Support infrastructure

All in `recursive_descent/support/`.

#### `context_factory.py` (~40 lines)

`create_context()` &mdash; creates a `ParserContext` from tokens and an
optional `ParserConfig`.  Normalises tokens via `KeywordNormalizer` before
context creation.  Has 3 production callers inside `parser.py`.

#### `word_builder.py` (~290 lines)

`WordBuilder` &mdash; constructs `Word` AST nodes from tokens, handling
expansion decomposition and quote-context propagation.

#### `utils.py` (~90 lines)

`parse_with_heredocs()` function (used by the package-level
`parse_with_heredocs()`) and token-reconstruction utilities.

### 5.6 Parser combinators

All in `combinators/`.

#### `core.py` (~485 lines)

Foundation: `ParseResult[T]` dataclass, `Parser[T]` monad with `.map()`,
`.then()`, `.or_else()`, `.many()`, `.optional()`, `.sepBy()`.
`ForwardParser[T]` for recursive grammars.  Helper functions: `token()`,
`many()`, `sequence()`, `choice()`, `lazy()`, `between()`.

#### `tokens.py` (~385 lines)

`TokenParsers` &mdash; token-level parsers organised by category (basic
tokens, operators, delimiters, keywords, expansions, combined parsers).

#### `commands.py` (~675 lines)

`CommandParsers` &mdash; builds the command hierarchy: simple command &rarr;
pipeline &rarr; and-or list &rarr; statement list.  Handles redirections and
background operators.  Also includes control structure parsers (if, while,
for, case, select, functions, subshells, brace groups).

#### `special_commands.py` (~705 lines)

`SpecialCommandParsers` &mdash; arithmetic commands, enhanced test
expressions, array assignments, process substitution, and declaration
builtins (`declare`, `local`, `export`, `readonly`, `typeset`).

#### `expansions.py` (~360 lines)

`ExpansionParsers` &mdash; builds `Word` AST nodes from expansion tokens.
Integrates with `WordBuilder`.

#### `heredoc_processor.py` (~420 lines)

`HeredocProcessor` &mdash; post-parse pass that populates `Redirect` nodes
with heredoc content from the `heredoc_map`.

#### `parser.py` (~425 lines)

`ParserCombinatorShellParser` &mdash; main orchestrator.  Initialises all
combinator modules, wires circular dependencies, builds the complete parser
pipeline.

### 5.7 Validation

All in `validation/`.

#### `validation_pipeline.py` (~320 lines)

`ValidationPipeline` &mdash; `ASTVisitor` that applies registered
`ValidationRule` instances to each node and collects `Issue` objects into a
`ValidationReport`.

#### `validation_rules.py` (~400 lines)

`Severity` enum, `Issue` dataclass, `ValidationContext`,
`ValidationReport`, `ValidationRule` ABC, and seven concrete rules.

#### `semantic_analyzer.py` (~295 lines)

`SemanticAnalyzer` &mdash; `ASTVisitor` that maintains a `SymbolTable`,
tracks variable/function declarations and usages, and reports unused
symbols.

#### `symbol_table.py` (~180 lines)

`SymbolTable` &mdash; tracks variable and function symbols with scope
nesting.

#### `warnings.py` (~100 lines)

`WarningSeverity`, `SemanticWarning`, and `CommonWarnings` factory.

### 5.8 Visualisation

All in `visualization/`.

#### `ast_formatter.py` (~330 lines)

`ASTPrettyPrinter` &mdash; human-readable indented AST output with optional
position information.

#### `ascii_tree.py` (~500 lines)

`AsciiTreeRenderer` and `CompactAsciiTreeRenderer` &mdash; box-drawing
trees for terminal display.

#### `dot_generator.py` (~370 lines)

`ASTDotGenerator` &mdash; Graphviz DOT output with colour-coded node
types.

#### `sexp_renderer.py` (~315 lines)

`SExpressionRenderer` &mdash; Lisp-style S-expression output.


## 6. How the Shell Calls the Parser

In `psh/scripting/source_processor.py`, the main execution path:

1. Tokenise the input (with or without heredocs).
2. Parse:
   - For heredoc input: `parse_with_heredocs(tokens, heredoc_map)`.
   - Otherwise: `create_parser(tokens, active_parser=..., ...)` from
     `psh.parser`, which selects either the recursive descent parser or
     the combinator parser.
3. Walk the resulting AST with `ExecutorVisitor`.

The `create_parser()` function handles parser selection:

```python
from psh.parser import create_parser

parser = create_parser(tokens, active_parser='rd', trace_parsing=False)
ast = parser.parse()
```


## 7. Common Tasks

### 7.1 Adding a new control structure

1. **Token types** &mdash; add keyword token types in `psh/token_types.py`.
2. **AST node** &mdash; create a dataclass in `psh/ast_nodes.py`, inheriting
   from `UnifiedControlStructure` (which is both `Statement` and
   `CompoundCommand`).
3. **Parser** &mdash; add a `parse_my_structure()` method to
   `ControlStructureParser` in `parsers/control_structures.py`.
4. **Routing** &mdash; add a branch in `CommandParser.parse_pipeline_component()`
   to recognise the new keyword and delegate to your parser method.
5. **Executor** &mdash; add a `visit_MyStructure()` method in
   `psh/executor/control_flow.py`.
6. **Tests** &mdash; add tests in `tests/unit/parser/`.

### 7.2 Adding a new expression type

1. Add an AST node in `psh/ast_nodes.py`.
2. Add or extend a parser method in the appropriate sub-parser.
3. Wire it into the relevant parsing path.
4. Add a visitor method in the executor.

### 7.3 Adding a new redirection operator

1. Add the token type to `TokenType` in `psh/token_types.py`.
2. Add the operator to `OPERATORS_BY_LENGTH` in `psh/lexer/constants.py`.
3. Handle it in `RedirectionParser.parse_redirect()`.
4. Handle the resulting `Redirect` node in `psh/io_redirect/`.

### 7.4 Debugging parsing

```bash
# Show the AST
python -m psh --debug-ast -c "for i in 1 2 3; do echo \$i; done"

# Show tokens before parsing
python -m psh --debug-tokens -c "echo hello"

# Parse and validate without executing
python -m psh --validate script.sh
```

Programmatically:

```python
from psh.parser import Parser, ParserConfig

config = ParserConfig(profile_parsing=True)
parser = Parser(tokens, config=config)
ast = parser.parse()
print(parser.ctx.generate_profiling_report())
```


## 8. Design Rationale

### Why two parser implementations?

PSH is an educational shell.  Having both a recursive descent parser and a
parser combinator that produce the same AST lets students compare imperative
and functional parsing approaches.  The recursive descent parser is the
production default; the combinator parser is opt-in.

### Why delegate to eight sub-parsers?

A single monolithic parser class becomes difficult to navigate.  The
delegation pattern keeps each sub-parser focused on one grammar area and
makes it straightforward to add new constructs without touching unrelated
code.

### Why centralise state in `ParserContext`?

Passing parsing flags through method parameters creates explosion in method
signatures.  `ParserContext` consolidates all mutable state into one
object that sub-parsers access through `self.parser`.  The context manager
(`with parser.ctx:`) provides safe save/restore around nested parsing
blocks.

### Why build `Word` nodes instead of plain strings?

Shell arguments can mix literal text, variable expansions, command
substitutions, and different quoting styles in a single word (e.g.
`"Hello ${USER}!"` or `file${N}.txt`).  `Word` nodes preserve this
structure so the expansion engine can apply per-part quoting rules without
reparsing the argument.

### Why is validation optional?

Validation adds overhead and can produce false positives for unusual but
legal shell patterns.  Making it opt-in keeps the default fast path lean
while still being available for linting and educational tools.


## 9. File Dependency Graph

```
__init__.py
├── config.py
├── recursive_descent/
│   ├── parser.py
│   │   ├── context.py  (ParserContext, HeredocInfo, ParserProfiler)
│   │   ├── base_context.py  (ContextBaseParser)
│   │   ├── helpers.py  (TokenGroups, ErrorContext, ParseError)
│   │   ├── parsers/
│   │   │   ├── statements.py
│   │   │   ├── commands.py ─── support/word_builder.py
│   │   │   ├── control_structures.py
│   │   │   ├── tests.py
│   │   │   ├── arithmetic.py
│   │   │   ├── redirections.py
│   │   │   ├── functions.py
│   │   │   └── arrays.py
│   │   └── support/
│   │       ├── context_factory.py
│   │       ├── word_builder.py
│   │       └── utils.py
│   └── __init__.py
├── combinators/
│   ├── parser.py  (ParserCombinatorShellParser)
│   │   ├── core.py  (Parser[T], ParseResult[T], combinators)
│   │   ├── tokens.py
│   │   ├── commands.py
│   │   ├── special_commands.py
│   │   ├── expansions.py
│   │   └── heredoc_processor.py
│   └── __init__.py
├── validation/
│   ├── validation_pipeline.py
│   ├── validation_rules.py
│   ├── semantic_analyzer.py
│   ├── symbol_table.py
│   └── warnings.py
└── visualization/
    ├── ast_formatter.py
    ├── ascii_tree.py
    ├── dot_generator.py
    └── sexp_renderer.py

External dependencies (outside the parser package):
- psh/token_types.py     — Token and TokenType definitions
- psh/ast_nodes.py       — AST node dataclasses
- psh/token_stream.py    — TokenStream utility (used by ArithmeticParser)
- psh/lexer/             — KeywordNormalizer (used by context_factory)
```
