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


def test_multiline_compound_with_arith_shift_roundtrips_as_one_entry(histfile):
    """A multi-line compound containing an arithmetic '<<' must be recorded
    in its single-line cmdhist form, so a save -> reload round-trip yields ONE
    entry. Regression (r19-T4 bounce): the cmdhist joiner consumed the '<<'
    substring over-approximation as a final answer, kept the newline before
    `fi`, and the HISTFILE (one line per entry) reload SPLIT the command into
    bogus entries ('fi', 'done')."""
    m = _manager(histfile)
    m.load_from_file()  # empty
    m.add_to_history("if true\nthen echo $((1<<2))\nfi")
    joined = "if true; then echo $((1<<2)); fi"
    assert m.shell.state.history[-1] == joined  # recorded pre-joined
    m.save_to_file()

    fresh = _manager(histfile)
    fresh.load_from_file()
    assert fresh.shell.state.history == [joined]  # ONE entry, no 'fi' split


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


def test_history_dash_c_does_not_lose_subsequent_commands(histfile):
    """R14.B: `history -c` must reset the file-sync marker (via
    HistoryManager.clear_history), so commands added AFTER the clear are still
    persisted. The builtin used to clear state.history directly, leaving the
    marker stale — new commands fell outside the save slice and were lost."""
    shell = Shell()
    shell.state.history_file = histfile
    m = shell.interactive_manager.history_manager
    for c in ("echo a", "echo b", "echo c"):
        m.add_to_history(c)
    m.save_to_file()
    assert m._file_synced_len == 3

    shell.run_command("history -c")
    assert len(shell.state.history) == 0
    assert m._file_synced_len == 0  # marker reset (the fix)

    m.add_to_history("echo x")
    m.save_to_file()
    # The post-clear command survives (pre-fix it was dropped entirely).
    assert "echo x" in _read(histfile)


def test_in_session_trim_does_not_lose_new_entries(histfile):
    """Regression for the v0.447 stale-index bug: a session that exceeds
    max_history_size before saving must still persist ALL of its new commands,
    not just the tail past the (now-stale) sync index."""
    with open(histfile, "w") as f:
        f.write("old1\nold2\nold3\n")
    m = _manager(histfile)
    m.state.max_history_size = 4
    m.load_from_file()  # history=[old1,old2,old3], synced=3
    # Each add past size 4 trims one entry off the front, shifting the index.
    m.add_to_history("n1")
    m.add_to_history("n2")
    m.add_to_history("n3")
    m.save_to_file()
    contents = _read(histfile)
    # All three new commands survive (pre-fix, n1 and n2 were dropped).
    for c in ("n1", "n2", "n3"):
        assert c in contents, f"{c} lost after in-session trim: {contents}"
    # And the file respects the size cap.
    assert len(contents) <= 4
