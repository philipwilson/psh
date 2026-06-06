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
        """Create a copy of this variable."""
        return Variable(
            name=self.name,
            value=self.value,  # Note: arrays would need deep copy
            attributes=self.attributes
        )




class IndexedArray:
    """Indexed array implementation for bash-style arrays.

    Supports sparse arrays where indices don't need to be contiguous.
    """

    def __init__(self):
        self._elements: Dict[int, str] = {}
        self._max_index = -1

    def set(self, index: int, value: str):
        """Set element at given index."""
        # Negative indices not allowed for setting
        if index < 0:
            raise ValueError(f"array index must be non-negative: {index}")
        self._elements[index] = str(value)
        self._max_index = max(self._max_index, index)

    def get(self, index: int) -> Optional[str]:
        """Get element at given index. Supports negative indices."""
        if index < 0:
            # Convert negative index to positive
            # -1 means last element, -2 means second to last, etc.
            # First, get all indices in order
            indices = self.indices()
            if not indices:
                return None
            # Convert negative to positive
            if -index > len(indices):
                return None  # Out of bounds
            return self._elements.get(indices[index])
        return self._elements.get(index)

    def unset(self, index: int):
        """Remove element at given index."""
        if index in self._elements:
            del self._elements[index]
            # Recalculate max_index if needed
            if index == self._max_index:
                self._max_index = max(self._elements.keys()) if self._elements else -1

    def all_elements(self) -> List[str]:
        """Get all elements in order, skipping unset indices."""
        result = []
        for i in range(self._max_index + 1):
            if i in self._elements:
                result.append(self._elements[i])
        return result

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
