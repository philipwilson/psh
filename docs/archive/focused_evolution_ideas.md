## Focused Improvements for Long-Term Maintainability

### Keyword Infrastructure
- Expand `matches_keyword` and `matches_keyword_type` usage to all parser surfaces that still rely on raw `token.value` checks (`psh/parser/errors.py`, enhanced parser variants, and the archived combinator examples) so we have a single source of truth for keyword semantics.
- Consolidate keyword metadata updates into a small utility (e.g., `keyword_defs.promote_token(token, keyword)`) to remove duplicated `token.metadata.semantic_type` assignments and make it harder to forget metadata when new keywords are introduced.
- Consider giving `Token` a lazily-computed `normalized_value` property that always returns the canonical keyword spelling; this would simplify error reporting and downstream tooling that formats tokens.

### Parser Cohesion
- Gradually replace hand-written keyword loops inside the combinator parsers (e.g., case/if nesting counters) with reusable helpers that understand nesting by token type. This would let us share the same logic across combinator and recursive-descent implementations.
- Evaluate whether the recursive-descent `ControlStructureParser` can use the same `_collect_tokens_until_keyword` helper (or a shared variant) to reduce divergence between the two parsing stacks.
- Introduce a tiny layer (perhaps `KeywordGuard`) that wraps `BaseParser.expect`/`match_any` and caches the result of `matches_keyword_type` to avoid repeatedly lower-casing and comparing strings when the parser backtracks.

### Testing & Tooling
- Add golden tests around the keyword normalizer to capture edge cases (HEREDOC bodies, nested `case` items, `for … in` variations) so future changes to keyword handling are automatically validated.
- Create regression tests that exercise both parser implementations on the same token streams to ensure the keyword helpers stay behaviorally aligned.
- Wire a lightweight static check (pre-commit or CI script) that fails if new occurrences of `token.value == '<keyword>'` appear outside of whitelisted areas, keeping the codebase on the unified helper path.

### Documentation & Developer Experience
- Document the keyword-helper lifecycle in `ARCHITECTURE.llm` (or a dedicated developer guide) so contributors know the expected flow: lexer normalizes → helpers match → parsers consume.
- Publish a short “keyword normalization cookbook” explaining common pitfalls (e.g., handling `in` without a pending loop keyword) to lower the barrier for future contributors touching the lexer or parser layers.
