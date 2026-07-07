"""Positional parameter builtins (shift, getopts)."""

from typing import TYPE_CHECKING, List

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class ShiftBuiltin(Builtin):
    """Shift positional parameters."""

    @property
    def name(self) -> str:
        return "shift"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Shift positional parameters to the left by n positions."""
        # Default shift count is 1
        n = 1

        # Parse optional argument
        if len(args) > 1:
            try:
                n = int(args[1])
            except ValueError:
                self.error("numeric argument required", shell)
                return 1

        # Validate shift count
        if n < 0:
            self.error("shift count must be non-negative", shell)
            return 1

        # Check if we have enough parameters to shift
        param_count = len(shell.state.positional_params)
        if n > param_count:
            # POSIX: return failure if n > $#
            return 1

        # Perform the shift
        shell.state.positional_params = shell.state.positional_params[n:]

        return 0

    @property
    def synopsis(self) -> str:
        return "shift [n]"

    @property
    def description(self) -> str:
        return "Shift positional parameters"

    @property
    def help(self) -> str:
        return """shift: shift [n]
    Shift positional parameters.

    Rename the positional parameters $N+1,$N+2 ... to $1,$2 ...  If N is
    not given, it is assumed to be 1.

    Exit Status:
    Returns success unless N is negative or greater than $#."""


