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

    ``index_text`` is the VERBATIM subscript source text (a SUBSCRIPT token's
    value). It is interpreted only at evaluation, by target kind: an
    associative array keys on it after quote removal; an indexed array (or a
    scalar / undeclared name) lazily parses it as arithmetic — the campaign W2
    subscript authority (see ``ArithmeticEvaluator._array_key``). Carrying
    text, not a parsed expression, is what lets ``$((h[a b]))`` key ``a b``
    without the subscript ever needing to lex as arithmetic (r21 A3).
    """
    name: str
    index_text: str


@dataclass
class LValue:
    """An assignable location: a scalar variable or an array element.

    Reifying the lvalue lets assignment and increment/decrement have ONE
    implementation each (scalar and array alike) instead of scalar/array
    twin nodes. ``subscript_text`` is ``None`` for a plain scalar (``x``);
    for an array element (``a[i]``) it is the verbatim subscript source text,
    interpreted at evaluation by target kind exactly like
    :class:`ArrayElementNode.index_text`.
    """
    name: str
    subscript_text: Optional[str] = None


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
