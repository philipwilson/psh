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
from .builtins.environment import apply_set_o_option
from .core import ShellState, TrapManager
from .core.functions import FunctionManager
from .executor.job_control import JobManager
from .expansion import ExpansionManager
from .expansion.aliases import AliasManager
from .interactive import InteractiveManager, load_rc_file
from .invocation import InvocationConfig, SourceKind
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
                 force_interactive: bool = False, command_mode: bool = False,
                 invocation: Optional['InvocationConfig'] = None) -> None:
        # Phase 0: interpreter headroom for the recursive engines. Must be
        # process-wide and early, so every path into this shell (scripts,
        # -c, interactive, in-process embedding) gets the same ceiling.
        _ensure_recursion_headroom()

        # A frozen InvocationConfig (from parse_invocation) is authoritative
        # for every invocation fact; the legacy keyword arguments remain as a
        # compatible construction path for embedders and the test tree
        # (F1 ledger: the config path is the ONLY one __main__ takes).
        if invocation is not None:
            if parent_shell is not None:
                raise ValueError(
                    "invocation= and parent_shell= are mutually exclusive")
            args = list(invocation.positionals)
            if invocation.source_kind is SourceKind.SCRIPT:
                script_name = invocation.script_path
            elif invocation.argv0 != "psh":
                script_name = invocation.argv0  # -c 'cmd' name a b (POSIX $0)
            else:
                script_name = None
            norc = invocation.norc
            rcfile = invocation.rcfile
            ast_format = invocation.ast_format
            force_interactive = invocation.interactive
            command_mode = invocation.source_kind is SourceKind.COMMAND
            validate_only = "validate" in invocation.analysis_modes
            format_only = "format" in invocation.analysis_modes
            metrics_only = "metrics" in invocation.analysis_modes
            security_only = "security" in invocation.analysis_modes
            lint_only = "lint" in invocation.analysis_modes
        self._invocation = invocation

        self._create_state(args, script_name, debug_ast, debug_tokens, debug_scopes,
                           debug_expansion, debug_expansion_detail, debug_exec,
                           debug_exec_fork, norc, rcfile, parent_shell)

        # `-c command` mode ('c' in $-). Set BEFORE _init_interactive so the
        # rc/history/line-editing decision sees it (bash never sources rc for
        # -c without -i). Derived from the invocation config above, or passed
        # by a legacy caller.
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
        if invocation is not None:
            self._apply_invocation(invocation)

        # The one-shot startup step (run_invocation_startup: bare -o
        # listings, history, rc file) has NOT run: construction never reads
        # startup input (campaign F1). Child shells (for_subshell/clone)
        # must never run it at all.
        self._invocation_startup_done = parent_shell is not None

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
        # The computed SHELLOPTS/BASHOPTS values need the shell wired to
        # evaluate; re-derive any EXPORTED env entry now (an inherited raw
        # value is replaced by the live computed one — bash regenerates it).
        self.state.refresh_option_reflection_env()

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

        # The one command-name resolver shared by the executor's external
        # path, `command`, `type`, and `hash` (builtins appraisal finding 5).
        from .executor.command_resolver import CommandResolver
        self.command_resolver = CommandResolver(self)

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
        the PSH_TEST_PARSER environment hook (test matrix) wins. An explicit
        (already-validated) ``--parser`` choice from the invocation config
        overrides both — applied in ``_apply_invocation``, so it is in force
        BEFORE the rc file runs (probe class A2/rc-sees-parser).
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
        self.trap_manager = TrapManager(self)

    def _init_interactive(self, force_interactive: bool) -> None:
        """Phase 7: interactive-family determination (mode flags ONLY).

        Before: every component exists; the mode flag options hold defaults
        or a parent's copies. After: the 'interactive', 'stdin_mode',
        'emacs', 'histexpand' and 'monitor' options reflect THIS process
        (recomputed even for child shells). This phase reads NO startup
        input — history and the rc file belong to the explicit
        ``run_invocation_startup`` step (campaign F1: construction purity),
        which runs only after the full invocation is applied.

        The interactive FAMILY (bash's ``interactive_shell``) is independent
        of the input source (#20 H17): ``-i`` forces it for ``-c`` commands
        and script files too (bash ``-ic`` sources the rc, sets ``i``/``H``
        in ``$-``, and discards a failing line instead of aborting —
        probe-pinned, tmp/boundary-ledgers/F1-probes/). Without ``-i`` it
        holds exactly when commands come interactively from a terminal.
        """
        # A shell may be started with fd 0 already closed (`exec 0<&-; psh …`);
        # CPython then sets sys.stdin to None, so guard before .isatty() — a
        # closed/absent stdin is simply non-interactive (bash: same, exit 0),
        # never an AttributeError crash. Matches the stdin guard idiom used in
        # control_flow.py.
        stdin = sys.stdin
        tty_stdin = stdin is not None and not stdin.closed and stdin.isatty()

        # Reading a script FILE or a -c COMMAND string is non-interactive
        # even when stdin happens to be a terminal — UNLESS -i forces the
        # family (bash: `bash -c 'echo $-'` at a terminal has no `i`;
        # `bash -ic` does).
        noninteractive_source = (self.state.is_script_mode
                                 or self.state.options.get('command_mode', False))
        interactive_family = force_interactive or (
            tty_stdin and not noninteractive_source)
        self.state.options['interactive'] = interactive_family

        # stdin_mode ('s' in $-): commands come from standard input. The
        # invocation config refines this (a forced -s keeps 's' even with -c,
        # bash `-sc` → `hBcs`) in _apply_invocation.
        self.state.options['stdin_mode'] = not noninteractive_source

        # emacs line-editing and '!' history expansion ('H' in $-) default on
        # exactly for the interactive family (bash); an explicit CLI ±H
        # transition overrides this default afterwards (bash `+H -ic`).
        self.state.options['emacs'] = interactive_family
        self.state.options['histexpand'] = interactive_family

        # Job control / monitor mode ('m' in $-) is on by default for a shell
        # bash considers interactive that can also control the terminal: the
        # REPL and `bash -i`/`-ic` turn it on, plain `-c`/scripts leave it off.
        # The option is COSMETIC in psh — real job control keys off
        # supports_job_control, not this flag — so it exists purely to make
        # `$-` and `set -o monitor` report truthfully (bash-probed:
        # tmp/probes-r18t2-interactive/probe_mi1_*).
        self.state.options['monitor'] = (
            interactive_family and self.state.supports_job_control)

    def _apply_invocation(self, config: 'InvocationConfig') -> None:
        """Phase 8 (config path): apply the remaining invocation facts.

        Runs AFTER the interactive-family defaults so an explicit CLI
        transition overrides a derived default (bash: `+H -ic` removes the
        family's H; probe E5b), and BEFORE any startup input can run.
        After: every fact of the frozen config is installed — ordered option
        transitions (through the one set-o toggle engine, so vi/emacs/
        ignoreeof/posix couplings fire), stdin_mode refinement, script-mode
        policy, and the validated parser choice.
        """
        # 's' in $-: a forced -s keeps stdin_mode even with -c (bash `-sc`
        # → `hBcs`; probe E1a).
        self.state.options['stdin_mode'] = (
            config.forced_stdin or config.source_kind is SourceKind.STDIN)

        for name, enable in config.option_transitions:
            apply_set_o_option(self, name, enable)

        # bash drops -m when the terminal cannot support job control
        # ("cannot set terminal process group"; probes C5/E17: no `m` in $-).
        if (self.state.options.get('monitor')
                and not self.state.supports_job_control):
            self.state.options['monitor'] = False

        if config.parser is not None:
            self._active_parser = config.parser

        # Non-interactive-family -c/script runs use script-mode error
        # policies; the interactive family keeps the discard-line model even
        # for -c strings and script files (bash -ic / -i script.sh continue
        # after an unbound-variable line — probes P5/Q1). STDIN sources are
        # decided at dispatch (__main__: piped input without -i is script
        # mode; a TTY REPL is not).
        if config.source_kind is not SourceKind.STDIN:
            self.state.is_script_mode = not self.state.options.get(
                'interactive', False)

    def run_invocation_startup(self) -> None:
        """The explicit one-shot startup step (never part of construction).

        In order: bare ``-o``/``+o`` listing requests (bash prints the
        ``set -o`` table and continues; probe E3b), then — for the
        interactive FAMILY only — history loading (line-stream sources:
        bash `-i -s` AND `-i script.sh` list/resolve the HISTFILE entries,
        `-ic` does not; probes H1/H2 + bounce B2/B4) and the rc file (any
        source kind: `-ic` and `-i script.sh` source it, #20 H17).
        Idempotent, so the REPL entry (which also calls it for embedders)
        cannot double-run the rc; child shells (``for_subshell``) are
        constructed with the step already marked done and never repeat
        startup.
        """
        if self._invocation_startup_done:
            return
        self._invocation_startup_done = True

        config = self._invocation
        if config is not None and config.option_listings:
            set_builtin = self.builtin_registry.get('set')
            if set_builtin is not None:
                for sign in config.option_listings:
                    set_builtin.execute(['set', sign + 'o'], self)

        if not self.state.options.get('interactive', False):
            return

        # History loads for LINE-STREAM sources (stdin, script file) of an
        # interactive-family shell — never for a -c command string (bash:
        # `-ic 'history'` lists nothing while `-i -s`/`-i script.sh` list
        # the HISTFILE canaries and resolve `!!` against them).
        if config is None:
            loads_history = not self.state.options.get('command_mode', False)
        else:
            loads_history = config.source_kind is not SourceKind.COMMAND
        if loads_history:
            self.interactive_manager.load_history()

        if not self.state.norc:
            load_rc_file(self)

    # ------------------------------------------------------------------
    # Resource lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Release the resources this Shell owns (idempotent).

        That is the SignalManager's SIGCHLD/SIGWINCH self-pipes, plus any
        process-global signal disposition a trap leased (restored so an
        in-process shell does not leak its handler into the host).
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

        # Restore any process-global signal dispositions this shell leased when
        # a trap installed a handler for an unmanaged signal (H2). An
        # in-process shell must leave the host's dispositions as it found them;
        # a long-lived main shell never calls close() (its fds die with the
        # process). Idempotent — the lease map is drained on restore.
        trap_manager = getattr(self, 'trap_manager', None)
        if trap_manager is not None:
            trap_manager.restore_leased_dispositions()

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
        return self.alias_manager.expand_aliases(
            tokens, shell_options=self.state.options)

    def run_command(self, command_string: str, add_to_history: bool = True,
                    base_line: int = 1, line_oriented: bool = False,
                    posix_syntax_exit: bool = True) -> int:
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

        ``posix_syntax_exit=False`` exempts THIS string from the POSIX-mode
        fatal-syntax-error policy — only trap actions pass it (bash does not
        exit when the action string itself fails to parse; see
        ``InputSource.posix_syntax_exit``).
        """
        from .scripting.input_sources import StringInput

        # Use the unified execution system for consistency
        input_source = StringInput(command_string, "<command>",
                                   split_lines=line_oriented)
        input_source.posix_syntax_exit = posix_syntax_exit
        return self.script_manager.execute_from_source(
            input_source, add_to_history, base_line=base_line)
