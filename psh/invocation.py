"""Invocation parsing: argv -> frozen :class:`InvocationConfig` (campaign F1).

``parse_invocation(argv)`` is the ONE place psh interprets its command line.
It is pure: no printing, no ``sys.exit``, no environment reads, no Shell —
invalid invocations raise a typed :class:`InvocationError` that the entry
point renders. Everything downstream (``__main__.main`` dispatch, ``Shell``
construction, the startup step) consumes the frozen config instead of
re-deriving invocation facts from argv, so startup input (rc file, history)
can only ever observe a FULLY configured invocation (continuation finding A:
the rc used to run before ``set -u``/``--parser``/positionals were applied).

Option parsing is bash's: left to right, stopping at the first non-option
operand; ``--`` (or the historical lone ``-``) ends options explicitly.

The short-option surface is REGISTRY-DERIVED (continuation medium 1): every
option in ``OPTION_REGISTRY`` with a ``short_flag`` is a valid invocation
option with both ``-`` (enable) and ``+`` (disable) signs — exactly the
letters bash's usage line advertises for ``set``. The invocation-only
letters live in one explicit table (``_INVOCATION_ONLY``) with their sign
semantics probed against bash 5.2 (tmp/boundary-ledgers/F1-probes/,
integrator-ratified 2026-07-18):

* ``i`` is sign-AWARE: ``bash -i +i -c 'echo $-'`` prints no ``i`` — the
  later ``+i`` cancels the interactive request.
* ``s`` and ``c`` are sign-BLIND: ``bash +s A B`` still collects ``A B`` as
  positionals and reads stdin, and ``bash +c 'echo hi'`` ENABLES command
  mode and prints ``hi`` (the ``+`` acts exactly like ``-``).
* ``-h`` is bash ``hashall`` (campaign decision) — help is ``--help`` only.
* a bare TRAILING ``-o``/``+o`` is not an error: bash prints the ``set -o`` /
  ``set +o`` listing (exit 0) and continues; recorded in
  ``option_listings`` for the startup step to render.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

from .builtins.parser_experiment import PARSERS
from .core.option_registry import OPTION_REGISTRY, SHORT_TO_LONG, OptionCategory


class SourceKind(Enum):
    """Where the shell's main program text comes from."""
    COMMAND = "command"   # -c: the command string operand
    SCRIPT = "script"     # a script-file operand
    STDIN = "stdin"       # standard input (default, or forced by -s)


class InvocationError(Exception):
    """An invalid invocation. Carries the diagnostic lines and exit status.

    Raised by :func:`parse_invocation` instead of printing/exiting so the
    parser stays pure; ``__main__.main`` renders ``lines`` to stderr and
    exits with ``status`` — before any Shell exists, so an invalid
    invocation can never run startup input (probe class A4).
    """

    def __init__(self, lines: Tuple[str, ...], status: int = 2) -> None:
        super().__init__(lines[0] if lines else "invalid invocation")
        self.lines = lines
        self.status = status


@dataclass(frozen=True)
class InvocationConfig:
    """The complete, validated result of parsing psh's command line.

    Frozen: startup consumes invocation facts; nothing may rewrite them
    after parsing (guarded by tests/unit/test_parse_invocation.py's
    frozen meta-test).
    """
    source_kind: SourceKind
    command: Optional[str] = None          # COMMAND: the -c string
    script_path: Optional[str] = None      # SCRIPT: the file operand
    forced_stdin: bool = False             # -s / +s present (sign-blind, bash)
    interactive: bool = False              # -i final state (sign-aware, bash)
    # Ordered (long-option-name, enable) pairs, applied left-to-right so a
    # later +x overrides an earlier -x (bash: last wins). Includes --debug-*
    # and --posix (all registry names).
    option_transitions: Tuple[Tuple[str, bool], ...] = ()
    # Bare trailing -o/+o listing requests, as their signs ('-' or '+').
    option_listings: Tuple[str, ...] = ()
    parser: Optional[str] = None           # canonical parser name, validated
    analysis_modes: Tuple[str, ...] = ()   # --validate/--format/... requested
    argv0: str = "psh"                     # $0
    positionals: Tuple[str, ...] = ()      # $1, $2, ...
    norc: bool = False
    rcfile: Optional[str] = None
    ast_format: Optional[str] = None
    print_help: bool = False
    print_version: bool = False


#: Analysis (visitor) modes, in the order the CLI flags declare them.
ANALYSIS_MODES = ("validate", "format", "metrics", "security", "lint")

ANALYSIS_MODE_FLAGS = {f"--{mode}": mode for mode in ANALYSIS_MODES}

