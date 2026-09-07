"""The readonly attribute lock, tested on its owner (G17 / FLIP-PINS slot 2.4).

``ScopeManager.check_readonly_attribute_change`` is the single home of the
bash 5.3 rule that a READONLY variable refuses any attribute change that would
alter what a later assignment does (bash 5.3.15 CHANGES line 705, 5.3-alpha
item llllll: "Fixed a bug that allowed attribute changes to readonly variables
that changed the effects of attempted assignments").  ``apply_attribute``,
``remove_attribute``, ``create_local`` and ``declare``'s bare-name ``-a``/``-A``
branch all route through it.  Behavioral parity, per spelling and in all three
input modes, is pinned in
tests/conformance/bash/test_export_env_sync_conformance.py::TestReadonlyAttributeRefusal;
these lock the engine-level policy directly, including the states a shell-level
probe cannot address (a nameref cell that is itself readonly).

Repro: ``readonly R=1; declare -i R; echo rc=$?; declare -p R``.
"""

import pytest

from psh.core.exceptions import ReadonlyVariableError
from psh.core.scope import READONLY_LOCKED_ATTRIBUTES, ScopeManager
from psh.core.variables import VarAttributes

LOCKED = [
    VarAttributes.INTEGER,
    VarAttributes.LOWERCASE,
    VarAttributes.UPPERCASE,
    VarAttributes.ARRAY,
    VarAttributes.ASSOC_ARRAY,
    VarAttributes.NAMEREF,
]
ALLOWED = [
    VarAttributes.EXPORT,
    VarAttributes.TRACE,
    VarAttributes.READONLY,
]


def _readonly_scalar(value="1", attributes=VarAttributes.NONE):
    mgr = ScopeManager()
    mgr.set_variable("R", value, attributes=attributes | VarAttributes.READONLY)
    return mgr


class TestRefusedHalf:
    """Every locked attribute refuses, in both directions."""

    @pytest.mark.parametrize("attr", LOCKED, ids=lambda a: a.name)
    def test_adding_a_locked_attribute_raises(self, attr):
        mgr = _readonly_scalar()
        with pytest.raises(ReadonlyVariableError):
            mgr.apply_attribute("R", attr)
        assert not (mgr.get_variable_object("R").attributes & attr)

    @pytest.mark.parametrize("attr", LOCKED, ids=lambda a: a.name)
    def test_removing_a_locked_attribute_raises(self, attr):
        # NAMEREF is the one carve-out on removal and has its own rows below.
        if attr is VarAttributes.NAMEREF:
            pytest.skip("+n on a non-nameref is dropped by bash; see below")
        mgr = _readonly_scalar(attributes=attr)
        with pytest.raises(ReadonlyVariableError):
            mgr.remove_attribute("R", attr)
        assert mgr.get_variable_object("R").attributes & attr

    def test_no_op_add_still_raises(self):
        """The rule is keyed on the REQUESTED attribute, not on a delta."""
        mgr = _readonly_scalar(attributes=VarAttributes.INTEGER)
        with pytest.raises(ReadonlyVariableError):
            mgr.apply_attribute("R", VarAttributes.INTEGER)

    def test_a_locked_attribute_poisons_the_whole_request(self):
        """`declare -xi R`: the allowed EXPORT does not land either."""
        mgr = _readonly_scalar()
        with pytest.raises(ReadonlyVariableError):
            mgr.apply_attribute(
                "R", VarAttributes.EXPORT | VarAttributes.INTEGER)
        assert not mgr.get_variable_object("R").is_exported

    def test_error_names_the_variable(self):
        mgr = _readonly_scalar()
        with pytest.raises(ReadonlyVariableError) as exc:
            mgr.apply_attribute("R", VarAttributes.INTEGER)
        assert exc.value.name == "R"

    def test_locked_set_is_exactly_the_assignment_affecting_attributes(self):
        assert READONLY_LOCKED_ATTRIBUTES == (
            VarAttributes.INTEGER | VarAttributes.LOWERCASE
            | VarAttributes.UPPERCASE | VarAttributes.ARRAY
            | VarAttributes.ASSOC_ARRAY | VarAttributes.NAMEREF)


