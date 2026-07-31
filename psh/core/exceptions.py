"""Core exceptions: the psh error hierarchy and control-flow signals.

Two distinct families live here — do not mix them up:

- **Errors** derive from ``PshError`` so callers can catch "any psh
  error" with one except clause. Every shell-specific error class in
  the tree (lexer, parser, arithmetic, expansion, builtins) roots here —
  including the lexer's ``UnclosedQuoteError``, which dual-inherits
  ``(PshError, SyntaxError)`` so it ALSO stays catchable by the
  ``except SyntaxError`` line-continuation sites that key off it (see its
  class docstring in ``lexer/position.py``).
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

    ``exit_status`` carries the break command's own exit status: 0 for a
    successful ``break`` (bash: like any command, it sets ``$?`` to 0, and
    the loop's status is that of the last command executed — the break
    itself), or 1 for the bash ``break 0``/negative "loop count out of
    range" case. ``None`` (a manually raised signal) makes the loop keep
    the last body status.
    """
    def __init__(self, level=1, exit_status=None):
        self.level = level
        self.exit_status = exit_status
        super().__init__()

class LoopContinue(Exception):
    """Exception used to implement continue statement.

    ``exit_status`` carries the continue command's own exit status —
    normally 0 (bash: a successful ``continue`` sets ``$?`` to 0, so a loop
    whose last executed command was the continue reports 0).
    """
    def __init__(self, level=1, exit_status=0):
        self.level = level
        self.exit_status = exit_status
        super().__init__()

class FunctionReturn(Exception):
    """Exception used to implement the return builtin."""
    def __init__(self, exit_code: int):
        self.exit_code = exit_code
        super().__init__()


class TopLevelAbort(BaseException):
    """A fatal runtime condition that DISCARDS the current command line but
    does NOT exit the shell — bash reports the error, unwinds the whole current
    top-level command (the rest of the command list and any enclosing
    ``if``/loop/function/brace group on the same logical input), then resumes at
    the NEXT top-level command (next input line). So::

        readonly r=1; r=2; echo X      # one line  -> X skipped (whole list aborts)
        readonly r=1
        r=2                            # own line  -> aborts here ...
        echo X                         # ... resumes: X prints

    Raised for a fatal variable-assignment error (readonly variable, circular
    nameref, ``declare -i``/plain ``-i`` values that fail to evaluate), for
    exceeding ``FUNCNEST``, for a failed arithmetic/parameter EXPANSION
    (``$((1/0))``, ``${a[1//]}``, ``${v:1:-5}``, ...; see
    ``fatal_expansion_status`` in internal_errors.py for the full model),
    and for a ``failglob`` no-match.

    Derives from ``BaseException`` (like ``SystemExit``) so it unwinds past the
    executor's ``except Exception`` guards without being mistaken for an
    internal defect; it is caught explicitly at EVERY buffered-command boundary
    (``SourceProcessor._execute_buffered_command``) — including the nested
    processors run by ``eval``, ``source`` and trap actions, which CONTAIN the
    discard exactly like bash 5.2 (``eval 'r=2; echo x'; echo after`` kills
    ``x`` but runs ``after``; a sourced file resumes at its own next line) —
    and at child-shell boundaries (subshell ``execute_fn``, ``run_child_shell``,
    ``ProcessLauncher`` children). The error message is printed at the raise
    site (bash prints it before unwinding).

    ``errexit_immune``: bash's expansion-error discards (``$((1/0))`` etc.)
    do NOT interact with ``set -e`` — the next line runs even under errexit
    (probe-verified) — while a readonly-assignment discard or a ``failglob``
    no-match under errexit DOES exit the shell. The flag tells the boundary
    handler to suppress the errexit check for the immune family.

    ``contain_nested``: the assignment/subscript arithmetic-error family
    (``declare -i v='1/0'``, ``${a[1//]}``; see ``arith_assignment_discard``)
    is NOT contained by eval/source — bash kills the rest of the eval'd
    string / the whole sourced file AND the caller's line, resuming only at
    the top-level input loop's next line (probe-verified in file, stdin and
    interactive modes). Those raisers pass ``contain_nested=False`` so
    nested buffered boundaries re-raise instead of containing.
    """
    def __init__(self, status: int = 1, errexit_immune: bool = False,
                 contain_nested: bool = True):
        self.status = status
        self.errexit_immune = errexit_immune
        self.contain_nested = contain_nested
        super().__init__()


