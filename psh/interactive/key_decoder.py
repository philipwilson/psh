"""Terminal key decoding for the interactive line editor.

``KeyDecoder`` is THE only reader of the editor's input file descriptor
(Textbook B8 R2). It owns the raw fd, the decoded-character buffer, the
``select()`` multiplexing of input with the SIGWINCH self-pipe, and the
escape-sequence state machine. ``read_key()`` returns one ``KeyEvent``
— a small closed algebra of event types — and always consumes escape
sequences in full, so partial CSI bytes never leak to the caller.

Layering rule (what the decoder does NOT know): the MEANING of a key is
mode policy and lives in ``LineEditor``. The decoder reports what
arrived on the wire — ``Escape`` when ESC stood alone, ``Key('up')``
when a CSI/SS3 sequence followed, ``Meta('f')`` when an ordinary
character followed — and the editor decides whether a bare ESC enters
vi normal mode, whether Meta('f') means move-word-forward, and so on.

The one timing knob, ``esc_timeout``, parameterizes the classic ESC
disambiguation problem: ESC is both a key of its own (vi mode) and the
first byte of every escape sequence. Terminals transmit a sequence's
bytes in a single burst, so "did another byte arrive within the
window?" reliably tells a human ESC keypress from a sequence
introducer. See ``ESC_FOLLOWER_TIMEOUT``.
"""

import os
import select
from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional

#: Seconds to wait after ESC for a possible sequence follower before
#: reporting a bare ``Escape``. Used in vi mode only; emacs mode passes
#: ``esc_timeout=None`` and blocks for the follower, because there ESC
#: is meaningful only as a Meta/sequence prefix, never as a key.
#: Terminals send a sequence's bytes in one sub-millisecond burst, so
#: 50 ms is generous for sequence detection while keeping vi-mode ESC
#: feel instantaneous — deliberately snappier than readline's 500 ms
#: ``keyseq-timeout`` and zsh's 400 ms ``KEYTIMEOUT`` defaults. The
#: value is inherited unchanged from ``LineEditor._input_pending``
#: (v0.283); changing it changes the feel of vi mode.
ESC_FOLLOWER_TIMEOUT = 0.05


class KeyEvent:
    """Base class for decoded input events (a small closed algebra:
    Char, Key, Meta, Escape, Resize, Eof)."""
    __slots__ = ()


@dataclass(frozen=True)
class Char(KeyEvent):
    """A literal character — printable or control.

    Ctrl-C arrives here as ``Char('\\x03')``: in raw mode ISIG is off,
    so ^C is an ordinary byte on the fd, and its meaning (the
    'interrupt' action) is keybinding policy in the editor, exactly as
    before the extraction. Interrupts are NOT a decoder-level event.
    """
    char: str


@dataclass(frozen=True)
class Key(KeyEvent):
    """A named function key decoded from a full CSI/SS3 sequence.

    ``name`` is one of 'up', 'down', 'right', 'left', 'home', 'end',
    'delete' — or None for a complete but unrecognized sequence
    (modifier combos, CPR responses, ...), which is consumed in full
    and reported so the editor can ignore it without the sequence's
    bytes ever reaching the edit buffer.
    """
    name: Optional[str]


@dataclass(frozen=True)
class Meta(KeyEvent):
    """ESC followed by an ordinary character within the follower
    window (or at any time when ``esc_timeout`` is None). What the
    combination MEANS — emacs Meta/Alt combo vs. vi "enter normal mode,
    then run the key" — is the editor's mode policy."""
    char: str


@dataclass(frozen=True)
class Escape(KeyEvent):
    """A bare ESC keypress: no follower arrived within the window."""


@dataclass(frozen=True)
class Resize(KeyEvent):
    """The SIGWINCH self-pipe became readable (terminal resized).
    The pipe has already been drained."""


@dataclass(frozen=True)
class Eof(KeyEvent):
    """The input stream ended (read returned no data)."""


