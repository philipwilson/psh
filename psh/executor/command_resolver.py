"""One authoritative command-name resolver (builtins appraisal finding 5).

Before this module, five surfaces answered "what does this command name
mean?" independently — the executor's external strategy, ``command``,
``type``, ``hash``, and (nominally) completion — and drifted: a path
seeded with ``hash -p`` was visible to ``type`` but not ``command -v``,
``type -P`` ignored the hash, an empty PATH component (the cwd) was
searched by the executor but skipped by ``type``/``command``, and
``command -p`` forced external execution even for builtins.

``CommandResolver`` is the single source of truth. It answers two kinds
of question:

- :meth:`search_path` — the ONE PATH walk (bash rules: a name containing
  a slash is taken as given, an empty component denotes the cwd,
  ``X_OK`` gates a match). Every ``$PATH`` scan goes through it.
- :meth:`resolve` — the ordered candidate list for a name given a
  :class:`ResolveQuery` (which participation, which PATH, hash use,
  first-vs-all). ``type`` and ``command -v``/``-V`` render it; the
  executor's external path uses :meth:`resolve_for_exec`.

Rendering and dispatch stay with the callers — the resolver only reports
what a name resolves to, never how a surface prints or runs it.

Home rationale: resolution is an execution-time concern that needs the
whole shell (aliases, functions, builtins, the command hash, and PATH),
which the executor already holds; it also subsumes the external
strategy's former ``resolve_via_hash_table``. Placing it in ``core``
would invert the dependency (core does not import builtins/executor).
"""

import os
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from .strategies import POSIX_SPECIAL_BUILTINS

if TYPE_CHECKING:
    from ..core.functions import Function
    from ..shell import Shell


# Reserved words reported as "keyword" (bash's list). The single copy;
# TypeBuiltin/CommandBuiltin reference CommandResolver.SHELL_KEYWORDS.
SHELL_KEYWORDS = frozenset({
    'if', 'then', 'else', 'elif', 'fi', 'case', 'esac', 'for',
    'select', 'while', 'until', 'do', 'done', 'in', 'function',
    'time', '{', '}', '!', '[[', ']]', 'coproc',
})


class CandidateKind(Enum):
    """What a resolved command name is, in bash's lookup precedence order."""

    ALIAS = "alias"
    KEYWORD = "keyword"
    FUNCTION = "function"
    BUILTIN = "builtin"
    HASHED = "hashed"      # external, found in the command hash table
    EXTERNAL = "external"  # external, found via a PATH search


@dataclass(frozen=True)
class Candidate:
    """One thing a command name could resolve to."""

    kind: CandidateKind
    name: str
    path: Optional[str] = None            # HASHED / EXTERNAL
    alias_value: Optional[str] = None     # ALIAS
    builtin: object = None                # BUILTIN instance
    is_special_builtin: bool = False      # BUILTIN: a POSIX special builtin
    function: 'Optional[Function]' = None  # FUNCTION

    @property
    def is_file(self) -> bool:
        """A disk-file candidate (``type -t`` reports ``file``)."""
        return self.kind in (CandidateKind.HASHED, CandidateKind.EXTERNAL)


@dataclass(frozen=True)
class ResolveQuery:
    """Which sources a resolution consults and how it renders paths.

    Defaults describe a bare ``type NAME`` / ``command -v NAME`` lookup:
    every source participates, the hash is consulted (as a completed
    PATH search — counting a hit, like bash), and only the first match
    per source is returned. Callers narrow this:

    - ``command``/``builtin`` set ``use_functions=False`` (function bypass);
    - ``type -a`` sets ``all_matches=True`` (every builtin + every PATH
      file, and — like bash — the hash is IGNORED);
    - ``type -P`` clears the non-file sources (force a disk lookup);
    - ``command -p`` / ``env`` pass ``path`` to search a different PATH;
    - only the executor's exec path sets ``populate_hash`` / ``verify_hash``
      — introspection never remembers or checkhash-verifies (bash).
    """

    use_aliases: bool = True
    use_keywords: bool = True
    use_functions: bool = True
    use_builtins: bool = True
    consult_hash: bool = True
    use_path: bool = True
    all_matches: bool = False
    path: Optional[str] = None
    populate_hash: bool = False
    verify_hash: bool = False


# A bare `type NAME` / `command -v NAME` lookup: the immutable default query.
DEFAULT_QUERY = ResolveQuery()


@dataclass
class Resolution:
    """The ordered candidates a name resolved to (highest precedence first)."""

    name: str
    candidates: List[Candidate]

    @property
    def found(self) -> bool:
        return bool(self.candidates)

    @property
    def first(self) -> Optional[Candidate]:
        return self.candidates[0] if self.candidates else None


