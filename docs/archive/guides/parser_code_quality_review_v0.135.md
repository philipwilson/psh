# PSH Parser Quality Review

*Review date: 2026-02-09, covering `psh/parser/` at v0.135.0*

---

## Scope

A fresh study of the parser package (`psh/parser/`), covering the
recursive descent parser, the combinator parser, the validation and
visualization subpackages, and the support infrastructure.  The review
examines the code on four axes: elegance, efficiency, educational value,
and Pythonic style.

**Package size**: 42 Python files, ~12,070 lines total.

| Subpackage | Files | Lines | Purpose |
|---|---|---|---|
| `recursive_descent/` core | 4 | 1,437 | Parser, context, base class, helpers |
| `recursive_descent/parsers/` | 9 | 2,227 | 8 grammar sub-parsers + `__init__` |
| `recursive_descent/support/` | 4 | 735 | WordBuilder, factories, utilities |
| `combinators/` | 9 | 4,683 | Alternative functional parser |
| `validation/` | 6 | 1,282 | Semantic analysis and AST validation |
| `visualization/` | 5 | 1,522 | ASCII tree, DOT graph, S-expression |
| Root | 2 | 183 | `__init__.py`, `config.py` |

---

## 1. Elegance

### Strengths

**Delegating parser architecture.**  The main `Parser` class (498 lines)
creates 8 specialised sub-parsers and delegates all grammar rules to
them.  Each sub-parser is a plain class with a single
`__init__(self, main_parser)` constructor.  This mirrors the grammar
cleanly: `case` parsing lives in `control_structures.py`, function
definitions in `functions.py`, arrays in `arrays.py`.  The sub-parsers
are well-sized — the largest is `commands.py` at 511 lines; the
smallest is `functions.py` at 95.  Most are under 300 lines.

**Grammar reads like a specification.**  The statement hierarchy is
immediately visible:

```
parse_statement → parse_and_or_list → parse_pipeline → parse_pipeline_component → parse_command
```

Each level maps directly to a level in the shell grammar's precedence
hierarchy.  A reader can follow this chain from `statements.py:22`
through `commands.py:263` and understand the grammar without external
documentation.

**Unified argument parsing.**  As of v0.135.0, all argument parsing
flows through a single method: `parse_argument_as_word()`.  The former
`parse_composite_argument()` tuple path has been eliminated.  Every
caller — for-loop iterables, case expressions, here strings, array
elements, redirect targets — now uses the Word AST.  This is a
significant architectural improvement: one code path, one data
representation, no impedance mismatch.

**Word AST design.**  The `Word` / `LiteralPart` / `ExpansionPart`
hierarchy is the right abstraction for a shell parser.  Each part
carries per-part quote context (`quoted`, `quote_char`), which preserves
exactly the information needed for field splitting and glob expansion
without over-specifying it.  The `effective_quote_char`, `is_quoted`,
and `has_unquoted_expansion` properties provide clean semantic queries
that replace ad-hoc string inspection.

**Focused configuration.**  `ParserConfig` (101 lines) contains only 12
fields that are actually read by parser code.  Feature checks use
`getattr` with `False` as default, so ad-hoc queries work without
growing the dataclass.  Two factory presets (`strict_posix()`,
`permissive()`) plus `clone()` cover the common cases.

**Context manager for state flags.**  `ParserContext.__enter__` /
`__exit__` lets sub-parsers change parsing flags (like
`in_case_pattern`) with guaranteed rollback.  Only the 4 sub-parsers
that actually change flags use it; the other 4 correctly omit it.  The
contract is documented in the parser CLAUDE.md with a usage table.

**`_parse_loop_structure` factorisation.**
`control_structures.py:179–195` extracts the while/until loop structure
into a single method parameterised by start/body_start/body_end token
types.  This is textbook DRY without being over-abstract.

**Combinator core is textbook-quality.**  `combinators/core.py` (484
lines) implements the standard parser combinator primitives cleanly.
`ParseResult` is a proper generic dataclass.  The `Parser` class has
`map`, `then`, `or_else` as fluent methods.  `ForwardParser` solves
recursive grammar references.  `lazy` uses a single-element list as a
mutable cache for deferred parser creation — a standard functional
technique.

