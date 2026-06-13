# Reappraisal #4 — Tier C: lexer / parser / AST elegance

Date opened: 2026-06-13

> ⚡ **STATUS (2026-06-13) — Tiers A, B, C, D shipped (v0.340.0–v0.348.0);
> B3 and E deferred.** Nine releases, each zero-behavior-change behind a
> frozen characterization harness + bash differential probes:
> A1 invariant lock-down (v0.340) · A2 sidecar derive/delete (v0.341) ·
> B1 Word text-methods (v0.342) · B2 array-assignment normalization, dead
> pattern deleted (v0.343) · C1 typed cmdsub scanner state (v0.344) ·
> C2 command-position drift-lock — unified machine intentionally NOT
> extracted, the shared vocabulary already realizes Ugly 8 (v0.345) ·
> C3 OperatorDebrisWordRecognizer (v0.346) · D1 Word.quote_type derived from
> parts (v0.347) · D2 `[[ ]]` operands → Word model (v0.348).
>
> **DEFERRED — B3 (Ugly 6, declaration-arg reparse):** doing it "properly"
> (a structured `AssignmentWord` consumed by the declaration builtins) is a
> 5-subsystem change — new AST node + the argv model + the executor→builtin
> interface + 2 builtins + Word fidelity — because the builtins re-parse the
> VERBATIM source string (`shlex.split`) and the element Words deliberately
> lose source detail (`${y}b`→`$y`+`b`, quote boundaries). That couples it to
> the deferred Ugly 10 (token-payload fidelity, E1). Disproportionate risk for
> a working, well-documented, tested path. Revisit only if the token-payload
> work (E1) is taken on.
>
> **DEFERRED — E1 (Ugly 2 + 10, typed token payloads):** the most invasive
> change (the whole lexer↔parser boundary); the review's own phase plan omits
> it. Not scheduled.
>
> Suite at close: 6,718 passed / 6,965 collected; ruff + mypy clean; GitHub
> CI disabled (local gate is the gate); all releases auto-tagged.

Source: `docs/reviews/lexer_parser_ast_architecture_review_2026-06-13.md` (a
fresh lexer/parser/AST review identifying 12 "uglies" + a 6-phase plan). The
goal is **cleanliness, economy, elegance — zero behavior change**; the shell
already works well. Every claim below was verified against the live tree
before scheduling.

Verification highlights:
- The parallel legacy AST fields (`element_types`, `element_quote_types`,
  `value_type`, `value_quote_type`, `item_quote_types`) are consumed **only by
  `formatter_visitor` and `validator_visitor`** — never the executor/expansion
  hot path (which already uses `words`). `item_quote_types` has **zero**
  consumers (dead field). → the big AST cleanup is low-risk.
- B3 decomposed `find_command_substitution_end` into `_CmdSubScanner` but kept
  **string phase constants** + **list states** (`[state, pattern_paren_depth]`)
  — Ugly 7 is real and undone.
- `is_array_assignment` documents 6 tokenisation patterns; declaration-arg
  `_parse_array_initialization` returns a flat `str` that builtins re-parse —
  Uglies 5/6 confirmed.

## Tiers (sequenced by risk; each = one zero-behavior-change release)

Safety nets per release: invariant tests + AST round-trip (formatter) + full
suite + a characterization harness BEFORE any deletion/restructure. (Behavior
must not move, so bash probes matter less than AST-shape assertions.)

### Tier A — foundation + AST field cleanup (low risk, highest clarity/risk)
- **A1 — Invariant lock-down** (review Phase 1): tests that every parser-built
  AST carries its canonical fields (`SimpleCommand.words`, array
  `words`/`value_word`, `ForLoop`/`SelectLoop.item_words`, recursive-descent
  `CasePattern.word`); a meta-assertion that the executor never reads a legacy
  string field where a `Word` exists. No production change.
- **A2 — Derive/delete legacy fields** (Ugly 1, 12): delete dead
  `item_quote_types`; make `element_types`/`element_quote_types`/`value_type`/
  `value_quote_type` derived from `words` (or update formatter/validator to
  read `words` and drop the stored fields); make `value_word`/`item_words`
  non-optional for parser output; isolate combinator-only `CasePattern.pattern`
  compat.

### Tier B — parser shape normalization (medium risk, high value)
- **B1 — `Word` text-method discipline** (Ugly 4): `source_text()` /
  `literal_text()` / `display_text()`; retire semantic `str(word)` and
  `''.join(str(p)…)`; `__str__` → debug-only.
- **B2 — Normalize array/assignment token shapes** (Ugly 5): an
  `AssignmentCandidate`/`WordCursor` layer so `ArrayParser` consumes one
  structured candidate, collapsing the 6-pattern matrix.
- **B3 — Replace declaration-arg reparse** (Ugly 6): an `AssignmentWord` AST
  node so declaration builtins consume structured assignments instead of a
  serialized-then-reparsed string.

### Tier C — lexer / scanner consolidation (contained)
- **C1 — Type the cmdsub scanner state** (Ugly 7): `CasePhase` enum +
  `CaseScanState` dataclass; scanner-extent-vs-parser corpus test.
- **C2 — Shared `CommandPositionMachine`** (Ugly 8): one command-position
  policy reused by lexer, keyword normalizer, scanner.
- **C3 — Promote the fallback word recognizer** (Ugly 9): a named
  `OperatorDebrisWordRecognizer` with its own priority/tests.

### Tier D — finish the Word model (medium risk)
- **D1 — Quote context in parts only** (Ugly 3): retire whole-word
  `quote_type`; derive `is_fully_quoted`/`has_quoted_parts` from parts.
- **D2 — Test operands → `Word`/`TestOperand`** (Ugly 11): bring `[[ … ]]`
  into the Word model.

### Tier E — DEFERRED (high effort/risk)
- **E1 — Typed token payloads** (Ugly 2, 10): `Token.payload` variants
  (`WordPayload`/`RedirectPayload`/`KeywordPayload`) + structured expansion
  payloads. The most invasive change (whole lexer↔parser boundary); the
  review's own phase plan omits it. Not scheduled unless explicitly requested.

## Method (unchanged from reappraisal #4 Tier B)
Local-gated fast loop: branch → subagent implements (no commits, harness/
invariant tests FIRST) → orchestrator verifies (full `run_tests.py --parallel`,
ruff, mypy, formatter round-trip) → 4-file version ritual (no manual tag —
`release-tag.yml` auto-tags) → commit → `gh pr create --head` → merge
immediately. GitHub `tests.yml` is disabled; the local gate is the gate.
