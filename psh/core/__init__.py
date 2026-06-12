"""Core PSH modules for state management and variable handling.

Modules:
    assignment_utils - Variable assignment parsing and validation
    exceptions       - Control flow and error exceptions
    options          - Shell option behaviour handlers
    scope   - Hierarchical variable scope management
    state            - Central shell state container
    trap_manager     - Signal trap management
    variables        - Variable types, attributes, and array implementations
"""

from .assignment_utils import (
    is_valid_assignment,
    resolve_append_assignment,
)
from .exceptions import (
    ExpansionError,
    FunctionReturn,
    LoopBreak,
    LoopContinue,
    NamerefCycleError,
    PshError,
    ReadonlyVariableError,
    UnboundVariableError,
)
from .options import OptionHandler
from .scope import ScopeManager, VariableScope
from .state import ShellState
from .trap_manager import TrapManager
from .variables import AssociativeArray, IndexedArray, VarAttributes, Variable

__all__ = [
    # Exceptions
    'LoopBreak',
    'LoopContinue',
    'UnboundVariableError',
    'ReadonlyVariableError',
    'NamerefCycleError',
    'ExpansionError',
    # Variables
    'Variable',
    'VarAttributes',
    'IndexedArray',
    'AssociativeArray',
    # Scope management
    'ScopeManager',
    'VariableScope',
    # State
    'ShellState',
    # Options
    'OptionHandler',
    # Traps
    'TrapManager',
    # Assignment utilities
    'is_valid_assignment',
    'resolve_append_assignment',
]
