"""Shared helper for the array-initializer flat-text key (both parsers).

A ``declare -a arr=(...)`` argument carries a structured ``ArrayInitialization``
that the declaration builtins look up by the argument's *flat text* — the exact
argv element they receive. That argv element is the flat text after ARGUMENT
EXPANSION, which (the flat text being a single UNQUOTED literal) runs
``\\X -> X`` over the whole string. So a flat text built verbatim from the
source tokens (``arr=(a\\$b c)``) never equals the argv the builtin looks up by
(``arr=(a$b c)``), the lookup misses, and ``declare`` mistakes the array for a
scalar (``arr=([0]="(a$b c)")``).

Applying the SAME unquoted-escape removal when we build the flat text makes the
parse-time key equal the runtime argv BY CONSTRUCTION — for quoted, ANSI-C, and
plain elements alike, since expansion treats the whole flat text as one unquoted
literal regardless of the quotes embedded in it. The array's element VALUES are
built from the structured element Words (correct quoting), never from this text,
so collapsing its escapes only fixes the key.

Used by the recursive-descent (``recursive_descent/parsers/commands.py``) and
combinator (``combinators/commands/simple.py``) array-init paths, so one
function keeps both parsers' keys byte-identical.
"""


def process_unquoted_element_escapes(text: str) -> str:
    """Collapse unquoted backslash escapes (``\\X -> X``) as argv expansion does.

    Mirrors the string transform of ``WordExpander._process_unquoted_escapes``:
    every ``\\X`` becomes ``X`` (backslash dropped, next char kept); a lone
    trailing backslash is kept.

    The result is stored AS the flat-text key, which argv expansion then runs
    the same transform over once more, so the key equals the argv only when the
    collapsed text is a FIXED POINT — i.e. has no backslash left. That holds for
    ``\\$``, ``\\t``, ``\\'`` … (the escaped-dollar family this fixes). It does
    NOT hold for an escaped backslash (``a\\\\b`` -> ``a\\b``, still escaped):
    such a value has no escape-free unquoted spelling, so key==argv is
    unreachable through the flat text regardless — keep the verbatim text there
    so the outcome is no worse than leaving it uncollapsed (this residual-
    backslash element is a pre-existing, serializer-unfixable edge).
    """
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == '\\' and i + 1 < n:
            out.append(text[i + 1])
            i += 2
            continue
        out.append(text[i])
        i += 1
    collapsed = ''.join(out)
    return collapsed if '\\' not in collapsed else text