# Singleton instances for the parameterless events.
ESCAPE = Escape()
RESIZE = Resize()
EOF = Eof()


class KeyDecoder:
    """Decode raw terminal input into ``KeyEvent`` objects.

    Args:
        fd: Input file descriptor (the terminal, already in raw mode).
        sigwinch_fd: Optional read end of the SIGWINCH self-pipe. When
            given, ``read_key()`` multiplexes it with *fd*; a readable
            sigwinch pipe is drained and yields ``RESIZE``.
        esc_timeout: Seconds to wait for an ESC follower before
            reporting a bare ``ESCAPE``; None blocks indefinitely (ESC
            is then always a prefix, never a key of its own).
    """

    # CSI final bytes with no parameters: ESC [ X
    _CSI_FINAL_KEYS = {
        'A': 'up', 'B': 'down', 'C': 'right', 'D': 'left',
        'H': 'home', 'F': 'end',
    }
    # CSI tilde sequences: ESC [ params ~
    _CSI_TILDE_KEYS = {
        '1': 'home', '3': 'delete', '4': 'end', '7': 'home', '8': 'end',
    }
    # SS3 sequences (application cursor mode): ESC O X
    _SS3_KEYS = {
        'A': 'up', 'B': 'down', 'C': 'right', 'D': 'left',
        'H': 'home', 'F': 'end',
    }

    def __init__(self, fd: int, sigwinch_fd: Optional[int] = None,
                 esc_timeout: Optional[float] = ESC_FOLLOWER_TIMEOUT) -> None:
        self.fd = fd
        self.sigwinch_fd = sigwinch_fd
        self.esc_timeout = esc_timeout
        # Decoded-but-undelivered characters. os.read() is used instead
        # of sys.stdin.read(1) to bypass Python's BufferedReader: when
        # text is pasted, BufferedReader would consume all available
        # bytes from the fd but return only one character, making the
        # rest invisible to select(). Reading the raw fd and buffering
        # decoded characters here keeps select() and reads in sync.
        # A deque: the buffer is a FIFO consumed from the front
        # (popleft) with occasional front pushes (pushback/seed) and
        # back extends — all O(1), unlike a list's O(n) pop(0)/insert(0).
        self._char_buf: Deque[str] = deque()

    def pushback(self, char: str) -> None:
        """Make *char* the next character read.

        Used by the editor to hand the second ESC of a vi-mode ESC-ESC
        pair back for full disambiguation (it may introduce a sequence
        of its own).
        """
        self._char_buf.appendleft(char)

    def take_buffered(self) -> List[str]:
        """Hand off (and clear) characters read from the fd but not yet
        consumed — the tail of a multi-line paste. The next decoder is
        seeded with these (see ``seed``) so a paste's later commands run
        in turn instead of being dropped."""
        buffered = list(self._char_buf)
        self._char_buf.clear()
        return buffered

    def seed(self, chars: List[str]) -> None:
        """Prepend already-decoded characters ahead of any fresh fd
        input — the paste tail carried over from the previous decoder."""
        # extendleft reverses, so feed it reversed to preserve order.
        self._char_buf.extendleft(reversed(chars))

    def read_key(self) -> KeyEvent:
        """Read one key event (blocking).

        May raise OSError (e.g. EIO when the terminal disconnects);
        terminal-mode recovery is the caller's job — the decoder owns
        the fd's *traffic*, not the terminal's *modes*.
        """
        # Only select() when the character buffer is empty: buffered
        # characters (the tail of a paste, a pushed-back key) must be
        # delivered before new fd traffic, and they are invisible to
        # select(). Without a sigwinch pipe there is nothing to
        # multiplex, so plain blocking reads suffice.
        if self.sigwinch_fd is not None and not self._char_buf:
            readable, _, _ = select.select(
                [self.fd, self.sigwinch_fd], [], [])
            if self.sigwinch_fd in readable:
                self._drain_sigwinch()
                return RESIZE

        char = self._read_char()
        if not char:
            return EOF
        if char == '\x1b':
            return self._decode_escape()
        return Char(char)

    # ------------------------------------------------------------------
    # ESC disambiguation
    # ------------------------------------------------------------------

    def _decode_escape(self) -> KeyEvent:
        """ESC just arrived: bare key, sequence introducer, or Meta
        prefix?

        With a timeout (vi mode), a silent window means a human pressed
        ESC alone. Without one (emacs mode), block for the follower —
        a bare ESC then simply waits to become a Meta combination,
        matching the pre-decoder behavior exactly.
        """
        if self.esc_timeout is not None and not self._input_pending(self.esc_timeout):
            return ESCAPE

        follower = self._read_char()
        if follower in ('[', 'O'):
            return Key(self._read_sequence(follower))
        if not follower:
            # Stream ended right after ESC. In probing mode the pending
            # check was won by EOF (a closed fd selects readable):
            # report the bare ESC. In blocking mode report Meta('') —
            # the editor's meta-binding lookup misses and the next
            # read_key() returns EOF, as before the extraction.
            return ESCAPE if self.esc_timeout is not None else Meta('')
        return Meta(follower)

    def _input_pending(self, timeout: float) -> bool:
        """True if more input is already buffered or arrives within
        *timeout* seconds (terminals transmit escape sequences in a
        single burst, so this tells a bare ESC keypress from the ESC
        that introduces a sequence)."""
        if self._char_buf:
            return True
        if self.fd < 0:
            return False
        try:
            ready, _, _ = select.select([self.fd], [], [], timeout)
        except OSError:
            return False
        return bool(ready)

    def _read_sequence(self, intro: str) -> Optional[str]:
        """THE escape-sequence reader: the only input-side ANSI parser.

        Called with ESC and the intro byte ('[' for CSI, 'O' for SS3)
        already consumed. Reads the remainder of the sequence and
        returns a symbolic key name ('up', 'down', 'left', 'right',
        'home', 'end', 'delete') or None. Unrecognized sequences are
        consumed in full so they never leak into the edit buffer.
        """
        if intro == 'O':
            # SS3: exactly one final byte
            return self._SS3_KEYS.get(self._read_char())

        # CSI: parameter/intermediate bytes, then a final byte @ .. ~
        params: List[str] = []
        while True:
            ch = self._read_char()
            if not ch:
                return None
            if '\x40' <= ch <= '\x7e':
                final = ch
                break
            params.append(ch)

        if not params:
            return self._CSI_FINAL_KEYS.get(final)
        if final == '~':
            return self._CSI_TILDE_KEYS.get(''.join(params))
        # Parameterised sequences we don't handle (modifiers, CPR
        # responses ESC[r;cR, ...) are silently discarded.
        return None

    # ------------------------------------------------------------------
    # Raw fd reading
    # ------------------------------------------------------------------

    def _read_char(self) -> str:
        """Read one character: from the buffer, else the raw fd (see
        the ``_char_buf`` comment in ``__init__`` for why os.read)."""
        if self._char_buf:
            return self._char_buf.popleft()

        data = os.read(self.fd, 4096)
        if not data:
            return ''

        chars = data.decode('utf-8', errors='replace')
        if len(chars) > 1:
            self._char_buf.extend(chars[1:])
        return chars[0] if chars else ''

    def _drain_sigwinch(self) -> None:
        """Empty the SIGWINCH self-pipe so queued resize notifications
        coalesce into the single RESIZE event being returned.

        The zero-timeout select between reads makes this safe for both
        the real (non-blocking) notifier pipe and a plain test pipe.
        """
        assert self.sigwinch_fd is not None
        while True:
            try:
                data = os.read(self.sigwinch_fd, 4096)
            except OSError:
                return  # EAGAIN on the non-blocking notifier pipe
            if not data:
                return
            ready, _, _ = select.select([self.sigwinch_fd], [], [], 0)
            if not ready:
                return
