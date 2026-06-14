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
- Unterminated subshell: `(`
- Missing redirect targets: `echo >`, `cat <`
- Missing here-doc / here-string operands: `cat <<`, `cat <<<`
- Missing left-hand command before `&&`: `&& echo`

The diagnostic-parity test intentionally does not compare message text or
position formatting yet.  Recursive descent generally reports source-character
positions; the combinator parser often reports token-stream positions.

## Remaining Diagnostic Drift

Most remaining drift is parser commitment rather than message wording.  The
combinator parser still commonly falls back to a generic failure at the
construct's opening token instead of reporting the later missing terminator or
offending token.

Representative cases:

- Unterminated structures: `if ...`, `while ...`, `for ...`, `case ...`
- Malformed case header: `case a b in ...`
- Unterminated array initializer: `a=(1 2`
- Unterminated function bodies: `f() { echo hi`, `function f {`
- Function missing name: `function { echo hi; }`
- Unterminated / malformed `[[ ... ]]`
- Missing right-hand command after `|` or `&&`

## Recommended Next Tightening

1. Add commit-aware failures in control-structure parsers once their opening
   keyword has been consumed.
2. Preserve EOF diagnostics for unterminated compound constructs.
3. Normalize diagnostic position semantics before asserting positions.  Decide
   whether combinator errors should report source-character positions like
   recursive descent, or whether tests should compare token identity only.
