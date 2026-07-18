"""Shared declare-style variable reporting.

One formatter for every builtin that prints variables in reusable
``declare`` form: ``declare -p``, ``declare`` listings, ``readonly -p``
and (value escaping) ``export -p``. Pure functions over ``Variable`` —
no shell dependency.
"""
from ..core.variables import AssociativeArray, IndexedArray, VarAttributes, Variable
from ..utils.escapes import ansi_c_encode, has_control_char
from ..utils.escapes import format_assoc_key as _format_assoc_key

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


def quote_scalar_double(value: str) -> str:
    """A scalar value for ``declare -p`` output: double-quoted, but ``$'...'``
    (ANSI-C) when it contains control characters — matching bash 5.2
    (``declare -- x=$'a\\nb'``). The shared ``$'...'`` encoder lives in
    ``utils/escapes.py`` (``ansi_c_encode``); this is the double-quote
    (``declare -p``) variant of the wrapping."""
    if has_control_char(value):
        return "$'" + ansi_c_encode(value) + "'"
    return '"' + escape_value(value) + '"'


def quote_array_element(value: str) -> str:
    """One array element for reusable output (``declare -p`` and ``set``):
    ``"..."`` normally, ``$'...'`` when it holds control characters
    (bash: ``declare -a a=([0]=$'p\\nq' [1]="r s")``)."""
    return quote_scalar_double(value)


def format_assoc_key(key: str) -> str:
    """Render an associative-array key for reusable ``declare -p`` output.

    Delegates to THE one key-rendering rule (``utils/escapes.py``:
    ``$'...'`` for control characters, double-quoted for shell-special or
    whole-string ``@``/``*``/``~`` keys, bare otherwise) shared with the
    ``@A``/``@K`` transforms, so a key renders identically on every reuse
    surface — bash does the same (campaign W2)."""
    return _format_assoc_key(key)


def format_declaration(var: Variable) -> str:
    """Format one variable as a reusable ``declare`` command."""
    flags = [char for attr, char in _FLAG_CHARS if var.attributes & attr]
    flag_str = f"-{''.join(flags)}" if flags else "--"

    # Declared-but-unset (``export FOO``): attributes only, no value
    # (bash: ``declare -x FOO``)
    if var.attributes & VarAttributes.UNSET:
        return f"declare {flag_str} {var.name}"

    value_str = _format_array_or_scalar(var)
    return f"declare {flag_str} {var.name}{value_str}"


def _format_array_or_scalar(var: Variable) -> str:
    """The ``=<value>`` tail shared by ``declare -p`` and the ``set`` /
    plain-``declare`` listing: array elements are double-quoted (``$'...'``
    for control chars), a scalar goes through *scalar_fn*."""
    if isinstance(var.value, IndexedArray):
        # declare -a name=([0]="val" [1]="val")
        elements = [f'[{idx}]={quote_array_element(var.value.get(idx) or "")}'
                    for idx in var.value.indices()]
        return f"=({' '.join(elements)})" if elements else "=()"
    if isinstance(var.value, AssociativeArray):
        # declare -A name=([key]="val" [key2]="val2" )  — note bash's trailing
        # space before ')' for associative arrays, and keys quoted only when
        # needed. (psh iterates sorted; bash uses hash order — an accepted,
        # deterministic divergence since bash's order is unspecified.)
        elements = [f'[{format_assoc_key(key)}]={quote_array_element(val)}'
                    for key, val in sorted(var.value.items())]
        return f"=({' '.join(elements)} )" if elements else "=()"
    return f"={quote_scalar_double(str(var.value))}"


def format_assignment_reuse(var: Variable) -> str:
    r"""Format one variable as bash's ``set`` / plain-``declare`` (no-arg)
    listing does: ``name=value`` with a SINGLE-QUOTED scalar (``$'...'`` for
    control chars), no ``declare`` prefix and no attribute flags. Arrays use
    the same ``([0]="..." ...)`` element form as ``declare -p``.

    An unset (declared-but-no-value) variable prints just its name (bash omits
    the ``=``). Probe-verified against bash 5.2: ``x='a b'``, ``x=$'a\nb'``,
    ``a=([0]="x y")``.
    """
    from ..visitor.formatter_quoting import quote_word_reuse
    if var.attributes & VarAttributes.UNSET:
        return var.name
    if isinstance(var.value, (IndexedArray, AssociativeArray)):
        return f"{var.name}{_format_array_or_scalar(var)}"
    s = str(var.value)
    # An empty scalar stays bare (bash: `x=`); a non-empty one is quote-when-
    # needed. quote_word_reuse('') would give `''`, wrong for an assignment RHS.
    return f"{var.name}={quote_word_reuse(s) if s else ''}"


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
