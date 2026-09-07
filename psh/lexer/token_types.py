#!/usr/bin/env python3
"""Token type definitions for PSH lexer and parser."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Optional, Tuple

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
    Stages that need a changed token (keyword classification, heredoc-id
    attachment, in-parser retypes) build a new one with
    :func:`dataclasses.replace`. ``position``/``end_position`` remain the
    canonical stored offsets; :pyattr:`span` is a derived read-only view over
    them.

    The freeze reaches the WHOLE value graph, not merely this class's own
    attributes: ``parts`` is a TUPLE of frozen
    :class:`~psh.lexer.token_parts.TokenPart` values, whose own
    :class:`~psh.lexer.position.Position` fields are frozen too (freezing
    only the outer classes left those writable). Until reappraisal #22
    MEDIUM-10, ``frozen`` guarded the attributes while ``parts`` stayed a
    mutable list of mutable parts, so a lexed value could still be rewritten
    after the lexer had returned it. Construction accepts any iterable of parts
    and :meth:`__post_init__` coerces it, so a caller that builds a list still
    works while the STORED value is always a tuple.
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
    parts: Tuple['TokenPart', ...] = ()  # Token parts (from lexer.token_parts)
    fd: Optional[int] = None  # File descriptor prefix (e.g., 2 in 2>file)
    var_fd: Optional[str] = None  # Named-fd prefix var (e.g. 'fd' in {fd}>file)
    combined_redirect: bool = False  # True for &> and &>> (stdout+stderr)
    # Heredoc spec id (ordinal within the lexed unit), attached by the heredoc
    # lexer to a `<<`/`<<-` operator token once its body has been collected.
    # None means "no body was collected for this token" — bodies are still in
    # the token stream (plain tokenize()). The id keys the LexedUnit's
    # heredocs map; identity is ordinal, never delimiter text (campaign S2).
    # repr=False keeps Token's repr stable (invisible in repr).
    heredoc_id: Optional[int] = field(default=None, repr=False)
    # Structured `name=(...)` array initializer, stashed by the combinator on a
    # synthetic WORD token so `_build_simple_command` can recover it. None for
    # ordinary words. (Lexer-internal payload; retired with WordToken in a
    # later phase.) repr=False for the same repr-stability reason as heredoc_id.
    array_init: Optional[Any] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Coerce ``parts`` to a tuple so the stored graph is always frozen.

        Construction sites legitimately BUILD a list of parts while scanning a
        word; freezing at the boundary keeps that natural and still leaves no
        mutable edge on a finished token.
        """
        if not isinstance(self.parts, tuple):
            object.__setattr__(self, 'parts', tuple(self.parts))

    @property
    def span(self) -> SourceSpan:
        """The token's source range as a :class:`SourceSpan` (derived view)."""
        return SourceSpan(self.position, self.end_position)


def _closing_quote(quote_type: str) -> str:
    """The character that closes ``quote_type`` (``$'...'`` closes with ``'``)."""
    return "'" if quote_type == "$'" else quote_type


def slice_renders_token(token: Token, source_text: str) -> bool:
    """True when ``source_text[token.position:token.end_position]`` is a
    faithful source rendering of *token*.

    A token's span indexes THE TEXT THE LEXER SAW. A caller that hands the
    parser a different string still gets a slice — of the wrong string. That
    is exactly how a ``for``/``select`` header taken from an alias bound the
    wrong loop variable (Improvement Program 2026-09, C010): the tokens carry
    alias-body positions while ``source_text`` is the pre-expansion line, so
    ``for i`` sliced ``e`` out of ``beg echo …`` and the loop bound ``e``.
    Reproduce with::

        shopt -s expand_aliases; alias beg='for i in 1 2; do'
        beg echo "i=[$i]"; done

    A rendering is faithful when the slice still shows the token's OWN
    fields: an unquoted token spells its value verbatim, a ``$``-token keeps
    its ``$``, and a quoted token keeps its opening and closing quotes around
    inner text that either equals the value or contains a backslash — escape
    processing (``"a\\\\b"``, ``$'\\x41'``) is the only way the lexer's stored
    value legitimately differs from the spelling, and it needs a backslash to
    happen. Anything else is a slice of some other string.
    """
    if not (token.position <= token.end_position <= len(source_text)):
        return False
    if token.end_position <= token.position:
        return False
    sliced = source_text[token.position:token.end_position]
    if token.type == TokenType.STRING:
        opening = token.quote_type or '"'
        closing = _closing_quote(opening)
        if len(sliced) < len(opening) + len(closing):
            return False
        if not (sliced.startswith(opening) and sliced.endswith(closing)):
            return False
        inner = sliced[len(opening):-len(closing)]
        return inner == token.value or '\\' in inner
    if token.type == TokenType.VARIABLE:
        return sliced == f"${token.value}"
    return sliced == token.value


def token_lexeme(token: Token, source_text: Optional[str] = None) -> str:
    """The token's EXACT SOURCE SPELLING (quotes, ``$``, escapes included).

    The token's OWN fields are the authority: a STRING re-wraps its
    ``quote_type`` (``$'...'`` closes with ``'``), a VARIABLE restores ``$``
    (``value`` is ``x`` or ``{v}``); every other type already stores its full
    source form in ``value``. ``source_text`` only REFINES that spelling, and
    only for a span that :func:`slice_renders_token` verifies renders this
    token — which recovers escapes the value no longer carries (bash prints
    ``` `"a\\\\b"' ``` for ``for "a\\\\b"``) without ever letting a slice of a
    DIFFERENT string supply the answer (C010; see the predicate's docstring).
    An unverified span falls back to the reconstruction, so no reader of this
    helper can pick up a stale slice.

    Used where a diagnostic must show the user's raw spelling — e.g. bash's
    ``` `"in"': not a valid identifier ``` for a quoted for/select subject —
    and, for an unquoted word, it is the token's ``value`` either way, which
    is what makes it safe to store as a loop variable NAME.
    """
    if source_text is not None and slice_renders_token(token, source_text):
        return source_text[token.position:token.end_position]
    if token.type == TokenType.STRING:
        qt = token.quote_type or '"'
        return f"{qt}{token.value}{_closing_quote(qt)}"
    if token.type == TokenType.VARIABLE:
        return f"${token.value}"
    return token.value

