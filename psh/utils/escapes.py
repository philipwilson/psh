r"""Shared backslash-escape decoding and shell quoting.

The shell has SEVERAL escape dialects that look alike but differ on
purpose — this module houses the shared ones and documents the map so
nobody "deduplicates" behavior that bash itself keeps distinct:

- ``process_echo_escapes`` (here): the ``echo -e`` / ``print`` dialect
  (\n, \t, \xHH, \uHHHH, \0NNN octal, \c terminates output).
- printf format escapes: live in the printf builtin — printf's octal is
  \NNN without the leading 0 and ``%%`` handling is interleaved.
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

import re
from typing import Tuple


def process_echo_escapes(text: str) -> Tuple[str, bool]:
    """Process backslash escape sequences in ``text`` (echo -e dialect).

    Returns ``(processed_text, terminate)`` where ``terminate`` is True when a
    ``\\c`` sequence was found (output should stop and no trailing newline is
    added). Shared by the ``echo`` and ``print`` builtins so there is a single
    escape-handling implementation.
    """
    # Check for \c first (terminates output)
    if '\\c' in text:
        text = text[:text.index('\\c')]
        return text, True

    # First, protect double backslashes by replacing them temporarily
    # Use a placeholder that won't appear in normal text
    text = text.replace('\\\\', '\x01BACKSLASH\x01')

    # Process escape sequences
    replacements = [
        ('\\n', '\n'),
        ('\\t', '\t'),
        ('\\r', '\r'),
        ('\\b', '\b'),
        ('\\f', '\f'),
        ('\\a', '\a'),
        ('\\v', '\v'),
        ('\\e', '\x1b'),  # Escape character
        ('\\E', '\x1b'),  # Escape character (alternative)
    ]

    # Apply simple replacements
    for old, new in replacements:
        text = text.replace(old, new)

    # Handle hex sequences \xhh
    def replace_hex(match):
        hex_str = match.group(1)
        try:
            return chr(int(hex_str, 16))
        except ValueError:
            return match.group(0)
    text = re.sub(r'\\x([0-9a-fA-F]{1,2})', replace_hex, text)

    # Handle unicode sequences \uhhhh
    def replace_unicode4(match):
        hex_str = match.group(1)
        try:
            return chr(int(hex_str, 16))
        except ValueError:
            return match.group(0)
    text = re.sub(r'\\u([0-9a-fA-F]{4})', replace_unicode4, text)

    # Handle unicode sequences \Uhhhhhhhh
    def replace_unicode8(match):
        hex_str = match.group(1)
        try:
            return chr(int(hex_str, 16))
        except ValueError:
            return match.group(0)
    text = re.sub(r'\\U([0-9a-fA-F]{8})', replace_unicode8, text)

    # Handle octal sequences \nnn
    def replace_octal(match):
        octal_str = match.group(1)
        try:
            value = int(octal_str, 8)
            if value <= 255:  # Octal values should be in byte range
                return chr(value)
            else:
                return match.group(0)
        except ValueError:
            return match.group(0)
    # Match \0nnn format (with explicit 0) - up to 3 octal digits after \0
    # or \nnn where n starts with 0-3 (for values 0-255 in octal)
    text = re.sub(r'\\(0[0-7]{1,3}|[0-3][0-7]{2})', replace_octal, text)

    # Finally restore protected backslashes
    text = text.replace('\x01BACKSLASH\x01', '\\')

    return text, False


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
