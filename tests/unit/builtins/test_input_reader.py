"""Unit tests for the shared streaming input reader (psh.builtins.input_reader).

The reader is the single primitive behind ``read`` and ``mapfile``. These tests
exercise it directly (fd source and injected text stream) rather than through a
builtin, pinning the properties both builtins rely on:

* incremental UTF-8 decoding (a multibyte character split across ``os.read``
  boundaries decodes whole, not as replacement bytes),
* never consuming past the record/count boundary (the rest of a pipe is left
  readable by the next consumer),
* a monotonic total deadline for ``-t``,
* typed outcomes.

Red→green: before this campaign ``read``/``mapfile`` decoded a byte at a time
with ``os.read(fd, 1).decode('utf-8', 'replace')``, so ``read -N1`` on ``é``
produced U+FFFD and left the orphaned second byte in the stream. The
``utf8_*`` and ``leftover`` cases below fail against that code.
"""

import io
import os
import time

import pytest

from psh.builtins.input_reader import InputReader, Outcome, ReadResult


def _pipe(data: bytes) -> int:
    """A read fd preloaded with *data* (writer closed → clean EOF)."""
    r, w = os.pipe()
    os.write(w, data)
    os.close(w)
    return r


class _FakeClock:
    """A scripted stand-in for the ``time`` module's ``monotonic``.

    Returns the next value from ``schedule`` on each call and pins to the last
    value once exhausted. Lets a deadline test advance *simulated* time without
    real sleeps, so it never flakes under parallel load.
    """

    def __init__(self, schedule):
        self._schedule = list(schedule)
        self._i = 0

    def monotonic(self) -> float:
        i = min(self._i, len(self._schedule) - 1)
        self._i += 1
        return self._schedule[i]


class TestUtf8Decoding:
    def test_multibyte_record_decodes_whole(self):
        fd = _pipe("héllo wörld\n".encode("utf-8"))
        try:
            result = InputReader(fd=fd).read_record(
                delimiter="\n", include_delimiter=True)
        finally:
            os.close(fd)
        assert result.data == "héllo wörld\n"
        assert result.outcome is Outcome.DATA

    def test_N1_reads_one_character_two_bytes(self):
        fd = _pipe("éb\n".encode("utf-8"))
        try:
            reader = InputReader(fd=fd)
            result = reader.read_limited(delimiter=None, max_chars=1)
            assert result.data == "é"
            # The orphaned byte must NOT have been consumed: the next reader
            # still sees "b\n".
            assert os.read(fd, 100) == b"b\n"
        finally:
            os.close(fd)

    def test_emoji_counts_as_one_character(self):
        fd = _pipe("😀x\n".encode("utf-8"))
        try:
            result = InputReader(fd=fd).read_limited(delimiter=None, max_chars=1)
        finally:
            os.close(fd)
        assert result.data == "😀"

    def test_truncated_multibyte_at_eof_round_trips(self):
        # A lone UTF-8 lead byte at EOF round-trips as a surrogate (campaign
        # I1 / #20 H16): bash keeps the raw byte (`printf '\xc3' | read x` ->
        # $'\303' in both C and UTF-8 locales), so surrogateescape's \udcc3
        # (which .encode('utf-8','surrogateescape') restores to \xc3) is
        # correct — NOT the U+FFFD this used to assert.
        fd = _pipe(b"\xc3")
        try:
            result = InputReader(fd=fd).read_record(
                delimiter="\n", include_delimiter=True)
        finally:
            os.close(fd)
        assert result.data == "\udcc3"
        assert result.data.encode("utf-8", "surrogateescape") == b"\xc3"
        assert result.outcome is Outcome.EOF


