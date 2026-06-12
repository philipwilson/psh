# PSH Lexer: Programmer's Guide

> **Note (2026-06-11):** This guide describes the tree as of ~v0.27x, before
> the v0.285 module relocation and subsequent cleanups. In particular it
> references pre-relocation paths such as `psh/token_types.py`, `psh/token_transformer.py` (now under `psh/lexer/`), and `psh/brace_expansion.py` (now `psh/expansion/brace_expansion.py`).
> See the subsystem CLAUDE.md files for current structure.

This guide covers the lexer package in detail: its external API, internal
architecture, and the responsibilities of every source file.  It is aimed at
developers who need to modify the lexer, add new token types, or understand how
shell input becomes a token stream.

## 1. What the Lexer Does

The lexer converts a shell command string into a flat list of `Token` objects.
Each token carries a type (keyword, operator, word, etc.), a value, position
information, and optional metadata about quoting and expansions.

The lexer does **not** build an AST or evaluate anything.  Its output is
consumed by the parser, which produces the AST that the executor walks.

## 2. External API

The public interface is defined in `psh/lexer/__init__.py`.  The declared
public API (`__all__`) consists of five items.  Additional items are
importable from `psh.lexer` as convenience imports but are not part of the
public contract.  See `docs/guides/lexer_public_api.md` for the full
reference including API tiers and import guidance.

### 2.1 `tokenize()`

```python
from psh.lexer import tokenize

tokens = tokenize(
    input_string: str,
    strict: bool = True,
    shell_options: dict = None,
) -> List[Token]
```

This is the primary entry point.  It runs the full tokenization pipeline:

1. **Brace expansion** &mdash; `{a,b}` and `{1..5}` patterns are expanded
   before tokenization begins.  If expansion fails, the original string is used.
2. **Tokenization** &mdash; `ModularLexer` converts characters into tokens.
3. **Keyword normalisation** &mdash; `KeywordNormalizer` converts WORD tokens
   that appear at command position into their keyword token types (e.g.
   `WORD("if")` becomes `IF("if")`).
4. **Token transformation** &mdash; `TokenTransformer` validates context rules
   such as `;;` only being legal inside `case` statements.

Parameters:

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `input_string` | &mdash; | The shell command text to tokenize. |
| `strict` | `True` | `True` selects batch mode (scripts); `False` selects interactive mode, which enables error recovery and relaxed validation. |
| `shell_options` | `None` | A dict of shell option overrides.  Currently the only key inspected is `'extglob'`; when truthy, extended glob patterns like `?(...)` and `!(...)` are recognised. |

Returns a `List[Token]`.  The final token is always `Token(type=EOF)`.

### 2.2 `tokenize_with_heredocs()`

```python
from psh.lexer import tokenize_with_heredocs

tokens, heredoc_map = tokenize_with_heredocs(
    input_string: str,
    strict: bool = True,
    shell_options: dict = None,
)
```

Same pipeline as `tokenize()`, but uses `HeredocLexer` to collect heredoc
bodies.  The return value is a tuple:

- `tokens` &mdash; the token list (same shape as `tokenize()`).
- `heredoc_map` &mdash; a `dict` mapping each heredoc delimiter string to a
  dict with keys `'quoted'` (bool) and `'content'` (str).

The caller passes both values to the parser's `parse_with_heredocs()`.

### 2.3 `ModularLexer`

```python
from psh.lexer import ModularLexer, LexerConfig

config = LexerConfig.create_batch_config()
lexer = ModularLexer(input_string, config=config)
tokens = lexer.tokenize()
```

Direct access to the core tokenisation engine.  Most callers should use
`tokenize()` instead, since it also runs brace expansion, keyword
normalisation, and token transformation.  Direct `ModularLexer` access is
useful for tests and tools that need raw tokens.

### 2.4 `LexerConfig`

Configuration dataclass with 60+ settings controlling feature enablement, error
handling, and compatibility modes.  Four factory methods cover common
scenarios:

| Factory | Purpose |
|---------|---------|
| `LexerConfig.create_batch_config()` | Strict mode for scripts.  Default. |
| `LexerConfig.create_interactive_config()` | Relaxed mode for the REPL. |
| `LexerConfig.create_debug_config()` | Enables tracing and logging. |
| `LexerConfig.create_posix_config()` | Strict POSIX compliance (ASCII identifiers only). |

