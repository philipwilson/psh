# PSH Subsystem Code Quality Assessment

Date: 2026-06-11

Scope: current code under `psh/`, with spot checks against tests under `tests/`. This assessment intentionally does not rely on prior review documents, because the user noted they are out of date.

## Executive Summary

PSH is a serious, above-average teaching shell implementation. It has broad subsystem decomposition, a large regression/conformance test suite, and many areas of careful engineering, especially around AST representation, parser decomposition, redirection transactionality, shell option behavior, and historical bug coverage.

It is not yet "textbook quality" code in the sense of a clean, minimal, grammar-driven shell architecture where each semantic rule has one authoritative implementation. The main weakness is semantic duplication: shell grammar and expansion rules are spread across the lexer, keyword normalizer, parser, word builder, expansion manager, array executor, command executor, and process-substitution paths. That makes the code harder to reason about than it should be and has produced real behavior gaps.

The highest-value improvements are:

1. Make shell word/expansion handling structural end to end, especially for arrays, assignments, process substitution, and parameter expansion.
2. Centralize reserved-word and grammar context handling rather than duplicating partial parsers in the lexer and keyword normalizer.
3. Replace heuristic string scans with small, explicit parsers for command substitution and parameter expansion.
4. Split `CommandExecutor` and `ExpansionManager` into narrower semantic phases with shared expansion policies.
5. Remove or quarantine experimental/compatibility surfaces that weaken invariants, especially the parser-combinator implementation.

## Overall Rating

Approximate grade: **B / B+ for a working teaching shell, C+ / B- as "textbook quality" architecture**.

The project shows significant engineering maturity, but the codebase still contains large semantic hubs and compatibility shims. It is closer to an organically evolved production prototype than a textbook reference implementation.

## Subsystem Assessment

| Subsystem | Quality | Textbook? | Notes |
| --- | --- | --- | --- |
| Lexer | Good but over-contextual | No | Modular recognizers are good; too much parser state lives in lexing. |
| Parser | Good decomposition, mixed invariants | No | Recursive descent parser is maintainable; combinator parser creates duplicate surface without strong parity. |
| AST / Word Model | Promising | Partly | `Word`, `LiteralPart`, and `ExpansionPart` are the right direction, but not used uniformly. |
| Expansion | Feature-rich but too centralized | No | Correct expansion order is attempted, but normal words, assignments, arrays, and process substitution diverge. |
| Executor | Capable but hub-like | No | Visitor split helps, but `CommandExecutor` still owns too many semantics. |
| I/O Redirection | Strong | Mostly | The stream-vs-fd model is thoughtful; nested mutable manager state needs cleanup. |
| Interactive | Functional but large | No | Line editor and signal lifecycle need stronger separation and cleanup. |
| Builtins | Broad and practical | Mixed | Registry is simple; individual builtins vary and some are large. |
| Core State | Useful but leaky | No | Compatibility forwarding and process-global environment mutation weaken isolation. |
| Visitor / Analysis | Useful but heuristic | No | Duplicates command/builtin knowledge instead of deriving from shell capabilities. |
| Tests | Strong breadth | Good | Large test suite with conformance/regression focus; parity tests should assert deeper equivalence. |

## Detailed Findings

### Lexer

Strengths:

- The lexer has a recognizer registry and dedicated recognizers for whitespace, comments, operators, process substitution, and literals.
- `PositionTracker`, token parts, rich tokens, quote parsing, and expansion parsing show intentional structure.
- Several performance and correctness fixes are visible, such as incremental bracket tracking in `LiteralRecognizer`.

Weaknesses:

- Lexing is not mostly context-free. `ModularLexer` tracks command position, arithmetic depth, `[[ ]]` depth, and case context while producing tokens.
- `KeywordNormalizer` then runs another command-position/reserved-word pass, creating two partial grammar machines that can drift.
- Literal recognition is large and branch-heavy. `LiteralRecognizer` is over 700 lines and embeds many shell grammar exceptions.
- Command substitution parsing is not shell-grammar aware. `ExpansionParser._parse_command_substitution()` counts balanced parentheses and explicitly documents that `echo $(case x in x) echo inner;; esac)` fails even though bash accepts it.

Representative files:

- `psh/lexer/modular_lexer.py`
- `psh/lexer/recognizers/literal.py`
- `psh/lexer/keyword_normalizer.py`
- `psh/lexer/expansion_parser.py`

Suggested improvements:

- Move reserved-word recognition and command-position state to one parser/normalization stage.
- Keep lexer context only where the shell language truly requires lexical modes.
- Replace balanced-parenthesis command-substitution scanning with recursive shell parsing or a grammar-aware scanner.
- Reduce `LiteralRecognizer` by extracting explicit mini-parsers for braces, globs, array subscripts, and extglob.

