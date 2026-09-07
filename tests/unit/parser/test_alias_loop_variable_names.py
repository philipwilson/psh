"""A loop variable NAME comes from the token, never from a foreign slice (C010).

A token's span indexes THE TEXT THE LEXER SAW. Alias expansion breaks the
assumption that the parser's ``source_text`` is that text: the tokens come from
the alias body while ``source_text`` is the pre-expansion line, so the span
still slices — the wrong string. That is how::

    shopt -s expand_aliases; alias beg='for i in 1 2; do'
    beg echo "i=[$i]"; done

bound ``e`` (the character at ``beg echo …``[4:5]) instead of ``i`` and the body
saw an empty ``$i``.

The behavioural pins live in
``tests/conformance/bash/test_alias_loop_variable_conformance.py``. This module
pins the PARSER-level invariant directly, on a SYNTHETIC mismatch — tokens lexed
from one string handed to a parser told the source is another — so the guard
holds even if the alias seam is later reshaped.
"""

import pytest

from psh.ast_nodes import ForLoop, SelectLoop
from psh.lexer import tokenize
from psh.lexer.token_types import Token, TokenType, slice_renders_token, token_lexeme
from psh.parser import create_parser

# The two strings that alias expansion drives apart. Positions in EXPANDED_FOR
# are meaningless in ALIAS_LINE: [4,5) is 'i' in one and 'e' in the other, which
# is the exact corruption C010 reported.
ALIAS_LINE = 'beg echo "i=[$i]"; done'
EXPANDED_FOR = 'for i in 1 2; do echo "i=[$i]"; done'
EXPANDED_SELECT = 'select v in a b; do echo "v=[$v]"; break; done'


def _parse(text, source_text, parser="rd"):
    """Parse *text*'s tokens while telling the parser the source is another string."""
    return create_parser(tokenize(text), active_parser=parser,
                         source_text=source_text).parse()


def _loop(program):
    """The single loop node in a parsed one-statement program.

    Unwraps the Program -> AndOrList -> Pipeline layers the root always builds
    around a bare compound command.
    """
    node = program.statements[0].pipelines[0].commands[0]
    assert isinstance(node, (ForLoop, SelectLoop)), f"not a loop: {node!r}"
    return node


class TestLoopVariableIsTheTokensOwnName:
    """ForLoop/SelectLoop.variable is the token's value, whatever source_text says."""

    def test_for_variable_survives_a_foreign_source_text(self):
        loop = _loop(_parse(EXPANDED_FOR, ALIAS_LINE))
        assert isinstance(loop, ForLoop)
        # The offending slice, spelled out: the old derivation returned this.
        assert ALIAS_LINE[4:5] == "e"
        assert loop.variable == "i"

    def test_select_variable_survives_a_foreign_source_text(self):
        loop = _loop(_parse(EXPANDED_SELECT, "sel echo \"v=[$v]\"; break; done"))
        assert isinstance(loop, SelectLoop)
        assert loop.variable == "v"

    def test_for_variable_matches_with_no_source_text_at_all(self):
        assert _loop(_parse(EXPANDED_FOR, None)).variable == "i"

    def test_both_parsers_agree_on_the_alias_expanded_stream(self):
        """The combinator parser never had source_text to slice; RD now agrees."""
        rd = _loop(_parse(EXPANDED_FOR, ALIAS_LINE, parser="rd"))
        comb = _loop(_parse(EXPANDED_FOR, ALIAS_LINE, parser="combinator"))
        assert rd.variable == comb.variable == "i"

    def test_matching_source_text_still_gives_the_raw_spelling(self):
        """A truthful source_text keeps bash's raw-spelling diagnostic subject."""
        src = 'for "in" in a; do :; done'
        assert _loop(_parse(src, src)).variable == '"in"'


class TestSliceRendersToken:
    """The predicate that decides whether a span may speak for a token."""

    def test_accepts_the_span_of_the_text_the_token_came_from(self):
        src = 'for i in 1 2; do :; done'
        assert slice_renders_token(tokenize(src)[1], src)

    def test_rejects_a_span_read_out_of_a_different_string(self):
        """The synthetic offender: the C010 corruption, isolated."""
        tok = tokenize(EXPANDED_FOR)[1]
        assert tok.value == "i"
        assert not slice_renders_token(tok, ALIAS_LINE)
        assert token_lexeme(tok, ALIAS_LINE) == "i"

    def test_rejects_a_span_that_runs_past_the_end_of_the_source(self):
        """An alias longer than its name puts the span outside the short line."""
        tok = tokenize('for longvariablename in 1; do :; done')[1]
        assert not slice_renders_token(tok, "b echo x")
        assert token_lexeme(tok, "b echo x") == "longvariablename"

    @pytest.mark.parametrize("subject,expected", [
        ('"in"', '"in"'),          # STRING re-wrapped from quote_type
        ("'in'", "'in'"),
        ('$v', '$v'),              # VARIABLE restores the $
        ('${v}', '${v}'),
        ('a"b"c', 'a"b"c'),        # fused WORD keeps its own quotes in value
        ('1x', '1x'),
    ])
    def test_faithful_spans_are_accepted_and_returned_verbatim(self, subject, expected):
        src = f'for {subject} in a; do :; done'
        tok = tokenize(src)[1]
        assert slice_renders_token(tok, src)
        assert token_lexeme(tok, src) == expected

    @pytest.mark.parametrize("subject", ['"a\\\\b"', "$'\\x41'"])
    def test_escape_bearing_quoted_spans_keep_the_source_escapes(self, subject):
        """The slice branch earns its keep: bash prints `"a\\\\b"' for `for "a\\\\b"'.

        The lexer's stored value has the escape processed away, so only the
        span can spell it back — which is why the fix VERIFIES the span rather
        than abandoning it.
        """
        src = f'for {subject} in a; do :; done'
        tok = tokenize(src)[1]
        assert slice_renders_token(tok, src)
        assert token_lexeme(tok, src) == subject
        assert token_lexeme(tok) != subject  # the reconstruction cannot

    def test_zero_width_span_is_never_a_rendering(self):
        tok = Token(TokenType.WORD, "i", position=4, end_position=4)
        assert not slice_renders_token(tok, ALIAS_LINE)
        assert token_lexeme(tok, ALIAS_LINE) == "i"
