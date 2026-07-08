# Parser Combinator Subsystem Appraisal — 2026-07-06

## Scope

This is a fresh appraisal of `psh/parser/combinators/`, graded for:

- correctness against the complete supported shell language;
- textbook-quality parser-combinator design;
- architectural elegance and maintainability;
- efficiency and resource safety; and
- the work required to remove the subsystem's educational-only designation.

The review treated the combinator parser as an independent parser
implementation, not merely as a shadow of the recursive-descent parser. It
examined:

- parser selection and integration;
- the combinator result and error algebra;
- statement, pipeline, compound-command, word, expansion, array, redirection,
  and heredoc parsing;
- source locations and diagnostics;
- parser configuration;
- state isolation and token mutation;
- interactive completeness and nesting limits;
- focused, differential, integration, and production-selected tests; and
- representative performance.

The earlier June architecture review was consulted only after the fresh
inspection, as a regression checklist. Several of its recommendations have now
been implemented.

## Executive Judgment

The subsystem is a substantial educational parser with good modularization and
an increasingly valuable differential test suite. It is not production-ready.

The decisive problem is not simply that some grammar is missing. Some inputs
that the parser accepts are assigned the wrong structure and therefore execute
with the wrong meaning. A production parser must never reinterpret unsupported
syntax into a different valid program. It must either parse the input
correctly or reject it before execution.

The implementation has outgrown the label "toy parser": it handles a broad and
useful language subset, returns the canonical AST root, recursively parses
compound bodies, and passes hundreds of focused tests. However, its green
focused suite describes a compatibility island. It does not demonstrate
production readiness because the randomized grammar deliberately omits known
divergences and the production-selected test flow still has material failures.

## Grades

| Dimension | Grade | Assessment |
| --- | --- | --- |
| Educational value | B+ | A useful contrast with recursive descent, backed by meaningful differential tests. |
| Correctness on the supported-path corpus | B | The focused corpus is strong and green, but it deliberately excludes known gaps. |
| Full shell correctness | D+ | Unsupported syntax, missing source metadata, and accepted-but-wrong execution remain. |
| Textbook parser-combinator design | C- | Recognizable primitives exist, but the grammar mixes returned failures, exceptions, mutation, and cursor loops. |
| Architecture and maintainability | C+ | Recent modularization and recursive body parsing are good; contracts and state remain fragmented. |
| Clarity | B- | Local documentation is extensive, but some subsystem claims overstate functional purity and coverage. |
| Efficiency | B | Ordinary parsing is linear; it is slower than recursive descent but not prohibitively so. |
| Testing discipline | B+ | Differential testing is a major strength, but exclusions prevent it from being a readiness proof. |
| Production readiness | D+ | Safety, grammar completeness, integration, and release gating all need substantive work. |

## Validation

### Focused parser validation

The following focused selection was green:

```text
python -m pytest \
  tests/unit/parser/combinators \
  tests/parser_differential \
  tests/integration/parser/test_combinator_parity_regressions.py -q

515 passed
```

This is a useful regression gate. It is not a production gate: the random
differential grammar explicitly restricts itself to productions the two parsers
already agree on.

### Production-selected validation

The recommended quick flow was run with the combinator parser selected:

```text
python run_tests.py --quick --combinator --parallel 8
```

Combined result:

```text
12,512 passed
129 failed
1,011 skipped
12 xfailed
```

Not every failure necessarily represents a unique parser defect, but the
dominant clusters are genuine:

- the full `[[ ... ]]` grammar and regex semantics;
- recursive/interleaved `time` and `!` prefixes;
- composite case subjects and patterns;
- `select` without an `in` clause;
- `$LINENO` throughout compound structures and functions;
- function definitions inside command substitutions;
- process substitution embedded in case patterns; and
- parser diagnostics and incomplete-input behavior.

### Static checks

```text
ruff check psh/parser/combinators
```

