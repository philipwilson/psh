# Parser Combinator Diagnostic Characterization - 2026-06-14

Scope: recursive-descent parser vs parser-combinator implementation on the
starter and expanded rejection corpus in `tests/parser_differential`.

## Current Gates

- `test_combinator_error_parity.py`: both parsers reject the same invalid
  inputs.
- `test_combinator_diagnostic_parity.py`: a stable low-risk subset also matches
  exception type, EOF signal, offending token identity, and source position.

## Aligned Diagnostic Subset

The combinator parser now reports the same broad diagnostic shape for:

- Empty groups: `()`, `( )`, `{ }`
- Unterminated groups: `(`, `{ echo hi`
- Unterminated conditionals and loops: `if ...`, `while ...`, `for ...`,
  `case ...`, C-style `for ((...`
- Malformed compound headers: missing `then` before `fi`, extra case subject
  word in `case a b in ...`
- Unterminated array initializer: `a=(1 2`
- Unterminated function bodies and missing function names
- Unterminated / malformed enhanced tests: `[[ -n $x`, `[[ $x == ]]`
- Missing redirect targets: `echo >`, `cat <`
- Missing here-doc / here-string operands: `cat <<`, `cat <<<`
- Missing command around binary command operators: `echo |`, `echo |&`,
  `echo &&`, `echo ||`, `&& echo`, `|| echo`
- Nested missing terminators: nested `if`, `while`, and `case` examples
- Empty compound bodies: `if true; then; fi`, loop `do; done` forms (empty
  then/do bodies are syntax errors in bash, including their newline variants)
- Stray separator after `case ... in`: `case x in ; esac` (the `;` is the
  offending token).  Note the accept/reject boundary: an *empty case* with no
  patterns — `case x in esac`, including blank/comment-only lines before
  `esac` — is valid bash and is accepted by both parsers; only the stray `;`
  is rejected.  This accept side is pinned by `ACCEPTANCE_CORPUS` in
  `test_combinator_error_parity.py`.
- Separator edge cases: command operators before/after `;`
- Missing redirect targets after compound commands and groups
- Crossed `if`/loop terminators in loop, if, and function bodies

The diagnostic-parity test intentionally does not compare message text yet.
Both parsers now report source-character position, line, and column for this
stable subset.

## Remaining Diagnostic Drift

No diagnostic-summary drift remains in the pinned rejection corpus.  The stable
gate now matches recursive descent on exception type, EOF signal, offending
token identity, and source position for every representative case in
`test_combinator_error_parity.py`.

Known characterized but unpinned follow-ups:

- Malformed case item bodies with missing nested `if`/loop terminators still
  disagree on line/column metadata for case terminators (`;;`), even when the
  offending token value and source offset match.
- Missing `esac` inside `if`/loop bodies still disagrees on EOF vs the crossed
  outer terminator.

## Recommended Next Tightening

1. Tighten case-item terminator diagnostics so `;;` metadata and missing
   nested terminators align with recursive descent.
2. Continue broadening diagnostics around malformed case item bodies.
3. Consider comparing selected message text once position and token identity
   have stayed stable across a larger corpus.
