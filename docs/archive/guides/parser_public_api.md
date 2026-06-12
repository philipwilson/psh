# Parser Public API Reference

> **Note (2026-06-11):** This guide describes the tree as of ~v0.27x, before
> the v0.285 module relocation and subsequent cleanups. In particular it
> describes parser configuration machinery that has since been removed (the `PERMISSIVE`/`EDUCATIONAL` parsing modes, the `COLLECT`/`RECOVER` error-handling modes, and `parse_with_error_collection`).
> See the subsystem CLAUDE.md files for current structure.

**As of v0.186.0**

This document describes the public API of the `psh.parser` package: the
items declared in `__all__`, their signatures, and guidance on internal
imports that are available but not part of the public contract.

## Public API (`__all__`)

The declared public API consists of six items:

```python
__all__ = [
    'parse', 'parse_with_heredocs', 'create_parser', 'Parser',
    'ParserConfig',
    'ParseError',
]
```

### `parse()`

```python
from psh.parser import parse

ast = parse(
    tokens: List[Token],
    config: ParserConfig = None,
)
```

Primary entry point for parsing. Creates a `Parser` with the given
tokens and configuration, calls `parser.parse()`, and returns the AST.

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `tokens` | -- | List of tokens from `psh.lexer.tokenize()`. |
| `config` | `None` | Optional `ParserConfig`. When `None`, uses `ParserConfig()` (bash-compatible defaults). |

Returns a `CommandList` (single pipeline) or `TopLevel` (multiple
statements / function definitions).

### `parse_with_heredocs()`

```python
from psh.parser import parse_with_heredocs

ast = parse_with_heredocs(
    tokens: List[Token],
    heredoc_map: dict,
)
```

Parses tokens and populates heredoc content from a pre-collected map
(as returned by `psh.lexer.tokenize_with_heredocs()`).

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `tokens` | -- | List of tokens to parse. |
| `heredoc_map` | -- | Dict mapping heredoc delimiter strings to content. Values may be plain strings or dicts with `'content'` and `'quoted'` keys. |

Returns the same AST types as `parse()`.

### `create_parser()`

```python
from psh.parser import create_parser

parser = create_parser(
    tokens: List[Token],
    active_parser: str = 'rd',
    trace_parsing: bool = False,
    source_text: str = None,
)
ast = parser.parse()
```

Factory function that selects between the recursive descent parser and
the combinator parser.  Returns an object with a `.parse()` method.

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `tokens` | -- | List of tokens to parse. |
| `active_parser` | `'rd'` | `'rd'` for recursive descent, `'combinator'` for the combinator parser. |
| `trace_parsing` | `False` | Enable parser tracing output. |
| `source_text` | `None` | Optional source text for error reporting. |

Moved from `psh.utils.parser_factory` to `psh.parser` in v0.186.0.

### `Parser`

```python
from psh.parser import Parser

parser = Parser(
    tokens: List[Token],
    source_text: str = None,
    collect_errors: bool = False,
    config: ParserConfig = None,
    ctx: ParserContext = None,
)
```

The recursive descent parser class. Orchestrates parsing by delegating
to eight specialized sub-parsers (statements, commands, control
structures, tests, arithmetic, functions, redirections, arrays).

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `tokens` | -- | List of tokens to parse. |
| `source_text` | `None` | Original source text for error messages. |
| `collect_errors` | `False` | When `True`, collect errors instead of raising on first error. |
| `config` | `None` | Parser configuration. Uses `ParserConfig()` when `None`. |
| `ctx` | `None` | Pre-built `ParserContext`. When provided, `tokens`/`config`/`source_text` are ignored. |

#### Key methods

**Parsing:**

| Method | Returns | Description |
|--------|---------|-------------|
| `parse()` | `CommandList` or `TopLevel` | Parse all tokens into an AST. |
| `parse_with_heredocs(heredoc_map)` | `CommandList` or `TopLevel` | Parse and populate heredoc content. |
| `parse_with_error_collection()` | `MultiErrorParseResult` | Parse collecting multiple errors instead of stopping on first. |
| `parse_and_validate()` | `(AST, ValidationReport)` | Parse and run AST validation (if `config.enable_validation` is set). |