### Weaknesses

**No base class for sub-parsers.**  All 8 sub-parsers follow the same
implicit contract (`__init__(self, main_parser)`, stores
`self.parser`) but this is convention, not code.  The CLAUDE.md
documents this convention, which mitigates the issue but doesn't
eliminate it.  A lightweight protocol or mixin (even a type alias) would
formalise it.

**`_check_for_unclosed_expansions` is still verbose.**  The method
(commands.py:59–100) uses the `_raise_unclosed_expansion_error` helper
introduced in v0.134.0, but the 5 conditional branches each construct a
slightly different error message string through `if/elif` chains.  A
data-driven approach (mapping `expansion_type` to format string) would
reduce this to a table lookup.

**Array parser handles too many tokenisation variants.**
`arrays.py` (422 lines) is disproportionately large for what it parses.
The complexity comes from supporting multiple lexer tokenisation patterns
for the same syntax (e.g., `arr[0]=value` as one token vs
`arr[0]` + `=value` as two tokens vs `arr[0]` + `=` + `value` as
three).  The `is_array_assignment()` lookahead method alone is 90 lines
of save/restore/check logic.  This is a genuine engineering concern
but it obscures the grammar.

**Compatibility shim classes.**  `ParserFactory`, `ParserContextFactory`,
`ConfigurationValidator`, and `_ErrorCollectorView` exist solely so
that existing callers keep working after internal refactors.
Individually small, collectively they add indirection.  Each wraps
module-level functions or context attributes.

---

## 2. Efficiency

**O(n) token consumption.**  The recursive descent parser is linear in
the number of tokens for well-formed input.  Each token is consumed
exactly once via `advance()`.  This is the correct complexity class.

**Token normalisation on every parse.**  `create_context()` runs
`KeywordNormalizer().normalize(list(tokens))` on every `Parser`
instantiation, copying the entire token list.  For interactive use this
is negligible, but it's unnecessary work that could be avoided by
normalising during lexing.

**Profiler checks on every token.**  `ParserContext.advance()` checks
`if self.profiler:` on every token.  `enter_rule` / `exit_rule` do the
same.  When profiling is disabled (the common case), these are wasted
branches.  A null-object profiler (where every method is a no-op) would
avoid the conditionals.

**Deep call stack for simple commands.**  Parsing `echo hello` traverses
approximately 10 call frames before the first argument token is consumed.
This is inherent to recursive descent and not incorrect, but it means
error traces are deep and harder to read.

**WordBuilder inline import.**  `parse_argument_as_word()` imports
`WordBuilder` inside the method body (`from ..support.word_builder
import WordBuilder`).  This import executes on every call.  Python
caches module objects so the cost is a dictionary lookup, not a full
import, but moving it to module level would be more conventional and
marginally faster.

**No unbounded growth risk.**  `scope_stack` and `parse_stack` grow with
nesting depth but are bounded by Python's recursion limit.  The
combinator parser's `lazy` cache is O(1) per forward reference.

---

## 3. Educational Value

### Strengths

**Grammar is visible in code.**  A student reading the recursive descent
parser can follow the grammar's precedence hierarchy from top-level
statements down to individual command arguments.  Each parsing method
corresponds to a grammar rule.  This is the primary virtue of recursive
descent and the codebase preserves it well.

**AST nodes are self-documenting.**  `IfConditional`, `ForLoop`,
`CaseConditional`, `Pipeline`, `SimpleCommand` — the names tell you
what they are.  Field names like `condition`, `then_part`, `else_part`,
`variable`, `items`, `body` are descriptive without being verbose.

**Two parsers, same grammar.**  The combinator parser (`combinators/`,
4,683 lines) demonstrates how the same shell grammar can be expressed
through functional composition.  Having both implementations side-by-side
lets a learner compare imperative vs functional parsing approaches.
The recursive descent parser is natural for understanding grammar rules;
the combinator parser shows how they compose algebraically.

