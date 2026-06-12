# Keyword Helper Cookbook

This guide captures the end-to-end flow for keyword handling in PSH and provides quick reminders for contributors touching lexer or parser code.

## Lifecycle Overview

1. **Normalization (Lexer)**
   - `lexer/keyword_normalizer.KeywordNormalizer` lowers and canonicalizes `WORD` tokens into keyword token types (`TokenType.IF`, `TokenType.THEN`, etc.) and annotates metadata (`SemanticType.KEYWORD`).
   - Context rules (e.g. `;;` terminators appearing only inside `case` blocks) are enforced by the parser, not by a lexer pass.
   - After this stage, tokens expose meaningful `token.type`, `token.metadata.semantic_type`, and `Token.normalized_value`.

2. **Consumption (Parsers)**
   - Always match keywords with `matches_keyword` / `matches_keyword_type` (recursive descent) or the `KeywordGuard` helper (combinator parser) to avoid manual string comparisons.
   - Use `_collect_tokens_until_keyword`-style helpers for repeated patterns so recursive descent and combinator implementations stay in sync.

3. **Diagnostics & Tooling**
   - Error handling utilities (`ErrorSuggester`, `Token.normalized_value`) rely on canonical keyword strings when suggesting fixes.
   - Golden tests (`tests/unit/lexer/test_keyword_normalizer_golden.py`) ensure normalization stays stable across edge cases (heredocs, case patterns, for…in loops).
   - Static guardrails in `tests/unit/tooling/test_keyword_comparisons.py` fail CI when new `token.value == 'keyword'` checks are introduced outside allowlisted legacy examples.

## Common Pitfalls

- **Comparing `token.value` Directly**
  - Instead of `if token.value == 'fi':`, use `matches_keyword(token, 'fi')` or `guard.matches('fi')`.
  - The tooling test will fail if raw comparisons are committed.

- **Forgetting Metadata Updates**
  - When adding new keywords, extend `KEYWORD_TYPE_MAP` in `lexer/keyword_defs.py` and add fixtures to the golden tests to assert the normalized output.

- **Case Terminators**
  - Prefer token types (`TokenType.DOUBLE_SEMICOLON`, etc.) over raw string checks for `case` terminators; they’re normalized by the lexer.

- **Heredoc Content**
  - Lexer normalization runs on heredoc bodies; ensure new test cases cover both quoted and unquoted delimiters if you tweak the behavior.

## Quick Reference

- **Utility Functions:** `matches_keyword`, `matches_keyword_type`, `KeywordGuard.matches()` / `.matches_any()`
- **Token Helpers:** `Token.normalized_value`, `token.metadata.semantic_type == SemanticType.KEYWORD`
- **Tests to Update:** `tests/unit/lexer/test_keyword_normalizer.py`, `tests/unit/lexer/test_keyword_normalizer_golden.py`, `tests/test_parser_feature_parity.py`
- **Tooling Gate:** `tests/unit/tooling/test_keyword_comparisons.py`

Following this flow keeps both parser implementations, tooling, and documentation aligned whenever keyword handling changes.
