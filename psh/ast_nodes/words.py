"""Expansion nodes and Word nodes.

Words are the parser's representation of command arguments: each is a list
of parts (literal text or an embedded expansion) carrying per-part quote
context. The expansion nodes (``$var``, ``${...}``, ``$(...)``, ``$((...))``,
``<(...)``) live here too because the Word/part types reference
:class:`Expansion` directly.
"""

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

from .base import ASTNode

if TYPE_CHECKING:
    from .commands import Program

# A name renderable as a bare ``$name``: a plain identifier, a single special
# parameter ($?, $@, $*, $#, $$, $!, $-, $0), or a single positional digit.
# Anything else (notably an array subscript like ``arr[@]``) needs ``${...}``.
_BARE_VAR_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')
_SPECIAL_PARAM_CHARS = set('?@*#$!-0123456789')

# =============================================================================
# EXPANSION NODES
# =============================================================================

class Expansion(ASTNode):
    """Base class for all types of expansions."""
    pass


@dataclass
class ProcessSubstitution(Expansion):
    """Represents a process substitution <(...) or >(...).

    An Expansion so it can appear as an ExpansionPart inside a Word
    (embedded form, e.g. ``pre<(cmd)post``); a whole-word substitution is
    simply a Word with a single ProcessSubstitution part.

    Carries the nested command parsed into a :class:`Program` (``program``) so
    invalid syntax inside ``<(...)``/``>(...)`` is rejected during the OUTER
    parse, and analysis visitors can descend into the body. ``source`` retains
    the raw inner text for formatting/diagnostics and for execution, which
    re-parses ``source`` against the runtime alias table (bash re-parses
    substitution bodies at expansion time; see command_sub/process_sub).
    """
    direction: str  # 'in' or 'out'
    program: Optional['Program'] = None  # parsed nested command list
    source: str = ''                     # raw inner text (no <()/>() wrapper)

    def __str__(self):
        symbol = '<' if self.direction == 'in' else '>'
        return f"{symbol}({self.source})"


@dataclass
class CommandSubstitution(Expansion):
    """Represents command substitution $(...) or `...`.

    For modern ``$(...)`` the body is parsed into a :class:`Program`
    (``program``) at the outer parse, so a syntax error inside rejects the
    whole input buffer before any command runs (matching bash's read-time
    validation). Legacy backticks are EXCLUDED — bash defers parts of backtick
    parsing and continues around inner errors — so backtick nodes keep
    ``program=None`` and are never eagerly parsed. ``source`` retains the raw
    inner text; execution re-parses it against the runtime alias table (bash
    re-parses at expansion time, so alias/status/byte semantics are unchanged).
    """
    program: Optional['Program'] = None  # parsed body ($() only; None for `...`)
    source: str = ''                     # raw inner text (no $()/`` wrapper)
    backtick_style: bool = False         # True for `...`, False for $(...)

    def __str__(self):
        if self.backtick_style:
            return f"`{self.source}`"
        else:
            return f"$({self.source})"


@dataclass
class ParameterExpansion(Expansion):
    """Represents parameter expansion ${...}."""
    parameter: str  # Variable name
    operator: Optional[str] = None  # :-, :=, :?, :+, #, ##, %, %%, /, // etc.
    word: Optional[str] = None  # The word part for operators like ${var:-word}

    def __str__(self):
        # Prefix-names ${!prefix@}/${!prefix*}: the bang is a PREFIX and the
        # @/* a SUFFIX around the name. The operator string stores them
        # together ("!@"/"!*"), so split it — otherwise the bang lands after
        # the name (${prefix!@}), which is a different (broken) construct.
        if self.operator in ('!@', '!*'):
            return f"${{!{self.parameter}{self.operator[1]}}}"
        if self.operator and self.word is not None:
            return f"${{{self.parameter}{self.operator}{self.word}}}"
        elif self.operator:
            return f"${{{self.operator}{self.parameter}}}"
        else:
            return f"${{{self.parameter}}}"


