"""The variable write door: ``VariableStore.assign`` decides ``set -a`` once
(slot 1.16, C028) — a unit matrix over spelling × scope × attribute.

Every row drives the door's INTERFACE only (``store.assign`` with a
``TargetScope``, or the two ``ShellState`` forwards) and reads back through
the lookup authority (``get_variable_object``); nothing here touches the scope
stack or the private primitives. The owner is
``psh/core/variable_store.py#VariableStore._allexport_attributes``.
"""

import pytest

from psh.core import VarAttributes
from psh.core.scope import ScopeManager
from psh.core.variable_store import TargetScope
from psh.core.variables import AssociativeArray, IndexedArray
from psh.shell import Shell

A = VarAttributes


@pytest.fixture
def sh():
    return Shell(norc=True)


def _store(sh):
    return sh.state.scope_manager.store


def _attrs(sh, name):
    var = sh.state.scope_manager.get_declared_variable_object(name)
    assert var is not None, name
    return var.attributes


def _exported(sh, name) -> bool:
    return bool(_attrs(sh, name) & A.EXPORT)


def _allexport(sh, on=True):
    sh.state.options['allexport'] = on


# ---------------------------------------------------------------------------
# Scalars with a value: every target exports under set -a, none without it.
# ---------------------------------------------------------------------------

VALUE_TARGETS = [
    pytest.param(TargetScope.DYNAMIC, False, id="dynamic-top"),
    pytest.param(TargetScope.DEFAULT, False, id="default-top"),
    pytest.param(TargetScope.GLOBAL, False, id="global-top"),
    pytest.param(TargetScope.DYNAMIC, True, id="dynamic-in-function"),
    pytest.param(TargetScope.DEFAULT, True, id="default-in-function"),
    pytest.param(TargetScope.LOCAL, True, id="local-in-function"),
    pytest.param(TargetScope.GLOBAL, True, id="global-in-function"),
]


@pytest.mark.parametrize("target,in_function", VALUE_TARGETS)
@pytest.mark.parametrize("extra", [A.NONE, A.INTEGER, A.READONLY, A.UPPERCASE],
                         ids=["plain", "-i", "-r", "-u"])
def test_scalar_with_value_exports_under_allexport(sh, target, in_function, extra):
    _allexport(sh)
    if in_function:
        sh.state.scope_manager.push_scope('f')
    _store(sh).assign('v', '1', attributes=extra, target=target)
    assert _exported(sh, 'v')
    assert _attrs(sh, 'v') & extra == extra


@pytest.mark.parametrize("target,in_function", VALUE_TARGETS)
def test_scalar_with_value_not_exported_without_allexport(sh, target, in_function):
    if in_function:
        sh.state.scope_manager.push_scope('f')
    _store(sh).assign('v', '1', target=target)
    assert not _exported(sh, 'v')


def test_nameref_definition_exports_the_reference(sh):
    _allexport(sh)
    _store(sh).assign('x', '0')
    _store(sh).assign('r', 'x', attributes=A.NAMEREF)
    assert _attrs(sh, 'r') & (A.NAMEREF | A.EXPORT) == (A.NAMEREF | A.EXPORT)


def test_write_through_nameref_exports_the_target_not_the_reference(sh):
    _store(sh).assign('x', '0')
    _store(sh).assign('r', 'x', attributes=A.NAMEREF)
    _allexport(sh)
    _store(sh).assign('r', '1')
    assert _exported(sh, 'x') and sh.state.get_variable('x') == '1'
    assert not _exported(sh, 'r')


# ---------------------------------------------------------------------------
# Value-less declarations: only a NEW GLOBAL exports.
# ---------------------------------------------------------------------------

def test_valueless_declare_at_top_level_exports(sh):
    _allexport(sh)
    _store(sh).assign('y', '', attributes=A.UNSET, target=TargetScope.DEFAULT)
    assert _exported(sh, 'y') and _attrs(sh, 'y') & A.UNSET


def test_valueless_declare_g_in_function_exports(sh):
    _allexport(sh)
    sh.state.scope_manager.push_scope('f')
    _store(sh).assign('y', '', attributes=A.UNSET, target=TargetScope.GLOBAL)
    assert _exported(sh, 'y')


def test_valueless_declare_in_function_does_not_export(sh):
    _allexport(sh)
    sh.state.scope_manager.push_scope('f')
    _store(sh).assign('y', '', attributes=A.UNSET, target=TargetScope.DEFAULT)
    assert not _exported(sh, 'y')


