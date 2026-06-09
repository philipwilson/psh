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


def _expand_initializer_text(text: str, shell: 'Shell') -> str:
    """Strip one level of quotes and expand per bash quoting rules.

    Single-quoted text stays literal; double-quoted or unquoted text is
    expanded (no word splitting — used where the token boundary is fixed,
    e.g. associative-array keys and values).
    """
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        return text[1:-1]
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1]
    if '$' in text:
        text = shell.expansion_manager.expand_string_variables(text)
    return text


def _split_assoc_tokens(content: str) -> List[str]:
    """Split ``[k]="v 1" [j]=w`` on whitespace outside quotes.

    shlex cannot be used here: its non-POSIX mode does not group quotes
    that start mid-token (after ``]=``), and its POSIX mode strips the
    quotes we need to distinguish literal from expandable text.
    """
    tokens: List[str] = []
    cur = ''
    quote = None
    for c in content:
        if quote:
            cur += c
            if c == quote:
                quote = None
        elif c in ('"', "'"):
            quote = c
            cur += c
        elif c.isspace():
            if cur:
                tokens.append(cur)
                cur = ''
        else:
            cur += c
    if cur:
        tokens.append(cur)
    return tokens


def parse_assoc_array_entries(value: str, shell: 'Shell'):
    """Parse an associative-array initializer ``([k]=v ["a b"]="v 2")``.

    Returns (key, value) pairs. Keys and values follow the same quoting
    rules as indexed elements: single quotes literal, double quotes /
    unquoted expanded; keys may be dynamic ([$k]=v).
    """
    content = value[1:-1].strip()
    if not content:
        return []
    parts = _split_assoc_tokens(content)

    result = []
    for part in parts:
        if not part.startswith('['):
            continue
        sep = part.find(']=', 1)
        if sep == -1:
            continue
        key = _expand_initializer_text(part[1:sep], shell)
        val = _expand_initializer_text(part[sep + 2:], shell)
        result.append((key, val))
    return result


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
