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

        # Determine which arguments to parse
        if len(args) > 3:
            # Parse provided arguments
            argv = args[3:]
        else:
            # Parse positional parameters
            argv = shell.state.positional_params

        # Check if we've processed all arguments
        arg_index = optind - 1  # Convert to 0-based
        if arg_index >= len(argv):
            # No more arguments to process
            shell.state.set_variable(varname, '?')
            return 1

        # Get current argument
        current_arg = argv[arg_index]

        # Check if it's an option
        if not current_arg.startswith('-') or current_arg == '-':
            # Not an option, we're done
            shell.state.set_variable(varname, '?')
            return 1

        # Handle -- (end of options)
        if current_arg == '--':
            shell.state.set_variable('OPTIND', str(arg_index + 2))
            shell.state.set_variable(varname, '?')
            return 1

        # Get the option character(s) after the dash
        opt_chars = current_arg[1:]

        # Handle option character position within clustered options
        # OPTIND can have a subindex for clustered options (not implemented here for simplicity)
        # For now, we'll process one option at a time

        if len(opt_chars) > 1:
            # Clustered options like -abc
            # Process the first character and adjust for next call
            opt_char = opt_chars[0]
            # Reconstruct the argument with remaining options
            remaining = '-' + opt_chars[1:]
            argv[arg_index] = remaining
        else:
            # Single option
            opt_char = opt_chars[0]
            # Move to next argument for next call
            shell.state.set_variable('OPTIND', str(arg_index + 2))

        # Check if this option is in optstring
        opt_pos = optstring.find(opt_char)

        if opt_pos == -1:
            # Invalid option
            if not silent_mode and opterr:
                self.write_error_line(f"getopts: illegal option -- {opt_char}", shell)

            shell.state.set_variable(varname, '?')
            shell.state.set_variable('OPTARG', opt_char)
            return 0

        # Check if option requires an argument
        requires_arg = opt_pos + 1 < len(optstring) and optstring[opt_pos + 1] == ':'

        if requires_arg:
            # Option requires an argument
            if len(opt_chars) > 1:
                # Argument is the rest of the clustered options
                arg_value = opt_chars[1:]
                shell.state.set_variable('OPTIND', str(arg_index + 2))
            elif arg_index + 1 < len(argv):
                # Argument is the next argv element
                arg_value = argv[arg_index + 1]
                shell.state.set_variable('OPTIND', str(arg_index + 3))
            else:
                # Missing required argument
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
            # Option doesn't require an argument
            shell.state.scope_manager.unset_variable('OPTARG')

        # Set the variable to the option character
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
