#!/usr/bin/env python3
"""
Position tracking for the PSH lexer.

Provides ``Position``/``SourceMap``/``PositionTracker`` (offset ↔ line/column
resolution and line-text lookup) plus ``LexerConfig`` and the lexer's one
structural error, ``UnclosedQuoteError``.
"""

import bisect
from dataclasses import dataclass
from typing import Optional

from ..core.exceptions import PshError


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


class SourceMap:
    """Immutable line/column + line-text map for one source string.

    A single place that knows a source's line structure. The lexer resolves
    token offsets to ``Position``s through :meth:`location`; the parser reads
    error-context source lines through :meth:`line_text`.

    Two line conventions are kept deliberately, matching pre-existing behavior
    exactly: :meth:`location` counts lines by ``\\n`` only (the lexer's cursor
    advances the line number solely on ``\\n``), while :meth:`line_text` uses
    ``str.splitlines`` (what the parser's error context has always sliced). For
    ordinary ``\\n``-delimited input the two agree; they differ only for input
    containing bare ``\\r`` / other Unicode line boundaries, where both halves
    reproduce the shell's long-standing behavior.
    """

    def __init__(self, source: str):
        self._source = source
        # Start offset of each line, counting boundaries at '\n' only.
        starts = [0]
        for i, ch in enumerate(source):
            if ch == '\n':
                starts.append(i + 1)
        self._line_starts = starts
        # Line text for error display (splitlines drops the terminators).
        self._lines = source.splitlines()

    @property
    def line_starts(self) -> list:
        """Offsets where each line begins ('\\n'-delimited). Copy — read-only."""
        return list(self._line_starts)

    @property
    def lines(self) -> list:
        """Source lines (``str.splitlines``), for error display. Copy."""
        return list(self._lines)

    def location(self, offset: int) -> Position:
        """Resolve an absolute offset to a 1-based (line, column) Position.

        Offsets are clamped into ``[0, len(source)]``.
        """
        offset = max(0, min(offset, len(self._source)))
        line = bisect.bisect_right(self._line_starts, offset)
        column = offset - self._line_starts[line - 1] + 1
        return Position(offset, line, column)

    def line_text(self, line: int) -> Optional[str]:
        """Text of a 1-based line (splitlines semantics), or None if out of range."""
        if 1 <= line <= len(self._lines):
            return self._lines[line - 1]
        return None


class UnclosedQuoteError(PshError, SyntaxError):
    """A quoted string was still open at end of input.

    Structurally "incomplete input": more lines could close the quote, so
    line-gathering (the CommandAccumulator) keys off this exception type —
    not the message text — to keep reading. ``quote_char`` is the opening
    quote: ``'``, ``"``, ``$'`` or ``$"``.

    Dual-inherits ``(PshError, SyntaxError)`` deliberately. It roots at
    ``PshError`` like every other shell error (so ``exceptions.py``'s
    "everything roots at PshError" claim and the strict-errors
    expected-error taxonomy hold), AND it stays a ``SyntaxError`` because
    load-bearing ``except SyntaxError`` sites depend on catching it WITHOUT
    naming it: ``heredoc_lexer.py`` (a mid-construct quote spanning lines is
    command continuation) and ``line_editor_helpers.py`` (an unlexable lone
    line). ``PshError`` defines no ``__init__``, so ``super().__init__`` still
    resolves to ``SyntaxError.__init__`` via the MRO — construction is
    unchanged. See the P6 catch-site audit (reappraisal #19 ledger)."""

    def __init__(self, message: str, quote_char: str):
        self.quote_char = quote_char
        super().__init__(message)


@dataclass
class LexerConfig:
    """Lexer behavior configuration.

    Two live fields:
    - ``enable_extglob`` — process ``?()|*()|+()|@()|!()`` extended globs
      (toggled by ``shopt -s extglob``).
    - ``posix_mode`` — restrict identifier/character handling to POSIX sets.
    """

    # The historical enable_* flags for quotes, expansions, pipes,
    # redirections, etc. were never disabled by any caller and have been
    # removed; the corresponding shell features are always on. Only
    # extglob is genuinely toggled (by `shopt -s extglob`).
    enable_extglob: bool = False           # Process ?()|*()|+()|@()|!() extended globs
    posix_mode: bool = False               # When True, restrict to POSIX character sets


class PositionTracker:
    """Tracks position in input text with line and column information."""

    def __init__(self, input_text: str):
        self.input_text = input_text
        self.position = 0
        self.line = 1
        self.column = 1
        # The one line-structure map; get_position_at_offset delegates here
        # instead of maintaining a second line_starts list.
        self.source_map = SourceMap(input_text)

    def advance(self, count: int = 1) -> None:
        """Move position forward, updating line/column."""
        for _ in range(count):
            if self.position < len(self.input_text):
                if self.input_text[self.position] == '\n':
                    self.line += 1
                    self.column = 1
                else:
                    self.column += 1
                self.position += 1

    def get_current_position(self) -> Position:
        """Get current position as a Position object."""
        return Position(self.position, self.line, self.column)

    def get_position_at_offset(self, offset: int) -> Position:
        """Get position information for a specific offset."""
        return self.source_map.location(offset)
