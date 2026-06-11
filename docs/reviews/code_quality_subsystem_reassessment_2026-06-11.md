# PSH Subsystem Code Quality Reassessment

Date: 2026-06-11

Scope: current committed tree under `psh/`, with targeted inspection and targeted tests. This reassessment ignores prior review text as evidence and reviews the current code directly, but it does compare the current state against the previously identified risk areas.

## Executive Summary

The current code is materially better than the prior assessment. Several high-value improvements are visible in the implementation, not just in tests:

- Process substitution is now represented structurally as `ProcessSubstitution(Expansion)` and can appear as an `ExpansionPart` inside a `Word`.
- Embedded process substitution such as `pre<(cmd)post` now uses the normal word expansion path instead of a whole-argument pre-pass.
- Array initializers now carry `Word` AST nodes and route normal elements through `ExpansionManager.expand_word_to_fields()`.
- `ExpansionManager.expand_expansion()` no longer swallows broad internal exceptions and returns `str(expansion)`.
- `ProcessLauncher` now restores the parent signal mask in a `finally` even if `fork()` fails.
- Interactive signal handlers are installed only when entering the interactive loop and restored on exit.

Those are real architectural moves toward a more textbook implementation. The project is now closer to a **B+ teaching shell / B- architecture** than the prior **B / C+** assessment.

It is still not textbook quality. The remaining quality problem has narrowed: old compatibility paths and partial grammar state machines still sit alongside the newer structural paths. The highest-risk areas are nested builtin redirection state, word-splitting suppression outside true assignment contexts, legacy loop expansion, array element assignment values, parser/lexer grammar drift, and visitor coverage.

## Updated Rating

Approximate grade: **B+ for a working teaching shell, B- as architecture**.

The direction is good. The codebase now has more canonical structural mechanisms, but it has not yet deleted enough legacy string-based behavior to make the invariants simple.

## What Improved

### Process Substitution

`ProcessSubstitution` is now an `Expansion` node in `psh/ast_nodes.py`, with comments explicitly supporting embedded use inside `Word`.

`ExpansionManager._expand_word()` handles `ProcessSubstitution` parts directly by creating a `/dev/fd/N` path through `IOManager.create_process_substitution_for_expansion()`. This removes the older whole-argument detection limitation and is backed by `tests/integration/redirection/test_process_sub_embedded.py`.

Quality impact: strong improvement. This is the kind of structural fix the prior report recommended.

Remaining concerns:

- Process substitution still forks through `psh/io_redirect/process_sub.py` rather than a shared fork runner, though it now uses `apply_child_signal_policy()`.
- One embedded write-side test is not portable on macOS: both PSH and bash report `Operation not permitted` for the `/.>/dev/fd` shape used by the test, leaving the output file empty.

### Array Initializers

`ArrayInitialization` now carries parallel `words: List[Word]` metadata. The recursive descent and combinator parsers populate those words for initializer elements. `ArrayOperationExecutor.execute_array_initialization()` now expands normal initializer elements through `ExpansionManager.expand_word_to_fields()`.

Quality impact: strong improvement. Quoted globs, IFS splitting, nullglob/dotglob/noglob, `$@`, command substitution, tilde expansion, and composite words now share the core word expansion machinery.

Remaining concerns:

- Explicit initializer elements of the form `[index]=value` still use `_parse_explicit_array_assignment()` and string expansion.
- `ArrayElementAssignment` still has no `Word` field for values and uses `expand_string_variables()`, so scalar array element assignment remains on the legacy path.
- Legacy fallback code in `ArrayOperationExecutor._add_expanded_element_to_array()` remains reachable when `node.words` is absent.

### Expansion Error Handling

`ExpansionManager.expand_expansion()` now delegates to `ExpansionEvaluator.evaluate()` without catching `ValueError`, `AttributeError`, or `TypeError`. Regression tests in `tests/unit/expansion/test_expansion_error_propagation.py` confirm internal errors propagate.

Quality impact: strong improvement. Internal defects no longer silently turn into literal output.

### Process Launching And Signals

`ProcessLauncher.launch()` now restores the parent signal mask in a `finally`. `apply_child_signal_policy()` centralizes child-side signal setup and is used by additional fork paths.

Quality impact: good improvement. The remaining issue is centralization, not the specific mask restoration bug.

### Interactive Signal Lifecycle

`InteractiveManager.run_interactive_loop()` now installs signal handlers only when the interactive loop starts and restores them in a `finally`.

Quality impact: good improvement. Lifecycle ownership still remains split between REPL EOF handling, the `exit` builtin, and the manager.

## Current Findings

### 1. Nested Builtin Redirections Can Restore The Wrong State

Severity: High

