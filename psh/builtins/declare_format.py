"""Shared declare-style variable reporting.

One formatter for every builtin that prints variables in reusable
``declare`` form: ``declare -p``, ``declare`` listings, ``readonly -p``
and (value escaping) ``export -p``. Pure functions over ``Variable`` —
no shell dependency.
"""

from ..core.variables import AssociativeArray, IndexedArray, VarAttributes, Variable

# Attribute → flag char, in the order bash prints them.
# Empirically verified against bash 5: the order is `a A i n r t x l u`
# (note the case-fold flags l/u sort LAST, after every other attribute).
_FLAG_CHARS = (
    (VarAttributes.ARRAY, 'a'),
    (VarAttributes.ASSOC_ARRAY, 'A'),
    (VarAttributes.INTEGER, 'i'),
    (VarAttributes.NAMEREF, 'n'),
    (VarAttributes.READONLY, 'r'),
    (VarAttributes.TRACE, 't'),
    (VarAttributes.EXPORT, 'x'),
    (VarAttributes.LOWERCASE, 'l'),
    (VarAttributes.UPPERCASE, 'u'),
)


def escape_value(value: str) -> str:
    """Escape special characters in a value for double-quoted output."""
    # Escape backslashes first, then double quotes, dollar signs, and backticks
    value = value.replace('\\', '\\\\')
    value = value.replace('"', '\\"')
    value = value.replace('$', '\\$')
    value = value.replace('`', '\\`')
    return value


def format_declaration(var: Variable) -> str:
    """Format one variable as a reusable ``declare`` command."""
    flags = [char for attr, char in _FLAG_CHARS if var.attributes & attr]
    flag_str = f"-{''.join(flags)}" if flags else "--"

    # Declared-but-unset (``export FOO``): attributes only, no value
    # (bash: ``declare -x FOO``)
    if var.attributes & VarAttributes.UNSET:
        return f"declare {flag_str} {var.name}"

    if isinstance(var.value, IndexedArray):
        # declare -a name=([0]="val" [1]="val")
        elements = [f'[{idx}]="{escape_value(var.value.get(idx))}"'
                    for idx in var.value.indices()]
        value_str = f"=({' '.join(elements)})" if elements else "=()"
    elif isinstance(var.value, AssociativeArray):
        # declare -A name=([key]="val" [key2]="val2")
        elements = [f'[{key}]="{escape_value(val)}"'
                    for key, val in sorted(var.value.items())]
        value_str = f"=({' '.join(elements)})" if elements else "=()"
    else:
        value_str = f'="{escape_value(str(var.value))}"'

    return f"declare {flag_str} {var.name}{value_str}"


# The attribute filters ``declare -p<flags>`` selects on. NAMEREF is
# deliberately absent — psh has never filtered on -n here (bash's
# ``declare -pn`` lists only namerefs; preserved divergence, out of
# scope for a pure extraction).
_FILTER_OPTION_ATTRS = (
    ('readonly', VarAttributes.READONLY),
    ('export', VarAttributes.EXPORT),
    ('integer', VarAttributes.INTEGER),
    ('lowercase', VarAttributes.LOWERCASE),
    ('uppercase', VarAttributes.UPPERCASE),
    ('array', VarAttributes.ARRAY),
    ('assoc_array', VarAttributes.ASSOC_ARRAY),
    ('trace', VarAttributes.TRACE),
)


def matches_filter(var: Variable, options: dict) -> bool:
    """Does *var* carry every attribute the declare options select on?

    With no attribute options set, everything matches (plain
    ``declare -p`` lists all variables).
    """
    required = VarAttributes.NONE
    for key, attr in _FILTER_OPTION_ATTRS:
        if options.get(key, False):
            required |= attr
    return (var.attributes & required) == required
