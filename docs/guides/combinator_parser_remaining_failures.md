# Combinator Parser: Remaining Test Failures

**As of v0.276.0** — 0 known failures, but note the caveat below.

The combinator parser passes all tests in the main test suite
(excluding the directories that are structurally excluded due to subshell
FD inheritance, advanced function scoping, and complex variable assignment).

## Caveat: drift is the failure mode, not test failures

The combinator parser is experimental/educational and **lags behind
recursive-descent fixes by default** — the main suite mostly exercises
the rd parser, so combinator regressions don't show up as failures here.
The 2026-06-10 ground-up reappraisal found two such drifts (both
introduced by rd fixes in v0.266–v0.269, fixed in the combinator in
v0.276.0):

- Function-definition trailing redirects were applied at *definition*
  time instead of per call (`f() { ...; } > file`).
- Case patterns lost quote context, so quoted glob characters wrongly
  stayed active (`case ab in "a*")` matched).

Three-way parity regressions (bash vs rd vs combinator) live in
`tests/integration/parser/test_combinator_parity_regressions.py`. When
fixing parser behavior in the rd parser, check whether the combinator
needs the same fix, and add a parity test there.

## Summary

No known remaining failures. The last 3 "failures" before v0.171.0 were
test infrastructure issues (pytest capture interference with forked child
FDs), not parser bugs. They were resolved by rewriting the tests to use
`subprocess.run()`.

## How to Run

```bash
# Full combinator test suite (excluding known-excluded directories)
PSH_TEST_PARSER=combinator python -m pytest tests/ \
  --ignore=tests/integration/subshells/ \
  --ignore=tests/integration/functions/test_function_advanced.py \
  --ignore=tests/integration/variables/test_variable_assignment.py \
  -q --tb=line

# Via the smart test runner (handles -s flag tests automatically)
python run_tests.py --combinator > tmp/combinator-results.txt 2>&1
tail -15 tmp/combinator-results.txt
```

## Known open gap: statement sequencing does not require a separator

**Found 2026-07-05 (parser-hardening campaign, appraisal finding 5b).**

The combinator's statement-list loop
(`psh/parser/combinators/commands/statements.py`, `parse_statement_list`)
consumes `optional(separators)` between statements, so it accepts two
statements with **no** separator (`;`, newline, `&`, `|`, `&&`, `||`)
between them. A word immediately followed by a compound command parses as
two statements instead of a syntax error:

```sh
echo (x)        # combinator: two statements (`echo`, then subshell `(x)`)
                # rd + bash:  syntax error near `(`
```

This surfaced (it was not caused) when array-initializer adjacency was
fixed: `arr += (one two)` / `a= (x)` / `a = (x)` are no longer array
initializers in either parser (matching bash), after which the rd parser
reports a syntax error but the combinator falls into this sequencing gap
and yields two statements. The rd side is pinned bash-correct
(`echo (x)` → `ParseError`) in
`tests/unit/parser/test_word_then_subshell_sequencing.py`.

Fixing this properly means requiring a separator between statements in the
combinator's core sequencing — a broad change with wide blast radius,
deferred to its own campaign (the combinator is educational and outside the
production quality bar). The `array-spaced-append-init` entry was removed
from the AST-parity corpus because it is no longer an array-parity case.

## Known open gap: `=~` conditional-regex operand handling

**Documented 2026-07-05 (parser-hardening campaign, appraisal finding 5d).**

The combinator's `[[ ]]` parser (`psh/parser/combinators/special_commands.py`,
`_parse_test_expression`) models only single-token binary/unary operand forms;
its own docstring marks multi-token `=~` regexes as an explicit educational
boundary. As a result its `=~` operand handling diverges from the
recursive-descent parser (which enforces a bash-faithful operand policy):

- It **under-accepts** legal multi-token regexes: `[[ ab =~ a|b ]]` and
  `[[ ab =~ (a|b)+ ]]` are rejected (they are not three tokens), whereas rd +
  bash accept them.
- It **over-accepts** illegal single-token operands: `[[ x =~ ; ]]`,
  `[[ x =~ & ]]`, `[[ x =~ < ]]`, `[[ x =~ ( ]]` parse as a binary test with a
  one-token regex operand, whereas rd + bash reject them as a conditional
  syntax error.

Closing this needs a real multi-token regex-operand collector in the
combinator (the rd parser's `_parse_regex_operand` with its
separator/redirection/balanced-paren policy). That contradicts the combinator's
stated single-token design boundary and is deferred to its own campaign. The rd
side is pinned bash-correct in
`tests/unit/parser/test_regex_operand_policy.py` and the `parsefix_regex_*`
golden cases.

## History

| Date | Failures | Notes |
|------|----------|-------|
| v0.166.0 (pre-fix) | 39 | Baseline before bug-fix batch |
| v0.167.0 (batch 1) | 18 | Fixed: pipeline routing, for-loop expansions, stderr redirects, array assignments, C-style for `do` |
| v0.168.0 (batch 2) | 11 | Fixed: process substitution (LiteralPart), errexit in TopLevel, RBRACE in brace expansion |
| v0.169.0 (batch 3) | 5 | Fixed: lexer arithmetic operator drop, case pattern LBRACKET character classes |
| v0.170.0 (batch 4) | 3 | Fixed: associative array initialization (quoted keys/values, bracket tokens) |
| v0.171.0 (batch 5) | 0 | Rewrote C-style for I/O redirection tests to use subprocess (test infra fix, not parser bug) |
