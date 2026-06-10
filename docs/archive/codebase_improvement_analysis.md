# PSH Codebase Improvement Analysis

Date: 2026-02-09

## Current Snapshot

- Correctness baseline is strong: `python run_tests.py --quick` passed end-to-end (`2967 passed, 319 skipped, 29 xfailed, 1 xpassed`), plus subshell follow-up phases passing.
- Known debt is concentrated, not random: xfails cluster in interactive/history/completion areas and a smaller set of alias/subshell/pipeline edge cases.
- There are 5 explicit TODOs in active code paths:
  - `psh/builtins/environment.py:46`
  - `psh/builtins/job_control.py:31`
  - `psh/builtins/function_support.py:492`
  - `psh/builtins/type_builtin.py:90`
  - `psh/parser/recursive_descent/support/word_builder.py:288`
- Readability and style hygiene debt is non-trivial: `ruff check psh --statistics` reports 629 issues, mostly whitespace (`W293=598`), plus import/unused/escape issues.
- Architectural duplication remains in redirection and orchestration:
  - `psh/io_redirect/manager.py:55` and `psh/io_redirect/file_redirect.py:13`
  - `psh/shell.py:433` large mixed-responsibility flow
- Tooling/docs drift exists:
  - Migration-era references to legacy paths were present across CI and docs.
  - Some historical planning documents may still require path and status normalization.

## Prioritized Improvement Plan

### 1. Stabilize Source of Truth (Week 1)

- Align CI to current repository layout.
- Define one canonical local/CI test command set.
- Update or prune stale docs referencing non-existent paths.

Success target: green CI on real paths and one current status document.

### 2. Close High-Value Correctness Gaps (Weeks 2-3)

- Implement the 5 live TODOs listed above.
- Convert the current XPASS to a normal passing test.
- Reduce highest-impact xfails first (interactive/history and alias/subshell edge behavior).

Success target: meaningful xfail reduction with regression protection.

### 3. Refactor for Educational Clarity (Weeks 3-5)

- Split `Shell._execute_buffered_command` into parse, visitor-mode, and execute stages.
- Remove duplicated visitor-mode flows.
- Unify builtin/external redirection behavior through one engine.

Success target: smaller orchestration methods and fewer divergent execution paths.

### 4. Clarify Design-Pattern Boundaries (Week 5)

- Keep Visitor and Strategy patterns, but explicitly document extension points and invariants per subsystem.

Success target: contributors can add features without tracing unrelated modules.

### 5. Incremental Quality Gates (Ongoing)

- Enforce Ruff in stages:
  - First: import/unused issues (`I`, `F`).
  - Then: whitespace cleanup (`W293`, `W291`) in controlled batches.
- Add pre-commit checks.
- Add differential/property-style tests for expansion and quoting edge cases against bash.

Success target: sustained correctness and readability without disruptive cleanup churn.

## Practical Next Move

- Start with Phase 1 (CI and docs-truth alignment), then proceed to TODO-backed correctness items before broader refactors.
