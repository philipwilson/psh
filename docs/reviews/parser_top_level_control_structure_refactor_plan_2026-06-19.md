# Parser Top-Level Control-Structure Refactor Plan

Date: 2026-06-19

Related review item: `docs/reviews/code_architecture_teaching_quality_review_2026-06-18.md`, priority #3: "Simplify the parser top level so the grammar has one obvious path."

## Goal

Make recursive-descent top-level parsing use the same grammar path as nested command lists:

```text
program -> command_list
command_list -> statement*
statement -> function_definition | and_or_list
and_or_list -> pipeline (&&/|| pipeline)* [&]
pipeline -> pipeline_component (|/|& pipeline_component)*
pipeline_component -> simple_command | compound_command | subshell | brace_group | [[ ]] | (( ))
```

The current code mostly has this machinery already. The problem is that `Parser._parse_top_level_item()` special-cases top-level control structures, then manually re-wraps them when followed by `|`, `|&`, `&&`, `||`, or `&`. That creates a second grammar path for the same syntax and makes the parser harder to teach.

## Current State

### Files Involved

- `psh/parser/recursive_descent/parser.py`
- `psh/parser/recursive_descent/parsers/statements.py`
- `psh/parser/recursive_descent/parsers/commands.py`
- `psh/parser/recursive_descent/parsers/control_structures.py`
- `tests/unit/parser/test_parser_migration.py`
- `tests/unit/parser/test_background_lists.py`
- `tests/parser_differential/test_combinator_ast_parity.py`

### Current Duplicate Path

`Parser.parse()` loops over `_parse_top_level_item()`.

`_parse_top_level_item()` currently does three different things:

1. Function definition:
   Calls `self.functions.parse_function_def()`.

2. Control keyword at top level:
   Calls `self.control_structures.parse_control_structure()`, then manually handles:
   - `control | cmd`
   - `control |& cmd`
   - `control && cmd`
   - `control || cmd`
   - `control &`
   - bare `control`

3. Anything else:
   Calls `self.statements.parse_command_list()`.

The normal path already exists:

- `StatementParser.parse_statement()` handles function definitions, otherwise parses `and_or_list`.
- `StatementParser.parse_and_or_list()` handles `&&`, `||`, and trailing `&`.
- `CommandParser.parse_pipeline()` handles `|` and `|&`.
- `CommandParser.parse_pipeline_component()` handles control structures as pipeline components.

### Why This Matters

The duplicate top-level path increases maintenance risk:

- `&` behavior is encoded once in `StatementParser._apply_background()` and again manually in `Parser._parse_top_level_item()`.
- Pipeline construction for top-level control structures uses `parse_pipeline_with_initial_component()`, a special helper that should become unnecessary.
- A student tracing the grammar has to learn that top-level control structures bypass the normal statement path.
- AST wrapper shape differs by syntactic category: top-level compound commands tend to return `TopLevel`, while ordinary command lists often return `CommandList`.

## Design Decision: Root AST Shape

This refactor has one important compatibility decision.

### Option A: Preserve Current Root Shape Where Practical

Keep returning `TopLevel` for single top-level function definitions and single bare top-level compound commands, even after parsing through the normal statement path.

Pros:

- Smaller test update surface.
- Less risk to callers that distinguish `TopLevel` from `CommandList`.
- Better first refactor step.

Cons:

- Keeps some root-wrapper policy in `Parser`.
- The grammar is cleaner internally, but root simplification remains historically shaped.

### Option B: Normalize More Programs To `CommandList`

Let a single top-level compound command parsed through `parse_command_list()` simplify to `CommandList`, because control structures are valid `Statement`s.

Pros:

- Simpler root model.
- Fewer special cases.
- Better long-term teaching model.

Cons:

- Larger test and possibly caller update.
- Existing tests explicitly expect top-level compounds to be wrapped in `TopLevel`.
- Needs a broader audit of visitors, script execution, debug output, formatter, and parser parity tests.

### Recommendation

Use Option A for this refactor. Make the grammar path single first, and leave root-wrapper normalization as a separate follow-up. The plan below still asks for tests that document the current root shape so the team can later choose to simplify it deliberately.

## Target Architecture

### Parser

`Parser.parse()` should become a thin program/root wrapper around `StatementParser`:

- Skip leading newlines.
- Repeatedly parse one top-level statement or function definition through a shared entry point.
- Append parsed items to `TopLevel`.
- Skip separators.
- Simplify root shape through `_simplify_result()`.

`Parser._parse_top_level_item()` should no longer parse control structures directly.

Possible end state:

```python
def _parse_top_level_item(self) -> Optional[Union[Statement, StatementList]]:
    item = self.statements.parse_top_level_statement()
    return item
```