Commonly adjusted settings include `enable_extglob`, `posix_mode`,
`strict_mode`, and `enable_process_substitution`.

### 2.5 `LexerError`

```python
from psh.lexer import LexerError
```

Exception raised for unrecoverable tokenization errors.  Carries position
context (line, column, offset) for diagnostic messages.

### 2.6 Convenience imports (not in `__all__`)

The following are importable from `psh.lexer` but are not part of the
declared public API.  They are internal implementation details kept as
convenience imports to avoid churn.  New code should prefer the canonical
submodule paths.

**Constants** (from `psh.lexer.constants`):
`KEYWORDS`, `OPERATORS_BY_LENGTH`, `SPECIAL_VARIABLES`,
`DOUBLE_QUOTE_ESCAPES`, `WORD_TERMINATORS`

**Unicode utilities** (from `psh.lexer.unicode_support`):
`is_identifier_start`, `is_identifier_char`, `is_whitespace`,
`normalize_identifier`, `validate_identifier`

**Token metadata** (from `psh.lexer.token_parts`):
`TokenPart`, `RichToken`

**State** (from `psh.lexer.state_context`):
`LexerContext`

**Submodule-only** (removed from package-level imports; import from
`psh.lexer.position`):
`Position`, `LexerState`, `PositionTracker`, `LexerErrorHandler`,
`RecoverableLexerError`

### 2.7 The `Token` class

`Token` is defined in `psh/token_types.py` (outside the lexer package) and
used throughout the shell.  Its fields:

```
type: TokenType            # Enum member (WORD, PIPE, IF, REDIRECT_OUT, ...)
value: str                 # The text of the token
position: int              # Byte offset in the source string
end_position: int          # Byte offset after the last character
quote_type: Optional[str]  # The quoting character: ' " $' or None
line: Optional[int]        # 1-based line number
column: Optional[int]      # 1-based column number
adjacent_to_previous: bool # True when no whitespace separates this token from the previous one
is_keyword: bool           # Set by KeywordNormalizer
parts: Optional[List[TokenPart]]  # Fine-grained sub-token structure
```

`TokenType` is an enum with ~70 members covering words, operators,
redirections, keywords, expansion markers, assignment operators, and
structural delimiters.  See `psh/token_types.py` for the full list.


## 3. Architecture

### 3.1 Tokenisation pipeline

```
Input string
     |
     v
BraceExpander.expand_line()       # {a,b} -> a b   (pre-processing)
     |
     v
ModularLexer.tokenize()           # characters -> raw tokens
     |
     v
KeywordNormalizer.normalize()     # WORD("if") -> IF("if") at command position
     |
     v
TokenTransformer.transform()      # validate ;; context, etc.
     |
     v
List[Token]                        # output
```

`tokenize_with_heredocs()` substitutes `HeredocLexer` for `ModularLexer`.
`HeredocLexer` wraps `ModularLexer` and additionally collects heredoc bodies.

### 3.2 Inside ModularLexer

The core loop in `ModularLexer.tokenize()` repeats until EOF:

1. **Skip whitespace** &mdash; spaces and tabs are consumed silently.
2. **Try quotes and expansions** &mdash; if the current character is a quote
   character or `$`, delegate to `UnifiedQuoteParser` or `ExpansionParser`.
3. **Try recognisers** &mdash; iterate through registered recognisers in
   priority order.  The first one whose `can_recognize()` returns `True` gets
   to call `recognize()` and emit a token.
4. **Fallback** &mdash; if nothing matched, consume characters until a word
   terminator and emit a WORD token.

### 3.3 Recogniser registry

Recognisers are pluggable objects registered in a `RecognizerRegistry`.  Each
has a numeric priority; higher priorities are tried first.  The default set:

| Recogniser | Priority | Recognises |
|------------|----------|------------|
| `ProcessSubstitutionRecognizer` | 160 | `<(...)` and `>(...)` |
| `OperatorRecognizer` | 150 | All shell operators, context-aware |
| `LiteralRecognizer` | 70 | Words, identifiers, numbers, globs, assignments |
| `CommentRecognizer` | 60 | `# ...` to end of line |
| `WhitespaceRecognizer` | 30 | Spaces and tabs (returns `None` to skip) |

