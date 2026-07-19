"""Unit invariants for the lazy SCRIPT_FILE reader (campaign I2, #20 H14).

``LazyFileInput`` reads a script-file argument ON DEMAND, block-buffered over an
owned high-CLOEXEC descriptor: memory is bounded independent of file size,
consumed bytes are never re-read, and an append past the read frontier is seen.
These pins lock the reader's line semantics (CR/NUL/final-empty/surrogateescape)
and the never-re-read / append-seen invariant at the unit level; the bash-
compared behavioral truth lives in tests/system/test_lazy_script_source_i2.py.
"""
import os

from psh.scripting.program_source import ProgramSource


def _drain(src):
    out = []
    while True:
        line = src.read_line()
        if line is None:
            break
        out.append(line)
    return out


def _reader(path):
    return ProgramSource.script_file(str(path)).make_input_source()


def test_reads_physical_lines_with_trailing_empty(tmp_path):
    p = tmp_path / "s.sh"
    p.write_text("echo one\necho two\n")
    with _reader(p) as src:
        # Newline-terminated file yields one empty final line (FileInput
        # split('\n') parity — the dangling-\\ vs joined-\\ distinction).
        assert _drain(src) == ["echo one", "echo two", ""]


def test_no_trailing_empty_when_unterminated(tmp_path):
    p = tmp_path / "s.sh"
    p.write_bytes(b"echo one\necho two")  # no trailing newline
    with _reader(p) as src:
        assert _drain(src) == ["echo one", "echo two"]


def test_strips_one_trailing_cr_per_line(tmp_path):
    # FileInput CRLF parity (psh's documented dos2unix divergence): one trailing
    # CR per physical line is stripped; an embedded CR stays.
    p = tmp_path / "s.sh"
    p.write_bytes(b"echo a\r\nmid\rembed\r\n")
    with _reader(p) as src:
        assert _drain(src) == ["echo a", "mid\rembed", ""]


def test_deletes_every_nul(tmp_path):
    # STREAM channel policy: delete every NUL (equal to deleting over the
    # stream since NUL never ends a record).
    p = tmp_path / "s.sh"
    p.write_bytes(b"e\x00cho \x00hi\nx\x00\x00y\n")
    with _reader(p) as src:
        assert _drain(src) == ["echo hi", "xy", ""]


def test_nul_before_cr_matches_global_strip(tmp_path):
    # NUL stripped BEFORE the CRLF step (matching FileInput's global
    # strip-before-split): "abc\r\x00" -> "abc".
    p = tmp_path / "s.sh"
    p.write_bytes(b"abc\r\x00\n")
    with _reader(p) as src:
        assert _drain(src) == ["abc", ""]


def test_surrogateescape_roundtrip(tmp_path):
    # A non-UTF-8 script byte round-trips as a lone surrogate.
    p = tmp_path / "s.sh"
    p.write_bytes(b"echo \xff\n")
    with _reader(p) as src:
        line = src.read_line()
    assert line == "echo \udcff"
    assert line.encode("utf-8", "surrogateescape") == b"echo \xff"


def test_line_number_tracks_reads(tmp_path):
    p = tmp_path / "s.sh"
    p.write_text("a\nb\nc\n")
    with _reader(p) as src:
        assert src.get_line_number() == 0
        src.read_line()
        assert src.get_line_number() == 1
        src.read_line()
        assert src.get_line_number() == 2


def test_append_past_frontier_is_seen_no_reread(tmp_path):
    # The core H14 invariant at the unit level: after the last original line is
    # served and the buffer drains, a refill lands at the grown EOF and returns
    # the appended bytes — consumed bytes are never re-read.
    p = tmp_path / "s.sh"
    p.write_text("first\n")
    with _reader(p) as src:
        assert src.read_line() == "first"
        # Append while the reader is live (simulating a running command).
        with open(p, "a") as f:
            f.write("second\n")
        # The empty-final of the ORIGINAL content is NOT emitted, because the
        # refill found grown content instead of EOF.
        assert src.read_line() == "second"
        assert src.read_line() == ""   # empty final at the true (grown) EOF
        assert src.read_line() is None


def test_bounded_buffer_independent_of_file_size(tmp_path):
    # Memory is one block plus one partial line: after reading a few lines of a
    # multi-megabyte file, the internal buffer is at most one block, NOT the
    # whole file.
    p = tmp_path / "big.sh"
    line = "x" * 100 + "\n"
    with open(p, "w") as f:
        for _ in range(200000):        # ~20 MB
            f.write(line)
    with _reader(p) as src:
        for _ in range(5):
            src.read_line()
        assert len(src._buf) <= src._BLOCK  # never the whole 20 MB


def test_fd_is_high_and_closed_on_exit(tmp_path):
    p = tmp_path / "s.sh"
    p.write_text("echo hi\n")
    src = _reader(p)
    with src:
        fd = src._fd
        assert fd >= 255                 # relocated high (out of the user's way)
        # The relocated descriptor is CLOEXEC.
        import fcntl
        assert fcntl.fcntl(fd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC
        os.fstat(fd)                     # open while the source is live
    assert src._fd == -1                 # closed on __exit__