Or remove `_parse_top_level_item()` entirely if `parse()` can call the statement parser directly.

### StatementParser

Add one explicit method for top-level parsing if the root-wrapper policy needs to be preserved:

```python
def parse_top_level_statement(self) -> Optional[Union[Statement, StatementList]]:
    ...
```

This method should delegate to the same core machinery as nested statement lists. It may exist only to handle root-wrapper policy and line stamping.

The important invariant:

> No method in `Parser` should manually assemble an `AndOrList` or `Pipeline` for a control structure.

### CommandParser

`parse_pipeline_with_initial_component()` should become dead after the refactor and should be removed once tests pass.

If it cannot be removed immediately, mark it as transitional and add a test or `rg` guard proving only the intended caller remains. The preferred result is deletion.

### ControlStructureParser

No major behavior change should be needed. Its methods already parse trailing redirections on compound commands and set `background=False`; backgrounding should be applied at `and_or_list` level by `StatementParser._apply_background()`.

## Migration Plan

### Phase 0: Characterize Before Changing

Add tests first. These tests should capture current behavior and protect the refactor from semantic drift.

Add parser-level tests for AST shape:

- `while false; do :; done`
- `while false; do :; done | cat`
- `while false; do :; done && echo ok`
- `while false; do :; done || echo no`
- `while false; do :; done &`
- `if true; then echo yes; fi`
- `if true; then echo yes; fi | cat`
- `if true; then echo yes; fi && echo after`
- `case x in x) echo x ;; esac | cat`
- `for x in a; do echo "$x"; done &`

Add execution-level tests where AST shape is not enough:

- Top-level control structure in a pipeline still pipes output.
- Top-level control structure in an and-or list still short-circuits correctly.
- Top-level control structure backgrounding still returns promptly and `wait` observes completion.
- Redirections on compound commands still apply before pipeline/list/background handling.

Suggested test locations:

- `tests/unit/parser/test_top_level_control_structure_grammar.py`
- Extend `tests/unit/parser/test_background_lists.py`
- Possibly extend `tests/parser_differential/test_combinator_ast_parity.py` for normalized parity cases.

### Phase 1: Introduce Shared Top-Level Statement Entry

Add a method to `StatementParser`:

```python
def parse_top_level_statement(self) -> Optional[Union[Statement, StatementList]]:
    return self.parse_statement()
```

Initially this can be a trivial wrapper. The value is to give `Parser.parse()` a named dependency and a future place for any top-level-only root policy.

Then change `Parser._parse_top_level_item()` to:

```python
def _parse_top_level_item(self):
    return self.statements.parse_top_level_statement()
```

At this point, do not delete imports or helpers yet. Run focused tests and inspect failures.

Expected failures:

- Tests that expected a bare top-level control structure to be a direct `TopLevel.items[0]` compound node may now see an `AndOrList` containing a `Pipeline` containing that compound.
- Tests that expected `TopLevel` for single compound commands may now see `CommandList`, depending on `_simplify_result()` behavior.
- `$LINENO` tests may expose a missing or doubled line stamp.

### Phase 2: Preserve Or Deliberately Update Root Shape

If Option A is chosen, preserve current root shape explicitly and locally.

Possible approach:

1. Let the normal grammar parse an `AndOrList`.
2. In `_simplify_result()` or `parse_top_level_statement()`, unwrap only the historical bare-compound shape:
   - exactly one `AndOrList`
   - exactly one `Pipeline`
   - no `&&`/`||`
   - no background
   - exactly one command
   - command is a control structure that historically returned as a top-level item
3. Do not unwrap if the compound is piped, backgrounded, or part of an and-or chain.

This keeps the parser grammar path unified while isolating root compatibility as presentation/root policy.

If Option B is chosen instead, update tests and documentation to state that top-level compound commands are ordinary statements inside `CommandList`.

Recommendation: choose Option A now, and create a follow-up review item for root shape normalization.

### Phase 3: Delete The Special Pipeline Helper

Once `Parser._parse_top_level_item()` no longer uses direct control parsing:

1. Remove `CommandParser.parse_pipeline_with_initial_component()`.
2. Remove now-unused imports from `parser.py`:
   - `AndOrList`
   - `Pipeline`
   - possibly `Statement`
   - possibly `cast`
   - possibly `TokenType`
3. Run `rg "parse_pipeline_with_initial_component"` and confirm no references.
4. Run parser and relevant integration tests.

### Phase 4: Tighten Documentation

Update parser docs to describe the single path:

- `psh/parser/CLAUDE.md`
- `ARCHITECTURE.md`
- Possibly `docs/architecture/tour_of_psh_internals.md`