@dataclass
class VariableExpansion(Expansion):
    """Represents simple variable expansion $var."""
    name: str  # Variable name without $

    #: True when this came from BRACE-delimited ``${name}`` syntax rather than
    #: bare ``$name``. The two are semantically identical, but brace expansion
    #: (which runs before parameter expansion) fuses a trailing name-char run
    #: into a BARE variable — ``$v{1,2}`` -> the names ``v1``/``v2`` — while a
    #: delimited ``${v}{1,2}`` stays ``${v}1``/``${v}2`` (bash). The token-stream
    #: brace expander encoded this in the token value (``v`` vs ``{v}``); the
    #: Word AST needs it explicitly for WordBraceExpander's name fusion.
    #: Excluded from ``__eq__``/``__repr__`` so AST-repr characterization
    #: corpora and node-equality tests stay byte-identical.
    braced: bool = field(default=False, compare=False, repr=False)

    def __str__(self):
        # A subscripted reference (``arr[@]``, ``arr[0]``) or any name with
        # non-identifier characters must render as ``${name}`` — a bare
        # ``$arr[@]`` parses as ``${arr}[@]`` (element 0 + literal "[@]").
        name = self.name
        if _BARE_VAR_NAME.match(name) or (len(name) == 1 and name in _SPECIAL_PARAM_CHARS):
            return f"${name}"
        return f"${{{name}}}"


@dataclass
class ArithmeticExpansion(Expansion):
    """Represents arithmetic expansion $((...))."""
    expression: str  # The arithmetic expression

    def __str__(self):
        return f"$(({self.expression}))"


# =============================================================================
# WORD NODES (for representing mixed literal/expansion content)
# =============================================================================

@dataclass
class WordPart(ASTNode):
    """A part of a word - either literal text or an expansion."""
    pass


@dataclass
class LiteralPart(WordPart):
    """Literal text part of a word."""
    text: str
    quoted: bool = False  # Was this in a quoted context?
    quote_char: Optional[str] = None  # Which quote: "'" or '"' or None

    def __str__(self):
        return self.text


@dataclass
class ExpansionPart(WordPart):
    """Expansion part of a word."""
    expansion: Expansion
    quoted: bool = False  # Was this in a quoted context?
    quote_char: Optional[str] = None  # Which quote: "'" or '"' or None

    def __str__(self):
        return str(self.expansion)


def _expansion_literal_text(expansion: Expansion) -> str:
    """Render an Expansion as the literal ``$``-source text it came from.

    Helper for :meth:`Word.to_literal_string` (quote removal of words
    whose expansions were never live, e.g. inside single quotes). NOT the
    same as the nodes' ``__str__``: ``ParameterExpansion.__str__`` formats
    a word-less operator as a prefix (``${#var}``), while this historical
    rule appends it (``${var#}``) — kept verbatim from the expansion
    manager (zero-behavior-change; the branch is unreachable for words
    built by the parsers, which make single-quoted content literal).
    """
    if isinstance(expansion, VariableExpansion):
        return f"${expansion.name}"
    elif isinstance(expansion, CommandSubstitution):
        if expansion.backtick_style:
            return f"`{expansion.source}`"
        else:
            return f"$({expansion.source})"
    elif isinstance(expansion, ParameterExpansion):
        # Reconstruct parameter expansion syntax
        result = f"${{{expansion.parameter}"
        if expansion.operator:
            result += expansion.operator
            if expansion.word:
                result += expansion.word
        result += "}"
        return result
    elif isinstance(expansion, ArithmeticExpansion):
        return f"$(({expansion.expression}))"
    else:
        # ProcessSubstitution and any future expansion types render via
        # their __str__ (e.g. '<(cmd)')
        return str(expansion)


