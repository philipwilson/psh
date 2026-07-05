"""Tests for the builtin registry's duplicate-name rejection.

The registry maps every builtin name and alias to a single instance. Two
builtins claiming the same name is a programming error (the later import
would silently shadow the earlier one). ``register`` rejects it at
registration/import time so the collision surfaces loudly instead of
hiding as a runtime shadow.
"""

import pytest

from psh.builtins.base import Builtin
from psh.builtins.registry import BuiltinRegistry, registry


class _NamedBuiltin(Builtin):
    """Minimal concrete builtin whose name/aliases are set per-subclass."""

    _NAME = "unset"
    _ALIASES: list = []

    @property
    def name(self) -> str:
        return self._NAME

    @property
    def aliases(self) -> list:
        return list(self._ALIASES)

    def execute(self, args, shell) -> int:  # pragma: no cover - never run
        return 0


def _make(name, aliases=()):
    return type(
        f"_B_{name}",
        (_NamedBuiltin,),
        {"_NAME": name, "_ALIASES": list(aliases)},
    )


def test_duplicate_primary_name_rejected():
    reg = BuiltinRegistry()
    reg.register(_make("dup"))
    with pytest.raises(ValueError, match="already registered"):
        reg.register(_make("dup"))
    # The first registration is untouched.
    assert reg.has("dup")


def test_duplicate_via_alias_rejected():
    reg = BuiltinRegistry()
    reg.register(_make("first", aliases=["shared"]))
    # A second builtin whose PRIMARY name collides with the alias is rejected.
    with pytest.raises(ValueError, match="already registered"):
        reg.register(_make("shared"))
    # ...and so is one whose ALIAS collides with an existing name.
    with pytest.raises(ValueError, match="already registered"):
        reg.register(_make("other", aliases=["first"]))


def test_distinct_names_and_aliases_register_cleanly():
    reg = BuiltinRegistry()
    reg.register(_make("a", aliases=["aa"]))
    reg.register(_make("b", aliases=["bb", "bbb"]))
    assert reg.has("a") and reg.has("aa")
    assert reg.has("b") and reg.has("bb") and reg.has("bbb")
    assert len(reg.instances()) == 2


def test_real_builtin_set_has_no_duplicate_registrations():
    """The production builtin set (loaded at import) registers cleanly:
    every name/alias is owned by exactly one instance. This is what lets
    the rejection above be added without breaking any real builtin — a
    guard that the set stays collision-free.
    """
    keys = list(registry.all().keys())
    # No key maps to more than one instance is guaranteed by the dict; the
    # meaningful invariant is that re-registering any existing builtin class
    # would now be rejected (proving none slipped through as a silent shadow).
    fresh = BuiltinRegistry()
    for instance in registry.instances():
        fresh.register(type(instance))
    assert sorted(fresh.all().keys()) == sorted(keys)
