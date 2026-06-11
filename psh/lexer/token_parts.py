"""Token part classes for composite tokens."""

from dataclasses import dataclass, field
from typing import List, Optional

from .position import Position
from .token_types import Token


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


@dataclass
class RichToken(Token):
    """Enhanced token with metadata about its parts."""
    parts: List[TokenPart] = field(default_factory=list)
    is_composite: bool = False

    @classmethod
    def from_token(cls, token: Token, parts: Optional[List[TokenPart]] = None) -> 'RichToken':
        """Create RichToken from regular Token."""
        return cls(
            type=token.type,
            value=token.value,
            position=token.position,
            end_position=token.end_position,
            quote_type=token.quote_type,
            adjacent_to_previous=token.adjacent_to_previous,
            line=token.line,
            column=token.column,
            parts=parts or [],
            is_composite=bool(parts and len(parts) > 1)
        )
