"""Pipe-fed unit tests for KeyDecoder (Textbook B8 R2).

A real os.pipe() stands in for the terminal fd: each test writes the
byte stream a terminal would transmit and asserts the decoded KeyEvent
stream. The ESC-disambiguation window is exercised for real — a pipe
with nothing pending IS the silent terminal after a bare ESC keypress,
so the timing tests drive the actual select() probe rather than mocks.

No TTY and no raw mode are involved; everything here is fd traffic.
"""

import errno
import os
import select
import threading
import time
from unittest.mock import patch

import pytest

from psh.interactive.key_decoder import (
    EOF,
    ESC_FOLLOWER_TIMEOUT,
    ESCAPE,
    RESIZE,
    Char,
    Key,
    KeyDecoder,
    Meta,
)

# A short follower window keeps the wait-out-the-probe tests fast while
# still being enormous next to a same-burst write.
FAST = 0.02


@pytest.fixture
def stream():
    """A pipe standing in for the terminal: (read_fd, write_fd)."""
    r, w = os.pipe()
    yield r, w
    for fd in (r, w):
        try:
            os.close(fd)
        except OSError:
            pass


def probing(r, **kw):
    """Decoder in vi-style probing mode (bare ESC is a key)."""
    kw.setdefault('esc_timeout', FAST)
    return KeyDecoder(r, **kw)


def blocking(r, **kw):
    """Decoder in emacs-style blocking mode (ESC is only a prefix)."""
    return KeyDecoder(r, esc_timeout=None, **kw)


def write_later(w, data, delay):
    """Write *data* to fd *w* after *delay* seconds, from a thread."""
    t = threading.Timer(delay, os.write, args=(w, data))
    t.start()
    return t


class TestPlainCharacters:
    def test_single_char(self, stream):
        r, w = stream
        os.write(w, b'a')
        assert probing(r).read_key() == Char('a')

    def test_burst_yields_chars_in_order(self, stream):
        r, w = stream
        os.write(w, b'ab\r')
        dec = probing(r)
        assert [dec.read_key() for _ in range(3)] == \
            [Char('a'), Char('b'), Char('\r')]

    def test_control_char_is_a_char_not_an_event(self, stream):
        # ^C arrives as a byte in raw mode (ISIG off); its meaning —
        # the 'interrupt' action — is keybinding policy in the editor.
        # The decoder must NOT invent an Interrupt event for it.
        r, w = stream
        os.write(w, b'\x03')
        assert probing(r).read_key() == Char('\x03')

    def test_utf8_multibyte_char(self, stream):
        r, w = stream
        os.write(w, 'é'.encode('utf-8'))
        assert probing(r).read_key() == Char('é')

    def test_eof_when_stream_closes(self, stream):
        r, w = stream
        os.close(w)
        assert probing(r).read_key() == EOF


class TestSequences:
    """Every CSI/SS3 entry in the decoder's tables."""

    @pytest.mark.parametrize("final,key", [
        ('A', 'up'), ('B', 'down'), ('C', 'right'), ('D', 'left'),
        ('H', 'home'), ('F', 'end'),
    ])
    def test_csi_final_keys(self, stream, final, key):
        r, w = stream
        os.write(w, f'\x1b[{final}'.encode())
        assert probing(r).read_key() == Key(key)

    @pytest.mark.parametrize("params,key", [
        ('1~', 'home'), ('3~', 'delete'), ('4~', 'end'),
        ('7~', 'home'), ('8~', 'end'),
    ])
    def test_csi_tilde_keys(self, stream, params, key):
        r, w = stream
        os.write(w, f'\x1b[{params}'.encode())
        assert probing(r).read_key() == Key(key)

    @pytest.mark.parametrize("final,key", [
        ('A', 'up'), ('B', 'down'), ('C', 'right'), ('D', 'left'),
        ('H', 'home'), ('F', 'end'),
    ])
    def test_ss3_keys(self, stream, final, key):
        r, w = stream
        os.write(w, f'\x1bO{final}'.encode())
        assert probing(r).read_key() == Key(key)

    def test_sequences_decode_in_blocking_mode_too(self, stream):
        r, w = stream
        os.write(w, b'\x1b[A\x1bOB')
        dec = blocking(r)
        assert dec.read_key() == Key('up')
        assert dec.read_key() == Key('down')

    def test_unrecognized_csi_consumed_in_full(self, stream):
        # Ctrl-Right (xterm modifier form): unknown, but must be fully
        # consumed so 'C' never leaks out as a literal character.
        r, w = stream
        os.write(w, b'\x1b[1;5Cx')
        dec = probing(r)
        assert dec.read_key() == Key(None)
        assert dec.read_key() == Char('x')

    def test_eof_mid_csi_params_swallows_sequence(self, stream):
        r, w = stream
        os.write(w, b'\x1b[1;')  # stream ends before the final byte
        os.close(w)
        dec = probing(r)
        assert dec.read_key() == Key(None)
        assert dec.read_key() == EOF

    def test_partial_csi_completed_by_later_bytes(self, stream):
        # The introducer arrives in one burst, the final byte later:
        # the decoder blocks mid-sequence and finishes it — a partial
        # CSI is never abandoned in the buffer.
        r, w = stream
        os.write(w, b'\x1b[')
        t = write_later(w, b'A', FAST / 2)
        try:
            assert probing(r).read_key() == Key('up')
        finally:
            t.join()


