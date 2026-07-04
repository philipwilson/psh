"""Interactive EOF policy: bash's ignoreeof / IGNOREEOF semantics.

bash 5.2 truth table (PTY-probed, tmp/probes-r17t2-interactive/):

- With ignoreeof active, Ctrl-D at the prompt prints
  ``Use "exit" to leave the shell.`` on stderr and the shell stays.
- ``IGNOREEOF=N`` ignores N consecutive EOFs (each prints the message);
  EOF number N+1 exits. ``set -o ignoreeof`` binds ``IGNOREEOF=10``.
- An empty or non-numeric ``IGNOREEOF`` means 10 (bash's ``all_digits``
  check); ``IGNOREEOF=0`` exits on the first EOF.
- The consecutive-EOF counter is reset by a (non-blank) command line —
  blank lines do NOT reset it.
- The EOF that finally exits behaves "as if the user typed exit"
  (bash parse.y handle_eof_input_unit), so the stopped-jobs exit guard
  (JobManager.confirm_exit_with_stopped_jobs) applies to it too.
- At a PS2 continuation prompt, EOF with ignoreeof active abandons the
  unfinished command with the usual syntax error but the shell stays
  (no Use-"exit" message); without ignoreeof it exits after the error.

The option <-> variable coupling (bash sv_ignoreeof): the ``ignoreeof``
option tracks whether the IGNOREEOF *variable* exists — see
ShellState._sync_exported_variable and SetBuiltin._set_long_option.
"""

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..core.state import ShellState

EOF_IGNORED_MESSAGE = 'Use "exit" to leave the shell.'


def ignoreeof_limit(state: 'ShellState') -> Optional[int]:
    """The number of consecutive EOFs to ignore, or None when EOF exits.

    The IGNOREEOF variable is authoritative (its presence is what
    activates the feature in bash); the bare ``ignoreeof`` option is a
    fallback for embedders/tests that set the option without the
    variable (limit 10, the same default ``set -o ignoreeof`` binds).
    """
    value = state.scope_manager.get_variable('IGNOREEOF')
    if value is None:
        value = state.env.get('IGNOREEOF')
    if value is not None:
        # bash: a numeric value is the limit; empty/non-numeric mean 10.
        if value and all(c in '0123456789' for c in value):
            return int(value)
        return 10
    if state.options.get('ignoreeof'):
        return 10
    return None
