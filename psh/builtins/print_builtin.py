"""The ``print`` builtin, compatible with the zsh ``print`` command.

This is a zsh-style extension (not POSIX/bash). Unlike ``echo``, ``print``
interprets backslash escape sequences by default; use ``-r`` to disable that.

Supported flags (see the user guide for the full reference):

    -n          do not add the trailing terminator (newline)
    -r          raw: do not interpret escape sequences
    -R          BSD echo emulation: raw output; only -e and -n are recognised
                after it, all other words are arguments
    -e          (re)enable escape interpretation (mainly useful after -R)
    -l          separate arguments with newlines instead of spaces
    -N          use a NUL byte as both separator and terminator
    -s          append the arguments to the history list instead of printing
    -u N        write to file descriptor N (e.g. -u2 or -u 2)
    -f FORMAT   format the arguments using printf-style FORMAT
    -m          treat the first argument as a pattern and print only the
                remaining arguments that match it
    -o          sort the arguments in ascending order
    -O          sort the arguments in descending order
    -i          with -o/-O, sort case-insensitively
    -P          perform prompt expansion on each argument (using psh's
                bash-style prompt escapes, e.g. \\h, \\u, \\d)

Unsupported zsh flags (accepted nowhere; reported as an error): -z, -c, -C,
-D, -x, -X, -a, -p.
"""

import sys
from typing import TYPE_CHECKING, List, Tuple

from ..core.exceptions import PshError
from ..expansion.pattern import match_shell_pattern
from ..utils.escapes import process_echo_escapes
from ..utils.printf_formatter import format_printf
from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


class PrintOptionError(PshError):
    """Raised when option parsing fails."""


