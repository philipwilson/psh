"""
Command execution module for the PSH executor.

This module handles the dispatch of simple commands:
- Command-word expansion
- Builtin, function, and external command execution via strategies
- Redirection handling

The ``NAME=value`` assignment sub-domain (extraction, value expansion,
application, restoration, and the POSIX ordering contract) lives in
`command_assignments.py`; this module decides WHEN each of those steps
runs and whether prefix assignments persist (POSIX special builtins).
"""

import os
import sys
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from ..core import ReadonlyVariableError
from .command_assignments import CommandAssignments
from .strategies import (
    BuiltinExecutionStrategy,
    ExecutionStrategy,
    ExternalExecutionStrategy,
    FunctionExecutionStrategy,
    SpecialBuiltinExecutionStrategy,
)

if TYPE_CHECKING:
    from ..ast_nodes import SimpleCommand
    from ..shell import Shell
    from .command_assignments import RawAssignment
    from .context import ExecutionContext
    from .core import ExecutorVisitor


class RedirectionMode(Enum):
    """How a matched command's redirections are applied.

    Once a command name resolves to an execution strategy, exactly one of
    these modes governs the redirection handling. The choice is decided in
    one place (``_decide_redirection_mode``) and dispatched in one place
    (``_execute_with_strategy``).

    BUILTIN_INPROCESS
        A builtin (or special builtin) running in THIS process, not in a
        pipeline and not in a forked child. Redirections are applied at the
        Python-stream level and saved/restored around the single command
        (``_execute_builtin_with_redirections``), so they do not persist.

    EXTERNAL_DEFERRED
        An external command. Its redirections are NOT applied here — they
        are set up inside the forked child (``setup_child_redirections``).
        Applying them in the parent too would resolve ``2>&1`` against
        already-redirected fds and run heredoc/target command
        substitutions twice.

    FD_LEVEL_WINDOW
        Everything else — functions, aliases, and builtins that run in a
        pipeline or in a forked child. Redirections are applied at the fd
        level via ``io_manager.with_redirections`` (a save/restore window)
        because in a forked child builtins use ``os.write()`` on raw fds,
        so ``os.dup2()`` redirection is required rather than Python-level
        ``sys.stdout`` replacement.
    """

    BUILTIN_INPROCESS = "builtin_inprocess"
    EXTERNAL_DEFERRED = "external_deferred"
    FD_LEVEL_WINDOW = "fd_level_window"


