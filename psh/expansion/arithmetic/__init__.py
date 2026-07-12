"""Arithmetic expression evaluator for shell arithmetic expansion $((...)).

This package was decomposed from a single ``arithmetic.py`` module. The public
surface re-exported here is a superset of everything that was importable from
the old module, so existing imports such as
``from psh.expansion.arithmetic import evaluate_arithmetic`` keep working.

Module layout:
  tokens.py     — ArithTokenType, ArithToken
  tokenizer.py  — ArithTokenizer
  nodes.py      — ArithNode AST hierarchy
  parser.py     — ArithParser (recursive descent)
  errors.py     — ShellArithmeticError / ArithmeticError, _to_signed64
  evaluator.py  — ArithmeticEvaluator + evaluate_arithmetic /
                  execute_arithmetic_expansion entry points
"""

from .errors import ArithmeticError, ShellArithmeticError
from .evaluator import (
    ArithmeticEvaluator,
    arithmetic_expansion_value,
    evaluate_arithmetic,
    execute_arithmetic_expansion,
)
from .nodes import (
    ArithNode,
    ArrayAssignmentNode,
    ArrayElementNode,
    ArrayPostIncrementNode,
    ArrayPreIncrementNode,
    AssignmentNode,
    BinaryOpNode,
    NumberNode,
    PostIncrementNode,
    PreIncrementNode,
    TernaryNode,
    UnaryOpNode,
    VariableNode,
)
from .parser import ArithParser
from .tokenizer import ArithTokenizer
from .tokens import ArithToken, ArithTokenType

__all__ = [
    # Entry points
    "evaluate_arithmetic",
    "execute_arithmetic_expansion",
    "arithmetic_expansion_value",
    # Errors
    "ArithmeticError",
    "ShellArithmeticError",
    # Tokens
    "ArithToken",
    "ArithTokenType",
    # Tokenizer / parser / evaluator
    "ArithTokenizer",
    "ArithParser",
    "ArithmeticEvaluator",
    # AST nodes
    "ArithNode",
    "NumberNode",
    "VariableNode",
    "UnaryOpNode",
    "BinaryOpNode",
    "TernaryNode",
    "AssignmentNode",
    "PreIncrementNode",
    "PostIncrementNode",
    "ArrayElementNode",
    "ArrayAssignmentNode",
    "ArrayPreIncrementNode",
    "ArrayPostIncrementNode",
]
