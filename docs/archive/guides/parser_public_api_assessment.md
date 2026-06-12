# Parser Public API Assessment

**As of v0.177.0**

This document assesses the parser package's public API contract — what is
exported vs what is actually used — and recommends cleanup actions.
Follows the same methodology as `lexer_public_api_assessment.md`.

## API Surface

The parser exports **22 items** via `__all__` in `psh/parser/__init__.py`.
These fall into distinct tiers based on actual usage by code outside
`psh/parser/`.

## Tier 1: Core Production API

These are actively imported and used by production code outside the parser
package:

| Export | Production callers | Role |
|--------|-------------------|------|
| `parse()` | 4 files (`shell.py` x2, `multiline_handler.py`, `io_redirect/process_sub.py`) | Primary entry point |
| `parse_with_heredocs()` | 1 file (`scripting/source_processor.py`) | Heredoc-aware parsing |
| `Parser` | 4 files (`source_processor.py`, `parser_factory.py`, `executor/strategies.py`, `builtins/parse_tree.py`) | Direct parser construction |
| `ParseError` | 3 files (`multiline_handler.py`, `source_processor.py`, `builtins/parse_tree.py`) | Caught in error handling |
| `ParserConfig` | 1 file (`utils/parser_factory.py`) | Parser configuration |

### Effective API

The real contract used by production code is just five items:

```python
from psh.parser import parse
from psh.parser import parse_with_heredocs
from psh.parser import Parser
from psh.parser import ParseError
from psh.parser import ParserConfig
```

Note: `Parser` and `ParseError` are also imported from submodule paths
by some production callers (`builtins/parse_tree.py` uses
`from ..parser.recursive_descent.helpers import ParseError` and
`from ..parser.recursive_descent.parser import Parser`). These bypass the
package-level re-exports.

## Tier 2: Test-only usage

These are in `__all__` but only imported by test files, never by
production code:

| Export | Test callers | Notes |
|--------|-------------|-------|
| `ErrorContext` | 1 (`test_error_collection.py`, via submodule path) | Error detail container |
| `ParserContext` | 1 (`test_parser_context.py`, via submodule path) | Internal state object |
| `ParserProfiler` | 1 (`test_parser_context.py`, via submodule path) | Performance profiling |
| `ParsingMode` | 2 (`test_parser_configuration.py`, `test_parser_context.py`) | Config enum |
| `ErrorHandlingMode` | 3 (`test_parser_configuration.py`, `test_parser_context.py`, `test_parser_review_fixes.py`) | Config enum |
| `create_context` | 1 (`test_parser_context.py`, via submodule path) | Context factory |
| `create_strict_posix_context` | 1 (`test_parser_context.py`, via submodule path) | Context factory |
| `create_permissive_context` | 1 (`test_parser_context.py`, via submodule path) | Context factory |
| `create_strict_posix_parser` | 1 (`test_parser_configuration.py`, via submodule path) | Parser factory |
| `create_permissive_parser` | 1 (`test_parser_configuration.py`, via submodule path) | Parser factory |
| `validate_config` | 2 (`test_parser_configuration.py`, `test_parser_review_fixes.py`, via submodule path) | Config validator |
| `suggest_config` | 1 (`test_parser_configuration.py`, via submodule path) | Config suggestion |
| `parse_strict_posix` | 1 (`test_parser_configuration.py`) | Convenience wrapper |
| `parse_permissive` | 1 (`test_parser_configuration.py`) | Convenience wrapper |

Note: Most Tier 2 test callers import from the submodule path (e.g.
`from psh.parser.recursive_descent.support.context_factory import
create_context`) rather than from `psh.parser`. The package-level
re-export is unused by those tests.

## Tier 3: Zero callers outside `psh/parser/`

These are exported but never imported anywhere outside the parser
package — not in production code, not in tests:

| Export | Notes |
|--------|-------|
| `TokenGroups` | Used internally by sub-parsers; never imported from outside the parser |
| `ContextBaseParser` | Base class used internally; no external subclasses or direct usage |
| `HeredocInfo` | Heredoc tracking dataclass; internal to parser context |

## Subpackages with their own `__all__`

The parser package contains four subpackages that declare their own
`__all__`. These are **not** re-exported by `psh/parser/__init__.py` —
callers import from the subpackage path directly.

### `psh.parser.visualization` (5 exports)

| Export | Production callers | Test callers |
|--------|-------------------|-------------|
| `ASTPrettyPrinter` | 2 (`builtins/parse_tree.py`, `utils/ast_debug.py`) | 1 |
| `AsciiTreeRenderer` | 2 (`builtins/parse_tree.py`, `utils/ast_debug.py`) | 1 |
| `CompactAsciiTreeRenderer` | 2 (`builtins/parse_tree.py`, `utils/ast_debug.py`) | 1 |
| `ASTDotGenerator` | 2 (`builtins/parse_tree.py`, `utils/ast_debug.py`) | 1 |
| `DetailedAsciiTreeRenderer` | 0 | 1 (`test_parser_visualization.py`) |

