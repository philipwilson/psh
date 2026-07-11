"""
PSH Executor Package

This package implements the execution engine for PSH using a modular
visitor pattern architecture. It transforms AST nodes into executed
commands with proper process management, I/O handling, and job control.

The package is organized into focused modules:
- core: Main ExecutorVisitor coordinating execution
- command: Simple command execution (builtins, functions, externals)
- pipeline: Pipeline execution and process management
- control_flow: Control structures (if, while, for, case, select)
- function: Function execution and scope management
- array: Array initialization and element operations
- subshell: Subshell and brace group execution
- context: Execution context and state management
- strategies: Execution strategies (builtin, function, alias, external)
- process_launcher: Unified process creation with job control
- child_policy: Fork helper, child signal policy, shared child-body runner
- enhanced_test_evaluator: [[ ]] test expression evaluation
"""

from .child_policy import (
    apply_child_signal_policy,
    flush_child_streams,
    fork_with_signal_window,
    run_child_shell,
)
from .context import ExecutionContext
from .core import ExecutorVisitor
from .enhanced_test_evaluator import TestExpressionEvaluator
from .strategies import ExternalExecutionStrategy

__all__ = [
    'ExecutorVisitor',
    'ExecutionContext',
    'ExternalExecutionStrategy',
    'apply_child_signal_policy',
    'flush_child_streams',
    'fork_with_signal_window',
    'run_child_shell',
    'TestExpressionEvaluator',
]
