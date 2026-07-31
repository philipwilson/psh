"""Token part metadata for words that carry expansions / per-part quoting.

A :class:`~psh.lexer.token_types.Token` carries a ``parts`` tuple of these; the
old ``RichToken`` Token subclass was retired with the WordToken refactor (the
base Token already has the ``parts`` field, so no subclass is needed).
"""

from dataclasses import dataclass, field
from typing import Optional

from .position import Position


@dataclass(frozen=True)
class TokenPart:
    """One part of a composite token, with its metadata.

    ``frozen``: a part is a VALUE. Once the lexer has produced it no stage
    rewrites it — a stage needing a changed part builds a new one with
    :func:`dataclasses.replace`, exactly as :class:`Token` has required since
    v0.681. Freezing the part COMPLETES that freeze: a ``Token`` was already
    immutable in its own attributes while still handing out a mutable ``parts``
    list of mutable parts, so the lexical value graph could be rewritten after
    the lexer had returned it (reappraisal #22 MEDIUM-10). Every edge of that
    graph is now immutable, enforced over the CLASS — every field, every
    container edge, discovered at runtime rather than hand-listed — by
    ``tests/unit/lexer/test_lexical_value_graph_frozen.py``.
    """
    value: str
    quote_type: Optional[str] = None  # None, "'" or '"'
    is_variable: bool = False
    is_expansion: bool = False
    expansion_type: Optional[str] = None  # Type of expansion: 'variable', 'command', 'arithmetic', etc.
    error_message: Optional[str] = None  # Error message for invalid expansions
    start_pos: Position = field(default_factory=lambda: Position(0, 1, 1))
    end_pos: Position = field(default_factory=lambda: Position(0, 1, 1))
