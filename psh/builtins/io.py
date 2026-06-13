"""I/O related builtins (echo, pwd)."""

import os
from typing import TYPE_CHECKING, List, Tuple

from ..utils.escapes import process_echo_escapes
from ..utils.printf_formatter import format_printf
from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


def process_escapes(text: str) -> Tuple[str, bool]:
    """Process echo-dialect backslash escapes; see psh/utils/escapes.py.

    Kept as a thin alias because the print builtin and echo both import
    it from here.
    """
    return process_echo_escapes(text)


@builtin
class EchoBuiltin(Builtin):
    """Echo arguments to stdout."""

    @property
    def name(self) -> str:
        return "echo"

    @property
    def synopsis(self) -> str:
        return "echo [-neE] [arg ...]"

    @property
    def description(self) -> str:
        return "Display text"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Echo arguments to stdout."""
        # Parse flags
        suppress_newline, interpret_escapes, start_idx = self._parse_flags(args)

        # Get output text
        output = ' '.join(args[start_idx:]) if len(args) > start_idx else ''


        # Process escape sequences if needed
        if interpret_escapes:
            output, terminate = self._process_escapes(output)
            if terminate:
                suppress_newline = True

        # Write output
        self._write_output(output, suppress_newline, shell)
        return 0

    def _parse_flags(self, args: List[str]) -> Tuple[bool, bool, int]:
        """Parse echo flags and return (suppress_newline, interpret_escapes, start_index)."""
        suppress_newline = False
        interpret_escapes = False
        arg_index = 1

        while arg_index < len(args):
            arg = args[arg_index]
            if arg == '--':
                arg_index += 1
                break
            elif arg.startswith('-') and len(arg) > 1 and all(c in 'neE' for c in arg[1:]):
                # Process flag characters
                for flag in arg[1:]:
                    if flag == 'n':
                        suppress_newline = True
                    elif flag == 'e':
                        interpret_escapes = True
                    elif flag == 'E':
                        interpret_escapes = False
                arg_index += 1
            else:
                # Not a flag, stop parsing
                break

        return suppress_newline, interpret_escapes, arg_index

    def _process_escapes(self, text: str) -> Tuple[str, bool]:
        """Process escape sequences. Returns (processed_text, terminate_output)."""
        return process_escapes(text)

    def _write_output(self, text: str, suppress_newline: bool, shell: 'Shell'):
        """Write output to appropriate file descriptor."""
        # Add newline if not suppressed
        if not suppress_newline:
            text += '\n'

        if shell.state.options.get('debug-exec'):
            self.write_error_line(
                f"DEBUG EchoBuiltin: in_forked_child={shell.state.in_forked_child}", shell)
            self.write_error_line(
                f"DEBUG EchoBuiltin: Writing text: {repr(text[:50])}", shell)

        self.write(text, shell)

    @property
    def help(self) -> str:
        return """echo: echo [-neE] [arg ...]

    Display arguments separated by spaces, followed by a newline.
    If no arguments are given, print a blank line.

    Options:
        -n    Do not output the trailing newline
        -e    Enable interpretation of backslash escape sequences
        -E    Disable interpretation of backslash escapes (default)

    Escape sequences (with -e):
        \\a    Alert (bell)
        \\b    Backspace
        \\c    Suppress further output
        \\e    Escape character
        \\f    Form feed
        \\n    New line
        \\r    Carriage return
        \\t    Horizontal tab
        \\v    Vertical tab
        \\\\    Backslash
        \\0nnn Character with octal value nnn (0 prefix required)
        \\xhh  Character with hex value hh (1 to 2 digits)
        \\uhhhh    Unicode character with hex value hhhh (4 digits)
        \\Uhhhhhhhh Unicode character with hex value hhhhhhhh (8 digits)"""


@builtin
class PrintfBuiltin(Builtin):
    """Format and print data according to POSIX printf specification.

    The formatting engine itself is pure and lives in
    psh/utils/printf_formatter.py (bash 5.2 semantics, directly
    unit-testable); this builtin only handles option parsing, output,
    diagnostics, and applying %n / -v variable assignments.
    """

    @property
    def name(self) -> str:
        return "printf"

    @property
    def synopsis(self) -> str:
        return "printf [-v var] format [arguments ...]"

    @property
    def description(self) -> str:
        return "Format and print data according to the format string"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Format and print data according to the format string."""
        # printf -v var: store the result in var instead of printing (bash)
        target_var = None
        argv = args
        if len(argv) > 1 and argv[1] == '-v':
            if len(argv) < 3:
                self.error("-v: option requires an argument", shell)
                return 2
            target_var = argv[2]
            argv = [argv[0]] + argv[3:]
        if len(argv) > 1 and argv[1] == '--':
            argv = [argv[0]] + argv[2:]

        if len(argv) < 2:
            self.error("usage: printf [-v var] format [arguments]", shell)
            return 2

        result = format_printf(argv[1], argv[2:])

        for message in result.errors:
            self.error(message, shell)
        # %n assignments (number of characters written so far)
        for name, value in result.assignments:
            shell.expansion_manager.set_var_or_array_element(name, value)

        if target_var is not None:
            shell.expansion_manager.set_var_or_array_element(
                target_var, result.output)
        else:
            self.write(result.output, shell)
        return result.exit_code

    @property
    def help(self) -> str:
        return """printf: printf format [arguments ...]

    Format and print data according to the POSIX printf specification.

    Format specifiers:
        %d, %i    Signed decimal integer
        %o        Unsigned octal integer
        %u        Unsigned decimal integer
        %x, %X    Unsigned hexadecimal integer (lowercase/uppercase)
        %f, %F    Floating point (lowercase/uppercase)
        %e, %E    Scientific notation (lowercase/uppercase)
        %g, %G    General format (shortest of %f or %e)
        %a, %A    Hexadecimal floating point (lowercase/uppercase)
        %c        Single character
        %s        String
        %b        String with backslash escapes interpreted
        %q        String quoted for reuse as shell input
        %%        Literal percent sign

    Flags:
        -         Left-justify output
        +         Always show sign for signed conversions
        (space)   Prefix positive numbers with space
        #         Use alternate form (0x for hex, 0 for octal)
        0         Zero-pad numeric output

    Width and precision:
        %10s      Minimum field width of 10
        %.5s      Maximum string width of 5
        %10.2f    Field width 10, precision 2
        %*.*f     Width and precision from arguments

    Escape sequences:
        \\a    Alert (bell)
        \\b    Backspace
        \\f    Form feed
        \\n    Newline
        \\r    Carriage return
        \\t    Tab
        \\v    Vertical tab
        \\\\    Backslash
        \\nnn  Octal character (up to 3 digits)
        \\xhh  Hexadecimal character (2 digits)
        \\uhhhh    Unicode character (4 hex digits)
        \\Uhhhhhhhh Unicode character (8 hex digits)

    POSIX behavior:
        - Arguments are reused if more format specifiers than arguments
        - Missing numeric arguments default to 0
        - Missing string arguments default to empty string
        - Invalid numeric strings convert using leading digits or 0

    Exit Status:
    Returns 0 on success, 1 on format error, 2 on usage error."""


@builtin
class PwdBuiltin(Builtin):
    """Print working directory."""

    @property
    def name(self) -> str:
        return "pwd"

    @property
    def synopsis(self) -> str:
        return "pwd"

    @property
    def description(self) -> str:
        return "Print the current working directory"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Print the current working directory."""
        try:
            cwd = os.getcwd()
            self.write_line(cwd, shell)
            return 0
        except OSError as e:
            self.error(str(e), shell)
            return 1

    @property
    def help(self) -> str:
        return """pwd: pwd
    Print the current working directory.

    Display the full pathname of the current working directory.

    Exit Status:
    Returns 0 unless an error occurs while reading the pathname of the
    current directory."""
