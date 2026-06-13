"""Read builtin command implementation."""
import io
import os
import select
import sys
import termios
import time
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
            self.error(str(e), shell)
            return getattr(e, 'rc', 2)

        # Display prompt if specified
        if options['prompt']:
            sys.stderr.write(options['prompt'])
            sys.stderr.flush()

        try:
            # Decide once whether input comes from sys.stdin or the real fd
            use_sys_stdin = self._should_use_sys_stdin(options['fd'])

            # Read input based on options
            if options['timeout'] is not None:
                line = self._read_with_timeout(
                    options['fd'], options['timeout'], options['delimiter'],
                    options['max_chars'], options['silent'], use_sys_stdin
                )
                if line is None:
                    return 142  # Timeout exit code
            elif options['silent'] or options['max_chars'] is not None:
                line = self._read_special(
                    options['fd'], options['delimiter'],
                    options['max_chars'], options['silent'], use_sys_stdin
                )
            else:
                line = self._read_normal(
                    options['fd'], options['delimiter'], use_sys_stdin)

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
            ifs = shell.state.variables.get('IFS', shell.env.get('IFS', ' \t\n'))

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
            self.error(str(e), shell)
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
                    ifs = shell.state.variables.get('IFS', shell.env.get('IFS', ' \t\n'))
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

    # Flag options set a boolean; arg options consume a value.
    _FLAG_OPTS = {'r': 'raw_mode', 's': 'silent'}
    _ARG_OPTS = frozenset('apdnt')

    def _parse_options(self, args: List[str]) -> Tuple[Dict[str, any], List[str]]:
        """Parse read command options getopt-style, matching bash.

        Options may be clustered (``-rs``). An option that takes an
        argument consumes the rest of its word if non-empty (``-n3``,
        ``-rp prompt``) or the next word otherwise. ``--`` ends option
        processing. Invalid options raise ValueError with ``rc=2``;
        invalid option *values* (bad timeout/count) carry ``rc=1``,
        as bash distinguishes usage errors from value errors.

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
            'array_name': None
        }

        i = 1
        while i < len(args):
            arg = args[i]
            if arg == '--':
                i += 1
                break
            if not arg.startswith('-') or arg == '-':
                break
            j = 1
            while j < len(arg):
                char = arg[j]
                if char in self._FLAG_OPTS:
                    options[self._FLAG_OPTS[char]] = True
                    j += 1
                    continue
                if char in self._ARG_OPTS:
                    # Value is the remainder of this word, else the next word.
                    if j + 1 < len(arg):
                        value = arg[j + 1:]
                    else:
                        i += 1
                        if i >= len(args):
                            raise ValueError(
                                f"-{char}: option requires an argument")
                        value = args[i]
                    self._apply_arg_option(char, value, options)
                    break  # word fully consumed by the value
                raise ValueError(f"-{char}: invalid option")
            i += 1

        # Variable names are ignored when using -a option
        if options['array_name']:
            var_names = []  # Array name takes precedence
        else:
            var_names = args[i:] if i < len(args) else ['REPLY']

        return options, var_names

    def _apply_arg_option(self, char: str, value: str, options: Dict[str, any]) -> None:
        """Validate and store one argument-taking option."""
        if char == 'a':
            options['array_name'] = value
        elif char == 'p':
            options['prompt'] = value
        elif char == 'd':
            # First character of the delimiter string; empty means NUL
            options['delimiter'] = value[0] if value else '\0'
        elif char == 't':
            try:
                timeout = float(value)
            except ValueError:
                timeout = -1.0
            if timeout < 0:
                err = ValueError(f"{value}: invalid timeout specification")
                err.rc = 1  # bash exits 1 for bad values (2 for bad options)
                raise err
            options['timeout'] = timeout
        elif char == 'n':
            try:
                max_chars = int(value)
            except ValueError:
                max_chars = -1
            if max_chars < 0:
                err = ValueError(f"{value}: invalid number")
                err.rc = 1
                raise err
            options['max_chars'] = max_chars

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

    def _read_chars(self, fd: int, *, delimiter: str, limit: Optional[int],
                    use_sys_stdin: bool, echo: bool = False,
                    timeout: Optional[float] = None,
                    include_delimiter: bool = False) -> Tuple[str, str]:
        """The single character-read loop behind every read mode.

        Reads one character at a time from ``sys.stdin`` (StringIO/test
        stdin) or the raw descriptor until the delimiter, EOF or a read
        error, the character limit, or — when ``timeout`` is given — the
        running time budget expires (the budget is shared across
        characters, decremented after each one).

        Returns ``(data, status)`` where status is one of:
          'delim'   - stopped at the delimiter (included in ``data`` only
                      when ``include_delimiter`` is set)
          'eof'     - end of input or read error; ``data`` holds any
                      partial input
          'limit'   - ``limit`` characters were read
          'timeout' - the time budget expired (timeout mode only)
        """
        chars: List[str] = []
        remaining = timeout
        max_count = limit if limit is not None else float('inf')

        while len(chars) < max_count:
            if remaining is not None:
                start_time = time.time()
                ready, _, _ = select.select([fd], [], [], remaining)
                if not ready:
                    return ''.join(chars), 'timeout'

            if use_sys_stdin:
                char = sys.stdin.read(1)
            else:
                try:
                    char = os.read(fd, 1).decode('utf-8', errors='replace')
                except OSError:
                    return ''.join(chars), 'eof'

            if not char:
                return ''.join(chars), 'eof'
            if char == delimiter:
                if include_delimiter:
                    chars.append(char)
                return ''.join(chars), 'delim'
            chars.append(char)

            if echo:
                sys.stdout.write(char)
                sys.stdout.flush()

            if remaining is not None:
                remaining -= time.time() - start_time
                if remaining <= 0:
                    return ''.join(chars), 'timeout'

        return ''.join(chars), 'limit'

    def _read_normal(self, fd: int, delimiter: str,
                     use_sys_stdin: bool) -> Optional[str]:
        """Read until the delimiter with no limit, echo, or timeout.

        For the newline delimiter the result keeps its trailing newline
        (execute() strips it only after escape processing, so that
        backslash-newline continuation can see it); a custom delimiter is
        never included. EOF with no data at all is the None (exit 1)
        case; EOF after partial input returns the partial line.
        """
        data, status = self._read_chars(
            fd, delimiter=delimiter, limit=None, use_sys_stdin=use_sys_stdin,
            include_delimiter=(delimiter == '\n'))
        if status == 'eof' and not data:
            return None
        return data

    def _read_special(self, fd: int, delimiter: str, max_chars: Optional[int],
                      silent: bool, use_sys_stdin: bool) -> Optional[str]:
        """Read with special modes (silent and/or character limit)."""
        if max_chars == 0:
            return ''  # bash: read -n 0 reads nothing and succeeds

        if os.isatty(fd) and (silent or max_chars is not None):
            # Raw terminal mode for char-at-a-time input without canonical
            # buffering. Raw mode disables terminal echo, so -n without -s
            # echoes each character back manually.
            with self._terminal_raw_mode(fd, echo=not silent):
                data, _ = self._read_chars(
                    fd, delimiter=delimiter, limit=max_chars,
                    use_sys_stdin=False,
                    echo=(not silent and max_chars is not None))
                if silent:
                    # Echo newline after silent input
                    sys.stdout.write('\n')
                    sys.stdout.flush()
        elif max_chars is not None:
            data, _ = self._read_chars(
                fd, delimiter=delimiter, limit=max_chars,
                use_sys_stdin=use_sys_stdin)
        else:
            # Silent mode on a non-TTY is just a normal read (no echo to
            # suppress).
            return self._read_normal(fd, delimiter, use_sys_stdin)

        # Quirk preserved from the original: with a custom delimiter,
        # EOF-with-no-data returns '' (exit 0); with newline it is None
        # (EOF, exit 1).
        return data if data or delimiter != '\n' else None

    def _read_with_timeout(self, fd: int, timeout: float, delimiter: str,
                           max_chars: Optional[int], silent: bool,
                           use_sys_stdin: bool) -> Optional[str]:
        """Read with timeout support; None means timeout (exit 142)."""
        if max_chars == 0:
            return ''  # bash: read -n 0 reads nothing and succeeds

        if os.isatty(fd) and (silent or max_chars is not None):
            # Raw mode, char-at-a-time, with the time budget enforced
            # across characters.
            with self._terminal_raw_mode(fd, echo=not silent):
                data, status = self._read_chars(
                    fd, delimiter=delimiter, limit=max_chars,
                    use_sys_stdin=False,
                    echo=(not silent and max_chars is not None),
                    timeout=timeout)
                if silent and (data or status != 'timeout'):
                    # Echo newline after silent input (skipped only when
                    # the timeout expired before anything was typed).
                    sys.stdout.write('\n')
                    sys.stdout.flush()
            if status == 'timeout':
                return None
            return data if data else None

        # Simple case or non-TTY: select bounds only the wait for the
        # FIRST byte; once input is ready, reading proceeds unbounded.
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

        if max_chars is not None:
            data, _ = self._read_chars(
                fd, delimiter=delimiter, limit=max_chars,
                use_sys_stdin=use_sys_stdin)
            # Quirk preserved from the original: no data here (immediate
            # EOF) reports as a timeout (142) rather than EOF (1).
            return data if data else None
        return self._read_normal(fd, delimiter, use_sys_stdin)

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
