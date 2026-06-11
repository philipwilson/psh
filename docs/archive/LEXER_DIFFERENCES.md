# Known Differences Between StateMachineLexer and ModularLexer

This document lists the known tokenization differences between the legacy StateMachineLexer and the new ModularLexer. These differences do not affect functionality due to parser compatibility handling.

## 1. Composite Tokens

**Pattern**: `text$VAR` or `text${VAR}`
- **StateMachineLexer**: Single WORD token with parts
- **ModularLexer**: Separate WORD and VARIABLE tokens
- **Impact**: None - parser handles both formats

## 2. Assignment Operators

**Pattern**: `VAR=value`
- **StateMachineLexer**: Single WORD token "VAR="
- **ModularLexer**: Two tokens: WORD "VAR" and WORD "="
- **Impact**: None - parser recognizes assignment pattern

## 3. Keyword Recognition

**Pattern**: Keywords in certain contexts (e.g., `in` after `case $var`)
- **StateMachineLexer**: Recognizes as keyword tokens (IN, ESAC, etc.)
- **ModularLexer**: May tokenize as WORD
- **Impact**: None - parser has compatibility layer for keyword recognition

## 4. Redirection Operators

**Pattern**: `2>&1`
- **StateMachineLexer**: Single REDIRECT_DUP token
- **ModularLexer**: Multiple tokens (REDIRECT_ERR, AMPERSAND, WORD)
- **Impact**: None - parser assembles redirection correctly

## Performance

Despite these differences, ModularLexer provides:
- **1.7x faster** tokenization speed
- Better error recovery in interactive mode
- Cleaner, more maintainable architecture

## Migration

These differences are handled transparently by the parser's compatibility layer. No changes to shell scripts or user code are required when switching between lexers.