class TestEscDisambiguation:
    """The 50 ms window: what byte timings produce what events."""

    def test_bare_esc_yields_escape_after_window(self, stream):
        r, w = stream
        os.write(w, b'\x1b')
        start = time.monotonic()
        assert probing(r).read_key() == ESCAPE
        # The probe must actually wait out the (shortened) window.
        assert time.monotonic() - start >= FAST * 0.8

    def test_esc_with_same_burst_follower_is_meta(self, stream):
        r, w = stream
        os.write(w, b'\x1bf')
        assert probing(r).read_key() == Meta('f')

    def test_esc_then_late_key_are_separate_events(self, stream):
        # Slower than the window: a human ESC, then a normal key.
        r, w = stream
        os.write(w, b'\x1b')
        dec = probing(r)
        assert dec.read_key() == ESCAPE
        os.write(w, b'f')
        assert dec.read_key() == Char('f')

    def test_follower_arriving_within_window_is_caught(self, stream):
        # The window is a wait, not an instantaneous check: a sequence
        # whose tail arrives a few ms after ESC still decodes whole.
        r, w = stream
        os.write(w, b'\x1b')
        t = write_later(w, b'[A', FAST / 4)
        try:
            assert probing(r, esc_timeout=ESC_FOLLOWER_TIMEOUT).read_key() == Key('up')
        finally:
            t.join()

    def test_esc_esc_burst_is_meta_escape(self, stream):
        # The editor decides what ESC-ESC means; the decoder just
        # reports that an ESC followed an ESC within the window.
        r, w = stream
        os.write(w, b'\x1b\x1b')
        assert probing(r).read_key() == Meta('\x1b')

    def test_eof_right_after_esc_is_bare_escape(self, stream):
        # A closed fd selects readable, so the probe is "won" by EOF:
        # report the ESC the human managed to type.
        r, w = stream
        os.write(w, b'\x1b')
        os.close(w)
        dec = probing(r)
        assert dec.read_key() == ESCAPE
        assert dec.read_key() == EOF

    def test_blocking_mode_never_times_out(self, stream):
        # emacs mode: ESC waits indefinitely for its follower — a Meta
        # combo typed slowly (well past any window) still decodes.
        r, w = stream
        os.write(w, b'\x1b')
        t = write_later(w, b'f', FAST * 3)
        try:
            assert blocking(r).read_key() == Meta('f')
        finally:
            t.join()

    def test_blocking_mode_eof_after_esc_is_empty_meta(self, stream):
        # Pre-decoder behavior: the emacs meta lookup ran on '' and
        # missed, then the next read hit EOF. Preserve the division.
        r, w = stream
        os.write(w, b'\x1b')
        os.close(w)
        dec = blocking(r)
        assert dec.read_key() == Meta('')
        assert dec.read_key() == EOF

    def test_default_window_is_50ms(self):
        # The feel of vi mode is pinned to this constant (v0.283).
        assert ESC_FOLLOWER_TIMEOUT == 0.05
        assert KeyDecoder(-1).esc_timeout == 0.05


