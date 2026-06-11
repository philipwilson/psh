# PSH Parser Quality Review

*Review date: 2026-02-09, covering `psh/parser/` at v0.133.0*

---

## Scope

This is a fresh study of the parser package (`psh/parser/`), covering
the recursive descent parser, the combinator parser, the validation and
visualization subpackages, and the support infrastructure. The review
examines the code on four axes: elegance, efficiency, educational value,
and Pythonic style.

**Package size**: 41 Python files, 12,154 lines total.

| Subpackage | Files | Lines | Purpose |
|---|---|---|---|
| `recursive_descent/` core | 4 | 1,418 | Parser, context, base class, helpers |
| `recursive_descent/parsers/` | 9 | 2,310 | 8 grammar sub-parsers + `__init__` |
| `recursive_descent/support/` | 4 | 735 | WordBuilder, factories, utilities |
| `combinators/` | 9 | 4,683 | Alternative functional parser |
| `validation/` | 6 | 1,282 | Semantic analysis and AST validation |
| `visualization/` | 5 | 1,522 | ASCII tree, DOT graph, S-expression |
| Root | 2 | 183 | `__init__.py`, `config.py` |

---

## 1. Elegance

### Strengths

**Delegating parser architecture.** The main `Parser` class (498 lines)
creates 8 specialised sub-parsers and delegates all grammar rules to
them. Each sub-parser is a plain class with a single `__init__(self,
main_parser)` constructor. This mirrors the grammar cleanly: a reader
looking for `case` parsing finds it in `control_structures.py`, not
buried in a monolithic method. The sub-parsers are small -- the largest
is `commands.py` at 621 lines; the smallest is `functions.py` at 95.
Most are under 300 lines.

**Grammar reads like a specification.** The statement hierarchy is
immediately visible in the code:

```
parse_statement -> parse_and_or_list -> parse_pipeline -> parse_pipeline_component -> parse_command
```

Each level maps directly to a level in the shell grammar's precedence
hierarchy (commands compose into pipelines, pipelines into and-or lists,
and-or lists into command lists). A reader can follow this chain from
`statements.py:22` through `commands.py:282` and understand the grammar
without reading any external documentation.

**Word AST design.** The `Word` / `LiteralPart` / `ExpansionPart`
hierarchy is the right abstraction for a shell parser. Each part carries
per-part quote context (`quoted`, `quote_char`), which preserves exactly
the information needed for field splitting and glob expansion without
over-specifying it. The design eliminates the old `arg_types` /
`quote_types` string lists and replaces them with a structured tree.

**Focused configuration.** `ParserConfig` (101 lines) contains only 12
fields that are actually read by parser code. Feature checks use
`getattr` with `False` as default, so ad-hoc queries work without
growing the dataclass. Two factory presets (`strict_posix()`,
`permissive()`) cover the common cases.

**Unified error handling.** Errors flow through a single path:
`ParserContext.errors` is the sole error list, `add_error()` tracks
fatal errors, `can_continue_parsing()` enforces limits. There is no
separate error collector class.

**Context manager for state flags.** `ParserContext.__enter__` /
`__exit__` lets sub-parsers change parsing flags (like
`in_case_pattern`) with guaranteed rollback. Only the 4 sub-parsers that
actually change flags use it; the other 4 correctly omit it.

### Weaknesses

**No base class for sub-parsers.** All 8 sub-parsers follow the same
implicit contract (`__init__(self, main_parser)`, stores
`self.parser`) but this is convention, not code. A lightweight protocol
or mixin could formalize the contract. The CLAUDE.md now documents this
convention, which mitigates the issue but doesn't eliminate it.

**Duplicate argument parsing paths.** `CommandParser` has two parallel
methods for parsing arguments: `parse_composite_argument()` returns
`(value, arg_type, quote_type)` tuples, while `parse_argument_as_word()`
returns `Word` AST nodes. The tuple path is a legacy interface still
used by several callers (for-loop iterables, case expressions, here
strings, array elements, redirect targets). This means argument parsing
logic is partially duplicated between the two methods.

