"""Loop control builtins: break and continue.

In bash these are ordinary (special) builtins, not reserved words: they can
be shadowed by functions, their redirections apply (``break 2>/dev/null``),
and they compose in pipelines and && / || lists. psh matches that by parsing
them as plain simple commands and implementing the control transfer here,
via the LoopBreak/LoopContinue exceptions the loop executors catch.
"""
from abc import abstractmethod
from typing import TYPE_CHECKING, List, Optional

from ..core import (
    LoopBreak,
    LoopContinue,
    special_builtin_usage_discard,
    special_builtin_usage_exit_shell,
)
from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


class LoopControlBuiltin(Builtin):
    """Shared break/continue machinery (argument rules match bash)."""

    def _loop_depth(self, shell: 'Shell') -> int:
        """The enclosing-loop nesting depth at this invocation.

        Read from the active ExecutorVisitor's context — the same channel
        nested execution (eval, source, traps) shares, so ``eval break``
        sees the caller's loops. Function bodies and pipeline-forked
        children keep their own scope because those paths reset or fork the
        context's loop_depth.
        """
        executor = shell._current_executor
        return executor.context.loop_depth if executor is not None else 0

    def execute(self, args: List[str], shell: 'Shell') -> int:
        depth = self._loop_depth(shell)
        if depth == 0:
            # bash: warn and continue with status 0 (the argument is not
            # even validated when there is no enclosing loop). In POSIX
            # mode the no-op is SILENT — bash prints nothing (matrix doc
            # row, probe-verified vs bash 5.2).
            if not shell.state.options.get('posix'):
                self.error(
                    "only meaningful in a `for', `while', or `until' loop",
                    shell)
            return 0
        level = self._resolve_level(args, shell)
        if level is None:
            return shell.state.last_exit_code
        if level == 0:
            # Out-of-range (break 0/negative): bash exits ALL enclosing
            # loops with status 1 (error already reported by the resolver).
            # The same quirk applies to continue.
            raise LoopBreak(depth, exit_status=1)
        self._transfer(level)
        raise AssertionError('unreachable')  # _transfer always raises

    @abstractmethod
    def _transfer(self, level: int) -> None:
        """Raise the control-flow exception for a validated positive level."""

    def _resolve_level(self, args: List[str], shell: 'Shell') -> Optional[int]:
        """Resolve the level argument at runtime (bash semantics).

        Returns the positive level to act on; 0 for the non-positive
        "loop count out of range" case (error already reported, caller exits
        the loop); or None when the command must NOT transfer control because
        a non-numeric argument was reported (only reachable in an interactive
        shell — a non-interactive one has already exited by then). The
        too-many-arguments case never returns: it discards the current input
        unit.

        Both bad-argument cells belong to the ONE usage-error family in
        core/internal_errors.py, and they take DIFFERENT outcomes of it: a
        valid count with extras discards the input line, while a non-numeric
        count exits the shell. Neither status is spelled here.
        """
        if len(args) == 1:
            return 1
        if len(args) > 2:
            # Same too-many-arguments cell as `exit 7 8` / `shift 1 2` /
            # `return 3 4`: report and DISCARD the current input unit — the
            # loop dies, the shell does NOT exit, and the next input line runs
            # with $? = 2, in default AND POSIX mode.
            # Reproduce: printf 'for i in 1; do break 1 2; done\necho rc=$?\n'
            self.error("too many arguments", shell)
            special_builtin_usage_discard(shell.state)

        arg = args[1]
        try:
            level = int(arg)
        except ValueError:
            # Bad-count cell: bash 5.3.15 EXITS the shell here, in every input
            # mode and even under a `|| echo caught` guard.
            self.error(f"{arg}: numeric argument required", shell)
            special_builtin_usage_exit_shell(shell)
            return None

        if level <= 0:
            # bash: report "loop count out of range" and (the caller then)
            # exits ALL enclosing loops with status 1. Signalled by 0.
            self.error(f"{arg}: loop count out of range", shell)
            return 0
        return level


@builtin
class BreakBuiltin(LoopControlBuiltin):
    """Exit from a for, while, until, or select loop."""

    @property
    def name(self) -> str:
        return "break"

    def _transfer(self, level: int) -> None:
        # A successful break is a command that returned 0: it sets $? like
        # any other command, and the loop's status is that of the last
        # command executed — the break itself (bash). The out-of-range
        # `break 0` case carries 1 instead (see execute()).
        raise LoopBreak(level, exit_status=0)

    @property
    def synopsis(self) -> str:
        return "break [n]"

    @property
    def help(self) -> str:
        return """break: break [n]
    Exit for, while, until, or select loops.

    Exit from within a FOR, WHILE, UNTIL, or SELECT loop. If N is
    specified, break N enclosing loops.

    Exit Status:
    The exit status is 0 unless N is not greater than or equal to 1."""


@builtin
class ContinueBuiltin(LoopControlBuiltin):
    """Resume the next iteration of a for, while, until, or select loop."""

    @property
    def name(self) -> str:
        return "continue"

    def _transfer(self, level: int) -> None:
        # A successful continue returns 0 and sets $? (bash): a loop whose
        # last executed command was the continue reports status 0.
        raise LoopContinue(level, exit_status=0)

    @property
    def synopsis(self) -> str:
        return "continue [n]"

    @property
    def help(self) -> str:
        return """continue: continue [n]
    Resume for, while, until, or select loops.

    Resumes the next iteration of the enclosing FOR, WHILE, UNTIL, or
    SELECT loop. If N is specified, resumes the Nth enclosing loop.

    Exit Status:
    The exit status is 0 unless N is not greater than or equal to 1."""
