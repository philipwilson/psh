"""
Unit tests for Word helper properties.

Tests the is_quoted, is_unquoted_literal, is_variable_expansion,
has_expansion_parts, has_unquoted_expansion, and effective_quote_char
properties on the Word AST node.
"""

from psh.ast_nodes import (
    ArithmeticExpansion,
    CommandSubstitution,
    ExpansionPart,
    LiteralPart,
    ParameterExpansion,
    VariableExpansion,
    Word,
)


class TestIsQuoted:
    """Tests for Word.is_quoted property."""

    def test_single_quoted_word(self):
        word = Word(parts=[LiteralPart("hello", quoted=True, quote_char="'")])
        assert word.is_quoted is True

    def test_double_quoted_word(self):
        word = Word(parts=[LiteralPart("hello", quoted=True, quote_char='"')])
        assert word.is_quoted is True

    def test_ansi_c_quoted_word(self):
        word = Word(parts=[LiteralPart("hello", quoted=True, quote_char="$'")])
        assert word.is_quoted is True

    def test_unquoted_word(self):
        word = Word(parts=[LiteralPart("hello")])
        assert word.is_quoted is False

    def test_single_part_quoted(self):
        """Single-part word where the part itself is quoted."""
        word = Word(parts=[LiteralPart("hello", quoted=True, quote_char="'")])
        assert word.is_quoted is True

    def test_multi_part_unquoted(self):
        """Multi-part composite word with no quote_type."""
        word = Word(parts=[
            LiteralPart("hello"),
            ExpansionPart(VariableExpansion("USER")),
        ])
        assert word.is_quoted is False


class TestIsUnquotedLiteral:
    """Tests for Word.is_unquoted_literal property."""

    def test_plain_word(self):
        word = Word(parts=[LiteralPart("hello")])
        assert word.is_unquoted_literal is True

    def test_quoted_word(self):
        word = Word(parts=[LiteralPart("hello", quoted=True, quote_char="'")])
        assert word.is_unquoted_literal is False

    def test_word_with_expansion(self):
        word = Word(parts=[ExpansionPart(VariableExpansion("HOME"))])
        assert word.is_unquoted_literal is False

    def test_multi_part_word(self):
        word = Word(parts=[
            LiteralPart("hello"),
            LiteralPart("world"),
        ])
        assert word.is_unquoted_literal is False

    def test_single_quoted_part(self):
        word = Word(parts=[LiteralPart("hello", quoted=True, quote_char="'")])
        assert word.is_unquoted_literal is False

    def test_empty_word(self):
        word = Word(parts=[])
        assert word.is_unquoted_literal is True


class TestIsVariableExpansion:
    """Tests for Word.is_variable_expansion property."""

    def test_simple_variable(self):
        word = Word(parts=[ExpansionPart(VariableExpansion("HOME"))])
        assert word.is_variable_expansion is True

    def test_parameter_expansion(self):
        word = Word(parts=[ExpansionPart(ParameterExpansion("HOME"))])
        assert word.is_variable_expansion is True

    def test_command_substitution(self):
        word = Word(parts=[ExpansionPart(CommandSubstitution(source="echo hi"))])
        assert word.is_variable_expansion is False

    def test_arithmetic_expansion(self):
        word = Word(parts=[ExpansionPart(ArithmeticExpansion("1+1"))])
        assert word.is_variable_expansion is False

    def test_literal_word(self):
        word = Word(parts=[LiteralPart("hello")])
        assert word.is_variable_expansion is False

    def test_multi_part_with_variable(self):
        """Multi-part word is not a single variable expansion."""
        word = Word(parts=[
            ExpansionPart(VariableExpansion("HOME")),
            LiteralPart("/bin"),
        ])
        assert word.is_variable_expansion is False


class TestHasExpansionParts:
    """Tests for Word.has_expansion_parts property."""

    def test_word_with_expansion(self):
        word = Word(parts=[ExpansionPart(VariableExpansion("HOME"))])
        assert word.has_expansion_parts is True

    def test_word_without_expansion(self):
        word = Word(parts=[LiteralPart("hello")])
        assert word.has_expansion_parts is False

    def test_mixed_word(self):
        word = Word(parts=[
            LiteralPart("prefix"),
            ExpansionPart(VariableExpansion("VAR")),
            LiteralPart("suffix"),
        ])
        assert word.has_expansion_parts is True


