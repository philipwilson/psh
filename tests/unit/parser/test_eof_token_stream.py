"""Regression tests for EOF-safe parser token-stream semantics.

Appraisal finding 4: the parser is a public API taking ``List[Token]`` but
``ParserContext.peek()`` used to echo the last real token past the end of the
list, so a sentinel-free stream never reached EOF and both ``at_end()`` and
``advance()`` stalled — ``Parser([one_word]).parse()`` hung forever.

The parse cases run in a daemon thread with a bounded join so a nontermination
regression FAILS (bounded) instead of hanging the whole suite. We deliberately
do not depend on the pytest-timeout plugin being active.
"""

import threading

import pytest

from psh.lexer import tokenize
from psh.lexer.token_types import Token, TokenType
from psh.parser.recursive_descent.context import ParserContext
from psh.parser.recursive_descent.parser import Parser


def _parse_bounded(tokens, timeout=5.0):
    """Parse ``tokens`` in a daemon thread; fail (not hang) on nontermination."""
    result = {}

    def target():
        try:
            result["program"] = Parser(list(tokens)).parse()
        except BaseException as exc:  # noqa: BLE001 - surface any failure to assert
            result["error"] = exc

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout)
    assert not t.is_alive(), "parser did not terminate on the given token stream"
    if "error" in result:
        raise result["error"]
    return result["program"]


class TestSentinelFreeStreamsTerminate:
    def test_single_word_without_eof_terminates(self):
        # The historic hang: one ordinary token, no trailing EOF sentinel.
        program = _parse_bounded([Token(TokenType.WORD, "echo", 0)])
        assert len(program.statements) == 1

    def test_multi_word_without_eof_terminates(self):
        program = _parse_bounded([
            Token(TokenType.WORD, "echo", 0, end_position=4),
            Token(TokenType.WORD, "hi", 5, end_position=7),
        ])
        assert len(program.statements) == 1

    def test_control_structure_without_eof_terminates(self):
        toks = [t for t in tokenize("if true; then echo hi; fi")
                if t.type != TokenType.EOF]
        program = _parse_bounded(toks)
        assert len(program.statements) == 1

    def test_empty_token_list_terminates(self):
        program = _parse_bounded([])
        assert program.statements == []

    def test_eof_only_terminates(self):
        program = _parse_bounded([Token(TokenType.EOF, "", 0)])
        assert program.statements == []


class TestEofTerminatedStreamsUnchanged:
    def test_normal_input_unchanged(self):
        program = _parse_bounded(tokenize("echo hi"))
        assert len(program.statements) == 1


class TestParserContextEndDiscipline:
    def _ctx(self):
        return ParserContext(tokens=[
            Token(TokenType.WORD, "echo", 0, end_position=4),
            Token(TokenType.WORD, "hi", 5, end_position=7),
        ])

    def test_out_of_range_peek_is_synthetic_eof(self):
        ctx = self._ctx()
        # Past the end of a sentinel-free stream => synthetic EOF, not the
        # last real token echoed back.
        past = ctx.peek(10)
        assert past.type == TokenType.EOF
        assert past is not ctx.tokens[-1]
        # Stable: repeated past-end peeks return the same object.
        assert ctx.peek(11) is past

    def test_at_end_true_past_last_token(self):
        ctx = self._ctx()
        assert not ctx.at_end()
        ctx.advance()
        assert not ctx.at_end()
        ctx.advance()  # now current == len(tokens)
        assert ctx.at_end()

    def test_advance_may_reach_len(self):
        ctx = self._ctx()
        ctx.advance()
        ctx.advance()
        assert ctx.current == len(ctx.tokens)
        # Further advances park at the end and return synthetic EOF.
        tok = ctx.advance()
        assert tok.type == TokenType.EOF
        assert ctx.current == len(ctx.tokens)

    def test_negative_peek_rejected(self):
        ctx = self._ctx()
        with pytest.raises(IndexError):
            ctx.peek(-1)

    def test_eof_terminated_at_end_on_eof_token(self):
        ctx = ParserContext(tokens=[
            Token(TokenType.WORD, "echo", 0, end_position=4),
            Token(TokenType.EOF, "", 4),
        ])
        assert not ctx.at_end()
        ctx.advance()
        assert ctx.at_end()  # parked on the explicit EOF token
