# PSH Subsystem Code Quality Reassessment - 2026-06-12

## Scope

This is a fresh reassessment of the current source tree as of 2026-06-12. It does not rely on earlier review documents as evidence. I inspected the implementation directly, focusing on the lexer, parser, expansion, executor, redirection, visitor, and interactive subsystems, then ran targeted tests and command-line smoke checks against the areas that previously looked fragile.

## Executive Summary

The project is now materially stronger than the previous state. Several earlier high-risk semantic issues have been fixed with structural changes rather than narrow patches:

- Builtin redirection restoration now uses explicit per-invocation frames.
- Assignment expansion is now context-sensitive instead of suppressing splitting for any word containing `=`.
- `for` and `select` iterable words now preserve AST `Word` structure through expansion.
- Array element assignment values now carry `Word` structure.
- Command substitution extent detection is grammar-aware enough to handle nested `case`, quotes, comments, and heredoc-like constructs.
- `case` subjects are now parsed with the right shape: one word before `in`.
- Visitor coverage and redirect-carrier checks now have an introspective coverage matrix.

My current rating is:

- **Correctness trajectory:** strong and improving.
- **Architecture:** good, with clear subsystem boundaries and increasingly explicit invariants.
- **Textbook quality:** not yet. The system is now credible production-quality educational shell code in many areas, but several core classes and scanner functions remain too large and specialized to call textbook-clean.

The most important remaining theme is no longer "obvious semantic bugs in central shell behavior." It is now "complexity control and proving that legacy paths are either intentional or unreachable."

## What Improved

### Lexer

The lexer is better than before in the areas I inspected.

`psh/lexer/pure_helpers.py` now contains a grammar-aware `find_command_substitution_end()` rather than a simple parenthesis counter. It tracks nested command substitutions, quotes, comments, grouped commands, heredoc-like forms, and `case` statements. The behavior is backed by focused tests such as `tests/unit/lexer/test_cmdsub_extent.py`, `tests/integration/parsing/test_cmdsub_grammar.py`, and `tests/conformance/bash/test_cmdsub_case_conformance.py`.

`psh/lexer/modular_lexer.py` also now distinguishes confirmed array-assignment subscript context from ordinary bracket-looking text. That closes the class of bugs where an unterminated quote inside something resembling `x["...` could be hidden by a heuristic.

Remaining concern: the command-substitution scanner is now much more correct, but it is also a 300+ line specialized parser embedded in lexer helpers. That is a reasonable engineering tradeoff for shell lexing, but not textbook quality. It needs to be treated as a parser component with a permanent conformance suite and very clear ownership. The docstring acknowledges that it is not a full recursive parser, which is honest and useful.

### Parser

The recursive descent parser has improved in important semantic ways.

`for` and `select` parsing now preserve iterable `item_words`, allowing later expansion to use the canonical word-expansion pipeline. `case` parsing now enforces a single subject word before `in`, so invalid input such as `case a b in ...` is rejected instead of silently taking only part of the input as the subject.

The parser also appears to have better coverage around misplaced `case` terminators and command substitution grammar. This is the right direction: shell syntax has enough contextual behavior that parser regressions need precise negative tests, not just happy-path AST checks.

Remaining concern: there is still a dual-parser story, with the combinator parser present and apparently selectable/experimental. Some parity coverage exists, but a textbook codebase would either make parser parity a hard contract across supported syntax or clearly mark one parser as research/diagnostic infrastructure outside the main quality bar.

### Expansion

Expansion is significantly better.

`ExpansionManager` no longer treats any word containing `=` as assignment-like. Instead, declaration builtin handling is syntactic:

- the command word must be an unquoted literal declaration builtin,
- the argument must have an unquoted literal assignment prefix,
- only that value portion receives assignment-value expansion semantics.

That fixes a central shell-behavior bug: an ordinary argument like `foo=$x` now undergoes normal field splitting when `$x` contains spaces.

`expand_assignment_value_word()` is now used for array element assignments and command assignment values where `Word` structure exists. This preserves quote and expansion semantics far better than reconstructing strings after parsing.

Remaining concern: `ExpansionManager` is still very large, and `_expand_word()` is still a long, multi-mode function. The quality is better than before, but the design would be easier to reason about if the modes were split into smaller explicit strategies, for example normal word expansion, assignment-value expansion, declaration-assignment expansion, and here-doc/body expansion.

