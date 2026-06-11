# PSH Expander Implementation Review (2026-02-09)

> **Update (v0.145.0):** Findings 2–5 and 8–10 have been addressed.
> Finding 1 was investigated but retained with documented rationale.
> Findings 6–7 remain open.  See per-finding status annotations below.

## Scope
Review target: `psh/expansion` with parser/executor context from `psh/parser/*` and `psh/executor/*`.

Inspected modules:
- `psh/expansion/manager.py`
- `psh/expansion/variable.py`
- `psh/expansion/parameter_expansion.py`
- `psh/expansion/command_sub.py`
- `psh/expansion/glob.py`
- `psh/expansion/extglob.py`
- `psh/expansion/word_splitter.py`
- Parser/executor integration points in `psh/parser/recursive_descent/support/word_builder.py`, `psh/parser/combinators/expansions.py`, and `psh/executor/command.py`

Validation run:
- `pytest -q tests/unit/expansion` (554 passed, 17 skipped, 7 xfailed)
- `pytest -q tests/integration/parsing/test_word_splitting.py` (33 passed)
- `pytest -q tests/integration/parsing/test_quoting_escaping.py` (53 passed, 1 xpassed)
- `pytest -q tests/integration/parameter_expansion/test_parameter_expansion_comprehensive.py` (46 passed, 1 xfailed)

## Scores
- Correctness: **6.2/10**
- Educational quality: **7.4/10**
- Elegance: **5.6/10**
- Pythonic style: **5.1/10**

Rationale:
- Correctness is solid for covered paths, but several high-severity edge cases still diverge from bash behavior.
- Educational quality is decent due comments/docstrings, but some comments are stale or misleading.
- Elegance and pythonic style are limited by duplicated parsing logic, large branching methods, and broad exception handling.

## Findings (Ordered by Severity)

### High

1. **Field splitting is suppressed for any word containing `=` in first literal part, even when not an assignment word** — **RETAINED (v0.144.0)**
- Code: `psh/expansion/manager.py:231`, `psh/expansion/manager.py:235`
- Context: `CommandExecutor` already isolates true prefix assignments before expansion (`psh/executor/command.py:77`, `psh/executor/command.py:113`).
- Impact: regular arguments like `a=$x` are treated as assignment-like and skip required word splitting.
- Repro:
  - bash: `x="1 2"; printf '<%s>\n' a=$x` -> `<a=1>` `<2>`
  - psh: same command -> `<a=1 2>`
- **Status:** Investigated in v0.144.0.  The heuristic was initially removed per this recommendation, but this broke `declare VAR=$(echo 'substituted value')` — builtins like `declare`, `export`, and `local` receive their `VAR=value` arguments through `expand_arguments()`, not through the executor's assignment extraction path.  The heuristic was restored with an updated comment documenting why it is needed.  A proper fix would require passing an `is_assignment` flag from the executor, but that is a larger change affecting the builtin calling convention.

2. **Multiple `"$@"` expansions in one quoted word are handled incorrectly** — **FIXED (v0.145.0)**
- Code: `psh/expansion/manager.py:173`, `psh/expansion/manager.py:282`
- Root cause: algorithm returns at first `"$@"`, collapsing subsequent `"$@"` into suffix text instead of preserving argument-boundary semantics.
- Repro:
  - bash: `set -- 1 2; printf '<%s>\n' "a$@b$@c"` -> `<a1>` `<2b1>` `<2c>`
  - psh: same command -> `<a1>` `<2b1 2c>`
- **Fix:** Rewrote `_expand_at_with_affixes()` to continue processing remaining parts after each `$@` instead of returning immediately.  Regression test added.

3. **Command-substitution scanning in string expansion is quote-unaware** — **FIXED (v0.145.0)**
- Code: `psh/expansion/variable.py:669`, `psh/expansion/variable.py:674`
- Impact: `)` inside quotes in `$(...)` is misinterpreted as delimiter, truncating the substitution.
- Repro:
  - bash script: `printf '<%s>\n' "${x:-$(printf 'a)b')}"` -> `<a)b>`
  - psh script: emits unclosed-quote error and wrong output (`<b')>`).