The visualization subpackage has the healthiest export profile of any
parser subpackage: 4 of 5 exports have production callers.
`DetailedAsciiTreeRenderer` is test-only.

### `psh.parser.validation` (11 exports)

| Export | Production callers | Test callers |
|--------|-------------------|-------------|
| `SemanticAnalyzer` | 0 | 2 |
| `SemanticError` | 0 | 0 |
| `SymbolTable` | 0 | 0 |
| `SemanticWarning` | 0 | 0 |
| `WarningSeverity` | 0 | 0 |
| `CommonWarnings` | 0 | 0 |
| `ValidationRule` | 0 | 1 |
| `ValidationReport` | 0 | 2 |
| `Issue` | 0 | 1 |
| `Severity` | 0 | 1 |
| `ValidationPipeline` | 0 | 2 |

The validation subpackage has **zero production callers**. It is invoked
indirectly via `Parser.parse_and_validate()` and
`Parser.validate_ast()`, but no production code calls those methods. The
entire validation subsystem is exercised only by tests.

Five of 11 exports (`SemanticError`, `SymbolTable`, `SemanticWarning`,
`WarningSeverity`, `CommonWarnings`) have zero callers anywhere.

### `psh.parser.combinators` (50+ exports)

The combinator parser is documented as experimental/educational. Its
exports are used only by its own unit tests
(`tests/unit/parser/combinators/`), the parser parity tests, and
`psh/utils/parser_factory.py` (which imports
`ParserCombinatorShellParser` directly from the submodule). The
combinator package is out of scope for this assessment.

### `psh.parser.recursive_descent` (8 exports)

This subpackage re-exports the same items that `psh/parser/__init__.py`
re-exports (`Parser`, `ContextBaseParser`, `ParserContext`, etc.). It
serves as an intermediate re-export layer. Some production code imports
directly from this level or deeper (e.g.
`from psh.parser.recursive_descent.parser import Parser`).

## Additional Issues

### Stale `__version__`

Unlike the lexer, the parser package does not have a stale `__version__`.
No issue here.

### Redundant entry points

The package exports four module-level parsing functions that are thin
wrappers:

```python
# __init__.py
def parse(tokens, config=None):
    return Parser(tokens, config=config or ParserConfig()).parse()

def parse_with_heredocs(tokens, heredoc_map):
    return utils_parse_with_heredocs(tokens, heredoc_map)

def parse_strict_posix(tokens, source_text=None):
    return create_strict_posix_parser(tokens, source_text).parse()

def parse_permissive(tokens, source_text=None):
    return create_permissive_parser(tokens, source_text).parse()
```

Only `parse` and `parse_with_heredocs` have production callers.
`parse_strict_posix` and `parse_permissive` are tested by
`test_parser_configuration.py` but never used outside tests. They are
one-liners that combine a factory function with `.parse()` — the value
they add over calling `Parser(tokens, config=ParserConfig.strict_posix()).parse()`
is marginal.

### Factory function proliferation

The package exports six factory functions:

- `create_context`, `create_strict_posix_context`, `create_permissive_context`
- `create_strict_posix_parser`, `create_permissive_parser`
- `validate_config`, `suggest_config`

None have production callers. The `ParserConfig` class itself already
provides `ParserConfig.strict_posix()` and `ParserConfig.permissive()`
factory methods, making the standalone factory functions redundant with
different spelling.

### Bypass imports

Several production files import from deep submodule paths instead of from
the package:

| File | Imports from |
|------|-------------|
| `builtins/parse_tree.py` | `psh.parser.recursive_descent.helpers.ParseError` |
| `builtins/parse_tree.py` | `psh.parser.recursive_descent.parser.Parser` |
| `utils/parser_factory.py` | `psh.parser.config.ParserConfig` |

These work but bypass the package's `__all__` contract. If the public
API were cleaner, these could use `from psh.parser import ...` instead.

### `ErrorContext` is only useful with `ParseError`

`ErrorContext` is a dataclass used to construct `ParseError` instances.
Outside the parser, the only external consumer is `test_error_collection.py`.
Production code catches `ParseError` but never constructs `ErrorContext`
directly. It is an implementation detail of error construction.

## Recommendations

### 1. Trim `__all__` to actual public API

Remove Tier 3 items from `__all__`. These are internal implementation
details that leaked into the public API surface:

