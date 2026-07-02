"""
Tests for the unset model in ScopeManager (bash dynamic-scope semantics).

bash keeps a per-name stack of variable instances; ``unset`` removes the
MOST RECENT one, revealing the next-outer instance — except when the
removed instance is a local in its own declaring scope, which stays
"local and unset" (an UNSET tombstone), so the outer instance does not
show through in that scope. Tombstones exist ONLY for that case; unsetting
a global (or a calling function's local) removes it outright.

Also guards listing behavior: get_all_variables()/
all_variables_with_attributes() must not include tombstones, so
`f(){ local x=1; unset x; set | grep ^x=; }` shows nothing (bash).

All behaviors verified against bash 5.2 (probes promoted to the
`unset_*` cases in tests/behavioral/golden_cases.yaml, re-run under
`--compare-bash`; reappraisal #15 finding D1).
"""

from psh.core.scope import ScopeManager
from psh.core.variables import VarAttributes


class TestTombstoneVisibility:
    def test_global_unset_hides_from_get_all_variables(self):
        mgr = ScopeManager()
        mgr.set_variable('X', '1')
        mgr.unset_variable('X')
        assert 'X' not in mgr.get_all_variables()

    def test_function_unset_of_global_hides_from_get_all_variables(self):
        mgr = ScopeManager()
        mgr.set_variable('HOME', '/home/user')
        mgr.push_scope('f')
        mgr.unset_variable('HOME')
        assert 'HOME' not in mgr.get_all_variables()
        mgr.pop_scope()

    def test_unset_local_hides_not_reveals(self):
        """bash: unsetting a local does NOT reveal the outer value."""
        mgr = ScopeManager()
        mgr.set_variable('g', 'outer')
        mgr.push_scope('f')
        mgr.create_local('g', 'inner')
        mgr.unset_variable('g')
        assert 'g' not in mgr.get_all_variables()
        assert mgr.get_variable('g') is None
        mgr.pop_scope()
        # Outer value still intact after the function returns
        assert mgr.get_all_variables().get('g') == 'outer'

    def test_tombstone_excluded_from_all_variables_with_attributes(self):
        mgr = ScopeManager()
        mgr.set_variable('Y', '2')
        mgr.push_scope('f')
        mgr.unset_variable('Y')
        names = [v.name for v in mgr.all_variables_with_attributes()]
        assert 'Y' not in names
        mgr.pop_scope()

    def test_set_after_unset_visible_again(self):
        mgr = ScopeManager()
        mgr.set_variable('Z', '1')
        mgr.unset_variable('Z')
        mgr.set_variable('Z', '2')
        assert mgr.get_all_variables().get('Z') == '2'

    def test_unset_attribute_flag_is_the_mechanism(self):
        """The tombstone is a Variable carrying the UNSET attribute —
        planted ONLY when a local is unset in its own declaring scope
        (bash: the variable stays "local and unset" there). This test
        formerly pinned the pre-D1 model, which planted a tombstone even
        when unsetting a GLOBAL from a function — bash instead deletes
        the global outright (``x=1; f(){ unset x; x=new; }; f`` leaves
        x=new, not unset)."""
        mgr = ScopeManager()
        mgr.push_scope('f')
        mgr.create_local('v', 'local-value')
        mgr.unset_variable('v')
        scope_var = mgr.current_scope.variables.get('v')
        assert scope_var is not None
        assert scope_var.attributes & VarAttributes.UNSET
        mgr.pop_scope()

    def test_unset_global_from_function_leaves_no_tombstone(self):
        """Unsetting a global from a function REMOVES the global — no
        tombstone anywhere (bash: a later assignment writes the global)."""
        mgr = ScopeManager()
        mgr.set_variable('HOME', '/home/user')
        mgr.push_scope('f')
        mgr.unset_variable('HOME')
        assert 'HOME' not in mgr.current_scope.variables
        assert 'HOME' not in mgr.global_scope.variables
        mgr.pop_scope()


