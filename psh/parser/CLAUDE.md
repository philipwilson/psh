# Parser Subsystem

This document provides guidance for working with the PSH parser subsystem.

## Architecture Overview

The parser transforms token streams into Abstract Syntax Trees (ASTs). PSH uses a **recursive descent parser** with specialized sub-parsers for different language constructs.

```
Tokens → Parser → AST (Program root)
              ↓
    ┌─────────┼─────────┬──────────┬─────────┐
    ↓         ↓         ↓          ↓         ↓
Statements Commands  Control   Functions  Tests
                    Structures
```

## Key Files

### Core Parser (`recursive_descent/`)

| File | Purpose |
|------|---------|
| `parser.py` | Main `Parser` class - orchestrates all parsing |
| `context.py` | `ParserContext` - centralized state management |
| `base_context.py` | `ContextBaseParser` - base class with context integration |
| `helpers.py` | `TokenGroups`, `ErrorContext`, `ParseError` |

### Specialized Parsers (`recursive_descent/parsers/`)

| File | Parses |
|------|--------|
| `statements.py` | Statement lists, command lists, and-or lists (`&&`/`||`) |
| `commands.py` | Simple commands, pipelines, arguments, subshell/brace groups |
| `control_structures.py` | `if`, `while`, `for`, `case`, `select` |
| `tests.py` | `[[ ]]` test expressions |
| `arithmetic.py` | `(( ))` arithmetic expressions |
| `functions.py` | Function definitions |
| `redirections.py` | I/O redirections, heredocs |
| `arrays.py` | Array assignments |

### Support Infrastructure (`recursive_descent/support/`)

| File | Purpose |
|------|---------|
| `context_factory.py` | Factory functions for creating configured contexts |
| `word_builder.py` | Build Word AST nodes from tokens |
| `utils.py` | Parser utilities |

### Parser Combinators (`combinators/`) -- Educational Only

**Status: Educational only (project decision 2026-06-12).** This is NOT
the production parser and is **outside the production quality bar**. It
exists as an educational counterpoint demonstrating functional parsing,
and as a proof of concept that parser combinators can handle real shell
syntax. There is no plan to converge with or replace the recursive descent
parser. Parity regression tests (`tests/integration/parser/
test_combinator_parity_regressions.py` and friends) pin known-good
behavior against drift, but remaining gaps (e.g. composite words in some
list contexts, `select` without `in`) are documented rather than tracked
as defects; reviews should not count them as findings. Revisit if/when
dedicated time is available.

See [Combinator Parser Guide](../../docs/guides/combinator_parser_guide.md)
for a detailed walkthrough. Use `parser-select combinator` inside psh to
try it interactively.

| File | Purpose |
|------|---------|
| `core.py` | Combinator primitives (`token`, `many`, `sequence`, etc.) |
| `tokens.py` | Token-level matchers |
| `expansions.py` | Expansion parsers and Word AST building |
| `arrays.py` | `ArrayParsers` — THE array assignment/initialization parser (used by the live command path in `commands.py`) |
| `commands.py` | Simple commands, pipelines, and-or lists, statement lists |
| `control_structures/` | Package of mixins: `conditionals.py` (if, case), `loops.py` (while, until, for, select), `structures.py` (functions, subshell/brace groups) |
| `special_commands.py` | `(( ))`, `[[ ]]`, process substitution (NOT arrays — those live in `arrays.py`) |
| `heredoc_processor.py` | Post-parse heredoc content population |
| `utils.py` | Shared combinator helpers |
| `parser.py` | `ParserCombinatorShellParser` integration class |

**Compound-body / condition engine.** `CommandParsers.build_statement_list(
terminators, terminator_types)` (in `commands.py`) is the single recursion-based
engine for every compound statement list — loops/if/case/function/subshell/brace
bodies, the `while`/`until`/`if`/`elif` **condition headers** (stopping at
`do`/`then`), and the top-level list all build terminator-specific variants of
it. It parses a statement list that stops at (without consuming) its terminator
keyword(s); nested compounds consume their own `done`/`fi`/`esac`, so the
recursion *is* the nesting tracker, and a terminator keyword is only ever
recognised at command-start position (so `while echo do; …` / `if echo then; …`
treat the keyword-spelled argument as a plain word — matching bash and rd).
Prefer it over token-slice-and-reparse for any new body or header.

