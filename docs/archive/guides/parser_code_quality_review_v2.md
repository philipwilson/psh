# PSH Parser Code Quality Review

*Original review: 2026-02-09, covering psh/parser/ at v0.130.0*
*Updated: 2026-02-09, reflecting changes through v0.132.0*

---

## Executive Summary

The PSH parser is a well-architected recursive descent implementation that
correctly parses a complex shell grammar. Its delegation to specialised
sub-parsers mirrors the grammar cleanly, and the Word AST design is a
genuine strength. A companion combinator parser provides an educational
counterpoint demonstrating functional parsing.

v0.131.0 addressed the three highest-impact issues from the original
review: speculative configuration was pruned from 45 to 12 fields,
the three overlapping error-handling paths were unified into one, and
the combinator parser now has a companion guide. v0.132.0 completed
the remaining code-quality items: factory classes were converted to
module-level functions, dead compatibility code was deleted, and
`ErrorContext.severity` was changed from a string to an `Enum`.

**Overall: A-.** Sound architecture with focused configuration,
unified error handling, and clean Pythonic style. All 10
recommendations from the original review are now complete.

---

## 1. Elegance

### What works

**Delegating parser architecture.** The main `Parser` class
(recursive_descent/parser.py) creates specialised sub-parsers and
delegates all grammar rules to them:

```python
self.statements = StatementParser(self)
self.commands = CommandParser(self)
self.control_structures = ControlStructureParser(self)
self.tests = TestParser(self)
self.arithmetic = ArithmeticParser(self)
self.redirections = RedirectionParser(self)
self.arrays = ArrayParser(self)
self.functions = FunctionParser(self)
```

Each sub-parser handles exactly one grammar domain. A reader looking for
`case` parsing finds it in `control_structures.py`, not buried in a
monolithic method.

**Word AST design.** The `Word`/`LiteralPart`/`ExpansionPart` hierarchy
(ast_nodes.py) represents shell words with per-part quote context.
This is the correct abstraction for a shell parser -- it preserves the
information needed for field splitting and glob expansion without
over-specifying it:

```python
# "hello $USER!" becomes:
Word(parts=[
    LiteralPart("hello ", quoted=True, quote_char='"'),
    ExpansionPart(VariableExpansion("USER"), quoted=True, quote_char='"'),
    LiteralPart("!", quoted=True, quote_char='"'),
], quote_type='"')
```

**TokenGroups.** Predefined frozensets (helpers.py) make token
classification readable:

```python
WORD_LIKE = frozenset({WORD, STRING, VARIABLE, ...})
CONTROL_KEYWORDS = frozenset({IF, THEN, ELSE, ELIF, FI, ...})
REDIRECTS = frozenset({REDIRECT_IN, REDIRECT_OUT, ...})
```

These are used consistently across all sub-parsers.

**Context manager for state preservation.** `ParserContext.__enter__` /
`__exit__` lets sub-parsers change parsing flags with automatic rollback:

```python
with self.parser.ctx:
    self.parser.ctx.in_case_pattern = True
    pattern_str = self._parse_case_pattern()
# in_case_pattern automatically restored
```

**Focused configuration (v0.131.0).** `ParserConfig` now contains only
the 12 fields actually read by parser code. `is_feature_enabled()` and
`should_allow()` use `getattr` with a default of `False`, so ad-hoc
feature checks still work without requiring fields in the dataclass.
Two presets (`strict_posix()`, `permissive()`) cover the common cases.

**Unified error handling (v0.131.0).** Errors flow through a single path:
`ParserContext.errors` is the sole error list, with `add_error()` tracking
fatal errors and `can_continue_parsing()` enforcing limits. The old
`ErrorCollector` class has been removed. `parse_with_error_collection()`
uses `ctx.errors` directly.

### What doesn't

**No base class for sub-parsers.** Each sub-parser independently
implements `__init__(self, main_parser)` and stores `self.parser`. There
is no shared base class or protocol enforcing this pattern, which leads
to the inconsistencies described in Section 5.

---

## 2. Efficiency

**Token normalisation overhead.** Every `Parser` instantiation runs
keyword normalisation (context_factory.py):

```python
normalizer = KeywordNormalizer()
normalized_tokens = normalizer.normalize(list(tokens))
```

This copies the entire token list. The combinator parser does the same
independently. For interactive use this is negligible, but it's
unnecessary work -- the lexer could normalise keywords directly.

**Profiler checks on every token.** `ParserContext.advance()` checks
`if self.profiler:` on every token consumption. `enter_rule` and
`exit_rule` do the same. When profiling is disabled (the common case),
these are wasted branches. The profiler could be a null-object that
does nothing, avoiding the conditional entirely.

**Deep call stack for simple commands.** Parsing `echo hello` traverses:

