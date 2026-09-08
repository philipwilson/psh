"""Unit pins: which redirect gives a frame's fd 0 an INPUT (C022).

``psh/io_redirect/redirect_program.py#supplies_frame_stdin`` is the one
classifier behind the async-stdin rule: a compound command's redirect list
supplies fd 0 — and so reaches a command the body backgrounds — only when the
list contains an INPUT-direction redirect that lands on fd 0.

BOTH halves were live defects. Ignoring DIRECTION made ``{ cat & wait; } 0>&1``
hand the background reader a write-only fd 0, where it blocks forever at a
terminal; ignoring the FD would make ``3< file`` supply a descriptor nobody
reads. A CLOSE counts when it closes fd 0, whichever way it is spelled — bash
agrees (``redir.c#stdin_redirection`` answers on the redirector for the close
and dup forms).
"""

import pytest

from psh.ast_nodes import Redirect
from psh.io_redirect.redirect_program import (
    list_supplies_frame_stdin,
    supplies_frame_stdin,
    target_fd_of,
)


def _r(type_, fd=None, **kw):
    return Redirect(type=type_, target=kw.pop("target", "f"), fd=fd, **kw)


@pytest.mark.parametrize("redirect,expected", [
    # File-opening INPUT forms on fd 0.
    (_r('<'), True),
    (_r('<', fd=0), True),
    (_r('<>'), True),
    (_r('<>', fd=0), True),
    # ...and on any other fd: it supplies THAT descriptor, not fd 0.
    (_r('<', fd=3), False),
    (_r('<>', fd=7), False),
    # Here-documents and here-strings are input on fd 0 by default.
    (_r('<<'), True),
    (_r('<<-'), True),
    (_r('<<<'), True),
    (_r('<<', fd=3), False),
    # Input DUPs: `<&3` and `0<&3` supply fd 0; `3<&4` does not.
    (_r('<&', dup_fd=3), True),
    (_r('<&', fd=0, dup_fd=3), True),
    (_r('<&', fd=3, dup_fd=4), False),
    # The MOVE spelling `0<&3-` still supplies fd 0 (dup, then close 3).
    (_r('<&', fd=0, dup_fd=3, move=True), True),
    # OUTPUT forms supply nothing — including when they name fd 0. This is the
    # B1 half: `0>&1` gives fd 0 a write-only descriptor.
    (_r('>'), False),
    (_r('>', fd=0), False),
    (_r('>>', fd=0), False),
    (_r('>|', fd=0), False),
    (_r('>&', fd=0, dup_fd=1), False),
    (_r('>&', dup_fd=2), False),
    (_r('>&', fd=0, dup_fd=1, move=True), False),
    # A CLOSE of fd 0 counts, in either spelling; a close of anything else
    # does not (a bare `>&-` closes fd 1).
    (_r('<&-', target=None), True),
    (_r('<&-', target=None, fd=0), True),
    (_r('>&-', target=None, fd=0), True),
    (_r('>&-', target=None), False),
    (_r('<&-', target=None, fd=3), False),
    # `&>file` names fd 1 (and 2); a named fd is allocated at >= 10.
    (_r('>', combined=True), False),
    (_r('<', var_fd='v'), False),
    (_r('<<<', var_fd='v'), False),
])
def test_supplies_frame_stdin(redirect, expected):
    """C022: direction AND fd, one classifier."""
    assert supplies_frame_stdin(redirect) is expected, redirect


def test_list_answers_for_the_whole_list():
    """An input on fd 0 ANYWHERE in the list supplies the frame — the last
    redirect still decides what fd 0 ends up being (`{ } < in 0>&1` inherits a
    write-only fd 0 in both shells)."""
    assert list_supplies_frame_stdin([]) is False
    assert list_supplies_frame_stdin([_r('>'), _r('>>', fd=2)]) is False
    assert list_supplies_frame_stdin([_r('>'), _r('<')]) is True
    assert list_supplies_frame_stdin([_r('<'), _r('>&', fd=0, dup_fd=1)]) is True


@pytest.mark.parametrize("redirect,fd", [
    (_r('<'), 0), (_r('>'), 1), (_r('>', fd=2), 2), (_r('<<'), 0),
    (_r('<<', fd=4), 4), (_r('>', combined=True), 1), (_r('<&-', target=None), 0),
    (_r('>&-', target=None), 1),
])
def test_target_fd_of_is_the_one_default_fd_rule(redirect, fd):
    """The default-fd rule has one home; ``RedirectPlan.target_fd`` delegates
    to it, so the classifier and the applicator cannot drift apart."""
    assert target_fd_of(redirect) == fd
