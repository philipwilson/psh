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
