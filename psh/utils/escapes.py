r"""Shared backslash-escape decoding and shell quoting.

The shell has SEVERAL escape dialects that look alike but differ on
purpose — this module houses the shared ones and documents the map so
nobody "deduplicates" behavior that bash itself keeps distinct:

- ``process_echo_escapes`` (here): the ``echo -e`` / ``print`` dialect.
  Octal REQUIRES the leading zero (``\0ddd``); ``\101`` stays literal.
- ``process_percent_b_escapes`` (here): the ``printf %b`` argument
  dialect.  Same scanner, but octal also accepts the bare POSIX form
  ``\ddd`` (``\101`` -> 'A').  Both dialects stop output at ``\c``
  AFTER processing everything before it.
- printf FORMAT-string escapes: live in printf_formatter (octal is
  1-3 digits with no special leading-0 rule, ``\'``/``\"``/``\?`` drop
  the backslash, ``\c`` is NOT special, and an unknown escape leaves
  the next character to be re-scanned — ``\%`` feeds ``%`` back to
  conversion parsing).
- ``read`` (no -r) backslashes: line continuation and IFS protection
  only, no C escapes — lives in the read builtin.
- ``[[ ]]`` operand escapes and word-level unquoted escapes: lexer/
  expansion concerns, not output formatting.

Likewise there are TWO reuse-as-input quoters because bash formats them
differently (verified against bash 5.2):

- ``quote_printf_q`` — ``printf %q``: backslash-escapes specials
  (``a\ b``); ANSI-C ``$'...'`` with \xHH only for control chars.
- ``quote_at_q`` — ``${var@Q}``: single-quoted form (``'a b'``);
  ANSI-C ``$'...'`` with \OOO octal for control chars.
"""

from typing import Tuple

_SIMPLE_ESCAPES = {
    'a': '\a', 'b': '\b', 'e': '\x1b', 'E': '\x1b', 'f': '\f',
    'n': '\n', 'r': '\r', 't': '\t', 'v': '\v', '\\': '\\',
}

_OCTAL_DIGITS = '01234567'
_HEX_DIGITS = '0123456789abcdefABCDEF'


def unicode_escape_char(value: int) -> str:
    r"""Best-effort ``chr()`` for \u/\U escape values.

    bash writes raw bytes here, so it can emit UTF-8-encoded surrogates
    and even codepoints past U+10FFFF; a Python str cannot survive the
    encode on output (the byte-model limitation, see
    docs/missing_features.md).  Emit nothing for those rather than
    crash at write time — bash itself emits nothing for values its own
    encoder rejects (e.g. ``\\UFFFFFFFF``).
    """
    if 0xD800 <= value <= 0xDFFF or value > 0x10FFFF:
        return ''
    return chr(value)


def process_echo_escapes(text: str) -> Tuple[str, bool]:
    r"""Process backslash escapes in ``text`` (echo -e / print dialect).

    Returns ``(processed_text, terminate)`` where ``terminate`` is True
    when a ``\c`` sequence was found (output stops there and no trailing
    newline is added).  Octal needs the leading zero: ``\0ddd``.
    """
    return _scan_escapes(text, bare_octal=False)


def process_percent_b_escapes(text: str) -> Tuple[str, bool]:
    r"""Process backslash escapes in a ``printf %b`` argument.

    Like the echo dialect, but octal also accepts the POSIX bare form
    ``\ddd`` (no leading zero required): ``\101`` -> 'A'.
    """
    return _scan_escapes(text, bare_octal=True)


