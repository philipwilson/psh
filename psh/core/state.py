"""Shell state management."""
import os
from typing import Any, Dict, Optional, Set

from ..version import __version__
from .command_hash import CommandHashTable
from .execution_state import ExecutionState
from .history_state import HistoryState
from .option_registry import ShellOptions
from .scope import ScopeManager
from .stream_bindings import StreamBindings
from .terminal_state import TerminalState
from .variables import VarAttributes


class ShellState:
    """Container for shell state that can be shared across components.

    Environment policy: ``os.environ`` is read ONCE here at startup;
    ``state.env`` is the shell's live environment from then on, and it
    is passed EXPLICITLY to every child (``execvpe(args, shell.env)``
    in executor/strategies.py and builtins/core.py, ``env=state.env``
    for shebang re-execution, and ``Shell.for_subshell(...)`` copies).
    Nothing in psh writes ``os.environ`` after startup — a write there
    would be invisible to children and only leak state into the hosting
    Python process (the pre-v0.312 ``FOO=bar exec`` leak).
    """

    # Lazily created by the pushd/popd/dirs builtins (directory_stack.py) on
    # first use via a hasattr() guard, so it has no __init__ assignment.
    # Declared here (pure annotation, no runtime effect) so the dynamic
    # attribute type-checks. Typed Any to avoid a core→builtins layering
    # import for DirectoryStack.
    directory_stack: Any

    def __init__(self, args=None, script_name=None, debug_ast=False,
                 debug_tokens=False, debug_scopes=False, debug_expansion=False, debug_expansion_detail=False,
                 debug_exec=False, debug_exec_fork=False, norc=False, rcfile=None):
        # Standard-stream overrides. The three stdin/stdout/stderr
        # properties below delegate to this one explicit object; each
        # stream tracks the live sys.* object unless a caller installs an
        # override (capture buffer, subshell pipe, exec-rebound file), and
        # snapshot()/restore() own the save/restore of that override state.
        self.streams = StreamBindings()

        # Environment and variables (the ONE read of os.environ — see
        # the class docstring for the environment policy)
        self.env = os.environ.copy()

        # Initialize enhanced scope manager for variable scoping with attributes
        self.scope_manager = ScopeManager()

        # Remembered command locations (the `hash` builtin / bash's
        # COMMAND EXECUTION hashing). Any PATH write empties it — the
        # scope manager fires the observer below for every PATH
        # assignment/local/unset (bash 5.2, probe-verified: even
        # ``PATH=$PATH`` and ``local PATH=...`` clear; ``cd`` does not).
        # The lambda reads self.command_hash at call time so adopt()'s
        # table replacement stays wired.
        self.command_hash = CommandHashTable()
        self.scope_manager.path_changed = lambda: self.command_hash.clear()

        # Default prompt variables (set in global scope)
        self.scope_manager.set_variable('PS1', 'psh$ ')
        self.scope_manager.set_variable('PS2', '> ')

        # Shell version variable for compatibility
        self.scope_manager.set_variable('PSH_VERSION', __version__)

        # Import environment variables into scope manager with EXPORT attribute
        # This ensures they're properly tracked as exported variables
        for name, value in self.env.items():
            self.scope_manager.set_variable(name, value, attributes=VarAttributes.EXPORT, local=False)

        # From here on, every write/unset/attribute-change of a variable
        # re-derives that name's entry in the live environment, so a plain
        # reassignment of an export-attributed variable updates what
        # children see (bash: ``export FOO=old; FOO=new; printenv FOO``
        # prints ``new``). Wired AFTER the import loop above — the loop
        # iterates self.env, which the observer mutates.
        self.scope_manager.variable_changed = self._sync_exported_variable

        # Ensure PWD is set to current working directory if not already in
        # environment (the observer adds the env entry).
        if 'PWD' not in self.env:
            self.scope_manager.set_variable('PWD', os.getcwd(), attributes=VarAttributes.EXPORT, local=False)

        # Positional parameters and script info
        self.positional_params = args if args else []
        self.script_name = script_name or "psh"
        self.is_script_mode = script_name is not None and script_name != "psh"

        # getopts within-argument cursor (the character position inside a
        # clustered option arg, e.g. -abc). Tracked here — like OPTIND — so a
        # cluster spans calls WITHOUT mutating the positional parameters.
        self._getopts_charpos: int = 1
        self._getopts_charpos_optind: Optional[int] = None

        # Centralized shell options dictionary
        # Shell options live in a registry-backed, dict-compatible container
        # (psh/core/option_registry.py is the single source of truth for every
        # option's default, short flag, $- letter, and category). Only the
        # values that differ from the registry defaults at construction —
        # the CLI debug flags and the PSH_STRICT_ERRORS seed — are passed as
        # overrides; everything else takes its registry default.
        self.options = ShellOptions(overrides={
            'debug-ast': debug_ast,
            'debug-tokens': debug_tokens,
            'debug-scopes': debug_scopes,
            'debug-expansion': debug_expansion,
            'debug-expansion-detail': debug_expansion_detail,
            'debug-exec': debug_exec,
            'debug-exec-fork': debug_exec_fork,
            'strict-errors': self._seed_strict_errors(),
        })

        # Enable debug mode on scope manager if debug-scopes is set
        if self.options['debug-scopes']:
            self.scope_manager.enable_debug(True)

        # RC file options
        self.norc = norc
        self.rcfile = rcfile

        # Execution state — one cohesive object (last_exit_code / last_bg_pid /
        # foreground_pgid / command_number / pipestatus / errexit_eligible /
        # last_cmdsub_status / in_forked_child delegate to it via properties).
        self.execution = ExecutionState()

        # History settings — one cohesive object (history / history_file /
        # max_history_size delegate to it via properties).
        self.history_state = HistoryState()

        # Editor configuration
        self.edit_mode = 'emacs'

        # Function call stack
        self.function_stack = []

        # Depth of nested `source`/`.` execution. `return` is legal inside a
        # sourced script (it stops the file), so ReturnBuiltin checks this in
        # addition to function_stack.
        self.source_depth = 0

        # The shell's parent process id at startup ($PPID). Subshells
        # inherit it (bash: PPID does not change in subshells).
        self.initial_ppid = os.getppid()

        # The shell's own pid at startup ($$). Captured once: $$ must keep
        # the ORIGINAL shell's pid in subshells, command substitutions and
        # forked children (POSIX) — never the child's os.getpid().
        self.shell_pid = os.getpid()

        # Terminal capabilities — one cohesive object (is_terminal /
        # terminal_fd / supports_job_control delegate to it via properties);
        # populated by terminal.detect() below.
        self.terminal = TerminalState()

        # PS4 prompt for xtrace
        self.scope_manager.set_variable('PS4', '+ ')

        # Initialize getopts variables
        self.scope_manager.set_variable('OPTIND', '1')
        self.scope_manager.set_variable('OPTERR', '1')

        # PSH-specific variables
        self.scope_manager.set_variable('PSH_AST_FORMAT', 'tree')  # Default AST format

        # Trap handlers: signal -> command string
        # Maps signal names (e.g., 'INT', 'TERM', 'EXIT') to trap command strings
        self.trap_handlers: Dict[str, str] = {}

        # Names in trap_handlers that came from a parent shell and are kept
        # for LISTING only (the POSIX ``saved=$(trap)`` idiom): they never
        # fire in this shell, and the first trap modification drops them.
        # Populated by adopt(); semantics live in TrapManager.
        self.inherited_traps: Set[str] = set()

        # Detect terminal capabilities after initialization
        self.terminal.detect(debug=self.options.get('debug-exec', False))

    def _seed_strict_errors(self) -> bool:
        """Default value for the strict-errors option, from the environment.

        The test harness flips PSH_STRICT_ERRORS to surface latent internal
        defects (otherwise masked as a generic exit-1). Truthy values are
        ``1``/``true``/``yes`` (case-insensitive), mirroring the
        PSH_SHOW_ALL_OPTIONS convention; anything else is False.
        """
        return self.env.get('PSH_STRICT_ERRORS', '').lower() in ('1', 'true',
                                                                  'yes')

    def adopt(self, parent: 'ShellState') -> None:
        """Copy inheritable execution state from a parent shell's state.

        This is the pure state-copying half of subshell creation (the
        Shell-level half — function/alias manager copies — lives in
        ``Shell._inherit_from_parent``). It copies the live environment,
        every variable scope (whole ``Variable`` objects, preserving
        attributes), positional parameters, shell options (set -e,
        pipefail, ...), ``$?``, script mode, ``$0``, PIPESTATUS, ``$PPID``
        and ``$$``, the function/source context (FUNCNAME, ``return`` in
        a sourced file), traps (listing-only — see below), the directory
        stack, command history, the getopts cursor and the scope
        manager's computed-special state (SECONDS baseline), then
        re-syncs exported variables (including local exports) into the
        environment.

        Mode flags ('interactive', 'stdin_mode', 'emacs') are recomputed
        afterwards by ``Shell._init_interactive`` and overwrite their
        copies. Jobs are never copied — those are shell-specific.

        Every ``__init__`` field must be handled here or justified on the
        exclusion list in tests/unit/core/test_state_adopt_completeness.py
        (the drift-lock for the seven silently-uncopied fields
        reappraisal #15 found).
        """
        self.env = parent.env.copy()
        # Copy global variables as whole Variable objects to preserve
        # attributes (export, readonly, arrays, ...).
        for name, var in parent.scope_manager.global_scope.variables.items():
            self.scope_manager.global_scope.variables[name] = var.copy()
        # Copy all nested scopes to inherit local variables and their
        # attributes (skip global — already copied above).
        for scope in parent.scope_manager.scope_stack[1:]:
            self.scope_manager.scope_stack.append(scope.copy())
        self.positional_params = parent.positional_params.copy()
        self.options.update(parent.options)
        # bash: subshell-style children inherit the command hash table
        # (probe: `hash ls; (hash)` lists the entry in the subshell).
        self.command_hash = parent.command_hash.copy()
        # Inherit the per-command execution state as a unit — $? ($last_exit_code),
        # $! (last_bg_pid; subshells inherit it, bash: `sleep 1 & ( echo $! )`),
        # PIPESTATUS, errexit eligibility, etc. Copying via the sub-object means a
        # new execution field can't be silently forgotten here (the v0.453 $! bug).
        parent.execution.copy_into(self.execution)
        self.script_name = parent.script_name
        self.is_script_mode = parent.is_script_mode
        self.initial_ppid = parent.initial_ppid
        self.shell_pid = parent.shell_pid
        # Function/source context: ${FUNCNAME[@]} is visible in subshells
        # (bash: f() { (echo ${FUNCNAME[0]}); }; f prints f), and `return`
        # is legal in a child of a function or sourced-file context.
        self.function_stack = parent.function_stack.copy()
        self.source_depth = parent.source_depth
        # getopts cursor: a clustered-option walk (-ab) spans into children
        # (bash: set -- -ab; getopts ab o; $(getopts ab o; echo $o) sees b).
        self._getopts_charpos = parent._getopts_charpos
        self._getopts_charpos_optind = parent._getopts_charpos_optind
        # Command history: the child sees the parent's entries, but its own
        # additions must not leak back (fresh list, shared settings).
        self.history_state = parent.history_state.copy()
        # pushd/popd stack ((dirs) shows the parent's stack). Created
        # lazily by the directory-stack builtins, hence the guard.
        if hasattr(parent, 'directory_stack'):
            self.directory_stack = parent.directory_stack.copy()
        # Traps: bash RESETS non-ignored traps in a subshell-style child —
        # they never fire there — but keeps them LISTABLE (the POSIX
        # saved=$(trap) idiom) until the child's first trap modification
        # (TrapManager.drop_inherited_traps). Ignored ('') traps remain
        # genuinely in effect. ERR/DEBUG escape the reset under
        # set -E (errtrace) / set -T (functrace), as in bash.
        self.trap_handlers = dict(parent.trap_handlers)
        live = set()
        if self.options.get('errtrace'):
            live.add('ERR')
        if self.options.get('functrace'):
            live.add('DEBUG')
        self.inherited_traps = {
            name for name, action in self.trap_handlers.items()
            if action != '' and name not in live
        }
        # SECONDS baseline, deactivated specials, current line number
        # (RANDOM's generator state deliberately stays fresh — see method).
        self.scope_manager.adopt_special_state(parent.scope_manager)
        # Sync all exported variables (including local exports) to environment
        self.scope_manager.sync_exports_to_environment(self.env)

    # stdin/stdout/stderr delegate to the explicit StreamBindings object
    # (self.streams). Each returns the live sys.* stream unless a caller
    # has installed an override; setting installs one. Behaviour is
    # identical to the former dynamic _custom_* attributes.
    @property
    def stdout(self):
        """The shell's output stream (live sys.stdout unless overridden)."""
        return self.streams.stdout

    @stdout.setter
    def stdout(self, value):
        """Install a custom stdout override."""
        self.streams.stdout = value

    @property
    def stderr(self):
        """The shell's error stream (live sys.stderr unless overridden)."""
        return self.streams.stderr

    @stderr.setter
    def stderr(self, value):
        """Install a custom stderr override."""
        self.streams.stderr = value

    @property
    def stdin(self):
        """The shell's input stream (live sys.stdin unless overridden)."""
        return self.streams.stdin

    @stdin.setter
    def stdin(self, value):
        """Install a custom stdin override."""
        self.streams.stdin = value

    # is_terminal/terminal_fd/supports_job_control delegate to the explicit
    # TerminalState object (self.terminal), detected once at startup.
    @property
    def is_terminal(self) -> bool:
        """True if stdin is a controlling terminal."""
        return self.terminal.is_terminal

    @is_terminal.setter
    def is_terminal(self, value: bool) -> None:
        self.terminal.is_terminal = value

    @property
    def terminal_fd(self) -> Optional[int]:
        """The controlling-terminal fd (0 when present), else None."""
        return self.terminal.terminal_fd

    @terminal_fd.setter
    def terminal_fd(self, value: Optional[int]) -> None:
        self.terminal.terminal_fd = value

    @property
    def supports_job_control(self) -> bool:
        """True if the terminal supports job control (tcgetpgrp succeeds)."""
        return self.terminal.supports_job_control

    @supports_job_control.setter
    def supports_job_control(self, value: bool) -> None:
        self.terminal.supports_job_control = value

    # history/history_file/max_history_size delegate to the explicit
    # HistoryState object (self.history_state). The list is returned by
    # reference so in-place append()/clear() still work.
    @property
    def history(self) -> list:
        """The command history list (mutated in place by HistoryManager)."""
        return self.history_state.entries

    @history.setter
    def history(self, value: list) -> None:
        self.history_state.entries = value

    @property
    def history_file(self) -> str:
        """Path to the persisted history file.

        Honors ``$HISTFILE`` (bash) when set, else the HistoryState default
        (``~/.psh_history``). Read dynamically so a script setting ``HISTFILE``
        takes effect.
        """
        histfile = self.get_variable('HISTFILE')
        if histfile:
            return os.path.expanduser(histfile)
        return self.history_state.file_path

    @history_file.setter
    def history_file(self, value: str) -> None:
        self.history_state.file_path = value

    @property
    def max_history_size(self) -> int:
        """Maximum number of history entries to keep/persist.

        Honors ``$HISTSIZE`` (bash) when set to a non-negative integer, else the
        HistoryState default. Read dynamically.
        """
        histsize = self.get_variable('HISTSIZE')
        if histsize:
            try:
                n = int(histsize)
            except (ValueError, TypeError):
                n = -1
            if n >= 0:
                return n
        return self.history_state.max_size

    @max_history_size.setter
    def max_history_size(self, value: int) -> None:
        self.history_state.max_size = value

    # Per-command execution state delegates to the explicit ExecutionState
    # object (self.execution); see execution_state.py.
    @property
    def last_exit_code(self) -> int:
        """Exit status of the last foreground command ($?)."""
        return self.execution.last_exit_code

    @last_exit_code.setter
    def last_exit_code(self, value: int) -> None:
        self.execution.last_exit_code = value

    @property
    def last_bg_pid(self) -> Optional[int]:
        """PID of the most recent background command ($!)."""
        return self.execution.last_bg_pid

    @last_bg_pid.setter
    def last_bg_pid(self, value: Optional[int]) -> None:
        self.execution.last_bg_pid = value

    @property
    def foreground_pgid(self) -> Optional[int]:
        """Process group currently owning the terminal."""
        return self.execution.foreground_pgid

    @foreground_pgid.setter
    def foreground_pgid(self, value: Optional[int]) -> None:
        self.execution.foreground_pgid = value

    @property
    def command_number(self) -> int:
        """Monotonic command counter (prompt \\#/\\!, history numbering)."""
        return self.execution.command_number

    @command_number.setter
    def command_number(self, value: int) -> None:
        self.execution.command_number = value

    @property
    def pipestatus(self) -> list:
        """Exit statuses of the most recent foreground pipeline (PIPESTATUS)."""
        return self.execution.pipestatus

    @pipestatus.setter
    def pipestatus(self, value: list) -> None:
        self.execution.pipestatus = value

    @property
    def errexit_eligible(self) -> bool:
        """Whether the most recent command status may trigger `set -e`."""
        return self.execution.errexit_eligible

    @errexit_eligible.setter
    def errexit_eligible(self, value: bool) -> None:
        self.execution.errexit_eligible = value

    @property
    def last_cmdsub_status(self) -> Optional[int]:
        """Exit status of the most recent command substitution, or None."""
        return self.execution.last_cmdsub_status

    @last_cmdsub_status.setter
    def last_cmdsub_status(self, value: Optional[int]) -> None:
        self.execution.last_cmdsub_status = value

    @property
    def in_forked_child(self) -> bool:
        """True only inside a forked child (pipeline member, subshell, ...)."""
        return self.execution.in_forked_child

    @in_forked_child.setter
    def in_forked_child(self, value: bool) -> None:
        self.execution.in_forked_child = value

    @property
    def debug_ast(self):
        """Whether AST debug output is enabled."""
        return self.options.get('debug-ast', False)

    @debug_ast.setter
    def debug_ast(self, value):
        self.options['debug-ast'] = value

    @property
    def debug_tokens(self):
        """Whether token debug output is enabled."""
        return self.options.get('debug-tokens', False)

    @debug_tokens.setter
    def debug_tokens(self, value):
        self.options['debug-tokens'] = value

    @property
    def debug_scopes(self):
        """Whether scope debug output is enabled."""
        return self.options.get('debug-scopes', False)

    @debug_scopes.setter
    def debug_scopes(self, value):
        self.options['debug-scopes'] = value
        if hasattr(self, 'scope_manager'):
            self.scope_manager.enable_debug(value)

    @property
    def variables(self) -> Dict[str, str]:
        """Return all visible variables as a dict."""
        return self.scope_manager.get_all_variables()

    def get_variable(self, name: str, default: str = '') -> str:
        """Get variable value, checking shell variables first, then environment."""
        # Check scope manager first (includes locals and globals)
        result = self.scope_manager.get_variable(name)
        if result is not None:
            return result
        # Fall back to environment
        return self.env.get(name, default)

    def set_variable(self, name: str, value: Any):
        """Set a shell variable.

        ``value`` is usually a string but may be an array object
        (``IndexedArray``/``AssociativeArray``) — e.g. a scalar append to an
        array variable resolves to the whole array — which the scope manager
        stores as-is.

        Under ``set -a`` (allexport) the variable gains the EXPORT
        attribute. Either way the scope manager's variable_changed
        observer (:meth:`_sync_exported_variable`) keeps ``self.env`` —
        the live environment; os.environ is read once at startup and
        never written — in sync with the variable's export attribute.
        """
        attributes = (VarAttributes.EXPORT if self.options.get('allexport', False)
                      else VarAttributes.NONE)
        self.scope_manager.set_variable(name, value, attributes=attributes, local=False)

    def export_variable(self, name: str, value: str):
        """Set a variable with the EXPORT attribute (the observer adds the
        ``state.env`` entry; os.environ is never written — class docstring)."""
        self.scope_manager.set_variable(name, value, attributes=VarAttributes.EXPORT, local=False)

    def _sync_exported_variable(self, name: str) -> None:
        """Re-derive one name's live-environment entry from its variable.

        Installed as ``scope_manager.variable_changed``; fired after any
        write, unset, attribute change, or scope pop affecting *name*.
        The environment entry exists exactly when the visible variable
        carries the EXPORT attribute, is not an array (bash never exports
        arrays), and is not declared-but-unset (``export FOO`` records
        the attribute; the entry appears when FOO is assigned).
        """
        var = self.scope_manager.get_variable_object(name)
        if var is not None and var.is_exported and not var.is_array:
            self.env[name] = var.as_string()
        else:
            self.env.pop(name, None)

    def get_positional_param(self, index: int) -> str:
        """Get positional parameter by index (1-based)."""
        if 1 <= index <= len(self.positional_params):
            return self.positional_params[index - 1]
        return ''

    def set_positional_params(self, params):
        """Set positional parameters ($1, $2, etc.)."""
        self.positional_params = params.copy() if params else []

    def ifs_star_separator(self) -> str:
        """Separator for joining ``$*`` / ``${arr[*]}`` — THE one source.

        bash distinguishes unset IFS (join with a space) from a null IFS
        (``IFS=``, join with no separator); only the first char is used
        otherwise. Shared by get_special_variable below and the expansion
        operators (OperatorOpsMixin delegates here).
        """
        ifs = self.scope_manager.get_variable('IFS', None)
        if ifs is None:
            return ' '
        return ifs[0] if ifs else ''

    def get_special_variable(self, name: str) -> str:
        """Get special variable value ($?, $$, $!, etc.)."""
        if name == '?':
            return str(self.last_exit_code)
        elif name == '$':
            return str(self.shell_pid)
        elif name == '!':
            return str(self.last_bg_pid) if self.last_bg_pid else ''
        elif name == '#':
            return str(len(self.positional_params))
        elif name == '0':
            return self.script_name
        elif name == '@':
            # $@ in a string (non-list) context joins with a space
            # regardless of IFS (bash: ``IFS=:; set -- a b; x=$@`` → "a b")
            return ' '.join(self.positional_params)
        elif name == '*':
            return self.ifs_star_separator().join(self.positional_params)
        elif name == '-':
            return self.get_option_string()
        elif name.isdigit():
            return self.get_positional_param(int(name))
        return ''

    def get_option_string(self) -> str:
        """The ``$-`` flag string. Order and letters are owned by the option
        registry (see ``ShellOptions.option_string``)."""
        return self.options.option_string()

