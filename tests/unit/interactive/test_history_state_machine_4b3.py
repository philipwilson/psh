"""The history state machine: read cursor and pending set (slot 4B.3).

MEDIUM-7 was a conflation of two different quantities:

* ``_file_read_len`` — a position in the DEFAULT history FILE. Memory-side
  operations (``-d``, ``-c``, the HISTSIZE trim) must never move it, because
  deleting something from memory does not un-read a file line.
* the PENDING set — the entries recorded this session and not yet written.
  Lines that arrived from a file (load, ``-r``, ``-n``) are never pending.

Before this slot the read cursor had **zero** references anywhere under
``tests/`` — which is how the conflation survived. These cells pin the marker
model DIRECTLY, op by op, as well as through observable behaviour: a
state-machine bug shows up in the cursor long before it shows up in a listing,
and the end-to-end vs-bash coverage lives in
``tests/conformance/bash/test_history_state_machine_conformance.py``.

Both cursor and pending behaviour were derived from bash 5.2.26 probes rather
than from symmetry arguments; where psh deliberately differs from bash the
conformance module carries the both-sides characterization.
"""

import pytest

from psh.shell import Shell


@pytest.fixture
def mgr(tmp_path):
    """A HistoryManager whose $HISTFILE is a per-test temp file."""
    shell = Shell(norc=True)
    shell.state.history_file = str(tmp_path / "psh_history")
    return shell.interactive_manager.history_manager


def seed_file(mgr, *lines):
    with open(mgr.state.history_file, "w") as f:
        f.write("".join(line + "\n" for line in lines))


def other_file(mgr, name, *lines):
    import os
    path = os.path.join(os.path.dirname(mgr.state.history_file), name)
    with open(path, "w") as f:
        f.write("".join(line + "\n" for line in lines))
    return path


def read_file(path):
    with open(path) as f:
        return [ln.rstrip("\n") for ln in f if ln.strip()]


# --------------------------------------------------------------------------
# The READ CURSOR, op by op.  bash 5.2.26 leaves its file counter untouched
# across every MEMORY-side operation; only file reads/appends move it.
# --------------------------------------------------------------------------