class TestAllowedHalf:
    """EXPORT / TRACE / READONLY still apply to a readonly variable."""

    @pytest.mark.parametrize("attr", ALLOWED, ids=lambda a: a.name)
    def test_adding_an_allowed_attribute_lands(self, attr):
        mgr = _readonly_scalar()
        mgr.apply_attribute("R", attr)
        assert mgr.get_variable_object("R").attributes & attr

    @pytest.mark.parametrize("attr", [VarAttributes.EXPORT, VarAttributes.TRACE],
                             ids=lambda a: a.name)
    def test_removing_an_allowed_attribute_lands(self, attr):
        mgr = _readonly_scalar(attributes=attr)
        mgr.remove_attribute("R", attr)
        assert not (mgr.get_variable_object("R").attributes & attr)

    def test_removing_readonly_itself_still_refuses(self):
        """A different, older rule: readonly cannot be cleared at all."""
        mgr = _readonly_scalar()
        with pytest.raises(ReadonlyVariableError):
            mgr.remove_attribute("R", VarAttributes.READONLY)

    def test_writable_variable_accepts_every_locked_attribute(self):
        mgr = ScopeManager()
        mgr.set_variable("W", "1")
        for attr in LOCKED:
            mgr.apply_attribute("W", attr)
        assert mgr.get_variable_object("W").attributes & VarAttributes.INTEGER


class TestNamerefRemovalCarveOut:
    """bash drops a ``+n`` that has no nameref to remove, so a plain readonly
    accepts it; a readonly NAMEREF cell does not."""

    def test_plus_n_on_a_readonly_non_nameref_is_allowed(self):
        mgr = _readonly_scalar()
        mgr.remove_attribute("R", VarAttributes.NAMEREF)
        assert mgr.get_variable_object("R").is_readonly

    def test_plus_n_alongside_a_locked_attribute_still_refuses(self):
        mgr = _readonly_scalar()
        with pytest.raises(ReadonlyVariableError):
            mgr.remove_attribute(
                "R", VarAttributes.NAMEREF | VarAttributes.INTEGER)

    def test_plus_n_on_a_readonly_nameref_refuses(self):
        mgr = ScopeManager()
        mgr.set_variable("T", "1")
        mgr.set_variable("r", "T", attributes=(VarAttributes.NAMEREF
                                               | VarAttributes.READONLY))
        with pytest.raises(ReadonlyVariableError):
            mgr.remove_attribute("r", VarAttributes.NAMEREF)
        assert mgr.get_variable_object("r").is_nameref


class TestNamerefResolvedTarget:
    """Non-nameref attribute changes follow the reference, so the READONLY of
    the TARGET decides — and the error names the target."""

    def test_locked_change_through_a_nameref_refuses_and_names_the_target(self):
        mgr = ScopeManager()
        mgr.set_variable("R", "1", attributes=VarAttributes.READONLY)
        mgr.set_variable("a", "R", attributes=VarAttributes.NAMEREF)
        mgr.set_variable("b", "a", attributes=VarAttributes.NAMEREF)
        with pytest.raises(ReadonlyVariableError) as exc:
            mgr.apply_attribute("b", VarAttributes.INTEGER)
        assert exc.value.name == "R"

    def test_readonly_nameref_to_a_writable_target_allows_the_change(self):
        """The readonly is on the nameref cell, not on what it points at."""
        mgr = ScopeManager()
        mgr.set_variable("T", "1")
        mgr.set_variable("r", "T", attributes=(VarAttributes.NAMEREF
                                               | VarAttributes.READONLY))
        mgr.apply_attribute("r", VarAttributes.INTEGER)
        assert mgr.get_variable_object("T").is_integer


class TestLocalScope:
    """``create_local`` routes through the same owner, so ``local -i`` on a
    readonly local refuses while ``local -x`` still merges."""

    def _in_function(self):
        mgr = ScopeManager()
        mgr.push_scope("f")
        return mgr

    def test_locked_attribute_on_a_readonly_local_refuses(self):
        mgr = self._in_function()
        mgr.create_local("x", "1", VarAttributes.READONLY)
        with pytest.raises(ReadonlyVariableError):
            mgr.create_local("x", None, VarAttributes.INTEGER)
        var = mgr.get_variable_object("x")
        assert var.is_readonly and not var.is_integer and var.value == "1"

    def test_allowed_attribute_on_a_readonly_local_merges(self):
        mgr = self._in_function()
        mgr.create_local("x", "1", VarAttributes.READONLY)
        mgr.create_local("x", None, VarAttributes.EXPORT)
        var = mgr.get_variable_object("x")
        assert var.is_readonly and var.is_exported

    def test_locked_attribute_on_a_readonly_global_refuses_from_a_function(self):
        mgr = ScopeManager()
        mgr.set_variable("R", "1", attributes=VarAttributes.READONLY)
        mgr.push_scope("f")
        with pytest.raises(ReadonlyVariableError):
            mgr.apply_attribute("R", VarAttributes.INTEGER)

    def test_writable_local_still_takes_a_locked_attribute(self):
        mgr = self._in_function()
        mgr.create_local("x", "1")
        mgr.create_local("x", None, VarAttributes.INTEGER)
        assert mgr.get_variable_object("x").is_integer