was clean. The repository's normal mypy configuration was also clean. A strict
`--disallow-untyped-defs` check found 28 missing annotations.

Optional complexity checks identified 13 high-complexity functions. Grammar
code naturally has branching, but the concentration in case, loop,
simple-command, pipeline, redirection, and word-building routines confirms that
much of the implementation is imperative cursor parsing inside `Parser`
closures rather than declarative combinator composition.

### Performance

Representative parsing of repeated `echo x` statements scaled linearly from
100 to 4,000 statements. For the larger samples, the combinator parser was
approximately 4.2 times slower than recursive descent.

Parser construction was also approximately four times slower. Neither result
is automatically disqualifying for a shell, because execution normally
dominates parse time. The important performance risks are instead:

- repetition parsers that can succeed without making progress;
- unbounded recursive nesting;
- command-substitution re-tokenization;
- rebuilding parser graphs; and
- parsing input twice because interactive completeness is owned by the
  recursive-descent parser.

## Material Improvements Since the Previous Review

Recent changes have substantially improved the subsystem:

1. The parser returns the canonical `Program` root.
2. Compound bodies use recursive statement-list parsing instead of broad token
   slicing and reparsing.
3. Function bodies, nested brace groups, and nested control structures now
   participate in the same recursive grammar.
4. The old monolithic command and control modules have been split into more
   focused files.
5. Heredoc population uses the shared AST visitor infrastructure.
6. Functions, pipelines, redirections, arrays, and composite words have much
   better AST parity.
7. Differential tests compare canonical AST structure as well as acceptance
   and diagnostic positions.
8. Unsupported compound `[[ ... ]]` expressions are rejected instead of being
   flattened into plausible but incorrect test nodes.
9. Structured missing-terminator metadata has replaced earlier message-text
   matching in important paths.

The recursion-based body engine in
`psh/parser/combinators/commands/statements.py` is the strongest architectural
part of the current grammar. It correctly lets nested constructs consume their
own terminators.

## Production-Blocking Correctness Findings

### P0: Trailing redirections can change program meaning

`ArithmeticEvaluation` and `EnhancedTestStatement` deliberately do not consume
trailing redirections in `special_commands.py`. The statement-list loop in
`commands/statements.py` then permits another statement to start without first
requiring a separator.

That combination causes silent reinterpretation.

For example:

```sh
(( 0 )) >/dev/null && echo WRONG
```

Bash and the recursive-descent parser produce no output. The combinator parser
prints:

```text
WRONG
```

Likewise:

```sh
(( 0 )) >/dev/null || echo fallback
```

Bash and recursive descent print `fallback`; the combinator parser prints
nothing.

The combinator parser returns the arithmetic command before the redirect. It
then parses `>/dev/null && echo ...` as a second, redirection-only and-or list.
The logical operator therefore binds to the wrong statement.

This is production-blocking misexecution, not merely unsupported syntax.

#### Required correction

Every compound or special command must use one shared suffix grammar for:

- zero or more trailing redirections; and
- background/list termination at the correct grammar layer.

The statement-list grammar must require a real separator between statements:

```text
list := separators? and_or (separator and_or)* separator?
```

where `separator` includes `;`, newline, and `&`. There must be no zero-width
path from one completed statement to the next.

`&` needs to remain both a list separator and an operation on the preceding
and-or list. The current design consumes it inside and-or parsing, which makes
the surrounding list grammar harder to state correctly. A cleaner design is
for a terminated-and-or production to return both the node and the terminator,
or for the list parser to own separator consumption and apply backgrounding to
the preceding node.

### P0: Standalone process substitution produces an invalid command AST

`SpecialCommandParsers.special_command` includes process substitution as a
top-level command alternative:

```python
self.arithmetic_command
    .or_else(self.enhanced_test_statement)
    .or_else(self.process_substitution)
```

Therefore:

```sh
<(printf hi)
```

