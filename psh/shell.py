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
    Program,
    StatementList,
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
    from .lexer.token_types import Token


# Python-frame headroom for psh's recursive engines (parser, expansion,
# executor visitor). One shell function call burns ~18 Python frames and one
# nested compound ~12 (measured empirically, 2026-07-04), so CPython's default
# limit of 1000 capped shell recursion at ~50 calls — bash handles 5000+.
# 40,000 frames gives ~2,200 shell-call / ~3,300 nested-compound depth.
# Safe on the supported interpreters (>= 3.12): Python frames live on the
# heap and C-stack recursion is guarded separately, so a runaway raises
# RecursionError (converted to a clean shell error at the function-call
# boundary / last-resort guards) rather than overflowing the OS stack —
# verified to survive limits up to 60,000 even under `ulimit -s 512`.
RECURSION_LIMIT = 40_000


def _ensure_recursion_headroom() -> None:
    """Raise the interpreter recursion limit to RECURSION_LIMIT.

    Only ever raises, never lowers — an embedding process (e.g. the test
    runner) that already set a higher limit keeps it. Process-wide by
    nature; idempotent, so per-Shell invocation (including forked
    subshell children) is harmless.
    """
    if sys.getrecursionlimit() < RECURSION_LIMIT:
        sys.setrecursionlimit(RECURSION_LIMIT)


