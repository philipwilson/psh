"""
Heredoc collection support for the PSH lexer.

This module provides functionality to collect heredoc content during lexing,
allowing the lexer to properly handle multi-line heredoc input.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class HeredocCollector:
    """Manages heredoc collection during lexing."""

    @dataclass
    class PendingHeredoc:
        """Information about a heredoc being collected.

        ``key`` is the heredoc's index into ``collected`` — stored here so
        content lines and completion are recorded against exactly this
        heredoc (a delimiter-string scan misfiled content when two heredocs
        shared a delimiter). ``start_line`` is the 1-based source line where
        this heredoc's body gathering begins; the driver re-stamps it when a
        pending heredoc is promoted to first (matching the line bash reports
        in its "delimited by end-of-file" warning).
        """
        key: str
        delimiter: str
        strip_tabs: bool
        quoted: bool
        start_line: int
        start_col: int

    # Pending heredocs that need content
    pending: List[PendingHeredoc] = field(default_factory=list)

    # Collected heredoc content
    collected: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Counter for unique heredoc keys
    _counter: int = 0

    def register_heredoc(self, delimiter: str, strip_tabs: bool, quoted: bool,
                        line: int, col: int) -> str:
        """
        Register a new heredoc that needs content collection.

        Args:
            delimiter: The heredoc delimiter
            strip_tabs: Whether to strip tabs (<<- operator)
            quoted: Whether delimiter was quoted (affects expansion)
            line: Line number where heredoc starts
            col: Column number where heredoc starts

        Returns:
            Unique key for this heredoc
        """
        key = f"heredoc_{self._counter}_{delimiter}"
        self._counter += 1

        self.pending.append(self.PendingHeredoc(
            key=key,
            delimiter=delimiter,
            strip_tabs=strip_tabs,
            quoted=quoted,
            start_line=line,
            start_col=col
        ))

        # Initialize collected entry
        self.collected[key] = {
            'delimiter': delimiter,
            'strip_tabs': strip_tabs,
            'quoted': quoted,
            'content': [],
            'complete': False
        }

        return key

    def has_pending_heredocs(self) -> bool:
        """Check if there are heredocs waiting for content."""
        return bool(self.pending)

    def collect_line(self, line: str) -> List[Tuple[str, bool]]:
        """
        Process a line for heredoc content collection.

        Args:
            line: The line to process

        Returns:
            List of (key, complete) tuples for heredocs that were completed
        """
        completed: List[Tuple[str, bool]] = []

        # Only the FIRST pending heredoc is live (bodies are read in order).
        if self.pending:
            heredoc = self.pending[0]
            # Is this line the terminator? bash requires the terminator line
            # to equal the delimiter exactly (only <<- strips leading tabs);
            # a line like "EOF " with trailing whitespace is body content,
            # not the terminator. The shared rule also drops a CRLF
            # line-ending CR so a CRLF script terminates.
            from ..utils.heredoc_detection import heredoc_terminator_matches
            if heredoc_terminator_matches(
                    line, heredoc.delimiter, heredoc.strip_tabs):
                self.collected[heredoc.key]['complete'] = True
                completed.append((heredoc.key, True))
                self.pending.pop(0)
            else:
                content_line = line
                if heredoc.strip_tabs:
                    content_line = line.lstrip('\t')
                self.collected[heredoc.key]['content'].append(content_line)

        return completed

    def finalize_at_eof(self, last_line: int) -> List[Tuple[str, int]]:
        """End of input with heredocs still pending: delimit them by EOF.

        Bash does not drop an unterminated heredoc — it uses everything
        gathered so far as the body, warns ("here-document at line N
        delimited by end-of-file"), and runs the command (silently swallowing
        it was worse than bash's warn-and-recover). Content routing matches
        bash: the first pending heredoc keeps the gathered lines; any later
        pending heredocs get empty bodies.

        Returns ``(delimiter, start_line)`` pairs for the caller's warnings,
        in order. The first pending heredoc reports the line its body
        gathering began at (its — possibly re-stamped — ``start_line``);
        later ones report ``last_line``, where their gathering would have
        begun (bash reports the same line numbers).
        """
        warnings: List[Tuple[str, int]] = []
        for index, heredoc in enumerate(self.pending):
            self.collected[heredoc.key]['complete'] = True
            warnings.append((heredoc.delimiter,
                             heredoc.start_line if index == 0 else last_line))
        self.pending.clear()
        return warnings

    def get_content(self, key: str) -> Optional[str]:
        """Get the collected content for a heredoc."""
        if key in self.collected:
            info = self.collected[key]
            if info['complete']:
                # Join lines with newlines and add final newline
                content = '\n'.join(info['content'])
                if info['content']:  # Add final newline if there was content
                    content += '\n'
                return content
        return None

    def get_heredoc_info(self, key: str) -> Optional[Dict[str, Any]]:
        """Get complete information about a heredoc."""
        if key in self.collected:
            info = self.collected[key].copy()
            info['content'] = self.get_content(key)
            return info
        return None

    def clear(self):
        """Clear all heredoc state."""
        self.pending.clear()
        self.collected.clear()
        self._counter = 0

    def get_incomplete_heredocs(self) -> List[str]:
        """Get list of delimiters for incomplete heredocs."""
        return [h.delimiter for h in self.pending]
