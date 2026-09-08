"""The single last-resort guard for unexpected internal exceptions.

When an exception that is NOT a deliberate shell-semantics or control-flow
signal escapes command execution, it almost certainly indicates an internal
defect in psh rather than a normal command failure. Interactively we want the
shell to stay alive (report a generic message, return status 1); but a test
harness wants the defect surfaced loudly so it can be told apart from an
ordinary nonzero exit.

``report_internal_defect`` is the one place that decides between those two
behaviors based on the ``strict-errors`` shell option. Every structurally
identical last-resort guard delegates here so the policy lives in a single
source of truth — the current delegates are command dispatch
(``executor/command.py``), builtin execution (``executor/strategies.py``),
control-flow / compound execution (``executor/control_flow.py``), the function
body (``executor/function.py``), the buffered-statement source guard
(``scripting/source_processor.py``), the analysis-visitor modes
(``scripting/visitor_modes.py``), and trap-action bodies
(``core/trap_manager.py``). (Grep for ``report_internal_defect(`` rather than
trusting a hard count here — new guards are expected to route through it.)

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
- ``RecursionError`` — the interpreter recursion limit is psh's de-facto
  nesting ceiling (an implicit FUNCNEST), so hitting it is a legitimate
  runaway-script error, not a psh bug. The function-call boundary converts
  it to bash's "maximum function nesting level exceeded" abort before it
  can reach a guard; this entry covers the function-less paths (deep
  ``eval`` chains, deeply nested compounds at execution time).

Everything else (other ``RuntimeError``s, ``AttributeError``, ``TypeError``,
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
    from ..shell import Shell
    from .state import ShellState


# Exceptions that are legitimate shell errors, not internal defects. Even in
# strict-errors mode these are handled normally (printed, exit 1) rather than
# re-raised. See the module docstring for the rationale.
_EXPECTED_SHELL_ERRORS = (PshError, OSError, SyntaxError, RecursionError)


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
      ``bash -c 'echo ${x@Z}'`` with x set exits 127) — **unless ERREXIT is
      on, which forces 1** (see the errexit note below). No enclosing
      construct contains it (not even ``eval``); subshell/cmdsub children
      exit with the CHILD status instead (see
      :func:`fatal_expansion_child_status`). An interactive (or embedded/test)
      shell instead discards the current line with status 1.

      **The errexit override on the ``-c`` status (slot 3.5, ruling (d)).**
      ``bash -c 'set -e; echo ${x?boom}'`` exits **1**, not 127. Probed
      against bash 5.2.26 across the whole family (``${x?}``, ``${x:?}``,
      unknown ``@X``, ``set -u``, and through ``eval``), both ``set -e`` and
      ``set -o errexit`` spellings, and re-verified by the integrator.
      Two properties make this rule NOT the one its
      :func:`substitution_abort_status` sibling uses, and both are pinned:

      * it reads the RAW errexit FLAG, not EFFECTIVE errexit — every
        suppressing context (``|| recover``, an ``if``/``while`` condition,
        ``!``, a non-final ``&&``) still yields 1, and none of them recovers,
        because the shell-exit is the expansion's own and errexit merely
        colours its status. The sibling, by contrast, must subtract the
        suppression;
      * it is the CURRENT flag: ``set -e; set +e`` is back to 127.

      Reasoning from the sibling by analogy gives the wrong answer here; the
      probe is the authority.

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
        channel = False
        if (state.options.get('command_mode')
                and not state.options.get('interactive')):
            if state.options.get('errexit', False):
                # errexit forces 1 over the -c channel status. RAW flag, not
                # effective errexit — see the docstring's two pinned
                # properties (ruling (d)).
                code = 1
            else:
                code = getattr(exc, 'exit_code', 127)  # UnboundVariable: 127
            channel = True
        else:
            # Interactive-family shells discard the line with status 1 even
            # for a -c string: `bash -ic 'set -u; echo $undef; echo after'`
            # exits 1, not 127 (probe B6, campaign F1).
            code = 1
        # The stamp: only a status produced by the CHANNEL branch above is
        # re-mapped at a fork boundary (A10.1); everything else keeps its own
        # status. BOTH exits out of this branch must carry it — a ``-c``
        # invocation has ``is_script_mode`` True (the script NAME is set), so
        # the SystemExit route below is the one the ``-c`` channel actually
        # takes, and stamping only the TopLevelAbort would fix the model
        # everywhere except the channel that motivates it.
        if state.is_script_mode:
            exc_exit = SystemExit(code)
            exc_exit.fatal_expansion_channel = channel  # type: ignore[attr-defined]
            raise exc_exit
        if at_boundary:
            return code
        raise TopLevelAbort(code, fatal_expansion_channel=channel)
    # Discard-line family: errexit-immune (bash resumes the next line even
    # under set -e — unlike a readonly or failglob discard).
    if at_boundary:
        state.errexit_eligible = False
        return 1
    raise TopLevelAbort(1, errexit_immune=True)


def fatal_expansion_child_status(state: 'ShellState') -> int:
    """The FORKED-CHILD half of :func:`fatal_expansion_status`'s shell-exit
    family — the A10.1 rule.

    A forked child does NOT use the CHANNEL rule: it exits **1** for a
    ``${x?}``/``${x:?}``/unknown-``@X``/``set -u`` failure even inside a ``-c``
    shell, where the main shell uses 127. Consumed at the fork boundary by
    ``executor/child_policy.py#map_child_exception``, keyed on the
    ``fatal_expansion_channel`` stamp the raise site applied — never re-derived
    from ``state``, which cannot tell a stamped abort from a readonly discard.

    **It is FLAT 1, and that is the whole point of this function existing
    separately from its sibling.** :func:`substitution_child_abort_status`
    drops the channel rule but KEEPS an errexit branch (its child is 2 under
    effective errexit), and its docstring warns the status is "NOT a flat
    constant". The analogy does not carry: probed against bash 5.2.26 (slot
    3.5), the fatal-expansion child is 1 with errexit OFF, with errexit ON
    outside the fork, with errexit ON *inside* the fork
    (``( set -e; echo ${x?boom} ) || echo "child rc=$?"`` -> 1), in an
    ``if`` condition, and for both the subshell and command-substitution
    routes. So there is no errexit branch and no suppression argument to
    thread — deliberately, on evidence, not by omission.

    Takes ``state`` for signature symmetry with the sibling and to keep the
    call site uniform; a future channel- or option-dependence would land here
    rather than at the boundary.
    """
    return 1


def substitution_abort_status(state: 'ShellState', nested: bool,
                              errexit_suppressed: bool) -> int:
    """The ONE status mapping for a substitution-origin shell abort.

    Consumes ``SubstitutionSyntaxAbort`` at the outermost boundary
    (``scripting/source_processor.py#execute_as_main``). bash 5.2.26's status
    for this fatality is NOT a single number — it depends on the channel and
    on where the error was found — so the whole mapping lives here rather than
    as scattered exit-code comparisons at the frames.

    Probe-verified (slot 2.4 batteries under ``tmp/r24-probes/``, PATH bash
    5.2.26, every row run in the ``-c``, script-file and stdin channels):

    * ``set -e`` active -> **2**, in every channel and for both the direct and
      the eval/source-nested shapes. errexit is checked FIRST because it wins
      over the ``-c`` rule (``set -e`` under ``-c`` gives 2, not 127). It is
      EFFECTIVE errexit: in a suppressing context (``||``, ``&&`` non-final, an
      ``if``/``while`` condition, ``!``) bash uses the ordinary channel status
      instead, so the flag alone is not enough. The suppression is read from
      the stamp the error carries (see
      ``core/exceptions.py#SubstitutionSyntaxAbort``), never re-derived here.
    * ``-c`` (``command_mode``) -> **127**, at any nesting depth and for either
      error kind: the direct parse, or an ``eval``/``source``/function/trap
      frame inside the ``-c`` string, all give 127 — provided both of
      ``SourceProcessor``'s syntax-error exits reach this policy (see
      ``core/exceptions.py#SubstitutionSyntaxAbort``).
    * a script FILE or stdin -> **2** when the outermost source's own parse
      found it, **1** when it came from a nested ``eval``/``source`` string.
      The 1 is bash's ``EX_BADSYNTAX`` (257) truncated to 8 bits; psh reports
      the real status rather than replicating the pre-truncation internal that
      bash leaks into ``$?`` inside an EXIT trap (declared divergence, pinned).

    A FORKED child does not come here: it goes through
    :func:`substitution_child_abort_status` instead, which drops the CHANNEL
    rule (a subshell/cmdsub/pipeline member inside a ``-c`` shell exits 1, not
    127) but keeps the errexit branch above.
    """
    if state.options.get('errexit', False) and not errexit_suppressed:
        return 2
    if state.options.get('command_mode'):
        return 127
    return 1 if nested else 2


def substitution_child_abort_status(state: 'ShellState',
                                    errexit_suppressed: bool) -> int:
    """The FORKED-CHILD half of :func:`substitution_abort_status`.

    A forked child does NOT use the channel rule — it exits 1 even inside a
    ``-c`` shell, where the main shell uses 127. Probed per ROUTE (slot 2.4
    batteries ``tmp/r24-probes/r7a.py`` and ``r6b*.py``): subshell, brace
    group, command substitution, backticks, process substitution, pipeline
    members and every background spelling. ONE ROUTE DISAGREES and is
    DECLARED, not covered by this sentence: a child whose own command resolves
    DIRECTLY to a shell FUNCTION, where bash leaks the ``-c`` channel status
    (127) into the child — pinned as
    ``test_function_member_channel_rule_is_a_declared_divergence``.

    But it DOES honour the errexit branch, for the same reason that branch is
    FIRST in the main policy: with ``set -e`` active in the child, bash exits
    **2** there too — ``( set -e; eval 'echo $(if)' )`` leaves ``$?``=2 where
    the same subshell without errexit leaves 1.

    The errexit test is EFFECTIVE errexit, not the raw flag: bash consults the
    flag MINUS the suppression context. ``set -e`` with the fork inside a
    suppressing context — ``( … ) || recover``, an ``if``/``while`` condition,
    a ``!`` negation — leaves the child at **1**, because errexit does not
    apply there; the same fork outside such a context is 2. The two shapes are
    indistinguishable from ``state`` alone (both read ``errexit=True``), which
    is why the suppression depth is passed IN from the fork site.

    WHICH forks inherit that depth is bash's severing rule, not a per-site
    choice: a fork whose body is a COMPOUND command or a directly-invoked
    FUNCTION carries it; a fork running a BARE SIMPLE command severs it and
    runs with errexit effective (``executor/context.py#errexit_suppress_deferred``
    quotes the manual sentence). It holds at the pipeline-member route and at
    the background route alike — but NOT at the substitution routes, where
    bash's rule is spelling-split: an ARGUMENT-spelled substitution child
    (``$( )``, backticks, ``<( )``) keeps the enclosing context's suppression,
    while a REDIRECTION-spelled procsub (``< <( )``, ``> >( )``) runs with
    errexit effective (the declared divergence is pinned by
    ``test_redirect_procsub_suppression_is_a_declared_divergence``).

    Kept beside the main policy rather than inlined at the fork sites so the
    two halves cannot drift: it is the SAME mapping restricted to the axis a
    child can see.
    """
    if state.options.get('errexit', False) and not errexit_suppressed:
        return 2
    return 1


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


def special_builtin_usage_discard(state: 'ShellState', status: int = 1) -> NoReturn:
    """Discard the current input unit after a special-builtin USAGE error.

    bash 5.2 (probe-verified, tmp bcontract battery): ``exit 7 8`` (too many
    arguments, valid first operand) and ``shift 1 2`` report the usage error
    but DO NOT exit the shell and DO NOT run the rest of the current input
    unit. The discard is identical in shape to
    :func:`arith_assignment_discard`: the rest of the current line dies
    (killing ``&&``/``||`` tails, an enclosing group/function/loop on the same
    input), execution resumes at the NEXT top-level input line, the discard
    passes THROUGH ``eval``/``source`` (contained only at fork boundaries), and
    it is errexit-immune (the next line runs even under ``set -e``). Both
    behaviours hold in default AND POSIX mode. Under ``-c`` the whole string is
    the input unit, so it is abandoned with ``status``.

    The caller must already have printed the error message.
    """
    if state.options.get('command_mode'):
        raise SystemExit(status)
    raise TopLevelAbort(status, errexit_immune=True, contain_nested=False)


def special_builtin_stops_at_first_bad_identifier(state: 'ShellState') -> bool:
    """Does a special builtin's IDENTIFIER error end its operand loop?

    The operand-loop half of the same bash 5.3 rule
    :func:`special_builtin_usage_exit` states (CHANGES, bash-5.3-alpha,
    "1. Changes to Bash" item jj, "POSIX special builtins now exit the shell
    in posix mode on more failure cases"; item nnnnn). In POSIX mode
    ``export``/``readonly`` diagnose the FIRST invalid identifier and stop —
    later operands are neither diagnosed nor created; in default mode the
    loop runs to completion (bash's continue-on-error declaration loop).

    The stop is a property of POSIX MODE ALONE, not of the exit: it still
    happens when ``command``/``builtin`` strips the exit, and inside a
    guard that suppresses it. Reproduce (bash 5.3.15, all three input
    modes)::

        set -o posix; export 1bad=x 2bad=y      # ONE diagnostic, exits 1
        set -o posix; command export 1bad=x 2bad=y   # ONE, rc 1, continues
        set -o posix; export 1bad=x 2bad=y || echo caught   # ONE, caught
        export 1bad=x 2bad=y                    # TWO diagnostics, rc 1

    ``unset`` is NOT in this class: its readonly refusals diagnose EVERY
    operand and exit afterwards (``set -o posix; readonly r=1 s=2; unset r s``
    prints both, exits 1).
    """
    return bool(state.options.get('posix'))


def special_builtin_usage_exit(shell: 'Shell', status: int,
                               suppressible: bool = False) -> int:
    """The ONE POSIX-mode special-builtin EXIT-on-error policy.

    Applied where a ``SpecialBuiltinUsageError`` surfaces from a DIRECT
    special-builtin invocation (the strategy paths of the builtin guard;
    ``command``/``builtin`` invocations bypass it, stripping the special
    property — bash/POSIX). The rule, probe-verified against bash 5.3.15 in
    the ``-c``, script-file and stdin modes
    (docs/reviews/posix_special_builtin_exit_matrix_2026-07-07.md):

    - In POSIX mode a NON-interactive shell — script file, ``-c``, piped
      stdin, all covered by ``is_script_mode`` — EXITS with the builtin's
      own status (2 for option/syntax usage errors; 1 for the readonly,
      identifier and dot-file cases). The exit is NOT contained by
      ``eval``/``source``/function calls/trap actions (``SystemExit``
      passes through them), only by fork boundaries (subshells, command
      substitution, pipeline members — the child exits, the parent
      survives, exactly like bash).
    - bash 5.3 WIDENED the exit set to OPERAND errors (CHANGES,
      bash-5.3-alpha, "1. Changes to Bash" item jj, "POSIX special builtins
      now exit the shell in posix mode on more failure cases"; item nnnnn,
      "Fix posix-mode cases where failure of special builtins did not cause
      the shell to exit"): an invalid identifier given to
      ``export``/``readonly``, and ``unset`` refusing a readonly variable,
      array, array element or function. Under the 5.2 series those reported
      and continued. ``readonly -f``/``unset -f`` NAME operands that are
      merely absent stay silent rc-0/rc-1 non-exits, and ``unset 1bad``
      remains a silent rc-0 no-op.
    - SUPPRESSIBLE outcomes (invalid options, top-level ``return``, and the
      5.3 operand class above) are exempt in errexit-suppressed contexts —
      if/while/until conditions, non-final &&/|| members, ``!``-negated
      pipelines — reaching through functions, brace groups, subshells AND,
      on bash 5.3, through an ``eval``/``.`` boundary: ``set -o posix; eval
      'set -q' || echo caught`` prints ``caught`` and the shell lives
      (5.2 exited there). The one boundary the suppression does NOT cross
      is a TRAP ACTION: a guard around the interrupted command does not
      reach the action bash runs between commands (``set -o posix; trap
      'set -q' DEBUG; false || echo caught`` still exits 2 —
      ``ExecutionContext.trap_action_boundary``). The HARD class (eval/dot
      syntax, missing/unreadable dot-file, readonly ASSIGNMENT) exits even
      when guarded.
    - Otherwise (default mode; interactive or embedded shells, where
      ``is_script_mode`` is False) the builtin simply FAILS with
      ``status`` — byte-identical to the pre-policy behavior.

    The exit PUBLISHES ``status`` as ``$?`` before raising, because the EXIT
    trap runs after the shell has unwound and reads the live
    ``last_exit_code``: ``set -o posix; trap 'echo rc=$?' EXIT; export
    1bad=x`` prints ``rc=1`` on bash 5.3.15 (``set -q`` prints 2), and a
    cleanup trap that branches on ``$?`` would otherwise see success where
    bash sees the failure. ``execute_as_main`` recovers the process status
    from the ``SystemExit`` itself, so this only fixes what the trap observes.

    The message was already printed at the raise site.
    """
    state = shell.state
    if state.options.get('posix') and state.is_script_mode:
        if suppressible:
            executor = getattr(shell, '_current_executor', None)
            if (executor is not None
                    and executor.context.special_exit_suppressed):
                return status
        state.last_exit_code = status
        raise SystemExit(status)
    return status


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

    The diagnostic write is BEST-EFFORT: after ``exec 2>&-`` the shell's own
    stderr fd is gone, so the message cannot be delivered (exactly as in bash,
    which silently can't report to a closed fd 2). Swallow that secondary write
    failure rather than letting it escape and abort the whole command list —
    the status (1) is still returned. The strict-errors re-raise above runs
    FIRST, so a genuine internal defect still surfaces regardless.
    """
    if (state.options.get('strict-errors')
            and not isinstance(exc, _EXPECTED_SHELL_ERRORS)):
        raise exc
    try:
        if state.options.get('debug-exec'):
            import traceback
            traceback.print_exc(file=stream)
        # bash location-prefixes these expected-shell-error reports (e.g. a
        # readonly-assignment escaping `declare`): `<$0>: line N: declare: x:
        # readonly variable`. See ShellState.error_location_prefix.
        print(f"{state.error_location_prefix()}{prefix}{exc}", file=stream)
    except (OSError, ValueError):
        pass
    return 1