`IOManager.setup_builtin_redirections()` still stores opened stream state on the shared manager (`_opened_streams`). Nested builtin/eval redirections can interfere with an outer redirection frame.

Observed repro:

```sh
python -m psh -c 'f=$(mktemp); exec 3>"$f"; eval "echo one >&3; echo two >&3" 3>&1; printf "FILE:<%s>\n" "$(cat "$f")"; rm "$f"'
```

PSH output:

```text
one
FILE:<two>
```

Bash output:

```text
one
two
FILE:<>
```

Recommendation: make builtin redirection setup return a per-invocation frame object that owns saved fds and opened streams. Restore exactly that frame by identity; do not restore from manager-global mutable state.

### 2. Assignment-Like Arguments Suppress Word Splitting Too Broadly

Severity: High

`ExpansionManager._expand_word()` suppresses word splitting whenever the first literal part contains `=`, even after the command name. That preserves declaration-style arguments, but it is wrong for ordinary command arguments.

Example:

```sh
x="a b"; printf "<%s>\n" foo=$x
```

Bash prints two fields: `<foo=a>` and `<b>`. PSH currently keeps `<foo=a b>`.

Recommendation: remove generic assignment-looking suppression from normal command-argument expansion. Command-prefix assignments are already stripped before argument expansion. Declaration builtins such as `declare`, `export`, `local`, and `readonly` should opt into an explicit assignment-argument expansion policy.

### 3. Legacy Loop Expansion Ignores Current IFS

Severity: Medium

`ControlFlowExecutor` still has a legacy expansion path for `for`/`select` item expansion. In particular, command substitution results are split with Python whitespace splitting instead of shell `IFS`.

Example:

```sh
IFS=:; for i in $(printf a:b); do printf "<%s>\n" "$i"; done
```

Bash splits into `a` and `b`; PSH keeps `a:b` as one item.

Recommendation: represent loop words as `Word` nodes and route them through `ExpansionManager.expand_word_to_fields()` or a context-specific field API.

### 4. Array Element Assignment Values Remain String-Based

Severity: Medium

Array initializers improved, but `ArrayElementAssignment.value` is still a string with quote metadata rather than a `Word`. `ArrayOperationExecutor.execute_array_element_assignment()` expands with `expand_string_variables()` and manually strips outer quotes.

Recommendation: add `value_word: Optional[Word]` to `ArrayElementAssignment`, populate it in both parsers, and expand scalar array assignments through an assignment-value expansion policy.

### 5. Lexer Accepts Unterminated Quotes In Bracket-Looking Words

Severity: Medium

The lexer suppresses quote/expansion parsing in broad `NAME[` contexts, and the literal recognizer treats quotes as literal while its bracket tracker is inside a bracket. This allows inputs like:

```sh
echo x["unterminated
echo arr["x$USER]
```

to parse as normal words, while bash rejects them.

Recommendation: suppress quote parsing only for confirmed array-assignment forms, not every unmatched `NAME[` shape. Add regression tests for unterminated quotes in bracket/glob-looking words.

### 6. `case` Expression Parsing Is Too Permissive

Severity: Medium

The recursive descent parser accepts multiple word-like tokens before `in` and joins them into one case expression. Bash rejects `case a b in ...`.

Recommendation: parse exactly one shell word/composite for the case expression, then require `in`. If another word appears before `in`, raise a targeted syntax error.

### 7. Parser-Combinator Implementation Still Weakens The Quality Contract

Severity: Medium

The combinator parser remains publicly selectable while its own docstring says it is experimental and may lag. Some parity tests assert only non-`None` ASTs rather than normalized structural equivalence.

Recommendation: either explicitly exclude the combinator parser from the “textbook quality” bar and hide it from normal user-facing selection, or define its supported grammar subset and enforce normalized AST parity.

### 8. Visitor Coverage Is Incomplete

Severity: Medium

The formatter still falls back for supported AST nodes:

```sh
python -m psh --format -c 'until false; do echo hi; done'
```

prints:

```text
# Unknown node: UntilLoop
```

The security visitor also misses redirect-bearing compound commands:

```sh
python -m psh --security -c 'while true; do :; done >/etc/passwd'
```

prints:

```text
No security issues found!
```

Recommendation: add a coverage matrix test across every AST node type and every `redirects` field. Visitors should fail tests when a real node reaches an unknown fallback.

### 9. `TokenTransformer` Looks Like Dead Validation Code

Severity: Low

`psh/lexer/token_transformer.py` appears to validate `;;`, `;&`, and `;;&`, but the branches append the original token. This layer is misleading if it does not enforce anything.

Recommendation: remove it, or move real case-terminator validation into parser code with tests.

### 10. Shell Lifecycle And Service Ownership Are Still Broad

Severity: Low

