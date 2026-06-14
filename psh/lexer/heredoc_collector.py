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
        """Information about a heredoc being collected."""
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

        # Only check the FIRST pending heredoc (heredocs are collected in order)
        if self.pending:
            heredoc = self.pending[0]
            # Check if this line is the delimiter. For <<- the delimiter line
            # may itself be tab-indented; strip leading tabs before comparing,
            # the same way content lines are stripped (bash does this too).
            delimiter_line = line.lstrip('\t') if heredoc.strip_tabs else line
            if delimiter_line.rstrip() == heredoc.delimiter:
                # Find the key for this heredoc
                for key, info in self.collected.items():
                    if (info['delimiter'] == heredoc.delimiter and
                        not info['complete']):
                        info['complete'] = True
                        completed.append((key, True))
                        break

        # Remove completed heredocs from pending (in order)
        if completed:
            # Since we only check the first pending heredoc, we only need to remove it
            self.pending.pop(0)
            remaining_pending = self.pending
        else:
            remaining_pending = self.pending

        # If we didn't complete any heredocs, add the line to the FIRST pending one only
        if not completed and self.pending:
            # Only the first pending heredoc should collect content
            heredoc = self.pending[0]
            content_line = line
            if heredoc.strip_tabs:
                content_line = line.lstrip('\t')

            # Find the key and add content
            for key, info in self.collected.items():
                if (info['delimiter'] == heredoc.delimiter and
                    not info['complete']):
                    info['content'].append(content_line)
                    break

        self.pending = remaining_pending
        return completed

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
