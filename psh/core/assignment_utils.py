"""Shared utilities for variable assignment handling.

This module provides common functions for parsing and validating shell
variable assignments, used by both the executor core and command modules.

It is also the single home for the shell's ASCII assignment-word / name
regex family (see below), so the ``NAME=value`` / ``NAME[sub]=value`` /
``NAME+=value`` shapes are defined once instead of copy-pasted across the
lexer-adjacent, parser, expansion and printf modules that recognise them.
"""

import re
from typing import Tuple

#: The ASCII shell-name character pattern: a name starts with a letter or
#: underscore and continues with letters, digits or underscores. This is the
#: single definition of that fragment; the regexes below compose it, and other
#: modules interpolate it into their own (context-specific) patterns rather than
#: re-spelling the character classes.
#:
#: IMPORTANT — this is the *lexer/parser-time SHAPE* of a name and is ASCII-only
#: by design. It is deliberately NOT the runtime identifier POLICY, which lives
#: in :func:`psh.lexer.unicode_support.is_valid_name` and accepts Unicode-letter
#: names unless ``set -o posix`` is active (a documented divergence from bash).
#: The two answer different questions and diverge on non-ASCII names; do not
#: "unify" them.
SHELL_NAME = r'[A-Za-z_][A-Za-z0-9_]*'

#: A whole string that is exactly a bare ASCII shell name — no subscript, no
#: operators. Used (via ``.match``) wherever a value must be a plain name:
#: ``printf %n`` targets, and the fusable-name check in token brace expansion.
NAME_RE = re.compile(rf'^{SHELL_NAME}$')

#: An assignment WORD prefix: NAME, an optional ``[subscript]`` (which may be
#: empty), an optional ``+``, then ``=``. This is what bash's lexer reads as an
#: assignment word (``a=1``, ``a[0]=1``, ``a[$i]=1``, ``a+=x``). Used to reject
#: ``a=b()`` / ``a[0]=b()`` as function names and to suppress brace expansion on
#: command-prefix assignments (``a={x,y}`` stays literal; ``echo a={x,y}``
#: expands).
ASSIGNMENT_WORD_RE = re.compile(rf'^{SHELL_NAME}(\[[^\]]*\])?\+?=')

#: An assignment prefix WITHOUT a subscript: NAME, optional ``+``, then ``=``.
#: Used by the declaration-builtin value handler (``declare foo=$x``), which
#: recognises only ``NAME=`` / ``NAME+=`` prefixes taken from unquoted literal
#: text. Kept DISTINCT from :data:`ASSIGNMENT_WORD_RE`: that handler routes
#: subscripted element assignments differently, so adding the subscript group
#: here would change what it recognises.
ASSIGNMENT_PREFIX_RE = re.compile(rf'^{SHELL_NAME}\+?=')


def is_valid_assignment(arg: str, posix_mode: bool = False) -> bool:
    """Check if argument is a valid variable assignment (VAR=value).

    A valid assignment has:
    - An '=' character
    - A variable name before the '=' that ``unicode_support.is_valid_name``
      accepts for the current mode

    Name validity is delegated to the shell's single authoritative identifier
    policy (``psh.lexer.unicode_support.is_valid_name``). With ``posix_mode``
    (``set -o posix``) the name must be ASCII ``[A-Za-z_][A-Za-z0-9_]*``, matching
    bash; otherwise psh's lenient Unicode-letter rule applies (a documented
    divergence). A word that is not a valid assignment is treated as an ordinary
    command word, so ``é=1`` under posix runs as a command (``command not
    found``), exactly as bash does.

    Args:
        arg: The argument string to check
        posix_mode: Restrict names to the POSIX/ASCII set when True

    Returns:
        True if the argument is a valid assignment, False otherwise

    Examples:
        >>> is_valid_assignment("FOO=bar")
        True
        >>> is_valid_assignment("_var=123")
        True
        >>> is_valid_assignment("123=invalid")
        False
        >>> is_valid_assignment("no_equals")
        False
    """
    from ..lexer.unicode_support import is_valid_name
    if '=' not in arg:
        return False

    var_name = arg.split('=', 1)[0]
    # NAME+=value appends (bash); validate the name without the '+'
    if var_name.endswith('+'):
        var_name = var_name[:-1]
    return is_valid_name(var_name, posix_mode)


def resolve_append_assignment(scope_manager, var: str, value: str) -> Tuple[str, object]:
    """Resolve ``NAME+=value`` appends to (name, final_value) — the PURE path.

    ``var`` is the text left of '=' (so ``NAME+`` for appends; anything else is
    returned unchanged). This is the compute-only entry point the command-prefix
    (``a+=z cmd``), ``local x+=v``, and rollback callers use: they need the
    resolved value WITHOUT a commit so they can snapshot the original before
    installing it (a prefix append must restore the untouched original after the
    command). The actual computation is the ONE shared formula,
    :meth:`VariableStore.compute_append_value` (appraisal H8) — plain variables
    append textually, ``-i`` variables append arithmetically, and a scalar
    append to an array updates a COPY's element 0 (integer-add / concat +
    case-fold), never mutating the live container.
    """
    if not var.endswith('+'):
        return var, value
    name = var[:-1]
    # Resolve a nameref to its target BEFORE reading the old value/attributes:
    # `n=5; declare -n r=n; r+=3` must append to n's VALUE (-> "53"), not to r's
    # own value (the literal target name "n", which gave "n3"); the integer/array
    # attributes likewise belong to the target. A plain (non-nameref) name
    # resolves to itself, so this is a no-op for the common case. The write side
    # (set_variable, below) re-resolves the nameref, so we still return `name`.
    target = scope_manager.resolve_nameref_name(name)
    var_obj = scope_manager.get_variable_object(target)
    return name, scope_manager.store.compute_append_value(var_obj, value)
