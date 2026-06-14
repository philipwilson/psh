"""Base AST classes and the shared abstract bases.

These are the roots every other ``ast_nodes`` submodule imports from. They
carry no dataclass fields of their own — they only establish the type
hierarchy (so dispatch/introspection can group nodes) and the
Statement/Command mixin split that lets control structures appear both at
statement level and as pipeline components.
"""

from abc import ABC
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .redirects import Redirect


class ASTNode(ABC):
    pass


class Statement(ASTNode):
    """Base class for all statements that can appear in StatementList."""
    pass


class Command(ASTNode):
    """Base class for all executable commands."""

    # Every concrete Command subclass is a dataclass that declares its own
    # ``redirects``/``background`` fields (the Command interface); these bare
    # annotations only document that contract for type-checkers. They assign
    # no value, so they create no class attribute and are NOT collected by
    # subclass ``@dataclass`` decorators (those only inherit fields from
    # dataclass bases) — zero runtime effect.
    if TYPE_CHECKING:
        redirects: List["Redirect"]
        background: bool


class CompoundCommand(Command):
    """Base class for control structures usable in pipelines."""
    pass


class UnifiedControlStructure(Statement, CompoundCommand):
    """Base class for unified control structures.

    These types serve as both Statement and Command: each inherits from both
    Statement and CompoundCommand, so a control structure can appear at
    statement level or as a pipeline component.
    """
    pass
