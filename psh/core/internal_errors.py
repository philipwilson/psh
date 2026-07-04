"""The single last-resort guard for unexpected internal exceptions.

When an exception that is NOT a deliberate shell-semantics or control-flow
signal escapes command execution, it almost certainly indicates an internal
defect in psh rather than a normal command failure. Interactively we want the
shell to stay alive (report a generic message, return status 1); but a test
harness wants the defect surfaced loudly so it can be told apart from an
ordinary nonzero exit.

``report_internal_defect`` is the one place that decides between those two
behaviors based on the ``strict-errors`` shell option. The four structurally
identical guards (command dispatch, builtin execution, function body,
buffered-statement source guard) all delegate here so the policy lives in a
single source of truth.

The expected-error taxonomy
---------------------------
Even in ``strict-errors`` mode, not every exception reaching a last-resort
guard is an internal defect. Some are legitimate shell-error paths that
happen to be signalled via exceptions, and strict mode must NOT re-raise
them — they get the normal "print message / return 1" handling. An exception
is an **expected shell error** (never strict-re-raised) when it is one of:

- ``PshError`` — psh's own error root (``ExpansionError``,
  ``ShellArithmeticError``, ``UnboundVariableError``,
  ``FunctionDefinitionError``, ...).
- ``OSError`` — syscall/IO failures (redirections: bad fd, noclobber,
  rollback, missing dir, permission; fork failures, EAGAIN).
- ``SyntaxError`` — lex/parse failures during eval/source/trap (e.g.
  ``UnclosedQuoteError``).

Everything else (``RuntimeError``, ``AttributeError``, ``TypeError``,
``KeyError``, ``NameError``, ``IndexError``, plain ``ValueError``, ...) is
an **internal defect**, and strict mode re-raises it so the test harness can
tell a Python bug apart from an ordinary nonzero command exit.

Note: control-flow signals and the specifically-handled PshErrors are dealt
with by the callers BEFORE reaching here, so this taxonomy only governs the
residual exception that escaped to a last-resort guard.
"""

from typing import TYPE_CHECKING, NoReturn, TextIO

from .exceptions import (
    FatalExpansionError,
    PshError,
    TopLevelAbort,
    UnboundVariableError,
)

if TYPE_CHECKING:
    from .state import ShellState


# Exceptions that are legitimate shell errors, not internal defects. Even in
# strict-errors mode these are handled normally (printed, exit 1) rather than
# re-raised. See the module docstring for the rationale.
_EXPECTED_SHELL_ERRORS = (PshError, OSError, SyntaxError)


def fatal_expansion_status(state: 'ShellState', exc: BaseException, *,
                           at_boundary: bool = False) -> int:
    """Apply bash's fatal expansion-error model (message already printed).

    bash 5.2, probe-verified (tmp/probes-r17t2-arith/truth_table.py — error
    kinds x contexts x input modes). Two families:

    - **Shell-exit family** — ``${x:?msg}``, runtime bad substitution
      (``FatalExpansionError``) and ``set -u`` violations
      (``UnboundVariableError``): a NON-interactive shell (script file,
      ``-c``, piped stdin) EXITS. The status is 1 for a script file or
      piped stdin regardless of kind; under ``-c`` it is the error's own
      status — 127 for ``:?``/``set -u``/unknown-``@X``-transform, but 1
      for a bad parameter NAME (``bash -c 'echo ${}'`` exits 1 while
      ``bash -c 'echo ${x@Z}'`` with x set exits 127). No enclosing
      construct contains it (not even ``eval``); subshell/cmdsub children
      simply exit. An interactive (or embedded/test) shell instead discards
      the current line with status 1.

    - **Discard-line family** — every other expansion failure
      (``$((1/0))``, arith syntax errors, bad subscripts ``${a[1//]}``,
      substring errors, invalid indirection, ``:=`` on positionals, ...):
      the REST OF THE CURRENT LINE is dropped (kills ``&&``/``||`` tails,
      if-bodies, the rest of a function/group/loop body on the same input
      line) and execution resumes at the NEXT input line with status 1 —
      in every input mode. Contained at subshell/cmdsub boundaries AND at
      the ``eval``/``source``/trap-action buffered boundaries (bash resumes
      the sourced file's next line; ``eval 'X; echo y'; echo after`` kills
      ``y`` but runs ``after``). Notably it does NOT interact with
      ``set -e`` (bash resumes the next line even under errexit).

    ``at_boundary=True`` is for callers already AT a buffered-command
    boundary (the source-processor guard): the discard is complete there,
    so the status is returned instead of raising ``TopLevelAbort``.
    """
    if isinstance(exc, (FatalExpansionError, UnboundVariableError)):
        if state.options.get('command_mode'):
            code = getattr(exc, 'exit_code', 127)  # UnboundVariable: 127
        else:
            code = 1
        if state.is_script_mode:
            raise SystemExit(code)
        if at_boundary:
            return code
        raise TopLevelAbort(code)
    # Discard-line family: errexit-immune (bash resumes the next line even
    # under set -e — unlike a readonly or failglob discard).
    if at_boundary:
        state.errexit_eligible = False
        return 1
    raise TopLevelAbort(1, errexit_immune=True)


