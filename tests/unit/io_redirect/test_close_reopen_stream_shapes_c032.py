"""C032 guard: the compound scan's stream half must FOLLOW the fd number.

``IOManager._swap_closed_output_streams`` runs ONCE, after the whole redirect
list has already been applied in source order, so it cannot tell from a single
``>&-`` whether fd 1/2 ends up closed.  It must therefore install the
fd-number-following ``_RawFdStream``, never the opaque always-EBADF
``_ClosedStream``: a list that closes and then REOPENS the same fd
(``{ echo hi; } 1>&- 1>f``) leaves that fd live, and an opaque stream would
sever the reopen and lose the body's output.

This walks every list SHAPE the scan can see and pins, for each:

* which of fd 1 / fd 2 gets a stream installed at all (``output_close_fd``),
* that the installed object is fd-following and names the RIGHT fd number,
* that ``restore()`` puts the displaced objects back by IDENTITY (no leak),
* the bytes that actually reach the file the reopen points at (D3).

``test_opaque_stream_offender_is_caught`` is the synthetic offender: it feeds
the SAME shape assertions a reconstruction of the defect (the scan installing
``_ClosedStream``) and requires them to fail, so the guard cannot go green on
a shape table that no longer discriminates.

Expectations verified against bash 5.3.15.  End-to-end behaviour in all three
input modes lives in
``tests/integration/redirection/test_close_then_reopen_c032.py``.
"""
import os
import sys

import pytest
from shell_oracle import is_comparable, run_psh

from psh.ast_nodes import Redirect
from psh.io_redirect.manager import IOManager, _ClosedStream, _RawFdStream


def close(fd=None, type='>&-'):
    return Redirect(type=type, target=None, fd=fd)


def dup(fd, dup_fd):
    return Redirect(type=f'{fd}>&{dup_fd}', target=None, fd=fd, dup_fd=dup_fd)


def to_file(fd, name, type='>'):
    return Redirect(type=type, target=name, fd=fd)


# (id, redirect list, fds the scan must install a stream on,
#  end-to-end script, {file: bytes}, rc)
SHAPES = [
    ("no_close",
     [to_file(1, 'f')],
     [],
     '{ echo hi; } 1>f', {"f": "hi\n"}, 0),
    ("close_fd1_only",
     [close(1)],
     [1],
     '{ echo hi; } 1>&-', {}, 1),
    ("close_fd2_only",
     [close(2)],
     [2],
     '{ cd /nonexistent_zz; } 2>&-', {}, 1),
    ("bare_close_defaults_to_fd1",
     [close(None)],
     [1],
     '{ echo hi; } >&-', {}, 1),
    ("input_spelling_closes_fd1",
     [close(1, type='<&-')],
     [1],
     '{ echo hi; } 1<&-', {}, 1),
    ("bare_input_close_is_fd0",
     [close(None, type='<&-')],
     [],
     '{ echo hi; } <&-', {}, 0),
    ("close_fd3_has_no_stream",
     [close(3)],
     [],
     '{ echo hi; } 3>&-', {}, 0),
    ("named_fd_close_has_no_stream",
     [Redirect(type='>&-', target=None, fd=None, var_fd='v')],
     [],
     'exec {v}>/dev/null; { echo hi; } {v}>&-', {}, 0),
    # --- the C032 shapes: close THEN reopen, same fd, one list ---
    ("close_then_reopen_file_fd1",
     [close(1), to_file(1, 'f')],
     [1],
     '{ echo hi; } 1>&- 1>f', {"f": "hi\n"}, 0),
    ("close_then_reopen_append_fd1",
     [close(1), to_file(1, 'f', type='>>')],
     [1],
     '{ echo hi; } 1>&- 1>>f', {"f": "hi\n"}, 0),
    ("close_then_dup_fd1_from_2",
     [to_file(2, 'f'), close(1), dup(1, 2)],
     [1],
     '{ echo hi; } 2>f 1>&- 1>&2', {"f": "hi\n"}, 0),
    ("close_then_reopen_file_fd2",
     [close(2), to_file(2, 'f')],
     [2],
     '{ echo err >&2; } 2>&- 2>f', {"f": "err\n"}, 0),
    ("close_then_dup_fd2_from_1",
     [to_file(1, 'f'), close(2), dup(2, 1)],
     [2],
     '{ echo err >&2; } 1>f 2>&- 2>&1', {"f": "err\n"}, 0),
    ("both_fds_closed_then_reopened",
     [close(1), close(2), to_file(1, 'o'), to_file(2, 'e')],
     [1, 2],
     '{ echo out; echo err >&2; } 1>&- 2>&- 1>o 2>e',
     {"o": "out\n", "e": "err\n"}, 0),
    # --- reopen THEN close: the fd is dead at the END, EBADF is correct ---
    ("reopen_then_close_fd1",
     [to_file(1, 'f'), close(1)],
     [1],
     '{ echo hi; } 1>f 1>&-', {"f": ""}, 1),
    ("close_reopen_close_fd1",
     [close(1), to_file(1, 'f'), close(1)],
     [1, 1],
     '{ echo hi; } 1>&- 1>f 1>&-', {"f": ""}, 1),
]


