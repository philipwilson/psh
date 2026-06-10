#!/usr/bin/env python3
"""Main entry point for psh when run as a module."""

import sys

from .shell import Shell


def main():
    """Main entry point for psh command."""
    # Check for debug flags first
    debug_ast = False
    debug_tokens = False
    debug_scopes = False
    debug_expansion = False
    debug_expansion_detail = False
    debug_exec = False
    debug_exec_fork = False
    norc = False
    rcfile = None
    parser_type = None
    validate_only = False
    format_only = False
    metrics_only = False
    security_only = False
    lint_only = False
    force_interactive = False
    # Visitor executor is now the only executor
    args = sys.argv[1:]

    # Extract debug flags
    ast_format = None
    if "--debug-ast" in args:
        debug_ast = True
        args.remove("--debug-ast")
    if "--debug-ast=pretty" in args:
        debug_ast = True
        ast_format = "pretty"
        args.remove("--debug-ast=pretty")
    if "--debug-ast=tree" in args:
        debug_ast = True
        ast_format = "tree"
        args.remove("--debug-ast=tree")
    if "--debug-ast=dot" in args:
        debug_ast = True
        ast_format = "dot"
        args.remove("--debug-ast=dot")
    if "--debug-ast=compact" in args:
        debug_ast = True
        ast_format = "compact"
        args.remove("--debug-ast=compact")
    if "--debug-ast=sexp" in args:
        debug_ast = True
        ast_format = "sexp"
        args.remove("--debug-ast=sexp")
    if "--debug-tokens" in args:
        debug_tokens = True
        args.remove("--debug-tokens")
    if "--debug-scopes" in args:
        debug_scopes = True
        args.remove("--debug-scopes")
    if "--debug-expansion" in args:
        debug_expansion = True
        args.remove("--debug-expansion")
    if "--debug-expansion-detail" in args:
        debug_expansion_detail = True
        debug_expansion = True  # Detail implies basic
        args.remove("--debug-expansion-detail")
    if "--debug-exec" in args:
        debug_exec = True
        args.remove("--debug-exec")
    if "--debug-exec-fork" in args:
        debug_exec_fork = True
        debug_exec = True  # Fork implies basic
        args.remove("--debug-exec-fork")

    # Extract validation flag
    if "--validate" in args:
        validate_only = True
        args.remove("--validate")

    # Extract visitor flags
    if "--format" in args:
        format_only = True
        args.remove("--format")
    if "--metrics" in args:
        metrics_only = True
        args.remove("--metrics")
    if "--security" in args:
        security_only = True
        args.remove("--security")
    if "--lint" in args:
        lint_only = True
        args.remove("--lint")

    # Extract force-interactive flag (both -i and --force-interactive)
    if "-i" in args:
        force_interactive = True
        args.remove("-i")
    if "--force-interactive" in args:
        force_interactive = True
        args.remove("--force-interactive")

    # Extract RC file flags
    if "--norc" in args:
        norc = True
        args.remove("--norc")

    # Handle --rcfile
    for i, arg in enumerate(args):
        if arg == "--rcfile":
            if i + 1 < len(args):
                rcfile = args[i + 1]
                args = args[:i] + args[i+2:]  # Remove both --rcfile and its argument
                break
            else:
                print("psh: --rcfile requires an argument", file=sys.stderr)
                sys.exit(2)
        elif arg.startswith("--rcfile="):
            rcfile = arg[9:]  # Remove "--rcfile=" prefix
            args.remove(arg)
            break

    # Handle --parser
    for i, arg in enumerate(args):
        if arg == "--parser":
            if i + 1 < len(args):
                parser_type = args[i + 1]
                args = args[:i] + args[i+2:]
                break
            else:
                print("psh: --parser requires an argument", file=sys.stderr)
                sys.exit(2)
        elif arg.startswith("--parser="):
            parser_type = arg[9:]  # Remove "--parser=" prefix
            args.remove(arg)
            break

    # Update sys.argv to remove the flags
    sys.argv = [sys.argv[0]] + args

    shell = Shell(debug_ast=debug_ast, debug_tokens=debug_tokens, debug_scopes=debug_scopes,
                  debug_expansion=debug_expansion, debug_expansion_detail=debug_expansion_detail,
                  debug_exec=debug_exec, debug_exec_fork=debug_exec_fork,
                  norc=norc, rcfile=rcfile, validate_only=validate_only,
                  format_only=format_only, metrics_only=metrics_only,
                  security_only=security_only, lint_only=lint_only,
                  ast_format=ast_format,
                  force_interactive=force_interactive
                  )

    # This process IS psh: install process-global signal handlers (trap
    # checking, SIGCHLD bookkeeping). In-process embedders/tests construct
    # Shell directly and never get handlers installed; the interactive loop
    # additionally re-runs setup and claims the foreground.
    shell.interactive_manager.signal_manager.setup_signal_handlers()

    # Apply --parser selection
    if parser_type is not None:
        from .builtins import PARSERS
        target = None
        for name, aliases in PARSERS.items():
            if parser_type == name or parser_type in aliases:
                target = name
                break
        if target is None:
            print(f"psh: unknown parser: {parser_type}", file=sys.stderr)
            print("Available parsers: recursive_descent (rd), combinator (pc)", file=sys.stderr)
            sys.exit(2)
        shell.active_parser = target

    if len(sys.argv) > 1:
        if sys.argv[1] == "-c" and len(sys.argv) > 2:
            # Execute command with -c flag (script mode)
            shell.state.is_script_mode = True
            shell.state.options['command_mode'] = True  # 'c' in $-
            command = sys.argv[2]
            # Set positional parameters from remaining arguments
            shell.state.positional_params = list(sys.argv[3:])

            # Handle visitor modes for -c commands
            if any([format_only, metrics_only, security_only, lint_only, validate_only]):
                exit_code = shell._handle_visitor_mode_for_command(command)
                sys.exit(exit_code)

            # Use StringInput with script mode to process line-by-line like bash -c
            from .input_sources import StringInput
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
            # Show help
            print("Usage: psh [options] [script [args...]]")
            print("       psh [options] -c command [args...]")
            print("\nPython Shell (psh) - An educational Unix shell implementation")
            print("\nOptions:")
            print("  -c command       Execute command and exit")
            print("  -i               Force interactive mode (load rc, set $- 'i' flag)")
            print("  -h, --help       Show this help message and exit")
            print("  -V, --version    Show version information and exit")
            print("  --norc           Do not read ~/.pshrc on startup")
            print("  --rcfile FILE    Read FILE instead of ~/.pshrc")
            print("  --parser PARSER  Select parser: recursive_descent (rd), combinator (pc)")
            print("  --force-interactive Same as -i")
            print("  --debug-ast      Print AST before execution (debugging)")
            print("  --debug-ast=FORMAT AST format: pretty, tree, compact, dot, sexp")
            print("  --debug-tokens   Print tokens before parsing (debugging)")
            print("  --debug-scopes   Print variable scope operations (debugging)")
            print("  --debug-expansion Print expansions as they occur (debugging)")
            print("  --debug-expansion-detail Print detailed expansion steps (debugging)")
            print("  --debug-exec     Print executor operations (debugging)")
            print("  --debug-exec-fork Print fork/exec details (debugging)")
            print("  --validate       Validate script without executing (check for errors)")
            print("  --format         Format script and print formatted version")
            print("  --metrics        Analyze script and print code metrics")
            print("  --security       Perform security analysis on script")
            print("  --lint           Perform linting analysis on script")
            print("\nArguments:")
            print("  script           Script file to execute")
            print("  args             Arguments passed to script or command")
            print("\nExamples:")
            print("  psh                          # Start interactive shell")
            print("  psh script.sh arg1 arg2      # Execute script with arguments")
            print("  psh -c 'echo $1' hello       # Execute command with arguments")
            print("  source script.sh arg1        # Source script with arguments")
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
            if any([format_only, metrics_only, security_only, lint_only, validate_only]):
                exit_code = shell._handle_visitor_mode_for_script(script_path)
                sys.exit(exit_code)

            exit_code = shell.script_manager.run_script(script_path, script_args)
            sys.exit(exit_code)
    else:
        if sys.stdin.isatty():
            # Interactive REPL (TTY attached)
            shell.interactive_manager.run_interactive_loop()
        elif force_interactive:
            # -i with piped stdin: interactive flag is set (rc loaded, history loaded)
            # but read commands from pipe, don't run REPL
            script_content = sys.stdin.read()
            if script_content.strip():
                from .input_sources import StringInput
                input_source = StringInput(script_content, "<stdin>")
                exit_code = shell.script_manager.source_processor.execute_from_source(
                    input_source, add_to_history=False)
                shell.trap_manager.execute_exit_trap()
                sys.exit(exit_code)
            sys.exit(0)
        else:
            # Non-interactive mode - read all commands from stdin and execute as a script
            script_content = sys.stdin.read()
            if script_content.strip():
                from .input_sources import StringInput
                input_source = StringInput(script_content, "<stdin>")
                exit_code = shell.script_manager.source_processor.execute_from_source(
                    input_source, add_to_history=False)
                shell.trap_manager.execute_exit_trap()
                sys.exit(exit_code)
            sys.exit(0)


if __name__ == "__main__":
    main()