**Factory:**

| Method | Returns | Description |
|--------|---------|-------------|
| `create_configured_parser(tokens, **overrides)` | `Parser` | Create a child parser with the same config (cloned, not shared). |
| `Parser.from_context(ctx)` | `Parser` | Class method: create parser from an existing `ParserContext`. |
| `Parser.create_with_config(tokens, config, source_text=None)` | `Parser` | Class method: create parser with explicit config. |

**Feature checking:**

| Method | Returns | Description |
|--------|---------|-------------|
| `is_feature_enabled(feature)` | `bool` | Check if a feature (e.g. `'arithmetic'`) is enabled. |
| `should_collect_errors()` | `bool` | Whether error collection mode is active. |
| `should_attempt_recovery()` | `bool` | Whether error recovery is enabled. |
| `require_feature(feature)` | `None` | Raise `ParseError` if the feature is disabled. |
| `check_posix_compliance(feature, alternative=None)` | `None` | Raise `ParseError` if in strict POSIX mode. |

**Validation:**

| Method | Returns | Description |
|--------|---------|-------------|
| `validate_ast(ast)` | `ValidationReport` | Run validation pipeline on an AST. |
| `enable_validation(enable_semantic=True, enable_rules=True)` | `None` | Turn on AST validation. |
| `disable_validation()` | `None` | Turn off AST validation. |

#### `MultiErrorParseResult`

Returned by `parse_with_error_collection()`:

| Field / Method | Type | Description |
|----------------|------|-------------|
| `.ast` | AST or `None` | Partial or complete AST. |
| `.errors` | `List[ParseError]` | All errors encountered. |
| `.success` | `bool` | `True` if AST is present and no errors. |
| `.partial_success` | `bool` | `True` if AST is present but errors exist. |
| `.has_errors()` | `bool` | Whether any errors were collected. |
| `.format_errors()` | `str` | Formatted error display. |

### `ParserConfig`

```python
from psh.parser import ParserConfig

config = ParserConfig(
    parsing_mode: ParsingMode = ParsingMode.BASH_COMPAT,
    error_handling: ErrorHandlingMode = ErrorHandlingMode.STRICT,
    max_errors: int = 10,
    collect_errors: bool = False,
    enable_error_recovery: bool = False,
    show_error_suggestions: bool = True,
    enable_arithmetic: bool = True,
    allow_bash_conditionals: bool = True,
    allow_bash_arithmetic: bool = True,
    trace_parsing: bool = False,
    profile_parsing: bool = False,
    enable_validation: bool = False,
    enable_semantic_analysis: bool = True,
    enable_validation_rules: bool = True,
)
```

Configuration dataclass controlling parser behavior. Fields are grouped
by purpose:

| Group | Fields | Purpose |
|-------|--------|---------|
| **Mode** | `parsing_mode` | Overall parsing strategy. |
| **Errors** | `error_handling`, `max_errors`, `collect_errors`, `enable_error_recovery`, `show_error_suggestions` | How parse errors are reported and recovered from. |
| **Features** | `enable_arithmetic`, `allow_bash_conditionals`, `allow_bash_arithmetic` | Language feature toggles. |
| **Debug** | `trace_parsing`, `profile_parsing` | Development and performance analysis. |
| **Validation** | `enable_validation`, `enable_semantic_analysis`, `enable_validation_rules` | Post-parse AST validation. |

#### Factory methods

| Method | Parsing Mode | Error Handling | Key Settings |
|--------|-------------|----------------|-------------|
| `ParserConfig()` | `BASH_COMPAT` | `STRICT` | All features enabled. |
| `ParserConfig.strict_posix()` | `STRICT_POSIX` | `STRICT` | `allow_bash_conditionals=False`, `allow_bash_arithmetic=False`. |
| `ParserConfig.permissive()` | `PERMISSIVE` | `RECOVER` | `collect_errors=True`, `enable_error_recovery=True`, `max_errors=50`. |

#### Instance methods

