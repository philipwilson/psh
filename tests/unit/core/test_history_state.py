"""Unit tests for the HistoryState decomposition (R9.B2)."""

from psh.core.history_state import HistoryState


def test_defaults():
    hs = HistoryState()
    assert hs.entries == []
    assert hs.file_path.endswith(".psh_history")
    assert hs.max_size == 1000


def test_state_history_is_mutated_in_place_by_reference():
    """ShellState.history must return the live list so append()/clear() work."""
    from psh.core.state import ShellState

    state = ShellState()
    assert state.history is state.history_state.entries
    state.history.append("echo one")
    state.history.append("echo two")
    assert state.history_state.entries == ["echo one", "echo two"]
    state.history.clear()
    assert state.history_state.entries == []


def test_state_history_setter_replaces_list():
    from psh.core.state import ShellState

    state = ShellState()
    state.history = ["reassigned"]
    assert state.history_state.entries == ["reassigned"]
    assert state.history == ["reassigned"]


def test_state_file_and_size_properties_delegate():
    from psh.core.state import ShellState

    state = ShellState()
    state.history_file = "/tmp/custom_history"
    state.max_history_size = 42
    assert state.history_state.file_path == "/tmp/custom_history"
    assert state.history_state.max_size == 42
