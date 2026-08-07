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

The result is IMMUTABLE and carries no reference to a ``Variable`` cell. That
is the read/write split made structural: `lookup()` is the READ authority, and
every write goes through the mutation engine (`variable_store.py` /
`scope.py`) by identifier, where the readonly guard, nameref resolution, and
the ``variable_changed`` observer live. A read result that exposed a live cell
was a way around all three at once — see the threat model below.

Reading attributes or scope identity is NOT this type's job: ask
``get_variable_object`` / ``get_declared_variable_object``, which is where
``${x@a}`` and ``declare -p`` already go.

WHY read-only properties over private slots, and not ``frozen=True``
(slot 4B.1 ruling (a); the earlier non-frozen ruling this replaces was made on
a premise that was never measured):

1. **The premise was false.** ``lookup()`` is not on the hot read path. The
   string projection ``ScopeManager.get_variable`` shares the resolver walk and
   builds no ``VariableLookup`` at all, and ``lookup()`` has ONE production
   caller — ``expansion/operators.py#_param_is_set``, the non-colon
   ``${x+w}`` / ``${x-w}`` set-ness test. Measured construction counts on real
   workloads: variable-read-heavy 0, mixed scripting 0, nameref/export churn 0,
   shell startup 0.
2. **Immutability here costs nothing, and locking it in matters.** Properties
   over private slots reject assignment at 1.00x construction and +2.81 ns on a
   ~1380 ns ``lookup()``; ``frozen=True`` measured 1.13x end-to-end. Zero tax
   is what keeps the tri-state authority usable on the hot path, so the
   ``get_variable`` / ``lookup`` projection split is never perf-locked: if
   those projections are ever unified, this representation survives unchanged.

Both grounds are load-bearing — with (1) alone the cost would be affordable
rather than absent, and (2) is what makes the choice robust to the projections
merging. The frozen-dataclass cost this avoids is real, and the ratified
non-frozen ruling for ``FieldRun`` (W1) rests on its own hot-path measurement,
which is NOT re-opened or generalised by anything here.

THREAT MODEL (ruled, slot 4B.1 ruling (c)): the pins prove HONEST-CALLER
ACCIDENT — plain attribute assignment to a public name raises, on fresh
instances and on both shared singletons. Declared OUT OF SCOPE as deliberate
circumvention: ``object.__setattr__``, module rebinding, and direct writes to
the private ``_status`` / ``_value`` slots. That third clause is WEAKER than
the frozen-dataclass surface used for pattern nodes (slot 3.2); the
alternatives that would close it were priced and declined on measured cost.
``tests/unit/core/test_variable_lookup_immutability.py`` commits the limit as
a labelled control, so strengthening it later flips a visible cell.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Optional


class LookupStatus(Enum):
    """The three states of a variable read (see the module docstring)."""

    MISSING = auto()
    PRESENT_UNSET = auto()
    VALUE = auto()


class VariableLookup:
    """The immutable, typed result of ``ScopeManager.lookup(name)``.

    ``value`` is the string value when (and only when) ``status is VALUE``.
    There is deliberately no reference to the resolved cell (module docstring).

    Build only through :meth:`missing` / :meth:`present_unset` /
    :meth:`of_value`. ``MISSING`` and ``PRESENT_UNSET`` carry no per-instance
    data, so each is a shared frozen constant — safe to share for the same
    reason ``True`` and ``None`` are, and allocation-free. Equality is
    ``status`` + ``value``; instances are unhashable (defining ``__eq__``
    without ``__hash__``), which is preserved from the original type rather
    than newly chosen.
    """

    __slots__ = ("_status", "_value")

    def __init__(self, status: LookupStatus, value: Optional[str] = None):
        self._status = status
        self._value = value

    @property
    def status(self) -> LookupStatus:
        return self._status

    @property
    def value(self) -> Optional[str]:
        return self._value

    def __repr__(self) -> str:
        return f"VariableLookup({self._status.name}, value={self._value!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, VariableLookup):
            return NotImplemented
        return self._status is other._status and self._value == other._value

    @property
    def is_set(self) -> bool:
        """True iff the name holds a value (``${x+w}`` fires, ``${x-w}`` keeps
        the value). Both MISSING and PRESENT_UNSET are "unset" for the
        non-colon parameter operators."""
        return self._status is LookupStatus.VALUE

    @property
    def is_present(self) -> bool:
        """True iff a cell exists (VALUE or PRESENT_UNSET). A PRESENT_UNSET cell
        shadows outer instances even though it reads as unset."""
        return self._status is not LookupStatus.MISSING

    @classmethod
    def missing(cls) -> "VariableLookup":
        return _MISSING

    @classmethod
    def present_unset(cls) -> "VariableLookup":
        return _PRESENT_UNSET

    @classmethod
    def of_value(cls, value: str) -> "VariableLookup":
        return cls(LookupStatus.VALUE, value)


_MISSING = VariableLookup(LookupStatus.MISSING, None)
_PRESENT_UNSET = VariableLookup(LookupStatus.PRESENT_UNSET, None)
