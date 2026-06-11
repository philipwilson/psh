"""Shared FileRedirector predicates (noclobber, dup-fd validity).

These were inlined across the four redirect-dispatch methods; this pins the
extracted helpers used by all of them.
"""

import os

import pytest

from psh.io_redirect.file_redirect import FileRedirector


@pytest.fixture
def fr(shell):
    return FileRedirector(shell)


class TestNoclobberBlocks:
    def test_blocks_when_set_and_exists(self, fr, shell, tmp_path):
        target = str(tmp_path / "exists.txt")
        open(target, "w").close()
        shell.state.options['noclobber'] = True
        assert fr._noclobber_blocks(target) is True

    def test_allows_when_unset(self, fr, shell, tmp_path):
        target = str(tmp_path / "exists.txt")
        open(target, "w").close()
        shell.state.options['noclobber'] = False
        assert fr._noclobber_blocks(target) is False

    def test_allows_when_missing(self, fr, shell, tmp_path):
        target = str(tmp_path / "missing.txt")
        shell.state.options['noclobber'] = True
        assert fr._noclobber_blocks(target) is False

    # bash exempts non-regular files: noclobber protects only data that a
    # truncating open would destroy (bash 5.2 verified: `set -C; > /dev/null`
    # succeeds, `> fifo` succeeds, `> dangling_symlink` fails).

    def test_allows_device_file(self, fr, shell):
        shell.state.options['noclobber'] = True
        assert fr._noclobber_blocks('/dev/null') is False

    def test_allows_fifo(self, fr, shell, tmp_path):
        fifo = str(tmp_path / "pipe")
        os.mkfifo(fifo)
        shell.state.options['noclobber'] = True
        assert fr._noclobber_blocks(fifo) is False

    def test_blocks_symlink_to_regular_file(self, fr, shell, tmp_path):
        target = str(tmp_path / "exists.txt")
        open(target, "w").close()
        link = str(tmp_path / "link")
        os.symlink(target, link)
        shell.state.options['noclobber'] = True
        assert fr._noclobber_blocks(link) is True

    def test_blocks_dangling_symlink(self, fr, shell, tmp_path):
        # bash opens O_CREAT|O_EXCL when the stat target is missing; the
        # dangling link makes that fail EEXIST, so the redirect is blocked.
        link = str(tmp_path / "dangling")
        os.symlink(str(tmp_path / "missing.txt"), link)
        shell.state.options['noclobber'] = True
        assert fr._noclobber_blocks(link) is True

    def test_allows_directory(self, fr, shell, tmp_path):
        # Not blocked by noclobber; the subsequent open fails EISDIR instead
        # (bash reports "Is a directory", not "cannot overwrite").
        shell.state.options['noclobber'] = True
        assert fr._noclobber_blocks(str(tmp_path)) is False


class TestDupFdValid:
    def test_valid_for_open_fd(self, fr):
        r, w = os.pipe()
        try:
            assert fr._dup_fd_valid(r) is True
            assert fr._dup_fd_valid(w) is True
        finally:
            os.close(r)
            os.close(w)

    def test_invalid_for_closed_fd(self, fr):
        r, w = os.pipe()
        os.close(r)
        os.close(w)
        assert fr._dup_fd_valid(r) is False

    def test_invalid_for_unopened_high_fd(self, fr):
        # Probe upward for a genuinely-closed fd rather than hardcoding a number:
        # under pytest-xdist a worker keeps its execnet channel on a high fd, so a
        # fixed fd like 99 may actually be open and the assertion would flake.
        fd = 50
        while True:
            try:
                os.fstat(fd)  # open -> keep looking
                fd += 1
            except OSError:
                break         # closed
        assert fr._dup_fd_valid(fd) is False