**Combinator primitives are clean.**  `core.py` implements `token`,
`many`, `many1`, `optional`, `sequence`, `separated_by`, `lazy`,
`between`, `skip`, `try_parse`, `keyword`, `literal`, and
`ForwardParser` — the standard combinator vocabulary.  Each has a
docstring with Args/Returns.  A student learning parser combinators
for the first time could use this file as a reference.

**Debug tooling.**  `--debug-ast`, `--debug-tokens`, and `--validate`
flags let a learner observe the parser in action.  The `visualization/`
subpackage provides 4 AST output formats: ASCII tree, compact tree,
S-expression, and DOT graph.  These are genuinely useful for
understanding how input becomes structure.

**Sub-parser sizes track grammar complexity.**  `statements.py` (103
lines) is small because statement lists are simple.
`control_structures.py` (484 lines) is larger because `if`, `while`,
`for`, `case`, `select`, `break`, `continue` each have distinct syntax.
`functions.py` (95 lines) is tiny because function definitions are
structurally simple.  The code's bulk mirrors the grammar's bulk, which
is exactly right for an educational codebase.

**Comprehensive subsystem documentation.**  The parser CLAUDE.md
documents the delegating architecture, the sub-parser contract (with a
context manager usage table), the WordBuilder entry points, and the
Word AST structure.  The combinator parser has its own companion guide.

### Weaknesses

**WordBuilder complexity is not scaffolded.**  `WordBuilder` (285 lines)
is the most complex single piece of the parser.  It decomposes
`RichToken` STRING tokens — which contain embedded `TokenPart` metadata
from the lexer — into `Word` nodes with per-part quote context.  This
involves detecting parameter expansion operators, handling composite
tokens with mixed quoted/unquoted segments, and building expansion AST
nodes from token metadata.  The CLAUDE.md cross-references help
discoverability, but there is no inline guided walkthrough for someone
encountering this code for the first time.

**Combinator `control_structures.py` is monolithic.**  At 1,306 lines,
this is by far the largest file in the parser.  It implements every
control structure (if, while, until, for, case, select, function defs,
break/continue, subshells, brace groups) in a single module.  Token
collection logic is repeated across loop types rather than factored out.
The recursive descent counterpart splits this across multiple focused
files.

**Validation and visualisation are disconnected.**  The `validation/`
subpackage (1,282 lines) provides semantic analysis and validation
rules, but validation is gated behind `enable_validation` which defaults
to `False` and no production code path enables it.  Similarly, the
`visualization/` subpackage (1,522 lines) is feature-rich but never
invoked from the main execution path.  These are potentially valuable
educational tools that are hard for a student to discover.

---

## 4. Pythonic Style

### Pythonic

**Dataclasses.**  AST nodes, `ParserConfig`, `ErrorContext`,
`HeredocInfo`, `ParseResult`, `ParserContext` all use `@dataclass` with
proper `field(default_factory=...)` for mutable defaults.

**Type hints.**  Comprehensive annotations on function signatures.
Return types like `Union[ForLoop, CStyleForLoop]` and
`Optional[Statement]` express the grammar's alternatives explicitly.
The `Generic[T]` combinator `Parser` class is properly parameterised.

**Logging.**  Parser tracing uses `logging.debug()` throughout.

**Enum types.**  `ErrorSeverity`, `ParsingMode`, `ErrorHandlingMode` are
proper enums.  `TokenType` is an enum throughout.  `frozenset` token
groups (`WORD_LIKE`, `REDIRECTS`, `CONTROL_KEYWORDS`) are used for
immutable token classification.

**Module-level factory functions.**  Parser and context creation use
plain functions (`create_context()`, `create_strict_posix_parser()`)
rather than factory classes.

**Context manager protocol.**  `ParserContext.__enter__` / `__exit__`
for state preservation is clean and idiomatic.

### Un-Pythonic

**Property wrappers for simple forwarding.**  `Parser.tokens` and
`Parser.current` are properties that forward to `self.ctx.tokens` and
`self.ctx.current`.  These exist for backward compatibility but add
indirection.  Python convention favours direct attribute access.

