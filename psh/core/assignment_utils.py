"""Shared utilities for variable assignment handling.

This module provides common functions for parsing and validating shell
variable assignments, used by both the executor core and command modules.
"""

from typing import Tuple


def is_valid_assignment(arg: str) -> bool:
    """Check if argument is a valid variable assignment (VAR=value).

    A valid assignment has:
    - An '=' character
    - A variable name before the '=' that:
      - Starts with a letter or underscore
      - Contains only alphanumeric characters or underscores

    Args:
        arg: The argument string to check

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
    if '=' not in arg:
        return False

    var_name = arg.split('=', 1)[0]
    # NAME+=value appends (bash); validate the name without the '+'
    if var_name.endswith('+'):
        var_name = var_name[:-1]
    # Variable name must start with letter or underscore
    if not var_name or not (var_name[0].isalpha() or var_name[0] == '_'):
        return False

    # Rest must be alphanumeric or underscore
    return all(c.isalnum() or c == '_' for c in var_name[1:])


def resolve_append_assignment(scope_manager, var: str, value: str) -> Tuple[str, object]:
    """Resolve ``NAME+=value`` appends to (name, final_value).

    ``var`` is the text left of '=' (so ``NAME+`` for appends; anything
    else is returned unchanged). Plain variables append textually;
    integer (-i) variables append arithmetically — achieved by handing
    the INTEGER transform the expression "(old)+(value)" to evaluate,
    matching bash. A scalar append to an array variable updates element
    0 in place and returns the array (bash: ``a=(1 2); a+=x`` makes
    a[0] "1x").
    """
    from .variables import AssociativeArray, IndexedArray, VarAttributes
    if not var.endswith('+'):
        return var, value
    name = var[:-1]
    var_obj = scope_manager.get_variable_object(name)
    if var_obj is not None and isinstance(var_obj.value, IndexedArray):
        indexed = var_obj.value
        indexed.set(0, (indexed.get(0) or '') + value)
        return name, indexed
    if var_obj is not None and isinstance(var_obj.value, AssociativeArray):
        assoc = var_obj.value
        assoc.set('0', (assoc.get('0') or '') + value)
        return name, assoc
    old = '' if var_obj is None or var_obj.value is None else str(var_obj.value)
    if (var_obj is not None and var_obj.attributes & VarAttributes.INTEGER
            and value.strip()):
        return name, f"({old or 0})+({value})"
    return name, old + value
