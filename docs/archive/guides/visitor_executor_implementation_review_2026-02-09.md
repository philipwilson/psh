# PSH Visitor & Executor Implementation Review (2026-02-09)

**Reviewer:** Claude Opus 4.6
**Date:** 2026-02-09
**Scope:** `psh/visitor/` (8 modules, ~3,655 lines) and `psh/executor/` (9 modules, ~2,850 lines)
**Version:** 0.145.0 (fixes applied in v0.146.0–v0.148.0; see [Fix Status](#fix-status-v0146v0148) below)

---

## Executive Summary

The visitor and executor subsystems form the back half of psh's
pipeline: the parser produces AST nodes, the visitor pattern dispatches
them, and the executor turns them into running processes.  Together
they are responsible for every observable behaviour of the shell.

The architecture is well-chosen.  The generic `ASTVisitor[T]` base
class with method-cache dispatch is a textbook implementation that is
both performant and extensible.  The executor's delegation to focused
specialists (`CommandExecutor`, `PipelineExecutor`, `ControlFlowExecutor`,
`SubshellExecutor`, `FunctionOperationExecutor`, `ArrayOperationExecutor`)
keeps the top-level `ExecutorVisitor` short and readable.  The unified
`ProcessLauncher` with `ProcessConfig`/`ProcessRole` is a genuine
strength --- it eliminates an entire class of fork-setup bugs by
centralising signal handling, process-group management, and sync-pipe
coordination.

The main weaknesses are concentrated in two areas: (1) the analysis
visitors in `psh/visitor/` duplicate data (builtin lists, dangerous
command dicts) and share structural patterns (traversal, summary
formatting) without sharing code, and (2) several executor files
contain testing infrastructure leaked into production code
(`PYTEST_CURRENT_TEST` guards, `eval_test_mode` branches) that
complicates reading and reasoning about the real execution paths.

**Overall rating: B+.**  Strong architecture, good separation of
concerns, solid process management.  Dragged down by duplicated
visitor data, test-mode leakage, and a few correctness concerns in
context mutation.

### Consolidated Scores

| Dimension | Rating | Notes |
|-----------|--------|-------|
| Correctness | 7.5/10 | Core execution paths well-tested; context mutation in loops is fragile; `_expand_assignment_value` in core.py has a quote-unaware scanner |
| Elegance | 7/10 | Manager+Specialist architecture is clean; analysis visitors are repetitive; test-mode branches reduce clarity |
| Efficiency | 8/10 | Method cache in visitor dispatch; ProcessLauncher sync pipes; reasonable choices throughout |
| Educational value | 7.5/10 | Visitor pattern, Strategy pattern, ProcessLauncher are excellent teaching material; test-mode code confuses students |
| Pythonic style | 7/10 | Good use of dataclasses, context managers, type hints; bare `except:` in a few places, inline imports |

---

## Visitor Subsystem (`psh/visitor/`)

### `base.py` (170 lines) --- A

The best file in both subsystems.  `ASTVisitor[T]` is a clean generic
base with method-cache dispatch that a student can understand in a
single reading.  The `_method_cache` dict avoids repeated `getattr`
calls, which matters when visiting large ASTs.

`ASTTransformer` correctly defaults `generic_visit` to returning the
node unchanged, and `transform_children` uses `dataclasses.fields()`
introspection to find child nodes automatically --- a genuinely elegant
approach that avoids maintaining a parallel list of child-field names.

`CompositeVisitor` is a simple but useful pattern for running multiple
analysis passes.  One minor concern: it doesn't call `super().__init__()`
so there's no `_method_cache`, but since it overrides `visit()` directly
this doesn't matter in practice.

### `formatter_visitor.py` (495 lines) --- A-

The `_format_word()` helper (lines 77--105) is well-designed: it groups
consecutive Word parts by quote context and reconstructs the correct
shell syntax.  This is the kind of detail that makes the formatter
produce correct round-trip output for composite words like
`"$var"'literal'unquoted`.

The visit methods are methodical and produce clean shell output.  The
indentation tracking with `_increase_indent`/`_decrease_indent` is
simple and correct.

### `debug_ast_visitor.py` (391 lines) --- B+

Solid debugging tool.  Displays both `node.args` and Word AST structure
side by side (lines 104--132), which is useful during the Word AST
migration period.  Once the migration is fully complete, the `node.args`
display could be removed to simplify the output.

### `validator_visitor.py` (502 lines) --- B+

Good structural validation: empty commands, mismatched operators, break
outside loops, duplicate function names, infinite C-style for loops.
The context stack for error messages is a nice touch.

One issue: the `generic_visit()` at line 464 is a no-op, which means
unhandled node types are silently ignored rather than traversed.  This
is fine for validation (you can't validate what you don't understand),
but it means adding a new AST node type won't produce validation errors
for obvious structural problems until a visitor method is added.

### `metrics_visitor.py` (585 lines) --- B

Comprehensive complexity analysis including cyclomatic complexity,
nesting depth, command frequency, and per-function metrics.  The
`_count_commands_in_node()` helper uses a visited set to avoid infinite
recursion, which shows defensive thinking.

Two concerns: (1) `import re` appears inside methods at lines 466 and
479 rather than at module level, and (2) the `BASH_BUILTINS` set
(lines 141--150) duplicates lists in `enhanced_validator_visitor.py`
and `linter_visitor.py`.

### `enhanced_validator_visitor.py` (713 lines) --- B

Extended semantic analysis with variable tracking across scopes,
command existence checking, undefined variable detection, and common
typo suggestions.  The `VariableTracker` class (lines 37--112) with
its scope stack is a clean design.

Issues:
- Hardcoded builtin list (lines 162--189) and typo dictionary
  (lines 192--228) duplicate data from other visitors.
- Line 414: zips `node.args` with `node.words` assuming equal length
  --- this is fragile if the two lists ever diverge.
- ~~`_has_parameter_default()` at line 600 used context-wide string
  matching (`any(op in text for op in [':-', ':='])`) which could
  suppress warnings when `:-` or `:=` appeared outside `${...}`
  expansions.~~ **FIXED v0.148.0** — now checks only inside `${...}`
  delimiters with proper brace nesting.

### `security_visitor.py` (344 lines) --- B-

Detects dangerous commands (`rm -rf`, `chmod 777`), sensitive file
writes, `curl | sh` patterns, and unquoted variable expansions.

Issues:
- `_is_piped_to_shell()` at line 287 always returns `False` --- it's
  stubbed out.
- Type annotation `Dict[str, any]` at line 289 should be
  `Dict[str, Any]`.
- The curl/wget pipe detection (line 174) checks command names
  sequentially in the pipeline but doesn't verify an actual pipe
  connection.

### `linter_visitor.py` (422 lines) --- B-

Style checking for unused variables, useless cat, missing error
handling, naming conventions.

Issues:
- `import re` inside methods at lines 258 and 325.
- ~~The `generic_visit()` at line 411 uses `dir(node)` to find child
  attributes, which also finds methods and properties --- it should use
  `dataclasses.fields()` like `ASTTransformer.transform_children()`.~~
  **FIXED v0.148.0** — now uses `dataclasses.fields(node)`.
- Dangerous command dict (lines 110--114) partially duplicates the one
  in `security_visitor.py`.

### Cross-cutting visitor issues

1. **Duplicated data.**  Three visitors independently define lists of
   shell builtins.  Two define dangerous command dictionaries.  These
   should be shared constants, either in a common module or in
   `ast_nodes.py`.

2. **Inline `import re`.**  Four instances across `linter_visitor.py`
   and `metrics_visitor.py`.  Move to module level.

3. **Inconsistent traversal.**  Some visitors use `generic_visit()` for
   traversal (linter, metrics), others require explicit child visiting
   in every method (formatter, debug).  A mixin or base class that
   provides automatic recursive traversal would reduce boilerplate.

---

## Executor Subsystem (`psh/executor/`)

### `core.py` --- ExecutorVisitor (542 lines) --- B+

The top-level dispatcher is clean and readable.  Each `visit_*` method
is a 2--3 line delegation to the appropriate specialist executor.  The
`_apply_redirections` context manager is a good pattern that prevents
FD leak on exceptions.

Issues:

1. **`_expand_assignment_value()` (lines 297--367) is a quote-unaware
   character scanner** that duplicates logic from
   `expand_string_variables()` in the expansion subsystem.  It manually
   finds `$(...)`, backticks, and `$((...))` by counting parentheses
   without tracking quotes.  This is the same class of bug fixed in
   v0.145.0 for the expansion subsystem but remains here.  However,
   this method may now be dead code --- `CommandExecutor` uses
   `_expand_assignment_value_from_word()` instead, which takes the Word
   AST path.  If so, it should be deleted.

2. **`_handle_exec_builtin()` (lines 416--454) duplicates exec logic**
   that also exists in `CommandExecutor._handle_exec_builtin()` (lines
   567--603).  The core.py version manually resets signals at lines
   482--485 rather than using `apply_child_signal_policy()`.

3. **`_find_command_in_path()` (lines 509--526) duplicates PATH
   searching** logic that also exists in the `command` builtin.

4. **Unused helper methods** `_extract_assignments()`,
   `_is_valid_assignment()`, `_is_exported()` at lines 278--288 are
   thin wrappers around `assignment_utils` functions that are also
   defined in `CommandExecutor`.

### `command.py` --- CommandExecutor (604 lines) --- B+

Well-structured command execution with a clear 4-phase flow: extract
assignments, expand arguments, find strategy, execute.  The
`_is_assignment_candidate()` static method (lines 240--289) is a
thorough implementation that correctly handles quoted variable names
and process substitution tokens.

Issues:

1. **Bare `except:` at line 316** in `_handle_pure_assignments`.
   Should be `except ReadonlyVariableError:`.

2. **Bare `except:` at line 345** in `_apply_command_assignments`.
   Same issue.

3. **`_handle_array_assignment()` (lines 552--565) creates a new
   `ArrayOperationExecutor` instance** on every call, even though one
   already exists on `ExecutorVisitor`.  The method should delegate
   to the shared instance.

4. **Test infrastructure in `_execute_builtin_with_redirections()`**
   (lines 531--537): the `isinstance(self.shell.stdout, io.StringIO)`
   check is a testing concern leaked into production code.

### `strategies.py` --- Execution Strategies (421 lines) --- B

Clean Strategy pattern implementation with correct POSIX priority
ordering.  The alias expansion with recursion guard
(`expanding` set, lines 240--275) is well-handled.

Issues:

1. **`FunctionExecutionStrategy.execute()` creates a new
   `ExecutorVisitor` instance** (lines 209--212) and overwrites its
   `context` field.  This means function calls inside pipelines or
   loops lose the pipeline context of the outer visitor.  The comment
   at lines 206--208 acknowledges this as a known limitation.

2. **`ExternalExecutionStrategy.execute()` has a bare `except:`** at
   line 335.

3. **`PYTEST_CURRENT_TEST` guard** at line 331 leaks testing concerns
   into production code.

### `context.py` --- ExecutionContext (190 lines) --- A-

Clean dataclass with well-named context-creation methods
(`fork_context`, `subshell_context`, `pipeline_context_enter`,
`loop_context_enter`, `function_context_enter`).  Each method creates
a new context with appropriate state rather than mutating the original.

One concern: the `*_context_enter` methods return new objects, but
`control_flow.py` mutates `context.loop_depth` and
`context.in_pipeline` directly (e.g., lines 124, 130, 153 in
`control_flow.py`).  This breaks the immutable-context pattern and
could cause bugs if the same context object is shared across
concurrent execution paths.  The context should either be fully
immutable (all mutations via `*_enter` methods) or the direct mutations
should be documented as intentional.

**Note (v0.146.0):** The `loop_depth` mutation is now safe because it
is wrapped in `try/finally`, but direct mutation is still used rather
than the `*_enter` pattern.

### `control_flow.py` --- ControlFlowExecutor (692 lines) --- B

Comprehensive control structure execution: if/elif/else, while, until,
for, C-style for, case (with `;&` and `;;&` fall-through), select with
interactive menu, break/continue with nesting levels.

Issues:

1. **Direct context mutation** (lines 124, 130, 153, etc.).
   `context.loop_depth += 1` and `context.in_pipeline = False` mutate
   the shared context object instead of creating new contexts via the
   `ExecutionContext` methods.  This works because execution is
   single-threaded, but it's fragile and inconsistent with the
   immutable-context design in `context.py`.
   **Partially addressed v0.146.0:** `loop_depth` increment/decrement
   is now wrapped in outer `try/finally` so multi-level `break`/`continue`
   can no longer skip the decrement.  Direct mutation pattern is retained.

2. **`_expand_for_loop_items()` and `_expand_select_items()`** (lines
   504--540) are near-identical.  They should be a single method.

3. **`_word_split_and_glob()`** (lines 591--613) reimplements word
   splitting with `re.split()` instead of using the existing
   `WordSplitter` class.  This risks inconsistent IFS handling.

4. **Case pattern matching** (lines 615--667): the
   `_convert_case_pattern_for_fnmatch()` method has a heuristic at
   line 660 that guesses whether `[*]` was originally `\[*\]`.  This
   is fragile and could misinterpret intentional character classes.

### `pipeline.py` --- PipelineExecutor (500 lines) --- B-

The forking pipeline execution is functionally correct with proper
sync-pipe coordination and process-group management.  The
`PipelineContext` class cleanly encapsulates pipe state.

Issues:

1. **Test-mode code** (lines 107--111, 312--468) accounts for ~160
   lines of alternative execution paths (`eval_test_mode`,
   `_execute_simple_pipeline_in_test_mode`,
   `_execute_builtin_to_builtin_pipeline`,
   `_execute_mixed_pipeline_in_test_mode`).  These use StringIO
   buffers and `subprocess.Popen` as alternatives to fork/exec.  While
   necessary for test output capture, this code: (a) doubles the
   maintenance surface for pipelines, ~~(b) has a fallback at line 462
   that creates anonymous types with `type()` calls, which is fragile
   and hard to read,~~ and (c) confuses students trying to understand
   how pipelines actually work.  This should be isolated into a
   separate test helper module.
   **Partially addressed v0.147.0:** The `type()` fallback (item b)
   now uses a real `Pipeline` AST node and the caller's `context`.

2. **`PYTEST_CURRENT_TEST` guard** at line 143.

3. **Closure capture in pipeline fork** (lines 170--194): the
   `make_execute_fn` factory correctly captures `cmd_index` and
   `cmd_node` by parameter, avoiding the classic loop-variable closure
   bug.  This is well-done.

### `process_launcher.py` --- ProcessLauncher (344 lines) --- A-

The strongest file in the executor subsystem.  `ProcessConfig` and
`ProcessRole` provide a clean, typed interface for process creation.
The `launch()` method handles fork, process-group setup (both child
and parent side), and sync-pipe coordination in a well-structured flow.

Issues:

1. **Bare `except:` at line 246** in the child-process `finally` block
   for flushing stdout/stderr.  Should be `except OSError:`.

2. **Bare `except:` at line 311** in `launch_job()`.  Should be
   `except OSError:`.

3. **`launch_job()` (lines 287--343) creates a `SimpleCommand` with
   `command_str.split()`** at line 320, which is a simplified parser
   that doesn't handle quoting.  This is only used for redirect setup,
   so it's unlikely to cause problems in practice, but it's
   architecturally questionable.

### `child_policy.py` --- apply_child_signal_policy (46 lines) --- A

Excellent.  A single function that is the authoritative source for
child signal setup.  The docstring clearly explains the 4 steps and
the `is_shell_process` distinction.  Every fork path in the codebase
calls this function, which eliminates an entire category of signal-
handling inconsistencies.

### `function.py` --- FunctionOperationExecutor (138 lines) --- B+

Clean function execution with proper scope management: push scope,
set positional params, execute body, restore state in `finally` block.

One concern: the `finally` block at lines 116--137 manually restores
special variables `#`, `@`, `*` from `old_positional_params`.  If
`old_positional_params` was empty (the shell started with no args),
the `#` is set to `'0'` and `@` to `[]`, which is correct.  But the
index arithmetic at line 131 (`old_positional_params[1:]`) suggests
the first element is `$0`, which is inconsistent with how
`state.positional_params` is used elsewhere (where `[0]` is `$1`).

---

## Correctness Concerns

| # | Issue | Severity | Location | Status |
|---|-------|----------|----------|--------|
| 1 | Context mutation: `context.loop_depth += 1` and `context.in_pipeline = False` mutate shared context instead of using immutable `*_enter` methods | Medium | `control_flow.py:124,130,153` | **Partially fixed v0.146.0** — loop_depth now in `try/finally`; direct mutation pattern retained but safe |
| 2 | `_expand_assignment_value()` in core.py has quote-unaware scanner (may be dead code) | Low | `core.py:297-367` | Open |
| 3 | `_word_split_and_glob()` reimplements IFS splitting instead of using `WordSplitter` | Medium | `control_flow.py:591-613` | Open |
| 4 | `FunctionExecutionStrategy` creates new `ExecutorVisitor`, losing pipeline context | Medium | `strategies.py:209-212` | Open |
| 5 | Bare `except:` in multiple files | Low | `command.py:316,345`, `strategies.py:335`, `process_launcher.py:246,311` | Open |
| 6 | Duplicate exec handling between `core.py` and `command.py` | Low | `core.py:416-526`, `command.py:567-603` | Open |

---

## Structural Recommendations

### High Priority

1. **Consolidate shared visitor data into a common module.**  Create
   `psh/visitor/constants.py` (or similar) containing:
   - `SHELL_BUILTINS: frozenset` (used by enhanced_validator, linter,
     metrics)
   - `DANGEROUS_COMMANDS: dict` (used by enhanced_validator, security,
     linter)
   - `SPECIAL_VARIABLES: set` (used by enhanced_validator)
   - `COMMON_TYPOS: dict` (used by enhanced_validator)

   This eliminates 3 copies of the builtin list and 2 copies of the
   dangerous commands dict.

2. **Make ExecutionContext mutations consistent.**  Either:
   (a) Make all mutations go through the `*_enter` methods (preferred:
   creates a new context for each scope, avoids aliasing bugs), or
   (b) Document that direct mutation is the intended pattern and remove
   the unused `*_enter` methods.

   Currently the code mixes both approaches, which is confusing.

3. **Use `WordSplitter` in `_word_split_and_glob()`** instead of
   reimplementing IFS splitting with `re.split()`.  The existing
   `WordSplitter` class handles edge cases (backslash escapes, empty
   IFS, whitespace collapsing) that the regex approach misses.

### Medium Priority

4. **Isolate test-mode pipeline execution.**  Move
   `_execute_simple_pipeline_in_test_mode`,
   `_execute_builtin_to_builtin_pipeline`, and
   `_execute_mixed_pipeline_in_test_mode` into a separate
   `test_pipeline_helper.py` module (or behind a clear
   `if self.state.eval_test_mode:` guard at the top of
   `_execute_pipeline`).  This keeps the production code path clean
   and readable.

5. **Delete likely-dead code in `core.py`.**  The following methods
   appear to be superseded by `CommandExecutor` equivalents:
   - `_expand_assignment_value()` (superseded by
     `_expand_assignment_value_from_word()`)
   - `_extract_assignments()`, `_is_valid_assignment()`,
     `_is_exported()` (duplicated in `CommandExecutor`)
   - `_handle_exec_builtin()`, `_exec_with_command()`,
     `_exec_without_command()`, `_find_command_in_path()` (superseded
     by `CommandExecutor._handle_exec_builtin()`)

   Verify these are unreachable, then delete.

6. **Deduplicate `_expand_for_loop_items` / `_expand_select_items`.**
   These two methods in `control_flow.py` differ only in the node type.
   Extract a shared `_expand_loop_items(items, quote_types)` method.

7. **Move inline `import re` to module level** in `linter_visitor.py`
   and `metrics_visitor.py` (4 instances total).

### Low Priority

8. **Replace bare `except:` with specific types** in `command.py`
   (lines 316, 345), `strategies.py` (line 335), and
   `process_launcher.py` (lines 246, 311).

9. **Fix `security_visitor.py` type annotation** at line 289:
   `Dict[str, any]` -> `Dict[str, Any]`.

10. **Implement or remove `_is_piped_to_shell()`** in
    `security_visitor.py` (line 287).  Currently always returns
    `False`.

11. ~~**Use `dataclasses.fields()` in linter's `generic_visit()`**
    instead of `dir(node)`, matching the pattern in
    `ASTTransformer.transform_children()`.~~ **FIXED v0.148.0**

12. **Deduplicate `_apply_redirections` context manager.**  This
    identical pattern appears in `core.py`, `command.py`, and
    `control_flow.py`.  Extract to a shared mixin or utility.

---

## Positive Notes

- **ProcessLauncher + ProcessConfig + ProcessRole** is excellent
  systems-level design.  Centralising all fork/exec/signal logic into
  one module with a typed configuration object is the kind of
  discipline that prevents the "works on my machine" bugs that plague
  shell implementations.

- **`child_policy.py`** demonstrates how a single 46-line function can
  eliminate an entire category of bugs.  Before this existed, each of 5
  fork paths had its own signal setup logic.

- **`ExecutionContext` as a dataclass** with named factory methods
  (`fork_context`, `subshell_context`, etc.) is a clean alternative to
  scattered boolean flags.  The `should_use_print()` method documents a
  subtle distinction (FD writes vs print in forked children) that would
  otherwise be tribal knowledge.

- **The Strategy pattern** for command execution gives a clear,
  extensible priority chain.  Adding a new command type (e.g., a
  plugin system) would require only a new strategy class and an
  insertion into the list.

- **`ASTVisitor[T]` with method cache** is both correct and
  performant.  The generic type parameter ensures that visitor methods
  return consistent types, and the cache avoids O(n) `getattr` calls
  on every visit.

- **The `_format_word()` helper** in `formatter_visitor.py` is a
  model of how to reconstruct quoting context from Word AST parts.
  It correctly groups consecutive parts by quote type, which is
  necessary for producing valid shell syntax from decomposed Word
  nodes.

---

## Quantitative Summary

### Visitor Subsystem

| File | Lines | Rating | Key Strength | Key Weakness |
|------|-------|--------|-------------|--------------|
| `base.py` | 170 | A | Generic visitor with method cache | --- |
| `formatter_visitor.py` | 495 | A- | `_format_word()` quote reconstruction | --- |
| `debug_ast_visitor.py` | 391 | B+ | Dual args/Word display | Will need cleanup post-migration |
| `validator_visitor.py` | 502 | B+ | Context stack for errors | No-op `generic_visit` |
| `metrics_visitor.py` | 585 | B | Comprehensive complexity metrics | Inline imports, duplicated builtins |
| `enhanced_validator_visitor.py` | 713 | B | Scope-aware variable tracking | Hardcoded data, fragile args/words zip (`_has_parameter_default` fixed v0.148.0) |
| `security_visitor.py` | 344 | B- | Detects real vulnerability patterns | Stubbed method, type annotation error |
| `linter_visitor.py` | 422 | B- | Useful style checks | ~~`dir(node)` traversal~~ (fixed v0.148.0), inline imports |

### Executor Subsystem

| File | Lines | Rating | Key Strength | Key Weakness |
|------|-------|--------|-------------|--------------|
| `child_policy.py` | 46 | A | Single source of truth for signals | --- |
| `context.py` | 190 | A- | Clean immutable-context factory methods | Mutations elsewhere break the pattern |
| `process_launcher.py` | 344 | A- | Unified process creation | Bare `except:`, simplified command parser |
| `core.py` | 542 | B+ | Clean delegation to specialists | Likely-dead code, duplicate exec handling |
| `command.py` | 604 | B+ | Thorough assignment candidate detection | Bare `except:`, test infrastructure leak |
| `function.py` | 138 | B+ | Proper scope save/restore | Positional param indexing inconsistency |
| `control_flow.py` | 692 | B | Complete control structure coverage | Context mutation (loop_depth fixed v0.146.0), duplicated expand methods |
| `strategies.py` | 421 | B | Clean Strategy pattern | New visitor on function call, pytest guard |
| `pipeline.py` | 500 | B- | Correct sync-pipe coordination | ~160 lines of test-mode code (fallback fixed v0.147.0) |

---

## Fix Status (v0.146.0–v0.148.0)

The following items from the Correctness Concerns, Structural Recommendations,
and the companion codex review have been addressed or triaged:

### Fixed

| Ref | Item | Version | Resolution |
|-----|------|---------|------------|
| CC-1 | `context.loop_depth` mutation not in `finally` | v0.146.0 | Wrapped in outer `try/finally` (while, until, for) |
| SR-11 | Linter `generic_visit()` uses `dir(node)` | v0.148.0 | Replaced with `dataclasses.fields(node)` |
| Codex #1 | Background brace-group double execution | v0.146.0 | Check `node.background` before any execution |
| Codex #3 | Special-builtin prefix assignment persistence | v0.146.0 | `_execute_with_strategy()` returns `(exit_code, is_special)` |
| Codex #4 | Linter generic traversal duplicates | v0.148.0 | `dir(node)` → `dataclasses.fields(node)` |
| Codex #6 | Formatter C-style for `$` injection | v0.148.0 | Removed spurious `$` from f-string |
| Codex #7 | Enhanced validator `_has_parameter_default` under-reporting | v0.148.0 | Now checks inside `${...}` delimiters only |
| Codex #8 | Pipeline test-mode fallback invalid context | v0.147.0 | Real `Pipeline` node + real `context` |

### Verified not-a-bug

| Ref | Item | Version | Analysis |
|-----|------|---------|----------|
| Codex #5 | Formatter array subscript semantics | v0.148.0 | `${arr[0]}` round-trips correctly via `ParameterExpansion.__str__()`; unbraced `$arr[0]` correctly emits as-is |

### Open (from this review)

| Ref | Item | Severity |
|-----|------|----------|
| CC-2 | `_expand_assignment_value()` quote-unaware scanner (likely dead code) | Low |
| CC-3 | `_word_split_and_glob()` reimplements IFS splitting | Medium |
| CC-4 | `FunctionExecutionStrategy` creates new `ExecutorVisitor` | Medium |
| CC-5 | Bare `except:` in multiple files | Low |
| CC-6 | Duplicate exec handling between `core.py` and `command.py` | Low |
| SR-1 | Consolidate shared visitor data into common module | High |
| SR-2 | Make ExecutionContext mutations consistent | High |
| SR-3 | Use `WordSplitter` in `_word_split_and_glob()` | High |
| SR-4 | Isolate test-mode pipeline execution | Medium |
| SR-5 | Delete likely-dead code in `core.py` | Medium |
| SR-6 | Deduplicate `_expand_for_loop_items` / `_expand_select_items` | Medium |
| SR-7 | Move inline `import re` to module level | Medium |
| SR-8 | Replace bare `except:` with specific types | Low |
| SR-9 | Fix `security_visitor.py` type annotation | Low |
| SR-10 | Implement or remove `_is_piped_to_shell()` | Low |
| SR-12 | Deduplicate `_apply_redirections` context manager | Low |

Regression tests: `tests/regression/test_visitor_executor_review_fixes.py` (17 tests)
