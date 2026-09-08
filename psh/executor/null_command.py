"""The status of a simple command that runs no program (bash's null command).

A simple command whose words expand to ZERO fields still *is* a command: its
assignments apply, its redirections are performed, and it reports a status.
bash computes that status in ``execute_null_command`` (execute_cmd.c) and psh
computes it here, in ONE place, for every shape that reaches it — a bare
``$(exit 5)``, a redirect-only ``> f``, an assignment-only ``x=$(exit 5)``, and
a bare array assignment ``a=($(exit 7))``.

The rule, in the order the three clauses are decided:

1. A redirection SETUP failure is status 1 (``$(exit 5) > /nodir/f`` -> 1).
2. Otherwise, if any redirection targets **fd 0** — or uses the named-fd
   ``{var}>`` form — the status is 0.  bash performs those redirections in a
   forked child (so the shell's own stdin is not consumed) and the child exits
   success, which erases the substitution status: ``$(exit 5) < f`` -> 0,
   ``$(exit 5) <<EOF`` -> 0, ``$(exit 5) <<< z`` -> 0, ``$(exit 5) {v}> f``
   -> 0, while ``$(exit 5) > f`` -> 5 and ``$(exit 5) 3< f`` -> 5.
3. Otherwise the status is the exit status of the LAST command substitution
   performed while expanding this command (its words, its assignment values,
   and its redirection targets, in that order), or 0 if none ran.

Clause 2's exact membership is empirical against bash 5.3.15 (there is no
CHANGES entry; the fork is an implementation detail of ``execute_null_command``
that is nonetheless observable through ``$?``). Every listed form was probed in
``-c``, script-file and stdin modes.

Repro for the rule this module exists to enforce (C041):

    psh -c '$(exit 5); echo rc=$?'    # rc=5, not rc=0
"""
from typing import TYPE_CHECKING, List

from ..io_redirect.redirect_program import target_fd_of

if TYPE_CHECKING:
    from ..ast_nodes import Redirect
    from ..core.state import ShellState


def null_command_redirects_stdin(redirects: List['Redirect']) -> bool:
    """True if these redirections make bash fork for a null command.

    That is: any of them targets fd 0, or opens onto a ``{var}``-named fd.
    See clause 2 of the module docstring for the probed membership.
    """
    for redirect in redirects:
        if redirect.var_fd is not None:
            return True
        if target_fd_of(redirect) == 0:
            return True
    return False


def null_command_status(state: 'ShellState',
                        redirects: List['Redirect']) -> int:
    """The status of a null command whose redirections already applied cleanly.

    Callers own clause 1 (they hold the redirect guard and return 1 themselves);
    this decides clauses 2 and 3.
    """
    if redirects and null_command_redirects_stdin(redirects):
        return 0
    status = state.last_cmdsub_status
    return status if status is not None else 0
