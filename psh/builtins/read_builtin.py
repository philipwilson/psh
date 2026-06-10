"""Read builtin command implementation."""
import io
import os
import select
import sys
import termios
import tty
from contextlib import contextmanager
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class ReadBuiltin(Builtin):
    """Read a line from standard input and assign to variables."""

    @property
    def name(self) -> str:
        return "read"

    @property
    def synopsis(self) -> str:
        return "read [-rs] [-a array] [-d delim] [-n chars] [-p prompt] [-t timeout] [var ...]"

    @property
    def help(self) -> str:
        return """read: read [-rs] [-a array] [-d delim] [-n chars] [-p prompt] [-t timeout] [var ...]
    Read a line from standard input and assign to variables.

    Reads a single line from stdin (or the specified fd) and splits it
    into fields using IFS. Fields are assigned to the named variables;
    if more fields than variables, the last variable gets the remainder.
    With no variables, the line is stored in REPLY.

    Options:
      -r            Raw mode (do not interpret backslash escapes)
      -s            Silent mode (do not echo input)
      -a array      Read into indexed array ARRAY
      -d delim      Use DELIM as line delimiter instead of newline
      -n chars      Read at most CHARS characters
      -p prompt     Display PROMPT on stderr before reading
      -t timeout    Time out after TIMEOUT seconds (exit code 142)

    Exit Status:
    Returns 0 unless EOF is reached, a timeout expires, or an error occurs."""

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Execute the read builtin."""
        try:
            options, var_names = self._parse_options(args)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2

        # Display prompt if specified
        if options['prompt']:
            sys.stderr.write(options['prompt'])
            sys.stderr.flush()

        try:
            # Read input based on options
            if options['timeout'] is not None:
                line = self._read_with_timeout(
                    options['fd'], options['timeout'], options['delimiter'],
                    options['max_chars'], options['silent']
                )
                if line is None:
                    return 142  # Timeout exit code
            elif options['silent'] or options['max_chars'] is not None:
                line = self._read_special(
                    options['fd'], options['delimiter'],
                    options['max_chars'], options['silent']
                )
            else:
                line = self._read_normal(options['fd'], options['delimiter'])

            # Check for EOF
            if line is None:
                return 1

            # Process backslash escapes unless in raw mode
            # This must be done BEFORE stripping the delimiter so that
            # backslash-delimiter line continuation works correctly
            if not options['raw_mode']:
                line = self._process_escapes(line)

            # Remove trailing delimiter if present (after escape processing)
            if line.endswith(options['delimiter']):
                line = line[:-1]

            # Get IFS value (default is space, tab, newline)
            ifs = shell.variables.get('IFS', shell.env.get('IFS', ' \t\n'))

            # Handle assignment based on array option or number of variables
            if options['array_name']:
                # Array assignment: always split on IFS
                fields = self._split_with_ifs(line, ifs)
                self._assign_to_array(fields, options['array_name'], shell)
            elif len(var_names) == 1:
                # Single variable: trim leading/trailing IFS whitespace only
                # Don't split the line
                ifs_whitespace = [c for c in ifs if c in ' \t\n']
                if ifs_whitespace:
                    # Trim leading whitespace
                    while line and line[0] in ifs_whitespace:
                        line = line[1:]
                    # Trim trailing whitespace
                    while line and line[-1] in ifs_whitespace:
                        line = line[:-1]
                shell.state.set_variable(var_names[0], line)
            else:
                # Multiple variables: split based on IFS
                fields = self._split_with_ifs(line, ifs)
                self._assign_to_variables(fields, var_names, shell)

            return 0

        except KeyboardInterrupt:
            # Ctrl-C pressed
            return 130
        except (OSError, ValueError) as e:
            print(f"read: {e}", file=sys.stderr)
            return 1

    def _process_escapes(self, line: str) -> str:
        """Process backslash escape sequences.

        Handles:
        - \\ -> \
        - \n -> newline
        - \t -> tab
        - \r -> carriage return
        - \\<space> -> space (preserves space)
        - \\<newline> -> line continuation (removes both)
        - \\<other> -> <other> (backslash removed)
        """
        result = []
        i = 0

        while i < len(line):
            if line[i] == '\\' and i + 1 < len(line):
                next_char = line[i + 1]
                if next_char == '\\':
                    result.append('\\')
                elif next_char == 'n':
                    result.append('\n')
                elif next_char == 't':
                    result.append('\t')
                elif next_char == 'r':
                    result.append('\r')
                elif next_char == '\n':
                    # Line continuation - skip both characters
                    # Note: This is only for backslash-newline within the line
                    # A trailing backslash at end of input is different
                    pass
                else:
                    # Other escaped character - just add the character
                    result.append(next_char)
                i += 2
            else:
                result.append(line[i])
                i += 1

        return ''.join(result)

    def _split_with_ifs(self, line: str, ifs: str) -> List[str]:
        """Split line based on IFS (Internal Field Separator).

        Rules:
        1. If IFS is empty, no splitting occurs
        2. Leading/trailing IFS whitespace characters are trimmed
        3. Multiple consecutive IFS whitespace characters count as one separator
        4. Non-whitespace IFS characters are always separators
        """
        if not ifs:
            # No IFS, return entire line as one field
            return [line]

        # Separate whitespace and non-whitespace IFS characters
        ifs_whitespace = set(c for c in ifs if c in ' \t\n')
        ifs_non_whitespace = set(c for c in ifs if c not in ' \t\n')

        fields = []
        current_field = []
        i = 0

        # Skip leading IFS whitespace
        while i < len(line) and line[i] in ifs_whitespace:
            i += 1

        while i < len(line):
            char = line[i]

            if char in ifs_non_whitespace:
                # Non-whitespace IFS character - always a separator
                fields.append(''.join(current_field))
                current_field = []
                i += 1
            elif char in ifs_whitespace:
                # Whitespace IFS character
                if current_field:
                    fields.append(''.join(current_field))
                    current_field = []
                # Skip consecutive IFS whitespace
                while i < len(line) and line[i] in ifs_whitespace:
                    i += 1
            else:
                # Regular character
                current_field.append(char)
                i += 1

        # Add last field if any
        if current_field:
            fields.append(''.join(current_field))

        # If no fields were found, return empty string
        if not fields:
            fields = ['']

        return fields

    def _assign_to_variables(self, fields: List[str], var_names: List[str], shell: 'Shell'):
        """Assign fields to variables.

        Rules:
        1. Each field is assigned to corresponding variable
        2. If more fields than variables, last variable gets all remaining fields
        3. If fewer fields than variables, extra variables are set to empty string
        """
        for i, var_name in enumerate(var_names):
            if i < len(fields):
                if i == len(var_names) - 1 and i < len(fields) - 1:
                    # Last variable - assign all remaining fields joined by first IFS char
                    ifs = shell.variables.get('IFS', shell.env.get('IFS', ' \t\n'))
                    if ifs:
                        sep = ifs[0]
                    else:
                        sep = ' '
                    value = sep.join(fields[i:])
                else:
                    # Normal assignment
                    value = fields[i]
            else:
                # No more fields - set to empty
                value = ''

            shell.state.set_variable(var_name, value)

    def _assign_to_array(self, fields: List[str], array_name: str, shell: 'Shell'):
        """Assign fields to an indexed array.

        Creates or replaces an indexed array with the given fields.
        Each field becomes an array element with sequential indices starting from 0.
        """
        from ..core import IndexedArray, VarAttributes

        # Create new indexed array
        array = IndexedArray()

        # Handle empty input case: if only field is empty string, create empty array
        if len(fields) == 1 and fields[0] == '':
            # Empty input should create empty array (bash behavior)
            pass  # Don't add any elements
        else:
            # Assign each field to sequential indices
            for i, field in enumerate(fields):
                array.set(i, field)

        # Set the array in shell state
        shell.state.scope_manager.set_variable(array_name, array, attributes=VarAttributes.ARRAY)

    def _parse_options(self, args: List[str]) -> Tuple[Dict[str, any], List[str]]:
        """Parse read command options.

        Returns:
            Tuple of (options dict, variable names list)
        """
        options = {
            'raw_mode': False,
            'silent': False,
            'prompt': None,
            'timeout': None,
            'max_chars': None,
            'delimiter': '\n',
            'fd': 0,
            'array_name': None  # New option for array assignment
        }

        i = 1
        while i < len(args):
            if args[i] == '-r':
                options['raw_mode'] = True
            elif args[i] == '-s':
                options['silent'] = True
            elif args[i] == '-a':
                if i + 1 < len(args):
                    options['array_name'] = args[i + 1]
                    i += 1
                else:
                    raise ValueError("read: -a: option requires an argument")
            elif args[i].startswith('-') and len(args[i]) > 2:
                # Handle combined options like -ra, -rs, etc.
                option_chars = args[i][1:]
                for char in option_chars:
                    if char == 'r':
                        options['raw_mode'] = True
                    elif char == 's':
                        options['silent'] = True
                    elif char == 'a':
                        # -a in combined form requires next argument
                        if i + 1 < len(args):
                            options['array_name'] = args[i + 1]
                            i += 1
                        else:
                            raise ValueError("read: -a: option requires an argument")
                    else:
                        raise ValueError(f"read: -{char}: invalid option")
                break  # Combined options processed, continue to remaining args
            elif args[i] == '-p':
                if i + 1 < len(args):
                    options['prompt'] = args[i + 1]
                    i += 1
                else:
                    raise ValueError("read: -p: option requires an argument")
            elif args[i] == '-t':
                if i + 1 < len(args):
                    try:
                        options['timeout'] = float(args[i + 1])
                        if options['timeout'] < 0:
                            raise ValueError(f"read: {args[i + 1]}: invalid timeout specification")
                    except ValueError:
                        raise ValueError(f"read: {args[i + 1]}: invalid timeout specification")
                    i += 1
                else:
                    raise ValueError("read: -t: option requires an argument")
            elif args[i] == '-n':
                if i + 1 < len(args):
                    try:
                        options['max_chars'] = int(args[i + 1])
                        if options['max_chars'] <= 0:
                            raise ValueError(f"read: {args[i + 1]}: invalid number")
                    except ValueError:
                        raise ValueError(f"read: {args[i + 1]}: invalid number")
                    i += 1
                else:
                    raise ValueError("read: -n: option requires an argument")
            elif args[i] == '-d':
                if i + 1 < len(args):
                    # Use first character of delimiter string, empty means null
                    options['delimiter'] = args[i + 1][0] if args[i + 1] else '\0'
                    i += 1
                else:
                    raise ValueError("read: -d: option requires an argument")
            elif args[i].startswith('-'):
                raise ValueError(f"read: {args[i]}: invalid option")
            else:
                break
            i += 1

        # Variable names are ignored when using -a option
        if options['array_name']:
            var_names = []  # Array name takes precedence
        else:
            var_names = args[i:] if i < len(args) else ['REPLY']

        return options, var_names

    def _should_use_sys_stdin(self, fd: int) -> bool:
        """Decide whether to read from ``sys.stdin`` or the real OS descriptor.

        The real descriptor is authoritative whenever it is valid — this covers
        redirections in forked subshells (``( ... ) < file``), pipes, and files,
        where ``fd`` was set up with ``os.dup2`` even though ``sys.stdin`` is a
        Python-level object pytest may have swapped out. ``sys.stdin`` is used
        only for a genuine in-process replacement (e.g. a ``StringIO`` test
        stdin with no real ``fileno``). pytest's ``DontReadFromInput`` capture
        object is explicitly treated as "use the real fd" so that redirected
        reads work under capture without the ``-s`` flag.
        """
        if 'DontReadFromInput' in sys.stdin.__class__.__name__:
            return False
        try:
            sys.stdin.fileno()
        except (AttributeError, io.UnsupportedOperation):
            return True  # StringIO-backed / non-fd stdin
        # Real stdin object: prefer the fd if it is a valid OS descriptor.
        try:
            os.fstat(fd)
            return False
        except (OSError, AttributeError, ValueError):
            return True

    def _read_normal(self, fd: int, delimiter: str) -> Optional[str]:
        """Read normally from file descriptor until delimiter."""
        use_sys_stdin = self._should_use_sys_stdin(fd)

        if delimiter == '\n':
            if use_sys_stdin:
                # Use sys.stdin for StringIO/test scenarios
                line = sys.stdin.readline()
                if not line:
                    return None
                return line
            else:
                # Use os.read for real file descriptors
                chars = []
                while True:
                    try:
                        char = os.read(fd, 1).decode('utf-8', errors='replace')
                    except OSError:
                        # Error reading - return what we have
                        return None if not chars else ''.join(chars)

                    if not char:
                        return None if not chars else ''.join(chars)
                    chars.append(char)
                    if char == '\n':
                        return ''.join(chars)
        else:
            # Read character by character for custom delimiter
            chars = []
            if use_sys_stdin:
                # Use sys.stdin for StringIO scenarios
                while True:
                    char = sys.stdin.read(1)
                    if not char:
                        return None if not chars else ''.join(chars)
                    if char == delimiter:
                        return ''.join(chars)
                    chars.append(char)
            else:
                while True:
                    try:
                        char = os.read(fd, 1).decode('utf-8', errors='replace')
                    except OSError:
                        # Not a valid file descriptor
                        return None if not chars else ''.join(chars)

                    if not char:
                        return None if not chars else ''.join(chars)
                    if char == delimiter:
                        return ''.join(chars)
                    chars.append(char)

    def _read_special(self, fd: int, delimiter: str, max_chars: Optional[int],
                      silent: bool) -> Optional[str]:
        """Read with special modes (silent and/or character limit)."""
        chars = []

        # Check if we're dealing with a TTY
        is_tty = os.isatty(fd)

        # If we need raw terminal mode and have a TTY
        if is_tty and (silent or max_chars is not None):
            with self._terminal_raw_mode(fd, echo=not silent):
                limit = max_chars if max_chars is not None else float('inf')
                while len(chars) < limit:
                    try:
                        char = os.read(fd, 1).decode('utf-8', errors='replace')
                    except OSError:
                        break

                    if not char:
                        break

                    if char == delimiter:
                        break

                    chars.append(char)

                    # Echo character if not silent and in raw mode
                    if not silent and max_chars is not None:
                        sys.stdout.write(char)
                        sys.stdout.flush()

                # Echo newline after silent input
                if silent:
                    sys.stdout.write('\n')
                    sys.stdout.flush()
        else:
            # Non-TTY or no special handling needed
            if max_chars is not None:
                use_sys_stdin = self._should_use_sys_stdin(fd)

                # Read up to max_chars
                limit = max_chars
                while len(chars) < limit:
                    if use_sys_stdin:
                        char = sys.stdin.read(1)
                    else:
                        try:
                            char = os.read(fd, 1).decode('utf-8', errors='replace')
                        except OSError:
                            break
                    if not char:
                        break
                    if char == delimiter:
                        break
                    chars.append(char)
            else:
                # Just read normally for silent mode on non-TTY
                line = self._read_normal(fd, delimiter)
                if line is None:
                    return None
                return line

        return ''.join(chars) if chars or delimiter != '\n' else None

    def _read_with_timeout(self, fd: int, timeout: float, delimiter: str,
                          max_chars: Optional[int], silent: bool) -> Optional[str]:
        """Read with timeout support."""
        chars = []
        remaining_timeout = timeout
        is_tty = os.isatty(fd)

        if is_tty and (silent or max_chars is not None):
            # Need raw mode for character-by-character reading
            with self._terminal_raw_mode(fd, echo=not silent):
                limit = max_chars if max_chars is not None else float('inf')

                while len(chars) < limit:
                    import time
                    start_time = time.time()

                    # Use select to wait for input with timeout
                    ready, _, _ = select.select([fd], [], [], remaining_timeout)
                    if not ready:
                        # Timeout
                        if silent and chars:
                            sys.stdout.write('\n')
                            sys.stdout.flush()
                        return None

                    # Read one character
                    try:
                        char = os.read(fd, 1).decode('utf-8', errors='replace')
                    except OSError:
                        break

                    if not char:
                        break

                    if char == delimiter:
                        break

                    chars.append(char)

                    # Echo character if not silent
                    if not silent and max_chars is not None:
                        sys.stdout.write(char)
                        sys.stdout.flush()

                    # Update remaining timeout
                    elapsed = time.time() - start_time
                    remaining_timeout -= elapsed
                    if remaining_timeout <= 0:
                        if silent:
                            sys.stdout.write('\n')
                            sys.stdout.flush()
                        return None

                # Echo newline after silent input
                if silent:
                    sys.stdout.write('\n')
                    sys.stdout.flush()
        else:
            # Simple case or non-TTY: just wait for line with timeout
            use_sys_stdin = self._should_use_sys_stdin(fd)
            if use_sys_stdin:
                # StringIO-backed stdin doesn't support select; read immediately.
                ready = [sys.stdin]
            else:
                try:
                    ready, _, _ = select.select([fd], [], [], timeout)
                except (OSError, AttributeError, ValueError):
                    ready = []

            if not ready:
                return None

            # For non-TTY with char limit
            if max_chars is not None:
                limit = max_chars
                while len(chars) < limit:
                    if use_sys_stdin:
                        char = sys.stdin.read(1)
                    else:
                        try:
                            char = os.read(fd, 1).decode('utf-8', errors='replace')
                        except OSError:
                            break
                    if not char:
                        break
                    if char == delimiter:
                        break
                    chars.append(char)
                return ''.join(chars) if chars else None
            else:
                return self._read_normal(fd, delimiter)

        return ''.join(chars) if chars else None

    @contextmanager
    def _terminal_raw_mode(self, fd: int, echo: bool = True):
        """Context manager for raw terminal mode."""
        # Check if fd is a TTY
        if not os.isatty(fd):
            # Not a TTY, just yield without changing settings
            yield
            return

        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd, termios.TCSANOW)
            if not echo:
                new_settings = termios.tcgetattr(fd)
                new_settings[3] &= ~termios.ECHO
                termios.tcsetattr(fd, termios.TCSANOW, new_settings)
            yield
        finally:
            termios.tcsetattr(fd, termios.TCSANOW, old_settings)