**Remove from `__all__`:**
- `TokenGroups` — zero external callers; only used by sub-parsers
  internally
- `ContextBaseParser` — zero external callers; base class is an
  implementation detail
- `HeredocInfo` — zero external callers; internal to parser context

Also remove their import statements from `__init__.py` since no external
code imports them via the package path.

### 2. Demote Tier 2 exports

Remove from `__all__` but **keep the import statements** so existing test
imports continue to work:

**Internal state / profiling (no production callers):**
- `ErrorContext` — implementation detail of `ParseError`
- `ParserContext` — internal mutable state; tests import from submodule
- `ParserProfiler` — debugging tool; tests import from submodule

**Config enums (useful for tests but not production):**
- `ParsingMode` — tests can import from `psh.parser.config`
- `ErrorHandlingMode` — tests can import from `psh.parser.config`

**Factory functions (zero production callers):**
- `create_context`
- `create_strict_posix_context`
- `create_permissive_context`
- `create_strict_posix_parser`
- `create_permissive_parser`
- `validate_config`
- `suggest_config`

**Convenience wrappers (zero production callers):**
- `parse_strict_posix`
- `parse_permissive`

### 3. New `__all__` after cleanup

```python
__all__ = [
    # Main parsing interface
    'parse', 'parse_with_heredocs', 'Parser',
    # Configuration
    'ParserConfig',
    # Errors
    'ParseError',
]
```

This mirrors the lexer's API shape: entry-point functions, the engine
class, configuration, and the error type.

### 4. Fix bypass imports

Update the two production files that bypass the package re-exports:

```python
# builtins/parse_tree.py — currently:
from ..parser.recursive_descent.helpers import ParseError
from ..parser.recursive_descent.parser import Parser
# Preferred:
from ..parser import ParseError, Parser

# utils/parser_factory.py — currently:
from ..parser.config import ParserConfig
# Preferred:
from ..parser import ParserConfig
```

This is optional but would make import patterns consistent with the rest
of the codebase.

### 5. Trim the `psh.parser.validation` `__all__`

Five of 11 exports have zero callers anywhere:
- `SemanticError`
- `SymbolTable`
- `SemanticWarning`
- `WarningSeverity`
- `CommonWarnings`

Remove these from `__all__` and their import statements in
`validation/__init__.py`. They remain importable from their defining
modules.

### 6. Trim the `psh.parser.recursive_descent` `__all__`

This subpackage re-exports 8 items. Three of them (`TokenGroups`,
`ContextBaseParser`, `HeredocInfo`) have zero external callers and should
be removed from its `__all__` to match the parent package cleanup.

## Verification (after implementing recommendations 1-3)

```bash
# Verify public API imports still work
python -c "from psh.parser import parse, parse_with_heredocs, Parser, ParserConfig, ParseError"

# Verify demoted items still importable
python -c "from psh.parser import ParserContext, ErrorContext, ParserProfiler"
python -c "from psh.parser import create_context, validate_config, suggest_config"
python -c "from psh.parser import parse_strict_posix, parse_permissive"
python -c "from psh.parser import ParsingMode, ErrorHandlingMode"

# Verify Tier 3 items importable from submodules
python -c "from psh.parser.recursive_descent.helpers import TokenGroups"
python -c "from psh.parser.recursive_descent.base_context import ContextBaseParser"
python -c "from psh.parser.recursive_descent.context import HeredocInfo"

# Run parser tests
python -m pytest tests/unit/parser/ -q --tb=short

# Run full suite
python run_tests.py > tmp/test-results.txt 2>&1; tail -15 tmp/test-results.txt
grep FAILED tmp/test-results.txt
```

## Files Modified (if recommendations implemented)

| File | Changes |
|------|---------|
| `psh/parser/__init__.py` | Remove 3 imports (Tier 3); remove 17 `__all__` entries (Tier 2 + Tier 3); keep Tier 2 import statements |
| `psh/parser/recursive_descent/__init__.py` | Remove 3 `__all__` entries (`TokenGroups`, `ContextBaseParser`, `HeredocInfo`) |
| `psh/parser/validation/__init__.py` | Remove 5 `__all__` entries + 5 imports (zero-caller items) |
| `psh/builtins/parse_tree.py` | (Optional) Change to package-level imports |
| `psh/utils/parser_factory.py` | (Optional) Change to package-level imports |

## Related Documents

- `docs/guides/lexer_public_api_assessment.md` — Same analysis for the
  lexer package (already implemented in v0.177.0)
- `docs/guides/lexer_public_api.md` — Lexer API reference (post-cleanup)
- `psh/parser/CLAUDE.md` — Parser subsystem working guide
- `docs/guides/parser_guide.md` — Full parser programmer's guide
