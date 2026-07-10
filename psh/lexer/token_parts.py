"""Token part metadata for words that carry expansions / per-part quoting.

A :class:`~psh.lexer.token_types.Token` carries a ``parts`` list of these; the
old ``RichToken`` Token subclass was retired with the WordToken refactor (the
base Token already has the ``parts`` field, so no subclass is needed).
"""

from dataclasses import dataclass, field
from typing import Optional

from .position import Position


@dataclass
class TokenPart:
    """Represents a part of a composite token with metadata."""
    value: str
    quote_type: Optional[str] = None  # None, "'" or '"'
    is_variable: bool = False
    is_expansion: bool = False
    expansion_type: Optional[str] = None  # Type of expansion: 'variable', 'command', 'arithmetic', etc.
    error_message: Optional[str] = None  # Error message for invalid expansions
    start_pos: Position = field(default_factory=lambda: Position(0, 1, 1))
    end_pos: Position = field(default_factory=lambda: Position(0, 1, 1))
