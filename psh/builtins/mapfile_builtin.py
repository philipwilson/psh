"""mapfile / readarray builtin: read lines from input into an indexed array."""
import os
from typing import TYPE_CHECKING, List

from ..core import IndexedArray, ReadError, VarAttributes
from ..lexer.unicode_support import is_valid_name
from .base import Builtin
from .input_reader import Outcome
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
        return "mapfile [-d delim] [-n count] [-O origin] [-s count] [-t] [-u fd] [-C callback] [-c quantum] [array]"

    @property
    def help(self) -> str:
        return """mapfile: mapfile [-d delim] [-n count] [-O origin] [-s count] [-t] [-u fd] [-C callback] [-c quantum] [array]
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

        # Parse options via the shared getopt-style walker: -t is boolean; the
        # value flags carry a value ("-tn2" == "-t -n 2"). -C (callback) and -c
        # (quantum) take a value too (so they cluster/consume correctly) but psh
        # does not implement callbacks — rejected in the hook with a specific
        # message. Invalid option / missing option-value is a usage error
        # (bash status 2) reported by parse_flags_ordered; bad option VALUES
        # are status 1 (the ReadError rc). The check hook validates and
        # stores each value AT ITS argv event, so combined errors keep bash's
        # first-in-argv precedence regardless of class (`mapfile -n xx -Z`
        # reports the bad count rc 1, not the later invalid option rc 2;
        # probe-pinned).
        def _apply(ch: str, val: str) -> None:
            nonlocal delim, count, origin, skip, fd, have_origin
            if ch in ('C', 'c'):
                raise ReadError(
                    f"-{ch}: callback option not supported", 2)
            if ch == 'd':
                delim = val[0] if val else '\0'
            elif ch == 'n':
                count = self._count(val)
            elif ch == 'O':
                origin = self._origin(val)
                have_origin = True
            elif ch == 's':
                skip = self._count(val)
            elif ch == 'u':
                fd = self._fd(val)

        try:
            events, operands = self.parse_flags_ordered(
                args, shell, flags='t', value_flags='dnOsuCc', check=_apply)
        except ReadError as e:
            self.error(str(e), shell)
            return e.rc
        if events is None:
            return 2
        strip = any(ch == 't' for ch, _ in events)

        rest = operands
        # bash uses the first non-option argument as the array and ignores any
        # extras (returning success), so we do the same.
        if rest:
            array_name = rest[0]
        # Single identifier policy (unicode_support.is_valid_name): under
        # ``set -o posix`` the name is ASCII-only as bash requires; otherwise
        # psh's lenient Unicode-letter rule applies, consistent with every
        # other name site (assignment, declare, read, ...).
        if not is_valid_name(array_name, shell.state.options.get('posix', False)):
            self.error(f"`{array_name}': not a valid identifier", shell)
            return 1

        # A -u file descriptor must be open (bash: "N: invalid file descriptor:
        # Bad file descriptor", status 1) — a silent no-op used to hide this.
        if fd != 0:
            try:
                os.fstat(fd)
            except OSError as e:
                self.error(
                    f"{fd}: invalid file descriptor: {e.strerror or e}", shell)
                return 1

        lines = self._read_lines(shell, fd, delim, skip, count)
        if strip:
            lines = [ln[:-1] if ln.endswith(delim) else ln for ln in lines]

        self._assign(shell, array_name, lines, origin, have_origin)
        return 0

    def _read_lines(self, shell: 'Shell', fd: int, delim: str,
                    skip: int, count: int) -> List[str]:
        """Read the requested records, leaving the rest of the stream intact.

        With a line ``count`` (``-n``), records are read one at a time through
        the shared :class:`InputCursor` and reading STOPS once ``skip + count``
        records have been consumed. This is what fixes the historical drain
        bug: ``mapfile -n1`` used to slurp the whole descriptor into a userspace
        buffer, so a following ``cat`` on the same pipe saw nothing; now only
        the needed records are consumed and the rest is left for the next
        consumer, exactly as bash does.

        With no count (``count == 0``) mapfile reads to EOF regardless, so a
        bulk drain is behaviorally identical to bash (nothing is left over
        either way) and avoids reading a large file one byte at a time.
        """
        reader = shell.state.input_cursors.cursor_for_fd(shell, fd)
        if count == 0:
            all_lines = self._split_lines(reader.read_all(), delim)
            return all_lines[skip:] if skip else all_lines

        lines: List[str] = []
        discarded = 0
        while len(lines) < count:
            result = reader.read_record(delimiter=delim, include_delimiter=True)
            # A pure EOF (or read error) with nothing buffered ends the input.
            if result.data == '' and result.outcome is not Outcome.DATA:
                break
            # Otherwise result.data is a record: either delimiter-terminated or
            # a final line without a trailing delimiter (bash keeps that too).
            if discarded < skip:
                discarded += 1
            else:
                lines.append(result.data)
            if result.outcome is not Outcome.DATA:
                break  # EOF/error reached on this final record; nothing left
        return lines

    @staticmethod
    def _split_lines(data: str, delim: str) -> List[str]:
        """Split *data* into records, each retaining its trailing *delim*.

        A final record without a trailing delimiter is still included; empty
        input yields no records (bash behaviour).
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

    # -- value validation (bash exit codes and messages) --------------------

    @staticmethod
    def _count(value: str) -> int:
        """A -n / -s line count: a non-negative integer (bash)."""
        try:
            parsed = int(value)
            if parsed < 0:
                raise ValueError
        except ValueError:
            raise ReadError(f"{value}: invalid line count") from None
        return parsed

    @staticmethod
    def _origin(value: str) -> int:
        """An -O array origin: a non-negative integer (bash)."""
        try:
            parsed = int(value)
            if parsed < 0:
                raise ValueError
        except ValueError:
            raise ReadError(f"{value}: invalid array origin") from None
        return parsed

    @staticmethod
    def _fd(value: str) -> int:
        """A -u file descriptor: a non-negative integer (bash)."""
        try:
            parsed = int(value)
            if parsed < 0:
                raise ValueError
        except ValueError:
            raise ReadError(
                f"{value}: invalid file descriptor specification") from None
        return parsed

    def _assign(self, shell: 'Shell', name: str, lines: List[str],
                origin: int, have_origin: bool) -> None:

        if have_origin:
            # Overlay onto a COPY of the existing array, not the live one: if
            # the variable is readonly, set_variable rejects the assignment
            # below and the live array must stay untouched (P1.2 — a failed
            # operation does not mutate a readonly value; `readonly a=(old);
            # mapfile -O 1 a` leaves a=(old)).
            var = shell.state.scope_manager.get_variable_object(name)
            if var is not None and isinstance(var.value, IndexedArray):
                array = var.value.copy()
            else:
                array = IndexedArray()
        else:
            array = IndexedArray()

        for offset, line in enumerate(lines):
            array.set(origin + offset, line)

        shell.state.scope_manager.set_variable(
            name, array, attributes=VarAttributes.ARRAY)
