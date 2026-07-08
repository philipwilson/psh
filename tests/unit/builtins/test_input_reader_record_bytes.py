"""Unit pins for InputReader.read_record_bytes — the byte-record drain.

read_record_bytes is the never-over-read primitive the lazy stdin-as-script
reader (StdinInput) is built on: it returns the raw bytes up to (not including)
a delimiter byte and leaves the REST of the source untouched for the next
consumer. That drain guarantee — a `read`/`cat` after the shell reads a script
line still sees the following bytes — is the whole point, so it is pinned here
at the byte level (a bulk os.read would drain a pipe and fail these).

These are additive: the existing read_record/read/mapfile char-record behavior
is untouched (see test_read_mapfile_streaming.py).
"""

import io
import os

from psh.builtins.input_reader import InputReader

NL = 0x0A


def _pipe(data: bytes):
    """Return a read-fd preloaded with *data* (writer closed → clean EOF)."""
    r, w = os.pipe()
    os.write(w, data)
    os.close(w)
    return r


class TestNeverOverReads:
    def test_leaves_remainder_on_a_pipe(self):
        """After one record, a raw os.read on the same fd sees EXACTLY the
        rest — the reader consumed the delimiter and not one byte more."""
        r = _pipe(b"line one\nDATA-FOR-NEXT-CONSUMER\nmore\n")
        try:
            reader = InputReader(fd=r)
            assert reader.read_record_bytes(delimiter_byte=NL) == b"line one"
            # The bytes a following `read`/`cat` would get, verbatim:
            assert os.read(r, 4096) == b"DATA-FOR-NEXT-CONSUMER\nmore\n"
        finally:
            os.close(r)

    def test_leaves_remainder_on_a_seekable_file(self, tmp_path):
        p = tmp_path / "s"
        p.write_bytes(b"cmd\nrest1\nrest2\n")
        fd = os.open(str(p), os.O_RDONLY)
        try:
            reader = InputReader(fd=fd)
            assert reader.read_record_bytes(delimiter_byte=NL) == b"cmd"
            assert os.read(fd, 4096) == b"rest1\nrest2\n"
        finally:
            os.close(fd)

    def test_two_readers_share_the_fd_position(self):
        """A fresh InputReader over the same fd continues where the first
        stopped (models StdinInput handing off to the read builtin)."""
        r = _pipe(b"a\nb\nc\n")
        try:
            first = InputReader(fd=r)
            assert first.read_record_bytes(delimiter_byte=NL) == b"a"
            second = InputReader(fd=r)  # a different reader, same fd
            assert second.read_record_bytes(delimiter_byte=NL) == b"b"
            assert first.read_record_bytes(delimiter_byte=NL) == b"c"
        finally:
            os.close(r)


class TestRecordBoundaries:
    def test_sequential_records(self):
        r = _pipe(b"one\ntwo\nthree\n")
        try:
            reader = InputReader(fd=r)
            assert reader.read_record_bytes(delimiter_byte=NL) == b"one"
            assert reader.read_record_bytes(delimiter_byte=NL) == b"two"
            assert reader.read_record_bytes(delimiter_byte=NL) == b"three"
            assert reader.read_record_bytes(delimiter_byte=NL) is None
        finally:
            os.close(r)

    def test_final_record_without_delimiter(self):
        """A last record with no trailing delimiter returns its bytes; the
        NEXT call returns None."""
        r = _pipe(b"has-nl\nno-nl")
        try:
            reader = InputReader(fd=r)
            assert reader.read_record_bytes(delimiter_byte=NL) == b"has-nl"
            assert reader.read_record_bytes(delimiter_byte=NL) == b"no-nl"
            assert reader.read_record_bytes(delimiter_byte=NL) is None
        finally:
            os.close(r)

    def test_empty_input_is_none(self):
        r = _pipe(b"")
        try:
            assert InputReader(fd=r).read_record_bytes(delimiter_byte=NL) is None
        finally:
            os.close(r)

    def test_empty_record_between_delimiters_is_bytes_not_none(self):
        """A blank line yields b'' (an empty record), distinct from None (EOF)."""
        r = _pipe(b"\n\nx\n")
        try:
            reader = InputReader(fd=r)
            assert reader.read_record_bytes(delimiter_byte=NL) == b""
            assert reader.read_record_bytes(delimiter_byte=NL) == b""
            assert reader.read_record_bytes(delimiter_byte=NL) == b"x"
            assert reader.read_record_bytes(delimiter_byte=NL) is None
        finally:
            os.close(r)

    def test_custom_delimiter(self):
        r = _pipe(b"a:b:c")
        try:
            reader = InputReader(fd=r)
            assert reader.read_record_bytes(delimiter_byte=ord(":")) == b"a"
            assert reader.read_record_bytes(delimiter_byte=ord(":")) == b"b"
            assert reader.read_record_bytes(delimiter_byte=ord(":")) == b"c"
        finally:
            os.close(r)


class TestRawBytesNoDecode:
    def test_non_utf8_bytes_returned_raw(self):
        """The delimiter is byte-level, so a non-UTF-8 byte comes back RAW —
        the caller (StdinInput) owns the surrogateescape decode."""
        r = _pipe(b"caf\xe9\n\xff\xfe\n")
        try:
            reader = InputReader(fd=r)
            assert reader.read_record_bytes(delimiter_byte=NL) == b"caf\xe9"
            assert reader.read_record_bytes(delimiter_byte=NL) == b"\xff\xfe"
        finally:
            os.close(r)

    def test_multibyte_utf8_intact(self):
        euro = "€".encode("utf-8")  # e2 82 ac — none of which is 0x0a
        r = _pipe(euro + b"\n")
        try:
            assert InputReader(fd=r).read_record_bytes(delimiter_byte=NL) == euro
        finally:
            os.close(r)


class TestErrorAndStreamPaths:
    def test_closed_fd_is_none_not_crash(self):
        r, w = os.pipe()
        os.close(w)
        os.close(r)  # fd now invalid
        # os.read raises EBADF -> Outcome.ERROR -> None (no exception escapes).
        assert InputReader(fd=r).read_record_bytes(delimiter_byte=NL) is None

    def test_stream_path_matches_fd_semantics(self):
        reader = InputReader(stream=io.StringIO("one\ntwo"))
        assert reader.read_record_bytes(delimiter_byte=NL) == b"one"
        assert reader.read_record_bytes(delimiter_byte=NL) == b"two"
        assert reader.read_record_bytes(delimiter_byte=NL) is None


class TestPartialDrainHonorsDelimiter:
    def test_delimiter_buffered_in_partial_is_honored(self):
        """If a prior char read left a delimiter byte in _partial, the byte
        record must stop there and push the remainder back — never skip past a
        record boundary. (StdinInput never mixes reads; this pins the guard.)"""
        r = _pipe(b"AFTER\n")
        try:
            reader = InputReader(fd=r)
            # Simulate a mixed prior char read that buffered "x\ny" mid-decode.
            reader._partial = bytearray(b"x\ny")
            assert reader.read_record_bytes(delimiter_byte=NL) == b"x"
            # The remainder "y" was pushed back, then the fd's "AFTER" follows.
            assert reader.read_record_bytes(delimiter_byte=NL) == b"yAFTER"
        finally:
            os.close(r)
