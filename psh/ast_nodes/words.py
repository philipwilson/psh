"""Expansion nodes and Word nodes.

Words are the parser's representation of command arguments: each is a list
of parts (literal text or an embedded expansion) carrying per-part quote
context. The expansion nodes (``$var``, ``${...}``, ``$(...)``, ``$((...))``,
``<(...)``) live here too because the Word/part types reference
:class:`Expansion` directly.
"""

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Tuple, Union, cast

from .base import ASTNode

if TYPE_CHECKING:
    # ArrayInitialization is referenced by Word.array_init as a string forward
    # reference; a runtime import would create a cycle (arrays.py imports Word).
    from .arrays import ArrayInitialization  # noqa: F401
    from .commands import Program

    # Syntax templates (campaign S3) import Expansion FROM this module, so they
    # are string forward references here to avoid the cycle.
    from .syntax_templates import ArithmeticTemplate, SubscriptSpec, WordTemplate  # noqa: F401

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

    #: Typed operand carrier (campaign S3), set by the parser word builder for
    #: an operator form built at parse time. ``word`` remains the raw operand
    #: (the lazy pattern/word-grammar authority the operand expanders read);
    #: ``word_template`` is the read-time-validation authority — its nested
    #: modern ``$()``/``<()``/``>()`` were parsed and validated when the command
    #: was read, so ``${x:-$(if)}`` rejects at read time like bash. None on the
    #: runtime string-expansion path and for manually built nodes. Guard-
    #: consistent: ``word_template.text == word`` (test_syntax_template_guards).
    word_template: Optional['WordTemplate'] = field(
        default=None, compare=False, repr=False)

    #: Typed subscript carrier for a subscripted parameter (``${arr[SUB]}``),
    #: where SUB lives in ``parameter``. Validates a nested ``$()`` in the
    #: subscript at read time (``${a[$(if)]}``). None when the parameter has no
    #: subscript. Guard-consistent with the subscript slice of ``parameter``.
    subscript_spec: Optional['SubscriptSpec'] = field(
        default=None, compare=False, repr=False)

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

    #: Typed subscript carrier (campaign S3) for a subscripted reference
    #: (``${arr[SUB]}``, which the word builder keeps as a braced
    #: VariableExpansion with SUB inside ``name``). Read-time validates a nested
    #: ``$()`` in the subscript (``${a[$(if)]}``). None for a plain name.
    #: Excluded from eq/repr like ``braced``. Guard-consistent with the
    #: subscript slice of ``name``.
    subscript_spec: Optional['SubscriptSpec'] = field(
        default=None, compare=False, repr=False)

    def __str__(self):
        # No following-part context here: the spelling authority is
        # variable_expansion_text (see its docstring for the rule).
        return variable_expansion_text(self)


@dataclass
class ArithmeticExpansion(Expansion):
    """Represents arithmetic expansion $((...))."""
    expression: str  # The arithmetic expression

    #: Typed carrier (campaign S3), set by the parser word builder. ``expression``
    #: stays the raw text (the LAZY arithmetic-grammar authority — the arithmetic
    #: is parsed only at evaluation, so ``op='+'; $((1 $op 2))`` works);
    #: ``arith_template`` carries the read-time-validated nested ``$()``. None on
    #: the runtime path / manual nodes. Guard: ``arith_template.text == expression``.
    arith_template: Optional['ArithmeticTemplate'] = field(
        default=None, compare=False, repr=False)

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


