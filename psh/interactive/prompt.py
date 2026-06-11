"""Prompt expansion for PS1 and PS2 variables.

This module handles the expansion of special escape sequences in shell prompts,
similar to bash's prompt expansion feature.
"""

import datetime
import os
import pwd
import socket
from typing import Optional


class PromptExpander:
    """Handles expansion of prompt escape sequences."""

    def __init__(self, shell):
        self.shell = shell
        self._hostname = None
        self._username = None

    def expand_prompt(self, prompt: str) -> str:
        """Expand prompt escape sequences in the given string.

        Supported sequences:
        \\a - ASCII bell character (07)
        \\d - date in "Weekday Month Date" format
        \\e - ASCII escape character (033)
        \\h - hostname up to first '.'
        \\H - full hostname
        \\n - newline
        \\r - carriage return
        \\s - shell name (basename of $0)
        \\t - current time in 24-hour HH:MM:SS format
        \\T - current time in 12-hour HH:MM:SS format
        \\@ - current time in 12-hour am/pm format
        \\A - current time in 24-hour HH:MM format
        \\u - username
        \\v - shell version (short)
        \\V - shell version (long)
        \\w - current working directory
        \\W - basename of current working directory
        \\! - history number
        \\# - command number
        \\$ - # if uid=0, else $
        \\nnn - character with octal code nnn
        \\\\ - literal backslash
        \\[ - begin non-printing sequence
        \\] - end non-printing sequence

        ANSI Color Codes (use within \\[ and \\] for proper cursor positioning):
        Example: PS1='\\[\\e[32m\\]\\u@\\h\\[\\e[0m\\]:\\w\\$ '

        Colors: 30=black, 31=red, 32=green, 33=yellow, 34=blue, 35=magenta, 36=cyan, 37=white
        Background: 40-47 (same color order)
        Attributes: 0=reset, 1=bold, 2=dim, 4=underline, 5=blink, 7=reverse
        """
        if not prompt:
            return prompt

        result = []
        i = 0
        while i < len(prompt):
            if prompt[i] == '\\' and i + 1 < len(prompt):
                next_char = prompt[i + 1]
                expanded = self._expand_escape(next_char)
                if expanded is not None:
                    result.append(expanded)
                    i += 2
                else:
                    # Check for octal sequence
                    if i + 3 < len(prompt) and all(c in '01234567' for c in prompt[i+1:i+4]):
                        octal_value = int(prompt[i+1:i+4], 8)
                        result.append(chr(octal_value))
                        i += 4
                    else:
                        # Not a recognized escape, keep the backslash
                        result.append(prompt[i])
                        i += 1
            else:
                result.append(prompt[i])
                i += 1

        return ''.join(result)

    def _expand_escape(self, char: str) -> Optional[str]:
        """Expand a single escape character."""
        expansions = {
            'a': '\a',  # ASCII bell
            'd': self._get_date(),
            'e': '\033',  # ASCII escape
            'h': self._get_hostname(short=True),
            'H': self._get_hostname(short=False),
            'n': '\n',
            'r': '\r',
            's': 'psh',  # Shell name
            't': self._get_time_24(),
            'T': self._get_time_12(),
            '@': self._get_time_ampm(),
            'A': self._get_time_24_short(),
            'u': self._get_username(),
            'v': self._get_version_short(),
            'V': self._get_version_long(),
            'w': self._get_cwd(),
            'W': self._get_cwd_basename(),
            '!': self._get_history_number(),
            '#': self._get_command_number(),
            '$': '#' if os.geteuid() == 0 else '$',
            '\\': '\\',
            '[': '\001',  # Start non-printing sequence (readline)
            ']': '\002',  # End non-printing sequence (readline)
        }

        return expansions.get(char)

    def _get_date(self) -> str:
        """Get date in 'Weekday Month Date' format."""
        now = datetime.datetime.now()
        return now.strftime('%a %b %d')

    def _get_time_24(self) -> str:
        """Get time in 24-hour HH:MM:SS format."""
        return datetime.datetime.now().strftime('%H:%M:%S')

    def _get_time_12(self) -> str:
        """Get time in 12-hour HH:MM:SS format."""
        return datetime.datetime.now().strftime('%I:%M:%S')

    def _get_time_ampm(self) -> str:
        """Get time in 12-hour am/pm format."""
        return datetime.datetime.now().strftime('%I:%M %p')

    def _get_time_24_short(self) -> str:
        """Get time in 24-hour HH:MM format."""
        return datetime.datetime.now().strftime('%H:%M')

    def _get_hostname(self, short: bool = True) -> str:
        """Get hostname (cached)."""
        if self._hostname is None:
            try:
                self._hostname = socket.gethostname()
            except OSError:
                self._hostname = 'localhost'

        if short:
            return self._hostname.split('.')[0]
        return self._hostname

    def _get_username(self) -> str:
        """Get username (cached)."""
        if self._username is None:
            try:
                self._username = pwd.getpwuid(os.getuid()).pw_name
            except (KeyError, OSError):
                self._username = os.environ.get('USER', 'unknown')
        return self._username

    def _get_version_short(self) -> str:
        """Get short version string."""
        from ..version import __version__
        # Extract major.minor from version like "0.25.0"
        parts = __version__.split('.')
        if len(parts) >= 2:
            return f"{parts[0]}.{parts[1]}"
        return __version__

    def _get_version_long(self) -> str:
        """Get long version string."""
        from ..version import __version__
        return __version__

    def _get_cwd(self) -> str:
        """Get current working directory with ~ substitution."""
        cwd = os.getcwd()
        home = os.path.expanduser('~')
        if cwd.startswith(home):
            cwd = '~' + cwd[len(home):]
        return cwd

    def _get_cwd_basename(self) -> str:
        """Get basename of current working directory."""
        cwd = self._get_cwd()
        if cwd == '~':
            return cwd
        return os.path.basename(cwd) or '/'

    def _get_history_number(self) -> str:
        """Get the current history number."""
        return str(len(self.shell.history) + 1)

    def _get_command_number(self) -> str:
        """Get the current command number."""
        return str(self.shell.command_number + 1)