becomes a top-level `ProcessSubstitution` AST node. The executor has no command
semantics for such a node and reports an unimplemented-node error. Bash and the
recursive-descent parser instead expand it as a word in command position.

Process substitution is a word expansion, not a special command production.
Remove it from `special_command` and let simple-command word parsing own it.
There should be one process-substitution construction path.

### P1: Valid functions inside command substitution are rejected

`ExpansionParsers._validate_command_substitution()` re-tokenizes the inner
command and explicitly rejects function definitions:

```sh
echo $(f() { echo hi; }; f)
```

Bash and recursive descent print `hi`. The combinator path raises `ValueError`,
which leaks through the parser API as an unexpected internal error.

This shallow validation is not a safe approximation of the nested shell
grammar.

#### Immediate correction

Delete `_validate_command_substitution()` and delegate command-substitution
word construction to the same shared `WordBuilder` used by recursive descent.
That restores the current system contract in which command-substitution text is
parsed when executed.

#### Preferred longer-term contract

Choose one consistent design:

- parse command-substitution contents into a nested `Program` during the outer
  parse; or
- deliberately defer all nested parsing to expansion time.

Do not retain a third path that re-tokenizes and rejects selected constructs.
Normal syntax errors must become `ParseError`, never leaked `ValueError`.

### P1: AST source locations are not populated

The combinator parser uses token positions for immediate diagnostics but does
not stamp `ASTNode.line`. `$LINENO` semantics depend on the definition-site
line stored on each AST node.

This causes broad conformance failures for:

- if/elif/else;
- loops and cases;
- brace and subshell groups;
- pipelines and and-or lists;
- function definitions and calls;
- nested functions;
- eval and traps; and
- script-file execution.

Add a `located(parser)` combinator or equivalent constructor wrapper that:

1. captures the starting token;
2. runs the production;
3. stamps the resulting AST node with its starting line; and
4. preferably records a complete source span.

The public combinator parser also needs `source_text` and `line_offset`. The
wrapper in `psh/parser/__init__.py` currently discards both for the combinator
branch.

### P1: The full enhanced-test grammar is absent

`special_commands.py` explicitly limits `[[ ... ]]` to simple negation,
single-operand, unary, and three-token binary tests.

Production gaps include:

- `&&` and `||`;
- parenthesized grouping;
- operator precedence;
- multi-token regular expressions;
- quoted and unquoted regex fragments;
- per-part glob quoting;
- POSIX character classes;
- arithmetic evaluation of numeric operands;
- `BASH_REMATCH`; and
- trailing redirections.

The replacement should be a dedicated precedence grammar, for example:

```text
or-expression  := and-expression ("||" and-expression)*
and-expression := not-expression ("&&" not-expression)*
not-expression := "!"* primary
primary        := "(" or-expression ")"
                | unary-test
                | binary-test
                | word-test
```

The right operand of `=~` requires regex-specific token and quote preservation.
It cannot be reconstructed by joining ordinary shell words.

### P1: Other documented grammar gaps remain release blockers

The production-selected gate and random-differential exclusions identify these
additional gaps:

- recursive and interleaved `time`/`!` prefixes such as `! time true`,
  `time time true`, and `time ! time true`;
- valid empty prefixed pipelines;
- composite case subjects such as `case a"b"c in`;
- composite case patterns such as `a"b"c)`;
- `select name; do ...; done`, which defaults to positional parameters;
- bare `]` and `}` as command words;
- process-substitution-looking fragments embedded in case patterns; and
- some nested terminator and friendly diagnostic cases.

These cannot remain "educational-scope gaps" after production promotion.

## The Core Combinator Algebra

The central design problem is the split error model in `core.py`.

The module describes `ParseSuccess` and `ParseFailure`, including a committed
failure flag, but:

- no grammar production constructs `committed=True`;
- commitment is implemented by raising `ParseError`;
- normal failure therefore travels through returned values while committed
  failure travels through exceptions;
- `optional()` ignores the committed flag and would swallow a committed
  returned failure;