def variable_expansion_text(expansion: 'VariableExpansion',
                            next_part: Optional[WordPart] = None,
                            separated: bool = False) -> str:
    """The source spelling of a ``$name`` reference — THE brace authority.

    Every reconstruction of shell source from a Word (``--format``,
    ``declare -f``/``type``/``export -f``, ``$BASH_COMMAND``, ``--debug-ast``,
    the ``.args`` view, diagnostics) renders a :class:`VariableExpansion`
    through this function, so the spelling is decided once. Braces are emitted
    when ANY of:

    * the name cannot be spelled bare — a subscripted reference (``arr[@]``,
      ``arr[0]``) or any non-identifier name; a bare ``$arr[@]`` re-parses as
      ``${arr}[@]`` (element 0 plus a literal ``[@]``);
    * the SOURCE wrote them (``braced``) — dropping them changes which variable
      is read, because brace expansion runs BEFORE parameter expansion and
      fuses a following name-char run into a bare name: ``${v}{1,2}`` yields
      ``${v}1``/``${v}2`` while ``$v{1,2}`` yields the names ``v1``/``v2``;
    * the next part that actually PRINTS would fuse with the name once the word
      is written back out — its text starts with a name char. Neither quoting
      nor an empty part in between saves it: the renderers close the gap the
      source's quotes left, either by merging a RUN of adjacent same-quote
      parts (a ``$v`` region, an EMPTY one and an ``x`` region are emitted as
      one ``"…"``) or by dropping quotes
      altogether (``display_text``), so ``$v`` + ``""`` + ``"x"`` would
      re-parse as the name ``vx``. The neighbour is therefore chosen by
      :func:`next_rendered_part`, which walks past zero-length parts — the
      syntactically next part is not necessarily the next one on the page.

    A bare ``$v{1,2}`` is NOT re-braced: ``{`` is not a name char, and the
    fusion into ``v1``/``v2`` is what the source asked for — ``braced`` is the
    only thing that separates it from ``${v}{1,2}``. ``separated`` flips that:
    it means the SOURCE put something between the name and ``next_part`` that a
    rendering may not preserve — a zero-length part, or a quote boundary — and
    that something already stopped the fusion. ``$v""{1,2}`` and ``"$v"{1,2}``
    both mean ``${v}1``/``${v}2``, not ``v1``/``v2`` (bash 5.3.15), so a
    renderer that drops the empty region or the quotes has to say so with
    braces.

    DELIBERATE CONSERVATISM — do not "simplify" this back. The rule serves two
    renderers that close the source's quote gap DIFFERENTLY: the formatter
    merges adjacent same-quote regions, ``display_text`` drops quotes entirely.
    Asking each caller to compute its own adjacency would put the decision back
    in two places, which is the shape of the defect this function exists to
    delete. So the rule takes the union and sometimes writes braces a minimal
    renderer would omit (``foo$v"dq"`` -> ``foo${v}"dq"``). That is safe
    everywhere except before ``{``: ``${v}`` and ``$v`` name the same parameter,
    and the special parameters brace legally and equivalently — note that a
    NAME is never invented in the process, so ``$#`` before ``x`` renders
    ``${#}x`` (``$#`` then a literal), never ``${#x}`` (the length of ``x``),
    and ``$!`` before ``x`` renders ``${!}x``, never the indirection
    ``${!x}``. Probed on bash 5.3.15 for ``? @ * # $ ! - 0 1 2``.

    The RUNTIME half of the same rule is
    ``psh/expansion/brace_expansion_words.py#_fuse_bare_variables``, which
    performs the fusion this function must anticipate; the render side has to
    stay at least as conservative as it, never less.

    Reproduce the two harms with::

        v=1 v1=A v2=B; f() { echo ${v}{1,2}; }; eval "$(declare -f f)"; f
        v=1 vx=BAD;    g() { echo "$v""x"; };   eval "$(declare -f g)"; g

    which must print ``11 12`` and ``1x`` — the direct calls' output — not
    ``A B`` and ``BAD``. The third harm is the same ``g`` with an EMPTY
    double-quoted region between the two (a shape this file cannot spell
    inside a docstring); it is written out in ``psh/visitor/CLAUDE.md`` and
    carried as the ``dq_empty_*`` rows of the round-trip corpus.
    """
    name = expansion.name
    bare_ok = bool(_BARE_VAR_NAME.match(name)) or (
        len(name) == 1 and name in _SPECIAL_PARAM_CHARS)
    if (bare_ok and not expansion.braced
            and not _fuses_with(next_part, separated)):
        return f"${name}"
    return f"${{{name}}}"


def part_source_text(parts: List[WordPart], index: int) -> str:
    """Part ``index`` of ``parts`` as source text, in its neighbours' context.

    The ONE place a word part is turned back into source: a ``$name`` goes
    through :func:`variable_expansion_text` with the next PRINTING part as
    brace context (:func:`next_rendered_part`), everything else through its own
    ``__str__``. Every consumer that rebuilds a word —
    :meth:`Word.display_text`, :meth:`Word.to_literal_string`, the formatter,
    the tilde-prefix collapse, the array-subscript and array-element flat texts
    — calls this rather than ``str(part)``, so none of them can drift into its
    own spelling rule.
    """
    part = parts[index]
    if isinstance(part, ExpansionPart) and isinstance(part.expansion,
                                                      VariableExpansion):
        nxt, separated = next_rendered_part(parts, index)
        return variable_expansion_text(part.expansion, nxt, separated)
    return str(part)


