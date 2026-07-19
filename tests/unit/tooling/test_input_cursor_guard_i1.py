"""Drift-lock guards for the source-lifetime byte cursor (campaign I1).

Two invariants with RUN synthetic offenders:

1. The InputCursorRegistry is keyed by an owned open-file-description IDENTITY,
   not by the bare fd — so a rebind (`exec 0<file`) yields a NEW cursor. A
   synthetic fd-keyed registry that ignores the rebind is proven to violate the
   invariant, so FULL cursor-sharing can only be an ADDITIVE extension.

2. The reader decodes with surrogateescape (malformed bytes round-trip), NOT
   `errors='replace'`. A synthetic replace-decoder offender is proven to fail
   the round-trip the real cursor satisfies.
"""
import codecs
import os

from psh.builtins.input_reader import InputCursor
from psh.io_redirect.input_cursor import InputCursorRegistry, OpenDescription


# A stub whose class name contains 'DontReadFromInput' makes make_reader take
# the real-fd path (see make_reader), so cursor_for_fd returns an fd-backed
# cursor we can persist and rebind.
class DontReadFromInputStub:
    pass


class _StubShell:
    def __init__(self, stdin):
        self.stdin = stdin


def _pipe(data: bytes = b"x\n") -> int:
    r, w = os.pipe()
    os.write(w, data)
    os.close(w)
    return r


def _shell():
    return _StubShell(DontReadFromInputStub())


class TestRegistryKeyedByDescription:
    def test_same_fd_persists_then_rebind_gives_new_cursor(self):
        reg = InputCursorRegistry()
        shell = _shell()
        fd = _pipe()
        try:
            c1 = reg.cursor_for_fd(shell, fd)
            c2 = reg.cursor_for_fd(shell, fd)
            assert c1 is c2, "same description must reuse one cursor (carryover)"
            reg.rebind(fd)
            c3 = reg.cursor_for_fd(shell, fd)
            assert c3 is not c1, "a rebind must yield a NEW cursor (new description)"
        finally:
            os.close(fd)

    def test_synthetic_fd_keyed_offender_violates_the_invariant(self):
        # An offender that keys by fd and ignores rebind returns the SAME cursor
        # after a rebind — proving the description keying is load-bearing.
        class FdKeyedOffender(InputCursorRegistry):
            def rebind(self, fd):  # pragma: no cover - deliberately wrong
                pass  # ignore: fd-keyed behavior

        reg = FdKeyedOffender()
        shell = _shell()
        fd = _pipe()
        try:
            c1 = reg.cursor_for_fd(shell, fd)
            reg.rebind(fd)
            c3 = reg.cursor_for_fd(shell, fd)
            assert c3 is c1, "offender reuses the cursor across a rebind (the bug)"
        finally:
            os.close(fd)

    def test_open_description_identity_is_object_identity(self):
        a = OpenDescription("fd0")
        b = OpenDescription("fd0")
        assert a is not b and a != b  # same label is NOT the same description
        assert a == a and {a: 1}[a] == 1


class TestSurrogateescapeNotReplace:
    def test_malformed_byte_round_trips_not_replacement(self):
        fd = _pipe(b"\xc3A\n")
        try:
            data = InputCursor(fd=fd).read_record(
                delimiter="\n", include_delimiter=False).data
        finally:
            os.close(fd)
        assert data.encode("utf-8", "surrogateescape") == b"\xc3A"
        assert "�" not in data, "U+FFFD replacement resurfaced"

    def test_synthetic_replace_offender_loses_the_bytes(self):
        # The retired policy: decoding \xc3A with errors='replace' yields U+FFFD
        # and cannot round-trip. This proves the round-trip assertion has teeth.
        offender = codecs.getincrementaldecoder("utf-8")("replace")
        got = offender.decode(b"\xc3") + offender.decode(b"A")
        assert "�" in got
        assert got.encode("utf-8", "surrogateescape") != b"\xc3A"
