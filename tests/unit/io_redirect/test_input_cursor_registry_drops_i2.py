"""Registry drop + fresh-child pins folded from I1 to I2 (campaign I2 handoff).

Two polish pins the I1 integrator routed here:

1. **close-drops named identity** — `exec 3<&-` drops fd 3's cursor entry, so a
   later reopen/read builds a fresh cursor (no stale decoder/queue carryover).
   The close is one of the input-family redirect types the exec hook rebinds.
2. **fresh-child registry** — a forked child starts with an EMPTY input-cursor
   registry (and empty script-fd reservation), matching bash carrying no
   userspace read buffer across a fork.
"""
import os

from psh.builtins.input_reader import InputCursor
from psh.core.state import ChildContext, ShellState
from psh.executor.command import CommandExecutor
from psh.io_redirect.input_cursor import InputCursorRegistry, OpenDescription


def test_close_and_dup_are_rebind_types():
    # `exec 3<&-` (close) and `exec 3<&N` (dup) are input-family redirects the
    # exec hook rebinds — which is what drops fd 3's cursor entry.
    types = CommandExecutor._INPUT_REBIND_TYPES
    assert "<&-" in types
    assert "<&" in types
    assert "<" in types


def test_rebind_drops_the_cursor_entry():
    # A permanent close/rebind of an fd drops its persisted cursor (the state
    # that would otherwise carry over across the reopened description).
    reg = InputCursorRegistry()
    r, w = os.pipe()
    try:
        desc = OpenDescription("fd3")
        reg._fd_to_desc[3] = desc
        reg._desc_to_cursor[desc] = InputCursor(fd=r)
        assert reg._fd_to_desc.get(3) is desc
        reg.rebind(3)                       # what `exec 3<&-` triggers
        assert 3 not in reg._fd_to_desc
        assert desc not in reg._desc_to_cursor
    finally:
        os.close(r)
        os.close(w)


def test_forked_child_starts_with_fresh_registries():
    parent = ShellState()
    # Populate the parent's I1 cursor registry and I2 script-fd reservation.
    pdesc = OpenDescription("fd0")
    parent.input_cursors._fd_to_desc[0] = pdesc
    parent.input_cursors._desc_to_cursor[pdesc] = InputCursor(fd=0)
    parent.reserved_script_fds[255] = object()

    child = ShellState.clone_for_child(parent, ChildContext.SUBSHELL)

    # The child inherits no userspace read buffer and does not own the parent's
    # script reader.
    assert child.input_cursors._fd_to_desc == {}
    assert child.input_cursors._desc_to_cursor == {}
    assert child.reserved_script_fds == {}
    # ...and it is a DISTINCT registry object, not the parent's.
    assert child.input_cursors is not parent.input_cursors
    assert child.reserved_script_fds is not parent.reserved_script_fds