def next_rendered_part(parts: List[WordPart],
                       index: int) -> Tuple[Optional[WordPart], bool]:
    """The first part after ``index`` that PRINTS, and whether it is SEPARATED.

    THE neighbour rule, so no caller has to assemble it. Two answers, because
    the renderers need both and neither is derivable from the other:

    * the next part that actually prints. Zero-length parts are skipped: ``""``,
      ``''``, ``$''`` and ``$""`` each parse to a ``LiteralPart('')`` that
      contributes no characters, so they separate nothing in the emitted text —
      the formatter merges the whole run of same-quote parts into one region,
      and ``display_text`` drops the quotes entirely. Answering about
      ``parts[index + 1]`` would describe the SOURCE, not the page: with a
      ``$v`` region, an EMPTY region and an ``x`` region, the syntactically next
      part is the empty one while the next part on the page is ``x``, and a
      ``$v`` spelled bare in front of it re-parses as the name ``vx``.
    * whether the source kept the two apart with something a rendering may
      drop — a zero-length part walked past on the way, or a quote boundary on
      either side. That separator is invisible on the page but NOT in the
      source's meaning: it stops the name from reaching a following ``{``
      (``$v""{1,2}`` and ``"$v"{1,2}`` are ``${v}1``/``${v}2``, while
      ``$v{1,2}`` is ``v1``/``v2``), so a renderer that drops it has to put the
      braces back. Forward-only: an empty part BEFORE the name, or AFTER the
      brace list, separates nothing between them and must not brace.

    Returns ``(None, separated)`` when nothing after ``index`` prints.
    """
    # `quoted` is declared on BOTH concrete part classes; the abstract
    # ``WordPart`` base is the only reason the annotation looks wider, so the
    # cast states that rather than a defensive read inventing a default.
    separated = bool(cast(_QuotedPart, parts[index]).quoted)
    for j in range(index + 1, len(parts)):
        nxt = parts[j]
        if isinstance(nxt, LiteralPart) and not nxt.text:
            separated = True
            continue
        return nxt, separated or bool(cast(_QuotedPart, nxt).quoted)
    return None, separated


def _fuses_with(next_part: Optional[WordPart], separated: bool) -> bool:
    """Would a bare ``$name`` swallow ``next_part``'s leading text once written?

    ``next_part`` is the next part that PRINTS (:func:`next_rendered_part`),
    never blindly the syntactically next one. Only a LITERAL can fuse — another
    expansion starts with ``$``, which delimits the name — and only through its
    leading ``[A-Za-z0-9_]`` run (``$x`` + ``there`` -> ``$xthere``).

    The literal's own ``quoted`` flag is deliberately NOT consulted. A quote
    delimits the name in the SOURCE, but not in the text the renderers emit:
    ``_format_word`` merges consecutive parts that share a quote char into one
    region (``"$v"`` + ``""`` + ``"x"`` -> ``"$vx"``) and ``display_text`` drops
    quotes entirely (``$v`` + ``""`` + ``"x"`` -> ``$vx``), and either re-parses
    as the name ``vx``. Braces cost nothing where they are not needed —
    ``${v}`` and ``$v`` name the same parameter — so this errs toward emitting
    them.

    A leading ``{`` fuses only when ``separated``: a DIRECTLY adjacent, equally
    unquoted ``$v{1,2}`` re-parses to this same shape and re-fuses identically,
    so bracing it would CHANGE which variables are read. With a zero-length
    part or a quote boundary in between, the source already stopped the fusion
    and a renderer that drops that separator would restore it.
    """
    if not isinstance(next_part, LiteralPart) or not next_part.text:
        return False
    lead = next_part.text[0]
    return lead.isalnum() or lead == '_' or (separated and lead == '{')


#: The only concrete ``WordPart`` subclasses. Both declare ``quoted`` /
#: ``quote_char``; the abstract base does not, so code that reads a quote
#: context narrows to this rather than guarding with ``getattr``.
_QuotedPart = Union[LiteralPart, ExpansionPart]


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

        A ``$name`` part is spelled by :func:`variable_expansion_text` with the
        FOLLOWING part as context, so a source ``${v}{1,2}`` does not flatten
        to ``$v{1,2}`` (which names ``v1``/``v2`` instead of ``v``).
        """
        return ''.join(self.part_source_text(i)
                       for i in range(len(self.parts)))

    def part_source_text(self, index: int) -> str:
        """This word's part ``index`` as source text (:func:`part_source_text`)."""
        return part_source_text(self.parts, index)

    def to_literal_string(self) -> str:
        """The word's text after quote removal, with expansions unexpanded.

        Used by the expansion engine for single-quoted and ANSI-C-quoted
        words, where quote removal is the ONLY processing. Distinct from
        ``__str__``, which is a source-shaped repr that re-wraps the word
        in its quote characters; this returns the runtime value (quotes
        gone, any ExpansionPart rendered as its ``$``-source text).
        """
        chunks: List[str] = []
        for i, part in enumerate(self.parts):
            if isinstance(part, (LiteralPart, ExpansionPart)):
                # In single quotes an expansion is literal text: the same
                # source spelling every other reconstruction uses.
                chunks.append(self.part_source_text(i))
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