class Shell:
    # Explicit attribute type: ``_create_state`` assigns ``self.state`` from a
    # clone of ``parent_shell.state`` (a child) or a fresh ShellState. That
    # self-referential RHS (``parent_shell.state``) would otherwise force the
    # type checker into a has-type inference cycle when computing Shell.state.
    state: ShellState

    def __init__(self, args: Optional[List[str]] = None, script_name: Optional[str] = None,
                 debug_ast: bool = False, debug_tokens: bool = False, debug_scopes: bool = False,
                 debug_expansion: bool = False, debug_expansion_detail: bool = False,
                 debug_exec: bool = False, debug_exec_fork: bool = False,
                 norc: bool = False, rcfile: Optional[str] = None, validate_only: bool = False,
                 format_only: bool = False, metrics_only: bool = False,
                 security_only: bool = False, lint_only: bool = False,
                 parent_shell: Optional['Shell'] = None, ast_format: Optional[str] = None,
                 force_interactive: bool = False, command_mode: bool = False) -> None:
        # Phase 0: interpreter headroom for the recursive engines. Must be
        # process-wide and early, so every path into this shell (scripts,
        # -c, interactive, in-process embedding) gets the same ceiling.
        _ensure_recursion_headroom()

        self._create_state(args, script_name, debug_ast, debug_tokens, debug_scopes,
                           debug_expansion, debug_expansion_detail, debug_exec,
                           debug_exec_fork, norc, rcfile, parent_shell)

        # `-c command` mode ('c' in $-). Set BEFORE _init_interactive so the
        # rc/history/line-editing decision sees it (bash never sources rc for
        # -c). __main__ determines this from argv before constructing us.
        if command_mode:
            self.state.options['command_mode'] = True

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
                      norc: bool, rcfile: Optional[str],
                      parent_shell: Optional['Shell'] = None) -> None:
        """Phase 1: create the central ShellState.

        Before: nothing exists. After: ``self.state`` holds either fresh
        defaults (top-level shell: environment snapshot, options, variable
        scopes, execution state) or — for a child shell — an EXACT clone of
        the parent's state (``ShellState.clone_for_child``: no fresh
        ``os.environ`` import, no seeded defaults, deep-copied arrays and
        per-instance function metadata). Either way its scope manager can
        reach back to this shell for arithmetic evaluation.

        Assigning ``self.state`` in this one method (rather than also directly
        in ``__init__``) keeps its inferred type unambiguous for the type
        checker.
        """
        if parent_shell is not None:
            self.state = ShellState.clone_for_child(
                parent_shell.state, norc=norc, rcfile=rcfile)
        else:
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
        """Phase 3 (child shells only): adopt the parent's managers.

        ``self.state`` was already cloned from the parent in ``__init__`` (see
        ``ShellState.clone_for_child``, which carries the environment,
        variables, options, ``$?``, PIPESTATUS, ``$PPID``/``$$`` and the rest).
        This phase copies the remaining Shell-level managers: this shell owns
        COPIES of the parent's functions and aliases (so a child's
        ``readonly -f`` / redefinition cannot leak back). Jobs are not
        inherited — those are shell-specific. Must run before
        ``_init_shell_components``, whose components capture references to the
        (possibly replaced) function manager.
        """
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

        # Loop-depth seed, same mechanism: run_child_shell sets this on a
        # substitution child forked inside a loop so `x=$(break)` stays
        # silent (bash) instead of warning "only meaningful in a loop".
        self._loop_depth_seed: int = 0

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
        # A shell may be started with fd 0 already closed (`exec 0<&-; psh …`);
        # CPython then sets sys.stdin to None, so guard before .isatty() — a
        # closed/absent stdin is simply non-interactive (bash: same, exit 0),
        # never an AttributeError crash. Matches the stdin guard idiom used in
        # control_flow.py.
        stdin = sys.stdin
        is_interactive = force_interactive or (
            stdin is not None and not stdin.closed and stdin.isatty())
        self.state.options['interactive'] = is_interactive

        # Running a script FILE or a -c COMMAND string is non-interactive even
        # when stdin happens to be a terminal: bash sources rc, loads history,
        # and enables line editing only for a genuinely interactive shell —
        # never for -c or a script. BOTH mode flags are now known at
        # construction (__main__ passes script_name / command_mode in), so this
        # decision is finally correct. Previously it read is_script_mode BEFORE
        # __main__ had set it, sourcing ~/.pshrc (and loading history) into every
        # `psh -c '...'` and `psh script.sh` invoked from a terminal.
        noninteractive_mode = (self.state.is_script_mode
                               or self.state.options.get('command_mode', False))
        live_interactive = is_interactive and not noninteractive_mode

        # stdin_mode: reading commands interactively from stdin (no -c, no script)
        self.state.options['stdin_mode'] = not noninteractive_mode

        # Load history only for a live interactive shell (bash never loads it
        # for -c / scripts).
        if live_interactive:
            self.interactive_manager.load_history()

        # emacs line-editing and '!' history expansion ('H' in $-) are
        # interactive-only (bash).
        self.state.options['emacs'] = live_interactive
        self.state.options['histexpand'] = live_interactive

        # Job control / monitor mode ('m' in $-) is on by default for a shell
        # bash considers interactive that can also control the terminal: the
        # REPL and `bash -i`/`-ic` turn it on, plain `-c`/scripts leave it off.
        # The option is COSMETIC in psh — real job control keys off
        # supports_job_control, not this flag — so it exists purely to make
        # `$-` and `set -o monitor` report truthfully (bash-probed:
        # tmp/probes-r18t2-interactive/probe_mi1_*).
        self.state.options['monitor'] = (
            (live_interactive or force_interactive)
            and self.state.supports_job_control)

        if live_interactive and not self.state.norc:
            from .interactive import load_rc_file
            load_rc_file(self)

    # ------------------------------------------------------------------
    # Resource lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Release the fd-backed resources this Shell owns (idempotent).

        Currently that is the SignalManager's SIGCHLD/SIGWINCH self-pipes.
        Safe to call more than once and safe on a shell that never allocated
        them (the self-pipes are created lazily, only when interactive signal
        handlers are installed) — and it only frees resources that the shell
        re-creates on demand, so a closed shell that is subsequently used again
        keeps working.

        The long-lived interactive / main shell need not call this: its fds die
        with the process. ``close()`` exists for the MANY transient Shell
        instances — tests, the ``env`` builtin's child, subshell helpers — so
        their self-pipes are freed immediately rather than lingering until
        garbage collection. It never touches the (possibly shared) stdin/
        stdout/stderr streams, which the shell does not own.
        """
        interactive_manager = getattr(self, 'interactive_manager', None)
        if interactive_manager is not None:
            signal_manager = getattr(interactive_manager, 'signal_manager', None)
            if signal_manager is not None:
                signal_manager.close()

    def __enter__(self) -> 'Shell':
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

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

    def execute_program(self, program: Program) -> int:
        """Execute a parsed program (the canonical parser root)."""
        return self._execute_with_visitor(program)

    def execute_command_list(self, command_list: StatementList) -> int:
        """Execute a nested command list (a subshell/brace-group body)."""
        return self._execute_with_visitor(command_list)

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
        executor.context.loop_depth = getattr(self, '_loop_depth_seed', 0)
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

    def expand_aliases(self, tokens: 'List[Token]') -> 'List[Token]':
        """Alias-expand a token stream at the lex->parse boundary.

        The single gate for the ``expand_aliases`` shopt option: ``shopt -u
        expand_aliases`` makes this a pass-through, so aliases stop expanding
        for subsequently-parsed commands (bash). psh keeps the option ON by
        default in every mode, whereas bash defaults it OFF non-interactively —
        a deliberate divergence so the many `-c`/script tests that rely on
        aliases keep working. Because psh expands over the whole logical
        command at once, ``shopt -u`` on the SAME line as the use does not
        disable it (the same parse-time model that lets psh honor a same-line
        ``alias`` definition).
        """
        if not self.state.options.get('expand_aliases', True):
            return tokens
        return self.alias_manager.expand_aliases(tokens)

    def run_command(self, command_string: str, add_to_history: bool = True,
                    base_line: int = 1, line_oriented: bool = False) -> int:
        """Execute a command string using the unified input system.

        ``base_line`` is the absolute source line the command text begins at,
        for ``$LINENO``. It defaults to 1 (a fresh context). Nested executions
        that bash anchors at the invoking command's line — ``eval`` and trap
        actions — pass ``scope_manager.get_current_line_number()`` so $LINENO
        inside reflects that line rather than resetting to 1.

        ``line_oriented`` reads the string PHYSICAL-line-by-line (like a script
        file / ``-c``) instead of as one chunk, so a discard-line error inside
        it (a word-arithmetic failure, an assignment to a readonly variable in
        ``$(( ))``) is contained to the offending line and execution resumes at
        the next line — matching bash's ``eval`` (``eval 'echo a\\necho $((1/0))
        \\necho c'`` prints a and c). ``eval`` passes True.
        """
        from .scripting.input_sources import StringInput

        # Use the unified execution system for consistency
        input_source = StringInput(command_string, "<command>",
                                   split_lines=line_oriented)
        return self.script_manager.execute_from_source(
            input_source, add_to_history, base_line=base_line)
