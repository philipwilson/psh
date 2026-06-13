# PSH Code Quality Assessment

Date: 2026-06-13

This assessment is based on the current code in `psh/` and the current test and tooling configuration. I did not rely on existing review documents; older architecture notes were intentionally treated as non-authoritative.

## Executive Summary

PSH is not textbook-quality code in the narrow sense: it is not small, formally clean, or easy to audit from first principles. That is partly because shell semantics are intrinsically hostile to clean textbook structure, but there are also local design debts: duplicated parser implementations, state spread across layers, large semantic state machines, runtime debug prints, and some exception masking.

It is, however, substantially above typical educational interpreter code. The project has clear subsystem boundaries, unusually explicit comments about POSIX/bash behavior, a large test suite, and several mature design moves: structural `Word` ASTs, expansion policies, scoped process-substitution cleanup, centralized shell construction phases, visitor-based execution, and transactional builtin redirection frames.

The right verdict is: production-minded and semantics-aware, but not textbook. It is good code with accumulated complexity.

## Evidence Gathered

- Static project size: 206 Python files, about 50,559 lines in `psh/`, 2,175 functions, 342 classes.
- Largest runtime modules include `psh/expansion/arithmetic.py` (1,155 lines), `psh/expansion/brace_expansion.py` (844), `psh/expansion/word_expander.py` (823), `psh/lexer/modular_lexer.py` (661), and `psh/lexer/recognizers/word_scanners.py` (623).
- Longest functions include `find_command_substitution_end` at 341 lines, arithmetic `tokenize` at 213 lines, pipeline execution at 158 lines, command execution at 121 lines, array assignment parsing at 120 lines, and literal collection at 140 lines.
- `ruff check .` currently fails with 189 fixable issues, mostly in archived docs/examples, plus `conftest.py`. This is a tooling-scope problem: either archive files should be excluded, or the repository should be made lint-clean under the configured command.
- `python run_tests.py --quick` completed after about 3.5 minutes. Combined result: 5,811 passed, 2 failed, 218 skipped, 19 xfailed, 1 deselected. Phase 1 failed; Phase 2 subshell tests passed. The current failures were `tests/integration/redirection/test_process_sub_cleanup.py::TestProcessSubOutputCorrectness::test_write_side_substitution_tee` (`tee: /dev/fd/4: Operation not permitted`) and `tests/unit/io_redirect/test_fd_operations.py::TestDynamicDupTarget::test_dup_stdout_to_arithmetic_fd` (expected `hi`, got empty output).

## Subsystem Assessment

| Subsystem | Quality | Textbook? | Assessment |
| --- | --- | --- | --- |
| Lexer | High | No | Modular and well tested, but command-position and word-shape semantics are complex and spread across recognizers, quote/expansion parsers, keyword normalization, and command-substitution scanners. |
| Parser | Mixed-high | No | The production recursive-descent parser is understandable and decomposed. The experimental combinator parser lowers the subsystem's overall quality story because it is selectable but explicitly outside the production bar. |
| AST model | Medium-high | No | `Word` and `WordPart` are the right direction. Some AST nodes still behave like compatibility containers, and string views remain important in downstream logic. |
| Expansion | High but risky | No | Strong policy abstraction and real bash/POSIX detail. `WordExpander` and arithmetic expansion carry too much semantic density in large state machines. |
| Executor | Medium-high | No | Good visitor/strategy split and serious process management. Weaknesses are duplicated execution state, broad exception conversion, and complex process/job-control paths. |
| I/O redirection | High | Close, but no | The builtin redirection frame model is excellent and well documented. It is still inherently process-global and needs strict tests around nesting and failures. |
| Core state | Medium | No | Central shell state is necessary, but some responsibilities overlap with executor context and variable expansion. |
| Builtins | Medium | No | Broad feature coverage, but quality likely varies by builtin. Some builtins are large and option parsing is often hand-rolled. |
| Interactive | Medium | No | Functionally separated into focused modules, but line editing/history/terminal behavior is hard to prove and less central to the parser/executor quality bar. |
| Visitor/tools | Medium | No | Useful analysis and formatting visitors, but not uniformly integrated into the production correctness story. |

