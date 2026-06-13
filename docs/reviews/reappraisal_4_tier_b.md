# Reappraisal #4 — Tier B (post-verification residue)

Date opened: 2026-06-13

This tier is the **verified** residue of the independent code-quality
assessment in `code_quality_assessment_2026-06-13.md`. That assessment was
written deliberately blind to project conventions, so several of its
headline recommendations were already shipped or overstated. Each surviving
item below was re-checked against the live tree before being queued:

Discarded after verification (already done / not real):
- "Add a production-only lint target `ruff check psh tests`" — already the
  mandated gate (CLAUDE.md), already clean.
- "Gate or remove the combinator parser" — done in v0.309 (docstring +
  `--help` both say *educational*).
- "Remove runtime debug prints in io_redirect" — already gated behind
  `debug-exec`.
- "Two quick-suite failures → redirection cleanup is broken" — both pass in
  isolation; `tee: /dev/fd/4: Operation not permitted` is a macOS sandbox
  quirk, the fd-dup one is test-ordering pollution.

## The tier (sequenced by risk)

| ID | Title | Shape |
|----|-------|-------|
| B1 | Tooling honesty | Make bare `ruff check .` pass (exclude `docs/archive`, fix root `conftest.py`); keep `ruff check psh tests` as the production gate. File the assessment into `docs/reviews/`. |
| B2 | Strict internal-error test mode | Opt-in mode so unexpected *implementation* exceptions re-raise in tests instead of collapsing to shell exit status 1. |
| B3 | Decompose `find_command_substitution_end` | ~340-line scanner in `cmdsub_scanner.py` → explicit state helpers, behind a characterization harness. |
| B4 | Decompose `arithmetic.py` | 1,155-line tokenizer/parser/evaluator → focused modules, behind a characterization harness. |
| B5 | WordExpander segment-IR | Introduce an explicit `ExpandedSegment(text, quoted, splittable, glob_eligible)` and run expansion / splitting / globbing / quote-removal as visibly separate passes. The big architectural one. |
| B6 | Single-authority state | Collapse `ExecutionContext`/`ShellState` forked-child flag duplication; centralize special-variable lookup. |
| B7 | ProcessLauncher failure-path tests | fork failure, redirect failure, signal interruption, stopped jobs, process-sub cleanup. |

## Method (unchanged from the Textbook Program)

Per release: `fix/`/`chore/` branch → subagent implements (no commits,
verify-first, characterization/differential harness BEFORE any deletion,
zero-behavior-change contract with accidents PINNED not smuggled) →
orchestrator spot-probes vs bash 5.2 → 4-file version ritual → commit →
`gh pr create --head` → `gh run watch` chained to merge + annotated tag on
green.
