"""AST node classes for shell arithmetic expressions."""

from dataclasses import dataclass
from typing import Optional

from .tokens import ArithTokenType


@dataclass
class ArithNode:
    """Base class for arithmetic AST nodes"""
    pass


@dataclass
class NumberNode(ArithNode):
    """Numeric literal"""
    value: int


@dataclass
class VariableNode(ArithNode):
    """Variable reference"""
    name: str


@dataclass
class UnaryOpNode(ArithNode):
    """Unary operation"""
    op: ArithTokenType
    operand: ArithNode


@dataclass
class BinaryOpNode(ArithNode):
    """Binary operation"""
    op: ArithTokenType
    left: ArithNode
    right: ArithNode


@dataclass
class TernaryNode(ArithNode):
    """Ternary conditional (?:)"""
    condition: ArithNode
    true_expr: ArithNode
    false_expr: ArithNode


@dataclass
class ArrayElementNode(ArithNode):
    """Array element READ (arr[index]).

    ``index`` is the parsed subscript expression (used for indexed arrays,
    which arithmetic-evaluate the subscript). ``index_text`` is the raw
    subscript source text (used verbatim as the key for associative arrays,
    where the subscript is a literal string, not an arithmetic expression).
    """
    name: str
    index: ArithNode
    index_text: str = ""


@dataclass
class LValue:
    """An assignable location: a scalar variable or an array element.

    Reifying the lvalue lets assignment and increment/decrement have ONE
    implementation each (scalar and array alike) instead of scalar/array
    twin nodes. ``subscript`` is ``None`` for a plain scalar (``x``); for an
    array element (``a[i]``) it is the parsed subscript expression
    (arithmetic-evaluated for indexed arrays) and ``subscript_text`` is the
    raw subscript source text (used verbatim as the key for associative
    arrays, whose subscripts are literal strings — see
    :class:`ArrayElementNode`).
    """
    name: str
    subscript: Optional[ArithNode] = None
    subscript_text: str = ""


@dataclass
class AssignmentNode(ArithNode):
    """Assignment to an lvalue (``x = v``, ``a[i] += v``).

    ``op`` is the assignment token (``ASSIGN`` or a compound ``*_ASSIGN``);
    the target scalar-vs-array distinction lives entirely in ``lvalue``.
    """
    lvalue: LValue
    op: ArithTokenType
    value: ArithNode


@dataclass
class IncDecNode(ArithNode):
    """Increment/decrement of an lvalue (``++x``, ``x--``, ``++a[i]``,
    ``a[i]--``). ``op`` is ``INCREMENT`` or ``DECREMENT``; ``prefix`` is
    ``True`` for the pre form (returns the new value) and ``False`` for the
    post form (returns the old value)."""
    lvalue: LValue
    op: ArithTokenType
    prefix: bool
