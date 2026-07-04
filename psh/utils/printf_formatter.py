"""Pure printf formatting engine (bash 5.2 semantics).

This module implements the printf FORMAT/argument processing used by the
``printf`` builtin (and ``print -f``).  It has **no shell dependency** —
it takes a format string and a list of argument strings and returns a
:class:`PrintfResult` — so it can be unit-tested directly, without
constructing a Shell.

Behavior is pinned to bash 5.2 by probe batteries (see
tests/unit/utils/test_printf_formatter.py):

- POSIX argument cycling: the format is applied at least once, then
  repeated while arguments remain.  Missing arguments format as ''/0.
- ``%*d`` / ``%.*f``: a ``*`` width or precision consumes the next
  argument.  A negative width left-justifies; a negative precision is
  treated as if omitted.
- Integer conversions accept base-prefixed constants (``0x1A``, ``010``)
  and the leading-quote form (``"A`` / ``'A`` -> 65).  Trailing junk
  produces an ``invalid number`` diagnostic (exit status 1) but the
  parsed prefix is still used; out-of-range values clamp with a
  ``Result too large`` *warning* (exit status unchanged), matching
  strtoimax/strtoumax semantics.
- ``%n`` assigns the number of characters written so far to the named
  variable (returned in :attr:`PrintfResult.assignments` for the caller
  to apply); an invalid identifier is a fatal error.
- An invalid or missing conversion character is fatal: output produced
  so far is kept, processing stops, exit status 1.
- ``\\c`` in a ``%b`` argument terminates ALL output (exit status 0).
- Unknown escapes in the format keep their backslash (bash prints
  ``\\z`` literally; ``\\c`` is only special inside ``%b`` arguments).
"""

import math
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .escapes import process_percent_b_escapes, quote_printf_q, unicode_escape_char

INT64_MIN = -(2 ** 63)
INT64_MAX = 2 ** 63 - 1
UINT64_MAX = 2 ** 64 - 1

# Conversion characters the engine implements.  bash additionally
# implements %T via the %(datefmt)T form, handled separately.
_CONVERSIONS = 'diouxXeEfFgGaAcsbqn%'

# Length modifiers are parsed and ignored (bash accepts %ld, %lld, ...).
_LENGTH_MODIFIERS = 'hlLjzt'

_IDENTIFIER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

_FLOAT_RE = re.compile(
    r'[ \t\n\r\f\v]*[+-]?(?:'
    r'0[xX][0-9a-fA-F]+(?:\.[0-9a-fA-F]*)?(?:[pP][+-]?\d+)?'
    r'|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?'
    r'|[iI][nN][fF](?:[iI][nN][iI][tT][yY])?'
    r'|[nN][aA][nN]'
    r')')


@dataclass
class PrintfResult:
    """Outcome of formatting: text, status, diagnostics, %n assignments."""
    output: str
    exit_code: int
    errors: List[str] = field(default_factory=list)
    assignments: List[Tuple[str, str]] = field(default_factory=list)


class _FatalError(Exception):
    """Stops all processing; message reported, exit status 1 (bash)."""


class _TerminateOutput(Exception):
    """\\c inside a %b argument: stop all output, exit status 0 (bash)."""


@dataclass
class _Spec:
    """One parsed %-conversion with * width/precision already resolved."""
    flags: str
    width: Optional[int]
    precision: Optional[int]
    conversion: str


def format_printf(format_str: str, arguments: List[str]) -> PrintfResult:
    """Format ``arguments`` per ``format_str`` with bash 5.2 semantics."""
    return _PrintfEngine(format_str, arguments).run()


