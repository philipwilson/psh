"""Unit tests for concurrency-safe history persistence (HistoryManager).

Regression for the multi-terminal clobber bug: several psh sessions sharing
one history file (e.g. each terminal window auto-starting psh from .zshrc)
used to overwrite one another on exit — the last shell to call
``save_to_file`` truncate-rewrote the file with only its own list, dropping
every other session's commands. ``save_to_file`` now appends only the
session's new entries under an exclusive lock, merging with the current
on-disk contents, so concurrent shells no longer clobber each other.
"""

import os

import pytest

from psh.shell import Shell


@pytest.fixture
def histfile(tmp_path):
    return str(tmp_path / ".psh_history")


def _manager(histfile):
    """A HistoryManager bound to a fresh shell pointed at `histfile`."""
    shell = Shell()
    shell.state.history_file = histfile
    return shell.interactive_manager.history_manager


def _read(histfile):
    if not os.path.exists(histfile):
        return []
    with open(histfile) as f:
        return [ln.rstrip("\n") for ln in f if ln.strip()]


def test_save_then_load_roundtrip(histfile):
    m = _manager(histfile)
    m.load_from_file()  # empty
    m.add_to_history("echo one")
    m.add_to_history("echo two")
    m.save_to_file()
    assert _read(histfile) == ["echo one", "echo two"]


def test_sequential_sessions_accumulate(histfile):
    a = _manager(histfile)
    a.load_from_file()
    a.add_to_history("from session A")
    a.save_to_file()

    b = _manager(histfile)
    b.load_from_file()
    b.add_to_history("from session B")
    b.save_to_file()

    assert _read(histfile) == ["from session A", "from session B"]


def test_concurrent_sessions_do_not_clobber(histfile):
    """The core fix: two overlapping sessions both load, both add, both save;
    neither loses the other's commands (last-writer-wins is gone)."""
    # Seed a baseline (like an existing ~/.psh_history).
    with open(histfile, "w") as f:
        f.write("old1\nold2\n")

    a = _manager(histfile)
    b = _manager(histfile)
    a.load_from_file()  # both load the same 2 baseline lines
    b.load_from_file()

    a.add_to_history("cmd from A")
    b.add_to_history("cmd from B")

    # A exits first, then B exits last (the old code had B clobber A here).
    a.save_to_file()
    b.save_to_file()

    contents = _read(histfile)
    assert "old1" in contents and "old2" in contents
    assert "cmd from A" in contents, f"A's command was clobbered: {contents}"
    assert "cmd from B" in contents, f"B's command missing: {contents}"


def test_save_appends_only_new_entries_no_duplication(histfile):
    """A session that loaded N entries and added M must not re-write the N."""
    with open(histfile, "w") as f:
        f.write("loaded1\nloaded2\n")
    m = _manager(histfile)
    m.load_from_file()
    m.add_to_history("new1")
    m.save_to_file()
    # loaded entries appear exactly once (merged, not duplicated)
    assert _read(histfile) == ["loaded1", "loaded2", "new1"]


def test_save_trims_to_max_history_size(histfile):
    m = _manager(histfile)
    m.state.max_history_size = 3
    m.load_from_file()
    for i in range(5):
        m.add_to_history(f"cmd{i}")
    m.save_to_file()
    assert _read(histfile) == ["cmd2", "cmd3", "cmd4"]
