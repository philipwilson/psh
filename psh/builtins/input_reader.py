"""One streaming input service shared by the ``read`` and ``mapfile`` builtins.

Both builtins need the same thing: pull characters from an input source one
record at a time, without ever consuming past the record they asked for, so
whatever is left stays available to the next consumer. bash guarantees exactly
this — ``printf 'a\\nb\\n' | { read x; cat; }`` prints ``b`` — and it holds for
pipes, terminals and regular files alike. The reader below provides that single
primitive.

Design notes (educational shell — clarity over micro-optimizations):

* **UTF-8 safe.** A byte descriptor is decoded incrementally, so a multibyte
  character split across ``os.read`` boundaries decodes to the right character
  instead of a run of U+FFFD replacements. (The previous per-byte
  ``os.read(fd, 1).decode('utf-8', 'replace')`` mangled every multibyte char and
  even left an orphaned trailing byte in the stream for the next reader.)

* **Never over-reads.** Bytes are pulled one at a time from a non-seekable
  source, so the reader stops exactly at the delimiter/count boundary and the
  rest of the stream is untouched. This is the whole point of the service: a
  bulk ``os.read(fd, 65536)`` would drain a pipe and starve the next consumer.

* **Injectable source and sinks.** The source is either a real fd or a text
  stream (e.g. a ``StringIO`` under test); neither the reader nor its callers
  reach for the ``sys.stdin`` global. Echo, when requested, goes to a passed-in
  callback rather than a hard-wired ``sys.stdout``.

* **Monotonic total deadline.** A ``-t`` timeout is expressed as a single
  ``time.monotonic()`` deadline shared across the whole read, not a budget
  re-armed per byte, so slow trickled input cannot outlast the timeout.

* **Typed outcomes.** Every read returns a :class:`ReadResult` whose
  :class:`Outcome` says how it ended (DATA / EOF / TIMEOUT / ERROR), rather than
  threading bare status strings around.
"""
import enum
import io
import os
import select
import time
from typing import TYPE_CHECKING, Callable, Optional, TextIO

if TYPE_CHECKING:
    from ..shell import Shell


class Outcome(enum.Enum):
    """How a read terminated."""

    DATA = "data"        # delimiter found, or the requested char count reached
    EOF = "eof"          # input ended before the delimiter/count was reached
    TIMEOUT = "timeout"  # the -t deadline expired first
    ERROR = "error"      # a read error occurred (e.g. bad file descriptor)


class ReadResult:
    """The characters read plus how the read ended.

    ``data`` holds every character consumed for this record (the terminating
    delimiter is included only when ``include_delimiter`` was requested).
    ``hit_delimiter`` distinguishes a delimiter stop from a character-count stop
    when ``outcome is Outcome.DATA``. ``error`` carries the OSError on
    ``Outcome.ERROR``.
    """

    __slots__ = ("data", "outcome", "hit_delimiter", "error")

    def __init__(self, data: str, outcome: Outcome,
                 hit_delimiter: bool = False,
                 error: Optional[OSError] = None) -> None:
        self.data = data
        self.outcome = outcome
        self.hit_delimiter = hit_delimiter
        self.error = error

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (f"ReadResult(data={self.data!r}, outcome={self.outcome}, "
                f"hit_delimiter={self.hit_delimiter})")


