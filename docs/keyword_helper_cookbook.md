# Keyword Helper Cookbook

This guide captures the end-to-end flow for keyword handling in PSH and provides quick reminders for contributors touching lexer or parser code.

## Lifecycle Overview

1. **Normalization (Lexer)**
   - `lexer/keyword_normalizer.KeywordNormalizer` canonicalizes command-position `WORD` tokens into keyword token types (`TokenType.IF`, `TokenType.THEN`, etc.) and stamps `Token.is_keyword = True`.
   - Matching is case-sensitive, as in bash: only the exact lowercase spelling (`if`, not `IF`) becomes a reserved word; everything else stays a plain `WORD`.
   - Context rules (e.g. `;;` terminators appearing only inside `case` blocks) are enforced by the parser, not by a lexer pass.
   - After this stage, tokens expose a meaningful `token.type` and `token.is_keyword`.

2. **Consumption (Parsers)**
   - Match keywords with the shared predicates in `lexer/keyword_defs.py` — never a raw `token.value == '...'` comparison:
     - `matches_keyword(token, 'fi')` — match by canonical lowercase keyword string.
     - `matches_keyword_type(token, TokenType.FI)` — match by keyword token type.
   - Both are pure predicates (they never mutate the token). The recursive-descent path additionally reads the lex-time `token.is_keyword` stamp; the combinator parser calls `matches_keyword` directly (see `parser/combinators/`).

3. **Diagnostics & Tooling**
   - `keyword_from_type(token_type)` recovers the canonical keyword string for a token type (exercised by the command-position consistency tests).
   - Golden tests (`tests/unit/lexer/test_keyword_normalizer_golden.py`) ensure normalization stays stable across edge cases (heredocs, case patterns, for…in loops).
   - Static guardrails in `tests/unit/tooling/test_keyword_comparisons.py` fail CI when new `token.value == 'keyword'` checks are introduced outside allowlisted legacy examples.

## Common Pitfalls

- **Comparing `token.value` Directly**
  - Instead of `if token.value == 'fi':`, use `matches_keyword(token, 'fi')`.
  - The tooling test will fail if raw comparisons are committed.

- **Forgetting Table Updates**
  - When adding new keywords, extend `KEYWORD_TYPE_MAP` in `lexer/keyword_defs.py` and add fixtures to the golden tests to assert the normalized output.

- **Case Terminators**
  - Prefer token types (`TokenType.DOUBLE_SEMICOLON`, etc.) over raw string checks for `case` terminators; they're normalized by the lexer.

- **Heredoc Content**
  - Lexer normalization runs on heredoc bodies; ensure new test cases cover both quoted and unquoted delimiters if you tweak the behavior.

## Quick Reference

- **Utility Functions:** `matches_keyword`, `matches_keyword_type`, `keyword_from_type` (all in `lexer/keyword_defs.py`)
- **Token Helper:** `token.is_keyword` (stamped by `KeywordNormalizer` at lex time)
- **Tests to Update:** `tests/unit/lexer/test_keyword_normalizer.py`, `tests/unit/lexer/test_keyword_normalizer_golden.py`, `tests/test_parser_feature_parity.py`
- **Tooling Gate:** `tests/unit/tooling/test_keyword_comparisons.py`

Following this flow keeps both parser implementations, tooling, and documentation aligned whenever keyword handling changes.
