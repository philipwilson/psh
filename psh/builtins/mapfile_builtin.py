"""mapfile / readarray builtin: read lines from input into an indexed array."""
import io
import os
import sys
from typing import TYPE_CHECKING, List

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class MapfileBuiltin(Builtin):
    """Read lines from standard input into an indexed array variable."""

    @property
    def name(self) -> str:
        return "mapfile"

    @property
    def aliases(self) -> List[str]:
        return ["readarray"]

    @property
    def synopsis(self) -> str:
        return "mapfile [-d delim] [-n count] [-O origin] [-s count] [-t] [-u fd] [array]"

    @property
    def help(self) -> str:
        return """mapfile: mapfile [-d delim] [-n count] [-O origin] [-s count] [-t] [-u fd] [array]
    Read lines from standard input into an indexed array variable.

    Read lines from the standard input (or file descriptor FD given by -u)
    into the indexed array variable ARRAY. The default ARRAY is MAPFILE.
    `readarray' is a synonym for `mapfile'.

    Options:
      -d delim   Use DELIM (first character) to terminate lines, not newline.
                 An empty DELIM means lines are terminated by NUL.
      -n count   Copy at most COUNT lines. 0 copies all lines.
      -O origin  Begin assigning at index ORIGIN (the array is not cleared).
      -s count   Discard the first COUNT lines read.
      -t         Remove the trailing DELIM (newline) from each line read.
      -u fd      Read from file descriptor FD instead of standard input.

    Exit Status:
    Returns 0 unless an invalid option is given or ARRAY is invalid or readonly.

    Note: the -C callback and -c quantum options are not supported."""

    def execute(self, args: List[str], shell: 'Shell') -> int:
        delim = '\n'
        count = 0          # 0 = all
        origin = 0
        skip = 0
        strip = False
        fd = 0
        have_origin = False
        array_name = 'MAPFILE'

        # Parse options, supporting clustered short flags ("-tn2" == "-t -n 2").
        arg_flags = set('dnOsu')   # flags that take an argument
        i = 1
        n = len(args)
        try:
            while i < n and args[i].startswith('-') and args[i] != '-':
                cluster = args[i]
                if cluster == '--':
                    i += 1
                    break
                j = 1
                while j < len(cluster):
                    ch = cluster[j]
                    if ch in ('C', 'c'):
                        self.error(f"-{ch}: callback option not supported", shell)
                        return 2
                    if ch == 't':
                        strip = True
                        j += 1
                        continue
                    if ch not in arg_flags:
                        self.error(f"-{ch}: invalid option", shell)
                        return 2
                    # Argument is the rest of the cluster, else the next word.
                    if j + 1 < len(cluster):
                        val = cluster[j + 1:]
                    else:
                        i += 1
                        if i >= n:
                            raise ValueError(f"-{ch}: option requires an argument")
                        val = args[i]
                    if ch == 'd':
                        delim = val[0] if val else '\0'
                    elif ch == 'n':
                        count = self._to_int(val, '-n')
                    elif ch == 'O':
                        origin = self._to_int(val, '-O')
                        have_origin = True
                    elif ch == 's':
                        skip = self._to_int(val, '-s')
                    elif ch == 'u':
                        fd = self._to_int(val, '-u')
                    break  # argument consumed the remainder of the cluster
                i += 1
        except ValueError as e:
            self.error(str(e), shell)
            return 2

        rest = args[i:]
        # bash uses the first non-option argument as the array and ignores any
        # extras (returning success), so we do the same.
        if rest:
            array_name = rest[0]
        # Single identifier policy (unicode_support.is_valid_name): under
        # ``set -o posix`` the name is ASCII-only as bash requires; otherwise
        # psh's lenient Unicode-letter rule applies, consistent with every
        # other name site (assignment, declare, read, ...).
        from ..lexer.unicode_support import is_valid_name
        if not is_valid_name(array_name, shell.state.options.get('posix', False)):
            self.error(f"`{array_name}': not a valid identifier", shell)
            return 1

        # Read and split input into lines (each keeps its trailing delimiter,
        # except possibly the final unterminated line).
        data = self._read_all(fd)
        lines = self._split_lines(data, delim)

        if skip > 0:
            lines = lines[skip:]
        if count > 0:
            lines = lines[:count]
        if strip:
            lines = [ln[:-1] if ln.endswith(delim) else ln for ln in lines]

        self._assign(shell, array_name, lines, origin, have_origin)
        return 0

    @staticmethod
    def _to_int(value: str, flag: str) -> int:
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"{flag}: {value}: invalid number") from None

    def _read_all(self, fd: int) -> str:
        """Read all input from the descriptor (or sys.stdin under test capture)."""
        if self._use_sys_stdin(fd):
            return sys.stdin.read()
        chunks = []
        while True:
            try:
                block = os.read(fd, 65536)
            except OSError:
                break
            if not block:
                break
            chunks.append(block)
        return b''.join(chunks).decode('utf-8', errors='replace')

    def _use_sys_stdin(self, fd: int) -> bool:
        """Mirror ReadBuiltin: prefer the real OS fd when it is valid."""
        if 'DontReadFromInput' in sys.stdin.__class__.__name__:
            return False
        try:
            sys.stdin.fileno()
        except (AttributeError, io.UnsupportedOperation):
            return True
        try:
            os.fstat(fd)
            return False
        except (OSError, AttributeError, ValueError):
            return True

    @staticmethod
    def _split_lines(data: str, delim: str) -> List[str]:
        """Split *data* into lines, each retaining its trailing *delim*.

        A final line without a trailing delimiter is still included. Empty
        input yields no lines (bash behaviour).
        """
        lines = []
        start = 0
        for idx, ch in enumerate(data):
            if ch == delim:
                lines.append(data[start:idx + 1])
                start = idx + 1
        if start < len(data):
            lines.append(data[start:])
        return lines

    def _assign(self, shell: 'Shell', name: str, lines: List[str],
                origin: int, have_origin: bool) -> None:
        from ..core import IndexedArray, VarAttributes

        if have_origin:
            # Do not clear: overlay onto the existing array (or a new one).
            var = shell.state.scope_manager.get_variable_object(name)
            if var is not None and isinstance(var.value, IndexedArray):
                array = var.value
            else:
                array = IndexedArray()
        else:
            array = IndexedArray()

        for offset, line in enumerate(lines):
            array.set(origin + offset, line)

        shell.state.scope_manager.set_variable(
            name, array, attributes=VarAttributes.ARRAY)
