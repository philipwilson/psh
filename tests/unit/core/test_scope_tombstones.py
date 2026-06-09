"""
Tests for UNSET tombstone visibility in EnhancedScopeManager.

Regression guard: get_all_variables()/all_variables_with_attributes() used to
include UNSET tombstones, so `f(){ unset HOME; set | grep ^HOME=; }` still
showed `HOME=` (bash shows nothing). Verified against bash 5.2.
"""

from psh.core.scope_enhanced import EnhancedScopeManager
from psh.core.variables import VarAttributes


class TestTombstoneVisibility:
    def test_global_unset_hides_from_get_all_variables(self):
        mgr = EnhancedScopeManager()
        mgr.set_variable('X', '1')
        mgr.unset_variable('X')
        assert 'X' not in mgr.get_all_variables()

    def test_function_unset_of_global_hides_from_get_all_variables(self):
        mgr = EnhancedScopeManager()
        mgr.set_variable('HOME', '/home/user')
        mgr.push_scope('f')
        mgr.unset_variable('HOME')
        assert 'HOME' not in mgr.get_all_variables()
        mgr.pop_scope()

    def test_unset_local_hides_not_reveals(self):
        """bash: unsetting a local does NOT reveal the outer value."""
        mgr = EnhancedScopeManager()
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
        mgr = EnhancedScopeManager()
        mgr.set_variable('Y', '2')
        mgr.push_scope('f')
        mgr.unset_variable('Y')
        names = [v.name for v in mgr.all_variables_with_attributes()]
        assert 'Y' not in names
        mgr.pop_scope()

    def test_set_after_unset_visible_again(self):
        mgr = EnhancedScopeManager()
        mgr.set_variable('Z', '1')
        mgr.unset_variable('Z')
        mgr.set_variable('Z', '2')
        assert mgr.get_all_variables().get('Z') == '2'

    def test_unset_attribute_flag_is_the_mechanism(self):
        """The tombstone is a Variable carrying the UNSET attribute."""
        mgr = EnhancedScopeManager()
        mgr.set_variable('HOME', '/home/user')
        mgr.push_scope('f')
        mgr.unset_variable('HOME')
        scope_var = mgr.current_scope.variables.get('HOME')
        assert scope_var is not None
        assert scope_var.attributes & VarAttributes.UNSET
        mgr.pop_scope()


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
