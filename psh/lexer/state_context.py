"""Explicit lexical state for the lexer's command-position / case machine.

The lexer threads a small amount of cross-token state through tokenization so
the recognizers can answer context-sensitive questions (is ``[[`` the test
operator or a glob? is ``}`` a reserved word? is ``in`` the case keyword?).
That state used to be an ad-hoc cluster of booleans on a ``LexerContext``
dataclass; it is now an explicit :class:`LexicalState` whose single mutator is
:func:`psh.lexer.command_position.advance_lexical_state` (the ONE lexer-stage
transition function).

Two independent axes make up the state:

* **Command position** — :class:`LexicalRole` (COMMAND_POSITION vs ARGUMENT).
  At command position a reserved word is recognized as a keyword and operators
  like ``[[`` / ``}`` / ``!`` are enabled; as an argument the same spellings
  are ordinary words.
* **Case-statement phase** — the ``case_depth`` / ``case_expecting_in`` /
  ``in_case_pattern`` fields. These are deliberately kept as INDEPENDENT bits
  rather than collapsed into a single phase enum: a malformed input such as
  ``case x ;;`` can leave ``case_expecting_in`` and ``in_case_pattern`` both
  True at once (verified), so a single mutually-exclusive phase would silently
  change behavior on degenerate inputs. :class:`CasePhase` is offered only as a
  read-only derived VIEW (see :pyattr:`LexicalState.case_phase`).

The two axes are genuinely orthogonal — e.g. command position is True while a
case is in its BODY right after a pattern's ``)`` — so neither is derivable
from the other, and a single unified ``role`` enum cannot represent the whole
state. ``bracket_depth`` and ``arithmetic_depth`` are simple nesting counters
tracked alongside.
"""

from enum import Enum
from typing import Optional, Tuple


class LexicalRole(Enum):
    """The role the NEXT token plays in the command dimension.

    The lexer's binary command-position axis, made explicit. The finer
    for/select/case-subject and function-name roles are NOT tracked here: they
    belong to a later pipeline stage (the ``KeywordNormalizer``), which
    deliberately keeps its own machine — see ``command_position.py`` for why
    the stages' transitions are irreducibly separate.
    """

    COMMAND_POSITION = 'command'
    ARGUMENT = 'argument'


class CasePhase(Enum):
    """Read-only VIEW of the lexer's ``case`` phase (introspection / tests).

    NOT the stored representation. The underlying ``case_expecting_in`` and
    ``in_case_pattern`` flags are independent bits (a malformed ``case x ;;``
    sets both), so this phase is a derived summary with a fixed precedence, not
    a single source of truth.
    """

    NOT_IN_CASE = 'none'
    EXPECTING_IN = 'expecting_in'   # after `case` subject, before `in`
    PATTERN = 'pattern'             # collecting patterns (`[`/`[[` are globs)
    BODY = 'body'                   # inside a case arm's command list