class SubstitutionSyntaxAbort(BaseException):
    """A substitution-body syntax error TERMINATES the non-interactive shell.

    The I3 CONSUMER of the typed producer contract
    ``ParseError.substitution_origin`` (see
    ``parser/recursive_descent/helpers.py#SubstitutionSyntaxError``): bash
    treats a syntax error inside ``$(...)``/``<(...)``/``>(...)`` as fatal to
    the shell PROCESS, while an ORDINARY syntax error in the same position is
    not (``eval 'if'; echo A`` prints A; ``eval 'echo $(if)'; echo A`` does
    not). Carrying that distinction as a TYPE — rather than by comparing exit
    codes — is what this boundary used to lose.

    Semantically an ``exit``, NOT a discard: unlike :class:`TopLevelAbort`
    (which unwinds one command line and RESUMES) this ends the process. So:

    * NO frame contains it — not a function, an ``if`` condition, an ``&&``
      list, ``eval``, ``source``, a trap action, nor any nesting of those;
      nothing on those paths catches ``BaseException``, so propagation is
      automatic and no frame needs to know about it. TWO qualifications:
      (a) it holds only while BOTH of ``SourceProcessor``'s syntax-error exits
      raise this — the unterminated-body kind (``$(if)``) arrives via the
      flushed buffer, the complete-but-ill-formed kind (``$(fi)``) via the
      accumulator's trial parse, and wiring one leaves the frames containing
      the other; (b) there is exactly ONE deliberate catcher,
      ``core/trap_manager.py#TrapManager.execute_exit_trap``, which swallows it
      at teardown because a shell that is already exiting has nothing left to
      abort.
    * FORK boundaries DO contain it, because they are separate processes: a
      subshell, command/process substitution, a pipeline member and a
      background job all die while the parent continues — with status 1, or 2
      when EFFECTIVE errexit applies in the child. That falls out of
      ``executor/child_policy.py#CHILD_EXIT_EXCEPTIONS`` and
      ``core/internal_errors.py#substitution_child_abort_status``.
    * The EXIT trap still runs and observes the abort status, because the one
      consumption point is ``scripting/source_processor.py#execute_as_main``,
      which fires the trap after recovering the status.

    Raised only when the shell is NON-interactive: bash's interactive loop
    reports the diagnostic and carries on (a sourced file even resumes at its
    own next line).

    ``nested`` records WHERE the error was found — inside an ``eval``/
    ``source``/trap STRING (True) versus the outermost source's own parse
    (False). It selects the status, which is otherwise channel-dependent; the
    whole mapping lives in ``core/internal_errors.py#substitution_abort_status``
    rather than at the raise site, which cannot know the outermost channel.

    ``errexit_suppressed`` is STAMPED AT CONSTRUCTION from the live executor
    context's suppression depth, because the fact must travel WITH the error.
    A suppressing context entered INSIDE a forked child (``( set -e; cmd ||
    recover )``) is invisible at the fork boundary, and the counter unwinds as
    the exception propagates, so any later read is either blind or stale. The
    context's counter is already the TOTAL depth — seeded from the fork site
    and incremented by in-child contexts — so nothing needs composing here.
    Consumers READ THIS FIELD; no consumer re-derives it.
    """
    def __init__(self, nested: bool = False, errexit_suppressed: bool = False):
        self.nested = nested
        self.errexit_suppressed = errexit_suppressed
        super().__init__()


# --- Errors -------------------------------------------------------------

class SpecialBuiltinUsageError(PshError):
    """Typed outcome: a POSIX special builtin hit a USAGE/SYNTAX error.

    Raised by a special builtin's classified error branch AFTER it printed
    its diagnostic — an invalid option (``set -q``, ``export -q``, ...),
    ``return`` outside a function/sourced script, a missing/unreadable
    ``.``/``source`` file, an assignment to a readonly variable via
    ``readonly``/``export``, or a syntax error inside ``eval``/a sourced
    file (raised at the nested buffered-command boundary). ``status``
    carries the builtin's own exit status (2 for option/syntax usage
    errors, 1 for the readonly/dot cases).

    Converted by the ONE executor policy at the builtin guard
    (``execute_builtin_guarded`` → ``special_builtin_usage_exit``): in
    POSIX mode a NON-interactive shell (script/-c/piped stdin) EXITS with
    ``status``; otherwise — default mode, interactive, or an invocation
    through ``command``/``builtin`` (which strip the special property) —
    the builtin simply fails with ``status``, byte-identical to the
    pre-policy behavior. Operand/semantic errors (``export 1bad=x``,
    ``trap 'x' NOSUCHSIG``, ``unset r`` on a readonly) deliberately do NOT
    raise this. Truth table:
    docs/reviews/posix_special_builtin_exit_matrix_2026-07-07.md.

    ``suppressible`` records bash's TWO exit classes (probe-verified,
    tmp/posixexit/suppress_core.txt + suppress_rest.txt): INVALID-OPTION
    usage errors and a top-level ``return`` are SUPPRESSED in
    errexit-exempt contexts (if/while/until conditions, non-final &&/||
    members, ``!``-negated pipelines — reaching through functions, brace
    groups and subshells, but NOT through an eval/dot boundary): the
    builtin merely fails with ``status`` there (``set -o posix; set -q ||
    echo caught`` survives, rc 0). The eval/dot SYNTAX errors,
    missing/unreadable dot-file and readonly-assignment outcomes are HARD
    (``suppressible=False``): bash exits even inside a guard
    (``if . /missing; then`` exits rc 1).
    """
    def __init__(self, status: int = 2, suppressible: bool = False):
        self.status = status
        self.suppressible = suppressible
        super().__init__("")


