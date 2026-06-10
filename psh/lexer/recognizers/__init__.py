"""Token recognizer system for modular lexing."""

from .base import TokenRecognizer
from .comment import CommentRecognizer
from .literal import LiteralRecognizer
from .operator import OperatorRecognizer
from .registry import RecognizerRegistry
from .whitespace import WhitespaceRecognizer

__all__ = [
    'TokenRecognizer',
    'OperatorRecognizer',
    'LiteralRecognizer',
    'WhitespaceRecognizer',
    'CommentRecognizer',
    'RecognizerRegistry',
]
