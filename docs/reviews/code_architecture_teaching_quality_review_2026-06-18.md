# Code and Architecture Quality Review

Date: 2026-06-18

Scope: repository-wide assessment of PSH as code, architecture, and a future textbook-quality teaching resource. This review sampled the main architecture docs, all subsystem `CLAUDE.md` files, the lexer/parser/AST path, expansion/executor/I/O/core state, public documentation, and representative tests. Three parallel explorer reviews were also used for independent subsystem coverage.

## Executive Summary

PSH is already a serious and unusually well-documented educational shell. The strongest architectural ideas are clear:

- `Word` AST nodes are the canonical argument representation, with quote and expansion structure preserved instead of flattened too early.
- Expansion uses named policies and an explicit segment model, making shell word-splitting and globbing rules inspectable.
- Command execution has moved important policy decisions into named objects such as `CommandResolution`, `ExecutionResult`, `RedirectionMode`, and `CommandAssignments`.
- Fork and child-process behavior is centralized enough to be teachable, especially through `child_policy.py`.
- The test suite contains valuable invariant and characterization tests, not only example-driven unit tests.

The project is not yet textbook quality overall. It is functionally mature, but the teaching surface still has too much drift, too many old review artifacts, and several complex semantic paths whose invariants are carried by prose rather than by types or narrower interfaces. The next phase should not be broad feature work. It should be a clarity pass: make the core model smaller, more explicit, and easier to trust.

## Top Priorities

### 1. Fix the process-substitution child-shell policy

Priority: High  
Type: correctness and architecture

`psh/io_redirect/process_sub.py` creates process-substitution children with `run_child_shell(..., norc=False)`. For input process substitution, the child only rewires stdout; stdin can remain the parent fd 0. `run_child_shell()` then builds a child shell after I/O setup, and `Shell._init_interactive()` uses `sys.stdin.isatty()` to decide whether to load interactive state and rc files.

This creates a plausible bug: in an interactive parent, `<(cmd)` can accidentally construct an interactive child shell and source rc files. That conflicts with the `Shell.for_subshell()` docstring, which says children skip rc loading by default.

Recommended work:

1. Add a pinned behavior test for interactive `<(cmd)` proving rc files are not sourced and stdin is not consumed.
2. Change process substitution to use `norc=True` unless there is a bash-verified reason not to.
3. Introduce a small child-shell mode object or enum for command substitution, process substitution, subshells, env children, and background shell children. It should centralize `norc`, stdin policy, stream inheritance, and `is_shell_process`.

Relevant files:

- `psh/io_redirect/process_sub.py`
- `psh/executor/child_policy.py`
- `psh/shell.py`

### 2. Make the public teaching surface reproducible and self-consistent

Priority: High  
Type: documentation, trust, teaching quality

The repo has excellent material, especially `docs/architecture/tour_of_psh_internals.md`, but the first-contact docs are not as trustworthy as the internals. Examples and statistics drift:

- `README.md` says both `8,439 total` and `5,500+` tests.
- `README.md` demonstrates `examples/fibonacci.sh`, but there is no `examples/` directory.
- `tests/README.md` names directories and docs that do not exist.
- `docs/testing_source_of_truth.md` says `python run_tests.py --quick` is canonical, while root `CLAUDE.md` says the release gate is `python run_tests.py --parallel` plus ruff and mypy.

For a textbook resource, runnable examples and accurate claims matter as much as implementation quality.

Recommended work:

1. Add a small `examples/` tree with scripts for metrics, lint, security, parser visualization, shell basics, and a larger idiomatic shell script.
2. Add smoke tests that run the examples through the documented commands.
3. Extend doc-pointer/statistics tests to cover `README.md`, `tests/README.md`, `docs/testing_source_of_truth.md`, and `docs/test_pattern_guide.md`.
4. Replace scattered exact test-count claims with one generated or deliberately rounded statistics block.
5. Rewrite `tests/README.md` from the actual current tree.

Relevant files:

- `README.md`
- `tests/README.md`
- `docs/testing_source_of_truth.md`
- `tests/unit/tooling/test_doc_pointers.py`