> Note: AST validation/linting/security analysis is performed by the visitor
> validators in `psh/visitor/` (e.g. `EnhancedValidatorVisitor`), not by the
> parser. There is no parser-side validation subsystem.

## Core Patterns

### 1. Delegating Parser Pattern

The main `Parser` delegates to specialized sub-parsers:

```python
class Parser(ContextBaseParser):
    def __init__(self, ...):
        # Sub-parsers for different constructs
        self.statements = StatementParser(self)
        self.commands = CommandParser(self)
        self.control_structures = ControlStructureParser(self)
        self.tests = TestParser(self)
        self.arithmetic = ArithmeticParser(self)
        self.functions = FunctionParser(self)
        self.redirections = RedirectionParser(self)
        self.arrays = ArrayParser(self)
```

### 2. Sub-Parser Contract

All 8 sub-parsers extend `ParserSubcomponent`
(`recursive_descent/parsers/base.py`), which holds the shared contract:

- **Initialization**: the base's `__init__(self, main_parser)` stores
  `self.parser` (the main `Parser` instance) — sub-parsers no longer repeat
  it. The base is deliberately minimal: it adds NO token-access delegation
  (no `self.peek()` forwarding), so sub-parsers reference `self.parser.X`
  explicitly and a reader always sees that token state lives on the one
  shared `Parser`. (See the base's module docstring for the rationale.)
- **State access**: Use `self.parser.peek()`, `.advance()`, `.match()`,
  `.expect()`, `.consume_if()`, etc. (methods inherited from
  `ContextBaseParser`).
- **Token position**: Use `self.parser.current` (the property on
  `Parser`), not `self.parser.ctx.current` directly. Both work, but the
  property is the intended public interface.
- **Optional consumption**: Prefer `self.parser.consume_if(TokenType.X)`
  over the inline `if self.parser.match(X): self.parser.advance()`
  pattern.
- **Error creation**: Use `self.parser.error(message)` or
  `self.parser.error(message, token)`.

### 3. ParserContext State Management

`ParserContext` holds the parser's shared state — the token stream and
position, configuration, error collection, and source text for error
messages. (It deliberately does NOT track grammar context for parse
decisions: the recursive call structure *is* the context in a
recursive-descent parser. The one apparent exception,
`open_constructs`, is a write-only trail of which constructs are open
('if', 'then', 'while', ...) read by exactly one consumer — the
`CommandAccumulator`'s incomplete-input hints after an `at_eof` parse
failure, which drive the interactive `if> `/`for then> ` continuation
prompts. No parse method ever reads it. `nesting_depth` is likewise not
grammar context but a resource limit: a counter of compound-command
nesting maintained by `CommandParser._parse_compound_component`, checked
only against `MAX_NESTING_DEPTH` (1000) so runaway nesting raises a
clean ParseError instead of a Python RecursionError.)

```python
class ParserContext:
    tokens: List[Token]      # Token stream
    current: int             # Current position
    config: ParserConfig

    # Pre-collected heredoc bodies (heredoc-aware parse only), keyed by the
    # lexer-assigned heredoc_key; None otherwise.
    heredoc_map: Optional[Mapping[str, object]]

    # Source context (for error messages)
    source_text: Optional[str]
    source_lines: Optional[List[str]]

    # Resource limit (see above)
    nesting_depth: int
```

Parse errors: `consume()` raises a `ParseError` on the first unexpected token
(no error-collection mode). `ParseError` has one diagnostic interface —
`error.summary` (short reason), `error.render()` (rich: position, source line,
caret, suggestions), and `str(error)` delegating to `render()`. Execution and
analysis (`--validate` etc.) both print `render()`.

### 4. TokenGroups for Matching

Predefined token sets for common checks:

```python
class TokenGroups:
    WORD_LIKE = frozenset({WORD, STRING, VARIABLE, ...})
    REDIRECTS = frozenset({REDIRECT_IN, REDIRECT_OUT, ...})
    STATEMENT_SEPARATORS = frozenset({SEMICOLON, NEWLINE, ...})
    CONTROL_KEYWORDS = frozenset({IF, WHILE, FOR, ...})
```

## Parsing Flow

### Top-Level Parsing

There is ONE grammar path and ONE root type. `parse()` loops over
`parse_command_list` — it does NOT special-case control structures. A control
structure at command position is just a pipeline component (see
`parse_pipeline_component`), so `while …; done | cat`, `… && …`, `… &`, etc.
flow through the same `and_or_list`/`pipeline` machinery as a simple command,
and the top level builds no `Pipeline`/`AndOrList` by hand. (This is enforced
by `tests/unit/parser/test_top_level_control_structure_grammar.py`.)

```python
def parse(self) -> Program:
    program = Program()
    while not self.at_end():
        command_list = self.statements.parse_command_list()
        program.statements.extend(command_list.statements)
        self.skip_separators()
    return program
```

Every parse — including empty input — returns a single canonical `Program`
whose `statements` are the ordinary statements the grammar produced
(`AndOrList` / `FunctionDef`). There is NO post-parse root reshaping: a bare
compound keeps its normal `AndOrList → Pipeline` ancestry, exactly like any
other statement (it is not unwrapped at the root). So `while …; done; echo a`
groups the same way as `echo a; while …; done`. `Program` is the root only;
nested command bodies (loop/if/function/group interiors) still use
`StatementList`. The combinator parser returns the same `Program` root, so
both parsers share one concrete root contract
(`tests/parser_differential/test_combinator_ast_parity.py`).

### Statement Parsing

```
Statement → AndOrList (&&/|| chains)
AndOrList → Pipeline (| chains)
Pipeline → Command (simple or compound)
Command → SimpleCommand | IfConditional | WhileLoop | ...
```

## Common Tasks

### Adding a New Control Structure

1. Add token types in `psh/lexer/token_types.py`

2. Add AST node in the `psh/ast_nodes/` package (control structures go in
   `psh/ast_nodes/control.py`):
```python
@dataclass
class MyNewStructure(Command):
    condition: Command
    body: List[Statement]
```

3. Add parser method in `parsers/control_structures.py`:
```python
def parse_my_structure(self) -> MyNewStructure:
    self.parser.expect(TokenType.MY_KEYWORD)
    condition = self.parser.commands.parse_command()
    self.parser.expect(TokenType.DO)
    body = self.parser.statements.parse_command_list_until(TokenType.DONE)
    self.parser.expect(TokenType.DONE)
    return MyNewStructure(condition=condition, body=body)
```

4. Add to `parse_pipeline_component()` in `commands.py`:
```python
elif self.parser.match(TokenType.MY_KEYWORD):
    return self.parse_my_structure_command()
```

5. Add executor method in `psh/executor/control_flow.py`

6. Add tests in `tests/unit/parser/`

### Adding a New Expression Type

1. Create or extend parser in `parsers/`

2. Add AST node in the `psh/ast_nodes/` package

3. Wire into appropriate parsing method

4. Add visitor method in executor

## Key Implementation Details

### Keyword vs Word Distinction

Keywords are only recognized at command position:
- `if echo` → IF keyword, WORD "echo"
- `echo if` → WORD "echo", WORD "if"

The parser uses `TokenGroups.CONTROL_KEYWORDS` to identify keywords.

### Compound Command Handling

Compound commands can appear in pipelines:
```python
def parse_pipeline_component(self) -> Command:
    if self.parser.match(TokenType.WHILE):
        return self.parse_while_command()
    elif self.parser.match(TokenType.IF):
        return self.parse_if_command()
    # ... other compound commands
    else:
        return self.parse_command()  # Simple command
```

### Heredoc Collection

Heredocs are handled in two phases:
1. The lexer (`tokenize_with_heredocs`) collects each body separately and
   stamps a `heredoc_key` on the `<<`/`<<-` operator token; the bodies live
   in a `heredoc_map` returned alongside the tokens.
2. The parser attaches the body to the `Redirect` node AS IT IS CONSTRUCTED —
   `parse_with_heredocs` / the interactive trial parse thread the map into
   `Parser(..., heredoc_map=...)`, and `RedirectionParser._attach_heredoc_body`
   looks the body up by key. Attachment is key-driven: a heredoc redirect whose
   key is absent from the map is a hard error (no post-parse AST walk, no
   delimiter-suffix guessing). The former post-parse `populate_heredoc_content`
   AST walk was removed. (The educational combinator keeps its own
   `HeredocProcessor` visitor with identical observable attachment.)

## Testing

```bash
# Run parser unit tests
python -m pytest tests/unit/parser/ -v

# Test specific feature
python -m pytest tests/unit/parser/test_parser_migration.py -v

# Debug AST output
python -m psh --debug-ast -c "if true; then echo yes; fi"
```

## Common Pitfalls

1. **Token Advancement**: Always call `advance()` to consume tokens after matching. `match()` only peeks.

2. **Newline Handling**: Use `skip_newlines()` appropriately - some constructs allow them, others don't.

3. **Heredoc State**: Heredocs require special handling; they're collected after the statement.

4. **Error Position**: Always include token position in error messages for debugging.

## Debug Options

```bash
python -m psh --debug-ast      # Show parsed AST structure
python -m psh --debug-tokens   # Show tokens before parsing
python -m psh --validate       # Parse and validate without executing
```

## Word AST

The parser always builds **Word AST nodes** for command arguments. Each
`SimpleCommand.words` list contains `Word` objects with `LiteralPart` and
`ExpansionPart` nodes carrying per-part quote context (`quoted`, `quote_char`).
`words` is the **single source of truth** for a command's arguments: the
string view `SimpleCommand.args` is a derived, read-only property
(`psh/ast_nodes/commands.py`) that flattens each Word's parts — there is no stored
args list to keep in sync. Build `words` only; never assign `args`.

```python
# "hello $USER!" becomes:
Word(parts=[
    LiteralPart("hello ", quoted=True, quote_char='"'),
    ExpansionPart(VariableExpansion("USER"), quoted=True, quote_char='"'),
    LiteralPart("!", quoted=True, quote_char='"'),
], quote_type='"')
```

### WordBuilder

`WordBuilder` (`support/word_builder.py`) is the bridge between lexer
tokens and the Word AST. It is the most complex single piece of the
parser -- it handles RichToken decomposition, composite word merging,
and parameter expansion operator parsing.

**Entry point**: `CommandParser.parse_argument_as_word()` in
`parsers/commands.py`. This method detects composite sequences via
`TokenStream.peek_composite_sequence()`, then delegates to the
appropriate WordBuilder method.

**Three key operations**:

1. **Single tokens** -- `build_word_from_token()`: Decomposes
   double-quoted STRING tokens with `RichToken.parts` into
   `LiteralPart`/`ExpansionPart` nodes with per-part quote context.

2. **Composite tokens** -- `build_composite_word()`: Merges adjacent
   tokens (e.g. `"hello"$USER'!'`) into a single `Word` with per-part
   quote tracking.

3. **Expansion tokens** -- `parse_expansion_token()`: Parses VARIABLE,
   PARAM_EXPANSION, COMMAND_SUB, and ARITH_EXPANSION tokens into
   expansion AST nodes. The `${...}` operator grammar itself
   (`${var:-default}`, `${arr[@]:1:2}`, ...) lives in the single shared
   parser `psh/expansion/param_parser.py`; WordBuilder just strips the
   delimiters and delegates, so the AST carries fully classified
   (parameter, operator, word) triples.

### Nested command/process substitutions carry a parsed Program

`CommandSubstitution` and `ProcessSubstitution` (`ast_nodes/words.py`) carry
`program` (the body parsed into a `Program`) **and** `source` (the raw inner
text). For modern `$(...)`/`<(...)`/`>(...)`, `WordBuilder` parses the body at
the OUTER parse via `support/nested_parse.py::parse_nested_command` (bound to
the active `ParserContext` for line-offset and depth accounting). So invalid
nested syntax (`echo $(if)`) is a `ParseError` that rejects the whole input
buffer before any command runs — matching bash's read-time validation, which
rejects even a substitution that would never execute (`false && echo $(if)`).

Deliberate properties of the nested parse:

- **Syntax-validation only, no alias expansion.** bash's read-time check does
  not consult the alias table (`$(beg …; done)` with `alias beg='… do'` is a
  read-time syntax error), and execution re-parses `source` against the RUNTIME
  alias table (`alias ll=x; echo $(ll)` runs `x`). So `program` is the
  alias-free syntactic view used for early rejection and analysis; command_sub /
  process_sub still run the body from `source`. This double-parse mirrors bash
  and keeps alias/byte/status/trap semantics byte-identical to before.
- **Legacy backticks are excluded** (`program=None`, not eagerly parsed): bash
  defers backtick parsing and continues around inner errors.
- Depth is capped (`nested_parse.MAX_SUBSTITUTION_NESTING`, `ParserContext.`
  `substitution_depth`) so an adversarially deep `$( $( … ) )` chain is a clean,
  bounded `ParseError` rather than an O(n²) re-parse cascade — the interim cost
  of extracting-and-reparsing bodies until the lexer gains token-level
  substitution recursion (a separate campaign).
- The combinator parser routes substitution nodes through the SAME `WordBuilder`
  entry points, so parser-differential AST parity holds by direct comparison.

**Known, documented divergences** (bash rejects at read time; psh validates at
runtime — these route through the raw-string operand/arithmetic engines, not the
Word AST, so they are out of scope until the expansion-subsystem structured
work): `${x:-$(if)}` (parameter-expansion word), `$(( $(if) ))` (arithmetic
operand), and `$(if)` inside a heredoc BODY. Also: a cmdsub-body syntax error in
`bash -c` exits 127 (a quirk of bash's `-c` handling); psh uses its uniform
syntax-error code 2. All are pinned in
`tests/conformance/bash/test_nested_substitution_timing_conformance.py`.

## Configuration

`ParserConfig` (`psh/parser/config.py`) is the parser's single configuration
object. **The production grammar is NOT feature-configurable**: compound
dispatch (`commands.py`, `control_structures.py`) calls the specialized
sub-parsers directly, so `[[ ]]` and `(( ))` are always accepted. The former
strict-POSIX / feature-gate fields (`parsing_mode`, `enable_arithmetic`,
`allow_bash_conditionals`, `allow_bash_arithmetic`) plus their
`strict_posix` / `is_feature_enabled` / `should_allow` /
`check_posix_compliance` methods were a façade — bypassed on every live
path — and were removed. So was the `collect_errors` error-collection mode:
it drove an unsafe recovery that returned a fabricated AST after a missing
required token, and its collected errors were never read. `consume()` now
always raises on the first unexpected token. POSIX/bash behavior that IS
honored lives in the lexer (`posix` tokenize mode) and runtime options, not
here.

```python
@dataclass
class ParserConfig:
    """Currently empty — the production parser has no options."""
```

`ParserConfig` is retained as the parser's single configuration object and
extension point (it threads through the factory, `ParserContext`, and every
sub-parser). `config.clone(**overrides)` delegates to `dataclasses.replace`,
so an unknown field name raises `TypeError` (a misspelled override no longer
silently no-ops). No live path passes a non-default config; `create_parser()`
/ `parse_with_heredocs()` always construct a default `ParserConfig()`.

The `parser-config` / `parser-mode` builtins do NOT drive `ParserConfig`; they
toggle the shell options that really affect lexing/parsing/expansion (`posix`,
`braceexpand`, `histexpand`).