def _scan_escapes(text: str, *, bare_octal: bool) -> Tuple[str, bool]:
    r"""One left-to-right pass over ``text`` decoding backslash escapes.

    Pinned to bash 5.2 (tmp/probes-r17t2-escapes truth table):

    - ``\c`` stops output where it stands; escapes BEFORE it are kept
      processed (``a\tb\cd`` -> 'a<TAB>b').  A ``\c`` whose backslash
      was already consumed (``\\\\c``) is literal '\' + 'c'.
    - Octal: ``\0`` plus up to 3 more octal digits, value mod 256
      (``\0777`` -> 0xFF); with ``bare_octal`` additionally ``\ddd``
      (1-3 digits, mod 256).  ``\8`` is never octal.
    - ``\xHH``: 1-2 hex digits; ``\uHHHH``: 1-4; ``\UHHHHHHHH``: 1-8
      (bash accepts SHORT forms: ``\u41`` -> 'A').
    - Unknown escapes (and ``\x``/``\u``/``\U`` with no hex digits)
      keep the backslash; a trailing lone backslash is literal.
    """
    out = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch != '\\' or i + 1 >= n:
            out.append(ch)
            i += 1
            continue
        c = text[i + 1]
        if c == 'c':
            return ''.join(out), True
        if c in _SIMPLE_ESCAPES:
            out.append(_SIMPLE_ESCAPES[c])
            i += 2
            continue
        if c == '0' or (bare_octal and c in _OCTAL_DIGITS):
            # \0 + up to 3 more octal digits ('\0' alone is NUL); the
            # bare \ddd form allows up to 3 digits total.
            max_digits = 4 if c == '0' else 3
            j = i + 1
            while j < n and j - i - 1 < max_digits and text[j] in _OCTAL_DIGITS:
                j += 1
            out.append(chr(int(text[i + 1:j], 8) % 256))
            i = j
            continue
        if c == 'x':
            j = i + 2
            while j < n and j - i - 2 < 2 and text[j] in _HEX_DIGITS:
                j += 1
            if j > i + 2:
                out.append(chr(int(text[i + 2:j], 16)))
                i = j
                continue
        elif c in 'uU':
            max_digits = 4 if c == 'u' else 8
            j = i + 2
            while j < n and j - i - 2 < max_digits and text[j] in _HEX_DIGITS:
                j += 1
            if j > i + 2:
                out.append(unicode_escape_char(int(text[i + 2:j], 16)))
                i = j
                continue
        # Unknown escape: keep the backslash and the character.
        out.append('\\')
        out.append(c)
        i += 2
    return ''.join(out), False


# Characters that never need quoting in %q output.
_Q_SAFE = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    "%+,-./:=@_"
)


def quote_printf_q(value: str) -> str:
    """Quote a string so it can be reused as shell input (printf %q).

    Mirrors bash: an empty string becomes ``''``; a string containing any
    control character is wrapped whole in the ANSI-C ``$'...'`` form;
    otherwise special characters are individually backslash-escaped
    (``a b`` -> ``a\\ b``).
    """
    if value == '':
        return "''"
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        named = {'\t': '\\t', '\n': '\\n', '\r': '\\r',
                 '\\': '\\\\', "'": "\\'"}
        body = []
        for ch in value:
            code = ord(ch)
            if ch in named:
                body.append(named[ch])
            elif code < 32 or code == 127:
                body.append(f"\\x{code:02x}")
            else:
                body.append(ch)
        return "$'" + ''.join(body) + "'"
    return ''.join(ch if ch in _Q_SAFE else '\\' + ch for ch in value)


def quote_at_q(s: str) -> str:
    """Quote a string so it can be reused as shell input (bash ${var@Q}).

    Empty -> ''. Strings with control characters use the $'...' ANSI-C
    form with octal escapes; otherwise a single-quoted form (``'a b'``)
    with embedded quotes escaped as ``'\\''``.
    """
    if s == '':
        return "''"
    if any(ord(c) < 32 or ord(c) == 127 for c in s):
        out = []
        simple = {'\n': '\\n', '\t': '\\t', '\r': '\\r', '\\': '\\\\',
                  "'": "\\'", '\a': '\\a', '\b': '\\b', '\f': '\\f',
                  '\v': '\\v'}
        for c in s:
            if c in simple:
                out.append(simple[c])
            elif ord(c) < 32 or ord(c) == 127:
                out.append('\\%03o' % ord(c))
            else:
                out.append(c)
        return "$'" + ''.join(out) + "'"
    return "'" + s.replace("'", "'\\''") + "'"
