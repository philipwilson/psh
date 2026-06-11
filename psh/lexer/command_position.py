"""Shared command-position token classifications.

"Command position" is the start of a simple command, where a reserved word is
recognized as a keyword (and where the lexer enables operators like ``[[``).
Two passes track it: the lexer during tokenization (working on ``WORD``-valued
keywords) and the keyword normalizer afterward (working on typed keywords).
Both consult the same classification sets defined here so the notion of "what
returns us to command position" lives in one place.
"""

from .token_types import TokenType

# Operator token types after which the next token is at command position.
# Shared verbatim by both passes.
STATEMENT_SEPARATORS = frozenset({
    TokenType.SEMICOLON,
    TokenType.NEWLINE,
    TokenType.AND_AND,
    TokenType.OR_OR,
    TokenType.PIPE,
})

# Case-item terminators (``;;``, ``;&``, ``&;``) also return to command
# position. The normalizer treats these as separators; the lexer instead tracks
# case state directly (case_depth / in_case_pattern), so it does not fold these
# into its command-position reset.
CASE_TERMINATORS = frozenset({
    TokenType.DOUBLE_SEMICOLON,
    TokenType.SEMICOLON_AMP,
    TokenType.AMP_SEMICOLON,
})

# Reserved-word token types after which the next token is at command position.
# These types only exist after keyword normalization, so only the normalizer
# uses them — during tokenization these words are still plain WORD tokens.
RESET_TO_COMMAND_POSITION = frozenset({
    TokenType.THEN,
    TokenType.DO,
    TokenType.ELSE,
    TokenType.ELIF,
    TokenType.FI,
    TokenType.DONE,
    TokenType.ESAC,
})

# Structural openers after which the lexer is at command position.
COMMAND_GROUP_OPENERS = frozenset({
    TokenType.LPAREN,
    TokenType.LBRACE,
})