Recognisers return either `(Token, new_position)` on success, `(None, new_position)` to silently skip input (whitespace, comments), or `None` to
decline.

### 3.4 State tracking

`LexerContext` (in `state_context.py`) is the single mutable state object
shared across the lexer and its recognisers.  It tracks:

- Nesting depths for `()`, `[]`, `{}`, `[[]]`, and `$(())`.
- A quote stack (for nested quoting inside expansions).
- Command-position flag (whether the next word could be a keyword).
- Array-assignment state.
- POSIX mode flag.

### 3.5 Quote and expansion parsing

Two dedicated parsers handle the complex syntax of quoted strings and dollar
expansions:

- **`UnifiedQuoteParser`** &mdash; driven by a `QuoteRules` dict that maps
  each quote character to its behaviour (whether expansions are allowed,
  which escape sequences are valid, etc.).  Handles single quotes, double
  quotes, ANSI-C quotes (`$'...'`), and backticks.

- **`ExpansionParser`** &mdash; dispatches on the character after `$`:
  - `$VAR` or `${VAR}` &rarr; variable / parameter expansion.
  - `$(cmd)` &rarr; command substitution.
  - `$((expr))` &rarr; arithmetic expansion.
  - `$'...'` &rarr; ANSI-C quoting (delegated to quote parser).

Both parsers use stateless helper functions from `pure_helpers.py` for
delimiter matching and escape processing.

### 3.6 Keyword normalisation

After tokenisation, `KeywordNormalizer` makes a single pass over the token
list.  It tracks command position (reset after `;`, `|`, `&&`, `||`,
newlines, and certain keywords) and converts WORD tokens whose values are
reserved words into their keyword token types.  It also handles the
context-sensitive `in` keyword, which is only valid after `for`, `case`, or
`select`.

### 3.7 Heredoc support

`HeredocLexer` (in `heredoc_lexer.py`) wraps `ModularLexer` and adds
heredoc-body collection.  When it encounters `<<` or `<<-` operators, it
registers the delimiter with a `HeredocCollector` and then collects subsequent
lines of input until the delimiter appears alone on a line.  The collected
content is returned in the `heredoc_map` alongside the token list.


## 4. Source File Reference

The files below are all under `psh/lexer/`.  Line counts are approximate.

### 4.1 Package entry point

#### `__init__.py` (~150 lines)

Defines `tokenize()` and `tokenize_with_heredocs()`, re-exports the public
API, and declares `__all__`.  This is the only file external code needs to
import from.

### 4.2 Core tokenisation

#### `modular_lexer.py` (~650 lines)

The `ModularLexer` class.  Coordinates position tracking, state management,
quote/expansion parsing, and the recogniser registry.  The main loop lives in
`tokenize()`, which calls `_skip_whitespace()`,
`_try_quotes_and_expansions()`, `_try_recognizers()`, and
`_handle_fallback_word()` in sequence.  Also maintains command-position
tracking (`_update_command_position_context()`) and array-assignment detection
(`_is_inside_potential_array_assignment()`).

#### `position.py` (~400 lines)

Defines `Position`, `LexerState`, `LexerError`, `RecoverableLexerError`,
`LexerConfig`, `LexerErrorHandler`, and `PositionTracker`.

`LexerConfig` is the largest class here, with 60+ fields covering feature
toggles, error-handling policy, performance settings, and compatibility modes.
The four factory methods (`create_batch_config`, `create_interactive_config`,
`create_debug_config`, `create_posix_config`) set sensible defaults for
common scenarios.

`PositionTracker` wraps the input string and provides `current_char()`,
`peek_char()`, `advance()`, and `get_position()` while maintaining
line/column counts.

#### `state_context.py` (~170 lines)

The `LexerContext` dataclass: unified mutable state for the lexer.  Tracks
nesting depths (brackets, parentheses, braces, double-brackets, arithmetic),
a quote stack, command-position flags, recent control keywords, and
array-assignment state.  Provides helper methods like `push_quote()`,
`pop_quote()`, `enter_arithmetic()`, `exit_arithmetic()`, and
`get_nesting_summary()`.

