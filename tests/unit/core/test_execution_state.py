"""ExecutionState — the per-command execution scratch sub-object of ShellState.

Mirrors test_history_state / test_terminal_state: the typed sub-object exists,
ShellState delegates to it via properties (so call sites are untouched), and
copy_into() carries the inheritable fields for subshell adoption (the v0.453
$!-in-subshell bug was a missed field in that copy).
"""

from psh.core.execution_state import ExecutionState
from psh.core.state import ShellState


def test_defaults():
    e = ExecutionState()
    assert e.last_exit_code == 0
    assert e.last_bg_pid is None
    assert e.foreground_pgid is None
    assert e.command_number == 0
    assert e.pipestatus == []
    assert e.errexit_eligible is True
    assert e.last_cmdsub_status is None
    assert e.in_forked_child is False


def test_shellstate_properties_delegate_to_execution():
    s = ShellState()
    s.last_exit_code = 42
    s.last_bg_pid = 1234
    s.pipestatus = [0, 1]
    s.in_forked_child = True
    # Reads go through to the sub-object…
    assert s.execution.last_exit_code == 42
    assert s.execution.last_bg_pid == 1234
    assert s.execution.pipestatus == [0, 1]
    assert s.execution.in_forked_child is True
    # …and back out through the property.
    s.execution.last_cmdsub_status = 7
    assert s.last_cmdsub_status == 7


def test_pipestatus_mutated_in_place_via_property():
    s = ShellState()
    s.pipestatus.append(5)  # in-place mutation through the property
    assert s.execution.pipestatus == [5]


def test_copy_into_carries_inheritable_fields():
    parent = ExecutionState()
    parent.last_exit_code = 3
    parent.last_bg_pid = 999
    parent.foreground_pgid = 100
    parent.command_number = 12
    parent.pipestatus = [0, 2]
    parent.errexit_eligible = False
    parent.last_cmdsub_status = 4
    parent.in_forked_child = True

    child = ExecutionState()
    parent.copy_into(child)

    assert child.last_exit_code == 3
    assert child.last_bg_pid == 999  # $! inherited (v0.453 regression)
    assert child.foreground_pgid == 100
    assert child.command_number == 12
    assert child.pipestatus == [0, 2]
    assert child.errexit_eligible is False
    assert child.last_cmdsub_status == 4
    # in_forked_child is NOT inherited — the child sets it itself.
    assert child.in_forked_child is False


def test_copy_into_pipestatus_is_a_fresh_list():
    parent = ExecutionState()
    parent.pipestatus = [1, 2, 3]
    child = ExecutionState()
    parent.copy_into(child)
    child.pipestatus.append(4)
    assert parent.pipestatus == [1, 2, 3]  # not aliased