@builtin
class PrintBuiltin(Builtin):
    """Print arguments (zsh-compatible)."""

    @property
    def name(self) -> str:
        return "print"

    @property
    def synopsis(self) -> str:
        return "print [-nrRelNsoOiPm] [-u fd] [-f format] [arg ...]"

    @property
    def description(self) -> str:
        return "Display arguments (zsh-compatible print)"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        try:
            opts, rest = self._parse_options(args)
        except PrintOptionError as e:
            self.error(str(e), shell)
            return 2

        # -m: first argument is a pattern; keep matching arguments only.
        if opts['match']:
            if not rest:
                # No pattern supplied: nothing to print.
                rest = []
            else:
                pattern = rest[0]
                rest = [a for a in rest[1:]
                        if match_shell_pattern(a, pattern)]

        # -o / -O: sort arguments (optionally case-insensitively with -i).
        if opts['sort'] or opts['rsort']:
            key = (lambda s: s.lower()) if opts['insensitive'] else None
            rest = sorted(rest, key=key, reverse=opts['rsort'])

        # -P: prompt expansion on each argument.
        if opts['prompt']:
            from ..interactive.prompt import PromptExpander
            expander = PromptExpander(shell)
            rest = [expander.decode_escapes(a) for a in rest]

        # -f: printf-style formatting takes over output entirely.
        if opts['format'] is not None:
            result = format_printf(opts['format'], rest)
            for message in result.errors:
                self.error(message, shell)
            write_rc = self._write(result.output, opts['fd'], shell)
            # A write failure fails the command even if the format was valid.
            return result.exit_code or write_rc

        # -s: append to history instead of printing.
        if opts['history']:
            command = ' '.join(rest)
            shell.add_history(command)
            return 0

        # Escape processing (default on, unless raw).
        terminate = False
        if opts['escapes']:
            processed = []
            for a in rest:
                text, term = process_echo_escapes(a)
                processed.append(text)
                if term:
                    terminate = True
                    break
            rest = processed

        separator = opts['separator']
        output = separator.join(rest)

        if not terminate and not opts['no_newline']:
            output += opts['terminator']

        return self._write(output, opts['fd'], shell)

    def _parse_options(self, args: List[str]) -> Tuple[dict, List[str]]:
        """Parse print options; returns (options dict, remaining args)."""
        opts = {
            'no_newline': False,
            'escapes': True,       # print interprets escapes by default
            'separator': ' ',
            'terminator': '\n',
            'history': False,
            'fd': 1,
            'format': None,
            'match': False,
            'sort': False,
            'rsort': False,
            'insensitive': False,
            'prompt': False,
        }

        # Deliberately NOT parse_flags(): print follows zsh's grammar — a
        # bare '-' ends options, and -R rewrites the option set mid-walk.
        i = 1
        bsd_mode = False  # set by -R: only -e/-n recognised afterwards
        while i < len(args):
            arg = args[i]
            # Both '--' and a lone '-' terminate option parsing and are consumed
            # (zsh treats a bare '-' as an end-of-options marker).
            if arg == '--' or arg == '-':
                i += 1
                break
            if not arg.startswith('-'):
                break

            flags = arg[1:]

            if bsd_mode:
                # After -R, only -e and -n (in any combination) are options.
                if not all(c in 'en' for c in flags):
                    break

            j = 0
            while j < len(flags):
                c = flags[j]
                if c == 'n':
                    opts['no_newline'] = True
                elif c == 'r':
                    opts['escapes'] = False
                elif c == 'R':
                    opts['escapes'] = False
                    bsd_mode = True
                elif c == 'e':
                    opts['escapes'] = True
                elif c == 'l':
                    opts['separator'] = '\n'
                elif c == 'N':
                    opts['separator'] = '\0'
                    opts['terminator'] = '\0'
                elif c == 's':
                    opts['history'] = True
                elif c == 'o':
                    opts['sort'] = True
                elif c == 'O':
                    opts['rsort'] = True
                elif c == 'i':
                    opts['insensitive'] = True
                elif c == 'P':
                    opts['prompt'] = True
                elif c == 'm':
                    opts['match'] = True
                elif c == 'u':
                    # -u takes a numeric fd: attached (-u2) or separate (-u 2).
                    rest_of_arg = flags[j + 1:]
                    if rest_of_arg:
                        fd_str = rest_of_arg
                    else:
                        if i + 1 >= len(args):
                            raise PrintOptionError("-u: option requires an argument")
                        i += 1
                        fd_str = args[i]
                    try:
                        opts['fd'] = int(fd_str)
                    except ValueError:
                        raise PrintOptionError(f"-u: {fd_str}: invalid file descriptor") from None
                    break
                elif c == 'f':
                    # -f takes a format string: attached (-f'%s') or separate.
                    rest_of_arg = flags[j + 1:]
                    if rest_of_arg:
                        opts['format'] = rest_of_arg
                    else:
                        if i + 1 >= len(args):
                            raise PrintOptionError("-f: option requires an argument")
                        i += 1
                        opts['format'] = args[i]
                    break
                elif c in 'zcCDxXap':
                    raise PrintOptionError(f"-{c}: unsupported option")
                else:
                    raise PrintOptionError(f"-{c}: invalid option")
                j += 1

            i += 1

        return opts, args[i:]

    def _write(self, text: str, fd: int, shell: 'Shell') -> int:
        """Write ``text`` to the requested file descriptor.

        Returns 0 on success, 1 on a write/descriptor failure (`print -u99`
        reports the bad descriptor and the whole command fails, matching zsh
        — the old code caught the error but returned success)."""
        is_forked_child = shell.state.in_forked_child

        # fd 1 in the parent process should go through shell.stdout so
        # redirections and capture work; same for fd 2 and shell.stderr.
        if fd == 1 and not is_forked_child:
            stream = shell.stdout if hasattr(shell, 'stdout') else sys.stdout
            stream.write(text)
            stream.flush()
            return 0
        if fd == 2 and not is_forked_child:
            stream = shell.stderr if hasattr(shell, 'stderr') else sys.stderr
            stream.write(text)
            stream.flush()
            return 0

        # Otherwise write every byte directly to the numeric descriptor
        # (write-all: os.write may write fewer bytes than requested).
        try:
            self.write_all_fd(fd, text.encode('utf-8', errors='surrogateescape'))
        except OSError as e:
            self.error(f"-u: {fd}: {e.strerror}", shell)
            return 1
        return 0

    @property
    def help(self) -> str:
        return """print: print [-nrRelNsoOiPm] [-u fd] [-f format] [arg ...]

    Display arguments, compatible with the zsh print builtin.

    Unlike echo, print interprets backslash escape sequences by default;
    use -r to print arguments raw.

    Options:
        -n        Do not add the trailing newline
        -r        Raw: do not interpret escape sequences
        -R        BSD echo emulation (raw); only -e and -n follow it
        -e        (Re)enable escape interpretation
        -l        Separate arguments with newlines instead of spaces
        -N        Use a NUL byte as separator and terminator
        -s        Append arguments to the history list instead of printing
        -u fd     Write to file descriptor fd (e.g. -u2)
        -f format Format arguments using a printf-style format string
        -m        Treat the first argument as a pattern; print only the
                  remaining arguments that match it
        -o        Sort arguments ascending
        -O        Sort arguments descending
        -i        With -o/-O, sort case-insensitively
        -P        Perform prompt expansion on each argument (psh prompt
                  escapes, e.g. \\h, \\u)

    Escape sequences (when interpretation is enabled):
        \\a \\b \\c \\e \\f \\n \\r \\t \\v \\\\ \\xhh \\0nnn \\uhhhh \\Uhhhhhhhh

    Unsupported zsh options (reported as errors): -z -c -C -D -x -X -a -p

    Exit Status:
    Returns 0 on success, 2 on an option error."""
