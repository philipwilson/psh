"""Input source abstraction for psh.

This module provides different input sources for the shell:
- FileInput: Read commands EAGERLY from source/rc files (whole-content NUL
  filtering + binary refusal; bash reads these eagerly too)
- LazyFileInput: Read commands LAZILY from a SCRIPT-FILE argument, block-buffered
  over an owned high-CLOEXEC descriptor (campaign I2, #20 H14)
- StringInput: Read commands from strings (for -c option)
- StdinInput: Read commands LAZILY from fd 0 (a script delivered on stdin)

(Interactive REPL input is handled by psh/interactive/, not here.)

Construction happens ONLY through ``ProgramSource.make_input_source()``
(``psh/scripting/program_source.py``) — the one normalization boundary that
decides each channel's byte/NUL policy and per-channel parse flags.  Direct
construction elsewhere in ``psh/`` is forbidden by the static ratchet
``tests/unit/tooling/test_program_source_guard.py``.
"""

import fcntl
import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable, List, Optional

if TYPE_CHECKING:
    from ..core.state import ShellState

# The high floor a script-file descriptor is relocated to (campaign I2). bash
# reads a script argument through fd 255 (CLOEXEC); psh matches the convention.
# The exact landing slot is an implementation detail — F_DUPFD_CLOEXEC returns
# the first free fd >= this floor, and the reservation registry
# (``ShellState.reserved_script_fds``) makes a user PERMANENT redirect to that
# exact number relocate the reader rather than clobber it (LazyFileInput).
_SCRIPT_FD_FLOOR = 255

# F_DUPFD_CLOEXEC is present on Linux and macOS; fall back defensively (the
# same pattern as psh/io_redirect/fd_remap.py, inlined to keep scripting/ from
# importing io_redirect/).
_F_DUPFD_CLOEXEC = getattr(fcntl, 'F_DUPFD_CLOEXEC', None)


