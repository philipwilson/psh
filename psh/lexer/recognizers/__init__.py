"""Token recognizer system for modular lexing."""

from .base import TokenRecognizer
from .comment import CommentRecognizer
from .literal import LiteralRecognizer
from .operator import OperatorRecognizer
from .operator_debris import OperatorDebrisWordRecognizer
from .registry import RecognizerRegistry

__all__ = [
    'TokenRecognizer',
    'OperatorRecognizer',
    'LiteralRecognizer',
    'OperatorDebrisWordRecognizer',
    'CommentRecognizer',
    'RecognizerRegistry',
]
