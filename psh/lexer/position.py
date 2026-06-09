#!/usr/bin/env python3
"""
Position tracking and error handling for the PSH lexer.

This module provides enhanced position tracking with line/column information
and comprehensive error handling with recovery capabilities.
"""

import bisect
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class Position:
    """Represents a position in the input text with line and column information."""
    offset: int  # Absolute position in input (0-based)
    line: int    # Line number (1-based)
    column: int  # Column number (1-based)

    def __str__(self) -> str:
        return f"line {self.line}, column {self.column}"

    def __repr__(self) -> str:
        return f"Position(offset={self.offset}, line={self.line}, column={self.column})"


class LexerError(SyntaxError):
    """Enhanced error with position and context information."""

    def __init__(self, message: str, position: Position, input_text: str, severity: str = "error"):
        self.position = position
        self.input_text = input_text
        self.severity = severity
        super().__init__(self._format_error(message))

    def _format_error(self, message: str) -> str:
        """Format error message with context and position information."""
        lines = self.input_text.splitlines()

        # Show context around error
        context_lines = []
        start_line = max(1, self.position.line - 2)
        end_line = min(len(lines), self.position.line + 2)

        for line_num in range(start_line, end_line + 1):
            if line_num <= len(lines):
                line_content = lines[line_num - 1] if line_num <= len(lines) else ""
                prefix = "  " if line_num != self.position.line else "> "
                context_lines.append(f"{prefix}{line_num:4d} | {line_content}")

                if line_num == self.position.line:
                    # Add error pointer
                    context_lines.append(f"       | {' ' * (self.position.column - 1)}^")

        return f"""
Lexer {self.severity.title()}: {message}
  at {self.position}

{chr(10).join(context_lines)}
"""


@dataclass
class LexerConfig:
    """
    Comprehensive configuration for lexer behavior and features.

    This class controls all major aspects of lexer operation including:
    - Feature enablement/disablement
    - Character handling modes
    - Performance optimizations
    - Error handling behavior
    - Debugging capabilities
    """

    # === CORE FEATURES ===

    # Quote processing
    enable_double_quotes: bool = True      # Process "..." with expansions
    enable_single_quotes: bool = True      # Process '...' as literals
    enable_backtick_quotes: bool = True    # Process `...` command substitution

    # Variable and expansion features
    enable_variable_expansion: bool = True      # Process $VAR
    enable_parameter_expansion: bool = True     # Process ${VAR:-default}
    enable_command_substitution: bool = True    # Process $(cmd)
    enable_arithmetic_expansion: bool = True    # Process $((expr))
    enable_process_substitution: bool = True    # Process <(cmd) and >(cmd)

    # Operator and syntax features
    enable_pipes: bool = True              # Process | operator
    enable_redirections: bool = True       # Process <, >, >>, etc.
    enable_background: bool = True         # Process & operator
    enable_logical_operators: bool = True  # Process && and ||
    enable_extglob: bool = False           # Process ?()|*()|+()|@()|!() extended globs


    # === CHARACTER HANDLING ===

    posix_mode: bool = False              # When True, restrict to POSIX character sets
    case_sensitive: bool = True           # Case sensitivity for identifiers

    @classmethod
    def create_interactive_config(cls) -> 'LexerConfig':
        """Configuration for interactive shell use.

        Currently identical to batch configuration: the lexer has no
        error-recovery mode, so the historical strict/recovery distinction
        had no effect and was removed.
        """
        return cls()

    @classmethod
    def create_batch_config(cls) -> 'LexerConfig':
        """Configuration for batch script processing (see
        create_interactive_config)."""
        return cls()


class PositionTracker:
    """Tracks position in input text with line and column information."""

    def __init__(self, input_text: str):
        self.input_text = input_text
        self.position = 0
        self.line = 1
        self.column = 1
        self.line_starts = [0]  # Track start position of each line

    def advance(self, count: int = 1) -> None:
        """Move position forward, updating line/column."""
        for _ in range(count):
            if self.position < len(self.input_text):
                if self.input_text[self.position] == '\n':
                    self.line += 1
                    self.column = 1
                    self.line_starts.append(self.position + 1)
                else:
                    self.column += 1
                self.position += 1

    def get_current_position(self) -> Position:
        """Get current position as a Position object."""
        return Position(self.position, self.line, self.column)

    def get_position_at_offset(self, offset: int) -> Position:
        """Get position information for a specific offset."""
        offset = max(0, min(offset, len(self.input_text)))

        # Use binary search to find the line
        line = bisect.bisect_right(self.line_starts, offset)
        line_start = self.line_starts[line - 1]
        column = offset - line_start + 1

        return Position(offset, line, column)