### Parser

Strengths:

- The production recursive descent parser is split into command, statement, control-structure, redirection, arithmetic, array, function, and test parsers.
- `ParserContext` centralizes token stream state and error collection.
- The parser has useful feature gates and POSIX/bash compliance hooks.

Weaknesses:

- The parser still reconstructs shell source strings in places, especially array initialization.
- Array parsing handles multiple tokenization shapes through special cases rather than a single structured assignment grammar.
- The parser-combinator implementation is publicly selectable but marked experimental and not converged with production behavior.
- Existing parser parity tests mostly check successful parsing, not normalized AST equivalence or execution equivalence.

Representative files:

- `psh/parser/recursive_descent/parser.py`
- `psh/parser/recursive_descent/parsers/commands.py`
- `psh/parser/recursive_descent/parsers/arrays.py`
- `psh/parser/combinators/parser.py`
- `tests/test_parser_feature_parity.py`

Suggested improvements:

- Define one production parser contract. If the combinator parser is educational, keep it out of production-facing selection or mark its feature subset explicitly.
- Add normalized AST golden tests for parser parity where both parsers claim support.
- Introduce a structured assignment/array-element AST path so parser code does not reconstruct source strings from token values.
- Treat word parsing as a shared semantic layer rather than a set of local reparsing routines.

### AST And Word Model

Strengths:

- `Word`, `LiteralPart`, `ExpansionPart`, and expansion node classes are the right abstraction for shell semantics.
- The model carries quote context, which is essential for correct splitting and globbing.

Weaknesses:

- The model is not consistently used. Arrays, assignment values, process substitution, and some builtin paths still fall back to strings.
- Some AST classes are compatibility-oriented and contain old/simple fields alongside newer structured fields.
- `__str__` methods are useful for debugging but can blur the line between source rendering and semantic representation.

Suggested improvements:

- Make `Word` the canonical representation for all shell words, including array initializer elements, assignment values, redirection targets, and process substitution affixes.
- Avoid storing both raw string forms and structured word forms unless the invariant is documented and tested.
- Add invariants/tests that forbid semantic code from reparsing `str(word)` except in debugging/formatting paths.

### Expansion

Strengths:

- `ExpansionManager` applies the expected expansion phases and has a structural word path.
- The code handles tricky shell cases such as `$@`, quoted array fields, IFS edges, escaped glob characters, tilde expansion, and extglob.
- `WordSplitter`, `GlobExpander`, `VariableExpander`, and other helpers are separated enough to be testable.

Weaknesses:

- `ExpansionManager` is a 700-line semantic hub. `_expand_word()` alone is over 160 lines.
- Array initialization does not use the normal expansion engine. `ArrayOperationExecutor` calls `expand_string_variables()`, Python `.split()`, and raw `glob.glob()`, bypassing quote context, `IFS`, `noglob`, `nullglob`, `dotglob`, and the project `WordSplitter`/`GlobExpander`.
- Embedded process substitution is only detected as a whole unquoted argument. `cat <(printf hi)` works, but `echo pre<(echo hi)post` remains literal where bash produces an affixed `/dev/fd/...` path.
- `expand_expansion()` catches `ValueError`, `AttributeError`, and `TypeError` and returns `str(expansion)`, which can hide internal bugs as literal output.
- Parameter expansion parsing is heuristic in multiple layers.

Representative files:

- `psh/expansion/manager.py`
- `psh/expansion/variable.py`
- `psh/expansion/parameter_expansion.py`
- `psh/executor/array.py`

Suggested improvements:

- Route array initializer elements through the same `Word`-based expansion engine as command arguments.
- Represent process substitution as an expansion/word part, not a whole-argument pre-pass.
- Narrow expansion exception handling to known user-facing expansion errors; fail loudly for internal type/attribute errors.
- Split expansion policy by context: command argument, assignment value, array element, redirect target, pattern operand.
- Build one parameter-expansion parser and share it between lexing/word-building/evaluation.

### Executor

Strengths:

- The visitor-based executor separates top-level AST dispatch from command, pipeline, control-flow, array, function, and subshell execution.
- There is visible care around `errexit`, traps, command substitutions, assignments, background jobs, and command resolution.
- Strategy classes for special builtins, functions, builtins, aliases, and externals are a good direction.

Weaknesses:

- `CommandExecutor` remains a semantic hub: it handles traps, array assignments, assignment parsing, expansion ordering, temporary environment mutation, xtrace, `exec`, strategy dispatch, redirections, and error policy.
- Assignment-word expansion is implemented separately from normal word expansion.
- Fork/process policy is not fully centralized. `ProcessLauncher` exists, but command substitution still forks directly.
- Process signal mask restoration around fork should be guarded with `try/finally` in all paths.

Representative files:

- `psh/executor/core.py`
- `psh/executor/command.py`
- `psh/executor/pipeline.py`
- `psh/executor/process_launcher.py`
- `psh/expansion/command_sub.py`

Suggested improvements:

- Split command execution into an `AssignmentPlan`, `ExpansionContext`, `CommandResolution`, and `Invocation` phase.
- Centralize fork setup, signal policy, child shell construction, and parent cleanup in one helper used by external commands, command substitution, process substitution, and background execution.
- Make executor strategies consume a prepared invocation object rather than reading and mutating shell state directly.

### I/O Redirection

Strengths:

- This is one of the strongest subsystems.
- The `IOManager` module docstring explains the distinction between fd-level redirection for external commands and Python stream swapping for in-process builtins.
- Builtin redirection setup is transactional and attempts rollback on failure.
- Process substitution cleanup scopes show real attention to fd and zombie handling.

Weaknesses:

- Builtin redirection state is stored on the singleton `IOManager` via mutable fields like `_opened_streams`, which risks nested redirection interference.
- Some cleanup relies on broad exception swallowing, understandable for fd cleanup but hard to audit.

Representative files:

- `psh/io_redirect/manager.py`
- `psh/io_redirect/file_redirect.py`
- `psh/io_redirect/process_sub.py`

Suggested improvements:

- Replace manager-level mutable redirect state with a per-redirection context object.
- Add stress tests for nested builtin redirection through `eval`, `source`, traps, and command substitutions.
- Keep the strong stream-vs-fd documentation; it is close to textbook-quality explanatory material.

### Interactive

Strengths:

- The line editor supports substantial behavior: emacs/vi modes, history, completion, raw fd reads, resize handling, and prompt width behavior.
- Interactive tests exist, including PTY smoke tests.

Weaknesses:

- `LineEditor` is over 1,000 lines and owns input reading, rendering, key dispatch, history search, completion state, undo/redo, vi mode, and terminal behavior.
- Signal handlers are installed for interactive mode but are not clearly restored when the REPL exits.
- Several interactive tests are skipped or xfailed because PTY behavior is difficult.

Representative files:

- `psh/interactive/line_editor.py`
- `psh/interactive/repl_loop.py`
- `psh/interactive/signal_manager.py`
- `tests/system/interactive/`

Suggested improvements:

- Split line editing into buffer model, keymap dispatch, renderer, terminal I/O adapter, history search, and completion controller.
- Wrap interactive loop lifecycle in `try/finally` that restores signals and terminal resources.
- Continue moving interactive behavior into PTY-backed tests rather than pipe-based tests.

### Builtins

Strengths:

- The builtin registry is simple and convenient.
- Builtins are grouped by domain and have broad tests.
- Many builtins are pragmatic and readable in isolation.

Weaknesses:

- The global registry stores builtin instances, so the architecture assumes builtins are stateless.
- Some builtins are very large, especially `read`, `declare`, `printf`, and I/O-related builtins.
- Visitor/linter code duplicates builtin command knowledge instead of deriving it from the registry.

Representative files:

- `psh/builtins/registry.py`
- `psh/builtins/read_builtin.py`
- `psh/builtins/function_support.py`
- `psh/builtins/io.py`

Suggested improvements:

- Either enforce builtin statelessness with tests or register classes/factories instead of singleton instances.
- Extract shared option parsing and output routing patterns from large builtins.
- Feed command/builtin metadata into visitors and help/lint tools from one source of truth.

### Core State And Shell Orchestration

Strengths:

- `ShellState`, scope management, functions, options, traps, and variable attributes are separated enough to understand the runtime model.
- Parent-shell inheritance handles many subtle shell details.

Weaknesses:

- `Shell.__init__()` is a god-constructor that wires state, managers, parser selection, traps, history, interactive mode, rc loading, and compatibility behavior.
- `Shell.__getattr__`/`__setattr__` delegate many names into `ShellState`, which hides ownership and makes static reasoning harder.
- The shell mutates process-global `os.environ` in some paths even though it also has shell-local environment state.

Representative files:

- `psh/shell.py`
- `psh/core/state.py`
- `psh/core/scope.py`

Suggested improvements:

- Split shell construction into explicit lifecycle phases: state creation, manager wiring, parent inheritance, parser selection, interactive initialization, rc loading.
- Gradually remove compatibility attribute forwarding and access `shell.state` explicitly.
- Keep `os.environ` immutable after startup except for deliberate, documented integration points.