### 4.3 Recognisers

All recogniser files live under `psh/lexer/recognizers/`.

#### `base.py` (~115 lines)

Abstract base classes for the recogniser pattern:

- `TokenRecognizer` &mdash; requires `priority` (property), `can_recognize()`,
  and `recognize()`.
- `ContextualRecognizer` &mdash; adds `is_valid_in_context()` for
  context-dependent validation.

#### `registry.py` (~230 lines)

`RecognizerRegistry` manages a sorted list of recogniser instances.
`register()` adds a recogniser; `recognize()` iterates in priority order and
returns the first successful result.  `setup_default_recognizers()` wires up
the standard six recognisers.

#### `operator.py` (~350 lines)

`OperatorRecognizer` (priority 150).  Performs greedy longest-match against
`OPERATORS_BY_LENGTH`.  Special logic handles:

- FD duplication (`2>&1`, `N>&M`).
- Context-dependent meaning of `<` and `>` (redirection vs. comparison inside
  `[[ ]]`).
- `))` only valid inside arithmetic.
- `=~`, `==`, `!=` only valid inside `[[ ]]`.
- Operator enable/disable checks against `LexerConfig`.

#### `literal.py` (~930 lines)

`LiteralRecognizer` (priority 70).  The largest recogniser, handling words,
identifiers, numbers, glob patterns, extended globs, and variable
assignments.  Key responsibilities:

- Collecting word characters until a terminator.
- Recognising `NAME=value` and `NAME[key]=value` assignment patterns.
- Handling glob brackets (`[...]`) and extended globs (`?(...)`, `!(...)`,
  etc.) when `extglob` is enabled.
- Classifying the collected text as WORD, ASSIGNMENT_WORD, or a number type.
- Delegating to the quote and expansion parsers when quotes or `$` appear
  mid-word.

#### `whitespace.py` (~60 lines)

`WhitespaceRecognizer` (priority 30).  Skips spaces, tabs, and Unicode
whitespace.  Does not handle newlines (those are operators).  Returns
`(None, new_pos)` to signal that input was consumed but no token emitted.

#### `comment.py` (~80 lines)

`CommentRecognizer` (priority 60).  Recognises `#` at the start of input or
after whitespace/operators, and skips to end of line.  Returns
`(None, new_pos)`.

#### `process_sub.py` (~115 lines)

`ProcessSubstitutionRecognizer` (priority 160).  Matches `<(` and `>(`
followed by balanced parentheses.  Emits `PROCESS_SUB_IN` or
`PROCESS_SUB_OUT` tokens containing the command text.

#### `__init__.py` (~20 lines)

Re-exports all recogniser classes and the `setup_default_recognizers()`
function.

### 4.4 Quote and expansion parsing

#### `quote_parser.py` (~390 lines)

`UnifiedQuoteParser` with rules-based handling of all quote types.  The
`QUOTE_RULES` dict maps each quote character to a `QuoteRules` dataclass
specifying whether expansions and escape sequences are allowed.

Key methods: `parse_quoted_string()` (full quote parsing with expansion
support), `parse_simple_quoted_string()` (fast path for single quotes),
`is_quote_character()`.

#### `expansion_parser.py` (~405 lines)

`ExpansionParser` handles everything that starts with `$`:

- `_parse_simple_variable()` &mdash; `$VAR` and special parameters.
- `_parse_brace_expansion()` &mdash; `${VAR}`, `${VAR:-default}`, etc.
- `_parse_command_or_arithmetic()` &mdash; distinguishes `$()` from `$(())`.
- `_parse_command_substitution()` &mdash; `$(cmd)`.
- `_parse_arithmetic_expansion()` &mdash; `$((expr))`.
- `parse_backtick_substitution()` &mdash; `` `cmd` ``.

Uses `pure_helpers.py` for balanced-delimiter matching.

### 4.5 Heredoc support

#### `heredoc_lexer.py` (~180 lines)

`HeredocLexer` wraps `ModularLexer` for multi-line input with heredocs.
Detects `<<` and `<<-` operators, registers heredoc delimiters, collects
body lines, and returns `(tokens, heredoc_map)`.

