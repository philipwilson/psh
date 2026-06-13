from abc import ABC
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Tuple, Union

if TYPE_CHECKING:
    from .lexer.token_types import Token


class ASTNode(ABC):
    pass


class Statement(ASTNode):
    """Base class for all statements that can appear in StatementList."""
    pass


@dataclass
class Redirect(ASTNode):
    type: str  # '<', '>', '>>', '<<', '<<-', '<>', '>|', '2>', '2>>', '2>&1', etc.
    target: str
    fd: Optional[int] = None  # File descriptor (None for stdin/stdout, 2 for stderr, etc.)
    dup_fd: Optional[int] = None  # For duplications like 2>&1
    heredoc_content: Optional[str] = None  # For here documents
    quote_type: Optional[str] = None  # Quote type used (' or " or None) for here strings
    heredoc_quoted: bool = False  # Whether heredoc delimiter was quoted (disables variable expansion)
    combined: bool = False  # True for &> and &>> (redirects both stdout and stderr)


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
    """
    direction: str  # 'in' or 'out'
    command: str    # Command to execute

    def __str__(self):
        symbol = '<' if self.direction == 'in' else '>'
        return f"{symbol}({self.command})"


@dataclass
class CommandSubstitution(Expansion):
    """Represents command substitution $(...) or `...`."""
    command: str  # The command to execute
    backtick_style: bool = False  # True for `...`, False for $(...)

    def __str__(self):
        if self.backtick_style:
            return f"`{self.command}`"
        else:
            return f"$({self.command})"


@dataclass
class ParameterExpansion(Expansion):
    """Represents parameter expansion ${...}."""
    parameter: str  # Variable name
    operator: Optional[str] = None  # :-, :=, :?, :+, #, ##, %, %%, /, // etc.
    word: Optional[str] = None  # The word part for operators like ${var:-word}

    def __str__(self):
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

    def __str__(self):
        return f"${self.name}"


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
            return f"`{expansion.command}`"
        else:
            return f"$({expansion.command})"
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


# =============================================================================
# ARRAY ASSIGNMENT NODES (defined early for use in SimpleCommand)
# =============================================================================

@dataclass
class ArrayAssignment(ASTNode):
    """Base class for array assignments."""
    pass


def _word_element_type(word: 'Word') -> str:
    """Legacy element-type string DERIVED from a Word's quote context.

    Reproduces the value the parsers used to STORE in
    ``ArrayInitialization.element_types`` (display/tooling metadata only;
    the executor never reads it). The recursive-descent parser computed
    this exact mapping from the element Word; deriving it here keeps the
    formatter/validator output byte-identical after the stored field was
    dropped (A2, 2026-06-13).
    """
    if word.is_quoted:
        return 'STRING'
    if any(getattr(p, 'quoted', False) for p in word.parts):
        return 'COMPOSITE_QUOTED'
    if len(word.parts) > 1:
        return 'COMPOSITE'
    return 'WORD'


@dataclass
class ArrayInitialization(ArrayAssignment):
    """Array initialization: arr=(one two three) or arr+=(four five)"""
    name: str
    elements: List[str]  # The elements inside parentheses (flat strings)
    is_append: bool = False  # True for += initialization
    # Word AST nodes for each element (REQUIRED, parallel to `elements`).
    # Both parsers always populate this; the executor expands each element
    # through the same Word expansion pipeline as command arguments (IFS
    # splitting, quote-aware globbing, tilde, noglob/nullglob/dotglob) and
    # raises an internal error on a missing Word (fallback audit 2026-06-12).
    words: List[Word] = field(default_factory=list)

    # Legacy string-list metadata, now DERIVED from `words` rather than
    # stored. Sole consumers: formatter_visitor / validator_visitor
    # (the executor uses `words` exclusively). A2 dropped the parallel
    # stored fields so a node can no longer "claim two truths at once".
    @property
    def element_types(self) -> List[str]:
        """Per-element legacy type string (WORD/STRING/COMPOSITE/…)."""
        return [_word_element_type(w) for w in self.words]

    @property
    def element_quote_types(self) -> List[Optional[str]]:
        """Per-element dominant quote char, derived from each Word."""
        return [w.effective_quote_char for w in self.words]


@dataclass
class ArrayElementAssignment(ArrayAssignment):
    """Array element assignment: arr[0]=value or arr[0]+=value"""
    name: str
    index: Union[str, List['Token']]  # The index expression (str for compatibility, List[Token] for late binding)
    value: str  # The value to assign
    # Word AST node for the value (REQUIRED — no default). Both parsers
    # always build it; the executor expands it with bash assignment-value
    # semantics (all expansions, no word splitting, no pathname expansion,
    # tilde after '='/':'). The A1 invariant tests enforce population.
    value_word: Word
    is_append: bool = False  # True for += assignment

    # Legacy string metadata, now DERIVED from `value_word` rather than
    # stored. Sole consumer: formatter_visitor (re-quotes the value).
    @property
    def value_type(self) -> str:
        """'STRING' if the value Word is quoted, else 'WORD' (derived)."""
        return 'STRING' if self.value_word.is_quoted else 'WORD'

    @property
    def value_quote_type(self) -> Optional[str]:
        """The value Word's dominant quote char (derived)."""
        return self.value_word.effective_quote_char