## Lexer

The lexer is one of the stronger parts of the codebase. `psh/lexer/modular_lexer.py` delegates to recognizers and specialized parsers instead of being one unstructured scanner. `psh/lexer/recognizers/word_scanners.py` is especially notable: it replaces retroactive heuristics with pure mini-scanners and a forward `WordShapeTracker`, and its comments make invariants explicit.

The main weakness is that shell lexical context is still distributed. Command-position knowledge appears in lexer state, keyword normalization, parser expectations, and raw command-substitution scanning. That is practical, but not textbook. A textbook lexer would expose a smaller, canonical stream of token/word events with fewer downstream reinterpretations.

Specific issues:

- Parameter expansion classification in `psh/lexer/modular_lexer.py` still depends on scanning expansion text for operator-like substrings. That is fragile; the expansion parser should return structured metadata instead.
- Command-position rules in `psh/lexer/command_position.py` are centralized as vocabulary, but the behavior still depends on several consumers staying aligned.
- `psh/lexer/cmdsub_scanner.py` has a very long `find_command_substitution_end` function. This is a correctness hotspot and should be decomposed into smaller scanners or parser states.
- Debug and compatibility comments are useful, but some comments describe inherited quirks. That is a sign the implementation is preserving behavior rather than expressing a clean model.

Recommended improvements:

1. Make expansion parsing return structured token classification so lexer-side substring guesses disappear.
2. Add a shared command-position conformance matrix that compares lexer state, keyword normalization, parser behavior, and command-substitution scanning on the same snippets.
3. Decompose command-substitution scanning into explicit state transitions with unit tests per state.
4. Keep `WordShapeTracker`; it is a strong piece of engineering.

## Parser

The production recursive-descent parser is generally good. `psh/parser/recursive_descent/parser.py` acts as an orchestrator, and grammar areas are split into commands, statements, arrays, functions, redirections, tests, arithmetic, and control structures. `ParserContext` centralizes state, which is preferable to passing many mutable pieces around.

The parser is not textbook-quality because it must compensate for token-shape ambiguity and historical behavior. Array parsing and declaration-style initializers are especially string-inspection heavy. In `psh/parser/recursive_descent/parsers/commands.py` and `psh/parser/recursive_descent/parsers/arrays.py`, some flows serialize or inspect token strings rather than consuming a fully normalized grammar-level representation.

The combinator parser is a separate concern. `psh/parser/combinators/parser.py` explicitly says it is experimental and outside the production quality bar. That is fine as an educational artifact, but it should not be presented as an equivalent parser path unless conformance expectations are clear.

Recommended improvements:

1. Normalize array assignment and declaration initializer forms earlier, so parser code consumes canonical shapes instead of many tokenization variants.
2. Move declaration array initializer handling toward structured `Word`/array AST consumption instead of string reconstruction.
3. Either remove the combinator parser from normal user-selectable flows or gate it clearly as experimental in CLI/help/user-facing output.
4. Expand parser tests around canonical AST shape, not just successful execution, for arrays, functions, redirections, and nested compound commands.

## AST Model

The AST is moving in the right direction. `Word`, `LiteralPart`, and `ExpansionPart` in `psh/ast_nodes.py` give expansion code structural information that raw shell strings cannot provide. `SimpleCommand.words` being the source of truth, with `args` derived, is the correct direction.

The weakness is that the AST is not yet a fully authoritative semantic model. Some downstream code still relies on string rendering, `__str__`, or compatibility-shaped values. The AST classes also mix syntax representation, runtime convenience, and historical string views.

Recommended improvements:

1. Treat `Word` and `WordPart` as the only representation for shell words across parser, expansion, and builtins.
2. Reduce reliance on `__str__` for behavior; reserve it for debug/source rendering.
3. Add explicit AST invariants and validation tests for tricky constructs.

