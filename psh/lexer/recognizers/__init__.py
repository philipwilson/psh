"""Token recognizer system for modular lexing."""

from .base import TokenRecognizer
from .comment import CommentRecognizer
from .literal import LiteralRecognizer
from .operator import OperatorRecognizer
from .operator_debris import OperatorDebrisWordRecognizer
from .registry import RecognizerRegistry
from .whitespace import WhitespaceRecognizer

__all__ = [
    'TokenRecognizer',
    'OperatorRecognizer',
    'LiteralRecognizer',
    'OperatorDebrisWordRecognizer',
    'WhitespaceRecognizer',
    'CommentRecognizer',
    'RecognizerRegistry',
]
