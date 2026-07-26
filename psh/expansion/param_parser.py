"""THE parameter-expansion parser: ``${...}`` content -> ParameterExpansion.

This module is the single classifier for the text between ``${`` and ``}``.
It replaced four mutually-dependent parser copies (v0.320 / Textbook B5):
the WordBuilder operator scan (parser side), ``parse_expansion`` in
parameter_expansion.py (runtime re-parse), the pre-dispatch ladder in
variable.py's ``expand_variable``, and the ``_parse_trailing_op`` rebake in
fields.py. It imports only the AST node — no shell state — so both the
parser (WordBuilder) and the string-expansion entry point
(``expand_variable``) can share it.

Grammar reference — every recognized form, one example each
============================================================

Plain parameters (operator None; evaluation resolves the name):
    ``${var}``            -> ('var', None, None)
    ``${@}`` ``${*}``     -> ('@', None, None) — special parameters,
    ``${?}`` ``${5}``        digits, '-', '$', '!' likewise
    ``${arr[3]}``         -> ('arr[3]', None, None) — subscript kept in the
    ``${arr[@]}``            parameter (brackets balance through nesting:
    ``${a[x,y]}``            ``${arr[arr[0]+1]}``; assoc keys may hold any
                             chars: ``${h["k 1"]}``)

Length:
    ``${#var}``           -> ('var', '#', None)
    ``${#arr[@]}``        -> ('arr[@]', '#', None)
    ``${#}``              -> ('', '#', None) — number of positional params
    ``${#-}``             -> ('-', '#', None) — length of a special param
    ``#`` introduces a length form only when the rest is a whole parameter
    spec; otherwise '#' is itself the parameter: ``${#:-d}``/``${#-d}``
    -> ('#', ':-'/'-', 'd') (bash's disambiguation).

Indirection and name listing:
    ``${!var}``           -> ('var', '!', None)
    ``${!arr[0]}``        -> ('arr[0]', '!', None) — via an array element
    ``${!#}``             -> ('#', '!', None) — special-parameter indirection
    ``${!arr[@]}``        -> ('arr[@]', '!', None) — array keys/indices
    ``${!prefix*}``       -> ('prefix', '!*', '') — names, IFS-joined
    ``${!prefix@}``       -> ('prefix', '!@', '') — names, space-joined
    ``${!name<op>w}`` scans like any parameter; the evaluator resolves the
    indirection first: ``${!v:-d}`` -> ('!v', ':-', 'd').

Operators found by the scan (parameter is everything before the operator):
    defaults     ``${v:-d}`` ``${v:=d}`` ``${v:?m}`` ``${v:+a}``
                 and unset-only ``${v-d}`` ``${v=d}`` ``${v?m}`` ``${v+a}``
    slice        ``${v:2}`` ``${v:2:3}`` ``${v: -3}`` ``${arr[@]:1:2}``
                 (operand kept verbatim: ('arr[@]', ':', '1:2'))
    remove       ``${v#p}`` ``${v##p}`` ``${v%p}`` ``${v%%p}``
    substitute   ``${v/p/r}`` ``${v//p/r}`` ``${v/#p/r}`` ``${v/%p/r}``
                 (operand is the raw 'pattern/replacement' text)
    case-mod     ``${v^}`` ``${v^^}`` (upper) ``${v,}`` ``${v,,}`` (lower)
                 ``${v~}`` ``${v~~}`` (toggle) with optional pattern:
                 ``${v,,pattern}`` (an absent pattern yields word '' — the
                 evaluator defaults it to '?')
    transform    ``${v@Q}`` — '@' + one of QEPAUuLakK in final position
                 (final position distinguishes it from a literal '@')

Operand text is NEVER parsed here — quotes, nesting, and inner expansions
(``${v:-${w:-x}}``, ``${v:-"a b"}``, ``${v#"$w"}``) are evaluated later by
the operand mini-expanders; the scan stops at the first operator.

Scan strategy: earliest position wins, longest operator at that position.
"Longest at the position" is what disambiguates ``${v:-d}`` (the ':-'
use-default operator) from ``${v:2}`` (the ':' slice): both start with
':' at position 1, so ':-' must be tried before ':' — a shortest-first or
unordered scan would read ``${v:-d}`` as a slice with offset '-d'.
"Earliest position" is what keeps operator characters inside an operand
from matching: in ``${v:-x@Q}`` the ':-' at position 1 beats the trailing
'@Q', so the operand is the literal 'x@Q' (bash).

Positions inside bracket subscripts never match: ``${a[x,y]^^}`` is a
case-mod of element 'a[x,y]', not a ',' operator (depth tracking, so
``${arr[arr[0]+1]}`` stays plain), and an unclosed bracket suppresses the
scan entirely (``${a[x:-d`` is a plain — unset — name, as before).

Known representational choices (pinned by the differential corpus):
    * ``${#}`` is ('', '#', None) (not ('#', '#', '')) — both evaluate to
      the positional count; this one round-trips through str().
    * ``${!@}``/``${!*}`` are ('', '!@'/'!*', '') — prefix listing with an
      empty prefix (every variable name), preserving historical behavior.
    * For substitutions without '/', the operand has no trailing '/'
      appended (('v', '/', 'p') for ``${v/p}``); the evaluator's
      pattern/replacement splitter treats both spellings identically.
"""
from ..ast_nodes import ParameterExpansion
from ..lexer.cmdsub_scanner import find_command_substitution_end
from ..lexer.unicode_support import is_valid_name

