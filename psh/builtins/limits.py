"""ulimit builtin: display and set process resource limits.

Unlike an external ``ulimit`` binary (which can only change its own child
process's limits and is bash-builtin-only on Linux), this builtin calls
``resource.setrlimit`` on the psh process itself, so a limit set here is
inherited by every command psh subsequently forks — matching bash's shell
builtin semantics.
"""

import resource
from typing import TYPE_CHECKING, List, Optional

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


# Resource table mirroring bash's ulimit: option letter -> (RLIMIT_* name,
# block factor, description, unit string). The reported/settable value is the
# kernel value divided by (for a query) or multiplied by (for a set) the block
# factor. An entry is only ACTIVE when Python's ``resource`` module exposes the
# named constant on this platform; an inactive letter is rejected as an invalid
# option, exactly as bash rejects resources its platform did not compile in
# (e.g. ``-x`` on macOS). Insertion order is alphabetical so ``-a`` prints in
# bash's sorted order.
_RESOURCES: dict = {
    'c': ('RLIMIT_CORE',      512,  'core file size',       'blocks'),
    'd': ('RLIMIT_DATA',      1024, 'data seg size',        'kbytes'),
    'e': ('RLIMIT_NICE',      1,    'scheduling priority',  ''),
    'f': ('RLIMIT_FSIZE',     512,  'file size',            'blocks'),
    'i': ('RLIMIT_SIGPENDING', 1,   'pending signals',      ''),
    'l': ('RLIMIT_MEMLOCK',   1024, 'max locked memory',    'kbytes'),
    'm': ('RLIMIT_RSS',       1024, 'max memory size',      'kbytes'),
    'n': ('RLIMIT_NOFILE',    1,    'open files',           ''),
    'q': ('RLIMIT_MSGQUEUE',  1,    'POSIX message queues', 'bytes'),
    'r': ('RLIMIT_RTPRIO',    1,    'real-time priority',   ''),
    's': ('RLIMIT_STACK',     1024, 'stack size',           'kbytes'),
    't': ('RLIMIT_CPU',       1,    'cpu time',             'seconds'),
    'u': ('RLIMIT_NPROC',     1,    'max user processes',   ''),
    'v': ('RLIMIT_AS',        1024, 'virtual memory',       'kbytes'),
    'x': ('RLIMIT_LOCKS',     1,    'file locks',           ''),
}