- `many()` has no progress check and can loop forever when its child succeeds
  at the same position;
- `map()`, `then()`, `sequence()`, and `skip()` reset some failure positions to
  the caller's starting position;
- farthest-error selection consequently loses useful information;
- `with_error_context()` mutates the returned failure;
- the raw mutable `ParseResult` constructor remains in over 100 call sites; and
- heterogeneous ordered choice falls back to loose typing.

The current grammar therefore has textbook-shaped combinator names without one
coherent combinator semantics.

### Required core model

Use immutable result variants:

```python
@dataclass(frozen=True)
class Success(Generic[T]):
    value: T
    next_position: int


@dataclass(frozen=True)
class Failure:
    position: int
    expected: frozenset[str]
    contexts: tuple[str, ...]
    committed: bool
    kind: FailureKind
```

The error position and backtracking state must be separate. A parser can
backtrack to its original input position while still reporting that its best
failure occurred farther into the stream.

Provide explicit operations for:

- `attempt()` — permit controlled backtracking;
- `cut()` — commit after an unambiguous prefix;
- `label()` — replace low-level expectations with a grammar label;
- `context()` — add structured nesting context;
- `eof()` — require completion; and
- progress-checked `many()` and `separated_by()`.

`optional()` must propagate committed failure. Every repetition combinator must
treat success without position advancement as an internal parser-definition
error.

Normal syntax errors should remain in the result algebra. The public parser
boundary should convert the final failure to `ParseError` exactly once.
Exceptions should be reserved for invariant violations and implementation
defects.

## State, Configuration, and Integration

### Caller-owned tokens are mutated

`ParserCombinatorShellParser._prepare_tokens()` copies the list but not the
tokens before `KeywordNormalizer` mutates their types and keyword flags.
Pipeline parsing also demotes a `TIME` token to `WORD` in place after a pipe.

This means parsing can change caller-owned input and can depend on which parser
or parse attempt ran first.

Production correction:

- accept `Sequence[Token]`;
- make lexical tokens immutable, or normalize into fresh immutable tokens;
- represent context-sensitive keyword interpretation in parser state or a
  normalized token view; and
- test that repeated parsing leaves the original tokens unchanged.

### Configuration is inert

The combinator subsystem stores and forwards `ParserConfig`, but no combinator
grammar code reads the relevant fields. It therefore does not enforce:

- strict POSIX mode;
- arithmetic feature enablement;
- Bash arithmetic policy;
- Bash conditional policy; or
- configured error collection.

`configure()` also rebuilds modules twice because `_initialize_modules()`
already builds the complete parser before `configure()` calls the build method
again.

Either remove configuration from the combinator API or implement the complete
public contract. A production alternative parser must behave like the selected
parser configuration, not merely retain its values.

### Interactive completeness is owned by recursive descent

`CommandAccumulator._trial_parse()` always uses the recursive-descent parser as
the completeness oracle. If the active parser is combinator, the resulting AST
and tokens are discarded and execution reparses the source.

Thus combinator mode does not independently own:

- complete versus incomplete classification;
- open-construct hints;
- expected closing delimiters;
- nesting limits; or
- the reusable trial AST.

A production combinator parser should return a structured outcome such as:

```text
Complete(Program)
Incomplete(expected_closers, open_constructs)
Invalid(Failure)
```

The command accumulator should use the selected parser through a common
interface rather than shadowing one parser with the other.

### Nesting has no explicit combinator limit

Direct combinator-parser use can reach Python `RecursionError` with sufficiently
nested groups. The shell's global recursion-limit adjustment and the
recursive-descent trial parser currently mask some of this in end-to-end use.

The combinator parser needs an explicit nesting budget in parse state and a
controlled `ParseError` when the budget is exceeded.

### Heredoc and parser state should be per parse

The visitor-based heredoc pass is sound, but the parser stores the heredoc map
on the parser instance. A later ordinary parse can therefore observe state from
an earlier `parse_with_heredocs()` call.

