"""Rolling pipe construction in PipelineContext (D4).

PipelineContext now creates one pipe per boundary just before the command that
writes into it and releases the parent's copies after each fork, so the parent
holds O(1) pipe descriptors regardless of pipeline length. The old design
pre-opened all N-1 pipes, so the parent held ~2N descriptors and long pipelines
hit EMFILE under an ordinary RLIMIT_NOFILE.

These pure in-process unit tests exercise the fd bookkeeping directly, with no
fork: they only touch descriptors they allocate (via the context's own
os.pipe), never the runner's 0/1/2, so they are xdist-safe.
"""
import os

import pytest

from psh.executor.pipeline import PipelineContext


def _open_fd_count():
    return len(os.listdir('/dev/fd'))


def test_parent_holds_o1_descriptors_across_long_pipeline():
    """Across an N-command pipeline the parent never holds more than one
    boundary's descriptors, and leaks none at the end."""
    ctx = PipelineContext(job_manager=None)
    n = 200
    baseline = _open_fd_count()
    peak = 0
    for i in range(n):
        ctx.open_boundary(has_next=(i < n - 1))
        # Data fds held by the parent right now (before the next advance):
        # the carried read end plus this boundary's freshly created pipe.
        peak = max(peak, _open_fd_count() - baseline)
        ctx.advance()  # a real fork would happen between these two calls
    assert _open_fd_count() == baseline, "rolling construction leaked a descriptor"
    # O(1): a carried read end + one new pipe's two ends = 3, independent of N
    # (the old pre-open design held ~2N).
    assert peak <= 3, f"parent held {peak} data fds (not O(1))"


def test_open_boundary_returns_expected_endpoints():
    """First command has no stdin; last command has no stdout."""
    ctx = PipelineContext(job_manager=None)
    try:
        # Leader (has a successor): no stdin, a fresh stdout pipe end.
        stdin_fd, stdout_fd, owned = ctx.open_boundary(has_next=True)
        assert stdin_fd is None
        assert stdout_fd is not None
        assert stdout_fd in owned
        ctx.advance()
        # Last command (no successor): inherits the carried read end as stdin,
        # no stdout pipe.
        stdin_fd, stdout_fd, owned = ctx.open_boundary(has_next=False)
        assert stdin_fd is not None
        assert stdout_fd is None
        assert owned == [stdin_fd]
    finally:
        ctx.close_open_fds()


def test_close_open_fds_releases_partial_boundary():
    """Descriptors opened but not yet advanced past are fully released."""
    ctx = PipelineContext(job_manager=None)
    baseline = _open_fd_count()
    ctx.open_boundary(has_next=True)   # one pipe (2 fds)
    ctx.advance()                      # carry the read end (1 fd held)
    ctx.open_boundary(has_next=True)   # carried + new pipe = 3 fds held
    assert _open_fd_count() > baseline
    ctx.close_open_fds()
    assert _open_fd_count() == baseline


def test_pipe_failure_midway_leaks_nothing(monkeypatch):
    """If os.pipe fails at the k-th boundary, close_open_fds releases the
    descriptors opened so far — bounded error cleanup, no leak."""
    ctx = PipelineContext(job_manager=None)
    baseline = _open_fd_count()
    real_pipe = os.pipe
    calls = {'n': 0}

    def flaky_pipe():
        calls['n'] += 1
        if calls['n'] == 3:
            raise OSError(24, 'Too many open files')
        return real_pipe()

    monkeypatch.setattr(os, 'pipe', flaky_pipe)
    with pytest.raises(OSError):
        for _ in range(10):
            ctx.open_boundary(has_next=True)
            ctx.advance()
    monkeypatch.setattr(os, 'pipe', real_pipe)
    ctx.close_open_fds()
    assert _open_fd_count() == baseline
