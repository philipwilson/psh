# Parser Feature Gap Analysis: Recursive Descent vs Parser Combinator

## Summary

The two parsers have **near-complete feature parity** for shell grammar coverage. The combinator parser supports all major control structures, command types, redirections, and expansions. However, there are meaningful gaps in **edge-case handling, error reporting, and parser infrastructure features**.

## Syntax/Grammar Gaps

| Feature | Recursive Descent | Combinator | Severity |
|---------|:-:|:-:|----------|
| `&>` combined redirect | N/A (not in lexer) | N/A | Non-issue -- neither parser supports it because the **lexer** doesn't emit a token for `&>`. The parity test marks it as skipped, but it's actually missing from both parsers. |
| Pipeline negation (`! cmd`) | `pipeline.negated = True` | Not implemented | **Real gap** -- `!` prefix on pipelines is not recognized |
| FD-prefixed redirects (`3>file`) | `_is_fd_prefixed_redirect()` / `_parse_fd_prefixed_redirect()` | Not implemented | **Real gap** -- numeric FD prefix without space not detected |
| FD duplication detection (`2>&1` as word) | `_is_fd_duplication()` / `parse_fd_dup_word()` | Not implemented | **Real gap** -- ambiguous redirect/argument distinction not handled |

## Error Handling & Recovery Gaps

| Feature | Recursive Descent | Combinator | Notes |
|---------|:-:|:-:|-------|
| Multi-error collection | `parse_with_error_collection()` | None | RD can collect multiple errors and continue parsing |
| Error recovery | `_try_statement_recovery()`, `_skip_to_sync_token()` | None | RD skips to synchronization points after errors |
| Rich error context | `ErrorContext` with position, suggestions | Simple error strings | RD produces structured, actionable error messages |
| Unclosed expansion detection | `_check_for_unclosed_expansions()` with specific messages for `${`, `$(`, `$((`, backtick | None | RD gives precise diagnostics for each unclosed type |
| Escaped dollar detection | `\$(...)` raises specific error | None | RD detects bash-incompatible escape patterns |

## Parser Infrastructure Gaps

| Feature | Recursive Descent | Combinator | Notes |
|---------|:-:|:-:|-------|
| AST validation pipeline | `parse_and_validate()` with `SemanticAnalyzer`, `ValidationPipeline`, `ValidationRules` | None | Full post-parse validation framework |
| Parser profiling | `trace_parsing`, `profile_parsing` config options | None | Performance instrumentation |
| Scope tracking | `scope_stack`, `loop_depth`, `function_depth`, `conditional_depth` | None | Nesting depth/scope awareness for semantic checks |
| Context state management | `ParserContext` with `__enter__`/`__exit__` for save/restore | Implicit via position passing | RD has explicit state flags (`in_case_pattern`, `in_arithmetic`, etc.) |
| `ParserConfig` integration | 14-field config controlling behavior | `configure(**options)` method exists but minimal | RD has `strict_posix`, `enable_bash_extensions`, etc. |

## Test Coverage Gaps

| Test Category | Recursive Descent | Combinator |
|--------------|:-:|:-:|
| Dedicated unit tests | Full (via integration) | 3,650 lines across 8 files |
| Parity tests | ~640 lines, 1 skip (`&>`) | Same file, same coverage |
| Integration/system tests | All ~4,000 lines | **Zero** -- never exercised |
| Conformance tests | All POSIX/bash tests | **Zero** |
| Performance benchmarks | Baselined | **Zero** |

## Features with Full Parity (no gaps)

- All control structures: `if`/`elif`/`else`, `while`, `until`, `for`, C-style `for`, `case`/`esac`, `select`, `break`/`continue`
- All command types: simple commands, pipelines, subshells, brace groups
- All function definition forms: `name(){}`, `function name{}`, `function name(){}`
- And-or lists (`&&`/`||`)
- All standard redirections: `<`, `>`, `>>`, `2>`, `2>>`, `<<`, `<<-`, `<<<`, `>&`
- All expansion types in Word AST: variable, parameter, command substitution (both forms), arithmetic, process substitution
- Array operations: initialization, element assignment, append
- Heredoc post-processing: full AST traversal
- Background execution (`&`)
- Word AST construction with per-part quote context

## Key Architectural Differences (not gaps)

| Aspect | Recursive Descent | Combinator |
|--------|:-:|:-:|
| State model | Mutable `ParserContext` | Immutable position passing |
| Backtracking | Manual save/restore | Automatic via `or_else`/`try_parse` |
| Circular deps | Direct method calls | `ForwardParser` + wiring phase |
| Debugging | `--debug-ast`, `--debug-tokens` | `explain_parse()` method |
| Performance | Single pass, no backtracking | May re-parse alternatives |

## Actionable Gaps (ordered by impact)

1. **Pipeline negation** (`! pipeline`) -- POSIX required, simple to add
2. **FD-prefixed redirects** (`3>file`, `3>>file`) -- common in real scripts
3. **FD duplication word detection** (`2>&1` as argument vs redirect) -- correctness issue
4. **Multi-error collection** -- useful for IDE integration / linting
5. **Unclosed expansion detection** -- user-facing diagnostics quality

The combinator parser's documentation correctly labels it as "experimental / educational" and notes it "may lag behind on edge-case fixes and new features." The grammar-level coverage is excellent, but the production-quality error handling and edge-case detection in the recursive descent parser is substantially more mature.