class _PrintfEngine:
    def __init__(self, format_str: str, arguments: List[str]):
        self.format = format_str
        self.args = list(arguments)
        self.arg_index = 0
        self.pieces: List[str] = []
        self.count = 0  # characters emitted so far (for %n)
        self.errors: List[str] = []
        self.assignments: List[Tuple[str, str]] = []
        self.exit_code = 0

    # ------------------------------------------------------------------
    # Driver

    def run(self) -> PrintfResult:
        try:
            # POSIX: apply the format at least once, then repeat it while
            # arguments remain.
            first_pass = True
            while first_pass or self.arg_index < len(self.args):
                first_pass = False
                consumed = self._apply_format_once()
                if not consumed:
                    # Format consumes no arguments: never cycle.
                    break
        except _FatalError as e:
            self.errors.append(str(e))
            self.exit_code = 1
        except _TerminateOutput:
            pass
        return PrintfResult(''.join(self.pieces), self.exit_code,
                            self.errors, self.assignments)

    def _apply_format_once(self) -> bool:
        """One pass over the format. Returns True if any argument was used."""
        fmt = self.format
        i = 0
        consumed_args = False
        while i < len(fmt):
            ch = fmt[i]
            if ch == '%':
                if fmt[i + 1:i + 2] == '%':
                    self._emit('%')
                    i += 2
                    continue
                if fmt[i + 1:i + 2] == '(':
                    # %(datefmt)T — strftime of an epoch argument (bash).
                    close = fmt.find(')T', i + 2)
                    if close == -1:
                        self._emit('%')
                        i += 1
                        continue
                    self._emit_time(fmt[i + 2:close])
                    consumed_args = True
                    i = close + 2
                    continue
                spec, i = self._parse_spec(i)
                if spec.conversion == '%':
                    # e.g. '%-%' — bash prints '%'.
                    self._emit('%')
                    continue
                self._emit_conversion(spec)
                consumed_args = True
            elif ch == '\\' and i + 1 < len(fmt):
                text, skip = _process_format_escape(fmt, i)
                self._emit(text)
                i += skip
            else:
                self._emit(ch)
                i += 1
        return consumed_args

    # ------------------------------------------------------------------
    # Spec parsing (with * resolution — consumes arguments in order)

    def _parse_spec(self, start: int) -> Tuple[_Spec, int]:
        """Parse the %-spec at ``start``; returns (spec, next_index).

        Width/precision given as ``*`` consume the next argument here, in
        order (width first, then precision), before the value argument.
        """
        fmt = self.format
        i = start + 1

        flags = ''
        while i < len(fmt) and fmt[i] in '-+# 0':
            if fmt[i] not in flags:
                flags += fmt[i]
            i += 1

        width: Optional[int] = None
        if i < len(fmt) and fmt[i] == '*':
            width = self._numeric_from_arg()
            i += 1
        else:
            digits = ''
            while i < len(fmt) and fmt[i].isdigit():
                digits += fmt[i]
                i += 1
            if digits:
                width = int(digits)

        precision: Optional[int] = None
        if i < len(fmt) and fmt[i] == '.':
            i += 1
            if i < len(fmt) and fmt[i] == '*':
                precision = self._numeric_from_arg()
                i += 1
            else:
                digits = ''
                while i < len(fmt) and fmt[i].isdigit():
                    digits += fmt[i]
                    i += 1
                precision = int(digits) if digits else 0  # bare '.' is 0

        # bash accepts (and ignores) C length modifiers: %ld, %lld, %zu, ...
        while i < len(fmt) and fmt[i] in _LENGTH_MODIFIERS:
            i += 1

        if i >= len(fmt):
            # bash: `%-5': missing format character (quotes the whole spec)
            raise _FatalError(
                f"`{fmt[start:i]}': missing format character")
        conv = fmt[i]
        if conv not in _CONVERSIONS:
            raise _FatalError(f"`{conv}': invalid format character")
        i += 1

        # bash: a negative * width means left-justify with the absolute
        # value; a negative precision is treated as if omitted.
        if width is not None and width < 0:
            if '-' not in flags:
                flags += '-'
            width = -width
        if precision is not None and precision < 0:
            precision = None

        return _Spec(flags, width, precision, conv), i

    def _numeric_from_arg(self) -> int:
        """Resolve a ``*`` width/precision from the next argument."""
        if self.arg_index >= len(self.args):
            return 0
        raw = self.args[self.arg_index]
        self.arg_index += 1
        return self._to_int(raw, signed=True)

    # ------------------------------------------------------------------
    # Emission

    def _emit(self, text: str):
        self.pieces.append(text)
        self.count += len(text)

    def _next_arg(self) -> str:
        """Next argument, '' once exhausted (POSIX missing-arg rule)."""
        if self.arg_index < len(self.args):
            value = self.args[self.arg_index]
            self.arg_index += 1
            return value
        self.arg_index += 1
        return ''

    def _emit_time(self, datefmt: str):
        """%(datefmt)T: strftime of an epoch-seconds argument."""
        if datefmt == '':
            datefmt = '%X'  # bash: an empty time format defaults to %X
        raw = self._next_arg()
        if raw in ('', '-1'):
            epoch = int(time.time())  # -1 / missing: now (bash)
        elif raw == '-2':
            epoch = int(time.time())  # -2: shell start time (approximated)
        else:
            epoch = self._to_int(raw, signed=True)
        self._emit(time.strftime(datefmt, time.localtime(epoch)))

    def _emit_conversion(self, spec: _Spec):
        conv = spec.conversion
        if conv == 'n':
            self._assign_count()
            return
        raw = self._next_arg()
        if conv == 's':
            formatted = _format_string(raw, spec)
        elif conv == 'b':
            expanded, terminate = process_percent_b_escapes(raw)
            formatted = _format_string(expanded, spec)
            if terminate:
                # \c in a %b argument stops ALL output (bash/POSIX).
                self._emit(formatted)
                raise _TerminateOutput()
        elif conv == 'q':
            formatted = _format_string(quote_printf_q(raw), spec)
        elif conv in 'diouxX':
            formatted = self._format_integer(raw, spec)
        elif conv in 'eEfFgGaA':
            formatted = self._format_float(raw, spec)
        else:  # 'c'
            formatted = _format_char(raw, spec)
        self._emit(formatted)

    def _assign_count(self):
        """%n: store the number of characters written so far."""
        if self.arg_index >= len(self.args):
            # Args exhausted (or empty name): bash skips silently.
            self.arg_index += 1
            return
        name = self.args[self.arg_index]
        self.arg_index += 1
        if name == '':
            return
        if not _IDENTIFIER_RE.match(name):
            raise _FatalError(f"`{name}': not a valid identifier")
        self.assignments.append((name, str(self.count)))

    # ------------------------------------------------------------------
    # Numeric argument parsing (strtoimax/strtoumax semantics)

    def _warn_invalid(self, text: str, kind: str = ''):
        label = f"invalid {kind} number" if kind else "invalid number"
        self.errors.append(f"{text}: {label}")
        self.exit_code = 1

    def _to_int(self, text: str, *, signed: bool) -> int:
        """Convert per bash printf getintmax/getuintmax rules."""
        if text == '':
            return 0
        if text[0] in '"\'':
            # POSIX: a leading quote means the next character's codepoint.
            return ord(text[1]) if len(text) > 1 else 0
        value, kind, end = _scan_integer(text)
        if value is None:
            self._warn_invalid(text)
            return 0
        if end != len(text):
            # Trailing junk: diagnostic, but the parsed prefix is used.
            self._warn_invalid(text, kind)
        if signed:
            if value > INT64_MAX or value < INT64_MIN:
                self.errors.append(f"warning: {text}: Result too large")
                value = INT64_MAX if value > INT64_MAX else INT64_MIN
        else:
            if value > UINT64_MAX or value < -UINT64_MAX:
                self.errors.append(f"warning: {text}: Result too large")
                value = UINT64_MAX
            value %= UINT64_MAX + 1  # negatives wrap (strtoumax)
        return value

    def _to_float(self, text: str) -> float:
        if text == '':
            return 0.0
        if text[0] in '"\'':
            return float(ord(text[1])) if len(text) > 1 else 0.0
        m = _FLOAT_RE.match(text)
        if not m:
            self._warn_invalid(text)
            return 0.0
        literal = m.group().strip()
        if m.end() != len(text):
            self._warn_invalid(text)
        try:
            if re.match(r'[+-]?0[xX]', literal):
                return float.fromhex(literal)
            return float(literal)
        except (ValueError, OverflowError):
            self._warn_invalid(text)
            return 0.0

    # ------------------------------------------------------------------
    # Conversion formatting

    def _format_integer(self, raw: str, spec: _Spec) -> str:
        conv = spec.conversion
        signed = conv in 'di'
        value = self._to_int(raw, signed=signed)

        if conv in 'di':
            body = str(value)
        elif conv == 'o':
            body = oct(value)[2:]
        elif conv == 'x':
            body = hex(value)[2:]
        elif conv == 'X':
            body = hex(value)[2:].upper()
        else:  # 'u'
            body = str(value)

        sign = ''
        if body.startswith('-'):
            sign, body = '-', body[1:]
        elif signed:
            if '+' in spec.flags:
                sign = '+'
            elif ' ' in spec.flags:
                sign = ' '

        # Precision: minimum digits (zero flag is ignored when given).
        if spec.precision is not None:
            body = body.zfill(spec.precision) if spec.precision else (
                '' if value == 0 else body)

        prefix = ''
        if '#' in spec.flags and value != 0:
            if conv == 'o' and not body.startswith('0'):
                prefix = '0'
            elif conv == 'x':
                prefix = '0x'
            elif conv == 'X':
                prefix = '0X'

        text = sign + prefix + body
        return _pad(text, spec, zero_ok=spec.precision is None,
                    sign_len=len(sign + prefix))

    def _format_float(self, raw: str, spec: _Spec) -> str:
        value = self._to_float(raw)
        conv = spec.conversion
        precision = 6 if spec.precision is None else spec.precision

        if conv in 'fF':
            body = f"{value:.{precision}f}"
            if conv == 'F':
                body = body.upper()
        elif conv in 'eE':
            body = f"{value:.{precision}e}"
            if conv == 'E':
                body = body.upper()
        elif conv in 'gG':
            body = f"{value:.{precision if precision else 1}g}"
            if conv == 'G':
                body = body.upper()
        else:  # aA — hexadecimal float (precision not implemented)
            body = _hex_float(value)
            if conv == 'A':
                body = body.upper()

        sign = ''
        if body.startswith('-'):
            sign, body = '-', body[1:]
        elif '+' in spec.flags:
            sign = '+'
        elif ' ' in spec.flags:
            sign = ' '
        text = sign + body
        return _pad(text, spec, zero_ok=True, sign_len=len(sign))


