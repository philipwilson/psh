"""The tri-state variable-read result — the ONE truth of "is this set?".

`ScopeManager.lookup()` returns a `VariableLookup`, which distinguishes the
three states a shell name can be in when it is read:

- ``MISSING``       — no cell exists anywhere in the scope chain (and the name
                      is not a currently-active computed special).
- ``PRESENT_UNSET`` — a cell EXISTS but is declared-unset: a tombstone from
                      ``local x; unset x``, a bare ``local x`` / ``declare x``,
                      or a declared-but-unset export (``export FOO`` before an
                      assignment). It reads as unset but stops the lookup — it
                      does NOT fall through to an outer instance or to the
                      environment (appraisal #20 H13).
- ``VALUE``         — a cell (or active special) holds a value.

Before this type, "no cell" and "cell declared but valueless" both collapsed to
``None``, and ``ShellState.get_variable`` papered over the difference by falling
back to ``self.env`` — so a declared-unset LOCAL shadowing an exported outer
resurrected the exported value (``export FOO=outer; f(){ local FOO; echo
"${FOO-u}"; }`` printed ``outer`` instead of bash's ``u``). The tri-state is the
representation that makes the env fallback unnecessary and wrong.

The ``binding`` half exposes the resolved ``Variable`` cell so consumers that
need attributes / scope identity (``${x@a}``, ``declare -p``) can read them
WITHOUT a second lookup. It is a READ view: lookups never mutate; every write
goes through the mutation engine (`variable_store.py` / `scope.py`).

``VariableLookup`` is a plain ``__slots__`` class rather than a frozen
dataclass: ``lookup()`` sits on the shell's hottest read path and freezing
roughly triples construction cost (``object.__setattr__`` per field — the same
measurement that drove W1's non-frozen ``FieldRun`` ruling). The discipline is
ALLOCATE-FRESH-NEVER-MUTATE: every instance is built by one of the three
factories below and never written after construction. ``__slots__`` keeps
instances closed (no ``__dict__`` to grow ad-hoc state on), guarded by the
slots test in ``tests/unit/core/test_variable_lookup.py``.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .variables import Variable


class LookupStatus(Enum):
    """The three states of a variable read (see the module docstring)."""

    MISSING = auto()
    PRESENT_UNSET = auto()
    VALUE = auto()


class VariableLookup:
    """The typed result of ``ScopeManager.lookup(name)``.

    ``value`` is the string value when (and only when) ``status is VALUE``.
    ``binding`` is the resolved ``Variable`` cell for VALUE and PRESENT_UNSET
    reads (read-only view), or ``None`` for MISSING.

    Instances are allocate-fresh-never-mutate (module docstring); build them
    only through :meth:`missing` / :meth:`present_unset` / :meth:`of_value`.
    """

    __slots__ = ("status", "value", "binding")

    def __init__(self, status: LookupStatus, value: Optional[str] = None,
                 binding: "Optional[Variable]" = None):
        self.status = status
        self.value = value
        self.binding = binding

    def __repr__(self) -> str:
        return (f"VariableLookup({self.status.name}, value={self.value!r}, "
                f"binding={self.binding!r})")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, VariableLookup):
            return NotImplemented
        return (self.status is other.status and self.value == other.value
                and self.binding == other.binding)

    @property
    def is_set(self) -> bool:
        """True iff the name holds a value (``${x+w}`` fires, ``${x-w}`` keeps
        the value). Both MISSING and PRESENT_UNSET are "unset" for the
        non-colon parameter operators."""
        return self.status is LookupStatus.VALUE

    @property
    def is_present(self) -> bool:
        """True iff a cell exists (VALUE or PRESENT_UNSET). A PRESENT_UNSET cell
        shadows outer instances even though it reads as unset."""
        return self.status is not LookupStatus.MISSING

    @classmethod
    def missing(cls) -> "VariableLookup":
        return _MISSING

    @classmethod
    def present_unset(cls, binding: "Optional[Variable]" = None) -> "VariableLookup":
        return cls(LookupStatus.PRESENT_UNSET, None, binding)

    @classmethod
    def of_value(cls, value: str, binding: "Optional[Variable]" = None) -> "VariableLookup":
        return cls(LookupStatus.VALUE, value, binding)


_MISSING = VariableLookup(LookupStatus.MISSING, None, None)
