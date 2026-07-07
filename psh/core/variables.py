"""Enhanced variable system with attributes for PSH shell.

This module provides the foundation for advanced variable features including
arrays, associative arrays, readonly variables, and other attributes.
"""

from dataclasses import dataclass
from enum import Flag, auto
from typing import Any, Dict, List, Optional


class VarAttributes(Flag):
    """Variable attributes that can be combined."""
    NONE = 0
    READONLY = auto()    # -r: Variable cannot be modified
    EXPORT = auto()      # -x: Variable is exported to environment
    INTEGER = auto()     # -i: Variable holds integer values
    LOWERCASE = auto()   # -l: Convert value to lowercase
    UPPERCASE = auto()   # -u: Convert value to uppercase
    ARRAY = auto()       # -a: Indexed array
    ASSOC_ARRAY = auto() # -A: Associative array
    NAMEREF = auto()     # -n: Name reference (indirect)
    TRACE = auto()       # -t: Function tracing enabled
    UNSET = auto()       # Variable explicitly unset in this scope


@dataclass
class Variable:
    """Enhanced variable with attributes and value.

    Attributes:
        name: Variable name
        value: Variable value (can be str, IndexedArray, AssociativeArray, or int)
        attributes: Combination of VarAttributes flags
    """
    name: str
    value: Any  # Can be str, list, dict, int, IndexedArray, AssociativeArray
    attributes: VarAttributes = VarAttributes.NONE

    @property
    def is_array(self) -> bool:
        """Check if variable is any type of array."""
        return bool(self.attributes & (VarAttributes.ARRAY | VarAttributes.ASSOC_ARRAY))

    @property
    def is_indexed_array(self) -> bool:
        """Check if variable is an indexed array."""
        return bool(self.attributes & VarAttributes.ARRAY)

    @property
    def is_assoc_array(self) -> bool:
        """Check if variable is an associative array."""
        return bool(self.attributes & VarAttributes.ASSOC_ARRAY)

    @property
    def is_readonly(self) -> bool:
        """Check if variable is readonly."""
        return bool(self.attributes & VarAttributes.READONLY)

    @property
    def is_exported(self) -> bool:
        """Check if variable is exported to environment."""
        return bool(self.attributes & VarAttributes.EXPORT)

    @property
    def is_integer(self) -> bool:
        """Check if variable has integer attribute."""
        return bool(self.attributes & VarAttributes.INTEGER)

    @property
    def is_lowercase(self) -> bool:
        """Check if variable converts to lowercase."""
        return bool(self.attributes & VarAttributes.LOWERCASE)

    @property
    def is_uppercase(self) -> bool:
        """Check if variable converts to uppercase."""
        return bool(self.attributes & VarAttributes.UPPERCASE)

    @property
    def is_unset(self) -> bool:
        """Check if variable is explicitly unset in current scope."""
        return bool(self.attributes & VarAttributes.UNSET)

    @property
    def is_nameref(self) -> bool:
        """Check if variable is a name reference."""
        return bool(self.attributes & VarAttributes.NAMEREF)

    @property
    def is_trace(self) -> bool:
        """Check if function has trace attribute."""
        return bool(self.attributes & VarAttributes.TRACE)

    def as_string(self) -> str:
        """Convert value to string representation."""
        if isinstance(self.value, str):
            return self.value
        elif isinstance(self.value, (int, float)):
            return str(self.value)
        elif hasattr(self.value, 'as_string'):
            # For array types that implement as_string
            return self.value.as_string()
        else:
            return str(self.value)

    def copy(self) -> 'Variable':
        """Create an independent copy of this variable.

        Array values are DEEP-copied (via IndexedArray/AssociativeArray.copy)
        so a child shell mutating an element cannot reach back into the
        parent's array — the copy the child boundary requires. Scalar values
        (str/int) are immutable and shared safely. ``attributes`` is an
        immutable ``Flag``.
        """
        value = self.value
        if isinstance(value, (IndexedArray, AssociativeArray)):
            value = value.copy()
        return Variable(
            name=self.name,
            value=value,
            attributes=self.attributes
        )




