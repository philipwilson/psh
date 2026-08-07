"""The tri-state variable-read authority — ScopeManager.lookup() (#20 H13).

`lookup()` returns a `VariableLookup(MISSING | PRESENT_UNSET | VALUE, binding)`.
Before it, "no cell" and "cell declared but valueless" both collapsed to None,
and ShellState.get_variable papered over the difference with an env fallback that
resurrected an outer exported value under a declared-unset local. These pins lock
the three states and the no-fallback contract. The result carries no cell
reference (slot 4B.1): cell-level facts are asserted here through the write
engine's own surface, `get_variable_object` / `get_declared_variable_object`,
and the result's immutability is pinned in
`test_variable_lookup_immutability.py`.

Probed against bash 5.2 (tmp/boundary-ledgers/R2-probes/matrix_base_9230699b.txt,
family A/C); the behavioral half is pinned in
tests/conformance/bash/test_variable_truth_conformance.py.
"""

from psh.core.scope import ScopeManager
from psh.core.variable_lookup import LookupStatus, VariableLookup
from psh.core.variables import VarAttributes


class TestTriStateStatus:
    def test_value_of_a_plain_variable(self):
        mgr = ScopeManager()
        mgr.set_variable('X', 'v')
        r = mgr.lookup('X')
        assert r.status is LookupStatus.VALUE
        assert r.is_set is True
        assert r.value == 'v'
        assert r.is_present is True
        assert mgr.get_variable_object('X').name == 'X'

    def test_missing_name_is_missing_not_present(self):
        mgr = ScopeManager()
        r = mgr.lookup('NOPE')
        assert r.status is LookupStatus.MISSING
        assert r.is_set is False
        assert r.is_present is False
        assert r.value is None
        assert mgr.get_declared_variable_object('NOPE') is None

    def test_declared_unset_local_is_present_unset(self):
        """`local x` (no value) — a declared-unset cell, reads unset, shadows."""
        mgr = ScopeManager()
        mgr.push_scope('f')
        mgr.create_local('x')  # bare `local x`
        r = mgr.lookup('x')
        assert r.status is LookupStatus.PRESENT_UNSET
        assert r.is_set is False
        assert r.is_present is True
        assert r.value is None
        assert mgr.get_declared_variable_object('x').is_unset
        mgr.pop_scope()

    def test_tombstone_local_unset_is_present_unset(self):
        """`local x=1; unset x` plants a tombstone: PRESENT_UNSET, not MISSING."""
        mgr = ScopeManager()
        mgr.push_scope('f')
        mgr.create_local('x', '1')
        mgr.unset_variable('x')
        r = mgr.lookup('x')
        assert r.status is LookupStatus.PRESENT_UNSET
        mgr.pop_scope()

    def test_empty_string_value_is_value_not_unset(self):
        mgr = ScopeManager()
        mgr.set_variable('X', '')
        r = mgr.lookup('X')
        assert r.status is LookupStatus.VALUE
        assert r.value == ''


class TestNoEnvironmentResurrection:
    """H13: a declared-unset local shadowing an exported outer must NOT read the
    exported value back through the environment."""

    def test_declared_unset_local_shadows_exported_global(self):
        mgr = ScopeManager()
        mgr.set_variable('FOO', 'outer', attributes=VarAttributes.EXPORT)
        mgr.push_scope('f')
        mgr.create_local('FOO')  # `local FOO` shadows the exported outer
        r = mgr.lookup('FOO')
        assert r.status is LookupStatus.PRESENT_UNSET
        assert r.value is None
        mgr.pop_scope()
        # After the function returns the outer value is visible again.
        assert mgr.lookup('FOO').status is LookupStatus.VALUE
        assert mgr.lookup('FOO').value == 'outer'

    def test_unset_local_then_lookup_stops_at_tombstone(self):
        mgr = ScopeManager()
        mgr.set_variable('FOO', 'outer', attributes=VarAttributes.EXPORT)
        mgr.push_scope('f')
        mgr.create_local('FOO', 'inner')
        mgr.unset_variable('FOO')
        assert mgr.lookup('FOO').status is LookupStatus.PRESENT_UNSET
        mgr.pop_scope()


class TestNamerefLookup:
    def test_lookup_follows_nameref_to_value(self):
        mgr = ScopeManager()
        mgr.set_variable('target', 'hi')
        mgr.set_variable('r', 'target', attributes=VarAttributes.NAMEREF)
        r = mgr.lookup('r')
        assert r.status is LookupStatus.VALUE
        assert r.value == 'hi'

    def test_lookup_nameref_to_unset_is_unset(self):
        mgr = ScopeManager()
        mgr.set_variable('r', 'target', attributes=VarAttributes.NAMEREF)
        # target does not exist
        assert mgr.lookup('r').is_set is False


class TestGetVariableProjection:
    """ScopeManager.get_variable is the string projection of lookup()."""

    def test_get_variable_returns_value(self):
        mgr = ScopeManager()
        mgr.set_variable('X', 'v')
        assert mgr.get_variable('X') == 'v'

    def test_get_variable_default_for_missing(self):
        mgr = ScopeManager()
        assert mgr.get_variable('NOPE', 'D') == 'D'

    def test_get_variable_default_for_declared_unset(self):
        mgr = ScopeManager()
        mgr.push_scope('f')
        mgr.create_local('x')
        assert mgr.get_variable('x', 'D') == 'D'
        mgr.pop_scope()


class TestVariableLookupType:
    def test_representation_is_closed_and_read_only(self):
        """The three properties the representation guarantees (slot 4B.1):
        state lives in PRIVATE slots, the public names reject assignment, and
        instances stay CLOSED — no __dict__ to grow ad-hoc state on. The full
        mutation-surface matrix is in test_variable_lookup_immutability.py."""
        r = VariableLookup.of_value('v')
        assert VariableLookup.__slots__ == ('_status', '_value')
        assert not hasattr(r, '__dict__')
        for name in ('status', 'value'):
            try:
                setattr(r, name, 'MUTATED')
            except AttributeError:
                pass
            else:
                raise AssertionError(f"VariableLookup.{name} must reject assignment")
        try:
            r.extra = 1  # type: ignore[attr-defined]
        except AttributeError:
            pass
        else:
            raise AssertionError("VariableLookup must not accept new attributes")

    def test_missing_is_shared_singleton(self):
        assert VariableLookup.missing() is VariableLookup.missing()

    def test_factory_helpers(self):
        assert VariableLookup.missing().status is LookupStatus.MISSING
        assert VariableLookup.present_unset().status is LookupStatus.PRESENT_UNSET
        assert VariableLookup.of_value('x').status is LookupStatus.VALUE