**`_check_for_unclosed_expansions` repetition.** This 68-line method in
`commands.py` constructs `ErrorContext` + `ParseError` objects in 5
nearly identical blocks that differ only in the error message string. A
small helper like `_expansion_error(msg, token)` would reduce this to 5
one-liners.

**`_format_variable` branches are identical.** Both branches of the
if/else at `commands.py:479-482` return `f"${value}"`. The conditional is
dead logic.

---

## 2. Efficiency

**O(n) token consumption.** The recursive descent parser is linear in
the number of tokens for well-formed input. Each token is consumed
exactly once. This is the correct complexity class for a shell parser.

**Token normalisation on every parse.** `create_context()` runs
`KeywordNormalizer().normalize(list(tokens))` on every `Parser`
instantiation, copying the entire token list. For interactive use this
is negligible, but it's unnecessary work that could be avoided by
normalising during lexing.

**Profiler checks on every token.** `ParserContext.advance()` checks
`if self.profiler:` on every token consumption, and `enter_rule` /
`exit_rule` do the same. When profiling is disabled (the common case),
these are wasted branches. A null-object profiler would avoid the
conditionals.

**Deep call stack for simple commands.** Parsing `echo hello` traverses
10 call frames before the first argument token is consumed. This is
inherent to recursive descent and not incorrect, but it means error
traces are deep and harder to read.

**`import re` inside method bodies.** `WordBuilder.parse_expansion_token`
and `RedirectionParser.parse_fd_dup_word` import `re` inside their
method bodies rather than at module level. These methods can be called
per-token, so the import overhead (small but nonzero) adds up. More
importantly, inline imports are un-Pythonic -- PEP 8 recommends all
imports at the top of the file.

**No unbounded growth risk.** `scope_stack` and `parse_stack` grow with
nesting depth but are bounded by Python's recursion limit.

---

## 3. Educational Value

### Strengths

**Grammar is visible in code.** A student reading the recursive descent
parser can follow the grammar's precedence hierarchy from top-level
statements down to individual command arguments. Each parsing method
corresponds to a grammar rule. This is the primary virtue of recursive
descent and the codebase preserves it well.

**AST nodes are self-documenting.** `IfConditional`, `ForLoop`,
`CaseConditional`, `Pipeline`, `SimpleCommand` -- the names tell you
what they are. Field names like `condition`, `then_part`, `else_part`,
`variable`, `items`, `body` are descriptive without being verbose.

**Two parsers, same grammar.** The combinator parser (`combinators/`,
4,683 lines) demonstrates how the same shell grammar can be expressed
through functional composition. The `Parser` class in `core.py` defines
primitives (`token`, `many`, `sequence`, `optional`, `or_else`, `lazy`)
and the grammar is built by composing them. Having both implementations
side-by-side lets a learner compare imperative vs functional parsing
approaches.

**Combinator core is textbook-quality.** `combinators/core.py` (483
lines) is a clean, well-documented implementation of the standard
parser combinator primitives. `ParseResult` is a proper generic
dataclass. The `Parser` class has `map`, `then`, `or_else` as fluent
methods. `ForwardParser` solves the recursive grammar problem elegantly.
Every function has a docstring with Args/Returns documentation.

**Debug tooling.** `--debug-ast`, `--debug-tokens`, and `--validate`
flags let a learner observe the parser in action. The `visualization/`
subpackage provides 4 AST output formats: tree, compact, S-expression,
and DOT graph. These are genuinely useful for understanding how the
parser transforms input.

**Comprehensive documentation.** The parser CLAUDE.md documents the
delegating architecture, the sub-parser contract (with context manager
usage table), the WordBuilder entry points, and the Word AST structure.
The combinator parser has its own companion guide.

### Weaknesses

**WordBuilder complexity is not scaffolded.** `WordBuilder` (285 lines)
is the most complex single piece of the parser. It decomposes
`RichToken` STRING tokens -- which contain embedded `TokenPart` metadata
from the lexer -- into `Word` nodes with per-part quote context. This
involves detecting parameter expansion operators, handling composite
tokens with mixed quoted/unquoted segments, and building expansion AST
nodes from token metadata. The cross-reference from `commands.py` and
the expanded CLAUDE.md documentation help discoverability, but there is
no inline guided walkthrough for someone encountering this code for the
first time.