**One remaining inline import.**  `parse_argument_as_word()` imports
`WordBuilder` inside the method body.  PEP 8 recommends all imports at
the top of the file.  There is no circular dependency risk here.

**`hasattr` checks for own attributes.**  `_has_decomposable_parts`
(word_builder.py:219) uses `getattr(token, 'parts', None)` to check for
RichToken characteristics.  An `isinstance(token, RichToken)` check
would be more explicit.

**Backward compatibility shim classes.**  `_ErrorCollectorView` (27
lines), `ParserFactory`, `ParserContextFactory`, and
`ConfigurationValidator` are compatibility wrappers.  Individually small,
collectively they add indirection that a fresh codebase would not need.

**`_is_fd_duplication` recompiles regex on every call.**
`commands.py:47` creates `re.compile(...)` inside the method body.  The
pattern should be a module-level constant or the method should use
`re.match()` directly (which caches internally).

---

## 5. Specific Observations

### Code Smells

1. **`_check_for_unclosed_expansions` conditional chain**
   (`commands.py:59–100`): Five branches construct error messages from
   `expansion_type` strings.  A dictionary mapping `expansion_type` to
   a format template would reduce this to a lookup.
   *(Addressed in v0.136.0 — replaced with `_UNCLOSED_EXPANSION_MSGS`
   dictionary lookup.)*

2. **`is_array_assignment` speculative parsing** (`arrays.py:37–126`):
   90 lines of save-position / advance / peek / restore logic.  The
   method tries 6 different tokenisation patterns for the same syntax.
   This is correct but hard to follow.
   *(Addressed in v0.137.0 — extracted 5 focused helper methods using
   peek-based lookahead; only unbounded bracket scan retains
   advance+restore.)*

3. **Combinator `control_structures.py` token collection duplication**:
   Token-collection-until-keyword logic is repeated for while, until,
   for, select, and case — each with minor variations.  The file has a
   `_collect_tokens_until_keyword()` helper but not all parsers use it.
   *(Addressed in v0.136.0 — split into package with 3 mixin modules
   and shared `format_token_value()` utility.)*

4. **`parse_partial()` duplicates `parse()`** in
   `combinators/parser.py`:  The two methods share most of their logic
   (token filtering, newline skipping, error handling) but are written
   as separate implementations.
   *(Addressed in v0.137.0 — extracted `_prepare_tokens()` and
   `_apply_heredocs()` helpers; `parse_partial()` fallback cascade
   replaced with a loop.)*

### Notable Quality

1. **`_parse_condition_then_block` helper**
   (`control_structures.py:132–139`): The if/elif pattern is cleanly
   factored into a method that returns a `(condition, body)` tuple.

2. **`_parse_parameter_expansion` operator precedence**
   (`word_builder.py:96–145`): The operator matching algorithm uses
   earliest-position + longest-match disambiguation.  The logic is
   non-trivial but the implementation is clear, with a well-ordered
   operator list and explicit comments explaining the precedence rules.

3. **Unified argument path** (`parse_argument_as_word`): After the
   v0.135.0 consolidation, every argument consumer in the recursive
   descent parser uses the same method and the same data structure.
   This eliminates an entire class of bugs where the tuple path and the
   Word path could diverge.

4. **`ForwardParser` for recursive grammars** (`core.py:440–464`):
   Clean solution for circular references.  `define()` sets the real
   parser after all forward references are declared.

5. **Error context with suggestions** (`context.py:282–292`):
   The parser detects common missing-token patterns (missing `;` before
   `then`, missing `fi`, missing `)`) and attaches actionable
   suggestions to the error context.

---

## 6. Comparative Assessment: Recursive Descent vs Combinators

The codebase maintains two complete parser implementations.  They serve
different purposes and have different quality profiles.

