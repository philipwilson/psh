"""InputCursorRegistry: aliasing, frame scoping, and the fd-set derivation.

Slot 4B.4. The shell-level consequences are pinned in
``tests/integration/redirection/test_input_cursor_contract_4b4.py``; these are
the registry-level invariants those rest on, plus the one that is invisible
from the shell.

Every cell closes the fds it opens (xdist workers share a process).
"""
import os

import pytest

from psh.ast_nodes import Redirect
from psh.io_redirect.input_cursor import (
    InputCursorRegistry,
    OpenDescription,
    dup_alias_fds,
)


class _Ctx:
    """Minimal IOContext: only ``.stdin`` is consulted, via make_reader."""

    def __init__(self, stdin):
        self.stdin = stdin


@pytest.fixture
def ctx():
    # A real fd-backed stdin so make_reader takes the fd path (a StringIO would
    # be treated as an injected stream and never registered at all).
    return _Ctx(open(os.devnull))


def _pipe(data=b""):
    r, w = os.pipe()
    if data:
        os.write(w, data)
    os.close(w)
    return r


class TestDupAliasing:
    def test_dup_makes_both_fds_resolve_to_one_cursor(self, ctx):
        reg = InputCursorRegistry()
        r = _pipe(b"hello\n")
        try:
            reg.bind_dup(9, r)
            assert reg.cursor_for_fd(ctx, r) is reg.cursor_for_fd(ctx, 9)
        finally:
            os.close(r)

    def test_dup_materializes_a_description_for_an_unread_source(self, ctx):
        """The lazy-registry case, which is the NORMAL one.

        `exec 3<&0` almost always runs before anything has read fd 0, so the
        source has no description yet. If bind_dup only copied an existing
        entry it would silently do nothing here — the failure mode that made
        the first draft of this feature look like it worked when it did not.
        """
        reg = InputCursorRegistry()
        r = _pipe(b"hello\n")
        try:
            assert reg._fd_to_desc == {}          # nothing read yet
            reg.bind_dup(9, r)
            assert reg._fd_to_desc[r] is reg._fd_to_desc[9]
        finally:
            os.close(r)

    def test_first_read_through_either_fd_keeps_the_alias(self, ctx):
        """cursor_for_fd must REUSE the description bind_dup recorded.

        Rebuilding it (the pre-4B.4 behavior) breaks the alias at the moment
        of first use, which no dup-site test can see because the dup itself
        looks correct.
        """
        reg = InputCursorRegistry()
        r = _pipe(b"AB\n")
        try:
            reg.bind_dup(9, r)
            desc_before = reg._fd_to_desc[r]
            reg.cursor_for_fd(ctx, 9)             # read through the ALIAS first
            assert reg._fd_to_desc[r] is desc_before
            assert reg._fd_to_desc[9] is desc_before
        finally:
            os.close(r)


class TestFrameScoping:
    def test_frame_hides_the_outer_cursor_and_restores_it(self, ctx):
        reg = InputCursorRegistry()
        r = _pipe(b"outer\n")
        try:
            outer = reg.cursor_for_fd(ctx, r)
            saved = reg.push_frame([r])
            inner = reg.cursor_for_fd(ctx, r)
            assert inner is not outer, "the frame reused the outer cursor"
            reg.pop_frame(saved)
            assert reg.cursor_for_fd(ctx, r) is outer, "the outer cursor was lost"
        finally:
            os.close(r)

    def test_pop_drops_the_frames_own_cursor(self, ctx):
        """The reverse leak, at registry level: what the frame bound must not
        survive the frame, or its buffered bytes surface on the restored fd."""
        reg = InputCursorRegistry()
        r = _pipe(b"x\n")
        try:
            saved = reg.push_frame([r])
            inner = reg.cursor_for_fd(ctx, r)
            reg.pop_frame(saved)
            assert reg.cursor_for_fd(ctx, r) is not inner
        finally:
            os.close(r)

    def test_frames_nest(self, ctx):
        reg = InputCursorRegistry()
        r = _pipe(b"x\n")
        try:
            outer = reg.cursor_for_fd(ctx, r)
            s1 = reg.push_frame([r])
            mid = reg.cursor_for_fd(ctx, r)
            s2 = reg.push_frame([r])
            inner = reg.cursor_for_fd(ctx, r)
            assert len({id(outer), id(mid), id(inner)}) == 3
            reg.pop_frame(s2)
            assert reg.cursor_for_fd(ctx, r) is mid
            reg.pop_frame(s1)
            assert reg.cursor_for_fd(ctx, r) is outer
        finally:
            os.close(r)

    def test_pop_is_inert_a_second_time(self, ctx):
        # restore_builtin_redirections clears its token after popping; a frame
        # restored twice (the fatal-signal drain path) must not undo anything.
        reg = InputCursorRegistry()
        r = _pipe(b"x\n")
        try:
            outer = reg.cursor_for_fd(ctx, r)
            saved = reg.push_frame([r])
            reg.pop_frame(saved)
            reg.pop_frame({})
            assert reg.cursor_for_fd(ctx, r) is outer
        finally:
            os.close(r)


class TestDupAliasFds:
    """The single derivation the three application paths share."""

    @pytest.mark.parametrize("rtype,fd,dup_fd,expected", [
        ('<&', 3, 0, (3, 0)),        # exec 3<&0
        ('>&', 2, 1, (2, 1)),        # 2>&1
        ('<&', None, 5, (0, 5)),     # <&5 defaults to fd 0
        ('>&', None, 5, (1, 5)),     # >&5 defaults to fd 1
        ('<&-', 3, None, None),      # a CLOSE is not a dup
        ('<', 0, None, None),        # an OPEN is not a dup
        ('<<', 0, None, None),       # a heredoc is not a dup
    ])
    def test_classification(self, rtype, fd, dup_fd, expected):
        r = Redirect(type=rtype, target=None, fd=fd, dup_fd=dup_fd)
        assert dup_alias_fds(r) == expected

    def test_unresolved_dynamic_dup_is_not_an_alias(self):
        """`<&$v` before resolution has no fd number, so it must fall back to
        the SAFE case (drop the binding) rather than guess one."""
        r = Redirect(type='<&', target='$v', fd=3, dup_fd=None)
        assert dup_alias_fds(r) is None

    def test_numeric_target_without_dup_fd_is_an_alias(self):
        r = Redirect(type='<&', target='4', fd=3, dup_fd=None)
        assert dup_alias_fds(r) == (3, 4)


def test_rebind_still_drops():
    """Aliasing must not have weakened the OPEN case."""
    reg = InputCursorRegistry()
    desc = OpenDescription("fd0")
    reg._fd_to_desc[0] = desc
    reg._desc_to_cursor[desc] = object()
    reg.rebind(0)
    assert reg._fd_to_desc == {} and reg._desc_to_cursor == {}
