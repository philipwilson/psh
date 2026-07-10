"""Characterization + unit tests for OperatorDebrisWordRecognizer.

The operator-debris recognizer (Tier C-C3, review Ugly 9) is the promotion
of the lexer's old ``_handle_fallback_word`` step-4 fallback to a real,
named, lowest-priority recognizer in the registry. A census proved the
fallback was live for exactly four word-start characters — ``] + = [`` —
each producing bash-verified words with a deliberately LOOSER terminator
set than the literal recognizer (``= + [ ]`` do not terminate the word).

These tests freeze the EXACT token streams (type + value + offsets +
adjacency) for every census case so the promotion is a zero-behavior
refactor: byte-identical token streams before and after.
"""

from psh.lexer import tokenize
from psh.lexer.recognizers import OperatorDebrisWordRecognizer
from psh.lexer.state_context import LexerContext


def _stream(text):
    """Full token characterization: (type, value, start, end, adjacent)."""
    return [
        (t.type.name, t.value, t.position, t.end_position, t.adjacent_to_previous)
        for t in tokenize(text)
    ]


class TestCharacterizationCorpus:
    """Frozen token streams for every census case (bash-verified shapes)."""

    def test_test_command_brackets(self):
        # `[ x = y ]` — LBRACKET operator, then bare `=` and closing `]`
        # debris words.
        assert _stream('[ x = y ]') == [
            ('LBRACKET', '[', 0, 1, False),
            ('WORD', 'x', 2, 3, False),
            ('WORD', '=', 4, 5, False),
            ('WORD', 'y', 6, 7, False),
            ('WORD', ']', 8, 9, False),
            ('EOF', '', 9, 9, True),
        ]

    def test_sparse_array_element_prefix(self):
        # a=([1]=x z): the `]=x` is one debris word (looser terminators).
        assert _stream('a=([1]=x z)') == [
            ('WORD', 'a=', 0, 2, False),
            ('LPAREN', '(', 2, 3, True),
            ('LBRACKET', '[', 3, 4, True),
            ('WORD', '1', 4, 5, True),
            ('WORD', ']=x', 5, 8, True),
            ('WORD', 'z', 9, 10, False),
            ('RPAREN', ')', 10, 11, True),
            ('EOF', '', 11, 11, True),
        ]

    def test_closing_bracket_composite(self):
        # a]b — WORD 'a' + adjacent debris WORD ']b'.
        assert _stream('a]b') == [
            ('WORD', 'a', 0, 1, False),
            ('WORD', ']b', 1, 3, True),
            ('EOF', '', 3, 3, True),
        ]

    def test_plus_equals_append(self):
        # vars+=(x): WORD 'vars' + debris WORD '+='.
        assert _stream('vars+=(x)') == [
            ('WORD', 'vars', 0, 4, False),
            ('WORD', '+=', 4, 6, True),
            ('LPAREN', '(', 6, 7, True),
            ('WORD', 'x', 7, 8, True),
            ('RPAREN', ')', 8, 9, True),
            ('EOF', '', 9, 9, True),
        ]

    def test_set_plus_option(self):
        # set +x — '+x' is a single debris word.
        assert _stream('set +x') == [
            ('WORD', 'set', 0, 3, False),
            ('WORD', '+x', 4, 6, False),
            ('EOF', '', 6, 6, True),
        ]

    def test_regex_plus_group(self):
        # ([a-z]+): glob class `[a-z` is literal, `]+` is a debris word.
        assert _stream('([a-z]+)') == [
            ('LPAREN', '(', 0, 1, False),
            ('LBRACKET', '[', 1, 2, True),
            ('WORD', 'a-z', 2, 5, True),
            ('WORD', ']+', 5, 7, True),
            ('RPAREN', ')', 7, 8, True),
            ('EOF', '', 8, 8, True),
        ]

    def test_bare_equals_in_test(self):
        assert _stream('[ a = b ]') == [
            ('LBRACKET', '[', 0, 1, False),
            ('WORD', 'a', 2, 3, False),
            ('WORD', '=', 4, 5, False),
            ('WORD', 'b', 6, 7, False),
            ('WORD', ']', 8, 9, False),
            ('EOF', '', 9, 9, True),
        ]

    def test_assignment_continuation(self):
        # a=b=c: WORD 'a=b' + adjacent debris WORD '=c'.
        assert _stream('a=b=c') == [
            ('WORD', 'a=b', 0, 3, False),
            ('WORD', '=c', 3, 5, True),
            ('EOF', '', 5, 5, True),
        ]

    def test_echo_closing_bracket(self):
        assert _stream('echo ]') == [
            ('WORD', 'echo', 0, 4, False),
            ('WORD', ']', 5, 6, False),
            ('EOF', '', 6, 6, True),
        ]

    def test_case_glob_class(self):
        # The `[0-9]*` glob class is collected by the literal recognizer
        # (a single WORD), NOT the debris recognizer — pinned here so a
        # future change that routes it through debris is caught.
        assert _stream('case 5 in [0-9]*) echo d;; esac') == [
            ('CASE', 'case', 0, 4, False),
            ('WORD', '5', 5, 6, False),
            ('IN', 'in', 7, 9, False),
            ('WORD', '[0-9]*', 10, 16, False),
            ('RPAREN', ')', 16, 17, True),
            ('WORD', 'echo', 18, 22, False),
            ('WORD', 'd', 23, 24, False),
            ('DOUBLE_SEMICOLON', ';;', 24, 26, True),
            ('ESAC', 'esac', 27, 31, False),
            ('EOF', '', 31, 31, True),
        ]


