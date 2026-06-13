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

from typing import TYPE_CHECKING, TextIO

from .exceptions import PshError

if TYPE_CHECKING:
    from .state import ShellState


# Exceptions that are legitimate shell errors, not internal defects. Even in
# strict-errors mode these are handled normally (printed, exit 1) rather than
# re-raised. See the module docstring for the rationale.
_EXPECTED_SHELL_ERRORS = (PshError, OSError, SyntaxError)


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