def test_valueless_local_does_not_export(sh):
    _allexport(sh)
    sh.state.scope_manager.push_scope('f')
    _store(sh).assign('y', None, target=TargetScope.LOCAL)
    assert not _exported(sh, 'y') and _attrs(sh, 'y') & A.UNSET


def test_valueless_readonly_at_top_level_exports(sh):
    _allexport(sh)
    _store(sh).assign('r', '', attributes=A.READONLY | A.UNSET,
                      target=TargetScope.DEFAULT)
    assert _attrs(sh, 'r') & (A.READONLY | A.EXPORT) == (A.READONLY | A.EXPORT)


# ---------------------------------------------------------------------------
# Never exported: arrays, dynamic specials.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("container,flag", [
    (IndexedArray(), A.ARRAY), (AssociativeArray(), A.ASSOC_ARRAY)],
    ids=["indexed", "assoc"])
@pytest.mark.parametrize("target", [TargetScope.DYNAMIC, TargetScope.DEFAULT,
                                    TargetScope.GLOBAL], ids=["dynamic", "default", "global"])
def test_array_container_never_exported(sh, container, flag, target):
    _allexport(sh)
    _store(sh).assign('a', container, attributes=flag, target=target)
    assert not _exported(sh, 'a')


def test_local_array_never_exported(sh):
    _allexport(sh)
    sh.state.scope_manager.push_scope('f')
    _store(sh).assign('a', IndexedArray(), attributes=A.ARRAY, target=TargetScope.LOCAL)
    assert not _exported(sh, 'a')


def test_dynamic_special_never_exported(sh):
    _allexport(sh)
    _store(sh).assign('RANDOM', '5')
    assert 'RANDOM' not in sh.state.env


# ---------------------------------------------------------------------------
# The forwards carry no policy of their own; the door applies it for them.
# ---------------------------------------------------------------------------

def test_shellstate_set_variable_forward_exports_under_allexport(sh):
    _allexport(sh)
    sh.state.set_variable('v', '1')
    assert _exported(sh, 'v') and sh.state.env['v'] == '1'


def test_shellstate_set_variable_forward_is_plain_without_allexport(sh):
    sh.state.set_variable('v', '1')
    assert not _exported(sh, 'v') and 'v' not in sh.state.env


def test_export_variable_forward_writes_past_temp_env(sh):
    sh.state.export_variable('E', '1')
    assert _exported(sh, 'E') and sh.state.env['E'] == '1'


# ---------------------------------------------------------------------------
# Target resolution belongs to the door.
# ---------------------------------------------------------------------------

def test_default_in_function_is_the_current_scope(sh):
    _store(sh).assign('x', 'outer')
    sh.state.scope_manager.push_scope('f')
    _store(sh).assign('x', 'inner', target=TargetScope.DEFAULT)
    assert sh.state.get_variable('x') == 'inner'
    sh.state.scope_manager.pop_scope()
    assert sh.state.get_variable('x') == 'outer'


def test_dynamic_in_function_rebinds_the_outer_instance(sh):
    _store(sh).assign('x', 'outer')
    sh.state.scope_manager.push_scope('f')
    _store(sh).assign('x', 'inner', target=TargetScope.DYNAMIC)
    sh.state.scope_manager.pop_scope()
    assert sh.state.get_variable('x') == 'inner'


def test_global_in_function_writes_past_a_local(sh):
    _store(sh).assign('x', 'outer')
    sh.state.scope_manager.push_scope('f')
    _store(sh).assign('x', 'local', target=TargetScope.LOCAL)
    _store(sh).assign('x', 'global', target=TargetScope.GLOBAL)
    assert sh.state.get_variable('x') == 'local'
    sh.state.scope_manager.pop_scope()
    assert sh.state.get_variable('x') == 'global'


def test_temp_env_scope_alone_is_not_a_function(sh):
    """A command-prefix temp-env scope under no function: DEFAULT is still the
    global scope (the engine used to ask ShellState.function_stack for this)."""
    sm = sh.state.scope_manager
    sm.push_temp_env_scope()
    assert sm.is_in_function() and not sm.has_function_scope()
    _store(sh).assign('d', '1', target=TargetScope.DEFAULT)
    sm.pop_scope()
    assert sh.state.get_variable('d') == '1'


def test_local_target_requires_a_function_scope(sh):
    with pytest.raises(RuntimeError):
        _store(sh).assign('x', '1', target=TargetScope.LOCAL)