class TestNotStolenByDebris:
    """The debris recognizer is LAST: operator/literal words win first."""

    def test_double_bracket_operator(self):
        # `[[ -f x ]]` must use DOUBLE_LBRACKET/DOUBLE_RBRACKET operators,
        # not be stolen by the debris recognizer.
        stream = _stream('[[ -f x ]]')
        types = [t[0] for t in stream]
        assert 'DOUBLE_LBRACKET' in types
        assert 'DOUBLE_RBRACKET' in types

    def test_plain_single_bracket_is_operator(self):
        # A standalone `[` at command position is the LBRACKET operator.
        assert _stream('[ x ]')[0] == ('LBRACKET', '[', 0, 1, False)


class TestCanRecognizeDomain:
    """can_recognize accepts exactly the four census-verified starts."""

    def setup_method(self):
        self.rec = OperatorDebrisWordRecognizer()
        self.ctx = LexerContext()

    def test_accepts_the_four_starts(self):
        for ch in ']+=[':
            assert self.rec.can_recognize(ch, 0, self.ctx) is True, ch

    def test_combined_starts(self):
        # ']+=[' — every position is an accepted debris start.
        text = ']+=['
        for pos in range(len(text)):
            assert self.rec.can_recognize(text, pos, self.ctx) is True

    def test_rejects_other_starts(self):
        for ch in 'abc0_-<>&|;(){}!#$`"\' \t.':
            assert self.rec.can_recognize(ch, 0, self.ctx) is False, ch

    def test_rejects_past_end(self):
        assert self.rec.can_recognize('=', 1, self.ctx) is False
        assert self.rec.can_recognize('', 0, self.ctx) is False


class TestRecognizeTerminators:
    """The collect loop's looser terminator set."""

    def setup_method(self):
        self.rec = OperatorDebrisWordRecognizer()
        self.ctx = LexerContext()

    def _recognize(self, text, pos=0):
        return self.rec.recognize(text, pos, self.ctx)

    def test_does_not_terminate_on_equals_plus_brackets(self):
        # `]=+[x` — none of = + [ ] terminate; reads to end.
        token, new_pos = self._recognize(']=+[x')
        assert token.value == ']=+[x'
        assert new_pos == 5

    def test_terminates_on_whitespace(self):
        token, new_pos = self._recognize(']foo bar')
        assert token.value == ']foo'
        assert new_pos == 4

    def test_terminates_on_hard_operators(self):
        for op in '<>&|;(){}!':
            token, new_pos = self._recognize(f']x{op}y')
            assert token.value == ']x', op
            assert new_pos == 2, op

    def test_terminates_on_quote_expansion_starters(self):
        for q in '$`"\'':
            token, new_pos = self._recognize(f']x{q}y')
            assert token.value == ']x', q
            assert new_pos == 2, q

    def test_returns_word_token(self):
        token, _ = self._recognize('=')
        assert token.type.name == 'WORD'
        assert token.value == '='
        assert token.position == 0
        assert token.end_position == 1

    def test_position_offset_honored(self):
        # Start partway through the string.
        token, new_pos = self._recognize('xy]=z', pos=2)
        assert token.value == ']=z'
        assert token.position == 2
        assert token.end_position == 5
        assert new_pos == 5


class TestDispatchOrdering:
    """Debris must be tried strictly LAST of any recognizer."""

    def test_debris_is_last_in_dispatch_order(self):
        from psh.lexer import ModularLexer

        recognizers = ModularLexer('').registry.get_recognizers()
        assert isinstance(recognizers[-1], OperatorDebrisWordRecognizer)
        # It comes after the literal recognizer, which otherwise claims words.
        types = [type(r).__name__ for r in recognizers]
        assert types.index('OperatorDebrisWordRecognizer') > \
            types.index('LiteralRecognizer')
