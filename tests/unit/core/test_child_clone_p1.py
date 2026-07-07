"""Core-state Phase 1: exact child cloning + graph independence.

These pin the C1/E2 defects the 2026-07-06 core-state appraisal reproduced:
a child shell built with ``Shell.for_subshell`` is NOT an exact independent
clone of its parent. Two failure classes:

1. RESURRECTION — a variable unset in the parent reappears in the child
   (the child's fresh ``__init__`` re-imports ``os.environ`` and re-seeds
   defaults like PS4, and ``adopt`` overlays instead of replacing).
2. SHARED MUTABLE IDENTITY — array values and ``Function`` metadata objects
   are shared across the child boundary, so a child mutation (or the env
   builtin's in-process child) changes the parent.

Fixed by ``ShellState.clone_for_child`` (an exact clone: no fresh
``os.environ`` import, no seeded defaults, deep-copied arrays and per-instance
Function metadata). The graph-independence walker below is the durable
replacement for the textual adopt drift-lock (``test_state_adopt_completeness``).
"""

from psh.core.variables import AssociativeArray, IndexedArray
from psh.shell import Shell


def _make_parent():
    """A parent shell seeded with every mutable state category we clone."""
    sh = Shell(norc=True)
    sh.run_command(
        "a=(x y z); "
        "declare -A m=([k1]=v1 [k2]=v2); "
        "set -- p1 p2; "
        "f() { echo body; }; "
        "trap 'echo hi' INT"  # INT is managed: no OS handler installed
    )
    return sh


# --------------------------------------------------------------------------
# Resurrection: an absent parent name must stay absent in the child.
# --------------------------------------------------------------------------

def test_unset_home_stays_absent_in_child():
    parent = Shell(norc=True)
    try:
        parent.run_command("unset HOME")
        child = Shell.for_subshell(parent)
        try:
            assert child.state.scope_manager.get_variable_object("HOME") is None
            assert "HOME" not in child.state.env
        finally:
            child.close()
    finally:
        parent.close()


def test_unset_ps4_stays_absent_in_child():
    parent = Shell(norc=True)
    try:
        parent.run_command("unset PS4")
        child = Shell.for_subshell(parent)
        try:
            assert child.state.scope_manager.get_variable_object("PS4") is None
        finally:
            child.close()
    finally:
        parent.close()


# --------------------------------------------------------------------------
# Independence: mutating the child must never touch the parent.
# --------------------------------------------------------------------------

def test_indexed_array_is_independent():
    parent = _make_parent()
    try:
        child = Shell.for_subshell(parent)
        try:
            child.run_command("a[0]=CHANGED; a+=(w)")
            assert parent.state.scope_manager.get_variable("a", None) is None or \
                parent.state.get_variable("a") == "x"  # parent a[0] unchanged
            pa = parent.state.scope_manager.get_variable_object("a").value
            assert pa.get(0) == "x", "parent array element leaked"
            assert 3 not in pa, "parent array gained the child's appended element"
        finally:
            child.close()
    finally:
        parent.close()


def test_assoc_array_is_independent():
    parent = _make_parent()
    try:
        child = Shell.for_subshell(parent)
        try:
            child.run_command("m[k1]=CHANGED; m[k3]=new")
            pm = parent.state.scope_manager.get_variable_object("m").value
            assert pm.get("k1") == "v1", "parent assoc element leaked"
            assert pm.get("k3") is None, "parent assoc gained child key"
        finally:
            child.close()
    finally:
        parent.close()


def test_function_metadata_is_independent():
    parent = _make_parent()
    try:
        child = Shell.for_subshell(parent)
        try:
            # Mark the function readonly in the child.
            child.run_command("readonly -f f")
            # Parent's function must remain re-definable.
            parent_f = parent.function_manager.get_function("f")
            assert parent_f is not None
            assert parent_f.readonly is False, "child readonly leaked to parent"
        finally:
            child.close()
    finally:
        parent.close()


# --------------------------------------------------------------------------
# Graph-independence walker — the durable drift-lock replacement.
# --------------------------------------------------------------------------

# Objects/types shared across the child boundary BY POLICY (see the copy-policy
# map): the locale service (startup-only), AST bodies (immutable), and scalar
# str/int values (immutable). Everything else mutable must have distinct
# identity in parent vs child.

def _mutable_identity_map(shell):
    """id(obj) -> description for every mutable object that must be
    parent/child-independent. Deliberately does NOT traverse shared-by-policy
    objects (locale, Function.body AST, scalar values)."""
    st = shell.state
    out = {}

    def note(obj, desc):
        out[id(obj)] = desc

    note(st.env, "env dict")
    note(st.trap_handlers, "trap_handlers dict")
    note(st.inherited_traps, "inherited_traps set")
    note(st.positional_params, "positional_params list")
    note(st.options, "options container")
    note(st.execution, "execution state")
    note(st.history_state, "history_state")
    note(st.history_state.entries, "history entries list")
    note(st.command_hash, "command_hash")
    note(st.function_stack, "function_stack list")
    if hasattr(st, "directory_stack"):
        note(st.directory_stack, "directory_stack")

    for scope in st.scope_manager.scope_stack:
        note(scope, f"scope<{scope.name}>")
        note(scope.variables, f"scope<{scope.name}>.variables")
        for name, var in scope.variables.items():
            note(var, f"Variable<{name}>")
            value = var.value
            if isinstance(value, (IndexedArray, AssociativeArray)):
                note(value, f"array<{name}>")
                note(value._elements, f"array<{name}>._elements")

    for name, fn in shell.function_manager.functions.items():
        note(fn, f"Function<{name}>")
        note(fn.redirects, f"Function<{name}>.redirects")

    return out


def test_child_shares_no_mutable_identity_with_parent():
    parent = _make_parent()
    try:
        child = Shell.for_subshell(parent)
        try:
            pmap = _mutable_identity_map(parent)
            cmap = _mutable_identity_map(child)
            shared = set(pmap) & set(cmap)
            details = sorted(pmap[i] for i in shared)
            assert not shared, (
                "parent and child share mutable object identity (child "
                f"mutation would leak): {details}")
        finally:
            child.close()
    finally:
        parent.close()
