"""Unified state representation for the lexer."""

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class LexerContext:
    """
    Unified state representation for the lexer.

    Tracks the cross-token state the recognizers actually consult:
    [[ ]] nesting, $((...)) nesting, command position, POSIX mode, and
    case-statement pattern context.
    """
    bracket_depth: int = 0  # [[ ]] nesting (replaces in_double_brackets)
    command_position: bool = True

    # Arithmetic paren nesting inside a `(( ))` command / C-style for header,
    # counted per individual paren (`((`/`))` = 2, single `(`/`)` = 1). Note:
    # `$((...))` expansion is a single token and never touches this counter.
    arithmetic_depth: int = 0

    # Configuration flags for Unicode/POSIX compliance
    posix_mode: bool = False

    # Case statement context tracking
    case_depth: int = 0               # Nesting depth of case..esac blocks
    case_expecting_in: bool = False   # True between 'case' and its 'in'
    in_case_pattern: bool = False     # True when next tokens are case patterns

    # Per-input cache for the assignment-prefix map: (input_text, map).
    # Built once per input by word_scanners.build_assignment_prefix_map and
    # shared by ModularLexer's quote dispatch and the literal recognizer
    # (see word_scanners.cached_assignment_prefix_map).
    assignment_map_cache: Optional[Tuple[str, bytearray]] = None

    def reset_command_position(self) -> None:
        """Reset to non-command position."""
        self.command_position = False

    def set_command_position(self) -> None:
        """Set to command position."""
        self.command_position = True

    def __str__(self) -> str:
        """Human-readable representation of the context."""
        parts = []
        if self.bracket_depth > 0:
            parts.append(f"brackets={self.bracket_depth}")
        if self.arithmetic_depth > 0:
            parts.append(f"arithmetic={self.arithmetic_depth}")
        if self.command_position:
            parts.append("cmd_pos")
        if self.case_depth > 0:
            parts.append(f"case_depth={self.case_depth}")
        return f"LexerContext({', '.join(parts)})"
