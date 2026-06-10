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
- child_policy: Child process signal setup
- enhanced_test_evaluator: [[ ]] test expression evaluation
"""

from .array import ArrayOperationExecutor
from .child_policy import apply_child_signal_policy
from .command import CommandExecutor
from .context import ExecutionContext
from .control_flow import ControlFlowExecutor
from .core import ExecutorVisitor
from .enhanced_test_evaluator import TestExpressionEvaluator
from .function import FunctionOperationExecutor
from .pipeline import PipelineContext, PipelineExecutor
from .strategies import (
    BuiltinExecutionStrategy,
    ExecutionStrategy,
    ExternalExecutionStrategy,
    FunctionExecutionStrategy,
)
from .subshell import SubshellExecutor

__all__ = [
    'ExecutorVisitor',
    'ExecutionContext',
    'ExternalExecutionStrategy',
    'apply_child_signal_policy',
    'TestExpressionEvaluator',
]
