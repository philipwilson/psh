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

    # Escapes whose value is a fixed string — no computation, no syscalls.
    _STATIC_ESCAPES = {
        'a': '\a',     # ASCII bell
        'e': '\033',   # ASCII escape
        'n': '\n',
        'r': '\r',
        's': 'psh',    # shell name
        '\\': '\\',
    }

    def __init__(self, shell):
        self.shell = shell
        self._hostname = None
        self._username = None
        # Escape char -> zero-arg thunk. Built ONCE per expander; a single
        # escape decodes by calling ONLY its thunk, so a `\w` never triggers
        # the strftime/ttyname/geteuid/... work the other escapes would do
        # (the old code eagerly evaluated every getter to pick one).
        self._escape_thunks = {
            'd': self._get_date,
            'h': lambda: self._get_hostname(short=True),
            'H': lambda: self._get_hostname(short=False),
            'j': self._get_job_count,
            'l': self._get_tty_basename,
            't': self._get_time_24,
            'T': self._get_time_12,
            '@': self._get_time_ampm,
            'A': self._get_time_24_short,
            'u': self._get_username,
            'v': self._get_version_short,
            'V': self._get_version_long,
            'w': self._get_cwd,
            'W': self._get_cwd_basename,
            '!': self._get_history_number,
            '#': self._get_command_number,
            '$': lambda: '#' if os.geteuid() == 0 else '$',
        }

    def decode_escapes(self, prompt: str) -> str:
        """Decode the backslash escape sequences in a prompt string ONLY.

        This is the escapes-only pass (no parameter/command/arithmetic
        expansion): ``print -P`` and callers that want just the ``\\u``/``\\h``/
        ``\\w`` decoding use it. The FULL ``promptvars`` pass (escapes THEN
        ``$``-expansion) is ``PromptManager.expand_prompt`` /
        ``PromptExpander.expand_full`` — deliberately a different name so the
        two contracts don't collide.

        Supported sequences:
        \\a - ASCII bell character (07)
        \\d - date in "Weekday Month Date" format
        \\D{format} - strftime(3) format (empty format: locale time)
        \\e - ASCII escape character (033)
        \\h - hostname up to first '.'
        \\H - full hostname
        \\j - number of jobs currently managed by the shell
        \\l - basename of the shell's terminal device name
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
        return ''.join(text for text, _ in self.expand_prompt_segments(prompt))

    def expand_full(self, prompt: str, readline_markers: bool = True) -> str:
        """Full prompt expansion: backslash escapes, THEN parameter / command /
        arithmetic expansion (bash's default ``promptvars``), with escape output
        protected from the second pass.

        Used for PS1/PS2 rendering and the ``${var@P}`` operator, so both agree.
        A ``\\$``-produced ``$`` must not start a command substitution, and an
        escape's value must not be re-interpreted — so each escape-produced
        segment is replaced by a NUL sentinel before the ``$``-pass and restored
        after (verified against bash via ``${var@P}``).

        ``readline_markers`` controls the ``\\[``/``\\]`` escapes: True (PS1/PS2
        rendering) emits the ``\\001``/``\\002`` non-printing delimiters the
        renderer needs for width math; False (``${var@P}``) drops them, since
        bash's ``@P`` yields a plain string with the brackets removed (octal
        ``\\001`` and literal markers already in the value are untouched).
        """
        segments = self.expand_prompt_segments(prompt, readline_markers=readline_markers)

        protected: dict = {}
        parts = []
        for idx, (text, from_escape) in enumerate(segments):
            if from_escape:
                key = f"\x00{idx}\x00"
                protected[key] = text
                parts.append(key)
            else:
                parts.append(text)
        combined = ''.join(parts)

        if '$' in combined or '`' in combined:
            try:
                combined = self.shell.expansion_manager.expand_string_variables(combined)
            except Exception:
                # A prompt must never abort the caller; fall back to the
                # escape-decoded form on any expansion error.
                pass

        for key, text in protected.items():
            combined = combined.replace(key, text)
        return combined

    def expand_prompt_segments(self, prompt: str, readline_markers: bool = True):
        """Decode prompt escapes into ``(text, from_escape)`` segments.

        ``from_escape`` is True for text produced by a ``\\``-escape (``\\w``,
        ``\\$``, ``\\nnn``, ...) and False for raw pass-through text. The caller
        (PromptManager) uses the flag to PROTECT escape output from the
        subsequent ``$``-expansion — bash decodes escapes first, then expands,
        but a ``\\$``-produced ``$`` must not start a command substitution and
        an escape's value must not be re-interpreted (verified via ``${var@P}``).
        """
        if not prompt:
            return []

        segments = []
        raw: list = []

        def flush_raw():
            if raw:
                segments.append((''.join(raw), False))
                raw.clear()

        i = 0
        while i < len(prompt):
            if prompt[i] == '\\' and i + 1 < len(prompt):
                next_char = prompt[i + 1]
                # \D{format} consumes through the closing brace (the only
                # multi-character escape); an unclosed brace takes the
                # rest of the string as the format, and a \D with no
                # brace at all stays literal — both bash-probed.
                if next_char == 'D' and prompt[i + 2:i + 3] == '{':
                    close = prompt.find('}', i + 3)
                    fmt = prompt[i + 3:close] if close != -1 else prompt[i + 3:]
                    flush_raw()
                    segments.append((self._get_strftime(fmt), True))
                    i = close + 1 if close != -1 else len(prompt)
                    continue
                expanded = self._expand_escape(next_char, readline_markers=readline_markers)
                if expanded is not None:
                    flush_raw()
                    segments.append((expanded, True))
                    i += 2
                else:
                    # Check for octal sequence
                    if i + 3 < len(prompt) and all(c in '01234567' for c in prompt[i+1:i+4]):
                        octal_value = int(prompt[i+1:i+4], 8)
                        flush_raw()
                        segments.append((chr(octal_value), True))
                        i += 4
                    else:
                        # Not a recognized escape, keep the backslash (raw).
                        raw.append(prompt[i])
                        i += 1
            else:
                raw.append(prompt[i])
                i += 1

        flush_raw()
        return segments

    def _expand_escape(self, char: str, readline_markers: bool = True) -> Optional[str]:
        """Expand a single escape character, evaluating ONLY that escape.

        Returns ``None`` for an unrecognized escape char (the caller then tries
        the octal-``\\nnn`` rule and otherwise keeps the backslash literal).

        With ``readline_markers`` off (``${var@P}``), ``\\[``/``\\]`` decode to
        nothing rather than the ``\\001``/``\\002`` non-printing delimiters.
        """
        thunk = self._escape_thunks.get(char)
        if thunk is not None:
            return thunk()
        if char == '[':
            return '\001' if readline_markers else ''  # start non-printing (readline)
        if char == ']':
            return '\002' if readline_markers else ''  # end non-printing (readline)
        return self._STATIC_ESCAPES.get(char)

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

    def _get_strftime(self, fmt: str) -> str:
        """bash ``\\D{format}``: strftime with the given format; an empty
        format means the locale's time representation (bash uses %X)."""
        try:
            return datetime.datetime.now().strftime(fmt or '%X')
        except ValueError:
            # An invalid format (e.g. a lone trailing '%') must never
            # abort prompt rendering.
            return ''

    def _get_job_count(self) -> str:
        """Number of jobs currently managed by the shell (bash ``\\j``)."""
        job_manager = getattr(self.shell, 'job_manager', None)
        return str(len(job_manager.jobs)) if job_manager is not None else '0'

    def _get_tty_basename(self) -> str:
        """Basename of the shell's terminal device (bash ``\\l``; the
        fallback when stdin is not a terminal is the literal ``tty``,
        matching bash)."""
        try:
            return os.path.basename(os.ttyname(0))
        except (OSError, ValueError):
            return 'tty'

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
        return str(len(self.shell.state.history) + 1)

    def _get_command_number(self) -> str:
        """Get the current command number."""
        return str(self.shell.state.command_number + 1)