#### `heredoc_collector.py` (~155 lines)

`HeredocCollector` manages the state machine for heredoc collection.
Tracks pending heredocs, processes incoming lines against delimiters,
handles the `<<-` tab-stripping variant, and stores collected content.

### 4.6 Keyword handling

#### `keyword_normalizer.py` (~150 lines)

`KeywordNormalizer` performs a post-tokenisation pass that converts WORD
tokens to keyword types at command position.  Tracks state across semicolons,
pipes, logical operators, and newlines.  Special-cases the `in` keyword
(only valid after `for`/`case`/`select`).

#### `keyword_defs.py` (~85 lines)

Shared keyword data and helper functions:

- `KEYWORD_TYPE_MAP` &mdash; maps keyword strings to `TokenType` values.
- `matches_keyword()`, `matches_keyword_type()`, `matches_any_keyword()`
  &mdash; safe comparison functions (preferred over raw string equality).
- `KeywordGuard` &mdash; caches keyword comparisons for a token.

### 4.7 Support modules

#### `constants.py` (~80 lines)

Data-only module defining `KEYWORDS`, `OPERATORS_BY_LENGTH`,
`SPECIAL_VARIABLES`, `VARIABLE_START_CHARS`, `VARIABLE_CHARS`,
`DOUBLE_QUOTE_ESCAPES`, and `WORD_TERMINATORS`.

#### `pure_helpers.py` (~660 lines)

Stateless helper functions used by the quote parser, expansion parser, and
recognisers:

- **Delimiter matching**: `find_closing_delimiter()`,
  `find_balanced_parentheses()`, `find_balanced_double_parentheses()`.
- **Extraction**: `extract_variable_name()`, `extract_quoted_content()`,
  `read_until_char()`.
- **Escape processing**: `handle_escape_sequence()`,
  `handle_ansi_c_escape()` (supports `\xHH`, `\0NNN`, `\uHHHH`,
  `\UHHHHHHHH`).
- **Detection**: `is_comment_start()`, `is_inside_expansion()`,
  `find_word_boundary()`.
- **Scanning**: `scan_whitespace()`, `find_operator_match()`.
- **Validation**: `validate_brace_expansion()`.

#### `token_parts.py` (~45 lines)

`TokenPart` (metadata for one piece of a composite token) and `RichToken`
(a `Token` subclass carrying a list of `TokenPart` objects).

#### `unicode_support.py` (~130 lines)

Character-classification functions with POSIX and Unicode modes.  See
section 2.6 above.

### 4.8 Validator modules (inactive)

The following files exist in the package but are not called from any active
code path.  They were part of an experimental enhanced-validation subsystem
and are candidates for removal:

| File | Lines | Purpose |
|------|-------|---------|
| `expansion_validator.py` | ~450 | Validates expansion syntax with detailed diagnostics. |
| `quote_validator.py` | ~365 | Validates quote pairing and matching. |
| `token_stream_validator.py` | ~425 | Integrates expansion, quote, and bracket validation across a token stream. |
| `context_recognizer.py` | ~200 | Abstract base for context-aware recognisers with semantic enhancement. |
| `enhanced_context.py` | ~270 | Extended `LexerContext` with parser hints and context history. |


## 5. Common Tasks

### 5.1 Adding a new operator

1. Add the operator string and its `TokenType` to `OPERATORS_BY_LENGTH` in
   `constants.py`, keyed by character length.
2. If the operator needs a new `TokenType`, add it to the `TokenType` enum in
   `psh/token_types.py`.
3. If the operator requires context-sensitive behaviour (e.g. only valid
   inside `[[ ]]`), add logic to `OperatorRecognizer.is_valid_in_context()`.
4. If the operator can be disabled by configuration, add a check to
   `OperatorRecognizer._is_operator_enabled()`.
5. Add tests in `tests/unit/lexer/`.

### 5.2 Adding a new keyword

1. Add the keyword string to `KEYWORDS` in `constants.py`.
2. Add a `TokenType` member in `psh/token_types.py`.
3. Add the mapping to `KEYWORD_TYPE_MAP` in `keyword_defs.py`.
4. If the keyword has special context rules (like `in`), add logic to
   `KeywordNormalizer`.