# --debug-* flags: option transitions (registry names) + optional AST format.
_DEBUG_FLAGS = {
    "--debug-ast": (("debug-ast",), None),
    "--debug-ast=pretty": (("debug-ast",), "pretty"),
    "--debug-ast=tree": (("debug-ast",), "tree"),
    "--debug-ast=dot": (("debug-ast",), "dot"),
    "--debug-ast=compact": (("debug-ast",), "compact"),
    "--debug-ast=sexp": (("debug-ast",), "sexp"),
    "--debug-tokens": (("debug-tokens",), None),
    "--debug-scopes": (("debug-scopes",), None),
    "--debug-expansion": (("debug-expansion",), None),
    # Detail/fork imply the basic flag.
    "--debug-expansion-detail": (("debug-expansion-detail", "debug-expansion"), None),
    "--debug-exec": (("debug-exec",), None),
    "--debug-exec-fork": (("debug-exec-fork", "debug-exec"), None),
}

# Invocation-only short options (NOT shell options; see module docstring for
# the probed sign semantics). 'o' is handled inline (it takes a name).
_INVOCATION_ONLY = frozenset("sic")


def resolve_parser_name(requested: str) -> Optional[str]:
    """Canonical parser name for *requested* (name or alias), or None.

    The parser table (``PARSERS`` in ``builtins/parser_experiment.py``) is
    the same one the ``parser-select`` builtin uses — one source of truth
    for which parsers exist.
    """
    for name, aliases in PARSERS.items():
        if requested == name or requested in aliases:
            return name
    return None


def _resolve_long_option(name: str) -> Optional[str]:
    """Resolve a ``-o NAME`` / ``+o NAME`` token to its canonical option name.

    Returns the registered option name, or ``None`` if NAME is not a
    user-settable option.  Mirrors the ``set -o`` check: any registered
    non-INTERNAL option name is accepted (psh's ``set -o`` is a deliberate
    superset of bash's set/shopt split), normalizing ``_`` vs ``-``.
    """
    for candidate in (name, name.replace('-', '_'), name.replace('_', '-')):
        spec = OPTION_REGISTRY.get(candidate)
        if spec is not None and spec.category is not OptionCategory.INTERNAL:
            return candidate
    return None


def _invalid_option(token: str) -> InvocationError:
    return InvocationError((
        f"psh: {token}: invalid option",
        "Try 'psh --help' for more information.",
    ))


@dataclass
class _ParseState:
    """Mutable accumulator while scanning argv (internal to this module)."""
    transitions: List[Tuple[str, bool]] = field(default_factory=list)
    listings: List[str] = field(default_factory=list)
    analysis: List[str] = field(default_factory=list)
    interactive: bool = False
    forced_stdin: bool = False
    command_mode: bool = False
    norc: bool = False
    rcfile: Optional[str] = None
    parser_request: Optional[str] = None
    ast_format: Optional[str] = None
    print_help: bool = False
    print_version: bool = False


def _value_option(argv: List[str], i: int, name: str) -> Tuple[str, int]:
    """Read the value of ``name VALUE`` or ``name=VALUE`` at position *i*.

    Returns (value, next_index).  Raises InvocationError (status 2) if the
    space-separated form is missing its argument.
    """
    if argv[i].startswith(name + "="):
        return argv[i][len(name) + 1:], i + 1
    if i + 1 < len(argv):
        return argv[i + 1], i + 2
    raise InvocationError((f"psh: {name} requires an argument",))


def _parse_cluster(argv: List[str], i: int, st: _ParseState) -> int:
    """Parse one ``-xyz`` / ``+xyz`` short-option cluster at ``argv[i]``.

    Returns the next index. A leading ``-`` ENABLES each set-option, ``+``
    DISABLES it; the invocation-only letters follow the probed bash sign
    semantics (module docstring). ``o`` consumes the cluster remainder or
    the next argument as a long option name; a bare trailing ``o`` records
    a listing request instead (bash prints the table and continues).
    """
    arg = argv[i]
    enable = arg[0] == "-"
    sign = arg[0]
    j = 1
    while j < len(arg):
        ch = arg[j]
        if ch in SHORT_TO_LONG:
            st.transitions.append((SHORT_TO_LONG[ch], enable))
        elif ch == "s":
            # Sign-blind (bash: `+s A B` collects positionals and reads
            # stdin exactly like -s; probes E2/C10).
            st.forced_stdin = True
        elif ch == "i":
            # Sign-aware (bash: `-i +i` cancels; probes C8/C9).
            st.interactive = enable
        elif ch == "c":
            # Sign-blind (bash: `+c 'echo hi'` runs the command string;
            # probes C11/C12).
            st.command_mode = True
        elif ch == "o":
            # -o/+o NAME: NAME is the rest of this cluster if any
            # (`-opipefail`), else the next argument (`-o pipefail`).
            # With NEITHER, bash prints the set -o / set +o listing and
            # continues (probes E3/E3b) — record the request.
            name = arg[j + 1:]
            if name:
                j = len(arg)  # remainder is the NAME, not more flags
            elif i + 1 < len(argv):
                name = argv[i + 1]
                i += 1
            else:
                st.listings.append(sign)
                return i + 1
            long_name = _resolve_long_option(name)
            if long_name is None:
                raise InvocationError((f"psh: {name}: invalid option name",))
            st.transitions.append((long_name, enable))
        else:
            raise _invalid_option(f"{sign}{ch}")
        j += 1
    return i + 1


