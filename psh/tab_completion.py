#!/usr/bin/env python3
"""Tab completion utilities for psh.

Provides TerminalManager (raw mode handling) and CompletionEngine
(path completion logic).  Both are consumed by the production
LineEditor in psh/line_editor.py.
"""

import os
import sys
import termios
import tty
from typing import List


class TerminalManager:
    """Manages terminal mode for raw input handling."""

    def __init__(self):
        self.old_settings = None
        self.is_raw = False

    def enter_raw_mode(self):
        """Put terminal in raw mode to capture individual keystrokes."""
        # Enter raw mode for any TTY (including PTYs)
        # Note: isatty() returns True for both real terminals and pseudo-terminals
        # TCSANOW everywhere: the default TCSAFLUSH/TCSADRAIN wait for the
        # terminal's output queue to drain, which BLOCKS on a pty whose
        # master isn't currently being read (pexpect between expects, a
        # wedged terminal emulator). bash stays responsive there; so must we.
        if sys.stdin.isatty() and not self.is_raw:
            try:
                self.old_settings = termios.tcgetattr(sys.stdin)
                tty.setraw(sys.stdin.fileno(), termios.TCSANOW)
                self.is_raw = True
            except (termios.error, OSError):
                # If we can't set raw mode, continue without it
                pass

    def exit_raw_mode(self):
        """Restore normal terminal mode."""
        if self.old_settings is not None and self.is_raw:
            termios.tcsetattr(sys.stdin, termios.TCSANOW, self.old_settings)
            self.is_raw = False

    def __enter__(self):
        self.enter_raw_mode()
        return self

    def __exit__(self, exc_type, _exc_val, _exc_tb):
        self.exit_raw_mode()


class CompletionEngine:
    """Handles tab completion logic."""

    def get_completions(self, text: str, line: str, cursor_pos: int) -> List[str]:
        """Get possible completions for the current context."""
        # Extract the word being completed
        word_start = self._find_word_start(line, cursor_pos)
        current_word = line[word_start:cursor_pos]

        # Get file/directory completions
        return self._get_path_completions(current_word)

    def _find_word_start(self, line: str, cursor_pos: int) -> int:
        """Find the start of the current word."""
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
