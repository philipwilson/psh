# Parser Combinator Architecture Review - 2026-06-15

## Scope

Fresh review of the parser combinator subsystem in `psh/parser/combinators/`,
with supporting reads of the focused combinator tests in
`tests/parser_differential/` and `tests/unit/parser/combinators/`.

This review does not rely on prior review documents. It grades the subsystem
against the user's requested standard: correctness, textbook parser-combinator
quality, code quality, architectural elegance, and economy.

Important context: `psh/parser/CLAUDE.md` currently marks the combinator parser
as **educational only** and outside the production quality bar. This review
therefore gives two judgments: whether the code is acceptable as an educational
counterpoint, and whether it is textbook/production-quality parser-combinator
code.

Validation run:

```text
python -m pytest tests/parser_differential tests/unit/parser/combinators -q
362 passed in 0.29s
```

## Overall Judgment

The subsystem is a useful educational implementation with a strong and
improving characterization harness. It is not textbook-quality parser
combinator code, and it is not production-quality as a replacement parser.

The recent work materially improved it: diagnostic helpers are now centralized,
missing nested terminators are tagged structurally rather than detected by
message text, and compound bodies increasingly use recursive statement-list
parsing rather than token slicing. Those changes move the subsystem in the
right direction.

The remaining architecture is still a hybrid: simple combinator primitives,
recursive-descent-style scanning loops, token collection/reparse phases,
post-construction parser mutation, and exception-based commitment are all mixed
together. That is practical for a parity-driven educational parser, but it is
not elegant or economical in the textbook sense.

## Grades

| Dimension | Grade | Rationale |
| --- | --- | --- |
| Correctness against pinned corpus | B | Focused combinator suite is green; AST, rejection, and diagnostic-position parity tests cover a meaningful slice. |
| Test harness | A- | Differential parity against recursive descent is the strongest part of the subsystem. Message-text parity is intentionally not complete. |
| Textbook parser-combinator design | C | The primitives are recognizable, but the grammar relies heavily on hand-written scans, mutation, and exceptions. |
| Error model | C+ | `raise_committed_error()` and structured `missing_terminator` tagging are real improvements, but commitment is still outside `ParseResult`. |
| Grammar architecture | C+ | `build_statement_list()` is a good direction; conditions, function bodies, arithmetic, and `[[ ]]` remain slice/collect parsers. |
| AST fidelity | B- | Many AST parity cases pass, but special-command/test expression parsing still admits simplifications and metadata loss. |
| Code economy | C+ | Several modules are too broad, and array/process/test logic is duplicated between command, array, expansion, and special parsers. |
| Production readiness | C | Good educational subsystem; not ready as a production parser without a deeper core/error/grammar refactor. |

## Strengths

1. The differential tests are high leverage.

   `tests/parser_differential/test_combinator_ast_parity.py` checks canonical
   AST equivalence rather than merely accept/reject behavior. The corpus covers
   simple commands, composite words, pipelines, redirects, arrays, compound
   commands, functions, tests, arithmetic, and flow-control statements.

   `tests/parser_differential/test_combinator_diagnostic_parity.py` separately
   pins exception class, EOF signal, offending token identity, source position,
   line, and column. That is the right staging: it tightens stable diagnostics
   without pretending message text is already equivalent.

2. The committed-diagnostic cleanup is a real architectural improvement.

   `psh/parser/combinators/diagnostics.py` now centralizes
   `error_context_for_token()`, `raise_committed_error()`, and
   `is_missing_nested_terminator()`. The previous reviewer concern about
   triplicated `_is_missing_nested_terminator` helpers has been addressed.

   More importantly, missing nested terminators are tagged via
   `error.missing_terminator` rather than inferred by substring-matching the
   diagnostic message. That is the correct direction.

3. `build_statement_list()` is the best architectural move in the current
   parser.

   `CommandParsers.build_statement_list()` explicitly avoids `many()` because
   `many()` would swallow real command failures. It also uses recursive
   statement parsing so nested loops/conditionals consume their own terminators.
   That is closer to a correct grammar model than earlier token-slicing
   approaches.

4. The AST output is increasingly aligned with the production parser.

   Word construction delegates to the shared `WordBuilder` in several places,
   arrays preserve `Word` metadata, redirects carry target words, and case
   patterns preserve enough quote context to match recursive descent in the
   pinned corpus.

5. The subsystem is honest about its status.

   `psh/parser/CLAUDE.md` and `ParserCombinatorShellParser` both say this is
   experimental/educational and not the production parser. That is important:
   the code is much more defensible under that contract than under a production
   parser contract.

## Major Uglies

### 1. The core has no first-class committed failure model

`ParseResult` is a boolean success/value/error tuple with a position. It does
not distinguish soft failure from committed failure, does not carry an error
kind, does not preserve expected sets, and does not track farthest failure.

Consequences:

- `Parser.or_else()` always retries the alternative after any `ParseResult`
  failure.