```
Parser.parse()
  -> _parse_top_level_item()
    -> statements.parse_command_list_until_top_level()
      -> parse_command_list()
        -> parse_statement()
          -> parse_and_or_list()
            -> commands.parse_pipeline()
              -> parse_pipeline_component()
                -> parse_command()
                  -> _parse_command_elements()
```

That is 10 call frames before the first token is consumed as an argument.
This is inherent to recursive descent and not incorrect, but it means
error stack traces are deep, which hurts debuggability.

**Algorithmic correctness.** The recursive descent parser is O(n) in the
number of tokens for well-formed input, which is correct. The combinator
parser uses `or_else` backtracking which is theoretically O(n^2) for
ambiguous prefixes, but in practice shell grammar has limited ambiguity
and the combinator parser handles educational-sized inputs.

**No unbounded growth risk.** `scope_stack` and `parse_stack` grow with
nesting depth but are bounded by the recursive descent call stack
itself -- Python will hit its recursion limit before these lists become
a memory concern.

---

## 3. Educational Value

### Strengths

**Grammar is visible in code.** The recursive descent structure maps
directly to shell grammar. A student can read:

```
parse_and_or_list -> parse_pipeline -> parse_pipeline_component -> parse_command
```

and understand the precedence hierarchy: commands compose into pipelines,
pipelines compose into and-or lists. This is the primary virtue of
recursive descent and the codebase preserves it well.

**AST nodes are self-documenting.** `IfConditional`, `ForLoop`,
`CaseConditional`, `Pipeline`, `SimpleCommand` -- the names tell you what
they are. Field names like `condition`, `then_part`, `else_part`,
`variable`, `items`, `body` are descriptive without being verbose.

**Debug tooling.** The `--debug-ast`, `--debug-tokens`, and
`--debug-expansion` flags let a learner observe the parser in action.
Multiple AST visualisation formats (tree, compact, S-expression, DOT
graph) are available via the `visualization/` subpackage.

**Combinator parser with companion guide (v0.131.0).** The `combinators/`
package demonstrates how the same grammar can be expressed through
functional composition. The `Parser` class in `combinators/core.py`
defines primitives (`token`, `many`, `sequence`, `optional`) and the
grammar is built by composing them. The companion guide
(`docs/guides/combinator_parser_guide.md`) explains the module structure,
feature coverage, reading order, and differences from recursive descent.

**Simple parser creation (v0.132.0).** Context and parser creation use
plain module-level functions (`create_context()`, `create_strict_posix_parser()`,
etc.) rather than factory classes. The simple path --
`Parser(tokens).parse()` -- still works, and the factory functions are
discoverable without navigating class hierarchies.

### Weaknesses

**Hidden complexity in word building.** `WordBuilder`
(support/word_builder.py) is the most complex single piece of the parser.
It decomposes `RichToken` STRING tokens -- which contain embedded
`TokenPart` metadata from the lexer -- into `Word` nodes with per-part
quote context. This involves detecting parameter expansion operators,
handling composite tokens with mixed quoted/unquoted segments, and
building expansion AST nodes from token metadata. It is critical to
correctness but buried in a support module with no prominent
cross-reference from `commands.py` or the parser CLAUDE.md.

**Inconsistent sub-parser patterns.** Some sub-parsers use the context
manager for state preservation (control_structures.py, tests.py,
arithmetic.py, functions.py); `commands.py` never does, because command
parsing doesn't change context flags. Some use `self.parser.ctx.current`
directly; others go through `self.parser.current` (a property wrapper).
These inconsistencies are individually harmless but collectively make the
codebase feel unfinished, which undermines the educational goal.

---

## 4. Pythonic Style

### Pythonic

**Dataclasses.** AST nodes, `ParserConfig`, `ErrorContext`, `HeredocInfo`
all use `@dataclass` with proper `field(default_factory=...)` for mutable
defaults. This is idiomatic and eliminates boilerplate.

**Type hints.** Comprehensive annotations on function signatures. Return
types like `Union[ForLoop, CStyleForLoop]` and `Optional[Statement]`
express the grammar's alternatives explicitly.

**Logging.** Parser tracing uses `logging.debug()`, which is correct
Python practice.

**Context managers.** `ParserContext.__enter__`/`__exit__` for state
preservation is clean and idiomatic.

**Module-level factory functions (v0.132.0).** Parser and context creation
functions (`create_context()`, `create_strict_posix_parser()`, etc.) are
plain module-level functions rather than `@staticmethod` methods on
classes. Thin compatibility shim classes preserve the old call syntax
during migration.

**Enum-typed severity (v0.132.0).** `ErrorContext.severity` uses the
`ErrorSeverity` enum (`INFO`, `WARNING`, `ERROR`, `FATAL`) rather than
bare strings, consistent with the `Severity` enum in the validation
subpackage.