Docs should state:

- Top-level parsing delegates to `StatementParser`.
- Control structures are pipeline components through `CommandParser.parse_pipeline_component()`.
- Root AST wrapper simplification is separate from grammar parsing.

### Phase 5: Add Guardrails

Add tests that prevent reintroducing the duplicate path:

1. A lightweight source scan test can assert `parser.py` does not manually construct `Pipeline()` or `AndOrList()`.
2. A parser AST test can assert `control | cmd`, `control && cmd`, and `control &` are all represented through the same `AndOrList`/`Pipeline` structure as simple commands.
3. A regression test can assert `parse_pipeline_with_initial_component` does not exist.

Avoid overfitting the scan. It should only guard the specific deleted smell, not ban legitimate AST construction elsewhere.

## Test Plan

### Focused Parser Tests

Run:

```bash
python -m pytest tests/unit/parser/test_background_lists.py -q
python -m pytest tests/unit/parser/test_parser_migration.py -q
python -m pytest tests/parser_differential/test_combinator_ast_parity.py -q
python -m pytest tests/parser_differential/test_combinator_error_parity.py -q
```

Add and run the new file:

```bash
python -m pytest tests/unit/parser/test_top_level_control_structure_grammar.py -q
```

### Focused Integration Tests

Run:

```bash
python -m pytest tests/integration/control_flow/ -q
python -m pytest tests/integration/pipeline/ -q
python -m pytest tests/integration/job_control/test_background_jobs.py -q
python -m pytest tests/integration/redirection/ -q
```

### Full Validation

Before merge:

```bash
python run_tests.py --quick
ruff check psh tests
mypy
```

For a release-quality parser change:

```bash
python run_tests.py --parallel
```

## Behavioral Risks

### Root AST Shape Drift

Risk: callers or tests may distinguish `TopLevel` from `CommandList`.

Mitigation:

- Decide Option A or B before implementation.
- Add root-shape characterization tests.
- Keep root wrapper policy in `_simplify_result()` rather than scattered through grammar parsing.

### Background Semantics Drift

Risk: `while ...; done &` currently uses special handling in `Parser._parse_top_level_item()`. The normal path uses `StatementParser._apply_background()`.

Mitigation:

- Verify background behavior for simple commands, pipelines, subshells, brace groups, and control structures.
- Confirm `&&`/`||` after `&` remains a syntax error.

### Line Number Drift

Risk: `Parser.parse()` currently stamps top-level control structures because they bypass `parse_statement()`. After the refactor, line stamping may happen in `parse_statement()` instead.

Mitigation:

- Run existing `$LINENO` system tests.
- Add one parser or system test for a top-level multi-line control structure if coverage is missing.

Relevant existing tests:

- `tests/system/test_lineno_script_file.py`

### Error Message Drift

Risk: malformed top-level control structures may now fail through `parse_pipeline_component()` instead of top-level special logic.

Mitigation:

- Run parser differential diagnostic/error parity tests.
- Add focused cases for missing RHS after `control &&`, `control |`, and illegal `control & &&`.

### Combinator Parser Parity Drift

Risk: recursive-descent AST root shape changes can break combinator parity tests.

Mitigation:

- Update parity normalization only if the new root shape is intentional.
- Do not hide nested AST differences in the parity helper.

## Acceptance Criteria

The refactor is complete when:

1. `Parser._parse_top_level_item()` no longer parses control structures directly.
2. `parser.py` no longer manually constructs `Pipeline` or `AndOrList` for top-level control structures.
3. `CommandParser.parse_pipeline_with_initial_component()` is deleted.
4. Control structures followed by `|`, `|&`, `&&`, `||`, and `&` parse and execute correctly.
5. Existing `$LINENO`, redirection, background, and parser parity tests pass.
6. Parser documentation describes one grammar path, with root wrapper simplification documented separately.

## Suggested Patch Sequence

1. Add characterization tests.
2. Add `StatementParser.parse_top_level_statement()`.
3. Change `_parse_top_level_item()` to delegate to the statement parser.
4. Handle root-shape compatibility in one place if needed.
5. Remove `parse_pipeline_with_initial_component()` and dead imports.
6. Update docs.
7. Add guardrail test.
8. Run focused tests, then the local gate.

## Follow-Up Work

This plan intentionally does not solve every AST-root simplification issue. After the grammar-path refactor lands, consider a separate design note for:

- whether `TopLevel` should remain only for function definitions and mixed function/command programs,
- whether single compound commands should simplify to `CommandList`,
- whether `CommandList = StatementList` should become one canonical name,
- whether visitor and formatter code can treat root wrappers through one `Program` abstraction.

