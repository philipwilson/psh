"""Phase 2 safety fix: the recognizer registry surfaces recognizer defects.

Recognizers are contracted to return None when they can't handle the input.
A raised exception signals a bug, and must propagate (with context) rather
than being swallowed and silently mis-tokenizing.
"""

import pytest

from psh.lexer.recognizers.base import TokenRecognizer
from psh.lexer.recognizers.registry import RecognizerRegistry


class _BoomRecognizer(TokenRecognizer):
    def can_recognize(self, input_text, pos, context):
        return True

    def recognize(self, input_text, pos, context):
        raise KeyError("internal defect")


class _NoneRecognizer(TokenRecognizer):
    """Well-behaved recognizer that simply doesn't match."""

    def can_recognize(self, input_text, pos, context):
        return True

    def recognize(self, input_text, pos, context):
        return None


def test_recognizer_exception_propagates_with_context():
    reg = RecognizerRegistry()
    reg.register(_BoomRecognizer())
    with pytest.raises(RuntimeError) as exc:
        reg.recognize("x", 0, None)
    msg = str(exc.value)
    assert "_BoomRecognizer" in msg
    assert "position 0" in msg
    # Original cause is chained.
    assert isinstance(exc.value.__cause__, KeyError)


def test_non_matching_recognizer_returns_none():
    reg = RecognizerRegistry()
    reg.register(_NoneRecognizer())
    assert reg.recognize("x", 0, None) is None