5. Add tests.

### 5.3 Adding a new recogniser

1. Create a class inheriting from `TokenRecognizer` (or
   `ContextualRecognizer` if context matters):

   ```python
   class MyRecognizer(TokenRecognizer):
       @property
       def priority(self) -> int:
           return 85  # between keywords (90) and literals (70)

       def can_recognize(self, input_text, pos, context):
           return input_text[pos] == '@'

       def recognize(self, input_text, pos, context):
           # return (Token, new_pos) or None
           ...
   ```

2. Register it in `setup_default_recognizers()` in `recognizers/registry.py`.
3. Add tests.

### 5.4 Adding a new quote type

1. Add a `QuoteRules` entry to the `QUOTE_RULES` dict in `quote_parser.py`:

   ```python
   QUOTE_RULES['~'] = QuoteRules(
       allow_expansions=False,
       allow_escapes=False,
       escape_chars=set(),
       name="tilde"
   )
   ```

2. Update `UnifiedQuoteParser.is_quote_character()` if needed.
3. Add tests.

### 5.5 Debugging tokenisation

```bash
# Show all tokens with types and positions
python -m psh --debug-tokens -c 'echo "hello $USER"'

# Show expansion tracing
python -m psh --debug-expansion -c 'echo ${HOME:-/tmp}'
```

For programmatic debugging, instantiate `ModularLexer` directly and inspect
its `tokens` list:

```python
from psh.lexer import ModularLexer, LexerConfig
config = LexerConfig.create_debug_config()
lexer = ModularLexer('echo "hello $USER"', config=config)
for tok in lexer.tokenize():
    print(f"{tok.type.name:20s} {tok.value!r:20s} line={tok.line} col={tok.column}")
```


## 6. Design Rationale

### Why a recogniser registry instead of a monolithic state machine?

A single large state machine becomes difficult to extend and test.  The
recogniser pattern lets each token type be implemented, tested, and debugged
in isolation.  New token types can be added without modifying existing code.

### Why is brace expansion done before tokenisation?

Brace expansion can create multiple tokens from a single pattern (`{a,b}`
becomes `a b`).  Doing it before tokenisation keeps the lexer free from
concerns about token multiplication.

### Why is keyword normalisation a separate pass?

Whether a word is a keyword depends on its position in the command, which is
difficult to determine character-by-character during tokenisation.  A
separate pass over the completed token list can make these decisions with full
context.

### Why are quotes and expansions handled separately from recognisers?

Quote and expansion parsing involve recursive, context-sensitive state
(nested quoting inside command substitutions inside double quotes, etc.).
Separating them into dedicated parsers with their own entry points keeps the
recognisers simple and focused on flat token boundaries.

### Why does `LiteralRecognizer` exist alongside the fallback?

The fallback in `ModularLexer._handle_fallback_word()` is a safety net.
`LiteralRecognizer` handles the vast majority of word tokenisation,
including complex cases like array assignments, extended globs, and
mid-word quote transitions.  The fallback catches anything the recogniser
declines.


## 7. File Dependency Graph

```
__init__.py
├── modular_lexer.py
│   ├── state_context.py
│   ├── position.py
│   ├── expansion_parser.py
│   │   └── pure_helpers.py
│   ├── quote_parser.py
│   │   ├── pure_helpers.py
│   │   └── token_parts.py
│   └── recognizers/
│       ├── registry.py
│       │   └── base.py
│       ├── operator.py ─── constants.py
│       ├── literal.py ──── constants.py, unicode_support.py
│       ├── whitespace.py ─ unicode_support.py
│       ├── comment.py
│       └── process_sub.py
├── keyword_normalizer.py ── keyword_defs.py
├── heredoc_lexer.py
│   ├── modular_lexer.py
│   └── heredoc_collector.py
├── constants.py
├── token_parts.py
├── unicode_support.py
└── position.py
```

External dependencies (outside the lexer package):
- `psh/token_types.py` &mdash; `Token` and `TokenType` definitions.
- `psh/brace_expansion.py` &mdash; `BraceExpander` (pre-processing).
- `psh/token_transformer.py` &mdash; `TokenTransformer` (post-processing).