class Command(ASTNode):
    """Base class for all executable commands."""
    pass


@dataclass
class SimpleCommand(Command):
    """Traditional command with arguments (formerly Command class).

    ``words`` is the single source of truth for the command's arguments:
    one Word per argument, carrying per-part quote context and expansion
    structure. The string view ``args`` is DERIVED from it (see the
    property below) — there is no stored string list to keep in sync.
    """
    redirects: List[Redirect] = field(default_factory=list)
    background: bool = False
    array_assignments: List[ArrayAssignment] = field(default_factory=list)  # Array assignments before command
    words: List[Word] = field(default_factory=list)  # Args as Word objects with expansions

    @property
    def args(self) -> List[str]:
        """Pre-expansion string view of ``words`` — derived, never stored.

        One string per Word: the concatenation of ``str(part)`` over the
        word's parts. This is the word WITHOUT its surrounding quotes
        (``echo "a b"`` yields ``a b``) but with expansions rendered as
        their ``$``-source form (``echo ${x:-d}`` yields ``${x:-d}``;
        note a braced simple variable normalizes: ``${y}`` renders
        ``$y``). Consumers: assignment-prefix extraction (name side
        only), command-name dispatch checks, and read-only tooling
        (visitors, --debug-ast, formatters). Execution semantics always
        come from ``words`` via the expansion engine, never from this
        view. Recomputed per access — do not mutate the returned list.
        """
        return [word.display_text() for word in self.words]


class CompoundCommand(Command):
    """Base class for control structures usable in pipelines."""
    pass


@dataclass
class SubshellGroup(CompoundCommand):
    """Represents a subshell group (...) that executes in an isolated environment."""
    statements: 'CommandList'
    redirects: List[Redirect] = field(default_factory=list)
    background: bool = False


@dataclass
class BraceGroup(CompoundCommand):
    """Represents a brace group {...} that executes in the current shell environment.

    Unlike subshells, brace groups:
    - Execute in the current shell process (no fork)
    - Variable assignments persist to the parent environment
    - Directory changes (cd) affect the parent shell
    - Are more efficient (no subprocess overhead)

    POSIX syntax requirements:
    - Must have space after opening brace: { command
    - Must have semicolon or newline before closing brace: command; }
    """
    statements: 'CommandList'
    redirects: List[Redirect] = field(default_factory=list)
    background: bool = False


@dataclass
class Pipeline(ASTNode):
    commands: List[Command] = field(default_factory=list)  # Now accepts both SimpleCommand and CompoundCommand
    negated: bool = False  # True if pipeline is prefixed with !
    pipe_stderr: List[bool] = field(default_factory=list)  # pipe_stderr[i] True if |& between commands[i] and commands[i+1]