# One transform letter may follow '@' in final position: ${v@Q} etc.
# ANY letter parses as a transform operator (bash): an UNKNOWN letter is
# not a parse error — ${unset@Z} expands to '' silently, and only a SET
# variable makes ${x@Z} a runtime "bad substitution" (probe-verified,
# bash 5.2; the set-ness check lives in the operator application).
# The known letters are what _apply_transform implements:
TRANSFORM_LETTERS = 'QEPAUuLakK'

# Two-character operators, tried before any one-character operator at the
# same position. '/#', '/%', '//' are handled by the '/' lookahead below.
_TWO_CHAR_OPS = (':-', ':=', ':?', ':+', '##', '%%', '^^', ',,', '~~')

# One-character operators. '~' is the case-toggle case-mod (sibling of the
# ^ upper and , lower one-char ops; the doubled '~~' is in _TWO_CHAR_OPS).
_ONE_CHAR_OPS = '#%:-=+?^,~'

_SPECIAL_PARAM_CHARS = '@*#?$!-'


def _is_identifier(name: str) -> bool:
    """A valid variable identifier.

    Routed through the shell's single identifier policy
    (``unicode_support.is_valid_name``) so ``${NAME}`` classification agrees
    with the lexer and every other name site. This runs at PARSE time, where
    the runtime ``set -o posix`` state is not yet available, so the lenient
    (non-posix) rule is used; the posix ASCII restriction is enforced at the
    runtime name-declaration sites (assignment, declare, read, ...).
    """
    return is_valid_name(name, posix_mode=False)


def _skip_single_quote(text: str, i: int) -> int:
    """Index just past the ``'`` closing the one at *i*, or -1 (no escapes)."""
    j = text.find("'", i + 1)
    return j + 1 if j >= 0 else -1


def _skip_double_quote(text: str, i: int) -> int:
    """Index just past the ``"`` closing the one at *i*, or -1.

    A backslash escapes the next character (``\\"`` does not close); embedded
    ``$(...)``/``${...}``/backtick extents are skipped so their ``"`` do not
    close the outer string (``"$(echo "x")"`` and ``"`echo "x"`"`` are each
    ONE double-quoted region in bash — backticks stay ACTIVE inside dq and
    may contain quotes; round-1 R1-8).
    """
    n = len(text)
    j = i + 1
    while j < n:
        c = text[j]
        if c == '\\' and j + 1 < n:
            j += 2
            continue
        if c == '"':
            return j + 1
        if c == '`':
            j = _skip_backtick(text, j)
            if j == -1:
                return -1
            continue
        if c == '$' and j + 1 < n and text[j + 1] == '(':
            j, _found = find_command_substitution_end(text, j + 2)
            continue
        if c == '$' and j + 1 < n and text[j + 1] == '{':
            j = _skip_braces(text, j + 1)
            if j == -1:
                return -1
            continue
        j += 1
    return -1


def _skip_ansi_c_quote(text: str, i: int) -> int:
    """Index just past the ``$'...'`` span whose ``$`` is at *i*, or -1.

    A backslash escapes the next character (``\\'`` does not close)."""
    n = len(text)
    j = i + 2
    while j < n:
        if text[j] == '\\' and j + 1 < n:
            j += 2
            continue
        if text[j] == "'":
            return j + 1
        j += 1
    return -1


def _skip_backtick(text: str, i: int) -> int:
    """Index just past the `` ` `` closing the one at *i*, or -1 (backslash
    escapes)."""
    n = len(text)
    j = i + 1
    while j < n:
        if text[j] == '\\' and j + 1 < n:
            j += 2
            continue
        if text[j] == '`':
            return j + 1
        j += 1
    return -1


