"""VariableStore transaction core — isolation tests (campaign commit 2).

Exercises the store's operations directly against a real ``Shell`` (so the
arithmetic evaluator and observers are wired), independent of the declaration
builtins that will adopt it in later commits. Focus: the append target-scope
policy (FIX3 base-read) and the guarded element primitives (readonly-before-
mutate, negative-index resolution owned by the store).
"""

import pytest

from psh.core import ReadonlyVariableError, VarAttributes
from psh.core.variable_store import TargetScope, VariableStore
from psh.shell import Shell


@pytest.fixture
def shell():
    sh = Shell(norc=True)
    yield sh
    sh.close()


def _store(sh) -> VariableStore:
    return sh.state.scope_manager.store


def _obj(sh, name):
    return sh.state.scope_manager.get_variable_object(name)


# -------------------------------------------------------------------------- #
# Whole-variable facade.
# -------------------------------------------------------------------------- #

class TestWholeVariableFacade:
    def test_assign_and_read(self, shell):
        _store(shell).assign("X", "hi")
        assert shell.state.get_variable("X") == "hi"

    def test_assign_readonly_then_reassign_refused(self, shell):
        _store(shell).assign("R", "1", attributes=VarAttributes.READONLY)
        with pytest.raises(ReadonlyVariableError):
            _store(shell).assign("R", "2")
        assert shell.state.get_variable("R") == "1"

    def test_add_and_remove_attributes(self, shell):
        _store(shell).assign("X", "hi")
        _store(shell).add_attributes("X", VarAttributes.EXPORT)
        assert _obj(shell, "X").is_exported
        _store(shell).remove_attributes("X", VarAttributes.EXPORT)
        assert not _obj(shell, "X").is_exported

    def test_unset(self, shell):
        _store(shell).assign("X", "hi")
        _store(shell).unset("X")
        assert _obj(shell, "X") is None


# -------------------------------------------------------------------------- #
# Append — target-scope aware (the FIX3 mechanism at the store level).
# -------------------------------------------------------------------------- #

class TestAppend:
    def test_string_append(self, shell):
        _store(shell).assign("X", "ab")
        _store(shell).append("X", "cd")
        assert shell.state.get_variable("X") == "abcd"

    def test_integer_append(self, shell):
        _store(shell).assign("N", "5", attributes=VarAttributes.INTEGER)
        _store(shell).append("N", "3")
        assert shell.state.get_variable("N") == "8"

    def test_append_unset_base(self, shell):
        _store(shell).append("X", "cd")
        assert shell.state.get_variable("X") == "cd"

    def test_global_append_reads_global_base_not_local_shadow(self, shell):
        # The store-level FIX3: with global_scope, the append base is the GLOBAL
        # instance even under a same-named local shadow.
        shell.run_command("x=G; f(){ :; }")
        sm = shell.state.scope_manager
        sm.push_scope("f")
        try:
            sm.create_local("x", "L")
            _store(shell).append("x", "A", global_scope=True)
            # Local shadow untouched; global updated from its own base.
            assert sm.current_scope.variables["x"].value == "L"
            assert sm.global_scope.variables["x"].value == "GA"
        finally:
            sm.pop_scope()

    def test_global_integer_append_reads_global_base(self, shell):
        shell.run_command("declare -i n=100")
        sm = shell.state.scope_manager
        sm.push_scope("f")
        try:
            sm.create_local("n", "1")
            _store(shell).append("n", "5", global_scope=True)
            assert sm.global_scope.variables["n"].value == "105"
        finally:
            sm.pop_scope()


# -------------------------------------------------------------------------- #
# Element primitives — guarded commit, negative-index owned by the store.
# -------------------------------------------------------------------------- #

class TestSetElement:
    def test_set_element_creates_indexed(self, shell):
        _store(shell).set_element("a", 2, "v")
        assert _obj(shell, "a").value.get(2) == "v"

    def test_set_element_existing_indexed(self, shell):
        shell.run_command("a=(x y z)")
        _store(shell).set_element("a", 1, "CHANGED")
        assert _obj(shell, "a").value.all_elements() == ["x", "CHANGED", "z"]

    def test_set_element_negative_index_resolved_once(self, shell):
        # Store owns the negative-index resolution: -1 maps to the last slot.
        shell.run_command("a=(x y z)")
        _store(shell).set_element("a", -1, "LAST")
        assert _obj(shell, "a").value.all_elements() == ["x", "y", "LAST"]

    def test_set_element_assoc(self, shell):
        shell.run_command("declare -A m=([k]=v)")
        _store(shell).set_element("m", "j", "w")
        assert _obj(shell, "m").value.get("j") == "w"

    def test_set_element_readonly_refused_no_mutation(self, shell):
        shell.run_command("a=(x y); readonly a")
        with pytest.raises(ReadonlyVariableError):
            _store(shell).set_element("a", 0, "Z")
        assert _obj(shell, "a").value.all_elements() == ["x", "y"]

    def test_set_element_through_nameref(self, shell):
        shell.run_command("arr=(x y); declare -n r=arr")
        _store(shell).set_element("r", 0, "Z")
        assert _obj(shell, "arr").value.get(0) == "Z"


class TestUnsetElement:
    def test_unset_element_indexed(self, shell):
        shell.run_command("a=(x y z)")
        _store(shell).unset_element("a", 1)
        assert _obj(shell, "a").value.indices() == [0, 2]

    def test_unset_element_negative_sparse_matches_write(self, shell):
        # a[5],a[10]: -2 -> slot 9 (unset) -> no-op, same formula as write.
        shell.run_command("a=([5]=F [10]=T)")
        _store(shell).unset_element("a", -2)
        assert _obj(shell, "a").value.indices() == [5, 10]

    def test_unset_element_assoc(self, shell):
        shell.run_command("declare -A m=([k]=v [j]=w)")
        _store(shell).unset_element("m", "k")
        assert _obj(shell, "m").value.keys() == ["j"]

    def test_unset_element_missing_name_noop(self, shell):
        _store(shell).unset_element("nope", 0)  # no raise
        assert _obj(shell, "nope") is None

    def test_unset_element_readonly_refused(self, shell):
        shell.run_command("a=(x y); readonly a")
        with pytest.raises(ReadonlyVariableError):
            _store(shell).unset_element("a", 0)
        assert _obj(shell, "a").value.all_elements() == ["x", "y"]


class TestResolveWriteFlags:
    def test_global(self):
        assert VariableStore.resolve_write_flags(TargetScope.GLOBAL, True) == (False, True)

    def test_local(self):
        assert VariableStore.resolve_write_flags(TargetScope.LOCAL, False) == (True, False)

    def test_default_in_function_is_local(self):
        assert VariableStore.resolve_write_flags(TargetScope.DEFAULT, True) == (True, False)

    def test_default_top_level_is_global(self):
        assert VariableStore.resolve_write_flags(TargetScope.DEFAULT, False) == (False, False)


def test_child_shell_store_is_independent():
    """clone() gives the child its own store bound to the child's manager."""
    parent = Shell(norc=True)
    try:
        parent.run_command("a=(x y)")
        child = Shell.for_subshell(parent)
        try:
            cstore = child.state.scope_manager.store
            assert cstore is not parent.state.scope_manager.store
            assert cstore._sm is child.state.scope_manager
            cstore.set_element("a", 0, "CHILD")
            assert parent.state.scope_manager.get_variable_object("a").value.get(0) == "x"
        finally:
            child.close()
    finally:
        parent.close()