## Expansion

Expansion is high quality but high risk. `psh/expansion/manager.py` has a clean orchestration role, and `WordExpansionPolicy` in `psh/expansion/word_expander.py` is one of the best abstractions in the project. It makes split/glob/assignment-tilde behavior explicit and gives context names to bash-specific semantics.

The main problem is density. `WordExpander` handles quote removal, tilde triggers, expansion evaluation, field production, `$@` behavior, splittability, glob eligibility, and escape processing in one large class with a mutable `_WalkState`. This is carefully written, but not simple to audit.

Arithmetic expansion is another hotspot. `psh/expansion/arithmetic.py` is large and implements its own tokenizer/parser/evaluator. That may be necessary, but it deserves stricter internal structure and more local proof points because arithmetic semantics are surprisingly broad.

Recommended improvements:

1. Split `WordExpander` around an explicit intermediate representation, for example `ExpandedSegment(text, quoted, splittable, glob_eligible)`.
2. Run expansion, splitting, globbing, and quote removal as visibly separate passes over that representation.
3. Keep `WordExpansionPolicy`, but make policy effects testable at pass boundaries.
4. Break arithmetic tokenization/parsing/evaluation into smaller modules or classes with focused tests.
5. Centralize special variable lookup so `VariableExpander` and `ShellState` do not duplicate behavior.

## Executor And Process Management

The executor is better structured than a monolithic shell loop. `psh/executor/core.py` uses a visitor; `psh/executor/command.py`, `pipeline.py`, `control_flow.py`, `function.py`, `subshell.py`, and `array.py` separate major responsibilities. `psh/executor/strategies.py` gives command resolution an explicit strategy order. `psh/executor/process_launcher.py` centralizes child setup, which is the right direction.

The weaknesses are mostly around state and failure visibility.

- `ExecutionContext` and `ShellState` both carry execution-context-like flags. For example, forked-child state appears in more than one place. One object should be authoritative.
- Several paths convert unexpected exceptions into shell status `1`, sometimes only showing tracebacks under debug flags. This is defensible for an interactive shell but weak for tests and internal quality.
- `CommandExecutor._execute_command` is long and handles many phases: traps, array assignment, prefix assignment extraction, expansion, command lookup, assignment application, xtrace, exec, strategy dispatch, and restoration.
- Pipeline and process-launching logic is careful but difficult to reason about because it spans process groups, sync pipes, terminal ownership, signal restoration, visitor context mutation, and job tracking.

Recommended improvements:

1. Add a strict internal-error mode for tests where unexpected implementation exceptions are re-raised instead of converted to exit status `1`.
2. Make either `ShellState` or `ExecutionContext` the single authority for forked-child and execution-context flags.
3. Split command execution into explicit phase objects or smaller functions with named inputs/outputs: extract assignments, expand command words, apply prefix environment, resolve command, execute, restore.
4. Add failure-path tests for process launcher and pipeline cleanup: fork failure, redirect failure, signal interruption, stopped jobs, and process-substitution cleanup.

## I/O Redirection

`psh/io_redirect/manager.py` is one of the most mature modules. The distinction between fd-level redirection and Python stream-level redirection for builtins is exactly the kind of detail that many shell implementations get wrong. The `BuiltinRedirectFrame` design is strong: setup is transactional, nested redirections have per-invocation frames, and restoration is LIFO.

This subsystem is close to production quality. It is still not textbook because it handles inherently global process state and Python stream objects, but the design is coherent.

Recommended improvements:

1. Add more adversarial tests around nested `eval`, `source`, traps, and failing redirects during nested builtin execution.
2. Remove or centralize runtime debug `print` calls under a logging/debug helper.
3. Keep the current frame model; it is the right abstraction.

## Core State

`psh/core/state.py` is necessarily central and large. `psh/shell.py` does a good job documenting shell construction phases and keeping orchestration out of CLI/execution logic. That phase-based initialization is a strong pattern.