class TestBashUnsetSemantics:
    """The dynamic-scope value-stack behaviors from reappraisal #15 D1."""

    def test_unset_global_then_assign_writes_global(self):
        """P1: x=1; f(){ unset x; x=new; }; f — bash leaves x=new."""
        mgr = ScopeManager()
        mgr.set_variable('x', '1')
        mgr.push_scope('f')
        mgr.unset_variable('x')
        mgr.set_variable('x', 'new')
        mgr.pop_scope()
        assert mgr.get_variable('x') == 'new'

    def test_unset_callers_local_reveals_global(self):
        """P3: unset in g of f's local reveals the global in g."""
        mgr = ScopeManager()
        mgr.set_variable('x', 'global')
        mgr.push_scope('f')
        mgr.create_local('x', 'f')
        mgr.push_scope('g')
        mgr.unset_variable('x')
        assert mgr.get_variable('x') == 'global'
        mgr.pop_scope()
        # f's local is gone for f too
        assert mgr.get_variable('x') == 'global'
        mgr.pop_scope()

    def test_unset_callers_local_then_assign_writes_global(self):
        """P4: after g unsets f's local, g's assignment lands on the
        global, visible in f and at top level."""
        mgr = ScopeManager()
        mgr.set_variable('x', 'global')
        mgr.push_scope('f')
        mgr.create_local('x', 'f')
        mgr.push_scope('g')
        mgr.unset_variable('x')
        mgr.set_variable('x', 'setbyg')
        mgr.pop_scope()
        assert mgr.get_variable('x') == 'setbyg'
        mgr.pop_scope()
        assert mgr.get_variable('x') == 'setbyg'

    def test_three_deep_unset_pops_one_instance_each(self):
        """P7: successive unsets from the innermost scope pop the value
        stack one instance at a time."""
        mgr = ScopeManager()
        mgr.set_variable('x', 'global')
        mgr.push_scope('f')
        mgr.create_local('x', 'f')
        mgr.push_scope('g')
        mgr.create_local('x', 'g')
        mgr.push_scope('h')
        mgr.unset_variable('x')
        assert mgr.get_variable('x') == 'f'
        mgr.unset_variable('x')
        assert mgr.get_variable('x') == 'global'
        mgr.unset_variable('x')
        assert mgr.get_variable('x') is None

    def test_own_local_double_unset_stays_local_unset(self):
        """P6: repeated unset of an own-scope local is idempotent — the
        global does not show through."""
        mgr = ScopeManager()
        mgr.set_variable('x', '1')
        mgr.push_scope('f')
        mgr.create_local('x', '2')
        mgr.unset_variable('x')
        mgr.unset_variable('x')
        assert mgr.get_variable('x') is None
        mgr.pop_scope()
        assert mgr.get_variable('x') == '1'

    def test_child_assignment_binds_to_callers_tombstone(self):
        """P21/P22: an assignment in a called function binds to the
        caller's declared-but-unset local, not the global."""
        mgr = ScopeManager()
        mgr.set_variable('x', 'global')
        mgr.push_scope('f')
        mgr.create_local('x')  # bare `local x` — declared-unset
        mgr.push_scope('g')
        mgr.set_variable('x', 'setbyg')
        mgr.pop_scope()
        assert mgr.get_variable('x') == 'setbyg'
        mgr.pop_scope()
        assert mgr.get_variable('x') == 'global'

    def test_deeper_unset_removes_callers_tombstone(self):
        """P37: from a DEEPER scope, unset removes the caller's
        declared-unset cell outright, revealing the global."""
        mgr = ScopeManager()
        mgr.set_variable('x', 'global')
        mgr.push_scope('f')
        mgr.create_local('x', 'f')
        mgr.unset_variable('x')  # tombstone in f
        mgr.push_scope('g')
        mgr.unset_variable('x')  # removes f's tombstone
        assert mgr.get_variable('x') == 'global'
        mgr.pop_scope()
        mgr.pop_scope()

    def test_unset_strips_attributes(self):
        """P43: `local -i x=5; unset x` leaves an attribute-less
        declared-unset cell (bash shows `declare -- x`)."""
        mgr = ScopeManager()
        mgr.push_scope('f')
        mgr.create_local('x', '5', attributes=VarAttributes.INTEGER)
        mgr.unset_variable('x')
        var = mgr.get_declared_variable_object('x')
        assert var is not None
        assert var.attributes == VarAttributes.UNSET
        mgr.pop_scope()

    def test_declare_p_finds_own_scope_tombstone(self):
        """P19b: get_declared_variable_object returns the plain tombstone
        so `declare -p x` prints `declare -- x` (bash)."""
        mgr = ScopeManager()
        mgr.set_variable('x', '1')
        mgr.push_scope('f')
        mgr.create_local('x', '2')
        mgr.unset_variable('x')
        assert mgr.get_declared_variable_object('x') is not None
        mgr.pop_scope()
        # At top level the global is still intact
        assert mgr.get_variable('x') == '1'


class TestTombstonesInSetBuiltin:
    @staticmethod
    def _run_psh(cmd):
        import subprocess
        import sys
        return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                              capture_output=True, text=True)

    def test_unset_variable_absent_from_set_output(self):
        result = self._run_psh('f(){ unset HOME; set | grep -c "^HOME="; }; f')
        assert result.stdout == "0\n"

    def test_unset_local_absent_from_set_output(self):
        result = self._run_psh('f(){ local x=1; unset x; set | grep -c "^x="; }; f')
        assert result.stdout == "0\n"

    def test_declare_p_unset_variable_fails(self, captured_shell):
        result = captured_shell.run_command(
            'f(){ unset HOME; declare -p HOME 2>/dev/null; echo rc=$?; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == "rc=1\n"

    def test_declare_p_own_local_unset_shows_declaration(self, captured_shell):
        """bash: a local unset in its own scope still shows `declare -- x`."""
        result = captured_shell.run_command(
            'x=1; f(){ local x=2; unset x; declare -p x; echo rc=$?; }; f')
        assert result == 0
        assert captured_shell.get_stdout() == "declare -- x\nrc=0\n"

    def test_unset_exported_local_restores_global_env_entry(self):
        """P34: unsetting an exported local reveals the exported global,
        whose environment entry must reappear for children (bash)."""
        result = self._run_psh(
            'export x=global; f(){ local x=f; g; }; '
            'g(){ unset x; printenv x; echo rc=$?; }; f')
        assert result.stdout == "global\nrc=0\n"
