#!/usr/bin/env python3
"""Main entry point for psh when run as a module."""

import sys
from typing import Dict, List, Tuple, cast

from .scripting.visitor_modes import (
    handle_visitor_mode_for_command,
    handle_visitor_mode_for_content,
    handle_visitor_mode_for_script,
)
from .shell import Shell

# Flags that take no value: flag → settings applied when present.
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

# POSIX short options that set a shell option (bash: -e -u -x -v -n -f -C).
# Each maps to its long name via the option registry (the single source of
# truth); a cluster like -eux enables all three. -s (stdin) and -i
# (interactive) are handled separately as they are not shell options.
_SHORT_SET_OPTIONS = frozenset("euxvnfC")

HELP_TEXT = """Usage: psh [options] [script [args...]]
       psh [options] -c command [args...]

Python Shell (psh) - An educational Unix shell implementation

Options:
  -c command       Execute command and exit
  -s               Read commands from stdin; operands become positional params
  -i               Force interactive mode (load rc, set $- 'i' flag)
  -e -u -x -v      Set shell options (errexit, nounset, xtrace, verbose)
  -n -f -C         Set shell options (noexec, noglob, noclobber; -eux clusters)
  --               End of options; remaining arguments are operands
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


def _resolve_long_option(name: str) -> "str | None":
    """Resolve a ``-o NAME`` / ``+o NAME`` token to its canonical option name.

    Returns the registered option name, or ``None`` if NAME is not a
    user-settable option.  Mirrors the ``set -o`` check: any registered
    non-INTERNAL option name is accepted (psh's ``set -o`` is a deliberate
    superset of bash's set/shopt split), normalizing ``_`` vs ``-``.
    """
    from .core.option_registry import OPTION_REGISTRY, OptionCategory
    for candidate in (name, name.replace('-', '_'), name.replace('_', '-')):
        spec = OPTION_REGISTRY.get(candidate)
        if spec is not None and spec.category is not OptionCategory.INTERNAL:
            return candidate
    return None


def _value_option(argv: List[str], i: int, name: str) -> Tuple[str, int]:
    """Read the value of ``name VALUE`` or ``name=VALUE`` at position *i*.

    Returns (value, next_index).  Exits with status 2 if the
    space-separated form is missing its argument.
    """
    if argv[i].startswith(name + "="):
        return argv[i][len(name) + 1:], i + 1
    if i + 1 < len(argv):
        return argv[i + 1], i + 2
    print(f"psh: {name} requires an argument", file=sys.stderr)
    sys.exit(2)


def parse_args(argv: List[str]) -> Tuple[Dict[str, object], List[str]]:
    """Parse psh's option flags from *argv*, left to right.

    Returns (options, operands).  Like bash, option parsing STOPS at the
    first non-option argument — the script name, or the command string
    after ``-c`` — so everything from there on belongs to the script
    untouched (``psh script.sh -i foo`` passes both args through as
    $1/$2).  ``--`` (or the historical lone ``-``) ends options
    explicitly; an unknown option in flag position exits with status 2.

    Both ``-`` and ``+`` short-option clusters are accepted: a leading
    ``-`` ENABLES each flag, a leading ``+`` DISABLES it (bash ``set +x``).
    ``-o NAME`` / ``+o NAME`` set a long option by name, and ``-c`` may be
    clustered (``-xc 'cmd'``). Each set-option is recorded as a
    ``(name, enable)`` pair so a later ``+x`` / ``-x`` overrides an earlier
    one (bash: last wins).
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
        "command_mode": False,
        "stdin_mode": False,
        "set_options": [],
        "help": False,
        "version": False,
    }

    from .core.option_registry import SHORT_TO_LONG

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--", "-"):
            i += 1
            break
        if not arg.startswith(("-", "+")):
            break
        if arg in _FLAG_TABLE:
            for key, value in _FLAG_TABLE[arg]:
                options[key] = value
            i += 1
        elif arg == "-c":
            options["command_mode"] = True
            i += 1
        elif arg in ("--help", "-h"):
            options["help"] = True
            i += 1
        elif arg in ("--version", "-V"):
            options["version"] = True
            i += 1
        elif arg == "--rcfile" or arg.startswith("--rcfile="):
            options["rcfile"], i = _value_option(argv, i, "--rcfile")
        elif arg == "--parser" or arg.startswith("--parser="):
            options["parser_type"], i = _value_option(argv, i, "--parser")
        elif not arg.startswith("--") and len(arg) > 1:
            # A short-option cluster: -e, -eux, -s, -xc, +x, -o NAME, ...
            # A leading '-' ENABLES each set-option, '+' DISABLES it (bash
            # `set +x`). Each char sets a shell option (bash -e/-u/-x/-v/
            # -n/-f/-C), or is -s (read stdin), -i (interactive), -c (a
            # command string follows), or -o/+o (a long option by NAME).
            enable = arg[0] == "-"
            sign = arg[0]
            j = 1
            while j < len(arg):
                ch = arg[j]
                if ch in _SHORT_SET_OPTIONS:
                    cast(List[Tuple[str, bool]], options["set_options"]).append(
                        (SHORT_TO_LONG[ch], enable))
                elif ch == "s":
                    options["stdin_mode"] = True
                elif ch == "i":
                    options["force_interactive"] = True
                elif ch == "c":
                    options["command_mode"] = True
                elif ch == "o":
                    # -o/+o NAME: NAME is the rest of this cluster if any
                    # (`-opipefail`), else the next argument (`-o pipefail`).
                    name = arg[j + 1:]
                    if name:
                        j = len(arg)  # remainder is the NAME, not more flags
                    elif i + 1 < len(argv):
                        name = argv[i + 1]
                        i += 1
                    else:
                        print(f"psh: {sign}o: option requires an argument",
                              file=sys.stderr)
                        sys.exit(2)
                    long_name = _resolve_long_option(name)
                    if long_name is None:
                        print(f"psh: {name}: invalid option name",
                              file=sys.stderr)
                        sys.exit(2)
                    cast(List[Tuple[str, bool]], options["set_options"]).append(
                        (long_name, enable))
                else:
                    print(f"psh: {sign}{ch}: invalid option", file=sys.stderr)
                    print("Try 'psh --help' for more information.",
                          file=sys.stderr)
                    sys.exit(2)
                j += 1
            i += 1
        else:
            print(f"psh: {arg}: invalid option", file=sys.stderr)
            print("Try 'psh --help' for more information.", file=sys.stderr)
            sys.exit(2)

    return options, argv[i:]


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


