"""Input source abstraction for psh.

This module provides different input sources for the shell:
- FileInput: Read commands from script files
- StringInput: Read commands from strings (for -c option)

(Interactive REPL input is handled by psh/interactive/, not here.)
"""

from abc import ABC, abstractmethod
from typing import List, Optional, TextIO


class InputSource(ABC):
    """Abstract base class for shell input sources."""

    @abstractmethod
    def read_line(self) -> Optional[str]:
        """Read the next line from the input source.

        Returns:
            The next line as a string, or None on EOF.
        """
        pass

    @abstractmethod
    def is_interactive(self) -> bool:
        """Return True if this is an interactive input source."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Return the name of this input source for error messages."""
        pass

    def get_line_number(self) -> int:
        """Return the current line number (1-based). Override if tracking line numbers."""
        return 0

    def get_location(self) -> str:
        """Return a location string for error messages."""
        line_num = self.get_line_number()
        if line_num > 0:
            return f"{self.get_name()}:{line_num}"
        return self.get_name()


class FileInput(InputSource):
    """Input source for reading commands from script files."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.file: Optional[TextIO] = None
        self.line_number = 0
        self.lines: List[str] = []
        self.current_line = 0
        self.loaded = False

    def __enter__(self):
        # Use surrogateescape so a non-UTF-8 byte in a script does not crash
        # the shell with an uncaught UnicodeDecodeError — bash processes script
        # bytes leniently (a stray byte just becomes a "command not found").
        # newline='' disables universal-newline translation so an embedded CR
        # (or a CRLF script's trailing \r) reaches the shell verbatim, exactly
        # as bash reads the raw bytes — splitting only on \n. (The stdin path
        # is unaffected; it still uses Python's default translation.)
        raw = open(self.file_path, 'r', encoding='utf-8',
                   errors='surrogateescape', newline='')
        # Relocate the script-reading descriptor out of the user-visible range.
        # A plain open() lands on the lowest free fd (typically 3), so a script
        # doing `exec 3>&-` or the classic `exec 3>&1 1>&2 2>&3 3>&-` swap would
        # clobber the fd we read the script from — at close that raised a
        # spurious "[Errno 9] Bad file descriptor" + exit 1. bash keeps its
        # script fd >= 10; do the same via F_DUPFD_CLOEXEC (lowest free fd >= 10,
        # close-on-exec set so it does not leak to child processes).
        self.file = self._relocate_high(raw)
        return self

    @staticmethod
    def _relocate_high(raw: TextIO) -> TextIO:
        """Move *raw*'s descriptor to the lowest free fd >= 10 (close-on-exec).

        Returns a new file object on the relocated fd; falls back to *raw*
        unchanged if relocation is unsupported (e.g. a non-fd stream).
        """
        import fcntl
        import os
        try:
            dup_flag = getattr(fcntl, 'F_DUPFD_CLOEXEC', fcntl.F_DUPFD)
            high_fd = fcntl.fcntl(raw.fileno(), dup_flag, 10)
        except (OSError, ValueError, AttributeError):
            return raw
        raw.close()  # release the low fd; the dup at high_fd stays open
        return os.fdopen(high_fd, 'r', encoding='utf-8',
                         errors='surrogateescape', newline='')

    def __exit__(self, exc_type, _exc_val, _exc_tb):
        if self.file:
            self.file.close()

    def _load_lines(self):
        """Read the whole file and split into PHYSICAL lines.

        We deliberately do NOT join backslash-newline continuations here — the
        command accumulator does that while it gathers a logical command, so
        physical line numbers stay intact for ``$LINENO`` (pre-joining shifted
        every later line number down by the count of preceding continuations).
        """
        if self.loaded:
            return

        # Read entire file content (only reached inside the `with` block,
        # so self.file has been opened by __enter__).
        assert self.file is not None
        content = self.file.read()

        # Split on newline only (the file was opened with newline='' so no CR
        # translation happened); each element is one physical line.
        self.lines = content.split('\n')
        self.loaded = True

    def read_line(self) -> Optional[str]:
        """Read the next physical line from the file."""
        if not self.loaded:
            self._load_lines()

        if self.current_line < len(self.lines):
            line = self.lines[self.current_line]
            self.current_line += 1
            self.line_number += 1
            return line
        return None

    def is_interactive(self) -> bool:
        return False

    def get_name(self) -> str:
        return self.file_path

    def get_line_number(self) -> int:
        return self.line_number


class StringInput(InputSource):
    """Input source for reading commands from a string."""

    def __init__(self, command: str, name: str = "<command>"):
        # Do NOT pre-join line continuations here: the command accumulator
        # joins them while gathering a logical command, and pre-joining shifted
        # $LINENO down by the count of preceding continuations (each joined-away
        # newline lost a physical line number).
        if name == "<command>":
            # run_command(): the whole (possibly multi-line) string is one
            # logical unit fed to the accumulator in a single chunk.
            self.lines = [command] if command else []
        else:
            # Script / -c / stdin: split into PHYSICAL lines for line-by-line
            # processing (also lets shopt settings affect later-line lexing).
            self.lines = command.split('\n')

        self.current = 0
        self.name = name
        self.line_number = 0

    def read_line(self) -> Optional[str]:
        """Read the next line from the string."""
        if self.current < len(self.lines):
            line = self.lines[self.current]
            self.current += 1
            self.line_number += 1
            return line
        return None

    def is_interactive(self) -> bool:
        return False

    def get_name(self) -> str:
        return self.name

    def get_line_number(self) -> int:
        return self.line_number