class TestOverReadAvoidance:
    def test_record_leaves_rest_for_next_consumer(self):
        fd = _pipe(b"a\nb\nc\n")
        try:
            reader = InputReader(fd=fd)
            first = reader.read_record(delimiter="\n", include_delimiter=True)
            assert first.data == "a\n"
            # Everything after the first record is untouched in the stream.
            assert os.read(fd, 100) == b"b\nc\n"
        finally:
            os.close(fd)

    def test_limited_stops_early_at_delimiter(self):
        fd = _pipe(b"ab\ncd\n")
        try:
            result = InputReader(fd=fd).read_limited(delimiter="\n", max_chars=10)
        finally:
            os.close(fd)
        assert result.data == "ab"
        assert result.hit_delimiter is True


class TestTextStreamSource:
    def test_stringio_record(self):
        result = InputReader(stream=io.StringIO("abc\ndef\n")).read_record(
            delimiter="\n", include_delimiter=True)
        assert result.data == "abc\n"

    def test_stringio_eof_partial(self):
        result = InputReader(stream=io.StringIO("tail")).read_record(
            delimiter="\n", include_delimiter=True)
        assert result.data == "tail"
        assert result.outcome is Outcome.EOF


class TestDeadline:
    def test_timeout_on_idle_pipe(self):
        r, w = os.pipe()  # writer open, nothing written → read blocks
        try:
            start = time.monotonic()
            result = InputReader(fd=r).read_record(
                delimiter="\n", include_delimiter=True,
                deadline=time.monotonic() + 0.3)
            elapsed = time.monotonic() - start
        finally:
            os.close(r)
            os.close(w)
        assert result.outcome is Outcome.TIMEOUT
        assert 0.2 < elapsed < 2.0  # generous margin for parallel load


class TestTotalDeadline:
    """The -t deadline bounds the WHOLE read, not each byte.

    A per-byte reset is a real bash-divergent escape: bytes trickled a@0.0s,
    b@0.6s, c@1.2s into ``read -t 1`` give bash rc=142 x="ab" (the total budget
    expires between b and c), but a mutant that re-arms the budget per byte
    reads all of "abc". The idle-pipe timeout test above cannot tell these
    apart — only a trickle can.

    This is driven through the reader's clock seam (a fake ``time`` with a
    scripted ``monotonic``) so it is deterministic and never load-sensitive:
    every byte is already present on the pipe, so ``select`` never blocks and no
    real time passes; the deadline is crossed purely by the simulated clock. An
    absolute/total deadline therefore stops mid-stream on schedule, while a
    per-byte reset (which ignores elapsed time) would consume the whole pipe.
    """

    def test_absolute_deadline_stops_midstream(self, monkeypatch):
        import psh.builtins.input_reader as ir
        # One monotonic() reading per byte-read attempt: 0.0 (a), 0.6 (b),
        # 1.2 (c) — the third is past the 1.0 deadline, so 'c' is never taken.
        monkeypatch.setattr(ir, "time", _FakeClock([0.0, 0.6, 1.2, 2.0]))
        fd = _pipe(b"abc")  # all present at once; timing is purely the clock
        try:
            result = ir.InputReader(fd=fd).read_limited(
                delimiter=None, max_chars=10, deadline=1.0)
        finally:
            os.close(fd)
        assert result.data == "ab", (
            "read consumed past the total deadline — the -t budget must not "
            "re-arm per byte")
        assert result.outcome is Outcome.TIMEOUT


class TestReadAll:
    def test_drains_to_eof(self):
        fd = _pipe("one\ntwö\n".encode("utf-8"))
        try:
            assert InputReader(fd=fd).read_all() == "one\ntwö\n"
        finally:
            os.close(fd)

    def test_read_all_from_stream(self):
        assert InputReader(stream=io.StringIO("xyz")).read_all() == "xyz"


class TestConstruction:
    def test_requires_exactly_one_source(self):
        with pytest.raises(ValueError):
            InputReader()
        with pytest.raises(ValueError):
            InputReader(fd=0, stream=io.StringIO(""))

    def test_result_repr_is_safe(self):
        r = ReadResult("x", Outcome.DATA, hit_delimiter=True)
        assert "ReadResult" in repr(r)