Pass heredoc contents in an immutable per-parse context or apply them explicitly
to the returned AST without mutating persistent parser configuration.

## AST and Word Construction

The combinator parser correctly reuses much of the production word-building
behavior, but it imports `WordBuilder` from the
`recursive_descent.support` namespace. That is a shared parsing service living
under the wrong owner.

Move token-to-`Word` construction into a parser-neutral module and make both
parsers depend on it.

Other cleanup:

- remove the duplicate special-command process-substitution parser;
- replace synthetic `Token` objects carrying dynamically attached
  `array_init` attributes with typed AST construction;
- use one composite-word parser for simple commands, loop items, case subjects,
  case patterns, test operands, and redirection targets; and
- make unrecognized redirection shapes fail closed.

`commands/redirections.py` currently retains a lenient fallback that constructs
a `Redirect` with an empty target for an unrecognized duplication-token shape.
A parser should reject an invalid or unknown operator representation rather
than manufacture a plausible AST.

## Textbook-Quality Assessment

The subsystem is not currently textbook-quality parser-combinator code.

It exposes recognizable primitives:

- `Parser`;
- `map`;
- `then`;
- `or_else`;
- `many`;
- `optional`;
- `sequence`;
- `between`; and
- `lazy`.

But grammar composition is not the dominant mechanism throughout the parser.
Large productions remain hand-written cursor loops that return `ParseResult`.
Commitment bypasses the result algebra through exceptions. Tokens and errors
are mutated. Some sublanguages are collected as token slices and parsed with
special-purpose imperative code.

Imperative parsing inside a combinator implementation is not inherently wrong;
shell grammar has context-sensitive boundaries and embedded sublanguages.
However, the educational documentation should describe the design honestly as
a hybrid until:

- backtracking and cut semantics live in the algebra;
- parser state is immutable from the caller's perspective;
- grammar alternatives and sequencing preserve structured errors; and
- the major productions are visibly expressed through the combinator
  vocabulary.

The goal should not be to port every recursive-descent routine into a closure
returning `ParseResult`. That would create a second recursive-descent parser
with combinator names. Shared semantic services should be extracted, while the
combinator implementation owns structural composition.

## Efficiency Assessment

The measured ordinary-case complexity is good: parsing scales linearly.
Approximately four-times slower parsing is acceptable provisionally because
shell execution normally dominates. It should be tracked, not optimized before
correctness.

Packrat parsing is not presently justified. Most shell command productions can
be selected using leading-token dispatch plus explicit cuts. Memoization would
increase memory consumption without correcting the current semantic and state
problems.

Higher-value efficiency work:

1. Add progress guards to repetition.
2. Add explicit nesting limits.
3. Stop re-tokenizing command substitutions.
4. Build the grammar graph exactly once per immutable configuration.
5. Let the selected parser's trial AST be reused.
6. Use token-discriminated dispatch before expensive ordered alternatives.
7. Establish parse-time and peak-memory benchmarks over realistic scripts,
   invalid inputs, and deeply nested constructs.

## Test Strategy Assessment

The differential tests are the strongest part of the subsystem. They have
prevented many structural regressions and helped move compound parsing toward a
canonical AST.

The current limitations are:

- the random grammar deliberately excludes known divergences;
- some parity tests check only successful AST construction rather than exact
  structure or behavior;
- some unit tests tolerate generic exceptions;
- documented combinator gaps are skipped or routed around in shared tests; and
- the focused suite is much narrower than the selected-parser production flow.

For production, tests must stop treating the recursive-descent implementation
as the only source of truth. The required triangle is:

```text
Bash behavior
      / \
     /   \
recursive-descent --- combinator
```

Use:

- Bash for language behavior and status;
- canonical AST equality between PSH parsers;
- accept/reject parity for invalid syntax;
- structured diagnostic parity;
- execution parity through the same executor;
- unrestricted random generation;
- mutation and repeated-parse tests;
- formatter parse/format/reparse tests;
- resource-limit tests; and
- performance regression tests.

## Recommended Production Programme

### Phase 0: Eliminate unsafe acceptance

Before adding broad syntax:

1. Fix statement separators.
2. Parse redirection suffixes on `(( ... ))` and `[[ ... ]]`.
3. Remove process substitution from top-level special-command alternatives.
4. Remove the shallow command-substitution validator.
5. Fail closed on unknown redirect forms.
6. Add exact Bash/RD/combinator regressions for every demonstrated case.
7. Establish the invariant: unsupported syntax must fail before execution and
   must never produce a different executable AST.

This is the minimum safety gate.

### Phase 1: Finish the combinator algebra

1. Introduce immutable success and failure variants.
2. Separate farthest error position from backtracking position.
3. Implement cut, attempt, label, context, and EOF.
4. Add progress checks.
5. Move committed syntax errors out of exceptions.
6. Tighten parser generics and eliminate raw result construction.
7. Build recursive grammar references once through explicit forward cells.

This is the central textbook-quality refactor.

### Phase 2: Complete the grammar

1. Implement the full `[[ ... ]]` precedence grammar.
2. Implement complete recursive `time`/`!` prefix semantics.
3. Use the canonical composite-word parser for case subjects and patterns.
4. Support no-`in` `select`.
5. Complete the command-position word token set.
6. Correct process-substitution handling in every word context.
7. Apply a single compound-command suffix parser everywhere.

### Phase 3: Satisfy the public parser contract

1. Stamp source lines and preferably full spans.
2. Accept `source_text` and `line_offset`.
3. Enforce `ParserConfig`.
4. Return structured incomplete-input results.
5. Own open-construct hints.
6. Add a documented nesting limit.
7. Make tokens, heredoc data, and diagnostics per-parse and reentrant.
8. Remove the recursive-descent shadow parse from combinator-selected
   completeness handling.

### Phase 4: Prove readiness

Promotion should require all of the following:

- `python run_tests.py --combinator` fully green;
- no parser-specific conformance skips;
- exact canonical AST equality for all shared valid inputs;
- accept/reject and structured diagnostic parity for invalid inputs;
- three-way execution comparison against Bash;
- random generation without known-gap exclusions;
- formatter and parse/reparse behavior preservation;
- proof that input tokens are unchanged;
- deterministic repeated parsing;
- safe independent parser instances;
- controlled behavior at the nesting limit; and
- stable linear performance and memory benchmarks.

## Production Acceptance Criteria

The educational-only label should be removed only when:

1. There are no known accepted-but-wrong programs.
2. Every supported Bash/PSH construct has an owned grammar production.
3. Unsupported constructs fail deterministically with status 2.
4. The combinator parser honors source, configuration, completeness, heredoc,
   and nesting contracts independently.
5. The selected-parser full test suite is a mandatory release gate.
6. Differential fuzzing has no exclusions for known combinator gaps.
7. Parser input is observationally immutable.
8. Errors are structured and flow through one result model.
9. Performance remains linear under valid, invalid, and nested input.
10. The documentation accurately describes measured behavior rather than an
    approximate coverage percentage.

## Strategic Conclusion

This subsystem cannot reach the production bar through isolated parity patches
alone. It needs:

- an immediate safety pass;
- one coherent combinator result and error algebra;
- complete grammar treatment for the documented gaps;
- source/configuration/completeness integration; and
- mandatory production-selected parity as a release gate.

Maintaining two production parsers creates a permanent synchronization cost.
Every future grammar or diagnostic change must either be implemented twice or
be expressed through shared parser-neutral services with two structural
front-ends.

If the project is willing to make combinator parity release-blocking, the
roadmap above is technically credible. If it is not willing to pay that
continuing maintenance cost, retaining the educational-only designation is the
correct engineering decision.
