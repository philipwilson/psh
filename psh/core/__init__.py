"""Core PSH modules for state management and variable handling.

Modules:
    assignment_utils - Variable assignment parsing and validation
    exceptions       - Control flow and error exceptions
    options          - Shell option behaviour handlers
    scope   - Hierarchical variable scope management
    internal_errors  - Last-resort guard for unexpected internal exceptions
    state            - Central shell state container
    trap_manager     - Signal trap management
    variables        - Variable types, attributes, and array implementations
"""

from .assignment_utils import (
    is_valid_assignment,
    resolve_append_assignment,
)
from .exceptions import (
    ArraySubscriptError,
    ExpansionError,
    FunctionDefinitionError,
    FunctionReturn,
    GlobNoMatchError,
    LoopBreak,
    LoopContinue,
    NamerefCycleError,
    PshError,
    ReadonlyVariableError,
    TopLevelAbort,
    UnboundVariableError,
)
from .internal_errors import report_internal_defect
from .options import OptionHandler
from .scope import ScopeManager, VariableScope
from .state import ShellState
from .trap_manager import TrapManager
from .variables import AssociativeArray, IndexedArray, VarAttributes, Variable

__all__ = [
    # Exceptions
    'LoopBreak',
    'LoopContinue',
    'TopLevelAbort',
    'UnboundVariableError',
    'ReadonlyVariableError',
    'NamerefCycleError',
    'ExpansionError',
    'GlobNoMatchError',
    'FunctionDefinitionError',
    'ArraySubscriptError',
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
    # Internal-defect guard
    'report_internal_defect',
    # Traps
    'TrapManager',
    # Assignment utilities
    'is_valid_assignment',
    'resolve_append_assignment',
]