def _scan_integer(text: str) -> Tuple[Optional[int], str, int]:
    """strtol(base=0)-like scan of a longest valid integer prefix.

    Returns (value, kind, end_index); value is None when no conversion
    was possible.  ``kind`` ('', 'octal', 'hex') selects bash's
    diagnostic wording for partial conversions ("invalid octal number").
    """
    n = len(text)
    i = 0
    while i < n and text[i] in ' \t\n\r\f\v':
        i += 1
    sign = 1
    if i < n and text[i] in '+-':
        if text[i] == '-':
            sign = -1
        i += 1
    if i < n and text[i] == '0' and i + 1 < n and text[i + 1] in 'xX':
        j = i + 2
        while j < n and text[j] in '0123456789abcdefABCDEF':
            j += 1
        if j > i + 2:
            return sign * int(text[i + 2:j], 16), 'hex', j
        # "0x" with no digits: strtol parses just the "0".
        return 0, 'hex', i + 1
    if i < n and text[i] == '0':
        j = i
        while j < n and text[j] in '01234567':
            j += 1
        return sign * int(text[i:j], 8), 'octal', j
    if i < n and text[i].isdigit():
        j = i
        while j < n and text[j].isdigit():
            j += 1
        return sign * int(text[i:j]), '', j
    return None, '', i