class TestReadCursorPerOp:
    def test_startup_load_sets_it_to_the_lines_read(self, mgr):
        seed_file(mgr, "a", "b", "c")
        mgr.load_from_file()
        assert mgr._file_read_len == 3

    def test_recording_does_not_move_it(self, mgr):
        seed_file(mgr, "a", "b", "c")
        mgr.load_from_file()
        mgr.add_to_history("typed one")
        assert mgr._file_read_len == 3

    def test_store_does_not_move_it(self, mgr):
        seed_file(mgr, "a", "b", "c")
        mgr.load_from_file()
        mgr.store_entry("stored one")
        assert mgr._file_read_len == 3

    @pytest.mark.parametrize("first,last", [(1, 1), (1, 2), (3, 3)])
    def test_delete_does_not_move_it(self, mgr, first, last):
        """MEDIUM-7 leg A. Below the cursor, spanning it, and at it — the
        cursor is a FILE position and a memory delete does not un-read."""
        seed_file(mgr, "a", "b", "c")
        mgr.load_from_file()
        mgr.delete_entry(first, last)
        assert mgr._file_read_len == 3

    def test_clear_does_not_move_it(self, mgr):
        """MEDIUM-7 leg C / LEDGER carry #32."""
        seed_file(mgr, "a", "b", "c")
        mgr.load_from_file()
        mgr.clear_history()
        assert mgr._file_read_len == 3

    def test_histsize_front_drop_does_not_move_it(self, mgr):
        seed_file(mgr, "a", "b", "c")
        mgr.load_from_file()
        mgr.state.max_history_size = 2
        mgr.add_to_history("typed one")          # forces a front-drop
        assert len(mgr.state.history) == 2
        assert mgr._file_read_len == 3

    def test_read_default_sets_it_to_the_files_length(self, mgr):
        seed_file(mgr, "a", "b", "c")
        mgr.load_from_file()
        seed_file(mgr, "a", "b", "c", "d")
        assert mgr.read_history() is True
        assert mgr._file_read_len == 4

    def test_read_named_does_not_move_it(self, mgr):
        """psh keeps a per-DEFAULT-file cursor. bash has ONE global counter that
        a named-file read overwrites — a declared deviation (a `history -r
        otherfile` there corrupts the default file's resume position)."""
        seed_file(mgr, "a", "b", "c")
        mgr.load_from_file()
        assert mgr.read_history(other_file(mgr, "other", "x", "y")) is True
        assert mgr._file_read_len == 3

    def test_read_new_default_advances_past_the_new_lines(self, mgr):
        seed_file(mgr, "a", "b", "c")
        mgr.load_from_file()
        seed_file(mgr, "a", "b", "c", "d", "e")
        assert mgr.read_new_history() is True
        assert mgr.state.history[-2:] == ["d", "e"]
        assert mgr._file_read_len == 5

    def test_read_new_named_does_not_move_it(self, mgr):
        seed_file(mgr, "a", "b", "c")
        mgr.load_from_file()
        assert mgr.read_new_history(other_file(mgr, "o2", "x", "y")) is True
        assert mgr._file_read_len == 3

    def test_append_default_advances_by_the_lines_written(self, mgr):
        seed_file(mgr, "a", "b", "c")
        mgr.load_from_file()
        mgr.add_to_history("typed one")
        assert mgr.append_history() is True
        assert mgr._file_read_len == 4

    def test_append_named_does_not_move_it(self, mgr):
        seed_file(mgr, "a", "b", "c")
        mgr.load_from_file()
        mgr.add_to_history("typed one")
        assert mgr.append_history(other_file(mgr, "o3")) is True
        assert mgr._file_read_len == 3

    def test_write_default_sets_it_to_the_list_length(self, mgr):
        seed_file(mgr, "a", "b", "c")
        mgr.load_from_file()
        mgr.add_to_history("typed one")
        assert mgr.write_history() is True
        assert mgr._file_read_len == 4

    def test_write_named_does_not_move_it(self, mgr):
        seed_file(mgr, "a", "b", "c")
        mgr.load_from_file()
        mgr.add_to_history("typed one")
        assert mgr.write_history(other_file(mgr, "o4")) is True
        assert mgr._file_read_len == 3

    def test_external_shrink_leaves_it_stale_and_that_is_harmless(self, mgr):
        """The underflow face: the file loses lines below the cursor. Both
        shells leave the counter alone; a later grow resumes from it."""
        seed_file(mgr, "a", "b", "c")
        mgr.load_from_file()
        seed_file(mgr, "only1")
        assert mgr.read_new_history() is True
        assert mgr.state.history == ["a", "b", "c"]     # nothing pulled
        seed_file(mgr, "only1", "g1", "g2", "g3", "g4")
        assert mgr.read_new_history() is True
        assert mgr.state.history[-2:] == ["g3", "g4"]   # resumed from 3


# --------------------------------------------------------------------------
# The PENDING set.  Invariants ruled at R3(a).
# --------------------------------------------------------------------------

class TestPendingMembership:
    """Invariant 2: pending iff it entered through the recording pipeline."""

    def test_recorded_entries_are_pending(self, mgr):
        mgr.add_to_history("typed one")
        assert mgr._pending_entries() == ["typed one"]

    def test_stored_entries_are_pending(self, mgr):
        mgr.store_entry("stored one")
        assert mgr._pending_entries() == ["stored one"]

    def test_loaded_lines_are_not_pending(self, mgr):
        seed_file(mgr, "a", "b")
        mgr.load_from_file()
        assert mgr._pending_entries() == []

    def test_lines_read_from_the_default_file_are_not_pending(self, mgr):
        seed_file(mgr, "a", "b")
        assert mgr.read_history() is True
        assert mgr._pending_entries() == []

    def test_lines_read_from_a_NAMED_file_are_not_pending(self, mgr):
        """The leak face: they belong to that other file, and treating them as
        pending appended another file's contents into $HISTFILE."""
        assert mgr.read_history(other_file(mgr, "o", "x", "y")) is True
        assert mgr._pending_entries() == []

    def test_read_new_lines_are_not_pending(self, mgr):
        seed_file(mgr, "a", "b")
        assert mgr.read_new_history() is True
        assert mgr._pending_entries() == []


