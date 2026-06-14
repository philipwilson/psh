#!/usr/bin/env python3
"""Main entry point for psh when run as a module."""

import sys
from typing import Dict, List, Tuple

from .scripting.visitor_modes import (
    handle_visitor_mode_for_command,
    handle_visitor_mode_for_script,
)
from .shell import Shell

# Flags that take no value: flag → settings applied when present.
# Each flag is removed from the argument list at most once (matching the
# historical args.remove() behavior).
_FLAG_TABLE: Dict[str, List[Tuple[str, object]]] = {
    "--debug-ast": [("debug_ast", True)],
    "--debug-ast=pretty": [("debug_ast", True), ("ast_format", "pretty")],
    "--debug-ast=tree": [("debug_ast", True), ("ast_format", "tree")],
    "--debug-ast=dot": [("debug_ast", True), ("ast_format", "dot")],
    "--debug-ast=compact": [("debug_ast", True), ("ast_format", "compact")],
    "--debug-ast=sexp": [("debug_ast", True), ("ast_format", "sexp")],
    "--debug-tokens": [("debug_tokens", True)],
    "--debug-scopes": [("debug_scopes", True)],
    "--debug-expansion": [("debug_expansion", True)],
    # Detail/fork imply the basic flag
    "--debug-expansion-detail": [("debug_expansion_detail", True),
                                 ("debug_expansion", True)],
    "--debug-exec": [("debug_exec", True)],
    "--debug-exec-fork": [("debug_exec_fork", True), ("debug_exec", True)],
    "--validate": [("validate_only", True)],
    "--format": [("format_only", True)],
    "--metrics": [("metrics_only", True)],
    "--security": [("security_only", True)],
    "--lint": [("lint_only", True)],
    "-i": [("force_interactive", True)],
    "--force-interactive": [("force_interactive", True)],
    "--norc": [("norc", True)],
}

HELP_TEXT = """Usage: psh [options] [script [args...]]
       psh [options] -c command [args...]

Python Shell (psh) - An educational Unix shell implementation

Options:
  -c command       Execute command and exit
  -i               Force interactive mode (load rc, set $- 'i' flag)
  -h, --help       Show this help message and exit
  -V, --version    Show version information and exit
  --norc           Do not read ~/.pshrc on startup
  --rcfile FILE    Read FILE instead of ~/.pshrc
  --parser PARSER  Select parser: recursive_descent (rd, default), combinator (pc, educational)
  --force-interactive Same as -i
  --debug-ast      Print AST before execution (debugging)
  --debug-ast=FORMAT AST format: pretty, tree, compact, dot, sexp
  --debug-tokens   Print tokens before parsing (debugging)
  --debug-scopes   Print variable scope operations (debugging)
  --debug-expansion Print expansions as they occur (debugging)
  --debug-expansion-detail Print detailed expansion steps (debugging)
  --debug-exec     Print executor operations (debugging)
  --debug-exec-fork Print fork/exec details (debugging)
  --validate       Validate script without executing (check for errors)
  --format         Format script and print formatted version
  --metrics        Analyze script and print code metrics
  --security       Perform security analysis on script
  --lint           Perform linting analysis on script

Arguments:
  script           Script file to execute
  args             Arguments passed to script or command

Examples:
  psh                          # Start interactive shell
  psh script.sh arg1 arg2      # Execute script with arguments
  psh -c 'echo $1' hello       # Execute command with arguments
  source script.sh arg1        # Source script with arguments"""


def print_help() -> None:
    """Print the command-line usage text."""
    print(HELP_TEXT)


def _extract_value_option(args: List[str], name: str) -> Tuple[object, List[str]]:
    """Extract ``name VALUE`` or ``name=VALUE`` from args (first match).

    Returns (value_or_None, remaining_args).  Exits with status 2 if the
    space-separated form is missing its argument.
    """
    for i, arg in enumerate(args):
        if arg == name:
            if i + 1 < len(args):
                return args[i + 1], args[:i] + args[i + 2:]
            print(f"psh: {name} requires an argument", file=sys.stderr)
            sys.exit(2)
        elif arg.startswith(name + "="):
            return arg[len(name) + 1:], args[:i] + args[i + 1:]
    return None, args


def parse_args(argv: List[str]) -> Tuple[Dict[str, object], List[str]]:
    """Strip psh's own option flags out of *argv*.

    Returns (options, remaining_args).  Unknown arguments (the script
    name, -c and its command, --, ...) are left in remaining_args for
    main() to interpret positionally.
    """
    options: Dict[str, object] = {
        "debug_ast": False,
        "debug_tokens": False,
        "debug_scopes": False,
        "debug_expansion": False,
        "debug_expansion_detail": False,
        "debug_exec": False,
        "debug_exec_fork": False,
        "norc": False,
        "rcfile": None,
        "parser_type": None,
        "validate_only": False,
        "format_only": False,
        "metrics_only": False,
        "security_only": False,
        "lint_only": False,
        "force_interactive": False,
        "ast_format": None,
    }

    args = list(argv)
    for flag, settings in _FLAG_TABLE.items():
        if flag in args:
            for key, value in settings:
                options[key] = value
            args.remove(flag)

    options["rcfile"], args = _extract_value_option(args, "--rcfile")
    options["parser_type"], args = _extract_value_option(args, "--parser")

    return options, args


