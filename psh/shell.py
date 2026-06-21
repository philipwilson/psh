"""The Shell object: psh's top-level orchestrator.

A Shell is a ``ShellState`` (variables, options, streams, execution
state) plus the component managers that operate on it (expansion, I/O,
scripting, interaction, jobs, functions, aliases, traps) and a small
execution facade (``run_command``/``execute_*``). Construction happens
in named lifecycle phases — see ``__init__`` — and child shells for
subshells/substitutions are built with ``Shell.for_subshell``.

This file deliberately contains no execution logic and no CLI-mode
logic: executors live in ``psh/executor/``, the ``--validate/--format/
--metrics/...`` analysis modes in ``psh/scripting/visitor_modes.py``.
"""

import os
import sys
from typing import TYPE_CHECKING, Any, Dict, List, Optional, TextIO

from .ast_nodes import (
    StatementList,
    TopLevel,
)
from .builtins import registry as builtin_registry
from .core import ShellState
from .core.functions import FunctionManager
from .executor.job_control import JobManager
from .expansion import ExpansionManager
from .expansion.aliases import AliasManager
from .interactive import InteractiveManager
from .io_redirect import IOManager
from .scripting.base import ScriptManager

if TYPE_CHECKING:
    from .executor.core import ExecutorVisitor