### Un-Pythonic

**Property wrappers for simple forwarding.** `Parser.tokens` and
`Parser.current` are properties that forward to `self.ctx.tokens` and
`self.ctx.current`. These exist for backward compatibility but add
indirection. Python convention favours direct attribute access -- if `ctx`
is the source of truth, callers should use it.

---

## 5. Specific Issues

### Code duplication

**`consume_if` vs inline match-advance.** `ContextBaseParser.consume_if`
(base_context.py:45-49) exists but sub-parsers frequently write the
equivalent inline:

```python
if self.parser.match(TokenType.SEMICOLON):
    self.parser.advance()
```

This pattern appears 30+ times across the sub-parsers. Consistent use of
`consume_if` would reduce noise.

### Inconsistencies between sub-parsers

| Pattern | Used in | Not used in |
|---|---|---|
| `with self.parser.ctx:` state preservation | control_structures, tests, arithmetic, functions | commands, statements, redirections, arrays |
| `self.parser.ctx.current` (direct) | commands, arithmetic, control_structures, arrays, functions | -- |
| `self.parser.current` (property) | tests | -- |
| `self.parser.error()` for error creation | all (after v0.130.0 cleanup) | -- |

The first row is the most significant: whether or not to use the context
manager depends on whether the sub-parser changes context flags, but
this rationale isn't documented anywhere.

### Over-engineering

**Validation pipeline.** The `validation/` subpackage
(validation_pipeline.py, semantic_analyzer.py, validation_rules.py)
provides AST validation that is gated behind `enable_validation`, which
defaults to `False` and is only enabled programmatically via
`parser.enable_validation()`. No production code path calls this. The
validation infrastructure exists but has no active consumers.

**ParserProfiler.** 110 lines (context.py) of profiling infrastructure
that is disabled by default. The `profile_parsing` config field exists
but no production code path sets it to `True`.

---

## 6. Summary Scores

| Dimension | Score | Key factor |
|---|---|---|
| **Elegance** | B+ | Sound delegation architecture; focused config; unified error handling |
| **Efficiency** | B | Correct complexity; minor constant-factor waste |
| **Educational** | B+ | Grammar visible in code; combinator guide now exists; WordBuilder needs onboarding |
| **Pythonic** | B+ | Good dataclass/typing/enum usage; property wrappers remain |

---

## 7. Recommended Improvements

### Completed in v0.131.0

1. ~~**Prune ParserConfig**~~ Done. Pruned from 45 to 12 fields. Removed
   33 unused fields, 5 factory methods, `get_compatibility_info()`.
   (~500 lines removed.)

2. ~~**Unify error handling**~~ Done. Deleted `ErrorCollector` class and
   `error_collector.py`. `ParserContext.errors` is now the sole error
   list with `fatal_error` tracking. Recovery strategies inlined.
   (~360 lines removed.)

3. ~~**Document the combinator parser**~~ Done. Created
   `docs/guides/combinator_parser_guide.md` covering concepts, module
   structure, feature coverage, reading order, and comparison with
   recursive descent.

### Completed in v0.132.0

4. ~~**Replace factory classes with functions.**~~ Done. Converted
   `ParserContextFactory` (9 static methods), `ParserFactory` (4 static
   methods), and `ConfigurationValidator` (2 static methods) to plain
   module-level functions. Deleted unused `ContextConfiguration` class
   (zero callers). Added thin compatibility shim classes for existing
   call sites.

7. ~~**Remove `BaseParser` compatibility adapter**~~ Done. Deleted class
   (~30 lines) and removed from `__init__.py` exports.

8. ~~**Replace `ErrorContext.severity` string with Enum**~~ Done. Added
   `ErrorSeverity` enum in helpers.py with `INFO`, `WARNING`, `ERROR`,
   `FATAL`. Added `FATAL` to validation `Severity` enum. Updated
   `ParserContext.add_error()` and test to use enum.

9. ~~**Remove unreachable `except ImportError`**~~ Done. Removed the
   dead handler from `ParserContext._enhance_error_context`.

10. ~~**Remove `parse_with_rule` and `parse_scoped`**~~ Done. Deleted
    both methods (~15 lines) from `ContextBaseParser`.

5. ~~**Standardise sub-parser patterns.**~~ Done. Added "Sub-Parser
   Contract" section to parser CLAUDE.md documenting the implicit
   convention: initialization, state access, token position, context
   manager usage (with table of which sub-parsers set which flags),
   `consume_if` preference, and error creation.

6. ~~**Promote WordBuilder documentation.**~~ Done. Expanded WordBuilder
   section in parser CLAUDE.md with entry point, three key operations,
   and cross-reference from `commands.py` (docstring on
   `parse_argument_as_word`).

All 10 recommendations are now complete.
