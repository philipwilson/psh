"""Unit tests for the collision-safe fd-remapping utility (``remap_fds``).

These are pure in-process tests. They NEVER touch the test runner's own
descriptors 0/1/2 (which under pytest-xdist carry the worker channel) — every
descriptor is kernel-allocated via ``os.pipe``/``os.dup``/``os.open`` and only
those descriptors are remapped or closed. Delivery is verified by writing to a
destination and reading the mark back from the matching pipe read end.
"""
import fcntl
import os

import pytest

from psh.io_redirect import remap_fds


def _open_fd_count() -> int:
    """Number of descriptors this process currently holds open."""
    return len(os.listdir('/dev/fd'))


def _delivers(dst_fd: int, reader_fd: int) -> bool:
    """True when writing to ``dst_fd`` is received on ``reader_fd``."""
    os.set_blocking(reader_fd, False)
    try:
        os.write(dst_fd, b'ping')
    except OSError:
        return False
    try:
        return os.read(reader_fd, 4) == b'ping'
    except BlockingIOError:
        return False


def _is_closed(fd: int) -> bool:
    try:
        os.fstat(fd)
        return False
    except OSError:
        return True


def _is_cloexec(fd: int) -> bool:
    return bool(fcntl.fcntl(fd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC)


class _Fds:
    """Track and unconditionally release every descriptor a test opens."""

    def __init__(self):
        self._fds = []

    def pipe(self):
        r, w = os.pipe()
        self._fds += [r, w]
        return r, w

    def dup(self, fd):
        d = os.dup(fd)
        self._fds.append(d)
        return d

    def devnull(self):
        fd = os.open(os.devnull, os.O_WRONLY)
        self._fds.append(fd)
        return fd

    def close_all(self):
        for fd in self._fds:
            try:
                os.close(fd)
            except OSError:
                pass


@pytest.fixture
def fds():
    box = _Fds()
    try:
        yield box
    finally:
        box.close_all()


def test_source_equals_destination_is_a_noop(fds):
    """{A: A} keeps A live and makes it inheritable (clears close-on-exec)."""
    r, w = fds.pipe()
    a = fds.dup(w)  # source == destination
    remap_fds({a: a}, owned=[a])
    assert not _is_closed(a)
    assert _delivers(a, r)
    # A destination is left inheritable so an exec'd program receives it.
    assert not _is_cloexec(a)


def test_simple_move_to_owned_destination(fds):
    """{src -> dst} delivers src's file to dst; src (owned) is closed."""
    r, w = fds.pipe()
    src = fds.dup(w)
    dst = fds.devnull()  # a descriptor we own, about to be overwritten
    remap_fds({src: dst}, owned=[src])
    assert _delivers(dst, r)
    assert _is_closed(src)


def test_source_equals_another_destination(fds):
    """A source that also sits on a second mapping's destination survives.

    ``{s1 -> s2, s2 -> d}``: s1's file must reach s2, so s2's own file must be
    preserved until it has been copied to d.
    """
    r1, w1 = fds.pipe()
    r2, w2 = fds.pipe()
    s1 = fds.dup(w1)
    s2 = fds.dup(w2)
    d = fds.devnull()
    remap_fds([(s1, s2), (s2, d)], owned=[s1, s2, d])
    assert _delivers(s2, r1)   # s2 now carries w1's file
    assert _delivers(d, r2)    # d now carries w2's file


def test_two_cycle_swaps_descriptors(fds):
    """{A: B, B: A} swaps the two descriptors' open files."""
    r1, w1 = fds.pipe()
    r2, w2 = fds.pipe()
    a = fds.dup(w1)
    b = fds.dup(w2)
    remap_fds([(a, b), (b, a)], owned=[a, b])
    assert _delivers(a, r2)   # a now carries w2
    assert _delivers(b, r1)   # b now carries w1


def test_three_cycle_rotates_descriptors(fds):
    """{A: B, B: C, C: A} rotates three descriptors' open files."""
    r1, w1 = fds.pipe()
    r2, w2 = fds.pipe()
    r3, w3 = fds.pipe()
    a = fds.dup(w1)
    b = fds.dup(w2)
    c = fds.dup(w3)
    remap_fds([(a, b), (b, c), (c, a)], owned=[a, b, c])
    assert _delivers(b, r1)   # b <- a's file (w1)
    assert _delivers(c, r2)   # c <- b's file (w2)
    assert _delivers(a, r3)   # a <- c's file (w3)


def test_one_source_feeds_two_destinations(fds):
    """``|&`` shape: {src -> d1, src -> d2} sends src's file to both."""
    r, w = fds.pipe()
    src = fds.dup(w)
    d1 = fds.devnull()
    d2 = fds.devnull()
    remap_fds([(src, d1), (src, d2)], owned=[src])
    assert _delivers(d1, r)
    assert _delivers(d2, r)
    assert _is_closed(src)


def test_owned_closed_once_and_destinations_protected(fds):
    """Owned non-destination fds close; a destination in owned is kept."""
    r, w = fds.pipe()
    a = fds.dup(w)          # destination (mapped to itself)
    extra = fds.dup(w)      # internal endpoint, not a destination
    remap_fds({a: a}, owned=[a, extra, extra])  # extra listed twice
    assert not _is_closed(a)   # protected destination survives
    assert _is_closed(extra)   # owned non-destination closed


def test_failure_injection_leaks_no_descriptor(fds, monkeypatch):
    """A dup2 failure mid-remap closes temporaries and owned fds, no leak."""
    r, _w = fds.pipe()
    src = fds.dup(_w)
    dst = fds.devnull()

    calls = {'n': 0}
    real_dup2 = os.dup2

    def flaky_dup2(a, b, *args, **kwargs):
        calls['n'] += 1
        raise OSError(9, 'injected')  # EBADF-like

    monkeypatch.setattr(os, 'dup2', flaky_dup2)

    before = _open_fd_count()   # r, _w, src, dst all open here
    with pytest.raises(OSError):
        remap_fds({src: dst}, owned=[src])
    monkeypatch.setattr(os, 'dup2', real_dup2)
    after = _open_fd_count()

    # src (owned) is closed; any temp the utility created is closed too. dst is
    # not owned, so it stays open. Net: exactly one fewer than before (src).
    assert after == before - 1
    assert _is_closed(src)
    assert not _is_closed(dst)


def test_no_descriptor_growth_across_repeated_remaps(fds):
    """Repeated remaps do not accumulate stray descriptors."""
    r, w = fds.pipe()
    baseline = _open_fd_count()
    for _ in range(50):
        a = os.dup(w)
        remap_fds({a: a}, owned=[a])  # a is protected, stays open
        os.close(a)
    assert _open_fd_count() == baseline
    assert _delivers(w, r)