### Visitor And Analysis Tools

Strengths:

- Visitor pattern is useful for execution, formatting, metrics, linting, validation, and security checks.
- Traversal helpers reduce repeated AST walking code.

Weaknesses:

- Analysis visitors duplicate semantic knowledge and static command allowlists.
- Formatter/debug visitors still have unknown-node fallbacks, which is acceptable for tooling but not a strong invariant.
- Visitor tools should be framed as heuristic unless fed a real shell capability model.

Representative files:

- `psh/visitor/`
- `psh/utils/shell_formatter.py`

Suggested improvements:

- Derive builtin/function/command knowledge from runtime registries where possible.
- Add visitor coverage tests that every AST node type has explicit behavior in formatter, validator, and executor paths.
- Keep heuristic security/lint warnings clearly separated from semantic validation.

## Concrete Correctness Risks To Prioritize

1. **Array initializer expansion is wrong for quoted globs and custom IFS.**
   - Current path: `psh/executor/array.py` uses string variable expansion, `.split()`, and `glob.glob()`.
   - Expected direction: parse array elements as `Word` nodes and use the normal expansion engine with context-specific policy.

2. **Embedded process substitution is missed.**
   - Current path: `ExpansionManager._has_process_substitution()` only recognizes whole words.
   - Expected direction: process substitution should be an expansion part with support for prefix/suffix text.

3. **Command substitution scanning is not shell-grammar aware.**
   - Current path: `ExpansionParser._parse_command_substitution()` counts balanced parentheses.
   - Expected direction: recursively parse shell syntax inside `$()` or implement a grammar-aware scanner.

4. **Parameter expansion parsing is duplicated and heuristic.**
   - Current path: lexer classification plus `WordBuilder` reparsing plus evaluator parsing.
   - Expected direction: one parser for `${...}` with nested quote/brace/operator awareness.

5. **Expansion failures can become literals.**
   - Current path: `ExpansionManager.expand_expansion()` catches broad implementation exceptions and returns `str(expansion)`.
   - Expected direction: distinguish user expansion errors from internal bugs.

6. **Nested builtin redirections can share mutable manager state.**
   - Current path: `IOManager` stores redirect setup state on the manager instance.
   - Expected direction: per-operation redirect context objects.

7. **Shell state leaks into process-global environment.**
   - Current path: some state/export assignment paths write `os.environ`.
   - Expected direction: use shell-local env for child launch; document any unavoidable host integration.

## Roadmap

### Phase 1: Fix semantic bugs with minimal architecture churn

- Route array initialization through the `Word` expansion pipeline.
- Add regression tests for quoted `*` in arrays, custom `IFS` in arrays, and embedded process substitution with affixes.
- Stop converting broad internal expansion exceptions to string output.
- Add lifecycle cleanup for interactive signal handlers.
- Wrap fork signal-mask restoration in `try/finally`.

### Phase 2: Establish semantic single sources of truth

- Make `Word` the canonical shell-word representation across command args, assignments, arrays, redirects, and process substitution.
- Create explicit expansion policy objects for argument, assignment, array element, redirect target, and pattern contexts.
- Replace parameter expansion string heuristics with one parser.
- Centralize fork/process setup.

### Phase 3: Reduce architecture ambiguity

- Decide whether the parser-combinator implementation is educational-only or production-supported.
- If supported, add normalized AST parity tests. If not, remove it from production-facing parser selection.
- Remove broad shell-state compatibility forwarding.
- Convert builtin registry from global singleton instances to factories, or enforce statelessness.

### Phase 4: Refactor large classes

- Split `LineEditor` into model, renderer, key dispatch, terminal adapter, history search, and completion controller.
- Split `CommandExecutor` into assignment planning, expansion preparation, command resolution, invocation, and error policy.
- Split `ExpansionManager` by context and move complex word-field algorithms into focused helpers with dense unit tests.
- Shrink `LiteralRecognizer` by extracting brace/glob/extglob/array-subscript scanners.

## Final Judgment

The project is not low-quality. It is a substantial implementation with many careful fixes and a strong test culture. But "textbook quality" requires sharper invariants than the current code has. The central architectural issue is that the shell language's grammar and expansion semantics are implemented in several overlapping places. That creates correctness drift and makes the system harder to extend safely.

The best path forward is not a rewrite. The project already has the right raw materials: AST words, expansion parts, parser modules, an executor visitor, redirection scopes, and conformance tests. The next quality jump comes from making those structures authoritative everywhere and deleting the older string-based fallback paths as tests lock behavior down.
