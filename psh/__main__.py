#!/usr/bin/env python3
"""Main entry point for psh when run as a module.

The command line is interpreted in exactly ONE place —
``psh.invocation.parse_invocation`` — which returns a frozen
:class:`~psh.invocation.InvocationConfig` (campaign F1). ``main()`` renders
help/version/errors, constructs the Shell FROM the config (options, parser,
``$0``/positionals all installed before any input runs), runs the explicit
startup step (bare ``-o`` listings, history, rc file), and dispatches on the
config's source kind. No other code may read ``sys.argv`` (guarded by
tests/unit/tooling/test_invocation_argv_guard.py).
"""
import sys

from .invocation import InvocationError, SourceKind, parse_invocation
from .scripting.visitor_modes import (
    handle_visitor_mode_for_command,
    handle_visitor_mode_for_content,
    handle_visitor_mode_for_script,
)
from .shell import Shell
from .version import get_version_info

HELP_TEXT = """Usage: psh [options] [script [args...]]
       psh [options] -c command [args...]

Python Shell (psh) - An educational Unix shell implementation

Options:
  -c command       Execute command and exit
  -s               Read commands from stdin; operands become positional params
  -i               Force interactive mode (load rc, set $- 'i' flag); +i cancels
  -a -b -e -f -h -m Set shell options (allexport, notify, errexit, noglob,
  -n -u -v -x        hashall, monitor, noexec, nounset, verbose, xtrace)
  -B -C -E -H -T   Set shell options (braceexpand, noclobber, errtrace,
                     histexpand, functrace)
  +e +x +B ...     A leading '+' turns the option OFF (bash set +x); clusters
  -o NAME          Enable shell option NAME by name (like set -o NAME)
  +o NAME          Disable shell option NAME by name (like set +o NAME)
  -o / +o          Bare trailing -o/+o prints the option listing (like set -o)
  --               End of options; remaining arguments are operands
  --help           Show this help message and exit
  -V, --version    Show version information and exit
  --norc           Do not read ~/.pshrc on startup
  --posix          Enable POSIX mode at startup (like set -o posix)
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

    try:
        config = parse_invocation(sys.argv[1:])
    except InvocationError as exc:
        for line in exc.lines:
            print(line, file=sys.stderr)
        sys.exit(exc.status)

    # --version wins over --help regardless of order (bash does the same);
    # both exit before a Shell is constructed (no rc sourcing, no history).
    if config.print_version:
        print(get_version_info())
        sys.exit(0)
    if config.print_help:
        print_help()
        sys.exit(0)

    # The frozen config carries EVERYTHING the shell needs: source kind,
    # $0/positionals, ordered option transitions, parser, rc policy. The
    # constructor applies all of it; startup input runs only afterwards.
    shell = Shell(invocation=config)

    # This process IS psh: install process-global signal handlers (trap
    # checking, SIGCHLD bookkeeping). In-process embedders/tests construct
    # Shell directly and never get handlers installed; the interactive loop
    # additionally re-runs setup and claims the foreground.
    shell.interactive_manager.signal_manager.setup_signal_handlers()

    # Explicit startup step (never part of construction): bare -o/+o
    # listings, then history, then the rc file — all AFTER the full
    # invocation was applied, so the rc observes -u/--parser/positionals
    # (continuation finding A) and runs for every interactive-family shell,
    # including -ic and -i script.sh (#20 H17).
    shell.run_invocation_startup()

    visitor_mode = bool(config.analysis_modes)

    if config.source_kind is SourceKind.COMMAND:
        command = config.command
        assert command is not None

        # Handle visitor modes for -c commands
        if visitor_mode:
            sys.exit(handle_visitor_mode_for_command(shell, command))

        # Use StringInput with script mode to process line-by-line like bash -c
        from .scripting.input_sources import StringInput
        input_source = StringInput(command, "-c", split_lines=True)
        # bash never bang-expands the -c command string, even under -ic
        # (`bash -ic 'echo !!'` prints `!!` — probe B8).
        input_source.history_expansion_eligible = False
        exit_code = shell.script_manager.execute_as_main(
            input_source, add_to_history=False)
        sys.exit(exit_code)
    elif config.source_kind is SourceKind.SCRIPT:
        script_path = config.script_path
        assert script_path is not None

        # Handle visitor modes for script files
        if visitor_mode:
            sys.exit(handle_visitor_mode_for_script(shell, script_path))

        exit_code = shell.script_manager.run_script(
            script_path, list(config.positionals))
        sys.exit(exit_code)
    else:
        # SourceKind.STDIN: commands come from stdin. Under -s any operands
        # are already installed as the positional parameters ($1, $2, ...);
        # $0 stays the shell name (bash: `echo ... | bash -s a b` → $0=bash).

        # Handle visitor modes for stdin: analysis modes NEVER execute their
        # input, so read ALL of stdin (piped input, or typed until EOF at a
        # TTY) and route it through the same chokepoint as -c and script
        # files. (This branch previously executed the piped script —
        # `cat script | psh --security` ran the very commands it was asked
        # to analyze.)
        if visitor_mode:
            script_content = _read_all_stdin()
            # A script on stdin is a stream input: a dangling backslash at
            # EOF drops, exactly as the execution path treats it.
            sys.exit(handle_visitor_mode_for_content(
                shell, script_content, "<stdin>", drop_dangling_at_eof=True))

        stdin = sys.stdin
        if stdin is not None and not stdin.closed and stdin.isatty():
            # Interactive REPL (TTY attached)
            shell.interactive_manager.run_interactive_loop()
        else:
            # Non-interactive: commands come from stdin and execute as a
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
            if not config.interactive:
                shell.state.is_script_mode = True
            # Read fd 0 LAZILY — one command's lines at a time — so a `read`,
            # `cat`, or `mapfile` INSIDE the script consumes the SUBSEQUENT
            # stdin lines as data, sharing the one fd exactly as bash does.
            # (The previous slurp of all of fd 0 into a StringInput drained
            # it, so every in-script stdin consumer saw immediate EOF — the
            # scripting appraisal 2026-07-07 finding #1.) A closed/empty fd 0
            # simply yields no commands (exit 0). execute_as_main fires the
            # EXIT trap exactly once, including on empty input (no trap set,
            # so a no-op there).
            # An interactive-family shell records its commands in history
            # (bash: `history` under `-i -s` lists them); plain piped input
            # does not.
            from .scripting.input_sources import StdinInput
            stdin_source = StdinInput(fd=0, name="<stdin>")
            exit_code = shell.script_manager.execute_as_main(
                stdin_source, add_to_history=config.interactive)
            sys.exit(exit_code)


if __name__ == "__main__":
    main()