- `many()` and `separated_by()` stop on any failure, including failures that
  should become syntax errors after input was consumed.
- Production-like commitment is implemented by raising `ParseError` from inside
  parsers, bypassing normal combinator composition.
- Several places must remember to call `raise_committed_error()` manually after
  seeing `|`, `&&`, `do`, `then`, `[[`, array starts, etc.

This is the central reason the subsystem is not textbook quality. A textbook
parser-combinator library needs a failure channel rich enough to express at
least:

- recoverable failure,
- committed/cut failure,
- expected labels,
- source location,
- preferably farthest-error selection.

Current references:

- `psh/parser/combinators/core.py`: `ParseResult`
- `psh/parser/combinators/core.py`: `Parser.or_else()`
- `psh/parser/combinators/core.py`: `many()`, `sequence()`, `separated_by()`
- `psh/parser/combinators/diagnostics.py`: `raise_committed_error()`

### 2. Some important grammar paths still collect token slices and reparse them

`build_statement_list()` is now recursive and elegant for many compound bodies,
but the subsystem has not consistently applied that model.

Examples:

- `if` condition parsing collects `condition_tokens` until `then`, then parses
  that slice as a statement list.
- `while` and `until` collect `condition_tokens` until `do`, then parse the
  slice.
- function bodies collect `body_tokens` until a matching `}`, then parse that
  inner list manually.
- enhanced tests collect tokens until `]]`, then pass them to a simplified
  `_parse_test_expression()`.
- arithmetic commands collect tokens until `))` and stringify them.

Token collection is often necessary for shell sublanguages, but the current
implementation uses it as an ad hoc control-flow mechanism rather than a
well-defined parser mode. It loses direct source-stream continuity, creates
inner/outer position mapping problems, and forces diagnostic remapping logic.

Current references:

- `psh/parser/combinators/control_structures/conditionals.py`: if condition
  token collection
- `psh/parser/combinators/control_structures/loops.py`: loop condition token
  collection
- `psh/parser/combinators/control_structures/structures.py`: function-body
  token collection and reparsing
- `psh/parser/combinators/special_commands.py`: arithmetic and enhanced-test
  token collection

### 3. Function-body diagnostics still contain message-text coupling

The previous missing-terminator helper duplication is fixed, but
`StructureParserMixin._parse_function_body()` still rewrites soft failure
messages by checking substrings such as `"expected 'fi'"`,
`"expected 'done'"`, `"expected 'esac'"`, and `"expected 'then'"`.

This is less severe than the old nested-terminator triplication because it is
localized, but it is still fragile. It will break if message text is improved,
translated, normalized, or made more bash-like.

Recommended direction: attach a structured diagnostic reason/code to parser
failures, for example:

```python
class ParseFailureKind(Enum):
    EXPECTED_COMMAND = auto()
    EXPECTED_THEN = auto()
    MISSING_TERMINATOR = auto()
    EMPTY_COMPOUND_BODY = auto()
```

Then remap by kind, not by English text.

### 4. Parser wiring is mutable and phase-sensitive

`ParserCombinatorShellParser._initialize_modules()` constructs token,
expansion, command, control, special, and heredoc parsers, then calls
`_wire_dependencies()`, then `_build_complete_parser()`. `CommandParsers` also
has `ForwardParser` fields and a `set_command_parser()` method that replaces
pipeline and and-or parsers after control structures exist.

This works, but it is not elegant. The grammar graph is not a stable value; it
is built in phases and then patched. Readers must understand which parser
attributes are placeholders, which have been replaced, and which have only been
initialized after `set_command_parsers()`.

Recommended direction: introduce a small grammar builder/fixpoint object that
owns recursive references explicitly. Either:

- define all recursive parser cells first, then fill them once; or
- keep `ForwardParser`, but make it the only recursion mechanism and remove
  ad hoc post-construction replacement of pipeline/and-or parsers.

### 5. Several modules are too broad

Line-count scan:

- `commands.py`: 878 lines
- `special_commands.py`: 755 lines
- `loops.py`: 578 lines
- `core.py`: 484 lines
- `parser.py`: 424 lines
- `heredoc_processor.py`: 418 lines

Some size is normal for shell grammar, but the responsibilities are mixed:

- `commands.py` handles redirects, simple-command word grouping, assignment
  parsing coordination, pipeline parsing, and-or parsing, statement lists, and
  top-level helper factories.
- `special_commands.py` handles arithmetic commands, enhanced tests, array
  parsing, process substitution, and utility word building.
- `loops.py` handles ordinary loops, C-style loop parsing, select, break, and
  continue.

The result is not disastrous, but it is not economical. Review and maintenance
cost is high because independent language concerns are braided together.

### 6. Array and process-substitution parsing are duplicated

Array parsing appears both in `arrays.py` and in `special_commands.py`.
Process-substitution parsing appears in both `expansions.py` and
`special_commands.py`.