class InputReader:
    """Record-oriented character reader over an fd or a text stream.

    Construct with exactly one source:

    * ``InputReader(fd=N)`` reads bytes from OS descriptor ``N`` and decodes
      them incrementally as UTF-8 (invalid bytes become U+FFFD, matching the
      shell's ``errors='replace'`` policy elsewhere).
    * ``InputReader(stream=obj)`` reads already-decoded characters from a text
      stream's ``read(1)`` (e.g. a ``StringIO`` test stdin). Text streams never
      block, so a deadline is not enforced against them.
    """

    def __init__(self, *, fd: Optional[int] = None,
                 stream: Optional[TextIO] = None) -> None:
        if (fd is None) == (stream is None):
            raise ValueError("InputReader needs exactly one of fd or stream")
        self._fd = fd
        self._stream = stream
        # Incremental UTF-8 decode state for the fd path: bytes gathered so far
        # for the character currently being assembled.
        self._partial = bytearray()

    # -- polling -------------------------------------------------------------

    def poll_readable(self) -> int:
        """``read -t 0``: 0 if a read would return without blocking, else 1.

        A ready fd (data waiting or at EOF — both are "readable" to select) and
        any text stream count as readable; a live fd with nothing buffered polls
        as would-block. Consumes nothing.
        """
        if self._fd is None:
            return 0  # a text stream never blocks
        if self._partial:
            return 0  # bytes already buffered mid-character
        try:
            ready, _, _ = select.select([self._fd], [], [], 0)
        except (OSError, ValueError):
            return 1
        return 0 if ready else 1

    # -- bulk drain ----------------------------------------------------------

    def read_all(self) -> str:
        """Drain the source to EOF and return it as text.

        For callers that will consume the entire input anyway (``mapfile`` with
        no line count reads to EOF, leaving nothing for a later reader — bash
        does the same). A bulk read is then behaviorally identical to reading
        record by record but far cheaper, so this is the one place the reader
        does large ``os.read`` blocks. Because it reads to EOF the whole byte
        run is decoded at once, so there is no multibyte-boundary concern. Do
        NOT use this when input must be left for a later consumer.
        """
        if self._stream is not None:
            return self._stream.read()
        assert self._fd is not None  # exactly one of fd/stream is set
        chunks = [bytes(self._partial)]  # any bytes buffered mid-character
        self._partial.clear()
        while True:
            try:
                block = os.read(self._fd, 65536)
            except OSError:
                break
            if not block:
                break
            chunks.append(block)
        return b''.join(chunks).decode('utf-8', errors='replace')

    # -- public record reads -------------------------------------------------

    def read_record(self, *, delimiter: str, include_delimiter: bool,
                    deadline: Optional[float] = None,
                    on_char: Optional[Callable[[str], None]] = None
                    ) -> ReadResult:
        """Read up to and including the next ``delimiter`` (or to EOF/timeout).

        Used for a whole line (``read`` with no ``-n``) and by ``mapfile`` for
        one array element.
        """
        return self._read(delimiter=delimiter, max_chars=None,
                          include_delimiter=include_delimiter,
                          deadline=deadline, on_char=on_char)

    def read_limited(self, *, delimiter: Optional[str], max_chars: int,
                     deadline: Optional[float] = None,
                     on_char: Optional[Callable[[str], None]] = None
                     ) -> ReadResult:
        """Read at most ``max_chars`` characters, stopping early at ``delimiter``.

        ``read -n``: the delimiter still terminates the read. Pass
        ``delimiter=None`` to ignore any delimiter and stop only on the count
        (``read -N``).
        """
        return self._read(delimiter=delimiter, max_chars=max_chars,
                          include_delimiter=False, deadline=deadline,
                          on_char=on_char)

    def read_record_bytes(self, *, delimiter_byte: int) -> Optional[bytes]:
        """Read raw bytes up to (not including) ``delimiter_byte``, or to EOF.

        The byte-oriented sibling of :meth:`read_record`: it never over-reads
        the source, so the rest of the stream stays available to the next
        consumer — the same guarantee that lets a ``read`` inside a stdin script
        consume the SUBSEQUENT physical lines as data. It returns the bytes read
        WITHOUT the delimiter, or ``None`` at a clean EOF (nothing buffered, the
        source ended). A final record with no trailing delimiter returns its
        bytes; the NEXT call then returns ``None``.

        Unlike :meth:`read_record` this does not decode: the caller owns the
        decode policy. The lazy stdin-as-script reader (``StdinInput``) splits on
        the newline byte here and decodes each physical line with
        ``errors='surrogateescape'`` so a non-UTF-8 script byte round-trips
        exactly as the ``FileInput`` script path treats it — which the
        ``errors='replace'`` char decode would not preserve.
        """
        if self._stream is not None:
            # Already-decoded text source (e.g. a StringIO test stdin): read one
            # char to the delimiter and re-encode with the surrogateescape
            # policy the caller decodes with, keeping the return type uniform.
            delim = chr(delimiter_byte)
            chars: list = []
            while True:
                ch = self._stream.read(1)
                if ch == '':
                    if not chars:
                        return None
                    break
                if ch == delim:
                    break
                chars.append(ch)
            return ''.join(chars).encode('utf-8', errors='surrogateescape')
        assert self._fd is not None  # exactly one of fd/stream is set
        # Any bytes buffered mid-character by a prior char read cannot be the
        # delimiter (it is an ASCII byte; a buffered byte is a multibyte
        # continuation), so draining them first is safe.
        buf = bytearray(self._partial)
        self._partial.clear()
        while True:
            byte, outcome, _err = self._next_byte(None)
            if outcome is not Outcome.DATA:
                # EOF/ERROR before the delimiter: return the partial record, or
                # None for a truly empty clean EOF.
                return bytes(buf) if buf else None
            if byte == delimiter_byte:
                return bytes(buf)
            buf.append(byte)

    # -- core loop -----------------------------------------------------------

    def _read(self, *, delimiter: Optional[str], max_chars: Optional[int],
              include_delimiter: bool, deadline: Optional[float],
              on_char: Optional[Callable[[str], None]]) -> ReadResult:
        chars: list = []
        while max_chars is None or len(chars) < max_chars:
            ch, outcome, err = self._next_char(deadline)
            if outcome is not Outcome.DATA:
                # Input ended / timed out / errored before a delimiter or the
                # count. Whatever was gathered is returned as a partial record.
                return ReadResult(''.join(chars), outcome, error=err)
            if delimiter is not None and ch == delimiter:
                if include_delimiter:
                    chars.append(ch)
                return ReadResult(''.join(chars), Outcome.DATA,
                                  hit_delimiter=True)
            chars.append(ch)
            if on_char is not None:
                on_char(ch)
        # Reached the character count without hitting a delimiter.
        return ReadResult(''.join(chars), Outcome.DATA, hit_delimiter=False)

    def _next_char(self, deadline: Optional[float]):
        """Return ``(char, Outcome.DATA, None)`` or ``(None, <end>, err)``."""
        if self._stream is not None:
            ch = self._stream.read(1)
            if ch == '':
                return None, Outcome.EOF, None
            return ch, Outcome.DATA, None
        return self._next_char_from_fd(deadline)

    # -- fd path: incremental UTF-8 decode -----------------------------------

    def _next_char_from_fd(self, deadline: Optional[float]):
        """Assemble one UTF-8 character from the byte descriptor.

        Reads exactly the bytes of one character (never lookahead), so a
        non-seekable stream is never consumed past the character returned.
        """
        while True:
            byte, outcome, err = self._next_byte(deadline)
            if outcome is not Outcome.DATA:
                if outcome is Outcome.EOF and self._partial:
                    # Truncated multibyte sequence at EOF: emit one replacement
                    # for the dangling bytes, then let EOF surface next call.
                    self._partial.clear()
                    return '�', Outcome.DATA, None
                return None, outcome, err

            self._partial.append(byte)
            char = self._try_decode()
            if char is not None:
                return char, Outcome.DATA, None
            # else: need more continuation bytes for this character.

    def _try_decode(self) -> Optional[str]:
        """Decode ``self._partial`` if it now holds one complete character.

        Returns the character (clearing the buffer), or ``None`` if more
        continuation bytes are still needed. A byte sequence that cannot form a
        valid character resolves to U+FFFD so the reader always makes progress.
        """
        first = self._partial[0]
        if first < 0x80:
            expected = 1
        elif first >> 5 == 0b110:
            expected = 2
        elif first >> 4 == 0b1110:
            expected = 3
        elif first >> 3 == 0b11110:
            expected = 4
        else:
            # Continuation byte or invalid lead byte with nothing to attach to:
            # not a valid start, so this single byte is a decode error.
            self._partial.clear()
            return '�'

        # Any byte after the first that is not a 0b10xxxxxx continuation means
        # the sequence is malformed: the current char is a replacement and the
        # offending byte starts the next character.
        for b in self._partial[1:]:
            if b >> 6 != 0b10:
                self._partial = bytearray([b])
                return '�'

        if len(self._partial) < expected:
            return None  # still gathering continuation bytes

        try:
            char = self._partial.decode('utf-8')
        except UnicodeDecodeError:
            char = '�'
        self._partial.clear()
        return char

    def _next_byte(self, deadline: Optional[float]):
        """Read one byte from the fd, honoring the shared deadline."""
        assert self._fd is not None  # only reached on the fd path
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None, Outcome.TIMEOUT, None
            try:
                ready, _, _ = select.select([self._fd], [], [], remaining)
            except (OSError, ValueError) as e:
                return None, Outcome.ERROR, e if isinstance(e, OSError) else None
            if not ready:
                return None, Outcome.TIMEOUT, None
        try:
            chunk = os.read(self._fd, 1)
        except OSError as e:
            return None, Outcome.ERROR, e
        if not chunk:
            return None, Outcome.EOF, None
        return chunk[0], Outcome.DATA, None


