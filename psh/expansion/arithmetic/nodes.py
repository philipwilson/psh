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
    """Array element reference (arr[index])"""
    name: str
    index: ArithNode


@dataclass
class ArrayAssignmentNode(ArithNode):
    """Assignment to an array element (arr[index] = value, arr[index] += value)"""
    name: str
    index: ArithNode
    op: ArithTokenType
    value: ArithNode
