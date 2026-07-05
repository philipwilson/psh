"""Command and list-container nodes.

The executable command (:class:`SimpleCommand`), the grouping compound
commands (subshell/brace), and the list containers that thread statements
together (:class:`Pipeline`, :class:`AndOrList`, :class:`StatementList`,
:class:`Program`).
"""

from dataclasses import dataclass, field
from typing import List

from .arrays import ArrayAssignment
from .base import ASTNode, Command, CompoundCommand, Statement
from .redirects import Redirect
from .words import Word


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


@dataclass
class SubshellGroup(CompoundCommand):
    """Represents a subshell group (...) that executes in an isolated environment."""
    statements: 'StatementList'
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
    statements: 'StatementList'
    redirects: List[Redirect] = field(default_factory=list)
    background: bool = False


@dataclass
class Pipeline(ASTNode):
    commands: List[Command] = field(default_factory=list)  # Now accepts both SimpleCommand and CompoundCommand
    negated: bool = False  # True if pipeline is prefixed with !
    pipe_stderr: List[bool] = field(default_factory=list)  # pipe_stderr[i] True if |& between commands[i] and commands[i+1]
    timed: bool = False        # True if prefixed with the `time` reserved word
    time_posix: bool = False   # True for `time -p` (POSIX timing output format)


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


@dataclass
class Program(ASTNode):
    """Root of one parsed shell input unit.

    The single canonical result type of both parsers for EVERY parse,
    including empty input. Its ``statements`` are the ordinary statements the
    command-list grammar produces (``AndOrList`` / ``FunctionDef``), each with
    its normal ``AndOrList -> Pipeline`` ancestry — a bare compound is NOT
    unwrapped at the root. Nested command bodies (loop/if/function/group
    interiors) still use :class:`StatementList`; ``Program`` is only ever the
    root, and gives program-wide metadata (source path, span, diagnostics) a
    single natural owner.
    """
    statements: List[Statement] = field(default_factory=list)
