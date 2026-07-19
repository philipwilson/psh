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


class TestReadonlySpecialRefusesLocal:
    """Bounce B4: a READONLY dynamic special (overlay readonly, no stored
    cell) refuses a masking local with bash's message body, rc 1, function
    continues, reads stay dynamic. rc/continuation twins in
    tests/conformance/bash/test_dynamic_special_scoping_conformance.py."""

    def test_message_body_and_continuation(self, captured_shell):
        assert captured_shell.run_command('readonly SECONDS') == 0
        rc = captured_shell.run_command(
            'f(){ local SECONDS=5; echo "in=[$SECONDS]"; }; f')
        assert rc == 0  # the echo runs; the function continues past the error
        assert 'local: SECONDS: readonly variable' in captured_shell.get_stderr()
        # reads stayed dynamic: the masked literal 5 must NOT appear
        assert 'in=[5]' not in captured_shell.get_stdout()

    def test_engine_level_refusal(self, captured_shell):
        from psh.core.exceptions import ReadonlyVariableError
        import pytest
        mgr = captured_shell.state.scope_manager
        captured_shell.run_command('readonly RANDOM')
        mgr.push_scope('f')
        with pytest.raises(ReadonlyVariableError):
            mgr.create_local('RANDOM', '7')
        mgr.pop_scope()
