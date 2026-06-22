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
    """Exception used to implement break statement.

    ``exit_status`` is normally None (the loop keeps the body's status); it is
    set only for the bash ``break 0``/negative "loop count out of range" case,
    where the loop must report status 1.
    """
    def __init__(self, level=1, exit_status=None):
        self.level = level
        self.exit_status = exit_status
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


class AssignmentAbort(BaseException):
    """A fatal variable-assignment error (readonly variable, circular nameref)
    that aborts the CURRENT top-level command but does NOT exit the shell.

    bash reports the error and unwinds the whole current top-level command —
    skipping the rest of the command list, and any enclosing ``if``/loop/
    function/brace group on the same logical input — then resumes at the NEXT
    top-level command (next input line). So::

        readonly r=1; r=2; echo X      # one line  -> X skipped (whole list aborts)
        readonly r=1
        r=2                            # own line  -> aborts here ...
        echo X                         # ... resumes: X prints

    Derives from ``BaseException`` (like ``SystemExit``) so it unwinds past the
    executor's ``except Exception`` guards without being mistaken for an
    internal defect; it is caught explicitly at the top-level command boundary
    (``SourceProcessor._execute_buffered_command``) and at child-shell
    boundaries (subshell ``execute_fn``, ``run_child_shell``). The error message
    is printed at the raise site (bash prints it before unwinding).
    """
    def __init__(self, status: int = 1):
        self.status = status
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

class GlobNoMatchError(PshError):
    """Raised when pathname expansion matches nothing under ``shopt -s
    failglob``. Unlike a parameter ExpansionError this is NOT fatal to a
    non-interactive shell — bash fails only the current command (status 1)
    and continues to the next — so the command-error handler reports it and
    returns 1 without exiting."""
    def __init__(self, pattern: str):
        self.pattern = pattern
        super().__init__(f"no match: {pattern}")

class BadSubstitutionError(ExpansionError):
    """Raised at expansion time for a syntactically-invalid ``${...}``
    parameter name (bash: "${...}: bad substitution", exit 1). Examples:
    ``${}``, ``${ }``, ``${1abc}``, ``${.foo}``, ``${:-x}``. The braces are
    included in the message text to match bash's format. Subclasses
    ExpansionError so the command-error handler treats it as
    already-printed (message emitted in place) and propagates exit 1."""
    def __init__(self, content: str, exit_code: int = 1):
        self.content = content
        super().__init__(f"${{{content}}}: bad substitution", exit_code=exit_code)

class FunctionDefinitionError(PshError):
    """Raised when a function cannot be defined or modified: reserved-word
    name, invalid name, or redefining/undefining a readonly function.

    A legitimate shell error (exit 1), NOT an internal defect — so the
    last-resort guard's expected-error taxonomy must never re-raise it,
    even under strict-errors. (Previously a bare ``ValueError``, which the
    taxonomy classifies as a defect.)"""
    exit_code = 1


class ArraySubscriptError(PshError):
    """Raised for a bad indexed-array subscript on a write (bash:
    "bad array subscript"). The canonical case is a negative subscript that,
    after mapping ``-N`` to ``(highest+1)-N``, still falls below 0
    (out of range). A legitimate shell error (exit 1), NOT an internal
    defect — must classify as expected so the strict-errors guard does not
    re-raise it. Carries the offending ``subscript`` so callers can format
    bash's ``NAME[SUBSCRIPT]: bad array subscript`` form."""
    exit_code = 1

    def __init__(self, subscript: int, message: str = "bad array subscript"):
        self.subscript = subscript
        super().__init__(message)