class Shell:
    def __init__(self, args: Optional[List[str]] = None, script_name: Optional[str] = None,
                 debug_ast: bool = False, debug_tokens: bool = False, debug_scopes: bool = False,
                 debug_expansion: bool = False, debug_expansion_detail: bool = False,
                 debug_exec: bool = False, debug_exec_fork: bool = False,
                 norc: bool = False, rcfile: Optional[str] = None, validate_only: bool = False,
                 format_only: bool = False, metrics_only: bool = False,
                 security_only: bool = False, lint_only: bool = False,
                 parent_shell: Optional['Shell'] = None, ast_format: Optional[str] = None,
                 force_interactive: bool = False) -> None:
        self._create_state(args, script_name, debug_ast, debug_tokens, debug_scopes,
                           debug_expansion, debug_expansion_detail, debug_exec,
                           debug_exec_fork, norc, rcfile)

        # CLI analysis-mode flags (--validate/--format/--metrics/--security/
        # --lint) and AST debug format. Stored verbatim for the callers that
        # branch on them: __main__/scripting.visitor_modes and the source
        # processor's validate-only path.
        self.validate_only = validate_only
        self.format_only = format_only
        self.metrics_only = metrics_only
        self.security_only = security_only
        self.lint_only = lint_only
        self.ast_format = ast_format

        self._init_managers()
        if parent_shell is not None:
            self._inherit_from_parent(parent_shell)
        self._init_shell_components()
        self._select_parser(parent_shell)
        self._init_traps()
        self._init_interactive(force_interactive)

    @classmethod
    def for_subshell(cls, parent: 'Shell', *, norc: bool = True) -> 'Shell':
        """Construct a child shell that inherits *parent*'s execution state.

        This is the construction path for forked or isolated children:
        ``( ... )`` subshells, command substitution, process substitution
        and the env builtin's in-process child. The child inherits the
        environment, all variable scopes (with attributes), functions,
        aliases, positional parameters, shell options, ``$?``, PIPESTATUS,
        ``$PPID`` and ``$$`` — but never jobs (see ``_inherit_from_parent``).
        Children skip rc-file loading by default (``norc=True``).
        """
        return cls(parent_shell=parent, norc=norc)

    # ------------------------------------------------------------------
    # Construction phases (called, in order, from __init__)
    # ------------------------------------------------------------------

    def _create_state(self, args: Optional[List[str]], script_name: Optional[str],
                      debug_ast: bool, debug_tokens: bool, debug_scopes: bool,
                      debug_expansion: bool, debug_expansion_detail: bool,
                      debug_exec: bool, debug_exec_fork: bool,
                      norc: bool, rcfile: Optional[str]) -> None:
        """Phase 1: create the central ShellState.

        Before: nothing exists. After: ``self.state`` holds fresh defaults
        (environment snapshot, options, variable scopes, execution state)
        and its scope manager can reach back to this shell for arithmetic
        evaluation.
        """
        self.state = ShellState(args, script_name, debug_ast,
                                debug_tokens, debug_scopes, debug_expansion,
                                debug_expansion_detail, debug_exec, debug_exec_fork,
                                norc, rcfile)
        self.state.scope_manager.set_shell(self)

    def _init_managers(self) -> None:
        """Phase 2: managers that hold no reference back to the shell.

        Before: only ``self.state`` exists. After: the builtin registry,
        alias, function and job managers exist (the job manager connected
        to state for option checking). These are exactly the managers a
        parent shell may replace in ``_inherit_from_parent``.
        """
        self.builtin_registry = builtin_registry
        self.alias_manager = AliasManager()
        self.function_manager = FunctionManager()
        self.job_manager = JobManager()
        self.job_manager.set_shell_state(self.state)

    def _inherit_from_parent(self, parent: 'Shell') -> None:
        """Phase 3 (child shells only): adopt the parent's state.

        Before: state and the basic managers hold fresh defaults. After:
        ``self.state`` carries the parent's environment, variables, options,
        ``$?``, PIPESTATUS, ``$PPID``/``$$`` (see ``ShellState.adopt``) and
        this shell owns COPIES of the parent's functions and aliases. Jobs
        are not inherited — those are shell-specific. Must run before
        ``_init_shell_components``, whose components capture references to
        the (possibly replaced) function manager.
        """
        self.state.adopt(parent.state)
        self.function_manager = parent.function_manager.copy()
        self.alias_manager = parent.alias_manager.copy()

    def _init_shell_components(self) -> None:
        """Phase 4: components that hold a reference to this shell.

        Before: state and the final (post-inheritance) basic managers
        exist. After: the expansion/I/O/script/interactive managers, the
        single shared ProcessLauncher — the one fork/job-control path for
        pipelines, external commands, background builtins/functions and
        subshells (executors must not build their own) — the history
        expander, and the nested-execution slot ``_current_executor``.
        """
        self.expansion_manager = ExpansionManager(self)
        self.io_manager = IOManager(self)
        self.script_manager = ScriptManager(self)
        self.interactive_manager = InteractiveManager(self)

        from .executor.process_launcher import ProcessLauncher
        self.process_launcher = ProcessLauncher(
            self.state, self.job_manager, self.io_manager,
            self.interactive_manager.signal_manager)

        from .interactive.history_expansion import HistoryExpander
        self.history_expander = HistoryExpander(self)

        # The ExecutorVisitor currently executing, if any. Nested execution
        # (eval, source) reuses it so loop depth and function context carry
        # into the nested commands — `eval break` must break the outer loop.
        self._current_executor: Optional['ExecutorVisitor'] = None

        # One-shot set -e suppression seed: SubshellExecutor sets this on a
        # freshly forked subshell Shell so that _execute_with_visitor seeds the
        # subshell's first ExecutorVisitor context (the errexit exemption must
        # cross the fork, as in bash). 0 = not suppressed.
        self._errexit_suppress_seed: int = 0

    def _select_parser(self, parent_shell: Optional['Shell']) -> None:
        """Phase 5: choose the active parser implementation.

        After: ``_active_parser`` is 'recursive_descent' (default) or
        'combinator'. A child shell keeps its parent's choice; otherwise
        the PSH_TEST_PARSER environment hook (test matrix) wins.
        """
        self._active_parser = 'recursive_descent'
        if parent_shell is not None:
            self._active_parser = parent_shell._active_parser
        elif os.environ.get('PSH_TEST_PARSER'):
            self._active_parser = os.environ['PSH_TEST_PARSER']

    def _init_traps(self) -> None:
        """Phase 6: trap manager (trap builtin storage, EXIT/signal dispatch).

        Before: state exists (the manager stores handlers in
        ``state.trap_handlers``). After: ``self.trap_manager`` is ready.
        """
        from .core import TrapManager
        self.trap_manager = TrapManager(self)

    def _init_interactive(self, force_interactive: bool) -> None:
        """Phase 7: interactive-mode determination, history and rc loading.

        Before: every component exists; the mode flag options hold defaults
        or a parent's copies. After: the 'interactive', 'stdin_mode' and
        'emacs' options reflect THIS process (recomputed even for child
        shells), history is loaded for interactive shells, and the rc file
        has run (interactive, non-script shells without --norc only).
        """
        is_interactive = force_interactive or sys.stdin.isatty()
        self.state.options['interactive'] = is_interactive

        # stdin_mode: True when reading from stdin (no script file argument)
        # Will be set to False by __main__.py when a script file is given
        self.state.options['stdin_mode'] = not self.state.is_script_mode

        # Load history only for interactive shells (bash doesn't load
        # history in non-interactive mode)
        if is_interactive:
            self.interactive_manager.load_history()

        # Set emacs mode based on interactive status (bash behavior)
        # Interactive: emacs on (for line editing), Non-interactive: emacs off
        self.state.options['emacs'] = is_interactive and not self.state.is_script_mode

        # History expansion ('H' in $-) is interactive-only in bash. A
        # non-interactive shell (-c, script, piped stdin) has no '!' history
        # expansion and no 'H' in $-.
        self.state.options['histexpand'] = is_interactive

        if not self.state.is_script_mode and is_interactive and not self.state.norc:
            from .interactive import load_rc_file
            load_rc_file(self)

    # ------------------------------------------------------------------
    # State delegation: the four stream/environment accessors that the
    # rest of the tree (and the test fixtures) address through the shell.
    # All other state lives behind the explicit `shell.state` attribute.
    # ------------------------------------------------------------------

    @property
    def env(self) -> Dict[str, str]:
        """The live environment (``state.env``; see ShellState's docstring).

        Assignment writes through to state so `shell.env = {...}` replaces
        the environment every component sees.
        """
        return self.state.env

    @env.setter
    def env(self, value: Dict[str, str]) -> None:
        self.state.env = value

    # shell.stdout/.stderr/.stdin delegate to ShellState properties that
    # track the LIVE sys.* streams unless a caller installs custom ones
    # (capture buffers, subshell pipes). Do not snapshot sys.stdout at
    # construction time — that would freeze init-time objects and miss
    # later replacements. Assignment writes through to state: subshell
    # and io_redirect code relies on `shell.stdout = x` being visible to
    # everything that reads `state.stdout`.

    @property
    def stdout(self) -> TextIO:
        """The shell's current output stream (live unless overridden)."""
        return self.state.stdout

    @stdout.setter
    def stdout(self, value: TextIO) -> None:
        self.state.stdout = value

    @property
    def stderr(self) -> TextIO:
        """The shell's current error stream (live unless overridden)."""
        return self.state.stderr

    @stderr.setter
    def stderr(self, value: TextIO) -> None:
        self.state.stderr = value

    @property
    def stdin(self) -> TextIO:
        """The shell's current input stream (live unless overridden)."""
        return self.state.stdin

    @stdin.setter
    def stdin(self, value: TextIO) -> None:
        self.state.stdin = value

    # ------------------------------------------------------------------
    # Execution facade
    # ------------------------------------------------------------------

    def execute_command_list(self, command_list: StatementList) -> int:
        """Execute a command list"""
        return self._execute_with_visitor(command_list)

    def execute_toplevel(self, toplevel: TopLevel) -> int:
        """Execute a top-level script/input containing functions and commands."""
        return self._execute_with_visitor(toplevel)

    def _execute_with_visitor(self, node: Any) -> int:
        """Execute an AST node, reusing the active executor when nested.

        Nested execution (eval, source, trap actions) must share the caller's
        ExecutorVisitor: a fresh visitor starts with loop_depth=0, which used
        to make `eval break` report "only meaningful in a loop" instead of
        breaking the enclosing loop.
        """
        if self._current_executor is not None:
            return self._current_executor.visit(node)

        from .executor import ExecutorVisitor
        executor = ExecutorVisitor(self)
        # A forked subshell created inside a set -e-suppressed context
        # (condition, non-final && / || member) seeds the suppression into
        # its fresh visitor so the exemption crosses the fork, as in bash.
        executor.context.errexit_suppress = getattr(self, '_errexit_suppress_seed', 0)
        self._current_executor = executor
        try:
            return executor.visit(node)
        finally:
            self._current_executor = None

    @property
    def active_parser(self) -> str:
        """Name of the active parser implementation.

        Either 'recursive_descent' (default) or 'combinator'. Public accessor so
        callers do not reach into the private `_active_parser` field.
        """
        return self._active_parser

    @active_parser.setter
    def active_parser(self, name: str) -> None:
        self._active_parser = name

    def add_history(self, command: str) -> None:
        """Record a command in the interactive history.

        Public entry point so callers do not walk
        interactive_manager.history_manager.add_to_history directly.
        Honors `set +o history` (the `history` shell option), which
        disables command-history recording (bash).
        """
        if not self.state.options.get('history', True):
            return
        self.interactive_manager.history_manager.add_to_history(command)

    def run_command(self, command_string: str, add_to_history: bool = True,
                    base_line: int = 1) -> int:
        """Execute a command string using the unified input system.

        ``base_line`` is the absolute source line the command text begins at,
        for ``$LINENO``. It defaults to 1 (a fresh context). Nested executions
        that bash anchors at the invoking command's line — ``eval`` and trap
        actions — pass ``scope_manager.get_current_line_number()`` so $LINENO
        inside reflects that line rather than resetting to 1.
        """
        from .scripting.input_sources import StringInput

        # Use the unified execution system for consistency
        input_source = StringInput(command_string, "<command>")
        return self.script_manager.execute_from_source(
            input_source, add_to_history, base_line=base_line)
