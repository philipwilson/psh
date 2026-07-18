"""Control-structure nodes.

Function definitions, case patterns/items, and the unified control
structures (loops, if, case, select, arithmetic command). The unified
structures inherit from both Statement and CompoundCommand so they work at
statement level and as pipeline components. (break/continue/return have no
AST nodes: they are ordinary simple commands backed by builtins, as in
bash.)
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Tuple

from .base import (
    ASTNode,
    Command,
    Statement,
    UnifiedControlStructure,
)
from .commands import StatementList
from .redirects import Redirect
from .words import Word

if TYPE_CHECKING:
    from .syntax_templates import ArithmeticTemplate  # noqa: F401


@dataclass
class FunctionDef(Statement, Command):
    """Function definition.

    A function definition is BOTH a ``Statement`` (a standalone ``f() { ...; }``
    at statement level updates the parent function table) AND a ``Command`` — a
    ``PipelineComponent`` — so it can appear as a pipeline member, negation/
    ``time`` target, and-or-list element, or background job exactly as bash's
    grammar allows (``f() { ...; } | cat``, ``! f() { :; }``, ``time f() { :; }``,
    ``x && f() { :; }``, ``f() { :; } &``). Whether the definition leaks into the
    parent follows the same fork rule as any command: a single-member pipeline
    runs in the current shell (LEAKS); a multi-member pipeline or background
    forks a child whose function-table write dies with the child (NO leak).
    (#20 H9; campaign S5.)
    """
    name: str
    body: StatementList
    # Redirections attached to the definition (f() { ...; } > file) are
    # applied at each CALL, not at definition time (bash).
    redirects: List[Redirect] = field(default_factory=list)
    # The ``Command`` interface's second field. A function definition is never
    # itself backgrounded (a trailing ``&`` backgrounds the enclosing and-or
    # list — see StatementParser._apply_background), so this is always False for
    # a FunctionDef; it exists so the pipeline executor's uniform
    # ``node.commands[-1].background`` read never trips on a FunctionDef member.
    background: bool = False


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
    # Typed carriers (campaign S3) for the three arithmetic clauses. The
    # *_expr strings stay the LAZY arithmetic-grammar authority (each clause is
    # arithmetic-parsed at its own execution point, so an unreached update
    # clause's bad arithmetic never errors — bash timing); the *_template
    # carriers hold the read-time-validated nested $() for each clause. None
    # for a missing clause / manually built node. Guard: template.text == *_expr.
    init_template: Optional['ArithmeticTemplate'] = field(
        default=None, compare=False, repr=False)
    condition_template: Optional['ArithmeticTemplate'] = field(
        default=None, compare=False, repr=False)
    update_template: Optional['ArithmeticTemplate'] = field(
        default=None, compare=False, repr=False)


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
    """Unified case statement.

    ``subject_word`` carries the parsed subject as a multi-part :class:`Word`
    with per-part quote context (like :class:`CasePattern`'s ``word``). The
    executor expands it quote-aware — tilde, parameter, command and
    arithmetic expansion, plus quote removal, but NO word splitting and NO
    globbing — so a single-quoted subject (``case '$x' in``) stays literal
    instead of being re-expanded. ``expr`` is the flattened display text,
    kept for the analysis/debug visitors and for manually built ASTs; when
    ``subject_word`` is None (a programmatically constructed node) the
    executor and formatter fall back to it.
    """
    expr: str
    items: List[CaseItem] = field(default_factory=list)
    redirects: List[Redirect] = field(default_factory=list)
    background: bool = False
    subject_word: Optional['Word'] = None


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
    # Typed carrier (campaign S3). ``expression`` stays the LAZY
    # arithmetic-grammar authority; ``arith_template`` holds the read-time-
    # validated nested $(). Guard: ``arith_template.text == expression``.
    arith_template: Optional['ArithmeticTemplate'] = field(
        default=None, compare=False, repr=False)
