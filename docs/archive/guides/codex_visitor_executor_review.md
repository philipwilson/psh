# Codex Review: `psh/visitor` and `psh/executor`

Date: 2026-02-09
Fixes applied: v0.146.0–v0.148.0 (see [Fix Status](#fix-status-v0146v0148) below)

## Scope
Primary review target:
- `psh/visitor/*`
- `psh/executor/*`

Context sampled for alignment:
- `psh/ast_nodes.py`
- `psh/shell.py`
- `psh/core/state.py`
- targeted tests under `tests/unit/executor` and `tests/integration/*`

Method:
- static analysis with line-level inspection
- targeted behavior probes via `python -m psh -c ...`

## Scorecard
### Visitor subsystem
| Dimension | Score (/10) | Assessment |
|---|---:|---|
| Correctness | 5.5 | Useful foundation, but some visitors emit duplicate or semantically unsafe output |
| Educational quality | 8.0 | Strong explanatory docstrings and approachable architecture |
| Elegance | 6.0 | Clean conceptual split by concern, but recurring duplication in traversal logic |
| Pythonic style | 5.5 | Overuse of dynamic reflection and broad exception patterns in places |

### Executor subsystem
| Dimension | Score (/10) | Assessment |
|---|---:|---|
| Correctness | 6.0 | Modular and generally coherent, but includes a few high-impact semantic bugs |
| Educational quality | 7.5 | Delegation model is easy to follow and onboard to |
| Elegance | 6.5 | Good module boundaries; some lifecycle/state handling still fragile |
| Pythonic style | 5.5 | Repeated context/redirection patterns and mutable shared state reduce clarity |

## Findings (severity-ordered)

### 1) Critical: background brace groups execute twice and mutate parent state — **FIXED v0.146.0**
- File refs:
  - `psh/executor/subshell.py:96`
  - `psh/executor/subshell.py:99`
  - `psh/executor/subshell.py:102`
- What happens:
  - `execute_brace_group()` runs `visitor.visit(node.statements)` before checking `node.background`.
  - If background is set, it then also runs `_execute_background_brace_group()`, causing a second execution.
- Impact:
  - duplicate side effects/output
  - background semantics violated (`{ ...; } &` leaks parent mutations)
- Repro observed:
  - `{ echo hi; } &` printed twice
  - `{ X=1; } & wait; printf "%s\n" "$X"` left `X=1` in parent
- Recommendation:
  - branch on `node.background` before any foreground execution path.
- **Resolution:** `execute_brace_group()` now checks `node.background` before any execution, matching the pattern used by `execute_subshell()`. Regression test: `TestBraceGroupBackground`.

### 2) High: `loop_depth` leaks on non-local exits in loop executors — **FIXED v0.146.0**
- File refs:
  - `psh/executor/control_flow.py:124`
  - `psh/executor/control_flow.py:153`
  - `psh/executor/control_flow.py:160`
  - `psh/executor/control_flow.py:183`
  - `psh/executor/control_flow.py:200`
  - `psh/executor/control_flow.py:234`
- What happens:
  - `context.loop_depth += 1` is not protected by an outer `finally` in `execute_while`, `execute_until`, `execute_for`.
  - multi-level `break`/`continue` propagation and certain early exits can skip decrement.
- Impact:
  - stale loop context after loops complete
  - downstream `break/continue` handling can become incorrect
- Repro observed:
  - nested `break 2` left `ExecutorVisitor.context.loop_depth == 1`.
- Recommendation:
  - wrap loop body methods with outer `try/finally` that always decrements loop depth.
- **Resolution:** `execute_while()`, `execute_until()`, and `execute_for()` now wrap `loop_depth` increment/decrement in an outer `try/finally`. Regression tests: `TestLoopDepthLeak` (4 tests).

### 3) High: command-prefixed assignments are restored even for POSIX special builtins — **FIXED v0.146.0**
- File refs:
  - `psh/executor/command.py:94`
  - `psh/executor/command.py:177`
  - `psh/executor/strategies.py:39`
- What happens:
  - command-prefixed assignments are always temporary via `_restore_command_assignments()`.
  - POSIX special builtins (`export`, `readonly`, `set`, `unset`, etc.) should apply assignment semantics differently.
- Impact:
  - shell behavior diverges from POSIX/Bash in special-builtin cases.
- Repro observed:
  - `FOO=1 export BAR=2; printf "%s\n" "$FOO"` did not preserve `FOO` as expected.
- Recommendation:
  - detect special-builtin resolution path and skip temporary rollback for that class.
- **Resolution:** `_execute_with_strategy()` now returns `(exit_code, is_special)`. The `finally` block in `execute()` skips `_restore_command_assignments()` when `is_special` is True. Regression tests: `TestSpecialBuiltinAssignmentPersistence` (4 tests).

### 4) High: linter generic traversal duplicates diagnostics — **FIXED v0.148.0**
- File ref:
  - `psh/visitor/linter_visitor.py:408`
- What happens:
  - `generic_visit()` walks `dir(node)` and revisits alias/derived structures.
  - properties like `pipelines` / `and_or_lists` can cause repeated traversal.
- Impact:
  - duplicate lint findings (noise, lower trust).
- Repro observed:
  - script `foo` produced repeated “Command might not be available” entries.
- Recommendation:
  - replace reflective `dir()` walk with explicit traversal or dataclass-field walk only.
- **Resolution:** `generic_visit()` now uses `dataclasses.fields(node)` to iterate only declared dataclass fields, matching `ASTTransformer.transform_children()`. Regression test: `TestLinterGenericVisit`.

### 5) Medium: formatter can change semantics of array parameter expansions — **Not-a-bug (verified v0.148.0)**
- File refs:
  - `psh/visitor/formatter_visitor.py:77`
  - `psh/visitor/formatter_visitor.py:136`
- What happens:
  - reconstructed words may emit `${arr[0]}` as `$arr[0]`.
- Impact:
  - format output can be behavior-changing rather than a pure pretty-print.
- Repro observed:
  - `arr=(a b); echo ${arr[0]}` formatted to `echo $arr[0]`, yielding `a[0]`.
- Recommendation:
  - preserve exact expansion form in AST metadata and emitter.
- **Resolution:** Investigation shows `${arr[0]}` is parsed as `ParameterExpansion(parameter='arr[0]')` whose `__str__()` returns `${arr[0]}` — so `_format_word()` produces correct output. For unbraced `$arr[0]`, the parser produces `VariableExpansion(name='arr')` + `LiteralPart('[0]')`, which correctly formats as `$arr[0]` (matching the input). Regression test: `TestFormatterArraySubscript`.

### 6) Medium: formatter emits invalid/non-portable C-style `for` text — **FIXED v0.148.0**
- File ref:
  - `psh/visitor/formatter_visitor.py:247`
- What happens:
  - emits `for (($init; $cond; $update))` with `$` injection.
- Impact:
  - generated shell text is not valid in Bash for normal arithmetic loop syntax.
- Recommendation:
  - emit `for (({init}; {cond}; {update}))`.
- **Resolution:** Changed f-string from `${init}; ${cond}; ${update}` to `{init}; {cond}; {update}`. Regression test: `TestFormatterCStyleFor`.

### 7) Medium: undefined-variable checks in enhanced validator can under-report — **FIXED v0.148.0**
- File refs:
  - `psh/visitor/enhanced_validator_visitor.py:604`
  - `psh/visitor/enhanced_validator_visitor.py:622`
- What happens:
  - default-operator detection uses context-wide heuristics and fragile positional slicing.
- Impact:
  - mixed expressions can suppress warnings for truly undefined variables.
- Recommendation:
  - evaluate defaults against each matched expansion token span, not the whole argument.
- **Resolution:** `_has_parameter_default()` now scans for `${...}` delimiters and only checks for `:-` / `:=` inside them, with proper brace nesting. Regression tests: `TestEnhancedValidatorParameterDefault` (4 tests).

### 8) Medium (latent): pipeline test-mode fallback builds invalid context object — **FIXED v0.147.0**
- File ref:
  - `psh/executor/pipeline.py:461`
- What happens:
  - exception fallback constructs synthetic `ExecutionContext` without required API.
- Impact:
  - secondary failures possible if fallback path triggers.
- Recommendation:
  - reuse original `context`/`node` in fallback path.
- **Resolution:** Replaced anonymous `type()` objects with a real `Pipeline` AST node and the caller's `context`. Added `context` parameter to `_execute_mixed_pipeline_in_test_mode()`.

### 9) Low: linter mixes command-resolution and function-resolution concerns
- File refs:
  - `psh/visitor/linter_visitor.py:207`
  - `psh/visitor/linter_visitor.py:182`
- What happens:
  - all commands are tracked as potential function calls.
- Impact:
  - “undefined function” warning can be misleading noise.
- Recommendation:
  - separate function-invocation tracking from generic command tracking.

## Educational quality assessment
Strengths:
- The architecture is pedagogically good: `ASTVisitor` base + specialized analyzers is clear.
- Executor decomposition (`command`, `pipeline`, `control_flow`, `subshell`, `function`) is easy to reason about.
- CLAUDE subsystem docs are useful onboarding references.

Gaps:
- Several docs imply stronger POSIX correctness than current behavior supports.
- Visitors are positioned as robust analysis tools but some are still heuristic prototypes (especially linter/security).

Recommendation:
- Label visitors by maturity (`experimental`, `heuristic`, `strict`) and align docs/tests accordingly.

## Structure recommendations
1. Introduce a shared, canonical child-traversal helper in `psh/visitor/base.py`.
- Removes duplicated and inconsistent generic traversal logic across visitors.
- *Partially addressed:* linter now uses `dataclasses.fields()` (v0.148.0), but not yet shared across all visitors.

2. Centralize execution context lifecycle management.
- Add scoped helpers/context managers for loop/pipeline/function state transitions.
- *Partially addressed:* loop_depth lifecycle is now safe via `try/finally` (v0.146.0), but still uses direct mutation rather than scoped context managers.

3. Separate test-mode pipeline emulation from production executor path.
- Keep job-control process code isolated from testing shims.
- *Partially addressed:* fallback path now uses real AST/context objects (v0.147.0), but test-mode code still lives in `pipeline.py`.

4. Unify redirection context manager implementation.
- `_apply_redirections()` is currently repeated across multiple executor modules.

5. ~~Add compatibility contracts for behavior-critical features.~~
- ~~Explicitly test assignment semantics, loop control depth handling, and formatter roundtrip behavior.~~
- **Done v0.146.0–v0.148.0:** 17 regression tests in `tests/regression/test_visitor_executor_review_fixes.py` cover assignment persistence, loop depth, formatter roundtrip, and validator behaviour.

## Pythonic/style recommendations
1. ~~Remove reflective `dir()` traversal for AST walking.~~ **Done v0.148.0** — replaced with `dataclasses.fields()`
2. Avoid broad bare `except:` blocks in runtime paths; catch specific exception classes.
3. Prefer typed dataclasses/enums for issues (`SecurityIssue` currently stringly typed).
4. Reduce cross-module calls to private methods (e.g., expansion internals); expose public APIs.
5. ~~Keep formatter either explicitly lossy (and documented) or semantics-preserving with tests.~~ **Done v0.148.0** — C-style for fixed, array subscript verified correct with test

## Priority fix order
1. ~~Fix background brace-group double execution + state leak.~~ **Done v0.146.0**
2. ~~Fix loop-depth lifecycle leaks (`while`, `until`, `for`).~~ **Done v0.146.0**
3. ~~Correct special-builtin assignment persistence semantics.~~ **Done v0.146.0**
4. ~~Replace linter generic traversal to eliminate duplicate findings.~~ **Done v0.148.0**
5. ~~Harden formatter to preserve expansion semantics.~~ **Done v0.148.0** (C-style for fixed; array subscript verified not-a-bug)

## Test additions recommended now
1. `tests/integration/subshells/test_background_brace_group_no_parent_leak.py`
2. `tests/integration/control_flow/test_loop_depth_restores_on_break_levels.py`
3. `tests/integration/variables/test_special_builtin_prefix_assignment_semantics.py`
4. `tests/unit/visitor/test_linter_does_not_duplicate_issues.py`
5. `tests/unit/visitor/test_formatter_preserves_array_subscript_expansion.py`

---

## Fix Status (v0.146.0–v0.148.0)

| # | Finding | Severity | Status | Version | Notes |
|---|---------|----------|--------|---------|-------|
| 1 | Background brace groups execute twice | Critical | **FIXED** | v0.146.0 | Check `node.background` before any execution |
| 2 | `loop_depth` leaks on non-local exits | High | **FIXED** | v0.146.0 | Wrapped in outer `try/finally` |
| 3 | Special-builtin assignment persistence | High | **FIXED** | v0.146.0 | `_execute_with_strategy()` returns `(exit_code, is_special)` |
| 4 | Linter generic traversal duplicates | High | **FIXED** | v0.148.0 | `dir(node)` → `dataclasses.fields(node)` |
| 5 | Formatter array subscript semantics | Medium | **Not-a-bug** | v0.148.0 | `${arr[0]}` round-trips correctly via `ParameterExpansion.__str__()` |
| 6 | Formatter C-style for `$` injection | Medium | **FIXED** | v0.148.0 | Removed spurious `$` from f-string |
| 7 | Enhanced validator under-reporting | Medium | **FIXED** | v0.148.0 | `_has_parameter_default()` now checks inside `${...}` only |
| 8 | Pipeline test-mode fallback invalid context | Medium | **FIXED** | v0.147.0 | Real `Pipeline` node + real `context` |
| 9 | Linter mixes command/function concerns | Low | Not addressed | — | Deferred (noise, not correctness) |

Regression tests: `tests/regression/test_visitor_executor_review_fixes.py` (17 tests)