class _Sentinel:
    """A stand-in for the real sys.stdout/sys.stderr, restored by identity."""

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"<sentinel {self.name}>"


def check_shape(swap, io, redirects, expect_fds, shape_id):
    """Assert the scan's stream half for ONE list shape.

    ``swap`` is the owner under test (or, for the offender test, a
    reconstruction of the defect).  Raises AssertionError on a violation; the
    real ``sys.stdout``/``sys.stderr`` are always restored.
    """
    out_sentinel, err_sentinel = _Sentinel("stdout"), _Sentinel("stderr")
    real_out, real_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out_sentinel, err_sentinel
    try:
        restore = swap(io, redirects)
        installed = {}
        if sys.stdout is not out_sentinel:
            installed[1] = sys.stdout
        if sys.stderr is not err_sentinel:
            installed[2] = sys.stderr
        assert sorted(installed) == sorted(set(expect_fds)), (
            f"{shape_id}: streams installed on {sorted(installed)}, "
            f"expected {sorted(set(expect_fds))}")
        for fd, stream in installed.items():
            assert isinstance(stream, _RawFdStream), (
                f"{shape_id}: fd {fd} got {type(stream).__name__}, not "
                f"_RawFdStream — an opaque stream severs a later reopen (C032)")
            assert not isinstance(stream, _ClosedStream), shape_id
            assert stream.fileno() == fd, (
                f"{shape_id}: stream for fd {fd} names fd {stream.fileno()}")
        restore()
        # No leak: the displaced objects come back by IDENTITY.
        assert sys.stdout is out_sentinel, f"{shape_id}: sys.stdout not restored"
        assert sys.stderr is err_sentinel, f"{shape_id}: sys.stderr not restored"
    finally:
        sys.stdout, sys.stderr = real_out, real_err


@pytest.fixture
def io(shell):
    return IOManager(shell)


@pytest.mark.parametrize(
    "shape_id,redirects,expect_fds,script,files,rc",
    SHAPES, ids=[s[0] for s in SHAPES])
def test_stream_half_follows_the_fd_number(shape_id, redirects, expect_fds,
                                           script, files, rc, io):
    check_shape(IOManager._swap_closed_output_streams, io, redirects,
                expect_fds, shape_id)


@pytest.mark.parametrize(
    "shape_id,redirects,expect_fds,script,files,rc",
    SHAPES, ids=[s[0] for s in SHAPES])
def test_shape_writes_the_expected_bytes(shape_id, redirects, expect_fds,
                                         script, files, rc, tmp_path):
    """D3: the same shapes, end to end — the bytes that reach the real file."""
    result = run_psh(["-c", script], cwd=str(tmp_path))
    assert is_comparable(result), f"{shape_id}: harness failure {result}"
    assert result.returncode == rc, (
        f"{shape_id}: rc {result.returncode} != {rc}; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}")
    for name, expected in files.items():
        path = os.path.join(str(tmp_path), name)
        assert os.path.exists(path), f"{shape_id}: {name} was never created"
        with open(path) as fh:
            got = fh.read()
        assert got == expected, f"{shape_id}: {name} = {got!r} != {expected!r}"


def _opaque_scan_offender(io, redirects):
    """The C032 defect, reconstructed: an UNORDERED scan installing the opaque
    always-EBADF stream, which severs a later reopen of the same fd."""
    saved = []
    for redirect in redirects:
        target_fd = IOManager.output_close_fd(redirect)
        if target_fd is None:
            continue
        saved.append((target_fd, IOManager.swap_output_stream_closed(target_fd)))

    def restore():
        for fd, stream in reversed(saved):
            if fd == 1:
                sys.stdout = stream
            else:
                sys.stderr = stream

    return restore


def test_opaque_stream_offender_is_caught(io):
    """Synthetic offender: the guard must reject the defect it replaced.

    Every shape that installs a stream at all must fail against the opaque
    reconstruction — otherwise the shape table has stopped discriminating.
    """
    discriminating = [s for s in SHAPES if s[2]]
    assert discriminating, "shape table installs no streams — it cannot discriminate"
    for shape_id, redirects, expect_fds, _script, _files, _rc in discriminating:
        with pytest.raises(AssertionError, match="_RawFdStream"):
            check_shape(_opaque_scan_offender, io, redirects, expect_fds, shape_id)
