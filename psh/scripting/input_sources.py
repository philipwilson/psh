"""Input source abstraction for psh.

This module provides different input sources for the shell:
- FileInput: Read commands from script files
- StringInput: Read commands from strings (for -c option)
- StdinInput: Read commands LAZILY from fd 0 (a script delivered on stdin)

(Interactive REPL input is handled by psh/interactive/, not here.)
"""

from abc import ABC, abstractmethod
from typing import List, Optional


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
        self.line_number = 0
        self.lines: List[str] = []
        self.current_line = 0
        self.loaded = False

    def __enter__(self):
        # Read the WHOLE script eagerly, then close the descriptor before any
        # command runs. psh never needs the fd again (read_line serves from
        # self.lines), and holding it open collided with user-visible fds:
        # a plain open() landed on fd 3 (clobbered by `exec 3>&-` — the
        # classic swap idiom), and the F_DUPFD_CLOEXEC relocation that
        # replaced it parked the fd at 10 — exactly bash's base for `{var}`
        # named-fd allocation — so `exec {fd}>/dev/null` returned 11 (bash:
        # 10) and a script touching fd 10 itself hit a spurious
        # "[Errno 9] Bad file descriptor" at close. (bash avoids the clash
        # differently: it reads lazily and moves its script fd to 255; psh
        # reads eagerly, so closing is simpler and cannot collide at all.)
        #
        # Use surrogateescape so a non-UTF-8 byte in a script does not crash
        # the shell with an uncaught UnicodeDecodeError — bash processes script
        # bytes leniently (a stray byte just becomes a "command not found").
        # newline='' disables universal-newline translation so an embedded CR
        # inside a line reaches the shell verbatim, exactly as bash reads the
        # raw bytes. (The stdin path is unaffected; it still uses Python's
        # default translation.)
        with open(self.file_path, 'r', encoding='utf-8',
                  errors='surrogateescape', newline='') as f:
            content = f.read()
        self._load_lines(content)
        return self

    def __exit__(self, exc_type, _exc_val, _exc_tb):
        # The descriptor was already closed at the end of __enter__.
        pass

    def _load_lines(self, content: str):
        """Split file *content* into PHYSICAL lines.

        We deliberately do NOT join backslash-newline continuations here — the
        command accumulator does that while it gathers a logical command, so
        physical line numbers stay intact for ``$LINENO`` (pre-joining shifted
        every later line number down by the count of preceding continuations).

        Split on newline only, then drop ONE trailing CR per line: this is the
        line-reading layer's CRLF handling, so a DOS-line-ending script runs
        as if dos2unix'd (psh's documented divergence — bash keeps the CR
        bytes). An embedded CR *inside* a line stays verbatim like bash; the
        lexer no longer treats CR as whitespace, so mid-line CRs are ordinary
        word characters there too.
        """
        self.lines = [line[:-1] if line.endswith('\r') else line
                      for line in content.split('\n')]
        self.loaded = True

    def read_line(self) -> Optional[str]:
        """Read the next physical line from the file."""
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

    def __init__(self, command: str, name: str = "<command>",
                 split_lines: Optional[bool] = None):
        # Do NOT pre-join line continuations here: the command accumulator
        # joins them while gathering a logical command, and pre-joining shifted
        # $LINENO down by the count of preceding continuations (each joined-away
        # newline lost a physical line number).
        #
        # ``split_lines`` selects the read granularity; when None it defaults
        # from the source name. Line-by-line reading (True) lets the buffered
        # boundary CONTAIN a discard-line error (a word-arithmetic failure,
        # readonly-in-$(( )) ...) to just the offending line and resume at the
        # next — which is why ``-c``/stdin/script and line-oriented ``eval``
        # use it. Single-chunk reading (False) feeds the whole string as one
        # logical unit (the historical run_command default).
        if split_lines is None:
            split_lines = (name != "<command>")
        if not split_lines:
            self.lines = [command] if command else []
        else:
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


class StdinInput(InputSource):
    """Lazy, line-at-a-time input source over fd 0 for a script ON STDIN.

    bash reads a script delivered on standard input (``cmds | psh``,
    ``psh < file``, ``psh -s``) LAZILY: it consumes just enough of fd 0 to run
    the current command and leaves the rest readable, so a ``read``/``cat``/
    ``mapfile`` inside the script consumes the SUBSEQUENT physical lines as data
    (``printf 'read x\\ncat\\n...' | bash``). psh used to slurp ALL of fd 0 into
    a ``StringInput`` up front, draining it so every in-script stdin consumer
    saw immediate EOF — silent wrong output (scripting appraisal 2026-07-07 #1).

    This reads one physical line at a time straight from fd 0 through the shared
    record-oriented ``InputReader`` (the same never-over-read primitive ``read``
    and ``mapfile`` use), so the shell's command source and the runtime ``read``
    stream are the SAME lazily-consumed fd. It works identically for a pipe and
    a seekable file: ``os.read`` advances the one shared file offset either way,
    and byte-at-a-time reads never consume past the newline that ends the line.

    Each physical line is decoded with ``errors='surrogateescape'`` (like the
    ``FileInput`` script path), so a non-UTF-8 script byte round-trips instead
    of crashing the shell. The line delimiter (the newline byte) is stripped;
    a trailing CR is KEPT (bash keeps it on the stdin path — this is NOT the
    FileInput CRLF divergence).
    """

    _NEWLINE = 0x0A  # b'\n'

    def __init__(self, fd: int = 0, name: str = "<stdin>"):
        # Import here (not at module load) so scripting/ does not import the
        # builtins package at import time; by the time a StdinInput is built the
        # shell is fully constructed and psh.builtins is loaded.
        from ..builtins.input_reader import InputReader
        self._reader = InputReader(fd=fd)
        self._name = name
        self.line_number = 0
        self._eof = False

    def read_line(self) -> Optional[str]:
        """Read the next physical line from fd 0, or None at EOF.

        Consumes exactly one line's bytes (up to and including its newline) and
        no more, leaving the remainder of fd 0 intact for an in-script ``read``/
        ``cat``/``mapfile``. A closed/invalid fd 0 surfaces as immediate EOF.
        """
        if self._eof:
            return None
        record = self._reader.read_record_bytes(delimiter_byte=self._NEWLINE)
        if record is None:
            self._eof = True
            return None
        self.line_number += 1
        return record.decode('utf-8', errors='surrogateescape')

    def is_interactive(self) -> bool:
        return False

    def get_name(self) -> str:
        return self._name

    def get_line_number(self) -> int:
        return self.line_number
