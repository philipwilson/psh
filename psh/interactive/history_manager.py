"""Command history management."""
import fcntl
import os
from typing import TYPE_CHECKING, List

from ..utils import contains_heredoc
from .base import InteractiveComponent
from .line_editor_helpers import convert_multiline_to_single

if TYPE_CHECKING:
    from ..shell import Shell


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

    Persistence is concurrency-safe (v0.447): ``save_to_file`` appends only
    THIS session's new entries under an exclusive file lock, merging with
    whatever other shells have written since we loaded — so several terminals
    sharing one history file no longer clobber each other (the old
    truncate-and-rewrite made the last shell to exit overwrite the rest).
    ``_file_synced_len`` tracks how many of ``state.history``'s entries are
    already on disk.
    """

    def __init__(self, shell: 'Shell') -> None:
        super().__init__(shell)
        # Count of state.history entries already persisted to the file
        # (entries loaded from it at startup, plus whatever we've since saved).
        self._file_synced_len = 0

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
        # Everything loaded is already on disk; only entries added after this
        # point are new and need appending on save.
        self._file_synced_len = len(self.state.history)

    def save_to_file(self) -> None:
        """Persist this session's new history entries (concurrency-safe).

        Rather than truncate-and-rewrite the whole file (which makes the last
        shell to exit clobber every other shell sharing the file), this holds
        an exclusive lock, re-reads the current on-disk history (picking up
        entries other shells appended after we loaded), appends only OUR new
        entries, trims to ``max_history_size``, and writes the merged result
        back. Concurrent shells therefore serialize on the lock instead of
        overwriting one another.
        """
        new_entries = self.state.history[self._file_synced_len:]
        if not new_entries:
            return
        try:
            # O_RDWR|O_CREAT so a missing file is created; 0o600 keeps history
            # private (the old open(,'w') left it at the umask default).
            fd = os.open(self.state.history_file,
                         os.O_RDWR | os.O_CREAT, 0o600)
            with os.fdopen(fd, 'r+') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    existing = [ln.rstrip('\n') for ln in f if ln.strip()]
                    combined = existing + new_entries
                    if len(combined) > self.state.max_history_size:
                        combined = combined[-self.state.max_history_size:]
                    f.seek(0)
                    f.truncate()
                    if combined:
                        f.write('\n'.join(combined) + '\n')
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            self._file_synced_len = len(self.state.history)
        except OSError:
            # Silently ignore history file errors
            pass

    def get_history(self) -> List[str]:
        """Get the command history."""
        return self.state.history.copy()

    def clear_history(self) -> None:
        """Clear command history (in-memory)."""
        self.state.history.clear()
        # The list is now empty; nothing is "already on disk" relative to it,
        # so subsequent commands append from the start.
        self._file_synced_len = 0
