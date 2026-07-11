"""Base class for shell builtins."""

import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Mapping, Optional, Tuple

if TYPE_CHECKING:
    from ..ast_nodes import ArrayInitialization
    from ..shell import Shell


@dataclass(frozen=True)
class BuiltinContext:
    """Per-invocation data the executor passes to a builtin beyond its argv.

    Today this carries the structured array initializers the parser attaches
    to ``name=(...)`` arguments (keyed by the exact argv element). The
    declaration builtins (``declare``/``typeset``/``local``/``export``/
    ``readonly``) read them through :meth:`Builtin.execute_in_context` to
    build arrays via the same structured path as the bare ``a=(...)`` form —
    this replaces the former ``shell._pending_array_inits`` side channel, so
    the data flow is an explicit parameter rather than mutable shell state.
    Ordinary builtins never look at it.
    """
    array_inits: Mapping[str, "ArrayInitialization"] = field(default_factory=dict)

    def array_init(self, arg: str) -> Optional["ArrayInitialization"]:
        """The ``ArrayInitialization`` for argv element ``arg``, or None."""
        return self.array_inits.get(arg)


# Shared empty context for direct builtin calls (registry lookups, the
# export→declare delegation's fallback, tests) — a builtin invoked outside the
# executor has no pending array initializers.
EMPTY_BUILTIN_CONTEXT = BuiltinContext()


