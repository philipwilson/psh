"""Shell builtins package.

Modules:
    aliases         - alias, unalias
    base            - Builtin abstract base class
    command_builtin - command
    core            - exit, :, true, false, exec
    debug_control   - debug-related commands
    directory_stack - pushd, popd, dirs
    disown          - disown
    environment     - export, set, unset
    eval_command    - eval
    function_support - declare, typeset, readonly, return; FunctionReturn exception
    help_command    - help
    io              - echo, printf, pwd
    job_control     - jobs, fg, bg, wait
    kill_command    - kill
    navigation      - cd
    parse_tree      - parse-tree visualization
    parser_control  - parser control commands
    parser_experiment - parser-select; PARSERS dict
    positional      - shift, getopts
    print_builtin   - print (zsh-compatible)
    read_builtin    - read
    mapfile_builtin - mapfile, readarray
    registry        - BuiltinRegistry and @builtin decorator
    shell_options   - shopt
    shell_state     - history, version, local
    signal_handling - trap
    source_command  - source, .
    test_command    - test, [
    type_builtin    - type
"""

# Import all builtin modules to trigger registration
from . import (
    aliases,
    command_builtin,
    core,
    debug_control,
    directory_stack,
    disown,
    environment,
    eval_command,
    function_support,
    help_command,
    io,
    job_control,
    kill_command,
    mapfile_builtin,
    navigation,
    parse_tree,
    parser_control,
    parser_experiment,
    positional,
    print_builtin,
    read_builtin,
    shell_options,
    shell_state,
    signal_handling,
    source_command,
    test_command,
    type_builtin,
)
from .base import Builtin
from .function_support import FunctionReturn
from .parser_experiment import PARSERS
from .registry import builtin, registry

__all__ = ['registry', 'builtin', 'Builtin', 'FunctionReturn', 'PARSERS']