def _skip_braces(text: str, i: int) -> int:
    """Index just past the ``}`` matching the ``{`` at *i*, or -1.

    Quote- and escape-aware (a ``}`` inside ``'...'``/``"..."``/``$'...'`` or
    after ``\\`` does not close), so ``${h["}"]}`` spans correctly."""
    n = len(text)
    depth = 0
    j = i
    while j < n:
        c = text[j]
        if c == '\\' and j + 1 < n:
            j += 2
            continue
        if c == "'":
            j = _skip_single_quote(text, j)
            if j == -1:
                return -1
            continue
        if c == '"':
            j = _skip_double_quote(text, j)
            if j == -1:
                return -1
            continue
        if c == '$' and j + 1 < n and text[j + 1] == "'":
            j = _skip_ansi_c_quote(text, j)
            if j == -1:
                return -1
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return -1


def find_subscript_end(text: str, open_idx: int) -> int:
    """Index of the ``]`` closing the ``[`` at *open_idx*, or -1. THE
    quote-aware subscript extent scanner (remediation 2.3, MEDIUM-4).

    bash's assignment-word and ``${arr[...]}`` scans respect quoting when
    finding a subscript's closing bracket (probe-verified, bash 5.2):
    ``a["]"]=ok`` keys ``]``; ``${a["]"]}`` reads it back. This is the ONE
    extent rule shared by the runtime ``${...}`` classifier (this module),
    the parser word builder, and both parsers' array-assignment heads —
    replacing four quote-blind ``index(']')``/depth-count copies.

    Skips (a ``]`` inside none of these closes): ``'...'``, ``"..."`` (with
    ``\\`` escapes and embedded expansion extents), ``$'...'``, ``\\x``
    escapes, ``$(...)`` via the lexer's grammar-aware scanner (a quoted or
    case-pattern ``]``/``)`` inside a command substitution is not an extent
    boundary), ``${...}`` brace spans, and `` `...` `` backticks. Unquoted
    ``[``/``]`` nest (``c[b[i]]=N`` addresses ``c[b[i]]``). An unclosed
    construct yields -1 (no extent — callers treat the text as not a
    subscripted form, exactly as before for an unclosed bare bracket).
    """
    n = len(text)
    depth = 0
    i = open_idx
    while i < n:
        c = text[i]
        if c == '\\' and i + 1 < n:
            i += 2
            continue
        if c == "'":
            i = _skip_single_quote(text, i)
            if i == -1:
                return -1
            continue
        if c == '"':
            i = _skip_double_quote(text, i)
            if i == -1:
                return -1
            continue
        if c == '`':
            i = _skip_backtick(text, i)
            if i == -1:
                return -1
            continue
        if c == '$' and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "'":
                i = _skip_ansi_c_quote(text, i)
                if i == -1:
                    return -1
                continue
            if nxt == '(':
                i, found = find_command_substitution_end(text, i + 2)
                if not found:
                    return -1
                continue
            if nxt == '{':
                i = _skip_braces(text, i + 1)
                if i == -1:
                    return -1
                continue
        if c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _subscript_end(content: str, start: int) -> int:
    """Index of the ']' closing the '[' at *start*, or -1 (quote- and
    nesting-aware — see :func:`find_subscript_end`)."""
    return find_subscript_end(content, start)


def _is_param_spec(text: str) -> bool:
    """Whether *text* is a complete parameter spec (and nothing more).

    A spec is: a valid identifier, an identifier followed by one balanced
    subscript spanning to the end (``arr[3]``, ``a[x,y]``, ``arr[@]``),
    digits, or a single special-parameter character. Used to disambiguate
    the ``${#param}`` length form from '#'-as-parameter (``${#:-d}``).
    """
    if not text:
        return False
    if text.isdigit():
        return True
    if len(text) == 1 and text in _SPECIAL_PARAM_CHARS:
        return True
    bracket = text.find('[')
    if bracket == -1:
        return _is_identifier(text)
    return (_is_identifier(text[:bracket])
            and _subscript_end(text, bracket) == len(text) - 1)


def _scan_operator(content: str):
    """Find the operator: earliest position, longest at that position.

    Returns (operator, position) or (None, -1). Scanning starts at 1 (an
    operator needs a non-empty parameter before it) and skips positions
    inside bracket subscripts.
    """
    n = len(content)
    i = 0
    while i < n:
        c = content[i]
        if c == '[':
            # Jump past the whole (quote-aware) subscript extent: operator
            # characters inside it never match (${a[x,y]^^} case-mods the
            # element a[x,y]; ${a["]"]:-d} finds ':-' AFTER the quoted ']').
            # An unclosed bracket suppresses the scan entirely (${a[x:-d is a
            # plain — unset — name, as before).
            end = find_subscript_end(content, i)
            if end == -1:
                return None, -1
            i = end + 1
            continue
        if i == 0:
            i += 1
            continue
        # ${param@...}: '@' + everything to the end is a transform operand.
        # bash accepts ANY operand here — empty, multi-char, punctuation
        # (${x@}, ${x@ZZ}, ${x@9}, ${x@_}): on an UNSET parameter the whole
        # expansion is silently empty; on a SET parameter anything but a
        # known single letter is a fatal bad substitution (probe-verified,
        # bash 5.2 — see TRANSFORM_LETTERS). The one exclusion: a bang-
        # prefixed content ending in bare '@' is the ${!prefix@} name
        # listing, not an empty transform.
        if c == '@' and not (content[0] == '!' and i == n - 1):
            return '@' + content[i + 1:], i
        if content[i:i + 2] in _TWO_CHAR_OPS:
            return content[i:i + 2], i
        if c == '/':
            nxt = content[i + 1] if i + 1 < n else ''
            if nxt in ('/', '#', '%'):
                return '/' + nxt, i
            return '/', i
        if c in _ONE_CHAR_OPS:
            return c, i
        i += 1
    return None, -1