| Dimension | Recursive Descent | Combinators |
|---|---|---|
| **Lines** | ~4,400 | ~4,680 |
| **File count** | 17 (core + parsers + support) | 9 |
| **Largest file** | commands.py (511 lines) | control_structures.py (1,306 lines) |
| **Grammar visibility** | Excellent — each method = one grammar rule | Good — composition is elegant but nested |
| **Code reuse** | Good — `_parse_loop_structure`, `_parse_condition_then_block` | Moderate — token collection repeated |
| **Error messages** | Rich — ErrorContext with suggestions, source lines | Basic — string error messages |
| **Word AST** | Full — `parse_argument_as_word()` unified path | Partial — uses Word for commands but simpler for control structures |
| **State management** | Centralised `ParserContext` with context manager | Implicit in token position threading |
| **Educational role** | Primary — teaches imperative parsing | Secondary — teaches functional composition |

The recursive descent parser is the production parser and has received
significantly more attention.  The combinator parser is a valuable
educational counterpoint but has areas of duplication, particularly in
`control_structures.py`, that would benefit from the same kind of
factoring that the recursive descent parser has undergone.

---

## 7. Summary Scores

| Dimension | Score | Key factor |
|---|---|---|
| **Elegance** | A- | Unified argument path; clean delegation; focused config; array parser complexity detracts |
| **Efficiency** | B+ | Correct complexity; minor constant-factor waste (normalisation, profiler checks, inline import) |
| **Educational** | A- | Grammar visible in code; dual-parser comparison; rich debug tooling; WordBuilder is steep |
| **Pythonic** | A- | Strong dataclass/typing/enum usage; one inline import and a few compat shims remain |

**Overall: A-.**

The parser is a well-structured, well-documented implementation of a
complex grammar.  The recursive descent architecture maps cleanly to the
shell grammar, making it readable and maintainable.  The v0.128–v0.135
cleanup work has been substantial and effective: dead code removal
(~3,000+ lines), argument path unification, error helper extraction,
inline import cleanup, and `_saved_states` dataclass declaration.  The
combinator parser provides a valuable educational counterpoint.

The remaining issues are minor: array parser tokenisation complexity,
a few compatibility shim classes, one inline import, and duplication
in the combinator parser's control structure file.  None affect
correctness or significantly impact readability.

---

## 8. Suggested Improvements

These are ordered by impact.  All are optional — the parser works
correctly and is well-tested.

1. **Factor combinator `control_structures.py`.** *(Done in v0.136.0)*
   Split into `control_structures/` package with 3 mixin modules
   (loops, conditionals, structures). Extracted shared
   `format_token_value()` into `utils.py`.

2. **Move WordBuilder import to module level.** *(Done in v0.136.0)*
   Moved to module-level along with RichToken, ErrorContext,
   ErrorSeverity, and ParsingMode (5 imports total across 3 files).

3. **Data-driven unclosed-expansion errors.** *(Done in v0.136.0)*
   Replaced with `_UNCLOSED_EXPANSION_MSGS` dictionary lookup.

4. **Compile regex at module level.** *(Done in v0.136.0)*
   All regex patterns compiled at module level as `_FD_DUP_RE`,
   `_SIMPLE_VAR_RE`, and `_SPECIAL_VAR_RE`.

5. **Remove compatibility shim classes.** *(Done in v0.136.0)*
   Deleted `ParserFactory`, `ConfigurationValidator`,
   `ParserContextFactory`, and `_ErrorCollectorView`. All callers
   migrated to module-level functions and `ctx` attributes.

6. **Extract helpers from `is_array_assignment()`.** *(Done in v0.137.0)*
   Broke 90-line monolithic method into 5 focused helpers using
   peek-based lookahead.  Only `_scan_bracket_assignment()` retains
   advance+restore (unbounded lookahead depth).  Main method is now a
   readable dispatcher documenting all 6 tokenisation patterns.

7. **Deduplicate combinator `parse()`/`parse_partial()`/`can_parse()`.**
   *(Done in v0.137.0)*
   Extracted `_prepare_tokens()` (normalize + skip whitespace) and
   `_apply_heredocs()` helpers.  Turned `parse_partial()` fallback
   cascade into a clean loop.  Fixed `can_parse()` to normalise
   keywords consistently with the other two methods.
