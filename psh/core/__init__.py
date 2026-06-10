"""Core PSH modules for state management and variable handling.

Modules:
    assignment_utils - Variable assignment parsing and validation
    exceptions       - Control flow and error exceptions
    options          - Shell option behaviour handlers
    scope_enhanced   - Hierarchical variable scope management
    state            - Central shell state container
    trap_manager     - Signal trap management
    variables        - Variable types, attributes, and array implementations
"""

from .assignment_utils import extract_assignments, is_exported, is_valid_assignment
from .exceptions import (
    ExpansionError,
    LoopBreak,
    LoopContinue,
    NamerefCycleError,
    ReadonlyVariableError,
    UnboundVariableError,
)
from .options import OptionHandler
from .scope_enhanced import EnhancedScopeManager, VariableScope
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
    'EnhancedScopeManager',
    'VariableScope',
    # State
    'ShellState',
    # Options
    'OptionHandler',
    # Traps
    'TrapManager',
    # Assignment utilities
    'is_valid_assignment',
    'extract_assignments',
    'is_exported',
]
