# Lexer Subsystem

This document provides guidance for working with the PSH lexer subsystem.

## Architecture Overview

The lexer transforms shell command strings into token streams using a **modular recognizer pattern**. The main entry point is `tokenize()` in `__init__.py`, which orchestrates:

1. Tokenization via `ModularLexer`
2. Keyword normalization (`KeywordNormalizer`)
3. Word fusion (`word_fusion.fuse_words`)

```
Input String → ModularLexer → KeywordNormalizer → fuse_words → Tokens
```

Steps 2–3 are the shared `_post_lex` pipeline (`__init__.py#_post_lex`).
**Word fusion** runs AFTER normalization: it collapses each maximal run of
adjacent word-like tokens (the literal run plus every quote/expansion token)
into ONE `WORD` token carrying the run's parts, so the parser sees one token
per shell word and never re-assembles a composite. It replaced the retired
parser-side `TokenStream.peek_composite_sequence`; running after
normalization means reserved words are already retyped and excluded from the
word-like set (see `__init__.py#_post_lex` and `word_fusion.py#fuse_words`).

There is no post-lexing validation pass: context rules like "`;;` only
inside `case`" are enforced by the parser (a `TokenTransformer` layer that
appeared to validate this was removed as dead code — it appended every
token unchanged).

Note: brace expansion is **NOT** a lexer pass. Since v0.678 it runs at the
Word-expansion stage (`ExpansionManager.brace_expand_word` →
`psh/expansion/brace_expansion_words.py` `WordBraceExpander`), where bash
performs it — so `{a,b}` stays one WORD in the token stream and expands at
execution time reading the LIVE `braceexpand` option. The old token-stream
`TokenBraceExpander` (and its same-stream `set`/`shopt` toggle scanner) were
retired.

## Key Files

| File | Purpose |
|------|---------|
| `__init__.py` | Entry point: `tokenize()` and `tokenize_with_heredocs()` (shared `_post_lex` pipeline) |
| `modular_lexer.py` | Core tokenization engine (~650 lines) |
| `state_context.py` | `LexicalState` (+ `LexicalRole`/`CasePhase`) - unified state; `LexerContext` alias |
| `command_position.py` | Command-position vocabulary for all THREE tracking machines (lexer pass, normalizer, cmdsub scanner). Transition tables + asymmetries diagram: `docs/architecture/command_position.md` |
| `cmdsub_scanner.py` | Grammar-aware `$(...)` extent scanner (`find_command_substitution_end` + maintenance contract) |
| `constants.py` | Keywords and special variables (operators live in `OperatorRecognizer.OPERATORS`) |
| `position.py` | Position tracking, `LexerConfig`, error classes |

### Recognizers (`recognizers/`)

| File | Recognizes |
|------|-----------|
| `operator.py` | Shell operators (`|`, `&&`, `>>`, etc.) |
| `literal.py` | Words, identifiers, assignments — collect loop with forward `WordShape` state (~330 lines) |
| `word_scanners.py` | Pure mini-scanners (`scan_glob_bracket`, `scan_assignment_prefix`, `scan_extglob_group`, `scan_inline_ansi_c`) + `WordShapeTracker` + the assignment-prefix map |
| `comment.py` | `# comments` |
| `process_sub.py` | Process substitution `<()` and `>()` |
| `registry.py` | Recognizer registration + ordered dispatch (registration order = dispatch order) |

### Support Modules

| File | Purpose |
|------|---------|
| `expansion_parser.py` | Parse `${}`, `$()`, `$(())`, backticks |
| `quote_parser.py` | Parse quoted strings (single, double, ANSI-C) |
| `pure_helpers.py` | Stateless char-level helpers (`QuoteState`, delimiter matching, escape decoding) |
| `heredoc_lexer.py` | Heredoc tokenization |
| `heredoc_collector.py` | `HeredocCollector` - gathers pending heredoc bodies line-by-line |
| `token_parts.py` | `TokenPart` (per-part word metadata; RichToken retired) |
| `unicode_support.py` | Unicode identifier handling |
| `token_types.py` | `Token` and `TokenType` definitions (shared with the parser) |
| `token_stream.py` | `TokenStream` - positioned token cursor + shared arithmetic-expression collector |
| `keyword_normalizer.py` | `KeywordNormalizer` - retypes reserved words in command position (post-lex step 2) |
| `word_fusion.py` | `fuse_words` - post-normalization word fusion, adjacent word-like tokens → one WORD-with-parts (post-lex step 3) |

