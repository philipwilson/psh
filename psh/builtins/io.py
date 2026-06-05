"""I/O related builtins (echo, pwd)."""

import os
import re
import sys
from typing import TYPE_CHECKING, List, Tuple

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


def process_escapes(text: str) -> Tuple[str, bool]:
    """Process backslash escape sequences in ``text``.

    Returns ``(processed_text, terminate)`` where ``terminate`` is True when a
    ``\\c`` sequence was found (output should stop and no trailing newline is
    added). Shared by the ``echo`` and ``print`` builtins so there is a single
    escape-handling implementation.
    """
    # Check for \c first (terminates output)
    if '\\c' in text:
        text = text[:text.index('\\c')]
        return text, True

    # First, protect double backslashes by replacing them temporarily
    # Use a placeholder that won't appear in normal text
    text = text.replace('\\\\', '\x01BACKSLASH\x01')

    # Process escape sequences
    replacements = [
        ('\\n', '\n'),
        ('\\t', '\t'),
        ('\\r', '\r'),
        ('\\b', '\b'),
        ('\\f', '\f'),
        ('\\a', '\a'),
        ('\\v', '\v'),
        ('\\e', '\x1b'),  # Escape character
        ('\\E', '\x1b'),  # Escape character (alternative)
    ]

    # Apply simple replacements
    for old, new in replacements:
        text = text.replace(old, new)

    # Handle hex sequences \xhh
    def replace_hex(match):
        hex_str = match.group(1)
        try:
            return chr(int(hex_str, 16))
        except ValueError:
            return match.group(0)
    text = re.sub(r'\\x([0-9a-fA-F]{1,2})', replace_hex, text)

    # Handle unicode sequences \uhhhh
    def replace_unicode4(match):
        hex_str = match.group(1)
        try:
            return chr(int(hex_str, 16))
        except ValueError:
            return match.group(0)
    text = re.sub(r'\\u([0-9a-fA-F]{4})', replace_unicode4, text)

    # Handle unicode sequences \Uhhhhhhhh
    def replace_unicode8(match):
        hex_str = match.group(1)
        try:
            return chr(int(hex_str, 16))
        except ValueError:
            return match.group(0)
    text = re.sub(r'\\U([0-9a-fA-F]{8})', replace_unicode8, text)

    # Handle octal sequences \nnn
    def replace_octal(match):
        octal_str = match.group(1)
        try:
            value = int(octal_str, 8)
            if value <= 255:  # Octal values should be in byte range
                return chr(value)
            else:
                return match.group(0)
        except ValueError:
            return match.group(0)
    # Match \0nnn format (with explicit 0) - up to 3 octal digits after \0
    # or \nnn where n starts with 0-3 (for values 0-255 in octal)
    text = re.sub(r'\\(0[0-7]{1,3}|[0-3][0-7]{2})', replace_octal, text)

    # Finally restore protected backslashes
    text = text.replace('\x01BACKSLASH\x01', '\\')

    return text, False


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

        # DEBUG: Log output method
        if shell.state.options.get('debug-exec'):
            print(f"DEBUG EchoBuiltin: _in_forked_child={getattr(shell.state, '_in_forked_child', False)}", file=sys.stderr)
            print(f"DEBUG EchoBuiltin: shell.stdout={getattr(shell, 'stdout', 'N/A')}", file=sys.stderr)
            print(f"DEBUG EchoBuiltin: shell.state.stdout={getattr(shell.state, 'stdout', 'N/A')}", file=sys.stderr)
            print(f"DEBUG EchoBuiltin: sys.stdout={sys.stdout}", file=sys.stderr)
            print(f"DEBUG EchoBuiltin: Writing text: {repr(text[:50])}", file=sys.stderr)

        # Check if we're in a child process (forked for pipeline/background)
        is_forked_child = hasattr(shell.state, '_in_forked_child') and shell.state._in_forked_child
        is_eval_test_mode = hasattr(shell.state, 'eval_test_mode') and shell.state.eval_test_mode

        if is_forked_child and not is_eval_test_mode:
            # In child process and not in eval test mode, write directly to fd 1
            output_bytes = text.encode('utf-8', errors='replace')
            os.write(1, output_bytes)
        else:
            # In parent process OR in eval test mode, use shell.stdout to respect redirections/capture
            output = shell.stdout if hasattr(shell, 'stdout') else sys.stdout
            # DEBUG: Log actual output stream
            if shell.state.options.get('debug-exec'):
                print(f"DEBUG EchoBuiltin: Using output stream: {output}", file=sys.stderr)
            output.write(text)
            output.flush()

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
    """Format and print data according to POSIX printf specification."""

    @property
    def name(self) -> str:
        return "printf"

    @property
    def synopsis(self) -> str:
        return "printf format [arguments ...]"

    @property
    def description(self) -> str:
        return "Format and print data according to the format string"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Format and print data according to the format string."""
        if len(args) < 2:
            self.error("usage: printf format [arguments ...]", shell)
            return 2

        format_str = args[1]
        arguments = args[2:]

        try:
            # Process format string with POSIX-compliant behavior
            output = self._process_format_string_posix(format_str, arguments)
            self._write_output(output, shell)
            return 0
        except (ValueError, TypeError, KeyError) as e:
            self.error(f"printf: {str(e)}", shell)
            return 1

    def _process_format_string_posix(self, format_str: str, arguments: list) -> str:
        """Process format string with POSIX-compliant behavior including argument cycling."""
        if not arguments:
            # No arguments - just process escape sequences in format string
            return self._process_escapes_only(format_str)

        result = []
        arg_index = 0

        # POSIX: Repeat format string until all arguments are consumed
        while arg_index < len(arguments):
            i = 0
            format_consumed_args = False

            while i < len(format_str):
                if format_str[i] == '%' and i + 1 < len(format_str):
                    if format_str[i + 1] == '%':
                        # Literal %
                        result.append('%')
                        i += 2
                    else:
                        # Parse format specifier
                        fmt_spec, end_pos = self._parse_format_specifier_enhanced(format_str, i)
                        if fmt_spec:
                            # Format the argument
                            formatted_value = self._format_argument_posix(fmt_spec, arguments, arg_index)
                            result.append(formatted_value)
                            # Advance argument index for consuming specifiers
                            if fmt_spec['type'] not in '%':  # All format types except %% consume arguments
                                arg_index += 1
                                format_consumed_args = True
                            i = end_pos
                        else:
                            # Invalid format specifier
                            result.append(format_str[i])
                            i += 1
                elif format_str[i] == '\\' and i + 1 < len(format_str):
                    # Handle escape sequences
                    escape_char, skip = self._process_escape_sequence(format_str, i)
                    result.append(escape_char)
                    i += skip
                else:
                    result.append(format_str[i])
                    i += 1

            # If format string didn't consume any arguments, break to avoid infinite loop
            if not format_consumed_args:
                break

        return ''.join(result)

    def _process_escapes_only(self, format_str: str) -> str:
        """Process escape sequences and %% literals in format string (no format specifiers with arguments)."""
        result = []
        i = 0

        while i < len(format_str):
            if format_str[i] == '%' and i + 1 < len(format_str):
                if format_str[i + 1] == '%':
                    # Literal %
                    result.append('%')
                    i += 2
                else:
                    # Single % without matching format - treat as literal
                    result.append(format_str[i])
                    i += 1
            elif format_str[i] == '\\' and i + 1 < len(format_str):
                escape_char, skip = self._process_escape_sequence(format_str, i)
                result.append(escape_char)
                i += skip
            else:
                result.append(format_str[i])
                i += 1

        return ''.join(result)

    def _write_output(self, text: str, shell: 'Shell'):
        """Write output to appropriate file descriptor."""
        # Check if we're in a child process (forked for pipeline/background)
        is_forked_child = hasattr(shell.state, '_in_forked_child') and shell.state._in_forked_child
        is_eval_test_mode = hasattr(shell.state, 'eval_test_mode') and shell.state.eval_test_mode

        if is_forked_child and not is_eval_test_mode:
            # In child process and not in eval test mode, write directly to fd 1
            output_bytes = text.encode('utf-8', errors='replace')
            os.write(1, output_bytes)
        else:
            # In parent process OR in eval test mode, use shell.stdout to respect redirections/capture
            output = shell.stdout if hasattr(shell, 'stdout') else sys.stdout
            output.write(text)
            output.flush()

    def _parse_format_specifier_enhanced(self, format_str: str, start: int) -> tuple:
        """Parse a POSIX-compliant format specifier starting at '%'.

        Returns:
            tuple: (spec_dict, end_position) or (None, 0) if invalid
        """
        if format_str[start] != '%':
            return None, 0

        i = start + 1
        spec = {
            'flags': '',
            'width': '',
            'precision': '',
            'type': '',
            'original': ''
        }

        # Parse flags (-+# 0)
        while i < len(format_str) and format_str[i] in '-+# 0':
            if format_str[i] not in spec['flags']:  # Avoid duplicate flags
                spec['flags'] += format_str[i]
            i += 1

        # Parse width (can be * for dynamic width)
        if i < len(format_str) and format_str[i] == '*':
            spec['width'] = '*'
            i += 1
        else:
            while i < len(format_str) and format_str[i].isdigit():
                spec['width'] += format_str[i]
                i += 1

        # Parse precision (.number or .*)
        if i < len(format_str) and format_str[i] == '.':
            spec['precision'] = '.'
            i += 1
            if i < len(format_str) and format_str[i] == '*':
                spec['precision'] += '*'
                i += 1
            else:
                while i < len(format_str) and format_str[i].isdigit():
                    spec['precision'] += format_str[i]
                    i += 1

        # Parse type specifier (POSIX: diouxXeEfFgGaAcspn%)
        if i < len(format_str) and format_str[i] in 'diouxXeEfFgGaAcspn%':
            spec['type'] = format_str[i]
            i += 1
            spec['original'] = format_str[start:i]
            return spec, i

        return None, 0

    def _format_argument_posix(self, spec: dict, arguments: list, arg_index: int) -> str:
        """Format an argument according to POSIX printf specification."""
        # Get argument value with cycling
        arg_value = self._get_argument_value(arguments, arg_index)

        fmt_type = spec['type']

        if fmt_type == 's':
            return self._format_string(arg_value, spec)
        elif fmt_type in 'diouxX':
            return self._format_integer(arg_value, spec)
        elif fmt_type in 'eEfFgGaA':
            return self._format_float(arg_value, spec)
        elif fmt_type == 'c':
            return self._format_character(arg_value, spec)
        elif fmt_type == '%':
            return '%'
        else:
            # Unknown format specifier - POSIX behavior is implementation-defined
            return f"%{spec['type']}"

    def _get_argument_value(self, arguments: list, arg_index: int) -> str:
        """Get argument value with POSIX cycling behavior."""
        if arg_index < len(arguments):
            return arguments[arg_index]
        else:
            # POSIX: missing arguments are treated as empty string or 0
            return ''

    def _format_string(self, value: str, spec: dict) -> str:
        """Format string according to spec."""
        # Apply precision (max chars)
        if spec['precision'] and spec['precision'] != '.':
            precision = int(spec['precision'][1:]) if spec['precision'][1:] else 0
            value = value[:precision]

        # Apply width and alignment
        width = int(spec['width']) if spec['width'] and spec['width'] != '*' else 0
        if width > 0:
            if '-' in spec['flags']:
                return value.ljust(width)
            else:
                return value.rjust(width)

        return value

    def _format_integer(self, value: str, spec: dict) -> str:
        """Format integer according to spec."""
        # Convert to integer with POSIX rules
        try:
            # POSIX: leading digits are used, rest ignored
            import re
            match = re.match(r'^[+-]?\d+', value.strip())
            if match:
                num_value = int(match.group())
            else:
                num_value = 0
        except (ValueError, AttributeError):
            num_value = 0

        fmt_type = spec['type']

        # Convert to appropriate base
        if fmt_type == 'd' or fmt_type == 'i':
            formatted = str(num_value)
        elif fmt_type == 'o':
            formatted = oct(abs(num_value))[2:]  # Remove '0o' prefix
            if num_value < 0:
                formatted = '-' + formatted
        elif fmt_type == 'x':
            formatted = hex(abs(num_value))[2:]  # Remove '0x' prefix
            if num_value < 0:
                formatted = '-' + formatted
        elif fmt_type == 'X':
            formatted = hex(abs(num_value))[2:].upper()
            if num_value < 0:
                formatted = '-' + formatted
        elif fmt_type == 'u':
            # Unsigned - treat negative as large positive
            if num_value < 0:
                num_value = (1 << 32) + num_value  # 32-bit wrap
            formatted = str(num_value)
        else:
            formatted = str(num_value)

        # Apply flags
        if '+' in spec['flags'] and num_value >= 0 and fmt_type in 'di':
            formatted = '+' + formatted
        elif ' ' in spec['flags'] and num_value >= 0 and fmt_type in 'di':
            formatted = ' ' + formatted

        if '#' in spec['flags']:
            if fmt_type == 'o' and not formatted.startswith('0'):
                formatted = '0' + formatted
            elif fmt_type == 'x' and num_value != 0:
                formatted = '0x' + formatted
            elif fmt_type == 'X' and num_value != 0:
                formatted = '0X' + formatted

        # Apply precision (minimum digits)
        if spec['precision'] and spec['precision'] != '.':
            precision = int(spec['precision'][1:]) if spec['precision'][1:] else 0
            if precision > 0:
                sign = ''
                if formatted.startswith(('+', '-')):
                    sign = formatted[0]
                    formatted = formatted[1:]
                formatted = sign + formatted.zfill(precision)

        # Apply width
        width = int(spec['width']) if spec['width'] and spec['width'] != '*' else 0
        if width > 0:
            if '-' in spec['flags']:
                formatted = formatted.ljust(width)
            elif '0' in spec['flags'] and not spec['precision']:
                # Zero padding only if no precision specified
                sign = ''
                if formatted.startswith(('+', '-', ' ')):
                    sign = formatted[0]
                    formatted = formatted[1:]
                formatted = sign + formatted.zfill(width - len(sign))
            else:
                formatted = formatted.rjust(width)

        return formatted

    def _format_float(self, value: str, spec: dict) -> str:
        """Format floating point number according to spec."""
        # Convert to float with POSIX rules
        try:
            float_value = float(value.strip())
        except (ValueError, TypeError):
            float_value = 0.0

        fmt_type = spec['type']
        precision = 6  # Default precision

        if spec['precision'] and spec['precision'] != '.':
            if spec['precision'][1:]:
                precision = int(spec['precision'][1:])
            else:
                precision = 0

        # Format according to type
        if fmt_type in 'fF':
            formatted = f"{float_value:.{precision}f}"
        elif fmt_type in 'eE':
            formatted = f"{float_value:.{precision}e}"
            if fmt_type == 'E':
                formatted = formatted.replace('e', 'E')
        elif fmt_type in 'gG':
            formatted = f"{float_value:.{precision}g}"
            if fmt_type == 'G':
                formatted = formatted.upper()
        elif fmt_type in 'aA':
            # Hexadecimal float (not widely supported, approximate)
            formatted = f"{float_value:.{precision}e}"
            if fmt_type == 'A':
                formatted = formatted.upper()
        else:
            formatted = str(float_value)

        # Apply flags
        if '+' in spec['flags'] and float_value >= 0:
            formatted = '+' + formatted
        elif ' ' in spec['flags'] and float_value >= 0:
            formatted = ' ' + formatted

        # Apply width
        width = int(spec['width']) if spec['width'] and spec['width'] != '*' else 0
        if width > 0:
            if '-' in spec['flags']:
                formatted = formatted.ljust(width)
            elif '0' in spec['flags']:
                sign = ''
                if formatted.startswith(('+', '-', ' ')):
                    sign = formatted[0]
                    formatted = formatted[1:]
                formatted = sign + formatted.zfill(width - len(sign))
            else:
                formatted = formatted.rjust(width)

        return formatted

    def _format_character(self, value: str, spec: dict) -> str:
        """Format character according to spec."""
        if not value:
            char = '\0'
        elif value.isdigit():
            # ASCII code
            try:
                char = chr(int(value))
            except (ValueError, OverflowError):
                char = '\0'
        else:
            # First character of string
            char = value[0]

        # Apply width
        width = int(spec['width']) if spec['width'] and spec['width'] != '*' else 0
        if width > 0:
            if '-' in spec['flags']:
                return char.ljust(width)
            else:
                return char.rjust(width)

        return char

    def _process_escape_sequence(self, format_str: str, start: int) -> tuple:
        """Process escape sequence starting at backslash. Returns (char, chars_consumed)."""
        if start + 1 >= len(format_str):
            return '\\', 1

        next_char = format_str[start + 1]

        # Standard escape sequences
        escape_map = {
            'a': '\a',    # Alert (bell)
            'b': '\b',    # Backspace
            'f': '\f',    # Form feed
            'n': '\n',    # Newline
            'r': '\r',    # Carriage return
            't': '\t',    # Tab
            'v': '\v',    # Vertical tab
            '\\': '\\',   # Backslash
            '"': '"',     # Double quote
            "'": "'",     # Single quote
        }

        if next_char in escape_map:
            return escape_map[next_char], 2

        # Octal escape sequence \nnn
        if next_char.isdigit():
            octal_str = ''
            i = start + 1
            while i < len(format_str) and i < start + 4 and format_str[i].isdigit():
                octal_str += format_str[i]
                i += 1
            try:
                value = int(octal_str, 8)
                if value <= 255:
                    return chr(value), i - start
            except (ValueError, OverflowError):
                pass

        # Hex escape sequence \xhh
        if next_char == 'x' and start + 3 < len(format_str):
            hex_str = format_str[start + 2:start + 4]
            if all(c in '0123456789abcdefABCDEF' for c in hex_str):
                try:
                    return chr(int(hex_str, 16)), 4
                except (ValueError, OverflowError):
                    pass

        # Unicode escape sequences \uhhhh and \Uhhhhhhhh
        if next_char == 'u' and start + 6 <= len(format_str):
            hex_str = format_str[start + 2:start + 6]
            if all(c in '0123456789abcdefABCDEF' for c in hex_str):
                try:
                    return chr(int(hex_str, 16)), 6
                except (ValueError, OverflowError):
                    pass

        if next_char == 'U' and start + 10 <= len(format_str):
            hex_str = format_str[start + 2:start + 10]
            if all(c in '0123456789abcdefABCDEF' for c in hex_str):
                try:
                    return chr(int(hex_str, 16)), 10
                except (ValueError, OverflowError):
                    pass

        # Default: return the character as-is
        return next_char, 2

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
            # Check if we're in a child process (forked for pipeline/background)
            is_forked_child = hasattr(shell.state, '_in_forked_child') and shell.state._in_forked_child
            is_eval_test_mode = hasattr(shell.state, 'eval_test_mode') and shell.state.eval_test_mode

            if is_forked_child and not is_eval_test_mode:
                # In child process and not in test mode, write directly to file descriptor
                os.write(1, (cwd + '\n').encode())
            else:
                # In parent process OR in test mode, use normal print to respect redirections/capture
                print(cwd, file=shell.stdout if hasattr(shell, 'stdout') else sys.stdout)
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