| Method | Returns | Description |
|--------|---------|-------------|
| `clone(**overrides)` | `ParserConfig` | Copy config with field overrides. Unknown fields are silently ignored. |
| `is_feature_enabled(feature)` | `bool` | Check `enable_{feature}` field via `getattr`. |
| `should_allow(capability)` | `bool` | Check `allow_{capability}` field via `getattr`. |

### `ParseError`

```python
from psh.parser import ParseError

try:
    ast = parse(tokens)
except ParseError as e:
    print(f"Parse error: {e}")
    ctx = e.error_context  # ErrorContext with position, suggestions, etc.
```

Exception raised for parse errors. Wraps an `ErrorContext` object that
carries position information, expected tokens, suggestions, and
severity.

| Attribute | Type | Description |
|-----------|------|-------------|
| `.error_context` | `ErrorContext` | Full error context with position, suggestions, severity. |
| `.message` | `str` | Formatted error message. |

## Convenience Imports (not in `__all__`)

The following items are importable from `psh.parser` for convenience but
are **not** part of the declared public contract. They are internal
implementation details whose signatures may change without notice.

Existing code that imports these will continue to work; the imports are
kept specifically to avoid churn. New code should prefer the submodule
import paths listed below.

### Configuration Enums

| Import | Canonical path | Description |
|--------|---------------|-------------|
| `ParsingMode` | `psh.parser.config` | Enum: `STRICT_POSIX`, `BASH_COMPAT`, `PERMISSIVE`, `EDUCATIONAL`. |
| `ErrorHandlingMode` | `psh.parser.config` | Enum: `STRICT`, `COLLECT`, `RECOVER`. |

### Parser Context and Profiling

| Import | Canonical path | Description |
|--------|---------------|-------------|
| `ParserContext` | `psh.parser.recursive_descent.context` | Centralized parser state (token stream, position, scopes, flags, errors). |
| `ParserProfiler` | `psh.parser.recursive_descent.context` | Performance profiler for parse rule timing and metrics. |
| `ErrorContext` | `psh.parser.recursive_descent.helpers` | Dataclass carried by `ParseError` with position, expected tokens, suggestions. |

### Factory

| Import | Canonical path | Description |
|--------|---------------|-------------|
| `create_context` | `psh.parser.recursive_descent.support.context_factory` | Create a `ParserContext` with keyword-normalization applied. Has 3 production callers. |

## Submodule-Only Imports

These classes were previously exported via `__all__` but had zero
callers outside the parser package. They have been removed from both
`__all__` and the package-level imports. Import them from their defining
module:

```python
from psh.parser.recursive_descent.base_context import ContextBaseParser
from psh.parser.recursive_descent.context import HeredocInfo
from psh.parser.recursive_descent.helpers import TokenGroups
```

| Class | Purpose |
|-------|---------|
| `ContextBaseParser` | Base class for `Parser`. Provides `peek()`, `advance()`, `match()`, `expect()`, `consume_if()`, `error()`, `skip_newlines()`, and scope/feature-checking methods. Consumers use `Parser` directly. |
| `HeredocInfo` | Dataclass tracking a single heredoc during parsing: delimiter, `strip_tabs`, `quoted`, content lines, closed state. Internal to `ParserContext`. |
| `TokenGroups` | Frozen sets of related `TokenType` values (`WORD_LIKE`, `REDIRECTS`, `CONTROL_KEYWORDS`, `STATEMENT_SEPARATORS`, `CASE_TERMINATORS`, `COMMAND_LIST_END`, `CASE_PATTERN_KEYWORDS`). Used by sub-parsers for token matching. |

## Deleted in v0.178.0

The following items were removed entirely (not just demoted). They were
thin wrappers with zero production callers:

