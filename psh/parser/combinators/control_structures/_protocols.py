"""Type-only Protocol for the ControlStructureParsers mixins.

``ControlStructureParsers`` (``__init__.py``) is composed from three
mixins — ``LoopParserMixin`` (loops.py), ``ConditionalParserMixin``
(conditionals.py), and ``StructureParserMixin`` (structures.py). Each
mixin references attributes set in ``ControlStructureParsers.__init__``
(``self.commands``, ``self.tokens``) and shared helper methods the composing
class inherits from ``TrailingRedirectMixin``
(``self._parse_trailing_redirects``, whose sole definition lives in
``combinators/trailing_redirects.py``). mypy cannot see those when checking
a mixin in isolation.

``ControlStructureProtocol`` declares exactly that shared surface so the
mixins type-check. It is purely a typing artifact: each mixin declares it
as a base **only** under ``TYPE_CHECKING`` (so there is no runtime MRO or
behavior change), and ``ControlStructureParsers`` structurally satisfies
it.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List, Protocol, Tuple

if TYPE_CHECKING:
    from ....ast_nodes import Redirect
    from ....lexer.token_types import Token
    from ..commands import CommandParsers
    from ..core import Parser
    from ..tokens import TokenParsers


class ControlStructureProtocol(Protocol):
    """Attributes and shared helpers the control-structure mixins use."""

    # Attributes set in ControlStructureParsers.__init__ / wiring
    commands: "CommandParsers"
    tokens: "TokenParsers"
    _compound_body: "Parser"

    # Shared helper inherited from TrailingRedirectMixin
    # (combinators/trailing_redirects.py) — the package-wide owner.
    def _parse_trailing_redirects(
        self, tokens: List["Token"], pos: int
    ) -> Tuple[List["Redirect"], int]: ...
