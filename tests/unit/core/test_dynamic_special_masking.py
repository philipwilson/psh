"""A local variable masks a dynamic special in its scope (R2, engine level).

`_local_shadows_special` is the one predicate the six special-interception
points (read, declare -p, seed-assign, attribute change, unset) consult so a
`local RANDOM` wins uniformly. Behavioral parity is pinned in
tests/conformance/bash/test_dynamic_special_scoping_conformance.py.
"""

from psh.core.scope import ScopeManager


class TestLocalShadowsSpecialPredicate:
    def test_no_shadow_at_global(self):
        mgr = ScopeManager()
        assert mgr._local_shadows_special('RANDOM') is False

    def test_shadow_when_local_present(self):
        mgr = ScopeManager()
        mgr.push_scope('f')
        mgr.create_local('RANDOM', '5')
        assert mgr._local_shadows_special('RANDOM') is True
        mgr.pop_scope()

    def test_non_special_name_is_never_shadowed(self):
        mgr = ScopeManager()
        mgr.push_scope('f')
        mgr.create_local('ordinary', 'v')
        assert mgr._local_shadows_special('ordinary') is False
        mgr.pop_scope()

    def test_shadow_visible_in_nested_scope(self):
        mgr = ScopeManager()
        mgr.push_scope('f')
        mgr.create_local('RANDOM', '5')
        mgr.push_scope('g')  # nested call
        assert mgr._local_shadows_special('RANDOM') is True
        mgr.pop_scope()
        mgr.pop_scope()


class TestMaskedRead:
    def test_masked_random_reads_the_local(self):
        mgr = ScopeManager()
        mgr.push_scope('f')
        mgr.create_local('RANDOM', '5')
        assert mgr.get_variable_object('RANDOM').value == '5'
        assert mgr.get_variable('RANDOM') == '5'
        mgr.pop_scope()

    def test_declare_p_read_sees_the_local(self):
        mgr = ScopeManager()
        mgr.push_scope('f')
        mgr.create_local('RANDOM', '5')
        cell = mgr.get_declared_variable_object('RANDOM')
        assert cell.value == '5'
        # A plain local, not the INTEGER-attributed dynamic special.
        assert not cell.is_integer
        mgr.pop_scope()

    def test_unmasked_random_is_numeric(self):
        mgr = ScopeManager()
        v = mgr.get_variable('RANDOM')
        assert v is not None and v.isdigit()

    def test_special_returns_after_scope_pop(self):
        mgr = ScopeManager()
        mgr.push_scope('f')
        mgr.create_local('RANDOM', '5')
        assert mgr.get_variable('RANDOM') == '5'
        mgr.pop_scope()
        # dynamic behaviour restored
        assert mgr.get_variable('RANDOM').isdigit()


class TestMaskedMutation:
    def test_assign_updates_local_not_seed(self):
        mgr = ScopeManager()
        mgr.push_scope('f')
        mgr.create_local('RANDOM', '5')
        mgr.set_variable('RANDOM', '6')
        assert mgr.get_variable('RANDOM') == '6'
        mgr.pop_scope()

    def test_unset_leaves_tombstone_no_resurrection(self):
        mgr = ScopeManager()
        mgr.push_scope('f')
        mgr.create_local('RANDOM', '5')
        mgr.unset_variable('RANDOM')
        # own-scope tombstone: reads as unset, does NOT resurrect the special
        assert mgr.lookup('RANDOM').is_set is False
        mgr.pop_scope()