class TestPendingIsAViewOfMemory:
    """Invariant 1: anything leaving state.history leaves pending, by ANY
    route — so a save can never resurrect an entry that is gone from memory."""

    def test_delete_removes_from_pending(self, mgr):
        mgr.add_to_history("keep me")
        mgr.add_to_history("delete me")
        mgr.delete_entry(2, 2)
        assert mgr._pending_entries() == ["keep me"]

    def test_clear_empties_pending(self, mgr):
        mgr.add_to_history("gone")
        mgr.clear_history()
        assert mgr._pending_entries() == []

    def test_histsize_front_drop_removes_from_pending(self, mgr):
        mgr.state.max_history_size = 2
        for c in ("one", "two", "three"):
            mgr.add_to_history(c)
        assert mgr.state.history == ["two", "three"]
        assert mgr._pending_entries() == ["two", "three"]

    def test_erasedups_removes_the_erased_copies_from_pending(self, mgr):
        mgr.state.set_variable("HISTCONTROL", "erasedups")
        for c in ("dup", "middle", "dup"):
            mgr.add_to_history(c)
        assert mgr.state.history == ["middle", "dup"]
        assert mgr._pending_entries() == ["middle", "dup"]

    def test_the_builtin_CV3_strip_removes_from_pending(self, mgr):
        """The history builtin deletes ``state.history[-1]`` DIRECTLY (the CV3
        strip, which this slot must not modify). Pending is a view precisely so
        that such an outside deletion cannot leave a phantom pending entry."""
        mgr.add_to_history("first")
        mgr.add_to_history("about to be stripped")
        del mgr.state.history[-1]                 # what _strip_own_invocation does
        assert mgr._pending_entries() == ["first"]

    def test_a_cleared_entry_is_never_written_afterwards(self, mgr):
        mgr.add_to_history("secret")
        mgr.clear_history()
        mgr.add_to_history("after")
        mgr.save_to_file()
        assert read_file(mgr.state.history_file) == ["after"]


class TestPendingMultisetSemantics:
    """Invariant 4: identical strings are counted, not deduplicated."""

    def test_two_identical_pending_entries_are_saved_once_each(self, mgr):
        mgr.add_to_history("same")
        mgr.add_to_history("same")
        assert mgr._pending_entries() == ["same", "same"]
        mgr.save_to_file()
        assert read_file(mgr.state.history_file) == ["same", "same"]

    def test_deleting_one_of_two_identical_entries_leaves_one_pending(self, mgr):
        mgr.add_to_history("same")
        mgr.add_to_history("same")
        mgr.delete_entry(1, 1)
        assert mgr._pending_entries() == ["same"]
        mgr.save_to_file()
        assert read_file(mgr.state.history_file) == ["same"]

    def test_a_read_copy_does_not_make_a_deleted_typed_copy_pending(self, mgr):
        """A line with the same TEXT arriving from the file is not pending, so
        the count — not merely the membership — is what is preserved."""
        seed_file(mgr, "same")
        mgr.load_from_file()                       # 'same' present, not pending
        assert mgr._pending_entries() == []


