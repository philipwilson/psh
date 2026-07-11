"""Shell state management."""
import enum
import os
import sys
from typing import Any, Dict, Iterable, Optional, Set

from ..version import __version__
from .command_hash import CommandHashTable
from .environment import is_environ_shell_name
from .exceptions import ReadonlyVariableError
from .execution_state import ExecutionState
from .getopts_state import GetoptsState
from .history_state import HistoryState
from .locale_service import LocaleService
from .option_registry import (
    SET_O_OPTION_NAMES,
    SHOPT_OPTION_NAMES,
    ShellOptions,
)
from .scope import ScopeManager
from .special_registry import SPECIAL_REGISTRY
from .stream_bindings import StreamBindings
from .terminal_state import TerminalState
from .variables import VarAttributes


def _colon_units(value: str):
    """Yield colon-separated units exactly like bash's extract_colon_unit.

    NOT a naive ``split(':')``: adjacent/leading/trailing colons yield empty
    units, but a lone ``':'`` yields ONE empty unit (split would give two)
    and an empty string yields none. Probe-pinned against bash 5.2's
    SHELLOPTS import warnings (``':'`` warns once, ``'::'`` twice,
    ``'errexit:'`` once, ``''`` not at all — tmp/optreflect/probe3).
    """
    i, n = 0, len(value)
    while i < n:
        if i and value[i] == ':':
            i += 1
        start = i
        while i < n and value[i] != ':':
            i += 1
        if i == start:
            if i < n:
                i += 1
            yield ''
        else:
            yield value[start:i]


