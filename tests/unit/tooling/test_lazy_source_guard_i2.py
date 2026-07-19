"""Drift-lock: only the SCRIPT_FILE channel is lazy (campaign I2, #20 H14).

The SCRIPT-FILE argument is read lazily (``LazyFileInput``); ``source``/``.`` and
the rc file stay EAGER (``FileInput``) — bash reads source/rc eagerly too, and
their evalfile NUL filter + >256 refusal are inherently whole-content. A
synthetic offender that reverted SCRIPT_FILE to the eager reader would miss an
append to a running script; this test proves that distinction is real and
load-bearing, so a regression cannot pass silently.
"""
from psh.scripting.input_sources import FileInput, LazyFileInput
from psh.scripting.program_source import ProgramSource, SourceChannel


def test_script_file_channel_is_lazy(tmp_path):
    p = tmp_path / "s.sh"
    p.write_text("echo hi\n")
    src = ProgramSource.script_file(str(p)).make_input_source()
    assert isinstance(src, LazyFileInput)
    assert not isinstance(src, FileInput)


def test_source_and_rc_channels_stay_eager(tmp_path):
    p = tmp_path / "f"
    p.write_text("echo hi\n")
    for source in (ProgramSource.sourced_file(str(p)),
                   ProgramSource.rc_file(str(p))):
        src = source.make_input_source()
        assert isinstance(src, FileInput)
        assert not isinstance(src, LazyFileInput)


def test_channel_class_map_is_exhaustive(tmp_path):
    # Every channel resolves to a source; only SCRIPT_FILE is the lazy reader.
    p = tmp_path / "f"
    p.write_text("echo hi\n")
    lazy = {c for c in SourceChannel
            if _is_lazy(ProgramSource(kind=c, name=str(p),
                                      path=str(p) if _is_file(c) else None,
                                      text=None if _is_file(c) else "x",
                                      fd=0 if c is SourceChannel.STDIN_SCRIPT
                                      else None))}
    assert lazy == {SourceChannel.SCRIPT_FILE}


def _is_file(channel):
    return channel in (SourceChannel.SCRIPT_FILE, SourceChannel.SOURCED_FILE,
                       SourceChannel.RC_FILE)


def _is_lazy(program):
    return isinstance(program.make_input_source(), LazyFileInput)


def test_synthetic_eager_offender_misses_append(tmp_path):
    # The behavior a regression to eager SCRIPT_FILE would reintroduce: an eager
    # FileInput slurps the file at __enter__, so an append made after that (a
    # running command extending the script) is NOT seen; the lazy reader sees
    # it. This is why the lazy/eager distinction above is load-bearing.
    p = tmp_path / "s.sh"
    p.write_bytes(b"first\n")

    eager = FileInput(str(p))
    with eager:                       # reads the whole file NOW
        with open(p, "a") as f:
            f.write("appended\n")     # a running command extends the script
        eager_lines = []
        while (ln := eager.read_line()) is not None:
            eager_lines.append(ln)
    assert "appended" not in eager_lines   # eager misses it

    p.write_bytes(b"first\n")
    lazy = ProgramSource.script_file(str(p)).make_input_source()
    with lazy:
        assert lazy.read_line() == "first"
        with open(p, "a") as f:
            f.write("appended\n")
        assert lazy.read_line() == "appended"   # lazy sees it