### 3. Simplify the parser top level so the grammar has one obvious path

Priority: High  
Type: architecture and teaching clarity

The recursive-descent parser is generally readable and well partitioned, but top-level parsing duplicates normal grammar machinery. `Parser._parse_top_level_item()` parses top-level control structures separately, then manually wraps pipelines, `&&`/`||`, and backgrounding. Ordinary commands flow through `StatementParser` and `CommandParser`.

This weakens the textbook story. A reader should be able to trace `statement -> and_or_list -> pipeline -> command` without learning a second top-level variant for control structures.

Recommended work:

1. Make the top-level parser call the same statement and and-or machinery wherever possible.
2. Keep function definitions as the primary top-level special case if needed.
3. Add regression tests around control structures followed by `|`, `&&`, `||`, and `&` before refactoring.

Relevant files:

- `psh/parser/recursive_descent/parser.py`
- `psh/parser/recursive_descent/parsers/statements.py`
- `psh/parser/recursive_descent/parsers/commands.py`

### 4. Turn prose-only semantic contracts into explicit interfaces

Priority: Medium-high  
Type: architecture

Many important invariants are accurately documented, but some are still enforced mainly by discipline:

- Parser sub-parsers share an implicit contract but no common protocol/base.
- Declaration array initializer delivery uses a transient shell slot, `_pending_array_inits`, set by `CommandExecutor` and read by declaration builtins.
- Process-substitution cleanup has both a planner-owned resource model and manual `active_fds` mutation in builtin redirection setup.
- `ShellState.options` remains a large string-keyed policy surface.

The comments are good, but textbook code should make illegal states harder to represent.

Recommended work:

1. Add a small `ParserSubcomponent` protocol/base to formalize the sub-parser interface.
2. Replace the pending array-init shell slot with an explicit `CommandInvocation` or `BuiltinContext` object passed to builtins.
3. Consolidate process-substitution resource ownership so the planner/resource object owns close semantics in all paths.
4. Gradually move shell options into typed groups, following the pattern already used for `ExecutionState`, `StreamBindings`, `TerminalState`, and `HistoryState`.

Relevant files:

- `psh/parser/recursive_descent/parser.py`
- `psh/shell.py`
- `psh/executor/command.py`
- `psh/io_redirect/manager.py`
- `psh/io_redirect/planner.py`
- `psh/core/state.py`

### 5. Reduce lexer command-position and word-recognition complexity

Priority: Medium-high  
Type: architecture and pedagogy

The lexer is robust and heavily documented, but it is conceptually expensive. Command-position state is tracked by the lexer, the keyword normalizer, and the command-substitution scanner. The literal recognizer also encodes assignment subscripts, glob classes, extglob, tilde forms, inline ANSI-C strings, arithmetic context, comments, and escapes in one large collection loop.

Some of this is inherent shell complexity. The improvement is not to pretend it is simple, but to make the state machines smaller and more visibly related.

Recommended work:

1. Add a transition-table diagram for command-position state across lexer, normalizer, and command-substitution scanner.
2. Split the literal recognizer loop into named `try_consume_*` helpers while keeping the current forward `WordShapeTracker` model.
3. Consider making braced parameter tokens less ambiguous: either emit one braced-parameter token and let `param_parser.py` classify it, or make lexer classification call the same parser.

Relevant files:

- `psh/lexer/command_position.py`
- `psh/lexer/modular_lexer.py`
- `psh/lexer/keyword_normalizer.py`
- `psh/lexer/cmdsub_scanner.py`
- `psh/lexer/recognizers/literal.py`
- `psh/parser/recursive_descent/support/word_builder.py`
- `psh/expansion/param_parser.py`

### 6. Curate the documentation set for students, not only maintainers

Priority: Medium  
Type: teaching quality

There are many high-value review and architecture documents under `docs/reviews/`, but the volume now obscures the canonical learning path. A student should not have to infer which documents are current.

Recommended work:

1. Create a short `docs/learning_path.md` that orders the reading sequence:
   `README.md` -> `ARCHITECTURE.md` quick map -> internals tour -> AST data flow -> selected subsystem notes -> examples.
