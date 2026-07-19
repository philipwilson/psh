"""The source-lifetime byte cursor shared by ``read``, ``mapfile`` and script
input.

Every consumer needs the same primitive: pull records/characters from one open
file description without ever consuming past the record it asked for, so
whatever is left stays available to the next consumer. bash guarantees exactly
this — ``printf 'a\\nb\\n' | { read x; cat; }`` prints ``b`` — for pipes,
terminals and regular files alike. :class:`InputCursor` provides that primitive.

Design notes (educational shell — clarity over micro-optimizations):

* **Byte-preserving, surrogateescape round-trip (campaign I1 / #20 H16).** The
  fd byte stream is decoded through ONE incremental UTF-8 decoder with
  ``errors='surrogateescape'``. A valid multibyte character split across
  ``os.read`` boundaries still decodes to the right character; a MALFORMED byte
  round-trips as a lone surrogate (``\\udc80``-``\\udcff``) that
  ``.encode('utf-8', 'surrogateescape')`` restores to the exact byte on output.
  This replaced a hand-rolled decoder that used ``errors='replace'`` (U+FFFD)
  and, worse, mis-read the byte after a malformed lead as a continuation —
  eating record delimiters and cascading every following record into
  replacement characters (#20 H16). The model is a deliberate HYBRID: a valid
  multibyte char is one char (like a UTF-8 locale), a malformed byte is one
  surrogate char (like the C locale's byte-per-char). It does NOT replicate a
  particular libc's ``mbrtowc`` quirks (an incomplete lead swallowing the
  following delimiter, ``read -N`` over-reading on a trailing incomplete lead);
  those are documented deliberate divergences.

* **Never over-reads.** Bytes are pulled one at a time from a non-seekable
  source, so a record read stops exactly at the delimiter boundary and the rest
  of the stream is untouched. A bulk ``os.read(fd, 65536)`` would drain a pipe
  and starve the next consumer.

* **Decoded queue owned across reads.** One byte feed can emit more than one
  character (a buffered malformed lead resolves to a surrogate PLUS the byte
  that disambiguated it). The surplus is held in :attr:`_decoded` and belongs to
  the cursor's lifetime, not one ``read`` call — so a ``read -N 1`` that split a
  malformed multibyte leaves the surplus for the NEXT read on this cursor
  (see :mod:`psh.io_redirect` for how a cursor is keyed to an open-file
  description so ``exec 3<&0`` shares it).

* **Injectable source and sinks.** The source is either a real fd or a text
  stream (e.g. a ``StringIO`` under test); neither the cursor nor its callers
  reach for the ``sys.stdin`` global. Echo, when requested, goes to a passed-in
  callback rather than a hard-wired ``sys.stdout``.

* **Monotonic total deadline.** A ``-t`` timeout is expressed as a single
  ``time.monotonic()`` deadline shared across the whole read, not a budget
  re-armed per byte, so slow trickled input cannot outlast the timeout.

* **Typed outcomes.** Every read returns a :class:`ReadResult` whose
  :class:`Outcome` says how it ended (DATA / EOF / TIMEOUT / ERROR), rather than
  threading bare status strings around.
"""
import codecs
import enum
import io
import os
import select
import time
from collections import deque
from typing import TYPE_CHECKING, Callable, Deque, Optional, TextIO

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