### Executor

The executor has meaningful correctness upgrades.

In `psh/executor/command.py`, builtin redirection now receives a redirect frame from `IOManager.setup_builtin_redirections()` and restores exactly that frame in `finally`. Pure assignments and command assignments now use `value_word` when available.

In `psh/executor/array.py`, array element assignment uses `node.value_word` with assignment-value expansion. Array initialization also handles explicit `[index]=value` entries with better structure than before.

Remaining concerns:

- `CommandExecutor` remains a large class with several responsibilities.
- Some fallback paths remain for legacy string-only AST values. These may be necessary for compatibility or tests, but they should be made explicit: either prove them reachable and test them, or isolate/deprecate them.
- Environment mutation still reaches `os.environ` directly in places such as `psh/core/state.py` and `psh/executor/command.py`. A textbook shell core would centralize environment snapshots and process environment application more tightly.

### Redirection

Redirection quality improved substantially.

`psh/io_redirect/manager.py` now has `BuiltinRedirectFrame`, with per-frame tracking of:

- original file descriptor snapshots,
- saved descriptors,
- opened streams,
- closed descriptors.

This fixes the nested builtin redirection class of bugs because restore no longer depends on a single shared manager-level mutable state. It is a good example of replacing implicit global state with explicit ownership.

Remaining concern: process substitution and command substitution still have separate direct fork paths. Child signal policy appears better centralized than before, but fork setup would be more textbook if there were a shared internal helper for child process setup, environment handling, signal disposition, and error reporting.

### Visitors

Visitor coverage is much stronger.

`FormatterVisitor` now handles `UntilLoop`, and `SecurityVisitor` now checks redirects attached to compound commands instead of only simple commands. The new `tests/unit/visitor/test_ast_coverage_matrix.py` is especially valuable because it checks visitor coverage against the AST shape rather than relying entirely on hand-written examples.

Remaining concern: introspective coverage tests are a strong guardrail, but visitor behavior tests should still cover representative runtime/security outcomes. The matrix can prove that a method exists; it cannot prove the method implements the right semantics.

### Interactive

The interactive subsystem remains mostly unchanged in the current assessment. It has useful tests and clear separation from non-interactive execution, but `LineEditor` remains over 1,000 lines. This is one of the clearest non-textbook areas in the codebase.

The likely next quality improvement is to split terminal mode management, key decoding, history navigation, completion UI, rendering, and editing buffer operations into smaller components with contract tests around each.

## Validation Performed

Targeted pytest command:

```bash
python -m pytest \
  tests/integration/redirection/test_builtin_redirect_nesting.py \
  tests/unit/expansion/test_assignment_word_splitting.py \
  tests/integration/control_flow/test_for_select_item_expansion.py \
  tests/integration/arrays/test_array_element_word_values.py \
  tests/unit/lexer/test_bracket_quote_words.py \
  tests/unit/lexer/test_cmdsub_extent.py \
  tests/integration/parsing/test_cmdsub_grammar.py \
  tests/conformance/bash/test_cmdsub_case_conformance.py \
  tests/unit/parser/test_case_subject.py \
  tests/unit/parser/test_misplaced_case_terminators.py \
  tests/unit/visitor/test_ast_coverage_matrix.py \
  tests/unit/visitor/test_analysis_visitors.py
```

Result:

```text
417 passed in 5.36s
```

Smoke checks:

- Nested builtin redirection no longer leaks writes into the original target.
- Ordinary `foo=$x` arguments now split normally when `$x` contains spaces.
- `case` inside command substitution now lexes/parses correctly.
- `until` formatting no longer fails due to a missing visitor.
- Security analysis now catches sensitive output redirects on compound commands.
- Unterminated quotes in bracket-looking ordinary words are rejected.
- `case a b in ...` is rejected with a parse error.

## Remaining Quality Risks

### 1. Large Core Classes and Functions

The largest current quality risk is complexity concentration.

Representative examples from the current tree:

- `LineEditor`: about 1,048 lines.
- `ExpansionManager`: about 914 lines.
- `LiteralRecognizer`: about 707 lines.
- `SpecialCommandParsers`: about 700 lines.
- `CommandExecutor`: about 700 lines.
- `ModularLexer`: about 687 lines.
- `find_command_substitution_end()`: about 322 lines.
- `_expand_word()`: about 233 lines.