@dataclass
class AndOrList(Statement):
    pipelines: List[Pipeline] = field(default_factory=list)
    operators: List[str] = field(default_factory=list)  # '&&' or '||' between pipelines
    background: bool = False  # trailing '&' backgrounds the whole list (POSIX)


@dataclass
class StatementList(ASTNode):
    """Container for statements (control structures, AndOrLists, etc)."""
    statements: List[Statement] = field(default_factory=list)

    @property
    def and_or_lists(self):
        """Extract AndOrList nodes from statements."""
        return [s for s in self.statements if isinstance(s, AndOrList)]


CommandList = StatementList


@dataclass
class FunctionDef(Statement):
    """Function definition."""
    name: str
    body: StatementList
    # Redirections attached to the definition (f() { ...; } > file) are
    # applied at each CALL, not at definition time (bash).
    redirects: List[Redirect] = field(default_factory=list)



@dataclass
class BreakStatement(Statement, CompoundCommand):
    """Break statement to exit loops."""
    level: int = 1  # Number of loops to break out of (default 1)
    redirects: List[Redirect] = field(default_factory=list)  # Required for Command interface
    background: bool = False  # Required for Command interface


@dataclass
class ContinueStatement(Statement, CompoundCommand):
    """Continue statement to skip to next iteration."""
    level: int = 1  # Number of loops to continue to (default 1)
    redirects: List[Redirect] = field(default_factory=list)  # Required for Command interface
    background: bool = False  # Required for Command interface


@dataclass
class CasePattern(ASTNode):
    """A single pattern in a case statement.

    ``word`` carries the per-part quote context when built by the
    recursive descent parser: quoted text matches literally while
    unquoted glob characters stay active. ``pattern`` is the flattened
    text, kept for display and for the combinator parser.
    """
    pattern: str
    word: Optional['Word'] = None


@dataclass
class CaseItem(ASTNode):
    """A case item: patterns + commands + terminator."""
    patterns: List[CasePattern] = field(default_factory=list)
    commands: StatementList = field(default_factory=lambda: StatementList())
    terminator: str = ';;'  # ';;', ';&', or ';;&'



@dataclass
class TopLevel(ASTNode):
    """Root node that can contain functions and/or commands."""
    items: List[Union[Statement, StatementList]] = field(default_factory=list)  # List of Statement or StatementList


# Enhanced test expressions for [[ ]]
class TestExpression(ASTNode):
    """Base class for test expressions."""
    pass


@dataclass
class BinaryTestExpression(TestExpression):
    """Binary test expression like STRING1 < STRING2.

    Operands are :class:`Word` nodes (Tier C-D2, 2026-06-13): quote context
    comes from the Word's parts, like everywhere else in the AST, replacing
    the former plain-string operands plus ``left_quote_type``/
    ``right_quote_type`` side-channels. ``left_quote_type`` was dead (no
    consumer) and is gone; ``right_quote_type`` is now a derived read-only
    property keyed off ``right_word.is_quoted`` for the evaluator's
    quoted-pattern/regex literal-matching path.

    ``left``/``right`` remain available as derived read-only strings (the
    operand's pre-expansion text) for the formatters/debug visitors.
    """
    left_word: 'Word'
    operator: str  # =, !=, <, >, =~, -eq, -ne, etc.
    right_word: 'Word'

    @property
    def left(self) -> str:
        """Pre-expansion text of the left operand (derived from the Word)."""
        return self.left_word.display_text()

    @property
    def right(self) -> str:
        """Pre-expansion text of the right operand (derived from the Word)."""
        return self.right_word.display_text()

    @property
    def right_quote_type(self) -> Optional[str]:
        """Legacy quote-type signal for the right operand, derived from the
        Word. The evaluator's quoted-literal vs glob/regex decision only
        needs the boolean "is the whole operand quoted"; this returns the
        dominant quote char when so (so ``is not None`` reproduces the old
        ``right_quote_type is not None``), else None — exactly matching the
        former stored field for every operand shape the parser builds
        (wholly-quoted -> set; unquoted or mixed-quote -> None)."""
        if self.right_word.is_quoted:
            return self.right_word.effective_quote_char or '"'
        return None