def _neutralize_closed_std_streams() -> None:
    """Stop CPython's shutdown flush from failing on a deliberately closed fd.

    A script may close fd 1/2 itself (`exec 1>&-`). At interpreter shutdown
    CPython flushes sys.stdout/sys.stderr; flushing a stream whose fd is gone
    raises, which both prints `Exception ignored while flushing sys.stdout` and
    makes the process exit 120 (a finalization failure) instead of the shell's
    real status. Pre-emptively flush here; if the fd is already gone, replace
    the stream with one writing to os.devnull so the finalizer flush is a no-op.
    Bash exits with the command's status and no such noise.
    """
    import os
    for name in ('stdout', 'stderr'):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            stream.flush()
        except (OSError, ValueError):
            try:
                setattr(sys, name, open(os.devnull, 'w'))
            except OSError:
                pass


def main():
    """Main entry point for psh command."""
    import atexit
    atexit.register(_neutralize_closed_std_streams)
    opts, args = parse_args(sys.argv[1:])

    # Update sys.argv to remove the flags
    sys.argv = [sys.argv[0]] + args

    visitor_mode = any([opts["format_only"], opts["metrics_only"],
                        opts["security_only"], opts["lint_only"],
                        opts["validate_only"]])

    shell = Shell(debug_ast=opts["debug_ast"], debug_tokens=opts["debug_tokens"],
                  debug_scopes=opts["debug_scopes"],
                  debug_expansion=opts["debug_expansion"],
                  debug_expansion_detail=opts["debug_expansion_detail"],
                  debug_exec=opts["debug_exec"], debug_exec_fork=opts["debug_exec_fork"],
                  norc=opts["norc"], rcfile=opts["rcfile"],
                  validate_only=opts["validate_only"],
                  format_only=opts["format_only"], metrics_only=opts["metrics_only"],
                  security_only=opts["security_only"], lint_only=opts["lint_only"],
                  ast_format=opts["ast_format"],
                  force_interactive=opts["force_interactive"]
                  )

    # This process IS psh: install process-global signal handlers (trap
    # checking, SIGCHLD bookkeeping). In-process embedders/tests construct
    # Shell directly and never get handlers installed; the interactive loop
    # additionally re-runs setup and claims the foreground.
    shell.interactive_manager.signal_manager.setup_signal_handlers()

    # Apply --parser selection
    if opts["parser_type"] is not None:
        from .builtins import PARSERS
        target = None
        for name, aliases in PARSERS.items():
            if opts["parser_type"] == name or opts["parser_type"] in aliases:
                target = name
                break
        if target is None:
            print(f"psh: unknown parser: {opts['parser_type']}", file=sys.stderr)
            print("Available parsers: recursive_descent (rd), combinator (pc)", file=sys.stderr)
            sys.exit(2)
        shell.active_parser = target

    if len(sys.argv) > 1:
        if sys.argv[1] == "-c" and len(sys.argv) > 2:
            # Execute command with -c flag (script mode)
            shell.state.is_script_mode = True
            shell.state.options['command_mode'] = True  # 'c' in $-
            # bash's `-c` is command mode, NOT stdin-reading mode: $- has 'c'
            # but not 's'. _init_interactive ran at construction (before this
            # flag was known), so clear stdin_mode now.
            shell.state.options['stdin_mode'] = False
            command = sys.argv[2]
            # Set positional parameters from remaining arguments
            shell.state.positional_params = list(sys.argv[3:])

            # Handle visitor modes for -c commands
            if visitor_mode:
                exit_code = handle_visitor_mode_for_command(shell, command)
                sys.exit(exit_code)

            # Use StringInput with script mode to process line-by-line like bash -c
            from .scripting.input_sources import StringInput
            input_source = StringInput(command, "-c")
            exit_code = shell.script_manager.source_processor.execute_from_source(
                input_source, add_to_history=False)
            shell.trap_manager.execute_exit_trap()
            sys.exit(exit_code)
        elif sys.argv[1] in ("--version", "-V"):
            # Show version
            from .version import get_version_info
            print(get_version_info())
            sys.exit(0)
        elif sys.argv[1] in ("--help", "-h"):
            print_help()
            sys.exit(0)
        elif sys.argv[1] == "--":
            # End of options marker
            if len(sys.argv) > 2:
                script_path = sys.argv[2]
                script_args = sys.argv[3:]
                exit_code = shell.script_manager.run_script(script_path, script_args)
                sys.exit(exit_code)
            else:
                # No script after --, start interactive mode
                shell.interactive_manager.run_interactive_loop()
        elif sys.argv[1].startswith("-"):
            # Unknown option
            print(f"psh: {sys.argv[1]}: invalid option", file=sys.stderr)
            print("Try 'psh --help' for more information.", file=sys.stderr)
            sys.exit(2)
        else:
            # Script file execution
            script_path = sys.argv[1]
            script_args = sys.argv[2:]

            # Handle visitor modes for script files
            if visitor_mode:
                exit_code = handle_visitor_mode_for_script(shell, script_path)
                sys.exit(exit_code)

            exit_code = shell.script_manager.run_script(script_path, script_args)
            sys.exit(exit_code)
    else:
        if sys.stdin.isatty():
            # Interactive REPL (TTY attached)
            shell.interactive_manager.run_interactive_loop()
        else:
            # Non-interactive: read all commands from stdin and execute as a
            # script. With -i the interactive flag is still set (rc loaded,
            # history loaded) but commands come from the pipe — no REPL.
            script_content = sys.stdin.read()
            if script_content.strip():
                from .scripting.input_sources import StringInput
                input_source = StringInput(script_content, "<stdin>")
                exit_code = shell.script_manager.source_processor.execute_from_source(
                    input_source, add_to_history=False)
                shell.trap_manager.execute_exit_trap()
                sys.exit(exit_code)
            sys.exit(0)


if __name__ == "__main__":
    main()
