# Lexer Public API Reference

**As of v0.177.0** (post-cleanup)

This document describes the public API of the `psh.lexer` package: the
items declared in `__all__`, their signatures, and guidance on internal
imports that are available but not part of the public contract.

## Public API (`__all__`)

The declared public API consists of five items:

```python
__all__ = [
    'ModularLexer', 'tokenize', 'tokenize_with_heredocs',
    'LexerConfig',
    'LexerError',
]
```

### `tokenize()`

```python
from psh.lexer import tokenize

tokens = tokenize(
    input_string: str,
    strict: bool = True,
    shell_options: dict = None,
) -> List[Token]
```

Primary entry point for shell tokenization. Runs the full pipeline:

1. **Brace expansion** -- `{a,b}` and `{1..5}` patterns are expanded
   before tokenization. If expansion fails, the original string is used.
2. **Tokenization** -- `ModularLexer` converts characters into tokens.
3. **Keyword normalization** -- `KeywordNormalizer` converts WORD tokens
   at command position into keyword token types (e.g. `WORD("if")` becomes
   `IF("if")`).
Context rules such as `;;` only being legal inside `case` statements are
enforced by the parser, not by a lexer pass.

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `input_string` | -- | The shell command text to tokenize. |
| `strict` | `True` | `True` selects batch mode (scripts); `False` selects interactive mode with error recovery. |
| `shell_options` | `None` | Shell option overrides. Currently only `'extglob'` is inspected; when truthy, extended glob patterns are recognized. |

Returns a `List[Token]`. The final token is always `Token(type=EOF)`.

### `tokenize_with_heredocs()`

```python
from psh.lexer import tokenize_with_heredocs

tokens, heredoc_map = tokenize_with_heredocs(
    input_string: str,
    strict: bool = True,
    shell_options: dict = None,
)
```

Same pipeline as `tokenize()`, but uses `HeredocLexer` to collect heredoc
bodies. Returns a tuple:

- `tokens` -- the token list (same shape as `tokenize()`).
- `heredoc_map` -- a `dict` mapping each heredoc delimiter string to a
  dict with keys `'quoted'` (bool) and `'content'` (str).

### `ModularLexer`

```python
from psh.lexer import ModularLexer, LexerConfig

config = LexerConfig.create_batch_config()
lexer = ModularLexer(input_string, config=config)
tokens = lexer.tokenize()
```

Direct access to the core tokenization engine. Most callers should use
`tokenize()` instead, since it also runs brace expansion, keyword
normalization, and token transformation. Direct `ModularLexer` access is
useful for tests and tools that need raw tokens without post-processing.

### `LexerConfig`

Configuration dataclass controlling feature enablement, error handling,
and compatibility modes. Four factory methods cover common scenarios:

| Factory | Purpose |
|---------|---------|
| `LexerConfig.create_batch_config()` | Strict mode for scripts. Default. |
| `LexerConfig.create_interactive_config()` | Relaxed mode for the REPL. |
| `LexerConfig.create_debug_config()` | Enables tracing and logging. |
| `LexerConfig.create_posix_config()` | Strict POSIX compliance (ASCII identifiers only). |

Commonly adjusted settings include `enable_extglob`, `posix_mode`,
`strict_mode`, and `enable_process_substitution`.

### `LexerError`

```python
from psh.lexer import LexerError

try:
    tokens = tokenize(input_string)
except LexerError as e:
    print(f"Tokenization failed: {e}")
```

Exception raised for unrecoverable tokenization errors. Carries position
context (line, column, offset) for diagnostic messages.

## Convenience Imports (not in `__all__`)

The following items are importable from `psh.lexer` for convenience but
are **not** part of the declared public contract. They are internal
implementation details whose signatures may change without notice.

Existing code that imports these will continue to work; the imports are
kept specifically to avoid churn. New code should prefer the submodule
import paths listed below.

### Constants

| Import | Canonical path | Type |
|--------|---------------|------|
| `KEYWORDS` | `psh.lexer.constants` | `set` of shell reserved words |
| `OPERATORS_BY_LENGTH` | `psh.lexer.constants` | `dict[int, dict[str, TokenType]]` |
| `SPECIAL_VARIABLES` | `psh.lexer.constants` | `set` of single-char special parameters |
| `DOUBLE_QUOTE_ESCAPES` | `psh.lexer.constants` | `dict` of escape-sequence mappings |
| `WORD_TERMINATORS` | `psh.lexer.constants` | `set` of word-ending characters |

### Unicode Utilities

| Import | Canonical path |
|--------|---------------|
| `is_identifier_start` | `psh.lexer.unicode_support` |
| `is_identifier_char` | `psh.lexer.unicode_support` |
| `is_whitespace` | `psh.lexer.unicode_support` |
| `normalize_identifier` | `psh.lexer.unicode_support` |
| `validate_identifier` | `psh.lexer.unicode_support` |

### Token Metadata

| Import | Canonical path | Notes |
|--------|---------------|-------|
| `TokenPart` | `psh.lexer.token_parts` | Metadata for one piece of a composite token. |
| `RichToken` | `psh.lexer.token_parts` | `Token` subclass with a `parts` list of `TokenPart` objects. Zero production callers after v0.177.0. |

### State

| Import | Canonical path | Notes |
|--------|---------------|-------|
| `LexerContext` | `psh.lexer.state_context` | Mutable state object for the lexer (nesting depths, quote stack, etc.). |

## Submodule-Only Imports

These classes were previously exported via `__all__` but had zero callers
outside the lexer package. They have been removed from both `__all__` and
the package-level imports. Import them from their defining module:

```python
from psh.lexer.position import Position
from psh.lexer.position import LexerState
from psh.lexer.position import PositionTracker
from psh.lexer.position import LexerErrorHandler
from psh.lexer.position import RecoverableLexerError
```

| Class | Purpose |
|-------|---------|
| `Position` | Dataclass: `offset`, `line`, `column`. Consumers access positions via `token.position` and rarely need this class directly. |
| `LexerState` | Enum of lexer states (NORMAL, IN_WORD, IN_SINGLE_QUOTE, etc.). Internal to `LexerContext`. |
| `PositionTracker` | Tracks line/column as the lexer advances. Internal to `ModularLexer`. |
| `LexerErrorHandler` | Centralized error handling with configurable recovery. Internal to `ModularLexer`. |
| `RecoverableLexerError` | Error subclass for interactive-mode recovery. Never caught outside the lexer. |

## API Tiers Summary

| Tier | Scope | How to import | Stability guarantee |
|------|-------|---------------|-------------------|
| **Public** | `tokenize`, `tokenize_with_heredocs`, `ModularLexer`, `LexerConfig`, `LexerError` | `from psh.lexer import ...` | Stable. Changes are versioned. |
| **Convenience** | Constants, unicode helpers, `TokenPart`, `RichToken`, `LexerContext` | `from psh.lexer import ...` (works) or `from psh.lexer.<module> import ...` (preferred) | Available but not guaranteed. Prefer submodule paths. |
| **Internal** | `Position`, `LexerState`, `PositionTracker`, `LexerErrorHandler`, `RecoverableLexerError` | `from psh.lexer.<module> import ...` | Internal. May change without notice. |

## Related Documents

- `docs/guides/lexer_guide.md` -- Full programmer's guide (architecture,
  file reference, design rationale)
- `docs/guides/lexer_public_api_assessment.md` -- Analysis that led to
  this cleanup
- `psh/lexer/CLAUDE.md` -- AI assistant working guide for the lexer
  subsystem