- **Fix:** Replaced hand-written scanners in `expand_string_variables()` with `find_balanced_parentheses(track_quotes=True)`, `find_balanced_double_parentheses(track_quotes=True)`, and `find_closing_delimiter(track_quotes=True)` from `psh/lexer/pure_helpers.py`.

4. **Arithmetic pre-expansion reuses the same quote-unaware delimiter scan** — **FIXED (v0.145.0)**
- Code: `psh/expansion/manager.py:615`, `psh/expansion/manager.py:586`
- Impact: arithmetic expressions containing command substitutions with quoted `)` break before arithmetic evaluation.
- Repro:
  - bash: `echo $(( $(echo ')' >/dev/null; echo 2) + 1 ))` -> `3`
  - psh: `psh: ): command not found`
- **Fix:** Replaced scanners in `_expand_command_subs_in_arithmetic()` with the same `pure_helpers` functions.

### Medium

5. **`process_escapes` API contract is not honored** — **FIXED (v0.142.0)**
- Code: signature at `psh/expansion/variable.py:633`.
- Call sites rely on this flag (`psh/executor/array.py:133`, `psh/executor/array.py:179`, `psh/executor/array.py:229`, `psh/executor/array.py:272`, `psh/executor/array.py:273`).
- Impact: callers cannot reliably opt out of escape processing; behavior can silently drift in array handling.
- **Fix:** Removed the dead `process_escapes` parameter from `expand_string_variables()` in both `variable.py` and `manager.py`, and removed `process_escapes=False` from all 5 callers in `executor/array.py`.

6. **Unexpected expansion-evaluation failures are silently downgraded to literal output**
- Code: `psh/expansion/manager.py:465`
- Impact: internal evaluator errors become user-visible wrong output instead of deterministic failure, making bugs harder to detect.

7. **Process-substitution AST contract is inconsistent between parser paths**
- Combinator parser produces `ExpansionPart(ProcessSubstitution)` (`psh/parser/combinators/expansions.py:180`).
- Expansion manager only pre-detects literal `<(`/`>(` words (`psh/expansion/manager.py:438`) and evaluator does not support `ProcessSubstitution` (`psh/expansion/evaluator.py:49`).
- Impact: if combinator parser path is used, process substitution behavior can silently degrade.

### Low

8. **Large method complexity and broad catches reduce maintainability** — **FIXED (v0.142.0, v0.143.0)**
- `expand_variable()` is very large and multi-responsibility (`psh/expansion/variable.py:20` onward).
- Bare catches: `psh/expansion/variable.py:72`, `psh/expansion/variable.py:87`, `psh/expansion/variable.py:192`, `psh/expansion/variable.py:209`, `psh/expansion/variable.py:494`, `psh/expansion/tilde.py:29`.
- Effect: hard to reason about correctness and hard to test behavior boundaries.
- **Fix:** All 6 bare `except:` handlers replaced with specific types in v0.142.0.  `expand_variable()` decomposed into 5 focused helpers in v0.143.0 (`_expand_array_length`, `_expand_array_indices`, `_expand_array_slice`, `_expand_array_subscript`, `_expand_special_variable`), reducing the dispatcher to ~80 lines.

9. **Dead private API indicates drift** — **FIXED (v0.142.0)**
- `_split_words()` appears unused (`psh/expansion/manager.py:471`).
- **Fix:** Deleted.

10. **Some comments are misleading/stale** — **FIXED (v0.142.0)**
- Example: "Block SIGCHLD" comment while code resets handler (`psh/expansion/command_sub.py:34`).
- **Fix:** Changed to "Reset SIGCHLD to default".

## Structural and Style Recommendations

