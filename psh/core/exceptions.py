"""Core exceptions: the psh error hierarchy and control-flow signals.

Two distinct families live here — do not mix them up:

- **Errors** derive from ``PshError`` so callers can catch "any psh
  error" with one except clause. Every shell-specific error class in
  the tree (lexer, parser, arithmetic, expansion, builtins) roots here.
- **Control-flow signals** (``LoopBreak``, ``LoopContinue``,
  ``FunctionReturn``) implement ``break``/``continue``/``return`` and
  deliberately do NOT derive from ``PshError`` — a blanket
  ``except PshError`` must never swallow a ``return`` statement.
"""


class PshError(Exception):
    """Root of all psh-specific error classes (not control flow)."""
    pass


# --- Control-flow signals (NOT errors) ---------------------------------

class LoopBreak(Exception):
    """Exception used to implement break statement."""
    def __init__(self, level=1):
        self.level = level
        super().__init__()

class LoopContinue(Exception):
    """Exception used to implement continue statement."""
    def __init__(self, level=1):
        self.level = level
        super().__init__()

class FunctionReturn(Exception):
    """Exception used to implement the return builtin."""
    def __init__(self, exit_code: int):
        self.exit_code = exit_code
        super().__init__()


# --- Errors -------------------------------------------------------------

class UnboundVariableError(PshError):
    """Raised when accessing unset variable with nounset option."""
    pass

class ReadonlyVariableError(PshError):
    """Raised when attempting to modify a readonly variable."""
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"readonly variable: {name}")

class NamerefCycleError(PshError):
    """Raised when writing through a circular nameref chain
    (declare -n a=b; declare -n b=a; a=5)."""
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"{name}: circular name reference")

class ExpansionError(PshError):
    """Raised when parameter expansion fails (e.g., :? operator)."""
    def __init__(self, message: str, exit_code: int = 1):
        self.exit_code = exit_code
        super().__init__(message)

class FunctionDefinitionError(PshError):
    """Raised when a function cannot be defined or modified: reserved-word
    name, invalid name, or redefining/undefining a readonly function.

    A legitimate shell error (exit 1), NOT an internal defect — so the
    last-resort guard's expected-error taxonomy must never re-raise it,
    even under strict-errors. (Previously a bare ``ValueError``, which the
    taxonomy classifies as a defect.)"""
    exit_code = 1
