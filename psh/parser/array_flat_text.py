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


def array_init_argv_key(flat_text: str) -> str:
    """The argv element a declaration builtin looks a ``name=(...)`` arg up by.

    The parser stores the array-init argument as one UNQUOTED literal Word whose
    text is ``flat_text``. Argument expansion runs a single unquoted-escape
    collapse over it before the builtin sees it, so the builtin's lookup argv is
    that collapse of ``flat_text`` — NOT ``flat_text`` verbatim. Keying the
    delivery map (``CommandExecutor._collect_array_inits``) by the verbatim text
    misses whenever an element's decoded value keeps a residual backslash
    (``arr=(a\\b)`` → flat text ``arr=(a\\b c)`` but argv ``arr=(a\b c)``), so
    declare mistook the compound assignment for a scalar (task #38 residual (i)).

    The flat text plays a DOUBLE role — it is BOTH this Word's literal (→ argv
    via one collapse) AND, via ``display_text()``, the lookup key — so key==argv
    demands ``flat_text`` be a FIXED POINT of the collapse, which a residual-
    backslash value can never be (``process_unquoted_element_escapes`` guards
    exactly that case to keep the LiteralPart correct). Computing the key AS the
    collapse resolves the double-role by construction and is idempotent on
    escape-free text, so ordinary arrays are byte-identical. This reopens the
    wave-3 (v0.687) "serializer-unfixable" ruling: the obstacle was the double
    role, breakable at the key rather than the flat text.

    Delegates to the ONE canonical unquoted-escape transform the expansion path
    is defined by (``WordExpander._process_unquoted_escapes``) so the key cannot
    drift from the real argv; the boolean it also returns (all-globs-escaped) is
    irrelevant to the string key.
    """
    from ..expansion.word_expander import WordExpander
    return WordExpander._process_unquoted_escapes(flat_text)[0]