1. **Make assignment-word handling explicit in expansion API** — **INVESTIGATED, DEFERRED**
- Pass expansion context from executor (`is_prefix_assignment_word`) instead of inferring from `'='` inside `Word` text.
- Remove heuristic at `psh/expansion/manager.py:231`.
- **Status (v0.144.0):** Attempted removal broke `declare VAR=$(...)` because builtins receive assignment arguments through `expand_arguments()`.  Heuristic retained with updated comment documenting the rationale.  A proper fix requires changes to the builtin calling convention.

2. **Introduce one shared balanced-scanner utility for `$(`, `$((`, `${`** — **DONE (v0.145.0)**
- Scanner should track quotes, escapes, and nesting.
- Reuse in:
  - `psh/expansion/variable.py` string expansion
  - `psh/expansion/manager.py` arithmetic pre-expansion
- This removes duplicated and currently inconsistent delimiter logic.
- **Fix:** All 5 scanners replaced with `find_balanced_parentheses()`, `find_balanced_double_parentheses()`, and `find_closing_delimiter()` from `psh/lexer/pure_helpers.py`, all called with `track_quotes=True`.  Added `track_quotes` parameter to `find_balanced_double_parentheses()`.

3. **Unify parameter-expansion parsing authority** — OPEN
- Today, parsing exists in both `ParameterExpansion.parse_expansion()` and `WordBuilder._parse_parameter_expansion()`.
- Consolidate to one parser to avoid semantic drift.

4. **Split `VariableExpander.expand_variable()` into focused handlers** — **DONE (v0.143.0)**
- Decomposed into 5 helpers: `_expand_array_length()`, `_expand_array_indices()`, `_expand_array_slice()`, `_expand_array_subscript()`, `_expand_special_variable()`.
- `expand_variable()` is now an ~80-line dispatcher.

5. **Tighten exception policy** — **DONE (v0.142.0)**
- All 6 bare `except:` handlers replaced with specific types: 5× `(ValueError, TypeError)` in `variable.py`, 1× `(KeyError, OSError)` in `tilde.py`.
- Remaining operator-detection heuristic in `expand_parameter_direct()` also replaced with unconditional `evaluate_arithmetic()`.

6. **Align parser variants on identical Word/Expansion contracts** — OPEN
- Decide whether process substitution is a dedicated `WordPart` type or always literal pre-pass token.
- Enforce same contract in recursive-descent and combinator parsers.

7. **Add regression coverage for uncovered high-risk edge cases** — **DONE (v0.142.0–v0.145.0)**
- 10 regression tests added in `tests/regression/test_expansion_review_fixes.py`:
  - 4 tests for `${var:=default}` and `${var:?msg}` parsing
  - 4 tests for multiple `"$@"` in one word
  - 2 tests for quote-aware scanners (quoted `)` in `$(...)`, braces in `${var:-...}`)

8. **Clean up interface drift and stale comments** — **DONE (v0.142.0)**
- Removed dead `process_escapes` parameter and updated all callers.
- Deleted unused `_split_words()` and `GlobExpander.should_expand()`.
- Fixed stale "Block SIGCHLD" comment.

## Remaining Open Items

| # | Finding/Recommendation | Status |
|---|----------------------|--------|
| 1 | Assignment-word heuristic | Retained with rationale; proper fix requires builtin calling convention changes |
| 3 | Unify parameter-expansion parsing authority | Open |
| 6 | Align parser variants on ProcessSubstitution contracts | Open |
| 6 (finding) | Silent failure degradation in `_expand_expansion` | Open |
| 7 (finding) | ProcessSubstitution not handled by evaluator | Open |

## Positive Notes
- Expansion subsystem has clear modular boundaries (`manager`, `variable`, `glob`, `tilde`, `command_sub`).
- Test coverage is broad and catches many historical regressions.
- Word-AST based expansion (per-part quote context) is a good architectural direction and substantially better than opaque string-only expansion.