Large code is not automatically bad, but in a shell these files sit exactly where language semantics are most subtle. The larger they get, the harder it is to audit whether a change preserves quoting, splitting, redirects, traps, subshell behavior, and parse context.

Recommendation: prioritize decomposition where it creates semantic boundaries, not just smaller files. The most useful splits would be expansion mode objects/functions, command-substitution scanning helpers, command executor strategies, and line-editor components.

### 2. Legacy AST Fallbacks

Several new fixes correctly preserve `Word` structure, but compatibility fallbacks remain for string-only paths.

Recommendation: classify each fallback as one of:

- required public compatibility,
- parser migration bridge,
- unreachable defensive branch,
- dead code.

Then add tests for the first two categories and remove or assert the last two categories. This would make the new canonical AST path much easier to trust.

### 3. Dual Parser Contract

The combinator parser is a useful experiment, but its supported contract is still less clear than the recursive descent parser's. A textbook-quality project would make this explicit.

Recommendation: decide whether the combinator parser is:

- a supported alternate parser with required parity tests,
- a development experiment,
- or a subsystem scheduled for removal.

Any answer is acceptable; ambiguity is the problem.

### 4. Specialized Lexer Grammar Drift

The new command substitution scanner is a serious improvement, but it creates a grammar model parallel to the parser. That means future parser grammar changes can drift from command-substitution extent detection.

Recommendation: keep adding conformance tests for tricky `$()` bodies: nested `case`, nested functions, arithmetic, here-doc variants, comments, quoted delimiters, process substitution, and parse-error boundaries. Also add a short developer note describing when parser changes must update `find_command_substitution_end()`.

### 5. Environment and Fork Boundaries

Environment handling and child-process setup are improved but not yet ideal. Direct `os.environ` mutation and separate fork paths make it harder to reason about isolation.

Recommendation: centralize process launch preparation around a small internal API that owns environment materialization, signal disposition, file descriptor setup, and error reporting. This would reduce semantic drift between external commands, command substitution, process substitution, and subshell-like execution.

### 6. Interactive Subsystem Size

The interactive layer is still too monolithic to be textbook. It may work well, but `LineEditor` is carrying too much state and behavior in one class.

Recommendation: split it only along observable responsibilities: input decoding, buffer editing, history movement, completion presentation, screen rendering, and terminal lifecycle. Avoid a cosmetic split that just moves methods without narrowing contracts.

## Subsystem Grades

These grades are qualitative and relative to "textbook quality" as a high bar.

| Subsystem | Current Grade | Notes |
| --- | --- | --- |
| Lexer | B+ | Stronger correctness; command-sub scanner is much better but complex. |
| Parser | B+ | Recursive descent path is solidifying; dual-parser contract remains unclear. |
| Expansion | B+ | Major semantic fixes; still concentrated in a large multi-mode manager. |
| Executor | B | Correctness improved; class size, environment handling, and fallbacks remain concerns. |
| Redirection | A- | Builtin redirection frame design is a strong fix; fork/redirection paths could be unified further. |
| Visitors | A- | Coverage matrix is excellent; continue adding behavior-level visitor tests. |
| Interactive | B- | Useful and functional, but still too monolithic for textbook code. |
| Tests | A- | Targeted regression coverage is strong; full conformance breadth remains the long-term challenge. |

## Recommended Next Steps

1. Document the canonical AST data-flow for words, assignment values, array elements, redirects, and compound commands.
2. Audit every string-only legacy fallback and either test, isolate, or remove it.
3. Split expansion modes out of `_expand_word()` into explicit, named paths.
4. Treat `find_command_substitution_end()` as a parser component: add ownership notes and keep expanding conformance tests.
5. Define the combinator parser's support status.
6. Centralize child process setup across command substitution, process substitution, external commands, and subshell-like execution.
7. Decompose `LineEditor` around observable responsibilities.

## Bottom Line

The project is now much closer to the quality bar it is aiming for. The recent changes fixed real shell semantics at the right architectural level, especially in redirection, expansion, parser word preservation, and visitor coverage.

It is still not textbook quality overall because too much subtle behavior remains concentrated in large functions and classes, and some compatibility paths are not clearly classified. But the current codebase is no longer dominated by the earlier correctness gaps. The next phase should be about shrinking semantic hot spots and making the new canonical paths impossible to bypass accidentally.