def make_reader(shell: 'Shell', fd: int) -> InputReader:
    """Build an :class:`InputReader` for a builtin reading from ``fd``.

    The real OS descriptor is authoritative whenever it is valid — this covers
    redirections in forked subshells (``( ... ) < file``), pipes and files,
    where ``fd`` was set up with ``os.dup2`` even though the shell's text-level
    stdin is a Python object a test may have swapped out. The text stream is
    used only for a genuine in-process replacement (e.g. a ``StringIO`` test
    stdin with no real ``fileno``). pytest's ``DontReadFromInput`` capture object
    is treated as "use the real fd" so redirected reads work under capture.

    Reading ``shell.stdin`` rather than the ``sys.stdin`` global keeps the source
    injectable: a test can install ``shell.stdin = StringIO(...)`` and this
    resolver honors it, while still falling through to the live ``sys.stdin``
    when nothing is overridden.
    """
    stream = shell.stdin
    if 'DontReadFromInput' in stream.__class__.__name__:
        return InputReader(fd=fd)
    try:
        stream.fileno()
    except (AttributeError, io.UnsupportedOperation):
        return InputReader(stream=stream)
    try:
        os.fstat(fd)
        return InputReader(fd=fd)
    except (OSError, AttributeError, ValueError):
        return InputReader(stream=stream)
