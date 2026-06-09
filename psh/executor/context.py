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
    in_forked_child: bool = False

    # Control flow state
    loop_depth: int = 0
    current_function: Optional[str] = None

    # set -e suppression depth. Non-zero while executing syntactic contexts
    # where POSIX exempts failures from errexit: if/elif/while/until
    # conditions, non-final pipelines of a && / || list, and !-negated
    # pipelines. Because nested commands (functions, groups, eval) share
    # this context, the exemption extends through them, as in bash.
    errexit_suppress: int = 0

    @contextmanager
    def errexit_suppressed(self):
        """Suppress set -e while executing a condition-like context."""
        self.errexit_suppress += 1
        try:
            yield
        finally:
            self.errexit_suppress -= 1

    def fork_context(self) -> 'ExecutionContext':
        """
        Create a context for a forked child process.

        Inherits pipeline/loop/function state but marks itself as being in a
        forked child, which affects how certain operations (like builtin
        output) are handled.
        """
        return ExecutionContext(
            in_pipeline=self.in_pipeline,
            in_forked_child=True,
            loop_depth=self.loop_depth,
            current_function=self.current_function,
            errexit_suppress=self.errexit_suppress,
        )

    def pipeline_context_enter(self) -> 'ExecutionContext':
        """Create a context for entering a pipeline (``in_pipeline=True``)."""
        return ExecutionContext(
            in_pipeline=True,
            in_forked_child=self.in_forked_child,
            loop_depth=self.loop_depth,
            current_function=self.current_function,
            errexit_suppress=self.errexit_suppress,
        )

    def in_loop(self) -> bool:
        """Check if we're currently inside a loop."""
        return self.loop_depth > 0

    def in_function(self) -> bool:
        """Check if we're currently inside a function."""
        return self.current_function is not None
