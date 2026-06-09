"""Shared parsing for indexed-array initializer arguments.

Declaration builtins (`local`, `declare`) receive array assignments as a
single reconstructed string argument like ``arr=(one $x "two words" 'lit')``.
Unlike scalar assignment values, the element text inside the parentheses is
NOT pre-expanded by the executor, so expansion happens here — and it must be
quote-aware to match bash:

- single-quoted elements stay literal,
- double-quoted elements are expanded but never word-split,
- unquoted elements are expanded and the result word-split (an expansion
  producing nothing contributes no element).
"""

import shlex
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from ..shell import Shell


def parse_array_elements(value: str, shell: 'Shell') -> List[str]:
    """Parse the elements of an indexed array initializer.

    Args:
        value: The full initializer including parentheses, e.g. ``(a "b c")``.
        shell: Shell used for variable/command-substitution expansion.

    Returns:
        The list of element strings, expanded per bash quoting rules.
    """
    content = value[1:-1].strip()
    if not content:
        return []

    try:
        # posix=False keeps the surrounding quotes on each element so we can
        # tell single-quoted (literal) from double-quoted/unquoted.
        parsed_values = shlex.split(content, posix=False)
    except ValueError:
        # Fallback to simple splitting on malformed quoting
        return content.split()

    result = []
    for val in parsed_values:
        if len(val) >= 2 and val[0] == "'" and val[-1] == "'":
            # Single quotes: no expansion
            result.append(val[1:-1])
        elif len(val) >= 2 and val[0] == '"' and val[-1] == '"':
            # Double quotes: expand, no word splitting
            val = val[1:-1]
            if '$' in val:
                val = shell.expansion_manager.expand_string_variables(val)
            result.append(val)
        else:
            # Unquoted: expand, then word-split the result
            if '$' in val:
                val = shell.expansion_manager.expand_string_variables(val)
                result.extend(val.split())
            else:
                result.append(val)
    return result
