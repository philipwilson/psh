# Code and Architecture Quality Reassessment

Date: 2026-06-20

This reassessment revisits the findings from
`docs/reviews/code_architecture_teaching_quality_review_2026-06-18.md`
after the recent changes. The criteria are the same: clarity, elegance,
economy, and suitability as a textbook-quality teaching codebase.

## Executive Summary

The codebase has moved materially closer to the goal. The most important
correctness issue from the previous review is fixed, the parser top-level
design has been simplified in exactly the right direction, the public
teaching surface is now guarded by tests, and the documentation has a much
clearer learning path.

Four of the six prior priority recommendations are satisfied or mostly
satisfied. Two remain partially open:

1. semantic contracts are improved for shell options, but several important
   cross-subsystem contracts are still implicit or side-channel based; and
2. lexer command-position documentation is now much stronger, but literal
   recognition and parameter-expansion classification still carry avoidable
   complexity.

The project is now less a "large codebase that teaches by being available"
and more a "codebase that intentionally teaches." The remaining work is less
about broad cleanup and more about sharpening a few architectural contracts so
students can see clean boundaries instead of inheriting folklore.

## Status Against Previous Recommendations

| # | Previous recommendation | Current status | Assessment |
|---|---|---|---|
| 1 | Fix process-substitution child-shell policy | Satisfied | The high-priority rc-file leak is fixed and regression-tested. |
| 2 | Make the public teaching surface reproducible and self-consistent | Mostly satisfied | Examples, README claims, and high-traffic docs now have guardrails. A few exact statistics remain duplicated. |
| 3 | Simplify parser top-level control-structure handling | Satisfied | Top-level parsing now uses the normal command-list grammar path. This is the strongest architectural improvement. |
| 4 | Turn prose-only semantic contracts into explicit interfaces | Partially satisfied | Shell options are now centralized and validated. Parser sub-parser contracts, array-init side channels, and some process-substitution cleanup ownership remain implicit. |
| 5 | Reduce lexer command-position and word-recognition complexity | Partially satisfied | Command-position vocabulary is documented and tested. Literal recognition and parameter-expansion classification remain complex. |
| 6 | Curate the documentation set for students | Satisfied | The learning path and reviews index make the repository much easier to approach. |

## 1. Process-Substitution Child-Shell Policy

Status: satisfied for the reported correctness issue.

The previous review flagged that process-substitution children in interactive
contexts could source startup files and pollute command output. That behavior
has been fixed. `psh/io_redirect/process_sub.py` now invokes child shells with
`norc=True` for both read and write process substitution paths, while preserving
the interactive execution context where needed.

The regression coverage is strong. `tests/integration/test_interactive_child_rc_leak.py`
creates an interactive PTY-backed shell with a temporary startup file and
checks three important properties:

- subshell-style children do not source the rc file;
- `<(echo HI)` output is not polluted by startup-file output; and
- process substitution still preserves the expected interactive option state.

Residual improvement:

The underlying policy is still represented by call arguments rather than a
named child-shell mode. That is acceptable now because the bug is covered, but
a small policy object or enum would still make this behavior more teachable
when more child contexts are added.

## 2. Public Teaching Surface

Status: mostly satisfied.

The previous review found that examples and documentation claims were not
reproducible enough for a teaching resource. This has improved substantially.

Notable improvements:

- `examples/` now contains real runnable examples plus an explanatory
  `examples/README.md`.
- `tests/unit/tooling/test_examples.py` validates that examples are populated,
  syntactically valid, and runnable where appropriate.
- `tests/unit/tooling/test_user_doc_links.py` checks high-traffic user-facing
  docs for broken repo-rooted paths and local markdown links.
- `tests/unit/tooling/test_readme_statistics.py` guards README statistics
  against large drift.
- `tests/README.md` and `docs/testing_source_of_truth.md` now point students
  toward the same testing story instead of competing narratives.

Residual improvement:

The README still contains exact test-count claims such as the collected test
count and file count. These are now guarded, which is a major improvement, but
for a low-maintenance teaching surface approximate claims are still preferable
unless exactness is important to the lesson.

## 3. Parser Top-Level Control Structures

Status: satisfied.

This is the clearest architectural win since the previous review.

The former design had special top-level parsing paths that manually assembled
pipeline and and/or-list structure around leading control constructs. That made
top-level syntax feel like an exception to the grammar students were otherwise
learning.

The current parser is much cleaner:

- `_parse_top_level_item()` now delegates to the normal command-list parser.
- Manual top-level construction of `Pipeline()` and `AndOrList()` is gone.
- The historical bare-compound top-level AST shape is isolated in
  `_simplify_result()`.
- `tests/unit/parser/test_top_level_control_structure_grammar.py` explicitly
  guards the intended architecture, including parser-shape checks that prevent
  reintroducing the old special path.
- `psh/parser/CLAUDE.md` now documents the single grammar path and the narrow
  compatibility exception.

