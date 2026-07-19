"""
Command execution module for the PSH executor.

This module handles the dispatch of simple commands:
- Command-word expansion
- Builtin, function, and external command execution via strategies
- Redirection handling

The ``NAME=value`` assignment sub-domain (extraction, value expansion,
application, restoration, and the POSIX ordering contract) lives in
`command_assignments.py`; this module decides WHEN each of those steps
runs and whether prefix assignments persist (a POSIX special builtin in
POSIX mode).
"""

import sys
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from ..ast_nodes import (
    ArrayElementAssignment,
    ArrayInitialization,
    LiteralPart,
    SimpleCommand,
    Word,
)
from ..builtins.base import EMPTY_BUILTIN_CONTEXT, BuiltinContext
from ..core import (
    ExpansionError,
    FunctionReturn,
    LoopBreak,
    LoopContinue,
    NamerefCycleError,
    OptionHandler,
    ReadonlyVariableError,
    SpecialBuiltinUsageError,
    TopLevelAbort,
    UnboundVariableError,
    arith_assignment_discard,
    fatal_expansion_status,
    report_internal_defect,
    special_builtin_usage_exit,
)
from ..io_redirect.manager import format_redirect_error
from ..parser.array_flat_text import array_init_argv_key
from .array import ArrayOperationExecutor
from .command_assignments import CommandAssignments
from .command_resolution import (
    CommandEnvOverlay,
    DispatchKind,
    NormalizedCommandName,
    ResolvedCommand,
    normalize_command_word,
    resolve_command,
)
from .strategies import (
    BuiltinExecutionStrategy,
    ExecutionStrategy,
    ExternalExecutionStrategy,
    FunctionExecutionStrategy,
    SpecialBuiltinExecutionStrategy,
    report_unbound_variable,
)

if TYPE_CHECKING:
    from ..shell import Shell
    from .command_assignments import RawAssignment
    from .context import ExecutionContext
    from .core import ExecutorVisitor


# The dispatch kinds that shift a name (not None) into the job manager's
# last-simple-command register — module constant so the hot dispatch path
# does not rebuild the tuple each call.
_BUILTIN_DISPATCH_KINDS = frozenset(
    {DispatchKind.SPECIAL_BUILTIN, DispatchKind.BUILTIN})


class RedirectionMode(Enum):
    """How a matched command's redirections are applied.

    Once a command name resolves to an execution strategy, exactly one of
    these modes governs the redirection handling. The choice is decided in
    one place (``_decide_redirection_mode``) and dispatched in one place
    (``_invoke_resolution``).

    BUILTIN_INPROCESS
        A builtin (or special builtin) running in THIS process, not in a
        pipeline and not in a forked child. Redirections are applied at the
        Python-stream level and saved/restored around the single command
        (``_execute_builtin_with_redirections``), so they do not persist.

    CHILD_DEFERRED
        A command whose forked child owns redirection setup: an external
        command, and any BACKGROUNDED builtin or function. Its redirections
        are NOT applied here — they are set up once inside the forked child
        (``setup_child_redirections``). Applying them in the parent too would
        resolve ``2>&1`` against already-redirected fds and, worse, run
        heredoc/target command substitutions TWICE (F3): once in the parent
        and once in the child.

    FD_LEVEL_WINDOW
        Everything else — functions, aliases, and FOREGROUND builtins that
        run in a pipeline or in a forked child. Redirections are applied at
        the fd level via ``io_manager.with_redirections`` (a save/restore
        window) because in a forked child builtins use ``os.write()`` on raw
        fds, so ``os.dup2()`` redirection is required rather than
        Python-level ``sys.stdout`` replacement.
    """

    BUILTIN_INPROCESS = "builtin_inprocess"
    CHILD_DEFERRED = "child_deferred"
    FD_LEVEL_WINDOW = "fd_level_window"


@dataclass
class ExecutionResult:
    """The result of *invoking* a resolved command.

    Replaces the previous ``(exit_code, is_special)`` tuple side-channel.
    The "do prefix assignments persist?" policy is now a NAMED field rather
    than a positional boolean, and there is room to grow (job/process
    metadata) without re-threading every call site.

    status
        The command's exit status.
    prefix_assignments_persist
        True when, in POSIX mode, the invoked command was a POSIX special
        builtin, so the caller (:meth:`CommandExecutor._run_command`) must
        NOT restore the prefix assignments — they persist in the current
        shell. False in default mode (carried through unchanged from the
        resolved command's ``assignments_persist``).
    """

    status: int
    prefix_assignments_persist: bool = False