2. Archive or index old review documents with a status table: current, superseded, historical.
3. Move implementation-history detail out of the main README into changelog/release notes.
4. Keep `CLAUDE.md` files as contributor/agent guidance, but do not make them the main textbook narrative.

Relevant files:

- `docs/reviews/`
- `docs/architecture/tour_of_psh_internals.md`
- `docs/architecture/ast_data_flow.md`
- `ARCHITECTURE.md`
- `README.md`

## Strengths To Preserve

### Word AST as the teaching anchor

`psh/ast_nodes/words.py` is one of the best parts of the project. `Word.parts`, `LiteralPart`, `ExpansionPart`, derived `quote_type`, `display_text()`, and `to_literal_string()` give students a concrete model for why shells cannot parse words as plain strings.

Preserve this model and keep pushing callers toward structured `Word` APIs rather than rendered text.

### Expansion policy and segment IR

`WordExpansionPolicy` and `ExpandedSegment` make a notoriously confusing shell topic explainable. The separation between the field-producing word walker and assignment-value scalar walker is a good design decision. This is already close to textbook material.

The next improvement is mostly presentation: diagrams and adversarial examples showing when each policy applies.

### Executor policy naming

`CommandAssignments`, `CommandResolution`, `ExecutionResult`, and `RedirectionMode` are good examples of replacing boolean soup with domain language. The command executor remains large, but it is no longer opaque.

Continue extracting named policy objects where behavior has a shell-semantics label.

### I/O redirection documentation

The stream-vs-fd split in `psh/io_redirect/manager.py` is unusually clear for a difficult subject. The `BuiltinRedirectFrame` model also teaches nested redirection restoration well. This should be retained and turned into a diagram in the internals tour.

### Child-process policy centralization

`fork_with_signal_window()`, `apply_child_signal_policy()`, and `run_child_shell()` give process behavior one narrative. That is valuable because most shell implementations scatter this knowledge across fork sites.

The recommendation above is to add child mode data, not to undo the centralization.

### Tests as architecture

The suite contains meta-tests and invariant tests that teach intent:

- AST canonical invariant tests
- legacy-field isolation tests
- doc-pointer tests
- conformance claim mapping
- behavioral golden cases

This is the right direction. The next step is to make investigatory tests visually distinct from conformance assertions.

## Areas For Smaller Cleanup

- Remove or quarantine generated caches from the repository tree if they are tracked or regularly visible: `__pycache__`, `.ruff_cache`, `.pytest_cache`, and `.DS_Store` clutter the teaching view.
- Rename conformance tests that call non-asserting `check_behavior()` so they do not look like proof of compatibility.
- Update `docs/test_pattern_guide.md` to prefer the conformance framework over raw subprocess examples for bash comparison tests.
- Tighten overbroad claims such as "Advanced Error Recovery" if the implementation is primarily error collection and contextual diagnostics.
- Keep exact version/test-count metadata in fewer places.

## Suggested Roadmap

### Phase 1: Trust and correctness

1. Fix or prove safe the process-substitution child-shell policy.
2. Make README examples runnable by adding `examples/`.
3. Align test command documentation.
4. Extend doc/statistics pointer checks to high-traffic docs.

### Phase 2: Core model clarity

1. Refactor parser top-level control-structure handling into the normal statement path.
2. Formalize parser subcomponent contracts.
3. Replace `_pending_array_inits` with an explicit invocation context.
4. Consolidate process-substitution resource cleanup.

### Phase 3: Textbook presentation

1. Add a canonical learning path.
2. Add diagrams for the interpreter pipeline, `Word` AST, expansion policies, redirection universes, and child process modes.
3. Curate old review docs into an indexed archive.
4. Add example scripts and exercises tied to the architecture tour.

## Overall Assessment

PSH is a strong educational implementation with real architectural maturity. It is not merely a pile of shell features in Python; it has a coherent data model and several well-named semantic subsystems.

The remaining gap is economy. Too much of the current quality depends on long comments explaining why a complex path is safe. For a textbook resource, the code should increasingly carry those explanations in its shape: fewer parallel paths, narrower context objects, typed policy surfaces, runnable examples, and one canonical learning route through the repo.