def arith_assignment_discard(state: 'ShellState') -> NoReturn:
    """Discard for an arithmetic error in ASSIGNMENT or SUBSCRIPT position.

    Covers ``declare -i v='1/0'`` / ``local -i``, a plain assignment to an
    integer-attributed variable, array-subscript evaluation failures on
    read and write (``${a[1//]}``, ``a[1//]=x``, ``unset 'a[08]'``).

    bash 5.2 (probe-verified, tmp/probes-r17t2-arith/): a HARDER discard
    than the word-arithmetic family. In every input mode it passes THROUGH
    eval/source containment — bash kills the rest of the eval'd string /
    the whole sourced file AND the caller's line, resuming only at the
    top-level input loop's next line. Under ``-c`` (where the whole string
    is the input) that means the REST OF THE ``-c`` STRING is abandoned
    (rc 1). Contained at fork boundaries (command substitution, subshells)
    like everything else. Word-arithmetic ``$((1/0))`` errors, by
    contrast, are contained per buffered command (eval/source resume).
    Like the other discard kinds this one is errexit-immune. The caller
    must already have printed the message.
    """
    if state.options.get('command_mode'):
        raise SystemExit(1)
    raise TopLevelAbort(1, errexit_immune=True, contain_nested=False)


def report_internal_defect(state: 'ShellState', exc: BaseException, *,
                           prefix: str = '', stream: TextIO) -> int:
    """Handle an UNEXPECTED exception escaping command execution.

    Callers must already have re-raised the deliberate shell-semantics and
    control-flow exceptions (FunctionReturn/LoopBreak/LoopContinue/SystemExit,
    ReadonlyVariableError, ExpansionError, ...) so that only genuine "this is
    probably a bug" exceptions reach here.

    In strict-errors mode, re-raise ``exc`` so tests surface the defect —
    but ONLY when ``exc`` is a genuine internal defect. Expected shell errors
    (``PshError``/``OSError``/``SyntaxError``; see ``_EXPECTED_SHELL_ERRORS``
    and the module docstring) fall through to normal handling even under
    strict mode. Re-raising from outside the original ``except`` frame still
    preserves ``exc.__traceback__``, so the traceback points at the real
    fault.

    Otherwise print a generic ``psh: {prefix}{exc}`` message (full traceback
    under debug-exec) and return 1, keeping an interactive shell alive.
    """
    if (state.options.get('strict-errors')
            and not isinstance(exc, _EXPECTED_SHELL_ERRORS)):
        raise exc
    if state.options.get('debug-exec'):
        import traceback
        traceback.print_exc(file=stream)
    print(f"psh: {prefix}{exc}", file=stream)
    return 1
