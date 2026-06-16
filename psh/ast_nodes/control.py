"""Control-structure nodes.

Function definitions, break/continue, case patterns/items, and the unified
control structures (loops, if, case, select, arithmetic command). The
unified structures inherit from both Statement and CompoundCommand so they
work at statement level and as pipeline components.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .base import (
    ASTNode,
    CompoundCommand,
    Statement,
    UnifiedControlStructure,
)
from .commands import StatementList
from .redirects import Redirect
from .words import Word


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
    level: int = 1  # Literal default level (used when level_words is empty)
    # The raw argument words (``break $n``, ``break foo``, the error case
    # ``break 1 2``). bash validates the level at RUNTIME (a never-executed
    # ``break foo`` is not an error) and the argument may be a non-literal
    # expansion — so the executor expands and validates these. Empty means
    # no argument; more than one resulting field is "too many arguments".
    level_words: List[Word] = field(default_factory=list)
    redirects: List[Redirect] = field(default_factory=list)  # Required for Command interface
    background: bool = False  # Required for Command interface


@dataclass
class ContinueStatement(Statement, CompoundCommand):
    """Continue statement to skip to next iteration."""
    level: int = 1  # Literal default level (used when level_words is empty)
    level_words: List[Word] = field(default_factory=list)  # raw arg words (see BreakStatement)
    redirects: List[Redirect] = field(default_factory=list)  # Required for Command interface
    background: bool = False  # Required for Command interface


def literal_loop_control_level(node) -> Optional[int]:
    """Best-effort STATIC level for a break/continue node.

    The int level if it is statically knowable — a single literal-integer
    argument word, or the int ``level`` field when there is no argument
    word. None when the level is a non-literal expansion (``break $n``)
    that can only be resolved at runtime, or when the argument is not a
    plain integer. For static analysis (validator) and pretty-printing.
    """
    words = node.level_words
    if not words:
        return node.level
    if len(words) != 1:
        return None
    try:
        return int(words[0].source_text())
    except ValueError:
        return None


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