class TestHasUnquotedExpansion:
    """Tests for Word.has_unquoted_expansion property."""

    def test_unquoted_expansion(self):
        word = Word(parts=[ExpansionPart(VariableExpansion("HOME"), quoted=False)])
        assert word.has_unquoted_expansion is True

    def test_quoted_expansion(self):
        word = Word(parts=[ExpansionPart(VariableExpansion("HOME"), quoted=True, quote_char='"')])
        assert word.has_unquoted_expansion is False

    def test_no_expansion(self):
        word = Word(parts=[LiteralPart("hello")])
        assert word.has_unquoted_expansion is False

    def test_mixed_quoted_unquoted(self):
        word = Word(parts=[
            ExpansionPart(VariableExpansion("A"), quoted=True, quote_char='"'),
            ExpansionPart(VariableExpansion("B"), quoted=False),
        ])
        assert word.has_unquoted_expansion is True


class TestEffectiveQuoteChar:
    """Tests for Word.effective_quote_char property."""

    def test_single_quoted(self):
        word = Word(parts=[LiteralPart("hello", quoted=True, quote_char="'")])
        assert word.effective_quote_char == "'"

    def test_double_quoted(self):
        word = Word(parts=[LiteralPart("hello", quoted=True, quote_char='"')])
        assert word.effective_quote_char == '"'

    def test_ansi_c_quoted(self):
        word = Word(parts=[LiteralPart("hello", quoted=True, quote_char="$'")])
        assert word.effective_quote_char == "$'"

    def test_unquoted(self):
        word = Word(parts=[LiteralPart("hello")])
        assert word.effective_quote_char is None

    def test_single_part_with_quote_char(self):
        word = Word(parts=[LiteralPart("hello", quoted=True, quote_char="'")])
        assert word.effective_quote_char == "'"

    def test_multi_part_no_quote(self):
        word = Word(parts=[
            LiteralPart("hello"),
            LiteralPart("world"),
        ])
        assert word.effective_quote_char is None


class TestWordTextMethods:
    """Tests for source_text / display_text / to_literal_string.

    source_text re-wraps in the word's quote chars (and is what __str__
    returns); display_text is the flattened pre-expansion text with no
    re-wrap; to_literal_string is the quote-removed literal value.
    """

    def test_composite_with_expansion(self):
        # a"b"$c — composite of literal, quoted literal, and expansion.
        word = Word(parts=[
            LiteralPart("a"),
            LiteralPart("b", quoted=True, quote_char='"'),
            ExpansionPart(VariableExpansion("c")),
        ])
        # display_text: flattened parts, no whole-word re-wrap.
        assert word.display_text() == "ab$c"
        # source_text == display_text when there is no whole-word quote_type.
        assert word.source_text() == "ab$c"
        assert str(word) == "ab$c"
        # to_literal_string renders the expansion as its $-source too.
        assert word.to_literal_string() == "ab$c"

    def test_single_quoted_word(self):
        word = Word(parts=[LiteralPart("a b", quoted=True, quote_char="'")])
        # source_text re-wraps in the single quotes.
        assert word.source_text() == "'a b'"
        assert str(word) == "'a b'"
        # display_text does NOT re-wrap.
        assert word.display_text() == "a b"
        # to_literal_string is the quote-removed literal.
        assert word.to_literal_string() == "a b"

    def test_double_quoted_word(self):
        # Uniformly double-quoted: both parts carry the quote, so the
        # whole-word quote_type derives to '"' (the parsers build it so).
        word = Word(parts=[
            LiteralPart("a ", quoted=True, quote_char='"'),
            ExpansionPart(VariableExpansion("x"), quoted=True, quote_char='"'),
        ])
        # source_text re-wraps in the double quotes.
        assert word.source_text() == '"a $x"'
        assert str(word) == '"a $x"'
        # display_text is the flattened text without the wrapping quotes.
        assert word.display_text() == "a $x"
        # to_literal_string: quotes removed, expansion as $-source.
        assert word.to_literal_string() == "a $x"

    def test_str_delegates_to_source_text(self):
        word = Word(parts=[LiteralPart("hi", quoted=True, quote_char="'")])
        assert str(word) == word.source_text()