## Core Patterns

### 1. Modular Recognizer Pattern

Recognizers are tried in **registration order** — the first to match wins.
There is no priority sorting; the dispatch sequence is declared once, in
`ModularLexer._setup_recognizers`:

```python
# In recognizers/registry.py
class RecognizerRegistry:
    def register(self, recognizer): ...   # appended to the dispatch order
    def recognize(self, input_text, pos, context): ...  # tries in that order

# Dispatch order (ModularLexer._setup_recognizers), the single declaration:
# 1. ProcessSubstitutionRecognizer  (before operators, so `<(` isn't `<`)
# 2. OperatorRecognizer             (greedy matching for multi-char operators)
# 3. LiteralRecognizer              (words, identifiers, assignments)
# 4. CommentRecognizer              (`#` to end of line)
# 5. OperatorDebrisWordRecognizer   (tried last; debris words ], +=, =, [)
#
# Whitespace is NOT a recognizer: the main loop skips it directly via
# _skip_whitespace() before dispatch (the old WhitespaceRecognizer was dead
# code and was removed).
```

### 2. LexicalState

`LexicalState` (`state_context.py`) tracks the cross-token state the
recognizers consult. Its single mutator is
`command_position.advance_lexical_state` — the one lexer-stage
command-position / case transition function.

```python
class LexicalState:
    role: LexicalRole              # command-position axis (COMMAND_POSITION / ARGUMENT)
    bracket_depth: int = 0         # [[ ]] nesting
    arithmetic_depth: int = 0      # $((...)) / (( )) nesting
    posix_mode: bool = False
    case_depth: int = 0            # case..esac nesting
    case_expecting_in: bool = False  # between `case` and `in`
    in_case_pattern: bool = False    # collecting case patterns
    # command_position (bool) and case_phase (CasePhase view) are derived
    # read-properties; recognizers read context.command_position unchanged.
```

The command-position axis is a `LexicalRole` enum; `command_position` is a
derived bool property. The case bits `case_expecting_in` and `in_case_pattern`
are INDEPENDENT (a malformed `case x ;;` sets both), so they are stored
separately rather than collapsed into one phase enum; `case_phase` is a
read-only `CasePhase` summary. `LexerContext` remains as a backward-compatible
alias of `LexicalState` (public import + the `command_position=` construction
kwargs stay valid).

Quote state is NOT tracked here: quotes are consumed whole by
`UnifiedQuoteParser` within a single token, so no cross-token quote
state exists.

### 3. Token Recognition Flow

```python
# In modular_lexer.py — the tokenize() loop tries, in order:
def tokenize(self):
    while ...:
        if self._skip_whitespace(): continue           # 1. Whitespace
        if self._try_quotes_and_expansions(): continue # 2. Quotes / $, ` → quote_parser / expansion_parser
        if self._try_recognizers(): continue           # 3. Recognizers in dispatch order
        raise RuntimeError(...)                        # 4. Unreachable (census-verified) — fail loudly
```

The recognizer pipeline (step 3) is uniform — there is no special
"fallback" step. Its last member,
`OperatorDebrisWordRecognizer` (registered last, in
`recognizers/operator_debris.py`), is tried strictly last and collects
operator-debris words (`], +=, =, [...`) that the literal recognizer
rejects as word starts. (This was historically a separate step-4
`_handle_fallback_word` method; promoted to a registered recognizer so
the pipeline has no special cases.)

The loop is TOTAL: an instrumented census established that the
operator-debris recognizer is live for exactly four word-start character
classes (`]`, `+`, `=`, `[` — see its docstring) and that nothing reaches
the final branch, which therefore raises instead of silently dropping a
character.

## Common Tasks

### Adding a New Operator

1. Add to `OperatorRecognizer.OPERATORS` in `recognizers/operator.py`
   (the single live operator table; matching is longest-first):
```python
OPERATORS = {
    '&&': TokenType.AND_AND,
    '&': TokenType.AMPERSAND,
    # Add here
}
```

2. Add `TokenType` in `psh/lexer/token_types.py` if needed

3. Add tests in `tests/unit/lexer/`

### Adding a New Keyword

1. Add to `KEYWORDS` in `constants.py`.
2. Add a `TokenType` member in `psh/lexer/token_types.py`.
3. Add the mapping to `KEYWORD_TYPE_MAP` in `keyword_defs.py`.
4. `KeywordNormalizer` (the post-tokenization pass) will automatically
   recognize it at command position.
5. If the keyword has special context rules (like `in`), add logic to
   `KeywordNormalizer`.

### Adding a New Recognizer

1. Create class inheriting from `TokenRecognizer`:
```python
# In recognizers/my_recognizer.py
class MyRecognizer(TokenRecognizer):
    def can_recognize(self, input_text, pos, context) -> bool:
        # Quick check if this recognizer applies
        return input_text[pos] == '@'

    def recognize(self, input_text, pos, context) -> Optional[Tuple[Token, int]]:
        # Return (token, new_position) or None
        ...
```
(There is no `priority` — dispatch order is registration order. There is no
keyword recognizer either: keywords are normalized from WORD tokens by the
`KeywordNormalizer` post-pass.)

2. Register it in `ModularLexer._setup_recognizers()` (in `modular_lexer.py`)
   **at the position in the list where it should be tried** — before any
   recognizer it must pre-empt, after any that should win over it.
   `recognizers/__init__.py` only re-exports classes; adding one there does
   not activate it. Optionally add the re-export for discoverability.

### Tokens are immutable

`Token` is `@dataclass(frozen=True)`: once the
lexer emits a token it is never mutated. Stages that need a changed token build
a new one with `dataclasses.replace` — the `KeywordNormalizer` (WORD → keyword
type), the heredoc lexer (attaching `heredoc_key`), and in-parser retypes all
do this. `position`/`end_position` are the canonical stored offsets; `span`
(a `SourceSpan`) is a derived read-only view. `SourceMap` (`position.py`) is the
one offset → (line, column) + line-text service (the lexer's `PositionTracker`
and the parser's error context both read it).

## Key Implementation Details

### Quote Handling

- Single quotes: No expansion, literal content
- Double quotes: Variable expansion, command substitution, escape sequences
  (`\$`, `\\`, `\"`, `` \` `` only — other backslashes stay literal)
- ANSI-C quotes (`$'...'`): Escape sequences like `\n`, `\t`
- Quotes are consumed whole by `UnifiedQuoteParser` (`QUOTE_RULES` defines
  per-context behavior; escape semantics live in
  `pure_helpers.handle_escape_sequence`)

### Expansion Parsing

`ExpansionParser` handles:
- `$VAR` and `${VAR}` - variable expansion
- `${VAR:-default}` - parameter expansion with operators
- `$(command)` - command substitution
- `$((expr))` - arithmetic expansion
- `` `command` `` - backtick substitution

### Array Assignment Detection

The lexer detects `arr[key]=value` and `arr=(a b c)` patterns:
- `build_assignment_prefix_map` (in `recognizers/word_scanners.py`) marks
  every position inside a confirmed `NAME[...]=` subscript in one O(n)
  pass; the map is cached on the `LexicalState` and shared by the quote
  dispatch and the literal recognizer
- `WordShapeTracker` (same module) maintains the forward word shape
  (`NEUTRAL → ASSIGN_NAME → ASSIGN_VALUE`) so the collect loop knows when
  `=` continues an assignment; `UnmatchedBracketTracker` keeps `]`, `=`,
  and quotes inside open subscripts part of the word

## Testing

```bash
# Run lexer unit tests
python -m pytest tests/unit/lexer/ -v

# Test specific recognizer
python -m pytest tests/unit/lexer/test_token_recognizers_comprehensive.py -v

# Debug tokenization
python -m psh --debug-tokens -c "echo hello"
```

## Common Pitfalls

1. **Greedy Operator Matching**: Operators are matched longest-first. `>>=` matches before `>>` before `>`.

2. **Context-Sensitive Keywords**: `if` is only a keyword at command position. `echo if` tokenizes `if` as WORD. Matching is also **case-sensitive** (like bash): `IF` is always a plain WORD.

3. **Quote Nesting**: Double quotes can contain `$()` which can contain more quotes. Track depth carefully.

4. **Array Assignment Quotes**: `arr["key"]=value` - quotes inside `[]` are part of the key, not separate tokens.

5. **Heredoc Interaction**: Heredocs are collected separately. Use `tokenize_with_heredocs()` when needed.

## Debug Options

```bash
python -m psh --debug-tokens    # Show all tokens with types and positions
python -m psh --debug-expansion # Trace expansion parsing
```
