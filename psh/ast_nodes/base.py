"""Base AST classes and the shared abstract bases.

These are the roots every other ``ast_nodes`` submodule imports from. They
carry no dataclass fields of their own — they only establish the type
hierarchy (so dispatch/introspection can group nodes) and the
Statement/Command mixin split that lets control structures appear both at
statement level and as pipeline components.
"""

from abc import ABC
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from .redirects import Redirect


class ASTNode(ABC):
    # Source line of this node's first token, for the ``$LINENO`` special
    # variable. The parser stamps it buffer-relative; the source processor
    # then offsets it to an absolute file/-c/eval line once per buffer (so a
    # function body bakes in its DEFINITION-site lines). ``None`` until
    # stamped. This is a plain class attribute, NOT a dataclass field —
    # ASTNode is not a dataclass, so concrete @dataclass subclasses neither
    # collect it as a field nor include it in their generated
    # ``__init__``/``__eq__``/``__repr__``. Setting ``node.line = N`` creates
    # an instance attribute; equality/repr of AST nodes is unaffected.
    line: Optional[int] = None


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