def _format_string(value: str, spec: _Spec) -> str:
    if spec.precision is not None:
        value = value[:spec.precision]
    return _pad(value, spec, zero_ok=False)


def _format_char(value: str, spec: _Spec) -> str:
    # bash: %c prints the FIRST character of the argument ('%c' 65 -> '6');
    # an empty/missing argument produces a NUL byte.
    char = value[0] if value else '\0'
    return _pad(char, spec, zero_ok=False)


def _pad(text: str, spec: _Spec, *, zero_ok: bool, sign_len: int = 0) -> str:
    """Apply width/justification. zero_ok permits '0'-flag zero padding;
    sign_len is the length of a sign/base prefix that must stay leftmost."""
    width = spec.width or 0
    if width <= len(text):
        return text
    if '-' in spec.flags:
        return text.ljust(width)
    if zero_ok and '0' in spec.flags:
        head, body = text[:sign_len], text[sign_len:]
        return head + body.rjust(width - sign_len, '0')
    return text.rjust(width)


def _hex_float(value: float) -> str:
    """C-style %a for the common cases (precision unsupported)."""
    if math.isnan(value):
        return 'nan'
    if math.isinf(value):
        return 'inf' if value > 0 else '-inf'
    if value == 0:
        return '-0x0p+0' if math.copysign(1.0, value) < 0 else '0x0p+0'
    text = value.hex()  # e.g. '0x1.91eb851eb851fp+1'
    # Trim a trailing '.0...0' mantissa like C does ('0x1.0000...p+3' -> '0x1p+3')
    mantissa, _, exponent = text.partition('p')
    if '.' in mantissa:
        mantissa = mantissa.rstrip('0').rstrip('.')
    return f"{mantissa}p{exponent}"