**Array parser handles too many tokenisation variants.** `arrays.py`
(397 lines) is disproportionately large for what it parses. The
complexity comes from supporting multiple lexer tokenisation patterns
for the same syntax (e.g., `arr[0]=value` as one token vs
`arr[0]` + `=value` as two tokens vs `arr[0]` + `=` + `value` as
three). This is a real-world engineering concern but it obscures the
grammar for educational purposes.

**Validation and visualisation are disconnected.** The `validation/`
subpackage (1,282 lines) provides semantic analysis and validation
rules, but the validation is gated behind `enable_validation` which
defaults to `False` and no production code path enables it. Similarly,
the `visualization/` subpackage (1,522 lines) is feature-rich but never
invoked from the main execution path. These are potentially valuable
educational tools that are hard for a student to discover.

---

## 4. Pythonic Style

### Pythonic

**Dataclasses.** AST nodes, `ParserConfig`, `ErrorContext`, `HeredocInfo`,
`ParseResult` all use `@dataclass` with proper
`field(default_factory=...)` for mutable defaults. This is idiomatic and
eliminates boilerplate.

**Type hints.** Comprehensive annotations on function signatures. Return
types like `Union[ForLoop, CStyleForLoop]` and `Optional[Statement]`
express the grammar's alternatives explicitly.

**Logging.** Parser tracing uses `logging.debug()`, which is correct
Python practice.

**Enum types.** `ErrorSeverity`, `ParsingMode`, `ErrorHandlingMode` are
proper enums, not string constants. `TokenType` is an enum throughout.
`frozenset` token groups are used for immutable token classification.

**Module-level factory functions.** Parser and context creation use plain
functions (`create_context()`, `create_strict_posix_parser()`) rather
than factory classes. This is the simplest correct pattern.

**Context manager protocol.** `ParserContext.__enter__` / `__exit__` for
state preservation is clean and idiomatic.

### Un-Pythonic

**Property wrappers for simple forwarding.** `Parser.tokens` and
`Parser.current` are properties that forward to `self.ctx.tokens` and
`self.ctx.current`. These exist for backward compatibility but add
indirection. Python convention favours direct attribute access.

**Inline imports.** Several files use inline imports (`import re` inside
methods in `word_builder.py`, `commands.py`, `redirections.py`; `from
....ast_nodes import ...` inside method bodies in `commands.py`). PEP 8
recommends all imports at the top of the file. Inline imports are
acceptable for breaking circular dependencies, but for `re` and
`ast_nodes` there is no circular dependency risk.

**`hasattr` checks for own attributes.** `_has_decomposable_parts`
uses `getattr(token, 'parts', None)` to check for RichToken
characteristics. This is a duck-typing approach that works but obscures
the fact that the function only operates on RichToken instances. An
`isinstance` check would be more explicit.

**Backward compatibility shims.** `_ErrorCollectorView` (27 lines)
exists solely so that test code checking `parser.error_collector is not
None` continues to work. The `context` property aliases `self.ctx`. The
`from_context` classmethod duplicates `__init__` logic. These shims are
individually small but collectively add indirection that a fresh
codebase would not need.

---

## 5. Specific Observations

### Code smells

1. **`_format_variable` dead branch** (`commands.py:479-482`): Both
   if/else branches return the same value. The conditional serves no
   purpose.

2. **`_check_for_unclosed_expansions` boilerplate**
   (`commands.py:48-115`): Five nearly identical `ErrorContext` +
   `raise ParseError` blocks. Could be reduced to a helper.

3. **`parse_composite_argument` vs `parse_argument_as_word`**: Two
   parallel paths for parsing arguments with different return types.
   The tuple-based path (`parse_composite_argument`) is legacy but
   still has active callers.

4. **`_saved_states` as monkey-patched list** (`context.py:469`):
   `__enter__` creates `_saved_states` via `hasattr` check rather than
   initialising it in `__init__` or `__post_init__`. The dataclass
   should declare this field.

