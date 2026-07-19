"""InputCursor type invariants (campaign I1).

The record reader owns an incremental UTF-8 surrogateescape decoder, a decoded
character queue, and raw byte pushback across reads. These pin the type
directly, over real pipes, independent of the read/mapfile builtins.
"""
import os

from psh.builtins.input_reader import InputCursor, Outcome


def _pipe(data: bytes) -> int:
    """Write *data* into a pipe, close the writer, return the read fd."""
    r, w = os.pipe()
    os.write(w, data)
    os.close(w)
    return r


class TestSurrogateescapeRoundTrip:
    def test_malformed_lead_before_ascii_round_trips(self):
        fd = _pipe(b"\xc3A\n")
        try:
            result = InputCursor(fd=fd).read_record(
                delimiter="\n", include_delimiter=False)
        finally:
            os.close(fd)
        # \xc3 is an invalid lead before 'A': one surrogate + 'A', delimiter kept.
        assert result.data == "\udcc3A"
        assert result.data.encode("utf-8", "surrogateescape") == b"\xc3A"
        assert result.hit_delimiter is True

    def test_bare_invalid_bytes_round_trip(self):
        fd = _pipe(b"\xff\xfe\n")
        try:
            result = InputCursor(fd=fd).read_record(
                delimiter="\n", include_delimiter=False)
        finally:
            os.close(fd)
        assert result.data.encode("utf-8", "surrogateescape") == b"\xff\xfe"

    def test_valid_multibyte_split_across_reads_decodes_whole(self):
        # é as two bytes; the cursor assembles it into one character.
        fd = _pipe(b"\xc3\xa9\n")
        try:
            result = InputCursor(fd=fd).read_record(
                delimiter="\n", include_delimiter=False)
        finally:
            os.close(fd)
        assert result.data == "é"


class TestNoDelimiterCascade:
    def test_malformed_lead_does_not_eat_the_delimiter(self):
        # The #20 H16 defect: a non-continuation byte after a lead must not be
        # consumed as this record's continuation, eating the newline.
        fd = _pipe(b"\xc3A\nB\n")
        try:
            cur = InputCursor(fd=fd)
            first = cur.read_record(delimiter="\n", include_delimiter=False)
            second = cur.read_record(delimiter="\n", include_delimiter=False)
        finally:
            os.close(fd)
        assert first.data.encode("utf-8", "surrogateescape") == b"\xc3A"
        assert second.data == "B"


class TestNeverOverRead:
    def test_record_leaves_rest_for_next_consumer(self):
        fd = _pipe(b"a\nb\nc\n")
        try:
            InputCursor(fd=fd).read_record(delimiter="\n", include_delimiter=True)
            rest = os.read(fd, 100)  # what a following `cat` would see
        finally:
            os.close(fd)
        assert rest == b"b\nc\n"


class TestDecodedQueueCarryover:
    def test_count_boundary_surplus_survives_to_next_read(self):
        # read_limited(1) on \xc3A must classify \xc3 by reading 'A' (lookahead);
        # the surplus 'A' stays in the SAME cursor for the next read, not lost.
        fd = _pipe(b"\xc3A\n")
        try:
            cur = InputCursor(fd=fd)
            first = cur.read_limited(delimiter=None, max_chars=1)
            second = cur.read_limited(delimiter=None, max_chars=1)
        finally:
            os.close(fd)
        assert first.data.encode("utf-8", "surrogateescape") == b"\xc3"
        assert second.data == "A"

    def test_truncated_multibyte_at_eof_round_trips(self):
        fd = _pipe(b"\xc3")  # lone lead byte then EOF
        try:
            result = InputCursor(fd=fd).read_record(
                delimiter="\n", include_delimiter=True)
        finally:
            os.close(fd)
        assert result.data == "\udcc3"
        assert result.outcome is Outcome.EOF


class TestPoll:
    def test_poll_readable_sees_buffered_chars(self):
        fd = _pipe(b"\xc3A\n")
        try:
            cur = InputCursor(fd=fd)
            cur.read_limited(delimiter=None, max_chars=1)  # leaves 'A' queued
            assert cur.poll_readable() == 0  # buffered -> readable, no block
        finally:
            os.close(fd)


class TestFdProperty:
    def test_fd_backed_reports_fd_stream_reports_none(self):
        import io
        fd = _pipe(b"x\n")
        try:
            assert InputCursor(fd=fd).fd == fd
        finally:
            os.close(fd)
        assert InputCursor(stream=io.StringIO("x")).fd is None
