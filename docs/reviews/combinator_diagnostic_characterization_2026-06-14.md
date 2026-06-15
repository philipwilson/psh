# Parser Combinator Diagnostic Characterization - 2026-06-14

Scope: recursive-descent parser vs parser-combinator implementation on the
starter rejection corpus in `tests/parser_differential`.

## Current Gates

- `test_combinator_error_parity.py`: both parsers reject the same invalid
  inputs.
- `test_combinator_diagnostic_parity.py`: a stable low-risk subset also matches
  exception type, EOF signal, and offending token identity.

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
- Missing left-hand command before `&&`: `&& echo`

The diagnostic-parity test intentionally does not compare message text or
position formatting yet.  Recursive descent generally reports source-character
positions; the combinator parser often reports token-stream positions.

## Remaining Diagnostic Drift

The remaining drift in the starter rejection corpus is now concentrated in
missing right-hand command diagnostics after binary command operators:

- `echo |`
- `echo &&`

The recursive-descent parser reports EOF for those cases.  The combinator
parser still reports the operator token because the command-list level sees the
operator as the point where parsing stopped.

## Recommended Next Tightening

1. Add command-operator commitment for missing right-hand commands after `|`
   and `&&`.
2. Normalize diagnostic position semantics before asserting positions.  Decide
   whether combinator errors should report source-character positions like
   recursive descent, or whether tests should compare token identity only.
