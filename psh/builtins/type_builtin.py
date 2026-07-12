"""The ``type`` builtin: report how a name would be interpreted.

A thin adapter over the shared :class:`~psh.executor.command_resolver.CommandResolver`:
it maps ``type``'s options to a :class:`ResolveQuery`, asks the resolver
for the ordered candidates, and renders them. All lookup order, the PATH
walk (empty component = cwd), and hash consultation live in the resolver —
and the descriptive banner itself is rendered by ONE function here
(:func:`render_candidate_banner`, also used by ``command -V``) — so
``type``, ``command -v``/``-V``, ``hash``, and the executor cannot drift
in either the resolution or its wording.
"""

from typing import TYPE_CHECKING, List

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..executor.command_resolver import Candidate
    from ..shell import Shell


def render_candidate_banner(name: str, cand: 'Candidate') -> str:
    """The descriptive banner for one resolver candidate (possibly multi-line).

    ONE renderer for the six candidate kinds, shared by ``type`` and
    ``command -V`` — bash 5.2 prints IDENTICAL wording for the two builtins
    across all six kinds (probe-verified: alias/keyword/function/builtin/
    hashed/external; tmp/r19-ledgers/T3-probes/t3c-banner-base.txt), so no
    per-builtin style knob is needed. The near-verbatim six-way chains this
    replaces had been pasted into both modules and could drift.
    """
    from ..executor.command_resolver import CandidateKind

    if cand.kind is CandidateKind.ALIAS:
        return f"{name} is aliased to `{cand.alias_value}'"
    if cand.kind is CandidateKind.KEYWORD:
        return f"{name} is a shell keyword"
    if cand.kind is CandidateKind.FUNCTION:
        from ..visitor import format_function_definition
        return (f"{name} is a function\n"
                f"{format_function_definition(name, cand.function)}")
    if cand.kind is CandidateKind.BUILTIN:
        return f"{name} is a shell builtin"
    if cand.kind is CandidateKind.HASHED:
        return f"{name} is hashed ({cand.path})"
    return f"{name} is {cand.path}"  # EXTERNAL


@builtin
class TypeBuiltin(Builtin):
    """Display information about command types."""

    @property
    def name(self) -> str:
        return "type"

    @property
    def synopsis(self) -> str:
        return "type [-afptP] name [name ...]"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        """Display information about command types."""
        # Parse options (clusterable, like bash: `type -af name`)
        opts, names = self.parse_flags(args, shell, flags='afptP')
        if opts is None:
            return 2
        show_all = opts['a']
        type_only = opts['t']
        path_only = opts['p']
        force_path = opts['P']
        file_only = opts['f']

        # bash: `type` with no operands prints nothing and succeeds
        if not names:
            return 0

        from ..executor.command_resolver import ResolveQuery

        # Map the options to one resolver query. -P (force a disk lookup)
        # excludes alias/keyword/function/builtin; -f suppresses aliases,
        # keywords and functions (psh's historical -f scope — bash suppresses
        # only functions; see the resolver campaign notes). -a collects every
        # match and, like bash, ignores the hash.
        query = ResolveQuery(
            use_aliases=not force_path and not file_only,
            use_keywords=not force_path and not file_only,
            use_functions=not force_path and not file_only,
            use_builtins=not force_path,
            consult_hash=not show_all,
            use_path=True,
            all_matches=show_all,
        )

        resolver = shell.command_resolver
        exit_code = 0
        for name in names:
            candidates = resolver.resolve(name, query).candidates
            if not candidates:
                # bash prints "not found" only for the bare form; -t/-p are
                # silent (psh also leaves -P silent-less — preserved).
                if not type_only and not path_only:
                    self.error(f"{name}: not found", shell)
                exit_code = 1
                continue
            # Non-`-a` reports only the highest-precedence match.
            shown = candidates if show_all else candidates[:1]
            for cand in shown:
                self._render(name, cand, shell, type_only, path_only, force_path)

        return exit_code

    def _render(self, name: str, cand: 'Candidate', shell: 'Shell',
                type_only: bool, path_only: bool, force_path: bool) -> None:
        """Print one candidate in the surface the options select."""
        if type_only:
            self.write_line(_TYPE_WORD[cand.kind.value], shell)
            return

        if path_only or force_path:
            # -p / -P print ONLY a path, and only for a disk-file candidate
            # (a file candidate always carries a path).
            if cand.is_file and cand.path is not None:
                self.write_line(cand.path, shell)
            return

        # Bare form: the shared descriptive banner (also `command -V`'s).
        self.write_line(render_candidate_banner(name, cand), shell)

    @property
    def help(self) -> str:
        return """type: type [-afptP] name [name ...]

    Display information about command type.

    For each NAME, indicate how it would be interpreted if used as a
    command name.

    Options:
      -a    display all locations containing an executable named NAME;
            includes aliases, builtins, and functions, if and only if
            the `-p' option is not also used
      -f    suppress shell function lookup
      -P    force a PATH search for each NAME, even if it is an alias,
            builtin, or function, and returns the name of the disk file
            that would be executed
      -p    returns either the name of the disk file that would be executed,
            or nothing if `type -t NAME' would not return `file'
      -t    output a single word which is one of `alias', `builtin',
            `file', `function', or `keyword', if NAME is an alias, shell
            builtin, disk file, shell function, or shell reserved word,
            respectively

    Arguments:
      NAME  Command name to be interpreted.

    Exit Status:
    Returns success if all of the NAMEs are found; fails if any are not found."""


# `type -t` words, keyed by CandidateKind.value (so this module needs no
# load-time import of the executor). Hashed and PATH externals both "file".
_TYPE_WORD = {
    "alias": "alias",
    "keyword": "keyword",
    "function": "function",
    "builtin": "builtin",
    "hashed": "file",
    "external": "file",
}
