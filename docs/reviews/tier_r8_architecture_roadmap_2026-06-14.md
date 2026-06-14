# Tier R8 — Architecture Roadmap

Date: 2026-06-14 (starting at v0.406.0)

Source: the maintainer's `docs/reviews/fresh_architecture_review_2026-06-14.md`
(inspected at v0.400.0), reconciled with the state after the reappraisal #7
campaign (v0.388 → v0.406). Where the two disagree, this memo reflects the
*current* tree.

This tier is **structural seam work, not bug-fixing and not subsystem
splitting** — exactly the bar the review sets. The R7 bash-fidelity bug list is
complete (only the deferred M8/byte-model remains); R8 targets the architectural
"uglies."

## What the review flagged that is ALREADY DONE (post-v0.406)

- **Ugly 10 / A8 — type coverage (file level): DONE.** The review (at v0.400)
  cited "118 mypy entries for 222 files" with `io_redirect/`, the executor
  files, "much of builtins," and "many visitor modules" outside scope. As of
  **v0.406 mypy covers 100% of `psh/` source files (223 in scope)** — every
  module the review named is now checked. The widening caught real bugs (`: &`
  AttributeError, `Dict[str, any]` typos). The ONLY remaining piece of Ugly 10
  is `check_untyped_defs = false` (depth, not coverage) → tracked as R8.7.
- **Ugly 8 — validator false positives: partially done.** R7.9 fixed the
  array-assignment / C-style-for / `$((…))` false positives in
  `EnhancedValidatorVisitor`. The broader "analyze `Word` parts instead of
  regexing rendered strings" refactor is still open → R8.4.
- **Ugly 9 / A7 — combinator parser contract: mostly affirmed.**
  `psh/parser/CLAUDE.md` already declares the combinator backend educational; it
  is now fully typed (via `ControlStructureProtocol`). Remaining work is a small
  doc/code affirmation + trimming production fallbacks → folded into R8.4/notes.

## R8 backlog (prioritized by value-per-risk)

### R8.1 — Control-flow context helpers (review Ugly 4 / A3) — LOW risk, FIRST
`ControlFlowExecutor` repeats redirect application, `context.in_pipeline`
save/restore, `loop_depth` inc/dec, errexit suppression in conditions, and
`LoopBreak`/`LoopContinue` level translation across while/for/case/if/C-style.
The review notes a latent inconsistency (C-style loops differ in the
`in_pipeline` save/restore shape) — a drift bug a shared helper would prevent.
Extract: `compound_redirection_context(node, context)`,
`pipeline_context_disabled(context)`, `loop_depth(context)`,
`translate_loop_control(exc, context)`. Zero behavior change; characterization
harness over every compound command (redirects applied to the whole body,
pipeline context restored, break/continue levels). **Start here.**

### R8.2 — Redirect primitive boundary (review Ugly 7 / A4) — LOW risk
The builtin stream backend calls `FileRedirector` privates
(`_redirect_input_from_file`, `_redirect_readwrite`, `_redirect_heredoc`,
`_redirect_herestring`, `_check_noclobber`, `_noclobber_blocks`). These are
shared redirect primitives, not implementation details. Promote them to a stable,
narrowly-typed public surface (rename without leading `_`, or extract a small
`redirect_ops` seam) so the stream backend no longer reaches into privates. Keep
the `RedirectPlan`/`apply_fd_plan` fd backend exactly as is. Zero behavior change.

### R8.3 — Command-invocation data flow (review Ugly 2/3 / A1) — MEDIUM risk, HIGH value
The centerpiece. Replace the `(exit_code, is_special)` tuple side-channel and the
`_execute_command` phase-hub with typed data:
- `SimpleCommandPlan` (extraction facts: raw assignments, command words,
  redirects, background, bypass flags, array-init metadata),
