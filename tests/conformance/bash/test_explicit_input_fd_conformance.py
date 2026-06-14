"""Conformance: an explicit input fd (`N<file`) reaches the named fd.

An explicit file-descriptor prefix on an input redirect (`5<file`) must open
the file on fd N, not clobber stdin — for external commands run through the
forked-child path too, not just `exec`. psh's child/builtin input paths used
to call `redirect_input_from_file(target)` without the redirect, defaulting
to fd 0, so `cmd 5<file` left fd 5 closed and an external command reading it
got "Bad file descriptor". Fixed by passing the redirect through (review:
redirection/IO architecture, Ugly 2). See fix/explicit-input-fd-child.

Each case is a self-contained command (its own mktemp + cleanup) run
identically under psh and bash via assert_identical_behavior.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from conformance_framework import ConformanceTest

_READ_FD5 = (
    'python3 -c "import os;print(os.read(5,100).decode().strip())"')
_READ_FD6 = (
    'python3 -c "import os;print(os.read(6,100).decode().strip())"')


class TestExplicitInputFd(ConformanceTest):
    """`N<file` opens the file on fd N across parent/child paths."""

    def test_external_reads_explicit_input_fd(self):
        # The forked-child path: an external command reading fd 5 directly.
        self.assert_identical_behavior(
            f'd=$(mktemp -d); printf "from5\\n" > "$d/f"; '
            f'{_READ_FD5} 5<"$d/f"; rm -rf "$d"')

    def test_plain_stdin_redirect_unchanged(self):
        self.assert_identical_behavior(
            'd=$(mktemp -d); printf "viastdin\\n" > "$d/f"; '
            'cat < "$d/f"; rm -rf "$d"')

    def test_fd0_prefix_equals_plain(self):
        self.assert_identical_behavior(
            'd=$(mktemp -d); printf "z\\n" > "$d/f"; '
            'cat 0< "$d/f"; rm -rf "$d"')

    def test_exec_explicit_input_fd(self):
        self.assert_identical_behavior(
            'd=$(mktemp -d); printf "ex\\n" > "$d/f"; '
            f'exec 6< "$d/f"; {_READ_FD6}; exec 6<&-; rm -rf "$d"')
