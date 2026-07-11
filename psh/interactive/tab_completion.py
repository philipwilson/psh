#!/usr/bin/env python3
"""Tab completion utilities for psh.

Provides CompletionEngine (path completion logic), consumed by the
production LineEditor in psh/line_editor.py.  TerminalManager (raw mode
handling) lives in psh/interactive/terminal.py and is re-exported here
for compatibility.
"""

import os
from typing import List

from .terminal import TerminalManager

__all__ = ['CompletionEngine', 'TerminalManager']


class CompletionEngine:
    """Handles tab completion logic."""

    def get_completions(self, text: str, line: str, cursor_pos: int) -> List[str]:
        """Get possible completions for the current context."""
        # Extract the word being completed
        word_start = self.find_word_start(line, cursor_pos)
        current_word = line[word_start:cursor_pos]

        # Get file/directory completions
        return self._get_path_completions(current_word)

    def find_word_start(self, line: str, cursor_pos: int) -> int:
        """Find the start of the current word (public: LineEditor uses it)."""
        # Handle quotes
        in_quotes = False
        quote_char = None
        escape_next = False

        for i in range(cursor_pos):
            if escape_next:
                escape_next = False
                continue

            if line[i] == '\\':
                escape_next = True
                continue

            if line[i] in '"\'':
                if not in_quotes:
                    in_quotes = True
                    quote_char = line[i]
                elif line[i] == quote_char:
                    in_quotes = False
                    quote_char = None

        # Find word boundary
        pos = cursor_pos - 1
        while pos >= 0:
            char = line[pos]

            # If we're in quotes, only stop at the opening quote
            if in_quotes:
                if char == quote_char and (pos == 0 or line[pos-1] != '\\'):
                    return pos + 1
            else:
                # Stop at whitespace or special shell characters
                if char in ' \t;|&<>':
                    return pos + 1

            pos -= 1

        return 0

    def _get_path_completions(self, partial_path: str) -> List[str]:
        """Get file/directory completions for a partial path."""
        # Remember if we started with ~
        started_with_tilde = partial_path.startswith('~')
        expanded_path = partial_path

        # Handle home directory expansion for searching
        if started_with_tilde:
            expanded_path = os.path.expanduser(partial_path)

        # Determine directory and basename
        if os.path.sep in expanded_path:
            dirname, basename = os.path.split(expanded_path)
            if not dirname:
                dirname = os.path.sep
        else:
            dirname = '.'
            basename = expanded_path

        # Expand the directory path
        dirname = os.path.expanduser(dirname)
        if not os.path.isabs(dirname):
            dirname = os.path.abspath(dirname)

        try:
            # Get all entries in the directory
            entries = os.listdir(dirname)

            # Filter entries that match the basename
            matches = []
            for entry in entries:
                # Include hidden files only if explicitly requested
                if not basename and entry.startswith('.'):
                    continue
                if entry.startswith(basename):
                    matches.append(entry)

            # Build full paths and add indicators
            results = []
            for match in sorted(matches):
                full_path = os.path.join(dirname, match)

                # Add trailing slash for directories
                if os.path.isdir(full_path):
                    match += os.path.sep

                # Reconstruct the path as it should appear
                if os.path.sep in partial_path:
                    # Keep the original directory part
                    dir_part = partial_path.rsplit(os.path.sep, 1)[0]
                    result = dir_part + os.path.sep + match
                else:
                    result = match

                results.append(result)

            return results

        except (OSError, PermissionError):
            return []

    def find_common_prefix(self, candidates: List[str]) -> str:
        """Find the longest common prefix among candidates."""
        if not candidates:
            return ""

        if len(candidates) == 1:
            return candidates[0]

        # Find common prefix
        prefix = candidates[0]
        for candidate in candidates[1:]:
            # Shorten prefix until it matches
            while not candidate.startswith(prefix):
                prefix = prefix[:-1]
                if not prefix:
                    break

        return prefix

    def escape_path(self, path: str) -> str:
        """Escape special characters in a path for shell use."""
        # Characters that need escaping
        special_chars = ' \t\n\\$`"\'(){}[]&;|<>*?!#'

        escaped = []
        for i, char in enumerate(path):
            # Don't escape tilde at the beginning (it's for home directory expansion)
            if char == '~' and i == 0:
                escaped.append(char)
            elif char in special_chars:
                escaped.append('\\')
                escaped.append(char)
            else:
                escaped.append(char)

        return ''.join(escaped)