# Operators that legitimately have an EMPTY parameter (parameter-less
# special forms): ${#} = positional count, ${!@}/${!*} = name listing of
# every variable. Every other operator requires a real parameter name.
_EMPTY_PARAM_OPERATORS = frozenset({'#', '!@', '!*'})


def validate_parameter_expansion(node: ParameterExpansion) -> bool:
    """Whether *node*'s parameter name is syntactically valid (bash).

    bash rejects a ``${...}`` whose parameter is empty (``${}``) or not a
    valid parameter spec (``${ }``, ``${1abc}``, ``${.foo}``, ``${:-x}``)
    with "bad substitution". A valid spec is an identifier, digits, a single
    special-parameter char, or an identifier with a balanced subscript
    (see _is_param_spec). Returns False for the bad-substitution cases.

    This is checked at EXPANSION time only (bash reports it at runtime, not
    when the enclosing command is merely parsed), so callers raise
    BadSubstitutionError; the parser itself never raises here.
    """
    param = node.parameter
    op = node.operator
    if param == '':
        # Empty parameter is valid only for the count / name-listing forms.
        return op in _EMPTY_PARAM_OPERATORS
    # Indirection (${!name...}): the name may live in the parameter with a
    # leading '!' (e.g. '!ref' for ${!ref:-d}) or already have been split
    # off into the '!' operator (param='ref' for ${!ref}). In the leading-'!'
    # case the remainder must be empty (${!} / ${!:-x} = last-bg-pid) or a
    # valid spec; ${!@}/${!*} prefix listing accepts any prefix.
    if op in ('!@', '!*'):
        return True
    if param.startswith('!'):
        rest = param[1:]
        return rest == '' or _is_param_spec(rest)
    return _is_param_spec(param)


def parse_parameter_expansion(content: str) -> ParameterExpansion:
    """Parse the content of a ``${...}`` expansion (braces removed).

    Returns a ParameterExpansion(parameter, operator, word) triple; see the
    module docstring for the full grammar and every emitted shape.
    """
    # Historical: a backslash-escaped '!' counts as '!' (string contexts).
    if content.startswith('\\!'):
        content = content[1:]

    if not content:
        return ParameterExpansion('', None, None)

    # ${!x} indirection of a special parameter — before the operator scan,
    # which would read '#'/'?'/'-' as an operator with parameter '!'.
    if len(content) == 2 and content[0] == '!' and content[1] in '#?$-!':
        return ParameterExpansion(content[1], '!', None)

    # ${!@} / ${!*}: name listing with an empty prefix (historical).
    if content in ('!@', '!*'):
        return ParameterExpansion('', '!' + content[1], '')

    # ${#param}: length, only when the rest is a whole parameter spec
    # (bash: ${#-} is the length of $-, but ${#-d} is $# with default 'd').
    if content == '#':
        return ParameterExpansion('', '#', None)
    if content[0] == '#' and _is_param_spec(content[1:]):
        return ParameterExpansion(content[1:], '#', None)

    operator, pos = _scan_operator(content)
    if operator is not None:
        word = content[pos + len(operator):]
        return ParameterExpansion(content[:pos], operator, word)

    # Bang forms without a scanned operator.
    if content[0] == '!' and len(content) > 1:
        rest = content[1:]
        if rest.endswith('*'):
            return ParameterExpansion(rest[:-1], '!*', '')
        if rest.endswith('@'):
            return ParameterExpansion(rest[:-1], '!@', '')
        if '[' in rest and rest.endswith(']'):
            bracket = rest.find('[')
            if (_is_identifier(rest[:bracket])
                    and _subscript_end(rest, bracket) == len(rest) - 1):
                # ${!arr[@]} keys, or ${!arr[idx]} element indirection —
                # the evaluator dispatches on the subscript.
                return ParameterExpansion(rest, '!', None)
        if all(c.isalnum() or c == '_' for c in rest):
            return ParameterExpansion(rest, '!', None)
        # Unrecognized '!...' text: fall through as a plain (unset) name.

    return ParameterExpansion(content, None, None)