# ---------------------------------------------------------------------------
# W1-N18: a local tombstone keeps its attributes across a redeclare.
# ---------------------------------------------------------------------------

def test_local_tombstone_valueless_redeclare_merges_attributes(sh):
    sm = sh.state.scope_manager
    sm.push_scope('f')
    _store(sh).assign('x', None, attributes=A.UPPERCASE, target=TargetScope.LOCAL)
    _store(sh).assign('x', None, attributes=A.EXPORT, target=TargetScope.LOCAL)
    assert _attrs(sh, 'x') & (A.UPPERCASE | A.EXPORT | A.UNSET) == (A.UPPERCASE | A.EXPORT | A.UNSET)


def test_local_tombstone_keeps_readonly_on_valueless_redeclare(sh):
    sm = sh.state.scope_manager
    sm.push_scope('f')
    _store(sh).assign('x', None, attributes=A.READONLY, target=TargetScope.LOCAL)
    _store(sh).assign('x', None, attributes=A.EXPORT, target=TargetScope.LOCAL)
    assert _attrs(sh, 'x') & (A.READONLY | A.EXPORT) == (A.READONLY | A.EXPORT)


def test_local_tombstone_case_attribute_applies_to_later_value(sh):
    sm = sh.state.scope_manager
    sm.push_scope('f')
    _store(sh).assign('x', None, attributes=A.UPPERCASE, target=TargetScope.LOCAL)
    _store(sh).assign('x', 'hi', target=TargetScope.LOCAL)
    assert sh.state.get_variable('x') == 'HI' and _attrs(sh, 'x') & A.UPPERCASE


def test_local_tombstone_integer_attribute_applies_to_later_value(sh):
    sm = sh.state.scope_manager
    sm.push_scope('f')
    _store(sh).assign('x', None, attributes=A.INTEGER, target=TargetScope.LOCAL)
    _store(sh).assign('x', '2+3', target=TargetScope.LOCAL)
    assert sh.state.get_variable('x') == '5'


# ---------------------------------------------------------------------------
# The options dependency is explicit: a bare manager gets a default table, a
# clone carries the child's table.
# ---------------------------------------------------------------------------

def test_bare_scope_manager_has_a_default_option_table():
    sm = ScopeManager()
    assert sm.options.get('allexport') is False
    sm.store.assign('v', '1')
    assert not (sm.get_variable_object('v').attributes & A.EXPORT)


def test_child_clone_reads_the_child_option_table(sh):
    from psh.core.state import ShellState
    _allexport(sh)
    child = ShellState.clone_for_child(sh.state)
    assert child.scope_manager.options is child.options
    child.scope_manager.store.assign('c', '1')
    assert child.scope_manager.get_variable_object('c').attributes & A.EXPORT
    child.options['allexport'] = False
    child.scope_manager.store.assign('d', '1')
    assert not (child.scope_manager.get_variable_object('d').attributes & A.EXPORT)
    # and the parent's table is untouched
    assert sh.state.options.get('allexport') is True


# ---------------------------------------------------------------------------
# remove_attributes: an explicit +x against allexport (verifier r1, b1/b3).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("target", [TargetScope.DEFAULT, TargetScope.GLOBAL, TargetScope.DYNAMIC],
                         ids=["default", "global", "dynamic"])
def test_valueless_plus_x_suppresses_allexport(sh, target):
    _allexport(sh)
    _store(sh).assign('v', '', attributes=A.UNSET, remove_attributes=A.EXPORT, target=target)
    assert not _exported(sh, 'v')


def test_valueless_plus_x_with_integer_keeps_integer_only(sh):
    _allexport(sh)
    _store(sh).assign('n', '', attributes=A.INTEGER | A.UNSET, remove_attributes=A.EXPORT,
                      target=TargetScope.DEFAULT)
    assert _attrs(sh, 'n') & (A.INTEGER | A.EXPORT) == A.INTEGER


def test_valued_plus_x_is_still_exported(sh):
    _allexport(sh)
    _store(sh).assign('v', '1', remove_attributes=A.EXPORT, target=TargetScope.DEFAULT)
    assert _exported(sh, 'v')


def test_fresh_local_plus_x_drops_inherited_export_only(sh):
    _store(sh).assign('G', 'g', attributes=A.EXPORT)
    sh.state.scope_manager.push_scope('f')
    _store(sh).assign('G', 'z', remove_attributes=A.EXPORT, target=TargetScope.LOCAL)
    assert not _exported(sh, 'G')


