"""Tokenizer for shell arithmetic expressions."""

from typing import List, Optional

from .tokens import ArithToken, ArithTokenType


class ArithTokenizer:
    """Tokenizer for arithmetic expressions"""

    # Operator table, consulted by maximal munch (longest match wins): the
    # main loop tries the 3-, then 2-, then 1-character slice at the current
    # position against this one dict. ``++``/``--`` are deliberately absent —
    # they are context-sensitive (see _pair_is_incdec) and handled bespoke;
    # a ``++`` pair that is NOT an inc/dec therefore finds no entry here and
    # correctly splits into two single ``+`` tokens.
    _OPERATORS = {
        # 3-character
        '<<=': ArithTokenType.LSHIFT_ASSIGN,
        '>>=': ArithTokenType.RSHIFT_ASSIGN,
        # 2-character
        '**': ArithTokenType.POWER,
        '==': ArithTokenType.EQ,
        '!=': ArithTokenType.NE,
        '<=': ArithTokenType.LE,
        '>=': ArithTokenType.GE,
        '&&': ArithTokenType.AND,
        '||': ArithTokenType.OR,
        '<<': ArithTokenType.LSHIFT,
        '>>': ArithTokenType.RSHIFT,
        '+=': ArithTokenType.PLUS_ASSIGN,
        '-=': ArithTokenType.MINUS_ASSIGN,
        '*=': ArithTokenType.MULTIPLY_ASSIGN,
        '/=': ArithTokenType.DIVIDE_ASSIGN,
        '%=': ArithTokenType.MODULO_ASSIGN,
        '&=': ArithTokenType.BIT_AND_ASSIGN,
        '|=': ArithTokenType.BIT_OR_ASSIGN,
        '^=': ArithTokenType.BIT_XOR_ASSIGN,
        # 1-character
        '+': ArithTokenType.PLUS,
        '-': ArithTokenType.MINUS,
        '*': ArithTokenType.MULTIPLY,
        '/': ArithTokenType.DIVIDE,
        '%': ArithTokenType.MODULO,
        '<': ArithTokenType.LT,
        '>': ArithTokenType.GT,
        '=': ArithTokenType.ASSIGN,
        '!': ArithTokenType.NOT,
        '~': ArithTokenType.BIT_NOT,
        '&': ArithTokenType.BIT_AND,
        '|': ArithTokenType.BIT_OR,
        '^': ArithTokenType.BIT_XOR,
        '?': ArithTokenType.QUESTION,
        ':': ArithTokenType.COLON,
        ',': ArithTokenType.COMMA,
        '(': ArithTokenType.LPAREN,
        ')': ArithTokenType.RPAREN,
        '[': ArithTokenType.LBRACKET,
        ']': ArithTokenType.RBRACKET,
    }

    def __init__(self, expr: str):
        self.expr = expr
        self.position = 0
        self.tokens: List[ArithToken] = []

    def current_char(self) -> Optional[str]:
        if self.position >= len(self.expr):
            return None
        return self.expr[self.position]

    def peek_char(self, offset: int = 1) -> Optional[str]:
        pos = self.position + offset
        if pos >= len(self.expr):
            return None
        return self.expr[pos]

    def advance(self) -> None:
        self.position += 1

    def skip_whitespace(self) -> None:
        char = self.current_char()
        while char is not None and char in ' \t\n':
            self.advance()
            char = self.current_char()

    # -- Number reading ------------------------------------------------------

    def read_number(self) -> int:
        """Read a number (decimal, octal, hex, or base#number)"""
        start_pos = self.position

        # First, check for base#number notation by looking ahead for a # after
        # an initial run of digits.
        saved_pos = self.position
        base_str = ''
        char = self.current_char()
        while char is not None and char.isdigit():
            base_str += char
            self.advance()
            char = self.current_char()

        if self.current_char() == '#' and base_str:
            self.advance()  # Skip #
            return self._read_based_number(int(base_str), start_pos)

        # Not base#number, restore position and check other formats.
        self.position = saved_pos

        peeked = self.peek_char()
        if self.current_char() == '0' and peeked is not None and peeked.lower() == 'x':
            return self._read_hex(start_pos)

        if self.current_char() == '0':
            # A leading 0 introduces octal (bash); the 0 stays in the digit
            # run. A lone 0 or a 0 before an operator reads a single 0, while
            # a trailing out-of-base digit/letter (08, 0a, 07x) errors.
            return self._read_octal(start_pos)

        # Regular decimal
        return self._read_digits(10, start_pos)

    def _read_based_number(self, base: int, start_pos: int) -> int:
        """Read the digits of a base#number after the '#' has been consumed.

        Bash digit mapping depends on the base:
          base <= 36: 0-9, a-z/A-Z (case insensitive, 10-35)
          base > 36:  0-9, a-z (10-35), A-Z (36-61), @ (62), _ (63)
        """
        if base < 2 or base > 64:
            raise SyntaxError(f"Invalid base {base} at position {start_pos}")
        return self._read_digits(base, start_pos)

    def _read_digits(self, base: int, start_pos: int) -> int:
        """Read a maximal run of base-alphabet digits and return their value.

        Consumes the whole run of based-number characters ([0-9a-zA-Z@_],
        bash's alphabet) before validating, so a digit out of range for
        ``base`` errors as one token ("value too great for base") instead of
        silently ending the number and leaving a stray trailing token — bash
        reads 0xffg, 08, 0a, 123abc and 16#1g as single error tokens. The
        caller has already consumed any 0x / base# prefix; ``start_pos`` marks
        the start of the full token for the error message. A char outside the
        based-number alphabet (e.g. '.') ends the number.
        """
        result = 0
        num_len = 0
        out_of_range = False
        char = self.current_char()
        while char is not None and self._based_digit_value(char, 64) is not None:
            digit_val = self._based_digit_value(char, base)
            if digit_val is None or digit_val >= base:
                out_of_range = True
            else:
                result = result * base + digit_val
            num_len += 1
            self.advance()
            char = self.current_char()

        if num_len == 0:
            raise SyntaxError(f"Invalid base {base} number at position {start_pos}")
        if out_of_range:
            token = self.expr[start_pos:self.position]
            raise SyntaxError(
                f"{token}: value too great for base (error token is \"{token}\")"
            )

        return result

    @staticmethod
    def _based_digit_value(char: str, base: int) -> Optional[int]:
        """Map a single character to its digit value for base#number, or None."""
        if char.isdigit():
            return ord(char) - ord('0')
        if base <= 36:
            # Case-insensitive for bases 2-36
            upper = char.upper()
            if upper.isalpha() and 'A' <= upper <= 'Z':
                return ord(upper) - ord('A') + 10
            return None
        if char.islower():
            return ord(char) - ord('a') + 10
        if char.isupper():
            return ord(char) - ord('A') + 36
        if char == '@':
            return 62
        if char == '_':
            return 63
        return None

    def _read_hex(self, start_pos: int) -> int:
        """Read a hex literal (0x.. / 0X..); leading 0x already detected."""
        self.advance()  # Skip 0
        self.advance()  # Skip x
        # bash: a bare "0x"/"0X" with no following hex digits evaluates to 0.
        char = self.current_char()
        if char is None or self._based_digit_value(char, 64) is None:
            return 0
        return self._read_digits(16, start_pos)

    def _read_octal(self, start_pos: int) -> int:
        """Read an octal literal (leading 0 already detected, kept in the run)."""
        return self._read_digits(8, start_pos)

    def read_identifier(self) -> str:
        """Read an identifier (variable name)"""
        ident = ''
        char = self.current_char()
        # First character must be letter or underscore
        if char is not None and (char.isalpha() or char == '_'):
            ident += char
            self.advance()
            char = self.current_char()
            # Rest can be letters, digits, or underscore
            while char is not None and (char.isalnum() or char == '_'):
                ident += char
                self.advance()
                char = self.current_char()
        return ident

    def _pair_is_incdec(self) -> bool:
        """Whether a ``++``/``--`` PAIR at the current position is an
        increment/decrement token, following bash's expr.c readtok
        (probe-verified against bash 5.2):

        - POSTFIX when the PREVIOUS token is a variable or a closing
          subscript bracket (``x++``, ``a[0] ++`` — whitespace before the
          pair does not matter);
        - otherwise PREFIX when the next NON-WHITESPACE character after
          the pair starts an identifier (``++x``, ``3 ++ x`` — the latter
          is then a syntax error in binary position, exactly like bash);
        - otherwise NOT an inc/dec at all: the caller emits a single
          ``+``/``-`` and rescans the second sign char, which may re-pair
          (``$((++5))`` = +(+5) = 5; ``$((5 ++ 3))`` = 5 + (+3) = 8;
          ``$((3---x))`` = 3 - --x, decrementing x).
        """
        prev = self.tokens[-1].type if self.tokens else None
        if prev in (ArithTokenType.IDENTIFIER, ArithTokenType.SUBSCRIPT):
            return True  # postfix position (`x++`, `a[i]++`)
        i = self.position + 2
        while i < len(self.expr) and self.expr[i].isspace():
            i += 1
        return i < len(self.expr) and (self.expr[i].isalpha()
                                       or self.expr[i] == '_')

    def _read_subscript(self, ident: str) -> ArithToken:
        """Capture ``[ ... ]`` after an adjacent identifier, VERBATIM.

        The subscript's content is not arithmetic-tokenized: bash captures the
        raw text to the matching bracket (nesting counted, quote-blind — its
        own quote removal ran on the whole expression earlier) and only later
        interprets it by target kind: associative targets key on the raw text
        after quote removal; indexed targets lazily parse it as arithmetic.
        That is why ``$((h[a b]))`` and ``$((h[ foo ]))`` key ``a b`` and
        `` foo `` for an associative ``h`` — never stripped, never required to
        lex as arithmetic (r21 A3). An unclosed subscript is bash's
        "bad array subscript" error.
        """
        start_pos = self.position
        self.advance()  # consume '['
        depth = 1
        content_start = self.position
        while self.position < len(self.expr):
            ch = self.expr[self.position]
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    raw = self.expr[content_start:self.position]
                    self.advance()  # consume ']'
                    return ArithToken(ArithTokenType.SUBSCRIPT, raw, start_pos)
            self.advance()
        raise SyntaxError(
            f"{ident}[{self.expr[content_start:]}: bad array subscript")

    def _match_operator(self, start_pos: int) -> Optional[ArithToken]:
        """Return the longest ``_OPERATORS`` token starting at the current
        position (maximal munch: 3-char, then 2-char, then 1-char), consuming
        its characters — or ``None`` if nothing matches. ``++``/``--`` are NOT
        table entries; the caller handles them before calling this."""
        for length in (3, 2, 1):
            op = self.expr[self.position:self.position + length]
            if len(op) == length:
                ttype = self._OPERATORS.get(op)
                if ttype is not None:
                    for _ in range(length):
                        self.advance()
                    return ArithToken(ttype, op, start_pos)
        return None

    # -- Main loop -----------------------------------------------------------

    def tokenize(self) -> List[ArithToken]:
        """Tokenize the arithmetic expression.

        Numbers and identifiers have their own readers; every operator and
        delimiter is dispatched through the maximal-munch ``_OPERATORS`` table
        (longest match wins). Only two shapes stay bespoke: ``++``/``--``
        (context-sensitive, see _pair_is_incdec) and the double-quote skip.
        """
        while self.position < len(self.expr):
            self.skip_whitespace()

            if self.position >= len(self.expr):
                break

            start_pos = self.position
            char = self.current_char()

            # Numbers
            if char is not None and char.isdigit():
                value = self.read_number()
                self.tokens.append(ArithToken(ArithTokenType.NUMBER, value, start_pos))
                continue

            # Identifiers — an IMMEDIATELY following `[` starts an array
            # subscript, captured verbatim to the balanced `]` (see
            # _read_subscript). bash requires adjacency: `h [k]` is a syntax
            # error, not a subscript.
            if char is not None and (char.isalpha() or char == '_'):
                ident = self.read_identifier()
                self.tokens.append(ArithToken(ArithTokenType.IDENTIFIER, ident, start_pos))
                if self.current_char() == '[':
                    self.tokens.append(self._read_subscript(ident))
                continue

            # bash tolerates double-quoted operands inside $(( )): the quotes
            # are stripped and the inner content tokenized normally.
            if char == '"':
                self.advance()
                continue

            # ++ / -- : the one context-sensitive pair. When _pair_is_incdec
            # says yes, emit the inc/dec token; otherwise fall through to the
            # table, where the pair splits into two single-sign tokens (so
            # `3---x` tokenizes as `3 - --x`, bash: -1 with x decremented).
            if (char in ('+', '-') and self.peek_char() == char
                    and self._pair_is_incdec()):
                ttype = (ArithTokenType.INCREMENT if char == '+'
                         else ArithTokenType.DECREMENT)
                self.tokens.append(ArithToken(ttype, char * 2, start_pos))
                self.advance()
                self.advance()
                continue

            # Operators and delimiters: maximal munch over _OPERATORS.
            token = self._match_operator(start_pos)
            if token is None:
                raise SyntaxError(f"Unexpected character '{char}' at position {start_pos}")
            self.tokens.append(token)

        # Add EOF token
        self.tokens.append(ArithToken(ArithTokenType.EOF, '', self.position))
        return self.tokens