class CommandResolver:
    """Resolve a command name against one shell's aliases/functions/builtins/
    hash table and PATH. Holds no state beyond the shell reference."""

    SHELL_KEYWORDS = SHELL_KEYWORDS

    def __init__(self, shell: 'Shell') -> None:
        self.shell = shell

    # -- the one PATH walk -------------------------------------------------

    def search_path(self, name: str, path_str: str, *,
                    all_matches: bool = False) -> List[str]:
        """Locate *name* on *path_str*, bash's rules.

        A name containing a slash is taken as given (returned verbatim if
        it is an executable file — bash does NOT canonicalise it, so
        ``type -P ./x`` prints ``./x``). Otherwise each PATH component is
        searched; an EMPTY component denotes the current directory (bash),
        rendered as ``./name``. Returns the first executable match, or all
        of them with ``all_matches=True`` (``type -a``). ``X_OK`` and
        regular-file are both required.
        """
        if '/' in name:
            if os.path.isfile(name) and os.access(name, os.X_OK):
                return [name]
            return []

        results: List[str] = []
        for component in path_str.split(':'):
            directory = component if component else '.'
            full_path = os.path.join(directory, name)
            if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
                if not all_matches:
                    return [full_path]
                results.append(full_path)
        return results

    # -- ordered resolution ------------------------------------------------

    def resolve(self, name: str, query: ResolveQuery = DEFAULT_QUERY) -> Resolution:
        """Return the ordered candidates for *name* under *query*."""
        shell = self.shell
        candidates: List[Candidate] = []

        if query.use_aliases:
            alias_value = shell.alias_manager.get_alias(name)
            if alias_value is not None:
                candidates.append(Candidate(
                    CandidateKind.ALIAS, name, alias_value=alias_value))

        if query.use_keywords and name in SHELL_KEYWORDS:
            candidates.append(Candidate(CandidateKind.KEYWORD, name))

        if query.use_functions:
            func = shell.function_manager.get_function(name)
            if func is not None:
                candidates.append(Candidate(
                    CandidateKind.FUNCTION, name, function=func))

        if query.use_builtins and shell.builtin_registry.has(name):
            candidates.append(Candidate(
                CandidateKind.BUILTIN, name,
                builtin=shell.builtin_registry.get(name),
                is_special_builtin=name in POSIX_SPECIAL_BUILTINS))

        candidates.extend(self._file_candidates(name, query))
        return Resolution(name, candidates)

    def _file_candidates(self, name: str, query: ResolveQuery) -> List[Candidate]:
        """The disk-file candidate(s): hashed entry then PATH search.

        ``all_matches`` returns every PATH file and, like bash's ``type -a``,
        does NOT consult the hash. Otherwise a hashed path wins over a fresh
        PATH search (bash), counting a hit; ``populate_hash`` remembers a
        fresh find (executor only).
        """
        path_str = (query.path if query.path is not None
                    else self.shell.env.get('PATH', ''))

        if query.all_matches:
            return [Candidate(CandidateKind.EXTERNAL, name, path=path)
                    for path in self.search_path(name, path_str, all_matches=True)]

        if query.consult_hash and '/' not in name:
            cached = self._hash_lookup(name, verify=query.verify_hash)
            if cached is not None:
                return [Candidate(CandidateKind.HASHED, name, path=cached)]

        if query.use_path:
            matches = self.search_path(name, path_str)
            if matches:
                if query.populate_hash and '/' not in name:
                    self.shell.state.command_hash.insert(name, matches[0], hits=1)
                return [Candidate(CandidateKind.EXTERNAL, name, path=matches[0])]

        return []

    def _hash_lookup(self, name: str, *, verify: bool) -> Optional[str]:
        """Consult the command hash, counting the hit (bash).

        With *verify* (``shopt -s checkhash``, executor only) a remembered
        path that is no longer an executable file is dropped and treated as
        a miss so PATH is re-searched; introspection never verifies (bash's
        ``type``/``command -v`` report a stale hash unchanged).
        """
        table = self.shell.state.command_hash
        cached = table.lookup(name)  # counts the hit, like bash
        if cached is None:
            return None
        if verify and not (os.path.isfile(cached) and os.access(cached, os.X_OK)):
            table.remove(name)  # stale: drop and force a fresh PATH search
            return None
        return cached

    # -- executor external resolution -------------------------------------

    def resolve_for_exec(self, name: str) -> Optional[str]:
        """The path to exec directly, or None to let ``execvpe`` walk PATH.

        The normal external-command path: consult and populate the command
        hash (honouring ``set +h`` and ``shopt -s checkhash``), searching
        the shell's live PATH. Returns None for a slash name, disabled
        hashing, or a PATH miss — the forked child then ``execvpe``s the
        name and produces the usual "command not found". Mirrors the old
        ``ExternalExecutionStrategy.resolve_via_hash_table`` contract so the
        parent-side hit count and remembered location match bash exactly.
        """
        if '/' in name or not self.shell.state.options.get('hashall', True):
            return None
        query = ResolveQuery(
            use_aliases=False, use_keywords=False, use_functions=False,
            use_builtins=False, consult_hash=True, use_path=True,
            populate_hash=True,
            verify_hash=bool(self.shell.state.options.get('checkhash')))
        candidate = self.resolve(name, query).first
        return candidate.path if candidate is not None else None
