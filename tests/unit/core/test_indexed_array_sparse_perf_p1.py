"""Core-state Phase 1 (E1): sparse array enumeration is O(stored), not O(max).

``IndexedArray.all_elements()`` used to scan ``range(max_index + 1)``, so a
sparse array with a very large highest index (``a[10000000]=x``) made
``"${a[*]}"`` O(max_index) — a denial-of-service surface. It now iterates the
stored indices (O(n log n) in the number of set elements) with identical
ascending-index ordering.

The perf guard is DETERMINISTIC (an op count, not a timing threshold, so it is
xdist-safe): with a huge max index and two stored elements, ``all_elements``
must touch a number of dict slots proportional to the STORED count, never to
the max index.
"""

from psh.core.variables import IndexedArray


def test_all_elements_is_proportional_to_stored_not_max_index():
    arr = IndexedArray()
    arr.set(0, "x")
    arr.set(1_000_000, "y")  # huge gap: an O(max_index) scan does ~1e6 probes

    probes = {"contains": 0, "getitem": 0}

    class _CountingDict(dict):
        def __contains__(self, key):
            probes["contains"] += 1
            return dict.__contains__(self, key)

        def __getitem__(self, key):
            probes["getitem"] += 1
            return dict.__getitem__(self, key)

    arr._elements = _CountingDict(arr._elements)

    result = arr.all_elements()

    assert result == ["x", "y"], "ascending-index order must be preserved"
    # O(stored): the work must not be driven by the max index (1e6). A
    # range(max+1) scan would do ~1e6 __contains__ probes.
    assert probes["contains"] + probes["getitem"] < 100, (
        f"all_elements did {probes} dict ops for 2 stored elements — an "
        "O(max_index) regression (should be O(stored))")


class TestSparseEnumerationSemantics:
    """Ordering/content must stay identical to the old max-index scan."""

    def test_sparse_ascending_order(self):
        arr = IndexedArray()
        for i, v in [(10, "ten"), (2, "two"), (100, "hundred"), (2, "two2")]:
            arr.set(i, v)
        assert arr.all_elements() == ["two2", "ten", "hundred"]

    def test_empty_array(self):
        assert IndexedArray().all_elements() == []

    def test_matches_indices_order(self):
        arr = IndexedArray()
        for i in (5, 1, 9, 3):
            arr.set(i, f"v{i}")
        # all_elements order corresponds to indices() order.
        assert arr.all_elements() == [arr.get(i) for i in arr.indices()]

    def test_after_unset_recomputes(self):
        arr = IndexedArray()
        arr.set(0, "a")
        arr.set(5, "b")
        arr.set(10, "c")
        arr.unset(5)
        assert arr.all_elements() == ["a", "c"]