@dataclass
class UnaryTestExpression(TestExpression):
    """Unary test expression like -f FILE."""
    operator: str  # -f, -d, -z, -n, etc.
    operand: str


@dataclass
class CompoundTestExpression(TestExpression):
    """Compound test expression with && or ||."""
    left: TestExpression
    operator: str  # && or ||
    right: TestExpression


@dataclass
class NegatedTestExpression(TestExpression):
    """Negated test expression with !."""
    expression: TestExpression


@dataclass
class EnhancedTestStatement(Statement):
    """Enhanced test construct [[ ... ]]."""
    expression: TestExpression  # The test expression to evaluate
    redirects: List[Redirect] = field(default_factory=list)


# =============================================================================
# UNIFIED CONTROL STRUCTURE TYPES
# =============================================================================
# These types serve as both Statement and Command: each inherits from both
# Statement and CompoundCommand, so a control structure can appear at
# statement level or as a pipeline component.


class UnifiedControlStructure(Statement, CompoundCommand):
    """Base class for unified control structures."""
    pass


@dataclass
class WhileLoop(UnifiedControlStructure):
    """Unified while loop that can be both Statement and Command."""
    condition: StatementList  # The command list that determines continue/stop
    body: StatementList       # Commands to execute repeatedly while condition is true
    redirects: List[Redirect] = field(default_factory=list)
    background: bool = False  # Only used in pipeline context


@dataclass
class UntilLoop(UnifiedControlStructure):
    """Unified until loop that can be both Statement and Command."""
    condition: StatementList  # The command list that determines loop termination
    body: StatementList       # Commands to execute repeatedly until condition is true
    redirects: List[Redirect] = field(default_factory=list)
    background: bool = False


@dataclass
class ForLoop(UnifiedControlStructure):
    """Unified for loop that can be both Statement and Command."""
    variable: str           # The loop variable name
    items: List[str]        # List of items to iterate over
    body: StatementList     # Commands to execute for each iteration
    redirects: List[Redirect] = field(default_factory=list)
    background: bool = False  # Only used in pipeline context
    # Word AST nodes for the items. The executor expands these through
    # ExpansionManager.expand_word_to_fields() so IFS splitting, globbing,
    # tilde and quote semantics match simple-command arguments. Both
    # parsers always populate this (A1 invariant tests enforce it); the
    # default empty list is only for manually constructed ASTs.
    item_words: List[Word] = field(default_factory=list)


@dataclass
class CStyleForLoop(UnifiedControlStructure):
    """Unified C-style for loop."""
    body: StatementList = field(default_factory=lambda: StatementList())
    init_expr: Optional[str] = None
    condition_expr: Optional[str] = None
    update_expr: Optional[str] = None
    redirects: List[Redirect] = field(default_factory=list)
    background: bool = False


@dataclass
class IfConditional(UnifiedControlStructure):
    """Unified if/then/else conditional."""
    condition: StatementList
    then_part: StatementList
    elif_parts: List[Tuple[StatementList, StatementList]] = field(default_factory=list)
    else_part: Optional[StatementList] = None
    redirects: List[Redirect] = field(default_factory=list)
    background: bool = False


@dataclass
class CaseConditional(UnifiedControlStructure):
    """Unified case statement."""
    expr: str
    items: List[CaseItem] = field(default_factory=list)
    redirects: List[Redirect] = field(default_factory=list)
    background: bool = False


@dataclass
class SelectLoop(UnifiedControlStructure):
    """Unified select statement."""
    variable: str
    items: List[str]
    body: StatementList
    redirects: List[Redirect] = field(default_factory=list)
    background: bool = False
    # Word AST nodes for the items (see ForLoop.item_words). Both parsers
    # always populate this; the default empty list is only for manually
    # constructed ASTs.
    item_words: List[Word] = field(default_factory=list)


@dataclass
class ArithmeticEvaluation(UnifiedControlStructure):
    """Unified arithmetic command."""
    expression: str
    redirects: List[Redirect] = field(default_factory=list)
    background: bool = False

