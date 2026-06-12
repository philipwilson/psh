# Lexer Public API Assessment

**As of v0.176.0**

This document assesses the lexer package's public API contract — what is
exported vs what is actually used — and recommends cleanup actions.

## API Surface

The lexer exports **27 items** via `__all__` in `psh/lexer/__init__.py`.
These fall into distinct tiers based on actual usage by code outside
`psh/lexer/`.

## Tier 1: Core Production API

These are actively imported and used by production code outside the lexer
package:

| Export | Production callers | Role |
|--------|-------------------|------|
| `tokenize()` | 8 files (shell.py, source_processor.py, aliases.py, strategies.py, builtins/parse_tree.py, io_redirect/process_sub.py, parser/combinators/expansions.py, multiline_handler.py) | Primary entry point |
| `tokenize_with_heredocs()` | 1 file (source_processor.py) | Heredoc-aware tokenization |
| `LexerError` | 1 file (source_processor.py) | Caught in error handling |
| `RichToken` | 1 file (parser/recursive_descent/parsers/commands.py) | `isinstance()` check |
| `TokenPart` | 1 file (token_types.py) | TYPE_CHECKING import only |
| `ModularLexer` | 0 direct external callers | Used internally by `tokenize()` and `heredoc_lexer.py`; exported for direct-construction use cases in tests |

### Effective API

The real contract used by production code is just three items:

```python
from psh.lexer import tokenize
from psh.lexer import tokenize_with_heredocs
from psh.lexer import LexerError
```

## Tier 2: Test-only usage

These are in `__all__` but only imported by test files, never by production
code:

| Export | Test callers | Notes |
|--------|-------------|-------|
| `LexerConfig` | 1 (regression test) | Created internally by `tokenize()`; callers never touch it |
| `LexerContext` | 1 (integration test) | Internal state object |
| `KEYWORDS` | 1 (API verification test) | Internal to `KeywordNormalizer` |
| `OPERATORS_BY_LENGTH` | 1 (API verification test) | Internal to recognizers |
| `SPECIAL_VARIABLES` | 0 external tests | Internal to expansion_parser |
| `DOUBLE_QUOTE_ESCAPES` | 0 external tests | Internal to quote_parser |
| `WORD_TERMINATORS` | 0 external tests | Internal to recognizers |
| `is_identifier_start` | 1 (API verification test) | Unicode helper |
| `is_identifier_char` | 1 (API verification test) | Unicode helper |
| `is_whitespace` | 1 (API verification test) | Unicode helper |
| `normalize_identifier` | 1 (API verification test) | Unicode helper |
| `validate_identifier` | 1 (API verification test) | Unicode helper |

Note: `test_lexer_package_api.py` exists specifically to verify these
exports are importable. Its imports are test verification, not functional
dependencies.

## Tier 3: Zero callers outside `psh/lexer/`

These are exported but never imported anywhere outside the lexer package —
not in production code, not in tests:

| Export | Notes |
|--------|-------|
| `LexerErrorHandler` | Error handler class; used internally only |
| `RecoverableLexerError` | Error subclass; never caught outside lexer |
| `PositionTracker` | Position tracking; internal to ModularLexer |
| `LexerState` | State enum; internal to lexer context |
| `Position` | Consumers access `token.position` but never import the class |

## Additional Issues

### Stale package `__version__`

Line 38 of `__init__.py`:

```python
__version__ = "0.91.1"  # Phase 3 Day 2: Clean imports and dependencies
```

This is unrelated to the project version (0.176.0) and the comment
references an obsolete development phase. It serves no purpose.

### `RichToken` / `TokenPart` are marginal

`RichToken` has exactly one `isinstance()` check in production
(`commands.py`). `TokenPart` is a TYPE_CHECKING-only import. These were
designed for rich token metadata but the Word AST migration
(v0.115–v0.120) largely superseded that need. They may be candidates for
eventual removal if the `isinstance` check can be eliminated.

### CLAUDE.md for lexer is stale

`psh/lexer/CLAUDE.md` says `modular_lexer.py` is ~900 lines (actual: ~608
after cleanups). The `LexerContext` code block shows fields that don't
match the actual dataclass (`in_single_quote`, `in_double_quote`,
`in_arithmetic` — the implementation uses `quote_stack` and depth
counters).

## Recommendations

### 1. Trim `__all__` to actual public API

Remove Tier 3 items from `__all__`. These are internal implementation
details that leaked into the public API surface. They can still be imported
directly from their modules by tests that need them.

**Remove from `__all__`:**
- `LexerErrorHandler`
- `RecoverableLexerError`
- `PositionTracker`
- `LexerState`
- `Position`

**Rationale:** Zero callers. Removing from `__all__` does not break any
code — items remain importable via their module paths.

### 2. Consider demoting Tier 2 exports

Tier 2 items (`LexerConfig`, `LexerContext`, constants, unicode functions)
could also be removed from `__all__` since no production code uses them.
Tests that need them can import from the specific submodule:

```python
# Instead of:
from psh.lexer import LexerConfig
# Tests can use:
from psh.lexer.position import LexerConfig
```

This is a judgement call — keeping them exported makes the test imports
cleaner, but inflates the apparent API surface. A middle ground would be
to keep `LexerConfig` and `ModularLexer` (useful for advanced/test usage)
and remove the rest.

**Candidates for removal from `__all__`:**
- `LexerContext` (internal state)
- `KEYWORDS`, `OPERATORS_BY_LENGTH`, `SPECIAL_VARIABLES`,
  `DOUBLE_QUOTE_ESCAPES`, `WORD_TERMINATORS` (internal constants)
- 5 unicode functions (internal helpers)

### 3. Remove stale `__version__`

Delete the `__version__ = "0.91.1"` line and its comment from
`__init__.py`. The project version lives in `psh/version.py`.

### 4. Update `psh/lexer/CLAUDE.md`

Fix the line count for `modular_lexer.py` and correct the `LexerContext`
field listing to match the actual dataclass implementation.

### 5. Update `test_lexer_package_api.py`

After trimming `__all__`, update the API verification test to match the
new export list. Items removed from `__all__` should be tested via their
submodule imports if needed.

### 6. Evaluate `RichToken` / `TokenPart` longer-term

Investigate whether the single `isinstance(token, RichToken)` check in
`commands.py` can be replaced with a simpler mechanism (e.g., checking for
a `parts` attribute). If so, `RichToken` and `TokenPart` could be removed
from the public API and potentially deprecated.

## Related Documents

- `psh/lexer/CLAUDE.md` — Subsystem working guide (needs update)
- `ARCHITECTURE.md` — System-wide architecture reference (the former ARCHITECTURE.llm is archived)