`Shell` still constructs and wires state, parent inheritance, managers, parser mode, traps, process launcher, interactive mode, rc loading, and compatibility attribute delegation. This is manageable but not textbook clean.

Recommendation: split initialization into explicit lifecycle phases or a small `ShellServices` container, and gradually remove magic `ShellState` attribute forwarding.

## Subsystem Snapshot

| Subsystem | Current Quality | Direction | Notes |
| --- | --- | --- | --- |
| Lexer | Good but still heuristic | Slightly better | Recognizer shape is good; bracket quote handling and context split remain. |
| Parser | Good recursive descent, ambiguous dual parser | Mixed | Array initializer Word support improved; case grammar and combinator contract remain. |
| AST / Word Model | Stronger | Better | Process substitution and array initializer words are real progress. |
| Expansion | Stronger but still central | Better | Canonical path improved; assignment-like suppression and loop drift remain. |
| Executor | Capable, still broad | Slightly better | Child signal policy and process launcher improved; command executor still catches broad defects. |
| I/O Redirection | Thoughtful but has nested-frame bug | Mixed | Conceptual design is strong; manager-global state is a correctness risk. |
| Interactive | Better lifecycle cleanup | Better | Signal cleanup improved; shutdown ownership still split. |
| Builtins | Broad and pragmatic | Similar | Large builtins and global singleton registry remain. |
| Core State | Useful but leaky | Similar | `os.environ` mutation remains. |
| Visitor / Analysis | Useful but incomplete | Similar | New AST shapes and compound redirects need coverage. |
| Tests | Stronger targeted coverage | Better | New tests pin important fixes; one macOS-portability issue found. |

## Validation Performed

Targeted tests:

```sh
python -m pytest tests/integration/arrays/test_array_init_word_expansion.py tests/integration/redirection/test_process_sub_embedded.py tests/unit/expansion/test_expansion_error_propagation.py
```

Result: **87 passed, 1 failed**.

The failure was `test_affixed_write_side_is_live`. Manual comparison showed bash also fails the same `/.>/dev/fd` operation on this macOS environment with `Operation not permitted`, so this appears to be a portability problem in the test expectation rather than a PSH-specific semantic regression.

Additional smoke checks:

```sh
python -m psh -c 'echo pre<(echo hi)post; x="a:b"; IFS=:; a=($x); printf "<%s>\n" "${a[@]}"'
```

Output confirmed embedded process substitution and array IFS splitting:

```text
pre/dev/fd/3post
<a>
<b>
```

Known remaining command-substitution grammar issue:

```sh
python -m psh -c 'echo $(case x in x) echo inner;; esac)'
```

still fails with a parse error at `;;`.

Verified nested builtin redirection bug, formatter `UntilLoop` fallback, and security visitor compound-redirection miss with the commands shown above.

One explorer also ran:

```sh
python -m pytest tests/unit/lexer/test_modular_lexer_integration.py tests/unit/lexer/test_keyword_normalizer.py tests/regression/test_parser_review_fixes.py tests/regression/test_codex_review_findings.py tests/test_parser_parity_basic.py -q
```

Result: **83 passed**.

## Revised Roadmap

### Phase 1: Close Remaining Semantic Drift

- Fix nested builtin redirection frames.
- Fix assignment-like ordinary argument word splitting.
- Route `for`/`select` expansion through the canonical Word field API.
- Add `Word` support to `ArrayElementAssignment` values.
- Add regression tests for the four issues above.

### Phase 2: Tighten Grammar Boundaries

- Fix unterminated quotes in bracket-looking words.
- Restrict `case` expression parsing to one shell word before `in`.
- Revisit command substitution scanning so `case` bodies inside `$()` are grammar-aware.
- Remove or implement `TokenTransformer`.

### Phase 3: Make Tooling Total Over The AST

- Add visitor coverage tests for every AST node class.
- Add redirect-field coverage tests for visitors, especially security and formatter.
- Replace unknown-node formatting for real AST nodes with test failures.

### Phase 4: Simplify Architecture

- Define whether the combinator parser is educational-only or production-supported.
- Split command execution into assignment planning, expansion context, resolution, invocation, and error policy.
- Consolidate fork paths behind a shared fork runner where practical.
- Split `Shell` construction into lifecycle phases and reduce compatibility forwarding.

## Final Judgment

The project has moved in the right direction. The current code is no longer just accumulating patches; some fixes deliberately move behavior onto structural AST and expansion paths. That is the right way to improve a shell implementation.

It is still not textbook quality because important semantics are not yet single-sourced. The biggest remaining task is deleting compatibility paths after migrating their callers to `Word` and explicit expansion policies. If that happens, PSH can plausibly become a high-quality reference implementation for a Python teaching shell.
