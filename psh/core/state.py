"""Shell state management."""
import os
import sys
from typing import Dict, Optional

from ..version import __version__
from .command_hash import CommandHashTable
from .scope import ScopeManager
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

    def __init__(self, args=None, script_name=None, debug_ast=False,
                 debug_tokens=False, debug_scopes=False, debug_expansion=False, debug_expansion_detail=False,
                 debug_exec=False, debug_exec_fork=False, norc=False, rcfile=None):
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

        # Centralized shell options dictionary
        self.options = {
            # Debug options (existing)
            'debug-ast': debug_ast,
            'debug-tokens': debug_tokens,
            'debug-scopes': debug_scopes,
            'debug-expansion': debug_expansion,
            'debug-expansion-detail': debug_expansion_detail,
            'debug-exec': debug_exec,
            'debug-exec-fork': debug_exec_fork,
            # Re-raise unexpected internal exceptions instead of swallowing
            # them to status 1, so a test harness surfaces internal defects.
            # Seeded from PSH_STRICT_ERRORS below; toggle with
            # set -o strict-errors / set +o strict-errors.
            'strict-errors': self._seed_strict_errors(),
            # Shell options (existing)
            'errexit': False,      # -e: exit on error
            'nounset': False,      # -u: error on undefined variables
            'xtrace': False,       # -x: print commands before execution
            'pipefail': False,     # -o pipefail: pipeline fails if any command fails
            # New POSIX options
            'allexport': False,    # -a: auto-export all variables
            'notify': False,       # -b: async job completion notifications
            'noclobber': False,    # -C: prevent file overwriting with >
            'noglob': False,       # -f: disable pathname expansion
            'hashcmds': True,      # -h: hash command locations (bash default ON)
            'monitor': False,      # -m: job control mode (default for interactive)
            'noexec': False,       # -n: read commands but don't execute
            'verbose': False,      # -v: echo input lines as read
            'ignoreeof': False,    # -o ignoreeof: don't exit on EOF
            'nolog': False,        # -o nolog: don't log function definitions
            # Bash compatibility options (shopt)
            'dotglob': False,      # dotglob: glob matches dotfiles
            'nullglob': False,     # nullglob: glob with no matches returns empty
            'extglob': False,      # extglob: extended globbing patterns
            'nocaseglob': False,   # nocaseglob: case-insensitive globbing
            'globstar': False,     # globstar: ** matches recursively
            'checkhash': False,    # checkhash: re-verify hashed paths before exec
            'braceexpand': True,   # -o braceexpand: enable brace expansion (default on)
            'emacs': False,        # -o emacs: emacs key bindings (context-dependent)
            'vi': False,           # -o vi: vi key bindings (off for set -o display)
            'histexpand': True,    # -o histexpand: enable history expansion (default on)
            'interactive': False,  # -i: interactive mode (set by shell init)
            'stdin_mode': True,    # reading from stdin (no script file; set by shell init)
            # Parser configuration options (enhanced features now standard)
            'posix': False,        # -o posix: strict POSIX mode
            'collect_errors': False,  # -o collect_errors: collect multiple parse errors
            'parser-mode': 'balanced', # -o parser-mode: performance mode (performance/balanced/development)
        }

        # Enable debug mode on scope manager if debug-scopes is set
        if self.options['debug-scopes']:
            self.scope_manager.enable_debug(True)

        # RC file options
        self.norc = norc
        self.rcfile = rcfile

        # Execution state
        self.last_exit_code = 0
        self.last_bg_pid = None
        self.foreground_pgid = None
        self.command_number = 0

        # History settings
        self.history = []
        self.history_file = os.path.expanduser("~/.psh_history")
        self.max_history_size = 1000
        self.history_index = -1
        self.current_line = ""

        # Editor configuration
        self.edit_mode = 'emacs'

        # Function call stack
        self.function_stack = []

        # Depth of nested `source`/`.` execution. `return` is legal inside a
        # sourced script (it stops the file), so ReturnBuiltin checks this in
        # addition to function_stack.
        self.source_depth = 0

        # Exit statuses of the most recently executed foreground pipeline
        # (PIPESTATUS). A single command records a one-element list.
        self.pipestatus = []

        # The shell's parent process id at startup ($PPID). Subshells
        # inherit it (bash: PPID does not change in subshells).
        self.initial_ppid = os.getppid()

        # The shell's own pid at startup ($$). Captured once: $$ must keep
        # the ORIGINAL shell's pid in subshells, command substitutions and
        # forked children (POSIX) — never the child's os.getpid().
        self.shell_pid = os.getpid()

        # Whether the most recent command status may trigger set -e.
        # Maintained by ExecutorVisitor.visit_AndOrList: False for failures
        # POSIX exempts from errexit (condition contexts, non-final members
        # of && / || lists, !-negated pipelines).
        self.errexit_eligible = True

        # Exit status of the most recent command substitution, or None.
        # CommandExecutor clears it before expanding a pure assignment's
        # value and uses it as the assignment's exit status (bash: a pure
        # assignment reports 0 unless a command substitution ran).
        self.last_cmdsub_status = None

        # Process state. True only inside a forked child (pipeline member,
        # subshell, command-substitution child, etc.); leaf builtins consult it
        # to decide between fd-level writes (os.write) and shell.stdout. A real
        # first-class attribute so callers read it directly, not via hasattr.
        self.in_forked_child = False

        # Terminal capabilities (set by _detect_terminal_capabilities)
        self.terminal_fd: Optional[int] = None
        self.supports_job_control: bool = False
        self.is_terminal: bool = False

        # PS4 prompt for xtrace
        self.scope_manager.set_variable('PS4', '+ ')

        # Initialize getopts variables
        self.scope_manager.set_variable('OPTIND', '1')
        self.scope_manager.set_variable('OPTERR', '1')

        # PSH-specific variables
        self.scope_manager.set_variable('PSH_AST_FORMAT', 'tree')  # Default AST format

        # Trap handlers: signal -> command string
        # Maps signal names (e.g., 'INT', 'TERM', 'EXIT') to trap command strings
        self.trap_handlers = {}

        # Detect terminal capabilities after initialization
        self._detect_terminal_capabilities()

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
        pipefail, ...), ``$?``, script mode, PIPESTATUS, ``$PPID`` and
        ``$$``, then re-syncs exported variables (including local
        exports) into the environment.

        Mode flags ('interactive', 'stdin_mode', 'emacs') are recomputed
        afterwards by ``Shell._init_interactive`` and overwrite their
        copies. Jobs are never copied — those are shell-specific.
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
        self.last_exit_code = parent.last_exit_code
        self.is_script_mode = parent.is_script_mode
        self.pipestatus = list(parent.pipestatus)
        self.initial_ppid = parent.initial_ppid
        self.shell_pid = parent.shell_pid
        # Sync all exported variables (including local exports) to environment
        self.scope_manager.sync_exports_to_environment(self.env)

    @property
    def stdout(self):
        """Always return current sys.stdout for test compatibility."""
        # If we have a custom stdout set, use it
        if hasattr(self, '_custom_stdout'):
            return self._custom_stdout
        # Otherwise return current sys.stdout (which pytest might have replaced)
        return sys.stdout

    @stdout.setter
    def stdout(self, value):
        """Allow setting a custom stdout."""
        self._custom_stdout = value

    @property
    def stderr(self):
        """Always return current sys.stderr for test compatibility."""
        if hasattr(self, '_custom_stderr'):
            return self._custom_stderr
        return sys.stderr

    @stderr.setter
    def stderr(self, value):
        """Allow setting a custom stderr."""
        self._custom_stderr = value

    @property
    def stdin(self):
        """Always return current sys.stdin for test compatibility."""
        if hasattr(self, '_custom_stdin'):
            return self._custom_stdin
        return sys.stdin

    @stdin.setter
    def stdin(self, value):
        """Allow setting a custom stdin."""
        self._custom_stdin = value

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

    def set_variable(self, name: str, value: str):
        """Set a shell variable.

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
        """Get string representation of set options for $- special variable.

        Returns flags matching bash's $- format. Includes both options set via
        'set' builtin and implicit flags like 'i' (interactive), 's' (stdin mode),
        'B' (braceexpand), and 'H' (histexpand).
        """
        opts = []
        # Bash $- order: single-letter options (lowercase then uppercase,
        # alphabetical), with the invocation-mode flags 'c' (-c) and 's'
        # (stdin) appended LAST. Verified against bash 5.x, e.g.
        #   bash -c 'echo $-'  -> hBc      bash -ic 'echo $-' -> hiBHc
        #   echo 'echo $-'|bash -> hBs     set -aefuvx        -> aefhuvxBc
        if self.options.get('allexport'): opts.append('a')
        if self.options.get('notify'): opts.append('b')
        if self.options.get('errexit'): opts.append('e')
        if self.options.get('noglob'): opts.append('f')
        if self.options.get('hashcmds'): opts.append('h')
        if self.options.get('interactive'): opts.append('i')
        if self.options.get('monitor'): opts.append('m')
        if self.options.get('noexec'): opts.append('n')
        if self.options.get('nounset'): opts.append('u')
        if self.options.get('verbose'): opts.append('v')
        if self.options.get('xtrace'): opts.append('x')
        if self.options.get('braceexpand'): opts.append('B')
        if self.options.get('noclobber'): opts.append('C')
        if self.options.get('histexpand'): opts.append('H')
        # Invocation-mode flags come last in bash's $-.
        if self.options.get('command_mode'): opts.append('c')
        if self.options.get('stdin_mode'): opts.append('s')
        return ''.join(opts)

    def _detect_terminal_capabilities(self):
        """Detect if we have a controlling terminal with job control support.

        This determines whether we can use tcsetpgrp(), tcgetpgrp(), etc.
        Results are cached in state for efficient checks.
        """
        try:
            # Check if stdin is a TTY
            if os.isatty(0):
                self.is_terminal = True
                self.terminal_fd = 0

                # Check if we can actually do job control
                # Some TTY environments don't support it (e.g., emacs shell-mode)
                try:
                    current_pgid = os.tcgetpgrp(0)
                    self.supports_job_control = True

                    if self.options.get('debug-exec'):
                        print(f"DEBUG: Terminal detected, job control available (pgid={current_pgid})",
                              file=sys.stderr)
                except OSError as e:
                    # TTY but no job control available
                    self.supports_job_control = False
                    if self.options.get('debug-exec'):
                        print(f"DEBUG: Terminal detected but job control unavailable: {e}",
                              file=sys.stderr)
            else:
                self.is_terminal = False
                self.supports_job_control = False
                if self.options.get('debug-exec'):
                    print(f"DEBUG: Not running on a terminal (stdin is not a TTY)",
                          file=sys.stderr)
        except (OSError, AttributeError):
            # Platform doesn't support TTY detection
            self.is_terminal = False
            self.supports_job_control = False
            if self.options.get('debug-exec'):
                print(f"DEBUG: Platform doesn't support TTY detection",
                      file=sys.stderr)
