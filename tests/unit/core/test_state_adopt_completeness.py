"""Drift-lock: every ShellState field must be handled by clone_for_child.

``ShellState.clone_for_child`` (v0.656) replaced the old build-then-overlay
``adopt``: it constructs the child via ``__new__`` and assigns every
inheritable field explicitly, with no fresh ``os.environ`` import and no
seeded defaults (so an unset parent name cannot resurrect in the child). That
makes field completeness MORE important than before — a new ``__init__`` field
not assigned in ``clone_for_child`` is simply absent on the child (an
``AttributeError`` on first access), not merely stale.

This module keeps the reappraisal-#15 drift-lock intent in two layers:

1. NAME completeness — every fresh-``ShellState`` field is assigned in
   ``clone_for_child``'s source (``self.<name> = ...``) or justified on the
   exclusion list.
2. IDENTITY independence (the graph walk) — after a real clone, no mutable
   field is shared between parent and child except the shared-by-policy
   allowlist. This catches a field that is "copied" by aliasing the parent's
   object (which the text grep cannot see) — the class of bug the old
   completeness test was blind to.
"""

import inspect
import re

from psh.core.state import ShellState
from psh.shell import Shell

# Fields clone_for_child assigns indirectly (never as a literal ``self.<name>``
# in its own source), with the reason. Empty today: clone_for_child assigns
# every ShellState instance field directly. A future indirectly-set field
# lands here with a one-line justification.
CLONE_INDIRECT = {
}


def _init_field_names():
    """Instance attributes of a fresh ShellState, plus class-level pure
    annotations (lazily-created attributes like directory_stack)."""
    names = set(vars(ShellState()))
    names |= set(getattr(ShellState, "__annotations__", {}))
    return names


def test_every_init_field_is_cloned_or_excluded():
    src = inspect.getsource(ShellState.clone_for_child)
    missing = sorted(
        name for name in _init_field_names()
        if name not in CLONE_INDIRECT
        and not re.search(rf"\bself\.{re.escape(name)}\b", src)
    )
    assert not missing, (
        f"ShellState.__init__ field(s) {missing} are neither assigned in "
        f"ShellState.clone_for_child() nor justified on CLONE_INDIRECT in "
        f"{__file__}. A child shell built via __new__ would be MISSING this "
        f"field entirely (AttributeError on access) — assign it in "
        f"clone_for_child() with its copy policy, or add it to CLONE_INDIRECT."
    )


def test_exclusion_list_names_real_fields():
    fields = _init_field_names()
    stale = sorted(name for name in CLONE_INDIRECT if name not in fields)
    assert not stale, (
        f"CLONE_INDIRECT entries {stale} no longer exist on ShellState — "
        f"remove them so the list stays truthful."
    )


# --------------------------------------------------------------------------
# Identity independence: mutable state must not be shared by aliasing.
# --------------------------------------------------------------------------

# Shared across the child boundary BY POLICY (copy-policy map): the locale
# service (startup-only, immutable in practice). Scalar str/int values and AST
# bodies are immutable and not walked.
_SHARED_BY_POLICY = {"locale"}


def _mutable_field_identities(state):
    """(field_name, id) for each mutable ShellState field that must be
    parent/child-independent. Immutable scalars/enums are skipped."""
    out = {}
    for name, value in vars(state).items():
        if name in _SHARED_BY_POLICY:
            continue
        if isinstance(value, (str, int, bool, type(None))):
            continue  # immutable scalar (script_name, source_depth, pids, ...)
        out[name] = id(value)
    return out


def test_clone_shares_no_mutable_field_by_aliasing():
    parent = Shell(norc=True)
    try:
        parent.run_command("a=(x y); export FOO=bar; set -- p q")
        child = Shell.for_subshell(parent)
        try:
            pids = _mutable_field_identities(parent.state)
            cids = _mutable_field_identities(child.state)
            aliased = sorted(
                name for name in pids
                if name in cids and pids[name] == cids[name])
            assert not aliased, (
                "clone_for_child aliased the parent's mutable field(s) "
                f"{aliased} instead of copying them — a child mutation would "
                f"leak into the parent. Deep-copy them (or move to "
                f"_SHARED_BY_POLICY with justification).")
        finally:
            child.close()
    finally:
        parent.close()
