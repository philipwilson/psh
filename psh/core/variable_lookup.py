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
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .variables import Variable


class LookupStatus(Enum):
    """The three states of a variable read (see the module docstring)."""

    MISSING = auto()
    PRESENT_UNSET = auto()
    VALUE = auto()


@dataclass(frozen=True)
class VariableLookup:
    """The typed result of ``ScopeManager.lookup(name)``.

    ``value`` is the string value when (and only when) ``status is VALUE``.
    ``binding`` is the resolved ``Variable`` cell for VALUE and PRESENT_UNSET
    reads (read-only view), or ``None`` for MISSING.
    """

    status: LookupStatus
    value: Optional[str] = None
    binding: "Optional[Variable]" = None

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
