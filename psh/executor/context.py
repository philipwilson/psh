"""
Execution context management for the PSH executor.

This module provides the ExecutionContext class that encapsulates execution
state, replacing scattered instance variables with a structured approach.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExecutionContext:
    """
    Encapsulates execution state for cleaner parameter passing.

    This context object replaces the scattered state variables that were
    previously stored as instance variables in ExecutorVisitor, providing
    a cleaner and more maintainable approach to state management.
    """

    # Execution environment flags
    in_pipeline: bool = False

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
    # suppressible class (invalid options / top-level return) is exempt from
    # the posix-mode exit only when errexit_suppress rose ABOVE this floor —
    # i.e. a guard established INSIDE the current eval/dot nesting. bash's
    # suppression reaches through functions, brace groups and subshells but
    # NOT through an eval/dot boundary (`eval 'set -q' || x` still exits,
    # `eval 'set -q || echo in'` survives — probe-verified,
    # tmp/posixexit/suppress_*.txt), so the nested SourceProcessor raises
    # the floor to the entry-time depth for the duration of the nested text.
    special_exit_floor: int = 0

    @contextmanager
    def errexit_suppressed(self):
        """Suppress set -e while executing a condition-like context."""
        self.errexit_suppress += 1
        try:
            yield
        finally:
            self.errexit_suppress -= 1

    @property
    def special_exit_suppressed(self) -> bool:
        """True when a guard INSIDE the current eval/dot nesting is active
        (the POSIX suppressible-exit exemption; see special_exit_floor)."""
        return self.errexit_suppress > self.special_exit_floor

    def fork_context(self) -> 'ExecutionContext':
        """
        Create a context for a forked child process.

        Inherits pipeline/loop/function state. (The forked-child flag itself
        lives on ShellState — ``state.in_forked_child``, the single authority
        read by builtins to choose fd-level vs Python-level I/O — and is set
        by child_policy/subshell at fork time, not carried here.)
        """
        return ExecutionContext(
            in_pipeline=self.in_pipeline,
            loop_depth=self.loop_depth,
            current_function=self.current_function,
            errexit_suppress=self.errexit_suppress,
            special_exit_floor=self.special_exit_floor,
        )

    def pipeline_context_enter(self) -> 'ExecutionContext':
        """Create a context for entering a pipeline (``in_pipeline=True``)."""
        return ExecutionContext(
            in_pipeline=True,
            loop_depth=self.loop_depth,
            current_function=self.current_function,
            errexit_suppress=self.errexit_suppress,
            special_exit_floor=self.special_exit_floor,
        )
