"""Token types and token dataclass for shell arithmetic expressions."""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Union


class ArithTokenType(Enum):
    """Token types for arithmetic expressions"""
    NUMBER = auto()
    IDENTIFIER = auto()

    # Arithmetic operators
    PLUS = auto()
    MINUS = auto()
    MULTIPLY = auto()
    DIVIDE = auto()
    MODULO = auto()
    POWER = auto()

    # Comparison operators
    LT = auto()
    GT = auto()
    LE = auto()
    GE = auto()
    EQ = auto()
    NE = auto()

    # Logical operators
    AND = auto()
    OR = auto()
    NOT = auto()

    # Bitwise operators
    BIT_AND = auto()
    BIT_OR = auto()
    BIT_XOR = auto()
    BIT_NOT = auto()
    LSHIFT = auto()
    RSHIFT = auto()

    # Assignment operators
    ASSIGN = auto()
    PLUS_ASSIGN = auto()
    MINUS_ASSIGN = auto()
    MULTIPLY_ASSIGN = auto()
    DIVIDE_ASSIGN = auto()
    MODULO_ASSIGN = auto()
    LSHIFT_ASSIGN = auto()
    RSHIFT_ASSIGN = auto()
    BIT_AND_ASSIGN = auto()
    BIT_OR_ASSIGN = auto()
    BIT_XOR_ASSIGN = auto()

    # Other operators
    QUESTION = auto()
    COLON = auto()
    COMMA = auto()

    # Increment/decrement
    INCREMENT = auto()
    DECREMENT = auto()

    # Delimiters
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()

    # An array subscript captured VERBATIM (value = the raw text between the
    # balanced brackets). Emitted only when `[` immediately follows an
    # IDENTIFIER (bash: `h [k]` is not a subscript); the content is NOT
    # arithmetic-tokenized here — an associative target keys on the raw text
    # (after quote removal) and an indexed target lazily parses it as
    # arithmetic at evaluation (campaign W2 / r21 A3).
    SUBSCRIPT = auto()

    # End of input
    EOF = auto()


@dataclass
class ArithToken:
    """Arithmetic token with type and value"""
    type: ArithTokenType
    value: Union[str, int]
    position: int
