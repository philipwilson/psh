"""Quoting and escaping decisions for the AST formatter.

The formatter reconstructs shell source from an AST (the text behind
``declare -f`` / ``type`` / ``$BASH_COMMAND`` / ``trap -p`` / ``--debug-ast``).
Emitting a stored value so it re-parses to the SAME bytes means re-escaping it
for whatever quoting context it lands in — inside ``"..."``, inside ``$'...'``
ANSI-C, or the quote-only-when-needed rule for a for/select ``in`` list item —
and re-wrapping a scalar in its original quotes.

These are the pure, stateless decision functions for that. They were inline
statics on ``FormatterVisitor``; collected here so the visitor reads as
orchestration and each rule is testable in isolation. Behavior is identical to
the former methods — no quoting decision or escape sequence changed.
"""

from ..utils.escapes import ansi_c_encode, has_control_char


def escape_double_quoted(text: str) -> str:
    r"""Re-escape a stored literal that will be re-wrapped in double quotes.

    Inside ``"..."`` the lexer unescapes only ``\"``, ``\``` and ``\\``
    (storing ``"``, `` ` ``, ``\``); it KEEPS the backslash before ``$``
    (``"a\$b"`` stores ``a\$b``) so the expansion phase can treat it as a
    literal ``$``. So the stored text is essentially source-form, and the
    OLD blanket ``\`` -> ``\\`` doubling corrupted ``\$`` into a live
    ``\`` + ``$expansion``. Re-emit so re-lexing yields the SAME stored
    text: escape a bare ``"`` and `` ` ``, and double a backslash only when
    it would otherwise pair with the following emitted char (another
    backslash, a `` ` ``/``"`` we are escaping, or the closing quote) into
    an unintended escape. A backslash before ``$`` (or any ordinary char)
    stays single — the lexer keeps it verbatim.
    """
    out = []
    n = len(text)
    for i, ch in enumerate(text):
        if ch == '"':
            out.append('\\"')
        elif ch == '`':
            out.append('\\`')
        elif ch == '\\':
            nxt = text[i + 1] if i + 1 < n else ''
            if nxt in ('`', '"', '\\', ''):
                out.append('\\\\')   # would form an escape with what follows
            else:
                out.append('\\')     # \$ , \n , ... kept verbatim by the lexer
        else:
            out.append(ch)
    return ''.join(out)


def escape_ansi_c(text: str) -> str:
    r"""Re-escape a decoded ``$'...'`` value for re-emission as ``$'...'``.

    The lexer DECODES the ANSI-C escapes into the stored value (``$'a\tb'``
    -> ``a<TAB>b``; ``$'q\'x'`` -> ``q'x``), so re-wrapping the raw value in
    ``$'...'`` would change it (a literal tab happens to survive, but a
    literal ``'`` closes the quote early). Re-encode backslash, single quote
    and control characters.
    """
    simple = {'\\': '\\\\', "'": "\\'", '\t': '\\t', '\n': '\\n',
              '\r': '\\r', '\a': '\\a', '\b': '\\b', '\f': '\\f',
              '\v': '\\v', '\x1b': '\\E'}
    out = []
    for ch in text:
        if ch in simple:
            out.append(simple[ch])
        elif ord(ch) < 32 or ord(ch) == 127:
            out.append(f'\\x{ord(ch):02x}')
        else:
            out.append(ch)
    return ''.join(out)


# Chars that force-quote a for/select list item: whitespace and the
# operators/quotes that would otherwise re-parse as syntax. Glob chars
# (`*?[]`), braces and `$` are deliberately NOT here — quoting them would
# suppress the globbing / brace / expansion the unquoted form performs.
WORD_LIST_FORCE_QUOTE = set(" \t\n;|&<>()'\"`")


def format_word_list_item(item: str) -> str:
    """Quote a for/select ``in`` list item only when needed (bash)."""
    if item == '':
        return '""'
    if any(c in WORD_LIST_FORCE_QUOTE for c in item):
        return '"' + escape_double_quoted(item) + '"'
    return item


def quote_scalar(text: str, quote_type) -> str:
    """Re-wrap a scalar (here-string word) in its original quotes."""
    if not quote_type:
        return text
    if quote_type == "$'":
        return f"$'{text}'"
    return f"{quote_type}{text}{quote_type}"


# --- Reusable variable/word serialization (bash `set`, plain `declare`,
# `declare -p`, `hash -l`). The ``$'...'`` encoder is the single authority
# ``ansi_c_encode`` in ``utils/escapes.py`` (imported at module top, shared
# with ``${var@Q}`` / ``printf %q``); this layer only adds the word-level
# single-quote wrapping around it. ------------------------------------------

# Characters that force single-quoting of a reusable word ANYWHERE in it
# (bash 5.2 ``sh_contains_shell_metas`` plus history ``!``; probe-verified).
# ``#`` and ``~`` force quoting only when they LEAD the word; control
# characters are handled by the ANSI-C path first.
_REUSE_META = frozenset(" !\"$&'()*;<>?[\\]^`{|}")


def quote_word_reuse(text: str) -> str:
    r"""Quote a word so it re-parses to itself — bash ``set`` / plain
    ``declare`` (no-arg) / ``hash -l`` style.

    Bare when it holds no shell-special character; ``$'...'`` (ANSI-C) when it
    holds a control character; otherwise single-quoted with ``'\''`` for
    embedded quotes. An EMPTY word becomes ``''`` (a standalone empty word must
    be quoted to survive a re-parse). For an assignment RHS, callers that want
    an empty value to stay bare (``x=``) test for ``''`` themselves.
    """
    if text == '':
        return "''"
    if has_control_char(text):
        return "$'" + ansi_c_encode(text) + "'"
    if text[0] in '#~' or any(c in _REUSE_META for c in text):
        return "'" + text.replace("'", "'\\''") + "'"
    return text