class Builtin(ABC):
    """Abstract base class for all shell builtins.

    STATELESSNESS CONTRACT: builtin instances are process-wide singletons —
    each class is instantiated exactly once at import time by the
    ``@builtin`` decorator and shared by every Shell in the process
    (including subshells and nested ``Shell.for_subshell(...)`` instances).
    A builtin must therefore keep NO per-invocation or per-shell state on
    ``self``: everything mutable lives on the ``shell`` argument passed to
    ``execute()`` (e.g. ``shell.state``, ``shell.env``,
    ``shell.state.directory_stack``). Concretely, ``vars(instance)`` must
    remain empty after any command battery; this is enforced by
    tests/unit/builtins/test_builtin_statelessness.py.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the primary command name."""
        pass

    @property
    def aliases(self) -> List[str]:
        """Return any command aliases."""
        return []

    @abstractmethod
    def execute(self, args: List[str], shell: 'Shell') -> int:
        """
        Execute the builtin command.

        Args:
            args: Command arguments, including the command name as args[0]
            shell: The shell instance for accessing state and I/O

        Returns:
            Exit code (0 for success, non-zero for failure)
        """
        pass

    def execute_in_context(self, args: List[str], shell: 'Shell',
                           context: BuiltinContext) -> int:
        """Execute with the per-invocation :class:`BuiltinContext`.

        The executor invokes builtins through THIS method (not ``execute``),
        so a builtin that needs invocation data beyond argv — the declaration
        builtins, which consume ``context.array_init(...)`` — overrides it.
        The default ignores the context and runs ``execute()``, so ordinary
        builtins need not know it exists.
        """
        return self.execute(args, shell)

    @property
    def synopsis(self) -> str:
        """Return brief command syntax for the builtin."""
        return f"{self.name}"

    @property
    def description(self) -> str:
        """Return one-line description for the builtin."""
        return self.__class__.__doc__ or 'no description available'

    @property
    def help(self) -> str:
        """Return detailed help text for the builtin."""
        return f"{self.synopsis}\n    {self.description}"

    @staticmethod
    def write_all_fd(fd: int, data: bytes) -> None:
        """Write every byte of *data* to *fd*, looping until done.

        ``os.write`` may write fewer bytes than requested (a full pipe, a slow
        consumer), so a single call can silently truncate large output. This
        is the write-all primitive the fd-level builtin output paths use;
        an underlying error (EBADF/EPIPE) raises ``OSError`` for the caller to
        turn into a failed exit status, matching bash.
        """
        mv = memoryview(data)
        while mv:
            written = os.write(fd, mv)
            mv = mv[written:]

    def write(self, text: str, shell: 'Shell') -> None:
        """Write to the builtin's stdout.

        In a forked child (pipeline member, background job) builtins write
        at the fd level so dup2-based redirections apply; in the parent they
        write to shell.stdout so shell-level redirections and test capture
        apply. This replaces the in_forked_child/os.write dance that used to
        be copied into each builtin.
        """
        if shell.state.in_forked_child:
            # surrogateescape (not 'replace') so bytes carried in as surrogate
            # escapes — e.g. a non-UTF-8 byte from `x=$(printf '\xff')` — write
            # back out as their original byte, matching bash's byte transparency.
            # write_all loops so a partial os.write never truncates the output.
            self.write_all_fd(1, text.encode('utf-8', errors='surrogateescape'))
        else:
            stdout = shell.stdout if hasattr(shell, 'stdout') else sys.stdout
            stdout.write(text)
            stdout.flush()

    def write_line(self, text: str, shell: 'Shell') -> None:
        """Write one line to the builtin's stdout (see write())."""
        self.write(text + '\n', shell)

    def error(self, message: str, shell: 'Shell') -> None:
        """Print a location-prefixed runtime error to stderr (bash ``builtin_error``).

        The line is ``<$0>: [line N: ]<name>: <message>`` — the location prefix
        (see :meth:`ShellState.error_location_prefix`) plus the builtin name.
        Follow-up *usage* lines are NOT location-prefixed in bash; emit those
        with :meth:`usage` (or a bare :meth:`write_error_line`), not this method.
        Diagnostics bash prints WITHOUT the builtin name (assignment/readonly
        failures) use :meth:`report_error`.
        """
        text = f"{shell.state.error_location_prefix()}{self.name}: {message}"
        if shell.state.in_forked_child:
            os.write(2, (text + "\n").encode('utf-8', errors='replace'))
            return
        stderr = shell.stderr if hasattr(shell, 'stderr') else sys.stderr
        print(text, file=stderr)
        stderr.flush()

    def report_error(self, message: str, shell: 'Shell') -> None:
        """Print a location-prefixed error WITHOUT the builtin name (bash ``report_error``).

        For diagnostics bash emits with the ``<$0>: [line N: ]`` prefix but no
        builtin name — notably assignment failures like ``<$0>: line N: NAME:
        readonly variable`` from ``export``/``cd`` writing a readonly variable.
        """
        text = f"{shell.state.error_location_prefix()}{message}"
        if shell.state.in_forked_child:
            os.write(2, (text + "\n").encode('utf-8', errors='replace'))
            return
        stderr = shell.stderr if hasattr(shell, 'stderr') else sys.stderr
        print(text, file=stderr)
        stderr.flush()

    def usage(self, message: str, shell: 'Shell') -> None:
        """Print an UNPREFIXED ``<name>: <message>`` line to stderr.

        bash's ``builtin_usage()``: the usage line that follows an
        option/argument error carries only the builtin name, NOT the
        ``<$0>: line N:`` location prefix that :meth:`error` adds. Callers pass
        the body (typically ``f"usage: {self.synopsis}"``).
        """
        self.write_error_line(f"{self.name}: {message}", shell)

    def write_error_line(self, text: str, shell: 'Shell') -> None:
        """Write one UNPREFIXED line to the builtin's stderr.

        Like error() but without the "name: " prefix — for follow-up
        diagnostic lines (usage text, option listings) that accompany an
        error() call. Forked-child-aware like write()/error().
        """
        if shell.state.in_forked_child:
            os.write(2, (text + '\n').encode('utf-8', errors='replace'))
            return
        stderr = shell.stderr if hasattr(shell, 'stderr') else sys.stderr
        stderr.write(text + '\n')
        stderr.flush()

    def parse_flags(self, args: List[str], shell: 'Shell',
                    flags: str = '', value_flags: str = ''
                    ) -> Tuple[Optional[dict], List[str]]:
        """Parse leading single-dash options from args (getopt-style).

        Args:
            args: Full argv including the command name at args[0].
            flags: Characters allowed as boolean flags (clusterable: -ab).
            value_flags: Characters that consume an argument (-d X or -dX).

        Returns:
            (opts, operands). opts maps each declared flag char to
            True/False (bool flags) or its value/None (value flags);
            operands are the remaining arguments after options and an
            optional ``--``. On an invalid option an error is printed and
            (None, args) is returned — callers should ``return 2``.
        """
        opts: dict = {c: False for c in flags}
        opts.update({c: None for c in value_flags})
        i = 1
        while i < len(args):
            arg = args[i]
            if arg == '--':
                i += 1
                break
            if not arg.startswith('-') or len(arg) == 1:
                break
            for pos, ch in enumerate(arg[1:]):
                if ch in value_flags:
                    rest = arg[pos + 2:]
                    if rest:
                        opts[ch] = rest
                    elif i + 1 < len(args):
                        i += 1
                        opts[ch] = args[i]
                    else:
                        self.error(f"-{ch}: option requires an argument", shell)
                        return None, args
                    break
                elif ch in flags:
                    opts[ch] = True
                else:
                    self.error(f"-{ch}: invalid option", shell)
                    self.usage(f"usage: {self.synopsis}", shell)
                    return None, args
            i += 1
        return opts, args[i:]