class InputCursor:
    """Record-oriented byte cursor over an fd or an injected text stream.

    Construct with exactly one source:

    * ``InputCursor(fd=N)`` reads bytes from OS descriptor ``N`` and decodes
      them incrementally as UTF-8 with ``errors='surrogateescape'`` (a malformed
      byte round-trips as a lone surrogate).
    * ``InputCursor(stream=obj)`` reads already-decoded characters from a text
      stream's ``read(1)`` (e.g. a ``StringIO`` test stdin). Text streams never
      block, so a deadline is not enforced against them.

    The cursor owns per-open-description state that outlives one ``read`` call:
    the incremental decoder, the decoded-character queue, the raw byte pushback
    used by the byte-record path, and the last-delimiter flag. EOF is NOT cached
    — a fresh attempt re-reads the fd, matching a terminal whose ``Ctrl-D`` is
    one-shot rather than sticky.
    """

    def __init__(self, *, fd: Optional[int] = None,
                 stream: Optional[TextIO] = None) -> None:
        if (fd is None) == (stream is None):
            raise ValueError("InputCursor needs exactly one of fd or stream")
        self._fd = fd
        self._stream = stream
        # Char path (fd source): ONE incremental UTF-8 surrogateescape decoder
        # spanning every read on this cursor, and the queue of characters it has
        # emitted but a read has not yet consumed (a byte feed can emit several).
        self._decoder: Optional[codecs.IncrementalDecoder] = None
        self._decoded: Deque[str] = deque()
        # Byte-record path (StdinInput): raw bytes read past a record boundary,
        # held for the next byte-record read. The char path never touches this
        # (a cursor is used for one path or the other; they are never mixed).
        self._pushback = bytearray()
        # Whether the most recent read_record_bytes record ended AT its
        # delimiter (True) or at EOF/error (False). StdinInput consults it to
        # tell a newline-terminated final line from an unterminated one.
        self.last_record_hit_delimiter = False

    @property
    def fd(self) -> Optional[int]:
        """The OS descriptor this cursor reads, or ``None`` for a stream source.

        The :class:`~psh.io_redirect.input_cursor.InputCursorRegistry` reads this
        to decide whether a cursor is keyed to an open-file-description (fd-based,
        persisted) or is a per-call stream-backed cursor (not persisted).
        """
        return self._fd

    def _get_decoder(self) -> codecs.IncrementalDecoder:
        if self._decoder is None:
            self._decoder = codecs.getincrementaldecoder('utf-8')(
                'surrogateescape')
        return self._decoder

    # -- polling -------------------------------------------------------------

    def poll_readable(self) -> int:
        """``read -t 0``: 0 if a read would return without blocking, else 1.

        A ready fd (data waiting or at EOF — both are "readable" to select) and
        any text stream count as readable; a live fd with nothing buffered polls
        as would-block. Consumes nothing.
        """
        if self._fd is None:
            return 0  # a text stream never blocks
        if self._decoded or self._pushback:
            return 0  # characters/bytes already buffered on this cursor
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
        does the same). Decoding is still ``surrogateescape`` so a non-UTF-8
        byte round-trips; because it reads to EOF the whole byte run is decoded
        at once, so there is no multibyte-boundary concern. Do NOT use this when
        input must be left for a later consumer.
        """
        if self._stream is not None:
            return self._stream.read()
        assert self._fd is not None  # exactly one of fd/stream is set
        # Any characters already decoded on this cursor come first, then any raw
        # pushback bytes, then the rest of the descriptor.
        prefix = ''.join(self._decoded)
        self._decoded.clear()
        chunks = [bytes(self._pushback)]
        self._pushback.clear()
        while True:
            try:
                block = os.read(self._fd, 65536)
            except OSError:
                break
            if not block:
                break
            chunks.append(block)
        # A fresh decoder drains any character the cursor's decoder was still
        # assembling, then the bulk bytes, so a split multibyte at the seam is
        # not lost.
        pending = self._get_decoder().decode(b'', final=True)
        self._decoder = None
        tail = b''.join(chunks).decode('utf-8', errors='surrogateescape')
        return prefix + pending + tail

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

        Unlike :meth:`read_record` this does not decode: **the caller owns the
        decode policy**. ``read``/``mapfile`` decode through :meth:`read_record`
        (incremental surrogateescape); ``StdinInput`` splits on the newline byte
        here and batch-decodes each physical line, also with surrogateescape.
        Because the delimiter (newline/NUL/colon) is always a single ASCII byte
        that can never be a UTF-8 continuation byte, splitting at the byte level
        before decoding is exact for either caller.
        """
        if self._stream is not None:
            # Already-decoded text source (e.g. a StringIO test stdin): read one
            # char to the delimiter and re-encode with the surrogateescape
            # policy the caller decodes with, keeping the return type uniform.
            delim = chr(delimiter_byte)
            chars: list = []
            self.last_record_hit_delimiter = False
            while True:
                ch = self._stream.read(1)
                if ch == '':
                    if not chars:
                        return None
                    break
                if ch == delim:
                    self.last_record_hit_delimiter = True
                    break
                chars.append(ch)
            return ''.join(chars).encode('utf-8', errors='surrogateescape')
        assert self._fd is not None  # exactly one of fd/stream is set
        # Honor a delimiter already among the pushback and push the remainder
        # back, so a record boundary can never be skipped.
        drained = bytes(self._pushback)
        self._pushback.clear()
        split = drained.find(delimiter_byte)
        if split != -1:
            self._pushback = bytearray(drained[split + 1:])
            self.last_record_hit_delimiter = True
            return drained[:split]
        buf = bytearray(drained)
        while True:
            byte, outcome, _err = self._next_byte(None)
            if outcome is not Outcome.DATA:
                # EOF/ERROR before the delimiter: return the partial record, or
                # None for a truly empty clean EOF.
                self.last_record_hit_delimiter = False
                return bytes(buf) if buf else None
            if byte == delimiter_byte:
                self.last_record_hit_delimiter = True
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

    # -- fd path: incremental surrogateescape decode -------------------------

    def _next_char_from_fd(self, deadline: Optional[float]):
        """Return the next decoded character from the byte descriptor.

        Reads exactly the bytes needed to emit the next character (at most one
        byte of lookahead, to disambiguate a malformed lead), so a record read
        never consumes past its delimiter. A byte feed that emits several
        characters (a malformed lead resolved to a surrogate PLUS the following
        byte) leaves the surplus in :attr:`_decoded` for the next read.
        """
        while True:
            if self._decoded:
                return self._decoded.popleft(), Outcome.DATA, None
            byte, outcome, err = self._next_byte(deadline)
            if outcome is not Outcome.DATA:
                if outcome is Outcome.EOF:
                    # Flush any bytes the decoder was still assembling as
                    # surrogates (a truncated multibyte at EOF round-trips).
                    tail = self._get_decoder().decode(b'', final=True)
                    self._decoder = None  # EOF may be transient (tty Ctrl-D)
                    if tail:
                        self._decoded.extend(tail)
                        return self._decoded.popleft(), Outcome.DATA, None
                return None, outcome, err
            emitted = self._get_decoder().decode(bytes([byte]))
            if emitted:
                self._decoded.extend(emitted)
            # else: the decoder is buffering a multibyte lead; read another byte.

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


#: Backwards-compatible alias. ``InputReader`` was renamed to the typed
#: :class:`InputCursor` (campaign I1); the old name is retained so external
#: references keep resolving during the migration window.
InputReader = InputCursor


def make_reader(shell: 'Shell', fd: int) -> InputCursor:
    """Build an :class:`InputCursor` for a builtin reading from ``fd``.

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
        return InputCursor(fd=fd)
    try:
        stream.fileno()
    except (AttributeError, io.UnsupportedOperation):
        return InputCursor(stream=stream)
    try:
        os.fstat(fd)
        return InputCursor(fd=fd)
    except (OSError, AttributeError, ValueError):
        return InputCursor(stream=stream)