| Item | Was in | Replacement |
|------|--------|-------------|
| `parse_strict_posix(tokens, source_text)` | `psh.parser` | `parse(tokens, config=ParserConfig.strict_posix())` |
| `parse_permissive(tokens, source_text)` | `psh.parser` | `parse(tokens, config=ParserConfig.permissive())` |
| `create_strict_posix_parser(tokens, source_text)` | `factory.py` | `Parser(tokens, source_text=source_text, config=ParserConfig.strict_posix())` |
| `create_permissive_parser(tokens, source_text)` | `factory.py` | `Parser(tokens, source_text=source_text, config=ParserConfig.permissive())` |
| `create_custom_parser(tokens, source_text, base_config, **overrides)` | `factory.py` | `Parser(tokens, config=base_config.clone(**overrides))` |
| `create_shell_parser(tokens, source_text, shell_options)` | `factory.py` | Build a `ParserConfig` manually; use `Parser(tokens, config=config)`. |
| `validate_config(config)` | `factory.py` | No replacement needed; was advisory only. |
| `suggest_config(use_case)` | `factory.py` | Use `ParserConfig()`, `.strict_posix()`, or `.permissive()` directly. |
| `create_strict_posix_context(tokens)` | `context_factory.py` | `create_context(tokens, config=ParserConfig.strict_posix())` |
| `create_permissive_context(tokens)` | `context_factory.py` | `create_context(tokens, config=ParserConfig.permissive())` |
| `create_repl_context(tokens)` | `context_factory.py` | `create_context(tokens, config=ParserConfig(...))` |
| `create_shell_parser_context(tokens, ...)` | `context_factory.py` | `create_context(tokens, config=...)` |
| `create_sub_parser_context(parent_ctx, tokens)` | `context_factory.py` | `create_context(tokens, config=parent_ctx.config)` with manual state copy. |
| `create_validation_context(tokens)` | `context_factory.py` | `create_context(tokens, config=ParserConfig(...))` |
| `create_performance_test_context(tokens)` | `context_factory.py` | `create_context(tokens, config=ParserConfig(...))` |

## API Tiers Summary

| Tier | Scope | How to import | Stability guarantee |
|------|-------|---------------|-------------------|
| **Public** | `parse`, `parse_with_heredocs`, `create_parser`, `Parser`, `ParserConfig`, `ParseError` | `from psh.parser import ...` | Stable. Changes are versioned. |
| **Convenience** | `ParsingMode`, `ErrorHandlingMode`, `ParserContext`, `ParserProfiler`, `ErrorContext`, `create_context` | `from psh.parser import ...` (works) or `from psh.parser.<submodule> import ...` (preferred) | Available but not guaranteed. Prefer submodule paths. |
| **Internal** | `ContextBaseParser`, `HeredocInfo`, `TokenGroups` | `from psh.parser.recursive_descent.<module> import ...` | Internal. May change without notice. |

## Typical Usage

### Parse a command string

```python
from psh.lexer import tokenize
from psh.parser import parse

tokens = tokenize("if true; then echo yes; fi")
ast = parse(tokens)
```

### Parse with strict POSIX mode

```python
from psh.lexer import tokenize
from psh.parser import parse, ParserConfig

tokens = tokenize("echo hello")
ast = parse(tokens, config=ParserConfig.strict_posix())
```

### Parse collecting multiple errors

```python
from psh.lexer import tokenize
from psh.parser import Parser, ParserConfig

tokens = tokenize("some input")
parser = Parser(tokens, config=ParserConfig.permissive())
result = parser.parse_with_error_collection()

if result.has_errors():
    print(result.format_errors())
if result.ast:
    # Use partial AST
    pass
```

### Parse with heredocs

```python
from psh.lexer import tokenize_with_heredocs
from psh.parser import parse_with_heredocs

tokens, heredoc_map = tokenize_with_heredocs("cat <<EOF\nhello\nEOF")
ast = parse_with_heredocs(tokens, heredoc_map)
```

### Parse and validate

```python
from psh.lexer import tokenize
from psh.parser import Parser, ParserConfig

tokens = tokenize("for x in a b; do echo $x; done")
config = ParserConfig(enable_validation=True)
parser = Parser(tokens, config=config)
ast, report = parser.parse_and_validate()

if report.has_errors():
    for issue in report.issues:
        print(issue)
```

## Related Documents

- `psh/parser/CLAUDE.md` -- AI assistant working guide for the parser
  subsystem (architecture, sub-parser contract, common tasks)
- `docs/guides/parser_public_api_assessment.md` -- Analysis that led to
  this cleanup
- `docs/guides/lexer_public_api.md` -- Companion API reference for the
  lexer package
