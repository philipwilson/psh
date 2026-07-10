"""The ``hash`` builtin: remembered command locations (POSIX + bash extras).

All behavior here is pinned to bash 5.2 probes (2026-06-13):

- ``hash`` lists the table as a ``hits\\tcommand`` header plus ``%4d\\t%s``
  rows; an empty table prints ``hash: hash table empty`` on STDOUT, rc 0.
- ``hash NAME...`` PATH-searches and remembers each name with hits 0;
  names that are functions or builtins are silently skipped (rc 0), names
  containing a slash are ignored (rc 0), and a not-found name reports
  ``hash: NAME: not found`` and makes the final status 1.
- ``hash -r`` empties the table (any names after -r are then hashed).
- ``hash -t NAME...`` prints remembered paths WITHOUT a PATH search
  (an unhashed name is ``not found``, rc 1); one name prints the bare
  path, several print ``name\\tpath`` lines. The lookup counts as a hit.
- ``hash -d NAME...`` forgets each name (missing: ``not found``, rc 1 —
  except against an EMPTY table, which silently succeeds, rc 0).
- ``hash -l`` prints ``builtin hash -p PATH NAME`` reusable lines (an
  empty table prints nothing).
- ``hash -p PATHNAME NAME...`` remembers PATHNAME for each name without
  any verification (bash happily hashes a nonexistent path).
- With hashing disabled (``set +h``), every use fails with
  ``hashing disabled``, rc 1.

The table itself lives on ``shell.state.command_hash`` (builtin
instances are stateless singletons); the executor side — populating the
table when external commands run, and the checkhash re-verify — lives in
``psh/executor/strategies.py``.
"""

from typing import TYPE_CHECKING, List

from .base import Builtin
from .registry import builtin

if TYPE_CHECKING:
    from ..shell import Shell


@builtin
class HashBuiltin(Builtin):
    """Remember or display program locations."""

    @property
    def name(self) -> str:
        return "hash"

    @property
    def synopsis(self) -> str:
        return "hash [-lr] [-p pathname] [-dt] [name ...]"

    def execute(self, args: List[str], shell: 'Shell') -> int:
        opts, names = self.parse_flags(args, shell, flags='lrdt',
                                       value_flags='p')
        if opts is None:
            return 2

        # bash: with hashing disabled (set +h) every hash use fails.
        if not shell.state.options.get('hashall', True):
            self.error("hashing disabled", shell)
            return 1

        table = shell.state.command_hash

        if opts['r']:
            table.clear()
            # bash: names after -r are then hashed normally (fall through)

        # bash quirk (probe-verified): -t / -d with no names report
        # "option requires an argument", rc 1.
        if not names:
            for ch in ('t', 'd'):
                if opts[ch]:
                    self.error(f"-{ch}: option requires an argument", shell)
                    return 1

        if opts['t'] and names:
            return self._print_types(names, shell, table)

        if opts['d'] and names:
            # bash quirk (probe-verified): -d against an EMPTY table
            # silently succeeds; only a populated table reports misses.
            if len(table) == 0:
                return 0
            status = 0
            for name in names:
                if not table.remove(name):
                    self.error(f"{name}: not found", shell)
                    status = 1
            return status

        if opts['p'] is not None and names:
            for name in names:
                table.insert(name, opts['p'])
            return 0

        if names:
            return self._hash_names(names, shell, table)

        if opts['l']:
            # Reusable form: the path and name are quoted so a value with a
            # space/quote/metachar (`hash -p '/tmp/a b' foo`) re-parses to the
            # same word (bash). Uses the shared reusable-word quoter.
            from ..visitor.formatter_quoting import quote_word_reuse
            for name, path, _hits in table.entries():
                self.write_line(
                    f"builtin hash -p {quote_word_reuse(path)} "
                    f"{quote_word_reuse(name)}", shell)
            return 0

        if opts['r']:
            return 0

        # Plain `hash`: list the table.
        if len(table) == 0:
            # bash prints this on stdout (not stderr), rc 0.
            self.write_line("hash: hash table empty", shell)
            return 0
        self.write_line("hits\tcommand", shell)
        for _name, path, hits in table.entries():
            self.write_line(f"{hits:4d}\t{path}", shell)
        return 0

    def _print_types(self, names: List[str], shell: 'Shell', table) -> int:
        """``hash -t``: table-only lookups (no PATH search — bash)."""
        status = 0
        for name in names:
            path = table.lookup(name)  # counts as a hit (bash)
            if path is None:
                self.error(f"{name}: not found", shell)
                status = 1
            elif len(names) > 1:
                self.write_line(f"{name}\t{path}", shell)
            else:
                self.write_line(path, shell)
        return status

    def _hash_names(self, names: List[str], shell: 'Shell', table) -> int:
        """``hash NAME...``: PATH-search and remember (hits 0 — bash)."""
        status = 0
        for name in names:
            # bash skips slash names, functions and builtins silently.
            if '/' in name:
                continue
            if shell.function_manager.get_function(name) is not None:
                continue
            if shell.builtin_registry.has(name):
                continue
            paths = shell.command_resolver.search_path(
                name, shell.env.get('PATH', ''))
            if paths:
                table.insert(name, paths[0])
            else:
                self.error(f"{name}: not found", shell)
                status = 1
        return status

    @property
    def help(self) -> str:
        return """hash: hash [-lr] [-p pathname] [-dt] [name ...]

    Remember or display program locations.

    Determine and remember the full pathname of each command NAME.  If
    no arguments are given, information about remembered commands is
    displayed: a table of hit counts and full pathnames.

    Options:
      -d    forget the remembered location of each NAME
      -l    display in a format that may be reused as input
      -p pathname    use PATHNAME as the full pathname of NAME
      -r    forget all remembered locations
      -t    print the remembered location of each NAME, preceding
            each location with the corresponding NAME if multiple
            NAMEs are given

    The table is emptied whenever PATH is assigned or unset. With
    hashing disabled (set +h), hash fails with "hashing disabled".
    The shopt option `checkhash' makes the shell re-verify remembered
    paths before executing them, re-searching PATH if one is gone.

    Exit Status:
    Returns success unless NAME is not found or an invalid option is
    given."""
