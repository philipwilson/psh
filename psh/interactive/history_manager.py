"""Command history management."""
import os
from typing import List

from ..utils import contains_heredoc
from .base import InteractiveComponent
from .line_editor_helpers import convert_multiline_to_single


def _newline_inside_quotes(command: str) -> bool:
    """True if any newline in *command* falls inside a quoted string."""
    quote = None
    escaped = False
    for ch in command:
        if escaped:
            escaped = False
        elif ch == '\\' and quote != "'":
            escaped = True
        elif quote is None and ch in ('"', "'"):
            quote = ch
        elif ch == quote:
            quote = None
        elif ch == '\n' and quote is not None:
            return True
    return False


class HistoryManager(InteractiveComponent):
    """Manages command history.

    The SOLE history writer is shell.add_history → add_to_history, fed by
    the source processor with the complete logical command (the line
    editor records nothing itself).
    """

    def add_to_history(self, command: str) -> None:
        """Add a command to history.

        A multi-line command becomes ONE entry, joined into its
        single-line ``; `` form like bash's cmdhist option — except
        that newlines inside quoted strings or heredocs are preserved
        verbatim, also matching bash.
        """
        if '\n' in command:
            if not _newline_inside_quotes(command) and not contains_heredoc(command):
                command = convert_multiline_to_single(command)
        # Don't add duplicates of the immediately previous command
        if not self.state.history or self.state.history[-1] != command:
            self.state.history.append(command)
            # Trim history if it exceeds max size
            if len(self.state.history) > self.state.max_history_size:
                self.state.history = self.state.history[-self.state.max_history_size:]

    def load_from_file(self) -> None:
        """Load command history from file."""
        try:
            if os.path.exists(self.state.history_file):
                with open(self.state.history_file, 'r') as f:
                    for line in f:
                        line = line.rstrip('\n')
                        if line:
                            self.state.history.append(line)
                # Trim to max size
                if len(self.state.history) > self.state.max_history_size:
                    self.state.history = self.state.history[-self.state.max_history_size:]
        except OSError:
            # Silently ignore history file errors
            pass

    def save_to_file(self) -> None:
        """Save command history to file."""
        try:
            with open(self.state.history_file, 'w') as f:
                # Save only the last max_history_size commands
                for cmd in self.state.history[-self.state.max_history_size:]:
                    f.write(cmd + '\n')
        except OSError:
            # Silently ignore history file errors
            pass

    def get_history(self) -> List[str]:
        """Get the command history."""
        return self.state.history.copy()

    def clear_history(self) -> None:
        """Clear command history."""
        self.state.history.clear()
