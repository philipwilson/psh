"""Shared utilities for variable assignment handling.

This module provides common functions for parsing and validating shell
variable assignments, used by both the executor core and command modules.
"""

import os
from typing import List, Tuple


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


def extract_assignments(args: List[str]) -> List[Tuple[str, str]]:
    """Extract variable assignments from beginning of arguments.

    Scans the argument list from the start, extracting valid assignments
    until a non-assignment is encountered.

    Args:
        args: List of argument strings

    Returns:
        List of (variable_name, value) tuples for each assignment found

    Examples:
        >>> extract_assignments(["FOO=bar", "BAZ=qux", "echo", "hello"])
        [("FOO", "bar"), ("BAZ", "qux")]
        >>> extract_assignments(["echo", "FOO=bar"])
        []
    """
    assignments = []

    for arg in args:
        if '=' in arg and is_valid_assignment(arg):
            var, value = arg.split('=', 1)
            assignments.append((var, value))
        else:
            # Stop at first non-assignment
            break

    return assignments


def is_exported(var_name: str) -> bool:
    """Check if a variable is exported to the environment.

    Args:
        var_name: Name of the variable to check

    Returns:
        True if the variable exists in os.environ
    """
    return var_name in os.environ
