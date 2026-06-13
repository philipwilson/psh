"""AST node classes for shell arithmetic expressions."""

from dataclasses import dataclass

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
class AssignmentNode(ArithNode):
    """Assignment operation"""
    var_name: str
    op: ArithTokenType
    value: ArithNode


@dataclass
class PreIncrementNode(ArithNode):
    """Pre-increment/decrement (++var, --var)"""
    var_name: str
    is_increment: bool


@dataclass
class PostIncrementNode(ArithNode):
    """Post-increment/decrement (var++, var--)"""
    var_name: str
    is_increment: bool


@dataclass
class ArrayElementNode(ArithNode):
    """Array element reference (arr[index]).

    ``index`` is the parsed subscript expression (used for indexed arrays,
    which arithmetic-evaluate the subscript). ``index_text`` is the raw
    subscript source text (used verbatim as the key for associative arrays,
    where the subscript is a literal string, not an arithmetic expression).
    """
    name: str
    index: ArithNode
    index_text: str = ""


@dataclass
class ArrayAssignmentNode(ArithNode):
    """Assignment to an array element (arr[index] = value, arr[index] += value).

    See :class:`ArrayElementNode` for the meaning of ``index`` vs
    ``index_text``.
    """
    name: str
    index: ArithNode
    op: ArithTokenType
    value: ArithNode
    index_text: str = ""


@dataclass
class ArrayPreIncrementNode(ArithNode):
    """Pre-increment/decrement of an array element (++arr[i], --arr[i])."""
    name: str
    index: ArithNode
    is_increment: bool
    index_text: str = ""


@dataclass
class ArrayPostIncrementNode(ArithNode):
    """Post-increment/decrement of an array element (arr[i]++, arr[i]--)."""
    name: str
    index: ArithNode
    is_increment: bool
    index_text: str = ""
