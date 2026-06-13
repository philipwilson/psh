"""The command hash table behind the ``hash`` builtin (bash/POSIX).

Maps command names to remembered full paths with a hit counter, exactly
mirroring bash 5.2's table (probe-verified 2026-06-13):

- Running an external command remembers its resolved path (hits start
  at 1); each later use through the table increments the counter.
- ``hash NAME`` remembers the path with hits 0; ``hash -t NAME`` looks
  the path up (and, like bash, the lookup itself counts as a hit).
- Any assignment to (or unset of) PATH empties the whole table — wired
  via :attr:`ScopeManager.path_changed` (see ``ShellState.__init__``).
- ``cd`` does NOT clear the table (bash keeps absolute paths).
- Subshell-style children inherit a copy (``ShellState.adopt``).

The table lives on ``shell.state`` (``state.command_hash``), never on a
builtin instance — builtins are process-wide singletons (the
statelessness contract in ``psh/builtins/base.py``).
"""

from typing import Dict, List, Optional, Tuple


class CommandHashTable:
    """name -> (full path, hit count), in insertion order."""

    def __init__(self) -> None:
        self._paths: Dict[str, str] = {}
        self._hits: Dict[str, int] = {}

    def insert(self, name: str, path: str, hits: int = 0) -> None:
        """Remember *path* for *name*, (re)setting the hit counter.

        bash neither verifies the path exists (``hash -p /bad/x name``
        succeeds) nor preserves the old counter on re-hash.
        """
        self._paths[name] = path
        self._hits[name] = hits

    def lookup(self, name: str) -> Optional[str]:
        """Return the remembered path, counting the lookup as a hit.

        bash increments the counter on every table consultation —
        including ``hash -t`` and execs that subsequently fail.
        """
        path = self._paths.get(name)
        if path is not None:
            self._hits[name] += 1
        return path

    def remove(self, name: str) -> bool:
        """Forget *name*; True if it was remembered (``hash -d``)."""
        if name in self._paths:
            del self._paths[name]
            del self._hits[name]
            return True
        return False

    def clear(self) -> None:
        """Empty the table (``hash -r``, any PATH change)."""
        self._paths.clear()
        self._hits.clear()

    def entries(self) -> List[Tuple[str, str, int]]:
        """(name, path, hits) triples in insertion order."""
        return [(name, path, self._hits[name])
                for name, path in self._paths.items()]

    def __len__(self) -> int:
        return len(self._paths)

    def __contains__(self, name: str) -> bool:
        return name in self._paths

    def copy(self) -> 'CommandHashTable':
        """Independent copy (subshell-style children inherit one)."""
        new = CommandHashTable()
        new._paths = dict(self._paths)
        new._hits = dict(self._hits)
        return new