5. **`ParserProfiler` import of `time`** (`context.py`): `import time`
   appears inside 4 separate methods. It should be at module level.

### Notable quality

1. **`_parse_loop_structure` factorisation**
   (`control_structures.py:179-195`): While and until loops share
   identical structure. The common pattern is extracted into a single
   method parameterised by start/body_start/body_end token types. This
   is textbook DRY without being over-abstract.

2. **`_parse_condition_then_block` helper**
   (`control_structures.py:132-139`): The if/elif pattern is cleanly
   factored. The method returns a `(condition, body)` tuple that the
   caller destructures.

3. **`_parse_parameter_expansion` operator precedence**
   (`word_builder.py:96-145`): The operator matching algorithm uses
   earliest-position + longest-match disambiguation. The logic is
   non-trivial but the implementation is clear, with a well-ordered
   operator list and explicit comments explaining the precedence rules.

4. **Combinator `lazy` primitive** (`core.py:288-304`): Uses a
   single-element list as a mutable cache to implement deferred parser
   creation for recursive grammars. This is a standard functional
   technique, implemented simply.

5. **Sub-parser file sizes** reflect the grammar's inherent complexity:
   `statements.py` (103 lines) is simple because statement lists are
   simple; `control_structures.py` (484 lines) is larger because `if`,
   `while`, `for`, `case`, `select`, `break`, `continue` each have
   distinct syntax. The code's bulk tracks the grammar's bulk.

---

## 6. Summary Scores

| Dimension | Score | Key factor |
|---|---|---|
| **Elegance** | B+ | Clean delegation; focused config; some legacy duplication remains |
| **Efficiency** | B | Correct complexity; minor constant-factor waste (normalisation, profiler checks) |
| **Educational** | A- | Grammar visible in code; dual-parser comparison; rich debug tooling; WordBuilder is steep |
| **Pythonic** | B+ | Good dataclass/typing/enum usage; inline imports and property wrappers detract |

**Overall: B+/A-.**

The parser is a well-structured, well-documented implementation of a
complex grammar. The recursive descent architecture maps cleanly to the
shell grammar, making it readable. The combinator parser provides a
valuable educational counterpoint. Recent cleanup work (v0.128-v0.133)
has removed significant dead code and improved documentation. The
remaining issues are minor: legacy argument-tuple interfaces, a few
repetitive error-construction patterns, and scattered inline imports.
None of these affect correctness or significantly impact readability.

---

## 7. Suggested Improvements

These are ordered by impact. All are optional -- the parser works
correctly and is well-tested.

1. **Consolidate argument parsing paths.** ✓ *Done (v0.135.0).* Migrated
   all `parse_composite_argument()` callers (for-loop iterables, case
   expressions, here strings, array elements, redirect targets) to use
   `parse_argument_as_word()` and the Word AST. Deleted
   `parse_composite_argument()`, `_token_to_argument()`, and
   `_format_variable()` from `CommandParser`. Added
   `_word_to_element_type()` static helper to `ArrayParser` for
   deriving legacy element-type strings from Word nodes.

2. **Extract error construction helper.** ✓ *Done (v0.134.0).* Replaced
   the 6 repetitive `ErrorContext + raise ParseError` blocks in
   `_check_for_unclosed_expansions` and `_validate_command_start` with
   a `_raise_unclosed_expansion_error(msg, token)` helper.

3. **Move inline imports to module level.** ✓ *Done (v0.134.0).* Moved
   `import re` to module level in `commands.py`, `redirections.py`, and
   `word_builder.py`. Moved `import time` to module level in
   `context.py`. Moved `LiteralPart` and `Word` to the existing
   module-level import block in `commands.py`.

4. **Initialise `_saved_states` in dataclass.** ✓ *Done (v0.134.0).*
   Added `_saved_states: List[dict] = field(default_factory=list)` to
   `ParserContext`. Removed `hasattr` guards in `__enter__`/`__exit__`.
   Added reset in `reset_state()`.

5. **Remove dead `_format_variable` branch.** ✓ *Done (v0.134.0).*
   Simplified to a single `return f"${token.value}"`.
