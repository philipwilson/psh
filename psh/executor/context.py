"""
Execution context management for the PSH executor.

This module provides the ExecutionContext class that encapsulates execution
state, replacing scattered instance variables with a structured approach.
"""

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
        )

    def pipeline_context_enter(self) -> 'ExecutionContext':
        """Create a context for entering a pipeline (``in_pipeline=True``)."""
        return ExecutionContext(
            in_pipeline=True,
            in_forked_child=self.in_forked_child,
            loop_depth=self.loop_depth,
            current_function=self.current_function,
        )

    def in_loop(self) -> bool:
        """Check if we're currently inside a loop."""
        return self.loop_depth > 0

    def in_function(self) -> bool:
        """Check if we're currently inside a function."""
        return self.current_function is not None
