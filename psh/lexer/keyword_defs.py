"""Shared keyword definitions and helpers."""

from typing import Iterable, Optional

from .token_types import TokenType

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
    'break': TokenType.BREAK,
    'continue': TokenType.CONTINUE,
    'return': TokenType.RETURN,
}

# Reverse lookup for matching by TokenType
KEYWORD_BY_TYPE = {value: key for key, value in KEYWORD_TYPE_MAP.items()}


def keyword_from_type(token_type: TokenType) -> Optional[str]:
    """Return the canonical keyword string for a token type."""
    return KEYWORD_BY_TYPE.get(token_type)


def matches_keyword_type(token, expected_type: TokenType) -> bool:
    """Check whether the token represents the given keyword token type."""
    if token.type == expected_type:
        return True

    keyword = KEYWORD_BY_TYPE.get(expected_type)
    if keyword is None:
        return False
    if token.type != TokenType.WORD:
        return False

    # Keyword matching is case-sensitive, as in bash: only the exact
    # lowercase spelling counts as a reserved word.
    if (token.value or '') == keyword:
        token.is_keyword = True
        return True

    return False


def matches_keyword(token, keyword: str) -> bool:
    """Check whether the token represents the given keyword string.

    `keyword` must be the canonical lowercase spelling; matching against
    token text is case-sensitive (as in bash).
    """
    expected_type = KEYWORD_TYPE_MAP.get(keyword)
    if expected_type is None:
        return False
    return matches_keyword_type(token, expected_type)


def matches_any_keyword(token, keywords: Iterable[str]) -> bool:
    """Return True if token matches any of the provided keyword strings."""
    return any(matches_keyword(token, keyword) for keyword in keywords)


class KeywordGuard:
    """Cache keyword comparisons for a token to avoid repeated normalization."""

    __slots__ = ("token", "_cache")

    def __init__(self, token):
        self.token = token
        self._cache: dict[str, bool] = {}

    def matches(self, keyword: str) -> bool:
        if keyword not in self._cache:
            self._cache[keyword] = matches_keyword(self.token, keyword)
        return self._cache[keyword]

    def matches_any(self, *keywords: str) -> bool:
        return any(self.matches(keyword) for keyword in keywords)
