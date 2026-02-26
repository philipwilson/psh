"""Terminal window title management.

Sets the terminal title bar via OSC 0 escape sequences to show the current
directory, shell name (or running command), and terminal dimensions.
"""

import os
import shutil
import sys


def set_terminal_title(title: str) -> None:
    """Write an OSC 0 escape sequence to set the terminal title.

    Guards on stdout being a TTY and TERM not being 'dumb'.
    """
    if not sys.stdout.isatty():
        return
    if os.environ.get('TERM') == 'dumb':
        return
    sys.stdout.write(f'\033]0;{title}\007')
    sys.stdout.flush()


def idle_title(shell) -> str:
    """Return the idle title: ``dirname — psh — cols×rows``."""
    dirname = os.path.basename(shell.state.variables.get('PWD', ''))
    cols, rows = shutil.get_terminal_size()
    return f'{dirname} \u2014 psh \u2014 {cols}\u00d7{rows}'


def command_title(cmd_str: str, shell) -> str:
    """Return a running-command title: ``dirname — cmd_str — cols×rows``."""
    dirname = os.path.basename(shell.state.variables.get('PWD', ''))
    cols, rows = shutil.get_terminal_size()
    return f'{dirname} \u2014 {cmd_str} \u2014 {cols}\u00d7{rows}'
