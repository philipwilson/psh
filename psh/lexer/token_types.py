#!/usr/bin/env python3
"""Token type definitions for PSH lexer and parser."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, List, Optional

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
    # (PARAM_EXPANSION retired with WordToken: the lexer emits VARIABLE for every
    #  ${...} form; the WordBuilder classifies simple-name vs operator.)
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
    # (COMPOSITE retired with WordToken: adjacent word pieces are fused into one
    #  WORD carrying `parts` by word_fusion, not merged into a COMPOSITE token.)


@dataclass(frozen=True)
class SourceSpan:
    """Half-open ``[start, end)`` byte range of a token in its source text.

    ``start``/``end`` are absolute offsets into the string the token was lexed
    from (the same values carried by ``Token.position``/``Token.end_position``).
    Slicing ``source[start:end]`` reconstructs the token's lexeme.
    """
    start: int
    end: int


@dataclass(frozen=True)
class Token:
    """Unified, immutable token for the shell lexer and parser.

    Tokens are ``frozen``: once produced by the lexer they are never mutated.
    Stages that need a changed token (keyword classification, heredoc-key
    attachment, in-parser retypes) build a new one with
    :func:`dataclasses.replace`. ``position``/``end_position`` remain the
    canonical stored offsets; :pyattr:`span` is a derived read-only view over
    them. (``frozen`` guards the attributes, not the contents of the mutable
    ``parts`` list — but ``parts`` is never mutated after construction.)
    """
    type: TokenType
    value: str
    position: int
    end_position: int = 0  # Position after the last character of the token
    quote_type: Optional[str] = None  # Track the quote character used (' or " or None)
    line: Optional[int] = None  # Line number (1-based)
    column: Optional[int] = None  # Column number (1-based)
    adjacent_to_previous: bool = False  # True if no whitespace between this and previous token
    is_keyword: bool = False  # True when keyword normalizer marks this as a keyword
    parts: List['TokenPart'] = field(default_factory=list)  # Token parts (imported from lexer.token_parts)
    fd: Optional[int] = None  # File descriptor prefix (e.g., 2 in 2>file)
    var_fd: Optional[str] = None  # Named-fd prefix var (e.g. 'fd' in {fd}>file)
    combined_redirect: bool = False  # True for &> and &>> (stdout+stderr)
    # Heredoc collector key, attached by the heredoc lexer to a `<<`/`<<-`
    # operator token once its body has been collected. None means "no body was
    # collected for this token" — the *declared* signal replaces the old
    # dynamic-setattr-plus-hasattr convention. repr=False keeps Token's repr
    # byte-identical to when this was a dynamic attribute (invisible in repr).
    heredoc_key: Optional[str] = field(default=None, repr=False)
    # Structured `name=(...)` array initializer, stashed by the combinator on a
    # synthetic WORD token so `_build_simple_command` can recover it. None for
    # ordinary words. (Lexer-internal payload; retired with WordToken in a
    # later phase.) repr=False for the same repr-stability reason as heredoc_key.
    array_init: Optional[Any] = field(default=None, repr=False)

    @property
    def span(self) -> SourceSpan:
        """The token's source range as a :class:`SourceSpan` (derived view)."""
        return SourceSpan(self.position, self.end_position)


def token_lexeme(token: Token, source_text: Optional[str] = None) -> str:
    """The token's EXACT SOURCE SPELLING (quotes, ``$``, escapes included).

    With ``source_text`` available the span slice is authoritative (a fused
    WORD's ``value`` already round-trips it). Without source (e.g. the
    combinator parser is handed a bare token list) the lexeme is
    reconstructed from the token's stripped fields: a STRING re-wraps its
    ``quote_type`` (``$'...'`` closes with ``'``), a VARIABLE restores ``$``
    (``value`` is ``x`` or ``{v}``); every other type already stores its full
    source form in ``value``.

    Used where a diagnostic must show the user's raw spelling — e.g. bash's
    ``` `"in"': not a valid identifier ``` for a quoted for/select subject.
    """
    if source_text is not None and token.end_position > token.position:
        return source_text[token.position:token.end_position]
    if token.type == TokenType.STRING:
        qt = token.quote_type or '"'
        closing = "'" if qt == "$'" else qt
        return f"{qt}{token.value}{closing}"
    if token.type == TokenType.VARIABLE:
        return f"${token.value}"
    return token.value

