"""Shell option handlers."""

import string
from typing import TYPE_CHECKING

from .exceptions import UnboundVariableError

if TYPE_CHECKING:
    from ..shell import Shell
    from .state import ShellState

# Characters that need no quoting in `set -x` trace output. Anything else (a
# space, an empty word, or a shell metacharacter such as ;, |, (, ), [, ], *,
# ?, $, quotes, ...) makes bash single-quote the word: `echo "a b"` traces as
# `+ echo 'a b'`, `[ 0 -lt 2 ]` as `+ '[' 0 -lt 2 ']'`.
_XTRACE_SAFE_CHARS = frozenset(string.ascii_letters + string.digits + '_-./,:=@%+')


def xtrace_quote(word: str) -> str:
    """Quote a word for `set -x` output the way bash does.

    A word that is non-empty and made only of unquoted-safe characters is
    emitted as-is; otherwise it is single-quoted, with embedded single quotes
    rendered as the usual ``'\\''`` close-reopen.
    """
    if word and all(c in _XTRACE_SAFE_CHARS for c in word):
        return word
    return "'" + word.replace("'", "'\\''") + "'"


class OptionHandler:
    """Handle shell option behaviors.

    errexit (set -e) and pipefail policy live in the executor (errexit is
    enforced structurally at statement-list level; pipefail is computed inline
    in the pipeline executor), so they are not duplicated here.
    """

    @staticmethod
    def check_unset_variable(state: 'ShellState', var_name: str,
                           in_expansion: bool = False) -> None:
        """
        Check if accessing unset variable should cause error.

        Args:
            state: Shell state
            var_name: Variable name being accessed
            in_expansion: True if in parameter expansion context like ${var:-default}

        Raises:
            UnboundVariableError: If variable is unset and nounset is enabled
        """
        if not state.options.get('nounset', False):
            return

        # Special handling for parameter expansions that provide defaults
        if in_expansion:
            return

        # Special handling for $@ and $* when no positional params
        if var_name in ['@', '*'] and not state.positional_params:
            # Bash allows these even with nounset
            return

        # Special variables that always have a value
        if var_name in ['?', '$', '#', '0']:
            return

        # Positional parameters
        if var_name.isdigit():
            index = int(var_name)
            if index > len(state.positional_params):
                raise UnboundVariableError(f"${var_name}: unbound variable")
            return

        # Check if variable exists in shell variables or environment
        # We need to check explicitly because get_variable returns a default
        if (state.scope_manager.get_variable(var_name) is None and
            var_name not in state.env):
            raise UnboundVariableError(f"{var_name}: unbound variable")

    @staticmethod
    def print_xtrace(shell: 'Shell', command_parts: list) -> None:
        """
        Print xtrace output for a command.

        Args:
            shell: The shell (its expansion manager expands PS4 like bash)
            command_parts: List of command parts (already expanded)
        """
        state = shell.state
        if not state.options.get('xtrace', False):
            return

        ps4 = shell.expansion_manager.expand_ps4()
        trace_line = ps4 + ' '.join(xtrace_quote(str(part)) for part in command_parts)
        print(trace_line, file=state.stderr)
        state.stderr.flush()  # Ensure trace appears before command output