@dataclass
class CommandResolution:
    """The result of *resolving* a command name to a strategy.

    Separates "which strategy handles this command, and what policy does
    that imply" (resolve) from "invoke it" (see :class:`ExecutionResult`).
    The resolution carries the matched strategy plus the one policy bit the
    invoke phase and its caller need:

    prefix_assignments_persist
        True when the command resolved to a POSIX special builtin
        (``:`` ``.`` ``eval`` ``export`` ``readonly`` ``set`` ``unset`` …),
        whose ``NAME=value`` prefix assignments persist in the current
        shell rather than being restored after the command. This replaces
        the previous ``isinstance(strategy, SpecialBuiltinExecutionStrategy)``
        check threaded through a positional boolean.
    """

    strategy: 'ExecutionStrategy'
    prefix_assignments_persist: bool


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
        True when the invoked command was a POSIX special builtin, so the
        caller (:meth:`CommandExecutor._run_command`) must NOT restore the
        prefix assignments — they persist in the current shell.
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
        # Order matters: special builtins > functions > builtins > external
        # (POSIX lookup order). Aliases are NOT a runtime strategy: they are
        # expanded as a token-stream transform at the lex→parse boundary
        # (AliasManager.expand_aliases, wired in scripting/source_processor.py
        # and command_accumulator.py), so by the time the executor runs the
        # command word is already the alias-expanded token.
        self.strategies = [
            SpecialBuiltinExecutionStrategy(),
            FunctionExecutionStrategy(),
            BuiltinExecutionStrategy(),
            ExternalExecutionStrategy()
        ]

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
            # bash runs the DEBUG trap before each simple command
            self.shell.trap_manager.execute_debug_trap()

            # Handle array assignments first. Their exit status matters when
            # there is no command word (a bare `a[i]=v` / `a[i]+=v`): bash
            # reports a failed subscript assignment (e.g. out-of-range
            # negative index → "bad array subscript") as exit 1.
            array_assignment_status = 0
            if node.array_assignments:
                for assignment in node.array_assignments:
                    array_assignment_status = self._handle_array_assignment(
                        assignment)

            # Phase 1: Extract raw assignments (before expansion)
            raw_assignments = self.assignments.extract(node)

            # Track command substitutions run while expanding assignment
            # values: a pure assignment's exit status is 0 unless a command
            # substitution ran, in which case it is that substitution's
            # status (bash). The clear must happen HERE — before COMMAND
            # word expansion, not inside apply_pure — because the
            # determining substitution can run while expanding command
            # words that expand to nothing (`V=v $(false)` reports 1).
            self.state.last_cmdsub_status = None

            # Pure assignment (only NAME=value words, no command word)?
            if raw_assignments and len(raw_assignments) == len(node.words):
                return self._run_pure_assignment(node, raw_assignments)

            # Bare array element assignment(s) with no command word
            # (`a[i]=v`): the array assignment status IS the command status.
            # A failed assignment (e.g. out-of-range subscript) aborts a
            # non-interactive `-c`/script invocation with status 1, exactly
            # like a readonly assignment error (CommandAssignments.apply_pure)
            # — but is non-fatal when reading a script from stdin.
            if node.array_assignments and not node.words:
                if node.redirects:
                    with self.io_manager.with_redirections(node.redirects):
                        pass
                if array_assignment_status != 0 and self.state.is_script_mode:
                    sys.exit(array_assignment_status)
                return array_assignment_status

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

    def _run_command(self, node: 'SimpleCommand', context: 'ExecutionContext',
                     raw_assignments: List['RawAssignment']) -> int:
        """Run an actual command invocation (a command word is present).

        Handles, in order: command-word expansion (BEFORE prefix
        assignments take effect, per POSIX), the redirect-only and
        words-vanish edge cases, prefix-assignment application with
        ``set -e`` abort, xtrace, the ``exec`` special case, array-init
        delivery to declaration builtins, strategy dispatch, and prefix
        restoration (skipped for POSIX special builtins so they persist).

        ``raw_assignments`` are the leading ``NAME=value`` prefix words
        already extracted by the coordinator.
        """
        tokens_consumed = len(raw_assignments)
        prefix_assignments_persist = False
        saved_vars = None

        try:
            # Phase 2: Expand the remaining arguments. POSIX expands the
            # command's own words BEFORE the temporary assignments take
            # effect, so `V=v echo $V` prints V's *prior* value.
            # command_start_index needs to account for tokens consumed by assignments
            command_start_index = tokens_consumed
            if command_start_index >= len(node.words):
                # No command to execute, but apply any redirections
                # (e.g., ">file" should create/truncate the file)
                if node.redirects:
                    with self.io_manager.with_redirections(node.redirects):
                        pass
                return 0

            # Create a sub-node for the command's own words only
            # (assignment prefixes sliced off). The string view
            # (.args) derives from words automatically.
            from ..ast_nodes import SimpleCommand
            command_node = SimpleCommand(
                redirects=node.redirects,
                background=node.background,
                words=node.words[command_start_index:],
            )

            # Check for the `\cmd` bypass mechanism before expansion
            command_node, bypass_aliases, bypass_functions = \
                self._strip_backslash_bypass(command_node)

            # Expand command arguments (before assignments apply)
            expanded_args = self._expand_arguments(
                command_node,
                declaration_eligible=not (bypass_aliases or bypass_functions))

            if not expanded_args or not expanded_args[0]:
                # The command words expanded to nothing: the assignments
                # affect the current shell environment (bash: after
                # `V=v $EMPTY`, $V is v).
                if raw_assignments:
                    return self.assignments.apply_pure(node, raw_assignments)
                return 0

            cmd_name = expanded_args[0]
            cmd_args = expanded_args[1:]

            # bash: $_ holds the last argument of the previous command.
            # Set it after this command's own expansion (which still saw
            # the old value) so the NEXT command reads this one's last arg.
            try:
                self.state.set_variable('_', expanded_args[-1])
            except ReadonlyVariableError:
                pass

            # Apply assignments for this command, now that its words are
            # expanded. Each value sees the assignments to its left.
            prefix = self.assignments.apply_prefix(raw_assignments)
            saved_vars = prefix.saved

            if prefix.failed and self.state.options.get('errexit'):
                # bash: under set -e a prefix-assignment error (e.g.
                # readonly) aborts WITHOUT running the command — even
                # in && / if contexts where errexit is normally
                # suppressed (probe-verified, bash 5.2).
                if self.shell.state.is_script_mode:
                    sys.exit(1)
                return 1


            # Handle xtrace option
            if self.state.options.get('xtrace'):
                self._print_xtrace(cmd_name, cmd_args)

            # Special handling for exec builtin (needs access to redirections)
            if cmd_name == 'exec':
                return self._handle_exec_builtin(node, expanded_args, prefix.applied)

            # Deliver structured array initializers to declaration
            # builtins (declare/typeset/local/export/readonly). The
            # parser attaches an ArrayInitialization (element Words with
            # full quote context) to each ``name=(...)`` argument Word;
            # we hand them to the builtin keyed by their flat-string view
            # (which is exactly the argv element the builtin sees, since
            # declaration-builtin values are never word-split). The
            # builtin expands them through the SAME structured path the
            # bare ``a=(...)`` form uses — no shlex reparse. The handoff is
            # an explicit, single-owner API on the shell (set here, peeked
            # by the builtin, cleared in finally) — never a globally mutable
            # attribute; see the array-init seam note below.
            pending_inits = self._collect_array_inits(command_node)
            set_inits = pending_inits is not None
            if set_inits:
                self.shell.set_pending_array_inits(pending_inits)
            try:
                # Execute the command using appropriate strategy
                result = self._execute_with_strategy(
                    cmd_name, cmd_args, node, context,
                    bypass_aliases, bypass_functions
                )
                prefix_assignments_persist = result.prefix_assignments_persist
            finally:
                if set_inits:
                    self.shell.clear_pending_array_inits()
            return result.status

        finally:
            # POSIX: assignments before special builtins persist
            if saved_vars is not None and not prefix_assignments_persist:
                self.assignments.restore(saved_vars)

    def _strip_backslash_bypass(self, command_node: 'SimpleCommand'):
        """Handle the `\\cmd` alias/function bypass.

        A leading backslash on the command word (e.g. ``\\ls``) makes the
        shell skip alias and function lookup. Strip the backslash from
        the first Word's LiteralPart so expansion (and the derived
        ``.args`` view) sees the plain name.

        Returns:
            (command_node, bypass_aliases, bypass_functions). The node is
            a rewritten copy when a bypass was found, otherwise unchanged.
        """
        if not (command_node.args and command_node.args[0].startswith('\\')):
            return command_node, False, False

        from ..ast_nodes import LiteralPart, SimpleCommand, Word

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
        return command_node, True, True

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
        - set -u violation: print once; abort a non-interactive shell
          with 127, otherwise return 127.
        - ExpansionError: message already printed; exit the shell in
          script mode, otherwise return its exit code.
        - Anything else is likely an internal defect: keep the shell
          alive, print a generic message (traceback under --debug-exec).
        """
        # Import these here to avoid circular imports
        from ..core import ExpansionError, LoopBreak, LoopContinue, UnboundVariableError
        from ..core.exceptions import FunctionReturn

        # Re-raise control flow exceptions
        if isinstance(e, (FunctionReturn, LoopBreak, LoopContinue, SystemExit)):
            raise

        # Handle other exceptions
        if isinstance(e, ReadonlyVariableError):
            # Readonly assignment outside the command-prefix path (e.g.
            # array element assignment): status 1, script continues.
            print(f"psh: {e.name}: readonly variable", file=self.state.stderr)
            return 1

        from ..core import NamerefCycleError
        if isinstance(e, NamerefCycleError):
            # Circular nameref in a command-prefix assignment: warn and
            # fail the command without aborting the script.
            self.state.scope_manager.warn_nameref_cycle(e.name)
            return 1

        if isinstance(e, UnboundVariableError):
            # set -u violation: print once and, like bash, abort a
            # non-interactive shell with status 127.
            print(f"psh: {e}", file=self.state.stderr)
            if self.shell.state.is_script_mode:
                sys.exit(127)
            return 127

        if isinstance(e, ExpansionError):
            # Error message already printed by the expansion code
            expansion_exit_code = getattr(e, 'exit_code', 1)
            # In script mode, we should exit the shell
            if self.shell.state.is_script_mode:
                sys.exit(expansion_exit_code)
            return expansion_exit_code

        # Last-resort guard: anything else is likely an internal defect.
        # Keep the shell alive (or re-raise under strict-errors) — see
        # report_internal_defect for the policy.
        from ..core import report_internal_defect
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
        from ..core import OptionHandler
        OptionHandler.print_xtrace(self.state, [cmd_name] + args)

    def _execute_with_strategy(self, cmd_name: str, args: List[str],
                              node: 'SimpleCommand', context: 'ExecutionContext',
                              bypass_aliases: bool = False,
                              bypass_functions: bool = False) -> ExecutionResult:
        """Resolve the command to a strategy, then invoke it.

        Two phases, as typed data:

        1. :meth:`_resolve_command` picks the matching strategy and the
           prefix-assignment-persistence policy it implies → a
           :class:`CommandResolution`.
        2. :meth:`_invoke_resolution` applies the resolved strategy's
           redirections in the one mode decided by
           ``_decide_redirection_mode`` and runs it → an
           :class:`ExecutionResult`.

        Returns:
            An :class:`ExecutionResult` carrying the exit status and the
            ``prefix_assignments_persist`` policy (True for POSIX special
            builtins), which the caller uses to decide whether to restore
            the prefix assignments.
        """
        resolution = self._resolve_command(
            cmd_name, bypass_aliases, bypass_functions)
        if resolution is None:
            # Should never happen: ExternalExecutionStrategy.can_execute
            # always matches. Preserves the historical 127 fallback.
            return ExecutionResult(status=127, prefix_assignments_persist=False)
        return self._invoke_resolution(
            resolution, cmd_name, args, node, context)

    def _resolve_command(self, cmd_name: str,
                         bypass_aliases: bool = False,
                         bypass_functions: bool = False
                         ) -> Optional[CommandResolution]:
        """Resolve a command name to the strategy that will run it.

        Walks the priority-ordered strategy list (special builtins >
        functions > builtins > external; aliases are expanded earlier as a
        token-stream transform, not here), honoring the ``\\cmd``
        bypass exclusions, and returns the first match as a
        :class:`CommandResolution`. The persistence policy — previously the
        ``isinstance(strategy, SpecialBuiltinExecutionStrategy)`` check —
        is recorded here as the ``prefix_assignments_persist`` field.

        Returns None only if no strategy matches (unreachable in practice,
        since ExternalExecutionStrategy is the catch-all).
        """
        # Note: The 'command' builtin handles its own bypass logic internally

        # Create strategy list based on bypass requirements.
        # bypass_aliases is now a no-op at this layer: aliases are expanded
        # at the lex→parse boundary (AliasManager.expand_aliases), so there
        # is no runtime alias strategy to exclude. The `\\cmd` backslash is
        # still stripped earlier (_strip_backslash_bypass) and naturally
        # avoids alias expansion because the leading-backslash WORD never
        # matches an alias name during the token transform.
        strategies_to_exclude: List[type[ExecutionStrategy]] = []
        if bypass_functions:
            strategies_to_exclude.append(FunctionExecutionStrategy)
            # Note: bypass_functions should NOT exclude special builtins

        if strategies_to_exclude:
            strategies_to_use = [
                strategy for strategy in self.strategies
                if not any(isinstance(strategy, exc_type) for exc_type in strategies_to_exclude)
            ]
        else:
            strategies_to_use = self.strategies

        for strategy in strategies_to_use:
            if strategy.can_execute(cmd_name, self.shell):
                return CommandResolution(
                    strategy=strategy,
                    prefix_assignments_persist=isinstance(
                        strategy, SpecialBuiltinExecutionStrategy),
                )
        return None

    def _invoke_resolution(self, resolution: CommandResolution,
                           cmd_name: str, args: List[str],
                           node: 'SimpleCommand',
                           context: 'ExecutionContext') -> ExecutionResult:
        """Run a resolved command, applying its redirections by mode.

        Applies the resolved strategy's redirections according to the one
        mode decided by :meth:`_decide_redirection_mode`, then executes it.
        The resolution's ``prefix_assignments_persist`` policy is carried
        through unchanged to the returned :class:`ExecutionResult`.
        """
        strategy = resolution.strategy
        persist = resolution.prefix_assignments_persist
        mode = self._decide_redirection_mode(strategy, context)

        if mode is RedirectionMode.BUILTIN_INPROCESS:
            status = self._execute_builtin_with_redirections(
                cmd_name, args, node, context, strategy
            )
            return ExecutionResult(status=status,
                                   prefix_assignments_persist=persist)

        if mode is RedirectionMode.EXTERNAL_DEFERRED:
            # External commands apply their redirections in the
            # forked child (setup_child_redirections); see the mode
            # docstring for why we must NOT apply them here too.
            status = strategy.execute(
                cmd_name, args, self.shell, context,
                node.redirects, node.background,
                visitor=self.visitor,
            )
            return ExecutionResult(status=status,
                                   prefix_assignments_persist=persist)

        # RedirectionMode.FD_LEVEL_WINDOW: functions, aliases,
        # builtins in pipelines, and builtins in forked children.
        with self.io_manager.with_redirections(node.redirects):
            status = strategy.execute(
                cmd_name, args, self.shell, context,
                node.redirects, node.background,
                visitor=self.visitor,
            )
            return ExecutionResult(status=status,
                                   prefix_assignments_persist=persist)

    def _decide_redirection_mode(
        self, strategy: 'ExecutionStrategy', context: 'ExecutionContext'
    ) -> RedirectionMode:
        """Select how a matched strategy's redirections are applied.

        This is the single place that encodes the redirection-mode policy;
        ``_execute_with_strategy`` performs the single dispatch on the
        result. See ``RedirectionMode`` for what each value means.
        """
        is_builtin = isinstance(
            strategy,
            (SpecialBuiltinExecutionStrategy, BuiltinExecutionStrategy),
        )
        if is_builtin and not context.in_pipeline and not self.state.in_forked_child:
            # A builtin running in this process (not a pipeline, not a
            # forked child): redirect at the Python-stream level and
            # save/restore around the one command.
            return RedirectionMode.BUILTIN_INPROCESS

        if isinstance(strategy, ExternalExecutionStrategy):
            # External commands redirect inside their own forked child.
            return RedirectionMode.EXTERNAL_DEFERRED

        # Functions, aliases, and builtins that run in a pipeline or forked
        # child: apply fd-level redirections in a save/restore window.
        return RedirectionMode.FD_LEVEL_WINDOW

    def _execute_builtin_with_redirections(self, cmd_name: str, args: List[str],
                                          node: 'SimpleCommand', context: 'ExecutionContext',
                                          strategy: ExecutionStrategy) -> int:
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
            name = e.filename if e.filename else os.strerror(e.errno)
            print(f"psh: {name}: {os.strerror(e.errno)}", file=self.state.stderr)
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
                visitor=self.visitor,
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
                # The flat literal text is exactly the argv element the
                # builtin sees (declaration values are not word-split).
                inits[word.display_text()] = word.array_init
        return inits or None

    def _handle_array_assignment(self, assignment):
        """Handle array initialization or element assignment."""
        from ..ast_nodes import ArrayElementAssignment, ArrayInitialization
        from .array import ArrayOperationExecutor

        # Create array executor for this operation
        array_executor = ArrayOperationExecutor(self.shell)

        if isinstance(assignment, ArrayInitialization):
            return array_executor.execute_array_initialization(assignment)
        elif isinstance(assignment, ArrayElementAssignment):
            return array_executor.execute_array_element_assignment(assignment)
        else:
            return 0

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
                # Make assignments permanent by exporting them into the
                # live environment (state.env; os.environ is read-once at
                # startup and never written — children get state.env
                # explicitly, so writing os.environ here only leaked).
                for var, value in assignments:
                    self.state.set_variable(var, value)
                    self.shell.env[var] = value

            if node.redirects:
                try:
                    self.io_manager.apply_permanent_redirections(node.redirects)
                    return 0
                except OSError as e:
                    # bash format: "bash: FILE: No such file or directory"
                    print(f"psh: {e.filename or 'exec'}: {e.strerror}",
                          file=self.state.stderr)
                    return 1
            else:
                # No redirections, just succeed
                return 0
        else:
            # exec with command - use the builtin's execute method
            return exec_builtin.execute(['exec'] + args, self.shell)
