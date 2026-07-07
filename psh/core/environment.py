"""The opaque-inherited-environment model.

A process's environment holds two kinds of entries, and bash treats them
differently (core-state appraisal finding H3):

- an entry whose name is a valid shell identifier (``PATH``, ``GOODVAR``)
  becomes an exported SHELL VARIABLE — visible to ``set`` / ``declare -p`` /
  ``compgen -v`` and assignable; while
- an entry whose name is NOT a valid identifier (``bad-name=x``, ``a.b=y``,
  ``1abc=z``, a non-ASCII name) is kept OPAQUE: passed through to child
  processes and visible to ``printenv``, but NEVER materialised as a shell
  variable.

psh previously imported EVERY inherited entry into the scope manager as an
exported variable, so an invalid name wrongly appeared in ``declare -p`` /
``set`` and round-tripped through ``export -p``. This module is the single home
for the import-partition rule; the opaque entries simply stay in ``state.env``
(so children and ``printenv`` still see them) without a backing ``Variable``.
"""

import re

from .assignment_utils import SHELL_NAME

#: bash's ``legal_identifier()``: an inherited environment entry becomes a shell
#: variable iff its whole name is a bare ASCII shell name. This is deliberately
#: the ASCII SHAPE (bash uses it for env import regardless of locale — a
#: non-ASCII name like ``café`` is kept opaque, probe-verified against bash
#: 5.2), reusing the one ``SHELL_NAME`` fragment.
_ENVIRON_SHELL_NAME_RE = re.compile(rf'^{SHELL_NAME}$')


def is_environ_shell_name(name: str) -> bool:
    """True if inherited env entry *name* should become a shell variable.

    False keeps the entry OPAQUE (present in the environment / ``printenv`` /
    child processes, but not a shell variable) — bash's behaviour for a name
    that is not a valid identifier.
    """
    return bool(_ENVIRON_SHELL_NAME_RE.match(name))