def _process_format_escape(fmt: str, start: int) -> Tuple[str, int]:
    """Process one backslash escape in the FORMAT string (bash dialect).

    Unlike %b/echo -e, \\c is NOT special here (bash prints it
    literally), \\'/\\"/\\? drop their backslash, and octal is 1-3
    digits with NO special leading-0 rule (\\0101 -> '\\x08' + '1').
    Returns (text, chars_consumed).
    """
    next_char = fmt[start + 1]

    escape_map = {
        'a': '\a', 'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r',
        't': '\t', 'v': '\v',
        'e': '\x1b', 'E': '\x1b',  # bash extension
        '\\': '\\', '"': '"', "'": "'", '?': '?',
    }
    if next_char in escape_map:
        return escape_map[next_char], 2

    # Octal: \nnn (1-3 digits, no leading 0 required in the format dialect)
    if next_char in '01234567':
        j = start + 1
        while j < len(fmt) and j < start + 4 and fmt[j] in '01234567':
            j += 1
        return chr(int(fmt[start + 1:j], 8) % 256), j - start

    # Hex: \xhh (1-2 digits)
    if next_char == 'x':
        j = start + 2
        while j < len(fmt) and j < start + 4 and fmt[j] in '0123456789abcdefABCDEF':
            j += 1
        if j > start + 2:
            return chr(int(fmt[start + 2:j], 16)), j - start

    # Unicode: \uhhhh and \Uhhhhhhhh (bash accepts 1-4 / 1-8 hex digits)
    for marker, max_len in (('u', 4), ('U', 8)):
        if next_char == marker:
            j = start + 2
            while (j < len(fmt) and j - start - 2 < max_len
                   and fmt[j] in '0123456789abcdefABCDEF'):
                j += 1
            if j > start + 2:
                return unicode_escape_char(int(fmt[start + 2:j], 16)), j - start

    # Unknown escape: emit the backslash and leave the next character to
    # be re-scanned — it is usually a literal (printf 'a\zb' -> 'a\zb')
    # but bash lets '%' start a conversion here (printf '\%' -> '\' then
    # a "missing format character" error).
    return '\\', 1