The concern is responsibility overlap. Shell state, scope management, variable expansion, execution context, function context, and special variables interact tightly. The current design works, but the ownership boundaries are not always obvious.

Recommended improvements:

1. Document and enforce ownership of variables, special parameters, shell options, execution flags, and environment synchronization.
2. Move special-parameter behavior to one authoritative API.
3. Make prefix assignment save/restore operate on full variable objects, not only string/env snapshots, so attributes and readonly/export state are preserved predictably.

## Builtins

The builtin subsystem has broad coverage and a registry pattern, but quality likely varies by command. Some modules are large (`environment.py`, `function_support.py`, `read_builtin.py`, `directory_stack.py`), and many builtins must hand-roll shell-specific option parsing and diagnostics.

Recommended improvements:

1. Introduce shared option-parsing helpers where bash/POSIX parsing rules repeat.
2. Standardize error reporting through builtin base helpers instead of direct `print(..., file=...)`.
3. Add per-builtin conformance tables for option parsing and edge diagnostics.

## Interactive

The interactive subsystem is split into reasonable modules: line editor, renderer, history, prompts, terminal, signals, keybindings, tab completion, and multiline handling. That is a good shape.

This code is less textbook because terminal behavior is hard to isolate, and long interactive modules naturally accumulate state. The system tests under `tests/system/interactive` help, but interactive correctness usually needs more PTY-level coverage than normal unit tests.

Recommended improvements:

1. Keep terminal rendering, key decoding, editing buffer, and history navigation isolated and unit-tested separately.
2. Prefer pure functions for layout decisions.
3. Expand PTY tests only for high-value regressions; they are expensive and brittle.

## Tooling And Tests

The test footprint is large and serious. There are unit, integration, system, regression, conformance, and performance directories. That is a major quality strength.

The tooling story needs tightening:

- The configured `ruff check .` fails today, mostly due to archived docs/examples. If `ruff check .` is a recommended command, it should pass.
- The quick test runner is not green on this machine: two current failures are in process substitution / fd duplication redirection behavior. That does not invalidate the broader quality assessment, but it does make I/O redirection cleanup and fd behavior a current priority.
- `pyproject.toml` has minimal mypy adoption over a limited file set, with `allow_untyped_defs = true` and `check_untyped_defs = false`. That is an understandable migration posture, but it means type checking is not yet a strong correctness tool.
- The project has many comments describing bash probes. These comments are valuable, but the most important ones should be backed by conformance tests.

Recommended improvements:

1. Make `ruff check .` pass by excluding archive/example code or cleaning it.
2. Add a stricter lint command for production code only, for example `ruff check psh tests`.
3. Gradually expand mypy coverage to lexer/parser/expansion/executor with stricter settings for new or cleaned modules.
4. Turn probe-backed comments into small conformance tests where the behavior is important.

## Highest-Value Improvement Plan

1. Make tooling honest: fix or scope `ruff check .`, and add a production-only lint target.
2. Add strict internal-error mode for tests so implementation bugs do not become shell status `1`.
3. Refactor `WordExpander` around an intermediate segment/field model.
4. Normalize parser input for array/declaration assignment shapes and remove string reconstruction paths.
5. Centralize special variables and execution context ownership.
6. Gate or remove the experimental combinator parser from normal user-facing parser selection.
7. Decompose the largest semantic hotspots: command-substitution scanning, arithmetic expansion, command execution, and pipeline execution.

## Final Verdict

PSH is not textbook-quality code. It is too large, too stateful, and too compatibility-driven for that label. But it is not low-quality code. Several subsystems show careful engineering and unusually good semantic awareness, especially expansion policy, word modeling, builtin redirection handling, shell initialization, and process-substitution ownership.

The main path to higher quality is not a rewrite. It is to make the hidden state explicit, collapse duplicate sources of truth, split the densest semantic machines into auditable passes, and make tooling/test commands reflect the quality bar the project wants contributors to meet.