def _dup_cloexec_high(fd: int, floor: int) -> int:
    """Duplicate ``fd`` onto the lowest free descriptor >= ``floor``, CLOEXEC.

    Close-on-exec so an exec'd child never inherits the script descriptor
    (bash makes its script fd CLOEXEC too — probe O2/O3).
    """
    if _F_DUPFD_CLOEXEC is not None:
        return fcntl.fcntl(fd, _F_DUPFD_CLOEXEC, floor)
    dup = fcntl.fcntl(fd, fcntl.F_DUPFD, floor)
    flags = fcntl.fcntl(dup, fcntl.F_GETFD)
    fcntl.fcntl(dup, fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)
    return dup


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
    record-oriented ``InputCursor`` (the same never-over-read primitive ``read``
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
        from ..builtins.input_reader import InputCursor
        self._reader = InputCursor(fd=fd)
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


class LazyFileInput(InputSource):
    """Lazy, block-buffered physical-line source for a SCRIPT-FILE argument.

    ``psh FILE`` used to slurp the whole file into memory and close the fd
    before line one ran (#20 H14): memory scaled with file size, a producer
    feeding the script through a FIFO could not send the rest after an early
    command's side effect, and a script that appended to itself never saw the
    appended lines.  This reads ON DEMAND, matching bash's private, block-
    buffered script descriptor (fd 255):

    Two read modes, chosen by whether the descriptor is SEEKABLE — bash's
    seekable-block vs unseekable-record discipline:

    * **Seekable (a regular file): block-buffered, forward-only.**
      ``os.read(fd, BLOCK)`` fills a bounded buffer; physical lines are served
      from it and the buffer is refilled when exhausted.  Memory is one block
      plus one partial line, independent of file size.  Over-reading is safe:
      the descriptor is PRIVATE (relocated high + CLOEXEC, separate from fd 0),
      so an in-script ``read`` on stdin is unaffected.  bash buffers similarly,
      so a modification to bytes already read into the buffer is invisible in
      BOTH shells (``: > "$0"`` mid-script still runs the buffered rest).
    * **Not seekable (a pipe / FIFO / ``/dev/stdin`` over a pipe):
      never-over-read.** Read one record at a time through the shared
      ``InputCursor`` (the ``read``/``mapfile``/``StdinInput`` primitive), so the
      rest of the stream stays available — a ``/dev/stdin`` script that SHARES
      fd 0's description must leave the following bytes for an in-script
      ``read``, and a FIFO producer that waits for the script's first side
      effect must not be over-consumed (an eager reader deadlocks).
    * **Re-reads at EOF, so growth is seen (both modes).** A refill that lands
      at the old EOF returns appended bytes; EOF is never cached.  The INVARIANT
      is *consumed bytes are never re-read; appends past the read frontier are
      seen* — the block SIZE (which mid-buffer edits are invisible) is a
      documented deliberate loss.

    **Descriptor ownership.** ``__enter__`` opens the file and relocates the fd
    to a high CLOEXEC slot (``_dup_cloexec_high`` from ``_SCRIPT_FD_FLOOR``),
    registering it on ``ShellState.reserved_script_fds``.  A user's ordinary
    redirect never touches it (fds 0-9, ``{v}`` 10+ which ``F_DUPFD`` skips over
    the open slot, parking 63; a temp redirect save/restores the slot).  A
    PERMANENT ``exec`` redirect to its exact number relocates the reader first
    (``relocate_away_from`` called from ``apply_permanent_redirections``) so it
    cannot be clobbered — bash owns its fd the same way (probe O1).  ``__exit__``
    unregisters and closes the fd.

    NUL bytes are deleted per record (STREAM policy — equal to deleting over the
    stream since NUL never ends a record) and one trailing CR is stripped per
    physical line (FileInput CRLF parity — psh's documented dos2unix divergence),
    then the line is decoded ``surrogateescape`` (non-UTF-8 script bytes
    round-trip).  A newline-terminated final line yields one empty line at EOF
    (FileInput ``split('\\n')`` parity — the dangling-``\\`` vs joined-``\\``
    distinction the gathering layer needs).
    """

    _NEWLINE = 0x0A  # b'\n'
    _BLOCK = 65536

    # A script-file argument is a bash STREAM input: a dangling backslash at
    # true EOF is dropped (see the base-class attribute).
    eof_drops_dangling_continuation: bool = True

    def __init__(self, file_path: str, state: Optional['ShellState'] = None):
        self.file_path = file_path
        # The reserved-fd registry the relocation hook consults. None for the
        # analysis path (read_text): analysis never executes, so no user
        # redirect can target the fd — registration is unnecessary there.
        self._state = state
        self._fd = -1
        self._seekable = True
        self._cursor: object = None  # InputCursor for the non-seekable path
        self._buf = b''
        self._pos = 0
        self._last_ended_with_newline = False
        self.line_number = 0

    def __enter__(self) -> 'LazyFileInput':
        raw = os.open(self.file_path, os.O_RDONLY)
        try:
            self._fd = _dup_cloexec_high(raw, _SCRIPT_FD_FLOOR)
        finally:
            os.close(raw)
        # A regular file is block-buffered (over-reading its PRIVATE fd is
        # invisible); a pipe/FIFO/dev-stdin must be read WITHOUT over-reading
        # (it may share fd 0's description) — bash's seekable-vs-unseekable rule.
        try:
            os.lseek(self._fd, 0, os.SEEK_CUR)
        except OSError:
            self._seekable = False
            from ..builtins.input_reader import InputCursor
            self._cursor = InputCursor(fd=self._fd)
        if self._state is not None:
            self._state.reserved_script_fds[self._fd] = self
        return self

    def __exit__(self, exc_type: object, exc_val: object,
                 exc_tb: object) -> None:
        self._close()

    def _close(self) -> None:
        if self._fd >= 0:
            if self._state is not None:
                self._state.reserved_script_fds.pop(self._fd, None)
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = -1

    def relocate_away_from(self, fd: int) -> None:
        """A PERMANENT redirect is about to seize ``fd``; if it is our script
        descriptor, dup it to a fresh high CLOEXEC slot and rebind.

        Called from ``FileRedirector.apply_permanent_redirections`` before the
        user's ``dup2``/close.  The old fd is left open — the user's redirect
        consumes it (``exec N>f`` dup2s over it, ``exec N<&-`` closes it) — while
        the reader continues from the relocated copy (shared open-file
        description, so the read offset is preserved).  Matches bash, which
        relocates its fd 255 when a permanent redirect targets it (probe O1).
        A temp redirect does NOT call this — its save/restore already preserves
        the descriptor (and bash does not relocate for temp redirects either).
        """
        if self._fd != fd or self._fd < 0:
            return
        new = _dup_cloexec_high(self._fd, _SCRIPT_FD_FLOOR)
        if self._state is not None:
            self._state.reserved_script_fds.pop(self._fd, None)
            self._state.reserved_script_fds[new] = self
        self._fd = new
        if not self._seekable:
            # The unseekable path's InputCursor holds the old fd. Relocation
            # only fires BETWEEN lines (during command execution), where a
            # never-over-read record cursor has no pending pushback/decoder
            # state, so rebuilding it on the relocated fd is lossless.
            from ..builtins.input_reader import InputCursor
            self._cursor = InputCursor(fd=new)

    def read_line(self) -> Optional[str]:
        """Read the next physical line, or None at true EOF.

        Never re-reads consumed bytes; a refill that lands at a grown EOF picks
        up appended bytes. Seekable sources are block-buffered; unseekable ones
        are read one record at a time (never over-read).
        """
        if self._seekable:
            return self._read_line_block()
        return self._read_line_record()

    def _read_line_block(self) -> Optional[str]:
        """Seekable path: serve a physical line from a bounded block buffer,
        refilling from the fd when the buffer holds no complete line."""
        while True:
            nl = self._buf.find(self._NEWLINE, self._pos)
            if nl != -1:
                raw = self._buf[self._pos:nl]
                self._pos = nl + 1
                self._last_ended_with_newline = True
                return self._decode_line(raw)
            # No complete line buffered: carry the partial tail and read more.
            tail = self._buf[self._pos:]
            try:
                block = os.read(self._fd, self._BLOCK) if self._fd >= 0 else b''
            except OSError:
                block = b''
            if not block:
                # True EOF at this moment (a regular file that grew would have
                # returned bytes). EOF is NOT cached — a later call re-reads.
                if tail:
                    self._buf = b''
                    self._pos = 0
                    self._last_ended_with_newline = False
                    return self._decode_line(tail)
                return self._final_empty_or_none()
            self._buf = tail + block
            self._pos = 0

    def _read_line_record(self) -> Optional[str]:
        """Unseekable path: read ONE record (never over-read) through the shared
        InputCursor, so an in-script `read` / a waiting FIFO producer keep the
        bytes this call did not consume."""
        cursor = self._cursor
        record = cursor.read_record_bytes(  # type: ignore[attr-defined]
            delimiter_byte=self._NEWLINE)
        if record is None:
            return self._final_empty_or_none()
        self._last_ended_with_newline = (
            cursor.last_record_hit_delimiter)  # type: ignore[attr-defined]
        return self._decode_line(record)

    def _final_empty_or_none(self) -> Optional[str]:
        """At true EOF, yield one empty final line when the last line was
        newline-terminated (FileInput split('\\n') parity — the dangling-\\ vs
        joined-\\ distinction), then None on the next call."""
        if self._last_ended_with_newline:
            self._last_ended_with_newline = False
            self.line_number += 1
            return ''
        return None

    def _decode_line(self, raw: bytes) -> str:
        """One physical line's bytes -> str: STREAM NUL strip, then CRLF, then
        surrogateescape decode. NUL first (matching FileInput's global
        strip-before-split), so ``abc\\r\\x00`` -> ``abc`` in both readers."""
        self.line_number += 1
        raw = raw.replace(b'\x00', b'')
        if raw.endswith(b'\r'):
            raw = raw[:-1]
        return raw.decode('utf-8', errors='surrogateescape')

    def is_interactive(self) -> bool:
        return False

    def get_name(self) -> str:
        return self.file_path

    def get_line_number(self) -> int:
        return self.line_number