class TestWritesConsumePending:
    def test_append_consumes_pending_for_the_default_file(self, mgr):
        mgr.add_to_history("one")
        assert mgr.append_history() is True
        assert mgr._pending_entries() == []

    def test_append_consumes_pending_for_a_NAMED_file_too(self, mgr):
        mgr.add_to_history("one")
        assert mgr.append_history(other_file(mgr, "o")) is True
        assert mgr._pending_entries() == []

    def test_write_to_the_default_file_consumes_pending(self, mgr):
        mgr.add_to_history("one")
        assert mgr.write_history() is True
        assert mgr._pending_entries() == []

    def test_write_to_a_NAMED_file_does_NOT_consume_pending(self, mgr):
        """P5. Advancing for any target made `history -w otherfile` drop the
        session's commands from $HISTFILE entirely — bash still saves them."""
        mgr.add_to_history("one")
        assert mgr.write_history(other_file(mgr, "o")) is True
        assert mgr._pending_entries() == ["one"]
        mgr.save_to_file()
        assert read_file(mgr.state.history_file) == ["one"]

    def test_save_consumes_pending(self, mgr):
        mgr.add_to_history("one")
        mgr.save_to_file()
        assert mgr._pending_entries() == []


class TestReadsDoNotSwallowPending:
    """R2-F2. A read used to mark the WHOLE list persisted, so typed commands
    still waiting to be saved were silently dropped."""

    def test_read_new_does_not_swallow_a_pending_typed_entry(self, mgr):
        seed_file(mgr, "a")
        mgr.load_from_file()
        mgr.add_to_history("typed one")
        seed_file(mgr, "a", "external")
        assert mgr.read_new_history() is True
        assert mgr._pending_entries() == ["typed one"]

    def test_read_does_not_swallow_a_pending_typed_entry(self, mgr):
        seed_file(mgr, "a")
        mgr.load_from_file()
        mgr.add_to_history("typed one")
        assert mgr.read_history(other_file(mgr, "o", "x")) is True
        assert mgr._pending_entries() == ["typed one"]

    def test_the_typed_entry_reaches_the_file_after_an_interleaved_read(self, mgr):
        """End to end: the swallow's user-visible consequence was the command
        never arriving in $HISTFILE at all."""
        seed_file(mgr, "a")
        mgr.load_from_file()
        mgr.add_to_history("typed one")
        seed_file(mgr, "a", "external")
        assert mgr.read_new_history() is True
        assert mgr.append_history() is True
        assert "typed one" in read_file(mgr.state.history_file)

    def test_the_read_line_is_not_duplicated_into_the_file(self, mgr):
        seed_file(mgr, "a")
        mgr.load_from_file()
        mgr.add_to_history("typed one")
        seed_file(mgr, "a", "external")
        assert mgr.read_new_history() is True
        assert mgr.append_history() is True
        assert read_file(mgr.state.history_file).count("external") == 1


class TestReadPathsRespectHistsize:
    """The exit criterion's "respect memory limits" clause: these paths used to
    extend the list with no cap at all."""

    def test_read_trims_to_histsize(self, mgr):
        mgr.state.max_history_size = 4
        big = other_file(mgr, "big", *[f"B{i}" for i in range(1, 11)])
        assert mgr.read_history(big) is True
        assert mgr.state.history == ["B7", "B8", "B9", "B10"]

    def test_read_new_trims_to_histsize(self, mgr):
        seed_file(mgr, "s1")
        mgr.load_from_file()
        mgr.state.max_history_size = 4
        seed_file(mgr, "s1", *[f"X{i}" for i in range(1, 11)])
        assert mgr.read_new_history() is True
        assert mgr.state.history == ["X7", "X8", "X9", "X10"]

    def test_store_trims_to_histsize(self, mgr):
        """MEDIUM-7 leg B: `history -s` bypassed the cap entirely."""
        mgr.state.max_history_size = 3
        for i in range(1, 6):
            mgr.store_entry(f"s{i}")
        assert mgr.state.history == ["s3", "s4", "s5"]


