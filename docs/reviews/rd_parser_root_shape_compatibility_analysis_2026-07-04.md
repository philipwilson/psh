# RD Parser Root-Shape Compatibility Analysis and Removal Plan

Date: 2026-07-04  
Version reviewed: PSH 0.617.0

## Summary

The recursive-descent parser now uses one coherent grammar for top-level and
nested commands. That part of the design is strong. Its remaining root-shape
complexity is a compatibility transformation applied after parsing:

1. Parse the input through the ordinary command-list grammar.
2. Build the normal `StatementList -> AndOrList -> Pipeline -> Command` tree.
3. Inspect the completed tree.
4. For selected single-command programs, remove the ordinary wrappers and
   return a different root type to reproduce historical AST output.

This is not currently a duplicate grammar or a demonstrated shell-semantics
bug. It is an irregular AST contract that creates unions, special cases, and
duplicate handling throughout execution and tooling. It should be removed in
favor of one stable `Program` root.

## Current root-shape behavior

`Parser.parse()` returns `Union[CommandList, TopLevel]`
([parser.py](../../psh/parser/recursive_descent/parser.py#L123)).
`CommandList` is itself only an alias for `StatementList`
([commands.py](../../psh/ast_nodes/commands.py#L94)), while `TopLevel.items`
may contain either a `Statement` or another `StatementList`
([commands.py](../../psh/ast_nodes/commands.py#L107)).

Current RD parser results include:

| Source | Concrete root | Immediate children |
|---|---|---|
| Empty input | `StatementList` | none |
| `echo hi` | `StatementList` | `AndOrList` |
| `(echo hi)` | `StatementList` | `AndOrList` |
| `{ echo hi; }` | `StatementList` | `AndOrList` |
| `while false; do :; done` | `TopLevel` | bare `WhileLoop` |
| `f() { :; }` | `TopLevel` | bare `FunctionDef` |
| `while false; do :; done \| cat` | `StatementList` | `AndOrList` |
| `while false; do :; done; echo hi` | `StatementList` | two `AndOrList` nodes |
| `echo a & echo b` | `TopLevel` | two `StatementList` nodes |

A small syntactic modifier can therefore change the concrete root and several
wrapper levels. A bare `WhileLoop` is directly below `TopLevel`, while the same
loop followed by `| cat`, `&& echo`, `&`, `!`, or `time` remains inside the
normal `AndOrList` and `Pipeline` wrappers.

## Historical origin

Before v0.507.0, top-level control structures followed a separate parsing
path. It duplicated part of the pipeline and and/or-list grammar and produced
order-dependent trees:

```text
echo a; while ...; done
    -> one CommandList

while ...; done; echo a
    -> TopLevel[WhileLoop, CommandList]
```

The current implementation correctly removed that second grammar. Top-level
input now goes through `parse_command_list()` just like nested command lists
([parser.py](../../psh/parser/recursive_descent/parser.py#L145)). Regression
tests explicitly guard against rebuilding pipelines or and/or lists in the
top-level parser
([test_top_level_control_structure_grammar.py](../../tests/unit/parser/test_top_level_control_structure_grammar.py#L1)).

The old observable AST shape was nevertheless retained for a program
consisting of one bare compound command or function definition. That is the
compatibility layer discussed here.

## How the compatibility layer works

`_simplify_result()` first decides whether to return a `CommandList` or a
`TopLevel` ([parser.py](../../psh/parser/recursive_descent/parser.py#L160)).

For a single parsed command list, `_bare_top_level_compound()` recognizes and
unwraps the historical special case. It verifies that the tree contains:

1. Exactly one statement.
2. Either a direct `FunctionDef`, or an `AndOrList`.
3. No `&&` or `||` operators.
4. No background marker.
5. Exactly one pipeline.
6. No `!` negation or `time` prefix.
7. Exactly one pipeline command.
8. A command whose type appears in `_BARE_TOP_LEVEL_TYPES`.

If all checks pass, the parser discards the `AndOrList` and `Pipeline`
containers it just created and returns:

```text
TopLevel
└── WhileLoop
```

instead of:

```text
StatementList
└── AndOrList
    └── Pipeline
        └── WhileLoop
```

The type whitelist and reverse structural recognition are in
[parser.py](../../psh/parser/recursive_descent/parser.py#L183).

## Why this is undesirable

### 1. The parser has a content-dependent return type

Callers cannot rely on one root class. They must branch, use a union type, or
normalize the result themselves. Empty input, simple commands, functions,
bare compounds, pipelines, and background lists do not share one root
contract.

### 2. Syntactic decoration changes structural identity

The root shape of a control structure changes when it is negated, timed,
backgrounded, or placed in a pipeline. Those operators should add nodes or
attributes around a command; they should not also select a different program
root representation.

### 3. New command types require compatibility bookkeeping

A newly implemented compound-command class must be added to
`_BARE_TOP_LEVEL_TYPES`. Forgetting that update does not necessarily break
execution, but it gives the new construct a different public AST shape from
its peers.

### 4. Downstream code must support two sequence containers

The source processor branches between `execute_toplevel()` and
`execute_command_list()` and then casts the second alternative
([source_processor.py](../../psh/scripting/source_processor.py#L336)).
`Shell` exposes two execution facades that perform the same delegation
([shell.py](../../psh/shell.py#L339)).

The executor has separate `visit_TopLevel()` and `visit_StatementList()` loops
with substantially overlapping sequencing, trap, line-number, exit-status,
and errexit behavior
([core.py](../../psh/executor/core.py#L103)).

### 5. Visitors and renderers encode the distinction

Validation, linting, debugging, formatting, execution, and visualization all
need container handlers for both shapes. The formatter even assigns different
joining rules to the two containers
([formatter_visitor.py](../../psh/visitor/formatter_visitor.py#L230)).

Container identity is therefore carrying formatting policy that should be
derived from statement separators or from a documented canonical-formatting
rule.

### 6. Parser parity tests must hide the difference

The differential tests normalize both `TopLevel` and `StatementList` into an
invented `Program` representation before comparing the two parsers
([test_combinator_ast_parity.py](../../tests/parser_differential/test_combinator_ast_parity.py#L108)).
That normalization is evidence that `Program` is already the conceptual
model, but it is missing from the production AST.

The combinator parser uses another root policy and normally converts results
to `TopLevel`
([parser.py](../../psh/parser/combinators/parser.py#L158)). The two public
parser implementations therefore do not currently promise the same concrete
root.

### 7. Root-level metadata has no single owner

Future program-wide metadata—source path, complete source span, dialect,
parser identity, diagnostics, comments, or formatting policy—would have to be
attached to both root classes or kept outside the AST.

## Recommended target model

Introduce exactly one parser result type:

```python
@dataclass
class Program(ASTNode):
    statements: list[Statement] = field(default_factory=list)
```

Both parsers should return `Program` for every successful parse, including
empty input:

```text
Program
├── AndOrList
│   └── Pipeline
│       └── WhileLoop
└── AndOrList
    └── Pipeline
        └── SimpleCommand
```

Nested command bodies should continue to use `StatementList`. The distinction
then becomes clear:

- `Program`: the root of a parsed input unit.
- `StatementList`: a sequence inside a function, group, conditional, loop, or
  other compound command.
- `AndOrList`, `Pipeline`, and command nodes: the actual shell grammar.

`Program.statements` should contain the ordinary statements produced by
`parse_command_list()`. A bare compound should retain its normal
`AndOrList -> Pipeline` ancestry rather than being unwrapped only at the root.

This design avoids `Program.body: StatementList`, which would add an
unnecessary second sequence container at every root. A direct statement list
also gives `Program` a natural place for future root metadata.

## Recommended implementation strategy

PSH is currently classified as alpha and the AST does not appear to be a
documented stable third-party API. Under that assumption, the cleanest course
is one focused breaking refactor rather than a long-lived adapter. If external
AST consumers are known to exist, use the staged compatibility option later
in this document.

### Phase 1: introduce and enforce `Program`

Add `Program` to `psh/ast_nodes/commands.py`:

```python
@dataclass
class Program(ASTNode):
    """Root of one parsed shell input unit."""

    statements: list[Statement] = field(default_factory=list)
```

Export it from `psh.ast_nodes`. Add a structural test asserting that:

- `Program` is an AST node.
- `Program.statements` contains only `Statement` instances.
- Parser entry points are annotated as returning `Program`.

Do not make `Program` an alias for `TopLevel`; that would preserve the same
ambiguous data model under a new name.

### Phase 2: change the RD parser to return `Program` directly

Replace the current top-level accumulator and simplification:

```python
def parse(self) -> Program:
    statements: list[Statement] = []
    self.skip_newlines()

    while not self.at_end():
        command_list = self.statements.parse_command_list()
        statements.extend(command_list.statements)
        self.skip_separators()

    return Program(statements=statements)
```

Preserve the current line-stamping behavior while extending the list.
Depending on where line metadata is most reliable, stamp each returned
statement rather than an intermediate `StatementList`.

Delete:

- `_simplify_result()`
- `_bare_top_level_compound()`
- `_BARE_TOP_LEVEL_TYPES`
- The `TopLevel` accumulator in `Parser.parse()`
- The union return annotation

The top-level parser must continue to call `parse_command_list()`; it must not
reintroduce special parsing for control structures.

### Phase 3: make the combinator parser return the same root

Replace its post-parse `TopLevel` conversion with one `Program` conversion.
Flatten a returned `StatementList` into `Program.statements`; wrap a direct
`Statement` as a one-element program.

After this phase, differential tests should compare the two returned ASTs
directly. Remove `_program_items()` and the special
`TopLevel`/`StatementList` canonicalization from
`test_combinator_ast_parity.py`.

### Phase 4: consolidate execution

Replace:

- `Shell.execute_toplevel()`
- `Shell.execute_command_list()` for root execution
- The source processor's root-type branch

with:

```python
def execute_program(self, program: Program) -> int:
    return self._execute_with_visitor(program)
```

Add `ExecutorVisitor.visit_Program()`. Extract the shared sequence mechanics
from `visit_TopLevel()` and `visit_StatementList()`:

```python
def _execute_sequence(
    self,
    statements: Iterable[Statement],
    *,
    context: SequenceContext,
) -> int:
    ...
```

Top-level-only behavior, such as whether `set -e` exits script mode or whether
an out-of-loop `break` is reported, should be selected by execution context,
not inferred from which incidental container class reached the visitor.

Keep `visit_StatementList()` for nested bodies, delegating to the same sequence
helper with nested context.

### Phase 5: migrate analysis and rendering visitors

Replace `visit_TopLevel()` with `visit_Program()` in:

- Executor
- Formatter
- Validator and enhanced validator
- Linter
- Debug AST renderer
- Metrics and security visitors where container behavior is inherited
- ASCII, S-expression, DOT, and other AST visualizers

For simple traversal-only visitors, `visit_Program()` should just visit every
statement. Do not duplicate this loop in every visitor if the visitor base can
provide the default container traversal.

### Phase 6: make formatting independent of historical containers

Before changing the formatter, record golden output for:

- One simple command
- Multiple newline- and semicolon-separated commands
- A single bare loop or conditional
- Adjacent compound and simple commands in both orders
- Background lists
- Functions
- Heredocs attached to commands and compound commands

Implement `visit_Program()` using a documented canonical joining rule.
Background behavior should be derived from `AndOrList.background`, not from a
`TopLevel` containing nested `StatementList` objects.

If exact original separator preservation is a goal, add separator/source-span
metadata explicitly. Do not use the root container class as an indirect
separator signal.

### Phase 7: simplify heredoc traversal and parser entry points

Change all parser entry points to return `Program`:

- `parse()`
- `Parser.parse()`
- `parse_with_heredocs()`
- `create_parser(...).parse()`
- Combinator equivalents

The RD heredoc utility currently advertises
`Union[CommandList, TopLevel]`
([utils.py](../../psh/parser/recursive_descent/support/utils.py#L88)).
Change it to `Program`.

Where practical, replace heredoc traversal based on probing attributes such as
`statements`, `commands`, and `items` with the standard AST visitor or a
dataclass-child traversal. A stable root makes this substantially easier.

### Phase 8: remove legacy names and tests

Delete `TopLevel` after all production references are gone.

Then assess `CommandList = StatementList`. If `CommandList` has no distinct
semantic meaning, remove the alias and use `StatementList` consistently. If a
public deprecation period is required, retain only a deprecated import alias;
do not use it in production annotations or implementations.

Replace tests that pin historical shapes with tests for the new invariant:

```python
@pytest.mark.parametrize("source", [...])
def test_every_parse_returns_program(source):
    ast = parse(tokenize(source))
    assert isinstance(ast, Program)
```

Retain the important regression assertion that top-level parsing never
constructs `Pipeline` or `AndOrList` itself. The ordinary statement parser must
remain the sole owner of those grammar layers.

## Compatibility option for external AST users

If the AST is a supported external interface, stage the change:

1. Make internal parser methods return `Program`.
2. Add a temporary, explicit `to_legacy_root(program)` adapter.
3. Keep the old public API behind a clearly named deprecated entry point, for
   example `parse_legacy_ast()`.
4. Make the primary `parse()` return `Program`.
5. Emit a deprecation warning from the legacy entry point.
6. Publish the removal version and migrate repository callers immediately.
7. Delete the adapter on schedule.

Do not make the primary parser return legacy shapes and normalize them in each
consumer. That merely moves the compatibility layer and allows it to become
permanent.

## Tests required for the migration

### Structural tests

- Every parser entry point returns `Program`, including empty input and
  heredoc input.
- `Program.statements` never contains another `Program` or `StatementList`.
- RD and combinator parsers use the same concrete root.
- Bare compounds retain normal `AndOrList -> Pipeline` ancestry.
- Source line metadata is correct on every program statement.

### Behavioral tests

- Existing pipeline, `&&`, `||`, `!`, `time`, and background behavior.
- `set -e` at top level and inside nested lists.
- `break`, `continue`, `return`, `exit`, and `TopLevelAbort` boundaries.
- Pending traps between statements.
- `$?`, `PIPESTATUS`, `$LINENO`, and command-number updates.
- Functions, sourced scripts, `eval`, command substitutions, and subshells.
- Heredocs on simple and compound commands.

### Formatter tests

- Formatting is idempotent: `format(format(source)) == format(source)`.
- Compound/simple statement order does not alter blank-line policy.
- Background-list formatting reparses to an equivalent `Program`.
- Formatter output remains behaviorally equivalent when executed.

### Architecture guardrails

- No production import of `TopLevel`.
- No `Union[Program, StatementList]` parser return annotations.
- No `_simplify_result`, `_bare_top_level_compound`, or equivalent root
  pattern matching.
- No parser-specific root normalization in differential tests.
- The top-level parser does not directly construct pipeline or and/or-list
  nodes.

## Suggested commit sequence

Keep the refactor reviewable with focused commits:

1. `refactor(ast): add canonical Program root`
2. `refactor(parser): make recursive descent return Program`
3. `refactor(parser): align combinator root with Program`
4. `refactor(executor): unify program and statement-list execution`
5. `refactor(visitor): migrate analysis and rendering to Program`
6. `test(parser): replace legacy root-shape assertions`
7. `refactor(ast): remove TopLevel and CommandList compatibility`
8. `docs: document canonical parser result`

Run the full gate after each execution- or formatter-affecting commit. Parser
shape tests alone cannot detect changes in errexit, traps, control-flow
exceptions, or formatting.

## Definition of done

The compatibility layer is genuinely removed when:

- Every parser entry point returns `Program`.
- Neither parser contains content-dependent root conversion.
- `TopLevel` is absent from production code.
- `CommandList` is either removed or exists only as a time-bounded deprecated
  import alias.
- Source processing and execution do not branch on root type.
- Visitors implement one root handler.
- Differential tests compare parser output without root normalization.
- The formatter derives layout from statements and separators, not root
  container identity.
- Full behavioral, conformance, formatter, visitor, and parser tests pass.

## Assessment

The existing compatibility code is careful, tested, and much better than the
duplicated top-level grammar it replaced. Removing it is therefore a design
simplification, not an emergency correctness fix.

The payoff is still worthwhile: one parser result type, one execution entry
point, simpler visitors, direct parser parity, a proper owner for program
metadata, and fewer opportunities for new syntax to acquire accidental AST
differences.