def _read_all_stdin() -> str:
    """Return all of stdin as text, tolerating non-UTF-8 bytes.

    Reads the raw bytes and decodes them with surrogateescape, mirroring
    FileInput's script treatment (psh/scripting/input_sources.py) so a binary
    or otherwise undecodable byte on stdin cannot crash psh with an uncaught
    UnicodeDecodeError — bash reads stdin bytes leniently (a stray byte simply
    becomes a "command not found"). Returns '' when stdin is unavailable
    (fd 0 closed at startup, where CPython sets sys.stdin to None).
    """
    stdin = sys.stdin
    if stdin is None or stdin.closed:
        return ""
    buffer = getattr(stdin, "buffer", None)
    if buffer is not None:
        return buffer.read().decode("utf-8", errors="surrogateescape")
    # A stream without a binary buffer (e.g. a StringIO installed by an
    # embedder) already yields str; read it directly.
    return stdin.read()


def _enable_byte_transparent_output() -> None:
    """Let surrogate-escaped bytes round-trip back out through stdout/stderr.

    psh decodes non-UTF-8 input (scripts, stdin, command substitution) with
    surrogateescape, so shell values can carry arbitrary bytes as lone
    surrogates. The default text streams encode with errors='strict', which
    raises on those surrogates (`x=$(printf '\\xff'); printf %s "$x"` would
    crash). Reconfiguring the streams to surrogateescape makes the parent-path
    builtin output boundary re-encode each surrogate to its original byte,
    matching bash's byte transparency and the forked-child fd-level writes.
    Only affects the standalone `python -m psh` entry point (not embedders,
    whose overridden streams are untouched)."""
    for name in ('stdout', 'stderr'):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure is None:
            continue
        try:
            reconfigure(errors='surrogateescape')
        except (OSError, ValueError):
            pass