class UnboundVariableError(PshError):
    """Raised when accessing unset variable with nounset option."""
    pass

class ReadonlyVariableError(PshError):
    """Raised when attempting to modify a readonly variable.

    The message is ``NAME: readonly variable`` (bash's word order) so a
    guard that prints ``psh: {builtin}: {exc}`` yields bash's
    ``declare: x: readonly variable`` form. Callers that build their own
    message use ``.name`` directly."""
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"{name}: readonly variable")

class NamerefCycleError(PshError):
    """Raised when writing through a circular nameref chain
    (declare -n a=b; declare -n b=a; a=5)."""
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"{name}: circular name reference")

class ExpansionError(PshError):
    """Raised when a word/parameter expansion fails at runtime.

    The message is printed at the RAISE site; the exception then carries
    the failure to the fatal-expansion chokepoints (``fatal_expansion_status``
    in internal_errors.py), which apply bash's DISCARD-LINE model: the rest
    of the current command line is dropped and execution resumes at the
    next input line. The two errors bash instead treats as fatal to a whole
    non-interactive shell (``${x:?}`` and bad substitution) use the
    ``FatalExpansionError`` subclass below."""
    def __init__(self, message: str, exit_code: int = 1):
        self.exit_code = exit_code
        super().__init__(message)

class FatalExpansionError(ExpansionError):
    """An expansion failure that EXITS a whole non-interactive shell (bash):
    ``${x:?msg}`` and an unknown ``${var@X}`` transform on a SET variable.
    bash 5.2, probe-verified (tmp/probes-r17t2-arith/): the shell exits —
    with the error's own status under ``-c`` (127 for these kinds) and 1
    for a script file / piped stdin — in EVERY enclosing context (function,
    if-condition, eval — eval does NOT contain it); an interactive shell
    just discards the current line with status 1. Contained at
    subshell/command-substitution boundaries (the child exits).
    All other expansion errors are plain ``ExpansionError`` = the
    discard-line family (the line dies, the next line runs)."""

class BadSubstitutionError(ExpansionError):
    """Raised at expansion time for a syntactically-invalid ``${...}``
    parameter NAME (bash: "${...}: bad substitution"). Examples:
    ``${}``, ``${ }``, ``${1abc}``, ``${.foo}``, ``${:-x}``. The braces are
    included in the message text to match bash's format. The name form is
    DISCARD-LINE family (bash resumes at the next line in every input
    mode, exit 1 for a one-line ``-c``) — unlike the unknown-``@X``
    transform bad substitution, which is fatal (``FatalExpansionError``,
    raised at its own site in operators.py)."""
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


class ReadError(PshError):
    """A ``read`` / ``mapfile`` option-VALUE error carrying bash's exit code.

    bash distinguishes an invalid *option* (a usage error — status 2, reported
    by ``parse_flags`` with the synopsis line) from an invalid option *value* —
    a bad file descriptor / count / timeout / origin (status 1, this class).
    ``rc`` carries that status so ``read`` and ``mapfile`` share ONE typed
    dialect instead of abusing a bare ``ValueError`` with a ``setattr``'d
    ``rc`` attribute. As a ``PshError`` it classifies as an EXPECTED shell
    error (the strict-errors guard never re-raises it) and roots at the one
    error base like every other shell error. The message is the bash text
    (``"<value>: invalid file descriptor specification"``, ...); the caller
    prints it via ``self.error(...)`` and returns ``rc``."""
    def __init__(self, message: str, rc: int = 1):
        self.rc = rc
        super().__init__(message)
