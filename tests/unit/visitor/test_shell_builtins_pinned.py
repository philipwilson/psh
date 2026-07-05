"""Pin psh/visitor/constants.py SHELL_BUILTINS against the live registry.

SHELL_BUILTINS is bash-scoped (see its docstring in constants.py): it lists
commands a script under analysis may assume are builtins, which is bash's
builtin vocabulary PLUS everything psh's own registry provides. Historically
it drifted in both directions; these tests make drift loud:

* every builtin registered in psh must appear in SHELL_BUILTINS (a new
  builtin fails here until added), and
* every SHELL_BUILTINS entry that is NOT a psh builtin must be on the
  explicit bash/keyword allowlist below (so psh-only typos or stale entries
  can't hide).
"""

from psh.builtins import registry
from psh.visitor.constants import SHELL_BUILTINS

# Entries that are intentionally in SHELL_BUILTINS even though psh's registry
# does not provide them: bash builtins psh hasn't implemented, plus shell
# keywords that scripts treat as commands.
BASH_SCOPED_EXTRAS = frozenset({
    # bash builtins psh does not (yet) implement — several have ledger
    # entries in tests/conformance/bash/test_absent_features.py
    # ('hash' moved out 2026-06-13 when psh implemented it)
    'bind', 'caller', 'compgen', 'complete', 'compopt', 'enable',
    'fc', 'logout', 'suspend',
    # keywords / control flow that scripts invoke like commands
    # ('break'/'continue' moved out 2026-07-02 when psh implemented them
    # as real builtins)
    '[[', ']]',
})


def test_every_registered_builtin_is_in_shell_builtins():
    """A newly registered psh builtin must be added to SHELL_BUILTINS."""
    missing = set(registry.names()) - SHELL_BUILTINS
    assert not missing, (
        f"Builtins registered in psh but missing from "
        f"psh/visitor/constants.py SHELL_BUILTINS: {sorted(missing)}. "
        f"Add them so the analysis visitors recognize them."
    )


def test_non_registry_entries_are_on_the_bash_allowlist():
    """Entries beyond the registry must be intentional bash-scoped extras."""
    extras = SHELL_BUILTINS - set(registry.names())
    unexpected = extras - BASH_SCOPED_EXTRAS
    assert not unexpected, (
        f"SHELL_BUILTINS entries that are neither psh builtins nor on the "
        f"documented bash-scoped allowlist: {sorted(unexpected)}. "
        f"If intentional, add to BASH_SCOPED_EXTRAS here with a reason."
    )
    # And the allowlist itself must not go stale: if psh implements one of
    # these (e.g. hash), move it out of BASH_SCOPED_EXTRAS.
    implemented = BASH_SCOPED_EXTRAS & set(registry.names())
    assert not implemented, (
        f"Now implemented by psh — remove from BASH_SCOPED_EXTRAS: "
        f"{sorted(implemented)}"
    )
