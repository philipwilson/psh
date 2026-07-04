"""Read builtin command implementation."""
import io
import os
import select
import sys
import termios
import time
import tty
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell

# A delimiter that can never equal a single decoded character, so the
# char-read loop never stops early (used by ``read -N``). os.read(fd, 1)
# decodes to at most one character, so a two-character marker never matches.
_NO_DELIM = '\x00\x00'


@builtin
class ReadBuiltin(Builtin):
    """Read a line from standard input and assign to variables."""

    @property
    def name(self) -> str:
        return "read"

    @property
    def synopsis(self) -> str:
        return "read [-rs] [-a array] [-d delim] [-n nchars] [-N nchars] [-p prompt] [-t timeout] [var ...]"

    @property
    def help(self) -> str:
        return """read: read [-rs] [-a array] [-d delim] [-n nchars] [-N nchars] [-p prompt] [-t timeout] [var ...]
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
      -n nchars     Read at most NCHARS characters (delimiter stops early)
      -N nchars     Read EXACTLY NCHARS characters (ignore delimiter and IFS)
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

        # Validate the target NAME(s) before reading anything (bash rejects a
        # non-identifier target with "not a valid identifier", status 1). Uses
        # the shell's single identifier policy (unicode_support.is_valid_name):
        # under ``set -o posix`` names are ASCII-only as in bash; otherwise
        # psh's lenient Unicode-letter rule applies (documented divergence).
        # A subscripted target ``NAME[i]`` validates only its base NAME.
        from ..lexer.unicode_support import is_valid_name
        posix_mode = shell.state.options.get('posix', False)
        targets = list(var_names)
        if options['array_name']:
            targets.append(options['array_name'])
        for target in targets:
            base = target.split('[', 1)[0]
            if not is_valid_name(base, posix_mode):
                self.error(f"`{target}': not a valid identifier", shell)
                return 1

        # Display the -p prompt, but ONLY when the input is a terminal (bash):
        # a `read -p` from a pipe / here-string / redirected file writes no
        # prompt, so it stays out of captured output.
        if options['prompt'] and self._read_input_is_tty(shell, options['fd']):
            sys.stderr.write(options['prompt'])
            sys.stderr.flush()

        # `read -u FD`: the fd must be open, else bash errors with status 1
        # ("read: 9: invalid file descriptor: Bad file descriptor").
        if options['fd_from_u']:
            try:
                os.fstat(options['fd'])
            except OSError as e:
                self.error(
                    f"{options['fd']}: invalid file descriptor: "
                    f"{e.strerror or e}", shell)
                return 1

        try:
            # Decide once whether input comes from sys.stdin or the real fd
            use_sys_stdin = self._should_use_sys_stdin(options['fd'])

            # `read -t 0` is a non-consuming poll: success (0) if the fd is
            # readable (data ready OR at EOF), 1 if a read would block. It
            # reads nothing and assigns no variables (bash).
            if options['timeout'] == 0:
                return self._poll_input(options['fd'], use_sys_stdin)

            delim = options['delimiter']

            # -N: read EXACTLY N characters, ignoring the delimiter and IFS.
            # The result (after backslash processing unless -r) is assigned
            # whole to the first variable; rc is 1 only if EOF cut it short.
            if options['exact_chars'] is not None:
                return self._read_exact(options, var_names, shell, use_sys_stdin)

            # Read input based on options
            if options['timeout'] is not None:
                line, read_status = self._read_with_timeout(
                    options['fd'], options['timeout'], delim,
                    options['max_chars'], options['silent'], use_sys_stdin
                )
                # On timeout bash still ASSIGNS whatever partial input was read
                # (splitting/clearing the variables normally), so fall through
                # to the assignment path; the 142 exit code is reported at the
                # end via read_status.
            elif options['silent'] or options['max_chars'] is not None:
                line, read_status = self._read_special(
                    options['fd'], delim,
                    options['max_chars'], options['silent'], use_sys_stdin
                )
            else:
                line, read_status = self._read_normal(
                    options['fd'], delim, use_sys_stdin)

            # EOF before the delimiter is a read FAILURE (exit 1), but bash
            # still assigns whatever was read (a partial last line, or empty
            # — which clears the variables). So fall through to assignment and
            # report the status at the end, rather than returning early.

            # Strip the trailing delimiter if present (so the rest of the
            # logic works on the line content). The normal/newline read path
            # keeps its delimiter; custom delimiters are already excluded.
            if line.endswith(delim):
                line = line[:-1]

            # Backslash processing (bash semantics). Without -r, a backslash
            # removes the special meaning of the next character (NO C-style
            # \t/\n translation); a backslash before the delimiter is line
            # continuation — both are removed and reading continues onto the
            # next line. -n / -d-with-char / silent / timeout modes use the
            # raw line as read (continuation only applies to the plain path).
            line_continuation = (not options['raw_mode']
                                 and options['max_chars'] is None
                                 and not options['silent']
                                 and options['timeout'] is None)
            if line_continuation:
                line, read_status = self._read_continuations(
                    line, options['fd'], delim, use_sys_stdin, read_status)

            # Decompose into (char, protected) pairs. Protected chars are
            # backslash-escaped: their backslash is removed and they are
            # exempt from IFS splitting/trimming (bash behavior). In raw
            # mode nothing is escaped.
            chars = self._process_escapes(line, options['raw_mode'])

            # Get IFS value (default is space, tab, newline)
            ifs = shell.state.variables.get('IFS', shell.env.get('IFS', ' \t\n'))

            # Handle assignment based on array option or number of variables
            if options['array_name']:
                # Array assignment: always split on IFS
                fields = self._split_with_ifs(chars, ifs)
                self._assign_to_array(fields, options['array_name'], shell)
            elif options.get('default_reply'):
                # A defaulted REPLY (no var names given) gets the whole
                # line, untrimmed and unsplit, matching bash.
                shell.state.set_variable(
                    var_names[0], ''.join(c for c, _ in chars))
            else:
                # Split into at most len(var_names) fields; the last field
                # is the raw remainder of the line (bash read semantics).
                fields = self._split_with_ifs(
                    chars, ifs, max_fields=len(var_names))
                self._assign_to_variables(fields, var_names, shell)

            # Report the read outcome. Exit 142 when a -t timeout expired,
            # exit 1 when input ended before the delimiter (EOF) — in both
            # cases the variables were just assigned the partial/empty result
            # (bash). Otherwise success.
            if read_status == 'timeout':
                return 142
            return 1 if read_status == 'eof' else 0

        except KeyboardInterrupt:
            # Ctrl-C pressed
            return 130
        except OSError as e:
            # bash's shape: "read: read error: 0: Bad file descriptor"
            # (e.g. reading after `exec 0<&-`) — never the raw Python
            # OSError repr ("[Errno 9] Bad file descriptor").
            self.error(
                f"read error: {options['fd']}: {e.strerror or e}", shell)
            return 1
        except ValueError as e:
            self.error(str(e), shell)
            return 1

    def _read_continuations(self, line: str, fd: int, delim: str,
                            use_sys_stdin: bool, status: str) -> Tuple[str, str]:
        """Honor backslash-<delimiter> line continuation (bash, non-raw).

        ``_read_normal`` stops at the first delimiter, so a line whose
        content ends in an *unescaped* trailing backslash had its delimiter
        escaped: drop that backslash and read the next line, repeating until
        the line does not end in an unescaped backslash or input is
        exhausted. (An even count of trailing backslashes means the final
        one is itself escaped — not a continuation.)

        ``status`` is the status of the read that produced ``line``; the
        returned status is that of the LAST read performed, so a continuation
        that ends at EOF (no closing delimiter) reports 'eof' (exit 1).
        """
        while self._has_unescaped_trailing_backslash(line):
            line = line[:-1]  # remove the continuation backslash
            nxt, status = self._read_normal(fd, delim, use_sys_stdin)
            if status == 'eof' and not nxt:
                break  # EOF: nothing more to splice on
            if nxt.endswith(delim):
                nxt = nxt[:-1]
            line += nxt
        return line, status

    @staticmethod
    def _has_unescaped_trailing_backslash(line: str) -> bool:
        """True if ``line`` ends in an odd run of backslashes."""
        count = 0
        i = len(line) - 1
        while i >= 0 and line[i] == '\\':
            count += 1
            i -= 1
        return count % 2 == 1

    def _process_escapes(self, line: str, raw: bool) -> List[Tuple[str, bool]]:
        """Decompose a line into (char, protected) pairs (bash semantics).

        In raw mode every character is unprotected and unchanged. Otherwise
        a backslash removes the special meaning of the next character: the
        backslash is dropped and that character is emitted as *protected*
        (literal — so it never acts as an IFS delimiter). There is NO
        C-style translation (``\\t`` -> ``t``, not a tab). A trailing lone
        backslash (no following char; can only survive at true EOF) is
        dropped, as bash does.
        """
        if raw:
            return [(c, False) for c in line]

        result: List[Tuple[str, bool]] = []
        i = 0
        n = len(line)
        while i < n:
            if line[i] == '\\' and i + 1 < n:
                result.append((line[i + 1], True))  # next char, literal
                i += 2
            elif line[i] == '\\':
                # Trailing lone backslash — drop it (bash).
                i += 1
            else:
                result.append((line[i], False))
                i += 1
        return result

    def _split_with_ifs(self, chars: List[Tuple[str, bool]], ifs: str,
                        max_fields: Optional[int] = None) -> List[str]:
        """Split (char, protected) pairs on IFS (Internal Field Separator).

        Rules:
        1. If IFS is empty, no splitting occurs
        2. Leading/trailing IFS whitespace characters are trimmed
        3. Multiple consecutive IFS whitespace characters count as one separator
        4. Non-whitespace IFS characters are always separators
        5. Backslash-protected characters are never separators (bash)

        With ``max_fields`` (variable assignment, as opposed to ``read -a``),
        at most that many fields are produced and the LAST one is the raw
        remainder of the line — interior delimiters and spacing preserved
        verbatim, trailing unprotected IFS whitespace stripped. Exception,
        exactly as in bash's read builtin: when extracting one more word plus
        its delimiter would consume the remainder entirely, the last field is
        just that word (so ``x:y:`` gives ``y`` but ``x:y::`` gives ``y::``).
        """
        if not ifs:
            # No IFS, return entire line as one field
            return [''.join(c for c, _ in chars)]

        # Separate whitespace and non-whitespace IFS characters
        ifs_whitespace = set(c for c in ifs if c in ' \t\n')
        ifs_non_whitespace = set(c for c in ifs if c not in ' \t\n')

        def is_ws(idx):
            c, prot = chars[idx]
            return not prot and c in ifs_whitespace

        def is_nonws(idx):
            c, prot = chars[idx]
            return not prot and c in ifs_non_whitespace

        fields: List[str] = []
        i = 0
        n = len(chars)

        # POSIX field splitting: a single delimiter is a run of IFS whitespace
        # with AT MOST ONE IFS non-whitespace character embedded in it — so IFS
        # whitespace ADJACENT to a non-whitespace delimiter is absorbed into it
        # (`IFS=": "` on `a : b` => [a, b], not [a, '', b]). Leading/trailing
        # IFS whitespace is ignored; a non-whitespace delimiter still produces
        # empty fields when it is leading or doubled (`:x` => ['', x];
        # `x::y` => [x, '', y]) but NOT a trailing empty (`x:` => [x]).
        while i < n and is_ws(i):  # strip leading IFS whitespace
            i += 1

        while i < n:
            field_start = i

            # Accumulate a field up to the next unprotected IFS character.
            field: List[str] = []
            while i < n and not is_ws(i) and not is_nonws(i):
                field.append(chars[i][0])
                i += 1
            fields.append(''.join(field))

            # Consume ONE delimiter: surrounding IFS whitespace plus at most one
            # IFS non-whitespace character (whitespace absorbed on both sides).
            while i < n and is_ws(i):
                i += 1
            if i < n and is_nonws(i):
                i += 1
                while i < n and is_ws(i):
                    i += 1

            # Last variable with input left over: it takes the raw remainder
            # (from the start of its word, minus trailing unprotected IFS
            # whitespace) instead of just the word extracted above.
            if max_fields is not None and len(fields) == max_fields and i < n:
                end = n
                while end > field_start and is_ws(end - 1):
                    end -= 1
                fields[-1] = ''.join(c for c, _ in chars[field_start:end])
                break

        # No fields (empty / all-whitespace input) reads as one empty field.
        if not fields:
            fields = ['']

        return fields

    def _assign_to_variables(self, fields: List[str], var_names: List[str], shell: 'Shell'):
        """Assign fields to variables positionally.

        The splitter (called with ``max_fields``) already folded any extra
        input into the last field as the raw remainder; variables beyond
        the available fields are set to the empty string.
        """
        for i, var_name in enumerate(var_names):
            value = fields[i] if i < len(fields) else ''
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
    _ARG_OPTS = frozenset('apdnNtu')

    def _parse_options(self, args: List[str]) -> Tuple[Dict[str, Any], List[str]]:
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
            'exact_chars': None,
            'delimiter': '\n',
            'fd': 0,
            'fd_from_u': False,
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
            options['default_reply'] = False
        elif i < len(args):
            var_names = args[i:]
            options['default_reply'] = False
        else:
            # No variable names given: the whole line goes to REPLY *without*
            # IFS whitespace trimming (bash); an explicit `read REPLY` trims.
            var_names = ['REPLY']
            options['default_reply'] = True

        return options, var_names

    def _apply_arg_option(self, char: str, value: str, options: Dict[str, Any]) -> None:
        """Validate and store one argument-taking option."""
        if char == 'a':
            options['array_name'] = value
        elif char == 'u':
            # Read from file descriptor FD instead of stdin (bash `read -u N`).
            try:
                fd = int(value)
                if fd < 0:
                    raise ValueError
            except ValueError:
                err = ValueError(
                    f"{value}: invalid file descriptor specification")
                setattr(err, 'rc', 1)
                raise err from None
            options['fd'] = fd
            options['fd_from_u'] = True
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
                setattr(err, 'rc', 1)  # bash exits 1 for bad values (2 for bad options)
                raise err
            options['timeout'] = timeout
        elif char == 'n':
            try:
                max_chars = int(value)
            except ValueError:
                max_chars = -1
            if max_chars < 0:
                err = ValueError(f"{value}: invalid number")
                setattr(err, 'rc', 1)
                raise err
            options['max_chars'] = max_chars
        elif char == 'N':
            # -N reads EXACTLY this many chars, ignoring the delimiter and
            # IFS (the raw chars, with backslash processing unless -r).
            try:
                exact = int(value)
            except ValueError:
                exact = -1
            if exact < 0:
                err = ValueError(f"{value}: invalid number")
                setattr(err, 'rc', 1)
                raise err
            options['exact_chars'] = exact

    def _read_input_is_tty(self, shell: 'Shell', fd: int) -> bool:
        """Whether the read source is a terminal (gates the ``-p`` prompt).

        Mirrors the source selection in ``_should_use_sys_stdin``: check the
        shell's Python-level stdin when that is what we read from, else the real
        OS descriptor. Any error (no ``isatty``, closed fd) means "not a tty".
        """
        try:
            if self._should_use_sys_stdin(fd):
                stdin = getattr(shell, 'stdin', sys.stdin)
                return bool(stdin.isatty())
            return os.isatty(fd)
        except (OSError, ValueError, AttributeError):
            return False

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

    def _poll_input(self, fd: int, use_sys_stdin: bool) -> int:
        """`read -t 0`: return 0 if input is available on the fd (data ready
        or EOF — both are "readable" to select), 1 if a read would block.
        Consumes nothing."""
        if use_sys_stdin:
            # StringIO/test stdin can't be select()'d; treat as readable.
            return 0
        try:
            ready, _, _ = select.select([fd], [], [], 0)
        except (OSError, ValueError):
            return 1
        return 0 if ready else 1

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
                     use_sys_stdin: bool) -> Tuple[str, str]:
        """Read until the delimiter with no limit, echo, or timeout.

        Returns ``(data, status)`` where status is 'ok' (the delimiter was
        found) or 'eof' (input ended first — bash assigns whatever was read,
        partial or empty, and reports failure). For the newline delimiter the
        data keeps its trailing newline (execute() strips it only after escape
        processing, so backslash-newline continuation can see it); a custom
        delimiter is never included.
        """
        data, status = self._read_chars(
            fd, delimiter=delimiter, limit=None, use_sys_stdin=use_sys_stdin,
            include_delimiter=(delimiter == '\n'))
        return data, ('ok' if status == 'delim' else 'eof')

    def _read_special(self, fd: int, delimiter: str, max_chars: Optional[int],
                      silent: bool, use_sys_stdin: bool) -> Tuple[str, str]:
        """Read with special modes (silent and/or character limit).

        Returns ``(data, status)`` — 'ok' when the delimiter was found or the
        ``-n`` character limit was reached, 'eof' when input ended first
        (bash assigns the partial/empty data and reports failure).
        """
        if max_chars == 0:
            return '', 'ok'  # bash: read -n 0 reads nothing and succeeds

        if os.isatty(fd) and max_chars is not None:
            # COUNT-terminated read (-n): raw terminal mode for char-at-a-time
            # input without canonical line buffering. Raw mode disables echo,
            # so -n without -s echoes each character back manually.
            with self._terminal_raw_mode(fd, echo=not silent):
                data, status = self._read_chars(
                    fd, delimiter=delimiter, limit=max_chars,
                    use_sys_stdin=False, echo=not silent)
                if silent:
                    # Echo newline after silent input
                    sys.stdout.write('\n')
                    sys.stdout.flush()
        elif os.isatty(fd) and silent:
            # SILENT delimiter-terminated read (`read -s`, no -n): stay in
            # CANONICAL mode and clear only ECHO (bash's model). Raw mode
            # would clear ICANON/ISIG/ICRNL, so Enter's CR would never map to
            # the newline delimiter (the read would hang) and Ctrl-D/Ctrl-C
            # would be inert. Canonical no-echo keeps line editing, the
            # Enter->delimiter mapping and Ctrl-D EOF, and leaves ISIG on so
            # Ctrl-C's SIGINT is delivered (terminating a -c read) — all while
            # hiding the typed text.
            with self._terminal_noecho_mode(fd):
                data, status = self._read_chars(
                    fd, delimiter=delimiter, limit=None,
                    use_sys_stdin=False,
                    include_delimiter=(delimiter == '\n'))
                # Enter is not echoed (ECHO off); print the newline bash prints.
                sys.stdout.write('\n')
                sys.stdout.flush()
        elif max_chars is not None:
            data, status = self._read_chars(
                fd, delimiter=delimiter, limit=max_chars,
                use_sys_stdin=use_sys_stdin)
        else:
            # Silent mode on a non-TTY is just a normal read (no echo to
            # suppress).
            return self._read_normal(fd, delimiter, use_sys_stdin)

        return data, ('ok' if status in ('delim', 'limit') else 'eof')

    def _read_exact(self, options: Dict[str, Any], var_names: List[str],
                    shell: 'Shell', use_sys_stdin: bool) -> int:
        """Implement ``read -N count`` (read EXACTLY count characters).

        Unlike -n, the delimiter is ignored entirely and IFS does not split
        or trim the result. Backslash processing still applies unless -r.
        The full (post-escape) text is assigned to the first variable; any
        further variables are cleared. Returns 1 when EOF arrived before
        ``count`` characters were read (bash), 0 otherwise.
        """
        count = options['exact_chars']
        fd = options['fd']
        if count == 0:
            # bash: read -N 0 reads nothing and succeeds, clearing the var.
            data, status = '', 'limit'
        elif os.isatty(fd):
            with self._terminal_raw_mode(fd, echo=True):
                # No delimiter stop: pass a delimiter that cannot appear in a
                # single decoded char (NUL would still match, so use a marker
                # that _read_chars never compares true against) — simplest is
                # to read raw and never treat any char as the delimiter.
                data, status = self._read_chars(
                    fd, delimiter=_NO_DELIM, limit=count,
                    use_sys_stdin=False, echo=True)
        else:
            data, status = self._read_chars(
                fd, delimiter=_NO_DELIM, limit=count, use_sys_stdin=use_sys_stdin)

        # Backslash processing (bash applies it for -N too, unless -r).
        chars = self._process_escapes(data, options['raw_mode'])
        text = ''.join(c for c, _ in chars)

        if options['array_name']:
            # bash assigns the whole result as a single element for -N.
            self._assign_to_array([text], options['array_name'], shell)
        else:
            shell.state.set_variable(var_names[0], text)
            for name in var_names[1:]:
                shell.state.set_variable(name, '')

        # rc 1 when input was exhausted before reaching the requested count.
        return 0 if status == 'limit' else 1

    def _read_with_timeout(self, fd: int, timeout: float, delimiter: str,
                           max_chars: Optional[int], silent: bool,
                           use_sys_stdin: bool) -> Tuple[str, str]:
        """Read with timeout support.

        Returns ``(data, status)`` — 'timeout' (exit 142) when the budget
        expires, 'ok' when the delimiter/char-limit is satisfied, 'eof' when
        input ends first (bash assigns the partial data and reports failure).
        """
        if max_chars == 0:
            return '', 'ok'  # bash: read -n 0 reads nothing and succeeds

        if os.isatty(fd) and max_chars is not None:
            # COUNT-terminated read (-n): raw mode, char-at-a-time, with the
            # time budget enforced across characters.
            with self._terminal_raw_mode(fd, echo=not silent):
                data, status = self._read_chars(
                    fd, delimiter=delimiter, limit=max_chars,
                    use_sys_stdin=False, echo=not silent, timeout=timeout)
                if silent and (data or status != 'timeout'):
                    # Echo newline after silent input (skipped only when
                    # the timeout expired before anything was typed).
                    sys.stdout.write('\n')
                    sys.stdout.flush()
            if status == 'timeout':
                return data, 'timeout'
            return data, ('ok' if status in ('delim', 'limit') else 'eof')

        if os.isatty(fd) and silent:
            # SILENT delimiter-terminated read at a tty (`read -s -t`): as in
            # _read_special, use canonical no-echo mode (not raw) so Enter
            # still terminates and signals still fire, with the time budget
            # enforced across the whole read.
            with self._terminal_noecho_mode(fd):
                data, status = self._read_chars(
                    fd, delimiter=delimiter, limit=None,
                    use_sys_stdin=False, timeout=timeout,
                    include_delimiter=(delimiter == '\n'))
                if data or status != 'timeout':
                    sys.stdout.write('\n')
                    sys.stdout.flush()
            if status == 'timeout':
                return data, 'timeout'
            return data, ('ok' if status in ('delim', 'limit') else 'eof')

        # Simple case or non-TTY. StringIO test stdin can't be select()'d and
        # never blocks, so it reads immediately with no budget enforcement.
        if use_sys_stdin:
            if max_chars is not None:
                data, status = self._read_chars(
                    fd, delimiter=delimiter, limit=max_chars,
                    use_sys_stdin=True)
                return data, ('ok' if status in ('delim', 'limit') else 'eof')
            return self._read_normal(fd, delimiter, use_sys_stdin)

        # Real fd: thread the time budget through the WHOLE read so the
        # deadline bounds every blocking read, not just the wait for the
        # first byte (bash saves the partial input and exits >128 on expiry).
        data, status = self._read_chars(
            fd, delimiter=delimiter, limit=max_chars,
            use_sys_stdin=False, timeout=timeout,
            include_delimiter=(max_chars is None and delimiter == '\n'))
        if status == 'timeout':
            return data, 'timeout'
        return data, ('ok' if status in ('delim', 'limit') else 'eof')

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

    @contextmanager
    def _terminal_noecho_mode(self, fd: int):
        """Canonical terminal mode with echo disabled (bash's `read -s`).

        Unlike ``_terminal_raw_mode``, this leaves ICANON, ISIG and ICRNL
        intact: line editing works, Enter's CR maps to the newline delimiter,
        Ctrl-D is EOF, and ISIG stays on so Ctrl-C's SIGINT is still delivered
        (it terminates a ``-c``/script read). Only the echo flags are cleared,
        so the typed line is hidden while the read still terminates on Enter.
        (Under the interactive REPL a Ctrl-C during a read is swallowed and the
        read continues, exactly like plain ``read`` — a pre-existing REPL-level
        SIGINT behavior this mode does not change.)
        """
        if not os.isatty(fd):
            yield
            return

        old_settings = termios.tcgetattr(fd)
        try:
            new_settings = termios.tcgetattr(fd)
            # lflags is index 3. Clear ECHO (hide typed chars) and ECHONL
            # (so the delimiter newline is not echoed either); keep ICANON
            # (line editing, Ctrl-D EOF) and ISIG (Ctrl-C's SIGINT delivered).
            new_settings[3] &= ~(termios.ECHO | termios.ECHONL)
            termios.tcsetattr(fd, termios.TCSANOW, new_settings)
            yield
        finally:
            termios.tcsetattr(fd, termios.TCSANOW, old_settings)
