"""Tokenizer for shell arithmetic expressions."""

from typing import List, Optional

from .tokens import ArithToken, ArithTokenType


class ArithTokenizer:
    """Tokenizer for arithmetic expressions"""

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
        if prev in (ArithTokenType.IDENTIFIER, ArithTokenType.RBRACKET):
            return True  # postfix position
        i = self.position + 2
        while i < len(self.expr) and self.expr[i].isspace():
            i += 1
        return i < len(self.expr) and (self.expr[i].isalpha()
                                       or self.expr[i] == '_')

    # -- Main loop -----------------------------------------------------------

    def tokenize(self) -> List[ArithToken]:
        """Tokenize the arithmetic expression"""
        while self.position < len(self.expr):
            self.skip_whitespace()

            if self.position >= len(self.expr):
                break

            start_pos = self.position
            char = self.current_char()

            # Numbers
            if char and char.isdigit():
                value = self.read_number()
                self.tokens.append(ArithToken(ArithTokenType.NUMBER, value, start_pos))

            # Identifiers
            elif char and (char.isalpha() or char == '_'):
                ident = self.read_identifier()
                self.tokens.append(ArithToken(ArithTokenType.IDENTIFIER, ident, start_pos))

            # Operators and delimiters
            elif char == '+':
                if self.peek_char() == '+' and self._pair_is_incdec():
                    self.tokens.append(ArithToken(ArithTokenType.INCREMENT, '++', start_pos))
                    self.advance()
                    self.advance()
                elif self.peek_char() == '=':
                    self.tokens.append(ArithToken(ArithTokenType.PLUS_ASSIGN, '+=', start_pos))
                    self.advance()
                    self.advance()
                else:
                    # Includes a '++' pair that is NOT an increment (see
                    # _pair_is_incdec): emit ONE sign and rescan the second.
                    self.tokens.append(ArithToken(ArithTokenType.PLUS, '+', start_pos))
                    self.advance()

            elif char == '-':
                if self.peek_char() == '-' and self._pair_is_incdec():
                    self.tokens.append(ArithToken(ArithTokenType.DECREMENT, '--', start_pos))
                    self.advance()
                    self.advance()
                elif self.peek_char() == '=':
                    self.tokens.append(ArithToken(ArithTokenType.MINUS_ASSIGN, '-=', start_pos))
                    self.advance()
                    self.advance()
                else:
                    # A '--' pair that is not a decrement splits here, and
                    # the second '-' is rescanned — so `3---x` tokenizes as
                    # `3 - --x` (bash: -1 with x decremented).
                    self.tokens.append(ArithToken(ArithTokenType.MINUS, '-', start_pos))
                    self.advance()

            elif char == '*':
                if self.peek_char() == '*':
                    self.tokens.append(ArithToken(ArithTokenType.POWER, '**', start_pos))
                    self.advance()
                    self.advance()
                elif self.peek_char() == '=':
                    self.tokens.append(ArithToken(ArithTokenType.MULTIPLY_ASSIGN, '*=', start_pos))
                    self.advance()
                    self.advance()
                else:
                    self.tokens.append(ArithToken(ArithTokenType.MULTIPLY, '*', start_pos))
                    self.advance()

            elif char == '/':
                if self.peek_char() == '=':
                    self.tokens.append(ArithToken(ArithTokenType.DIVIDE_ASSIGN, '/=', start_pos))
                    self.advance()
                    self.advance()
                else:
                    self.tokens.append(ArithToken(ArithTokenType.DIVIDE, '/', start_pos))
                    self.advance()

            elif char == '%':
                if self.peek_char() == '=':
                    self.tokens.append(ArithToken(ArithTokenType.MODULO_ASSIGN, '%=', start_pos))
                    self.advance()
                    self.advance()
                else:
                    self.tokens.append(ArithToken(ArithTokenType.MODULO, '%', start_pos))
                    self.advance()

            elif char == '<':
                if self.peek_char() == '<':
                    if self.peek_char(2) == '=':
                        self.tokens.append(ArithToken(ArithTokenType.LSHIFT_ASSIGN, '<<=', start_pos))
                        self.advance()
                        self.advance()
                        self.advance()
                    else:
                        self.tokens.append(ArithToken(ArithTokenType.LSHIFT, '<<', start_pos))
                        self.advance()
                        self.advance()
                elif self.peek_char() == '=':
                    self.tokens.append(ArithToken(ArithTokenType.LE, '<=', start_pos))
                    self.advance()
                    self.advance()
                else:
                    self.tokens.append(ArithToken(ArithTokenType.LT, '<', start_pos))
                    self.advance()

            elif char == '>':
                if self.peek_char() == '>':
                    if self.peek_char(2) == '=':
                        self.tokens.append(ArithToken(ArithTokenType.RSHIFT_ASSIGN, '>>=', start_pos))
                        self.advance()
                        self.advance()
                        self.advance()
                    else:
                        self.tokens.append(ArithToken(ArithTokenType.RSHIFT, '>>', start_pos))
                        self.advance()
                        self.advance()
                elif self.peek_char() == '=':
                    self.tokens.append(ArithToken(ArithTokenType.GE, '>=', start_pos))
                    self.advance()
                    self.advance()
                else:
                    self.tokens.append(ArithToken(ArithTokenType.GT, '>', start_pos))
                    self.advance()

            elif char == '=':
                if self.peek_char() == '=':
                    self.tokens.append(ArithToken(ArithTokenType.EQ, '==', start_pos))
                    self.advance()
                    self.advance()
                else:
                    self.tokens.append(ArithToken(ArithTokenType.ASSIGN, '=', start_pos))
                    self.advance()

            elif char == '!':
                if self.peek_char() == '=':
                    self.tokens.append(ArithToken(ArithTokenType.NE, '!=', start_pos))
                    self.advance()
                    self.advance()
                else:
                    self.tokens.append(ArithToken(ArithTokenType.NOT, '!', start_pos))
                    self.advance()

            elif char == '&':
                if self.peek_char() == '&':
                    self.tokens.append(ArithToken(ArithTokenType.AND, '&&', start_pos))
                    self.advance()
                    self.advance()
                elif self.peek_char() == '=':
                    self.tokens.append(ArithToken(ArithTokenType.BIT_AND_ASSIGN, '&=', start_pos))
                    self.advance()
                    self.advance()
                else:
                    self.tokens.append(ArithToken(ArithTokenType.BIT_AND, '&', start_pos))
                    self.advance()

            elif char == '|':
                if self.peek_char() == '|':
                    self.tokens.append(ArithToken(ArithTokenType.OR, '||', start_pos))
                    self.advance()
                    self.advance()
                elif self.peek_char() == '=':
                    self.tokens.append(ArithToken(ArithTokenType.BIT_OR_ASSIGN, '|=', start_pos))
                    self.advance()
                    self.advance()
                else:
                    self.tokens.append(ArithToken(ArithTokenType.BIT_OR, '|', start_pos))
                    self.advance()

            elif char == '^':
                if self.peek_char() == '=':
                    self.tokens.append(ArithToken(ArithTokenType.BIT_XOR_ASSIGN, '^=', start_pos))
                    self.advance()
                    self.advance()
                else:
                    self.tokens.append(ArithToken(ArithTokenType.BIT_XOR, '^', start_pos))
                    self.advance()

            elif char == '~':
                self.tokens.append(ArithToken(ArithTokenType.BIT_NOT, '~', start_pos))
                self.advance()

            elif char == '?':
                self.tokens.append(ArithToken(ArithTokenType.QUESTION, '?', start_pos))
                self.advance()

            elif char == ':':
                self.tokens.append(ArithToken(ArithTokenType.COLON, ':', start_pos))
                self.advance()

            elif char == ',':
                self.tokens.append(ArithToken(ArithTokenType.COMMA, ',', start_pos))
                self.advance()

            elif char == '(':
                self.tokens.append(ArithToken(ArithTokenType.LPAREN, '(', start_pos))
                self.advance()

            elif char == ')':
                self.tokens.append(ArithToken(ArithTokenType.RPAREN, ')', start_pos))
                self.advance()

            elif char == '[':
                self.tokens.append(ArithToken(ArithTokenType.LBRACKET, '[', start_pos))
                self.advance()

            elif char == ']':
                self.tokens.append(ArithToken(ArithTokenType.RBRACKET, ']', start_pos))
                self.advance()

            elif char == '"':
                # bash tolerates double-quoted operands inside $(( )): the quotes
                # are stripped and the inner content tokenized normally.
                self.advance()

            else:
                raise SyntaxError(f"Unexpected character '{char}' at position {start_pos}")

        # Add EOF token
        self.tokens.append(ArithToken(ArithTokenType.EOF, '', self.position))
        return self.tokens