class CommandExecutor:
    """
    Handles execution of simple commands.

    This class encapsulates the dispatch logic for SimpleCommand nodes —
    expansion, strategy selection, redirections — delegating the
    assignment sub-domain to CommandAssignments.
    """

    def __init__(self, shell: 'Shell', visitor: 'ExecutorVisitor'):
        """Initialize the command executor.

        Args:
            shell: The shell instance providing access to all components.
            visitor: The ExecutorVisitor that owns this executor;
                strategies receive it to execute function bodies and
                compound commands.
        """
        self.shell = shell
        self.visitor = visitor
        self.state = shell.state
        self.expansion_manager = shell.expansion_manager
        self.io_manager = shell.io_manager
        self.job_manager = shell.job_manager
        self.builtin_registry = shell.builtin_registry
        self.function_manager = shell.function_manager

        # The NAME=value sub-domain (extract/apply/restore + the POSIX
        # ordering contract) lives in its own specialist.
        self.assignments = CommandAssignments(shell)

        # Initialize execution strategies.
        # Order matters: functions > builtins (special or not) > external —
        # bash's default-mode lookup order, where functions shadow even
        # POSIX special builtins (`exit(){ ...; }; exit` runs the function;
        # POSIX puts special builtins first, which bash honors only in
        # POSIX mode). The special/regular builtin split still matters for
        # prefix-assignment persistence. Aliases are NOT a runtime
        # strategy: they are expanded as a token-stream transform at the
        # lex→parse boundary (AliasManager.expand_aliases, wired in
        # scripting/source_processor.py and command_accumulator.py), so by
        # the time the executor runs the command word is already the
        # alias-expanded token.
        # An immutable tuple, built once — resolve_command receives it
        # directly (no per-dispatch conversion; R3 bounce perf wiring).
        self.strategies = (
            FunctionExecutionStrategy(),
            SpecialBuiltinExecutionStrategy(),
            BuiltinExecutionStrategy(),
            ExternalExecutionStrategy(),
        )

    def execute(self, node: 'SimpleCommand', context: 'ExecutionContext') -> int:
        """
        Execute a simple command and return exit status.

        Args:
            node: The SimpleCommand AST node to execute
            context: The current execution context

        Returns:
            Exit status code
        """
        # Own any process substitutions this command creates (as arguments
        # or redirect targets): when the command finishes, the parent-side
        # fds are closed and the children reaped non-blockingly
        # (still-running ones are polled at later scope exits), so
        # `cat <(echo a)` neither leaks fds nor leaves zombies.
        with self.io_manager.process_sub_scope():
            return self._execute_command(node, context)

    def _execute_command(self, node: 'SimpleCommand', context: 'ExecutionContext') -> int:
        """Coordinate execution of a simple command.

        This is the thin dispatcher: it runs the per-command preamble
        (DEBUG trap, array assignments, raw-assignment extraction, the
        command-substitution-status reset), decides between the two
        execution shapes, and owns the shared error-to-exit-status mapping.

        - A **pure assignment** (leading ``NAME=value`` words with NO
          command word, e.g. ``x=1`` or ``arr=(a b c)``) sets variables in
          the current shell and runs no program → :meth:`_run_pure_assignment`.
        - An **actual command invocation** (a command word is present, with
          optional ``NAME=value`` prefixes that become temporary env) →
          :meth:`_run_command`.

        Both paths share the ``try/except`` here so the error taxonomy in
        :meth:`_handle_execution_error` applies uniformly.
        """
        try:
            # $BASH_COMMAND: stamp the node before the DEBUG trap fires so
            # the trap action (and the command's own expansions) see this
            # command. The pre-expansion text is rendered lazily, only when
            # $BASH_COMMAND is actually read (ShellState.bash_command).
            self.shell.trap_manager.set_bash_command(node)

            # bash runs the DEBUG trap before each simple command
            self.shell.trap_manager.execute_debug_trap()

            # Phase 1: Extract raw assignments (before expansion)
            raw_assignments = self.assignments.extract(node)

            # Track command substitutions run while expanding assignment
            # values. The clear must happen HERE — before ANY value expansion
            # (array element/init value, scalar value, OR command word) — so a
            # bare assignment's status is the last command substitution run
            # while expanding it: `a[0]=$(false)` -> 1, `a=($(sh -c 'exit
            # 7'))` -> 7, `V=v $(false)` -> 1 (F7). Previously it cleared AFTER
            # the array-assignment preamble, wiping the array value's status.
            self.state.last_cmdsub_status = None

            # A backgrounded pure / bare-array assignment (`x=5 &`, `a[0]=v &`)
            # runs in a forked SUBSHELL (bash): the assignment mutates the child
            # (which then exits), never the parent, and a background job / $! is
            # created. Without this, `x=5 & wait; echo $x` wrongly printed 5.
            # This is checked BEFORE applying any array assignment, so the
            # parent is never touched.
            is_pure_assignment = (
                raw_assignments and len(raw_assignments) == len(node.words))
            is_bare_array_assignment = (
                node.array_assignments and not node.words)
            if node.background and (is_pure_assignment or is_bare_array_assignment):
                return self._run_background_assignment(node, raw_assignments)

            # Prefix-position array element assignment (`a[0]=x cmd`): bash does
            # NOT accept an array-element subscript as a command-prefix
            # identifier — it prints "`a[0]': not a valid identifier", does NOT
            # create the array, and still runs the command (F7). A scalar
            # prefix `X=v cmd` is handled normally by _run_command below.
            if node.array_assignments and node.words:
                for assignment in node.array_assignments:
                    print(f"psh: `{self._array_assignment_lhs(assignment)}': "
                          "not a valid identifier", file=self.state.stderr)
                return self._run_command(node, context, raw_assignments)

            # Bare array assignment(s) with no command word (`a[i]=v`,
            # `a=(...)`): applied in the current shell under the SAME status
            # model as a pure scalar assignment (F7).
            if is_bare_array_assignment:
                return self._run_bare_array_assignment(node)

            # Pure assignment (only NAME=value words, no command word)?
            if is_pure_assignment:
                return self._run_pure_assignment(node, raw_assignments)

            # Actual command invocation (command word present).
            return self._run_command(node, context, raw_assignments)

        except Exception as e:
            return self._handle_execution_error(e)

    def _run_pure_assignment(self, node: 'SimpleCommand',
                             raw_assignments: List['RawAssignment']) -> int:
        """Run a pure assignment command — variables set, no program run.

        Delegates to :meth:`CommandAssignments.apply_pure`, which expands
        each value (left-to-right, so later values see earlier ones),
        applies them under the node's redirections, and returns 0 unless a
        command substitution ran while expanding (then that substitution's
        status) or a readonly/nameref error occurred (status 1, aborting a
        non-interactive shell).
        """
        return self.assignments.apply_pure(node, raw_assignments)

    def _run_background_assignment(self, node: 'SimpleCommand',
                                   raw_assignments: List['RawAssignment']) -> int:
        """Run a backgrounded pure/array assignment in a forked subshell (bash).

        ``x=5 &`` applies the assignment in the child (which immediately exits),
        so the PARENT's variables are untouched; a background job is registered
        and ``$!`` is set. The FOREGROUND call returns 0 (a backgrounded
        command's own status is success), but the JOB's exit status is the
        assignment's OWN status collected in the child (F7:
        ``x=$(false) & wait $!`` -> 1, ``a[-1]=x & wait $!`` -> nonzero) — not
        an unconditional 0.
        """
        launcher = self.shell.process_launcher
        command_string = " ".join(str(a) for a in node.args) or "assignment"

        def execute_fn() -> int:
            # In the forked child only. Clear the cmdsub tracker so the child's
            # own value expansion determines the status, then apply and RETURN
            # the assignment's status (a fatal discard raises to the launcher
            # child, which maps it to the exit code).
            self.state.last_cmdsub_status = None
            if node.array_assignments:
                return self._run_bare_array_assignment(node)
            return self._run_pure_assignment(node, raw_assignments)

        return launcher.launch_background_job(
            execute_fn, command_string, command_string, is_shell_process=True)

    def _run_bare_array_assignment(self, node: 'SimpleCommand') -> int:
        """Run bare array assignment(s) with no command word (`a[0]=v`, `a=(1 2)`).

        Joins the same status model as a pure scalar assignment
        (:meth:`CommandAssignments.apply_pure`) rather than the old separate
        preamble (F7):

        - Assignments apply left to right; each element/init value expansion
          records ``state.last_cmdsub_status`` (the caller cleared it first).
        - The command's status is that last command-substitution status if one
          ran while expanding (bash: ``a[0]=$(false)`` -> 1,
          ``a=($(sh -c 'exit 7'))`` -> 7), else 0. A SUCCESSFUL operation whose
          value's substitution failed is NOT an operation failure.
        - A failed assignment OPERATION (bad subscript, readonly) is fatal: it
          stops later assignments (first-failure — bash's ``a[-1]=x b[0]=y``
          does NOT assign ``b``) and discards the current command like any
          assignment/subscript error — ``SystemExit`` under ``-c``, abort of
          the current top-level command otherwise (``arith_assignment_discard``,
          the same discard the arithmetic-subscript path already uses).
        - Redirections apply after the assignments (bash order); a setup
          failure prints the one diagnostic and fails with 1.
        """
        for assignment in node.array_assignments:
            if self._handle_array_assignment(assignment) != 0:
                # Operation failure (diagnostic already printed by the array
                # executor): first-failure stop + discard the current command.
                arith_assignment_discard(self.state)
        if node.redirects:
            with self.io_manager.guarded_redirections(node.redirects) as ok:
                if not ok:
                    return 1
        if self.state.last_cmdsub_status is not None:
            return self.state.last_cmdsub_status
        return 0

    @staticmethod
    def _array_assignment_lhs(assignment) -> str:
        """Render an array assignment's left-hand side for a diagnostic.

        ``a[0]`` for an element assignment, ``a`` for a whole-array init — used
        only for the "not a valid identifier" prefix-position message (F7), so
        the exact index rendering is not compared against bash's.
        """
        if isinstance(assignment, ArrayElementAssignment):
            return f"{assignment.name}[{assignment.index}]"
        return getattr(assignment, 'name', '?')

    def _run_command(self, node: 'SimpleCommand', context: 'ExecutionContext',
                     raw_assignments: List['RawAssignment']) -> int:
        """Run an actual command invocation (a command word is present).

        Handles, in order: command-word expansion (BEFORE prefix
        assignments take effect, per POSIX), the redirect-only and
        words-vanish edge cases, prefix-assignment application with
        ``set -e`` abort, xtrace, the ``exec`` special case, array-init
        delivery to declaration builtins, strategy dispatch, and prefix
        restoration (skipped in POSIX mode for a POSIX special builtin, so
        those assignments persist).

        ``raw_assignments`` are the leading ``NAME=value`` prefix words
        already extracted by the coordinator.
        """
        tokens_consumed = len(raw_assignments)
        prefix_assignments_persist = False
        prefix = None
        pushed_temp_scope = False
        resolved = None

        try:
            # Phase 2: Expand the remaining arguments. POSIX expands the
            # command's own words BEFORE the temporary assignments take
            # effect, so `V=v echo $V` prints V's *prior* value.
            # command_start_index needs to account for tokens consumed by assignments
            command_start_index = tokens_consumed
            if command_start_index >= len(node.words):
                # No command to execute, but apply any redirections
                # (e.g., ">file" should create/truncate the file). A setup
                # failure (`> ""`, `> adir`) prints the one diagnostic shape
                # and fails with 1, like bash.
                if node.redirects:
                    with self.io_manager.guarded_redirections(
                            node.redirects) as ok:
                        if not ok:
                            return 1
                return 0

            # Create a sub-node for the command's own words only
            # (assignment prefixes sliced off). The string view
            # (.args) derives from words automatically.
            command_node = SimpleCommand(
                redirects=node.redirects,
                background=node.background,
                words=node.words[command_start_index:],
            )

            # A leading backslash on the command word (`\ls`, `\echo`) is a
            # QUOTE. It suppresses ALIAS expansion — handled upstream: the
            # backslash stays in the lexer token, so `\ls` never matched the
            # alias name `ls` during the token-stream transform — and, after
            # quote removal, also makes bash treat the word as NOT a
            # declaration builtin (so `\export foo=$x` word-splits the value).
            # It does NOT suppress function or builtin lookup (F2): once the
            # backslash is stripped the plain name participates in normal
            # function -> builtin -> external resolution.
            command_node, backslash_quoted = \
                self._strip_backslash_bypass(command_node)

            # Expand command arguments (before assignments apply). A
            # backslash-quoted command word is not declaration-eligible.
            expanded_args = self._expand_arguments(
                command_node, declaration_eligible=not backslash_quoted)

            if not expanded_args:
                # The command words produced ZERO fields — an unquoted
                # empty/unset expansion vanished entirely (`$empty`). There
                # is no command, so any prefix assignments affect the current
                # shell (bash: after `V=v $EMPTY`, $V is v).
                #
                # A QUOTED empty word (`''`, `""`, `"$empty"`) is different:
                # it produces ONE empty field, i.e. an attempted invocation
                # of a command whose name is the empty string. That must NOT
                # take this pure-assignment path (it would wrongly persist a
                # prefix assignment); it flows through normal resolution
                # below, where command lookup fails with status 127 — bash
                # prints "` `: command not found" and does not persist the
                # prefix (F1).
                if raw_assignments:
                    return self.assignments.apply_pure(node, raw_assignments)
                return 0

            cmd_name = expanded_args[0]
            cmd_args = expanded_args[1:]

            # Normalize the command word (post-quote-removal spelling + bypass
            # provenance) — a typed value that CANNOT consume a resolution, so
            # it is produced first (campaign R3 / #20 H10).
            normalized = normalize_command_word(
                cmd_name, backslash_bypass=backslash_quoted)

            # bash: $_ holds the last argument of the previous command.
            # Set it after this command's own expansion (which still saw
            # the old value) so the NEXT command reads this one's last arg.
            try:
                self.state.set_variable('_', expanded_args[-1])
            except ReadonlyVariableError:
                pass

            # Build the immutable command-environment overlay (the prefix
            # metadata resolution needs) and RESOLVE ONCE, before any scope
            # or dispatch decision. This is the H10 authority-timing fix: the
            # scope model (function temp-env scope vs command temp-env layer),
            # the ``exec`` shortcut, prefix-assignment persistence, and the
            # POSIX prefix-error branch are all driven by this one
            # ``ResolvedCommand`` — never recomputed from raw names.
            overlay = self.assignments.build_overlay(raw_assignments)
            resolved = self.resolve_command(normalized, overlay, context)

            # When the command resolves to a shell FUNCTION, temp-env prefix
            # assignments follow bash's temporary-variable-context model: they
            # act as an exported scope layered under the function's own locals,
            # so a plain body assignment is discarded on return while a body
            # ``declare -g``/``export`` reaches the global and survives. We push
            # that scope HERE (before value expansion, so `A=1 B=$A f` sees A in
            # the layer) and pop it in the finally; a mid-expansion error still
            # unwinds cleanly because the push precedes apply_prefix. A POSIX
            # special builtin shadowed by a same-named function resolves to the
            # BUILTIN (not the function), so it correctly takes the persist path
            # instead of the discarded-scope path (H10).
            if (resolved is not None and resolved.uses_temp_env_scope
                    and raw_assignments):
                self.state.scope_manager.push_temp_env_scope()
                pushed_temp_scope = True

            # Apply assignments for this command, now that its words are
            # expanded. Each value sees the assignments to its left.
            prefix = self.assignments.apply_prefix(
                raw_assignments, temp_scope=pushed_temp_scope)

            if prefix.failed and self.state.options.get('errexit'):
                # bash: under set -e a prefix-assignment error (e.g.
                # readonly) aborts WITHOUT running the command — even
                # in && / if contexts where errexit is normally
                # suppressed (probe-verified, bash 5.2).
                if self.shell.state.is_script_mode:
                    sys.exit(1)
                return 1

            if prefix.failed and self.state.options.get('posix'):
                # POSIX mode (probe tmp/posixexit, bash 5.2): a
                # prefix-assignment error (`readonly r=1; r=2 cmd`) does
                # NOT run the command. When the command is a POSIX special
                # builtin, a non-interactive shell exits entirely (rc 1;
                # bash's -c mode reports 127 there — the same ledgered -c
                # artifact as the bare-assignment case). Otherwise it is
                # the same DISCARD as a pure readonly assignment: the
                # enclosing statement on this input line dies (an `if
                # r=2 cmd; then` runs neither branch), contained at
                # eval/source boundaries, next line runs with $? = 1.
                # Default (bash) mode instead reports the error and RUNS
                # the command (the path below).
                if (resolved is not None and resolved.is_posix_special
                        and self.state.is_script_mode):
                    sys.exit(1)
                raise TopLevelAbort(1)


            # Handle xtrace option
            if self.state.options.get('xtrace'):
                self._print_xtrace(cmd_name, cmd_args)

            # Special handling for exec builtin (needs access to
            # redirections). A user-defined exec() function shadows the
            # builtin in default mode (bash), so the special case applies only
            # when resolution picked the ``exec`` special builtin — including
            # for `\exec` (F2: the backslash does not bypass the function) and
            # for POSIX mode (where the special builtin shadows the function).
            # Driven by the one resolution, never a fresh raw-name read (H10).
            if resolved is not None and resolved.is_exec_special:
                return self._handle_exec_builtin(node, expanded_args, prefix.applied)

            # Deliver structured array initializers to declaration
            # builtins (declare/typeset/local/export/readonly). The parser
            # attaches an ArrayInitialization (element Words with full quote
            # context) to each ``name=(...)`` argument Word; we hand them to
            # the builtin keyed by their flat-string view (exactly the argv
            # element the builtin sees, since declaration-builtin values are
            # never word-split). The builtin expands them through the SAME
            # structured path the bare ``a=(...)`` form uses — no shlex
            # reparse. Delivery is an explicit ``BuiltinContext`` PARAMETER
            # threaded to the builtin (see strategies.execute_builtin_guarded),
            # not mutable state on the shell object.
            pending_inits = self._collect_array_inits(command_node)
            invocation = (BuiltinContext(array_inits=pending_inits)
                          if pending_inits else EMPTY_BUILTIN_CONTEXT)
            # Dispatch the ALREADY-resolved command (no second resolution).
            result = self._dispatch_resolved(
                resolved, cmd_name, cmd_args, node, context, invocation,
            )
            prefix_assignments_persist = result.prefix_assignments_persist
            return result.status

        finally:
            # In POSIX mode, prefix assignments before a special builtin
            # persist (only then is prefix_assignments_persist True);
            # otherwise they are restored.
            if pushed_temp_scope:
                # Function temp-env layer: pop it (its variables are discarded,
                # revealing any global write the body made). Special builtins
                # never take the function path, so persistence doesn't apply.
                self.state.scope_manager.pop_scope()
            elif prefix is not None:
                if prefix_assignments_persist:
                    # POSIX special builtin: the temporary bindings are promoted
                    # to real exported vars (they persist); the seed-path overlay
                    # is dropped so later env reads see the persisted variables.
                    self.assignments.commit(prefix)
                else:
                    self.assignments.restore(prefix)

    def _strip_backslash_bypass(self, command_node: 'SimpleCommand'):
        """Strip a leading backslash on the command word (`\\ls`, `\\echo`).

        A leading backslash is a QUOTE on the command word. Its two observable
        effects (bash):

        - It suppresses ALIAS expansion — but that is already handled upstream:
          the backslash is preserved in the lexer token, so `\\ls` never
          matched the alias name `ls` during the token-stream alias transform.
        - After quote removal the word is not recognized as a declaration
          builtin, so `\\export foo=$x` word-splits its argument.

        It does NOT suppress function or builtin lookup (F2). This method
        therefore only strips the backslash from the first Word's LiteralPart
        (so expansion and the derived ``.args`` view see the plain name) and
        reports whether a backslash was present.

        Returns:
            (command_node, backslash_quoted). The node is a rewritten copy
            when a backslash was stripped, otherwise unchanged; the flag drives
            declaration-builtin eligibility only.
        """
        if not (command_node.args and command_node.args[0].startswith('\\')):
            return command_node, False


        # Strip the backslash from the first Word's LiteralPart. The
        # leading '\\' of args[0] can only come from a LiteralPart (an
        # ExpansionPart renders as '$...', '`...`' or '<(...)'), so this
        # rewrite is exactly the args[0][1:] strip in Word form.
        modified_words = command_node.words
        if command_node.words and command_node.words[0].parts:
            first_part = command_node.words[0].parts[0]
            if isinstance(first_part, LiteralPart) and first_part.text.startswith('\\'):
                new_part = LiteralPart(
                    first_part.text[1:], first_part.quoted, first_part.quote_char
                )
                # quote_type is derived from the parts; the rebuilt part list
                # carries the same per-part quote context as the original
                # (only the leading backslash of the literal text changed).
                new_word = Word(
                    parts=[new_part] + list(command_node.words[0].parts[1:]),
                )
                modified_words = [new_word] + list(command_node.words[1:])
        command_node = SimpleCommand(
            redirects=command_node.redirects,
            background=command_node.background,
            words=modified_words,
        )
        return command_node, True

    def _handle_execution_error(self, e: Exception) -> int:
        """Map an exception raised during command execution to an exit status.

        Policy (matching bash where noted):
        - Control-flow exceptions (return/break/continue) and SystemExit
          are re-raised for their handlers.
        - ReadonlyVariableError from other paths (array element
          assignments, etc.): status 1, script continues. (Command-prefix
          assignments no longer raise — CommandAssignments.apply_prefix
          reports and skips them so the command still runs, like bash.)
        - Circular nameref in a command prefix: warn, status 1.
        - set -u violation: print once, then the shell-exit family of the
          fatal expansion-error model (report_unbound_variable).
        - ExpansionError: message already printed at the raise site; apply
          bash's fatal expansion-error model (fatal_expansion_status):
          ${x:?}/bad substitution exit a non-interactive shell, everything
          else discards the rest of the current line via TopLevelAbort.
        - Anything else is likely an internal defect: keep the shell
          alive, print a generic message (traceback under --debug-exec).
        """

        # Re-raise control flow exceptions
        if isinstance(e, (FunctionReturn, LoopBreak, LoopContinue, SystemExit)):
            raise

        if isinstance(e, RecursionError):
            # Stack exhaustion (runaway recursion). Let it climb: the nearest
            # enclosing function-call boundary converts it to bash's
            # "maximum function nesting level exceeded" abort
            # (FunctionOperationExecutor.execute_function_call); with no
            # function on the stack it reaches the top-level source guard,
            # where the expected-error taxonomy reports it cleanly.
            raise

        # Handle other exceptions
        if isinstance(e, ReadonlyVariableError):
            # Readonly assignment outside the command-prefix path (e.g.
            # array element assignment): status 1, script continues.
            print(f"{self.state.error_location_prefix()}{e.name}: readonly variable", file=self.state.stderr)
            return 1

        if isinstance(e, NamerefCycleError):
            # Circular nameref in a command-prefix assignment: warn and
            # fail the command without aborting the script.
            self.state.scope_manager.warn_nameref_cycle(e.name)
            return 1

        if isinstance(e, UnboundVariableError):
            # set -u violation: print once and, like bash, abort a
            # non-interactive shell (shared with the arithmetic-command paths).
            return report_unbound_variable(self.state, e)

        if isinstance(e, ExpansionError):
            # Message already printed by the expansion code; apply the
            # bash fatal-model (discard-line, or shell-exit for :?/badsub).
            return fatal_expansion_status(self.state, e)

        # Last-resort guard: anything else is likely an internal defect.
        # Keep the shell alive (or re-raise under strict-errors) — see
        # report_internal_defect for the policy.
        return report_internal_defect(self.state, e, stream=self.state.stderr)

    def _expand_arguments(self, node: 'SimpleCommand', *,
                          declaration_eligible: bool = True) -> List[str]:
        """Expand all arguments in a command.

        declaration_eligible=False disables declaration-builtin
        recognition (used for the ``\\cmd`` bypass: bash word-splits
        ``\\export foo=$x`` because the quoted command word is not
        recognized as a declaration builtin).
        """
        return self.expansion_manager.expand_arguments(
            node, declaration_eligible=declaration_eligible)

    def _print_xtrace(self, cmd_name: str, args: List[str]):
        """Print command trace if xtrace is enabled.

        Delegates to OptionHandler.print_xtrace so the PS4/format/flush policy
        lives in one place in core rather than being reimplemented here.
        """
        OptionHandler.print_xtrace(self.shell, [cmd_name] + args)

    def resolve_command(self, normalized: NormalizedCommandName,
                        overlay: CommandEnvOverlay,
                        context: 'ExecutionContext'
                        ) -> Optional[ResolvedCommand]:
        """Resolve a normalized command word to its :class:`ResolvedCommand`.

        The ONE mode-aware dispatch resolution: delegates to the
        :func:`command_resolution.resolve_command` chokepoint, which reads the
        function/builtin registries once and returns every dispatch decision as
        typed fields. Called BEFORE any scope or prefix-assignment decision, so
        the scope model, ``exec`` shortcut, POSIX prefix-error branch, and
        persistence all flow from this one value instead of raw-name recomputes
        (#20 H10). The overlay carries the resolution-relevant prefix facts —
        in particular ``has_posix_override``, so a ``POSIXLY_CORRECT=1`` prefix
        resolves ITS OWN command in posix mode (bash installs assignments before
        lookup; resolving first must consult the fact instead). The external
        strategy's deferred PATH search reads the live environment, which
        ``apply_prefix`` updates with any temporary PATH before dispatch.
        """
        return resolve_command(
            self.shell, self.strategies, normalized, overlay, context)

    def _dispatch_resolved(self, resolved: Optional[ResolvedCommand],
                           cmd_name: str, args: List[str],
                           node: 'SimpleCommand', context: 'ExecutionContext',
                           invocation: BuiltinContext = EMPTY_BUILTIN_CONTEXT
                           ) -> ExecutionResult:
        """Invoke an already-resolved command (no second resolution).

        Shifts bash's last/this_shell_builtin register, then applies the
        resolved strategy's redirections in the one mode decided by
        :meth:`_decide_redirection_mode` and runs it → an
        :class:`ExecutionResult` carrying the exit status and the
        ``assignments_persist`` policy.
        """
        if resolved is None:
            # Should never happen: ExternalExecutionStrategy.can_execute
            # always matches. Preserves the historical 127 fallback.
            return ExecutionResult(status=127, prefix_assignments_persist=False)
        # Shift bash's last/this_shell_builtin register BEFORE dispatch,
        # so a builtin running now (e.g. `exit`) sees the PREVIOUS
        # command in the `last` slot — the stopped-jobs exit guard
        # exempts an exit directly preceded by `jobs`
        # (JobManager.confirm_exit_with_stopped_jobs). Functions and
        # externals shift a None in (they clear the exemption, like
        # bash); pure assignments never reach here (no shift).
        self.shell.job_manager.note_simple_command(
            cmd_name if resolved.dispatch_kind in _BUILTIN_DISPATCH_KINDS
            else None)
        return self._invoke_resolution(
            resolved, cmd_name, args, node, context, invocation)

    def _invoke_resolution(self, resolved: ResolvedCommand,
                           cmd_name: str, args: List[str],
                           node: 'SimpleCommand',
                           context: 'ExecutionContext',
                           invocation: BuiltinContext = EMPTY_BUILTIN_CONTEXT
                           ) -> ExecutionResult:
        """Run a resolved command, applying its redirections by mode.

        Applies the resolved strategy's redirections according to the one
        mode decided by :meth:`_decide_redirection_mode`, then executes it.
        The resolution's ``assignments_persist`` policy is carried
        through unchanged to the returned :class:`ExecutionResult`.
        """
        strategy = resolved.strategy
        persist = resolved.assignments_persist
        mode = self._decide_redirection_mode(strategy, context, node.background)

        if mode is RedirectionMode.BUILTIN_INPROCESS:
            status = self._execute_builtin_with_redirections(
                cmd_name, args, node, context, strategy, invocation
            )
            return ExecutionResult(status=status,
                                   prefix_assignments_persist=persist)

        if mode is RedirectionMode.CHILD_DEFERRED:
            # The forked child (external, or a backgrounded builtin/function)
            # applies its own redirections (setup_child_redirections); see the
            # mode docstring for why we must NOT apply them here too — doing so
            # would run the redirect targets' substitutions twice (F3).
            status = strategy.execute(
                cmd_name, args, self.shell, context,
                node.redirects, node.background,
                visitor=self.visitor, invocation=invocation,
            )
            return ExecutionResult(status=status,
                                   prefix_assignments_persist=persist)

        # RedirectionMode.FD_LEVEL_WINDOW: functions, aliases,
        # builtins in pipelines, and builtins in forked children.
        # guarded_redirections is the redirect-error chokepoint: a setup
        # failure (`f > adir`, `echo x > /bad/y | cat`) prints bash's one
        # `psh: TARGET: STRERROR` message shape and fails with status 1,
        # instead of leaking the raw Python OSError repr — the same policy
        # as the builtin, external, and compound dispatch sites.
        with self.io_manager.guarded_redirections(node.redirects) as ok:
            if not ok:
                return ExecutionResult(status=1,
                                       prefix_assignments_persist=persist)
            status = strategy.execute(
                cmd_name, args, self.shell, context,
                node.redirects, node.background,
                visitor=self.visitor, invocation=invocation,
            )
            return ExecutionResult(status=status,
                                   prefix_assignments_persist=persist)

    def _decide_redirection_mode(
        self, strategy: 'ExecutionStrategy', context: 'ExecutionContext',
        background: bool = False,
    ) -> RedirectionMode:
        """Select how a matched strategy's redirections are applied.

        This is the single place that encodes the redirection-mode policy;
        ``_invoke_resolution`` performs the single dispatch on the
        result. See ``RedirectionMode`` for what each value means.
        """
        is_builtin = isinstance(
            strategy,
            (SpecialBuiltinExecutionStrategy, BuiltinExecutionStrategy),
        )
        if background and (
                is_builtin or isinstance(strategy, FunctionExecutionStrategy)):
            # A BACKGROUNDED builtin or function runs in a forked child that
            # installs its own redirections. The parent must not install them
            # too, or the redirect targets' command/process substitutions run
            # twice (F3). (External commands already defer below; the
            # background decision has to come first so a backgrounded builtin
            # does not take the in-process save/restore path.)
            return RedirectionMode.CHILD_DEFERRED

        if is_builtin and not context.in_pipeline and not self.state.in_forked_child:
            # A foreground builtin running in this process (not a pipeline, not
            # a forked child): redirect at the Python-stream level and
            # save/restore around the one command.
            return RedirectionMode.BUILTIN_INPROCESS

        if isinstance(strategy, ExternalExecutionStrategy):
            # External commands redirect inside their own forked child.
            return RedirectionMode.CHILD_DEFERRED

        # Functions, aliases, and foreground builtins that run in a pipeline or
        # forked child: apply fd-level redirections in a save/restore window.
        return RedirectionMode.FD_LEVEL_WINDOW

    def _execute_builtin_with_redirections(self, cmd_name: str, args: List[str],
                                          node: 'SimpleCommand', context: 'ExecutionContext',
                                          strategy: ExecutionStrategy,
                                          invocation: BuiltinContext = EMPTY_BUILTIN_CONTEXT
                                          ) -> int:
        """Execute builtin with special redirection handling."""
        # DEBUG: Log builtin redirection setup
        if self.state.options.get('debug-exec'):
            print(f"DEBUG CommandExecutor: Setting up builtin redirections for '{cmd_name}'",
                  file=sys.stderr)
            print(f"DEBUG CommandExecutor: Redirections: {[r.type for r in node.redirects]}",
                  file=sys.stderr)

        # Builtins need special redirection handling. The shell's stream
        # properties live-track sys.* unless a custom stream is installed
        # (capture buffer, subshell pipe); during the builtin we point them
        # at the (possibly redirected) live streams, then restore the
        # custom-override STATE exactly — no type-sniffing.
        saved_streams = self.state.streams.snapshot()
        # The frame records everything this invocation's redirections
        # changed; setup/restore nest (eval/source/trap handlers run
        # further redirected builtins), so the pairing must be by frame,
        # innermost-first — guaranteed here by the try/finally.
        try:
            redirect_frame = self.io_manager.setup_builtin_redirections(node)
        except OSError as e:
            # A real syscall failure opening/duping the redirect target
            # (ENOENT/EISDIR/EACCES). Emit bash's `psh: TARGET: STRERROR` shape
            # instead of letting the raw OSError repr reach the generic handler.
            # OSErrors raised with a custom message and no errno (noclobber,
            # ambiguous redirect, bad fd) are NOT syscall errors — re-raise so
            # their existing `psh: <message>` formatting is preserved.
            if e.errno is None:
                raise
            print(format_redirect_error(
                e, location=self.state.error_location_prefix()),
                file=self.state.stderr)
            return 1
        try:
            # Update shell streams for builtins that might use them
            self.shell.stdout = sys.stdout
            self.shell.stderr = sys.stderr
            self.shell.stdin = sys.stdin

            # Execute builtin
            return strategy.execute(
                cmd_name, args, self.shell, context,
                node.redirects, node.background,
                visitor=self.visitor, invocation=invocation,
            )
        finally:
            self.io_manager.restore_builtin_redirections(redirect_frame)
            self.state.streams.restore(saved_streams)

    def _collect_array_inits(self, command_node: 'SimpleCommand'):
        """Map each declaration-builtin ``name=(...)`` arg to its structured init.

        Returns a dict keyed by the argument's flat-string view (the argv
        element the builtin receives) → ArrayInitialization, or None when the
        command is not a declaration builtin or has no array-init argument.

        Only declaration builtins (declare/typeset/local/export/readonly)
        consume the structured init; for an ordinary command a ``name=(...)``
        argument is just a literal string (bash does not array-ify it), so we
        return None and the builtin/command never sees a pending init.
        """
        if not self.expansion_manager.is_declaration_builtin_command(command_node):
            return None
        inits = {}
        for word in command_node.words:
            if word.array_init is not None:
                # Key by the argv element the builtin actually receives (the
                # runtime unquoted-escape collapse of the flat text), not the
                # verbatim display text — see array_init_argv_key for the
                # residual-backslash double-role analysis (task #38).
                inits[array_init_argv_key(word.display_text())] = word.array_init
        return inits or None

    def _handle_array_assignment(self, assignment):
        """Handle array initialization or element assignment."""

        # Create array executor for this operation
        array_executor = ArrayOperationExecutor(self.shell)

        if isinstance(assignment, ArrayInitialization):
            return array_executor.execute_array_initialization(assignment)
        elif isinstance(assignment, ArrayElementAssignment):
            return array_executor.execute_array_element_assignment(assignment)
        else:
            return 0

    def _report_exec_redirect_error(self, e: OSError) -> None:
        """Print an exec permanent-redirection failure in bash's shape.

        errno-less OSErrors carry psh's own complete message
        (noclobber/ambiguous/bad-fd) — print it verbatim rather than
        "exec: None" (mirrors setup_child_redirections). Otherwise use bash's
        "<$0>: line N: FILE: STRERROR". The location prefix is the single
        source of truth every runtime diagnostic uses (R1).
        """
        loc = self.state.error_location_prefix()
        if e.errno is None:
            print(f"{loc}{e}", file=self.state.stderr)
        else:
            print(f"{loc}{e.filename or 'exec'}: {e.strerror}",
                  file=self.state.stderr)

    def _handle_exec_builtin(self, node: 'SimpleCommand', command_args: List[str],
                            assignments: List[tuple]) -> int:
        """Handle exec builtin with access to redirections."""
        # Get the exec builtin for command execution
        exec_builtin = self.builtin_registry.get('exec')
        if not exec_builtin:
            print("psh: exec: builtin not found", file=self.state.stderr)
            return 127

        # Remove 'exec' from command args
        args = command_args[1:] if command_args and command_args[0] == 'exec' else command_args

        if not args:
            # exec without command - apply redirections permanently
            # and make variable assignments permanent
            if assignments:
                # Make assignments permanent in shell state; the variable
                # observer re-materializes the live environment (no direct env
                # poke — one env interface, appraisal H3). os.environ is
                # read-once at startup and never written; children get
                # state.env explicitly.
                for var, value in assignments:
                    self.state.set_variable(var, value)

            if node.redirects:
                try:
                    self.io_manager.apply_permanent_redirections(node.redirects)
                    return 0
                except OSError as e:
                    self._report_exec_redirect_error(e)
                    return 1
            else:
                # No redirections, just succeed
                return 0
        else:
            # exec with command - apply redirections PERMANENTLY first. exec
            # replaces the process image, so redirected fds carry into the new
            # program (and if the exec fails, they stay in effect — matching
            # bash, where `exec /no/such 2>/dev/null` is silent). Then hand off
            # to the builtin's execute (which performs the execvpe).
            if node.redirects:
                try:
                    self.io_manager.apply_permanent_redirections(node.redirects)
                except OSError as e:
                    self._report_exec_redirect_error(e)
                    return 1
            try:
                return exec_builtin.execute(['exec'] + args, self.shell)
            except SpecialBuiltinUsageError as e:
                # exec bypasses the strategy guard (this direct path exists
                # for redirect handling), so its usage outcome — an invalid
                # option — resolves here: a direct special-builtin
                # invocation, same policy as the guard's special_exit.
                return special_builtin_usage_exit(self.shell, e.status,
                                                  suppressible=e.suppressible)
