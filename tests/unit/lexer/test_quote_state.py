"""Unit tests for the shared QuoteState scanner primitive.

QuoteState encapsulates the single/double-quote + backslash-escape state machine
that the array-assignment collectors in the literal recognizer previously each
reimplemented.
"""


from psh.lexer.pure_helpers import QuoteState


def active_mask(text, **kw):
    """Return the list of booleans QuoteState yields for each char of text."""
    state = QuoteState(**kw)
    return [state.consume(c) for c in text]


class TestQuoteState:
    def test_plain_text_all_active(self):
        assert active_mask("abc") == [True, True, True]

    def test_single_quotes_inactive(self):
        # 'a' : quote, a(quoted), quote  -> all inactive
        assert active_mask("'a'") == [False, False, False]

    def test_double_quotes_inactive(self):
        assert active_mask('"a"') == [False, False, False]

    def test_active_resumes_after_quote(self):
        # x 'q' y  ->  x active, quote/q/quote inactive, y active
        assert active_mask("x'q'y") == [True, False, False, False, True]

    def test_backslash_escape_inactive(self):
        # \a b -> backslash inactive, a (escaped) inactive, space active, b active
        assert active_mask("\\a b") == [False, False, True, True]

    def test_backslash_literal_in_single_quotes(self):
        # Inside single quotes a backslash is literal (default), so the char
        # after it is NOT treated as escaped — but both stay inactive (quoted).
        assert active_mask("'\\'") == [False, False, False]

    def test_backslash_escape_everywhere_when_configured(self):
        state = QuoteState(backslash_literal_in_single=False)
        # Inside single quotes, \ now starts an escape.
        roles = [state.consume(c) for c in "'\\a'"]
        assert roles == [False, False, False, False]

    def test_double_quote_inside_single_is_literal(self):
        # " inside '...' is just a quoted char, doesn't open a double quote.
        s = QuoteState()
        s.consume("'")
        assert s.in_single is True
        s.consume('"')          # literal inside single quote
        assert s.in_double is False
        assert s.in_quotes is True

    def test_in_quotes_property(self):
        s = QuoteState()
        assert s.in_quotes is False
        s.consume('"')
        assert s.in_quotes is True
        s.consume('"')
        assert s.in_quotes is False
