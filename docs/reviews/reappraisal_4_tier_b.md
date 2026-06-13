# Reappraisal #4 — Tier B (post-verification residue)

Date opened: 2026-06-13

> ⚡ **STATUS (2026-06-13) — TIER B COMPLETE.** All seven items shipped as
> v0.329.0–v0.336.0, each green on the local gate and auto-tagged:
> B1 tooling honesty (v0.329) · CI health (v0.330) · B2 strict internal-error
> mode (v0.331) · B3 cmdsub-scanner decomposition (v0.332) · B4 arithmetic
> package (v0.333) · B5 WordExpander segment-IR (v0.334) · B6 single-authority
> state (v0.335) · B7 process failure-path tests (v0.336). Every refactor was
> zero-behavior-change behind a frozen characterization harness (103/150/94/49
> cases) and bash-differential probes. Three behavior follow-ups were
> discovered and recorded (below), plus B2-R2 (expected-error taxonomy). Suite
> at close: 6,241 passed / 6,478 collected; ruff + mypy clean.

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

## Emergent follow-up (from B2, 2026-06-13)

B2's strict-mode diagnostic sweep (`PSH_STRICT_ERRORS=1` over the full
suite) surfaced **~20 legitimate shell-error paths** that currently flow
through the last-resort *internal-defect* guard rather than being
classified as deliberate shell semantics:

- bad / unopened fd, `noclobber` overwrite, and redirect-rollback paths →
  `OSError` (`psh/io_redirect/...`)
- division by zero → `ShellArithmeticError`
- unclosed quote → `UnclosedQuoteError`
- invalid / readonly function name → bare `ValueError` (`psh/executor/core.py`)

None are bugs — in non-strict mode they already produce a clean message +
exit code. But they mean strict mode can't run suite-wide yet (they'd be
false positives). The real fix is an **expected-error taxonomy**: a base
shell-error type for conditions that are normal shell failures, so the
guards re-raise control-flow + handle any expected `PshError` + treat only
*truly* unexpected exceptions as defects. That work (call it **B2-R2**) is
the prerequisite to enabling `strict-errors` in `conftest` globally and
catching internal regressions automatically. Recorded here as a candidate;
not yet scheduled.

> ✅ **RESOLVED — the three behavior follow-ups are FIXED (v0.337–v0.339):**
> (1) assoc arrays in arithmetic → v0.337.0; (2) `$0`-in-function →
> v0.338.0; (3) **B2-R2 expected-error taxonomy → v0.339.0** — expected
> shell errors are classified as `PshError ∪ OSError ∪ SyntaxError`
> (function-name `ValueError`s promoted to `FunctionDefinitionError(PshError)`),
> `report_internal_defect` re-raises only genuine Python-bug exceptions, and
> `strict-errors` is now ENABLED suite-wide via `conftest`
> (`PSH_STRICT_ERRORS=1`) — so a real internal defect fails the suite loudly
> going forward.

## Emergent behavior finding (from B4, 2026-06-13)

While characterizing arithmetic, B4 confirmed (against pristine main, so
NOT a refactor regression) a real psh/bash divergence:
**associative-array elements do not resolve inside `$(( ))`** — `declare -A
m; m[k]=9; echo $(( m[k] * 2 ))` gives `0` in psh vs `18` in bash. Indexed
arrays work (`a[2]*2` → `18`). This is a genuine bug (the arithmetic
evaluator's array-element read path doesn't handle assoc keys), but it's a
BEHAVIOR change, out of scope for the zero-behavior-change refactor.
Candidate for a dedicated behavior release. (Also noted, expected and
already pinned: psh has no `0b` binary literal — `0b101` is octal-0 then
`b`, an error, like the existing `test_0b_is_not_binary` pin.)

## Emergent behavior finding (from B6, 2026-06-13)

Confirmed pre-existing (NOT a refactor regression): **`$0` inside a
function returns the function name in psh, the shell name in bash** —
`f(){ echo "$0"; }; f` → `f` (psh) vs `bash` (bash). The function-aware
`$0` lives in `variable.py`'s `_expand_special_variable` and was preserved
exactly by B6. POSIX/bash keep `$0` as the shell/script name regardless of
function nesting (`${FUNCNAME[0]}` is the function name). Candidate for a
dedicated behavior release alongside the B4 assoc-array-in-arithmetic fix.

## Method (unchanged from the Textbook Program)

Per release: `fix/`/`chore/` branch → subagent implements (no commits,
verify-first, characterization/differential harness BEFORE any deletion,
zero-behavior-change contract with accidents PINNED not smuggled) →
orchestrator spot-probes vs bash 5.2 → 4-file version ritual → commit →
`gh pr create --head` → `gh run watch` chained to merge + annotated tag on
green.
