"""M8 mutation-injection pytest plugin for slot 4B.1.

Selected by the env var ``M8_MUTATION``. At ``pytest_configure`` — BEFORE the
test module is imported, so its module-level ``from ... import VariableLookup``
picks up the mutant — this swaps the class into both modules that hold a
reference (``psh.core.variable_lookup`` and ``psh.core.scope``), the same
injection seam the Phase A benchmarks used.

Each mutation re-introduces exactly ONE defect class, so the pin suite's
response discriminates: a lock that turns the whole suite red proves nothing
about which pin catches what.
"""
from __future__ import annotations

import os

from psh.core.variable_lookup import LookupStatus


def _base_body(ns):
    ns["is_set"] = property(lambda self: self.status is LookupStatus.VALUE)
    ns["is_present"] = property(
        lambda self: self.status is not LookupStatus.MISSING)
    return ns


def m8_1_writable_fields():
    """Fields back to plain writable slots (the original MEDIUM-5 shape)."""
    class Mutant:
        __slots__ = ("status", "value")

        def __init__(self, status, value=None):
            self.status = status
            self.value = value

        def __repr__(self):
            return f"VariableLookup({self.status.name}, value={self.value!r})"

        def __eq__(self, other):
            if not isinstance(other, Mutant):
                return NotImplemented
            return self.status is other.status and self.value == other.value

        @property
        def is_set(self):
            return self.status is LookupStatus.VALUE

        @property
        def is_present(self):
            return self.status is not LookupStatus.MISSING

        @classmethod
        def missing(cls):
            return _M

        @classmethod
        def present_unset(cls):
            return _PU

        @classmethod
        def of_value(cls, value):
            return cls(LookupStatus.VALUE, value)

    _M = Mutant(LookupStatus.MISSING, None)
    _PU = Mutant(LookupStatus.PRESENT_UNSET, None)
    return Mutant


def _immutable_base():
    """The shipped shape, as a fresh class the other mutations specialise."""
    class Mutant:
        __slots__ = ("_status", "_value")

        def __init__(self, status, value=None):
            self._status = status
            self._value = value

        status = property(lambda self: self._status)
        value = property(lambda self: self._value)

        def __repr__(self):
            return f"VariableLookup({self._status.name}, value={self._value!r})"

        def __eq__(self, other):
            if not isinstance(other, Mutant):
                return NotImplemented
            return self._status is other._status and self._value == other._value

        @property
        def is_set(self):
            return self._status is LookupStatus.VALUE

        @property
        def is_present(self):
            return self._status is not LookupStatus.MISSING

        @classmethod
        def of_value(cls, value):
            return cls(LookupStatus.VALUE, value)

    return Mutant


def m8_2_present_unset_allocates():
    """PRESENT_UNSET stops being a shared constant."""
    Mutant = _immutable_base()
    _M = Mutant(LookupStatus.MISSING, None)
    Mutant.missing = classmethod(lambda cls: _M)
    Mutant.present_unset = classmethod(
        lambda cls: cls(LookupStatus.PRESENT_UNSET, None))
    return Mutant


def m8_3_binding_restored():
    """The live-cell leak restored: `.binding` is back AND `lookup()` fills it.

    Both halves are needed for a faithful re-introduction — a `binding` that
    is always None would flip the surface pins without restoring the defect.
    """
    class Mutant:
        __slots__ = ("_status", "_value", "_binding")

        def __init__(self, status, value=None, binding=None):
            self._status = status
            self._value = value
            self._binding = binding

        status = property(lambda self: self._status)
        value = property(lambda self: self._value)
        binding = property(lambda self: self._binding)

        def __repr__(self):
            return f"VariableLookup({self._status.name}, value={self._value!r})"

        def __eq__(self, other):
            if not isinstance(other, Mutant):
                return NotImplemented
            return self._status is other._status and self._value == other._value

        @property
        def is_set(self):
            return self._status is LookupStatus.VALUE

        @property
        def is_present(self):
            return self._status is not LookupStatus.MISSING

        @classmethod
        def missing(cls):
            return _M

        @classmethod
        def present_unset(cls, binding=None):
            return cls(LookupStatus.PRESENT_UNSET, None, binding)

        @classmethod
        def of_value(cls, value, binding=None):
            return cls(LookupStatus.VALUE, value, binding)

    _M = Mutant(LookupStatus.MISSING, None, None)
    return Mutant


def m8_4_missing_allocates():
    """MISSING stops being shared (fresh instance per miss)."""
    Mutant = _immutable_base()
    _PU = Mutant(LookupStatus.PRESENT_UNSET, None)
    Mutant.missing = classmethod(lambda cls: cls(LookupStatus.MISSING, None))
    Mutant.present_unset = classmethod(lambda cls: _PU)
    return Mutant


def m8_5_identity_equality():
    """__eq__ reverts to identity comparison."""
    Mutant = _immutable_base()
    _M = Mutant(LookupStatus.MISSING, None)
    _PU = Mutant(LookupStatus.PRESENT_UNSET, None)
    Mutant.missing = classmethod(lambda cls: _M)
    Mutant.present_unset = classmethod(lambda cls: _PU)
    Mutant.__eq__ = lambda self, other: self is other
    return Mutant


MUTATIONS = {
    "M8-1": ("fields writable again", m8_1_writable_fields),
    "M8-2": ("present_unset allocates", m8_2_present_unset_allocates),
    "M8-3": ("binding restored (live cell leak)", m8_3_binding_restored),
    "M8-4": ("missing allocates per miss", m8_4_missing_allocates),
    "M8-5": ("__eq__ reverts to identity", m8_5_identity_equality),
}


def pytest_configure(config):
    key = os.environ.get("M8_MUTATION")
    if not key or key == "NONE":
        return
    if key not in MUTATIONS:
        raise SystemExit(f"unknown M8_MUTATION {key!r}")
    _label, factory = MUTATIONS[key]
    mutant = factory()

    from psh.core import scope as scope_mod
    from psh.core import variable_lookup as vl_mod

    vl_mod.VariableLookup = mutant
    scope_mod.VariableLookup = mutant

    if key == "M8-3":
        # Restore the OLD lookup() so the leaked binding is a real live cell.
        def legacy_lookup(self, name):
            var, final_name = self._resolve_read(name)
            if var is not None:
                return mutant.of_value(var.as_string(), var)
            declared = self.get_declared_variable_object(final_name)
            if declared is not None and declared.is_unset:
                return mutant.present_unset(declared)
            return mutant.missing()

        scope_mod.ScopeManager.lookup = legacy_lookup