class ChildContext(enum.Enum):
    """How a child shell relates to its parent's OS process.

    ``SUBSHELL`` — a forked child: ``( )`` subshells, command/process
    substitution, backgrounded compounds. The clone runs in the forked
    process.

    ``IN_PROCESS`` — a child ``Shell`` sharing the parent's OS process (no
    fork). Named for completeness; standard ``env`` became external argv
    execution (v0.656), so there is no live in-process caller today — an
    embedding that wants one calls ``clone_for_child(context=IN_PROCESS)``
    directly.

    Both contexts share identical clone policy in Phase 1; the distinction is
    named now so a future policy split (e.g. process-local resource handling)
    has an explicit hook.
    """

    SUBSHELL = "subshell"
    IN_PROCESS = "in_process"


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
        # Undo PEP 538's C-locale coercion (see the method) BEFORE the locale
        # service reads the env and BEFORE the import loop turns it into a
        # variable, so the phantom LC_CTYPE never reaches classification,
        # ``$LC_CTYPE``, or a child's environment.
        self._strip_coerced_lc_ctype()

        # Central locale service: resolves the effective LC_CTYPE/LC_COLLATE
        # from the environment (bash precedence) and owns the process
        # ``setlocale`` calls. In the C/POSIX locale it is side-effect free and
        # every primitive stays byte-identical to psh's old codepoint/ASCII
        # behaviour; a ``*.UTF-8`` locale enables faithful collation, case
        # mapping, and character-class membership. Reactive as of Stage 4: the
        # ``_sync_exported_variable`` observer re-derives it on any LC_*/LANG
        # assignment, unset, or ``LC_ALL=C cmd`` temp-env prefix.
        self.locale = LocaleService(self.env)

        # Initialize enhanced scope manager for variable scoping with attributes
        self.scope_manager = ScopeManager()

        # getopts continuation cursor (typed). Created BEFORE the
        # variable_changed observer is wired below, because that observer bumps
        # getopts_state.optind_writes on every OPTIND assignment (the signal
        # getopts uses to detect a script `OPTIND=...` restart).
        self.getopts_state = GetoptsState()

        # Remembered command locations (the `hash` builtin / bash's
        # COMMAND EXECUTION hashing). Any PATH write empties it — the
        # scope manager fires the observer below for every PATH
        # assignment/local/unset (bash 5.2, probe-verified: even
        # ``PATH=$PATH`` and ``local PATH=...`` clear; ``cd`` does not).
        # The lambda reads self.command_hash at call time so clone_for_child()'s
        # table replacement stays wired.
        self.command_hash = CommandHashTable()
        self.scope_manager.path_changed = lambda: self.command_hash.clear()

        # Default prompt variables (set in global scope)
        self.scope_manager.set_variable('PS1', 'psh$ ')
        self.scope_manager.set_variable('PS2', '> ')

        # Shell version variable for compatibility
        self.scope_manager.set_variable('PSH_VERSION', __version__)

        # Import inherited environment entries as exported shell variables —
        # but ONLY those whose name is a valid shell identifier. An entry with
        # an invalid name (``bad-name``, ``a.b``, a non-ASCII name) stays in
        # ``self.env`` as an OPAQUE inherited entry: it is passed to children
        # and shown by ``printenv``, but is NOT a shell variable (no scope
        # entry, so ``declare -p`` / ``set`` / ``compgen -v`` / ``export -p``
        # do not list it) — bash's behaviour (core-state appraisal H3).
        for name, value in self.env.items():
            # A readonly dynamic special (SHELLOPTS/BASHOPTS) can never be
            # assigned — the lifecycle interception would raise. Their
            # inherited values are consumed by
            # _import_option_reflection_from_env below (bash: the listed
            # options are enabled and the variable is marked exported).
            spec = SPECIAL_REGISTRY.get(name)
            if (spec is not None and spec.lifecycle
                    and spec.default_attributes & VarAttributes.READONLY):
                continue
            if is_environ_shell_name(name):
                self.scope_manager.set_variable(name, value, attributes=VarAttributes.EXPORT, local=False)

        # The opaque inherited-environment base: the entries whose NAME is not a
        # valid shell identifier (``bad-name``, ``a.b``, a non-ASCII name). They
        # are NOT shell variables, so they never flow through the scope manager;
        # they are passed to children and shown by ``printenv`` but not ``set`` /
        # ``declare -p`` / ``export -p`` (bash; appraisal H3). Kept as an
        # EXPLICIT typed store so the execution environment can be MATERIALIZED
        # as opaque-base + exported-vars + command-overlay instead of derived by
        # incremental mutation, and so a child clone inherits it exactly.
        self._env_base: Dict[str, str] = {
            name: value for name, value in self.env.items()
            if not is_environ_shell_name(name)
        }
        # Command-local temporary-environment overlay (``VAR=x cmd`` over a
        # builtin/external): the LITERAL strings this one command's process
        # environment carries, composed on top of the exported variables at
        # materialization. Empty except for the duration of such a command (a
        # function call layers a temp-env SCOPE instead — see
        # CommandAssignments.apply_prefix). The literal wins over the
        # exported-variable value so ``RANDOM=5 cmd`` passes ``5`` and
        # ``a+=z cmd`` passes the element-0 view, not a re-derived value.
        self._env_overlay: Dict[str, str] = {}

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

        # Seed IFS to the default <space><tab><newline> as a REAL variable so
        # ``$IFS`` expands, ``declare -p IFS`` prints it, and the save/restore
        # idiom (``OLD=$IFS; IFS=,; ...; IFS=$OLD``) round-trips. bash resets
        # IFS's VALUE to the default at startup regardless of any inherited
        # value, but keeps the export attribute if it was inherited exported —
        # passing no attributes preserves an imported EXPORT (declare -x) while
        # replacing the value (declare -- otherwise). Word splitting still uses
        # the same default when IFS is UNSET (get_variable's fallback arg), so
        # ``unset IFS`` keeps bash's whitespace splitting.
        self.scope_manager.set_variable('IFS', ' \t\n')

        # Positional parameters and script info
        self.positional_params = args if args else []
        self.script_name = script_name or "psh"
        self.is_script_mode = script_name is not None and script_name != "psh"

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

        # SHELLOPTS/BASHOPTS inherited via the environment activate the listed
        # options at startup and mark the (computed, readonly) variable
        # exported (bash). Runs after the options container AND edit_mode
        # exist; the on_change observer below then keeps any exported entry
        # current on every option write.
        self._import_option_reflection_from_env()
        # POSIXLY_CORRECT present in the startup environment (any value,
        # including empty) enables posix mode (bash); it was already imported as
        # an exported shell variable by the env-import loop above. And if the
        # SHELLOPTS import just above enabled posix via an inherited list naming
        # it, bash binds POSIXLY_CORRECT the way `set -o posix` does. Both are
        # done BEFORE on_change is wired: the variable-write path is safe
        # pre-wiring, whereas firing the option observer here would materialize
        # the computed SHELLOPTS value before the shell is fully wired. An
        # inherited POSIXLY_CORRECT value is kept; the SHELLOPTS path binds "y".
        if 'POSIXLY_CORRECT' in self.env:
            self.options['posix'] = True
        if (self.options.get('posix')
                and self.scope_manager.get_variable('POSIXLY_CORRECT') is None):
            self.scope_manager.set_variable(
                'POSIXLY_CORRECT', 'y', local=False)
        self.options.on_change = self._refresh_option_reflection_env

        # Function call stack
        self.function_stack = []

        # Depth of nested `source`/`.` execution. `return` is legal inside a
        # sourced script (it stops the file), so ReturnBuiltin checks this in
        # addition to function_stack.
        self.source_depth = 0

        # Re-entrancy depth of arithmetic evaluation. A variable whose value is
        # itself an expression is evaluated recursively (`x="x+1"; $((x))`), so
        # a self-referential or too-deeply-chained expression would exhaust the
        # interpreter stack. evaluate_arithmetic() bounds it to bash's
        # EXPR_NEST_MAX, tripping a clean "expression recursion level exceeded"
        # arithmetic error instead of a RecursionError.
        self._arith_recursion_depth = 0

        # The shell's parent process id at startup ($PPID). Subshells
        # inherit it (bash: PPID does not change in subshells).
        self.initial_ppid = os.getppid()

        # The shell's own pid at startup ($$). Captured once: $$ must keep
        # the ORIGINAL shell's pid in subshells, command substitutions and
        # forked children (POSIX) — never the child's os.getpid().
        self.shell_pid = os.getpid()

        # UID/EUID/PPID are READONLY INTEGER variables in bash (`declare -ir`),
        # initialized ONCE at startup — not recomputed per read. Storing them
        # as real variables (rather than computing them on read) makes
        # assignment and `unset` fail like bash, and lists them in `declare -p`
        # / `readonly -p`. PPID uses the startup parent pid (kept stable across
        # subshells because clone_for_child() copies the whole global scope); a subshell's
        # own $$/BASHPID differ but PPID does not (bash).
        for _pid_name, _pid_value in (('UID', os.getuid()),
                                      ('EUID', os.geteuid()),
                                      ('PPID', self.initial_ppid)):
            self.scope_manager.set_variable(
                _pid_name, str(_pid_value), local=False,
                attributes=VarAttributes.READONLY | VarAttributes.INTEGER)

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

        # Platform identity variables (bash: HOSTNAME/OSTYPE/MACHTYPE/HOSTTYPE)
        # are ORDINARY shell variables initialized at startup — freely
        # reassignable and unsettable, unlike the readonly UID/EUID/PPID above.
        # Only seed a name the environment did not already provide, so an
        # inherited (exported) HOSTNAME is preserved like bash. Values are
        # derived from uname and differ machine-to-machine.
        _uname = os.uname()
        _machine = _uname.machine
        _sysname = _uname.sysname.lower()
        _ostype = (f"{_sysname}{_uname.release}" if _sysname == 'darwin'
                   else f"{_sysname}-gnu")
        _vendor = 'apple' if _sysname == 'darwin' else 'pc'
        for _pname, _pvalue in (('HOSTNAME', _uname.nodename),
                                ('HOSTTYPE', _machine),
                                ('OSTYPE', _ostype),
                                ('MACHTYPE', f"{_machine}-{_vendor}-{_ostype}")):
            if self.scope_manager.get_variable_object(_pname) is None:
                self.scope_manager.set_variable(_pname, _pvalue)

        # Trap handlers: signal -> command string
        # Maps signal names (e.g., 'INT', 'TERM', 'EXIT') to trap command strings
        self.trap_handlers: Dict[str, str] = {}

        # Names in trap_handlers that came from a parent shell and are kept
        # for LISTING only (the POSIX ``saved=$(trap)`` idiom): they never
        # fire in this shell, and the first trap modification drops them.
        # Populated by clone_for_child(); semantics live in TrapManager.
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

    def error_location_prefix(self) -> str:
        """bash's ``<$0>: [line N: ]`` location prefix for a runtime error.

        The single source of truth for the diagnostic prefix bash prepends to
        every runtime error — builtin errors, command-not-found, exec failures,
        ``set -u``/``${x:?}`` expansion errors, readonly-assignment failures.
        ``<$0>`` is the shell's invocation name (:attr:`script_name`: ``"psh"``
        for ``-c``/stdin, the script path in script mode, the ``-c`` trailing
        operand when given). ``line N:`` is added ONLY when the shell is
        NON-interactive — at an interactive prompt bash omits it (``bash: cd:
        ...``). Mirrors bash's ``get_name_for_error``/``builtin_error`` in
        ``error.c``. Parse errors deliberately keep psh's own richer
        ``psh: <src>:<line>:`` format and do NOT use this.
        """
        prog = self.script_name
        if self.options.get('interactive'):
            return f"{prog}: "
        return f"{prog}: line {self.scope_manager.get_current_line_number()}: "

    @classmethod
    def clone_for_child(cls, parent: 'ShellState',
                        context: ChildContext = ChildContext.SUBSHELL,
                        *, norc: bool = True,
                        rcfile: Optional[str] = None) -> 'ShellState':
        """Build an EXACT independent clone of *parent* for a child shell.

        This replaces the old construct-a-fresh-state-then-overlay ``adopt``
        path (``Shell._create_state`` used to build a fully seeded state that
        ``adopt`` immediately overwrote). The clone does NO fresh
        ``os.environ`` import and seeds NO defaults, so the child's variable
        AND environment keysets are EXACTLY the parent's: a name the parent
        unset stays unset in the child (the C1 resurrection defect — e.g.
        ``unset HOME`` no longer resurrects from the child's fresh import, and
        ``unset PS4`` no longer resurrects the ``+ `` default), and the
        discarded fresh initialization is gone (E2).

        Each component is cloned with its mapped copy policy:

        * mutable inheritable data (env, scopes with deep-copied arrays,
          command hash, options, execution state, history, positional params,
          function stack, directory stack, traps) is deep-cloned so a child
          mutation never reaches the parent;
        * process-local data (streams, terminal capabilities, the arithmetic
          re-entrancy counter) is reset for the child process;
        * derived state (the exported-environment sync, inherited-trap set) is
          recomputed; and
        * the locale service is shared (reactive as of Stage 4, but every
          in-tree clone is a forked SUBSHELL — separate memory — so a child's
          mid-session ``reinit`` mutates only its own copy and the process
          ``setlocale`` is inherited across the fork; a future IN_PROCESS
          embedding would need to give the child its own service and
          save/restore the process locale around it).

        ``$PPID``/``$$`` stay stable across subshells (POSIX); RANDOM's
        generator state is deliberately reset (bash reseeds it in a subshell);
        traps are reset-for-listing per subshell semantics (kept LISTABLE via
        ``inherited_traps`` until the child's first trap modification).

        The Shell-level half — function/alias manager copies and the
        ``scope_manager.set_shell`` back-reference — lives in
        ``Shell._inherit_from_parent`` / ``Shell.__init__``. Mode flags
        ('interactive', 'stdin_mode', 'emacs') are recomputed afterwards by
        ``Shell._init_interactive``. Jobs are never copied.

        The *context* is recorded for a future policy split (SUBSHELL vs
        IN_PROCESS); both share identical policy in Phase 1.
        """
        self = cls.__new__(cls)

        # Process-local streams: fresh. A forked child inherits fds at the OS
        # level; each child installs its own overrides (subshell pipes,
        # capture buffers) rather than the parent's.
        self.streams = StreamBindings()

        # Environment + variable scopes: EXACT copies, no import, no seeding.
        self.env = parent.env.copy()
        # Opaque inherited-env base and any active command-env overlay: copied
        # exactly so the child materializes env from the same authorities (a
        # child forked mid temp-env command inherits the overlay, like bash's
        # `V=x eval '(printenv V)'`).
        self._env_base = dict(parent._env_base)
        self._env_overlay = dict(parent._env_overlay)
        self.locale = parent.locale
        # clone() copies every scope (whole Variable objects, arrays deep) and
        # the computed-special state WITHOUT any set_variable call, so the
        # child keyset matches the parent's exactly.
        self.scope_manager = parent.scope_manager.clone()

        # Command hash table (bash: `hash ls; (hash)` lists it in the subshell)
        # + PATH observer. The lambda reads self.command_hash at call time.
        self.command_hash = parent.command_hash.copy()
        self.scope_manager.path_changed = lambda: self.command_hash.clear()
        self.scope_manager.variable_changed = self._sync_exported_variable

        self.positional_params = parent.positional_params.copy()
        self.script_name = parent.script_name
        self.is_script_mode = parent.is_script_mode

        # getopts cursor: a clustered-option walk (-ab) spans into children
        # (bash: set -- -ab; getopts ab o; $(getopts ab o; echo $o) sees b).
        self.getopts_state = parent.getopts_state.copy()

        # Shell options (set -e, pipefail, debug flags, ...). The on_change
        # observer is rewired to THIS state (the fresh container's is None, so
        # the update itself doesn't fire it); the copied env already holds the
        # parent's current SHELLOPTS/BASHOPTS entries.
        self.options = ShellOptions()
        self.options.update(parent.options)
        self.options.on_change = self._refresh_option_reflection_env

        # RC policy is per-invocation (children skip rc files by default),
        # never inherited.
        self.norc = norc
        self.rcfile = rcfile

        # Per-command execution state as a unit — $?/$!/PIPESTATUS/errexit
        # eligibility. copy_into leaves in_forked_child False (the fork site
        # stamps it).
        self.execution = ExecutionState()
        parent.execution.copy_into(self.execution)

        # Command history: child sees the parent's entries; its appends do not
        # leak back (fresh list, shared settings).
        self.history_state = parent.history_state.copy()
        self.edit_mode = parent.edit_mode

        # Function/source context: ${FUNCNAME[@]} is visible in subshells and
        # `return` is legal in a child of a function/sourced-file context.
        self.function_stack = parent.function_stack.copy()
        self.source_depth = parent.source_depth

        # Process-local arithmetic re-entrancy: a fresh evaluation context.
        self._arith_recursion_depth = 0

        # $PPID / $$ stay stable across subshells (POSIX).
        self.initial_ppid = parent.initial_ppid
        self.shell_pid = parent.shell_pid

        # Terminal capabilities: re-detected per process (a forked child may
        # have different fds), matching the fresh-init behaviour adopt relied
        # on. This keeps the not-a-terminal invariant that A5 will tighten.
        self.terminal = TerminalState()
        self.terminal.detect(debug=self.options.get('debug-exec', False))

        # Traps: bash RESETS non-ignored inherited traps in a subshell-style
        # child (they never fire there) but keeps them LISTABLE (the POSIX
        # saved=$(trap) idiom) until the child's first trap modification.
        # Ignored ('') traps remain in effect. ERR/DEBUG escape the reset
        # under set -E / set -T.
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

        # pushd/popd stack ((dirs) shows the parent's). Created lazily, hence
        # the guard.
        if hasattr(parent, 'directory_stack'):
            self.directory_stack = parent.directory_stack.copy()

        # Re-sync exported variables (including local exports) into the child
        # environment.
        self.scope_manager.sync_exports_to_environment(self.env)
        return self

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
        """Maximum number of in-memory history entries to keep.

        Honors ``$HISTSIZE`` (bash) when set to an integer: a NEGATIVE value
        means unlimited (bash), reported as ``sys.maxsize`` so the trim
        comparisons never fire. A non-numeric value falls back to the
        HistoryState default. Read dynamically.
        """
        histsize = self.get_variable('HISTSIZE')
        if histsize:
            try:
                n = int(histsize)
            except (ValueError, TypeError):
                return self.history_state.max_size
            # bash: a negative HISTSIZE means unlimited history.
            return sys.maxsize if n < 0 else n
        return self.history_state.max_size

    @max_history_size.setter
    def max_history_size(self, value: int) -> None:
        self.history_state.max_size = value

    @property
    def max_history_file_size(self) -> Optional[int]:
        """Maximum number of lines to persist to the history file.

        Honors ``$HISTFILESIZE`` (bash), read dynamically. We must tell an
        *unset* variable apart from one set to ``0`` or ``""``: reading the
        raw value straight from the scope/environment preserves ``None`` for
        genuinely unset (``ShellState.get_variable`` would collapse it to
        ``""``). Only unset returns ``None`` (the caller then falls back to
        ``max_history_size``) -- so ``HISTFILESIZE=0`` is NOT mistaken for
        unset. Value mapping matches bash: ``0`` caps the file to zero lines
        (truncate-to-empty), a positive integer is the line cap, and an
        empty-string / negative / non-numeric value inhibits truncation
        (reported as ``sys.maxsize``).
        """
        raw = self.scope_manager.get_variable('HISTFILESIZE')
        if raw is None:
            raw = self.env.get('HISTFILESIZE')
        if raw is None:
            return None
        try:
            n = int(raw)
        except (ValueError, TypeError):
            return sys.maxsize
        return sys.maxsize if n < 0 else n

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
    def bash_command(self) -> str:
        """Pre-expansion text of the command being executed ($BASH_COMMAND).

        The executor stamps the AST NODE (cheap) rather than rendered text;
        the render happens here, on the first read, and is cached back into
        the slot — so scripts that never read $BASH_COMMAND (no DEBUG/ERR
        trap, no literal reference) pay nothing per command. During a trap
        action the stamp is frozen (TrapManager.set_bash_command), so this
        renders the FROZEN node — the interrupted command (bash).
        """
        value = self.execution.bash_command
        if isinstance(value, str):
            return value
        from ..ast_nodes import CaseConditional, ForLoop
        from ..visitor import (
            format_bash_command,
            format_case_header,
            format_for_header,
        )
        # Compound constructs report a HEADER; everything else (simple
        # commands, [[ ]], ...) reports its own text.
        if isinstance(value, ForLoop):
            text = format_for_header(value)
        elif isinstance(value, CaseConditional):
            text = format_case_header(value)
        else:
            text = format_bash_command(value)
        self.execution.bash_command = text
        return text

    @bash_command.setter
    def bash_command(self, value: object) -> None:
        self.execution.bash_command = value

    @property
    def in_forked_child(self) -> bool:
        """True only inside a forked child (pipeline member, subshell, ...)."""
        return self.execution.in_forked_child

    @in_forked_child.setter
    def in_forked_child(self, value: bool) -> None:
        self.execution.in_forked_child = value

    @property
    def in_substitution(self) -> bool:
        """True inside a command/process substitution child (not a ( ) subshell)."""
        return self.execution.in_substitution

    @in_substitution.setter
    def in_substitution(self, value: bool) -> None:
        self.execution.in_substitution = value

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

        allexport does NOT auto-export a computed dynamic special (bash:
        ``set -a; RANDOM=5`` seeds RANDOM but leaves it unexported); only an
        explicit ``export``/``readonly`` marks a special exported.
        """
        allexport = (self.options.get('allexport', False)
                     and not self.scope_manager.is_dynamic_special(name))
        attributes = VarAttributes.EXPORT if allexport else VarAttributes.NONE
        self.scope_manager.set_variable(name, value, attributes=attributes, local=False)

    def export_variable(self, name: str, value: str):
        """Set a variable with the EXPORT attribute (the observer adds the
        ``state.env`` entry; os.environ is never written — class docstring).

        ``skip_temp_env`` writes past a command's temp-env prefix layer to the
        variable's real home, so ``X=1 f; f(){ export X=2; }`` updates the
        global X (which survives the function return) rather than the discarded
        temp layer — bash. (``cd``/``pushd``'s PWD/OLDPWD exports likewise want
        the real variable, never a temp shadow.)"""
        self.scope_manager.set_variable(name, value, attributes=VarAttributes.EXPORT,
                                        local=False, skip_temp_env=True)

    def _materialize_env_name(self, name: str) -> None:
        """Set ``self.env[name]`` from the ONE authoritative composition:
        command overlay (wins) > innermost exported variable > opaque base >
        absent.

        This is the single place ``self.env`` is derived for a name, so no
        caller needs to poke the dict directly (appraisal H3). The exported
        instance is the innermost EXPORTED one across scopes (not merely the
        innermost visible): a non-exported local shadowing an exported outer
        leaves the outer's entry in place (bash). Arrays are never exported and
        a declared-but-unset export (``export FOO``) has no entry until FOO is
        assigned; both fall through to the opaque base (which cannot hold their
        name, since exportable names are valid identifiers) and then to absent.
        """
        if name in self._env_overlay:
            self.env[name] = self._env_overlay[name]
            return
        var = self.scope_manager.find_exported_instance(name)
        if var is not None:
            self.env[name] = var.as_string()
        elif name in self._env_base:
            self.env[name] = self._env_base[name]
        else:
            self.env.pop(name, None)

    def _sync_exported_variable(self, name: str) -> None:
        """Re-derive one name's live-environment entry, then run the couple of
        variable-observer side effects (getopts restart, ignoreeof tracking).

        Installed as ``scope_manager.variable_changed``; fired after any
        write, unset, attribute change, or scope pop affecting *name*.
        """
        self._materialize_env_name(name)

        if name == 'OPTIND':
            # Every OPTIND assignment (getopts' own advance AND a script
            # `OPTIND=...`) bumps the counter; getopts compares it to the value
            # it recorded after its own write to detect a script restart —
            # including a same-value `OPTIND=$OPTIND` (bash restarts the scan).
            self.getopts_state.optind_writes += 1

        if name == 'IGNOREEOF':
            # sv_ignoreeof (bash): the `ignoreeof` option tracks whether
            # the IGNOREEOF variable exists at all — any value counts,
            # even '' or non-numeric (those just mean the default limit
            # of 10; the limit rules live in
            # psh/interactive/eof_policy.py).
            self.options['ignoreeof'] = (
                self.scope_manager.get_variable('IGNOREEOF') is not None)

        if name == 'POSIXLY_CORRECT':
            # sv_strict_posix (bash): the `posix` option tracks whether the
            # POSIXLY_CORRECT variable exists at all — any value counts, even
            # '' (assigning it enables posix mode, unsetting disables it). The
            # reverse coupling (the posix option binding/unbinding the variable)
            # lives in the option on_change observer
            # (_couple_posixly_correct_variable); the two settle in one bounce
            # (assigning finds the variable already present, so the observer
            # leaves the value alone rather than clobbering it with "y").
            self.options['posix'] = (
                self.scope_manager.get_variable('POSIXLY_CORRECT') is not None)

        if name in self._LOCALE_VARS:
            # bash treats LC_ALL/LC_CTYPE/LC_COLLATE/LANG as reactive special
            # variables: assigning, unsetting, or laying one over a command
            # (``LC_ALL=C cmd``) immediately re-resolves the effective locale.
            # This observer fires on all of those — including temp-env setup AND
            # its scope-pop teardown — so the locale tracks live state both into
            # and out of a prefixed command (Stage 4).
            self.locale.reinit(self._locale_env_snapshot())

    #: The four variables the effective locale is resolved from; a write/unset
    #: of any of them re-derives the locale profile (:meth:`_sync_exported_variable`).
    _LOCALE_VARS = frozenset(('LC_ALL', 'LC_CTYPE', 'LC_COLLATE', 'LANG'))

    #: PEP 538 rewrites ``os.environ['LC_CTYPE']`` to one of these when it
    #: coerces the C locale (``sys.flags.utf8_mode`` is then 1, which a
    #: genuinely user-set value leaves 0 — the discriminator).
    _PEP538_COERCION_TARGETS = frozenset(('C.UTF-8', 'C.UTF8', 'UTF-8'))

    def _strip_coerced_lc_ctype(self) -> None:
        """Undo PEP 538's C-locale coercion so psh presents bash's locale view.

        On CPython 3.7+ a shell started under an effectively-C environment (bare,
        or ``LANG=C`` with no ``LC_ALL``/``LC_CTYPE``) has
        ``os.environ['LC_CTYPE']`` silently rewritten to a UTF-8 target *before*
        psh runs, and ``sys.flags.utf8_mode`` set. bash never sees that phantom:
        under the same environment it uses the C locale, shows an empty
        ``$LC_CTYPE``, and passes no ``LC_CTYPE`` to children. Dropping the
        phantom from the inherited environment here (before it is imported as a
        shell variable) makes all three match bash. A genuine ``LC_CTYPE`` the
        user set is preserved: coercion is the only thing that pairs
        ``utf8_mode`` with a coercion-target value, so a real ``en_US.UTF-8``
        (utf8_mode 0) or any non-target value is untouched. The narrow residual —
        a user who both sets ``LC_CTYPE=C.UTF-8`` and forces UTF-8 mode
        (``PYTHONUTF8``/``-X utf8``) — is a documented corner (a Python runtime
        knob, not a shell path; see docs/user_guide/17_differences_from_bash.md)."""
        if not sys.flags.utf8_mode:
            return
        val = self.env.get('LC_CTYPE')
        if val is not None and val.upper() in self._PEP538_COERCION_TARGETS:
            del self.env['LC_CTYPE']

    def _locale_env_snapshot(self) -> Dict[str, str]:
        """The current values of the locale variables as bash resolves the
        effective locale from — command temp-env overlay shadowing the shell
        variable (exported OR not), via ``get_variable`` (v0.679 lookup-consults).
        LC_*/LANG are valid identifiers, so an inherited one is already imported
        as a variable and the opaque ``_env_base`` never holds them; a stripped
        PEP 538 phantom is simply absent. Feeds :meth:`LocaleService.reinit`."""
        snap: Dict[str, str] = {}
        for name in self._LOCALE_VARS:
            val = self.scope_manager.get_variable(name)
            if val is not None:
                snap[name] = val
        return snap

    # bash set -o names psh does NOT implement (real bash options with no psh
    # analogue). At SHELLOPTS import they are silently skipped — NOT warned — so
    # a psh child of a bash parent (whose exported SHELLOPTS routinely carries
    # interactive-comments) does not spew startup warnings. No spelling-alias
    # table is needed: `hashall` is psh's native name since #34, so it imports
    # directly and a stale `hashcmds` warns like any unknown name, matching bash.
    _BASH_ONLY_SET_O = frozenset({
        'interactive-comments', 'keyword', 'onecmd', 'physical', 'privileged',
    })

    def _import_option_reflection_from_env(self) -> None:
        """Consume inherited SHELLOPTS/BASHOPTS at startup (bash).

        Each valid option named in the colon-separated list is ENABLED before
        any startup file or command runs, and the variable is marked exported
        (bash exports SHELLOPTS/BASHOPTS only when they arrived via the
        environment). An unknown SHELLOPTS name warns like bash's
        "line 0: NAME: invalid option name"; an unknown BASHOPTS name is
        silently ignored (probe-verified bash 5.2).
        """
        for env_name, table in (('SHELLOPTS', SET_O_OPTION_NAMES),
                                ('BASHOPTS', SHOPT_OPTION_NAMES)):
            raw = self.env.get(env_name)
            if raw is None:
                continue
            # bash iterates the value with extract_colon_unit, so empty
            # units (adjacent/leading/trailing colons) reach the unknown-name
            # branch and WARN for SHELLOPTS (": invalid option name") while
            # BASHOPTS' unknown-silent rule swallows them (v0.674 fixlet F2).
            for name in _colon_units(raw):
                if name in table:
                    if name in ('vi', 'emacs'):
                        # Keep edit_mode coupled exactly like `set -o vi`.
                        self.edit_mode = name
                        self.options['vi'] = (name == 'vi')
                        self.options['emacs'] = (name == 'emacs')
                    elif name == 'ignoreeof':
                        # `set -o ignoreeof` binds IGNOREEOF=10; mirror it.
                        self.scope_manager.set_variable('IGNOREEOF', '10')
                        self.options['ignoreeof'] = True
                    else:
                        self.options[name] = True
                elif env_name == 'SHELLOPTS' and name not in self._BASH_ONLY_SET_O:
                    # bash prefixes this env-import diagnostic `<$0>: line 0:`
                    # — a startup sentinel (LINENO 0, no command has run) using
                    # argv0 even in script mode, so NOT error_location_prefix()
                    # (which is script_name + the running line). Match its shape.
                    print(f"psh: line 0: {name}: invalid option name",
                          file=self.stderr)
            # Exported because it arrived via the environment; recorded on the
            # special's persistent attribute overlay (the value itself stays
            # computed). The env entry still holds the RAW inherited string at
            # this point — the computed value needs the Shell wired
            # (set_shell), so Shell.__init__ calls
            # refresh_option_reflection_env() right after wiring.
            self.scope_manager.apply_attribute(env_name, VarAttributes.EXPORT)

    def refresh_option_reflection_env(self) -> None:
        """Re-derive the SHELLOPTS/BASHOPTS environment entries.

        An EXPORTED one materializes its current computed value (bash keeps
        the exported entry tracking every option change); an unexported one
        stays absent. Called by the options on_change observer and once by
        Shell.__init__ after the scope manager's shell is wired.
        """
        self._materialize_env_name('SHELLOPTS')
        self._materialize_env_name('BASHOPTS')

    def _refresh_option_reflection_env(self, name: str) -> None:
        # ShellOptions.on_change observer: any option write may change the
        # computed SHELLOPTS/BASHOPTS values.
        self.refresh_option_reflection_env()
        if name == 'posix':
            self._couple_posixly_correct_variable()

    def _couple_posixly_correct_variable(self) -> None:
        """Keep POSIXLY_CORRECT in step with the posix option (bash
        set_posix_mode / SET_INT_VAR of posixly_correct).

        Enabling posix binds POSIXLY_CORRECT to ``y`` — but only when the
        variable is not already set, so an inherited or user-supplied value is
        preserved (bash: ``POSIXLY_CORRECT=custom; set -o posix`` keeps
        ``custom``). The binding is NOT exported (bash: ``set -o posix`` leaves
        it unexported). Disabling posix unsets the variable. The reverse
        coupling (the variable's existence driving the option) lives in
        :meth:`_sync_exported_variable`; setting/unsetting the variable here
        re-enters that observer, which finds the option already in the target
        state and stops — one bounce, no clobber.
        """
        posix_on = bool(self.options.get('posix', False))
        var = self.scope_manager.get_variable('POSIXLY_CORRECT')
        # A user-made-readonly POSIXLY_CORRECT is pathological; bash's internal
        # bind/unbind of it is silent (`set +o posix` prints nothing even when
        # the variable is readonly). Match that quiet best-effort rather than
        # surfacing a "readonly variable" diagnostic the plain option toggle
        # never produced before this coupling existed.
        try:
            if posix_on and var is None:
                self.scope_manager.set_variable(
                    'POSIXLY_CORRECT', 'y', local=False)
            elif not posix_on and var is not None:
                self.scope_manager.unset_variable('POSIXLY_CORRECT')
        except ReadonlyVariableError:
            pass

    def apply_command_env(self, assignments: Dict[str, str]) -> None:
        """Compose a command-local temporary-environment overlay.

        Used by the SEED path of a ``VAR=x cmd`` prefix (a dynamic special, an
        array-object append, or a nameref-to-element — the cases that bind a real
        shell variable): it records the LITERAL string each name contributes to
        *this command's* process environment and materializes it (the overlay
        wins over the exported-variable value, so ``RANDOM=5 cmd`` passes ``5``
        and an array passes its element-0 view). Plain scalar prefix vars go into
        ``ScopeManager.command_temp_env`` instead and reach the env through the
        observer + ``find_exported_instance`` — no overlay entry. Paired with
        :meth:`restore_command_env`; env is only ever written through the one
        materialization path (appraisal H3)."""
        for name, value in assignments.items():
            self._env_overlay[name] = value
            self._materialize_env_name(name)

    def restore_command_env(self, names: Iterable[str]) -> None:
        """Drop a command's temp-env overlay entries and re-materialize each
        name from the authoritative source (exported variable / opaque base /
        absent). The caller restores the shell VARIABLES separately; this only
        tears down the env overlay.
        """
        for name in names:
            self._env_overlay.pop(name, None)
            self._materialize_env_name(name)

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

