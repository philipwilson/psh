"""Shared keyword definitions and helpers."""

from typing import Optional

from .token_types import Token, TokenType

# Mapping between keyword strings and their canonical token types
KEYWORD_TYPE_MAP = {
    'if': TokenType.IF,
    'then': TokenType.THEN,
    'else': TokenType.ELSE,
    'elif': TokenType.ELIF,
    'fi': TokenType.FI,
    'for': TokenType.FOR,
    'select': TokenType.SELECT,
    'while': TokenType.WHILE,
    'until': TokenType.UNTIL,
    'do': TokenType.DO,
    'in': TokenType.IN,
    'done': TokenType.DONE,
    'case': TokenType.CASE,
    'esac': TokenType.ESAC,
    'function': TokenType.FUNCTION,
    'time': TokenType.TIME,
}

# Reverse lookup for matching by TokenType
KEYWORD_BY_TYPE = {value: key for key, value in KEYWORD_TYPE_MAP.items()}


def keyword_from_type(token_type: TokenType) -> Optional[str]:
    """Return the canonical keyword string for a token type."""
    return KEYWORD_BY_TYPE.get(token_type)


def matches_keyword_type(token: Token, expected_type: TokenType) -> bool:
    """Check whether the token represents the given keyword token type.

    Pure predicate: it never mutates the token. (The recursive-descent path
    gets ``is_keyword`` stamped at lex time by ``KeywordNormalizer``; the
    combinator only needs the yes/no answer here.)
    """
    if token.type == expected_type:
        return True

    keyword = KEYWORD_BY_TYPE.get(expected_type)
    if keyword is None:
        return False
    if token.type != TokenType.WORD:
        return False

    # Keyword matching is case-sensitive, as in bash: only the exact
    # lowercase spelling counts as a reserved word.
    return (token.value or '') == keyword


def matches_keyword(token: Token, keyword: str) -> bool:
    """Check whether the token represents the given keyword string.

    `keyword` must be the canonical lowercase spelling; matching against
    token text is case-sensitive (as in bash).
    """
    expected_type = KEYWORD_TYPE_MAP.get(keyword)
    if expected_type is None:
        return False
    return matches_keyword_type(token, expected_type)