This change improves correctness, economy, and pedagogy at once. The parser is
now easier to explain: parse the grammar once, then simplify the public result
shape where compatibility requires it.

## 4. Explicit Semantic Contracts

Status: partially satisfied.

The shell-options portion of this finding is satisfied. The new
`psh/core/option_registry.py` centralizes option definitions, categories,
short-name mapping, defaults, shopt exposure, and `$-` ordering. `ShellOptions`
preserves dict-like compatibility while validating unknown option names and
providing typed accessors for hot options. The associated unit tests are a good
model for contract-oriented teaching code.

Remaining contract issues:

- Parser sub-parsers still follow an implicit convention rather than a shared
  interface. `psh/parser/CLAUDE.md` still describes this as an implicit
  contract with no enforcing base class.
- Array initialization still crosses from executor to builtins through shell
  side-channel state such as `_pending_array_inits`.
- Process-substitution cleanup ownership is improved by `RedirectPlan`, but
  builtin redirection setup still manually transfers some process-substitution
  file descriptors to the process-substitution handler.

Recommended next improvement:

Tackle the executor-to-builtin array-initialization side channel next. It is
smaller than the parser interface question and more concrete than the remaining
process-substitution ownership cleanup. A dedicated command-execution context
object would make the data flow easier to teach and reduce mutable state on the
shell object.

## 5. Lexer Command-Position and Word Recognition

Status: partially satisfied.

The command-position story is now much better documented. The
`psh/lexer/command_position.py` module explains the three related state
machines and why they are not currently unified. The tests in
`tests/unit/lexer/test_command_position_consistency.py` lock down vocabulary
consistency and documented asymmetries.

That is a good teaching improvement: students can now see that the apparent
duplication is partly deliberate and guarded.

Remaining issues:

- Literal collection in `psh/lexer/recognizers/literal.py` still has a large,
  multi-responsibility loop with many syntax-specific exits.
- `psh/lexer/modular_lexer.py` still classifies some `${...}` tokens by
  scanning for operator substrings and relying on downstream tolerance when the
  token kind is imprecise.

Recommended next improvement:

Extract small recognizer helpers around the literal loop before attempting a
larger lexer redesign. The goal should be to make the rules visible as named
operations, not to make tokenization more abstract.

## 6. Student Documentation Curation

Status: satisfied.

The documentation set is now much more navigable.

`docs/learning_path.md` gives students a clear route through the project:
README, examples, architecture, internals, subsystem notes, user guide,
conformance, and testing. `docs/reviews/README.md` separates live findings,
completed work, and historical review artifacts. That makes the reviews useful
without letting them become the de facto tutorial.

This directly addresses the previous concern that the repository had many good
documents but too little guidance about which ones mattered first.

## Additional Observations

### Generated Files Still Clutter the Working Tree

The working tree still contains generated directories and files such as
`__pycache__`, `.ruff_cache`, `.pytest_cache`, and `.DS_Store` under project
subtrees. They appear to be ignored or untracked, but they still make local tree
browsing less clean for students. A teaching repository benefits from a
visible tree that is as intentional as the code.

Recommended action: add a documented cleanup command or ensure the existing
cleanup workflow removes these artifacts consistently.

### Some Conformance Tests Still Look Investigatory

The earlier review noted that some conformance tests compare behavior without
always asserting the result. `tests/conformance/bash/test_bash_compatibility.py`
still contains many `check_behavior(...)` calls, including some whose result is
not asserted directly. That can be valid for exploratory compatibility reports,
but the file should make the distinction explicit.

Recommended action: separate "compatibility probes" from "required behavior
tests", or rename/helper-document the probe style so readers do not mistake
observation for enforcement.

## Prioritized Next Steps

1. Replace the array-initialization side channel with an explicit execution
   context passed from executor to builtins.
2. Continue the lexer simplification by extracting named helpers from literal
   recognition and making parameter-expansion token classification less
   heuristic.
3. Finish process-substitution cleanup ownership by making `RedirectPlan` the
   single place that transfers or closes process-substitution resources.
4. Decide whether parser sub-parsers should have a lightweight protocol or
   abstract base class, then document the decision in code rather than only in
   CLAUDE.md.
5. Keep README statistics approximate unless exact numbers are part of a tested
   release process.
6. Clean generated artifacts from local teaching trees and document the cleanup
   workflow.

## Verification Run

Focused guardrails passed on 2026-06-20:

```text
python -m pytest tests/unit/parser/test_top_level_control_structure_grammar.py \
  tests/integration/test_interactive_child_rc_leak.py \
  tests/unit/tooling/test_examples.py \
  tests/unit/core/test_option_registry.py -q

61 passed in 3.56s
```

```text
python -m pytest tests/unit/tooling/test_user_doc_links.py \
  tests/unit/tooling/test_readme_statistics.py -q

15 passed in 1.65s
```

I did not run the full suite for this reassessment.