- `CommandResolution` (`kind`, `target`, `prefix_assignments_persist`),
- `ExecutionResult` (`status` + optional job/process metadata).
Refactor `_execute_command` into a visible pipeline: plan → expand → apply prefix
→ resolve → invoke → cleanup. Hot path — frozen characterization harness +
`--compare-bash`. Makes POSIX phase-order testable as data and assignment
persistence inspectable rather than a boolean convention. May be split into
sub-steps (introduce the dataclasses first behind the existing flow, then thread
them).

### R8.4 — Visitor analysis over the Word AST (review Ugly 8 / A6) — MEDIUM
Add `visitor/word_analysis.py` helpers over `LiteralPart`/`ExpansionPart`/
`ParameterExpansion`/quote flags; route the enhanced-validator/linter/security
checks through them, removing regex scans over rendered strings (kept only as a
legacy/manual-AST fallback). Aligns tooling with the runtime model; reduces
false positives. Isolated to the visitor stack.

### R8.5 — ShellState decomposition (review Ugly 6 / A5) — MEDIUM, gradual
Do NOT rewrite in one pass. Introduce typed internal sub-objects behind a stable
facade, starting with `StreamState`/`StreamBindings` (replace the dynamic
`_custom_*` stream-override attributes with an explicit snapshot/restore object —
the subtlest, highest-value first target), then `OptionState`,
`ExecutionStatus`, `TerminalState`, `HistoryState`. Each step behind compatibility
properties; zero behavior change per step.

### R8.6 — Resolver/Invoker split + alias at parse time (review Ugly 1/2 / A2) — HIGH risk, FENCED
After R8.3, split strategy responsibilities into `CommandResolver` /
`CommandInvoker` / `ProcessJobRunner`, and move alias expansion to the
lexical/parser boundary (token/word-stream transform), keeping a runtime shim.
**History note:** alias-at-parse-time is the same change deferred across
reappraisals #4 and #5 (as T3.4) — entangled with psh's *deliberate*
non-interactive alias-expansion divergence and an injection-class metacharacter
bug. It needs a serious bash probe battery (whitespace, quotes, redirections,
semicolons, metacharacters in post-alias args) and explicit decisions about the
divergence. Treat as a deliberate big-bang, last.

### R8.7 — `check_untyped_defs` deepening (remaining Ugly 10) — MEDIUM, can be noisy
Turn on `check_untyped_defs` per-package via `[[tool.mypy.overrides]]`, starting
with `core/`, then outward as bodies are cleaned. The file-coverage ratchet is
done; this is the depth ratchet.

### Smaller folded items
- **Ugly 5 — pipeline children mutate `visitor.context`.** Add
  `ExecutorVisitor.with_context()` / construct a child visitor per fork; fold
  into R8.3 (same execution-context cleanup) or do as a small standalone.
- **A7 — combinator parser contract.** Affirm educational-only status in code +
  reduce production fallback branches (e.g. the case-pattern fallback in
  `execute_case`); opportunistic during R8.4.

## Execution protocol (unchanged)
Per item: a branch → subagent (no commits; frozen characterization harness
BEFORE the change; bash-adjudicated where behavior is observable; for
zero-behavior refactors, characterization == golden) → orchestrator full-gate
verify (`run_tests.py --parallel` + `ruff check psh tests` + `mypy` +, where
relevant, `pytest tests/behavioral --compare-bash`) → 4-file version ritual → PR
→ merge → verify auto-tag. Run mypy/refactor agents in the MAIN tree
(foreground) — the worktree-cwd hazard from the R7 mypy parallelization is not
worth re-incurring now that there is no separate bug stream to parallelize
against.

## Bottom line
R8 moves psh from "several textbook subsystems" toward a uniformly textbook
architecture: typed command-invocation data flow (R8.3), alias handling out of
runtime argv reparse (R8.6), extracted compound-command scaffolding (R8.1),
formalized state/redirect boundaries (R8.2/R8.5), and static analysis aligned to
the canonical Word AST (R8.4). Order: R8.1 → R8.2 → R8.3 → R8.4 → R8.5 → R8.7,
with R8.6 as the fenced final big-bang.