def parse_invocation(argv: List[str]) -> InvocationConfig:
    """Parse psh's command line into a frozen :class:`InvocationConfig`.

    Pure: raises :class:`InvocationError` for every invalid invocation
    (unknown option, missing value, invalid parser/option name, missing -c
    operand) — it never prints or exits, and no Shell exists yet, so
    validation failures structurally precede all startup input.
    """
    st = _ParseState()

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--", "-"):
            i += 1
            break
        if not arg.startswith(("-", "+")):
            break
        if arg in _DEBUG_FLAGS:
            names, ast_format = _DEBUG_FLAGS[arg]
            st.transitions.extend((name, True) for name in names)
            if ast_format is not None:
                st.ast_format = ast_format
            i += 1
        elif arg == "--force-interactive":
            # Long alias for -i (which parses via the cluster branch); the
            # long form is always an ENABLE.
            st.interactive = True
            i += 1
        elif arg == "--norc":
            st.norc = True
            i += 1
        elif arg == "--help":
            st.print_help = True
            i += 1
        elif arg in ("--version", "-V"):
            st.print_version = True
            i += 1
        elif arg == "--posix":
            # bash `--posix`: enable posix mode at startup, through the same
            # transition path as `-o posix` (the POSIXLY_CORRECT coupling
            # fires when the shell applies it).
            st.transitions.append(("posix", True))
            i += 1
        elif arg in ANALYSIS_MODE_FLAGS:
            mode = ANALYSIS_MODE_FLAGS[arg]
            if mode not in st.analysis:
                st.analysis.append(mode)
            i += 1
        elif arg == "--rcfile" or arg.startswith("--rcfile="):
            st.rcfile, i = _value_option(argv, i, "--rcfile")
        elif arg == "--parser" or arg.startswith("--parser="):
            st.parser_request, i = _value_option(argv, i, "--parser")
        elif not arg.startswith("--") and len(arg) > 1:
            i = _parse_cluster(argv, i, st)
        else:
            raise _invalid_option(arg)

    operands = argv[i:]

    # Validate the parser BEFORE any Shell can exist (probe class A4a: an
    # invalid parser used to run the rc file first).
    parser: Optional[str] = None
    if st.parser_request is not None:
        parser = resolve_parser_name(st.parser_request)
        if parser is None:
            raise InvocationError((
                f"psh: unknown parser: {st.parser_request}",
                "Available parsers: recursive_descent (rd), combinator (pc)",
            ))

    # Source kind, $0 and positionals (POSIX `sh -c command_string
    # [name [args...]]`; with -s the operands are ALL positionals).
    if st.command_mode:
        if not operands:
            raise InvocationError(("psh: -c: option requires an argument",))
        command = operands[0]
        argv0 = operands[1] if len(operands) > 1 else "psh"
        positionals = tuple(operands[2:])
        return InvocationConfig(
            source_kind=SourceKind.COMMAND, command=command,
            forced_stdin=st.forced_stdin, interactive=st.interactive,
            option_transitions=tuple(st.transitions),
            option_listings=tuple(st.listings), parser=parser,
            analysis_modes=tuple(st.analysis), argv0=argv0,
            positionals=positionals, norc=st.norc, rcfile=st.rcfile,
            ast_format=st.ast_format, print_help=st.print_help,
            print_version=st.print_version)

    if operands and not st.forced_stdin:
        return InvocationConfig(
            source_kind=SourceKind.SCRIPT, script_path=operands[0],
            interactive=st.interactive,
            option_transitions=tuple(st.transitions),
            option_listings=tuple(st.listings), parser=parser,
            analysis_modes=tuple(st.analysis), argv0=operands[0],
            positionals=tuple(operands[1:]), norc=st.norc, rcfile=st.rcfile,
            ast_format=st.ast_format, print_help=st.print_help,
            print_version=st.print_version)

    # Stdin (default, or forced by -s — under which any operands are the
    # positional parameters and $0 stays the shell name, bash).
    return InvocationConfig(
        source_kind=SourceKind.STDIN, forced_stdin=st.forced_stdin,
        interactive=st.interactive,
        option_transitions=tuple(st.transitions),
        option_listings=tuple(st.listings), parser=parser,
        analysis_modes=tuple(st.analysis), argv0="psh",
        positionals=tuple(operands), norc=st.norc, rcfile=st.rcfile,
        ast_format=st.ast_format, print_help=st.print_help,
        print_version=st.print_version)
