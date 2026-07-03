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

        if self.current_char() == '0' and peeked is not None and peeked.isdigit():
            return self._read_octal(start_pos)

        # Regular decimal
        return self.read_decimal()

    def _read_based_number(self, base: int, start_pos: int) -> int:
        """Read the digits of a base#number after the '#' has been consumed.

        Bash digit mapping depends on the base:
          base <= 36: 0-9, a-z/A-Z (case insensitive, 10-35)
          base > 36:  0-9, a-z (10-35), A-Z (36-61), @ (62), _ (63)
        """
        if base < 2 or base > 64:
            raise SyntaxError(f"Invalid base {base} at position {start_pos}")

        result = 0
        num_len = 0
        out_of_range = False
        char = self.current_char()
        # Consume the whole run of base-digit characters ([0-9a-zA-Z@_], bash's
        # based-number alphabet) before validating, mirroring the octal reader:
        # an out-of-range digit must error, not silently end the token and leave
        # a stray trailing token. A char outside that alphabet ends the number.
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
        hex_digits = ''
        char = self.current_char()
        while char is not None and char in '0123456789abcdefABCDEF':
            hex_digits += char
            self.advance()
            char = self.current_char()
        if not hex_digits:
            raise SyntaxError(f"Invalid hex number at position {start_pos}")
        return int(hex_digits, 16)

    def _read_octal(self, start_pos: int) -> int:
        """Read an octal literal (leading 0); leading 0+digit already detected."""
        octal_digits = ''
        char = self.current_char()
        while char is not None and char in '01234567':
            octal_digits += char
            self.advance()
            char = self.current_char()
        # If we hit 8 or 9, it's an invalid octal digit (bash errors here).
        char = self.current_char()
        if char is not None and char in '89':
            # Read the rest of the digits so the error message shows the full token.
            while char is not None and char.isdigit():
                octal_digits += char
                self.advance()
                char = self.current_char()
            # octal_digits already includes the leading '0'; don't prepend
            # another one (bash reports e.g. "08", not "008").
            raise SyntaxError(
                f"{octal_digits}: value too great for base (error token is \"{octal_digits}\")"
            )
        return int(octal_digits, 8) if octal_digits else 0

    def read_decimal(self) -> int:
        """Read a decimal number"""
        num_str = ''
        char = self.current_char()
        while char is not None and char.isdigit():
            num_str += char
            self.advance()
            char = self.current_char()
        return int(num_str) if num_str else 0

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
                if self.peek_char() == '+':
                    self.tokens.append(ArithToken(ArithTokenType.INCREMENT, '++', start_pos))
                    self.advance()
                    self.advance()
                elif self.peek_char() == '=':
                    self.tokens.append(ArithToken(ArithTokenType.PLUS_ASSIGN, '+=', start_pos))
                    self.advance()
                    self.advance()
                else:
                    self.tokens.append(ArithToken(ArithTokenType.PLUS, '+', start_pos))
                    self.advance()

            elif char == '-':
                if self.peek_char() == '-':
                    self.tokens.append(ArithToken(ArithTokenType.DECREMENT, '--', start_pos))
                    self.advance()
                    self.advance()
                elif self.peek_char() == '=':
                    self.tokens.append(ArithToken(ArithTokenType.MINUS_ASSIGN, '-=', start_pos))
                    self.advance()
                    self.advance()
                else:
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
