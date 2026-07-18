"""Input source abstraction for psh.

This module provides different input sources for the shell:
- FileInput: Read commands from script files
- StringInput: Read commands from strings (for -c option)
- StdinInput: Read commands LAZILY from fd 0 (a script delivered on stdin)

(Interactive REPL input is handled by psh/interactive/, not here.)

Construction happens ONLY through ``ProgramSource.make_input_source()``
(``psh/scripting/program_source.py``) — the one normalization boundary that
decides each channel's byte/NUL policy and per-channel parse flags.  Direct
construction elsewhere in ``psh/`` is forbidden by the static ratchet
``tests/unit/tooling/test_program_source_guard.py``.
"""

from abc import ABC, abstractmethod
from typing import Callable, List, Optional


class InputSource(ABC):
    """Abstract base class for shell input sources."""

    # Whether a syntax error in this source may trigger the POSIX-mode
    # fatal-syntax-error policy (SourceProcessor._posix_syntax_abort).
    # True for every real input (script file, -c, stdin, eval'd and
    # sourced text); Shell.run_command sets it False for a TRAP ACTION
    # string — bash does NOT exit when the action itself fails to parse,
    # though anything nested deeper (an eval inside the action) does
    # (probe-verified vs bash 5.2, tmp/posixexit).
    posix_syntax_exit: bool = True

    # Bash's two rules for a dangling backslash at TRUE end of input
    # (a trailing ``\`` with no newline after it), probe-verified vs
    # bash 5.2 (tmp/contcarry/):
    #
    # * STREAM inputs — a script file argument, a script on stdin, a
    #   ``/dev/fd`` process-substitution script — DROP it: a file ending
    #   ``echo hi \`` runs ``echo hi``. (bash reads these through its
    #   getc layer, which discards a backslash followed by EOF.)
    # * STRING inputs — ``-c``, ``eval``, and notably ``source``/``.``
    #   (bash reads the sourced file into a string) — keep it as a
    #   literal word character: ``bash -c 'echo hi \'`` prints ``hi \``.
    #
    # A backslash-NEWLINE pair at end of input is a normal continuation
    # (joined with the empty remainder) in EVERY mode; this flag only
    # governs the no-newline dangling case. SourceProcessor threads it
    # into process_line_continuations(drop_dangling_at_eof=...).
    eof_drops_dangling_continuation: bool = False

    # Whether history expansion (`!!`, `!n`, ...) may apply to this source's
    # lines when the shell's interactive machinery is active. bash 5.2
    # (probe-verified, tmp/boundary-ledgers/F1-probes/, campaign F1): the
    # MAIN input stream of an interactive-family shell expands — the REPL,
    # piped stdin under -i, and even a script file under `-i script.sh` —
    # but a `-c` COMMAND STRING never does (`bash -ic 'echo !!'` prints
    # `!!` literally), and neither does the rc file. __main__ clears this
    # for the -c StringInput; rc_loader clears it for the rc FileInput.
    # (The SourceProcessor gate additionally requires a non-script-mode
    # shell, so plain scripts/stdin without -i never expand.)
    history_expansion_eligible: bool = True

    # Whether a FunctionReturn escaping this source's top level (no
    # enclosing executor) STOPS the source — the sourced-program channels
    # (source/., rc), where `return` outside a function legally ends the
    # file. The source processor re-raises so execute_sourced_file
    # (program_source.py) resolves it; other sources keep the historical
    # swallow-per-buffer behavior (a subshell-style child that inherited a
    # sourced-file context). Set by ProgramSource.make_input_source().
    stops_on_function_return: bool = False

    def __enter__(self) -> 'InputSource':
        """Context protocol: sources that own resources override (FileInput
        reads its file here); the string/stdin sources need no setup."""
        return self

    def __exit__(self, exc_type: object, exc_val: object,
                 exc_tb: object) -> None:
        return None  # deliberate no-op default (B027): nothing to release

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
    """Input source for reading commands from script files.

    ``eof_drops_dangling_continuation`` is per-USE, not per-class: a script
    file ARGUMENT is a bash stream input (True — the script executor and
    ``--validate`` pass it), while ``source``/``.`` and rc files are bash
    STRING inputs (False, the default) even though psh reads all of them
    through this class. See the base-class attribute for the bash rule.
    """

    def __init__(self, file_path: str,
                 eof_drops_dangling_continuation: bool = False,
                 content_filter: Optional[Callable[[str], str]] = None):
        self.file_path = file_path
        self.eof_drops_dangling_continuation = eof_drops_dangling_continuation
        # The channel's NUL policy from ProgramSource (strip_nul_stream for
        # a script-file argument, the evalfile filter for source/rc);
        # applied to the decoded content before line-splitting.
        self.content_filter = content_filter
        self.line_number = 0
        self.lines: List[str] = []

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
        if self.content_filter is not None:
            # The channel's NUL policy (program_source.py) — decided once,
            # before the text is split into lines.
            content = self.content_filter(content)
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

    def read_line(self) -> Optional[str]:
        """Read the next physical line from the file. ``line_number`` doubles as
        the read cursor (index of the next physical line)."""
        if self.line_number < len(self.lines):
            line = self.lines[self.line_number]
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
                 split_lines: bool = False):
        # Do NOT pre-join line continuations here: the command accumulator
        # joins them while gathering a logical command, and pre-joining shifted
        # $LINENO down by the count of preceding continuations (each joined-away
        # newline lost a physical line number).
        #
        # ``split_lines`` selects the read granularity. Line-by-line reading
        # (True) lets the buffered boundary CONTAIN a discard-line error (a
        # word-arithmetic failure, readonly-in-$(( )) ...) to just the offending
        # line and resume at the next — which is why ``-c``/stdin/script and
        # line-oriented ``eval`` pass it explicitly. Single-chunk reading
        # (False, the default) feeds the whole string as one logical unit (the
        # historical run_command default).
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

    # A script on stdin is a bash STREAM input: a dangling backslash at
    # true EOF is dropped (see the base-class attribute).
    eof_drops_dangling_continuation: bool = True

    def __init__(self, fd: int = 0, name: str = "<stdin>"):
        # Import here (not at module load) so scripting/ does not import the
        # builtins package at import time; by the time a StdinInput is built the
        # shell is fully constructed and psh.builtins is loaded.
        from ..builtins.input_reader import InputReader
        self._reader = InputReader(fd=fd)
        self._name = name
        self.line_number = 0
        self._eof = False
        self._last_hit_delimiter = False

    def read_line(self) -> Optional[str]:
        """Read the next physical line from fd 0, or None at EOF.

        Consumes exactly one line's bytes (up to and including its newline) and
        no more, leaving the remainder of fd 0 intact for an in-script ``read``/
        ``cat``/``mapfile``. A closed/invalid fd 0 surfaces as immediate EOF.

        Line semantics match ``FileInput`` exactly: when the input's final
        line is newline-TERMINATED, one empty final line is yielded at EOF
        (``FileInput``'s ``split('\\n')`` produces it naturally; the record
        reader strips the newline, so it is restored here). That final empty
        line is what tells the gathering layer the input ended ``...\\<LF>``
        (a joinable continuation) rather than ``...\\`` (a dangling one) —
        the two shapes differ in bash. Costs no extra reads: it is emitted
        only when EOF has already been observed.
        """
        if self._eof:
            return None
        record = self._reader.read_record_bytes(delimiter_byte=self._NEWLINE)
        if record is None:
            self._eof = True
            if self._last_hit_delimiter:
                self._last_hit_delimiter = False
                self.line_number += 1
                return ''
            return None
        self._last_hit_delimiter = self._reader.last_record_hit_delimiter
        self.line_number += 1
        # Stream-channel NUL policy: bash's shell_getc layer discards every
        # NUL byte it reads (`e\0cho hi` on stdin runs `echo hi`); a script
        # on stdin is never content-sniffed. Deleting per record equals
        # deleting over the stream, since NUL never ends a record. This IS
        # the _CHANNEL_POLICY STDIN_SCRIPT row's _STREAM policy, applied
        # here because the lazy fd read has no whole-content filter seam —
        # if the table row changes, this line must change with it (mirror
        # comment on the row in program_source.py).
        record = record.replace(b'\x00', b'')
        return record.decode('utf-8', errors='surrogateescape')

    def is_interactive(self) -> bool:
        return False

    def get_name(self) -> str:
        return self._name

    def get_line_number(self) -> int:
        return self.line_number