class TestStoreUsesTheRecordingPolicy:
    """bash applies the same filters to `history -s` as to a typed line."""

    def test_ignoredups_applies(self, mgr):
        mgr.state.set_variable("HISTCONTROL", "ignoredups")
        mgr.store_entry("dup")
        mgr.store_entry("dup")
        assert mgr.state.history == ["dup"]

    def test_erasedups_applies(self, mgr):
        mgr.state.set_variable("HISTCONTROL", "erasedups")
        for c in ("aaa", "bbb", "aaa"):
            mgr.store_entry(c)
        assert mgr.state.history == ["bbb", "aaa"]

    def test_ignorespace_applies(self, mgr):
        mgr.state.set_variable("HISTCONTROL", "ignorespace")
        mgr.store_entry(" spaced")
        assert mgr.state.history == []

    def test_histignore_matches_the_STORED_text(self, mgr):
        """Not the invocation: `HISTIGNORE='s*'` blocks `history -s s1`."""
        mgr.state.set_variable("HISTIGNORE", "s*")
        mgr.store_entry("s1")
        mgr.store_entry("kept")
        assert mgr.state.history == ["kept"]

    def test_an_embedded_newline_is_NOT_joined(self, mgr):
        """`-s` skips the cmdhist joiner: bash stores the newline verbatim,
        so this stays ONE entry rather than becoming `a; b`."""
        mgr.store_entry("a\nb")
        assert mgr.state.history == ["a\nb"]

    def test_a_typed_multiline_command_IS_joined(self, mgr):
        """Control for the cell above — the joiner is still right for typed
        input, so `-s` skipping it is a targeted exemption, not a removal."""
        mgr.add_to_history("if true\nthen true\nfi")
        assert mgr.state.history == ["if true; then true; fi"]

    def test_the_alias_contract_survives_a_store(self, mgr):
        """Every new path mutates in place; rebinding would disconnect the
        line editor's HistoryNavigator for the rest of the session."""
        hist = mgr.state.history
        mgr.state.max_history_size = 2
        for i in range(4):
            mgr.store_entry(f"s{i}")
        assert mgr.state.history is hist


class TestCompositions:
    """Fixes compose: the pairs that touch both quantities at once."""

    def test_delete_then_append_keeps_the_pending_entry(self, mgr):
        """Deleting an OLD already-saved entry must not drop a NEW one from the
        save. (bash drops it — its counter is positional; declared deviation.)"""
        seed_file(mgr, "old1", "old2")
        mgr.load_from_file()
        mgr.add_to_history("new one")
        mgr.delete_entry(1, 1)                     # delete 'old1'
        assert mgr.append_history() is True
        assert read_file(mgr.state.history_file) == ["old1", "old2", "new one"]

    def test_clear_then_read_then_record_then_save(self, mgr):
        seed_file(mgr, "a", "b")
        mgr.load_from_file()
        mgr.clear_history()
        assert mgr.read_history() is True           # re-reads a,b (not pending)
        mgr.add_to_history("after")
        mgr.save_to_file()
        assert read_file(mgr.state.history_file) == ["a", "b", "after"]

    def test_store_cap_frontdrop_then_append_writes_no_duplicates(self, mgr):
        """The exit criterion's last clause under the `-s` producer: the cap's
        front-drop must maintain pending, or the save re-emits stale entries."""
        seed_file(mgr, "old1", "old2", "old3")
        mgr.load_from_file()
        mgr.state.max_history_size = 4
        for i in range(1, 4):
            mgr.store_entry(f"n{i}")
        assert mgr.append_history() is True
        lines = read_file(mgr.state.history_file)
        assert lines == ["old1", "old2", "old3", "n1", "n2", "n3"]
        assert len(lines) == len(set(lines))        # no duplicate file lines

    def test_histsize_trim_then_read_new(self, mgr):
        seed_file(mgr, "a", "b", "c")
        mgr.load_from_file()
        mgr.state.max_history_size = 2
        mgr.add_to_history("typed")                 # trims to [c, typed]
        seed_file(mgr, "a", "b", "c", "d")
        assert mgr.read_new_history() is True
        assert mgr.state.history == ["typed", "d"]  # cursor was NOT rewound
