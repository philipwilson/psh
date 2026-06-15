# R9.C3 Brief — Make the combinator grammar use its own combinators

**For a fresh session.** Self-contained. Read this, then `psh/parser/combinators/CLAUDE.md`
(via `psh/parser/CLAUDE.md`) and the files named below.

## Where this sits

Campaign: reappraisal #8 / Tier R9 (memo: `docs/reviews/ground_up_reappraisal_2026-06-15.md`;
running log: memory `psh-reappraisal-8-tier-r9`). The combinator parser is the
**only B-graded subsystem** in the reappraisal; R9.C is "elevate it to first-class."

R9.C progress:
- **C1 done (v0.430.0, PR #165)** — structured nested-terminator dispatch:
  `ParseError.missing_terminator` set by `raise_committed_error(..., terminator=)`;
  `is_missing_nested_terminator()` reads the field, not a message substring.
- **C2 done (v0.431.0, PR #166)** — core hygiene: removed vestigial
  `ParseResult.remaining`; unified `then()` to reset-to-start on failure (like
  `sequence()`).
- **C3 = THIS BRIEF (not started)** — the heart of "first-class", and the
  **riskiest refactor in the whole campaign.**

Start from **main at ≥ v0.431.0**, fully green.

## The problem (the reviewer's "central irony")

This is an *educational* parser-combinator parser, yet its grammar barely uses
combinators. `core.py` is a clean, well-documented combinator library
(`Parser`, `ParseResult`, `many`, `many1`, `sequence`, `optional`, `separated_by`,
`between`, `lazy`, `or_else`, `ForwardParser`, …) — but the compound-statement
parsers parse bodies with **manual `while pos < len(tokens)` token-slicing plus a
hand-tracked `nesting_level`**, via the helper
`_collect_tokens_until_keyword(tokens, start_pos, end_keyword, start_keyword=None)`
(`psh/parser/combinators/control_structures/__init__.py:192`). That helper slices
out the body token span (counting `start_keyword`/`end_keyword` nesting), then
re-parses the slice with `self.commands.statement_list.parse(slice, 0)`.

So the parser demonstrates the *opposite* of what `core.py` teaches. C3 makes the
grammar embody the library.

### Why a naive rewrite breaks (read this before touching anything)

Shell compound bodies need **nesting-aware termination**. `while ...; do A; while
...; do B; done; done` — the body of the outer loop must stop at the *second*
`done`, not the first. A naive `between(keyword('do'), keyword('done'), body)`
matches the **first** `done` and breaks nested loops. The manual slicing exists
precisely to handle this.

The correct combinator approach is **recursion, not slicing**: a
"statement-list-until-terminator-keyword" parser where a nested compound is parsed
by the *same* recursive machinery, so its inner `done` is consumed by the inner
parser and never seen by the outer terminator check. This is how a recursive-
descent parser handles it (and the rd parser is the behavioral oracle here).

## Hard gate (non-negotiable, run after EVERY construct)

The combinator parser must stay behaviorally identical to recursive descent. The
protection is the differential parity suite:

```
python -m pytest tests/parser_differential -q          # ast + error + diagnostic parity vs rd
python -m pytest tests/unit/parser/combinators tests/integration/parser/test_combinator_parity_regressions.py -q
```

Plus bash probes for anything touched (the campaign's bash-verification workflow):
compare `python -m psh --parser combinator -c "$c"` against `python -m psh -c "$c"`
(rd, the default) AND against `bash -c "$c"` for stdout/stderr/exit. Convert any
keeper probes into `tests/parser_differential` cases.

Then the full local gate per release: `ruff check psh tests`, `mypy`,
`python run_tests.py --parallel` (THE gate). Message *text* differences between
parsers are the one intentionally-unaligned dimension (see
`docs/reviews/combinator_diagnostic_characterization_2026-06-14.md`); position /
exception-type / accept-reject must match.

## Recommended approach — incremental, one construct at a time

Do NOT rewrite all constructs at once. Suggested order (simplest blast radius first):

1. **`while` loop (PROOF OF CONCEPT first).** `_build_while_loop` in
   `psh/parser/combinators/control_structures/loops.py` (~line 67+). Replace the
   `_collect_tokens_until_keyword(..., 'done', 'do')` + re-parse with a
   recursion-based body parser (a statement-list that stops at the `done`
   keyword), expressed with the existing combinators (`lazy`/`many`/`ForwardParser`
   for the recursion into nested compounds). Keep condition parsing as-is at first
   if it isn't slicing-based. Land this as its own release and PROVE parity before
   continuing.
2. `until` loop (mirror of while).
3. `for` / `select` loops.
4. C-style `for` (`(( ; ; ))` body).
5. `if` / `elif` / `else` and `case` (`conditionals.py`) — the most involved;
   `case` items have their own terminator (`;;`/`;&`/`;;&`) logic.

After each, you may be able to delete part of `_collect_tokens_until_keyword`;
remove it entirely only once no caller remains. The currently-unused primitives
(`between`, `lazy`, `literal`, `fail_with`, `try_parse`, `with_error_context`) were
deliberately KEPT in C2 for this rewrite to consume — use them (especially `lazy`/
`ForwardParser` for recursion). If some remain genuinely unused at the end, drop
them then.

## Key files & symbols

| File | What |
|------|------|
| `psh/parser/combinators/core.py` | the combinator library — `Parser`/`ParseResult`/`many`/`many1`/`sequence`/`optional`/`separated_by`/`between`(:308)/`lazy`(:287)/`ForwardParser`(:441)/`or_else` |
| `psh/parser/combinators/control_structures/loops.py` (599 ln) | while/until/for/c-style-for/select — the slicing-based bodies |
| `psh/parser/combinators/control_structures/conditionals.py` (484 ln) | if/elif/else + case |
| `psh/parser/combinators/control_structures/__init__.py` | `_collect_tokens_until_keyword` (:192) — the slicing helper to dissolve |
| `psh/parser/combinators/control_structures/_protocols.py` | `ControlStructureProtocol` (mixin typing; update if signatures change) |
| `psh/parser/combinators/commands.py` (813 ln) | `statement_list` parser (`_build_statement_list_parser`, :96) — the recursion target |
| `psh/parser/combinators/diagnostics.py` | `raise_committed_error(..., terminator=)`, `is_missing_nested_terminator` (C1) — keep tagging fi/done/esac |

## Cautions / gotchas

- **`mypy` covers the whole combinator package** (it's a whole-package entry in
  `pyproject.toml`); `check_untyped_defs` is NOT yet on for `psh.parser.*`, but keep
  new code annotated. `ParseError`/`ErrorContext` live in
  `psh/parser/recursive_descent/helpers.py` (shared with rd).
- **Empty-body & terminator rejection must stay bash-correct** — see the R9.A/B
  history: `case x in esac` (empty) is VALID; `case x in ; esac` is an error;
  empty then/do bodies are errors. There are pinned tests
  (`tests/parser_differential/test_combinator_error_parity.py` has both a
  REJECTION_CORPUS and an ACCEPTANCE_CORPUS). Do not regress these.
- **Keep the C1 structured terminator tags**: wherever a rewritten construct
  raises "missing fi/done/esac", pass `terminator=` so nested-error remapping and
  the diagnostic-parity suite keep working.
- **`mypy 2>&1 | tail` masks the exit code** — run `mypy` plainly and check `$?`.
- Background `run_tests.py --parallel` and read `tmp/test-results-*.txt`.

## Release ritual (per construct/release)

Branch `refactor/r9c3-<construct>` off main → make change (NO commit until green)
→ characterize/parity-test/bash-probe → full gate (ruff + mypy + `run_tests.py
--parallel`) → bump `psh/version.py` + the 3 doc files (README `**Current
Version**` + Tests/Coverage counts if changed, `ARCHITECTURE.md`, `CHANGELOG.md`)
→ commit with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
trailer (this is our own work) + the 🤖 Generated-with line in the PR body →
`gh pr create --head <branch>` → `gh pr merge <n> --merge --delete-branch` →
verify the `vX.Y.Z` auto-tag (`release-tag.yml`; `git fetch --tags`). GitHub
per-PR CI is DISABLED — the gate is LOCAL.

Update memory `psh-reappraisal-8-tier-r9` (+ the MEMORY.md index line) as C3
progresses.

## Definition of done for C3

Compound-statement bodies are parsed by recursion/combinators (no
`while pos < len` slicing; `_collect_tokens_until_keyword` gone or reduced to a
genuinely-needed remnant with a documented reason); the grammar visibly uses
`core.py`'s combinators; all parity suites + full gate green; bash-parity
preserved. Then the combinator parser earns an A and R9.C is complete (→ R9.D).