class LexicalState:
    """Cross-token state the lexer threads through tokenization.

    Tracks the state the recognizers consult: command position (as a
    :class:`LexicalRole`), ``[[ ]]`` nesting, ``(( ))`` nesting, POSIX mode,
    and case-statement pattern context. Mutated in place through tokenization;
    its sole transition function is
    :func:`psh.lexer.command_position.advance_lexical_state`.

    The constructor accepts ``command_position`` (a bool) rather than a role,
    keeping the historical construction signature
    (``LexicalState(command_position=True, bracket_depth=1)``) working for the
    recognizer tests that build states directly.
    """

    __slots__ = (
        'role', 'bracket_depth', 'arithmetic_depth', 'case_depth',
        'case_expecting_in', 'in_case_pattern', 'posix_mode',
        'assignment_map_cache',
    )

    def __init__(
        self,
        *,
        command_position: bool = True,
        bracket_depth: int = 0,
        arithmetic_depth: int = 0,
        case_depth: int = 0,
        case_expecting_in: bool = False,
        in_case_pattern: bool = False,
        posix_mode: bool = False,
        assignment_map_cache: Optional[Tuple[str, bytearray]] = None,
    ) -> None:
        # Command-position axis, stored as a role; `command_position` derives it.
        self.role = (
            LexicalRole.COMMAND_POSITION if command_position
            else LexicalRole.ARGUMENT)

        # [[ ]] nesting (replaces the old in_double_brackets bool).
        self.bracket_depth = bracket_depth

        # Arithmetic paren nesting inside a `(( ))` command / C-style for
        # header, counted per individual paren (`((`/`))` = 2, single `(`/`)`
        # = 1). Note: `$((...))` expansion is a single token and never touches
        # this counter.
        self.arithmetic_depth = arithmetic_depth

        # Case-statement context. These three are INDEPENDENT bits (see the
        # module docstring): do not assume mutual exclusivity.
        self.case_depth = case_depth               # case..esac nesting depth
        self.case_expecting_in = case_expecting_in  # between `case` and its `in`
        self.in_case_pattern = in_case_pattern      # next tokens are patterns

        # Unicode/POSIX compliance flag.
        self.posix_mode = posix_mode

        # Per-input cache for the assignment-prefix map: (input_text, map).
        # Built once per input by word_scanners.build_assignment_prefix_map and
        # shared by ModularLexer's quote dispatch and the literal recognizer
        # (see word_scanners.cached_assignment_prefix_map).
        self.assignment_map_cache = assignment_map_cache

    # -- command-position axis (LexicalRole) ------------------------------

    @property
    def command_position(self) -> bool:
        """True when the next token is at command position (role COMMAND)."""
        return self.role is LexicalRole.COMMAND_POSITION

    @command_position.setter
    def command_position(self, value: bool) -> None:
        self.role = (
            LexicalRole.COMMAND_POSITION if value else LexicalRole.ARGUMENT)

    def reset_command_position(self) -> None:
        """Move to argument position (non-command)."""
        self.role = LexicalRole.ARGUMENT

    def set_command_position(self) -> None:
        """Move to command position."""
        self.role = LexicalRole.COMMAND_POSITION

    # -- case-statement phase (derived VIEW) ------------------------------

    @property
    def case_phase(self) -> CasePhase:
        """A derived summary of the case flags (read-only; see CasePhase).

        Fixed precedence so the degenerate ``(expecting_in and in_pattern)``
        combo maps deterministically; the stored flags remain authoritative.
        """
        if self.case_expecting_in:
            return CasePhase.EXPECTING_IN
        if self.in_case_pattern:
            return CasePhase.PATTERN
        if self.case_depth > 0:
            return CasePhase.BODY
        return CasePhase.NOT_IN_CASE

    # -- lifecycle --------------------------------------------------------

    def copy(self) -> "LexicalState":
        """A snapshot of the cross-line state, for resuming a lexer.

        Carries every semantic field (command position, bracket / case /
        arithmetic state) but drops ``assignment_map_cache`` — that cache is
        keyed by input-string identity, so a fresh lexer over a new input
        rebuilds it lazily. Used by the heredoc driver to seed the next
        logical command's lexer with the state left by the previous one
        instead of re-lexing the whole accumulated prefix.
        """
        return LexicalState(
            command_position=self.command_position,
            bracket_depth=self.bracket_depth,
            arithmetic_depth=self.arithmetic_depth,
            case_depth=self.case_depth,
            case_expecting_in=self.case_expecting_in,
            in_case_pattern=self.in_case_pattern,
            posix_mode=self.posix_mode,
            assignment_map_cache=None,
        )

    def __repr__(self) -> str:
        """Human-readable representation of the state."""
        parts = []
        if self.bracket_depth > 0:
            parts.append(f"brackets={self.bracket_depth}")
        if self.arithmetic_depth > 0:
            parts.append(f"arithmetic={self.arithmetic_depth}")
        if self.command_position:
            parts.append("cmd_pos")
        if self.case_depth > 0:
            parts.append(f"case={self.case_phase.value}({self.case_depth})")
        return f"LexicalState({', '.join(parts)})"

    __str__ = __repr__


# Backward-compatible public alias. ``LexerContext`` is the historical name for
# this object (still imported by the recognizers as a type annotation and by
# tests that construct it directly); it is retained as an alias so that public
# API and existing call sites keep working unchanged.
LexerContext = LexicalState
