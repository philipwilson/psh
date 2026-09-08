"""
Execution context management for the PSH executor.

This module provides the ExecutionContext class that encapsulates execution
state, replacing scattered instance variables with a structured approach.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Optional


@dataclass
class ExecutionContext:
    """
    Encapsulates execution state for cleaner parameter passing.

    This context object replaces the scattered state variables that were
    previously stored as instance variables in ExecutorVisitor, providing
    a cleaner and more maintainable approach to state management.
    """

    # ONE-SHOT exec-in-place token. Its meaning is narrow and positional:
    # "this process was forked to BE one pipeline member, that member is a
    # SIMPLE COMMAND, and its dispatch has not happened yet — so when that
    # command resolves to an external program there is nothing left for this
    # process to do afterwards and it may execve() in place instead of
    # forking again."
    #
    # ONE WRITER — executor/pipeline.py, through for_pipeline_member(), in
    # the forked member child only.
    # ONE READER — take_exec_in_place(), called exactly once per simple
    # command by executor/command.py#CommandExecutor.execute, which binds the
    # answer into `exec_in_place` for that one dispatch.
    #
    # Because the token is CONSUMED by the member's own top-level command,
    # nothing a nested frame runs can observe it: a function body, `eval`
    # text, a sourced file, a compound body and a subshell all dispatch their
    # commands after the token is gone, so each of their external commands
    # forks and the commands after it still run. That is the whole reason
    # `f(){ /bin/echo A; echo B; }; f | cat` prints A and B (C001); before the
    # one-shot the flag was inherited and /bin/echo replaced the member
    # process, silently discarding `echo B` and the member's real status.
    exec_in_place_token: bool = False

    # The answer take_exec_in_place() gave for the simple command CURRENTLY
    # being dispatched — the only thing the exec branch in
    # executor/strategies.py may read. False for every command run by a
    # nested frame.
    exec_in_place: bool = False

    # DURABLE, and a DIFFERENT question from the token: "is this process a
    # forked pipeline member?" It stays true for everything the member runs,
    # including nested frames, and answers questions about the PROCESS rather
    # than about one dispatch (e.g. the pipeline parent already set the
    # terminal title for the whole pipeline, so a member must not repaint it).
    is_pipeline_member: bool = False

    # Control flow state
    loop_depth: int = 0
    current_function: Optional[str] = None

    # set -e suppression depth. Non-zero while executing syntactic contexts
    # where POSIX exempts failures from errexit: if/elif/while/until
    # conditions, non-final pipelines of a && / || list, and !-negated
    # pipelines. Because nested commands (functions, groups, eval) share
    # this context, the exemption extends through them, as in bash.
    errexit_suppress: int = 0

    # The suppression a forked PIPELINE MEMBER inherited but must NOT apply to
    # its own simple command. bash's rule, verbatim from the manual ("The Set
    # Builtin"):
    #
    #     If a compound command or shell function executes in a context where
    #     -e is being ignored, none of the commands executed within the
    #     compound command or function body will be affected by the -e setting.
    #
    # A SIMPLE-COMMAND member introduces no such body, so `set -e` stays
    # effective for the text its `eval`/`.` parses: `set -e; { true | eval
    # 'echo $(if)'; } || recover` leaves 2 in bash, while the same member
    # wrapped in `{ }`, `( )`, a function, or any loop/case leaves 1.
    #
    # ONE WRITER — the pipeline member closure (executor/pipeline.py), in the
    # forked child only, on a context created for that member alone.
    # ONE READER — executor/function.py#FunctionOperationExecutor._function_frame,
    # which re-applies it for a function BODY's duration: the "or shell
    # function" half of the same sentence. It is read at BODY entry rather than
    # decided from the member's AST because `{ true | $Q; }` names a function
    # only after expansion.
    #
    # Bookkeeping, not status derivation: the substitution abort's stamp still
    # reads errexit_suppress at the raise site (core/exceptions.py#
    # SubstitutionSyntaxAbort), and this field exists so that counter is
    # already correct when it does.
    errexit_suppress_deferred: int = 0

    # Floor for the POSIX special-builtin SUPPRESSIBLE-exit check: the
    # suppressible class (invalid options, top-level return, and bash 5.3's
    # export/readonly/unset operand errors) is exempt from the posix-mode
    # exit only when errexit_suppress rose ABOVE this floor. On bash 5.3 an
    # OUTER guard suppresses through functions, brace groups, subshells AND
    # through an eval/dot boundary, so those nestings leave the floor alone;
    # a TRAP ACTION is the one boundary it does not cross, and
    # `trap_action_boundary` raises the floor for the action's duration.
    # Reproduce (bash 5.3.15 and psh agree on all three):
    #   set -o posix; eval 'set -q' || echo caught   -> caught, rc 0
    #   set -o posix; eval 'set -q || echo in'       -> in, rc 0
    #   set -o posix; trap 'set -q' DEBUG; false || echo caught  -> rc 2
    special_exit_floor: int = 0

    @contextmanager
    def errexit_suppressed(self):
        """Suppress set -e while executing a condition-like context."""
        self.errexit_suppress += 1
        try:
            yield
        finally:
            self.errexit_suppress -= 1

    @contextmanager
    def trap_action_boundary(self):
        """Run a TRAP ACTION with the POSIX suppressible-exit floor raised.

        bash runs a trap action between commands, and a guard around the
        INTERRUPTED command does not suppress a special-builtin exit inside
        the action: `set -o posix; trap 'set -q' DEBUG; false || echo caught`
        exits 2 on bash 5.3.15 in all three input modes. A guard INSIDE the
        action suppresses again (`trap 'set -q || echo in' EXIT` survives),
        which is exactly what raising the floor to the entry-time depth
        expresses. The one caller is core/trap_manager.py#execute_trap.
        """
        saved = self.special_exit_floor
        self.special_exit_floor = self.errexit_suppress
        try:
            yield
        finally:
            self.special_exit_floor = saved

    @property
    def special_exit_suppressed(self) -> bool:
        """True when a guard reaching this command is active and no trap-action
        boundary intervenes (the POSIX suppressible-exit exemption; see
        special_exit_floor)."""
        return self.errexit_suppress > self.special_exit_floor

    def take_exec_in_place(self) -> bool:
        """Consume the one-shot exec-in-place token (see the field).

        Returns the token's value and clears it, so the SECOND caller — and
        therefore every command a nested frame runs — gets False.
        """
        decided = self.exec_in_place_token
        self.exec_in_place_token = False
        return decided

    @contextmanager
    def exec_in_place_decision(self) -> Iterator[None]:
        """Bind ``exec_in_place`` for ONE simple-command dispatch.

        Entered once per simple command by
        executor/command.py#CommandExecutor.execute, which is the single
        gateway to simple-command execution, so every dispatch after the
        first sees the consumed (False) token.
        """
        previous = self.exec_in_place
        self.exec_in_place = self.take_exec_in_place()
        try:
            yield
        finally:
            self.exec_in_place = previous

    def for_pipeline_member(self, *, exec_in_place: bool) -> 'ExecutionContext':
        """Create the context for one forked pipeline-member process.

        The SOLE writer of the exec-in-place token and of
        ``is_pipeline_member``: executor/pipeline.py calls this in the child
        it forked for a member, passing ``exec_in_place=True`` only when that
        member is a simple command (the one shape whose dispatch can be the
        last thing the process does).

        Loop depth, the current function name and the errexit bookkeeping are
        inherited so a bare ``break | cat`` inside a loop stays silent and the
        errexit rules keep working. The forked-child flag itself is NOT
        carried here: it lives on ShellState (``state.in_forked_child``, the
        single authority read by builtins to choose fd-level vs Python-level
        I/O) and is set by child_policy at fork time.
        """
        return ExecutionContext(
            exec_in_place_token=exec_in_place,
            is_pipeline_member=True,
            loop_depth=self.loop_depth,
            current_function=self.current_function,
            errexit_suppress=self.errexit_suppress,
            special_exit_floor=self.special_exit_floor,
        )
