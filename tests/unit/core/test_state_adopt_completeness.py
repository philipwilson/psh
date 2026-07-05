"""Drift-lock: every ShellState.__init__ field must be handled by adopt().

``ShellState.adopt()`` is the single state-copying chokepoint for
subshell-style children (``Shell.for_subshell``: ``( )`` subshells,
command substitution, process substitution, the env builtin's in-process
child). Reappraisal #15 found SEVEN fields that had been added to
``__init__`` but never copied — ``script_name`` (so ``$(dirname "$0")``
returned "."), ``function_stack`` (FUNCNAME empty in subshells),
``trap_handlers`` (the POSIX ``saved=$(trap)`` idiom returned nothing),
``source_depth``, ``directory_stack``, ``history_state`` and
``_getopts_charpos``.

This test makes that drift impossible to repeat silently: every instance
attribute a fresh ShellState carries (plus class-level lazy-attribute
annotations) must either be mentioned in ``adopt()``'s source as
``self.<name>`` or appear on the exclusion list below with a one-line
justification. Adding a new ``__init__`` field without updating adopt()
or this list FAILS the suite — the same pattern as the option-registry
drift-lock and ``ExecutionState.copy_into`` (which adopt copies as a
unit, so new execution fields are covered there).
"""

import inspect
import re

from psh.core.state import ShellState

# Fields adopt() deliberately does NOT copy. Keys must be real ShellState
# attributes; each value is the reason a child shell starts fresh.
ADOPT_EXCLUSIONS = {
    'streams': "live sys.* stream overrides; each child installs its own "
               "(subshell pipes, capture buffers) — never the parent's",
    'terminal': "TerminalState is re-detected per process in __init__ "
                "(a forked child may have different fds)",
    'norc': "per-invocation CLI flag; for_subshell passes its own "
            "(children never source rc files)",
    'rcfile': "per-invocation CLI flag, like norc",
    'edit_mode': "line-editor configuration; children never run the "
                 "interactive editor",
    '_arith_recursion_depth': "transient arithmetic-evaluation re-entrancy "
                              "counter (unwound by finally); a forked child "
                              "begins a fresh evaluation context, so it must "
                              "start at 0, never inherit the parent's",
}


def _init_field_names():
    """Instance attributes of a fresh ShellState, plus class-level pure
    annotations (lazily-created attributes like directory_stack)."""
    names = set(vars(ShellState()))
    names |= set(getattr(ShellState, '__annotations__', {}))
    return names


def test_every_init_field_is_adopted_or_excluded():
    adopt_source = inspect.getsource(ShellState.adopt)
    missing = sorted(
        name for name in _init_field_names()
        if name not in ADOPT_EXCLUSIONS
        and not re.search(rf'\bself\.{re.escape(name)}\b', adopt_source)
    )
    assert not missing, (
        f"ShellState.__init__ field(s) {missing} are neither copied/handled "
        f"in ShellState.adopt() nor justified on ADOPT_EXCLUSIONS in "
        f"{__file__}. Subshell-style children would silently lose this "
        f"state (the reappraisal-#15 $0/FUNCNAME/trap bug class). Either "
        f"copy the field in adopt() or add it to the exclusion list with a "
        f"justification."
    )


def test_exclusion_list_names_real_fields():
    """A stale exclusion entry (field renamed/removed) must fail too."""
    fields = _init_field_names()
    stale = sorted(name for name in ADOPT_EXCLUSIONS if name not in fields)
    assert not stale, (
        f"ADOPT_EXCLUSIONS entries {stale} no longer exist on ShellState — "
        f"remove them so the list stays truthful."
    )
