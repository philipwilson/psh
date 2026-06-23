#!/usr/bin/env python3
"""Token type definitions for PSH lexer and parser."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from .token_parts import TokenPart


class TokenType(Enum):
    """All token types recognized by the shell lexer."""
    # Basic tokens
    WORD = auto()
    PIPE = auto()
    PIPE_AND = auto()             # |&
    REDIRECT_IN = auto()
    REDIRECT_OUT = auto()
    REDIRECT_APPEND = auto()
    REDIRECT_DUP = auto()
    REDIRECT_READWRITE = auto()   # <>
    REDIRECT_CLOBBER = auto()     # >|
    HEREDOC = auto()
    HEREDOC_STRIP = auto()
    HERE_STRING = auto()
    SEMICOLON = auto()
    AMPERSAND = auto()
    AND_AND = auto()
    OR_OR = auto()
    NEWLINE = auto()
    EOF = auto()

    # Quoted strings and variables
    STRING = auto()
    VARIABLE = auto()

    # Expansions
    COMMAND_SUB = auto()
    COMMAND_SUB_BACKTICK = auto()
    ARITH_EXPANSION = auto()
    PARAM_EXPANSION = auto()       # ${var:-default} style expansions
    PROCESS_SUB_IN = auto()    # <(...)
    PROCESS_SUB_OUT = auto()   # >(...)

    # Grouping
    LPAREN = auto()
    RPAREN = auto()
    LBRACE = auto()
    RBRACE = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    DOUBLE_LPAREN = auto()  # ((
    DOUBLE_RPAREN = auto()  # ))

    # Keywords
    FUNCTION = auto()
    IF = auto()
    THEN = auto()
    ELSE = auto()
    FI = auto()
    ELIF = auto()
    WHILE = auto()
    UNTIL = auto()
    DO = auto()
    DONE = auto()
    FOR = auto()
    IN = auto()
    BREAK = auto()
    CONTINUE = auto()
    RETURN = auto()
    CASE = auto()
    ESAC = auto()
    SELECT = auto()
    TIME = auto()              # `time` pipeline-timing reserved word

    # Case terminators
    DOUBLE_SEMICOLON = auto()  # ;;
    SEMICOLON_AMP = auto()     # ;&
    AMP_SEMICOLON = auto()     # ;;&

    # Special operators
    EXCLAMATION = auto()       # !
    DOUBLE_LBRACKET = auto()   # [[
    DOUBLE_RBRACKET = auto()   # ]]
    REGEX_MATCH = auto()       # =~
    EQUAL = auto()             # ==
    NOT_EQUAL = auto()         # !=

    # Composite tokens
    COMPOSITE = auto()         # Merged adjacent tokens


@dataclass
class Token:
    """Unified token class for the shell lexer and parser."""
    type: TokenType
    value: str
    position: int
    end_position: int = 0  # Position after the last character of the token
    quote_type: Optional[str] = None  # Track the quote character used (' or " or None)
    line: Optional[int] = None  # Line number (1-based)
    column: Optional[int] = None  # Column number (1-based)
    adjacent_to_previous: bool = False  # True if no whitespace between this and previous token
    is_keyword: bool = False  # True when keyword normalizer marks this as a keyword
    parts: Optional[List['TokenPart']] = field(default=None)  # Token parts (imported from lexer.token_parts)
    fd: Optional[int] = None  # File descriptor prefix (e.g., 2 in 2>file)
    var_fd: Optional[str] = None  # Named-fd prefix var (e.g. 'fd' in {fd}>file)
    combined_redirect: bool = False  # True for &> and &>> (stdout+stderr)

    def __post_init__(self):
        """Initialize parts if not provided."""
        if self.parts is None:
            self.parts = []