def main():
    """Main entry point for psh command."""
    import atexit
    atexit.register(_neutralize_closed_std_streams)
    _enable_byte_transparent_output()
    opts, operands = parse_args(sys.argv[1:])

    # --version wins over --help regardless of order (bash does the same);
    # both exit before a Shell is constructed (no rc sourcing, no history).
    if opts["version"]:
        from .version import get_version_info
        print(get_version_info())
        sys.exit(0)
    if opts["help"]:
        print_help()
        sys.exit(0)

    # POSIX `sh -c command_string [name [args...]]`: the command string is the
    # first operand, the next is $0, and the rest are $1, $2, ...
    command_mode = bool(opts["command_mode"])
    stdin_mode = bool(opts["stdin_mode"])
    if command_mode and not operands:
        print("psh: -c: option requires an argument", file=sys.stderr)
        sys.exit(2)

    # The shell must know its run-mode at construction: bash sources ~/.pshrc,
    # loads history, and enables line editing only for an INTERACTIVE shell —
    # never for `-c` or a script file (_init_interactive decides this). With
    # -s the first operand is a POSITIONAL parameter, not a script name.
    init_script_name = (operands[0] if operands and not command_mode
                        and not stdin_mode else None)

    visitor_mode = any([opts["format_only"], opts["metrics_only"],
                        opts["security_only"], opts["lint_only"],
                        opts["validate_only"]])

    # opts is Dict[str, object] (its build loop assigns by dynamic key, so it
    # cannot be a TypedDict); convert each value to the concrete type Shell's
    # constructor declares.
    def _flag(key: str) -> bool:
        return bool(opts[key])

    def _opt_str(key: str) -> "str | None":
        value = opts[key]
        return None if value is None else str(value)

    shell = Shell(debug_ast=_flag("debug_ast"), debug_tokens=_flag("debug_tokens"),
                  debug_scopes=_flag("debug_scopes"),
                  debug_expansion=_flag("debug_expansion"),
                  debug_expansion_detail=_flag("debug_expansion_detail"),
                  debug_exec=_flag("debug_exec"), debug_exec_fork=_flag("debug_exec_fork"),
                  norc=_flag("norc"), rcfile=_opt_str("rcfile"),
                  validate_only=_flag("validate_only"),
                  format_only=_flag("format_only"), metrics_only=_flag("metrics_only"),
                  security_only=_flag("security_only"), lint_only=_flag("lint_only"),
                  ast_format=_opt_str("ast_format"),
                  force_interactive=_flag("force_interactive"),
                  script_name=init_script_name, command_mode=command_mode,
                  )

    # This process IS psh: install process-global signal handlers (trap
    # checking, SIGCHLD bookkeeping). In-process embedders/tests construct
    # Shell directly and never get handlers installed; the interactive loop
    # additionally re-runs setup and claims the foreground.
    shell.interactive_manager.signal_manager.setup_signal_handlers()

    # Apply POSIX short options set on the command line (-e/-u/-x/-v/-n/-f/-C)
    # BEFORE any input runs, so they govern the whole run and show up in $-.
    for long_name, value in cast(List[Tuple[str, bool]], opts["set_options"]):
        shell.state.options[long_name] = value

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

    if command_mode:
        # Execute command with -c flag (script mode)
        shell.state.is_script_mode = True
        shell.state.options['command_mode'] = True  # 'c' in $-
        # bash's `-c` is command mode, NOT stdin-reading mode: $- has 'c'
        # but not 's'. _init_interactive ran at construction (before this
        # flag was known), so clear stdin_mode now.
        shell.state.options['stdin_mode'] = False
        command = operands[0]
        # `-c '...' name a b` → $0=name, $1=a, $#=2 (bash).
        if len(operands) > 1:
            shell.state.script_name = operands[1]
            shell.state.positional_params = list(operands[2:])
        else:
            shell.state.positional_params = []

        # Handle visitor modes for -c commands
        if visitor_mode:
            exit_code = handle_visitor_mode_for_command(shell, command)
            sys.exit(exit_code)

        # Use StringInput with script mode to process line-by-line like bash -c
        from .scripting.input_sources import StringInput
        input_source = StringInput(command, "-c")
        exit_code = shell.script_manager.source_processor.execute_as_main(
            input_source, add_to_history=False)
        sys.exit(exit_code)
    elif operands and not stdin_mode:
        # Script file execution
        script_path = operands[0]
        script_args = operands[1:]

        # Handle visitor modes for script files
        if visitor_mode:
            exit_code = handle_visitor_mode_for_script(shell, script_path)
            sys.exit(exit_code)

        exit_code = shell.script_manager.run_script(script_path, script_args)
        sys.exit(exit_code)
    else:
        # No script operand (or -s): commands come from stdin. Under -s any
        # remaining operands are the positional parameters ($1, $2, ...); $0
        # stays the shell name (bash: `echo ... | bash -s a b` → $0=bash).
        if stdin_mode:
            shell.state.is_script_mode = True
            shell.state.options['stdin_mode'] = True  # 's' in $-
            shell.state.positional_params = list(operands)

        # Handle visitor modes for stdin: analysis modes NEVER execute their
        # input, so read ALL of stdin (piped input, or typed until EOF at a
        # TTY) and route it through the same chokepoint as -c and script
        # files. (This branch previously executed the piped script —
        # `cat script | psh --security` ran the very commands it was asked
        # to analyze.)
        if visitor_mode:
            script_content = _read_all_stdin()
            exit_code = handle_visitor_mode_for_content(
                shell, script_content, "<stdin>")
            sys.exit(exit_code)

        stdin = sys.stdin
        if stdin is not None and not stdin.closed and stdin.isatty():
            # Interactive REPL (TTY attached)
            shell.interactive_manager.run_interactive_loop()
        else:
            # Non-interactive: read all commands from stdin and execute as a
            # script. With -i the interactive flag is still set (rc loaded,
            # history loaded) but commands come from the pipe — no REPL.
            # This IS script execution (bash treats `cmds | bash` exactly
            # like `bash -s`): set is_script_mode so the non-interactive
            # abort policies (errexit exits the shell, set -u / ${x:?} /
            # bad substitution are fatal, exec-failure exits) apply to
            # piped input too. Signal handlers were already installed at
            # startup, so this flag does not change handler selection.
            # Under -i the shell stays interactive-family (bash -i piped
            # discards the failing line and continues — probe-verified).
            if not _flag("force_interactive"):
                shell.state.is_script_mode = True
            script_content = _read_all_stdin()
            if script_content.strip():
                from .scripting.input_sources import StringInput
                input_source = StringInput(script_content, "<stdin>")
                exit_code = shell.script_manager.source_processor.execute_as_main(
                    input_source, add_to_history=False)
                sys.exit(exit_code)
            sys.exit(0)


if __name__ == "__main__":
    main()