@builtin
class UlimitBuiltin(Builtin):
    """Display or set process resource limits."""

    @property
    def name(self) -> str:
        return "ulimit"

    @property
    def synopsis(self) -> str:
        return "ulimit [-SHacdefilmnpqrstuvx] [limit]"

    @property
    def description(self) -> str:
        return "Modify or display process resource limits"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        show_all = False
        use_hard = False
        use_soft = False
        opts: List[str] = []

        # Recognised option letters: -H/-S/-a/-p plus every resource letter
        # ACTIVE on this platform. Building the set from active resources
        # means a platform-absent letter (-x/RLIMIT_LOCKS on macOS) is an
        # invalid option AT ITS argv EVENT, exactly like bash rejects
        # resources its build lacks — so `ulimit -x -Z` reports -x, the
        # FIRST invalid letter (probe-pinned). The walker preserves argv
        # ORDER, so a multi-resource query (`ulimit -n -s`) prints in the
        # order requested. -p stays in the set and is rejected AFTER the
        # walk: bash scans the whole option word set first, so a later
        # invalid letter beats -p (`ulimit -p -Z` reports -Z; probe-pinned).
        active = ''.join(ch for ch in _RESOURCES if self._rid(ch) is not None)
        events, operands = self.parse_flags_ordered(
            args, shell, flags='HSap' + active)
        if events is None:
            return 2
        for ch, _ in events:
            if ch == 'H':
                use_hard = True
            elif ch == 'S':
                use_soft = True
            elif ch == 'a':
                show_all = True
            elif ch == 'p':
                # Pipe size is not a getrlimit resource; bash hardcodes it
                # and there is no portable Python API, so be honest rather
                # than silently wrong.
                self.error("-p: pipe size limit not supported by psh", shell)
                return 2
            else:
                # An active resource letter (walker-validated).
                opts.append(ch)

        if show_all:
            self._print_all(shell, use_hard, use_soft)
            return 0

        # bash's default resource is -f (file size) when none is named.
        if not opts:
            opts = ['f']

        value = operands[0] if operands else None
        if value is not None:
            rc = 0
            for ch in opts:
                if not self._set_limit(ch, value, use_hard, use_soft, shell):
                    rc = 1
            return rc

        # Query. A single resource prints just the value; multiple resources
        # print labelled lines like ``-a`` (bash).
        labelled = len(opts) > 1
        rc = 0
        for ch in opts:
            if not self._query(ch, use_hard, use_soft, shell, labelled):
                rc = 1
        return rc

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _rid(ch: str) -> Optional[int]:
        """The RLIMIT_* constant for option *ch* on this platform, or None."""
        return getattr(resource, _RESOURCES[ch][0], None)

    @staticmethod
    def _pick(soft: int, hard: int, use_hard: bool, use_soft: bool) -> int:
        """Which limit a query/display reports.

        bash's precedence: an explicit ``-S`` (or the default) shows the soft
        limit; ``-H`` alone shows the hard limit; ``-H -S`` together shows the
        soft limit (soft wins)."""
        return hard if (use_hard and not use_soft) else soft

    @staticmethod
    def _format(value: int, factor: int) -> str:
        if value == resource.RLIM_INFINITY:
            return 'unlimited'
        return str(value // factor)

    @staticmethod
    def _label_line(ch: str, desc: str, unit: str, value: str) -> str:
        paren = f"({unit}, -{ch})" if unit else f"(-{ch})"
        # Description left-justified in a 20-col field, the unit/option group
        # right-justified in a 20-col field, then the value — matching bash's
        # ``ulimit -a`` layout.
        return f"{desc:<20}{paren:>20} {value}"

    def _print_all(self, shell: 'Shell', use_hard: bool, use_soft: bool) -> None:
        for ch, (rname, factor, desc, unit) in _RESOURCES.items():
            rid = getattr(resource, rname, None)
            if rid is None:
                continue
            try:
                soft, hard = resource.getrlimit(rid)
            except (ValueError, OSError):
                continue
            value = self._format(self._pick(soft, hard, use_hard, use_soft), factor)
            self.write_line(self._label_line(ch, desc, unit, value), shell)

    def _query(self, ch: str, use_hard: bool, use_soft: bool,
               shell: 'Shell', labelled: bool) -> bool:
        rname, factor, desc, unit = _RESOURCES[ch]
        rid = self._rid(ch)
        assert rid is not None  # validated during option parsing
        try:
            soft, hard = resource.getrlimit(rid)
        except (ValueError, OSError) as e:
            self.error(f"{desc}: {e}", shell)
            return False
        value = self._format(self._pick(soft, hard, use_hard, use_soft), factor)
        if labelled:
            self.write_line(self._label_line(ch, desc, unit, value), shell)
        else:
            self.write_line(value, shell)
        return True

    def _set_limit(self, ch: str, value_str: str, use_hard: bool,
                   use_soft: bool, shell: 'Shell') -> bool:
        rname, factor, desc, unit = _RESOURCES[ch]
        rid = self._rid(ch)
        assert rid is not None
        try:
            soft, hard = resource.getrlimit(rid)
        except (ValueError, OSError) as e:
            self.error(f"{desc}: {e}", shell)
            return False

        newval = self._parse_value(value_str, factor, soft, hard)
        if newval is None:
            self.error(f"{value_str}: invalid number", shell)
            return False

        if use_hard and use_soft:
            new_soft = new_hard = newval
        elif use_hard:
            new_soft, new_hard = soft, newval
        elif use_soft:
            new_soft, new_hard = newval, hard
        else:
            # Neither -H nor -S: bash sets BOTH the soft and hard limits.
            new_soft = new_hard = newval

        try:
            resource.setrlimit(rid, (new_soft, new_hard))
        except (ValueError, OSError) as e:
            reason = getattr(e, 'strerror', None) or str(e)
            self.error(f"{desc}: cannot modify limit: {reason}", shell)
            return False
        return True

    @staticmethod
    def _parse_value(value_str: str, factor: int,
                     soft: int, hard: int) -> Optional[int]:
        """Interpret a ulimit limit argument into a kernel-unit value.

        Accepts ``unlimited`` (→ RLIM_INFINITY), the keywords ``hard``/``soft``
        (→ the current hard/soft limit, already in kernel units), or an integer
        count that is scaled UP by the resource's block factor (the inverse of
        the divide-by-factor a query applies). Returns None on a non-numeric
        argument."""
        if value_str == 'unlimited':
            return resource.RLIM_INFINITY
        if value_str == 'hard':
            return hard
        if value_str == 'soft':
            return soft
        try:
            return int(value_str) * factor
        except ValueError:
            return None

    @property
    def help(self) -> str:
        return """ulimit: ulimit [-SHacdefilmnpqrstuvx] [limit]

    Modify or display process resource limits.

    Provides control over the resources available to the shell and the
    processes it starts. A LIMIT sets the named resource; without a LIMIT
    the current value is printed. Limit values are in the units shown by
    ``ulimit -a`` (the special values `unlimited`, `hard`, and `soft` are
    also accepted).

    Options:
      -H        Use / set the hard limit
      -S        Use / set the soft limit (the default)
      -a        Report all current limits
      -c        The maximum size of core files created (blocks)
      -d        The maximum size of a process's data segment (kbytes)
      -e        The maximum scheduling priority (`nice`)
      -f        The maximum size of files written (blocks; the default)
      -i        The maximum number of pending signals
      -l        The maximum size a process may lock into memory (kbytes)
      -m        The maximum resident set size (kbytes)
      -n        The maximum number of open file descriptors
      -q        The maximum bytes in POSIX message queues
      -r        The maximum real-time scheduling priority
      -s        The maximum stack size (kbytes)
      -t        The maximum amount of cpu time (seconds)
      -u        The maximum number of user processes
      -v        The size of virtual memory (kbytes)
      -x        The maximum number of file locks

    Resources whose limit is unavailable on this platform are reported as
    an invalid option. Pipe size (-p) is not supported.

    Exit Status:
    Returns success unless an invalid option is supplied or an error occurs."""