The active command path uses `ArrayParsers` from `commands.py`, while
`SpecialCommandParsers` still builds array parsers that are not included in
`special_command`. That code may be covered by unit tests, but architecturally
it is a stale second implementation.

Recommended direction:

- Make `arrays.py` the single implementation for array assignment/init parsing.
- Remove or deprecate the array builders in `special_commands.py`.
- Do the same for process substitution: one parser/AST construction path, not
  two string-extraction implementations.

### 7. `[[ ... ]]` and arithmetic are characterization parsers, not robust subgrammars

The enhanced-test parser recognizes simple unary, simple binary, negation, and
then falls back to treating complex expressions as a loose binary expression.
It explicitly documents that quote context is not tracked for fallback operands.

Arithmetic commands stringify token values with whitespace normalization and
skip optional redirection parsing with a comment saying "For now, skip
redirection parsing to keep it simple."

That is acceptable for educational coverage and current parity cases, but not
for production-quality shell parsing. These should be treated as sublanguages
with their own parsers or delegated consistently to the production parser's
subsystems.

### 8. Type precision is weak

Many parser functions return raw `ParseResult`, raw `Parser`, or
`ParseResult` with implicit value invariants guarded by `assert result.value is
not None`. `ParseResult.success == True` does not prove `value is not None` to
the type checker because success and value are not modeled as a discriminated
union.

Recommended direction:

- Split `ParseSuccess[T]` and `ParseFailure` variants, or use a discriminated
  dataclass union.
- Carry structured failure details in `ParseFailure`.
- Reserve exceptions for unrecoverable internal defects, not normal committed
  parse failures.

## Are They Textbook Quality?

No.

The subsystem has textbook-shaped primitives: `Parser`, `map`, `then`,
`or_else`, `many`, `optional`, `sequence`, `between`, and `lazy`. But textbook
quality is not just having those functions. A high-quality parser-combinator
implementation would make grammar composition the main way parsing works, and
would model errors/backtracking/cut behavior inside the combinator algebra.

This subsystem still relies on:

- hand-written scanning loops,
- token-slice reparsing,
- exception-based commitment,
- mutable grammar patching,
- local diagnostic conventions,
- duplicated mini-parsers for the same constructs.

So the right label is: **useful educational parser with good parity tests, not
textbook-quality parser-combinator architecture.**

## Correctness Assessment

The current correctness story is much stronger than the architecture:

- 362 focused combinator tests pass.
- AST parity corpus is broad for an educational parser.
- rejection parity covers many missing-terminator, empty-body, redirect, pipe,
  and and-or failure cases.
- diagnostic parity now pins source positions and token identity for a stable
  subset.

The main caveat is that this is characterization correctness against recursive
descent for selected cases, not comprehensive shell grammar correctness. The
repo explicitly documents known gaps and says conformance work does not target
this parser.

## Recommended Roadmap

### Phase 1: Small cleanup PRs

1. Remove stale duplicate array parsing from `special_commands.py`, or mark it
   private/test-only with a clear deprecation path.
2. Collapse duplicate process-substitution parsing into one implementation.
3. Replace the remaining function-body message substring checks with structured
   diagnostic kinds.
4. Add a short architecture note describing the intended status of
   `build_statement_list()` as the preferred compound-body engine.

### Phase 2: Core parser model

1. Redesign `ParseResult` as a discriminated success/failure model.
2. Add committed failure/cut semantics to the core.
3. Add expected labels and farthest-error tracking.
4. Update `or_else()`, `many()`, `separated_by()`, `sequence()`, and
   `between()` so they preserve the right failure instead of always resetting
   or swallowing.
5. Move committed syntax errors out of exceptions where practical.

This is the highest-value architectural improvement. It would make the rest of
the parser less dependent on local discipline.

### Phase 3: Grammar simplification

1. Replace condition token collection with compositional "parse until
   separator + keyword" helpers that operate on the original stream.
2. Replace function-body token slicing with `build_statement_list()` plus a
   `RBRACE` terminator mode, preserving direct outer-stream positions.
3. Factor pipeline/and-or parsing so initial and fully wired parsers are not
   separate definitions patched after construction.
4. Split `commands.py` into simple command, redirects, pipeline/and-or, and
   statement-list modules.

### Phase 4: Sublanguage decisions

1. Decide whether `[[ ... ]]` and arithmetic are intentionally shallow in the
   educational parser. If yes, document the boundary and remove comments that
   read like abandoned work.
2. If no, give them real subgrammar parsers or delegate to shared production
   parser helpers.

## Suggested Immediate Next Work

The best next PR is not another parity patch. It should be a cleanup PR:

1. Remove or consolidate the duplicate array/process-substitution parsers in
   `special_commands.py`.
2. Add structured diagnostic kinds for the remaining function-body remaps.
3. Keep the focused combinator test suite green.

That work is small enough to review and would reduce code volume and fragility
without forcing the larger `ParseResult` redesign immediately.

