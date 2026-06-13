"""The single last-resort guard for unexpected internal exceptions.

When an exception that is NOT a deliberate shell-semantics or control-flow
signal escapes command execution, it almost certainly indicates an internal
defect in psh rather than a normal command failure. Interactively we want the
shell to stay alive (report a generic message, return status 1); but a test
harness wants the defect surfaced loudly so it can be told apart from an
ordinary nonzero exit.

``report_internal_defect`` is the one place that decides between those two
behaviors based on the ``strict-errors`` shell option. The three structurally
identical guards (command dispatch, builtin execution, function body) all
delegate here so the policy lives in a single source of truth.
"""

from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from .state import ShellState


def report_internal_defect(state: 'ShellState', exc: BaseException, *,
                           prefix: str = '', stream: TextIO) -> int:
    """Handle an UNEXPECTED exception escaping command execution.

    Callers must already have re-raised the deliberate shell-semantics and
    control-flow exceptions (FunctionReturn/LoopBreak/LoopContinue/SystemExit,
    ReadonlyVariableError, ExpansionError, ...) so that only genuine "this is
    probably a bug" exceptions reach here.

    In strict-errors mode, re-raise ``exc`` so tests surface the defect.
    Re-raising from outside the original ``except`` frame still preserves
    ``exc.__traceback__``, so the traceback points at the real fault.

    Otherwise print a generic ``psh: {prefix}{exc}`` message (full traceback
    under debug-exec) and return 1, keeping an interactive shell alive.
    """
    if state.options.get('strict-errors'):
        raise exc
    if state.options.get('debug-exec'):
        import traceback
        traceback.print_exc(file=stream)
    print(f"psh: {prefix}{exc}", file=stream)
    return 1