@dataclass
class Word(ASTNode):
    """A word that may contain expansions.

    Examples:
    - "hello" -> [LiteralPart("hello")]
    - "$USER" -> [ExpansionPart(VariableExpansion("USER"))]
    - "Hello $USER!" -> [LiteralPart("Hello "), ExpansionPart(VariableExpansion("USER")), LiteralPart("!")]
    - "${HOME}/bin" -> [ExpansionPart(ParameterExpansion("HOME")), LiteralPart("/bin")]
    """
    parts: List[WordPart] = field(default_factory=list)

    #: Structured array initializer for a ``name=(...)`` argument of a
    #: declaration builtin (``declare -a a=(1 2)``, ``local``, ``export``,
    #: ``readonly``, ``typeset``). The parser cannot tell at parse time
    #: whether the command is a declaration builtin, so it always attaches
    #: this when it sees ``name=(...)`` in ARGUMENT position; the Word's
    #: literal parts still carry the flat string (``a=(1 2)``) for
    #: ``.args``/display. The declaration builtins consume it through the
    #: SAME structured expansion the bare ``a=(...)`` path uses (see
    #: ArrayOperationExecutor.build_indexed_array / build_associative_array),
    #: eliminating the old serialize-then-shlex-reparse. Ordinary commands
    #: ignore it (the flat string is the argument). ``None`` for every
    #: non-array-init word.
    array_init: Optional['ArrayInitialization'] = None

    @property
    def quote_type(self) -> Optional[str]:
        """The whole-word quote character (``'``, ``"``, ``$'``) or None.

        DERIVED from the parts — the parts are the single source of truth
        for quote context (Tier C-D1, 2026-06-13; previously this was a
        stored dataclass field duplicating per-part state). A whole-word
        quote_type exists when every part is quoted with the SAME quote
        char, and equals that char (``'abc'`` → ``'``, ``"a b"`` → ``"``,
        ``"a$b c"`` → ``"``, ``$'x'`` → ``$'``, empty ``""`` → ``"``).
        A word with any unquoted part, or parts with mixed quote chars
        (``a"b"c``, ``"a"'b'``), has no whole-word quote_type (None).
        The expansion dispatch (word_expander) reads this property.

        Note: this promotes two shapes the old STORED field left at None to
        their (uniform) quote char — adjacent same-quote composites
        (``"a""b"``) and quoted case patterns. Both are verified
        behavior-neutral: a uniformly double-quoted word expands the same
        through either dispatch branch, and case patterns are matched via
        per-part quote context (never via this property). See
        tests/unit/parser/test_word_quote_derivation.py.
        """
        parts = self.parts
        if not parts:
            return None
        first = getattr(parts[0], 'quote_char', None)
        for part in parts:
            if not getattr(part, 'quoted', False):
                return None
            if getattr(part, 'quote_char', None) != first:
                return None
        return first

    def __repr__(self) -> str:
        # Keep the historical repr shape (``Word(parts=[...],
        # quote_type=...)``) even though quote_type is now a derived
        # property, so AST-repr characterization corpora stay byte-identical.
        return f"Word(parts={self.parts!r}, quote_type={self.quote_type!r})"

    def __str__(self):
        # Debug/source rendering only. Semantic code should call the explicit
        # text methods below (source_text / display_text / to_literal_string)
        # rather than relying on str(word).
        return self.source_text()

    def source_text(self) -> str:
        """Source-shaped repr: the flattened parts re-wrapped in this word's
        quote characters (``a b`` quoted becomes ``"a b"``).

        This is what ``__str__`` returns. Use it for debug/source rendering,
        NOT for the pre-expansion text a consumer wants (see ``display_text``).
        """
        content = self.display_text()
        if self.quote_type:
            return f"{self.quote_type}{content}{self.quote_type}"
        return content

    def display_text(self) -> str:
        """Pre-expansion flattened text: the concatenation of ``str(part)``
        over this word's parts, WITHOUT re-wrapping in the whole-word quote
        characters.

        ``echo "a b"`` yields ``a b``; expansions render as their
        ``$``-source form (``${x:-d}`` -> ``${x:-d}``). This is the text
        semantic call sites want when they bypass ``__str__``'s quote
        re-wrapping; it is the basis of ``SimpleCommand.args``.
        """
        return ''.join(str(part) for part in self.parts)

    def to_literal_string(self) -> str:
        """The word's text after quote removal, with expansions unexpanded.

        Used by the expansion engine for single-quoted and ANSI-C-quoted
        words, where quote removal is the ONLY processing. Distinct from
        ``__str__``, which is a source-shaped repr that re-wraps the word
        in its quote characters; this returns the runtime value (quotes
        gone, any ExpansionPart rendered as its ``$``-source text).
        """
        chunks: List[str] = []
        for part in self.parts:
            if isinstance(part, LiteralPart):
                chunks.append(part.text)
            elif isinstance(part, ExpansionPart):
                # In single quotes, expansions are literal
                chunks.append(_expansion_literal_text(part.expansion))
        return ''.join(chunks)

    @property
    def is_quoted(self) -> bool:
        """True if wholly quoted (single, double, or ANSI-C).

        Derived from the parts: either a whole-word quote (``quote_type``
        set — every part quoted with the same char) or a single quoted
        part. The two coincide except that ``quote_type`` also covers
        uniformly-quoted multi-part words (``"a$b c"``), which were already
        ``is_quoted`` under the old stored field.
        """
        if self.quote_type in ("'", '"', "$'"):
            return True
        return (len(self.parts) == 1 and
                getattr(self.parts[0], 'quoted', False))

    @property
    def is_unquoted_literal(self) -> bool:
        """True if plain unquoted word with no expansions (old arg_type == 'WORD')."""
        if not self.parts:
            return True
        return (len(self.parts) == 1 and
                isinstance(self.parts[0], LiteralPart) and
                not self.parts[0].quoted)

    @property
    def is_variable_expansion(self) -> bool:
        """True if single variable expansion $VAR (old arg_type == 'VARIABLE')."""
        if len(self.parts) != 1:
            return False
        part = self.parts[0]
        if not isinstance(part, ExpansionPart):
            return False
        return isinstance(part.expansion, (VariableExpansion, ParameterExpansion))

    @property
    def has_expansion_parts(self) -> bool:
        """True if any part contains an expansion."""
        return any(isinstance(p, ExpansionPart) for p in self.parts)

    @property
    def has_unquoted_expansion(self) -> bool:
        """True if unquoted expansion parts exist (vulnerable to splitting/injection)."""
        return any(isinstance(p, ExpansionPart) and not p.quoted
                   for p in self.parts)

    @property
    def effective_quote_char(self) -> Optional[str]:
        """The dominant quote character, or None.

        Derived from the parts: the whole-word ``quote_type`` if the word is
        uniformly quoted (``"a$b c"`` -> ``"``), else a single part's own
        ``quote_char`` (even when not flagged quoted — preserves the
        historical single-part fallback). Multi-part words with mixed or no
        quoting have no dominant quote (None).
        """
        qt = self.quote_type
        if qt is not None:
            return qt
        if len(self.parts) == 1:
            return getattr(self.parts[0], 'quote_char', None)
        return None

    @classmethod
    def from_string(cls, text: str, quote_type: Optional[str] = None) -> 'Word':
        """Create a Word from a literal string.

        The quote context lives on the part (the parts are the single
        source of truth for quote state); ``quote_type`` here is the
        whole-word quote char to stamp onto the single LiteralPart.
        """
        return cls(parts=[LiteralPart(text, quoted=bool(quote_type),
                                      quote_char=quote_type)])


# ArrayInitialization is referenced by Word.array_init as a forward reference;
# importing it at module load time would create a cycle (arrays.py imports
# Word). The annotation is a string, so no runtime import is needed here.
if False:  # pragma: no cover - typing aid only
    from .arrays import ArrayInitialization  # noqa: F401