@builtin
class GetoptsBuiltin(Builtin):
    """Parse option arguments."""

    @property
    def name(self) -> str:
        return "getopts"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Parse positional parameters as options."""
        # Validate arguments
        if len(args) < 3:
            self.error("usage: getopts optstring name [arg ...]", shell)
            return 2

        optstring = args[1]
        varname = args[2]

        # Determine if we're in silent error reporting mode
        silent_mode = optstring.startswith(':')
        if silent_mode:
            optstring = optstring[1:]

        # Get OPTIND (1-based index of next argument to process)
        try:
            optind = int(shell.state.get_variable('OPTIND', '1'))
        except (ValueError, TypeError):
            optind = 1

        # Get OPTERR (controls error message printing)
        try:
            opterr = int(shell.state.get_variable('OPTERR', '1'))
        except (ValueError, TypeError):
            opterr = 1

        # Determine which arguments to parse. NEVER mutate the positional
        # parameters: the old code rewrote argv[i] to track cluster progress,
        # which corrupted $1 (`set -- -abc; getopts ab o` left $1 as -bc).
        # Take a copy and track the within-cluster character position
        # out-of-band on shell.state, the way bash's internal cursor does.
        if len(args) > 3:
            argv = list(args[3:])
        else:
            argv = list(shell.state.positional_params)

        arg_index = optind - 1  # 0-based index of the current arg

        # Within-arg character cursor (1 = first char after the leading '-'),
        # from the typed GetoptsState. It is preserved ONLY while the scan
        # continues on the SAME argument source at the SAME OPTIND and the
        # script has not reassigned OPTIND since getopts last wrote it; any of
        # those changing restarts at 1 (bash). This is what stops a shorter
        # next word from overrunning the stale offset (the old "string index
        # out of range" crash) and makes a manual `OPTIND=1` restart the scan.
        source = tuple(argv)
        gs = shell.state.getopts_state
        sp = gs.char_offset if gs.cursor_valid_for(source, optind) else 1

        def advance(new_optind: int, new_sp: int) -> None:
            # The OPTIND write bumps getopts_state.optind_writes (observer);
            # gs.advance then records that as expected_writes, so only a LATER
            # script OPTIND assignment invalidates the cursor.
            shell.state.set_variable('OPTIND', str(new_optind))
            gs.advance(source, new_optind, new_sp)

        # Check if we've processed all arguments
        if arg_index >= len(argv):
            shell.state.set_variable(varname, '?')
            return 1

        current_arg = argv[arg_index]

        # Not an option (or a lone '-') — done.
        if not current_arg.startswith('-') or current_arg == '-':
            shell.state.set_variable(varname, '?')
            return 1

        # Handle -- (end of options)
        if current_arg == '--':
            advance(arg_index + 2, 1)
            shell.state.set_variable(varname, '?')
            return 1

        opt_char = current_arg[sp]
        # More option chars remain in THIS arg after the current one?
        more_in_cluster = (sp + 1) < len(current_arg)

        # Check if this option is in optstring
        opt_pos = optstring.find(opt_char)

        if opt_pos == -1:
            # Invalid option. Advance past this char — within the cluster if
            # more remain, else to the next arg. Silent mode records the bad
            # char in OPTARG; non-silent prints an error and unsets OPTARG.
            if more_in_cluster:
                advance(optind, sp + 1)
            else:
                advance(arg_index + 2, 1)
            shell.state.set_variable(varname, '?')
            if silent_mode:
                shell.state.set_variable('OPTARG', opt_char)
            else:
                if opterr:
                    self.write_error_line(f"getopts: illegal option -- {opt_char}", shell)
                shell.state.scope_manager.unset_variable('OPTARG')
            return 0

        # Check if option requires an argument
        requires_arg = opt_pos + 1 < len(optstring) and optstring[opt_pos + 1] == ':'

        if requires_arg:
            if more_in_cluster:
                # Argument is the rest of this arg (e.g. -dVALUE).
                arg_value = current_arg[sp + 1:]
                advance(arg_index + 2, 1)
            elif arg_index + 1 < len(argv):
                # Argument is the next argv element.
                arg_value = argv[arg_index + 1]
                advance(arg_index + 3, 1)
            else:
                # Missing required argument: still advance past the option.
                advance(arg_index + 2, 1)
                if silent_mode:
                    shell.state.set_variable(varname, ':')
                    shell.state.set_variable('OPTARG', opt_char)
                else:
                    if opterr:
                        self.write_error_line(f"getopts: option requires an argument -- {opt_char}", shell)
                    shell.state.set_variable(varname, '?')
                    shell.state.scope_manager.unset_variable('OPTARG')
                return 0
            shell.state.set_variable('OPTARG', arg_value)
        else:
            # Option without an argument: advance the cursor within/past the arg.
            if more_in_cluster:
                advance(optind, sp + 1)
            else:
                advance(arg_index + 2, 1)
            shell.state.scope_manager.unset_variable('OPTARG')

        shell.state.set_variable(varname, opt_char)
        return 0

    @property
    def synopsis(self) -> str:
        return "getopts optstring name [arg ...]"

    @property
    def description(self) -> str:
        return "Parse option arguments"

    @property
    def help(self) -> str:
        return """getopts: getopts optstring name [arg ...]
    Parse option arguments.

    Getopts is used by shell procedures to parse positional parameters
    as options.

    OPTSTRING contains the option letters to be recognized; if a letter
    is followed by a colon, the option is expected to have an argument,
    which should be separated from it by white space.

    Each time it is invoked, getopts will place the next option in the
    shell variable $name, initializing name if it does not exist, and
    the index of the next argument to be processed into the shell
    variable OPTIND.  OPTIND is initialized to 1 each time the shell or
    a shell script is invoked.  When an option requires an argument,
    getopts places that argument into the shell variable OPTARG.

    getopts reports errors in one of two ways.  If the first character
    of OPTSTRING is a colon, getopts uses silent error reporting.  In
    this mode, no error messages are printed.  If an invalid option is
    seen, getopts places the option character found into OPTARG.  If a
    required argument is not found, getopts places a ':' into NAME and
    sets OPTARG to the option character found.  If getopts is not in
    silent mode, and an invalid option is seen, getopts places '?' into
    NAME and unsets OPTARG.  If a required argument is not found, a '?'
    is placed in NAME, OPTARG is unset, and a diagnostic message is
    printed.

    If the shell variable OPTERR has the value 0, getopts disables the
    printing of error messages, even if the first character of
    OPTSTRING is not a colon.  OPTERR has the value 1 by default.

    Getopts normally parses the positional parameters, but if arguments
    are supplied as ARG values, they are parsed instead.

    Exit Status:
    Returns success if an option is found; fails if the end of options is
    encountered or an error occurs."""
