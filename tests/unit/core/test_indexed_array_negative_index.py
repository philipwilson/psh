"""IndexedArray negative-subscript reads use the bash one-past-the-top rule.

Regression for reappraisal #10 R12.A: `IndexedArray.get()` resolved a negative
subscript by indexing the list of *set* indices, which disagreed with the write
path (`resolve_write_index`, which uses `highest_index + 1 + index`) and with
bash on sparse arrays. `get()` now uses the same mapping, so reads and writes
agree; an out-of-range negative read expands to empty (None) — bash treats a bad
*read* subscript as a warning + empty, only a bad *write* is a hard error.
"""

import pytest

from psh.core.exceptions import ArraySubscriptError
from psh.core.variables import IndexedArray


def _sparse():
    a = IndexedArray()
    a.set(0, "x")
    a.set(5, "y")
    return a  # _max_index == 5; slots 1..4 unset


def test_negative_one_is_highest_slot():
    assert _sparse().get(-1) == "y"  # slot 5


def test_negative_offsets_from_max_plus_one_not_set_list():
    a = _sparse()
    # -2 -> 5+1-2 = slot 4 (unset) -> empty, NOT 'x' (the old set-list rule)
    assert a.get(-2) is None
    # -6 -> 5+1-6 = slot 0 -> 'x'
    assert a.get(-6) == "x"


def test_read_matches_write_mapping_on_sparse():
    a = _sparse()
    # Writing a[-2] hits the same slot a read of a[-2] resolves to.
    a.set(-2, "W")          # slot 4
    assert a.get(-2) == "W"
    assert a.get(4) == "W"


def test_out_of_range_negative_read_is_empty_not_error():
    a = _sparse()
    # -7 -> 5+1-7 = -1 (out of range): bash warns + expands empty; we return None.
    assert a.get(-7) is None


def test_out_of_range_negative_write_raises():
    a = _sparse()
    with pytest.raises(ArraySubscriptError):
        a.set(-7, "z")


def test_unset_middle_then_negative_read():
    a = IndexedArray()
    for i, v in enumerate("pqrst"):
        a.set(i, v)          # 0..4
    a.unset(2)               # remove 'r'; _max_index stays 4
    # -3 -> 4+1-3 = slot 2 (now unset) -> empty (matches bash)
    assert a.get(-3) is None
    assert a.get(-1) == "t"