def test_fresh_local_plus_x_under_allexport_exports(sh):
    _store(sh).assign('G', 'g', attributes=A.EXPORT)
    _allexport(sh)
    sh.state.scope_manager.push_scope('f')
    _store(sh).assign('G', 'z', remove_attributes=A.EXPORT, target=TargetScope.LOCAL)
    assert _exported(sh, 'G')


def test_fresh_valueless_local_plus_x_is_not_exported(sh):
    _store(sh).assign('G', 'g', attributes=A.EXPORT)
    _allexport(sh)
    sh.state.scope_manager.push_scope('f')
    _store(sh).assign('G', None, remove_attributes=A.EXPORT, target=TargetScope.LOCAL)
    assert not _exported(sh, 'G') and _attrs(sh, 'G') & A.UNSET


def test_local_redeclare_plus_attribute_strips_it_before_merge(sh):
    sh.state.scope_manager.push_scope('f')
    _store(sh).assign('x', '1', attributes=A.UPPERCASE | A.EXPORT, target=TargetScope.LOCAL)
    _store(sh).assign('x', 'hi', remove_attributes=A.UPPERCASE, target=TargetScope.LOCAL)
    assert sh.state.get_variable('x') == 'hi' and _exported(sh, 'x')


# ---------------------------------------------------------------------------
# unset of a declared-unset local strips its attributes (verifier r1, b2).
# ---------------------------------------------------------------------------

def test_unset_of_declared_tombstone_strips_attributes(sh):
    sm = sh.state.scope_manager
    sm.push_scope('f')
    _store(sh).assign('x', None, attributes=A.UPPERCASE, target=TargetScope.LOCAL)
    sm.unset_variable('x')
    assert _attrs(sh, 'x') == A.UNSET
    _store(sh).assign('x', 'v', target=TargetScope.LOCAL)
    assert sh.state.get_variable('x') == 'v' and not (_attrs(sh, 'x') & A.UPPERCASE)


def test_unset_of_readonly_tombstone_is_refused(sh):
    from psh.core import ReadonlyVariableError
    sm = sh.state.scope_manager
    sm.push_scope('f')
    _store(sh).assign('x', None, attributes=A.READONLY, target=TargetScope.LOCAL)
    with pytest.raises(ReadonlyVariableError):
        sm.unset_variable('x')
    assert _attrs(sh, 'x') & A.READONLY


# ---------------------------------------------------------------------------
# nameref to an array element: the door's EXPORT lands on the array (b4).
# ---------------------------------------------------------------------------

def test_nameref_element_write_marks_the_array_exported_under_allexport(sh):
    sh.run_command("a=(0 1); declare -n r='a[1]'")
    _allexport(sh)
    _store(sh).assign('r', '5')
    assert _exported(sh, 'a') and sh.state.scope_manager.get_variable_object('a').value.get(1) == '5'


def test_nameref_element_write_without_allexport_leaves_array_unexported(sh):
    sh.run_command("a=(0 1); declare -n r='a[1]'")
    _store(sh).assign('r', '5')
    assert not _exported(sh, 'a')


def test_local_nameref_element_write_does_not_mark_the_array(sh):
    sh.run_command("a=(0 1)")
    _allexport(sh)
    sm = sh.state.scope_manager
    sm.push_scope('f')
    _store(sh).assign('r', 'a[1]', attributes=A.NAMEREF, target=TargetScope.LOCAL)
    _store(sh).assign('r', '5')
    assert not _exported(sh, 'a') and sm.get_variable_object('a').value.get(1) == '5'


def test_global_nameref_element_write_from_inside_a_function_marks_the_array(sh):
    sh.run_command("a=(0 1); declare -n r='a[1]'")
    _allexport(sh)
    sh.state.scope_manager.push_scope('f')
    _store(sh).assign('r', '5')
    assert _exported(sh, 'a')


def test_declaration_through_global_nameref_under_allexport_does_not_mark_the_array(sh):
    sh.run_command("a=(0 1); declare -n r='a[1]'")
    _allexport(sh)
    _store(sh).assign('r', '5', target=TargetScope.DEFAULT)
    assert not _exported(sh, 'a')
    _store(sh).assign('r', '6', target=TargetScope.GLOBAL)
    assert not _exported(sh, 'a')


def test_explicit_export_through_global_nameref_marks_the_array(sh):
    sh.run_command("a=(0 1); declare -n r='a[1]'")
    _store(sh).assign('r', '5', attributes=A.EXPORT, target=TargetScope.DEFAULT)
    assert _exported(sh, 'a')
