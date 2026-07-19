"""apply_attribute / remove_attribute resolve namerefs to the target (R2).

The mutation engine's attribute paths resolve a nameref to its target EXCEPT
when the attribute being changed is the nameref attribute itself. Behavioral
parity is pinned in tests/conformance/bash/test_nameref_attribute_conformance.py;
these lock the engine-level routing directly on ScopeManager.
"""

from psh.core.scope import ScopeManager
from psh.core.variables import VarAttributes


def _mgr_with_nameref():
    mgr = ScopeManager()
    mgr.set_variable('x', '5')
    mgr.set_variable('r', 'x', attributes=VarAttributes.NAMEREF)
    return mgr


class TestApplyAttributeResolvesNameref:
    def test_integer_lands_on_target(self):
        mgr = _mgr_with_nameref()
        mgr.apply_attribute('r', VarAttributes.INTEGER)
        assert mgr.get_variable_object('x').is_integer
        assert not mgr.get_variable_object('r').is_integer

    def test_readonly_lands_on_target(self):
        mgr = _mgr_with_nameref()
        mgr.apply_attribute('r', VarAttributes.READONLY)
        assert mgr.get_variable_object('x').is_readonly

    def test_export_lands_on_target(self):
        mgr = _mgr_with_nameref()
        mgr.apply_attribute('r', VarAttributes.EXPORT)
        assert mgr.get_variable_object('x').is_exported


class TestRemoveAttributeResolvesNameref:
    def test_remove_integer_from_target(self):
        mgr = _mgr_with_nameref()
        mgr.apply_attribute('r', VarAttributes.INTEGER)
        mgr.remove_attribute('r', VarAttributes.INTEGER)
        assert not mgr.get_variable_object('x').is_integer


class TestNamerefAttributeDoesNotResolve:
    def test_setting_nameref_attribute_targets_the_cell(self):
        mgr = ScopeManager()
        mgr.set_variable('x', '5')
        mgr.set_variable('r', 'x', attributes=VarAttributes.NAMEREF)
        # Re-applying NAMEREF must stay on r (not resolve to x).
        mgr.apply_attribute('r', VarAttributes.NAMEREF)
        assert mgr.get_variable_object('r').is_nameref
        # x must be unaffected — still a plain scalar.
        assert not mgr.get_variable_object('x').is_nameref

    def test_removing_nameref_attribute_targets_the_cell(self):
        mgr = ScopeManager()
        mgr.set_variable('x', '5')
        mgr.set_variable('r', 'x', attributes=VarAttributes.NAMEREF)
        mgr.remove_attribute('r', VarAttributes.NAMEREF)
        assert not mgr.get_variable_object('r').is_nameref

    def test_non_nameref_name_resolves_to_itself(self):
        mgr = ScopeManager()
        mgr.set_variable('plain', 'v')
        mgr.apply_attribute('plain', VarAttributes.INTEGER)
        assert mgr.get_variable_object('plain').is_integer


class TestCycleAttributeOpsWarnTwiceAndContinue:
    """Bounce B2: an attribute op on a nameref CYCLE prints bash's circular-
    reference warning TWICE, is skipped, and the command succeeds (rc 0) —
    unlike a value write, which rejects. Behavioral rc/continuation twins in
    tests/conformance/bash/test_nameref_attribute_conformance.py."""

    def test_declare_i_on_cycle_warns_twice_rc0(self, captured_shell):
        assert captured_shell.run_command('declare -n a=b; declare -n b=a') == 0
        rc = captured_shell.run_command('declare -i a')
        assert rc == 0
        warnings = [ln for ln in captured_shell.get_stderr().splitlines()
                    if 'circular name reference' in ln]
        assert len(warnings) == 2
        # State unchanged: both cells still plain namerefs.
        mgr = captured_shell.state.scope_manager
        assert mgr.get_variable_object('a').is_nameref
        assert not mgr.get_variable_object('a').is_integer

    def test_export_on_cycle_warns_twice_rc0(self, captured_shell):
        captured_shell.run_command('declare -n a=b; declare -n b=a')
        assert captured_shell.run_command('export a') == 0
        warnings = [ln for ln in captured_shell.get_stderr().splitlines()
                    if 'circular name reference' in ln]
        assert len(warnings) == 2

    def test_engine_level_cycle_skips_and_warns_twice(self, captured_shell):
        """Direct apply_attribute callers (not just builtins) get the policy.
        warn_nameref_cycle writes to sys.stderr; capture it directly since
        this bypasses run_command's stream swap."""
        import contextlib
        import io
        mgr = captured_shell.state.scope_manager
        captured_shell.run_command('declare -n a=b; declare -n b=a')
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            mgr.apply_attribute('a', VarAttributes.INTEGER)  # must not raise
        warnings = [ln for ln in buf.getvalue().splitlines()
                    if 'circular name reference' in ln]
        assert len(warnings) == 2