class TestResize:
    @pytest.fixture
    def sigwinch(self):
        r, w = os.pipe()
        yield r, w
        for fd in (r, w):
            try:
                os.close(fd)
            except OSError:
                pass

    def test_sigwinch_pipe_yields_resize(self, stream, sigwinch):
        r, _w = stream
        sr, sw = sigwinch
        os.write(sw, b'\x1c')
        assert probing(r, sigwinch_fd=sr).read_key() == RESIZE

    def test_resize_drains_the_pipe(self, stream, sigwinch):
        r, _w = stream
        sr, sw = sigwinch
        os.write(sw, b'\x1c')
        probing(r, sigwinch_fd=sr).read_key()
        ready, _, _ = select.select([sr], [], [], 0)
        assert not ready  # nothing left pending

    def test_queued_notifications_coalesce_into_one_resize(self, stream, sigwinch):
        r, w = stream
        sr, sw = sigwinch
        os.write(sw, b'\x1c\x1c\x1c')
        os.write(w, b'a')
        dec = probing(r, sigwinch_fd=sr)
        assert dec.read_key() == RESIZE
        assert dec.read_key() == Char('a')  # not a second RESIZE

    def test_resize_during_typing_is_interleaved(self, stream, sigwinch):
        # Both fds readable: the resize is reported first, then the
        # pending keystrokes — nothing is lost in either direction.
        r, w = stream
        sr, sw = sigwinch
        os.write(w, b'ab')
        os.write(sw, b'\x1c')
        dec = probing(r, sigwinch_fd=sr)
        events = [dec.read_key() for _ in range(3)]
        assert events == [RESIZE, Char('a'), Char('b')]

    def test_buffered_chars_are_delivered_before_resize(self, stream, sigwinch):
        # Characters already read into the decoder's buffer (the tail
        # of a burst) bypass select(), so a resize arriving mid-burst
        # waits its turn — the pre-decoder loop behaved identically
        # (select() ran only with an empty character buffer).
        r, w = stream
        sr, sw = sigwinch
        os.write(w, b'ab')
        dec = probing(r, sigwinch_fd=sr)
        assert dec.read_key() == Char('a')  # buffers 'b'
        os.write(sw, b'\x1c')
        assert dec.read_key() == Char('b')
        assert dec.read_key() == RESIZE

    def test_no_sigwinch_fd_reads_directly(self, stream):
        # Without a sigwinch pipe there is no select() multiplexing at
        # all — plain blocking reads (the nested read_line case).
        r, w = stream
        os.write(w, b'x')
        dec = KeyDecoder(r)  # sigwinch_fd=None
        assert dec.read_key() == Char('x')


class TestErrorAndPushback:
    def test_eio_propagates(self, stream):
        # Terminal disconnect: the OSError must reach the caller (the
        # editor restores terminal modes and re-raises; the REPL exits).
        r, _w = stream
        dec = KeyDecoder(r)
        with patch('psh.interactive.key_decoder.os.read',
                   side_effect=OSError(errno.EIO, 'Input/output error')):
            with pytest.raises(OSError) as exc:
                dec.read_key()
        assert exc.value.errno == errno.EIO

    def test_pushback_is_read_next(self, stream):
        r, w = stream
        os.write(w, b'b')
        dec = probing(r)
        dec.pushback('a')
        assert dec.read_key() == Char('a')
        assert dec.read_key() == Char('b')

    def test_pushed_back_esc_is_redisambiguated(self, stream):
        # The vi ESC-ESC path: the editor hands the second ESC back;
        # with nothing following it must resolve to a bare ESCAPE.
        r, _w = stream
        dec = probing(r)
        dec.pushback('\x1b')
        assert dec.read_key() == ESCAPE

    def test_pushed_back_esc_can_introduce_a_sequence(self, stream):
        r, w = stream
        os.write(w, b'[A')
        dec = probing(r)
        dec.pushback('\x1b')
        assert dec.read_key() == Key('up')


class TestPasteCarryover:
    """The tail of a multi-line paste survives across decoders.

    A greedy os.read() pulls the whole paste into the decoder's buffer;
    when the editor accepts the first line and starts a fresh decoder for
    the next read, ``take_buffered`` / ``seed`` carry the unconsumed tail
    over so the paste's later commands run (reappraisal #16 H8a).
    """

    def test_take_buffered_returns_and_clears_unconsumed_tail(self, stream):
        r, w = stream
        os.write(w, b'ab\ncd')
        dec = probing(r)
        assert dec.read_key() == Char('a')   # first read buffers the rest
        tail = dec.take_buffered()
        assert tail == ['b', '\n', 'c', 'd']
        assert dec.take_buffered() == []     # cleared

    def test_seeded_chars_are_read_before_fresh_fd_input(self, stream):
        r, w = stream
        os.write(w, b'Y')
        dec = probing(r)
        dec.seed(['c', 'd'])                 # carried-over tail
        assert [dec.read_key() for _ in range(3)] == \
            [Char('c'), Char('d'), Char('Y')]

    def test_carryover_round_trip_preserves_order(self, stream):
        r, w = stream
        os.write(w, b'echo one\necho two\r')
        first = probing(r)
        # Consume "echo one" and the LF that would accept the line.
        for _ in range('echo one\n'.index('\n') + 1):
            first.read_key()
        tail = first.take_buffered()
        second = probing(r)
        second.seed(tail)
        got = ''.join(ev.char for ev in
                      (second.read_key() for _ in range(len('echo two\r'))))
        assert got == 'echo two\r'