class IndexedArray:
    """Indexed array implementation for bash-style arrays.

    Supports sparse arrays where indices don't need to be contiguous.
    """

    def __init__(self):
        self._elements: Dict[int, str] = {}
        self._max_index = -1

    def resolve_write_index(self, index: int) -> int:
        """Map a (possibly negative) subscript to a concrete write index.

        bash semantics: a negative subscript ``-N`` on an indexed array
        refers to ``(highest_index + 1) - N`` — i.e. ``-1`` is the last
        slot, ``-2`` the one before it. ``highest_index`` is the largest
        currently-set index (``_max_index``), so this is sparse-aware and
        matches bash's "offset from one past the top" rule (verified:
        ``a[5]=F; a[-1]`` → index 5, ``a[-6]`` → index 0). On an empty
        array ``_max_index`` is -1, so ``a[-1]`` resolves to -1 (out of
        range). A non-negative subscript is returned unchanged.

        Raises ArraySubscriptError when the mapped index is still < 0
        (bash: "bad array subscript").
        """
        if index >= 0:
            return index
        mapped = self._max_index + 1 + index
        if mapped < 0:
            from .exceptions import ArraySubscriptError
            raise ArraySubscriptError(index)
        return mapped

    def set(self, index: int, value: str):
        """Set element at given index.

        Negative indices are mapped bash-style (``-1`` = last element); see
        ``resolve_write_index``. An out-of-range negative index raises
        ``ArraySubscriptError``.
        """
        index = self.resolve_write_index(index)
        self._elements[index] = str(value)
        self._max_index = max(self._max_index, index)

    def get(self, index: int) -> Optional[str]:
        """Get element at given index, supporting negative subscripts.

        A negative subscript uses the SAME bash "offset from one past the top"
        mapping as a write (``-1`` is the highest set index's slot, ``-2`` the
        one before it, ...), so reads and writes agree on sparse arrays — the
        old read counted over the list of *set* indices instead, which diverged
        from both the write path and bash. A mapped slot that is unset reads as
        None (empty), like any unset slot.

        Unlike a write, an out-of-range negative read does NOT raise: bash
        treats a bad *read* subscript as a warning and expands to empty (only a
        bad *write* subscript is a hard error), so we return None here.
        """
        if index < 0:
            mapped = self._max_index + 1 + index
            if mapped < 0:
                return None  # out of range: bash warns + expands empty
            index = mapped
        return self._elements.get(index)

    def negative_out_of_range(self, index: int) -> bool:
        """True if ``index`` is a negative subscript that maps below slot 0.

        bash treats such a READ as a "bad array subscript" warning (it still
        expands to empty); callers that want to emit the diagnostic check this
        before ``get`` (which silently returns None for it). Mirrors the
        out-of-range condition in ``resolve_write_index``/``get``.
        """
        return index < 0 and (self._max_index + 1 + index) < 0

    def unset(self, index: int):
        """Remove element at given index."""
        if index in self._elements:
            del self._elements[index]
            # Recalculate max_index if needed
            if index == self._max_index:
                self._max_index = max(self._elements.keys()) if self._elements else -1

    def copy(self) -> 'IndexedArray':
        """Independent deep copy (elements dict + max index)."""
        new = IndexedArray()
        new._elements = dict(self._elements)
        new._max_index = self._max_index
        return new

    def all_elements(self) -> List[str]:
        """Get all elements in ascending index order.

        Iterates the STORED indices (O(n log n) in the number of set
        elements), not ``range(max_index + 1)`` — a sparse array can select a
        very large highest index (``a[10000000]=x``), so the old
        max-index scan was O(max_index) and a denial-of-service surface on
        ``"${a[*]}"``. ``_elements`` holds only set indices, so sorting them
        yields the same ascending sequence the scan produced.
        """
        return [self._elements[i] for i in sorted(self._elements)]

    def indices(self) -> List[int]:
        """Get all defined indices in sorted order."""
        return sorted(self._elements.keys())

    def next_index(self) -> int:
        """Index one past the highest set index (0 for an empty array).

        This is where bash appends with ``arr+=(x)`` / ``arr[next]=x``.
        """
        return self._max_index + 1

    def __contains__(self, index: int) -> bool:
        """True if *index* has a value set (supports ``index in arr``)."""
        return index in self._elements

    def length(self) -> int:
        """Number of elements in the array."""
        return len(self._elements)

    def clear(self):
        """Remove all elements."""
        self._elements.clear()
        self._max_index = -1

    def as_string(self) -> str:
        """String representation (first element or empty)."""
        return self._elements.get(0, "")

    def __repr__(self):
        return f"IndexedArray({self._elements})"


class AssociativeArray:
    """Associative array (hash/dictionary) implementation.

    Provides bash-compatible associative array functionality.
    """

    def __init__(self):
        self._elements: Dict[str, str] = {}

    def set(self, key: str, value: str):
        """Set element with given key."""
        self._elements[str(key)] = str(value)

    def get(self, key: str) -> Optional[str]:
        """Get element with given key."""
        return self._elements.get(str(key))

    def unset(self, key: str):
        """Remove element with given key."""
        key = str(key)
        if key in self._elements:
            del self._elements[key]

    def copy(self) -> 'AssociativeArray':
        """Independent deep copy (preserves insertion order)."""
        new = AssociativeArray()
        new._elements = dict(self._elements)
        return new

    def all_elements(self) -> List[str]:
        """Get all values in insertion order for bash compatibility."""
        # Return values in insertion order (Python 3.7+ dict behavior matches bash)
        return list(self._elements.values())

    def keys(self) -> List[str]:
        """Get all keys in insertion order for bash compatibility."""
        # Return keys in insertion order (Python 3.7+ dict behavior matches bash)
        return list(self._elements.keys())

    def items(self) -> List[tuple[str, str]]:
        """Get all key-value pairs in insertion order for bash compatibility."""
        # Return items in insertion order (Python 3.7+ dict behavior matches bash)
        return list(self._elements.items())

    def __contains__(self, key: str) -> bool:
        """True if *key* is set (supports ``key in arr``)."""
        return str(key) in self._elements

    def length(self) -> int:
        """Number of elements in the array."""
        return len(self._elements)

    def clear(self):
        """Remove all elements."""
        self._elements.clear()

    def as_string(self) -> str:
        """String representation (empty for associative arrays)."""
        # Bash doesn't allow ${assoc} without subscript
        return ""

    def __repr__(self):
        return f"AssociativeArray({self._elements})"
