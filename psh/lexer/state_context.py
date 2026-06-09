"""Unified state representation for the lexer."""

from dataclasses import dataclass


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

    # $((...)) tracking
    arithmetic_depth: int = 0

    # Configuration flags for Unicode/POSIX compliance
    posix_mode: bool = False

    # Case statement context tracking
    case_depth: int = 0               # Nesting depth of case..esac blocks
    case_expecting_in: bool = False   # True between 'case' and its 'in'
    in_case_pattern: bool = False     # True when next tokens are case patterns

    def enter_arithmetic(self) -> None:
        """Enter $((...)) context."""
        self.arithmetic_depth += 1

    def exit_arithmetic(self) -> None:
        """Exit $((...)) context."""
        if self.arithmetic_depth > 0:
            self.arithmetic_depth -= 1

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
